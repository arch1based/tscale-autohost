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
APP_BUILD = "1.8.1"                        # σύγκριση για ενημερώσεις
APP_VERSION = "ICSautoScaleUpdater · έκδοση %s — Θεσσαλονίκη, Αύγουστος 2026" % APP_BUILD
UPDATE_VERSION_URL = "https://raw.githubusercontent.com/arch1based/tscale-autohost/main/VERSION"
UPDATE_PAGE_URL = "https://github.com/arch1based/tscale-autohost"
UPDATE_API_URL = "https://api.github.com/repos/arch1based/tscale-autohost/releases/latest"
UPDATE_ASSET = "ICSautoScaleUpdater.zip"
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
USER_PROFILES_PATH = os.path.join(CONFIG_DIR, "profiles.json")
PROFILE_KEYS = ("step2_format", "step2_delimiter", "step2_trailing_delim", "step2_quotes",
                "step2_in_encoding", "step2_out_encoding", "step2_final_newline",
                "step2_write_header", "step2_sanitize", "step2_dedupe",
                "step2_positions_bytes", "step2_startline", "step2_onebased")
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


RE_IP = re.compile(r"^\d{1,3}(\.\d{1,3}){3}$")


def ip_xml_path(exe_path):
    """Το ip.xml κάθεται δίπλα στο AutoProcess.exe."""
    return os.path.join(os.path.dirname(exe_path), "ip.xml") if exe_path else ""


def read_ips(exe_path):
    """Διαβάζει τις IP των ζυγών από το ip.xml του AutoProcess."""
    path = ip_xml_path(exe_path)
    if not path or not os.path.isfile(path):
        return []
    try:
        with open(path, "rb") as fh:
            text = fh.read().decode("utf-8-sig", "replace")
        return re.findall(r"<ip>\s*([^<\s]+)\s*</ip>", text)
    except Exception:
        return []


def write_ips(exe_path, ips):
    """Γράφει το ip.xml ακριβώς στη μορφή που περιμένει το AutoProcess.

    Κρατάμε BOM + CRLF όπως το πρωτότυπο: το AutoProcess είναι .NET εφαρμογή
    και δεν έχει νόημα να ρισκάρουμε διαφορετική μορφή για την ομορφιά.
    """
    path = ip_xml_path(exe_path)
    if not path:
        raise StepError("Βήμα 4", "Δεν έχει οριστεί η εφαρμογή του ζυγού.",
                        "Διάλεξε πρώτα το AutoProcess.exe.")
    bad = [ip for ip in ips if not RE_IP.match(ip)]
    if bad:
        raise StepError("Βήμα 4", "Μη έγκυρη διεύθυνση IP: %s" % ", ".join(bad),
                        "Σωστή μορφή: 10.130.20.49")
    body = "".join("  <ip>%s</ip>\r\n" % ip for ip in ips)
    text = ('<?xml version="1.0" encoding="utf-8"?>\r\n<ips>\r\n%s</ips>' % body)
    try:
        with open(path, "wb") as fh:
            fh.write(b"\xef\xbb\xbf" + text.encode("utf-8"))
    except Exception as exc:
        raise StepError("Βήμα 4", "Αδυναμία εγγραφής του ip.xml.", "%s\n%s" % (path, exc))
    return path


POLL_UNITS = {"δευτερόλεπτα": 1, "λεπτά": 60, "ώρες": 3600}


def seconds_to_unit(secs):
    """Δευτερόλεπτα -> (αριθμός, μονάδα) με τη μεγαλύτερη μονάδα που ταιριάζει ακριβώς."""
    secs = max(1, int(secs or 1))
    for name, mult in (("ώρες", 3600), ("λεπτά", 60)):
        if secs % mult == 0:
            return secs // mult, name
    return secs, "δευτερόλεπτα"


def parse_ips(text):
    """«10.0.0.1, 10.0.0.2» -> λίστα IP."""
    return [p.strip() for p in re.split(r"[,;\s]+", text or "") if p.strip()]


def bundled_autoprocess():
    """Ψάχνει AutoProcess σε υποφάκελο «autosend» δίπλα στο πρόγραμμα.

    Το AutoProcess είναι λογισμικό του κατασκευαστή των ζυγών και δεν διανέμεται
    μαζί μας. Αν όμως ο τεχνικός το αντιγράψει εκεί, το βρίσκουμε μόνοι μας
    ώστε να μη χρειάζεται αναζήτηση σε κάθε εγκατάσταση.
    """
    roots = [os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else APP_DIR,
             APP_DIR]
    for root in roots:
        p = os.path.join(root, "autosend", "AutoProcess.exe")
        if os.path.isfile(p):
            return p
    return ""


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


def download_update(url, dest, timeout=300, log=None):
    """Κατεβάζει το zip της νέας έκδοσης και το ελέγχει πριν χρησιμοποιηθεί."""
    data = _get(url, timeout, binary=True)
    if len(data) < 1024 * 1024:
        raise ValueError("το αρχείο που κατέβηκε είναι πολύ μικρό (%d bytes)" % len(data))
    if data[:2] != b"PK":                      # υπογραφή zip
        raise ValueError("το αρχείο που κατέβηκε δεν είναι zip")
    with open(dest, "wb") as fh:
        fh.write(data)
    import zipfile
    with zipfile.ZipFile(dest) as z:
        if z.testzip() is not None:
            raise ValueError("το zip είναι κατεστραμμένο")
        names = z.namelist()
    if not any(n.lower().endswith(APP_ID.lower() + ".exe") for n in names):
        raise ValueError("το πακέτο δεν περιέχει το %s.exe" % APP_ID)
    if log:
        log("  -> κατέβηκε: %.1f MB, %d αρχεία" % (len(data) / 1048576.0, len(names)))
    return dest


def extract_update(zip_path, target_dir, log=None):
    """Ξεπακετάρει τη νέα έκδοση σε προσωρινό φάκελο."""
    import zipfile
    shutil.rmtree(target_dir, ignore_errors=True)
    os.makedirs(target_dir, exist_ok=True)
    with zipfile.ZipFile(zip_path) as z:
        z.extractall(target_dir)
    exe = os.path.join(target_dir, APP_ID + ".exe")
    if not os.path.isfile(exe):
        raise ValueError("δεν βρέθηκε το %s.exe μέσα στο πακέτο" % APP_ID)
    if log:
        log("  -> ξεπακετάρισμα: %s" % target_dir)
    return target_dir


def install_update_and_restart(new_dir):
    """Αντιγράφει τη νέα έκδοση πάνω από την τρέχουσα και ξαναξεκινά.

    Η εφαρμογή δεν μπορεί να γράψει πάνω στα δικά της αρχεία όσο τρέχει, οπότε
    ένα .bat περιμένει να κλείσει, αντιγράφει και την ξανανοίγει. Οι ρυθμίσεις
    ζουν στο %APPDATA% και δεν αγγίζονται.
    """
    cur = sys.executable
    app_dir = os.path.dirname(cur)
    bat = os.path.join(os.environ.get("TEMP") or app_dir, "%s_update.bat" % APP_ID)
    script = ("@echo off\n"
              "chcp 65001 >nul\n"
              ":wait\n"
              'tasklist /FI "IMAGENAME eq {name}" 2>nul | find /I "{name}" >nul\n'
              "if not errorlevel 1 (\n"
              "  timeout /t 1 /nobreak >nul\n"
              "  goto wait\n"
              ")\n"
              'xcopy "{new}\\*" "{app}\\" /E /I /Y >nul\n'
              "if errorlevel 1 (\n"
              "  echo Η αντιγραφή απέτυχε — η παλιά έκδοση παραμένει.\n"
              "  pause\n"
              "  exit /b 1\n"
              ")\n"
              'start "" "{exe}"\n'
              'rmdir /s /q "{new}"\n'
              'del /q "%~f0"\n').format(name=os.path.basename(cur), new=new_dir,
                                        app=app_dir, exe=cur)
    with open(bat, "w", encoding="cp1253", errors="replace") as fh:
        fh.write(script)
    subprocess.Popen(["cmd", "/c", bat], creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


def load_config():
    with open(DEFAULT_PATH, "r", encoding="utf-8") as fh:
        cfg = json.load(fh)
    builtin_profiles = cfg.get("profiles", {})
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
                saved = json.load(fh)
            cfg.update(saved)
            migrated = migrate_config(cfg, saved)
            if path != CONFIG_PATH or migrated:
                save_config(cfg)                 # μεταφορά ή αναβάθμιση ρυθμίσεων
        except Exception:
            pass
    # Τα προφίλ ανήκουν στην έκδοση: αλλιώς μια παλιά αποθήκευση θα έκρυβε
    # για πάντα τα καινούρια.
    cfg["profiles"] = dict(builtin_profiles)
    for name, entry in load_user_profiles().items():
        cfg["profiles"]["★ " + name] = entry          # τα δικά μας πρώτα-πρώτα ξεχωριστά
    return cfg


def load_user_profiles():
    """Προφίλ που έφτιαξε ο τεχνικός — ξεχωριστά από τα ενσωματωμένα."""
    try:
        with open(USER_PROFILES_PATH, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return {}


def save_user_profiles(profiles):
    with open(USER_PROFILES_PATH, "w", encoding="utf-8") as fh:
        json.dump(profiles, fh, indent=2, ensure_ascii=False)


def migrate_config(cfg, saved):
    """Αναβαθμίζει παλιές αποθηκευμένες ρυθμίσεις. True αν άλλαξε κάτι.

    Οι ρυθμίσεις του χρήστη υπερισχύουν των προεπιλογών, οπότε μια παλιά τιμή
    μπορεί να επιβιώσει μιας διόρθωσης — εδώ την ξαναφέρνουμε στη σειρά.
    """
    changed = False
    if int(saved.get("config_version", 0)) < 2:
        # Πριν την 1.2.0 το Βήμα 2 υπέθετε πάντα cp1253 και κατέστρεφε τα UTF-8.
        cfg["src_encoding"] = "auto"
        cfg["dst_encoding"] = "auto"
        cfg["config_version"] = 2
        changed = True
    return changed


def save_config(cfg):
    data = {k: v for k, v in cfg.items() if k != "profiles"}
    with open(CONFIG_PATH, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)


# --------------------------------------------------------------------------
# VIMA 0 - host1 / host2
# --------------------------------------------------------------------------
def normalize_ext(value, fallback):
    """«csv» / «.csv» / κενό -> έγκυρη κατάληξη αρχείου."""
    ext = (value or "").strip()
    if not ext:
        return fallback
    return ext if ext.startswith(".") else "." + ext


def make_hosts(src, out_dir, log, cfg=None):
    """Αντιγράφει το αρχείο του ERP σε host1 και host2.

    Οι δύο ζυγαριές μπορεί να θέλουν διαφορετική κατάληξη: π.χ. host1.txt για
    T-Scale και host2.csv για Ishida. Το περιεχόμενο είναι το ίδιο — αλλάζει
    μόνο το όνομα, γιατί κάθε πρόγραμμα ψάχνει τη δική του κατάληξη.
    """
    cfg = cfg or {}
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

    src_ext = os.path.splitext(src)[1] or ".txt"
    exts = (normalize_ext(cfg.get("host1_ext"), src_ext),
            normalize_ext(cfg.get("host2_ext"), src_ext))
    made = []
    for name, ext in zip(("host1", "host2"), exts):
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
    """Ποια κωδικοσελίδα έχει το αρχείο: utf-8-sig / utf-8 / cp737 / cp1253."""
    if raw.startswith(b"\xef\xbb\xbf"):
        return "utf-8-sig"                    # UTF-8 με BOM
    if not any(b > 0x7F for b in raw):
        return "cp1253"                       # μόνο ASCII — αδιάφορο
    try:
        raw.decode("utf-8")                   # έγκυρο UTF-8 δεν είναι σύμπτωση
        return "utf-8"
    except UnicodeDecodeError:
        pass
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
    # Προεπιλογή: διάβασε και γράψε στην ΙΔΙΑ κωδικοσελίδα που έχει το αρχείο.
    # (Παλιότερα υπέθετε cp1253 και κατέστρεφε τα ελληνικά σε αρχεία UTF-8,
    #  μετατοπίζοντας και τις θέσεις των πεδίων στο επόμενο βήμα.)
    src_enc = cfg.get("src_encoding") or "auto"
    dst_enc = cfg.get("dst_encoding") or "auto"
    if src_enc == "auto":
        src_enc = detected
    if rules["cnv2win"]:
        dst_enc = "cp1253"
    elif rules["cnv2dos"]:
        dst_enc = "cp737"
    elif dst_enc == "auto":
        dst_enc = src_enc
    if src_enc != detected:
        log("  (σημείωση) το αρχείο μοιάζει %s, διαβάζεται ως %s" % (detected, src_enc))
    log("  κωδικοσελίδα: %s → %s" % (src_enc, dst_enc))
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
XFORMS = {
    "": "—",
    "comma2dot": "κόμμα → τελεία (13,9 → 13.9)",
    "dot2comma": "τελεία → κόμμα (13.9 → 13,9)",
    "digits": "μόνο ψηφία",
    "upper": "ΚΕΦΑΛΑΙΑ",
    "nospace": "χωρίς διπλά κενά",
    "strip0": "χωρίς μηδενικά μπροστά",
    "cents2comma": "λεπτά → τιμή με κόμμα (00315 → 3,15)",
    "cents2dot": "λεπτά → τιμή με τελεία (00315 → 3.15)",
    "prefix21": "πρόθεμα 21 (barcode ζυγαριάς: 00010 → 2100010)",
}


def extract_delimited_field(cols, f, off, delim):
    """Διαβάζει ένα πεδίο από ήδη χωρισμένη γραμμή (delimited host).

    «Θέση» θετική = συγκεκριμένη στήλη (1‑based, ή 0‑based αν off=0).
    «Θέση» αρνητική = μετρημένη από το τέλος (Python‑style: -1 η τελευταία
      στήλη) — χρήσιμο όταν οι πρώτες στήλες (π.χ. περιγραφή) μπορεί να
      περιέχουν τυχαία το ίδιο το διαχωριστικό και μετατοπίζουν τα υπόλοιπα.
    «Κόψιμο/Μήκος» θετικό = κόβει το πεδίο σε τόσους χαρακτήρες.
    «Κόψιμο/Μήκος» αρνητικό = ΣΥΝΕΝΩΝΕΙ όλες τις στήλες από τη «Θέση» μέχρι
      αυτή τη στήλη (αρνητική = από το τέλος), ξαναβάζοντας το διαχωριστικό
      ανάμεσά τους — έτσι δεν χάνεται τίποτα αν η περιγραφή περιέχει κόμμα.
    """
    pos = int(f.get("pos") or 0)
    cap = int(f.get("len") or 0)
    if pos == 0:
        return ""
    col = pos if pos < 0 else pos - off
    if cap < 0:
        end = cap + 1                    # inclusive αρνητικό τέλος -> Python slice
        end_slice = None if end == 0 else end
        try:
            span = cols[col:end_slice]
        except Exception:
            span = []
        return delim.join(c.strip() for c in span)
    if not (-len(cols) <= col < len(cols)):
        return ""
    val = cols[col].strip()
    return val[:cap] if cap > 0 else val


def apply_xform(value, kind):
    """Μετατροπή τιμής πεδίου πριν γραφτεί στο αρχείο."""
    if not kind:
        return value
    if kind == "comma2dot":
        return value.replace(",", ".")
    if kind == "dot2comma":
        return value.replace(".", ",")
    if kind == "digits":
        return "".join(ch for ch in value if ch.isdigit())
    if kind == "upper":
        return value.upper()
    if kind == "nospace":
        return " ".join(value.split())
    if kind == "strip0":
        return value.lstrip("0") or "0"
    if kind in ("cents2comma", "cents2dot"):
        digits = "".join(ch for ch in value if ch.isdigit())
        if not digits:
            return value
        whole, cents = str(int(digits) // 100), "%02d" % (int(digits) % 100)
        return whole + ("," if kind == "cents2comma" else ".") + cents
    if kind == "prefix21":
        return "21" + value if value else value
    return value


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
    is_delimited = cfg.get("step2_input_type", "fixed") == "delimited"
    # Σταθερή στήλη: fixed -> Μήκος 0, delimited -> καμία Στήλη ορισμένη (ακριβώς 0·
    # αρνητική Στήλη είναι έγκυρη θέση από το τέλος, όχι σταθερή τιμή).
    constants = [f["name"] for f in fields
                if (int(f.get("pos") or 0) == 0 if is_delimited else int(f.get("len") or 0) <= 0)]
    if constants:
        log("  (σταθερές στήλες: %s)" % ", ".join(constants))

    off = 1 if cfg.get("step2_onebased", True) else 0
    start_line = max(1, int(cfg.get("step2_startline", 1) or 1))
    out_enc = cfg.get("step2_out_encoding") or cfg.get("dst_encoding", "cp1253")

    try:
        with open(src, "rb") as fh:
            raw = fh.read()
    except Exception as exc:
        raise StepError("Βήμα 3", "Αδυναμία ανάγνωσης του host αρχείου.", "%s\n%s" % (src, exc))

    in_enc = cfg.get("step2_in_encoding") or "auto"
    if in_enc == "auto":
        in_enc = detect_codepage(raw)
        log("  <- κωδικοσελίδα εισόδου: %s (αυτόματα)" % in_enc)
    else:
        log("  <- κωδικοσελίδα εισόδου: %s" % in_enc)

    by_bytes = bool(cfg.get("step2_positions_bytes", False))
    if by_bytes:
        # Οι θέσεις μετρούν bytes: κόβουμε πρώτα και αποκωδικοποιούμε μετά.
        head = 3 if in_enc == "utf-8-sig" else 0
        lines = [ln[head:] if i == 0 else ln
                 for i, ln in enumerate(raw.split(b"\n"))]
        lines = [ln.rstrip(b"\r") for ln in lines]
    else:
        lines = raw.decode(in_enc, "replace").splitlines()

    input_type = cfg.get("step2_input_type", "fixed")
    in_delim = cfg.get("step2_input_delimiter", ",") or ","

    rows = []
    for line in lines[start_line - 1:]:
        if not (line.strip() if not by_bytes else line.strip(b" \t")):
            continue

        if input_type == "delimited":
            # Αρχείο ήδη χωρισμένο με διαχωριστικό (π.χ. CSV του ERP): κάθε
            # πεδίο διαβάζεται με τη «Θέση» ως αριθμό στήλης (1 = πρώτη· αρνητικός
            # αριθμός μετράει από το τέλος: -1 η τελευταία, -2 η προτελευταία…).
            txt = line if not by_bytes else line.decode(
                in_enc if in_enc != "utf-8-sig" else "utf-8", "replace")
            cols = next(csv.reader([txt], delimiter=in_delim))
            row = []
            for f in fields:
                val = extract_delimited_field(cols, f, off, in_delim)
                val = apply_xform(val, f.get("xform", ""))
                if not val and str(f.get("extra", "")).strip():
                    val = str(f["extra"]).strip()
                row.append(val)
            rows.append(row)
            continue

        row = []
        for f in fields:
            pos = int(f.get("pos") or 0) - off
            ln = int(f.get("len") or 0)
            val = line[pos:pos + ln] if pos >= 0 else line[:0]
            if by_bytes:
                val = val.decode(in_enc if in_enc != "utf-8-sig" else "utf-8", "replace")
            val = val.strip()
            val = apply_xform(val, f.get("xform", ""))
            if not val and str(f.get("extra", "")).strip():
                val = str(f["extra"]).strip()
            row.append(val)
        rows.append(row)

    fmt_delim = {"csv": ",", "tab": "\t", "semicolon": ";"}.get(
        cfg.get("step2_format", "csv"), cfg.get("step2_delimiter", ",") or ",")
    if cfg.get("step2_sanitize", True) and not cfg.get("step2_quotes") \
            and cfg.get("step2_format") != "fixed":
        # Οι ζυγοί δεν καταλαβαίνουν εισαγωγικά: ένα κόμμα μέσα σε περιγραφή
        # (π.χ. «ΧΑΛΒΑΣ 2,5KG») θα μετατόπιζε όλα τα επόμενα πεδία.
        hit = 0
        for row in rows:
            for i, v in enumerate(row):
                if fmt_delim in v:
                    row[i] = v.replace(fmt_delim, " ")
                    hit += 1
        if hit:
            log("  (καθαρίστηκαν %d πεδία που περιείχαν «%s»)"
                % (hit, "TAB" if fmt_delim == "\t" else fmt_delim))

    if cfg.get("step2_dedupe") and rows:
        before = len(rows)
        keep = {}
        for row in rows:
            keep[row[0]] = row                     # κρατά την τελευταία εγγραφή
        rows = list(keep.values())
        if before != len(rows):
            log("  (αφαιρέθηκαν %d διπλοεγγραφές, έμειναν %d κωδικοί)"
                % (before - len(rows), len(rows)))

    if not rows:
        raise StepError("Βήμα 3", "Το host αρχείο δεν περιέχει γραμμές δεδομένων.",
                        "Αρχείο: %s\nΓραμμή έναρξης: %d" % (src, start_line))

    fmt = cfg.get("step2_format", "csv")
    try:
        if fmt == "fixed":
            # σταθερό πλάτος: κάθε πεδίο γεμίζει το δικό του μήκος
            with open(dst, "w", encoding=out_enc, errors="replace", newline="\r\n") as fh:
                if cfg.get("step2_write_header", True):
                    fh.write("".join(f["name"][:int(f["len"])].ljust(int(f["len"]))
                                     for f in fields) + "\n")
                for row in rows:
                    fh.write("".join(v[:int(f["len"])].ljust(int(f["len"]))
                                     for v, f in zip(row, fields)) + "\n")
        else:
            delim = {"csv": ",", "tab": "\t", "semicolon": ";"}.get(
                fmt, cfg.get("step2_delimiter", ",") or ",")
            tail = delim if cfg.get("step2_trailing_delim") else ""
            with open(dst, "w", encoding=out_enc, errors="replace", newline="") as fh:
                if cfg.get("step2_quotes"):
                    # πρότυπο CSV: εισαγωγικά όπου το πεδίο περιέχει διαχωριστικό
                    w = csv.writer(fh, delimiter=delim, lineterminator="\r\n")
                    if cfg.get("step2_write_header", True):
                        w.writerow([f["name"] for f in fields] + ([""] if tail else []))
                    for row in rows:
                        w.writerow(list(row) + ([""] if tail else []))
                else:
                    # όπως το θέλουν οι ζυγοί: σκέτα πεδία, χωρίς εισαγωγικά
                    out = []
                    if cfg.get("step2_write_header", True):
                        out.append(delim.join(f["name"] for f in fields) + tail)
                    out.extend(delim.join(row) + tail for row in rows)
                    fh.write("\r\n".join(out))
                    if cfg.get("step2_final_newline", True):
                        fh.write("\r\n")
    except Exception as exc:
        raise StepError("Βήμα 3", "Αδυναμία εγγραφής του αρχείου προϊόντων.",
                        "%s\n%s" % (dst, exc))

    log("  -> %s (%d εγγραφές, %d πεδία, κωδικοσελίδα %s)"
        % (dst, len(rows), len(fields), out_enc))
    return dst


# --------------------------------------------------------------------------
# VIMA 4 - Efarmogi zygou (AutoProcess i antistoixi allou zygou)
# --------------------------------------------------------------------------
# Οι επιπλέον ζυγοί: κάθε ένας έχει δικό του πρόγραμμα αποστολής και δικό του
# αρχείο. Το κλειδί μπαίνει μπροστά από κάθε ρύθμιση (π.χ. ishida_exe).
EXTRA_SENDERS = (("ishida", "Ishida"), ("ils", "ILS"))


def run_sender(exe, secs, kill, log, stop_event=None, label="εφαρμογή ζυγού"):
    """Τρέχει ένα πρόγραμμα αποστολής και το κλείνει όταν περάσει ο χρόνος."""
    name = os.path.basename(exe)
    try:
        proc = subprocess.Popen([exe], cwd=os.path.dirname(exe))
    except Exception as exc:
        raise StepError("Βήμα 4", "Αδυναμία εκκίνησης: %s" % label, "%s\n%s" % (exe, exc))

    log("  -> %s (%s): τρέχει για %d δευτερόλεπτα…" % (name, label, secs))
    deadline = time.time() + secs
    while time.time() < deadline:
        if proc.poll() is not None:
            log("  -> %s: τερμάτισε μόνο του (κωδικός %s)." % (name, proc.returncode))
            return
        if stop_event is not None and stop_event.is_set():
            break
        time.sleep(0.5)

    if proc.poll() is None and kill:
        try:
            proc.terminate()
            time.sleep(1.5)
            if proc.poll() is None:
                proc.kill()
            log("  -> %s: έκλεισε μετά τα %d δευτερόλεπτα." % (name, secs))
        except Exception as exc:
            raise StepError("Βήμα 4", "Αδυναμία τερματισμού: %s" % label, str(exc))


def deliver_file(src, dst, log, label):
    """Αντιγράφει το αρχείο εκεί που το περιμένει το πρόγραμμα του ζυγού."""
    if not dst:
        return
    if not src or not os.path.isfile(src):
        raise StepError("Βήμα 4", "Δεν βρέθηκε το αρχείο για %s." % label,
                        "Αρχείο: %s" % src)
    folder = os.path.dirname(dst)
    if folder and not os.path.isdir(folder):
        try:
            os.makedirs(folder)
        except Exception as exc:
            raise StepError("Βήμα 4", "Αδυναμία δημιουργίας φακέλου για %s." % label,
                            "%s\n%s" % (folder, exc))
    try:
        shutil.copyfile(src, dst)
    except Exception as exc:
        raise StepError("Βήμα 4", "Αδυναμία αντιγραφής αρχείου για %s." % label,
                        "%s -> %s\n%s" % (src, dst, exc))
    log("  -> %s: %s -> %s" % (label, os.path.basename(src), dst))


def run_step3(cfg, log, stop_event=None):
    """Βήμα 4: στέλνει σε T-Scale και, προαιρετικά, σε Ishida / ILS."""
    exe = (cfg.get("step3_exe") or "").strip()
    secs = int(cfg.get("step3_seconds", 120) or 120)
    if not exe or not os.path.isfile(exe):
        raise StepError("Βήμα 4", "Δεν βρέθηκε η εφαρμογή του ζυγού.", exe)

    # Οι IP γράφονται λίγο πριν την εκκίνηση, ώστε να μη μείνει ποτέ το
    # AutoProcess με παλιές διευθύνσεις επειδή ξεχάστηκε μια αποθήκευση.
    ips = parse_ips(cfg.get("scale_ips", ""))
    if ips:
        current = read_ips(exe)
        if current != ips:
            write_ips(exe, ips)
            log("  -> ενημερώθηκε το ip.xml: %s" % ", ".join(ips))

    run_sender(exe, secs, cfg.get("step3_kill", True), log, stop_event, "T-Scale")

    for key, label in EXTRA_SENDERS:
        if not cfg.get("%s_enabled" % key):
            continue
        x_exe = (cfg.get("%s_exe" % key) or "").strip()
        if not x_exe or not os.path.isfile(x_exe):
            raise StepError("Βήμα 4", "Δεν βρέθηκε το πρόγραμμα για %s." % label,
                            x_exe or "(δεν έχει οριστεί)")
        deliver_file((cfg.get("%s_src" % key) or "").strip(),
                     (cfg.get("%s_dst" % key) or "").strip(), log, label)
        run_sender(x_exe, int(cfg.get("%s_seconds" % key, 120) or 120),
                   cfg.get("%s_kill" % key, True), log, stop_event, label)


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


def _show(text, width=100):
    """Κάνει ορατά τα κρυφά: CRLF, κενά στο τέλος."""
    t = text.replace("\r", "<CR>").replace("\n", "<LF>")
    return (t[:width] + "…") if len(t) > width else t


def build_preview(cfg):
    """Τρέχει όλα τα βήματα σε προσωρινό φάκελο και επιστρέφει αναλυτική αναφορά.

    Δεν αγγίζει τα πραγματικά αρχεία και δεν ανοίγει την εφαρμογή του ζυγού.
    """
    out = []
    add = out.append
    tmp = os.path.join(CONFIG_DIR, "preview")
    shutil.rmtree(tmp, ignore_errors=True)
    os.makedirs(tmp, exist_ok=True)

    add("ΠΡΟΕΠΙΣΚΟΠΗΣΗ — τίποτα δεν στέλνεται, τα αρχεία γράφονται σε προσωρινό φάκελο")
    add("=" * 78)

    # ---------------- Βήμα 1 ----------------
    src = cfg.get("watch_file")
    add("\nΒΗΜΑ 1 · Αρχείο ERP → host1 / host2")
    add("-" * 78)
    if not src or not os.path.isfile(src):
        add("  ΣΦΑΛΜΑ: δεν βρέθηκε το αρχείο του ERP: %s" % src)
        return "\n".join(out)
    raw = open(src, "rb").read()
    add("  αρχείο   : %s" % src)
    add("  μέγεθος  : %d bytes | κωδικοσελίδα: %s | CRLF: %d | LF μόνο: %d"
        % (len(raw), detect_codepage(raw), raw.count(b"\r\n"),
           raw.count(b"\n") - raw.count(b"\r\n")))
    host1, _h2 = make_hosts(src, tmp, lambda m: None, cfg)
    add("  δημιουργήθηκαν: host1 / host2 (αντίγραφα, χωρίς αλλαγές)")
    lines_in = raw.decode(detect_codepage(raw), "replace").splitlines()
    for i, l in enumerate(lines_in[:2]):
        add("  γραμμή %d (%d χαρ.): %s" % (i + 1, len(l), _show(l)))

    # ---------------- Βήμα 2 ----------------
    current = host1
    add("\nΒΗΜΑ 2 · Μετατροπή")
    add("-" * 78)
    if not cfg.get("step1_enabled"):
        add("  απενεργοποιημένο — το Βήμα 3 θα διαβάσει το host1")
    else:
        rules = parse_step1_script(cfg.get("step1_script", ""), host1)
        add("  κανόνες: CNV2WIN=%s | SKIPLINE=%s | PADLINE=%s | αντικαταστάσεις: %d"
            % (rules["cnv2win"], rules["skip"], rules["pad"], len(rules["ifexist"])))
        for pos, val, then in rules["ifexist"]:
            add("    στη θέση %d: «%s» → «%s»" % (pos, val, then))
        before = lines_in[0] if lines_in else ""
        s1_logs = []
        current = run_step1(dict(cfg, step1_external_exe=""), host1, s1_logs.append)
        for l in s1_logs:
            add("  " + l.strip())
        after_raw = open(current, "rb").read()
        after = after_raw.decode(detect_codepage(after_raw), "replace").splitlines()
        add("  έξοδος   : %s" % os.path.basename(current))
        add("  πριν     : %s" % _show(before))
        add("  μετά     : %s" % _show(after[0] if after else ""))
        if before == (after[0] if after else ""):
            add("  (καμία αλλαγή στην πρώτη γραμμή)")

    # ---------------- Βήμα 3 ----------------
    add("\nΒΗΜΑ 3 · Αρχείο προϊόντων")
    add("-" * 78)
    if not cfg.get("step2_enabled"):
        add("  απενεργοποιημένο")
        return "\n".join(out)

    ext = ".csv" if cfg.get("step2_format", "csv") in ("csv", "semicolon") else ".txt"
    cfg2 = dict(cfg, step2_output=os.path.join(tmp, "product" + ext))
    logs = []
    dst = run_step2(cfg2, current, logs.append)
    for l in logs:
        add("  " + l.strip())

    # ανάλυση πεδίων στην πρώτη γραμμή δεδομένων
    src_lines = open(current, "rb").read()
    enc = cfg.get("step2_in_encoding") or "auto"
    enc = detect_codepage(src_lines) if enc == "auto" else enc
    body = src_lines.decode(enc, "replace").splitlines()
    start = max(1, int(cfg.get("step2_startline", 1) or 1))
    sample = body[start - 1] if len(body) >= start else ""
    off = 1 if cfg.get("step2_onebased", True) else 0
    input_type = cfg.get("step2_input_type", "fixed")
    in_delim = cfg.get("step2_input_delimiter", ",") or ","
    if input_type == "delimited":
        cols_sample = next(csv.reader([sample], delimiter=in_delim)) if sample else []
        add("\n  πώς κόβεται η γραμμή %d (%d στήλες, διαχωριστικό «%s»):"
            % (start, len(cols_sample), in_delim))
        add("  %-16s %6s %6s  %-24s %s" % ("ΠΕΔΙΟ", "ΣΤΗΛΗ", "ΩΣ", "ΤΙ ΚΟΒΕΙ", "ΜΕΤΑ ΤΗ ΜΕΤΑΤΡΟΠΗ"))
        for f in cfg.get("step2_fields", []):
            if not f.get("enabled"):
                continue
            rawv = extract_delimited_field(cols_sample, f, off, in_delim)
            val = apply_xform(rawv, f.get("xform", ""))
            if not val and str(f.get("extra", "")).strip():
                val = str(f["extra"]).strip()
            note = "(σταθερή στήλη)" if not f.get("pos") else \
                   ("(συνένωση στηλών)" if int(f.get("len") or 0) < 0 else "")
            add("  %-16s %6s %6s  %-24s %s %s" % (f["name"], f.get("pos"), f.get("len") or "—",
                                                  "«%s»" % rawv, "«%s»" % val, note))
    else:
        add("\n  πώς κόβεται η γραμμή %d (μήκος %d χαρακτήρες):" % (start, len(sample)))
        add("  %-16s %5s %5s  %-24s %s" % ("ΠΕΔΙΟ", "ΘΕΣΗ", "ΜΗΚΟΣ", "ΤΙ ΚΟΒΕΙ", "ΜΕΤΑ ΤΗ ΜΕΤΑΤΡΟΠΗ"))
        for f in cfg.get("step2_fields", []):
            if not f.get("enabled"):
                continue
            pos, ln = int(f.get("pos") or 0) - off, int(f.get("len") or 0)
            rawv = sample[pos:pos + ln] if ln > 0 and pos >= 0 else ""
            val = apply_xform(rawv.strip(), f.get("xform", ""))
            if not val and str(f.get("extra", "")).strip():
                val = str(f["extra"]).strip()
            note = "" if ln > 0 else "(σταθερή στήλη)"
            add("  %-16s %5s %5s  %-24s %s %s" % (f["name"], f.get("pos"), f.get("len"),
                                                  "«%s»" % rawv, "«%s»" % val, note))

    # ---------------- το τελικό αρχείο ----------------
    d = open(dst, "rb").read()
    add("\n  ΤΕΛΙΚΟ ΑΡΧΕΙΟ: %s" % cfg.get("step2_output") or dst)
    add("  μέγεθος: %d bytes | κωδικοσελίδα: %s | CRLF: %d | BOM: %s"
        % (len(d), cfg.get("step2_out_encoding", "cp1253"), d.count(b"\r\n"),
           d[:3] == b"\xef\xbb\xbf"))
    txt = d.decode(cfg.get("step2_out_encoding", "cp1253"), "replace")
    for i, l in enumerate(txt.split("\r\n")[:4]):
        add("  %s %s" % ("επικεφαλίδα:" if i == 0 else "γραμμή %d:   " % i, _show(l)))
    add("  τελευταία bytes: %r" % d[-24:])
    delim = {"csv": ",", "tab": "\t", "semicolon": ";"}.get(cfg.get("step2_format", "csv"), ",")
    counts = sorted({l.count(delim) for l in txt.split("\r\n") if l})
    add("  διαχωριστικά ανά γραμμή: %s %s" % (counts,
        "OK — σταθερή δομή" if len(counts) == 1 else "ΠΡΟΣΟΧΗ: ανομοιόμορφες γραμμές!"))

    # ---------------- Βήμα 4 ----------------
    add("\nΒΗΜΑ 4 · Εφαρμογή ζυγού")
    add("-" * 78)
    if not cfg.get("step3_enabled"):
        add("  απενεργοποιημένο")
    else:
        exe = cfg.get("step3_exe", "")
        add("  θα εκτελεστεί: %s" % exe)
        add("  υπάρχει: %s | διάρκεια: %s δευτ." % (os.path.isfile(exe), cfg.get("step3_seconds")))
        wanted = parse_ips(cfg.get("scale_ips", ""))
        current = read_ips(exe)
        add("  IP ζυγών (ρύθμιση): %s" % (", ".join(wanted) or "—"))
        add("  IP ζυγών (ip.xml):  %s%s" % (", ".join(current) or "—",
            "" if not wanted or current == wanted else "  → θα ενημερωθεί πριν την αποστολή"))

        for key, label in EXTRA_SENDERS:
            if not cfg.get("%s_enabled" % key):
                add("  %-8s: απενεργοποιημένο" % label)
                continue
            x_exe = (cfg.get("%s_exe" % key) or "").strip()
            src = (cfg.get("%s_src" % key) or "").strip()
            dst = (cfg.get("%s_dst" % key) or "").strip()
            add("  %-8s: %s (υπάρχει: %s, %s δευτ.)"
                % (label, x_exe or "—", os.path.isfile(x_exe), cfg.get("%s_seconds" % key)))
            if dst:
                add("            αρχείο: %s → %s%s"
                    % (src or "—", dst, "" if os.path.isfile(src) else "   ΠΡΟΣΟΧΗ: δεν βρέθηκε"))
    add("\n(τα αρχεία της προεπισκόπησης: %s)" % tmp)
    return "\n".join(out)


def run_pipeline(cfg, log, stop_event=None):
    log("=== Έναρξη διαδικασίας %s ===" % datetime.datetime.now().strftime("%d/%m/%Y %H:%M:%S"))
    host1, host2 = make_hosts(cfg.get("watch_file"), cfg.get("output_dir"), log, cfg)
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

    def _add_edit_menu(self, widget):
        """Δεξί κλικ + συντομεύσεις που δουλεύουν και σε ελληνική διάταξη.

        Το Tk δένει τα Ctrl+C/V στο γράμμα, οπότε με ελληνικό πληκτρολόγιο
        (ψ, χ, ω) δεν λειτουργούσαν καθόλου. Εδώ τα πιάνουμε από τον κωδικό
        του πλήκτρου, ανεξάρτητα από τη γλώσσα.
        """
        menu = tk.Menu(widget, tearoff=0)
        menu.add_command(label="Αποκοπή", command=lambda: widget.event_generate("<<Cut>>"))
        menu.add_command(label="Αντιγραφή", command=lambda: widget.event_generate("<<Copy>>"))
        menu.add_command(label="Επικόλληση", command=lambda: widget.event_generate("<<Paste>>"))
        menu.add_separator()
        menu.add_command(label="Επιλογή όλων",
                         command=lambda: widget.event_generate("<<SelectAll>>"))

        def popup(e):
            try:
                widget.focus_set()
                menu.tk_popup(e.x_root, e.y_root)
            finally:
                menu.grab_release()

        def ctrl(e):
            key = (e.keysym or "").lower()
            code = getattr(e, "keycode", 0)
            action = None
            if key == "c" or code in (67, 54):
                action = "<<Copy>>"
            elif key == "v" or code in (86, 55):
                action = "<<Paste>>"
            elif key == "x" or code in (88, 53):
                action = "<<Cut>>"
            elif key == "a" or code in (65, 38):
                action = "<<SelectAll>>"
            if action:
                widget.event_generate(action)
                return "break"

        widget.bind("<Button-3>", popup)
        widget.bind("<Control-KeyPress>", ctrl)
        return widget

    def _console(self, parent, height, font):
        box = scrolledtext.ScrolledText(
            parent, height=height, font=font, background=COLORS["console"],
            foreground=COLORS["console_fg"], insertbackground=COLORS["console_fg"],
            relief="flat", borderwidth=0, padx=12, pady=10,
            selectbackground=COLORS["brand"])
        return self._add_edit_menu(box)

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
        ttk.Button(bar, text="🔍  Προεπισκόπηση", command=self.show_preview).pack(side="left", padx=8)
        self.btn_watch = ttk.Button(bar, text="●  Έναρξη παρακολούθησης", command=self.toggle_watch)
        self.btn_watch.pack(side="left")
        ttk.Button(bar, text="Αποθήκευση ρυθμίσεων", command=self.on_save).pack(side="left")
        ttk.Button(bar, text="Έξοδος", style="Ghost.TButton",
                   command=self.quit_app).pack(side="right")
        ttk.Button(bar, text="Ελαχιστοποίηση κάτω δεξιά", style="Ghost.TButton",
                   command=self.hide_to_tray).pack(side="right")

        # Τα δευτερεύοντα σε μενού: σε στενό παράθυρο τα κουμπιά της μπάρας
        # δεν χωρούσαν και κόβονταν.
        tools = ttk.Menubutton(bar, text="⚙  Εργαλεία  ▾", style="Ghost.TButton")
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
        self._add_edit_menu(ttk.Entry(parent, textvariable=var, width=78)
                            ).grid(row=r, column=1, sticky="we", padx=6)

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
        ext = ttk.Frame(f)
        ext.grid(row=2, column=0, columnspan=3, sticky="w", pady=(6, 0))
        ttk.Label(ext, text="Κατάληξη:").pack(side="left")
        ttk.Label(ext, text="host1", style="Hint.TLabel").pack(side="left", padx=(10, 2))
        self.v_ext1 = tk.StringVar(value="")
        self._add_edit_menu(ttk.Entry(ext, textvariable=self.v_ext1, width=6)).pack(side="left")
        ttk.Label(ext, text="host2", style="Hint.TLabel").pack(side="left", padx=(12, 2))
        self.v_ext2 = tk.StringVar(value="csv")
        self._add_edit_menu(ttk.Entry(ext, textvariable=self.v_ext2, width=6)).pack(side="left")
        ttk.Label(ext, style="Hint.TLabel",
                  text="(κενό = ίδια με το αρχείο του ERP · π.χ. txt για T-Scale, csv για Ishida)"
                  ).pack(side="left", padx=10)

        row = ttk.Frame(f)
        row.grid(row=3, column=0, columnspan=3, sticky="w", pady=8)
        ttk.Label(row, text="Έλεγχος για νέο αρχείο κάθε:").pack(side="left")
        ttk.Entry(row, textvariable=self.v_poll, width=6).pack(side="left", padx=6)
        self.v_poll_unit = tk.StringVar(value="δευτερόλεπτα")
        ttk.Combobox(row, textvariable=self.v_poll_unit, width=13, state="readonly",
                     values=("δευτερόλεπτα", "λεπτά", "ώρες")).pack(side="left")
        self.lbl_poll = ttk.Label(row, style="Hint.TLabel")
        self.lbl_poll.pack(side="left", padx=8)
        for v in (self.v_poll, self.v_poll_unit):
            v.trace_add("write", lambda *_: self.refresh_poll_hint())
        ttk.Checkbutton(row, text="Αυτόματη έναρξη με το άνοιγμα",
                        variable=self.v_auto).pack(side="left", padx=12)
        bk = ttk.Frame(f)
        bk.grid(row=7, column=0, columnspan=3, sticky="w", pady=(2, 0))
        self.v_backup = tk.BooleanVar(value=True)
        self.v_keep = tk.StringVar(value="3")
        ttk.Checkbutton(bk, text="Κράτα αντίγραφα των τελευταίων", variable=self.v_backup).pack(side="left")
        ttk.Entry(bk, textvariable=self.v_keep, width=4).pack(side="left", padx=5)
        ttk.Label(bk, text="εκτελέσεων στον φάκελο backup").pack(side="left")
        ttk.Button(bk, text="Άνοιγμα backup", style="Ghost.TButton",
                   command=self.open_backup).pack(side="left", padx=10)

        self.v_popup = tk.BooleanVar(value=False)
        ttk.Checkbutton(bk, text="Μήνυμα στο τέλος κάθε εκτέλεσης", variable=self.v_popup
                        ).pack(side="left", padx=14)

        self.v_boot = tk.BooleanVar(value=autostart_enabled())
        ttk.Checkbutton(f, variable=self.v_boot, command=self.on_boot_toggle,
                        text="Εκκίνηση με τα Windows — ξεκινά ελαχιστοποιημένο "
                             "στην περιοχή ειδοποιήσεων (κάτω δεξιά)"
                        ).grid(row=5, column=0, columnspan=3, sticky="w", pady=(2, 0))
        ttk.Label(f, style="Hint.TLabel", wraplength=880, justify="left",
                  text="Μόλις αλλάξει το αρχείο του ERP, δημιουργούνται αυτόματα τα host1.<κατάληξη> και "
                       "host2.<κατάληξη> στον φάκελο εξόδου και ξεκινούν τα ενεργοποιημένα βήματα."
                  ).grid(row=8, column=0, columnspan=3, sticky="w", pady=10)

    def _build_tab1(self):
        f = self.tab1
        self.v_s1 = tk.BooleanVar()
        ttk.Checkbutton(f, style="Big.TCheckbutton", text="Ενεργοποίηση Βήματος 2 — Μετατροπή αρχείου", variable=self.v_s1).pack(anchor="w")
        ttk.Label(f, style="Hint.TLabel", justify="left", wraplength=920,
                  text="Οι κανόνες είναι σε απλό κείμενο για να τους αλλάζεις ανά ζυγαριά.\n"
                       "<HOST1> = το host1 που μόλις δημιουργήθηκε, <OUT1> = αυτόματο όνομα εξόδου.\n"
                       "Εντολές: INPUTFIL= / OUTPUTFL= / CNV2WIN / CNV2DOS / UPPERCASE / SKIPLINE=n / "
                       "PADLINE=n / DESCRIPT=θέση μήκος / IFEXISTn=θέση=[τιμή] THEN=[τιμή]\n"
                       "Γράψε ελεύθερα όσες γραμμές θες. Δεξί κλικ για αντιγραφή/επικόλληση "
                       "(δουλεύει και με ελληνικό πληκτρολόγιο)."
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

        prof = ttk.Frame(f)
        prof.pack(fill="x", pady=(2, 6))
        ttk.Label(prof, text="Προφίλ ζυγού:").pack(side="left")
        names = list(self.cfg.get("profiles", {}))
        self.v_profile = tk.StringVar(value=names[0] if names else "")
        self.cmb_profile = ttk.Combobox(prof, textvariable=self.v_profile, values=names,
                                        state="readonly", width=36)
        self.cmb_profile.pack(side="left", padx=6)
        ttk.Button(prof, text="Φόρτωση", style="Accent.TButton",
                   command=lambda: self.load_profile(self.v_profile.get())).pack(side="left")
        ttk.Button(prof, text="Αποθήκευση ως…", command=self.save_profile).pack(side="left", padx=6)
        ttk.Button(prof, text="Διαγραφή", style="Ghost.TButton",
                   command=self.delete_profile).pack(side="left")

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
        intype = ttk.Frame(f)
        intype.pack(fill="x", pady=(2, 4))
        ttk.Label(intype, text="Αρχείο εισόδου:").pack(side="left")
        self.v_input_type = tk.StringVar(value="fixed")
        ttk.Radiobutton(intype, text="Σταθερού πλάτους (θέσεις/μήκη)", value="fixed",
                        variable=self.v_input_type,
                        command=self.on_input_type_change).pack(side="left", padx=(8, 0))
        ttk.Radiobutton(intype, text="Με διαχωριστικό — στήλες (π.χ. CSV του ERP)", value="delimited",
                        variable=self.v_input_type,
                        command=self.on_input_type_change).pack(side="left", padx=(10, 0))
        ttk.Label(intype, text="διαχωριστικό:").pack(side="left", padx=(14, 2))
        self.v_in_delim = tk.StringVar(value=",")
        self._add_edit_menu(ttk.Entry(intype, textvariable=self.v_in_delim, width=3)
                            ).pack(side="left")

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

        extra = ttk.Frame(f)
        extra.pack(fill="x", pady=(2, 2))
        self.v_tail = tk.BooleanVar(value=False)
        self.v_quotes = tk.BooleanVar(value=False)
        ttk.Checkbutton(extra, text="Διαχωριστικό και στο τέλος κάθε γραμμής (π.χ. ;…;)",
                        variable=self.v_tail).pack(side="left")
        ttk.Checkbutton(extra, text="Εισαγωγικά όπου χρειάζεται (πρότυπο CSV)",
                        variable=self.v_quotes).pack(side="left", padx=14)

        extra2 = ttk.Frame(f)
        extra2.pack(fill="x", pady=(0, 2))
        self.v_sanitize = tk.BooleanVar(value=True)
        self.v_dedupe = tk.BooleanVar(value=False)
        ttk.Checkbutton(extra2, text="Καθάρισε το διαχωριστικό μέσα στις περιγραφές",
                        variable=self.v_sanitize).pack(side="left")
        ttk.Checkbutton(extra2, text="Μία εγγραφή ανά κωδικό (κρατά την τελευταία)",
                        variable=self.v_dedupe).pack(side="left", padx=14)
        self.v_finalnl = tk.BooleanVar(value=True)
        ttk.Checkbutton(extra2, text="Αλλαγή γραμμής στο τέλος του αρχείου",
                        variable=self.v_finalnl).pack(side="left")
        ttk.Checkbutton(o, text="Θέση 1 = πρώτος χαρακτήρας", variable=self.v_onebased).pack(side="left", padx=12)

        self.lbl_intype_hint = ttk.Label(f, style="Hint.TLabel", justify="left", wraplength=920)
        self.lbl_intype_hint.pack(anchor="w", pady=(0, 4))

        b = ttk.Frame(f)
        b.pack(side="bottom", fill="x", pady=(6, 0))
        ttk.Button(b, text="Εναλλαγή ✓ (ή Space)", command=self.toggle_field).pack(side="left")
        ttk.Button(b, text="Επεξεργασία γραμμής", command=self.on_edit_cell).pack(side="left", padx=6)
        ttk.Button(b, text="Αρχικοποίηση", command=self.reset_fields).pack(side="left")
        # Ο πίνακας φτιάχνεται ΜΕΣΑ στο πλαίσιό του: αλλιώς μένει από κάτω του
        # στη σειρά σχεδίασης και δεν φαίνεται καθόλου.
        tree_box = ttk.Frame(f)
        tree_box.pack(fill="x", pady=4)

        enc = ttk.Frame(f)
        enc.pack(fill="x", pady=(6, 2))
        ttk.Label(enc, text="Κωδικοσελίδα — είσοδος:").pack(side="left")
        self.v_enc_in = tk.StringVar(value="auto")
        ttk.Combobox(enc, textvariable=self.v_enc_in, width=12, state="readonly",
                     values=("auto", "utf-8", "utf-8-sig", "cp1253", "cp737")
                     ).pack(side="left", padx=6)
        ttk.Label(enc, text="έξοδος:").pack(side="left", padx=(10, 0))
        self.v_enc_out = tk.StringVar(value="cp1253")
        ttk.Combobox(enc, textvariable=self.v_enc_out, width=12, state="readonly",
                     values=("cp1253", "utf-8", "utf-8-sig", "cp737")
                     ).pack(side="left", padx=6)
        self.v_bytes = tk.BooleanVar(value=False)
        ttk.Checkbutton(enc, text="Οι θέσεις μετρούν bytes (αρχεία UTF-8)",
                        variable=self.v_bytes).pack(side="left", padx=12)
        ttk.Label(f, style="Hint.TLabel", justify="left", wraplength=920,
                  text="«auto» αναγνωρίζει μόνο του UTF-8 / Windows-1253 / DOS-737. "
                       "ΠΡΟΣΟΧΗ: για ελληνικά η ΕΞΟΔΟΣ πρέπει να είναι cp1253 — με utf-8 ο "
                       "ζυγός δείχνει ακαταλαβίστικους χαρακτήρες."
                  ).pack(anchor="w", pady=(0, 2))

        cols = ("name", "out", "pos", "len", "xform", "extra")
        self.tree = ttk.Treeview(tree_box, columns=cols, show="headings",
                                 height=8, selectmode="browse")
        for c, t, w in (("name", "Περιγραφή", 190), ("out", "Για έξοδο", 90),
                        ("pos", "Από Θέση", 80), ("len", "Μήκος", 80),
                        ("xform", "Μετατροπή", 190), ("extra", "Εξτρα", 130)):
            self.tree.heading(c, text=t)
            self.tree.column(c, width=w, anchor="w")
        self.tree.bind("<Double-1>", self.on_edit_cell)
        self.tree.bind("<space>", lambda e: self.toggle_field())
        sb = ttk.Scrollbar(tree_box, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.tree.pack(side="left", fill="both", expand=True)

        ttk.Button(b, text="Δοκιμή · προεπισκόπηση", style="Accent.TButton",
                   command=self.preview_csv).pack(side="right")

    def _build_tab3(self):
        f = self.tab3
        self.v_s3 = tk.BooleanVar()
        ttk.Checkbutton(f, style="Big.TCheckbutton", text="Ενεργοποίηση Βήματος 4 — Εφαρμογή ζυγού", variable=self.v_s3).pack(anchor="w")
        g = ttk.Frame(f)
        g.pack(fill="x", pady=8)
        self.v_s3exe = tk.StringVar()
        self._pick_row(g, "Πρόγραμμα T-Scale (AutoProcess.exe):", self.v_s3exe, "exe", 0)

        bundled = ttk.Frame(f)
        bundled.pack(fill="x", pady=(4, 0))
        self.btn_bundled = ttk.Button(bundled, text="Εύρεση δίπλα στο πρόγραμμα",
                                      command=self.use_bundled_autoprocess)
        self.btn_bundled.pack(side="left")
        self.lbl_bundled = ttk.Label(bundled, style="Hint.TLabel")
        self.lbl_bundled.pack(side="left", padx=10)

        ipf = ttk.Frame(f)
        ipf.pack(fill="x", pady=(10, 0))
        ttk.Label(ipf, text="IP ζυγών:").pack(side="left")
        self.v_ips = tk.StringVar()
        self._add_edit_menu(ttk.Entry(ipf, textvariable=self.v_ips, width=40)).pack(side="left", padx=6)
        ttk.Button(ipf, text="Αποθήκευση IP", style="Accent.TButton",
                   command=self.save_ips).pack(side="left")
        ttk.Button(ipf, text="Ανάγνωση από AutoProcess", style="Ghost.TButton",
                   command=self.load_ips).pack(side="left", padx=6)
        ttk.Label(f, style="Hint.TLabel", justify="left", wraplength=920,
                  text="Οι διευθύνσεις των ζυγών, χωρισμένες με κόμμα (π.χ. 10.130.20.49, "
                       "10.130.20.46). Γράφονται στο ip.xml δίπλα στο AutoProcess — δεν "
                       "χρειάζεται να το ανοίξεις με το χέρι. Αποθηκεύονται αυτόματα και "
                       "πριν από κάθε εκτέλεση."
                  ).pack(anchor="w", pady=(4, 0))
        r = ttk.Frame(f)
        r.pack(fill="x")
        self.v_s3sec = tk.StringVar(value="120")
        self.v_s3kill = tk.BooleanVar(value=True)
        ttk.Label(r, text="Διάρκεια (δευτερόλεπτα):").pack(side="left")
        ttk.Entry(r, textvariable=self.v_s3sec, width=7).pack(side="left", padx=6)
        ttk.Checkbutton(r, text="Κλείσε την αυτόματα όταν περάσει ο χρόνος",
                        variable=self.v_s3kill).pack(side="left", padx=12)
        ttk.Label(f, style="Hint.TLabel", justify="left", wraplength=920,
                  text="Το AutoProcess είναι το πρόγραμμα του κατασκευαστή που στέλνει τα "
                       "δεδομένα στους ζυγούς T-Scale. Δείξε πού είναι εγκατεστημένο στο "
                       "μηχάνημα του πελάτη.").pack(anchor="w", pady=(8, 0))

        ttk.Separator(f, orient="horizontal").pack(fill="x", pady=(12, 8))
        ttk.Label(f, text="Επιπλέον ζυγοί (προαιρετικά)",
                  style="Big.TCheckbutton").pack(anchor="w")
        ttk.Label(f, style="Hint.TLabel", justify="left", wraplength=920,
                  text="Αν το κατάστημα έχει και άλλου τύπου ζυγούς, στέλνονται στην ίδια "
                       "εκτέλεση, αμέσως μετά τους T-Scale. Άφησέ τα κλειστά αν δεν "
                       "χρειάζονται.").pack(anchor="w", pady=(0, 6))

        self.v_extra = {}
        for key, label in EXTRA_SENDERS:
            self._build_extra_sender(f, key, label)

    def _build_extra_sender(self, parent, key, label):
        """Ένα μπλοκ ρυθμίσεων για επιπλέον ζυγό (Ishida, ILS…)."""
        box = ttk.Frame(parent)
        box.pack(fill="x", pady=(6, 0))

        v = {"enabled": tk.BooleanVar(value=False), "exe": tk.StringVar(),
             "src": tk.StringVar(), "dst": tk.StringVar(),
             "seconds": tk.StringVar(value="120"), "kill": tk.BooleanVar(value=True)}
        self.v_extra[key] = v

        head = ttk.Frame(box)
        head.pack(fill="x")
        ttk.Checkbutton(head, text="Αποστολή σε %s" % label,
                        variable=v["enabled"]).pack(side="left")
        ttk.Label(head, text="διάρκεια:", style="Hint.TLabel").pack(side="left", padx=(16, 3))
        ttk.Entry(head, textvariable=v["seconds"], width=6).pack(side="left")
        ttk.Checkbutton(head, text="κλείσε το μετά",
                        variable=v["kill"]).pack(side="left", padx=8)

        grid = ttk.Frame(box)
        grid.pack(fill="x", padx=(20, 0))
        self._pick_row(grid, "Πρόγραμμα %s:" % label, v["exe"], "exe", 0)
        self._pick_row(grid, "Αρχείο host προς αποστολή:", v["src"], "file", 1)
        self._pick_row(grid, "Να αντιγράφεται εδώ:", v["dst"], "save", 2)

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
        self.v_ext1.set(c.get("host1_ext", ""))
        self.v_ext2.set(c.get("host2_ext", "csv"))
        n, unit = seconds_to_unit(c.get("poll_seconds", 3))
        self.v_poll.set(str(n))
        self.v_poll_unit.set(unit)
        self.refresh_poll_hint()
        self.v_auto.set(bool(c.get("auto_run", False)))
        self.v_backup.set(bool(c.get("backup_enabled", True)))
        self.v_popup.set(bool(c.get("show_success_popup", False)))
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
        self.v_input_type.set(c.get("step2_input_type", "fixed"))
        self.v_in_delim.set(c.get("step2_input_delimiter", ","))
        self.on_input_type_change()
        self.v_header.set(bool(c.get("step2_write_header", True)))
        self.v_delim.set(c.get("step2_delimiter", ","))
        self.v_format.set(c.get("step2_format", "csv"))
        self.v_enc_in.set(c.get("step2_in_encoding", "auto"))
        self.v_enc_out.set(c.get("step2_out_encoding", "cp1253"))
        self.v_bytes.set(bool(c.get("step2_positions_bytes", False)))
        self.v_tail.set(bool(c.get("step2_trailing_delim", False)))
        self.v_quotes.set(bool(c.get("step2_quotes", False)))
        self.v_sanitize.set(bool(c.get("step2_sanitize", True)))
        self.v_dedupe.set(bool(c.get("step2_dedupe", False)))
        self.v_finalnl.set(bool(c.get("step2_final_newline", True)))
        self.v_s3.set(bool(c.get("step3_enabled", True)))
        self.v_s3exe.set(c.get("step3_exe", ""))
        self.v_s3sec.set(str(c.get("step3_seconds", 120)))
        self.v_s3kill.set(bool(c.get("step3_kill", True)))
        self.v_ips.set(c.get("scale_ips", "") or ", ".join(read_ips(c.get("step3_exe", ""))))
        for key, _label in EXTRA_SENDERS:
            v = self.v_extra[key]
            v["enabled"].set(bool(c.get("%s_enabled" % key, False)))
            v["exe"].set(c.get("%s_exe" % key, ""))
            v["src"].set(c.get("%s_src" % key, ""))
            v["dst"].set(c.get("%s_dst" % key, ""))
            v["seconds"].set(str(c.get("%s_seconds" % key, 120)))
            v["kill"].set(bool(c.get("%s_kill" % key, True)))
        self.refresh_tree()
        self.refresh_bundled_hint()
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
                                     XFORMS.get(f.get("xform", ""), "—"),
                                     f.get("extra", "")))

    def collect(self):
        c = self.cfg
        c["watch_file"] = self.v_watch.get().strip()
        c["output_dir"] = self.v_outdir.get().strip()
        c["host1_ext"] = self.v_ext1.get().strip()
        c["host2_ext"] = self.v_ext2.get().strip()
        try:
            c["poll_seconds"] = self.poll_seconds()
        except ValueError:
            c["poll_seconds"] = 3
        c["auto_run"] = self.v_auto.get()
        c["backup_enabled"] = self.v_backup.get()
        c["show_success_popup"] = self.v_popup.get()
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
        c["step2_input_type"] = self.v_input_type.get()
        c["step2_input_delimiter"] = self.v_in_delim.get() or ","
        c["step2_write_header"] = self.v_header.get()
        c["step2_delimiter"] = self.v_delim.get() or ","
        c["step2_format"] = self.v_format.get()
        c["step2_in_encoding"] = self.v_enc_in.get()
        c["step2_out_encoding"] = self.v_enc_out.get()
        c["step2_positions_bytes"] = self.v_bytes.get()
        c["step2_trailing_delim"] = self.v_tail.get()
        c["step2_quotes"] = self.v_quotes.get()
        c["step2_sanitize"] = self.v_sanitize.get()
        c["step2_dedupe"] = self.v_dedupe.get()
        c["step2_final_newline"] = self.v_finalnl.get()
        c["step3_enabled"] = self.v_s3.get()
        c["step3_exe"] = self.v_s3exe.get().strip()
        try:
            c["step3_seconds"] = max(1, int(self.v_s3sec.get()))
        except ValueError:
            c["step3_seconds"] = 120
        c["step3_kill"] = self.v_s3kill.get()
        c["scale_ips"] = self.v_ips.get().strip()
        for key, _label in EXTRA_SENDERS:
            v = self.v_extra[key]
            c["%s_enabled" % key] = v["enabled"].get()
            c["%s_exe" % key] = v["exe"].get().strip()
            c["%s_src" % key] = v["src"].get().strip()
            c["%s_dst" % key] = v["dst"].get().strip()
            try:
                c["%s_seconds" % key] = max(1, int(v["seconds"].get()))
            except ValueError:
                c["%s_seconds" % key] = 120
            c["%s_kill" % key] = v["kill"].get()
        return c

    def on_save(self):
        save_config(self.collect())
        self.save_ips(silent=True)
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

    def on_input_type_change(self):
        delimited = self.v_input_type.get() == "delimited"
        self.tree.heading("pos", text="Στήλη" if delimited else "Από Θέση")
        self.tree.heading("len", text="Κόψιμο" if delimited else "Μήκος Πεδίου")
        if delimited:
            self.lbl_intype_hint.configure(
                text="Στήλη = αριθμός πεδίου στη γραμμή (1 = πρώτο). Αρνητικός αριθμός μετράει "
                     "από το τέλος (-1 = τελευταία στήλη) — χρήσιμο για την τιμή, όταν η "
                     "περιγραφή μπορεί να περιέχει τυχαία το ίδιο το διαχωριστικό. Κόψιμο "
                     "θετικό = κόβει σε τόσους χαρακτήρες· αρνητικό = συνενώνει τις στήλες από "
                     "τη Στήλη μέχρι αυτή (π.χ. Στήλη 2, Κόψιμο -4 = «από τη 2η μέχρι την "
                     "4η-από-το-τέλος», για περιγραφές με ενδεχόμενα κόμματα μέσα.")
        else:
            self.lbl_intype_hint.configure(
                text="Από Θέση/Μήκος = χαρακτήρες πάνω στη γραμμή, όπως στα αρχεία σταθερού "
                     "πλάτους του ERP (π.χ. host1_cnv.txt).")

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
        ttk.Label(win, text="Μετατροπή").grid(row=4, column=0, sticky="w", padx=8, pady=4)
        labels = list(XFORMS.values())
        keys = list(XFORMS.keys())
        xf = tk.StringVar(value=XFORMS.get(f.get("xform", ""), "—"))
        ttk.Combobox(win, textvariable=xf, values=labels, state="readonly",
                     width=32).grid(row=4, column=1, padx=8, pady=4)
        ttk.Checkbutton(win, text="Για έξοδο σε αρχείο", variable=en).grid(row=5, column=1, sticky="w", padx=8)

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
            f["xform"] = keys[labels.index(xf.get())] if xf.get() in labels else ""
            win.destroy()
            self.refresh_tree()
            self.tree.selection_set(str(i))
        ttk.Button(win, text="Καταχώρηση", command=ok).grid(row=6, column=1, sticky="e", padx=8, pady=10)

    def load_profile(self, name):
        """Έτοιμο σετ θέσεων/μηκών για γνωστό τύπο αρχείου."""
        profiles = self.cfg.get("profiles", {})     # ενσωματωμένα + του τεχνικού
        if name not in profiles:
            messagebox.showerror(APP_NAME, "Δεν βρέθηκε το προφίλ «%s»." % name)
            return
        if not messagebox.askyesno(APP_NAME, "Να αντικατασταθεί ο πίνακας με το προφίλ «%s»;" % name):
            return
        entry = profiles[name]
        fields = entry.get("fields", entry) if isinstance(entry, dict) else entry
        self.cfg["step2_fields"] = [dict(f) for f in fields]
        settings = entry.get("settings", {}) if isinstance(entry, dict) else {}
        self.cfg.update(settings)
        self._load_into_widgets()
        self.log("Φορτώθηκε το προφίλ: %s%s" % (name, " (μαζί με τη μορφή αρχείου)" if settings else ""))

    def refresh_profiles(self, select=None):
        names = list(self.cfg.get("profiles", {}))
        self.cmb_profile.configure(values=names)
        if select and select in names:
            self.v_profile.set(select)

    def save_profile(self):
        """Αποθηκεύει τις τρέχουσες ρυθμίσεις ως προφίλ πελάτη."""
        from tkinter import simpledialog
        cur = self.v_profile.get().replace("★ ", "")
        name = simpledialog.askstring(APP_NAME, "Όνομα προφίλ (π.χ. όνομα πελάτη):",
                                      initialvalue=cur, parent=self)
        if not name:
            return
        name = name.strip().replace("★", "").strip()
        self.collect()
        profiles = load_user_profiles()
        if name in profiles and not messagebox.askyesno(
                APP_NAME, "Το προφίλ «%s» υπάρχει ήδη. Να αντικατασταθεί;" % name):
            return
        profiles[name] = {
            "settings": {k: self.cfg.get(k) for k in PROFILE_KEYS},
            "fields": [dict(f) for f in self.cfg.get("step2_fields", [])],
        }
        save_user_profiles(profiles)
        self.cfg["profiles"]["★ " + name] = profiles[name]
        self.refresh_profiles("★ " + name)
        self.log("Αποθηκεύτηκε το προφίλ «%s» (%s)" % (name, USER_PROFILES_PATH))

    def delete_profile(self):
        name = self.v_profile.get()
        if not name.startswith("★ "):
            messagebox.showinfo(APP_NAME, "Τα ενσωματωμένα προφίλ δεν διαγράφονται.\n\n"
                                          "Διαγράφονται μόνο όσα έχεις αποθηκεύσει εσύ "
                                          "(σημειωμένα με ★).")
            return
        plain = name[2:]
        if not messagebox.askyesno(APP_NAME, "Να διαγραφεί το προφίλ «%s»;" % plain):
            return
        profiles = load_user_profiles()
        profiles.pop(plain, None)
        save_user_profiles(profiles)
        self.cfg["profiles"].pop(name, None)
        self.refresh_profiles(list(self.cfg["profiles"])[0])
        self.log("Διαγράφηκε το προφίλ «%s»" % plain)

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

    def save_ips(self, silent=False):
        """Γράφει τις IP στο ip.xml του AutoProcess."""
        exe = self.v_s3exe.get().strip()
        if not exe:
            if not silent:
                messagebox.showinfo(APP_NAME, "Διάλεξε πρώτα την εφαρμογή του ζυγού.")
            return False
        ips = parse_ips(self.v_ips.get())
        if not ips:
            if not silent:
                messagebox.showinfo(APP_NAME, "Δώσε τουλάχιστον μία IP, π.χ. 10.130.20.49")
            return False
        try:
            path = write_ips(exe, ips)
        except StepError as exc:
            if not silent:
                messagebox.showerror(APP_NAME, exc.full())
            return False
        self.log("IP ζυγών (%s) -> %s" % (", ".join(ips), path))
        if not silent:
            messagebox.showinfo(APP_NAME, "Αποθηκεύτηκαν %d διευθύνσεις στο:\n%s"
                                % (len(ips), path))
        return True

    def load_ips(self):
        exe = self.v_s3exe.get().strip()
        ips = read_ips(exe)
        if not ips:
            messagebox.showinfo(APP_NAME, "Δεν βρέθηκαν IP στο ip.xml του AutoProcess.")
            return
        self.v_ips.set(", ".join(ips))
        self.log("Διαβάστηκαν IP από το AutoProcess: %s" % ", ".join(ips))

    def use_bundled_autoprocess(self):
        p = bundled_autoprocess()
        if not p:
            messagebox.showinfo(
                APP_NAME,
                "Δεν βρέθηκε AutoProcess δίπλα στο πρόγραμμα.\n\nΤο AutoProcess είναι "
                "λογισμικό του κατασκευαστή των ζυγών και δεν έρχεται μαζί μας. Διάλεξέ "
                "το με «Αναζήτηση…», ή αντίγραψε τον φάκελό του ως «autosend» δίπλα στο "
                "πρόγραμμα για να βρίσκεται αυτόματα.")
            return
        self.v_s3exe.set(p)
        self.log("Βρέθηκε AutoProcess δίπλα στο πρόγραμμα: %s" % p)
        self.refresh_bundled_hint()
        if not self.v_ips.get().strip():
            existing = read_ips(p)
            if existing:
                self.v_ips.set(", ".join(existing))

    def refresh_poll_hint(self):
        if not hasattr(self, "lbl_poll"):
            return
        try:
            secs = self.poll_seconds()
        except ValueError:
            self.lbl_poll.configure(text="(μη έγκυρος αριθμός)")
            return
        if secs < 60:
            txt = "= κάθε %d δευτ." % secs
        elif secs < 3600:
            txt = "= κάθε %g λεπτά" % (secs / 60.0)
        else:
            txt = "= κάθε %g ώρες" % (secs / 3600.0)
        self.lbl_poll.configure(text=txt)

    def poll_seconds(self):
        """Ο αριθμός του πεδίου × η επιλεγμένη μονάδα, σε δευτερόλεπτα."""
        n = max(1, int(float(self.v_poll.get())))
        return n * POLL_UNITS.get(self.v_poll_unit.get(), 1)

    def refresh_bundled_hint(self):
        p = bundled_autoprocess()
        if not hasattr(self, "lbl_bundled"):
            return
        if p:
            self.lbl_bundled.configure(text="βρέθηκε: %s" % p)
            self.btn_bundled.state(["!disabled"])
        else:
            self.lbl_bundled.configure(
                text="(αν αντιγράψεις τον φάκελο του AutoProcess ως «autosend» δίπλα "
                     "στο πρόγραμμα, βρίσκεται μόνο του)")
            self.btn_bundled.state(["disabled"])

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
        tmp = os.environ.get("TEMP") or os.path.dirname(sys.executable)
        dest = os.path.join(tmp, APP_ID + "_new.zip")
        self._new_dir = os.path.join(tmp, APP_ID + "_new")

        def job():
            try:
                log = lambda m: self.after(0, self.log, m)
                download_update(url, dest, log=log)
                extract_update(dest, self._new_dir, log=log)
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
            shutil.rmtree(getattr(self, "_new_dir", "") or "", ignore_errors=True)
            messagebox.showerror(
                APP_NAME,
                "Η λήψη της ενημέρωσης απέτυχε.\n\n%s\n\nΤο πρόγραμμα δεν άλλαξε "
                "καθόλου και συνεχίζει με την έκδοση %s." % (err, APP_BUILD))
            return

        self.log("Εγκατάσταση έκδοσης %s και επανεκκίνηση…" % latest)
        write_log("=== Ενημέρωση %s -> %s ===" % (APP_BUILD, latest))
        try:
            save_config(self.collect())
            install_update_and_restart(self._new_dir)
        except Exception as exc:
            messagebox.showerror(APP_NAME, "Η εγκατάσταση απέτυχε.\n\n%s" % exc)
            return
        self.quit_app()

    def show_preview(self):
        """Δείχνει βήμα-βήμα τι θα γίνει, χωρίς να σταλεί τίποτα στους ζυγούς."""
        self.collect()
        save_config(self.cfg)
        try:
            report = build_preview(self.cfg)
        except StepError as exc:
            messagebox.showerror(APP_NAME, exc.full())
            return
        except Exception:
            messagebox.showerror(APP_NAME, "Απρόσμενο σφάλμα στην προεπισκόπηση:\n\n"
                                 + traceback.format_exc())
            return

        win = tk.Toplevel(self)
        win.title("Προεπισκόπηση βημάτων — %s" % APP_NAME)
        win.geometry("980x640")
        try:
            win.iconbitmap(resource("logo.ico"))
        except Exception:
            pass
        box = self._console(win, 30, ("Consolas", 9))
        box.pack(fill="both", expand=True, padx=10, pady=10)
        box.insert("1.0", report)
        box.configure(state="disabled")

        bar = ttk.Frame(win, style="Bar.TFrame", padding=8)
        bar.pack(fill="x")

        def copy():
            self.clipboard_clear()
            self.clipboard_append(report)
            messagebox.showinfo(APP_NAME, "Η αναφορά αντιγράφηκε — μπορείς να την επικολλήσεις.",
                                parent=win)

        ttk.Button(bar, text="Αντιγραφή αναφοράς", style="Accent.TButton",
                   command=copy).pack(side="left")
        ttk.Button(bar, text="Άνοιγμα φακέλου προεπισκόπησης", style="Ghost.TButton",
                   command=lambda: self._open(os.path.join(CONFIG_DIR, "preview"))).pack(side="left", padx=8)
        ttk.Button(bar, text="Κλείσιμο", style="Ghost.TButton",
                   command=win.destroy).pack(side="right")

    @staticmethod
    def _open(path):
        try:
            os.startfile(path)                               # Windows
        except AttributeError:
            subprocess.Popen(["xdg-open", path])

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
        # Ξέρουμε ότι ολοκληρώθηκε η δική μας ροή· αν ο ζυγός δέχτηκε τα δεδομένα
        # το λέει το log της εφαρμογής του ζυγού, όχι εμείς.
        if not silent and self.cfg.get("show_success_popup"):
            messagebox.showinfo(APP_NAME, "Τα βήματα ολοκληρώθηκαν και η εφαρμογή του ζυγού "
                                          "εκτελέστηκε.\n\nΑν η μεταφορά πέτυχε, φαίνεται στο "
                                          "log της εφαρμογής του ζυγού.")

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
        n, unit = seconds_to_unit(self.cfg["poll_seconds"])
        self.log("Παρακολούθηση: %s (έλεγχος κάθε %d %s)" % (path, n, unit))
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
