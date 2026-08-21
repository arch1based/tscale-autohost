# -*- coding: utf-8 -*-
"""
Aftomati enimerosi zygon (ICSautoScaleUpdater) - daemon gia Windows.

Roi ergasias:
  Vima 1 : parakolouthisi tou arxeiou pou vgazei to ERP -> dimiourgia host1/host2
  Vima 2 : metatropi (CNV script) me kanones pou fainontai kai allazoun apo to GUI
  Vima 3 : eksagogi arxeiou proionton (product.csv i .txt)
  Vima 4 : ekkinisi tis efarmogis tou zygou (AutoProcess i alli) gia X deuterolepta
"""

import os
import re
import sys
import hashlib
import csv
import json
import time
import shutil
import threading
import traceback
import subprocess
import datetime

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext

APP_NAME = "Αυτόματη ενημέρωση ζυγών"      # τι βλέπει ο χρήστης
APP_ID = "ICSautoScaleUpdater"             # όνομα exe / registry / φακέλων
APP_BUILD = "1.0.4"                        # σύγκριση για ενημερώσεις
APP_VERSION = "ICSautoScaleUpdater · έκδοση %s — Θεσσαλονίκη, Αύγουστος 2026" % APP_BUILD
UPDATE_VERSION_URL = "https://raw.githubusercontent.com/arch1based/tscale-autohost/main/VERSION"
UPDATE_PAGE_URL = "https://github.com/arch1based/tscale-autohost"
UPDATE_API_URL = "https://api.github.com/repos/arch1based/tscale-autohost/releases/latest"
UPDATE_ASSET = "ICSautoScaleUpdater.exe"
# Κωδικός τεχνικού για ενημέρωση (αποτρέπει να την τρέξει προσωπικό του καταστήματος).
# Είναι φραγμός κατά λάθους χειρισμού, όχι κρυπτογραφική ασφάλεια.
UPDATE_PASSWORD_SHA256 = "e78f27ab3ef177a9926e6b90e572b9853ce6cf4d87512836e9ae85807ec9d7fe"
COLORS = {
    "bg":      "#eef2f7",   # φόντο παραθύρου
    "card":    "#ffffff",   # κάρτες / καρτέλες
    "ink":     "#0f172a",   # βασικό κείμενο
    "muted":   "#64748b",   # δευτερεύον κείμενο
    "line":    "#dbe3ec",   # περιγράμματα
    "brand":   "#1a8fd1",   # μπλε ICS
    "brand_d": "#127ab7",
    "ok":      "#12a150",
    "warn":    "#e08c00",
    "err":     "#dc2626",
    "console": "#0f1b2b",
    "console_fg": "#d7e3f4",
}

APP_VENDOR = "ICS — ΚΑΡΑΦΥΛΛΗΣ ΣΥΣΤΗΜΑΤΑ ΠΛΗΡΟΦΟΡΙΚΗΣ"
APP_DIR = os.path.dirname(os.path.abspath(__file__))
SINGLETON_PORT = 49731
_singleton_sock = None


def claim_single_instance():
    """True αν είμαστε το μοναδικό αντίγραφο. Κρατάει τη θύρα όσο ζει η εφαρμογή."""
    global _singleton_sock
    import socket
    sk = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sk.bind(("127.0.0.1", SINGLETON_PORT))
        sk.listen(1)
        _singleton_sock = sk
        return True
    except OSError:
        sk.close()
        return False


def wake_running_instance(timeout=3.0):
    """Λέει στο αντίγραφο που ήδη τρέχει να εμφανιστεί. True αν απάντησε."""
    import socket
    try:
        with socket.create_connection(("127.0.0.1", SINGLETON_PORT), timeout) as c:
            c.sendall(b"SHOW")
            c.settimeout(timeout)
            return c.recv(16) == b"OK"
    except Exception:
        return False


def _config_dir():
    """Μόνιμος φάκελος ρυθμίσεων — επιβιώνει από κάθε νέο build του exe."""
    base = os.environ.get("APPDATA") or os.path.expanduser("~/.config")
    d = os.path.join(base, "ICS", APP_ID)
    try:
        os.makedirs(d, exist_ok=True)
        return d
    except Exception:
        return APP_DIR


CONFIG_DIR = _config_dir()
CONFIG_PATH = os.path.join(CONFIG_DIR, "autohost_config.json")
LEGACY_CONFIG = os.path.join(APP_DIR, "autohost_config.json")
LEGACY_CONFIGS = (
    LEGACY_CONFIG,
    os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~/.config"),
                 "ICS", "TScaleAutoHost", "autohost_config.json"),
)
LOG_DIR = os.path.join(CONFIG_DIR, "logs")
LOG_KEEP_DAYS = 30
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_NAME = APP_ID
LEGACY_RUN_NAMES = ("TScaleAutoHost",)
DEFAULT_PATH = os.path.join(APP_DIR, "config_default.json")


# --------------------------------------------------------------------------
# Sfalmata me katanoito minima
# --------------------------------------------------------------------------
class StepError(Exception):
    def __init__(self, step, message, detail=""):
        super().__init__(message)
        self.step = step
        self.message = message
        self.detail = detail

    def full(self):
        txt = "[%s] %s" % (self.step, self.message)
        if self.detail:
            txt += "\n" + self.detail
        return txt


# --------------------------------------------------------------------------
# Ruthmiseis
# --------------------------------------------------------------------------
def resource(name):
    """Diadromi porou, kai otan trexei os PyInstaller onefile."""
    base = getattr(sys, "_MEIPASS", APP_DIR)
    p = os.path.join(base, name)
    return p if os.path.exists(p) else os.path.join(APP_DIR, name)


def exe_command():
    """I entoli pou ksekinaei tin efarmogi elachistopoiimeni."""
    if getattr(sys, "frozen", False):
        return '"%s" --tray' % sys.executable
    pyw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    runner = pyw if os.path.exists(pyw) else sys.executable
    return '"%s" "%s" --tray' % (runner, os.path.join(APP_DIR, "autohost.py"))


def set_autostart(enable):
    """Eggrafi/diagrafi apo tin ekkinisi ton Windows (HKCU Run)."""
    try:
        import winreg
    except ImportError:
        raise StepError("Εκκίνηση", "Η αυτόματη εκκίνηση υποστηρίζεται μόνο στα Windows.", "")
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_ALL_ACCESS) as k:
            for old_name in LEGACY_RUN_NAMES:    # παλιό όνομα προγράμματος
                try:
                    winreg.DeleteValue(k, old_name)
                except FileNotFoundError:
                    pass
            if enable:
                winreg.SetValueEx(k, RUN_NAME, 0, winreg.REG_SZ, exe_command())
            else:
                try:
                    winreg.DeleteValue(k, RUN_NAME)
                except FileNotFoundError:
                    pass
    except Exception as exc:
        raise StepError("Εκκίνηση", "Αδυναμία ενημέρωσης της αυτόματης εκκίνησης των Windows.", str(exc))


def autostart_enabled():
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
            winreg.QueryValueEx(k, RUN_NAME)
        return True
    except Exception:
        return False


def log_path(day=None):
    day = day or datetime.date.today()
    return os.path.join(LOG_DIR, "%s-%s.log" % (APP_ID, day.isoformat()))


def write_log(msg):
    """Γράφει στο ημερήσιο αρχείο log. Ποτέ δεν ρίχνει την εφαρμογή."""
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(log_path(), "a", encoding="utf-8") as fh:
            fh.write("%s  %s\n" % (stamp, msg))
    except Exception:
        pass


def purge_old_logs():
    """Σβήνει τα log παλαιότερα των LOG_KEEP_DAYS ημερών."""
    try:
        limit = time.time() - LOG_KEEP_DAYS * 86400
        for name in os.listdir(LOG_DIR):
            if not name.endswith(".log"):
                continue
            f = os.path.join(LOG_DIR, name)
            if os.path.getmtime(f) < limit:
                os.remove(f)
    except Exception:
        pass


def parse_version(text):
    """«1.2.3» -> (1, 2, 3). Ό,τι δεν είναι αριθμός γίνεται 0."""
    parts = []
    for chunk in str(text).strip().split(".")[:4]:
        digits = "".join(ch for ch in chunk if ch.isdigit())
        parts.append(int(digits) if digits else 0)
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts)


def _get(url, timeout, binary=False):
    import urllib.request
    req = urllib.request.Request(url, headers={"User-Agent": APP_ID,
                                               "Cache-Control": "no-cache"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = resp.read()
    return data if binary else data.decode("utf-8", "replace")


def fetch_latest_version(timeout=8):
    """(έκδοση, σημειώσεις, url_του_exe). Προτιμά το τελευταίο GitHub Release."""
    try:
        rel = json.loads(_get(UPDATE_API_URL, timeout))
        version = (rel.get("tag_name") or "").lstrip("vV")
        notes = (rel.get("body") or "").strip()
        exe_url = ""
        for asset in rel.get("assets", []):
            if asset.get("name", "").lower() == UPDATE_ASSET.lower():
                exe_url = asset.get("browser_download_url", "")
                break
        if version:
            return version, notes, exe_url
    except Exception:
        pass                                  # χωρίς release, πέφτουμε στο VERSION
    lines = [l.strip() for l in _get(UPDATE_VERSION_URL, timeout).splitlines() if l.strip()]
    if not lines:
        raise ValueError("κενή απάντηση")
    return lines[0], "\n".join(lines[1:]), ""


def download_update(url, dest, timeout=120, log=None):
    """Κατεβάζει το νέο exe σε προσωρινό αρχείο και επιστρέφει τη διαδρομή του."""
    data = _get(url, timeout, binary=True)
    if len(data) < 1024 * 1024:               # ένα onefile exe είναι πολλά MB
        raise ValueError("το αρχείο που κατέβηκε είναι πολύ μικρό (%d bytes)" % len(data))
    if data[:2] != b"MZ":                     # υπογραφή εκτελέσιμου των Windows
        raise ValueError("το αρχείο που κατέβηκε δεν είναι εκτελέσιμο των Windows")
    with open(dest, "wb") as fh:
        fh.write(data)
    if log:
        log("  -> κατέβηκε: %s (%.1f MB)" % (dest, len(data) / 1048576.0))
    return dest


def install_update_and_restart(new_exe):
    """Αντικαθιστά το τρέχον exe και ξαναξεκινά.

    Το ίδιο το exe δεν μπορεί να γράψει πάνω στον εαυτό του όσο τρέχει, οπότε
    ένα μικρό .bat περιμένει να κλείσει, κάνει την αντικατάσταση και το ανοίγει ξανά.
    Οι ρυθμίσεις δεν αγγίζονται: ζουν στο %APPDATA%, όχι δίπλα στο exe.
    """
    cur = sys.executable
    backup = cur + ".old"
    bat = os.path.join(os.environ.get("TEMP") or os.path.dirname(cur),
                       "%s_update.bat" % APP_ID)
    script = """@echo off
chcp 65001 >nul
echo Ενημέρωση σε εξέλιξη, περιμένετε...
:wait
tasklist /FI "IMAGENAME eq {name}" 2>nul | find /I "{name}" >nul
if not errorlevel 1 (
  timeout /t 1 /nobreak >nul
  goto wait
)
if exist "{backup}" del /q "{backup}"
move /y "{cur}" "{backup}" >nul
move /y "{new}" "{cur}" >nul
start "" "{cur}"
del /q "%~f0"
""".format(name=os.path.basename(cur), cur=cur, new=new_exe, backup=backup)
    with open(bat, "w", encoding="cp1253", errors="replace") as fh:
        fh.write(script)
    subprocess.Popen(["cmd", "/c", bat], creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


def load_config():
    with open(DEFAULT_PATH, "r", encoding="utf-8") as fh:
        cfg = json.load(fh)
    # παλιές ρυθμίσεις δίπλα στο exe -> μεταφορά στον μόνιμο φάκελο
    path = CONFIG_PATH
    if not os.path.exists(path):
        for legacy in LEGACY_CONFIGS:
            if os.path.exists(legacy):
                path = legacy
                break
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as fh:
                cfg.update(json.load(fh))
            if path != CONFIG_PATH:
                save_config(cfg)                 # μεταφορά στο νέο σημείο
        except Exception:
            pass
    return cfg


def save_config(cfg):
    with open(CONFIG_PATH, "w", encoding="utf-8") as fh:
        json.dump(cfg, fh, indent=2, ensure_ascii=False)


# --------------------------------------------------------------------------
# VIMA 0 - host1 / host2
# --------------------------------------------------------------------------
def make_hosts(src, out_dir, log):
    if not src or not os.path.isfile(src):
        raise StepError("Βήμα 1", "Δεν βρέθηκε το αρχείο του ERP.", src)
    if not out_dir:
        out_dir = os.path.dirname(src)
    if not os.path.isdir(out_dir):
        try:
            os.makedirs(out_dir)
        except Exception as exc:
            raise StepError("Βήμα 1", "Αδυναμία δημιουργίας φακέλου εξόδου.",
                            "%s\n%s" % (out_dir, exc))

    ext = os.path.splitext(src)[1] or ".txt"
    made = []
    for name in ("host1", "host2"):
        dst = os.path.join(out_dir, name + ext)
        try:
            shutil.copyfile(src, dst)
        except Exception as exc:
            raise StepError("Βήμα 1", "Αδυναμία εγγραφής του %s." % os.path.basename(dst),
                            "%s\n%s" % (dst, exc))
        made.append(dst)
        log("  -> %s" % dst)
    return made[0], made[1]


# --------------------------------------------------------------------------
# VIMA 1 - o "CNV" diermineas
#
# Ypostirizomenes entoles (mia ana grammi, opos sto arxiko script):
#   INPUTFIL=<diadromi>            arxeio eisodou   (<HOST1> = to host1 pou ftiaxtike)
#   OUTPUTFL=<diadromi>            arxeio eksodou   (<OUT1>  = auto-onoma dipla sto host1)
#   CNV2WIN                        metatropi kodikoselidas DOS(737) -> Windows(1253)
#   CNV2DOS                        to antitheto
#   UPPERCASE                      ola kefalaia
#   SKIPLINE=n                     paraleipsi ton proton n grammon
#   DESCRIPT=aaa            bbb    krata to pedio [aaa..aaa+bbb] os perigrafi (thesi, mikos)
#   IFEXISTn=P=[V]   THEN=[X]      an sti thesi P yparxei i timi V tote:
#                                     X = -1  -> agnoise ti grammi
#                                     alliws  -> antikatestise ti thesi me tin timi X
#   PADLINE=n                      symplirwse kathe grammi se stathero mikos n
# --------------------------------------------------------------------------

def detect_codepage(raw):
    """cp737 (DOS ελληνικά) ή cp1253 (Windows ελληνικά);"""
    dos = win = 0
    for b in raw:
        if 0x80 <= b <= 0xAF or 0xE0 <= b <= 0xF0:
            dos += 1
        elif 0xB8 <= b <= 0xFE:
            win += 1
    return "cp737" if dos > win else "cp1253"


RE_IFEXIST = re.compile(r"^IFEXIST\d*\s*=\s*(\d+)\s*=\s*\[([^\]]*)\]\s*THEN\s*=\s*\[([^\]]*)\]\s*$", re.I)


def parse_step1_script(text, host1, one_based=True):
    """Metatrepei to keimeno ton kanonon se lexiko entolon."""
    rules = {
        "input": None, "output": None,
        "cnv2win": False, "cnv2dos": False, "upper": False,
        "skip": 0, "pad": 0, "descript": None, "ifexist": [],
    }
    out_default = os.path.join(os.path.dirname(host1),
                               os.path.splitext(os.path.basename(host1))[0] + "_cnv" +
                               (os.path.splitext(host1)[1] or ".txt"))
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or line.startswith(";"):
            continue
        up = line.upper()

        m = RE_IFEXIST.match(line)
        if m:
            rules["ifexist"].append((int(m.group(1)), m.group(2), m.group(3)))
            continue
        if up.startswith("INPUTFIL"):
            val = line.split("=", 1)[1].strip()
            rules["input"] = host1 if val.upper() == "<HOST1>" else val
        elif up.startswith("OUTPUTFL") or up.startswith("OUTPUTFILE"):
            val = line.split("=", 1)[1].strip()
            if val.upper() == "<OUT1>":
                rules["output"] = out_default
            elif os.path.dirname(val):
                rules["output"] = val                     # πλήρης διαδρομή
            else:
                # σκέτο όνομα αρχείου -> στον ίδιο φάκελο με το host1
                rules["output"] = os.path.join(os.path.dirname(host1), val)
        elif up == "CNV2WIN":
            rules["cnv2win"] = True
        elif up == "CNV2DOS":
            rules["cnv2dos"] = True
        elif up == "UPPERCASE":
            rules["upper"] = True
        elif up.startswith("SKIPLINE"):
            rules["skip"] = int(line.split("=", 1)[1].strip() or 0)
        elif up.startswith("PADLINE"):
            rules["pad"] = int(line.split("=", 1)[1].strip() or 0)
        elif up.startswith("DESCRIPT"):
            nums = re.findall(r"\d+", line.split("=", 1)[1])
            if len(nums) >= 2:
                rules["descript"] = (int(nums[0]), int(nums[1]))
        else:
            raise StepError("Βήμα 2", "Άγνωστη εντολή στο script: %s" % line,
                            "Έλεγξε τη γραμμή στο πλαίσιο «Κανόνες Βήματος 2».")

    if not rules["input"]:
        rules["input"] = host1
    if not rules["output"]:
        rules["output"] = out_default
    return rules


def run_step1(cfg, host1, log):
    text = cfg.get("step1_script", "")
    rules = parse_step1_script(text, host1)
    src, dst = rules["input"], rules["output"]

    if not os.path.isfile(src):
        raise StepError("Βήμα 2", "Δεν βρέθηκε το αρχείο εισόδου του Βήματος 2.", src)

    try:
        raw = open(src, "rb").read()
    except Exception as exc:
        raise StepError("Βήμα 2", "Αδυναμία ανάγνωσης του αρχείου εισόδου.",
                        "%s\n%s" % (src, exc))

    detected = detect_codepage(raw)
    if rules["cnv2win"]:
        src_enc, dst_enc = detected, "cp1253"
    elif rules["cnv2dos"]:
        src_enc, dst_enc = detected, "cp737"
    else:
        src_enc = cfg.get("src_encoding", "cp1253")
        dst_enc = cfg.get("dst_encoding", "cp1253")
    if src_enc != detected:
        log("  (σημείωση) το αρχείο μοιάζει %s, διαβάζεται ως %s" % (detected, src_enc))
    try:
        lines = raw.decode(src_enc, "replace").splitlines()
    except Exception as exc:
        raise StepError("Βήμα 2", "Αδυναμία ανάγνωσης του αρχείου εισόδου.",
                        "%s\n%s" % (src, exc))

    if rules["skip"]:
        lines = lines[rules["skip"]:]

    out_lines = []
    dropped = 0
    for line in lines:
        skip_line = False
        for pos, val, then in rules["ifexist"]:
            idx = pos - 1
            if idx < 0 or idx >= len(line):
                continue
            if line[idx:idx + len(val)] != val:
                continue
            if then.strip().upper() == "DELETE":
                skip_line = True
                break
            # αντικατάσταση της τιμής στη συγκεκριμένη θέση
            line = line[:idx] + then + line[idx + len(val):]
        if skip_line:
            dropped += 1
            continue
        if rules["upper"]:
            line = line.upper()
        if rules["pad"]:
            line = line.ljust(rules["pad"])[:rules["pad"]]
        out_lines.append(line)

    try:
        with open(dst, "w", encoding=dst_enc, errors="replace", newline="\r\n") as fh:
            fh.write("\n".join(out_lines) + ("\n" if out_lines else ""))
    except Exception as exc:
        raise StepError("Βήμα 2", "Αδυναμία εγγραφής του αρχείου εξόδου.",
                        "%s\n%s" % (dst, exc))

    log("  -> %s (%d γραμμές, %d αγνοήθηκαν)" % (dst, len(out_lines), dropped))

    exe = (cfg.get("step1_external_exe") or "").strip()
    if exe:
        if not os.path.isfile(exe):
            raise StepError("Βήμα 2", "Δεν βρέθηκε το εξωτερικό πρόγραμμα μετατροπής.", exe)
        cfg_file = os.path.join(os.path.dirname(dst), "cnv_script.txt")
        with open(cfg_file, "w", encoding="cp1253", errors="replace") as fh:
            fh.write(text.replace("<HOST1>", host1).replace("<OUT1>", dst))
        try:
            res = subprocess.run([exe, cfg_file], capture_output=True, timeout=120)
        except Exception as exc:
            raise StepError("Βήμα 2", "Αποτυχία εκτέλεσης του εξωτερικού προγράμματος.", str(exc))
        if res.returncode != 0:
            raise StepError("Βήμα 2", "Το εξωτερικό πρόγραμμα επέστρεψε σφάλμα (%d)." % res.returncode,
                            (res.stderr or res.stdout or b"").decode("cp1253", "replace"))
    return dst


# --------------------------------------------------------------------------
# VIMA 2 - eksagogi product.csv apo arxeio statherou platous
# --------------------------------------------------------------------------
def run_step2(cfg, fallback_input, log):
    chosen = (cfg.get("step2_input") or "").strip()
    src = chosen or fallback_input
    log("  <- είσοδος: %s%s" % (src, "" if chosen else "  (αυτόματα από το προηγούμενο βήμα)"))
    dst = (cfg.get("step2_output") or "").strip()
    if not dst:
        ext = ".csv" if cfg.get("step2_format", "csv") in ("csv", "semicolon") else ".txt"
        dst = os.path.join(os.path.dirname(src), "product" + ext)
    if not src or not os.path.isfile(src):
        raise StepError("Βήμα 3", "Δεν βρέθηκε το αρχείο εισόδου (host).",
                        "Διαδρομή: %s\nΔιάλεξε αρχείο εισόδου στην καρτέλα «Βήμα 3» ή άφησέ το "
                        "κενό για να χρησιμοποιηθεί αυτόματα το host1 του φακέλου εξόδου." % src)

    out_dir = os.path.dirname(dst)
    if out_dir and not os.path.isdir(out_dir):
        try:
            os.makedirs(out_dir)
        except Exception as exc:
            raise StepError("Βήμα 3", "Δεν υπάρχει ο φάκελος εξόδου και δεν μπόρεσε να δημιουργηθεί.",
                            "%s\n%s" % (out_dir, exc))

    fields = [f for f in cfg.get("step2_fields", []) if f.get("enabled")]
    if not fields:
        raise StepError("Βήμα 3", "Δεν είναι επιλεγμένο κανένα πεδίο στον πίνακα παραμέτρων.",
                        "Τσέκαρε τουλάχιστον ένα πεδίο στη στήλη «Για έξοδο».")
    for f in fields:
        if int(f.get("len") or 0) <= 0:
            raise StepError("Βήμα 3", "Το πεδίο «%s» είναι επιλεγμένο αλλά έχει Μήκος = 0." % f["name"],
                            "Βάλε Μήκος Πεδίου > 0 ή ξε-τσέκαρέ το.")

    off = 1 if cfg.get("step2_onebased", True) else 0
    start_line = max(1, int(cfg.get("step2_startline", 1) or 1))
    enc = cfg.get("dst_encoding", "cp1253")

    try:
        with open(src, "r", encoding=enc, errors="replace") as fh:
            lines = fh.read().splitlines()
    except Exception as exc:
        raise StepError("Βήμα 3", "Αδυναμία ανάγνωσης του host αρχείου.", "%s\n%s" % (src, exc))

    rows = []
    for line in lines[start_line - 1:]:
        if not line.strip():
            continue
        row = []
        for f in fields:
            pos = int(f.get("pos") or 0) - off
            ln = int(f.get("len") or 0)
            val = line[pos:pos + ln].strip() if pos >= 0 else ""
            if not val and str(f.get("extra", "")).strip():
                val = str(f["extra"]).strip()
            row.append(val)
        rows.append(row)

    if not rows:
        raise StepError("Βήμα 3", "Το host αρχείο δεν περιέχει γραμμές δεδομένων.",
                        "Αρχείο: %s\nΓραμμή έναρξης: %d" % (src, start_line))

    fmt = cfg.get("step2_format", "csv")
    try:
        if fmt == "fixed":
            # σταθερό πλάτος: κάθε πεδίο γεμίζει το δικό του μήκος
            with open(dst, "w", encoding=enc, errors="replace", newline="\r\n") as fh:
                if cfg.get("step2_write_header", True):
                    fh.write("".join(f["name"][:int(f["len"])].ljust(int(f["len"]))
                                     for f in fields) + "\n")
                for row in rows:
                    fh.write("".join(v[:int(f["len"])].ljust(int(f["len"]))
                                     for v, f in zip(row, fields)) + "\n")
        else:
            delim = {"csv": ",", "tab": "\t", "semicolon": ";"}.get(
                fmt, cfg.get("step2_delimiter", ",") or ",")
            with open(dst, "w", encoding=enc, errors="replace", newline="") as fh:
                w = csv.writer(fh, delimiter=delim)
                if cfg.get("step2_write_header", True):
                    w.writerow([f["name"] for f in fields])
                w.writerows(rows)
    except Exception as exc:
        raise StepError("Βήμα 3", "Αδυναμία εγγραφής του αρχείου προϊόντων.",
                        "%s\n%s" % (dst, exc))

    log("  -> %s (%d εγγραφές, %d πεδία)" % (dst, len(rows), len(fields)))
    return dst


# --------------------------------------------------------------------------
# VIMA 4 - Efarmogi zygou (AutoProcess i antistoixi allou zygou)
# --------------------------------------------------------------------------
def run_step3(cfg, log, stop_event=None):
    exe = (cfg.get("step3_exe") or "").strip()
    secs = int(cfg.get("step3_seconds", 120) or 120)
    if not exe or not os.path.isfile(exe):
        raise StepError("Βήμα 4", "Δεν βρέθηκε η εφαρμογή του ζυγού.", exe)
    try:
        proc = subprocess.Popen([exe], cwd=os.path.dirname(exe))
    except Exception as exc:
        raise StepError("Βήμα 4", "Αδυναμία εκκίνησης της εφαρμογής του ζυγού.", "%s\n%s" % (exe, exc))

    log("  -> %s: τρέχει για %d δευτερόλεπτα…" % (os.path.basename(exe), secs))
    deadline = time.time() + secs
    while time.time() < deadline:
        if proc.poll() is not None:
            log("  -> %s: τερμάτισε μόνο του (κωδικός %s)." % (os.path.basename(exe), proc.returncode))
            return
        if stop_event is not None and stop_event.is_set():
            break
        time.sleep(0.5)

    if proc.poll() is None and cfg.get("step3_kill", True):
        try:
            proc.terminate()
            time.sleep(1.5)
            if proc.poll() is None:
                proc.kill()
            log("  -> %s: έκλεισε μετά τα %d δευτερόλεπτα." % (os.path.basename(exe), secs))
        except Exception as exc:
            raise StepError("Βήμα 4", "Αδυναμία τερματισμού της εφαρμογής του ζυγού.", str(exc))


# --------------------------------------------------------------------------
# Oli i roi
# --------------------------------------------------------------------------
def archive_run(cfg, files, log):
    """Κρατάει αντίγραφο των αρχείων της εκτέλεσης σε φάκελο backup."""
    keep = max(1, int(cfg.get("backup_keep", 3) or 3))
    root = os.path.join(cfg.get("output_dir") or os.path.dirname(cfg.get("watch_file", "")),
                        "backup")
    stamp = datetime.datetime.now().strftime("%Y-%m-%d_%H%M%S")
    dest = os.path.join(root, stamp)
    try:
        os.makedirs(dest, exist_ok=True)
        n = 0
        for f in files:
            if f and os.path.isfile(f):
                shutil.copy2(f, os.path.join(dest, os.path.basename(f)))
                n += 1
        log("  -> backup: %s (%d αρχεία)" % (dest, n))

        # κράτα μόνο τις τελευταίες `keep` εκτελέσεις
        runs = sorted(d for d in os.listdir(root) if os.path.isdir(os.path.join(root, d)))
        for old_run in runs[:-keep]:
            shutil.rmtree(os.path.join(root, old_run), ignore_errors=True)
            log("  -> διαγράφηκε παλιό backup: %s" % old_run)
    except Exception as exc:
        # το backup δεν πρέπει ποτέ να ρίξει την ενημέρωση των ζυγών
        log("  Προσοχή: απέτυχε η αρχειοθέτηση (%s)" % exc)


def run_pipeline(cfg, log, stop_event=None):
    log("=== Έναρξη διαδικασίας %s ===" % datetime.datetime.now().strftime("%d/%m/%Y %H:%M:%S"))
    host1, host2 = make_hosts(cfg.get("watch_file"), cfg.get("output_dir"), log)
    log("Βήμα 1: δημιουργήθηκαν host1/host2. OK")
    produced = [cfg.get("watch_file"), host1, host2]

    current = host1
    if cfg.get("step1_enabled"):
        current = run_step1(cfg, host1, log)
        produced.append(current)
        log("Βήμα 2: μετατροπή. OK")
    else:
        log("Βήμα 2: απενεργοποιημένο.")

    if cfg.get("step2_enabled"):
        produced.append(run_step2(cfg, current, log))
        log("Βήμα 3: product.csv. OK")
    else:
        log("Βήμα 3: απενεργοποιημένο.")

    if cfg.get("backup_enabled", True):
        archive_run(cfg, produced, log)

    if cfg.get("step3_enabled"):
        run_step3(cfg, log, stop_event)
        log("Βήμα 4: εφαρμογή ζυγού. OK")
    else:
        log("Βήμα 4: απενεργοποιημένο.")

    log("=== Ολοκληρώθηκε με επιτυχία ===")


# --------------------------------------------------------------------------
# GUI
# --------------------------------------------------------------------------
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_NAME)
        try:                                    # καθαρά γράμματα σε οθόνες με scaling
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        w = min(1040, sw - 60)
        h = min(900, sh - 90)                  # να μη μπαίνει κάτω από τη γραμμή εργασιών
        self.geometry("%dx%d+%d+%d" % (w, h, max(0, (sw - w) // 2), max(0, (sh - h) // 3)))
        self.minsize(760, 460)
        self.cfg = load_config()
        self.worker = None
        self.stop_event = threading.Event()
        self.watch_thread = None
        self.watching = False
        self.last_stamp = None

        self.tray = None
        self.pending_error = None
        self._build()
        self._load_into_widgets()
        self.protocol("WM_DELETE_WINDOW", self.on_close)

    # ---------------- εμφάνιση ----------------
    def _apply_theme(self):
        C = COLORS
        st = ttk.Style(self)
        try:
            st.theme_use("clam")
        except tk.TclError:
            pass
        self.configure(bg=C["bg"])
        base = ("Segoe UI", 10)

        st.configure(".", background=C["card"], foreground=C["ink"], font=base,
                     bordercolor=C["line"], focuscolor=C["brand"])
        st.configure("TFrame", background=C["card"])
        st.configure("Bar.TFrame", background=C["bg"])
        st.configure("Card.TFrame", background=C["card"], relief="flat")
        st.configure("Header.TFrame", background=C["card"])
        st.configure("TLabel", background=C["card"], foreground=C["ink"], font=base)
        st.configure("OnCard.TLabel", background=C["card"])
        st.configure("Title.TLabel", background=C["card"], foreground=C["ink"],
                     font=("Segoe UI", 17, "bold"))
        st.configure("Vendor.TLabel", background=C["card"], foreground=C["brand"],
                     font=("Segoe UI", 8, "bold"))
        st.configure("Version.TLabel", background=C["card"], foreground=C["muted"],
                     font=("Segoe UI", 8))
        st.configure("Hint.TLabel", background=C["card"], foreground=C["muted"],
                     font=("Segoe UI", 9))
        st.configure("Pill.TLabel", background=C["card"], foreground=C["muted"],
                     font=("Segoe UI", 9, "bold"), padding=(12, 6))

        st.configure("TCheckbutton", background=C["card"], foreground=C["ink"], font=base,
                     focuscolor=C["card"])
        st.map("TCheckbutton", background=[("active", C["card"])],
               indicatorcolor=[("selected", C["brand"]), ("!selected", C["card"])])
        st.configure("Big.TCheckbutton", font=("Segoe UI", 11, "bold"), foreground=C["brand_d"])
        st.map("Big.TCheckbutton", background=[("active", C["card"])],
               indicatorcolor=[("selected", C["brand"]), ("!selected", C["card"])])

        st.configure("TEntry", fieldbackground=C["card"], background=C["card"],
                     foreground=C["ink"], bordercolor=C["line"], insertcolor=C["ink"],
                     padding=5, relief="flat")
        st.map("TEntry", bordercolor=[("focus", C["brand"])])

        st.configure("TButton", background=C["card"], foreground=C["ink"], font=base,
                     borderwidth=1, relief="flat", padding=(12, 7))
        st.map("TButton", background=[("active", "#e6eef7"), ("pressed", "#dbe6f2")],
               bordercolor=[("active", C["brand"])])
        st.configure("Accent.TButton", background=C["brand"], foreground="#ffffff",
                     font=("Segoe UI", 10, "bold"), borderwidth=0, padding=(16, 8))
        st.map("Accent.TButton", background=[("active", C["brand_d"]), ("pressed", "#0f6b9f")])
        st.configure("Ghost.TButton", background=C["bg"], foreground=C["muted"],
                     borderwidth=0, padding=(12, 7))
        st.map("Ghost.TButton", background=[("active", "#e3eaf3")], foreground=[("active", C["ink"])])
        st.configure("Pick.TButton", padding=(8, 5))

        st.configure("TNotebook", background=C["bg"], borderwidth=0, tabmargins=(6, 6, 6, 0))
        st.configure("TNotebook.Tab", background="#dde5ee", foreground=C["muted"],
                     font=("Segoe UI", 10, "bold"), padding=(18, 10), borderwidth=0)
        st.map("TNotebook.Tab",
               background=[("selected", C["card"]), ("active", "#e8eef6")],
               foreground=[("selected", C["brand_d"])])

        st.configure("Treeview", background=C["card"], fieldbackground=C["card"],
                     foreground=C["ink"], rowheight=27, borderwidth=0, font=("Segoe UI", 10))
        st.configure("Treeview.Heading", background="#e4ebf3", foreground=C["muted"],
                     font=("Segoe UI", 9, "bold"), relief="flat", padding=(8, 8))
        st.map("Treeview.Heading", background=[("active", "#d8e2ee")])
        st.map("Treeview", background=[("selected", C["brand"])],
               foreground=[("selected", "#ffffff")])

        st.configure("TSeparator", background=C["line"])
        st.configure("Vertical.TScrollbar", background="#cfd9e5", troughcolor=C["bg"],
                     borderwidth=0, arrowcolor=C["muted"])

    def _scrollable(self, parent):
        """Επιστρέφει frame μέσα σε καμβά με κύλιση.

        Σε μικρή οθόνη το περιεχόμενο των καρτελών δεν χωρούσε και κοβόταν·
        έτσι ό,τι δεν φαίνεται το φτάνεις με τη ροδέλα ή τη μπάρα.
        """
        canvas = tk.Canvas(parent, highlightthickness=0, bg=COLORS["card"], bd=0)
        sb = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        inner = ttk.Frame(canvas, style="Card.TFrame", padding=(14, 8))
        win = canvas.create_window((0, 0), window=inner, anchor="nw")

        def on_inner(_e=None):
            canvas.configure(scrollregion=canvas.bbox("all"))

        def on_canvas(e):
            canvas.itemconfigure(win, width=e.width)

        inner.bind("<Configure>", on_inner)
        canvas.bind("<Configure>", on_canvas)

        def wheel(e):
            delta = -1 if getattr(e, "num", 0) == 5 or getattr(e, "delta", 0) < 0 else 1
            canvas.yview_scroll(-delta, "units")

        for seq in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            canvas.bind_all(seq, lambda e, c=canvas: wheel(e) if str(c) in str(e.widget) or True else None)
        return inner

    def _console(self, parent, height, font):
        box = scrolledtext.ScrolledText(
            parent, height=height, font=font, background=COLORS["console"],
            foreground=COLORS["console_fg"], insertbackground=COLORS["console_fg"],
            relief="flat", borderwidth=0, padx=12, pady=10,
            selectbackground=COLORS["brand"])
        return box

    # ---------------- layout ----------------
    def _build(self):
        try:
            self.iconphoto(True, tk.PhotoImage(file=resource("logo.png")))
            self.iconbitmap(resource("logo.ico"))
        except Exception:
            pass

        self._apply_theme()

        top = ttk.Frame(self, style="Header.TFrame", padding=(16, 12))
        top.pack(fill="x")
        self.logo_img = self._load_logo(56)
        if self.logo_img is not None:
            ttk.Label(top, image=self.logo_img, style="OnCard.TLabel").pack(side="left", padx=(0, 14))
        titles = ttk.Frame(top, style="Header.TFrame")
        titles.pack(side="left")
        ttk.Label(titles, text=APP_NAME, style="Title.TLabel").pack(anchor="w")
        ttk.Label(titles, text=APP_VENDOR, style="Vendor.TLabel").pack(anchor="w", pady=(2, 0))
        ttk.Label(titles, text=APP_VERSION, style="Version.TLabel").pack(anchor="w")

        self.status_dot = tk.Canvas(top, width=12, height=12, highlightthickness=0,
                                    bg=COLORS["card"])
        self._dot = self.status_dot.create_oval(2, 2, 11, 11, fill=COLORS["muted"], outline="")
        self.status = ttk.Label(top, text="Σε αναμονή", style="Pill.TLabel")
        self.status.pack(side="right")
        self.status_dot.pack(side="right")

        tk.Frame(self, height=3, bg=COLORS["brand"], bd=0).pack(fill="x")

        nb = ttk.Notebook(self)
        pages = []
        for title in ("  Βήμα 1 · Αρχείο ERP  ", "  Βήμα 2 · Μετατροπή  ",
                      "  Βήμα 3 · Αρχείο προϊόντων  ", "  Βήμα 4 · Εφαρμογή ζυγού  "):
            page = ttk.Frame(nb, style="Card.TFrame")
            nb.add(page, text=title)
            pages.append(self._scrollable(page))
        self.tab0, self.tab1, self.tab2, self.tab3 = pages

        self._build_tab0()
        self._build_tab1()
        self._build_tab2()
        self._build_tab3()

        bar = ttk.Frame(self, style="Bar.TFrame", padding=(12, 10))
        bar.pack(side="bottom", fill="x")
        ttk.Button(bar, text="▶  Εκτέλεση τώρα", style="Accent.TButton",
                   command=self.run_once).pack(side="left")
        self.btn_watch = ttk.Button(bar, text="●  Έναρξη παρακολούθησης", command=self.toggle_watch)
        self.btn_watch.pack(side="left", padx=8)
        ttk.Button(bar, text="Αποθήκευση ρυθμίσεων", command=self.on_save).pack(side="left")
        ttk.Button(bar, text="Έξοδος", style="Ghost.TButton",
                   command=self.quit_app).pack(side="right")
        ttk.Button(bar, text="Ελαχιστοποίηση κάτω δεξιά", style="Ghost.TButton",
                   command=self.hide_to_tray).pack(side="right")

        # Τα δευτερεύοντα σε μενού: σε στενό παράθυρο τα κουμπιά της μπάρας
        # δεν χωρούσαν και κόβονταν.
        tools = ttk.Menubutton(bar, text="Εργαλεία  ▾", style="Ghost.TButton")
        menu = tk.Menu(tools, tearoff=0)
        menu.add_command(label="Άνοιγμα φακέλου εξόδου", command=self.open_out_dir)
        menu.add_command(label="Άνοιγμα backup", command=self.open_backup)
        menu.add_command(label="Αρχείο log", command=self.open_log_file)
        menu.add_separator()
        menu.add_command(label="Καθαρισμός οθόνης", command=lambda: self.txt_log.delete("1.0", "end"))
        menu.add_separator()
        menu.add_command(label="Έλεγχος ενημέρωσης…", command=self.check_update)
        menu.add_command(label="Σχετικά", command=self.show_about)
        tools["menu"] = menu
        tools.pack(side="right", padx=(0, 6))
        self.menu_tools = menu

        self.txt_log = self._console(self, 5, ("Consolas", 9))
        self.txt_log.pack(side="bottom", fill="x", padx=12, pady=(0, 8))
        for tag, col in (("ok", "#4ade80"), ("err", "#f87171"),
                         ("info", COLORS["console_fg"]), ("dim", "#7b8ca3")):
            self.txt_log.tag_configure(tag, foreground=col)

        nb.pack(fill="both", expand=True, padx=12, pady=(10, 0))

    def _pick_row(self, parent, label, var, kind="file", r=0):
        ttk.Label(parent, text=label).grid(row=r, column=0, sticky="w", pady=3)
        ttk.Entry(parent, textvariable=var, width=78).grid(row=r, column=1, sticky="we", padx=6)

        def pick():
            if kind == "dir":
                p = filedialog.askdirectory(title="Διάλεξε φάκελο")
            elif kind == "exe":
                p = filedialog.askopenfilename(title="Διάλεξε εφαρμογή",
                                               filetypes=[("Εφαρμογή", "*.exe"), ("Όλα", "*.*")])
            elif kind == "save":
                cur = var.get().strip()
                p = filedialog.asksaveasfilename(
                    title="Πού να δημιουργείται το αρχείο;",
                    initialfile=os.path.basename(cur) or "product.csv",
                    initialdir=os.path.dirname(cur) or self.v_outdir.get().strip() or None,
                    defaultextension=".csv",
                    confirmoverwrite=False,
                    filetypes=[("CSV", "*.csv"), ("Όλα", "*.*")])
            else:
                p = filedialog.askopenfilename(title="Διάλεξε αρχείο",
                                               filetypes=[("Αρχεία δεδομένων", "*.txt *.csv"), ("Όλα", "*.*")])
            if p:
                var.set(os.path.normpath(p))
        ttk.Button(parent, text="Αναζήτηση…", style="Pick.TButton", command=pick).grid(row=r, column=2)
        parent.columnconfigure(1, weight=1)

    def _build_tab0(self):
        f = self.tab0
        self.v_watch = tk.StringVar()
        self.v_outdir = tk.StringVar()
        self.v_poll = tk.StringVar(value="3")
        self.v_auto = tk.BooleanVar()
        self._pick_row(f, "Αρχείο που βγάζει το ERP:", self.v_watch, "file", 0)
        self._pick_row(f, "Φάκελος εξόδου (host1 / host2):", self.v_outdir, "dir", 1)
        row = ttk.Frame(f)
        row.grid(row=2, column=0, columnspan=3, sticky="w", pady=8)
        ttk.Label(row, text="Έλεγχος κάθε (δευτ.):").pack(side="left")
        ttk.Entry(row, textvariable=self.v_poll, width=6).pack(side="left", padx=6)
        ttk.Checkbutton(row, text="Αυτόματη έναρξη παρακολούθησης με το άνοιγμα",
                        variable=self.v_auto).pack(side="left", padx=12)
        bk = ttk.Frame(f)
        bk.grid(row=6, column=0, columnspan=3, sticky="w", pady=(2, 0))
        self.v_backup = tk.BooleanVar(value=True)
        self.v_keep = tk.StringVar(value="3")
        ttk.Checkbutton(bk, text="Κράτα αντίγραφα των τελευταίων", variable=self.v_backup).pack(side="left")
        ttk.Entry(bk, textvariable=self.v_keep, width=4).pack(side="left", padx=5)
        ttk.Label(bk, text="εκτελέσεων στον φάκελο backup").pack(side="left")
        ttk.Button(bk, text="Άνοιγμα backup", style="Ghost.TButton",
                   command=self.open_backup).pack(side="left", padx=10)

        self.v_boot = tk.BooleanVar(value=autostart_enabled())
        ttk.Checkbutton(f, variable=self.v_boot, command=self.on_boot_toggle,
                        text="Εκκίνηση με τα Windows — ξεκινά ελαχιστοποιημένο "
                             "στην περιοχή ειδοποιήσεων (κάτω δεξιά)"
                        ).grid(row=4, column=0, columnspan=3, sticky="w", pady=(2, 0))
        ttk.Label(f, style="Hint.TLabel", wraplength=880, justify="left",
                  text="Μόλις αλλάξει το αρχείο του ERP, δημιουργούνται αυτόματα τα host1.<κατάληξη> και "
                       "host2.<κατάληξη> στον φάκελο εξόδου και ξεκινούν τα ενεργοποιημένα βήματα."
                  ).grid(row=7, column=0, columnspan=3, sticky="w", pady=10)

    def _build_tab1(self):
        f = self.tab1
        self.v_s1 = tk.BooleanVar()
        ttk.Checkbutton(f, style="Big.TCheckbutton", text="Ενεργοποίηση Βήματος 2 — Μετατροπή αρχείου", variable=self.v_s1).pack(anchor="w")
        ttk.Label(f, style="Hint.TLabel", justify="left", wraplength=920,
                  text="Οι κανόνες είναι σε απλό κείμενο για να τους αλλάζεις ανά ζυγαριά.\n"
                       "<HOST1> = το host1 που μόλις δημιουργήθηκε, <OUT1> = αυτόματο όνομα εξόδου.\n"
                       "Εντολές: INPUTFIL= / OUTPUTFL= / CNV2WIN / CNV2DOS / UPPERCASE / SKIPLINE=n / "
                       "PADLINE=n / DESCRIPT=θέση μήκος / IFEXISTn=θέση=[τιμή] THEN=[τιμή ή -1]"
                  ).pack(anchor="w", pady=6)
        self.txt_s1 = self._console(f, 8, ("Consolas", 10))
        self.txt_s1.pack(fill="x")
        g = ttk.Frame(f)
        g.pack(fill="x", pady=8)
        self.v_s1exe = tk.StringVar()
        self._pick_row(g, "Προαιρετικό εξωτερικό .exe μετατροπής:", self.v_s1exe, "exe", 0)

    def _build_tab2(self):
        f = self.tab2
        self.v_s2 = tk.BooleanVar()
        ttk.Checkbutton(f, style="Big.TCheckbutton", text="Ενεργοποίηση Βήματος 3 — Αρχείο προϊόντων", variable=self.v_s2).pack(anchor="w")

        g = ttk.Frame(f)
        g.pack(fill="x", pady=6)
        self.v_s2in = tk.StringVar()
        self.v_s2out = tk.StringVar()
        self._pick_row(g, "Αρχείο εισόδου — άφησέ το κενό:", self.v_s2in, "file", 0)
        self._pick_row(g, "Να δημιουργείται εδώ:", self.v_s2out, "save", 1)
        ttk.Label(f, style="Hint.TLabel", justify="left", wraplength=920,
                  text="Κενή είσοδος = παίρνει ό,τι έβγαλε το προηγούμενο βήμα (έξοδος Βήματος 2, "
                       "αλλιώς host1). Το αρχείο εξόδου φτιάχνεται μόνο του — δεν χρειάζεται να υπάρχει."
                  ).pack(anchor="w", pady=(0, 4))
        o = ttk.Frame(f)
        o.pack(fill="x", pady=4)
        self.v_start = tk.StringVar(value="1")
        self.v_onebased = tk.BooleanVar(value=True)
        self.v_header = tk.BooleanVar(value=True)
        self.v_delim = tk.StringVar(value=",")
        ttk.Label(o, text="Γραμμή έναρξης:").pack(side="left")
        ttk.Entry(o, textvariable=self.v_start, width=5).pack(side="left", padx=4)
        ttk.Checkbutton(o, text="Γράψε γραμμή επικεφαλίδων", variable=self.v_header).pack(side="left", padx=(12, 0))

        fmt = ttk.Frame(f)
        fmt.pack(fill="x", pady=(6, 2))
        ttk.Label(fmt, text="Μορφή αρχείου:").pack(side="left")
        self.v_format = tk.StringVar(value="csv")
        for val, txt in (("csv", "CSV για T-Scale (κόμμα)"),
                         ("semicolon", "CSV με ερωτηματικό (;)"),
                         ("tab", "TXT με Tab"),
                         ("fixed", "TXT σταθερού πλάτους")):
            ttk.Radiobutton(fmt, text=txt, value=val, variable=self.v_format,
                            command=self.on_format_change).pack(side="left", padx=(10, 0))
        ttk.Checkbutton(o, text="Θέση 1 = πρώτος χαρακτήρας", variable=self.v_onebased).pack(side="left", padx=12)


        b = ttk.Frame(f)
        b.pack(side="bottom", fill="x", pady=(6, 0))
        ttk.Button(b, text="Εναλλαγή ✓ (ή Space)", command=self.toggle_field).pack(side="left")
        ttk.Button(b, text="Επεξεργασία γραμμής", command=self.on_edit_cell).pack(side="left", padx=6)
        ttk.Button(b, text="Αρχικοποίηση Παραμέτρων", command=self.reset_fields).pack(side="left")
        # Ο πίνακας φτιάχνεται ΜΕΣΑ στο πλαίσιό του: αλλιώς μένει από κάτω του
        # στη σειρά σχεδίασης και δεν φαίνεται καθόλου.
        tree_box = ttk.Frame(f)
        tree_box.pack(fill="x", pady=4)
        cols = ("name", "out", "pos", "len", "extra")
        self.tree = ttk.Treeview(tree_box, columns=cols, show="headings",
                                 height=8, selectmode="browse")
        for c, t, w in (("name", "Περιγραφή", 220), ("out", "Για έξοδο σε αρχείο", 140),
                        ("pos", "Από Θέση", 90), ("len", "Μήκος Πεδίου", 110),
                        ("extra", "Εξτρα περιγραφή", 200)):
            self.tree.heading(c, text=t)
            self.tree.column(c, width=w, anchor="w")
        self.tree.bind("<Double-1>", self.on_edit_cell)
        self.tree.bind("<space>", lambda e: self.toggle_field())
        sb = ttk.Scrollbar(tree_box, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.tree.pack(side="left", fill="both", expand=True)

        for pname in load_config().get("profiles", {}):
            ttk.Button(b, text="Προφίλ: %s" % pname.split(" (")[0],
                       command=lambda n=pname: self.load_profile(n)).pack(side="left", padx=6)
        ttk.Button(b, text="Δοκιμή · προεπισκόπηση", style="Accent.TButton",
                   command=self.preview_csv).pack(side="right")

    def _build_tab3(self):
        f = self.tab3
        self.v_s3 = tk.BooleanVar()
        ttk.Checkbutton(f, style="Big.TCheckbutton", text="Ενεργοποίηση Βήματος 4 — Εφαρμογή ζυγού", variable=self.v_s3).pack(anchor="w")
        g = ttk.Frame(f)
        g.pack(fill="x", pady=8)
        self.v_s3exe = tk.StringVar()
        self._pick_row(g, "Εφαρμογή ζυγού (π.χ. AutoProcess):", self.v_s3exe, "exe", 0)
        r = ttk.Frame(f)
        r.pack(fill="x")
        self.v_s3sec = tk.StringVar(value="120")
        self.v_s3kill = tk.BooleanVar(value=True)
        ttk.Label(r, text="Διάρκεια (δευτερόλεπτα):").pack(side="left")
        ttk.Entry(r, textvariable=self.v_s3sec, width=7).pack(side="left", padx=6)
        ttk.Checkbutton(r, text="Κλείσε την αυτόματα όταν περάσει ο χρόνος",
                        variable=self.v_s3kill).pack(side="left", padx=12)
        ttk.Label(f, style="Hint.TLabel", justify="left", wraplength=920,
                  text="Είναι το πρόγραμμα που στέλνει τα δεδομένα στη ζυγαριά. Για τους T-Scale "
                       "είναι το AutoProcess, αλλά μπορείς να δείξεις οποιαδήποτε άλλη εφαρμογή "
                       "αν ο ζυγός είναι διαφορετικού τύπου.").pack(anchor="w", pady=(8, 0))

    def _load_logo(self, height):
        try:
            from PIL import Image, ImageTk
            im = Image.open(resource("logo.png"))
            w = int(im.width * height / im.height)
            return ImageTk.PhotoImage(im.resize((w, height), Image.LANCZOS))
        except Exception:
            try:
                img = tk.PhotoImage(file=resource("logo.png"))
                f = max(1, img.height() // height)
                return img.subsample(f, f)
            except Exception:
                return None

    def on_boot_toggle(self):
        want = self.v_boot.get()
        try:
            self.collect()
            save_config(self.cfg)
            set_autostart(want)
            self.log("Εκκίνηση με τα Windows: %s" % ("ΝΑΙ" if want else "ΟΧΙ"))
        except StepError as exc:
            self.v_boot.set(not want)
            messagebox.showerror(APP_NAME, exc.full())

    # ---------------- περιοχή ειδοποιήσεων (κάτω δεξιά) ----------------
    def listen_for_wakeups(self):
        """Ακούει άλλα αντίγραφα που ζητούν να εμφανιστεί το παράθυρο.

        Το tkinter δεν είναι thread-safe: το νήμα σηκώνει μόνο σημαία και το
        παράθυρο εμφανίζεται από το κύριο νήμα στο _poll_wake.
        """
        sk = _singleton_sock
        if sk is None:
            return
        self._wake_requested = False

        def loop():
            while True:
                try:
                    conn, _ = sk.accept()
                except OSError:
                    return
                try:
                    if conn.recv(16) == b"SHOW":
                        conn.sendall(b"OK")
                        self._wake_requested = True
                except Exception:
                    pass
                finally:
                    try:
                        conn.close()
                    except Exception:
                        pass

        threading.Thread(target=loop, daemon=True).start()
        self._poll_wake()

    def _poll_wake(self):
        if getattr(self, "_wake_requested", False):
            self._wake_requested = False
            self.show_window()
        self.after(400, self._poll_wake)

    def setup_tray(self):
        self.tray = None
        try:
            import pystray
            from PIL import Image
        except Exception:
            return
        try:
            image = Image.open(resource("logo.png"))
        except Exception:
            return

        menu = pystray.Menu(
            pystray.MenuItem("Άνοιγμα", lambda *_: self.after(0, self.show_window), default=True),
            pystray.MenuItem("Εκτέλεση τώρα", lambda *_: self.after(0, self.run_once)),
            pystray.MenuItem("Έξοδος", lambda *_: self.after(0, self.quit_app)),
        )
        self.tray = pystray.Icon(RUN_NAME, image, APP_NAME, menu)
        threading.Thread(target=self.tray.run, daemon=True).start()

    def hide_to_tray(self):
        if getattr(self, "tray", None) is None:
            # χωρίς pystray δεν υπάρχει εικονίδιο κάτω δεξιά· ελαχιστοποίηση στη
            # γραμμή εργασιών, ώστε να μη μείνει ποτέ αόρατο και αβρισκούμενο
            self.iconify()
            self.log("Ελαχιστοποιήθηκε στη γραμμή εργασιών (λείπει το pystray).")
            return
        self.withdraw()
        self.log("Το πρόγραμμα συνεχίζει κάτω δεξιά στην περιοχή ειδοποιήσεων.")
        if not self.cfg.get("tray_hint_shown"):
            self.cfg["tray_hint_shown"] = True
            save_config(self.cfg)
            try:
                self.tray.notify("Συνεχίζει να δουλεύει εδώ κάτω δεξιά. "
                                 "Διπλό κλικ για άνοιγμα.", APP_NAME)
            except Exception:
                pass

    def show_window(self):
        self.deiconify()
        self.lift()
        self.focus_force()
        err = getattr(self, "pending_error", None)
        if err:
            self.pending_error = None
            if getattr(self, "tray", None) is not None:
                try:
                    self.tray.title = APP_NAME
                except Exception:
                    pass
            messagebox.showerror(APP_NAME, err)

    def quit_app(self):
        self.watching = False
        self.stop_event.set()
        try:
            save_config(self.collect())
        except Exception:
            pass
        if getattr(self, "tray", None) is not None:
            try:
                self.tray.stop()
            except Exception:
                pass
        self.destroy()

    # ---------------- config <-> widgets ----------------
    def _load_into_widgets(self):
        c = self.cfg
        self.v_watch.set(c.get("watch_file", ""))
        self.v_outdir.set(c.get("output_dir", ""))
        self.v_poll.set(str(c.get("poll_seconds", 3)))
        self.v_auto.set(bool(c.get("auto_run", False)))
        self.v_backup.set(bool(c.get("backup_enabled", True)))
        self.v_keep.set(str(c.get("backup_keep", 3)))
        self.v_s1.set(bool(c.get("step1_enabled", True)))
        self.txt_s1.delete("1.0", "end")
        self.txt_s1.insert("1.0", c.get("step1_script", ""))
        self.v_s1exe.set(c.get("step1_external_exe", ""))
        self.v_s2.set(bool(c.get("step2_enabled", True)))
        self.v_s2in.set(c.get("step2_input", ""))
        self.v_s2out.set(c.get("step2_output", ""))
        self.v_start.set(str(c.get("step2_startline", 1)))
        self.v_onebased.set(bool(c.get("step2_onebased", True)))
        self.v_header.set(bool(c.get("step2_write_header", True)))
        self.v_delim.set(c.get("step2_delimiter", ","))
        self.v_format.set(c.get("step2_format", "csv"))
        self.v_s3.set(bool(c.get("step3_enabled", True)))
        self.v_s3exe.set(c.get("step3_exe", ""))
        self.v_s3sec.set(str(c.get("step3_seconds", 120)))
        self.v_s3kill.set(bool(c.get("step3_kill", True)))
        self.refresh_tree()
        if self.v_auto.get():
            self.after(600, self.toggle_watch)

    def refresh_tree(self):
        self.tree.tag_configure("odd", background="#f7fafd")
        self.tree.tag_configure("off", foreground=COLORS["muted"])
        self.tree.delete(*self.tree.get_children())
        for i, f in enumerate(self.cfg.get("step2_fields", [])):
            tags = ["odd"] if i % 2 else []
            if not f.get("enabled"):
                tags.append("off")
            self.tree.insert("", "end", iid=str(i), tags=tuple(tags),
                             values=(f["name"], "✓" if f.get("enabled") else "—",
                                     f.get("pos", 0) or "—", f.get("len", 0) or "—",
                                     f.get("extra", "")))

    def collect(self):
        c = self.cfg
        c["watch_file"] = self.v_watch.get().strip()
        c["output_dir"] = self.v_outdir.get().strip()
        try:
            c["poll_seconds"] = max(1, int(self.v_poll.get()))
        except ValueError:
            c["poll_seconds"] = 3
        c["auto_run"] = self.v_auto.get()
        c["backup_enabled"] = self.v_backup.get()
        try:
            c["backup_keep"] = max(1, int(self.v_keep.get()))
        except ValueError:
            c["backup_keep"] = 3
        c["step1_enabled"] = self.v_s1.get()
        c["step1_script"] = self.txt_s1.get("1.0", "end").rstrip() + "\n"
        c["step1_external_exe"] = self.v_s1exe.get().strip()
        c["step2_enabled"] = self.v_s2.get()
        c["step2_input"] = self.v_s2in.get().strip()
        c["step2_output"] = self.v_s2out.get().strip()
        try:
            c["step2_startline"] = max(1, int(self.v_start.get()))
        except ValueError:
            c["step2_startline"] = 1
        c["step2_onebased"] = self.v_onebased.get()
        c["step2_write_header"] = self.v_header.get()
        c["step2_delimiter"] = self.v_delim.get() or ","
        c["step2_format"] = self.v_format.get()
        c["step3_enabled"] = self.v_s3.get()
        c["step3_exe"] = self.v_s3exe.get().strip()
        try:
            c["step3_seconds"] = max(1, int(self.v_s3sec.get()))
        except ValueError:
            c["step3_seconds"] = 120
        c["step3_kill"] = self.v_s3kill.get()
        return c

    def on_save(self):
        save_config(self.collect())
        self.log("Οι ρυθμίσεις αποθηκεύτηκαν: %s" % CONFIG_PATH)

    # ---------------- πίνακας παραμέτρων ----------------
    def on_format_change(self):
        """Αλλάζει την κατάληξη του αρχείου εξόδου ώστε να ταιριάζει με τη μορφή."""
        want = ".csv" if self.v_format.get() in ("csv", "semicolon") else ".txt"
        cur = self.v_s2out.get().strip()
        if cur:
            base, ext = os.path.splitext(cur)
            if ext.lower() in (".csv", ".txt") and ext.lower() != want:
                self.v_s2out.set(base + want)
                self.log("Το αρχείο εξόδου έγινε %s" % os.path.basename(base + want))

    def _sel(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo(APP_NAME, "Διάλεξε πρώτα μια γραμμή από τον πίνακα.")
            return None
        return int(sel[0])

    def toggle_field(self):
        i = self._sel()
        if i is None:
            return
        f = self.cfg["step2_fields"][i]
        f["enabled"] = not f.get("enabled")
        self.refresh_tree()
        self.tree.selection_set(str(i))

    def on_edit_cell(self, _event=None):
        i = self._sel()
        if i is None:
            return
        f = self.cfg["step2_fields"][i]
        win = tk.Toplevel(self)
        win.title("Πεδίο: %s" % f["name"])
        win.transient(self)
        win.grab_set()
        vals = {k: tk.StringVar(value=str(f.get(k, ""))) for k in ("name", "pos", "len", "extra")}
        en = tk.BooleanVar(value=bool(f.get("enabled")))
        for r, (k, lbl) in enumerate((("name", "Περιγραφή"), ("pos", "Από Θέση"),
                                      ("len", "Μήκος Πεδίου"), ("extra", "Εξτρα περιγραφή"))):
            ttk.Label(win, text=lbl).grid(row=r, column=0, sticky="w", padx=8, pady=4)
            ttk.Entry(win, textvariable=vals[k], width=34).grid(row=r, column=1, padx=8, pady=4)
        ttk.Checkbutton(win, text="Για έξοδο σε αρχείο", variable=en).grid(row=4, column=1, sticky="w", padx=8)

        def ok():
            try:
                f["pos"] = int(vals["pos"].get() or 0)
                f["len"] = int(vals["len"].get() or 0)
            except ValueError:
                messagebox.showerror(APP_NAME, "Η Θέση και το Μήκος πρέπει να είναι αριθμοί.", parent=win)
                return
            f["name"] = vals["name"].get().strip() or f["name"]
            f["extra"] = vals["extra"].get()
            f["enabled"] = en.get()
            win.destroy()
            self.refresh_tree()
            self.tree.selection_set(str(i))
        ttk.Button(win, text="Καταχώρηση", command=ok).grid(row=5, column=1, sticky="e", padx=8, pady=10)

    def load_profile(self, name):
        """Έτοιμο σετ θέσεων/μηκών για γνωστό τύπο αρχείου."""
        with open(DEFAULT_PATH, "r", encoding="utf-8") as fh:
            profiles = json.load(fh).get("profiles", {})
        if name not in profiles:
            messagebox.showerror(APP_NAME, "Δεν βρέθηκε το προφίλ «%s»." % name)
            return
        if not messagebox.askyesno(APP_NAME, "Να αντικατασταθεί ο πίνακας με το προφίλ «%s»;" % name):
            return
        self.cfg["step2_fields"] = [dict(f) for f in profiles[name]]
        self.refresh_tree()
        self.log("Φορτώθηκε το προφίλ παραμέτρων: %s" % name)

    def reset_fields(self):
        if not messagebox.askyesno(APP_NAME, "Επαναφορά όλων των παραμέτρων στις αρχικές τιμές;"):
            return
        with open(DEFAULT_PATH, "r", encoding="utf-8") as fh:
            self.cfg["step2_fields"] = json.load(fh)["step2_fields"]
        self.refresh_tree()

    def preview_csv(self):
        self.collect()
        try:
            src = self.cfg.get("step2_input") or ""
            if not src:
                messagebox.showinfo(APP_NAME, "Διάλεξε πρώτα αρχείο εισόδου (host) για τη δοκιμή.")
                return
            out = run_step2(dict(self.cfg, step2_output=os.path.join(
                os.path.dirname(src), "_preview_product.csv")), src, self.log)
            with open(out, "r", encoding=self.cfg.get("dst_encoding", "cp1253"), errors="replace") as fh:
                head = "".join(fh.readlines()[:6])
            messagebox.showinfo(APP_NAME, "Προεπισκόπηση:\n\n" + head)
        except StepError as exc:
            messagebox.showerror(APP_NAME, exc.full())

    # ---------------- εκτέλεση ----------------
    def set_status(self, text, color):
        self.status.configure(text=text, foreground=color)
        self.status_dot.itemconfigure(self._dot, fill=color)

    def open_out_dir(self):
        d = self.v_outdir.get().strip() or os.path.dirname(self.v_watch.get().strip())
        if not d or not os.path.isdir(d):
            messagebox.showinfo(APP_NAME, "Διάλεξε πρώτα φάκελο εξόδου στην 1η καρτέλα.")
            return
        try:
            os.startfile(d)                                  # Windows
        except AttributeError:
            subprocess.Popen(["xdg-open", d])

    # ---------------- ενημέρωση (μόνο χειροκίνητα, με κωδικό) ----------------
    def ask_password(self):
        """Κωδικός τεχνικού. Φραγμός κατά λάθους χειρισμού, όχι ασφάλεια."""
        win = tk.Toplevel(self)
        win.title("Κωδικός τεχνικού")
        win.transient(self)
        win.grab_set()
        win.resizable(False, False)
        ttk.Label(win, text="Η ενημέρωση γίνεται μόνο από τεχνικό της ICS.",
                  style="Hint.TLabel", wraplength=320).grid(row=0, column=0, columnspan=2,
                                                            padx=14, pady=(14, 6), sticky="w")
        ttk.Label(win, text="Κωδικός:").grid(row=1, column=0, padx=(14, 4), pady=6, sticky="w")
        var = tk.StringVar()
        ent = ttk.Entry(win, textvariable=var, show="●", width=18)
        ent.grid(row=1, column=1, padx=(0, 14), pady=6, sticky="w")
        ent.focus_set()
        result = {"ok": False}

        def ok(*_):
            if hashlib.sha256(var.get().strip().encode()).hexdigest() == UPDATE_PASSWORD_SHA256:
                result["ok"] = True
                win.destroy()
            else:
                messagebox.showerror(APP_NAME, "Λάθος κωδικός.", parent=win)
                var.set("")
                ent.focus_set()

        btns = ttk.Frame(win)
        btns.grid(row=2, column=0, columnspan=2, padx=14, pady=(4, 14), sticky="e")
        ttk.Button(btns, text="Άκυρο", command=win.destroy).pack(side="right", padx=(6, 0))
        ttk.Button(btns, text="OK", style="Accent.TButton", command=ok).pack(side="right")
        ent.bind("<Return>", ok)
        self.wait_window(win)
        return result["ok"]

    def show_about(self):
        messagebox.showinfo(
            APP_NAME,
            "%s\n%s\n\n%s\n\nΡυθμίσεις: %s\nLog: %s"
            % (APP_NAME, APP_VERSION, APP_VENDOR, CONFIG_PATH, LOG_DIR))

    def check_update(self):
        """Ρωτάει το GitHub αν υπάρχει νεότερη έκδοση.

        Τρέχει σε ξεχωριστό νήμα με timeout: αν δεν υπάρχει internet ή αργεί ο
        server, η εφαρμογή συνεχίζει κανονικά — δεν κολλάει ποτέ.
        """
        if not self.ask_password():
            return
        self.set_status("Έλεγχος ενημέρωσης…", COLORS["brand"])
        self._update_result = None

        def job():
            try:
                self._update_result = ("ok",) + fetch_latest_version()
            except Exception as exc:
                self._update_result = ("err", str(exc), "", "")

        threading.Thread(target=job, daemon=True).start()
        self.after(300, self._poll_update)

    def _poll_update(self):
        res = getattr(self, "_update_result", None)
        if res is None:
            self.after(300, self._poll_update)
            return
        self._update_result = None
        self.set_status("Σε αναμονή", COLORS["muted"])
        kind, latest, notes, exe_url = res

        if kind == "err":
            self.log("Ο έλεγχος ενημέρωσης απέτυχε: %s" % latest)
            messagebox.showwarning(
                APP_NAME,
                "Δεν ήταν δυνατός ο έλεγχος για ενημέρωση.\n\n%s\n\n"
                "Έλεγξε τη σύνδεση στο internet και ξαναδοκίμασε. Το πρόγραμμα "
                "συνεχίζει να δουλεύει κανονικά." % latest)
            return

        self.log("Έλεγχος ενημέρωσης: εγκατεστημένη %s, διαθέσιμη %s" % (APP_BUILD, latest))
        if parse_version(latest) <= parse_version(APP_BUILD):
            messagebox.showinfo(APP_NAME, "Έχεις την τελευταία έκδοση (%s)." % APP_BUILD)
            return

        frozen = getattr(sys, "frozen", False)
        if not (frozen and exe_url):
            messagebox.showinfo(
                APP_NAME,
                "Υπάρχει νεότερη έκδοση: %s (έχεις %s)\n\n%s\n\n"
                "Η αυτόματη εγκατάσταση δεν είναι διαθέσιμη εδώ — κάνε ενημέρωση "
                "χειροκίνητα από το GitHub." % (latest, APP_BUILD, notes or ""))
            import webbrowser
            webbrowser.open(UPDATE_PAGE_URL)
            return

        if not messagebox.askyesno(
                APP_NAME,
                "Υπάρχει νεότερη έκδοση!\n\nΕγκατεστημένη: %s\nΔιαθέσιμη: %s\n\n%s\n\n"
                "Να γίνει τώρα η ενημέρωση; Το πρόγραμμα θα κλείσει για λίγα δευτερόλεπτα "
                "και θα ξανανοίξει μόνο του.\nΟι ρυθμίσεις σου διατηρούνται."
                % (APP_BUILD, latest, notes or "")):
            return

        self.install_update(exe_url, latest)

    def install_update(self, url, latest):
        if self.watching:
            self.toggle_watch()
            self.log("Η παρακολούθηση σταμάτησε για την ενημέρωση.")
        self.set_status("Λήψη ενημέρωσης…", COLORS["brand"])
        self._download_result = None
        dest = os.path.join(os.path.dirname(sys.executable), APP_ID + ".new.exe")

        def job():
            try:
                download_update(url, dest, log=lambda m: self.after(0, self.log, m))
                self._download_result = ("ok", "")
            except Exception as exc:
                self._download_result = ("err", str(exc))

        threading.Thread(target=job, daemon=True).start()
        self.after(500, lambda: self._poll_download(dest, latest))

    def _poll_download(self, dest, latest):
        res = getattr(self, "_download_result", None)
        if res is None:
            self.after(500, lambda: self._poll_download(dest, latest))
            return
        self._download_result = None
        kind, err = res

        if kind == "err":
            self.set_status("Σφάλμα", COLORS["err"])
            self.log("ΣΦΑΛΜΑ -> Η λήψη της ενημέρωσης απέτυχε: %s" % err)
            try:
                os.remove(dest)
            except OSError:
                pass
            messagebox.showerror(
                APP_NAME,
                "Η λήψη της ενημέρωσης απέτυχε.\n\n%s\n\nΤο πρόγραμμα δεν άλλαξε "
                "καθόλου και συνεχίζει με την έκδοση %s." % (err, APP_BUILD))
            return

        self.log("Εγκατάσταση έκδοσης %s και επανεκκίνηση…" % latest)
        write_log("=== Ενημέρωση %s -> %s ===" % (APP_BUILD, latest))
        try:
            save_config(self.collect())
            install_update_and_restart(dest)
        except Exception as exc:
            messagebox.showerror(APP_NAME, "Η εγκατάσταση απέτυχε.\n\n%s" % exc)
            return
        self.quit_app()

    def open_backup(self):
        base = self.v_outdir.get().strip() or os.path.dirname(self.v_watch.get().strip())
        d = os.path.join(base, "backup") if base else ""
        if not d or not os.path.isdir(d):
            messagebox.showinfo(APP_NAME, "Δεν υπάρχει ακόμη φάκελος backup — "
                                          "θα δημιουργηθεί στην πρώτη εκτέλεση.")
            return
        try:
            os.startfile(d)                                  # Windows
        except AttributeError:
            subprocess.Popen(["xdg-open", d])

    def open_log_file(self):
        purge_old_logs()
        f = log_path()
        if not os.path.exists(f):
            write_log("(κενό log)")
        try:
            os.startfile(f)                                  # Windows
        except AttributeError:
            subprocess.Popen(["xdg-open", f])

    def log(self, msg):
        stamp = datetime.datetime.now().strftime("%H:%M:%S")
        tag = "info"
        if "ΣΦΑΛΜΑ" in msg:
            tag = "err"
        elif "OK" in msg or "επιτυχία" in msg:
            tag = "ok"
        elif msg.startswith("  ") or msg.startswith("==="):
            tag = "dim"
        self.txt_log.insert("end", "%s  " % stamp, "dim")
        self.txt_log.insert("end", "%s\n" % msg, tag)
        self.txt_log.see("end")
        write_log(msg)

    def run_once(self, silent=False):
        if self.worker and self.worker.is_alive():
            self.log("Η προηγούμενη εκτέλεση δεν έχει τελειώσει ακόμη.")
            return
        cfg = dict(self.collect())
        save_config(self.cfg)
        self.set_status("Εκτελείται…", COLORS["brand"])

        def job():
            try:
                run_pipeline(cfg, lambda m: self.after(0, self.log, m), self.stop_event)
                self.after(0, self._done_ok, silent)
            except StepError as exc:
                self.after(0, self._done_err, exc.full(), silent)
            except Exception:
                self.after(0, self._done_err, "Απρόσμενο σφάλμα:\n" + traceback.format_exc(), silent)

        self.worker = threading.Thread(target=job, daemon=True)
        self.worker.start()

    def _done_ok(self, silent):
        self.pending_error = None
        self.set_status("Επιτυχία", COLORS["ok"])
        if not silent:
            messagebox.showinfo(APP_NAME, "Η ενημέρωση των ζυγών ολοκληρώθηκε με επιτυχία.")

    def _done_err(self, text, silent):
        self.set_status("Σφάλμα", COLORS["err"])
        self.log("ΣΦΑΛΜΑ -> " + text.replace("\n", "\n         "))
        self.notify_error(text)

    def is_hidden(self):
        try:
            return self.state() in ("withdrawn", "iconic")
        except tk.TclError:
            return True

    def notify_error(self, text):
        """Κρυμμένο = ειδοποίηση κάτω δεξιά. Ορατό = κανονικό παράθυρο σφάλματος.

        Ποτέ modal παράθυρο πάνω σε κρυμμένο window: δεν φαίνεται και μπλοκάρει τη ροή.
        """
        self.pending_error = text
        if not self.is_hidden():
            messagebox.showerror(APP_NAME, text)
            return
        first = text.strip().split("\n")[0]
        if getattr(self, "tray", None) is not None:
            try:
                self.tray.title = "%s — ΣΦΑΛΜΑ" % APP_NAME
                self.tray.notify(first[:200] + "\n\nΆνοιξε το πρόγραμμα για λεπτομέρειες.",
                                 "%s — σφάλμα ενημέρωσης" % APP_NAME)
                return
            except Exception:
                pass
        self.bell()

    # ---------------- daemon ----------------
    def toggle_watch(self):
        if self.watching:
            self.watching = False
            self.stop_event.set()
            self.btn_watch.config(text="●  Έναρξη παρακολούθησης")
            self.set_status("Σε αναμονή", COLORS["muted"])
            self.log("Η παρακολούθηση σταμάτησε.")
            return
        self.collect()
        path = self.cfg.get("watch_file")
        if not path or not os.path.isfile(path):
            messagebox.showerror(APP_NAME, "Διάλεξε πρώτα το αρχείο που βγάζει το ERP.")
            return
        self.stop_event.clear()
        self.watching = True
        self.last_stamp = self._stamp(path)
        self.btn_watch.config(text="■  Διακοπή παρακολούθησης")
        self.set_status("Παρακολούθηση ενεργή", COLORS["ok"])
        self.log("Παρακολούθηση: %s (κάθε %ds)" % (path, self.cfg["poll_seconds"]))
        self.watch_thread = threading.Thread(target=self._watch_loop, daemon=True)
        self.watch_thread.start()

    @staticmethod
    def _stamp(path):
        try:
            st = os.stat(path)
            return (st.st_mtime, st.st_size)
        except OSError:
            return None

    def _wait_until_stable(self, path, tries=40):
        """Περιμένει να σταματήσει να γράφει το ERP: ίδιο μέγεθος σε 2 συνεχόμενους ελέγχους."""
        prev = None
        for _ in range(tries):
            if self.stop_event.is_set():
                return None
            time.sleep(0.7)
            cur = self._stamp(path)
            if cur is None:
                return None
            if cur == prev:
                return cur
            prev = cur
        self.after(0, self.log, "Προσοχή: το αρχείο του ERP γράφεται ακόμη μετά από 30 δευτερόλεπτα.")
        return self._stamp(path)

    def _watch_loop(self):
        while self.watching and not self.stop_event.is_set():
            time.sleep(max(1, int(self.cfg.get("poll_seconds", 3))))
            path = self.cfg.get("watch_file")
            cur = self._stamp(path)
            if cur is None or cur == self.last_stamp:
                continue
            self.after(0, self.log, "Εντοπίστηκε νέο αρχείο από το ERP — αναμονή να ολοκληρωθεί…")
            cur = self._wait_until_stable(path)
            if cur is None:
                continue
            self.last_stamp = cur
            self.after(0, self.log, "Το αρχείο ολοκληρώθηκε (%d bytes). Έναρξη ενημέρωσης." % cur[1])
            self.after(0, self.run_once, True)
            while self.worker and self.worker.is_alive():
                time.sleep(0.5)

    def on_close(self):
        """Το X ελαχιστοποιεί κάτω δεξιά — δεν κλείνει το πρόγραμμα."""
        try:
            save_config(self.collect())
        except Exception:
            pass
        if getattr(self, "tray", None) is not None:
            self.hide_to_tray()
            return
        # χωρίς pystray δεν υπάρχει εικονίδιο κάτω δεξιά
        if messagebox.askyesno(
                APP_NAME,
                "Να κλείσει τελείως το πρόγραμμα;\n\n"
                "ΟΧΙ = ελαχιστοποιείται στη γραμμή εργασιών και συνεχίζει να δουλεύει.\n\n"
                "(Για εικονίδιο κάτω δεξιά στην περιοχή ειδοποιήσεων χρειάζεται:\n"
                "pip install pystray Pillow)"):
            self.quit_app()
        else:
            self.iconify()


if __name__ == "__main__":
    # Ζωντανό αντίγραφο; Φέρ' το μπροστά και μην ανοίξεις δεύτερο.
    if wake_running_instance():
        sys.exit(0)

    # Αλλιώς ξεκινάμε κανονικά. Αν η θύρα κρατιέται από παλιά έκδοση ή άλλο
    # πρόγραμμα, ΔΕΝ μπλοκάρουμε τον χρήστη — απλώς χάνεται η προστασία διπλού
    # αντιγράφου γι' αυτή τη φορά και το γράφουμε στο log.
    singleton = claim_single_instance()
    startup_warning = None
    if not singleton:
        startup_warning = (
            "Η θύρα ελέγχου διπλού αντιγράφου είναι κατειλημμένη — πιθανότατα τρέχει "
            "παλιότερη έκδοση του AutoHost.\nΑν βλέπεις δύο εικονίδια, κλείσε το παλιό: "
            "Ctrl+Shift+Esc → %s.exe → Τερματισμός εργασίας." % APP_ID)

    purge_old_logs()
    write_log("=== Εκκίνηση %s (%s) ===" % (APP_NAME, APP_VERSION))
    app = App()
    if singleton:
        app.listen_for_wakeups()
    app.setup_tray()
    if startup_warning:
        app.log("Προσοχή: " + startup_warning.replace("\n", " "))
    if app.tray is None:
        app.log("Προσοχή: λείπει το pystray/Pillow — δεν υπάρχει εικονίδιο κάτω δεξιά "
                "(pip install pystray Pillow).")
    if "--tray" in sys.argv or "-t" in sys.argv:
        app.after(300, app.hide_to_tray)
        # με το boot ξεκινάει και η παρακολούθηση, ακόμη κι αν δεν είναι τσεκαρισμένο
        app.after(900, lambda: None if app.watching else app.toggle_watch())
    app.mainloop()
