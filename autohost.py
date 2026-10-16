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
import io
import sys
import glob
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

APP_BUILD = "2.20.0-beta.12"                        # σύγκριση για ενημερώσεις
# Δοκιμαστική έκδοση (beta): «2.20.0-beta.1». Ζει ΔΙΠΛΑ στην κανονική εγκατάσταση
# χωρίς να την αγγίζει — άλλο όνομα exe, άλλος φάκελος ρυθμίσεων, άλλη θύρα,
# άλλο κανάλι ενημερώσεων (branch «beta», pre-releases). Οι κανονικές εγκαταστάσεις
# δεν βλέπουν ποτέ beta: το GitHub δεν τις δίνει στο /releases/latest.
IS_BETA = "beta" in APP_BUILD.lower()
APP_NAME = "Αυτόματη ενημέρωση ζυγών" + (" — ΔΟΚΙΜΑΣΤΙΚΗ (beta)" if IS_BETA else "")
APP_ID = "ICSautoScaleUpdater" + ("-beta" if IS_BETA else "")   # όνομα exe / registry / φακέλων
APP_VERSION = "%s · έκδοση %s — Θεσσαλονίκη, Οκτώβριος 2026" % (APP_ID, APP_BUILD)
UPDATE_BRANCH = "beta" if IS_BETA else "main"
UPDATE_VERSION_URL = ("https://raw.githubusercontent.com/arch1based/tscale-autohost/%s/VERSION"
                      % UPDATE_BRANCH)
UPDATE_PAGE_URL = "https://github.com/arch1based/tscale-autohost"
UPDATE_API_URL = ("https://api.github.com/repos/arch1based/tscale-autohost/releases?per_page=30"
                  if IS_BETA else
                  "https://api.github.com/repos/arch1based/tscale-autohost/releases/latest")
UPDATE_ASSET = APP_ID + ".zip"
# Κωδικός τεχνικού για ενημέρωση (αποτρέπει να την τρέξει προσωπικό του καταστήματος).
# Είναι φραγμός κατά λάθους χειρισμού, όχι κρυπτογραφική ασφάλεια.
UPDATE_PASSWORD_SHA256 = "e78f27ab3ef177a9926e6b90e572b9853ce6cf4d87512836e9ae85807ec9d7fe"
def enable_high_dpi():
    """Ενεργοποιεί Per-Monitor DPI awareness στα Windows ΠΡΙΝ αρχικοποιηθεί το Tkinter.

    Αν κληθεί μετά το Tk(), το Tkinter κρατάει παλιό scaling (96 DPI) με αποτέλεσμα
    θολά ή μικροσκοπικά γράμματα σε οθόνες με κλιμάκωση (125%, 150%, 200%).
    """
    if sys.platform.startswith("win"):
        try:
            import ctypes
            # Per-monitor V2 awareness (Windows 10 1703+)
            try:
                ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
            except Exception:
                # Per-monitor (Windows 8.1+)
                try:
                    ctypes.windll.shcore.SetProcessDpiAwareness(2)
                except Exception:
                    ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass


# Πρώιμη κλήση DPI awareness για τα Windows
enable_high_dpi()

COLORS = {
    "bg":          "#f1f5f9",   # Slate-100: σύγχρονο ουδέτερο φόντο παραθύρου
    "card":        "#ffffff",   # Καθαρό λευκό για κάρτες & επιφάνειες
    "card_subtle": "#f8fafc",   # Slate-50: απαλό δευτερεύον φόντο
    "ink":         "#0f172a",   # Slate-900: βαθύ, ευανάγνωστο κείμενο υψηλής αντίθεσης
    "muted":       "#475569",   # Slate-600: ευδιάκριτο δευτερεύον κείμενο
    "muted_light": "#94a3b8",   # Slate-400: διακριτικό κείμενο / placeholders
    "line":        "#cbd5e1",   # Slate-300: καθαρά περιγράμματα
    "line_subtle": "#e2e8f0",   # Slate-200: διαχωριστικές γραμμές
    "brand":       "#0284c7",   # Sky-600: ζωντανό, σύγχρονο μπλε ICS
    "brand_d":     "#0369a1",   # Sky-700: πατημένο / ενεργό μπλε
    "brand_light": "#e0f2fe",   # Sky-100: απαλή μπλε επισήμανση
    "ok":          "#059669",   # Emerald-600: επιτυχία / ενεργό
    "ok_light":    "#d1fae5",   # Emerald-100: badge επιτυχίας
    "warn":        "#d97706",   # Amber-600: προειδοποίηση
    "warn_light":  "#fef3c7",   # Amber-100: badge προειδοποίησης
    "err":         "#dc2626",   # Red-600: σφάλμα
    "err_light":   "#fee2e2",   # Red-100: badge σφάλματος
    "console":     "#0b1120",   # Obsidian Slate: βαθύ μοντέρνο τερματικό
    "console_fg":  "#f1f5f9",   # Καθαρό φωτεινό κείμενο τερματικού
    "sidebar":     "#0f172a",   # Deep Obsidian Slate: σύγχρονη πλαϊνή μπάρα
    "sidebar_hover": "#1e293b", # Slate-800: hover στα κουμπιά πλοήγησης
    "sidebar_active": "#1e3a5f",# Slate/Navy: ενεργό tab
    "sidebar_fg":  "#94a3b8",   # Slate-400: κείμενο πλοήγησης
    "sidebar_fg_act": "#ffffff",# Λευκό: ενεργό κείμενο
}

FONTS = {
    "base":        ("Segoe UI", 11),
    "base_bold":   ("Segoe UI", 11, "bold"),
    "sm":          ("Segoe UI", 10),
    "sm_bold":     ("Segoe UI", 10, "bold"),
    "title":       ("Segoe UI", 13, "bold"),
    "app_title":   ("Segoe UI", 19, "bold"),
    "vendor":      ("Segoe UI", 10, "bold"),
    "version":     ("Segoe UI", 10),
    "tab":         ("Segoe UI", 11, "bold"),
    "btn":         ("Segoe UI", 11),
    "btn_accent":  ("Segoe UI", 11, "bold"),
    "mono":        ("Consolas", 11),
    "mono_sm":     ("Consolas", 10),
}

APP_VENDOR = "ICS — ΚΑΡΑΦΥΛΛΗΣ ΣΥΣΤΗΜΑΤΑ ΠΛΗΡΟΦΟΡΙΚΗΣ"
APP_DIR = os.path.dirname(os.path.abspath(__file__))
SINGLETON_PORT = 49732 if IS_BETA else 49731   # η beta δεν «ξυπνάει» τη live
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
LEGACY_CONFIGS = () if IS_BETA else (
    LEGACY_CONFIG,
    os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~/.config"),
                 "ICS", "TScaleAutoHost", "autohost_config.json"),
)
# Η κανονική (live) εγκατάσταση στο ίδιο μηχάνημα — η beta τη διαβάζει ΜΟΝΟ μία
# φορά, στην πρώτη της εκκίνηση, για να ξεκινήσει με τις ίδιες ρυθμίσεις.
LIVE_CONFIG_DIR = os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~/.config"),
                               "ICS", "ICSautoScaleUpdater")
USER_PROFILES_PATH = os.path.join(CONFIG_DIR, "profiles.json")
# Ζυγοί που δεν πρόλαβαν την τελευταία ενημέρωση (κλειστοί, εκτός δικτύου).
# Σε αρχείο ώστε να μη χαθούν αν κλείσει το πρόγραμμα ή πέσει το ρεύμα.
PENDING_PATH = os.path.join(CONFIG_DIR, "pending_scales.json")
# Όταν μετονομάζεται ένα προφίλ, η παλιά ονομασία μένει εδώ: αλλιώς μια
# αποθηκευμένη ρύθμιση πελάτη θα έδειχνε σε προφίλ που δεν υπάρχει πια.
PROFILE_ALIASES = {
    "ISHIDA · τιμή σε λεπτά 540 ✓ δοκιμασμένο": "ERGON · Ishida — τιμή σε λεπτά 540 ✓",
    "ISHIDA · τιμή σε λεπτά, 540 (κόμμα)": "ERGON · Ishida — τιμή σε λεπτά 540 ✓",
}

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
                        "Διάλεξε πρώτα το πρόγραμμα T-Scale του κατασκευαστή.")
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
    """«1.2.3» -> (1, 2, 3, 1, 0)· «1.2.3-beta.4» -> (1, 2, 3, 0, 4).

    Το 4ο μέλος λέει «τελική» (1) ή «δοκιμαστική» (0), ώστε η 2.20.0 να μετράει
    νεότερη από κάθε 2.20.0-beta.N. Ό,τι δεν είναι αριθμός γίνεται 0.
    """
    text = str(text).strip().lstrip("vV")
    base, _, pre = text.partition("-")
    parts = []
    for chunk in base.split(".")[:3]:
        digits = "".join(ch for ch in chunk if ch.isdigit())
        parts.append(int(digits) if digits else 0)
    while len(parts) < 3:
        parts.append(0)
    pre_digits = "".join(ch for ch in pre if ch.isdigit())
    return tuple(parts) + ((1, 0) if not pre else (0, int(pre_digits or 0)))


def _get(url, timeout, binary=False):
    import urllib.request
    req = urllib.request.Request(url, headers={"User-Agent": APP_ID,
                                               "Cache-Control": "no-cache"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = resp.read()
    return data if binary else data.decode("utf-8", "replace")


def _pick_release(data):
    """Το Release που μας αφορά. Live: το /releases/latest (ένα αντικείμενο).
    Beta: λίστα με όλα — κρατάμε το νεότερο, beta ή τελικό, ώστε μια beta
    εγκατάσταση να περάσει και στην τελική όταν βγει."""
    if isinstance(data, dict):
        return data
    best = None
    for rel in data or []:
        if rel.get("draft") or not rel.get("tag_name"):
            continue
        if best is None or parse_version(rel["tag_name"]) > parse_version(best["tag_name"]):
            best = rel
    return best or {}


def fetch_latest_version(timeout=8):
    """(έκδοση, σημειώσεις, url_του_exe). Προτιμά το τελευταίο GitHub Release."""
    try:
        rel = _pick_release(json.loads(_get(UPDATE_API_URL, timeout)))
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


BETA_API_URL = "https://api.github.com/repos/arch1based/tscale-autohost/releases?per_page=30"
BETA_ASSET = "ICSautoScaleUpdater-beta.zip"
BETA_DIR_NAME = "ICSautoScaleUpdater-beta"


def fetch_latest_beta(timeout=8):
    """(έκδοση, σημειώσεις, url_zip) της νεότερης δοκιμαστικής (pre-release) στο GitHub.

    Οι κανονικές εγκαταστάσεις ρωτούν το /releases/latest, που δεν δίνει ποτέ
    pre-releases· εδώ ρωτάμε ρητά τη λίστα, μόνο όταν ο τεχνικός το ζητήσει.
    """
    rels = json.loads(_get(BETA_API_URL, timeout))
    best = None
    for rel in rels or []:
        if rel.get("draft") or not rel.get("prerelease") or not rel.get("tag_name"):
            continue
        if best is None or parse_version(rel["tag_name"]) > parse_version(best["tag_name"]):
            best = rel
    if not best:
        return "", "", ""
    url = ""
    for asset in best.get("assets", []):
        if asset.get("name", "").lower() == BETA_ASSET.lower():
            url = asset.get("browser_download_url", "")
    return best["tag_name"].lstrip("vV"), (best.get("body") or "").strip(), url


def fetch_available_channels(timeout=8):
    """Επιστρέφει λεξικό με τα 3 διαθέσιμα κανάλια:
    - beta_redesign: Νέο περιβάλλον 2026 (>= 2.20.0-beta.10)
    - beta_classic:  Κλασική beta (< 2.20.0-beta.10)
    - stable:        Έκδοση παραγωγής
    """
    url = "https://api.github.com/repos/arch1based/tscale-autohost/releases?per_page=30"
    data = json.loads(_get(url, timeout))
    channels = {
        "beta_redesign": None,
        "beta_classic": None,
        "stable": None
    }
    for r in data or []:
        tag = (r.get("tag_name") or "").strip()
        if not tag or r.get("draft"):
            continue
        v = tag.lstrip("vV")
        is_pre = bool(r.get("prerelease"))
        zip_url = ""
        for a in r.get("assets", []):
            aname = (a.get("name") or "").lower()
            if aname.endswith(".zip"):
                zip_url = a.get("browser_download_url", "")
                break
        info = {
            "tag": tag,
            "version": v,
            "notes": (r.get("body") or "").strip(),
            "url": zip_url,
            "date": (r.get("published_at") or "")[:10]
        }
        if not is_pre:
            if channels["stable"] is None or parse_version(v) > parse_version(channels["stable"]["version"]):
                channels["stable"] = info
        else:
            if parse_version(v) >= parse_version("2.20.0-beta.10"):
                if channels["beta_redesign"] is None or parse_version(v) > parse_version(channels["beta_redesign"]["version"]):
                    channels["beta_redesign"] = info
            else:
                if channels["beta_classic"] is None or parse_version(v) > parse_version(channels["beta_classic"]["version"]):
                    channels["beta_classic"] = info
    return channels


def beta_install_dir():
    """Δίπλα στην κανονική εγκατάσταση: στον γονικό φάκελο της εφαρμογής, ICSautoScaleUpdater-beta."""
    app_dir = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else APP_DIR
    return os.path.join(os.path.dirname(app_dir), BETA_DIR_NAME)


def install_beta_side_by_side(zip_path, target_dir, log=None):
    """Ξεπακετάρει τη beta σε δικό της φάκελο και επιστρέφει τη διαδρομή του exe της."""
    import zipfile
    with zipfile.ZipFile(zip_path) as z:
        names = z.namelist()
        exe = BETA_DIR_NAME + ".exe"
        if not any(n.lower().endswith(exe.lower()) for n in names):
            raise ValueError("το πακέτο δεν περιέχει το %s" % exe)
        os.makedirs(target_dir, exist_ok=True)
        z.extractall(target_dir)
    for root, _dirs, files in os.walk(target_dir):
        for f in files:
            if f.lower() == exe.lower():
                if log:
                    log("Η beta ξεπακεταρίστηκε στο %s" % root)
                return os.path.join(root, f)
    raise ValueError("δεν βρέθηκε το exe της beta μετά το ξεπακετάρισμα")


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
    exes = [f for f in os.listdir(target_dir) if f.lower().endswith(".exe")]
    if not exes:
        raise ValueError("δεν βρέθηκε κανένα εκτελέσιμο (.exe) μέσα στο πακέτο")
    if log:
        log("  -> ξεπακετάρισμα: %s (%s)" % (target_dir, exes[0]))
    return target_dir


def install_update_and_restart(new_dir):
    """Αντιγράφει τη νέα έκδοση πάνω από την τρέχουσα και ξαναξεκινά.

    Η εφαρμογή δεν μπορεί να γράψει πάνω στα δικά της αρχεία όσο τρέχει, οπότε
    ένα .bat περιμένει να κλείσει, αντιγράφει και την ξανανοίγει. Οι ρυθμίσεις
    ζουν στο %APPDATA% και δεν αγγίζονται.
    """
    cur = sys.executable
    app_dir = os.path.dirname(cur)
    new_exes = [f for f in os.listdir(new_dir) if f.lower().endswith(".exe")]
    target_exe = os.path.join(app_dir, new_exes[0]) if new_exes else cur
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
                                        app=app_dir, exe=target_exe)
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
    if IS_BETA and not os.path.exists(path):
        path = copy_live_config_for_beta()
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


def copy_live_config_for_beta():
    """Πρώτη εκκίνηση της beta: ξεκινά με τις ρυθμίσεις της live εγκατάστασης.

    Αντιγράφει ρυθμίσεις και προφίλ τεχνικού — ΟΧΙ τους εκκρεμείς ζυγούς, ώστε η
    beta να μη στείλει τίποτα μόνη της. Σβήνει το auto_run: η παρακολούθηση
    ξεκινά μόνο με το χέρι. Επιστρέφει τη διαδρομή που πρέπει να διαβαστεί.
    """
    live_cfg = os.path.join(LIVE_CONFIG_DIR, "autohost_config.json")
    if not os.path.isfile(live_cfg):
        return CONFIG_PATH
    try:
        with open(live_cfg, "r", encoding="utf-8") as fh:
            saved = json.load(fh)
        saved["auto_run"] = False
        saved["_copied_from_live"] = datetime.datetime.now().isoformat(timespec="seconds")
        with open(CONFIG_PATH, "w", encoding="utf-8") as fh:
            json.dump(saved, fh, indent=2, ensure_ascii=False)
        live_prof = os.path.join(LIVE_CONFIG_DIR, "profiles.json")
        if os.path.isfile(live_prof) and not os.path.exists(USER_PROFILES_PATH):
            shutil.copyfile(live_prof, USER_PROFILES_PATH)
    except Exception:
        return CONFIG_PATH
    return CONFIG_PATH


def resolve_profile(profiles, name):
    """Βρίσκει προφίλ με το τρέχον ή με παλιό του όνομα."""
    if name in profiles:
        return name, profiles[name]
    alias = PROFILE_ALIASES.get(name)
    if alias and alias in profiles:
        return alias, profiles[alias]
    return name, None


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
    if int(saved.get("config_version", 0)) < 3:
        # Η 2.3.0 αποθήκευε direct_quirk=true (αλλοίωνε τα ελληνικά και ο ζυγός
        # τύπωνε κινέζικα). Επαληθεύτηκε σε πραγματικό ζυγό ότι το σωστό είναι
        # καθαρό UTF-8 — και επειδή οι αποθηκευμένες ρυθμίσεις υπερισχύουν των
        # προεπιλογών, η διόρθωση δεν έφτανε ποτέ σε όποιον είχε ήδη τρέξει.
        cfg["direct_quirk"] = False
        cfg["direct_wire_encoding"] = "utf-8"
        cfg["config_version"] = 3
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
    "nocomma": "χωρίς κόμματα (για ILS: ΣΑΛΑΜΙ, ΔΡΑΜΑΣ → ΣΑΛΑΜΙ ΔΡΑΜΑΣ)",
    "strip0": "χωρίς μηδενικά μπροστά",
    "cents2comma": "λεπτά → τιμή με κόμμα (00315 → 3,15)",
    "cents2dot": "λεπτά → τιμή με τελεία (00315 → 3.15)",
    "prefix21": "πρόθεμα 21 (barcode ζυγαριάς: 00010 → 2100010)",
    "dec2dot": "2 δεκαδικά με τελεία (5.4 → 5.40)",
    "dec2comma": "2 δεκαδικά με κόμμα (5.4 → 5,40)",
    "tocents": "τιμή → λεπτά (5.4 → 540)",
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


def apply_skip(value, f):
    """Παραλείπει τους πρώτους Ν χαρακτήρες της τιμής (κλειδί «skip» του πεδίου).

    Για ζυγούς που διαβάζουν το όνομα σε δύο κομμάτια σε ΜΗ συνεχόμενες θέσεις
    (ILS: Plu Name + Plu name extens): το δεύτερο πεδίο παίρνει την ίδια στήλη
    του ERP με skip = μήκος του πρώτου, ώστε να συνεχίζει από εκεί που κόπηκε.
    """
    try:
        n = int(f.get("skip") or 0)
    except (TypeError, ValueError):
        n = 0
    return value[n:] if n > 0 else value


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
    if kind == "nocomma":
        # Το αρχείο του ILS χωρίζεται με κόμμα και ΔΕΝ δέχεται εισαγωγικά: μια
        # περιγραφή σαν «ΣΑΛΑΜΙ, ΔΡΑΜΑΣ» θα μετατόπιζε όλες τις επόμενες στήλες.
        return " ".join(value.replace(",", " ").replace(";", " ").split())
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
    if kind in ("dec2dot", "dec2comma", "tocents"):
        # Μέσω λεπτών, ώστε το 5.4 και το 70 να καταλήγουν πάντα σε 2 δεκαδικά.
        txt = value.strip().replace(",", ".")
        if not txt:
            return value
        try:
            cents = int(round(float(txt) * 100))
        except ValueError:
            return value
        if kind == "tocents":
            return str(cents)
        whole, rest = divmod(abs(cents), 100)
        return "%s%d%s%02d" % ("-" if cents < 0 else "", whole,
                               "." if kind == "dec2dot" else ",", rest)
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
                val = apply_xform(apply_skip(val, f), f.get("xform", ""))
                if not val and str(f.get("extra", "")).strip():
                    val = str(f["extra"]).strip()
                row.append(val)
            rows.append(row)
            continue

        row = []
        for f in fields:
            pos = int(f.get("pos") or 0) - off
            ln = int(f.get("inlen") or f.get("len") or 0)     # inlen: μήκος στο ERP
            val = line[pos:pos + ln] if pos >= 0 else line[:0]
            if by_bytes:
                val = val.decode(in_enc if in_enc != "utf-8-sig" else "utf-8", "replace")
            val = val.strip()
            val = apply_xform(apply_skip(val, f), f.get("xform", ""))
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
            # Σταθερό πλάτος: κάθε πεδίο γεμίζει το δικό του μήκος. Η στοίχιση
            # μετράει — π.χ. οι Ishida θέλουν την τιμή δεξιά μέσα στο πεδίο.
            # Ό,τι δεν χωράει στο πλάτος του κόβεται. Σιωπηλά, αυτό είναι
            # επικίνδυνο: μια τιμή 1.250,00 € σε πεδίο πέντε ψηφίων γίνεται
            # άλλη τιμή στο ράφι. Τα μετράμε και τα λέμε.
            kommena = {}

            def cell(v, f):
                w = int(f.get("len") or 0)
                if len(v) > w:
                    palio = kommena.get(f["name"])
                    if palio is None or len(v) > len(palio[0]):
                        kommena[f["name"]] = (v, w)
                v = v[:w]
                align = f.get("align")
                if align == "zero":
                    # Με μηδενικά μπροστά: οι ζυγοί ILS θέλουν «000009» και
                    # «02500», όχι «     9» και «  2500».
                    return v.rjust(w, "0")
                return v.rjust(w) if align == "right" else v.ljust(w)

            with open(dst, "w", encoding=out_enc, errors="replace", newline="\r\n") as fh:
                if cfg.get("step2_write_header", True):
                    fh.write("".join(cell(f["name"], f) for f in fields) + "\n")
                for row in rows:
                    fh.write("".join(cell(v, f) for v, f in zip(row, fields)) + "\n")
            if kommena:
                log("  ΠΡΟΣΟΧΗ — δεν χώρεσαν και κόπηκαν:")
                for onoma, (timi, platos) in kommena.items():
                    log("     %s: «%s» (%d χαρακτήρες) σε πεδίο %d"
                        % (onoma, timi, len(timi), platos))
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


# --------------------------------------------------------------------------
# Απευθείας αποστολή στους ζυγούς, χωρίς το AutoProcess
#
# Το πρωτόκολλο βγήκε από ανάλυση και καταγραφή του AutoProcess:
#   POST http://<IP>:1235/products   με Content-Type: application/json
#   σώμα: ΕΝΑΣ πίνακας με όλα τα προϊόντα, όλες οι τιμές ως κείμενο.
# --------------------------------------------------------------------------
SCALE_PORT = 1235
# Ο ζυγός απαντά HTTP 429 σε δύο γρήγορα διαδοχικά αιτήματα. Μετρήθηκε σε
# πραγματικό ζυγό: 10 δευτερόλεπτα αναμονής αρκούν και περνάει κανονικά.
RATE_LIMIT_WAIT = 10

# Στήλη CSV -> πεδίο JSON (επιβεβαιωμένο με δοκιμαστικό αρχείο μοναδικών τιμών)
CSV_TO_JSON = {
    # --- όσα στέλνει και το AutoProcess (επιβεβαιωμένα με δοκιμή) ---
    "ProductNumber": "product_number", "BarCode": "product_code",
    "ProductName": "product_name", "Abbr": "product_abbr",
    "Price": "original_price", "Price Low": "sales_price",
    "Price Unit": "price_unit_index", "Category": "category_num",
    "Department": "department_num", "Pre tare": "pre_tare_value",
    "BarCode Format": "barcode_format", "Label Format": "label_format_num",
    "Disabled": "disabled",
}

# Ο ζυγός τα δέχεται, αλλά το AutoProcess δεν τα έστελνε ποτέ. Μένουν κλειστά
# από προεπιλογή: στέλνουμε ό,τι ακριβώς στέλνει και το AutoProcess.
CSV_TO_JSON_EXTRA = {
    "NameSpell": "name_sort", "AbbrSpell": "abbr_sort",
    "Origin": "place_of_origin", "Label Format2": "label_format_num2",
    "Pcs": "pcs_flag", "Tax": "tax_num", "Shelf Number": "shelf_num",
    "Image": "image_filename", "Period": "used_by_days",
    "Recommend": "reccommend_days", "Ingredient": "ingredients",
    "Temperautre": "temperature_info", "Nutritional": "nutrition",
    "Produced": "produced", "Pre tare unit": "pre_tare_unit_index",
    "Production date": "produced_date", "Packing date": "pack_date",
    "Use By date": "exp_date", "Expiration": "expiration_date",
    "REMARK1": "remark_1", "REMARK2": "remark_2", "REMARK3": "remark_3",
    "REMARK4": "remark_4", "REMARK5": "remark_5", "REMARK6": "remark_6",
    "REMARK7": "remark_7", "REMARK8": "remark_8",
}

# Τα 40 πεδία της κλάσης ModelProduct. Όσα μένουν κενά στέλνονται "" ή null,
# ακριβώς όπως τα στέλνει το AutoProcess — ποτέ δεν παραλείπονται.
MODEL_FIELDS = [
    ("product_number", ""), ("product_code", ""), ("product_name", ""),
    ("name_sort", None), ("product_abbr", ""), ("abbr_sort", None),
    ("category_num", ""), ("department_num", ""), ("pre_tare_value", ""),
    ("pre_tare_unit_index", ""), ("place_of_origin", None), ("pcs_flag", ""),
    ("original_price", ""), ("sales_price", ""), ("price_unit_index", ""),
    ("tax_num", None), ("barcode_format", ""), ("used_by_days", ""),
    ("reccommend_days", ""), ("label_format_num", ""), ("label_format_num2", None),
    ("image_filename", ""), ("disabled", ""), ("shelf_num", None),
    ("produced_date", ""), ("pack_date", ""), ("exp_date", ""),
    ("expiration_date", None), ("ingredients", ""), ("temperature_info", ""),
    ("nutrition", ""), ("produced", ""),
] + [("remark_%d" % i, "") for i in range(1, 9)]


# Όλα τα πεδία που δέχεται ο ζυγός T-Scale (κλάση ModelProduct, 40 πεδία), με
# ελληνική περιγραφή και το όνομα της στήλης στη βάση του ζυγού (όπως φαίνεται
# στην εξαγωγή Excel του ζυγού). Από εδώ διαλέγει ο τεχνικός τι θα στέλνει σε
# κάθε πελάτη — στο παράθυρο «Πεδία T-Scale», σαν το παλιό «Παράμετροι».
#   (στήλη CSV, πεδίο JSON, περιγραφή, στήλη στη βάση του ζυγού, βασικό;)
# «βασικό» = το έστελνε και το AutoProcess· τα υπόλοιπα θέλουν το
# direct_all_fields, που ανοίγει μόνο του όταν ενεργοποιηθεί τέτοιο πεδίο.
TSCALE_FIELDS = (
    ("ProductNumber", "product_number", "Κωδικός είδους (PLU)", "PRODUCT_NUM", True),
    ("BarCode", "product_code", "Barcode / κωδικός ετικέτας", "BARCODE", True),
    ("ProductName", "product_name", "Όνομα είδους", "PRODUCT_NAME", True),
    ("Abbr", "product_abbr", "Συντομογραφία ονόματος (2η γραμμή ετικέτας)", "ABBR", True),
    ("Price", "original_price", "Τιμή, π.χ. 5.40", "PRICE", True),
    ("Price Low", "sales_price", "Τιμή προσφοράς", "PRICE_LOWEST", True),
    ("Price Unit", "price_unit_index", "Μονάδα τιμής: 0 = ανά κιλό, 1 = ανά τεμάχιο", "PRICEUNIT", True),
    ("Category", "category_num", "Κατηγορία (αριθμός στον ζυγό)", "CATEGORY", True),
    ("Department", "department_num", "Τμήμα (αριθμός στον ζυγό)", "DEPARTMENT", True),
    ("Pre tare", "pre_tare_value", "Απόβαρο", "TARE", True),
    ("BarCode Format", "barcode_format", "Μορφή barcode (αριθμός)", "BARCODE_FORMAT", True),
    ("Label Format", "label_format_num", "Μορφή ετικέτας (αριθμός· -1 = προεπιλογή)", "LABELFORMAT", True),
    ("Disabled", "disabled", "Απενεργοποιημένο είδος (0/1)", "DISABLED", True),
    ("NameSpell", "name_sort", "Όνομα για ταξινόμηση / αναζήτηση", "NAME_SPELL", False),
    ("AbbrSpell", "abbr_sort", "Συντομογραφία για αναζήτηση", "ABBR_SPELL", False),
    ("Tax", "tax_num", "ΦΠΑ (αριθμός κατηγορίας ΦΠΑ στον ζυγό)", "TAX_NUM", False),
    ("Pcs", "pcs_flag", "Τεμαχιακό (0/1)", "PCS_FLAG", False),
    ("Origin", "place_of_origin", "Προέλευση", "AREA", False),
    ("Label Format2", "label_format_num2", "2η μορφή ετικέτας", "", False),
    ("Shelf Number", "shelf_num", "Ράφι", "", False),
    ("Image", "image_filename", "Αρχείο εικόνας", "IMAGE", False),
    ("Period", "used_by_days", "Ημέρες μέχρι τη λήξη", "PERIOD", False),
    ("Recommend", "reccommend_days", "Ημέρες προτεινόμενης κατανάλωσης", "RECOMMEND", False),
    ("Ingredient", "ingredients", "Συστατικά / αλλεργιογόνα", "INGREDIENT", False),
    ("Temperautre", "temperature_info", "Θερμοκρασία συντήρησης (κείμενο)", "TEMP_TEXT", False),
    ("Nutritional", "nutrition", "Διατροφικά στοιχεία", "NUTRITIONAL", False),
    ("Produced", "produced", "Παραγωγός", "PRODUCED", False),
    ("Pre tare unit", "pre_tare_unit_index", "Μονάδα απόβαρου", "P_TARE_UNIT", False),
    ("Production date", "produced_date", "Ημερομηνία παραγωγής", "KILL_DATA", False),
    ("Packing date", "pack_date", "Ημερομηνία συσκευασίας", "PACKING_DATA", False),
    ("Use By date", "exp_date", "Ανάλωση έως", "USED_DATA", False),
    ("Expiration", "expiration_date", "Λήξη", "", False),
) + tuple(("REMARK%d" % i, "remark_%d" % i, "Σημείωση %d (ελεύθερο κείμενο)" % i, "REMARK%d" % i, False)
          for i in range(1, 9))
TSCALE_BY_CSV = {t[0]: t for t in TSCALE_FIELDS}


def csv_map(cfg):
    """Η αντιστοίχιση στηλών: ίδια με το AutoProcess, ή διευρυμένη αν ζητηθεί."""
    m = dict(CSV_TO_JSON)
    if cfg.get("direct_all_fields"):
        m.update(CSV_TO_JSON_EXTRA)
    return m


def greek_as_autoprocess(text):
    """Μιμείται το σφάλμα κωδικοσελίδας του AutoProcess, ώστε ο ζυγός να δει
    ακριβώς ό,τι έβλεπε πάντα.

    Το AutoProcess διαβάζει το cp1253 αρχείο σαν Windows-1252: το «Κ» (0xCA) του
    φαίνεται «Ê», ενώ το «’» (0x92) περνάει σωστά — κάτι που αποκλείει το Latin-1.
    Ο ζυγός έχει μάθει να τα διαβάζει έτσι, οπότε το αναπαράγουμε πιστά αντί να
    «διορθώσουμε» κάτι που δουλεύει.
    """
    try:
        return text.encode("cp1253").decode("cp1252", "replace")
    except UnicodeEncodeError:
        return text


def build_products_json(path, cfg, log):
    """Διαβάζει το αρχείο προϊόντων και φτιάχνει το JSON που περιμένει ο ζυγός."""
    enc = cfg.get("step2_out_encoding") or "cp1253"
    delim = {"csv": ",", "tab": "\t", "semicolon": ";"}.get(
        cfg.get("step2_format", "csv"), cfg.get("step2_delimiter", ",") or ",")
    try:
        with open(path, "rb") as fh:
            raw = fh.read()
    except Exception as exc:
        raise StepError("Βήμα 4", "Αδυναμία ανάγνωσης του αρχείου προϊόντων.",
                        "%s\n%s" % (path, exc))

    text = raw.decode(enc, "replace")
    lines = [l for l in text.replace("\r\n", "\n").split("\n") if l.strip()]
    if not lines:
        raise StepError("Βήμα 4", "Το αρχείο προϊόντων είναι κενό.", path)

    if not cfg.get("step2_write_header", True):
        raise StepError("Βήμα 4", "Η απευθείας αποστολή χρειάζεται γραμμή επικεφαλίδων.",
                        "Ενεργοποίησε το «Γράψε γραμμή επικεφαλίδων» στο Βήμα 3.")

    mapping = csv_map(cfg)
    header = [h.strip() for h in lines[0].split(delim)]
    known = [h for h in header if h in mapping]
    unknown = [h for h in header if h and h not in mapping]
    log("  στέλνονται %d στήλες: %s" % (len(known), ", ".join(known)))
    if unknown:
        log("  (αγνοούνται, δεν υπάρχει αντίστοιχο πεδίο στον ζυγό: %s)" % ", ".join(unknown))

    items = []
    for line in lines[1:]:
        cols = line.split(delim)
        row = dict(MODEL_FIELDS)
        for i, name in enumerate(header):
            key = mapping.get(name)
            if key and i < len(cols):
                # Το AutoProcess πετάει τα διπλά εισαγωγικά (τα θεωρεί σήμανση CSV),
                # π.χ. ΣΑΛΑΜΙ ΑΕΡΟΣ "ΩΡΑΙΑ ΔΡΑΜΑ" -> ΣΑΛΑΜΙ ΑΕΡΟΣ ΩΡΑΙΑ ΔΡΑΜΑ.
                # Τα κενά στο τέλος μένουν: έτσι τα στέλνει και το AutoProcess.
                row[key] = cols[i].replace('"', "")
        items.append(row)
    return items


def scale_reachable(ip, timeout=5):
    """Γρήγορος έλεγχος ότι ο ζυγός ακούει, πριν στείλουμε megabytes.

    Χωρίς αυτό, ένας κλειστός ζυγός κρατάει τη ροή για λεπτά περιμένοντας
    timeout — και καθυστερούν μαζί του και οι υπόλοιποι.
    """
    import socket
    try:
        with socket.create_connection((ip, SCALE_PORT), timeout):
            return True, ""
    except Exception as exc:
        return False, "δεν απαντά στη θύρα %d (%s)" % (SCALE_PORT, exc)


def encode_body(items, quirk=False, wire="utf-8"):
    """Το σώμα του αιτήματος, με τον τρόπο γραφής των ελληνικών που ζητήθηκε.

    Τρεις παραλλαγές, γιατί δεν υπάρχει τεκμηρίωση κατασκευαστή:
      quirk=False, wire=utf-8   → «Κ» = ce 9a   (καθαρά ελληνικά — προεπιλογή)
      quirk=True,  wire=utf-8   → «Κ» = c3 8a   (mojibake· έβγαλε κινέζικα στον ERGON)
      quirk=True,  wire=cp1252  → «Κ» = ca      (αυτούσια cp1253 bytes)
    """
    if quirk:
        items = [{k: (greek_as_autoprocess(v) if isinstance(v, str) else v)
                  for k, v in row.items()} for row in items]
    # Χωρίς κενά μετά από «:» και «,» — έτσι το γράφει το Newtonsoft.Json του
    # AutoProcess, ώστε το σώμα να έχει την ίδια δομή.
    text = json.dumps(items, ensure_ascii=False, separators=(",", ":"))
    return text.encode(wire, "replace")


def send_to_scale(ip, items, log, timeout=180, quirk=False, wire="utf-8"):
    """Στέλνει τα προϊόντα σε έναν ζυγό. Επιστρέφει (επιτυχία, μήνυμα)."""
    import urllib.request, urllib.error
    ok, why = scale_reachable(ip)
    if not ok:
        return False, why
    body = encode_body(items, quirk, wire)
    url = "http://%s:%d/products" % (ip, SCALE_PORT)
    req = urllib.request.Request(url, data=body, method="POST", headers={
        "Content-Type": "application/json",
        "Accept": "application/json, application/xml, text/json, text/x-json, "
                  "text/javascript, text/xml",
        # Ίδιες κεφαλίδες με το AutoProcess: ο ζυγός βλέπει ακριβώς ό,τι συνήθιζε.
        "User-Agent": "RestSharp 102.7.0.0",
        "Accept-Encoding": "gzip, deflate",
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            answer = resp.read().decode("utf-8", "replace")[:200]
            return True, "HTTP %d %s" % (resp.status, answer.strip())
    except urllib.error.HTTPError as exc:
        return False, "HTTP %d: %s" % (exc.code, exc.reason)
    except Exception as exc:
        return False, str(exc)


# Τα πεδία που ανανεώνονται στην καθημερινή ενημέρωση τιμών. Ό,τι δεν είναι εδώ
# —πρώτα απ' όλα το όνομα— μένει στη ζυγαριά ακριβώς όπως το βρήκαμε.
PRICE_FIELDS = ("original_price", "sales_price", "price_unit_index")

# Αν λείπει μεγαλύτερο ποσοστό από αυτό, σταματάμε αντί να σβήσουμε: πιθανότατα
# το ERP έβγαλε μερικό αρχείο (ή κόπηκε στη μέση) και δεν είναι πραγματικές
# διαγραφές. Καλύτερα μια χαμένη εκτέλεση παρά άδεια ζυγαριά μέσα στη βάρδια.
MAX_DELETE_RATIO = 0.30


def find_deleted(yparxonta, items, log):
    """Ποια προϊόντα του ζυγού δεν υπάρχουν πια στο αρχείο του ERP.

    Καλείται ΜΟΝΟ όταν ο τεχνικός έχει δηλώσει ότι το ERP βγάζει ολόκληρο τον
    κατάλογο. Σε πελάτη που βγάζει μόνο τις αλλαγές, «ό,τι λείπει» είναι απλώς
    ό,τι δεν άλλαξε — και θα σβήναμε σχεδόν όλο το κατάστημα.
    """
    sto_arxeio = set()
    for row in items:
        sto_arxeio.add(str(row.get("product_number", "")).lstrip("0") or "0")
    energa = {k: v for k, v in yparxonta.items() if str(v.get("disabled")) != "1"}
    leipoun = [k for k in energa if k not in sto_arxeio]
    if not leipoun:
        return []
    analogia = len(leipoun) / float(len(energa) or 1)
    if analogia > MAX_DELETE_RATIO:
        raise StepError(
            "Βήμα 4",
            "Ακύρωση: το αρχείο θα έσβηνε %d από τα %d προϊόντα του ζυγού (%d%%)."
            % (len(leipoun), len(energa), round(analogia * 100)),
            "Αυτό συνήθως σημαίνει ότι το ERP έβγαλε μερικό αρχείο, ή ότι ο "
            "πελάτης στέλνει μόνο τις αλλαγές.\n\n"
            "Αν ο πελάτης στέλνει μόνο τις αλλαγές, ξε-τσέκαρε το «Το αρχείο "
            "περιέχει ΟΛΑ τα προϊόντα».\n"
            "Αν όντως καταργήθηκαν τόσα προϊόντα, σβήσ' τα από τη ζυγαριά με "
            "το χέρι — δεν το κάνουμε αυτόματα σε τέτοιο μέγεθος.")
    log("  θα απενεργοποιηθούν %d προϊόντα που δεν υπάρχουν πια στο ERP"
        % len(leipoun))
    svisimena = []
    for kleidi in leipoun:
        row = dict(yparxonta[kleidi])
        row["disabled"] = "1"
        svisimena.append(row)
    return svisimena


def fetch_scale_products(ip, timeout=90):
    """Διαβάζει τη βάση προϊόντων του ζυγού. Επιστρέφει {κωδικός: εγγραφή}."""
    import urllib.request
    url = "http://%s:%d/products" % (ip, SCALE_PORT)
    req = urllib.request.Request(url, headers={"User-Agent": "RestSharp 102.7.0.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode("utf-8", "replace"))
    yparxonta = {}
    for row in data:
        kleidi = str(row.get("product_number", "")).lstrip("0") or "0"
        yparxonta[kleidi] = row
    return yparxonta


def merge_prices_only(yparxonta, items, log):
    """Κρατάει τις εγγραφές του ζυγού και αλλάζει μόνο τις τιμές.

    Γιατί έτσι: τα ονόματα στη ζυγαριά είναι γραμμένα με την κωδικοσελίδα που
    έβαλε όποιος τα πρωτοέστειλε. Αν τα ξαναστείλουμε εμείς με άλλη, αλλάζει η
    γραφή τους και βγαίνουν αλλόκοτοι χαρακτήρες στην ετικέτα. Στην καθημερινή
    ενημέρωση δεν έχουμε λόγο να τα αγγίξουμε καθόλου.
    """
    telika, kaina, allages = [], 0, 0
    for row in items:
        kleidi = str(row.get("product_number", "")).lstrip("0") or "0"
        palia = yparxonta.get(kleidi)
        if palia is None:
            telika.append(row)                 # νέο προϊόν: πάει ολόκληρο
            kaina += 1
            continue
        enimeromeni = dict(palia)
        aliaxe = False
        for pedio in PRICE_FIELDS:
            nea = row.get(pedio)
            if nea not in (None, "") and str(nea) != str(palia.get(pedio, "")):
                enimeromeni[pedio] = nea
                aliaxe = True
        if aliaxe:
            allages += 1
        telika.append(enimeromeni)
    log("  ενημέρωση τιμών: %d άλλαξαν, %d νέα προϊόντα, %d συνολικά"
        % (allages, kaina, len(telika)))
    if kaina == len(telika):
        log("  ο ζυγός δεν είχε κανένα από αυτά — γράφονται όλα από την αρχή")
    elif kaina:
        log("  τα υπάρχοντα ονόματα μένουν ανέπαφα· γράφονται μόνο τα %d νέα" % kaina)
    else:
        log("  τα ονόματα στη ζυγαριά μένουν ανέπαφα")
    return telika


def load_pending():
    """Ζυγοί που περιμένουν ακόμα την ενημέρωση. {IP: πότε απέτυχε}"""
    try:
        with open(PENDING_PATH, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return {}


def save_pending(pending):
    try:
        with open(PENDING_PATH, "w", encoding="utf-8") as fh:
            json.dump(pending, fh, indent=2, ensure_ascii=False)
    except Exception:
        pass                        # δεν σταματάμε τη δουλειά για το σημειωματάριο


def mark_pending(ip, why):
    p = load_pending()
    if ip not in p:
        p[ip] = {"since": datetime.datetime.now().isoformat(timespec="seconds"),
                 "tries": 0, "why": why}
    p[ip]["tries"] = int(p[ip].get("tries", 0)) + 1
    p[ip]["why"] = why
    p[ip]["last"] = datetime.datetime.now().isoformat(timespec="seconds")
    save_pending(p)


def clear_pending(ip, log=None):
    p = load_pending()
    if ip in p:
        apo = p[ip].get("since", "")
        del p[ip]
        save_pending(p)
        if log:
            log("  -> %s: πρόλαβε την ενημέρωση (εκκρεμούσε από %s)" % (ip, apo))


def retry_pending_scales(cfg, log, stop_event=None):
    """Ξαναδοκιμάζει τους ζυγούς που έχασαν την τελευταία ενημέρωση.

    Στέλνει το ΤΡΕΧΟΝ product.csv, όχι ό,τι ίσχυε τότε: αν στο μεταξύ άλλαξαν
    κι άλλες τιμές, ο ζυγός που άνοιξε τώρα πρέπει να πάρει τις σημερινές.
    """
    pending = load_pending()
    if not pending:
        return
    path = (cfg.get("step2_output") or "").strip()
    if not path or not os.path.isfile(path):
        return                       # δεν έχει τρέξει ακόμα το Βήμα 3

    log("Εκκρεμούν %d ζυγοί από προηγούμενη ενημέρωση — δοκιμή ξανά: %s"
        % (len(pending), ", ".join(sorted(pending))))
    for ip in sorted(pending):
        if stop_event is not None and stop_event.is_set():
            return
        ok, why = scale_reachable(ip)
        if not ok:
            mark_pending(ip, why)
            log("  -> %s: ακόμα κλειστός (%s)" % (ip, why))
            continue
        log("  -> %s: απαντά, στέλνουμε" % ip)
        eidiko = dict(cfg)
        eidiko["scale_ips"] = ip     # μόνο αυτόν, οι άλλοι είναι ενημερωμένοι
        try:
            apotyxies = run_direct_send(eidiko, log, stop_event)
            if not apotyxies:
                clear_pending(ip, log)
        except StepError as exc:
            log("  -> %s: απέτυχε ξανά (%s)" % (ip, exc.message))


def run_direct_send(cfg, log, stop_event=None):
    """Βήμα 4 για τους T-Scale: στέλνει το ίδιο το πρόγραμμα."""
    ips = parse_ips(cfg.get("scale_ips", ""))
    if not ips:
        raise StepError(
            "Βήμα 4", "Δηλώθηκαν ζυγοί T-Scale, αλλά χωρίς IP.",
            "Γράψε τις διευθύνσεις στο Βήμα 4 — ή ξε-τσέκαρε το «Το κατάστημα έχει "
            "ζυγούς T-Scale» αν δεν υπάρχουν.")
    path = (cfg.get("step2_output") or "").strip()
    if not path or not os.path.isfile(path):
        raise StepError("Βήμα 4", "Δεν βρέθηκε το αρχείο προϊόντων για αποστολή.",
                        "Διαδρομή: %s" % path)

    items = build_products_json(path, cfg, log)
    rebuild = bool(cfg.get("direct_rebuild", False))
    plires = bool(cfg.get("erp_full_catalog", False))
    log("  -> απευθείας αποστολή: %d προϊόντα σε %d ζυγό(ους), θύρα %d%s"
        % (len(items), len(ips), SCALE_PORT,
           "  [ΠΛΗΡΗΣ ΑΝΑΚΑΤΑΣΚΕΥΗ]" if rebuild else "  [μόνο τιμές]"))
    log("  το αρχείο του ERP δηλώθηκε ως: %s"
        % ("ΟΛΟΚΛΗΡΟΣ ο κατάλογος" if plires else "μόνο οι αλλαγές"))

    # Ένας ζυγός που δεν απαντά δεν σταματά τους υπόλοιπους: συνεχίζουμε και
    # αναφέρουμε στο τέλος ποιοι έμειναν πίσω.
    failures = []
    tries = max(1, int(cfg.get("direct_retries", 2) or 2))
    for i, ip in enumerate(ips):
        if stop_event is not None and stop_event.is_set():
            break
        # Ο ζυγός απαντά 429 αν του μιλήσεις ξανά μέσα σε λίγα δευτερόλεπτα.
        # Με δύο ζυγούς στη σειρά, ο δεύτερος έτρωγε άρνηση χωρίς να φταίει.
        if i:
            time.sleep(RATE_LIMIT_WAIT)

        pros_apostoli = items
        # Τη βάση του ζυγού τη χρειαζόμαστε και για τη συγχώνευση τιμών, και για
        # να βρούμε τι καταργήθηκε σε πλήρη ανακατασκευή.
        if not rebuild or plires:
            # Καθημερινή ενημέρωση: διαβάζουμε πρώτα τι έχει ο ζυγός και
            # πειράζουμε μόνο τις τιμές. Αν η ανάγνωση αποτύχει, δεν στέλνουμε
            # ολόκληρα τα προϊόντα «στα τυφλά» — θα άλλαζε η γραφή των ονομάτων.
            try:
                yparxonta = fetch_scale_products(ip)
                log("  -> %s: διαβάστηκαν %d προϊόντα από τον ζυγό"
                    % (ip, len(yparxonta)))
                time.sleep(RATE_LIMIT_WAIT)
                if rebuild:
                    # Ολόκληρος ο κατάλογος: ό,τι λείπει έχει όντως καταργηθεί.
                    pros_apostoli = list(items) + find_deleted(yparxonta, items, log)
                else:
                    pros_apostoli = merge_prices_only(yparxonta, items, log)
            except StepError:
                raise
            except Exception as exc:
                log("  -> %s: ΑΠΟΤΥΧΙΑ ανάγνωσης (%s)" % (ip, exc))
                failures.append("%s — δεν διαβάστηκε η βάση του ζυγού: %s" % (ip, exc))
                mark_pending(ip, "δεν διαβάστηκε η βάση: %s" % exc)
                continue

        for attempt in range(1, tries + 1):
            ok, msg = send_to_scale(ip, pros_apostoli, log,
                                    quirk=cfg.get("direct_quirk", False),
                                    wire=cfg.get("direct_wire_encoding", "utf-8"))
            if ok:
                log("  -> %s: ΕΠΙΤΥΧΙΑ  (%s)" % (ip, msg))
                clear_pending(ip, log)
                break
            if attempt < tries:
                # Το 429 δεν είναι βλάβη — είναι «περίμενε». Θέλει περισσότερο
                # από τα 2 δευτερόλεπτα που αρκούν σε μια στιγμιαία αστοχία.
                anamoni = RATE_LIMIT_WAIT if "429" in msg else 2
                log("  -> %s: αποτυχία (%s) — αναμονή %ds, νέα προσπάθεια %d/%d"
                    % (ip, msg, anamoni, attempt + 1, tries))
                time.sleep(anamoni)
            else:
                log("  -> %s: ΑΠΟΤΥΧΙΑ μετά από %d προσπάθειες  (%s)" % (ip, tries, msg))
                failures.append("%s — %s" % (ip, msg))
                # Δεν τον ξεχνάμε: θα ξαναδοκιμάσουμε μόνοι μας ώσπου να ανοίξει.
                mark_pending(ip, msg)
    return failures


# --------------------------------------------------------------------------
# Apeftheias apostoli se zygous Ishida UNI-3, xoris to ScaleLink Pro 5
#
# Το πρωτόκολλο βγήκε από τον κώδικα του ίδιου του ScaleLink Pro 5 (κλάση
# Ishida.Slp.ScaleDb.Slp4000Scale) και επαληθεύτηκε με γέφυρα πάνω σε αληθινό
# ζυγό του πελάτη: 381 προϊόντα, και στις δύο κατευθύνσεις.
#
# Το UNI-3 δεν έχει δικό του πρωτόκολλο — μέσα στο SLP-5 είναι μοντέλο UNI7 με
# τη σημαία m_bUNI_3, οπότε μιλάει UNI-7. Πλήρης τεκμηρίωση: tools/PROTOKOLLO.md
# --------------------------------------------------------------------------
ISHIDA_PORT = 8071
ISHIDA_MSG_SEND = 1001          # εμείς -> ζυγός
ISHIDA_MSG_READ = 2001          # αίτημα ανάγνωσης
ISHIDA_SUBHEADER = 10           # 10 bytes στα UNI-7/UNI-3 (αλλού 8)
ISHIDA_BLOCK = 50               # εγγραφές ανά σύνδεση, όπως το SLP-5
ISHIDA_FIELDS = 118             # πεδία ανά εγγραφή PLU
ISHIDA_CODE_FIELD = 0
ISHIDA_PRICE_FIELD = 70         # τιμή σε ΑΚΕΡΑΙΑ ΛΕΠΤΑ: 790 = 7,90 € (ζυγιζόμενο· τεμάχιο → 71)
ISHIDA_PRICE_PIECE_FIELD = 71   # η τιμή όταν ο τρόπος πώλησης (69) είναι τεμάχιο (1/2)
ISHIDA_BCFORMAT_FIELD = 86      # ποια μορφή barcode τυπώνει το προϊόν
ISHIDA_BCCODE_FIELD = 89        # ο κωδικός που μπαίνει ΜΕΣΑ στο barcode (τα CCCCC)
ISHIDA_NAME_FIELD = 68
ISHIDA_SALESMODE_FIELD = 69     # 0 ζυγιζόμενο, 1/2 τεμάχιο, 4 ανά 100g
ISHIDA_POSFLAG_FIELD = 88       # ΔΕΝ είναι ΦΠΑ: 29 με barcode βάρους, 21 αλλιώς (ERGON)
ISHIDA_TAXNO_FIELD = 39         # η φορολογική κατηγορία του ζυγού (0 στον ERGON)
ISHIDA_GROUP_FIELD = 54         # ομάδα/κατηγορία (0, 2-6 στον ERGON)

# Και τα 118 πεδία της εγγραφής PLU του UNI-7 (θέση, όνομα στη βάση του SLP-5,
# περιγραφή). Βγήκαν από τη σειρά με την οποία το ScaleLink γράφει την εγγραφή
# και επαληθεύτηκαν πάνω στις 381 εγγραφές του ERGON: τα κενά πεδία συμπίπτουν
# ένα προς ένα. Κενό όνομα = πεδίο που το SLP αφήνει πάντα κενό.
ISHIDA_PLU_FIELDS = (
    (0, "Plu_No", "Κωδικός PLU"),
    (1, "ItemCode", "Κωδικός είδους (item code)"),
    (2, "PackDateFlag", "Σημαία ημ/νίας συσκευασίας"),
    (3, "PackTimeFlag", "Σημαία ώρας συσκευασίας"),
    (4, "PackTime", "Ώρα συσκευασίας"),
    (5, "ShelfLifeFlag", "Σημαία διάρκειας ζωής"),
    (6, "ExpiryTimeFlag", "Σημαία ώρας λήξης"),
    (7, "ShelfLife", "Διάρκεια ζωής (ημέρες)"),
    (8, "ExpTime", "Ώρα λήξης"),
    (9, "BestBeforeFlag", "Σημαία «ανάλωση κατά προτίμηση»"),
    (10, "BestBefore", "Ανάλωση κατά προτίμηση (ημέρες)"),
    (11, "PrintFlag", "Σημαία εκτύπωσης"),
    (12, "", ""),
    (13, "", ""),
    (14, "", ""),
    (15, "LabelFormatNo1", "Μορφή ετικέτας 1"),
    (16, "LabelFormatNo2", "Μορφή ετικέτας 2"),
    (17, "LabelFormatNoPrep", "Μορφή ετικέτας προετοιμασίας"),
    (18, "LinkPluNo", "Συνδεδεμένο PLU"),
    (19, "DepositFlag", "Σημαία εγγύησης"),
    (20, "", ""),
    (21, "FreeMsg1", "Ελεύθερο μήνυμα 1"),
    (22, "FreeMsg2", "Ελεύθερο μήνυμα 2"),
    (23, "FreeMsg3", "Ελεύθερο μήνυμα 3"),
    (24, "FreeMsg4", "Ελεύθερο μήνυμα 4"),
    (25, "FreeMsg5", "Ελεύθερο μήνυμα 5"),
    (26, "FreeMsg6", "Ελεύθερο μήνυμα 6"),
    (27, "FreeMsg7", "Ελεύθερο μήνυμα 7"),
    (28, "FreeMsg8", "Ελεύθερο μήνυμα 8"),
    (29, "FreeMsg9", "Ελεύθερο μήνυμα 9"),
    (30, "FreeMsg10", "Ελεύθερο μήνυμα 10"),
    (31, "FreeMsg11", "Ελεύθερο μήνυμα 11"),
    (32, "FreeMsg12", "Ελεύθερο μήνυμα 12"),
    (33, "FreeMsg13", "Ελεύθερο μήνυμα 13"),
    (34, "FreeMsg14", "Ελεύθερο μήνυμα 14"),
    (35, "FreeMsg15", "Ελεύθερο μήνυμα 15"),
    (36, "", ""),
    (37, "", ""),
    (38, "CostPrice", "Τιμή κόστους"),
    (39, "TaxNo", "Φορολογική κατηγορία (TaxNo) — 0 στον ERGON"),
    (40, "", ""),
    (41, "NutrText", "Κείμενο διατροφικών"),
    (42, "", ""),
    (43, "", ""),
    (44, "", ""),
    (45, "2ndLabelFlag", "Σημαία 2ης ετικέτας (2 = όχι)"),
    (46, "", ""),
    (47, "", ""),
    (48, "OpenPriceFlag", "Ανοιχτή τιμή"),
    (49, "Nutrition", "Διατροφικά (αριθμός)"),
    (50, "ForcedTraceFlag", "Σημαία ιχνηλασιμότητας"),
    (51, "SafeHandlingFlag", "Σημαία ασφαλούς χειρισμού"),
    (52, "SafeHandlingNo", "Ασφαλής χειρισμός (αριθμός)"),
    (53, "DeptCode", "Τμήμα"),
    (54, "GroupCode", "Ομάδα / κατηγορία"),
    (55, "PointFlag", "Σημαία πόντων"),
    (56, "PointType", "Τύπος πόντων"),
    (57, "Points", "Πόντοι"),
    (58, "TargetFlag", "Σημαία στόχου"),
    (59, "TargetLimit", "Όριο στόχου"),
    (60, "FeeFlag", "Σημαία τέλους"),
    (61, "Fee", "Τέλος"),
    (62, "CookingNo", "Οδηγίες μαγειρέματος (αριθμός)"),
    (63, "TraceFlag", "Σημαία ιχνηλασιμότητας 2"),
    (64, "SchemeNo", "Σχήμα (αριθμός)"),
    (65, "", ""),
    (66, "DateCalculation", "Υπολογισμός ημερομηνίας"),
    (67, "ImageNo", "Εικόνα (αριθμός)"),
    (68, "DescText", "ΟΝΟΜΑ — σε «…», με χαρακτήρες ελέγχου γραμμής"),
    (69, "SalesMode", "ΤΡΟΠΟΣ ΠΩΛΗΣΗΣ: 0 ζυγιζόμενο, 1/2 τεμάχιο, 4 ανά 100g"),
    (70, "UnitPrice", "ΤΙΜΗ σε λεπτά (ζυγιζόμενο, 70 / τεμάχιο, 71)"),
    (71, "UnitPrice", "ΤΙΜΗ σε λεπτά όταν ο τρόπος πώλησης είναι τεμάχιο (1/2)"),
    (72, "MarkFlag", "Σημαία σήμανσης"),
    (73, "MarkPrice", "Τιμή σήμανσης"),
    (74, "", ""),
    (75, "PackQuant", "Ποσότητα συσκευασίας"),
    (76, "Unit", "Μονάδα"),
    (77, "Weight", "Σταθερό βάρος"),
    (78, "UpperLimit", "Άνω όριο βάρους"),
    (79, "LowerLimit", "Κάτω όριο βάρους"),
    (80, "Tare", "Απόβαρο"),
    (81, "", ""),
    (82, "", ""),
    (83, "", ""),
    (84, "", ""),
    (85, "PosSelect", "Επιλογή POS"),
    (86, "BarCodeNum", "ΜΟΡΦΗ BARCODE (16 βάρος, 4 τιμή, 0 χωρίς)"),
    (87, "PosFlagSelect", "Επιλογή σημαίας POS"),
    (88, "Posflag", "Σημαία POS — στον ERGON 29 (barcode βάρους) / 21 (άλλα)· ΔΕΝ είναι ΦΠΑ"),
    (89, "PosCode", "ΚΩΔΙΚΟΣ ΜΕΣΑ ΣΤΟ BARCODE (τα CCCCC)"),
    (90, "RegCode", "Κωδικός ταμείου"),
    (91, "", ""),
    (92, "PopMsg", "Μήνυμα POP"),
    (93, "Coupon", "Κουπόνι"),
    (94, "ExMessage1", "Έξτρα μήνυμα 1"),
    (95, "ExMessage2", "Έξτρα μήνυμα 2"),
    (96, "ExMessage3", "Έξτρα μήνυμα 3"),
    (97, "Logo1", "Λογότυπο 1"),
    (98, "Logo2", "Λογότυπο 2"),
    (99, "Logo3", "Λογότυπο 3"),
    (100, "TrayNo", "Δίσκος"),
    (101, "WrappingMode", "Τρόπος περιτύλιξης"),
    (102, "", ""),
    (103, "ServeHeight", "Ύψος σερβιρίσματος"),
    (104, "", ""),
    (105, "", ""),
    (106, "", ""),
    (107, "PropTare", "Αναλογικό απόβαρο"),
    (108, "No2Tare", "Δεύτερο απόβαρο"),
    (109, "Ean128CodeType", "Τύπος EAN-128"),
    (110, "ItfCodeType", "Τύπος ITF"),
    (111, "", ""),
    (112, "PriceGroup1", "Ομάδα τιμής 1"),
    (113, "PriceGroup2", "Ομάδα τιμής 2"),
    (114, "PriceGroup3", "Ομάδα τιμής 3"),
    (115, "PriceGroup4", "Ομάδα τιμής 4"),
    (116, "PriceGroup5", "Ομάδα τιμής 5"),
    (117, "", ""),
)
ISHIDA_PLU_BY_POS = {p: (n, d) for p, n, d in ISHIDA_PLU_FIELDS}


# Τα πεδία που γράφουμε ΠΑΝΤΑ (δεν ρυθμίζονται από τον πίνακα «Πεδία ζυγού Ishida»).
ISHIDA_CORE_FIELDS = (ISHIDA_CODE_FIELD, ISHIDA_NAME_FIELD, ISHIDA_PRICE_FIELD,
                      ISHIDA_PRICE_PIECE_FIELD, ISHIDA_BCFORMAT_FIELD, ISHIDA_BCCODE_FIELD)


def ishida_extra_value(entry, row):
    """Η τιμή για ένα επιπλέον πεδίο: από στήλη του host2 (1 = πρώτη, -1 = τελευταία) ή σταθερή.
    Επιστρέφει None αν δεν προκύπτει τίποτα (τότε το πεδίο μένει όπως το έχει ο ζυγός)."""
    try:
        col = int(entry.get("col") or 0)
    except (TypeError, ValueError):
        col = 0
    val = ""
    if col:
        cols = row.get("cols") or []
        idx = col - 1 if col > 0 else col
        if -len(cols) <= idx < len(cols):
            val = cols[idx].strip()
    if not val and str(entry.get("extra", "")).strip():
        val = str(entry["extra"]).strip()
    if not val:
        return None
    return apply_xform(val, entry.get("xform", ""))


def ishida_active_extra_fields(cfg):
    """Τα ενεργά επιπλέον πεδία από τις ρυθμίσεις (λίστα dict με pos/col/extra/xform)."""
    out = []
    for e in cfg.get("ishida_fields") or []:
        try:
            pos = int(e.get("pos"))
        except (TypeError, ValueError):
            continue
        if e.get("enabled") and 0 < pos < ISHIDA_FIELDS and pos not in ISHIDA_CORE_FIELDS:
            out.append(dict(e, pos=pos))
    return out


def ishida_price_index(pedia):
    """Πού είναι η τιμή: 70 για ζυγιζόμενο (τρόπος 0/3), 71 για τεμάχιο."""
    try:
        tropos = (pedia[ISHIDA_SALESMODE_FIELD] or "0").strip()
    except IndexError:
        tropos = "0"
    return ISHIDA_PRICE_FIELD if tropos in ("0", "3", "") else ISHIDA_PRICE_PIECE_FIELD
ISHIDA_ENCODING = "cp1253"

# Οι μορφές barcode του ζυγού. Η λίστα είναι δική του — βρέθηκε ατόφια μέσα στο
# SetupFile/Greece.set του ScaleLink Pro 5. Κάθε γράμμα είναι μία θέση του EAN-13:
#   F σήμανση · C κωδικός είδους · W βάρος · P τιμή · I κωδικός καταστήματος
#   Q ποσότητα · (C/D) ψηφίο ελέγχου · (/10) διαίρεση με το 10
ISHIDA_BARCODE_FORMATS = [
    (0,  "χωρίς barcode"),
    (1,  "FFCCCCC(C/P)PPPP(C/D)"),
    (2,  "FFCCCCCCPPPP(C/D)"),
    (3,  "FCCCCCC(C/P)PPPP(C/D)"),
    (4,  "FFCCCCCPPPPP(C/D)          κωδικός 5 + τιμή 5"),
    (5,  "FCCCCCCPPPPP(C/D)"),
    (6,  "FFCCCC(C/P)PPPPP(C/D)"),
    (7,  "FFCCCCCCWWWW(C/D)"),
    (8,  "FCCCCCCWWWWW(C/D)"),
    (9,  "FCCCCCIIIIII(C/D)"),
    (10, "FFCCCCCCPPPP(C/D) *"),
    (11, "FFCCCCCCWWWW(C/D) *"),
    (12, "FFCCCC(C/W)WWWWW(C/D)"),
    (15, "FFCCCCC(0)PPPP(C/D)"),
    (16, "FFCCCCCWWWWW(C/D)          κωδικός 5 + βάρος 5"),
    (17, "FFCCCCCPPPPP(/10)(C/D)"),
    (18, "FFCCCCC(C/P)PPPP(/10)(C/D)"),
    (19, "FFCCCCC(C/W)WWWW(C/D)"),
    (20, "FCCCCCPPPPPP(C/D)"),
    (21, "FFCCCCPPPPPP(C/D)"),
    (22, "FCCCWWWWPPPP(C/D)"),
    (23, "FFCCCCQQPPPP(C/D)"),
    (24, "FIIIIIIPPPPP(C/D)"),
    (25, "FFIIIIIIPPPP(C/D)"),
    (26, "FCCCCPPPPPPP(C/D)"),
    (27, "FIIIIIIPPPPP(/10)(C/D)"),
    (28, "FFIIIIIIPPPP(/10)(C/D)"),
    (29, "FCCCCCCPPPPP(/10)(C/D)"),
    (30, "FFCCCCCCPPPP(/10)(C/D)"),
    (31, "FFCCCCCQQQQQ(C/D)"),
    (32, "CUSTOM"),
    (34, "FFSRRR(C/P)PPPPP(C/D)"),
    (35, "FFSCCC(C/P)PPPPP(C/D)"),
]
ISHIDA_BC_KEEP = -1             # «μην την αλλάζεις» — η προεπιλογή

# Πρότυπο για προϊόν που δεν υπάρχει ακόμα στον ζυγό.
#
# Δεν το επινοήσαμε: βγήκε από τις 381 εγγραφές ενός αληθινού UNI-3, κρατώντας
# τα 110 πεδία που ήταν ΙΔΙΑ σε όλα. Τα υπόλοιπα οκτώ (κωδικός, τρόπος πώλησης,
# ομάδα, όνομα, τιμή, μορφή barcode, ΦΠΑ, κωδικός barcode) τα γεμίζουμε εμείς.
#
# Χρησιμοποιείται ΜΟΝΟ όταν ο ζυγός είναι εντελώς άδειος. Αν έχει έστω ένα
# προϊόν, προτιμάμε εκείνο ως πρότυπο: ξέρει καλύτερα από εμάς πώς είναι
# στημένη η συγκεκριμένη εγκατάσταση.
ISHIDA_TEMPLATE = ',0,1,0,0,1,0,1000,0,2,0,1,,,,0,0,0,0,0,,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,,,,0,,,,,,2,,,0,0,2,1,0,0,0,0,0,0,1,0,3,0,0,0,0,,,0,,0,,0,0,0,,0,0,0,0,0,0,,,,,0,0,1,0,,0,,0,0,0,0,0,0,0,0,,,,,,,,0,0,,,,0,0,0,0,0,'

ISHIDA_TAX_FIELD = ISHIDA_POSFLAG_FIELD   # παλιό όνομα — ΔΕΝ είναι ΦΠΑ, δεν το γράφουμε πια


# Πόσους χαρακτήρες χωράει μία γραμμή ονόματος στον ζυγό, ανά μορφή. Μετρήθηκε
# στα 381 προϊόντα που είχε γράψει το ScaleLink Pro 5 σε αληθινό UNI-3: στην
# απλή μορφή καμία γραμμή δεν ξεπερνούσε τους 25 χαρακτήρες — τα μεγαλύτερα
# ονόματα τα έσπαγε σε δύο γραμμές. Γραμμή πάνω από το όριο → ο ζυγός δείχνει
# «too many characters» στην οθόνη του.
ISHIDA_LINE_SIMPLE = "\\x0d\\x0d"
ISHIDA_LINE_BIG = "\\x0d\\x08\\x02"
# Η γραμματοσειρά 13 του ζυγού λέγεται «C25 (30x15)»: 25 χαρακτήρες ανά γραμμή,
# 15 κουκκίδες ο καθένας + 2 κενό, για το τυπικό πλάτος περιγραφής. Αν η μορφή
# ετικέτας έχει στενότερο χώρο, χωράνε λιγότεροι — ο ζυγός τότε δείχνει «too
# many char for print». Γι' αυτό το όριο ρυθμίζεται (ishida_name_width).
# Η γραμματοσειρά 8 είναι «C36 (20x10)», έντονη: 11+2 κουκκίδες.
ISHIDA_NAME_WIDTH = {ISHIDA_LINE_SIMPLE: 25, ISHIDA_LINE_BIG: 32}


def ishida_set_name_width(xaraktires):
    """Ορίζει πόσους χαρακτήρες χωράει η γραμμή ονόματος (γραμματοσειρά C25).

    Η γραμμή με την έντονη γραμματοσειρά κρατά την ίδια αναλογία πλάτους:
    ό,τι χωράει σε 25 χαρακτήρες των 17 κουκκίδων, χωράει σε 32 των 13.
    """
    try:
        n = int(xaraktires)
    except (TypeError, ValueError):
        return
    n = max(10, min(40, n))
    ISHIDA_NAME_WIDTH[ISHIDA_LINE_SIMPLE] = n
    ISHIDA_NAME_WIDTH[ISHIDA_LINE_BIG] = (n * 17) // 13
ISHIDA_NAME_LINES = 2


def ishida_wrap_name(keimeno, platos, grammes=ISHIDA_NAME_LINES):
    """Σπάει το όνομα σε γραμμές, ακριβώς όπως το ScaleLink Pro 5.

    Κόβει μετά από το τελευταίο κενό, τελεία, «/» ή «-» που χωράει στη γραμμή
    («…ΠΟΠ Ε.» + «Ζ», «…ΚΑΡΑΜΑΝ/» + «ΚΟΣ ΒΟΔ», «SARY ΜΟΡΤΑΔΕΛΑ ΔΡΑΜΑΣ » +
    «ΖΩΪΚΗ Ε.Ζ»)· αν δεν
    υπάρχει τέτοιο σημείο, κόβει εκεί που τελειώνει η γραμμή. Το κείμενο δεν
    αλλάζει σε τίποτα: οι γραμμές ενωμένες ξαναδίνουν το αρχικό, με τα κενά του.
    Επαληθεύτηκε με τα ονόματα που είχε σπάσει το ίδιο το SLP-5.

    Επιστρέφει (γραμμές, κόπηκε κάτι στο τέλος).
    """
    ypoloipo = (keimeno or "").strip()
    out = []
    while ypoloipo:
        if len(ypoloipo) <= platos:
            out.append(ypoloipo)
            break
        thesi = platos
        for i in range(platos, 0, -1):
            if ypoloipo[i - 1] in " ./-":
                thesi = i
                break
        out.append(ypoloipo[:thesi])
        ypoloipo = ypoloipo[thesi:]
    return out[:grammes], len(out) > grammes


def _name_parts(pedio):
    """Χωρίζει το πεδίο ονόματος σε (όνομα, ό,τι ακολουθεί — π.χ. συστατικά)."""
    keimeno = pedio.strip().strip('"')
    thesi = keimeno.find("\\x0d\\x03")
    if thesi >= 0:
        return keimeno[:thesi], keimeno[thesi:]
    return keimeno, ""


def ishida_name_too_long(pedio):
    """Έχει το όνομα γραμμή μεγαλύτερη από όσο χωράει ο ζυγός;"""
    onoma, _oura = _name_parts(pedio)
    styl = ISHIDA_LINE_BIG if onoma.startswith(ISHIDA_LINE_BIG) else ISHIDA_LINE_SIMPLE
    platos = ISHIDA_NAME_WIDTH[styl]
    for kommati in re.split(r"\\x[0-9a-fA-F]{2}", onoma):
        if len(kommati) > platos:
            return True
    return False


def ishida_format_name(onoma):
    """Το όνομα όπως το αποθηκεύει ο ζυγός, με τις εντολές μορφοποίησης.

    Στον ζυγό τα ονόματα δεν είναι σκέτο κείμενο: έχουν μέσα χαρακτήρες που
    λένε στην ετικέτα πού αλλάζει γραμμή και τι μέγεθος γράμματα να βάλει,
    γραμμένους ως κείμενο («\\x0d»), όχι ως πραγματικά bytes.

    Κρατάμε την απλούστερη μορφή που χρησιμοποιεί ο ίδιος ο ζυγός — μία γραμμή,
    προεπιλεγμένο μέγεθος. Έτσι είναι γραμμένα 81 από τα 381 προϊόντα του.
    """
    katharo = (onoma or "").replace('"', "").replace(",", " ").strip()
    grammes, _kopike = ishida_wrap_name(katharo, ISHIDA_NAME_WIDTH[ISHIDA_LINE_SIMPLE])
    return '"%s"' % "".join(ISHIDA_LINE_SIMPLE + g for g in grammes)


def ishida_barcode_label(arithmos):
    """Η μορφή όπως τη δείχνουμε στον χρήστη: «16 · FFCCCCCWWWWW(C/D)»."""
    if arithmos == ISHIDA_BC_KEEP:
        return "μην την αλλάζεις (όπως είναι στον ζυγό)"
    for n, perigrafi in ISHIDA_BARCODE_FORMATS:
        if n == arithmos:
            return "%d · %s" % (n, perigrafi)
    return str(arithmos)


def _ishida_bcd(value, nbytes):
    """Αριθμός σε BCD, όπως η Num2Bcd του SLP-5: 4 ψηφία σε 2 bytes."""
    out = bytearray(nbytes)
    for i in range(nbytes - 1, -1, -1):
        out[i] = (value % 10) | ((value // 10 % 10) << 4)
        value //= 100
    return bytes(out)


def _ishida_bcd2num(raw, offset, psifia):
    num = 0
    for b in bytearray(raw[offset:offset + (psifia + 1) // 2]):
        num = num * 100 + (b >> 4) * 10 + (b & 0x0F)
    return num


def _ishida_header(msg_no, data_size):
    """Κεφαλίδα 8 bytes. Προσοχή: το μέγεθος γράφεται ΣΥΝ 8."""
    head = bytearray(8)
    head[0:2] = _ishida_bcd(msg_no, 2)
    total = data_size + 8
    head[4:8] = bytes([(total >> 24) & 255, (total >> 16) & 255,
                       (total >> 8) & 255, total & 255])
    return bytes(head)


def _ishida_subheader(msg_no, size, zitao_ki_alla=False):
    """Υπο-κεφαλίδα 10 bytes.

    Το byte 2 είναι η σημαία «θέλω κι άλλα» και **είναι απαραίτητη στα αιτήματα
    ανάγνωσης**: χωρίς αυτήν ο ζυγός απαντά ότι δεν έχει κανένα προϊόν, χωρίς
    κανένα σφάλμα. Το ScaleLink Pro 5 τη στέλνει πάντα όταν ζητάει δεδομένα και
    ποτέ όταν στέλνει (SendSubHeader, bIsNextRequest).
    """
    sub = bytearray(ISHIDA_SUBHEADER)
    sub[0:2] = _ishida_bcd(msg_no, 2)
    if zitao_ki_alla:
        sub[2] = 1
    sub[6:10] = bytes([(size >> 24) & 255, (size >> 16) & 255,
                       (size >> 8) & 255, size & 255])
    return bytes(sub)


def _ishida_recv(sock, n):
    raw = b""
    while len(raw) < n:
        part = sock.recv(n - len(raw))
        if not part:
            break
        raw += part
    return raw


def _ishida_read_message(sock):
    """Διαβάζει κεφαλίδα + σώμα. Επιστρέφει (μήνυμα, αποτέλεσμα, σώμα)."""
    head = _ishida_recv(sock, 8)
    if len(head) < 8:
        raise StepError("Βήμα 4", "Ο ζυγός Ishida έκλεισε τη σύνδεση.",
                        "Δεν ήρθε ολόκληρη η κεφαλίδα της απάντησης.")
    msg_no = _ishida_bcd2num(head, 0, 4)
    apotelesma = bytearray(head)[3]
    megethos = int.from_bytes(head[4:8], "big")
    soma = _ishida_recv(sock, max(megethos - 8, 0))
    return msg_no, apotelesma, soma


def _ishida_split_records(soma):
    """Σπάει το σώμα σε εγγραφές, με βάση τις υπο-κεφαλίδες."""
    out, off = [], 0
    while off + ISHIDA_SUBHEADER <= len(soma):
        size = int.from_bytes(soma[off + 6:off + ISHIDA_SUBHEADER], "big")
        if size <= 0 or off + ISHIDA_SUBHEADER + size > len(soma):
            break
        out.append(soma[off + ISHIDA_SUBHEADER:off + ISHIDA_SUBHEADER + size])
        off += ISHIDA_SUBHEADER + size
    return out


def ishida_split_fields(grammi):
    """Χωρίζει την εγγραφή σε πεδία κρατώντας τα ΑΥΤΟΥΣΙΑ, με τα εισαγωγικά τους.

    Δεν χρησιμοποιούμε τον αναγνώστη CSV της Python: αυτός θα έβγαζε το κείμενο
    καθαρό, κι όταν το ξαναγράφαμε θα χάνονταν τα εισαγωγικά που βάζει η Ishida
    ακόμα κι όπου δεν χρειάζονται. Η εγγραφή πρέπει να γυρίσει πίσω απαράλλαχτη
    εκτός από την τιμή, γι' αυτό κρατάμε τα κομμάτια όπως ήρθαν.
    """
    pedia, trexon, mesa = [], [], False
    for ch in grammi:
        if ch == '"':
            mesa = not mesa
            trexon.append(ch)
        elif ch == "," and not mesa:
            pedia.append("".join(trexon))
            trexon = []
        else:
            trexon.append(ch)
    pedia.append("".join(trexon))
    return pedia


def ishida_price_to_cents(value, idi_se_lepta=True):
    """Η τιμή σε ακέραια λεπτά — ο ζυγός δεν δέχεται τίποτε άλλο.

    Με «5.4» ή «5.40» ο ζυγός δείχνει 0,54: περιμένει 540.

    Από το αρχείο του Βήματος 3β η τιμή έρχεται **ήδη σε λεπτά** (το προφίλ την
    έχει μετατρέψει), γι' αυτό δεν την ξαναπολλαπλασιάζουμε. Αν κάποιος στήσει
    το αρχείο με τιμές σε ευρώ, ξε-τσεκάρει τη ρύθμιση και μετατρέπουμε εμείς.
    """
    text = str(value).strip().replace(",", ".")
    if not text:
        return None
    try:
        if idi_se_lepta:
            return int(round(float(text)))
        return int(round(float(text) * 100))
    except ValueError:
        return None


def ishida_read_price_file(cfg, log):
    """Διαβάζει το αρχείο που έφτιαξε το Βήμα 3β για την Ishida.

    Είναι το ίδιο αρχείο που έβγαινε πάντα (host2.csv) — με τις μετατροπές του
    προφίλ, δηλαδή με την τιμή ήδη σε λεπτά. Δεν το ξαναπειράζουμε εδώ: ό,τι
    γράφει το προφίλ, αυτό στέλνουμε.

    Η τιμή διαβάζεται από το ΤΕΛΟΣ της γραμμής (προεπιλογή: τρίτη από το τέλος).
    Έτσι, αν κάποια περιγραφή έχει μέσα κόμμα και μετατοπίσει τις στήλες, η τιμή
    βρίσκεται πάλι σωστά — το ίδιο κόλπο που χρησιμοποιεί και το Βήμα 3.
    """
    path = (cfg.get("ishida_file") or cfg.get("step2b_output") or "").strip()
    if not path:
        folder = cfg.get("output_dir") or os.path.dirname(cfg.get("watch_file", "") or "")
        path = os.path.join(folder, "host2.csv")
    if not os.path.isfile(path):
        raise StepError("Βήμα 4", "Δεν βρέθηκε το αρχείο της Ishida.",
                        "%s\n\nΤο φτιάχνει το Βήμα 3β. Άνοιξε το «Φτιάξε και δεύτερο "
                        "αρχείο» και διάλεξε το προφίλ της Ishida." % path)

    enc = cfg.get("step2b_encoding") or "cp1253"
    delim = cfg.get("ishida_delimiter", ",") or ","
    kodikos_col = int(cfg.get("ishida_code_col", 1) or 1)      # 1 = πρώτη στήλη
    timi_col = int(cfg.get("ishida_price_col", -3) or -3)      # -3 = τρίτη από το τέλος
    with open(path, "rb") as fh:
        raw = fh.read()
    text = raw.decode(enc, "replace")

    onoma_col = int(cfg.get("ishida_name_col", 2) or 2)        # 2η στήλη
    fpa_col = int(cfg.get("ishida_tax_col", -1) or -1)         # τελευταία

    def stili(cols, thesi):
        """Στήλη με θετική ή αρνητική θέση (αρνητική = από το τέλος)."""
        return cols[thesi - 1 if thesi > 0 else thesi].strip()

    items, akyres = [], 0
    for line in text.replace("\r\n", "\n").split("\n"):
        if not line.strip():
            continue
        cols = line.split(delim)
        try:
            kodikos = stili(cols, kodikos_col)
            timi = stili(cols, timi_col)
        except IndexError:
            akyres += 1
            continue
        if not kodikos:
            akyres += 1
            continue
        try:
            onoma = stili(cols, onoma_col)
        except IndexError:
            onoma = ""
        try:
            fpa = stili(cols, fpa_col)
        except IndexError:
            fpa = ""
        items.append({"product_number": kodikos, "original_price": timi,
                      "product_name": onoma, "tax": fpa, "cols": [c.strip() for c in cols]})
    # Δικλείδα: αν το αρχείο έχει τιμές με υποδιαστολή ενώ έχει δηλωθεί ότι
    # είναι σε λεπτά, το «8.50» θα γινόταν 8 λεπτά — δηλαδή λάθος τιμή στο ράφι,
    # χωρίς κανένα σφάλμα. Καλύτερα να σταματήσουμε και να το πούμε.
    if bool(cfg.get("ishida_price_cents", True)):
        me_ypodiastoli = [r["original_price"] for r in items
                          if "." in r["original_price"] or "," in r["original_price"]]
        if len(me_ypodiastoli) > max(2, len(items) // 20):
            raise StepError(
                "Βήμα 4",
                "Οι τιμές στο αρχείο της Ishida μοιάζουν σε ευρώ, όχι σε λεπτά.",
                "Βρέθηκαν %d τιμές με υποδιαστολή, π.χ. %s.\n\nΈτσι όπως είναι, το "
                "«8,50 €» θα έφτανε στον ζυγό ως 8 λεπτά.\n\nΉ ξε-τσέκαρε το «Η τιμή "
                "στο αρχείο είναι ήδη σε λεπτά» στο Βήμα 4, ή διάλεξε στο Βήμα 3 προφίλ "
                "που μετατρέπει την τιμή σε λεπτά."
                % (len(me_ypodiastoli), ", ".join(me_ypodiastoli[:5])))

    log("  αρχείο Ishida: %s" % path)
    log("  διαβάστηκαν %d προϊόντα (κωδικός: στήλη %d, τιμή: στήλη %d από %s)"
        % (len(items), abs(kodikos_col), abs(timi_col),
           "την αρχή" if timi_col > 0 else "το τέλος"))
    if akyres:
        log("  %d γραμμές δεν διαβάστηκαν σωστά και προσπεράστηκαν" % akyres)
    return items


ISHIDA_MSG_STATUS = 3013        # έλεγχος κατάστασης — η «χειραψία» πριν από τα άλλα


def ishida_status_check(ip, timeout=15, log=None):
    """Η πρώτη κουβέντα με τον ζυγό, ακριβώς όπως την κάνει το ScaleLink Pro 5.

    Στην καταγραφή, το SLP-5 ανοίγει πρώτα μια σύνδεση σκέτα γι' αυτό και μόνο
    μετά ζητάει προϊόντα. Το αντιγράφουμε: ο ζυγός το περιμένει, και χωρίς αυτό
    μπορεί να μην απαντήσει με δεδομένα.

    Επιστρέφει (απάντησε, τι είπε).
    """
    import socket
    try:
        with socket.create_connection((ip, ISHIDA_PORT), timeout) as sock:
            sock.settimeout(timeout)
            sock.sendall(_ishida_header(ISHIDA_MSG_STATUS, ISHIDA_SUBHEADER))
            sock.sendall(_ishida_subheader(ISHIDA_MSG_STATUS, 0))
            _msg, apotelesma, soma = _ishida_read_message(sock)
    except Exception as exc:
        return False, str(exc)
    katastasi = _ishida_bcd2num(soma, 0, 2) if len(soma) >= 12 else -1
    if log:
        log("  -> %s: ο ζυγός απάντησε στον έλεγχο (αποτέλεσμα %d, κατάσταση %d)"
            % (ip, apotelesma, katastasi))
    return True, "αποτέλεσμα %d, κατάσταση %d" % (apotelesma, katastasi)


def ishida_fetch_plus(ip, timeout=90, log=None):
    """Διαβάζει ΟΛΑ τα PLU του ζυγού. Επιστρέφει {κωδικός: ωμή εγγραφή}.

    Ο ζυγός τα δίνει σε μπλοκ: ζητάμε «από ποιον κωδικό και πέρα» και
    συνεχίζουμε από τον τελευταίο που μας έδωσε, ώσπου να απαντήσει με
    αποτέλεσμα 1 και άδειο σώμα.
    """
    import socket
    ishida_status_check(ip, log=log)               # πρώτα η χειραψία, όπως το SLP-5
    yparxonta = {}
    apo = "0"
    proti = True
    while True:
        with socket.create_connection((ip, ISHIDA_PORT), timeout) as sock:
            sock.settimeout(timeout)
            aitima = ("%s," % apo).encode(ISHIDA_ENCODING)
            sock.sendall(_ishida_header(ISHIDA_MSG_READ,
                                        len(aitima) + ISHIDA_SUBHEADER))
            sock.sendall(_ishida_subheader(ISHIDA_MSG_READ, len(aitima),
                                           zitao_ki_alla=True) + aitima)
            _msg, apotelesma, soma = _ishida_read_message(sock)

        # Αποτέλεσμα 1 με άδειο σώμα σημαίνει «δεν έχω άλλα» και είναι το
        # φυσιολογικό τέλος. Οτιδήποτε άλλο είναι άρνηση, και ΔΕΝ πρέπει να
        # περάσει για τέλος δεδομένων — αλλιώς φεύγουμε με άδεια χέρια χωρίς
        # να μάθει κανείς γιατί.
        if apotelesma != 0 or not soma:
            teliko = (apotelesma == 1 and not soma)
            if proti and not teliko:
                raise StepError(
                    "Βήμα 4", "Ο ζυγός Ishida αρνήθηκε να δώσει τα προϊόντα του.",
                    "%s — απάντησε στο αίτημα ανάγνωσης με αποτέλεσμα %d και "
                    "%d bytes δεδομένων.\n\nΣυνήθως σημαίνει ότι ο ζυγός είναι "
                    "απασχολημένος (τυπώνει ή ζυγίζει) ή ότι κάποιος τον έχει "
                    "ανοιχτό από το ScaleLink Pro 5. Δοκίμασε ξανά σε λίγο."
                    % (ip, apotelesma, len(soma)))
            break

        eggrafes = _ishida_split_records(soma)
        if not eggrafes:
            break
        proti = False
        teleftaios = apo
        for raw in eggrafes:
            grammi = raw.decode(ISHIDA_ENCODING, "replace")
            pedia = ishida_split_fields(grammi)
            if len(pedia) < ISHIDA_FIELDS:
                continue
            kodikos = pedia[ISHIDA_CODE_FIELD].strip()
            yparxonta[kodikos.lstrip("0") or "0"] = grammi
            teleftaios = kodikos
        if log:
            log("     ...%d προϊόντα ως τον κωδικό %s" % (len(yparxonta), teleftaios))
        if teleftaios == apo:
            break                                   # δεν προχωράει: σταματάμε
        apo = teleftaios
    return yparxonta


def ishida_name_text(pedio):
    """Το σκέτο κείμενο του ονόματος, χωρίς τις εντολές μορφοποίησης.

    Στον ζυγό ένα όνομα μπορεί να είναι σπασμένο σε δύο γραμμές
    («\\x0d\\x0dΦΕΤΑ ΔΟΧΕΙΟ ΔΩΔΩΝΗ ΠΟΠ Ε.\\x0d\\x0dΖ»): ενώνουμε τα κομμάτια
    για να το συγκρίνουμε με το όνομα του ERP.
    """
    keimeno = pedio.strip().strip('"')
    return "".join(re.split(r"\\x[0-9a-fA-F]{2}", keimeno))


def _kanoniko(keimeno):
    """Για σύγκριση: χωρίς κενά και εισαγωγικά, κεφαλαία."""
    return "".join((keimeno or "").replace('"', "").split()).upper()


def ishida_name_changed(pedio, onoma_erp):
    """Άλλαξε το όνομα στο ERP σε σχέση με αυτό που έχει ο ζυγός;

    «Περιέχεται» και όχι «ίσο»: μερικά προϊόντα έχουν μετά το όνομα κι άλλα
    μπλοκ (π.χ. συστατικά), που δεν είναι μέρος του ονόματος του ERP.
    """
    erp = _kanoniko(onoma_erp)
    if not erp:
        return False
    return erp not in _kanoniko(ishida_name_text(pedio))


def ishida_replace_name(pedio, onoma):
    """Βάζει το νέο όνομα κρατώντας τη μορφοποίηση του ζυγού.

    Κρατάμε το «στυλ» της αρχής (με ή χωρίς εντολή μεγέθους γραμμάτων), το
    σπάμε σε γραμμές που χωράνε στον ζυγό, και ό,τι μπλοκ ακολουθεί το όνομα —
    π.χ. συστατικά — μένει αυτούσιο.
    """
    katharo = (onoma or "").replace('"', "").replace(",", " ").strip()
    keimeno, oura = _name_parts(pedio)
    if keimeno.startswith(ISHIDA_LINE_BIG):
        grammes, _k = ishida_wrap_name(katharo, ISHIDA_NAME_WIDTH[ISHIDA_LINE_BIG])
        # Αν μετά το όνομα υπήρχε κενή γραμμή του ίδιου στυλ, τη διατηρούμε —
        # είναι μέρος της διάταξης της ετικέτας. Αν όμως το νέο όνομα θέλει δύο
        # γραμμές, η δεύτερη παίρνει τη θέση της.
        meta = ""
        kleisimo = keimeno.find("\\x02", len(ISHIDA_LINE_BIG))
        if kleisimo >= 0 and len(grammes) == 1:
            meta = keimeno[kleisimo + len("\\x02"):]
            if _kanoniko(ishida_name_text(meta)):
                meta = ""               # η 2η γραμμή είχε κείμενο: ήταν μέρος του ονόματος
        onoma_pedio = "".join(ISHIDA_LINE_BIG + g + "\\x02" for g in grammes)
        return '"%s%s%s"' % (onoma_pedio, meta, oura)
    grammes, _k = ishida_wrap_name(katharo, ISHIDA_NAME_WIDTH[ISHIDA_LINE_SIMPLE])
    return '"%s%s"' % ("".join(ISHIDA_LINE_SIMPLE + g for g in grammes), oura)


def ishida_new_record(protypo, kodikos, onoma, lepta, fpa, morfi_barcode):
    """Φτιάχνει εγγραφή για προϊόν που δεν υπάρχει ακόμα στον ζυγό."""
    pedia = ishida_split_fields(protypo)
    gymnos = kodikos.lstrip("0") or "0"
    pedia[ISHIDA_CODE_FIELD] = gymnos
    pedia[ishida_price_index(pedia)] = str(lepta)
    pedia[ISHIDA_NAME_FIELD] = ishida_format_name(onoma)
    pedia[ISHIDA_BCCODE_FIELD] = gymnos
    # Το πεδίο 88 (Posflag) ΔΕΝ είναι ΦΠΑ — κληρονομείται από το πρότυπο, που
    # διαλέγεται με την ίδια μορφή barcode. Το «fpa» του ERP δεν γράφεται πουθενά.
    if morfi_barcode != ISHIDA_BC_KEEP:
        pedia[ISHIDA_BCFORMAT_FIELD] = str(morfi_barcode)
    return ",".join(pedia)


def ishida_merge_prices(yparxonta, items, log, idi_se_lepta=True,
                       morfi_barcode=ISHIDA_BC_KEEP, kodikos_sto_barcode=False,
                       dimiourgia=False, onomata=True, extra_fields=None):
    """Κρατάει τις εγγραφές του ζυγού και αλλάζει ΜΟΝΟ την τιμή.

    Ίδιος λόγος με τους T-Scale: τα ονόματα στον ζυγό είναι γραμμένα με τη
    γραφή που έβαλε όποιος τα πρωτοέστειλε, μαζί με χαρακτήρες ελέγχου για τη
    μορφοποίηση της ετικέτας. Δεν έχουμε λόγο να τα αγγίξουμε.
    """
    telika, allages, agnosta, akyres = [], 0, [], 0
    barcode_allages, kaina, onomata_allages, spasmena = 0, 0, 0, 0
    extra_fields = list(extra_fields or [])
    extra_allages = 0
    # Πρότυπο για τα καινούργια: προτιμάμε ένα υπαρκτό προϊόν του ίδιου του
    # ζυγού — ξέρει καλύτερα από εμάς πώς είναι στημένη η εγκατάσταση. Μόνο σε
    # εντελώς άδειο ζυγό πέφτουμε στο ενσωματωμένο.
    protypo = ISHIDA_TEMPLATE
    if dimiourgia and yparxonta:
        protypo = next(iter(yparxonta.values()))
        if morfi_barcode != ISHIDA_BC_KEEP:
            # Ίδια μορφή barcode → ίδιες και οι «σημαίες» που τη συνοδεύουν (π.χ. το
            # πεδίο 88: 29 για barcode βάρους, 21 για τα άλλα στον ERGON).
            for eggrafi in yparxonta.values():
                p = ishida_split_fields(eggrafi)
                if len(p) > ISHIDA_BCFORMAT_FIELD and p[ISHIDA_BCFORMAT_FIELD] == str(morfi_barcode):
                    protypo = eggrafi
                    break
    for row in items:
        kodikos = str(row.get("product_number", "")).strip()
        kleidi = kodikos.lstrip("0") or "0"
        palia = yparxonta.get(kleidi)
        lepta = ishida_price_to_cents(row.get("original_price", ""), idi_se_lepta)
        if palia is None:
            if not dimiourgia:
                agnosta.append(kodikos)
                continue
            onoma = (row.get("product_name") or "").strip()
            if not onoma or lepta is None:
                akyres += 1
                continue
            neo = ishida_new_record(protypo, kodikos, onoma, lepta, (row.get("tax") or "").strip(),
                                    morfi_barcode)
            if extra_fields:
                p = ishida_split_fields(neo)
                for e in extra_fields:
                    v = ishida_extra_value(e, row)
                    if v is not None and e["pos"] < len(p):
                        p[e["pos"]] = v
                neo = ",".join(p)
            telika.append(neo)
            kaina += 1
            continue
        if lepta is None:
            akyres += 1
            continue
        pedia = ishida_split_fields(palia)
        if len(pedia) < ISHIDA_FIELDS:
            continue
        thesi_timis = ishida_price_index(pedia)
        idia_timi = pedia[thesi_timis] == str(lepta)

        # Το όνομα αλλάζει μόνο αν άλλαξε στο ERP. Τα υπόλοιπα μένουν όπως τα
        # έγραψε ο ζυγός, με τη μορφοποίησή τους.
        allaxe_onoma = False
        onoma_erp = (row.get("product_name") or "").strip()
        if onomata and onoma_erp and ishida_name_changed(pedia[68], onoma_erp):
            pedia[68] = ishida_replace_name(pedia[68], onoma_erp)
            allaxe_onoma = True
        elif ishida_name_too_long(pedia[68]):
            # Ίδιο όνομα, αλλά σε γραμμή που δεν χωράει — π.χ. γραμμένο από
            # παλιότερη έκδοση μας σε μία γραμμή. Ο ζυγός δείχνει «too many
            # characters»: το ξανασπάμε σε γραμμές, χωρίς να αλλάξει το κείμενο.
            idio = ishida_name_text(_name_parts(pedia[68])[0])
            pedia[68] = ishida_replace_name(pedia[68], idio)
            allaxe_onoma = True
            spasmena += 1

        # Η μορφή του barcode αλλάζει μόνο αν έχει ζητηθεί ρητά. Δεν είναι τιμή
        # που «διορθώνεται»: καθορίζει τι διαβάζει το ταμείο από την ετικέτα.
        piraxe_barcode = False
        if morfi_barcode != ISHIDA_BC_KEEP:
            if pedia[ISHIDA_BCFORMAT_FIELD] != str(morfi_barcode):
                pedia[ISHIDA_BCFORMAT_FIELD] = str(morfi_barcode)
                piraxe_barcode = True
            if kodikos_sto_barcode:
                # Τα CCCCC της μορφής: ο κωδικός του είδους, χωρίς μηδενικά μπροστά.
                gymnos = kodikos.lstrip("0") or "0"
                if pedia[ISHIDA_BCCODE_FIELD] != gymnos:
                    pedia[ISHIDA_BCCODE_FIELD] = gymnos
                    piraxe_barcode = True

        # Επιπλέον πεδία από τον πίνακα «Πεδία ζυγού Ishida» (τμήμα, ομάδα, απόβαρο…):
        # γράφονται μόνο αν διαφέρουν από ό,τι έχει ο ζυγός.
        allaxe_extra = False
        for e in extra_fields:
            v = ishida_extra_value(e, row)
            if v is not None and e["pos"] < len(pedia) and pedia[e["pos"]] != v:
                pedia[e["pos"]] = v
                allaxe_extra = True
        if allaxe_extra:
            extra_allages += 1

        if idia_timi and not piraxe_barcode and not allaxe_onoma and not allaxe_extra:
            continue                                # τίποτα δεν άλλαξε: δεν το στέλνουμε
        pedia[thesi_timis] = str(lepta)
        telika.append(",".join(pedia))
        if allaxe_onoma:
            onomata_allages += 1
        if not idia_timi:
            allages += 1
        if piraxe_barcode:
            barcode_allages += 1

    log("  άλλαξαν οι τιμές σε %d από τα %d προϊόντα του αρχείου"
        % (allages, len(items)))
    if onomata:
        log("  άλλαξαν τα ονόματα σε %d προϊόντα" % (onomata_allages - spasmena))
    if spasmena:
        log("  %d ονόματα ξαναχωρίστηκαν σε γραμμές που χωράνε στον ζυγό" % spasmena)
    if extra_fields:
        log("  επιπλέον πεδία (%s): άλλαξαν σε %d προϊόντα"
            % (", ".join("%d %s" % (e["pos"], ISHIDA_PLU_BY_POS.get(e["pos"], ("?", ""))[0])
                         for e in extra_fields), extra_allages))
    if morfi_barcode != ISHIDA_BC_KEEP:
        log("  μορφή barcode -> %s: άλλαξε σε %d προϊόντα"
            % (ishida_barcode_label(morfi_barcode), barcode_allages))
    if akyres:
        log("  %d προϊόντα δεν είχαν σωστή τιμή και προσπεράστηκαν" % akyres)
    if kaina:
        log("  δημιουργήθηκαν %d καινούργια προϊόντα%s"
            % (kaina, " (ο ζυγός ήταν άδειος — με το ενσωματωμένο πρότυπο)"
               if not yparxonta else ""))
    if agnosta:
        log("  %d προϊόντα δεν τα έχει ο ζυγός: %s%s"
            % (len(agnosta), ", ".join(agnosta[:8]),
               " …" if len(agnosta) > 8 else ""))
        log("  (δεν τα φτιάχνουμε εμείς — θέλουν όνομα και ετικέτα, τα περνάει ο τεχνικός)")
    return telika


def ishida_send_plus(ip, eggrafes, log, timeout=180):
    """Στέλνει τις εγγραφές σε μπλοκ, νέα σύνδεση για κάθε μπλοκ.

    Η νέα σύνδεση ανά μπλοκ δεν είναι δική μας ιδέα: έτσι κάνει και το SLP-5
    (ReconnectUni7Socket) όταν στέλνει PLU σε UNI-7.
    """
    import socket
    stalthikan = enimerothikan = me_sfalma = 0
    for start in range(0, len(eggrafes), ISHIDA_BLOCK):
        block = eggrafes[start:start + ISHIDA_BLOCK]
        soma = b""
        for grammi in block:
            raw = grammi.encode(ISHIDA_ENCODING, "replace")
            soma += _ishida_subheader(ISHIDA_MSG_SEND, len(raw)) + raw
        with socket.create_connection((ip, ISHIDA_PORT), timeout) as sock:
            sock.settimeout(timeout)
            sock.sendall(_ishida_header(ISHIDA_MSG_SEND, len(soma)))
            sock.sendall(soma)
            _msg, apotelesma, apantisi = _ishida_read_message(sock)

        if len(apantisi) < 12:
            raise StepError("Βήμα 4", "Ο ζυγός Ishida δεν απάντησε σωστά.",
                            "%s — απάντηση %d bytes αντί για 12" % (ip, len(apantisi)))
        elavan = _ishida_bcd2num(apantisi, 4, 4)
        enimerosan = _ishida_bcd2num(apantisi, 6, 4)
        sfalmata = _ishida_bcd2num(apantisi, 8, 4)
        kodikos_sfalmatos = int.from_bytes(apantisi[10:12], "big")
        stalthikan += len(block)
        enimerothikan += enimerosan
        me_sfalma += sfalmata
        log("     προϊόντα %d-%d: ο ζυγός πήρε %d, ενημέρωσε %d%s"
            % (start + 1, start + len(block), elavan, enimerosan,
               "  ΔΕΝ ΔΕΧΤΗΚΕ %d" % sfalmata if sfalmata else ""))
        if kodikos_sfalmatos or apotelesma:
            return False, ("ο ζυγός σταμάτησε με σφάλμα %d στα προϊόντα %d-%d"
                           % (kodikos_sfalmatos, start + 1, start + len(block)))
        time.sleep(0.3)
    if me_sfalma:
        return False, "ο ζυγός δεν δέχτηκε %d προϊόντα" % me_sfalma
    return True, "%d προϊόντα, ενημερώθηκαν %d" % (stalthikan, enimerothikan)


def ishida_reachable(ip, timeout=5):
    import socket
    try:
        with socket.create_connection((ip, ISHIDA_PORT), timeout):
            return True, ""
    except Exception as exc:
        return False, "δεν απαντά στη θύρα %d (%s)" % (ISHIDA_PORT, exc)


def run_ishida_direct(cfg, log, stop_event=None):
    """Βήμα 4 για τους Ishida, χωρίς το ScaleLink Pro 5."""
    ishida_set_name_width(cfg.get("ishida_name_width", 25))
    ips = parse_ips(cfg.get("ishida_ips", ""))
    if not ips:
        raise StepError("Βήμα 4", "Δεν έχει γραφτεί IP ζυγού Ishida.",
                        "Συμπλήρωσε τις διευθύνσεις στο πεδίο «IP ζυγών Ishida».")
    items = ishida_read_price_file(cfg, log)
    se_lepta = bool(cfg.get("ishida_price_cents", True))
    log("  -> Ishida: %d προϊόντα προς %d ζυγό(ους)  [αλλάζουν μόνο οι τιμές]"
        % (len(items), len(ips)))

    failures = []
    for ip in ips:
        if stop_event is not None and stop_event.is_set():
            break
        ok, giati = ishida_reachable(ip)
        if not ok:
            log("  -> %s: ο ζυγός δεν απαντά (%s)" % (ip, giati))
            failures.append("%s — %s" % (ip, giati))
            mark_pending(ip, giati)
            continue
        try:
            yparxonta = ishida_fetch_plus(ip, log=log)
            log("  -> %s: διαβάστηκαν %d προϊόντα από τον ζυγό" % (ip, len(yparxonta)))
            # Άδειος ζυγός (καινούργιος, ή μόλις τον άδειασε ο τεχνικός): εδώ δεν
            # υπάρχει τίποτα να χαλάσουμε — δεν υπάρχουν ονόματα να σβηστούν —
            # οπότε τον γεμίζουμε από το αρχείο χωρίς να ρωτήσουμε.
            dimiourgia = bool(cfg.get("ishida_create", False))
            if not yparxonta:
                dimiourgia = True
                log("  -> %s: ο ζυγός είναι άδειος — γράφονται όλα τα προϊόντα "
                    "από την αρχή" % ip)
            pros_apostoli = ishida_merge_prices(
                yparxonta, items, log, se_lepta,
                morfi_barcode=int(cfg.get("ishida_barcode", ISHIDA_BC_KEEP)),
                kodikos_sto_barcode=bool(cfg.get("ishida_barcode_code", False)),
                dimiourgia=dimiourgia,
                onomata=bool(cfg.get("ishida_update_names", True)),
                extra_fields=ishida_active_extra_fields(cfg))
        except StepError:
            raise
        except Exception as exc:
            log("  -> %s: ΑΠΟΤΥΧΙΑ ανάγνωσης (%s)" % (ip, exc))
            failures.append("%s — δεν διαβάστηκε η βάση του ζυγού: %s" % (ip, exc))
            mark_pending(ip, "δεν διαβάστηκε η βάση: %s" % exc)
            continue

        if not pros_apostoli:
            log("  -> %s: καμία αλλαγή — δεν στάλθηκε τίποτα" % ip)
            clear_pending(ip, log)
            continue
        try:
            ok, msg = ishida_send_plus(ip, pros_apostoli, log)
        except StepError:
            raise
        except Exception as exc:
            ok, msg = False, str(exc)
        if ok:
            log("  -> %s: ΕΠΙΤΥΧΙΑ  (%s)" % (ip, msg))
            clear_pending(ip, log)
        else:
            log("  -> %s: ΑΠΟΤΥΧΙΑ  (%s)" % (ip, msg))
            failures.append("%s — %s" % (ip, msg))
            mark_pending(ip, msg)
    return failures


def apologismos(cfg, failures, log):
    """Λέει καθαρά, στο τέλος, ποιοι ζυγοί ενημερώθηκαν και ποιοι όχι.

    Χωρίς αυτό, ένας σβηστός ζυγός χανόταν μέσα στις γραμμές του log και ο
    τεχνικός έφευγε από το κατάστημα νομίζοντας ότι πήγαν όλα καλά.
    """
    oloi = [(ip, "T-Scale") for ip in parse_ips(cfg.get("scale_ips", ""))
            if cfg.get("tscale_on", True)]
    oloi += [(ip, "Ishida") for ip in parse_ips(cfg.get("ishida_ips", ""))
             if cfg.get("ishida_on", False)]
    if not oloi:
        return
    apetyxan = {}
    for grammi in failures:
        ip = grammi.split(" ", 1)[0].strip()
        apetyxan[ip] = grammi.split("—", 1)[-1].strip() if "—" in grammi else ""

    log("")
    log("  ── ΑΠΟΛΟΓΙΣΜΟΣ ─────────────────────────────────────────")
    for ip, marka in oloi:
        if ip in apetyxan:
            log("  ✗ %-16s %-9s ΔΕΝ ΕΝΗΜΕΡΩΘΗΚΕ — %s" % (ip, marka, apetyxan[ip]))
        else:
            log("  ✓ %-16s %-9s ενημερώθηκε" % (ip, marka))
    if apetyxan:
        log("  Οι %d παραπάνω θα ξαναδοκιμαστούν μόνες τους μόλις ανοίξουν."
            % len(apetyxan))
    log("  ────────────────────────────────────────────────────────")


def run_step3(cfg, log, stop_event=None):
    """Βήμα 4: στέλνει σε T-Scale και σε Ishida — και τα δύο από εμάς."""
    # Το κατάστημα μπορεί να έχει μόνο τη μία μάρκα. Η κλειστή παραλείπεται
    # ολόκληρη: ούτε ελέγχεται, ούτε βγάζει σφάλμα που δεν έχει IP.
    exei_tscale = bool(cfg.get("tscale_on", True))
    exei_ishida = bool(cfg.get("ishida_on", False))
    if not exei_tscale and not exei_ishida:
        raise StepError(
            "Βήμα 4", "Δεν έχει δηλωθεί καμία μάρκα ζυγού.",
            "Τσέκαρε στο Βήμα 4 τι έχει το κατάστημα — T-Scale, Ishida UNI-3, ή και τα "
            "δύο — και γράψε τις IP.\n\nΑν δεν θέλεις να στέλνεται τίποτα, κλείσε "
            "ολόκληρο το Βήμα 4.")

    if cfg.get("direct_send"):
        failures = []
        if exei_tscale:
            failures += run_direct_send(cfg, log, stop_event)
        else:
            log("  -> T-Scale: δεν υπάρχουν σε αυτό το κατάστημα, παραλείπονται")
        failures += _run_ishida(cfg, log, stop_event)
        _run_extra_senders(cfg, log, stop_event)      # οι υπόλοιποι ζυγοί κανονικά
        apologismos(cfg, failures, log)
        if failures:
            raise StepError(
                "Βήμα 4", "Δεν ενημερώθηκαν %d ζυγοί." % len(failures),
                "\n".join(failures) +
                "\n\nΟι υπόλοιποι ενημερώθηκαν κανονικά και η προσπάθεια θα "
                "επαναληφθεί μόνη της μόλις ανοίξουν — δεν χάνεται η ενημέρωση.")
        return

    if not exei_tscale:
        failures = _run_ishida(cfg, log, stop_event)
        _run_extra_senders(cfg, log, stop_event)
        apologismos(cfg, failures, log)
        if failures:
            raise StepError("Βήμα 4", "Δεν ενημερώθηκαν %d ζυγοί Ishida." % len(failures),
                            "\n".join(failures))
        return

    exe = (cfg.get("step3_exe") or "").strip()
    secs = int(cfg.get("step3_seconds", 120) or 120)
    if not exe or not os.path.isfile(exe):
        raise StepError("Βήμα 4", "Δεν βρέθηκε το πρόγραμμα T-Scale του κατασκευαστή.",
                        "%s\n\nΕίτε δείξε πού είναι, στα «Για προχωρημένους» του "
                        "Βήματος 4, είτε ξανα-τσέκαρε την «Απευθείας αποστολή»." % exe)

    # Οι IP γράφονται λίγο πριν την εκκίνηση, ώστε να μη μείνει ποτέ το
    # AutoProcess με παλιές διευθύνσεις επειδή ξεχάστηκε μια αποθήκευση.
    ips = parse_ips(cfg.get("scale_ips", ""))
    if ips:
        current = read_ips(exe)
        if current != ips:
            write_ips(exe, ips)
            log("  -> ενημερώθηκε το ip.xml: %s" % ", ".join(ips))

    run_sender(exe, secs, cfg.get("step3_kill", True), log, stop_event, "T-Scale")
    failures = _run_ishida(cfg, log, stop_event)
    _run_extra_senders(cfg, log, stop_event)
    if failures:
        raise StepError(
            "Βήμα 4", "Δεν ενημερώθηκαν %d ζυγοί Ishida." % len(failures),
            "\n".join(failures) +
            "\n\nΟι υπόλοιποι ενημερώθηκαν κανονικά και η προσπάθεια θα "
            "επαναληφθεί στην επόμενη αλλαγή του ERP.")


# --------------------------------------------------------------------------
# Efresi zygon sto diktyo kai katastasi tous
#
# Κάθε μάρκα ακούει σε δική της θύρα, οπότε η ίδια η θύρα μας λέει τι είναι:
# 1235 T-Scale, 8071 Ishida UNI-3. Ανοίγουμε και κλείνουμε τη σύνδεση χωρίς να
# στείλουμε τίποτα — ο ζυγός δεν το καταλαβαίνει καν.
# --------------------------------------------------------------------------
SCALE_KINDS = ((SCALE_PORT, "T-Scale"), (ISHIDA_PORT, "Ishida"))


def local_subnets():
    """Τα δίκτυα όπου βρίσκεται αυτό το μηχάνημα, ως «10.130.20.» κ.λπ.

    Παίρνουμε τη διεύθυνση που θα χρησιμοποιούσαμε για να βγούμε προς τα έξω:
    είναι η κάρτα που βλέπει το δίκτυο του καταστήματος, άρα κι εκείνη που
    βλέπει τους ζυγούς.
    """
    import socket
    diktya = []
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1))
        diktya.append(".".join(s.getsockname()[0].split(".")[:3]) + ".")
        s.close()
    except Exception:
        pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]
            if ip.startswith("127."):
                continue
            net = ".".join(ip.split(".")[:3]) + "."
            if net not in diktya:
                diktya.append(net)
    except Exception:
        pass
    return diktya


def probe_scale(ip, port, timeout=0.6):
    """Ανοίγει και κλείνει μια σύνδεση. True αν ο ζυγός ακούει."""
    import socket
    try:
        with socket.create_connection((ip, port), timeout):
            return True
    except Exception:
        return False


def my_addresses():
    """Οι διευθύνσεις αυτού του μηχανήματος — για να μην τις περάσουμε για ζυγό."""
    import socket
    dikes_mas = set(["127.0.0.1"])
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1))
        dikes_mas.add(s.getsockname()[0])
        s.close()
    except Exception:
        pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            dikes_mas.add(info[4][0])
    except Exception:
        pass
    return dikes_mas


def scan_for_scales(subnet, log=None, stop_event=None, timeout=0.6, workers=120):
    """Σαρώνει ένα δίκτυο /24 και επιστρέφει [(IP, μάρκα, θύρα), …].

    Δοκιμάζουμε 120 διευθύνσεις ταυτόχρονα: σειριακά, 254 διευθύνσεις × 2 θύρες
    με μισό δευτερόλεπτο η καθεμία θα ήθελαν πάνω από τέσσερα λεπτά.

    Το ίδιο μας το μηχάνημα εξαιρείται: αν τρέχει εδώ κάποιο εργαλείο δοκιμών
    στην ίδια θύρα, θα εμφανιζόταν σαν ζυγός.
    """
    from concurrent.futures import ThreadPoolExecutor
    vrethikan = []
    dikes_mas = my_addresses()
    zeugaria = [("%s%d" % (subnet, n), port, onoma)
                for n in range(1, 255) for port, onoma in SCALE_KINDS
                if "%s%d" % (subnet, n) not in dikes_mas]

    def dokimi(z):
        ip, port, onoma = z
        if stop_event is not None and stop_event.is_set():
            return None
        return (ip, onoma, port) if probe_scale(ip, port, timeout) else None

    with ThreadPoolExecutor(max_workers=workers) as pool:
        for apotelesma in pool.map(dokimi, zeugaria):
            if apotelesma:
                vrethikan.append(apotelesma)
                if log:
                    log("     βρέθηκε %s στη %s (θύρα %d)"
                        % (apotelesma[1], apotelesma[0], apotelesma[2]))
    vrethikan.sort(key=lambda t: [int(x) for x in t[0].split(".")])
    return vrethikan


def scales_status(cfg, timeout=1.5):
    """Ποιοι από τους ρυθμισμένους ζυγούς απαντούν αυτή τη στιγμή.

    Επιστρέφει [(IP, μάρκα, ανοιχτός, σε εκκρεμότητα), …].
    """
    from concurrent.futures import ThreadPoolExecutor
    ekkremotites = load_pending()
    zygoi = [(ip, "T-Scale", SCALE_PORT) for ip in parse_ips(cfg.get("scale_ips", ""))]
    zygoi += [(ip, "Ishida", ISHIDA_PORT) for ip in parse_ips(cfg.get("ishida_ips", ""))]
    if not zygoi:
        return []
    with ThreadPoolExecutor(max_workers=max(1, len(zygoi))) as pool:
        anoixtoi = list(pool.map(lambda z: probe_scale(z[0], z[2], timeout), zygoi))
    return [(ip, marka, ok, ekkremotites.get(ip))
            for (ip, marka, _port), ok in zip(zygoi, anoixtoi)]


def _run_ishida(cfg, log, stop_event=None):
    """Οι Ishida απευθείας από εμάς — μόνο αν έχει δοθεί IP.

    Δεν υπάρχει ξεχωριστό τικ: κενό πεδίο IP σημαίνει «δεν υπάρχουν Ishida εδώ»,
    και δεν είναι σφάλμα — τα περισσότερα καταστήματα έχουν μόνο T-Scale.
    """
    if not cfg.get("ishida_on", False):
        return []
    if not parse_ips(cfg.get("ishida_ips", "")):
        raise StepError(
            "Βήμα 4", "Δηλώθηκαν ζυγοί Ishida, αλλά χωρίς IP.",
            "Γράψε τις διευθύνσεις στο Βήμα 4 — ή ξε-τσέκαρε το «Το κατάστημα έχει "
            "ζυγούς Ishida UNI-3» αν δεν υπάρχουν.")
    return run_ishida_direct(cfg, log, stop_event)


def _run_extra_senders(cfg, log, stop_event=None):
    for key, label in EXTRA_SENDERS:
        if not cfg.get("%s_enabled" % key):
            continue
        # Αν τους Ishida τους στέλνουμε πια μόνοι μας, το ScaleLink Pro 5
        # δεν έχει λόγο να ανοίξει — θα έστελνε τα ίδια δεδομένα δεύτερη φορά.
        if key == "ishida" and cfg.get("ishida_direct"):
            log("  -> Ishida: στείλαμε εμείς, οπότε το πρόγραμμα της Ishida δεν ανοίγει")
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
# Odigos antistoixisis stilon: arxeio ERP -> ti einai kathe stili -> profil
#
# Ο τεχνικός δεν γράφει θέσεις και μετατροπές: ανοίγει το αρχείο του ERP, βλέπει
# τις στήλες με πραγματικά δείγματα, λέει «αυτή είναι ο κωδικός, αυτή η τιμή»,
# και ο οδηγός φτιάχνει τα προφίλ για T-Scale, Ishida και ILS με τους κανόνες
# που δουλεύουν ήδη στον ERGON (ίδιες στήλες εξόδου, ίδια διάταξη ILS).
# --------------------------------------------------------------------------
WIZ_MEANINGS = (
    ("", "—  (δεν χρησιμοποιείται)"),
    ("code", "Κωδικός είδους"),
    ("name", "Όνομα / περιγραφή"),
    ("price", "Τιμή"),
    ("barcode", "Barcode"),
    ("vat", "ΦΠΑ"),
    ("category", "Κατηγορία"),
    ("dept", "Τμήμα"),
)
WIZ_MEANING_LABEL = dict(WIZ_MEANINGS)
_WIZ_VAT_VALUES = {"0", "4", "6", "9", "13", "17", "23", "24"}


def wizard_analyze_file(path, enc="auto", max_lines=40):
    """Τι είναι αυτό το αρχείο: κωδικοσελίδα, διαχωριστικό, στήλες, επικεφαλίδα.

    Επιστρέφει dict: enc, delimiter ("" = δεν βρέθηκε → σταθερό πλάτος), lines
    (οι πρώτες γραμμές), ncols (οι συνηθέστερες στήλες), varies (αν αλλάζει ο
    αριθμός στηλών ανά γραμμή — δηλ. το διαχωριστικό εμφανίζεται μέσα σε
    περιγραφές), header (μαντεψιά: η 1η γραμμή είναι ονόματα στηλών).
    """
    with open(path, "rb") as fh:
        raw = fh.read()
    if enc == "auto":
        enc = detect_codepage(raw)
    text = raw.decode(enc, "replace")
    lines = [l for l in text.splitlines() if l.strip()][:max_lines]
    if not lines:
        raise ValueError("Το αρχείο είναι κενό.")

    best, best_score = "", 0
    for d in (",", ";", "\t", "|"):
        counts = [l.count(d) for l in lines]
        if min(counts) == 0:
            continue
        # Προτιμάμε τον διαχωριστή που δίνει τις περισσότερες και σταθερότερες στήλες.
        from collections import Counter
        mode, freq = Counter(counts).most_common(1)[0]
        score = mode * 10 + freq
        if score > best_score:
            best, best_score = d, score
    out = {"enc": enc, "delimiter": best, "lines": lines, "ncols": 0, "varies": False,
           "header": False, "fixed": False, "segments": [], "preset": {}}
    if not best:
        out["fixed"] = True
        out["segments"], out["preset"] = wizard_fixed_segments(lines)
        out["ncols"] = len(out["segments"])
        return out
    from collections import Counter
    counts = [l.count(best) + 1 for l in lines]
    out["ncols"] = Counter(counts).most_common(1)[0][0]
    out["varies"] = len(set(counts)) > 1

    def numeric_cells(line):
        return sum(1 for c in next(csv.reader([line], delimiter=best))
                   if re.match(r"^\s*-?\d+([.,]\d+)?\s*$", c))
    if len(lines) > 1:
        out["header"] = numeric_cells(lines[0]) * 2 < numeric_cells(lines[1])
    return out


# Το κλασικό host της ICS (ERGON κ.ά.): 76 χαρακτήρες — κωδικός, όνομα 40, barcode,
# κατηγορία, τιμή σε λεπτά, μονάδα τιμής, barcode ξανά. Ίδιο με το παλιό make_export.par.
ICS_FIXED_LAYOUT = ((2, 5, "code"), (7, 40, "name"), (47, 7, "barcode"), (60, 4, "category"),
                    (64, 5, "price"), (69, 1, ""), (70, 7, ""))   # κωδικός 2-6, όπως το παλιό make_export.par


def wizard_fixed_segments(lines):
    """Τα «κομμάτια» μιας γραμμής σταθερού πλάτους: [(θέση 1-based, μήκος)], και προ-επιλογές.

    Αν είναι το κλασικό host της ICS (76 χαρακτήρες, κωδικός ψηφία, τιμή ψηφία
    στο 64-68) → η γνωστή διάταξη, με έτοιμες σημασίες. Αλλιώς μαντεψιά: κόβει
    όπου μια στήλη χαρακτήρων είναι κενή σε ΟΛΕΣ τις γραμμές, και όπου αλλάζει
    σταθερά ψηφίο↔γράμμα στην ίδια θέση σε όλες τις γραμμές. Ο τεχνικός διορθώνει
    τις θέσεις στον οδηγό.
    """
    mikos = {len(l) for l in lines}
    if mikos == {76} and all(l[0:6].isdigit() and l[63:68].isdigit() for l in lines[:10]):
        return [(p, n) for p, n, _m in ICS_FIXED_LAYOUT], \
               {i + 1: m for i, (_p, _n, m) in enumerate(ICS_FIXED_LAYOUT) if m}
    w = max(mikos)

    def kind(ch):
        return "s" if ch == " " else ("d" if ch.isdigit() else "a")
    blank = [all(i >= len(l) or l[i] == " " for l in lines) for i in range(w)]
    # αλλαγή κλάσης ψηφίο↔γράμμα σταθερή σε όλες τις γραμμές (όχι μέσα σε ονόματα)
    cut = [False] * (w + 1)
    for i in range(1, w):
        kinds = {(kind(l[i - 1]), kind(l[i])) for l in lines if i < len(l)}
        if kinds and all(a != b and "s" not in (a, b) for a, b in kinds) and len({k[1] for k in kinds}) == 1:
            cut[i] = True
    segs, start = [], None
    for i in range(w + 1):
        b = True if i >= w else blank[i]
        if not b and start is None:
            start = i
        elif (b or cut[i]) and start is not None:
            segs.append((start + 1, i - start))
            start = None if b else i
    return segs or [(1, w)], {}


def wizard_columns(analysis, start_line=1):
    """[(στήλη 1-based, όνομα επικεφαλίδας ή "", [δείγματα])] για κάθε στήλη."""
    lines = analysis["lines"]
    if analysis.get("fixed"):
        body = lines[(1 if analysis.get("header") else 0) + (start_line - 1):]
        cols = []
        for i, (pos, ln) in enumerate(analysis["segments"]):
            samples = [l[pos - 1:pos - 1 + ln].strip() for l in body[:8]]
            cols.append((i + 1, "", samples))
        return cols
    d = analysis["delimiter"]
    header = next(csv.reader([lines[0]], delimiter=d)) if analysis.get("header") and lines else []
    body = lines[(1 if analysis.get("header") else 0) + (start_line - 1):]
    if analysis.get("varies"):
        # Δείγματα μόνο από «κανονικές» γραμμές: όπου το διαχωριστικό μπήκε μέσα
        # σε περιγραφή οι στήλες είναι μετατοπισμένες και θα μπέρδευαν τη μαντεψιά.
        kanonikes = [l for l in body
                     if len(next(csv.reader([l], delimiter=d))) == analysis["ncols"]]
        body = kanonikes or body
    cols = []
    for i in range(analysis["ncols"]):
        samples = []
        for l in body[:8]:
            cells = next(csv.reader([l], delimiter=d))
            if i < len(cells):
                samples.append(cells[i].strip())
        name = header[i].strip() if i < len(header) else ""
        cols.append((i + 1, name, samples))
    return cols


def wizard_guess_meanings(cols):
    """Μαντεύει τι είναι κάθε στήλη από επικεφαλίδα και δείγματα. {στήλη: νόημα}."""
    out = {}
    taken = set()

    def take(i, m):
        if m and m not in taken:
            out[i] = m
            taken.add(m)
            return True
        return False

    # 1. από τα ονόματα της επικεφαλίδας
    rules = (("barcode", ("barcode", "ean")), ("code", ("κωδ", "code", "productnumber", "plu")),
             ("name", ("όνομα", "περιγρ", "name", "desc")), ("price", ("τιμ", "price")),
             ("vat", ("φπα", "vat", "tax")), ("category", ("κατηγ", "categ")),
             ("dept", ("τμήμα", "dept", "depart")))
    for i, name, _s in cols:
        n = name.lower()
        for m, keys in rules:
            if n and any(k in n for k in keys) and take(i, m):
                break
    # 2. από τα δείγματα
    for i, _name, samples in cols:
        if i in out or not samples:
            continue
        vals = [v for v in samples if v]
        if not vals:
            continue
        if all(re.match(r"^\d{8}$|^\d{12,14}$", v) for v in vals):
            take(i, "barcode")
        elif all(re.match(r"^\d+([.,]\d{1,3})?$", v) for v in vals) \
                and any("." in v or "," in v for v in vals):
            take(i, "price")
        elif all(v in _WIZ_VAT_VALUES for v in vals) and len(set(vals)) <= 4 \
                and set(vals) != {"0"} and "code" in taken:
            take(i, "vat")
        elif all(re.match(r"^\d{1,7}$", v) for v in vals) and "code" not in taken:
            take(i, "code")
        elif any(re.search(r"[A-Za-zΑ-Ωα-ωΆ-Ώά-ώ]{3,}", v) for v in vals) and "name" not in taken:
            take(i, "name")
    return out


def wizard_price_mode_guess(samples):
    """'decimal' αν οι τιμές έχουν υποδιαστολή, 'cents' αν είναι ακέραιοι."""
    vals = [v for v in samples if v]
    if vals and all(re.match(r"^\d+$", v) for v in vals):
        return "cents"
    return "decimal"


def wizard_build_profiles(meanings, analysis, price_mode, name_cap=40):
    """Από «στήλη → νόημα» φτιάχνει τα προφίλ (T-Scale, Ishida, ILS).

    Αν ο αριθμός στηλών αλλάζει ανά γραμμή (κόμμα μέσα σε περιγραφές), οι
    στήλες ΜΕΤΑ το όνομα μετρώνται από το τέλος (αρνητικές) — το κόλπο που
    κρατάει σωστή την τιμή στον ERGON.
    """
    by = {m: i for i, m in meanings.items() if m}
    if "code" not in by or "price" not in by:
        raise ValueError("Χρειάζονται τουλάχιστον Κωδικός και Τιμή.")
    ncols = analysis["ncols"]
    name_col = by.get("name", 0)
    fixed = bool(analysis.get("fixed"))

    def col(m):
        i = by.get(m, 0)
        if not i:
            return 0
        if fixed:
            return analysis["segments"][i - 1][0]
        if analysis.get("varies") and name_col and i > name_col:
            return i - (ncols + 1)
        return i

    def src(m):
        """Από πού γεμίζει: θέση (και μήκος στο ERP, για σταθερό πλάτος)."""
        i = by.get(m, 0)
        if fixed and i:
            return {"pos": analysis["segments"][i - 1][0], "inlen": analysis["segments"][i - 1][1]}
        return {"pos": col(m)}

    inp = {
        "step2_input_type": "fixed" if fixed else "delimited",
        "step2_input_delimiter": analysis.get("delimiter") or ",",
        "step2_in_encoding": analysis["enc"],
        "step2_startline": 2 if analysis.get("header") else 1,
        "step2_onebased": True,
        "step2_positions_bytes": False,
    }
    price_tscale = "cents2dot" if price_mode == "cents" else "comma2dot"
    price_cents = "digits" if price_mode == "cents" else "tocents"

    def F(name, pos=0, ln=0, extra="", xform="", align="", ils=None, **kw):
        f = {"name": name, "enabled": True, "pos": pos, "len": ln, "extra": extra,
             "xform": xform, "align": align}
        if ils is not None:
            f["ils"] = ils
        f.update(kw)
        return f

    tscale = {"settings": dict(inp, step2_format="semicolon", step2_delimiter=";",
                               step2_trailing_delim=True, step2_quotes=False,
                               step2_out_encoding="cp1253", step2_final_newline=True,
                               step2_write_header=True, step2_sanitize=True, step2_dedupe=True),
              "fields": [F("ProductNumber", **src("code")),
                         F("ProductName", ln=name_cap, xform="nospace", **src("name")),
                         F("NameSpell", ln=name_cap, xform="nospace", **src("name")),
                         F("Price", **src("price"), xform=price_tscale),
                         F("BarCode", **(src("barcode") if by.get("barcode") else src("code"))),
                         F("Price Unit", extra="0"),
                         F("Abbr", ln=name_cap, xform="nospace", **src("name")),
                         F("AbbrSpell", ln=name_cap, xform="nospace", **src("name"))]}
    if by.get("category"):
        tscale["fields"].append(F("Category", **src("category")))
    if by.get("dept"):
        tscale["fields"].append(F("Department", **src("dept")))
    if by.get("vat"):
        tscale["fields"].append(F("Tax", **src("vat")))

    # Ishida (host2): κωδ, όνομα, κατηγορία, τιμή σε λεπτά, 0, ΦΠΑ — ίδια σειρά
    # με τον ERGON, ώστε η απευθείας αποστολή (κωδ 1, όνομα 2, τιμή -3) να ισχύει.
    ishida = {"settings": dict(inp, step2_format="csv", step2_delimiter=",",
                               step2_trailing_delim=False, step2_quotes=False,
                               step2_out_encoding="cp1253", step2_final_newline=True,
                               step2_write_header=False, step2_sanitize=True, step2_dedupe=False),
              "fields": [F("Κωδικός", **src("code"), xform="digits"),
                         F("Περιγραφή", **src("name"), xform="nocomma"),
                         F("Κατηγορία", **src("category"), extra="" if by.get("category") else "0"),
                         F("Τιμή", **src("price"), xform=price_cents),
                         F("Πεδίο 5", extra="0"),
                         F("ΦΠΑ", **src("vat"), xform="digits", extra="" if by.get("vat") else "0")]}

    # ILS: η επαληθευμένη διάταξη του ERGON (116 χαρακτήρες), με ρόλους για το CFG.
    ils = {"settings": dict(inp, step2_format="fixed", step2_delimiter=",",
                            step2_trailing_delim=False, step2_quotes=False,
                            step2_out_encoding="cp1253", step2_final_newline=True,
                            step2_write_header=False, step2_sanitize=True, step2_dedupe=False),
           "fields": [F("Κωδικός", ln=6, xform="digits", align="zero", ils="Code", **src("code")),
                      F("Όνομα", ln=40, xform="nocomma", ils="PluName", **src("name")),
                      F("(κενό)", 0, 15, ils=""),
                      F("Σταθερό 01", 0, 2, extra="01", ils="Department"),
                      F("Τιμή", ln=5, xform=price_cents, align="zero", ils="UnitPrice", **src("price")),
                      F("Τύπος", 0, 1, extra="0", ils="WeightUnit"),
                      F("ΦΠΑ", ln=2, xform="digits", align="zero", ils="",
                        extra="" if by.get("vat") else "00", **src("vat")),
                      F("Κωδικός ξανά", ln=5, xform="digits", align="zero", ils="LfCode", **src("code")),
                      F("(κενό τέλος)", 0, 40, ils="")]}
    return {"tscale": tscale, "ishida": ishida, "ils": ils}


# --------------------------------------------------------------------------
# ILS: profil apo to AutoTrans.CFG tou pelati
#
# Το ILS διαβάζει αρχείο σταθερού πλάτους και τις θέσεις τις ξέρει από το
# «Field settings» του, που σώζονται στο AutoTrans.CFG (Chk<Πεδίο>=1 ενεργό,
# Cbox<Πεδίο>=θέση 1-based, <Πεδίο>_Len=μήκος). Κάθε εγκατάσταση έχει τη δική
# της — οπότε αντί να γράφει ο τεχνικός θέσεις με το χέρι, διαβάζουμε το CFG
# και φτιάχνουμε το προφίλ. Ονόματα κλειδιών: όπως στο tools/dokimi_ils.py,
# επαληθευμένα με το CFG του πρώτου πελάτη (ERGON).
# --------------------------------------------------------------------------
ILS_CFG_FIELDS = (
    # (όνομα ILS, ενεργό, θέση, μήκος, ετικέτα για τον πίνακα)
    # Όλα τα πεδία του «Field settings» του ScaleAutoTrans (Rongda), με τα ακριβή
    # κλειδιά του AutoTrans.CFG [ImportPluSet]. Θέση = 1-based χαρακτήρας στη
    # γραμμή (με «No delimiter»), ή αριθμός στήλης αν οριστεί διαχωριστικό.
    ("Code", "ChkCode", "CboxCode", "Code_Len", "Κωδικός (Code)"),
    ("LfCode", "ChkLfCode", "CboxLfcode", "lfCode_Len", "LF κωδικός (LFCode) — υποχρεωτικό"),
    ("PluName", "ChkPluName", "CboxPluName", "PluName_Len", "Όνομα (Plu Name) — υποχρεωτικό"),
    ("PluNameExtent", "ChkPluNameExtent", "PluNameExtent", "PluNameExtent_Len",
     "Όνομα, συνέχεια (Plu name extension)"),
    ("UnitPrice", "ChkUnitPrice", "CboxUnitPrice", "UnitPrice_Len", "Τιμή (Unit Price)"),
    ("WeightUnit", "ChkWeightUnit", "CboxWeightPos", "WeightUnit_Len", "Μονάδα βάρους (Unit Weight)"),
    ("PricingMode", "ChkPricingMode", "CboxPricingMode", "PricingMode_Len",
     "Τύπος πώλησης (Pricing type: 0 ζυγιζόμενο, 1 τεμάχια)"),
    ("Department", "ChkDeptMent", "CboxDeptMent", "Department_Len", "Τμήμα (Department)"),
    ("Tare", "ChkTare", "CboxTare", "Tare_Len", "Απόβαρο (PT Weight)"),
    ("BarCode", "chkBarCode", "CboxBarCode", "BarCode_Len", "Τύπος barcode (BarCode Type)"),
    ("HotKey", "ChkHotKey", "CboxHotKey", "HotKey_Len", "Πλήκτρο (HotKey)"),
    ("Shleftime", "ChkShleftime", "CboxShleftime", "Shleftime_Len", "Ημέρες διατήρησης (Shelf Time)"),
    ("RecommendDays", "ChkRecommendDays", "CboxRecommendDays", "RecommendDays_Len",
     "Ημέρες συνιστώμενης κατανάλωσης (Recommend Days)"),
    ("Tolerance", "ChkTolerance", "CboxTolerance", "Tolerance_Len", "Ανοχή (Error)"),
    ("MultiLabel", "ChkMultiLabel", "CboxMultiLabel", "MultiLabel_Len", "Ετικέτα (Label)"),
    ("Discount", "ChkDiscount", "CboxDisCount", "Discount_Len", "Ποσοστό έκπτωσης (Discount Rate)"),
    ("AllowPriceChange", "ChkAllowPriceChange", "CboxAllowPriceChange", "AllowPriceChange_Len",
     "Επιτρέπεται αλλαγή τιμής (0 ναι, 1 όχι)"),
    ("Message1", "ChkMessage1", "CboxMessage1", "Message1_Len", "Μήνυμα 1 (Message1)"),
    ("UpdateFlag", "ChkUpdateFlag", "CboxUpdateFlag", "UpdateFlag_Len",
     "Σημαία ενημέρωσης (Update flag: 0 διαγραφή, 1 ενημέρωση)"),
)
# Επιλογές του Field settings που ΔΕΝ είναι πεδία — τις γράφουμε κι αυτές στο CFG.
ILS_CFG_OPTIONS = {
    "CboxPluSep": "Διαχωριστικό: 0 κόμμα, 1 TAB, 2 ερωτηματικό, 3 κενό, 4 κανένα (σταθερό πλάτος)",
    "ChkIsHead": "Η 1η γραμμή είναι επικεφαλίδες",
    "ChkDiv10": "Πολλαπλασίασε την τιμή ×10 στην εισαγωγή",
    "ChkDiv100": "Πολλαπλασίασε την τιμή ×100 (αρχείο με 5.40 → 540)",
    "ChkDiv1000": "Πολλαπλασίασε την τιμή ×1000",
    "ChkFixWeightUnit": "Σταθερή μονάδα βάρους για όλα",
    "CboxFixWeightUnit": "Η σταθερή μονάδα",
    "Bartype_Weight": "Τύπος barcode ζυγιζόμενων (π.χ. 101)",
    "Bartype_PCS": "Τύπος barcode τεμαχιακών (π.χ. 102)",
}
ILS_SEP_INDEX = {",": 0, "\t": 1, ";": 2, " ": 3, "": 4}
# Πλήρες AutoTrans.CFG όπως το γράφει το ίδιο το ScaleAutoTrans (δομή και σειρά
# κλειδιών από πραγματική εγκατάσταση). Δεν υπάρχει «πρότυπο» από τον κατασκευαστή:
# το φτιάχνουμε εμείς, και τα πεδία/επιλογές γράφονται πάνω σε αυτό.
ILS_CFG_TEMPLATE = """[Language]
Code=CHINESE
Area=CHINA
lngstr=_en
[AutoTranSet]
FontSize=9
FontName=Arial
FontCharset=1
IsAutoUpdate=1
[ImportPluSet]
ChkHotKey=0
ChkPluName=1
ChkLfCode=1
ChkCode=1
chkBarCode=0
ChkUnitPrice=1
ChkDeptMent=0
ChkTare=0
ChkShleftime=0
ChkWeightUnit=0
CboxHotKey=1
CboxPluName=7
CboxLfcode=2
CboxCode=2
CboxBarCode=5
CboxUnitPrice=64
CboxDeptMent=11
CboxTare=10
CboxShleftime=11
ChkDiv100=0
ChkTolerance=0
CboxTolerance=16
CboxPluSep=4
ChkDiv1000=0
CboxWeightPos=69
ChkFixWeightUnit=0
CboxFixWeightUnit=0
ChkRecommendDays=0
CboxRecommendDays=22
ChkDiscount=0
CboxDisCount=18
ChkAllowPriceChange=0
CboxAllowPriceChange=15
ChkMessage1=0
CboxMessage1=16
ChkMultiLabel=0
CboxMultiLabel=17
ChkPricingMode=0
CboxPricingMode=9
Bartype_Weight=101
Bartype_PCS=102
ChkPluNameExtent=0
PluNameExtent=2
ChkIsHead=0
ChkDiv10=0
ChkUpdateFlag=0
CboxUpdateFlag=1
HotKey_Len=3
PluName_Len=30
lfCode_Len=5
Code_Len=5
BarCode_Len=2
UnitPrice_Len=5
Department_Len=2
Tare_Len=5
Shleftime_Len=3
WeightUnit_Len=1
RecommendDays_Len=3
AllowPriceChange_Len=1
Discount_Len=2
Message1_Len=4
Tolerance_Len=2
MultiLabel_Len=3
PricingMode_Len=1
PluNameExtent_Len=1
UpdateFlag_Len=1
[WeightIDSet]
0=10
1=4
2=2
3=3
4=0
5=5
6=6
7=7
8=8
9=9
10=1
11=11
12=12
"""


def parse_autotrans_cfg(path):
    """Τα ενεργά πεδία του ILS από το AutoTrans.CFG: [(όνομα, θέση, μήκος, ετικέτα)].

    Ταξινομημένα κατά θέση. Πεδία που δεν ξέρουμε (άλλο Chk…=1 με θέση και
    μήκος) μπαίνουν κι αυτά, με το όνομα του CFG, ώστε να μη χαθεί τίποτα.
    """
    with open(path, "rb") as fh:
        raw = fh.read()
    text = raw.decode("cp1253", "replace")
    val = {}
    for key, v in re.findall(r"^\s*([A-Za-z0-9_]+)\s*=\s*(.*?)\s*$", text, re.M):
        val[key.lower()] = v
    if not val:
        raise ValueError("Το αρχείο δεν έχει γραμμές τύπου ΚΛΕΙΔΙ=ΤΙΜΗ — είναι όντως το AutoTrans.CFG;")

    def num(key):
        try:
            return int(str(val.get(key.lower(), "")).strip())
        except ValueError:
            return None

    out, seen = [], set()
    for name, chk, cbox, ln, label in ILS_CFG_FIELDS:
        seen.update((chk.lower(), cbox.lower(), ln.lower()))
        if str(val.get(chk.lower(), "0")).strip() != "1":
            continue
        pos, length = num(cbox), num(ln)
        if pos is None or length is None or pos < 1 or length < 1:
            continue
        out.append((name, pos, length, label))

    # Άγνωστα ενεργά πεδία: Chk<X>=1 και υπάρχει θέση (Cbox<X> ή <X>) και μήκος (<X>_Len).
    for key in list(val):
        if not key.startswith("chk") or key in seen or str(val[key]).strip() != "1":
            continue
        x = key[3:]
        pos = num("cbox" + x) if ("cbox" + x) in val else num(x)
        length = num(x + "_len")
        if pos is None or length is None or pos < 1 or length < 1:
            continue
        out.append((x, pos, length, x))

    if not out:
        raise ValueError("Δεν βρέθηκε κανένα ενεργό πεδίο (π.χ. ChkCode=1, CboxCode=…, Code_Len=…).")
    out.sort(key=lambda t: t[1])
    return out


# Ρόλοι πεδίων του ILS — κλειδί «ils» σε κάθε πεδίο προφίλ. Από αυτούς βγαίνει το
# Field settings (AutoTrans.CFG) ώστε ο ζυγός να διαβάσει το αρχείο που φτιάχνουμε.
ILS_ROLES = (("", "— (το ILS δεν το διαβάζει)"),) + tuple(
    (name, label) for name, _chk, _cbox, _ln, label in ILS_CFG_FIELDS)
ILS_ROLE_LABEL = dict(ILS_ROLES)
# Το Plu Name του ILS χωράει 30 χαρακτήρες· ό,τι περισσεύει πάει στο Plu name extens
# (ERGON: 7-36 + 37-46). Επαληθευμένο με το αρχείο που δέχεται ο ζυγός του πελάτη.
ILS_PLUNAME_MAX = 30


def guess_ils_role(name, taken):
    """Μαντεύει τον ρόλο ILS ενός πεδίου από το όνομά του (για παλιά προφίλ χωρίς «ils»)."""
    n = str(name or "").lower()
    rules = (
        (("τιμ", "price", "unitprice"), "UnitPrice"),
        (("όνομα", "περιγρ", "name", "desc", "plu"), "PluName"),
        (("σημαία", "update", "flag"), "UpdateFlag"),
        (("τύπος πώλησης", "pricing", "τεμαχ"), "PricingMode"),
        (("τμήμα", "dept", "depart", "σταθερό 01"), "Department"),
        (("απόβαρο", "tare"), "Tare"),
        (("μονάδα", "weight", "ζυγιζ", "τύπος"), "WeightUnit"),
        (("έκπτωσ", "discount"), "Discount"),
        (("μήνυμα", "message"), "Message1"),
        (("ετικέτ", "label"), "MultiLabel"),
        (("ημέρες", "shelf", "διατήρ"), "Shleftime"),
        (("πλήκτρο", "hotkey"), "HotKey"),
        (("barcode",), "BarCode"),
        (("lf",), "LfCode"),
        (("κωδ", "code", "productnumber"), "Code"),
    )
    for keys, role in rules:
        if any(k in n for k in keys):
            if role == "Code" and "Code" in taken:
                return "" if "LfCode" in taken else "LfCode"   # «κωδικός ξανά»
            if role == "PluName" and "PluName" in taken:
                return "" if "PluNameExtent" in taken else "PluNameExtent"
            return "" if role in taken else role
    return ""


def ils_field_settings(fields):
    """Από το προφίλ (σταθερό πλάτος) → τι πρέπει να λέει το Field settings του ILS.

    Επιστρέφει ([(ρόλος, ενεργό, θέση 1-based, μήκος)] για ΟΛΟΥΣ τους ρόλους,
    προειδοποιήσεις). Οι θέσεις βγαίνουν από τη σειρά και τα μήκη των ενεργών
    πεδίων — ακριβώς όπως θα γραφτεί το αρχείο. Όνομα μεγαλύτερο από
    ILS_PLUNAME_MAX μοιράζεται μόνο του σε Plu Name + Plu name extens.
    """
    active = [f for f in fields if f.get("enabled")]
    taken = {f.get("ils") for f in active if f.get("ils")}
    found = {}
    warnings = []
    cursor = 1
    for f in active:
        ln = int(f.get("len") or 0)
        role = f.get("ils")
        if role is None:                            # παλιό προφίλ: μάντεψε
            role = guess_ils_role(f.get("name"), taken)
            if role:
                taken.add(role)
        if role in found:
            warnings.append("Δύο πεδία με ρόλο «%s» — το ILS διαβάζει ένα· κρατώ το πρώτο (%s)."
                            % (ILS_ROLE_LABEL.get(role, role), found[role][2]))
            role = ""
        if role == "PluName" and ln > ILS_PLUNAME_MAX and "PluNameExtent" not in taken:
            found["PluName"] = (cursor, ILS_PLUNAME_MAX, f["name"])
            found["PluNameExtent"] = (cursor + ILS_PLUNAME_MAX, ln - ILS_PLUNAME_MAX, f["name"])
        elif role:
            found[role] = (cursor, ln, f["name"])
        elif ln and (int(f.get("pos") or 0) or str(f.get("extra", "")).strip()):
            warnings.append("Το πεδίο «%s» (θέσεις %d-%d) δεν έχει ρόλο ILS — ο ζυγός θα το "
                            "αγνοήσει. Αν πρέπει να το διαβάζει, όρισε «Πεδίο ILS» στον πίνακα."
                            % (f["name"], cursor, cursor + ln - 1))
        cursor += ln
    for must in ("Code", "LfCode", "PluName", "UnitPrice"):
        if must not in found:
            warnings.append("Λείπει πεδίο με ρόλο «%s» — το ILS το απαιτεί (στο Field settings έχει "
                            "αστερίσκο)." % ILS_ROLE_LABEL[must])
    if "PluName" in found and found["PluName"][1] + found.get("PluNameExtent", (0, 0, ""))[1] > 36:
        warnings.append("Όνομα + συνέχεια = %d χαρακτήρες· το ILS γράφει «Plu name + extension <= 36»."
                        % (found["PluName"][1] + found.get("PluNameExtent", (0, 0, ""))[1]))
    out = []
    for role, _label in ILS_ROLES[1:]:
        if role in found:
            pos, ln, _src = found[role]
            out.append((role, True, pos, ln))
        else:
            out.append((role, False, 0, 0))
    return out, warnings


def ils_cfg_values(settings):
    """Τα κλειδιά του AutoTrans.CFG (Chk…, Cbox…, …_Len) με τις τιμές τους, με τη σειρά."""
    keys = {name: (chk, cbox, ln) for name, chk, cbox, ln, _lbl in ILS_CFG_FIELDS}
    out = []
    for role, on, pos, ln in settings:
        chk, cbox, lenkey = keys[role]
        out.append((chk, "1" if on else "0"))
        if on:
            out.append((cbox, str(pos)))
            out.append((lenkey, str(ln)))
    return out


def ils_cfg_options(profile_settings, fields):
    """Οι επιλογές του Field settings για το αρχείο που φτιάχνουμε.

    Σταθερό πλάτος → «No delimiter» (4). Επικεφαλίδα κατά το προφίλ. Η τιμή στο
    δικό μας αρχείο είναι ήδη σε λεπτά (tocents/digits) → κανένας πολλαπλασιασμός·
    αν το προφίλ γράφει τιμή με υποδιαστολή, ×100.
    """
    fmt = profile_settings.get("step2_format", "fixed")
    sep = "" if fmt == "fixed" else {"csv": ",", "tab": "\t", "semicolon": ";"}.get(
        fmt, profile_settings.get("step2_delimiter", ","))
    price = next((f for f in fields if f.get("enabled") and f.get("ils") == "UnitPrice"), None)
    decimal = bool(price and price.get("xform") in ("comma2dot", "dot2comma", "dec2dot", "dec2comma",
                                                     "cents2dot", "cents2comma"))
    return [("CboxPluSep", str(ILS_SEP_INDEX.get(sep, 4))),
            ("ChkIsHead", "1" if profile_settings.get("step2_write_header") else "0"),
            ("ChkDiv10", "0"), ("ChkDiv100", "1" if decimal else "0"), ("ChkDiv1000", "0")]


def write_autotrans_cfg(settings, out_path, existing=None, options=None):
    """Γράφει τα Field settings στο AutoTrans.CFG.

    Με «existing»: ΕΝΗΜΕΡΩΝΕΙ το αρχείο του πελάτη — αλλάζει μόνο τα κλειδιά των
    πεδίων, αφήνει όλα τα άλλα (IP, φάκελοι, ό,τι έχει) όπως είναι, κρατά γραμμή
    προς γραμμή τη μορφή, και πρώτα κρατά αντίγραφο .bak με ημερομηνία.
    Χωρίς existing: νέο αρχείο μόνο με τα κλειδιά των πεδίων.
    Επιστρέφει (αντίγραφο ή "", [αλλαγές], [προστέθηκαν]).
    """
    values = ils_cfg_values(settings) + list(options or [])
    wanted = {k.lower(): (k, v) for k, v in values}
    changed, added = [], []
    if True:
        if existing:
            with open(existing, "rb") as fh:
                raw = fh.read()
        else:
            raw = ILS_CFG_TEMPLATE.replace("\n", "\r\n").encode("cp1253")
        nl = b"\r\n" if b"\r\n" in raw else b"\n"
        text = raw.decode("cp1253", "replace")
        lines = text.split(nl.decode())
        seen = set()
        for i, line in enumerate(lines):
            m = re.match(r"^(\s*)([A-Za-z0-9_]+)(\s*=\s*)(.*?)(\s*)$", line)
            if not m:
                continue
            key = m.group(2).lower()
            if key not in wanted:
                continue
            seen.add(key)
            real_key, new_val = wanted[key]
            if m.group(4) != new_val:
                changed.append("%s: %s → %s" % (m.group(2), m.group(4) or "(κενό)", new_val))
                lines[i] = "%s%s%s%s%s" % (m.group(1), m.group(2), m.group(3), new_val, m.group(5))
        missing = [(k, v) for k, v in values if k.lower() not in seen]
        if missing:
            # Μετά την τελευταία γραμμή πεδίων που βρέθηκε, ώστε να μείνουν μαζί.
            idx = max((i for i, l in enumerate(lines)
                       if re.match(r"^\s*([A-Za-z0-9_]+)\s*=", l)
                       and re.match(r"^\s*([A-Za-z0-9_]+)\s*=", l).group(1).lower() in wanted),
                      default=len(lines) - 1)
            for k, v in reversed(missing):
                lines.insert(idx + 1, "%s=%s" % (k, v))
            added = ["%s=%s" % (k, v) for k, v in missing]
        if existing:
            backup = "%s.bak-%s" % (existing, datetime.datetime.now().strftime("%Y%m%d-%H%M%S"))
            shutil.copyfile(existing, backup)
        else:
            backup = ""
            changed = []                      # νέο αρχείο: δεν έχει νόημα «τι άλλαξε»
        data = nl.decode().join(lines).encode("cp1253", "replace")
    with open(out_path, "wb") as fh:
        fh.write(data)
    return backup, changed, added


def describe_ils_settings(settings):
    """Ο πίνακας όπως τον βλέπει ο τεχνικός στο «Field settings» του ILS."""
    lines = ["%-34s %-7s %-6s %s" % ("ΠΕΔΙΟ ILS", "ΕΝΕΡΓΟ", "ΘΕΣΗ", "ΜΗΚΟΣ")]
    for role, on, pos, ln in settings:
        lines.append("%-34s %-7s %-6s %s" % (ILS_ROLE_LABEL[role], "✓" if on else "—",
                                             pos if on else "", ln if on else ""))
    return lines


def _guess_erp_column(erp_fields, keywords):
    """Η στήλη του ERP για ένα νόημα (κωδικός, όνομα, τιμή…), από τον κύριο πίνακα.

    Ψάχνει τα ονόματα των πεδίων του τρέχοντος προφίλ με τη σειρά των λέξεων-
    κλειδιών, ώστε «ProductNumber» να προηγείται του «BarCode» στον κωδικό.
    """
    for kw in keywords:
        for f in erp_fields or []:
            name = str(f.get("name", "")).lower()
            try:
                pos = int(f.get("pos") or 0)
            except (TypeError, ValueError):
                pos = 0
            if kw in name and pos != 0:
                return pos
    return 0


def ils_profile_from_cfg(ils_fields, erp_fields, cfg):
    """Φτιάχνει προφίλ (fields, settings, προειδοποιήσεις) για αρχείο ILS.

    Οι θέσεις/μήκη έρχονται από το CFG· το ΑΠΟ ΠΟΥ (στήλη του ERP) μαντεύεται από
    τον κύριο πίνακα, και ο τεχνικός το διορθώνει στον πίνακα αν χρειαστεί.
    Κενά ανάμεσα στα πεδία γίνονται κενές στήλες, ώστε κάθε πεδίο να κάτσει
    ακριβώς στη θέση που περιμένει ο ζυγός.
    """
    src = {
        "code": _guess_erp_column(erp_fields, ("productnumber", "κωδ", "code", "plu")),
        "name": _guess_erp_column(erp_fields, ("productname", "όνομα", "περιγρ", "name", "desc")),
        "price": _guess_erp_column(erp_fields, ("τιμ", "price")),
    }
    warnings = []
    fields = []
    cursor = 1
    name_len_so_far = 0
    items = list(ils_fields)
    i = 0
    while i < len(items):
        name, pos, ln, label = items[i]
        if pos > cursor:
            fields.append({"name": "(κενό)", "enabled": True, "pos": 0, "len": pos - cursor,
                           "extra": "", "xform": "", "align": "", "ils": ""})
        elif pos + ln <= cursor:
            # Δύο πεδία του ILS στις ίδιες θέσεις (π.χ. Code και LFCode και τα δύο στη
            # θέση 2): το αρχείο έχει ΜΙΑ τιμή εκεί και το ILS τη διαβάζει δύο φορές.
            # Στο προφίλ μας δεν γράφεται δεύτερη — θα μετατόπιζε τα επόμενα.
            warnings.append("Το «%s» (θέσεις %d-%d) διαβάζει τις ίδιες θέσεις με προηγούμενο πεδίο· "
                            "γράφεται μία φορά." % (label, pos, pos + ln - 1))
            i += 1
            continue
        elif pos < cursor:
            warnings.append("ΠΡΟΣΟΧΗ: το «%s» (θέση %d) πέφτει μερικώς πάνω στο προηγούμενο πεδίο — "
                            "έλεγξε το CFG." % (label, pos))
        f = {"name": label, "enabled": True, "pos": 0, "len": ln, "extra": "", "xform": "",
             "align": "", "ils": name if name in ILS_ROLE_LABEL else ""}
        if name in ("Code", "LfCode"):
            f.update(pos=src["code"], xform="digits", align="zero")
        elif name == "PluName":
            f.update(pos=src["name"], xform="nocomma")
            # Αν η συνέχεια του ονόματος ακολουθεί αμέσως, γίνονται ένα πεδίο — όπως
            # στο επαληθευμένο αρχείο του ERGON (7-46 = 30 + 10).
            if i + 1 < len(items) and items[i + 1][0] == "PluNameExtent" \
                    and items[i + 1][1] == pos + ln:
                f["len"] = ln + items[i + 1][2]
                f["name"] = "Όνομα (%d+%d)" % (ln, items[i + 1][2])
                i += 1
            name_len_so_far = ln
        elif name == "PluNameExtent":
            f.update(pos=src["name"], xform="nocomma", skip=name_len_so_far)
        elif name == "UnitPrice":
            f.update(pos=src["price"], xform="tocents", align="zero")
        elif name == "Department":
            f.update(extra="01", align="zero")
        elif name == "Tare":
            f.update(extra="0", align="zero")
        elif name == "WeightUnit":
            f.update(extra="0")
        elif name == "PricingMode":
            f.update(extra="0")                   # 0 = ζυγιζόμενο, 1 = τεμάχια
        elif name == "UpdateFlag":
            f.update(extra="1")                   # 1 = ενημέρωση, 0 = διαγραφή
        elif name in ("BarCode", "HotKey", "Shleftime", "RecommendDays", "Tolerance", "MultiLabel",
                      "Discount", "AllowPriceChange", "Message1"):
            f.update(extra="0", align="zero")      # ουδέτερη τιμή· ο τεχνικός αλλάζει αν θέλει
        else:
            warnings.append("Το πεδίο «%s» δεν το ξέρω — βγαίνει κενό· όρισέ του στήλη ή "
                            "σταθερή τιμή στον πίνακα." % label)
        if name in ("Code", "LfCode", "PluName", "PluNameExtent", "UnitPrice") and not f["pos"]:
            warnings.append("Δεν βρήκα από ποια στήλη του ERP να πάρω το «%s» — όρισέ τη "
                            "στον πίνακα." % label)
        fields.append(f)
        cursor = pos + int(f["len"])          # μετά από συγχώνευση το μήκος μεγάλωσε
        i += 1

    settings = {
        # πώς ΔΙΑΒΑΖΕΤΑΙ το ERP: ίδια με τον κύριο πίνακα
        "step2_input_type": cfg.get("step2_input_type", "fixed"),
        "step2_input_delimiter": cfg.get("step2_input_delimiter", ","),
        "step2_in_encoding": cfg.get("step2_in_encoding", "auto"),
        "step2_startline": cfg.get("step2_startline", 1),
        "step2_onebased": cfg.get("step2_onebased", True),
        "step2_positions_bytes": cfg.get("step2_positions_bytes", False),
        # πώς ΓΡΑΦΕΤΑΙ το αρχείο του ILS: σταθερό πλάτος, χωρίς επικεφαλίδα
        "step2_format": "fixed",
        "step2_delimiter": ",",
        "step2_trailing_delim": False,
        "step2_quotes": False,
        "step2_out_encoding": "cp1253",
        "step2_final_newline": True,
        "step2_write_header": False,
        "step2_sanitize": True,
        "step2_dedupe": False,
    }
    return fields, settings, warnings


def describe_ils_profile(fields):
    """Πίνακας για τον τεχνικό: θέση, μήκος, πεδίο, από πού γεμίζει."""
    lines = ["%-9s %-5s %-20s %s" % ("ΘΕΣΕΙΣ", "ΜΗΚΟΣ", "ΠΕΔΙΟ", "ΓΕΜΙΖΕΙ ΑΠΟ")]
    cursor = 1
    for f in fields:
        ln = int(f.get("len") or 0)
        pos = int(f.get("pos") or 0)
        if pos:
            how = "στήλη %d του ERP" % pos
            if f.get("skip"):
                how += " (από τον %dο χαρακτήρα)" % (int(f["skip"]) + 1)
            if f.get("xform"):
                how += " · " + XFORMS.get(f["xform"], f["xform"])
        elif str(f.get("extra", "")).strip():
            how = "σταθερό «%s»" % f["extra"]
        else:
            how = "κενά"
        if f.get("align") == "zero":
            how += " · μηδενικά μπροστά"
        lines.append("%3d-%-5d %-5d %-20s %s" % (cursor, cursor + ln - 1, ln, f["name"], how))
        cursor += ln
    lines.append("")
    lines.append("Μήκος γραμμής: %d χαρακτήρες" % (cursor - 1))
    return lines


def build_extra_output(cfg, fallback_input, log, key="step2b",
                       default_name="host2", label="δεύτερο αρχείο"):
    """Φτιάχνει ακόμα ένα αρχείο με άλλο προφίλ, από τα ίδια δεδομένα.

    Κάθε μάρκα ζυγού θέλει τη δική της γραφή: οι Ishida την τιμή σε λεπτά, το
    ILS τις στήλες στη σειρά που περιμένει το «Field settings» του. Όλα βγαίνουν
    στην ίδια εκτέλεση, από το ίδιο αρχείο του ERP.
    """
    name = (cfg.get("%s_profile" % key) or "").strip()
    name, entry = resolve_profile(cfg.get("profiles") or {}, name)
    if not entry:
        raise StepError("Βήμα 3β", "Δεν βρέθηκε το προφίλ «%s» για το %s." % (name, label),
                        "Διάλεξε προφίλ στην καρτέλα «Βήμα 3».")
    fields = entry.get("fields", entry) if isinstance(entry, dict) else entry
    settings = entry.get("settings", {}) if isinstance(entry, dict) else {}

    dst = (cfg.get("%s_output" % key) or "").strip()
    if not dst:
        fmt = settings.get("step2_format", cfg.get("step2_format", "csv"))
        ext = ".csv" if fmt in ("csv", "semicolon") else ".txt"
        folder = cfg.get("output_dir") or os.path.dirname(cfg.get("watch_file", "") or "")
        dst = os.path.join(folder, default_name + ext)

    sub = dict(cfg)
    sub.update(settings)
    sub["step2_fields"] = fields
    sub["step2_input"] = (cfg.get("step2_input") or "").strip()
    sub["step2_output"] = dst
    log("  %s με προφίλ «%s»:" % (label, name))
    return run_step2(sub, fallback_input, log)


def build_second_output(cfg, fallback_input, log):
    """Το αρχείο για τους Ishida (host2)."""
    return build_extra_output(cfg, fallback_input, log, "step2b", "host2",
                              "δεύτερο αρχείο")


def build_ils_output(cfg, fallback_input, log):
    """Το αρχείο για το ILS (hostILS)."""
    return build_extra_output(cfg, fallback_input, log, "step2c", "hostILS",
                              "αρχείο ILS")


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
            val = apply_xform(apply_skip(rawv, f), f.get("xform", ""))
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
            pos, ln = int(f.get("pos") or 0) - off, int(f.get("inlen") or f.get("len") or 0)
            rawv = sample[pos:pos + ln] if ln > 0 and pos >= 0 else ""
            val = apply_xform(apply_skip(rawv.strip(), f), f.get("xform", ""))
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
        if cfg.get("direct_send"):
            add("  ΤΡΟΠΟΣ: στέλνουμε εμείς, χωρίς το πρόγραμμα του κατασκευαστή")
            add("  POST http://<IP>:%d/products   Content-Type: application/json" % SCALE_PORT)
            src = (cfg.get("step2_output") or "").strip()
            if os.path.isfile(src):
                try:
                    items = build_products_json(src, cfg, lambda m: None)
                    add("  θα σταλούν %d προϊόντα από %s" % (len(items), os.path.basename(src)))
                    if items:
                        sample = {k: v for k, v in items[0].items() if v not in ("", None)}
                        add("  δείγμα 1ου: %s" % json.dumps(sample, ensure_ascii=False)[:220])
                except StepError as exc:
                    add("  ΠΡΟΣΟΧΗ: %s" % exc.message)
            else:
                add("  ΠΡΟΣΟΧΗ: δεν βρέθηκε το αρχείο προϊόντων (%s)" % (src or "—"))
        exe = cfg.get("step3_exe", "")
        add("  εφαρμογή ζυγού: %s" % exe)
        add("  υπάρχει: %s | διάρκεια: %s δευτ.%s"
            % (os.path.isfile(exe), cfg.get("step3_seconds"),
               "   (δεν θα χρησιμοποιηθεί)" if cfg.get("direct_send") else ""))
        wanted = parse_ips(cfg.get("scale_ips", ""))
        current = read_ips(exe)
        add("  IP ζυγών (ρύθμιση): %s" % (", ".join(wanted) or "—"))
        add("  IP ζυγών (ip.xml):  %s%s" % (", ".join(current) or "—",
            "" if not wanted or current == wanted else "  → θα ενημερωθεί πριν την αποστολή"))

        for key, label in EXTRA_SENDERS:
            if key == "ishida" and cfg.get("ishida_on"):
                ish = parse_ips(cfg.get("ishida_ips", ""))
                add("  %-8s: στέλνουμε εμείς  [αλλάζουν μόνο οι τιμές]" % label)
                add("            IP ζυγών: %s" % (", ".join(ish) or "—  ΠΡΟΣΟΧΗ: κανένα"))
                for ip in ish:
                    ok, giati = ishida_reachable(ip)
                    add("            %s: %s" % (ip, "απαντά" if ok else "ΔΕΝ απαντά — %s" % giati))
                continue
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

    # Δεύτερο αρχείο για άλλου τύπου ζυγό (π.χ. Ishida): ίδια δεδομένα, άλλη
    # μορφή, στην ίδια εκτέλεση — όχι δεύτερο πέρασμα.
    if cfg.get("step2b_enabled"):
        produced.append(build_second_output(cfg, current, log))
        log("Βήμα 3β: δεύτερο αρχείο. OK")

    if cfg.get("step2c_enabled"):
        produced.append(build_ils_output(cfg, current, log))
        log("Βήμα 3γ: αρχείο ILS. OK")

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
    def report_callback_exception(self, exc, val, tb):
        """Πιάνει κάθε σφάλμα του παραθύρου, αντί να κλείσει σιωπηλά.

        Χωρίς αυτό, ένα σφάλμα μέσα σε κουμπί ή τικ έβγαινε μόνο στην κονσόλα —
        που στα Windows δεν υπάρχει — και το πρόγραμμα φαινόταν να «κρασάρει»
        χωρίς να αφήνει ίχνος. Τώρα γράφεται ολόκληρο στο log.
        """
        detail = "".join(traceback.format_exception(exc, val, tb))
        try:
            write_log("ΣΦΑΛΜΑ ΠΑΡΑΘΥΡΟΥ:\n" + detail)
        except Exception:
            pass
        try:
            self.log("Σφάλμα: %s (γράφτηκε ολόκληρο στο log)" % val)
        except Exception:
            pass
        try:
            self.show_error_bar("Κάτι πήγε στραβά, αλλά το πρόγραμμα συνεχίζει: %s" % val)
        except Exception:
            pass

    def __init__(self):
        enable_high_dpi()
        super().__init__()
        self.title(APP_NAME)
        try:                                    # καθαρά γράμματα και σωστό scaling στα Windows
            dpi = self.winfo_fpixels('1i')
            if dpi > 0:
                self.tk.call('tk', 'scaling', max(1.3333, dpi / 72.0))
        except Exception:
            pass
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        w = min(1200, max(980, sw - 60))
        h = min(920, max(720, sh - 80))                  # σύγχρονες διαστάσεις με άνεση
        self.geometry("%dx%d+%d+%d" % (w, h, max(0, (sw - w) // 2), max(0, (sh - h) // 3)))
        self.minsize(920, 580)
        self._first_run = not os.path.exists(CONFIG_PATH) and not any(
            os.path.exists(p) for p in LEGACY_CONFIGS)
        self.cfg = load_config()
        if self._first_run:
            # Νέα εγκατάσταση: ξεκινά ήδη φορτωμένο το πρώτο (προεπιλεγμένο) προφίλ,
            # χωρίς να χρειαστεί να πατηθεί «Φόρτωση».
            profiles = self.cfg.get("profiles", {})
            default_name = next(iter(profiles), None)
            if default_name:
                entry = profiles[default_name]
                fields = entry.get("fields", entry) if isinstance(entry, dict) else entry
                self.cfg["step2_fields"] = [dict(fld) for fld in fields]
                settings = entry.get("settings", {}) if isinstance(entry, dict) else {}
                self.cfg.update(settings)
        self.worker = None
        self.stop_event = threading.Event()
        self.watch_thread = None
        self.watching = False
        self.last_stamp = None
        self.last_run = None          # (πότε, πέτυχε;, μήνυμα) — για τη Σύνοψη

        self.tray = None
        self.pending_error = None
        self._build()
        self._load_into_widgets()
        if self._first_run:
            # Νέα εγκατάσταση: ξεκινά με τα Windows χωρίς να χρειαστεί κλικ.
            try:
                set_autostart(True)
            except Exception:
                pass
            self.v_boot.set(True)
        self.protocol("WM_DELETE_WINDOW", self.on_close)

    # ---------------- εμφάνιση ----------------
    def _apply_theme(self):
        C = COLORS
        F = FONTS
        st = ttk.Style(self)
        try:
            st.theme_use("clam")
        except tk.TclError:
            pass
        self.configure(bg=C["bg"])

        st.configure(".", background=C["card"], foreground=C["ink"], font=F["base"],
                     bordercolor=C["line"], focuscolor=C["brand"])
        st.configure("TFrame", background=C["card"])
        st.configure("Bar.TFrame", background=C["bg"])
        st.configure("Card.TFrame", background=C["card"], relief="flat")
        st.configure("Header.TFrame", background=C["card"])
        st.configure("Badge.TFrame", background=C["card_subtle"], relief="flat")
        st.configure("TLabel", background=C["card"], foreground=C["ink"], font=F["base"])
        st.configure("OnCard.TLabel", background=C["card"])
        st.configure("Title.TLabel", background=C["card"], foreground=C["ink"],
                     font=F["app_title"])
        st.configure("Vendor.TLabel", background=C["card"], foreground=C["brand"],
                     font=F["vendor"])
        st.configure("Version.TLabel", background=C["card"], foreground=C["muted"],
                     font=F["version"])
        st.configure("Hint.TLabel", background=C["card"], foreground=C["muted"],
                     font=F["sm"])
        st.configure("Pill.TLabel", background=C["card_subtle"], foreground=C["muted"],
                     font=F["sm_bold"], padding=(10, 4))

        st.configure("TCheckbutton", background=C["card"], foreground=C["ink"], font=F["base"],
                     focuscolor=C["card"], padding=3)
        st.map("TCheckbutton", background=[("active", C["card"])],
               indicatorcolor=[("selected", C["brand"]), ("!selected", C["card"])])
        st.configure("Big.TCheckbutton", font=F["base_bold"], foreground=C["brand_d"], padding=4)
        st.map("Big.TCheckbutton", background=[("active", C["card"])],
               indicatorcolor=[("selected", C["brand"]), ("!selected", C["card"])])

        st.configure("TRadiobutton", background=C["card"], foreground=C["ink"], font=F["base"],
                     focuscolor=C["card"], padding=3)
        st.map("TRadiobutton", background=[("active", C["card"])],
               indicatorcolor=[("selected", C["brand"]), ("!selected", C["card"])])

        st.configure("TEntry", fieldbackground=C["card"], background=C["card"],
                     foreground=C["ink"], bordercolor=C["line"], insertcolor=C["ink"],
                     font=F["base"], padding=6, relief="flat")
        st.map("TEntry", bordercolor=[("focus", C["brand"])])

        st.configure("TCombobox", fieldbackground=C["card"], background=C["card"],
                     foreground=C["ink"], font=F["base"], padding=5)

        st.configure("TButton", background=C["card"], foreground=C["ink"], font=F["btn"],
                     bordercolor=C["line"], borderwidth=1, relief="flat", padding=(14, 7))
        st.map("TButton", background=[("active", "#f1f5f9"), ("pressed", "#e2e8f0")],
               bordercolor=[("active", C["brand"])])
        st.configure("Accent.TButton", background=C["brand"], foreground="#ffffff",
                     font=F["btn_accent"], borderwidth=0, padding=(18, 9))
        st.map("Accent.TButton", background=[("active", C["brand_d"]), ("pressed", "#075985")])
        st.configure("Ghost.TButton", background=C["bg"], foreground=C["muted"],
                     font=F["btn"], borderwidth=0, padding=(12, 7))
        st.map("Ghost.TButton", background=[("active", "#e2e8f0")], foreground=[("active", C["ink"])])
        st.configure("Pick.TButton", font=F["btn"], padding=(10, 5))

        st.configure("TNotebook", background=C["bg"], borderwidth=0, tabmargins=(8, 8, 8, 0))
        st.configure("TNotebook.Tab", background=C["line_subtle"], foreground=C["muted"],
                     font=F["tab"], padding=(20, 11), borderwidth=0)
        st.map("TNotebook.Tab",
               background=[("selected", C["card"]), ("active", "#cbd5e1")],
               foreground=[("selected", C["brand_d"]), ("active", C["ink"])])

        # Σύγχρονη πλοήγηση: Απόκρυψη της παλιάς οριζόντιας μπάρας καρτελών
        st.layout("Hidden.TNotebook", [("Notebook.client", {"sticky": "nswe"})])
        st.layout("Hidden.TNotebook.Tab", [])
        st.configure("Hidden.TNotebook", background=C["bg"], borderwidth=0)

        st.configure("Treeview", background=C["card"], fieldbackground=C["card"],
                     foreground=C["ink"], rowheight=32, borderwidth=0, font=F["base"])
        st.configure("Treeview.Heading", background=C["card_subtle"], foreground=C["ink"],
                     font=F["sm_bold"], relief="flat", padding=(10, 8))
        st.map("Treeview.Heading", background=[("active", C["line_subtle"])])
        st.map("Treeview", background=[("selected", C["brand"])],
               foreground=[("selected", "#ffffff")])

        st.configure("TSeparator", background=C["line_subtle"])
        st.configure("Vertical.TScrollbar", background=C["line"], troughcolor=C["bg"],
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

        inner = ttk.Frame(canvas, style="Card.TFrame", padding=(18, 14))
        win = canvas.create_window((0, 0), window=inner, anchor="nw")

        def on_inner(_e=None):
            canvas.configure(scrollregion=canvas.bbox("all"))

        def on_canvas(e):
            canvas.itemconfigure(win, width=e.width)

        inner.bind("<Configure>", on_inner)
        canvas.bind("<Configure>", on_canvas)

        # Η ροδέλα: ΟΧΙ bind_all εδώ. Ένα bind_all ανά ακολουθία υπάρχει σε όλη την
        # εφαρμογή· αν το έκανε κάθε καμβάς, ο τελευταίος (π.χ. ο οδηγός) έμενε
        # δεμένος και αφού κλείσει το παράθυρό του, και κάθε κύλιση έβγαζε
        # «invalid command name» ενώ οι καρτέλες δεν κυλούσαν πια. Τον καμβά τον
        # σημαδεύουμε και τον βρίσκει ο καθολικός χειριστής (_install_wheel).
        canvas._is_scroll_canvas = True
        return inner

    def _install_wheel(self):
        """Μία φορά, για όλη την εφαρμογή: κυλά τον καμβά που είναι κάτω από τον δείκτη."""
        def wheel(e):
            try:
                w = self.winfo_containing(e.x_root, e.y_root)
            except (tk.TclError, KeyError):
                return
            while w is not None:
                # Πίνακες/κείμενα κυλούν μόνοι τους — μην κυλάμε και την καρτέλα από κάτω.
                if isinstance(w, (ttk.Treeview, tk.Text, tk.Listbox, ttk.Combobox)):
                    return
                if getattr(w, "_is_scroll_canvas", False):
                    try:
                        if not w.winfo_exists():
                            return
                        delta = -1 if getattr(e, "num", 0) == 5 or getattr(e, "delta", 0) < 0 else 1
                        w.yview_scroll(-delta, "units")
                    except tk.TclError:
                        pass
                    return
                w = getattr(w, "master", None)
        for seq in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            self.bind_all(seq, wheel)

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
            relief="flat", borderwidth=0, padx=14, pady=10,
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

        # Κεντρικό πλαίσιο: Αριστερή μπάρα πλοήγησης (Sidebar) + Δεξιός χώρος εργασίας (Workspace)
        main_box = tk.Frame(self, bg=COLORS["bg"])
        main_box.pack(fill="both", expand=True)

        # ---------------- 1. Αριστερή μπάρα πλοήγησης (Navigation Rail) ----------------
        sidebar = tk.Frame(main_box, bg=COLORS["sidebar"], width=265)
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)

        # Brand Header
        brand = tk.Frame(sidebar, bg=COLORS["sidebar"], padx=16, pady=16)
        brand.pack(fill="x")

        # Επάνω γραμμή: Logo ICS + Επωνυμία
        logo_row = tk.Frame(brand, bg=COLORS["sidebar"])
        logo_row.pack(fill="x", anchor="w")
        self.logo_img = self._load_logo(38)
        if self.logo_img is not None:
            tk.Label(logo_row, image=self.logo_img, bg=COLORS["sidebar"]).pack(side="left", padx=(0, 10))
        vendor_box = tk.Frame(logo_row, bg=COLORS["sidebar"])
        vendor_box.pack(side="left", fill="x", expand=True)
        tk.Label(vendor_box, text="ICS ΚΑΡΑΦΥΛΛΗΣ", font=("Segoe UI", 10, "bold"),
                 fg="#38bdf8", bg=COLORS["sidebar"], anchor="w").pack(fill="x")
        tk.Label(vendor_box, text="Συστήματα Πληροφορικής", font=("Segoe UI", 8),
                 fg="#94a3b8", bg=COLORS["sidebar"], anchor="w").pack(fill="x")

        # Όνομα Εφαρμογής (καθαρό, ευδιάκριτο, με σωστό wrap)
        tk.Label(brand, text="Αυτόματη Ενημέρωση Ζυγών", font=("Segoe UI", 12, "bold"),
                 fg="#ffffff", bg=COLORS["sidebar"], anchor="w", justify="left",
                 wraplength=230).pack(fill="x", pady=(10, 6))

        # Ένδειξη Έκδοσης & Beta Badge
        ver_row = tk.Frame(brand, bg=COLORS["sidebar"])
        ver_row.pack(fill="x", anchor="w")
        if IS_BETA:
            beta_pill = tk.Frame(ver_row, bg="#b45309", padx=6, pady=2)
            beta_pill.pack(side="left", padx=(0, 6))
            tk.Label(beta_pill, text="BETA", font=("Segoe UI", 8, "bold"),
                     fg="#ffffff", bg="#b45309").pack()
        ver_pill = tk.Frame(ver_row, bg="#1e293b", padx=7, pady=2)
        ver_pill.pack(side="left")
        tk.Label(ver_pill, text="έκδοση %s" % APP_BUILD, font=("Segoe UI", 8, "bold"),
                 fg="#94a3b8", bg="#1e293b").pack()

        # Διαχωριστικό
        tk.Frame(sidebar, height=1, bg="#1e293b", bd=0).pack(fill="x", pady=(10, 8))

        # Κάτω τμήμα Sidebar (σταθερό στο κάτω μέρος)
        side_bottom = tk.Frame(sidebar, bg=COLORS["sidebar"], padx=12, pady=10)
        side_bottom.pack(side="bottom", fill="x")

        # Κουμπιά εξόδου & tray
        btn_exit_row = tk.Frame(side_bottom, bg=COLORS["sidebar"])
        btn_exit_row.pack(fill="x", pady=(0, 8))
        tk.Button(btn_exit_row, text="✕  Έξοδος", relief="flat", bd=0, bg="#1e293b",
                  fg="#94a3b8", activebackground="#334155", activeforeground="#ffffff",
                  font=FONTS["sm"], cursor="hand2", padx=6, pady=5,
                  command=self.quit_app).pack(side="right", fill="x", expand=True, padx=(3, 0))
        tk.Button(btn_exit_row, text="🗕  Tray", relief="flat", bd=0, bg="#1e293b",
                  fg="#94a3b8", activebackground="#334155", activeforeground="#ffffff",
                  font=FONTS["sm"], cursor="hand2", padx=6, pady=5,
                  command=self.hide_to_tray).pack(side="left", fill="x", expand=True, padx=(0, 3))

        # Μενού εργαλείων
        tools = ttk.Menubutton(side_bottom, text="⚙  Εργαλεία  ▾", style="Ghost.TButton")
        menu = tk.Menu(tools, tearoff=0)
        menu.add_command(label="Άνοιγμα φακέλου εξόδου", command=self.open_out_dir)
        menu.add_command(label="Άνοιγμα backup", command=self.open_backup)
        menu.add_command(label="Αρχείο log", command=self.open_log_file)
        menu.add_separator()
        menu.add_command(label="Καθαρισμός οθόνης", command=lambda: self.txt_log.delete("1.0", "end"))
        menu.add_separator()
        menu.add_command(label="Έλεγχος ενημέρωσης…", command=self.check_update)
        if not globals().get("IS_BETA", False):
            self.v_accept_beta = tk.BooleanVar(value=bool(self.cfg.get("accept_beta", False)))
            menu.add_checkbutton(label="Δέχομαι δοκιμαστικές (beta) εκδόσεις",
                                 variable=self.v_accept_beta, command=self.on_accept_beta)
            menu.add_command(label="Δοκιμαστική έκδοση (beta)…", command=self.check_beta)
        menu.add_command(label="Σχετικά", command=self.show_about)
        tools["menu"] = menu
        tools.pack(fill="x", pady=(0, 8))
        self.menu_tools = menu

        # Κάρτα κατάστασης
        badge = tk.Frame(side_bottom, bg="#1e293b", padx=10, pady=8,
                         highlightbackground="#334155", highlightthickness=1)
        badge.pack(fill="x", pady=(0, 2))
        self.status_dot = tk.Canvas(badge, width=12, height=12, highlightthickness=0,
                                    bg="#1e293b")
        self._dot = self.status_dot.create_oval(1, 1, 11, 11, fill=COLORS["muted"], outline="")
        self.status_dot.pack(side="left", padx=(0, 8))
        self.status = tk.Label(badge, text="Σε αναμονή", font=("Segoe UI", 9, "bold"),
                               fg="#cbd5e1", bg="#1e293b", anchor="w", wraplength=190, justify="left")
        self.status.pack(side="left", fill="x", expand=True)

        tk.Frame(sidebar, height=1, bg="#1e293b", bd=0).pack(side="bottom", fill="x", pady=(0, 8))

        # Στοιχεία πλοήγησης
        nav_container = tk.Frame(sidebar, bg=COLORS["sidebar"])
        nav_container.pack(fill="both", expand=True, padx=8)

        self.nav_items_def = [
            ("📊", "Σύνοψη", "Επισκόπηση & έλεγχος"),
            ("📁", "Βήμα 1", "Αρχείο ERP"),
            ("⚙", "Βήμα 2", "Κανόνες Μετατροπής"),
            ("🏷", "Βήμα 3", "Αρχείο Προϊόντων"),
            ("⚖", "Βήμα 4", "Ζυγοί & Αποστολή"),
            ("📜", "Καταγραφή", "Ιστορικό & Logs"),
        ]
        self.nav_rows = []
        for i, (icon, title, desc) in enumerate(self.nav_items_def):
            row = tk.Frame(nav_container, bg=COLORS["sidebar"], cursor="hand2")
            row.pack(fill="x", pady=2)
            ind = tk.Frame(row, width=4, bg=COLORS["sidebar"])
            ind.pack(side="left", fill="y")
            icon_lbl = tk.Label(row, text=icon, font=("Segoe UI", 12),
                                bg=COLORS["sidebar"], fg=COLORS["sidebar_fg"], width=3)
            icon_lbl.pack(side="left", padx=(2, 4), pady=7)
            text_frame = tk.Frame(row, bg=COLORS["sidebar"])
            text_frame.pack(side="left", fill="x", expand=True, pady=5)
            title_lbl = tk.Label(text_frame, text=title, font=FONTS["base_bold"],
                                 bg=COLORS["sidebar"], fg=COLORS["sidebar_fg"], anchor="w")
            title_lbl.pack(fill="x")
            sub_lbl = tk.Label(text_frame, text=desc, font=("Segoe UI", 9),
                               bg=COLORS["sidebar"], fg="#64748b", anchor="w")
            sub_lbl.pack(fill="x")

            widgets = (row, ind, icon_lbl, text_frame, title_lbl, sub_lbl)
            self._bind_nav_item(widgets, i)
            self.nav_rows.append((row, ind, icon_lbl, title_lbl, sub_lbl))

        # ---------------- 2. Δεξιός χώρος εργασίας (Workspace) ----------------
        workspace = tk.Frame(main_box, bg=COLORS["bg"])
        workspace.pack(side="right", fill="both", expand=True)
        self.workspace = workspace

        # Πάνω μπάρα τίτλου & γρήγορων ενεργειών
        top_bar = tk.Frame(workspace, bg=COLORS["card"], padx=18, pady=10,
                           highlightbackground=COLORS["line_subtle"], highlightthickness=1)
        top_bar.pack(fill="x")

        title_box = tk.Frame(top_bar, bg=COLORS["card"])
        title_box.pack(side="left")
        self.page_title_lbl = tk.Label(title_box, text="📊  Σύνοψη & Έλεγχος",
                                       font=("Segoe UI", 13, "bold"), fg=COLORS["ink"],
                                       bg=COLORS["card"], anchor="w")
        self.page_title_lbl.pack(anchor="w")
        self.page_sub_lbl = tk.Label(title_box, text="Επισκόπηση κατάστασης συστήματος και άμεσες λειτουργίες",
                                     font=FONTS["sm"], fg=COLORS["muted"],
                                     bg=COLORS["card"], anchor="w")
        self.page_sub_lbl.pack(anchor="w")

        # Ενέργειες πάνω δεξιά
        actions_bar = tk.Frame(top_bar, bg=COLORS["card"])
        actions_bar.pack(side="right")
        ttk.Button(actions_bar, text="▶  Εκτέλεση τώρα", style="Accent.TButton",
                   command=self.run_once).pack(side="left", padx=3)
        self.btn_watch = ttk.Button(actions_bar, text="●  Έναρξη παρακολούθησης",
                                    command=self.toggle_watch)
        self.btn_watch.pack(side="left", padx=3)
        ttk.Button(actions_bar, text="🔍  Προεπισκόπηση",
                   command=self.show_preview).pack(side="left", padx=3)
        ttk.Button(actions_bar, text="💾  Αποθήκευση",
                   command=self.on_save).pack(side="left", padx=3)

        # Κάτω μπάρα κατάστασης (Footer Ticker)
        self.workspace_bottom = tk.Frame(workspace, bg=COLORS["card"], padx=14, pady=6,
                                         highlightbackground=COLORS["line_subtle"], highlightthickness=1)
        self.workspace_bottom.pack(side="bottom", fill="x")
        ticker_left = tk.Frame(self.workspace_bottom, bg=COLORS["card"])
        ticker_left.pack(side="left", fill="x", expand=True)
        self.status_ticker = tk.Label(ticker_left, text="🟢 Έτοιμο για λειτουργία",
                                      bg=COLORS["card"], fg=COLORS["muted"], font=FONTS["sm"], anchor="w")
        self.status_ticker.pack(side="left", fill="x", expand=True)
        ttk.Button(self.workspace_bottom, text="📜  Αρχείο καταγραφής (Log)", style="Ghost.TButton",
                   command=lambda: self._select_nav(5)).pack(side="right")

        # Μπάρα σφάλματος: μένει μέσα στο παράθυρο και ΔΕΝ μπλοκάρει
        self.err_bar = tk.Frame(workspace, bg=COLORS["err"])
        self.err_lbl = tk.Label(self.err_bar, bg=COLORS["err"], fg="white",
                                anchor="w", justify="left", font=FONTS["sm_bold"])
        self.err_lbl.pack(side="left", fill="x", expand=True, padx=(16, 8), pady=8)
        tk.Button(self.err_bar, text="Λεπτομέρειες", relief="flat", bd=0,
                  bg="white", fg=COLORS["err"], font=FONTS["sm_bold"],
                  command=self.show_last_errors, cursor="hand2", padx=10, pady=4
                  ).pack(side="right", padx=6, pady=6)
        tk.Button(self.err_bar, text="✕", relief="flat", bd=0, bg=COLORS["err"],
                  fg="white", font=FONTS["base_bold"],
                  command=self.clear_error_bar, cursor="hand2", padx=8, pady=4
                  ).pack(side="right", padx=(0, 12), pady=6)

        # Κεντρικό Notebook (Hidden tabs)
        nb = self.nb = ttk.Notebook(workspace, style="Hidden.TNotebook")
        pages = []
        for title in ("Σύνοψη", "Βήμα 1", "Βήμα 2", "Βήμα 3", "Βήμα 4"):
            page = ttk.Frame(nb, style="Card.TFrame")
            nb.add(page, text=title)
            pages.append(self._scrollable(page))
        self.tab_home, self.tab0, self.tab1, self.tab2, self.tab3 = pages

        # 6η καρτέλα: Πλήρες τερματικό Log
        page_log = ttk.Frame(nb, style="Card.TFrame")
        nb.add(page_log, text="Logs")
        self._build_tab_log(page_log)

        self.v_tscale_on = tk.BooleanVar(value=True)
        self.v_ish_on = tk.BooleanVar(value=False)

        self._build_tab_home()
        self._build_tab0()
        self._build_tab1()
        self._build_tab2()
        self._build_tab3()

        # Τα μπλοκ του Βήματος 3 ακολουθούν τα τσεκ ζυγών
        self.v_tscale_on.trace_add("write", lambda *_a: self._refresh_tab2_blocks())
        self.v_ish_on.trace_add("write", lambda *_a: self._refresh_tab2_blocks())
        self._refresh_tab2_blocks()

        nb.pack(fill="both", expand=True, padx=12, pady=10)
        self._install_wheel()

        def _on_tab_change(_event=None):
            try:
                cur = self.nb.index(self.nb.select())
                self._highlight_nav(cur)
            except Exception:
                pass
        self.nb.bind("<<NotebookTabChanged>>", _on_tab_change)
        self._select_nav(0)

    def _bind_nav_item(self, widgets, idx):
        def on_enter(_e):
            if hasattr(self, "nb") and self.nb.index(self.nb.select()) == idx:
                return
            for w in widgets:
                try:
                    w.configure(bg=COLORS["sidebar_hover"])
                except Exception:
                    pass
        def on_leave(_e):
            if hasattr(self, "nb") and self.nb.index(self.nb.select()) == idx:
                return
            for w in widgets:
                try:
                    w.configure(bg=COLORS["sidebar"])
                except Exception:
                    pass
        for w in widgets:
            w.bind("<Enter>", on_enter)
            w.bind("<Leave>", on_leave)
            w.bind("<Button-1>", lambda _e, i=idx: self._select_nav(i))

    def _select_nav(self, idx):
        if hasattr(self, "nb"):
            self.nb.select(idx)
        self._highlight_nav(idx)

    def _highlight_nav(self, idx):
        if not hasattr(self, "nav_rows") or not self.nav_rows:
            return
        meta = [
            ("📊  Σύνοψη & Έλεγχος", "Επισκόπηση κατάστασης συστήματος και άμεσες λειτουργίες"),
            ("📁  Βήμα 1 · Αρχείο ERP", "Διαδρομή αρχείου προέλευσης & συχνότητα παρακολούθησης"),
            ("⚙  Βήμα 2 · Μετατροπή", "Κανόνες κωδικοποίησης, barcodes και μορφοποίησης"),
            ("🏷  Βήμα 3 · Αρχείο Προϊόντων", "Διαμόρφωση πεδίων και εξαγωγή αρχείων ζυγών"),
            ("⚖  Βήμα 4 · Ζυγοί & Αποστολή", "Διευθύνσεις IP ζυγών (T-Scale, Ishida, ILS)"),
            ("📜  Καταγραφή & Logs", "Πλήρες ιστορικό λειτουργίας και μηνύματα συστήματος"),
        ]
        if idx < len(meta):
            t, s = meta[idx]
            if hasattr(self, "page_title_lbl"):
                self.page_title_lbl.configure(text=t)
            if hasattr(self, "page_sub_lbl"):
                self.page_sub_lbl.configure(text=s)

        for i, row_data in enumerate(self.nav_rows):
            row, ind, icon_lbl, title_lbl, sub_lbl = row_data
            bg_col = COLORS["sidebar_active"] if i == idx else COLORS["sidebar"]
            ind_col = COLORS["brand"] if i == idx else COLORS["sidebar"]
            fg_title = "#ffffff" if i == idx else COLORS["sidebar_fg"]
            fg_icon = "#38bdf8" if i == idx else COLORS["sidebar_fg"]
            fg_sub = "#cbd5e1" if i == idx else "#64748b"

            row.configure(bg=bg_col)
            ind.configure(bg=ind_col)
            icon_lbl.configure(bg=bg_col, fg=fg_icon)
            title_lbl.master.configure(bg=bg_col)
            title_lbl.configure(bg=bg_col, fg=fg_title)
            sub_lbl.configure(bg=bg_col, fg=fg_sub)

    def _build_tab_log(self, parent):
        container = ttk.Frame(parent, style="Card.TFrame", padding=(16, 16))
        container.pack(fill="both", expand=True)

        header = ttk.Frame(container, style="Card.TFrame")
        header.pack(fill="x", pady=(0, 10))

        ttk.Label(header, text="Αρχείο Καταγραφής Ενεργειών (Live Activity Console)",
                  font=FONTS["title"]).pack(side="left")

        btn_box = ttk.Frame(header, style="Card.TFrame")
        btn_box.pack(side="right")
        ttk.Button(btn_box, text="Καθαρισμός", style="Ghost.TButton",
                   command=lambda: self.txt_log.delete("1.0", "end")).pack(side="left", padx=4)
        ttk.Button(btn_box, text="Άνοιγμα αρχείου log", style="Ghost.TButton",
                   command=self.open_log_file).pack(side="left", padx=4)

        self.txt_log = self._console(container, 20, FONTS["mono"])
        self.txt_log.pack(fill="both", expand=True)

        for tag, col in (("ok", "#34d399"), ("err", "#f87171"),
                         ("info", COLORS["console_fg"]), ("dim", "#94a3b8")):
            self.txt_log.tag_configure(tag, foreground=col)

    def _pick_row(self, parent, label, var, kind="file", r=0):
        ttk.Label(parent, text=label).grid(row=r, column=0, sticky="w", pady=5)
        self._add_edit_menu(ttk.Entry(parent, textvariable=var, width=78)
                            ).grid(row=r, column=1, sticky="we", padx=8)

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

    def _build_tab_home(self):
        """Η «Σύνοψη»: σύγχρονο Executive Dashboard 2026 με Hero banner, 4 KPI cards και άμεσες ενέργειες."""
        f = self.tab_home

        # 1. Hero Banner / Κάρτα κατάστασης
        hero = tk.Frame(f, bg="#ffffff", padx=22, pady=18,
                        highlightbackground=COLORS["line_subtle"], highlightthickness=1)
        hero.pack(fill="x", pady=(2, 16))

        hero_left = tk.Frame(hero, bg="#ffffff")
        hero_left.pack(side="left", fill="both", expand=True)

        self.home_big = tk.Label(hero_left, text="", bg="#ffffff", fg=COLORS["ink"],
                                 font=("Segoe UI", 15, "bold"), anchor="w", justify="left",
                                 wraplength=640)
        self.home_big.pack(anchor="w", pady=(0, 4))
        self.home_sub = tk.Label(hero_left, text="", bg="#ffffff", fg=COLORS["muted"],
                                 font=FONTS["base"], anchor="w", justify="left", wraplength=640)
        self.home_sub.pack(anchor="w")

        hero_actions = tk.Frame(hero, bg="#ffffff")
        hero_actions.pack(side="right", padx=(16, 0))

        ttk.Button(hero_actions, text="▶  Ενημέρωση ζυγών τώρα", style="Accent.TButton",
                   command=self.run_once).pack(fill="x", pady=(0, 6))
        self.btn_watch_home = ttk.Button(hero_actions, text="●  Έναρξη παρακολούθησης",
                                         command=self.toggle_watch)
        self.btn_watch_home.pack(fill="x")

        # 2. Metric KPI Cards Grid (2x2 layout)
        grid_frame = tk.Frame(f, bg=COLORS["card"])
        grid_frame.pack(fill="x", pady=(0, 16))
        grid_frame.columnconfigure(0, weight=1, uniform="kpi")
        grid_frame.columnconfigure(1, weight=1, uniform="kpi")

        self.home_vals = {}

        # Card 1: Αρχείο ERP
        card1 = tk.Frame(grid_frame, bg=COLORS["card_subtle"], padx=18, pady=16,
                         highlightbackground=COLORS["line_subtle"], highlightthickness=1)
        card1.grid(row=0, column=0, sticky="nsew", padx=(0, 8), pady=(0, 12))
        tk.Label(card1, text="📁  ΑΡΧΕΙΟ ΠΡΟΕΛΕΥΣΗΣ (ERP)", bg=COLORS["card_subtle"],
                 fg=COLORS["brand_d"], font=FONTS["sm_bold"]).pack(anchor="w", pady=(0, 6))
        self.home_vals["erp"] = tk.Label(card1, text="—", bg=COLORS["card_subtle"], fg=COLORS["ink"],
                                         font=FONTS["base"], anchor="w", justify="left", wraplength=420)
        self.home_vals["erp"].pack(anchor="w")

        # Card 2: Παρακολούθηση
        card2 = tk.Frame(grid_frame, bg=COLORS["card_subtle"], padx=18, pady=16,
                         highlightbackground=COLORS["line_subtle"], highlightthickness=1)
        card2.grid(row=0, column=1, sticky="nsew", padx=(8, 0), pady=(0, 12))
        tk.Label(card2, text="⏱  ΑΥΤΟΜΑΤΙΣΜΟΣ & ΕΛΕΓΧΟΣ", bg=COLORS["card_subtle"],
                 fg=COLORS["brand_d"], font=FONTS["sm_bold"]).pack(anchor="w", pady=(0, 6))
        self.home_vals["watch"] = tk.Label(card2, text="—", bg=COLORS["card_subtle"], fg=COLORS["ink"],
                                           font=FONTS["base"], anchor="w", justify="left", wraplength=420)
        self.home_vals["watch"].pack(anchor="w")

        # Card 3: Ζυγοί
        card3 = tk.Frame(grid_frame, bg=COLORS["card_subtle"], padx=18, pady=16,
                         highlightbackground=COLORS["line_subtle"], highlightthickness=1)
        card3.grid(row=1, column=0, sticky="nsew", padx=(0, 8), pady=(0, 0))
        tk.Label(card3, text="⚖  ΤΕΡΜΑΤΙΚΑ ΖΥΓΙΣΗΣ (ΚΑΤΑΣΤΗΜΑ)", bg=COLORS["card_subtle"],
                 fg=COLORS["brand_d"], font=FONTS["sm_bold"]).pack(anchor="w", pady=(0, 6))
        self.home_vals["scales"] = tk.Label(card3, text="—", bg=COLORS["card_subtle"], fg=COLORS["ink"],
                                            font=FONTS["base"], anchor="w", justify="left", wraplength=420)
        self.home_vals["scales"].pack(anchor="w")

        # Card 4: Τελευταία εκτέλεση & Εκκρεμότητες
        card4 = tk.Frame(grid_frame, bg=COLORS["card_subtle"], padx=18, pady=16,
                         highlightbackground=COLORS["line_subtle"], highlightthickness=1)
        card4.grid(row=1, column=1, sticky="nsew", padx=(8, 0), pady=(0, 0))
        tk.Label(card4, text="🔄  ΙΣΤΟΡΙΚΟ & ΕΚΚΡΕΜΟΤΗΤΕΣ", bg=COLORS["card_subtle"],
                 fg=COLORS["brand_d"], font=FONTS["sm_bold"]).pack(anchor="w", pady=(0, 6))
        self.home_vals["last"] = tk.Label(card4, text="—", bg=COLORS["card_subtle"], fg=COLORS["ink"],
                                          font=FONTS["base"], anchor="w", justify="left", wraplength=420)
        self.home_vals["last"].pack(anchor="w", pady=(0, 4))

        pend_box = tk.Frame(card4, bg=COLORS["card_subtle"])
        pend_box.pack(anchor="w", fill="x")
        tk.Label(pend_box, text="Εκκρεμείς ζυγοί: ", bg=COLORS["card_subtle"], fg=COLORS["muted"],
                 font=FONTS["sm"]).pack(side="left")
        self.home_vals["pending"] = tk.Label(pend_box, text="—", bg=COLORS["card_subtle"], fg=COLORS["ink"],
                                             font=FONTS["sm_bold"], anchor="w")
        self.home_vals["pending"].pack(side="left")

        # 3. Action Row
        action_row = ttk.Frame(f)
        action_row.pack(fill="x", pady=(16, 12))
        ttk.Button(action_row, text="Τι πήγε στραβά;", style="Ghost.TButton",
                   command=self.show_last_errors).pack(side="left")
        ttk.Button(action_row, text="🧭  Νέα εγκατάσταση — οδηγός", style="Ghost.TButton",
                   command=self.column_wizard).pack(side="right")

        # 4. Note Guidance Card
        note_card = tk.Frame(f, bg=COLORS["card_subtle"], padx=16, pady=12,
                             highlightbackground=COLORS["brand_light"], highlightthickness=1)
        note_card.pack(fill="x", pady=(0, 10))
        ttk.Label(note_card, style="Hint.TLabel", justify="left", wraplength=900,
                  text="💡 «Ενημέρωση ζυγών τώρα» στέλνει αμέσως τις τιμές του ERP στους ζυγούς. "
                       "Με την παρακολούθηση ενεργή, γίνεται μόνο του κάθε φορά που το ERP "
                       "βγάζει νέο αρχείο — δεν χρειάζεται καμία άλλη ενέργεια.\n"
                       "Τα «Βήματα 1-4» στην αριστερή μπάρα περιέχουν τις τεχνικές ρυθμίσεις της εγκατάστασης."
                  ).pack(anchor="w")

        self.after(800, self._refresh_home)

    def _refresh_home(self):
        """Ανανεώνει τη Σύνοψη κάθε 2 δευτερόλεπτα από τις τρέχουσες ρυθμίσεις."""
        try:
            self._fill_home()
        except Exception:
            pass
        self.after(2000, self._refresh_home)

    def _fill_home(self):
        cfg = self.cfg
        C = COLORS
        path = (self.v_watch.get() or cfg.get("watch_file") or "").strip()
        busy = bool(self.worker and self.worker.is_alive())

        # αρχείο ERP
        if not path:
            self.home_vals["erp"].configure(text="δεν έχει οριστεί (Βήμα 1)", fg=C["warn"])
        elif not os.path.isfile(path):
            self.home_vals["erp"].configure(text="%s\nΔΕΝ ΒΡΕΘΗΚΕ το αρχείο" % path, fg=C["err"])
        else:
            try:
                mt = datetime.datetime.fromtimestamp(os.path.getmtime(path))
                self.home_vals["erp"].configure(
                    text="%s\nτελευταία αλλαγή από το ERP: %s" % (path, mt.strftime("%d/%m/%Y %H:%M")),
                    fg=C["ink"])
            except OSError:
                self.home_vals["erp"].configure(text=path, fg=C["ink"])

        # παρακολούθηση
        if self.watching:
            n, unit = seconds_to_unit(cfg.get("poll_seconds", 300))
            self.home_vals["watch"].configure(
                text="ενεργή — ελέγχει για νέο αρχείο κάθε %d %s" % (n, unit), fg=C["ok"])
        else:
            self.home_vals["watch"].configure(text="σταματημένη — δεν ενημερώνει μόνο του",
                                              fg=C["warn"])

        # ζυγοί
        meri = []
        if cfg.get("step3_enabled", True) and cfg.get("tscale_on", True):
            ips = parse_ips(self.v_ips.get() if hasattr(self, "v_ips") else cfg.get("scale_ips", ""))
            meri.append("T-Scale: %d ζυγ%s (%s)" % (len(ips), "ός" if len(ips) == 1 else "οί",
                                                    ", ".join(ips)) if ips else "T-Scale: χωρίς IP!")
        if cfg.get("step3_enabled", True) and cfg.get("ishida_on"):
            ips = parse_ips(cfg.get("ishida_ips", ""))
            meri.append("Ishida: %d ζυγ%s (%s)" % (len(ips), "ός" if len(ips) == 1 else "οί",
                                                   ", ".join(ips)) if ips else "Ishida: χωρίς IP!")
        if cfg.get("step2c_enabled") or cfg.get("ils_enabled"):
            meri.append("ILS: μέσω αρχείου hostILS")
        self.home_vals["scales"].configure(text="\n".join(meri) if meri else "κανένας (Βήμα 4)",
                                           fg=C["ink"] if meri else C["warn"])

        # τελευταία εκτέλεση
        if busy:
            self.home_vals["last"].configure(text="γίνεται τώρα…", fg=C["brand"])
        elif self.last_run:
            pote, ok, msg = self.last_run
            self.home_vals["last"].configure(
                text="%s — %s" % (pote.strftime("%d/%m/%Y %H:%M"),
                                  "ΕΠΙΤΥΧΙΑ" if ok else "ΣΦΑΛΜΑ: " + msg),
                fg=C["ok"] if ok else C["err"])
        else:
            self.home_vals["last"].configure(text="καμία από τότε που άνοιξε το πρόγραμμα",
                                             fg=C["muted"])

        # εκκρεμείς
        try:
            pend = load_pending()
        except Exception:
            pend = {}
        if pend:
            self.home_vals["pending"].configure(
                text="%d — θα ξαναδοκιμάσει μόνο του: %s" % (len(pend), ", ".join(sorted(pend))),
                fg=C["warn"])
        else:
            self.home_vals["pending"].configure(text="κανένας", fg=C["ink"])

        # η μεγάλη γραμμή
        if busy:
            big, sub, col = "⏳  Γίνεται ενημέρωση των ζυγών…", "Περίμενε λίγο.", C["brand"]
        elif self.last_run and not self.last_run[1]:
            big, sub, col = ("❌  Η τελευταία ενημέρωση ΑΠΕΤΥΧΕ",
                             "Δες «Τι πήγε στραβά;» ή κάλεσε τον τεχνικό.", C["err"])
        elif not path or not os.path.isfile(path):
            big, sub, col = ("⚠️  Δεν βρίσκω το αρχείο του ERP",
                             "Ο τεχνικός πρέπει να το ορίσει στο «Βήμα 1».", C["warn"])
        elif not meri:
            big, sub, col = ("⚠️  Δεν έχει δηλωθεί κανένας ζυγός",
                             "Ο τεχνικός πρέπει να τους ορίσει στο «Βήμα 4».", C["warn"])
        elif self.watching:
            big, sub, col = ("✅  Όλα καλά — παρακολουθεί το ERP",
                             "Μόλις βγει νέο αρχείο, οι ζυγοί ενημερώνονται μόνοι τους.", C["ok"])
        else:
            big, sub, col = ("⏸️  Σε αναμονή — η παρακολούθηση είναι σταματημένη",
                             "Πάτα «Έναρξη παρακολούθησης» για να ενημερώνει μόνο του.", C["warn"])
        self.home_big.configure(text=big, fg=col)
        self.home_sub.configure(text=sub)
        self.btn_watch_home.configure(
            text="■  Διακοπή παρακολούθησης" if self.watching else "●  Έναρξη παρακολούθησης")

    def _build_tab0(self):
        f = self.tab0
        self.v_watch = tk.StringVar()
        self.v_outdir = tk.StringVar()
        self.v_poll = tk.StringVar(value="3")
        self.v_auto = tk.BooleanVar()
        self._pick_row(f, "Αρχείο που βγάζει το ERP:", self.v_watch, "file", 0)
        self._pick_row(f, "Φάκελος εξόδου (host1 / host2):", self.v_outdir, "dir", 1)
        adv1bar = ttk.Frame(f)
        adv1bar.grid(row=4, column=0, columnspan=3, sticky="w", pady=(8, 0))
        self.btn_adv1 = ttk.Button(adv1bar, text="⚙  Περισσότερα  ▾", style="Ghost.TButton",
                                   command=self.toggle_adv1)
        self.btn_adv1.pack(side="left")
        ttk.Label(adv1bar, style="Hint.TLabel",
                  text="καταλήξεις αρχείων, αντίγραφα ασφαλείας, μηνύματα"
                  ).pack(side="left", padx=8)
        self.adv1 = ttk.Frame(f)

        ext = ttk.Frame(self.adv1)
        ext.pack(fill="x", pady=(6, 0))
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
        bk = ttk.Frame(self.adv1)
        bk.pack(fill="x", pady=(6, 0))
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
                        ).grid(row=6, column=0, columnspan=3, sticky="w", pady=(2, 0))
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
                       "PADLINE=n / DESCRIPT=θέση μήκος / IFEXISTn=θέση=[τιμή] THEN=[τιμή]\n"
                       "Γράψε ελεύθερα όσες γραμμές θες. Δεξί κλικ για αντιγραφή/επικόλληση "
                       "(δουλεύει και με ελληνικό πληκτρολόγιο)."
                  ).pack(anchor="w", pady=6)
        self.txt_s1 = self._console(f, 8, FONTS["mono"])
        self.txt_s1.pack(fill="x")
        g = ttk.Frame(f)
        g.pack(fill="x", pady=8)
        self.v_s1exe = tk.StringVar()
        self._pick_row(g, "Προαιρετικό εξωτερικό .exe μετατροπής:", self.v_s1exe, "exe", 0)

    def _block(self, parent, title, hint=None):
        """Ένα πλαίσιο ανά ζυγό στο Βήμα 3: τίτλος με χρώμα, προαιρετική υπόδειξη."""
        blk = ttk.Frame(parent)
        ttk.Separator(blk, orient="horizontal").pack(fill="x", pady=(12, 6))
        tk.Label(blk, text=title, bg=COLORS["card"], fg=COLORS["brand_d"],
                 font=FONTS["title"], anchor="w").pack(anchor="w")
        if hint:
            ttk.Label(blk, style="Hint.TLabel", justify="left", wraplength=950, text=hint
                      ).pack(anchor="w", pady=(2, 6))
        return blk

    def _build_tab2(self):
        """Βήμα 3: πώς διαβάζεται το ERP (κοινό) και ένα μπλοκ ανά ζυγό.

        Τα μπλοκ T-Scale και Ishida φαίνονται μόνο όταν το κατάστημα έχει τον
        ζυγό (τσεκ στο Βήμα 4) — ο τεχνικός βλέπει μόνο ό,τι τον αφορά.
        """
        f = self.tab2
        self.v_s2 = tk.BooleanVar()
        self.v_s2b = tk.BooleanVar(value=False)
        self.v_s2c = tk.BooleanVar(value=False)
        ttk.Checkbutton(f, style="Big.TCheckbutton", text="Ενεργοποίηση Βήματος 3 — Αρχεία προϊόντων",
                        variable=self.v_s2).pack(anchor="w")

        # ---- κοινά: οδηγός + πώς διαβάζεται το ERP
        topbar = ttk.Frame(f)
        topbar.pack(fill="x", pady=(2, 2))
        ttk.Button(topbar, text="🧭  Οδηγός από το αρχείο του ERP…", style="Accent.TButton",
                   command=self.column_wizard).pack(side="left")
        self.btn_adv2 = ttk.Button(topbar, text="⚙  Πώς διαβάζεται το ERP / μορφή αρχείων  ▾",
                                   style="Ghost.TButton", command=self.toggle_adv2)
        self.btn_adv2.pack(side="left", padx=(12, 0))
        ttk.Label(topbar, style="Hint.TLabel", text="τα ρυθμίζει το προφίλ — σπάνια με το χέρι"
                  ).pack(side="left", padx=8)
        self.adv2 = ttk.Frame(f)          # κρυφό: ό,τι ορίζει ήδη το προφίλ

        intype = ttk.Frame(self.adv2)
        intype.pack(fill="x", pady=(2, 4))
        ttk.Label(intype, text="Αρχείο ERP:").pack(side="left")
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

        o = ttk.Frame(self.adv2)
        o.pack(fill="x", pady=4)
        self.v_start = tk.StringVar(value="1")
        self.v_onebased = tk.BooleanVar(value=True)
        self.v_header = tk.BooleanVar(value=True)
        self.v_delim = tk.StringVar(value=",")
        ttk.Label(o, text="Γραμμή έναρξης:").pack(side="left")
        ttk.Entry(o, textvariable=self.v_start, width=5).pack(side="left", padx=4)
        ttk.Checkbutton(o, text="Θέση 1 = πρώτος χαρακτήρας", variable=self.v_onebased).pack(side="left", padx=12)

        enc = ttk.Frame(self.adv2)
        enc.pack(fill="x", pady=(2, 2))
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

        fmt = ttk.Frame(self.adv2)
        fmt.pack(fill="x", pady=(6, 2))
        ttk.Label(fmt, text="Μορφή product.csv:").pack(side="left")
        self.v_format = tk.StringVar(value="csv")
        for val, txt in (("csv", "CSV (κόμμα)"), ("semicolon", "CSV με ερωτηματικό (;)"),
                         ("tab", "TXT με Tab"), ("fixed", "TXT σταθερού πλάτους")):
            ttk.Radiobutton(fmt, text=txt, value=val, variable=self.v_format,
                            command=self.on_format_change).pack(side="left", padx=(10, 0))
        extra = ttk.Frame(self.adv2)
        extra.pack(fill="x", pady=(2, 2))
        self.v_tail = tk.BooleanVar(value=False)
        self.v_quotes = tk.BooleanVar(value=False)
        ttk.Checkbutton(extra, text="Γράψε γραμμή επικεφαλίδων", variable=self.v_header).pack(side="left")
        ttk.Checkbutton(extra, text="Διαχωριστικό και στο τέλος κάθε γραμμής (;…;)",
                        variable=self.v_tail).pack(side="left", padx=14)
        ttk.Checkbutton(extra, text="Εισαγωγικά όπου χρειάζεται (πρότυπο CSV)",
                        variable=self.v_quotes).pack(side="left")
        extra2 = ttk.Frame(self.adv2)
        extra2.pack(fill="x", pady=(0, 2))
        self.v_sanitize = tk.BooleanVar(value=True)
        self.v_dedupe = tk.BooleanVar(value=False)
        self.v_finalnl = tk.BooleanVar(value=True)
        ttk.Checkbutton(extra2, text="Καθάρισε το διαχωριστικό μέσα στις περιγραφές",
                        variable=self.v_sanitize).pack(side="left")
        ttk.Checkbutton(extra2, text="Μία εγγραφή ανά κωδικό (κρατά την τελευταία)",
                        variable=self.v_dedupe).pack(side="left", padx=14)
        ttk.Checkbutton(extra2, text="Αλλαγή γραμμής στο τέλος του αρχείου",
                        variable=self.v_finalnl).pack(side="left")
        self.lbl_intype_hint = ttk.Label(self.adv2, style="Hint.TLabel", justify="left", wraplength=920)
        self.lbl_intype_hint.pack(anchor="w", pady=(0, 2))
        ttk.Label(self.adv2, style="Hint.TLabel", justify="left", wraplength=920,
                  text="«auto» αναγνωρίζει μόνο του UTF-8 / Windows-1253 / DOS-737. Για ελληνικά η "
                       "ΕΞΟΔΟΣ πρέπει να είναι cp1253 — με utf-8 ο ζυγός δείχνει ακαταλαβίστικα."
                  ).pack(anchor="w", pady=(0, 2))

        # Επιλογή ζυγών καταστήματος απευθείας και στο Βήμα 3
        scale_sel = tk.Frame(f, bg=COLORS["card_subtle"], padx=14, pady=10,
                             highlightbackground=COLORS["line_subtle"], highlightthickness=1)
        scale_sel.pack(fill="x", pady=(6, 12))
        tk.Label(scale_sel, text="Ζυγοί καταστήματος (δημιουργία αρχείων):",
                 font=FONTS["base_bold"], fg=COLORS["ink"], bg=COLORS["card_subtle"]).pack(side="left", padx=(0, 12))
        ttk.Checkbutton(scale_sel, text="T-Scale (product.csv)", variable=self.v_tscale_on,
                        command=self.on_marka_toggle).pack(side="left", padx=8)
        ttk.Checkbutton(scale_sel, text="Ishida UNI-3 (host2.csv)", variable=self.v_ish_on,
                        command=self.on_marka_toggle).pack(side="left", padx=8)
        ttk.Checkbutton(scale_sel, text="ILS 1100 (hostILS.csv)", variable=self.v_s2c,
                        command=self._refresh_tab2_blocks).pack(side="left", padx=8)

        # ---- τα μπλοκ ανά ζυγό
        self.blocks = ttk.Frame(f)
        self.blocks.pack(fill="x")
        self.lbl_no_scales = ttk.Label(
            self.blocks, style="Hint.TLabel", wraplength=920, justify="left",
            text="Δεν έχει επιλεγεί κανένας ζυγός — τσεκάρετε παραπάνω τι ζυγούς έχει το "
                 "κατάστημα και εδώ θα εμφανιστούν οι ρυθμίσεις του καθενός.")

        # ======== T-Scale ========
        self.blk_tscale = self._block(
            self.blocks, "⚖  Ζυγοί T-Scale — αρχείο product.csv",
            "Τι στέλνεται στον ζυγό και από ποια στήλη του ERP: «Πεδία T-Scale». "
            "Το προφίλ είναι το έτοιμο σετ ανά πελάτη.")
        prof = ttk.Frame(self.blk_tscale)
        prof.pack(fill="x", pady=(2, 4))
        ttk.Label(prof, text="Προφίλ:").pack(side="left")
        names = list(self.cfg.get("profiles", {}))
        self.v_profile = tk.StringVar(value=names[0] if names else "")
        self.cmb_profile = ttk.Combobox(prof, textvariable=self.v_profile, values=names,
                                        state="readonly", width=36)
        self.cmb_profile.pack(side="left", padx=6)
        ttk.Button(prof, text="Φόρτωση", command=lambda: self.load_profile(self.v_profile.get())
                   ).pack(side="left")
        ttk.Button(prof, text="Αποθήκευση ως…", command=self.save_profile).pack(side="left", padx=6)
        ttk.Button(prof, text="Διαγραφή", style="Ghost.TButton",
                   command=self.delete_profile).pack(side="left")
        ttk.Button(prof, text="⚖  Πεδία T-Scale…", style="Accent.TButton",
                   command=self.tscale_fields_dialog).pack(side="right")
        g = ttk.Frame(self.blk_tscale)
        g.pack(fill="x", pady=2)
        self.v_s2in = tk.StringVar()
        self.v_s2out = tk.StringVar()
        self._pick_row(g, "Αρχείο εισόδου — άφησέ το κενό:", self.v_s2in, "file", 0)
        self._pick_row(g, "Να δημιουργείται εδώ:", self.v_s2out, "save", 1)
        ttk.Label(self.blk_tscale, style="Hint.TLabel", justify="left", wraplength=920,
                  text="Κενή είσοδος = ό,τι έβγαλε το προηγούμενο βήμα (Βήμα 2, αλλιώς host1). "
                       "Κενή έξοδος = product.csv στον φάκελο εξόδου."
                  ).pack(anchor="w", pady=(0, 2))
        b = ttk.Frame(self.blk_tscale)
        b.pack(fill="x", pady=(4, 0))
        ttk.Label(b, text="Πίνακας πεδίων:").pack(side="left")
        ttk.Button(b, text="Εναλλαγή ✓", command=self.toggle_field).pack(side="left", padx=(8, 0))
        ttk.Button(b, text="Επεξεργασία", command=self.on_edit_cell).pack(side="left", padx=6)
        ttk.Button(b, text="+ Γραμμή", command=self.add_field_row).pack(side="left")
        ttk.Button(b, text="− Αφαίρεση", command=self.remove_field_row).pack(side="left", padx=6)
        ttk.Button(b, text="▲", width=3, command=lambda: self.move_field_row(-1)).pack(side="left")
        ttk.Button(b, text="▼", width=3, command=lambda: self.move_field_row(1)).pack(side="left", padx=(2, 6))
        ttk.Button(b, text="Αρχικοποίηση", style="Ghost.TButton", command=self.reset_fields).pack(side="left")
        ttk.Button(b, text="Δοκιμή · προεπισκόπηση", command=self.preview_csv).pack(side="right")
        tree_box = ttk.Frame(self.blk_tscale)
        tree_box.pack(fill="x", pady=4)
        self.tree_box = tree_box
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

        # ======== Ishida ========
        self.blk_ishida = self._block(
            self.blocks, "Ζυγοί Ishida",
            "Τι ενημερώνεται στον ζυγό: «Πεδία ζυγού Ishida» (τα 118 πεδία του). Το host2 είναι "
            "το ενδιάμεσο αρχείο που φτιάχνουμε από το ERP (τιμή σε λεπτά) και διαβάζει η "
            "απευθείας αποστολή — το ρυθμίζει ο οδηγός, σπάνια με το χέρι.")
        srow = ttk.Frame(self.blk_ishida)
        srow.pack(fill="x")
        if not hasattr(self, "v_s2b"):
            self.v_s2b = tk.BooleanVar(value=False)
        ttk.Checkbutton(srow, text="Φτιάξε το αρχείο της Ishida", variable=self.v_s2b).pack(side="left")
        ttk.Label(srow, text="προφίλ:").pack(side="left", padx=(14, 3))
        self.v_s2b_profile = tk.StringVar()
        self.cmb_s2b = ttk.Combobox(srow, textvariable=self.v_s2b_profile, state="readonly",
                                    width=34, values=list(self.cfg.get("profiles", {})))
        self.cmb_s2b.pack(side="left")
        ttk.Button(srow, text="Στήλες αρχείου host2…", style="Ghost.TButton",
                   command=lambda: self.profile_fields_dialog("ishida")).pack(side="left", padx=(8, 0))
        ttk.Button(srow, text="Τι να ρυθμίσεις στο ScaleLink…", style="Pick.TButton",
                   command=self.ishida_import_settings_dialog).pack(side="left", padx=(6, 0))
        ttk.Button(srow, text="⚖  Πεδία ζυγού Ishida…", style="Accent.TButton",
                   command=self.ishida_scale_fields_dialog).pack(side="left", padx=(6, 0))
        g2 = ttk.Frame(self.blk_ishida)
        g2.pack(fill="x")
        self.v_s2b_out = tk.StringVar()
        self._pick_row(g2, "Να δημιουργείται εδώ:", self.v_s2b_out, "save", 0)
        ttk.Label(self.blk_ishida, style="Hint.TLabel", text="Κενή διαδρομή = host2.csv στον φάκελο εξόδου."
                  ).pack(anchor="w", pady=(2, 0))

        # ======== ILS ========
        self.blk_ils = self._block(
            self.blocks, "Ζυγοί ILS1100 — αρχείο hostILS (σταθερού πλάτους)",
            "Το ILS διαβάζει το αρχείο με τις θέσεις του «Field settings» (AutoTrans.CFG). "
            "Με το κουμπί βλέπεις τι πρέπει να λέει για το προφίλ και το γράφεις στο CFG του "
            "πελάτη (με αντίγραφο).")
        trow = ttk.Frame(self.blk_ils)
        trow.pack(fill="x")
        if not hasattr(self, "v_s2c"):
            self.v_s2c = tk.BooleanVar(value=False)
        ttk.Checkbutton(trow, text="Φτιάξε το αρχείο του ILS", variable=self.v_s2c).pack(side="left")
        ttk.Label(trow, text="προφίλ:").pack(side="left", padx=(14, 3))
        self.v_s2c_profile = tk.StringVar()
        self.cmb_s2c = ttk.Combobox(trow, textvariable=self.v_s2c_profile, state="readonly",
                                    width=34, values=list(self.cfg.get("profiles", {})))
        self.cmb_s2c.pack(side="left")
        ttk.Button(trow, text="Πεδία ILS…", style="Accent.TButton",
                   command=lambda: self.profile_fields_dialog("ils")).pack(side="left", padx=(8, 0))
        ttk.Button(trow, text="Field settings (AutoTrans.CFG)…", style="Pick.TButton",
                   command=self.ils_field_settings_dialog).pack(side="left", padx=(6, 0))
        ttk.Button(trow, text="Διάβασε υπάρχον CFG…", style="Ghost.TButton",
                   command=self.ils_profile_from_cfg_dialog).pack(side="left", padx=(4, 0))
        g3 = ttk.Frame(self.blk_ils)
        g3.pack(fill="x")
        self.v_s2c_out = tk.StringVar()
        self._pick_row(g3, "Να δημιουργείται εδώ:", self.v_s2c_out, "save", 0)
        ttk.Label(self.blk_ils, style="Hint.TLabel", text="Κενή διαδρομή = hostILS.csv στον φάκελο εξόδου."
                  ).pack(anchor="w", pady=(2, 0))

        self.v_s2c.trace_add("write", lambda *_a: self._refresh_tab2_blocks())

    def _refresh_tab2_blocks(self):
        """Δείχνει μόνο τα μπλοκ των ζυγών που έχει το κατάστημα (Βήμα 4)."""
        if not hasattr(self, "v_tscale_on") or not hasattr(self, "blocks"):
            return
        for w in self.blocks.winfo_children():
            w.pack_forget()
        shown = 0
        if self.v_tscale_on.get():
            self.blk_tscale.pack(fill="x"); shown += 1
        if self.v_ish_on.get():
            self.blk_ishida.pack(fill="x"); shown += 1
        # Το ILS δεν έχει «έχει ζυγούς» στο Βήμα 4: φαίνεται αν είναι τσεκαρισμένο
        # το αρχείο του, αλλιώς ως μία γραμμή για να μπορεί να ενεργοποιηθεί.
        self.blk_ils.pack(fill="x"); shown += 1
        for w in self.blk_ils.winfo_children()[2:]:
            if self.v_s2c.get():
                w.pack(fill="x")
            else:
                w.pack_forget()
        if not self.v_s2c.get():
            self.blk_ils.winfo_children()[3].pack(fill="x")   # η γραμμή με το τσεκ μένει
        if not (self.v_tscale_on.get() or self.v_ish_on.get()):
            self.lbl_no_scales.pack(anchor="w", pady=6, before=self.blk_ils)

    def _build_tab3(self):
        f = self.tab3
        self.v_s3 = tk.BooleanVar()
        ttk.Checkbutton(f, style="Big.TCheckbutton",
                        text="Ενεργοποίηση Βήματος 4 — Αποστολή στους ζυγούς",
                        variable=self.v_s3).pack(anchor="w")
        ttk.Label(f, style="Hint.TLabel", justify="left", wraplength=920,
                  text="Στέλνει το ίδιο το πρόγραμμα, στο παρασκήνιο, χωρίς να ανοίγει "
                       "τίποτα άλλο. Γράψε τις IP των ζυγών και τελείωσες — παίρνεις "
                       "πραγματική επιβεβαίωση για κάθε ζυγό ξεχωριστά."
                  ).pack(anchor="w", pady=(0, 8))

        # ---------------- T-Scale ----------------
        if not hasattr(self, "v_tscale_on"):
            self.v_tscale_on = tk.BooleanVar(value=True)
        ttk.Checkbutton(f, text="Το κατάστημα έχει ζυγούς T-Scale",
                        variable=self.v_tscale_on, style="Big.TCheckbutton",
                        command=self.on_marka_toggle).pack(anchor="w")
        ipf = ttk.Frame(f)
        ipf.pack(fill="x", pady=(2, 0))
        ttk.Label(ipf, text="IP ζυγών:").pack(side="left")
        self.v_ips = tk.StringVar()
        self.e_ips = self._add_edit_menu(ttk.Entry(ipf, textvariable=self.v_ips, width=40))
        self.e_ips.pack(side="left", padx=6)
        self.btn_save_ips = ttk.Button(ipf, text="Αποθήκευση IP", style="Accent.TButton",
                                       command=self.save_ips)
        self.btn_save_ips.pack(side="left")
        ttk.Label(f, style="Hint.TLabel", justify="left", wraplength=920,
                  text="Χωρισμένες με κόμμα (π.χ. 10.130.20.49, 10.130.20.46). "
                       "Αποθηκεύονται αυτόματα και πριν από κάθε εκτέλεση."
                  ).pack(anchor="w", pady=(4, 10))

        # ---------------- Ishida UNI-3 ----------------
        if not hasattr(self, "v_ish_on"):
            self.v_ish_on = tk.BooleanVar(value=False)
        ttk.Checkbutton(f, text="Το κατάστημα έχει ζυγούς Ishida UNI-3",
                        variable=self.v_ish_on, style="Big.TCheckbutton",
                        command=self.on_marka_toggle).pack(anchor="w")
        self.v_ish_direct = tk.BooleanVar(value=True)
        self.v_ish_ips = tk.StringVar()
        self.v_ish_cents = tk.BooleanVar(value=True)
        ishf = ttk.Frame(f)
        ishf.pack(fill="x", pady=(2, 0))
        ttk.Label(ishf, text="IP ζυγών:").pack(side="left")
        self.e_ish_ips = self._add_edit_menu(
            ttk.Entry(ishf, textvariable=self.v_ish_ips, width=40))
        self.e_ish_ips.pack(side="left", padx=6)
        self.chk_ish_cents = ttk.Checkbutton(
            ishf, text="Η τιμή στο αρχείο είναι ήδη σε λεπτά (540 = 5,40 €)",
            variable=self.v_ish_cents)
        self.chk_ish_cents.pack(side="left", padx=10)

        bcf = ttk.Frame(f)
        bcf.pack(fill="x", pady=(6, 0))
        ttk.Label(bcf, text="Μορφή barcode:").pack(side="left")
        self.v_ish_bc = tk.StringVar(value=ishida_barcode_label(ISHIDA_BC_KEEP))
        self.cmb_ish_bc = ttk.Combobox(
            bcf, textvariable=self.v_ish_bc, width=44, state="readonly",
            values=[ishida_barcode_label(ISHIDA_BC_KEEP)] +
                   [ishida_barcode_label(n) for n, _p in ISHIDA_BARCODE_FORMATS])
        self.cmb_ish_bc.pack(side="left", padx=6)
        self.v_ish_bc_code = tk.BooleanVar(value=False)
        self.chk_ish_bc_code = ttk.Checkbutton(
            bcf, text="και ο κωδικός του είδους μέσα στο barcode",
            variable=self.v_ish_bc_code)
        self.chk_ish_bc_code.pack(side="left", padx=10)

        nmf = ttk.Frame(f)
        nmf.pack(fill="x", pady=(6, 0))
        self.v_ish_names = tk.BooleanVar(value=True)
        self.chk_ish_names = ttk.Checkbutton(
            nmf, text="Ενημέρωσε και τα ονόματα, όταν αλλάξουν στο ERP",
            variable=self.v_ish_names)
        self.chk_ish_names.pack(side="left")
        ttk.Label(f, style="Hint.TLabel", justify="left", wraplength=920,
                  text="Αλλάζει μόνο το όνομα που είναι όντως διαφορετικό από του ERP· τα "
                       "υπόλοιπα μένουν όπως τα έχει ο ζυγός. Η μορφοποίηση της ετικέτας "
                       "(μέγεθος γραμμάτων, συστατικά κάτω από το όνομα) κρατιέται."
                  ).pack(anchor="w", pady=(2, 4))
        # Η λύση για το «too many characters for print»: τα ονόματα σπάνε σε γραμμές
        # τόσων χαρακτήρων όσους χωράει η ετικέτα. Ξεχωριστή, ευδιάκριτη γραμμή —
        # είναι η ρύθμιση που έσωσε τον ERGON και την ψάχνει κάθε τεχνικός.
        wf = ttk.Frame(f)
        wf.pack(fill="x", pady=(2, 0))
        tk.Label(wf, text="Χαρακτήρες ανά γραμμή ετικέτας:", bg=COLORS["card"], fg=COLORS["ink"],
                 font=FONTS["base_bold"]).pack(side="left")
        self.v_ish_width = tk.StringVar(value="25")
        self.e_ish_width = ttk.Spinbox(wf, from_=10, to=40, width=4, textvariable=self.v_ish_width)
        self.e_ish_width.pack(side="left", padx=8)
        self.lbl_ish_width = tk.Label(wf, text="", bg=COLORS["card"], fg=COLORS["warn"],
                                      font=FONTS["sm_bold"])
        self.lbl_ish_width.pack(side="left")
        ttk.Label(f, style="Hint.TLabel", justify="left", wraplength=920,
                  text="Αν ο ζυγός γράφει στην οθόνη του «too many characters for print», ΕΔΩ είναι η "
                       "ρύθμιση: χαμήλωσε τον αριθμό. ERGON: 25 (η γραμματοσειρά C25 της ετικέτας "
                       "χωράει 25· με 30 έβγαζε το μήνυμα). Τα ονόματα σπάνε μόνα τους σε γραμμές "
                       "τόσων χαρακτήρων και όσα δεν χωράνε ξαναχωρίζονται στην επόμενη αποστολή."
                  ).pack(anchor="w", pady=(2, 4))

        def _width_note(*_a):
            try:
                n = int(self.v_ish_width.get())
            except ValueError:
                n = 0
            self.lbl_ish_width.configure(
                text="" if n == 25 else ("← ERGON: 25" if 10 <= n <= 40 else "← 10 έως 40"))
        self.v_ish_width.trace_add("write", _width_note)

        crf = ttk.Frame(f)
        crf.pack(fill="x", pady=(6, 0))
        self.v_ish_create = tk.BooleanVar(value=False)
        self.chk_ish_create = ttk.Checkbutton(
            crf, text="Γράψε και τα προϊόντα που λείπουν από τον ζυγό",
            variable=self.v_ish_create)
        self.chk_ish_create.pack(side="left")
        ttk.Label(f, style="Hint.TLabel", justify="left", wraplength=920,
                  text="Σε ΑΔΕΙΑ ζυγαριά — καινούργια, ή μόλις σβήστηκαν τα προϊόντα της "
                       "— γράφονται όλα από την αρχή χωρίς να χρειάζεται αυτό το τικ: "
                       "δεν υπάρχει τίποτα να χαλάσει.\n"
                       "Τσέκαρέ το μόνο για ζυγαριά που ΕΧΕΙ ήδη προϊόντα και θέλεις να "
                       "μπουν και τα καινούργια του αρχείου. Το όνομα και ο ΦΠΑ έρχονται "
                       "από το αρχείο, και τα υπόλοιπα αντιγράφονται από προϊόν που έχει "
                       "ήδη ο ζυγός — ώστε οι ετικέτες να βγαίνουν όπως οι υπόλοιπες."
                  ).pack(anchor="w", pady=(4, 10))
        ttk.Label(f, style="Hint.TLabel", justify="left", wraplength=920,
                  text="Η δομή του EAN-13 που τυπώνει ο ζυγός. Κάθε γράμμα είναι μία "
                       "θέση: F σήμανση, C ο κωδικός του είδους, W το βάρος, P η τιμή, "
                       "(C/D) το ψηφίο ελέγχου. Το 16 (FFCCCCCWWWWW) βάζει κωδικό πέντε "
                       "ψηφίων και βάρος πέντε ψηφίων· το 4 βάζει τιμή στη θέση του "
                       "βάρους.\n"
                       "Η προεπιλογή είναι να ΜΗΝ την αλλάζουμε — καθορίζει τι διαβάζει "
                       "το ταμείο από την ετικέτα, και κάθε προϊόν μπορεί να έχει δική "
                       "του. Άλλαξέ την μόνο όταν το ζητάει ο πελάτης."
                  ).pack(anchor="w", pady=(4, 10))
        ttk.Label(f, style="Hint.TLabel", justify="left", wraplength=920,
                  text="Στέλνεται το αρχείο που φτιάχνει το «Φτιάξε και δεύτερο αρχείο» "
                       "στο Βήμα 3, με τις μετατροπές του προφίλ — το ίδιο αρχείο που "
                       "έβγαινε πάντα. Όποτε αλλάζει το αρχείο του ERP, ξαναφτιάχνεται "
                       "και ξαναφεύγει μόνο του.\n"
                       "Αλλάζουν μόνο οι τιμές: τα ονόματα και οι ετικέτες του ζυγού "
                       "μένουν όπως είναι. Καινούργια προϊόντα δεν μπαίνουν μόνα τους — "
                       "αυτά τα περνάει ο τεχνικός."
                  ).pack(anchor="w", pady=(4, 10))

        ergaleia = ttk.Frame(f)
        ergaleia.pack(fill="x", pady=(2, 2))
        self.btn_scan = ttk.Button(ergaleia, text="🔍  Αυτόματη εύρεση ζυγαριών",
                                   style="Accent.TButton", command=self.scan_scales_now)
        self.btn_scan.pack(side="left")
        ttk.Button(ergaleia, text="Ποιες ζυγαριές είναι ανοιχτές",
                   command=self.show_scale_status).pack(side="left", padx=8)
        ttk.Label(f, style="Hint.TLabel", justify="left", wraplength=920,
                  text="Η αυτόματη εύρεση ψάχνει όλο το δίκτυο του μηχανήματος και "
                       "ξεχωρίζει μόνη της ποιος ζυγός είναι T-Scale και ποιος Ishida "
                       "— κάθε μάρκα ακούει σε δική της θύρα. Κρατάει λίγα δευτερόλεπτα "
                       "και δεν στέλνει τίποτα στους ζυγούς."
                  ).pack(anchor="w", pady=(4, 8))

        ttk.Separator(f, orient="horizontal").pack(fill="x", pady=(2, 8))

        # ---------------- κοινές ρυθμίσεις ----------------
        rebuild = ttk.Frame(f)
        rebuild.pack(fill="x", pady=(2, 0))
        self.v_rebuild = tk.BooleanVar(value=False)
        ttk.Checkbutton(rebuild,
                        text="Ξαναφτιάξε ολόκληρη τη βάση (ονόματα + τιμές)",
                        variable=self.v_rebuild,
                        command=self.on_rebuild_toggle).pack(side="left")
        self.lbl_rebuild = ttk.Label(rebuild, style="Hint.TLabel")
        self.lbl_rebuild.pack(side="left", padx=10)
        ttk.Label(f, style="Hint.TLabel", justify="left", wraplength=920,
                  text="Κανονικά ενημερώνονται ΜΟΝΟ ΟΙ ΤΙΜΕΣ: το πρόγραμμα διαβάζει πρώτα "
                       "τι έχει ο ζυγός και αγγίζει μόνο την τιμή, οπότε τα ελληνικά "
                       "ονόματα μένουν ακριβώς όπως είναι. Τσέκαρέ το μόνο όταν άλλαξαν "
                       "ονόματα ή μπήκαν πολλά νέα προϊόντα — τότε ξαναγράφονται όλα. "
                       "Αφορά μόνο τους T-Scale."
                  ).pack(anchor="w", pady=(0, 4))

        rt = ttk.Frame(f)
        rt.pack(fill="x", pady=(2, 0))
        ttk.Label(rt, text="Αν ένας ζυγός είναι κλειστός, ξαναδοκίμασε κάθε:").pack(side="left")
        self.v_pending_min = tk.StringVar(value="15")
        ttk.Entry(rt, textvariable=self.v_pending_min, width=5).pack(side="left", padx=6)
        ttk.Label(rt, text="λεπτά").pack(side="left")
        self.btn_pending = ttk.Button(rt, text="Δοκιμή τώρα", style="Ghost.TButton",
                                      command=self.retry_pending_now)
        self.btn_pending.pack(side="left", padx=12)
        self.lbl_pending = ttk.Label(rt, style="Hint.TLabel")
        self.lbl_pending.pack(side="left", padx=6)
        ttk.Label(f, style="Hint.TLabel", justify="left", wraplength=920,
                  text="Ο ζυγός που ήταν σβηστός δεν χάνει την ενημέρωση: μένει σε "
                       "εκκρεμότητα και δοκιμάζεται μόνος του ώσπου να ανοίξει — παίρνει "
                       "τότε τις ΤΡΕΧΟΥΣΕΣ τιμές, όχι τις παλιές. Η εκκρεμότητα επιβιώνει "
                       "ακόμα κι αν κλείσει το πρόγραμμα ή πέσει το ρεύμα."
                  ).pack(anchor="w", pady=(0, 4))

        katal = ttk.Frame(f)
        katal.pack(fill="x", pady=(2, 0))
        self.v_fullcat = tk.BooleanVar(value=False)
        self.chk_fullcat = ttk.Checkbutton(
            katal, text="Το αρχείο του ERP περιέχει ΟΛΑ τα προϊόντα",
            variable=self.v_fullcat, command=self.on_rebuild_toggle)
        self.chk_fullcat.pack(side="left")
        ttk.Label(f, style="Hint.TLabel", justify="left", wraplength=920,
                  text="Ρώτα τον πελάτη: το ERP βγάζει κάθε φορά ολόκληρο τον κατάλογο, ή "
                       "μόνο όσα άλλαξαν; Μετράει ΜΟΝΟ στην πλήρη ανακατασκευή: αν βγάζει "
                       "ολόκληρο τον κατάλογο, όσα λείπουν θεωρούνται καταργημένα και "
                       "απενεργοποιούνται. Αν βγάζει μόνο τις αλλαγές, ΑΦΗΣΕ ΤΟ ΚΕΝΟ — "
                       "αλλιώς όσα δεν άλλαξαν θα έμοιαζαν καταργημένα."
                  ).pack(anchor="w", pady=(0, 4))

        # ---------------- για προχωρημένους ----------------
        ttk.Separator(f, orient="horizontal").pack(fill="x", pady=(10, 8))
        bar3m = ttk.Frame(f)
        bar3m.pack(fill="x")
        self.btn_adv3m = ttk.Button(bar3m, text="⚙  Για προχωρημένους  ▾",
                                    style="Ghost.TButton", command=self.toggle_adv3m)
        self.btn_adv3m.pack(side="left")
        ttk.Label(bar3m, style="Hint.TLabel",
                  text="ο παλιός τρόπος, μέσα από τα προγράμματα των κατασκευαστών"
                  ).pack(side="left", padx=8)

        self.adv3m = ttk.Frame(f)
        ttk.Label(self.adv3m, style="Hint.TLabel", justify="left", wraplength=920,
                  text="ΔΕΝ χρειάζεται σε κανονική εγκατάσταση. Είναι ο παλιός τρόπος: "
                       "αντί να στείλουμε εμείς, ανοίγει το πρόγραμμα του κατασκευαστή "
                       "για λίγα δευτερόλεπτα και στέλνει εκείνο. Άσε τα κλειστά εκτός "
                       "αν κάτι δεν δουλεύει με τον κανονικό τρόπο."
                  ).pack(anchor="w", pady=(4, 8))

        direct = ttk.Frame(self.adv3m)
        direct.pack(fill="x", pady=(0, 2))
        self.v_direct = tk.BooleanVar(value=True)
        ttk.Checkbutton(direct, text="Απευθείας αποστολή στους T-Scale (κανονικά ανοιχτό)",
                        variable=self.v_direct, command=self.on_direct_toggle,
                        style="Big.TCheckbutton").pack(side="left")
        self.lbl_direct = ttk.Label(direct, style="Hint.TLabel")
        self.lbl_direct.pack(side="left", padx=10)
        ttk.Label(self.adv3m, style="Hint.TLabel", justify="left", wraplength=920,
                  text="Ξε-τσέκαρέ το μόνο για να ξαναδουλέψει μέσω του προγράμματος "
                       "T-Scale του κατασκευαστή, με τις ρυθμίσεις από κάτω."
                  ).pack(anchor="w", pady=(0, 6))

        g = ttk.Frame(self.adv3m)
        g.pack(fill="x", pady=4)
        self.v_s3exe = tk.StringVar()
        self._pick_row(g, "Πρόγραμμα T-Scale του κατασκευαστή:", self.v_s3exe, "exe", 0)

        bundled = ttk.Frame(self.adv3m)
        bundled.pack(fill="x", pady=(4, 0))
        self.btn_bundled = ttk.Button(bundled, text="Εύρεση δίπλα στο πρόγραμμα",
                                      command=self.use_bundled_autoprocess)
        self.btn_bundled.pack(side="left")
        self.lbl_bundled = ttk.Label(bundled, style="Hint.TLabel")
        self.lbl_bundled.pack(side="left", padx=10)

        loadipf = ttk.Frame(self.adv3m)
        loadipf.pack(fill="x", pady=(6, 0))
        ttk.Button(loadipf, text="Ανάγνωση IP από το πρόγραμμα T-Scale",
                   style="Ghost.TButton", command=self.load_ips).pack(side="left")
        ttk.Label(self.adv3m, style="Hint.TLabel", justify="left", wraplength=920,
                  text="Οι IP γράφονται στο ip.xml δίπλα του — δεν χρειάζεται να το "
                       "ανοίξεις με το χέρι."
                  ).pack(anchor="w", pady=(2, 0))

        r = ttk.Frame(self.adv3m)
        r.pack(fill="x", pady=(8, 0))
        self.v_s3sec = tk.StringVar(value="120")
        self.v_s3kill = tk.BooleanVar(value=True)
        ttk.Label(r, text="Διάρκεια (δευτερόλεπτα):").pack(side="left")
        ttk.Entry(r, textvariable=self.v_s3sec, width=7).pack(side="left", padx=6)
        ttk.Checkbutton(r, text="Κλείσε το αυτόματα όταν περάσει ο χρόνος",
                        variable=self.v_s3kill).pack(side="left", padx=12)

        ttk.Separator(self.adv3m, orient="horizontal").pack(fill="x", pady=(12, 8))
        ttk.Label(self.adv3m, text="Άλλοι ζυγοί, μέσα από το δικό τους πρόγραμμα",
                  style="Big.TCheckbutton").pack(anchor="w")
        ttk.Label(self.adv3m, style="Hint.TLabel", justify="left", wraplength=920,
                  text="Για ζυγούς που δεν τους στέλνουμε εμείς. Οι Ishida UNI-3 δεν "
                       "χρειάζονται τίποτα από εδώ — μπαίνουν πάνω, με την IP τους."
                  ).pack(anchor="w", pady=(2, 6))
        self.adv4 = ttk.Frame(self.adv3m)
        self.adv4.pack(fill="x")
        self.v_extra = {}
        for key, label in EXTRA_SENDERS:
            self._build_extra_sender(self.adv4, key, label)

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

    def toggle_adv1(self):
        if self.adv1.winfo_ismapped():
            self.adv1.grid_remove()
            self.btn_adv1.configure(text="⚙  Περισσότερα  ▾")
        else:
            self.adv1.grid(row=5, column=0, columnspan=3, sticky="we", pady=(4, 0))
            self.btn_adv1.configure(text="⚙  Περισσότερα  ▴")

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
        # Το σφάλμα το δείχνει η μπάρα, όχι παράθυρο που περιμένει «ΟΚ»:
        # μπορεί να άνοιξε το παράθυρο κάποιος που περνούσε, όχι ο τεχνικός.
        err = getattr(self, "pending_error", None)
        if err:
            self.show_error_bar(err)

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
        if getattr(self, "v_accept_beta", None) is not None:
            self.v_accept_beta.set(bool(c.get("accept_beta", False)))
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
        self.v_s2b.set(bool(c.get("step2b_enabled", False)))
        self.cmb_s2b.configure(values=list(c.get("profiles", {})))
        saved_p = c.get("step2b_profile", "")
        self.v_s2b_profile.set(resolve_profile(c.get("profiles", {}), saved_p)[0] if saved_p else "")
        self.v_s2b_out.set(c.get("step2b_output", ""))
        self.v_s2c.set(bool(c.get("step2c_enabled", False)))
        self.cmb_s2c.configure(values=list(c.get("profiles", {})))
        self.v_s2c_profile.set(c.get("step2c_profile", ""))
        self.v_s2c_out.set(c.get("step2c_output", ""))
        self.v_finalnl.set(bool(c.get("step2_final_newline", True)))
        self.v_s3.set(bool(c.get("step3_enabled", True)))
        self.v_s3exe.set(c.get("step3_exe", ""))
        self.v_s3sec.set(str(c.get("step3_seconds", 120)))
        self.v_s3kill.set(bool(c.get("step3_kill", True)))
        self.v_ips.set(c.get("scale_ips", "") or ", ".join(read_ips(c.get("step3_exe", ""))))
        self.v_direct.set(bool(c.get("direct_send", True)))
        self.v_ish_ips.set(c.get("ishida_ips", ""))
        self.v_ish_cents.set(bool(c.get("ishida_price_cents", True)))
        self.v_ish_bc.set(ishida_barcode_label(int(c.get("ishida_barcode", ISHIDA_BC_KEEP))))
        self.v_ish_bc_code.set(bool(c.get("ishida_barcode_code", False)))
        self.v_ish_create.set(bool(c.get("ishida_create", False)))
        self.v_ish_names.set(bool(c.get("ishida_update_names", True)))
        self.v_ish_width.set(str(c.get("ishida_name_width", 25)))
        # Παλιές ρυθμίσεις δεν έχουν τα τικ: τα συμπεραίνουμε από το αν είχαν IP,
        # ώστε να μη «σβήσει» ξαφνικά η αποστολή σε όποιον έχει ήδη στήσει ζυγούς.
        self.v_tscale_on.set(bool(c.get("tscale_on", bool(parse_ips(c.get("scale_ips", ""))))))
        self.v_ish_on.set(bool(c.get("ishida_on", bool(parse_ips(c.get("ishida_ips", ""))))))
        self.on_marka_toggle()
        self.v_rebuild.set(bool(c.get("direct_rebuild", False)))
        self.v_fullcat.set(bool(c.get("erp_full_catalog", False)))
        self.v_pending_min.set(str(c.get("pending_retry_minutes", 15)))
        self.refresh_pending_hint()
        self.on_rebuild_toggle()
        self.on_direct_toggle()
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
            self.after(600, lambda: self.toggle_watch(quiet=True))

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
        if getattr(self, "v_accept_beta", None) is not None:
            c["accept_beta"] = bool(self.v_accept_beta.get())
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
        c["step2b_enabled"] = self.v_s2b.get()
        c["step2b_profile"] = self.v_s2b_profile.get()
        c["step2b_output"] = self.v_s2b_out.get().strip()
        c["step2c_enabled"] = self.v_s2c.get()
        c["step2c_profile"] = self.v_s2c_profile.get()
        c["step2c_output"] = self.v_s2c_out.get().strip()
        c["step2_final_newline"] = self.v_finalnl.get()
        c["step3_enabled"] = self.v_s3.get()
        c["step3_exe"] = self.v_s3exe.get().strip()
        try:
            c["step3_seconds"] = max(1, int(self.v_s3sec.get()))
        except ValueError:
            c["step3_seconds"] = 120
        c["step3_kill"] = self.v_s3kill.get()
        c["scale_ips"] = self.v_ips.get().strip()
        c["direct_send"] = self.v_direct.get()
        c["ishida_ips"] = self.v_ish_ips.get().strip()
        c["ishida_price_cents"] = self.v_ish_cents.get()
        keimeno = self.v_ish_bc.get()
        c["ishida_barcode"] = (int(keimeno.split("·")[0].strip())
                               if "·" in keimeno else ISHIDA_BC_KEEP)
        c["ishida_barcode_code"] = self.v_ish_bc_code.get()
        c["ishida_create"] = self.v_ish_create.get()
        c["ishida_update_names"] = self.v_ish_names.get()
        try:
            c["ishida_name_width"] = max(10, min(40, int(self.v_ish_width.get() or 25)))
        except ValueError:
            c["ishida_name_width"] = 25
        c["tscale_on"] = self.v_tscale_on.get()
        c["ishida_on"] = self.v_ish_on.get()
        c["ishida_direct"] = c["ishida_on"] and bool(parse_ips(c["ishida_ips"]))
        c["direct_rebuild"] = self.v_rebuild.get()
        c["erp_full_catalog"] = self.v_fullcat.get()
        try:
            c["pending_retry_minutes"] = max(1, int(self.v_pending_min.get() or 15))
        except ValueError:
            c["pending_retry_minutes"] = 15
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

    def toggle_adv2(self):
        """Δείχνει/κρύβει τις αναλυτικές ρυθμίσεις του Βήματος 3."""
        if self.adv2.winfo_ismapped():
            self.adv2.pack_forget()
            self.btn_adv2.configure(text="⚙  Πώς διαβάζεται το ERP / μορφή αρχείων  ▾")
        else:
            self.adv2.pack(fill="x", pady=(4, 0), before=self.blocks)
            self.btn_adv2.configure(text="⚙  Πώς διαβάζεται το ERP / μορφή αρχείων  ▴")

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

    def add_field_row(self, name=None, select=True):
        """Νέα γραμμή στον πίνακα (κενή ή με όνομα στήλης του ζυγού)."""
        from tkinter import simpledialog
        if name is None:
            name = simpledialog.askstring(APP_NAME, "Όνομα στήλης (π.χ. Tax, REMARK1 — ή ό,τι θες "
                                          "για αρχείο Ishida/ILS):", parent=self)
            if not name or not name.strip():
                return None
            name = name.strip()
        f = {"name": name, "enabled": True, "pos": 0, "len": 0, "extra": "", "xform": "", "align": ""}
        self.cfg.setdefault("step2_fields", []).append(f)
        self.refresh_tree()
        i = len(self.cfg["step2_fields"]) - 1
        if select:
            self.tree.selection_set(str(i))
            self.tree.see(str(i))
        return i

    def remove_field_row(self):
        i = self._sel()
        if i is None:
            return
        f = self.cfg["step2_fields"][i]
        if not messagebox.askyesno(APP_NAME, "Να αφαιρεθεί η γραμμή «%s»;" % f["name"]):
            return
        del self.cfg["step2_fields"][i]
        self.refresh_tree()

    def move_field_row(self, delta):
        i = self._sel()
        if i is None:
            return
        j = i + delta
        fields = self.cfg["step2_fields"]
        if not (0 <= j < len(fields)):
            return
        fields[i], fields[j] = fields[j], fields[i]
        self.refresh_tree()
        self.tree.selection_set(str(j))

    def edit_field_dialog(self, f, parent=None, on_done=None):
        """Το παράθυρο επεξεργασίας ενός πεδίου (κοινό για πίνακα και «Πεδία T-Scale»)."""
        win = tk.Toplevel(parent or self)
        win.title("Πεδίο: %s" % f["name"])
        win.transient(parent or self)
        win.grab_set()
        kat = TSCALE_BY_CSV.get(f.get("name", ""))
        if kat:
            ttk.Label(win, text="%s  →  %s" % (kat[2], kat[1]), style="Hint.TLabel",
                      wraplength=360, justify="left").grid(row=0, column=0, columnspan=2,
                                                            sticky="w", padx=8, pady=(8, 2))
        delimited = self.cfg.get("step2_input_type", "fixed") == "delimited"
        vals = {k: tk.StringVar(value=str(f.get(k, "") or "")) for k in ("name", "pos", "len", "extra", "inlen")}
        en = tk.BooleanVar(value=bool(f.get("enabled")))
        rows = (("name", "Περιγραφή / στήλη"),
                ("pos", "Στήλη του ERP (1 = πρώτη, -1 = τελευταία)" if delimited else "Από Θέση"),
                ("len", "Κόψιμο σε χαρακτήρες (0 = όλο)" if delimited else "Μήκος Πεδίου"),
                ("extra", "Σταθερή τιμή (αν δεν έρχεται από το ERP)"))
        for r, (k, lbl) in enumerate(rows, 1):
            ttk.Label(win, text=lbl).grid(row=r, column=0, sticky="w", padx=8, pady=4)
            ttk.Entry(win, textvariable=vals[k], width=34).grid(row=r, column=1, padx=8, pady=4)
        ttk.Label(win, text="Μετατροπή").grid(row=5, column=0, sticky="w", padx=8, pady=4)
        labels = list(XFORMS.values())
        keys = list(XFORMS.keys())
        xf = tk.StringVar(value=XFORMS.get(f.get("xform", ""), "—"))
        ttk.Combobox(win, textvariable=xf, values=labels, state="readonly",
                     width=32).grid(row=5, column=1, padx=8, pady=4)
        ALIGNS = [("", "αριστερά (προεπιλογή)"), ("right", "δεξιά, με κενά"),
                  ("zero", "δεξιά, με μηδενικά (000009)")]
        al_labels = [lbl for _k, lbl in ALIGNS]
        al_keys = [k for k, _l in ALIGNS]
        al = tk.StringVar(value=dict(ALIGNS).get(f.get("align", ""), al_labels[0]))
        ttk.Label(win, text="Στοίχιση (σταθερό πλάτος):").grid(row=6, column=0, sticky="e", padx=8)
        ttk.Combobox(win, textvariable=al, values=al_labels, state="readonly",
                     width=32).grid(row=6, column=1, sticky="w", padx=8)
        role_labels = [lbl for _k, lbl in ILS_ROLES]
        role_keys = [k for k, _l in ILS_ROLES]
        cur_role = f.get("ils")
        if cur_role is None:
            cur_role = guess_ils_role(f.get("name"), {x.get("ils") for x in self.cfg["step2_fields"]
                                                       if x is not f and x.get("ils")})
        rl = tk.StringVar(value=ILS_ROLE_LABEL.get(cur_role, role_labels[0]))
        ttk.Label(win, text="Πεδίο ILS (Field settings):").grid(row=7, column=0, sticky="e", padx=8)
        ttk.Combobox(win, textvariable=rl, values=role_labels, state="readonly",
                     width=32).grid(row=7, column=1, sticky="w", padx=8)
        ttk.Checkbutton(win, text="Για έξοδο σε αρχείο / αποστολή", variable=en).grid(
            row=8, column=1, sticky="w", padx=8)
        if not delimited:
            ttk.Label(win, text="Μήκος στο ERP (αν διαφέρει από το Μήκος Πεδίου):").grid(
                row=10, column=0, sticky="w", padx=8, pady=4)
            ttk.Entry(win, textvariable=vals["inlen"], width=8).grid(row=10, column=1, sticky="w", padx=8)

        def ok():
            try:
                f["pos"] = int(vals["pos"].get() or 0)
                f["len"] = int(vals["len"].get() or 0)
                f["inlen"] = int(vals["inlen"].get() or 0)
                if not f["inlen"]:
                    f.pop("inlen", None)
            except ValueError:
                messagebox.showerror(APP_NAME, "Η Θέση και το Μήκος πρέπει να είναι αριθμοί.", parent=win)
                return
            f["name"] = vals["name"].get().strip() or f["name"]
            f["extra"] = vals["extra"].get()
            f["enabled"] = en.get()
            f["xform"] = keys[labels.index(xf.get())] if xf.get() in labels else ""
            f["align"] = al_keys[al_labels.index(al.get())] if al.get() in al_labels else ""
            f["ils"] = role_keys[role_labels.index(rl.get())] if rl.get() in role_labels else ""
            win.destroy()
            if on_done:
                on_done()
        ttk.Button(win, text="Καταχώρηση", command=ok).grid(row=11, column=1, sticky="e", padx=8, pady=10)
        win.wait_window()

    def tscale_fields_dialog(self):
        """«Πεδία T-Scale» — το παλιό «Παράμετροι», μοντέρνο: όλα τα 40 πεδία του ζυγού.

        Ο τεχνικός τσεκάρει τι στέλνεται στον συγκεκριμένο πελάτη και ορίζει από
        ποια στήλη/θέση του ERP γεμίζει το καθένα. Ό,τι τσεκάρει μπαίνει στον
        πίνακα του Βήματος 3 — ο πίνακας είναι η αλήθεια, αυτό είναι η θέα του.
        """
        self.collect()
        win = tk.Toplevel(self)
        win.title("Πεδία T-Scale — τι στέλνεται στον ζυγό")
        win.transient(self)
        win.geometry("1160x740")
        win.minsize(920, 560)
        # Η μπάρα κουμπιών ΠΡΩΤΗ, κάτω: αλλιώς ο πίνακας που «απλώνει» την έσπρωχνε
        # έξω από το παράθυρο και δεν φαινόταν η «Καταχώρηση».
        bar = ttk.Frame(win, style="Bar.TFrame", padding=(10, 8))
        bar.pack(fill="x", side="bottom")
        top = ttk.Frame(win, style="Card.TFrame", padding=(10, 8))
        top.pack(fill="both", expand=True)
        ttk.Label(top, text="Πεδία T-Scale", style="Title.TLabel").pack(anchor="w")
        delimited = self.cfg.get("step2_input_type", "fixed") == "delimited"
        ttk.Label(top, style="Hint.TLabel", wraplength=960, justify="left",
                  text="Τσέκαρε (κλικ στο ✓ ή Space) ποια πεδία θα στέλνονται στον ζυγό και με "
                       "διπλό κλικ όρισε από πού γεμίζει το καθένα: %s, ή σταθερή τιμή. "
                       "Τα «βασικά» είναι όσα έστελνε και το AutoProcess· τα υπόλοιπα τα δέχεται "
                       "ο ζυγός κανονικά. Πεδίο χωρίς στήλη και χωρίς σταθερή τιμή στέλνεται κενό."
                       % ("στήλη του ERP" if delimited else "θέση/μήκος στη γραμμή του ERP")
                  ).pack(anchor="w", pady=(2, 6))
        cols = ("out", "csv", "desc", "pos", "len", "extra", "xform", "kind")
        tv = ttk.Treeview(top, columns=cols, show="headings", selectmode="browse", height=22)
        for c, t, w in (("out", "Στέλνεται", 80), ("csv", "Πεδίο", 135), ("desc", "Περιγραφή", 330),
                        ("pos", "Στήλη" if delimited else "Από Θέση", 75),
                        ("len", "Κόψιμο" if delimited else "Μήκος", 65), ("extra", "Σταθερή τιμή", 100),
                        ("xform", "Μετατροπή", 180), ("kind", "", 80)):
            tv.heading(c, text=t)
            tv.column(c, width=w, minwidth=w, anchor="w", stretch=(c == "desc"))
        sb = ttk.Scrollbar(top, orient="vertical", command=tv.yview)
        tv.configure(yscrollcommand=sb.set)
        tv.pack(side="left", fill="both", expand=True)
        sb.pack(side="left", fill="y")
        tv.tag_configure("off", foreground=COLORS["muted"])
        tv.tag_configure("on", foreground=COLORS["ink"])

        def row_for(csv_name):
            for f in self.cfg["step2_fields"]:
                if f.get("name") == csv_name:
                    return f
            return None

        def fill():
            tv.delete(*tv.get_children())
            for csv_name, _json, desc, _db, basic in TSCALE_FIELDS:
                f = row_for(csv_name)
                on = bool(f and f.get("enabled"))
                tv.insert("", "end", iid=csv_name, tags=("on" if on else "off",), values=(
                    "✓" if on else "—", csv_name, desc,
                    (f.get("pos") or "—") if f else "—", (f.get("len") or "—") if f else "—",
                    f.get("extra", "") if f else "", XFORMS.get(f.get("xform", ""), "—") if f else "—",
                    "βασικό" if basic else "επιπλέον"))
            alla = [f for f in self.cfg["step2_fields"] if f.get("name") not in TSCALE_BY_CSV]
            if alla:
                tv.insert("", "end", iid="__alla__", values=("", "", "— άλλες γραμμές του πίνακα "
                          "(δεν είναι πεδία T-Scale, π.χ. για Ishida/ILS): %s"
                          % ", ".join(f["name"] for f in alla), "", "", "", "", ""), tags=("off",))

        def ensure(csv_name):
            f = row_for(csv_name)
            if f is None:
                f = {"name": csv_name, "enabled": False, "pos": 0, "len": 0, "extra": "",
                     "xform": "", "align": ""}
                self.cfg["step2_fields"].append(f)
            return f

        def toggle(_e=None):
            sel = tv.selection()
            if not sel or sel[0] == "__alla__":
                return
            f = ensure(sel[0])
            f["enabled"] = not f.get("enabled")
            if f["enabled"] and not TSCALE_BY_CSV[sel[0]][4]:
                self.cfg["direct_all_fields"] = True
            fill()
            tv.selection_set(sel[0])

        def edit(_e=None):
            sel = tv.selection()
            if not sel or sel[0] == "__alla__":
                return
            f = ensure(sel[0])

            def done():
                if f.get("enabled") and not TSCALE_BY_CSV[sel[0]][4]:
                    self.cfg["direct_all_fields"] = True
                fill()
                tv.selection_set(sel[0])
            self.edit_field_dialog(f, parent=win, on_done=done)

        def click(e):
            if tv.identify_column(e.x) == "#1" and tv.identify_row(e.y):
                tv.selection_set(tv.identify_row(e.y))
                toggle()
                return "break"
        tv.bind("<Button-1>", click)
        tv.bind("<space>", toggle)
        tv.bind("<Double-1>", edit)

        ttk.Button(bar, text="Εναλλαγή ✓", command=toggle).pack(side="left")
        ttk.Button(bar, text="Επεξεργασία…", command=edit).pack(side="left", padx=6)

        def kleisimo():
            # Αφαιρούμε όσα δεν στέλνονται ΚΑΙ δεν έχουν ρυθμιστεί — να μη γεμίζει
            # ο πίνακας με άδειες γραμμές.
            self.cfg["step2_fields"] = [
                f for f in self.cfg["step2_fields"]
                if f.get("enabled") or f.get("pos") or str(f.get("extra", "")).strip()
                or f.get("name") not in TSCALE_BY_CSV]
            stelnontai = [f["name"] for f in self.cfg["step2_fields"]
                          if f.get("enabled") and f["name"] in TSCALE_BY_CSV]
            self.refresh_tree()
            self.log("Πεδία T-Scale: στέλνονται %d — %s" % (len(stelnontai), ", ".join(stelnontai)))
            win.destroy()
        ttk.Button(bar, text="Καταχώρηση", style="Accent.TButton", command=kleisimo).pack(side="right")
        fill()
        win.wait_window()

    def on_edit_cell(self, _event=None):
        i = self._sel()
        if i is None:
            return
        f = self.cfg["step2_fields"][i]
        self.edit_field_dialog(f, on_done=lambda: (self.refresh_tree(), self.tree.selection_set(str(i))))

    def load_profile(self, name):
        """Έτοιμο σετ θέσεων/μηκών για γνωστό τύπο αρχείου."""
        profiles = self.cfg.get("profiles", {})     # ενσωματωμένα + του τεχνικού
        name, _entry = resolve_profile(profiles, name)
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
        self.cmb_s2b.configure(values=names)
        self.cmb_s2c.configure(values=names)
        if select and select in names:
            self.v_profile.set(select)

    def _confirm_text(self, title, lines, yes="Αποθήκευση", no="Άκυρο"):
        """Ερώτηση ναι/όχι με μονοδιάστατο κείμενο (για πίνακες που θέλουν στοίχιση)."""
        win = tk.Toplevel(self)
        win.title(title)
        win.transient(self)
        win.grab_set()
        txt = tk.Text(win, width=max(60, min(110, max(len(l) for l in lines) + 2)),
                      height=min(32, len(lines) + 1), font=FONTS["mono"], wrap="none",
                      bg=COLORS["card"], fg=COLORS["ink"], relief="flat", padx=14, pady=12)
        txt.insert("1.0", "\n".join(lines))
        txt.configure(state="disabled")
        txt.pack(fill="both", expand=True, padx=10, pady=(10, 4))
        answer = {"ok": False}
        bar = ttk.Frame(win)
        bar.pack(fill="x", padx=10, pady=(0, 10))

        def ok():
            answer["ok"] = True
            win.destroy()
        ttk.Button(bar, text=yes, command=ok).pack(side="right")
        if no:
            ttk.Button(bar, text=no, style="Ghost.TButton", command=win.destroy).pack(side="right", padx=8)
        win.wait_window()
        return answer["ok"]

    def profile_fields_dialog(self, which):
        """«Πεδία ILS» / «Πεδία Ishida»: ο πίνακας πεδίων του προφίλ του αντίστοιχου αρχείου.

        Ό,τι είναι ο πίνακας του Βήματος 3 για την T-Scale, είναι αυτό για τα
        άλλα αρχεία: σειρά πεδίων, από πού γεμίζουν, μήκη (ILS: θέσεις στη
        γραμμή, ρόλος για το Field settings). Δουλεύει πάνω σε ΔΙΚΟ ΜΑΣ προφίλ
        (★)· ένα ενσωματωμένο αντιγράφεται πρώτα, για να μείνει άθικτο.
        """
        self.collect()
        is_ils = which == "ils"
        var_prof = self.v_s2c_profile if is_ils else self.v_s2b_profile
        key = "step2c_profile" if is_ils else "step2b_profile"
        title = ("Πεδία ILS — αρχείο hostILS" if is_ils
                 else "Στήλες του αρχείου host2 (ενδιάμεσο αρχείο, ΟΧΙ τα πεδία του ζυγού)")
        name = var_prof.get().strip()
        _n, entry = resolve_profile(self.cfg.get("profiles") or {}, name) if name else ("", None)
        if not entry:
            messagebox.showinfo(APP_NAME, "Διάλεξε πρώτα προφίλ για το αρχείο %s (ή φτιάξε με τον οδηγό)."
                                % ("ILS" if is_ils else "της Ishida"))
            return
        if not name.startswith("★ "):
            # ενσωματωμένο: αντίγραφο ως δικό μας, για να μπορεί να αλλάξει
            from tkinter import simpledialog
            neo = simpledialog.askstring(
                APP_NAME, "Το «%s» είναι ενσωματωμένο και δεν αλλάζει.\nΌνομα για δικό σου αντίγραφο "
                "(π.χ. πελάτης · %s):" % (name, "ILS" if is_ils else "Ishida"),
                initialvalue="%s · %s" % ("ΠΕΛΑΤΗΣ", "ILS" if is_ils else "Ishida"), parent=self)
            if not neo or not neo.strip():
                return
            neo = neo.strip().replace("★", "").strip()
            user = load_user_profiles()
            user[neo] = {"settings": dict(entry.get("settings", {})) if isinstance(entry, dict) else {},
                         "fields": [dict(f) for f in (entry.get("fields", entry) if isinstance(entry, dict) else entry)]}
            save_user_profiles(user)
            self.cfg["profiles"]["★ " + neo] = user[neo]
            self.refresh_profiles()
            name = "★ " + neo
            var_prof.set(name)
            self.cfg[key] = name
            entry = user[neo]
        fields = entry.get("fields", entry) if isinstance(entry, dict) else entry
        settings = entry.get("settings", {}) if isinstance(entry, dict) else {}
        fixed = settings.get("step2_format") == "fixed"
        work = [dict(f) for f in fields]

        win = tk.Toplevel(self)
        win.title(title)
        win.transient(self)
        win.geometry("1160x700")
        win.minsize(920, 560)
        bar = ttk.Frame(win, style="Bar.TFrame", padding=(10, 8))
        bar.pack(fill="x", side="bottom")
        top = ttk.Frame(win, style="Card.TFrame", padding=(10, 8))
        top.pack(fill="both", expand=True)
        ttk.Label(top, text="%s   —   προφίλ %s" % (title, name), style="Title.TLabel").pack(anchor="w")
        ttk.Label(top, style="Hint.TLabel", wraplength=1080, justify="left",
                  text=("Κάθε γραμμή = ένα κομμάτι της γραμμής του αρχείου, με τη σειρά. Οι θέσεις "
                        "βγαίνουν από τα μήκη. Διπλό κλικ: από ποια στήλη του ERP γεμίζει, μήκος, "
                        "μηδενικά μπροστά, και «Πεδίο ILS» για το Field settings." if fixed else
                        "Αυτό είναι το ενδιάμεσο αρχείο που φτιάχνουμε από το ERP, όχι ο ζυγός — τα 118 "
                        "πεδία του ζυγού είναι στο «Πεδία ζυγού Ishida». Κάθε γραμμή εδώ = μία στήλη του "
                        "αρχείου, με τη σειρά. Η απευθείας αποστολή Ishida "
                        "διαβάζει: κωδικός 1η στήλη, όνομα 2η, τιμή 3η από το τέλος, ΦΠΑ τελευταία.")
                  ).pack(anchor="w", pady=(2, 6))
        cols = ("n", "pos", "name", "src", "len", "xform", "role")
        tv = ttk.Treeview(top, columns=cols, show="headings", selectmode="browse", height=18)
        heads = (("n", "#", 40), ("pos", "ΘΕΣΕΙΣ" if fixed else "ΣΤΗΛΗ", 90), ("name", "Πεδίο", 170),
                 ("src", "Γεμίζει από", 260), ("len", "Μήκος" if fixed else "Κόψιμο", 70),
                 ("xform", "Μετατροπή", 230), ("role", "Πεδίο ILS" if fixed else "", 200 if fixed else 10))
        for c, t, w in heads:
            tv.heading(c, text=t)
            tv.column(c, width=w, minwidth=w, anchor="w", stretch=(c == "src"))
        sb = ttk.Scrollbar(top, orient="vertical", command=tv.yview)
        tv.configure(yscrollcommand=sb.set)
        tv.pack(side="left", fill="both", expand=True)
        sb.pack(side="left", fill="y")
        tv.tag_configure("off", foreground=COLORS["muted"])

        def fill(select=None):
            tv.delete(*tv.get_children())
            cursor = 1
            col = 1
            for i, f in enumerate(work):
                ln = int(f.get("len") or 0)
                pos = int(f.get("pos") or 0)
                if pos:
                    src = "στήλη %d του ERP" % pos
                    if f.get("skip"):
                        src += " (από τον %dο χαρ.)" % (int(f["skip"]) + 1)
                elif str(f.get("extra", "")).strip():
                    src = "σταθερό «%s»" % f["extra"]
                else:
                    src = "κενά" if fixed else "κενό"
                if f.get("align") == "zero":
                    src += " · μηδενικά μπροστά"
                thesi = ("%d-%d" % (cursor, cursor + ln - 1) if ln else "—") if fixed else str(col)
                tv.insert("", "end", iid=str(i), tags=() if f.get("enabled") else ("off",), values=(
                    i + 1, thesi, f["name"], src, ln or "—", XFORMS.get(f.get("xform", ""), "—"),
                    ILS_ROLE_LABEL.get(f.get("ils") or "", "—") if fixed else ""))
                if f.get("enabled"):
                    cursor += ln
                    col += 1
            total = sum(int(f.get("len") or 0) for f in work if f.get("enabled"))
            lbl_total.configure(text="Μήκος γραμμής: %d χαρακτήρες" % total if fixed
                                else "%d στήλες" % sum(1 for f in work if f.get("enabled")))
            if select is not None and 0 <= select < len(work):
                tv.selection_set(str(select)); tv.see(str(select))

        def sel():
            x = tv.selection()
            return int(x[0]) if x else None

        def edit(_e=None):
            i = sel()
            if i is None:
                return
            self.edit_field_dialog(work[i], parent=win, on_done=lambda: fill(i))

        def add():
            work.append({"name": "Νέο πεδίο", "enabled": True, "pos": 0, "len": 0, "extra": "",
                         "xform": "", "align": "", "ils": ""})
            fill(len(work) - 1)
            edit()

        def remove():
            i = sel()
            if i is None:
                return
            del work[i]
            fill(min(i, len(work) - 1))

        def move(d):
            i = sel()
            if i is None or not (0 <= i + d < len(work)):
                return
            work[i], work[i + d] = work[i + d], work[i]
            fill(i + d)

        def toggle():
            i = sel()
            if i is None:
                return
            work[i]["enabled"] = not work[i].get("enabled")
            fill(i)

        def save():
            user = load_user_profiles()
            plain = name.replace("★ ", "", 1)
            user[plain] = {"settings": dict(settings), "fields": [dict(f) for f in work]}
            save_user_profiles(user)
            self.cfg["profiles"][name] = user[plain]
            self.log("Αποθηκεύτηκε το προφίλ «%s»: %d πεδία%s" % (
                name, len(work), ", γραμμή %d χαρακτήρων" % sum(int(f.get("len") or 0) for f in work
                                                                  if f.get("enabled")) if fixed else ""))
            win.destroy()

        tv.bind("<Double-1>", edit)
        tv.bind("<space>", lambda e: toggle())
        lbl_total = ttk.Label(bar, style="Hint.TLabel", text="")
        lbl_total.pack(side="left", padx=(0, 12))
        ttk.Button(bar, text="Επεξεργασία…", command=edit).pack(side="left")
        ttk.Button(bar, text="+ Γραμμή", command=add).pack(side="left", padx=6)
        ttk.Button(bar, text="− Αφαίρεση", command=remove).pack(side="left")
        ttk.Button(bar, text="▲", width=3, command=lambda: move(-1)).pack(side="left", padx=(6, 0))
        ttk.Button(bar, text="▼", width=3, command=lambda: move(1)).pack(side="left", padx=(2, 6))
        ttk.Button(bar, text="Εναλλαγή ✓", command=toggle).pack(side="left")
        if fixed:
            ttk.Button(bar, text="Field settings (AutoTrans.CFG)…", style="Pick.TButton",
                       command=lambda: (save(), self.ils_field_settings_dialog())).pack(side="left", padx=12)
        ttk.Button(bar, text="Άκυρο", style="Ghost.TButton", command=win.destroy).pack(side="right")
        ttk.Button(bar, text="Αποθήκευση", style="Accent.TButton", command=save).pack(side="right", padx=8)
        fill(0)
        win.wait_window()

    def ishida_scale_fields_dialog(self):
        """«Πεδία ζυγού Ishida» — όπως τα «Πεδία T-Scale»: τα 118 πεδία της εγγραφής του ζυγού.

        Τα βασικά (κωδικός, όνομα, τιμή, barcode) γράφονται πάντα. Για τα υπόλοιπα ο
        τεχνικός τσεκάρει ποια θα ενημερώνονται και από ποια στήλη του αρχείου της
        Ishida (host2) ή με ποια σταθερή τιμή — ανά πελάτη. Αποθηκεύεται στο
        «ishida_fields» των ρυθμίσεων και το χρησιμοποιεί η απευθείας αποστολή.
        """
        self.collect()
        entries = {}
        for e in self.cfg.get("ishida_fields") or []:
            try:
                entries[int(e.get("pos"))] = dict(e)
            except (TypeError, ValueError):
                pass
        core_txt = {ISHIDA_CODE_FIELD: "πάντα: κωδικός", ISHIDA_NAME_FIELD: "πάντα: όνομα (αν άλλαξε στο ERP)",
                    ISHIDA_PRICE_FIELD: "πάντα: ΤΙΜΗ ζυγιζόμενων", ISHIDA_PRICE_PIECE_FIELD: "πάντα: ΤΙΜΗ τεμαχίων",
                    ISHIDA_BCFORMAT_FIELD: "πάντα: μορφή barcode (Βήμα 4)", ISHIDA_BCCODE_FIELD: "πάντα: κωδικός στο barcode"}

        win = tk.Toplevel(self)
        win.title("Πεδία ζυγού Ishida — τι ενημερώνεται στον ζυγό")
        win.transient(self)
        win.geometry("1160x740")
        win.minsize(920, 560)
        bar = ttk.Frame(win, style="Bar.TFrame", padding=(10, 8))
        bar.pack(fill="x", side="bottom")
        top = ttk.Frame(win, style="Card.TFrame", padding=(10, 8))
        top.pack(fill="both", expand=True)
        ttk.Label(top, text="Πεδία ζυγού Ishida (εγγραφή PLU, 118 πεδία)", style="Title.TLabel").pack(anchor="w")
        ttk.Label(top, style="Hint.TLabel", wraplength=1080, justify="left",
                  text="Διαβάζουμε όλη την εγγραφή από τον ζυγό και αλλάζουμε μόνο ό,τι είναι τσεκαρισμένο· "
                       "τα υπόλοιπα μένουν όπως τα έχει ο ζυγός. Τα «πάντα» γράφονται σε κάθε αποστολή. "
                       "Για τα άλλα: κλικ στο ✓ (ή Space) για ενεργοποίηση, διπλό κλικ για να ορίσεις από ποια "
                       "στήλη του αρχείου της Ishida (host2) γεμίζει ή ποια σταθερή τιμή παίρνει."
                  ).pack(anchor="w", pady=(2, 6))
        cols = ("out", "pos", "name", "desc", "src")
        tv = ttk.Treeview(top, columns=cols, show="headings", selectmode="browse", height=24)
        for c, t, w, st in (("out", "Ενημερώνεται", 95, False), ("pos", "Θέση", 50, False),
                            ("name", "Πεδίο", 140, False), ("desc", "Τι είναι", 420, True),
                            ("src", "Γεμίζει από", 260, False)):
            tv.heading(c, text=t)
            tv.column(c, width=w, minwidth=w, anchor="w", stretch=st)
        sb = ttk.Scrollbar(top, orient="vertical", command=tv.yview)
        tv.configure(yscrollcommand=sb.set)
        tv.pack(side="left", fill="both", expand=True)
        sb.pack(side="left", fill="y")
        tv.tag_configure("off", foreground=COLORS["muted"])
        tv.tag_configure("core", foreground=COLORS["brand"])

        def src_text(e):
            try:
                col = int(e.get("col") or 0)
            except (TypeError, ValueError):
                col = 0
            parts = []
            if col:
                parts.append("στήλη %d του host2" % col)
            if str(e.get("extra", "")).strip():
                parts.append("σταθερό «%s»" % e["extra"])
            if e.get("xform"):
                parts.append(XFORMS.get(e["xform"], e["xform"]))
            return " · ".join(parts) or "—"

        def fill(select=None):
            tv.delete(*tv.get_children())
            for pos, name, desc in ISHIDA_PLU_FIELDS:
                if not name:
                    continue
                if pos in core_txt:
                    tv.insert("", "end", iid=str(pos), tags=("core",),
                              values=("✓ πάντα", pos, name, desc, core_txt[pos]))
                    continue
                e = entries.get(pos, {})
                on = bool(e.get("enabled"))
                tv.insert("", "end", iid=str(pos), tags=() if on else ("off",),
                          values=("✓" if on else "—", pos, name, desc, src_text(e) if e else "—"))
            if select is not None:
                tv.selection_set(str(select)); tv.see(str(select))

        def sel():
            x = tv.selection()
            return int(x[0]) if x else None

        def toggle(_e=None):
            pos = sel()
            if pos is None or pos in core_txt:
                return
            e = entries.setdefault(pos, {"pos": pos, "enabled": False, "col": 0, "extra": "", "xform": ""})
            e["enabled"] = not e.get("enabled")
            if e["enabled"] and not (e.get("col") or str(e.get("extra", "")).strip()):
                edit()
            fill(pos)

        def edit(_e=None):
            pos = sel()
            if pos is None or pos in core_txt:
                return
            e = entries.setdefault(pos, {"pos": pos, "enabled": False, "col": 0, "extra": "", "xform": ""})
            d = tk.Toplevel(win)
            d.title("Πεδίο %d — %s" % (pos, ISHIDA_PLU_BY_POS[pos][0]))
            d.transient(win)
            d.grab_set()
            ttk.Label(d, text=ISHIDA_PLU_BY_POS[pos][1], style="Hint.TLabel", wraplength=380,
                      justify="left").grid(row=0, column=0, columnspan=2, sticky="w", padx=8, pady=(8, 4))
            v_col = tk.StringVar(value=str(e.get("col") or ""))
            v_extra = tk.StringVar(value=str(e.get("extra", "")))
            ttk.Label(d, text="Στήλη του host2 (1 = πρώτη, -1 = τελευταία, κενό = καμία):").grid(
                row=1, column=0, sticky="w", padx=8, pady=4)
            ttk.Entry(d, textvariable=v_col, width=8).grid(row=1, column=1, sticky="w", padx=8)
            ttk.Label(d, text="Σταθερή τιμή (αν δεν έρχεται από στήλη):").grid(row=2, column=0, sticky="w", padx=8, pady=4)
            ttk.Entry(d, textvariable=v_extra, width=24).grid(row=2, column=1, sticky="w", padx=8)
            labels = list(XFORMS.values()); keys = list(XFORMS.keys())
            v_xf = tk.StringVar(value=XFORMS.get(e.get("xform", ""), "—"))
            ttk.Label(d, text="Μετατροπή:").grid(row=3, column=0, sticky="w", padx=8, pady=4)
            ttk.Combobox(d, textvariable=v_xf, values=labels, state="readonly", width=32).grid(
                row=3, column=1, sticky="w", padx=8)
            v_on = tk.BooleanVar(value=bool(e.get("enabled")))
            ttk.Checkbutton(d, text="Ενημερώνεται στον ζυγό", variable=v_on).grid(row=4, column=1, sticky="w", padx=8)

            def ok():
                try:
                    e["col"] = int(v_col.get() or 0)
                except ValueError:
                    messagebox.showerror(APP_NAME, "Η στήλη πρέπει να είναι αριθμός.", parent=d)
                    return
                e["extra"] = v_extra.get()
                e["xform"] = keys[labels.index(v_xf.get())] if v_xf.get() in labels else ""
                e["enabled"] = v_on.get()
                d.destroy()
                fill(pos)
            ttk.Button(d, text="Καταχώρηση", command=ok).grid(row=5, column=1, sticky="e", padx=8, pady=10)
            d.wait_window()

        def click(ev):
            if tv.identify_column(ev.x) == "#1" and tv.identify_row(ev.y):
                tv.selection_set(tv.identify_row(ev.y))
                toggle()
                return "break"
        tv.bind("<Button-1>", click)
        tv.bind("<space>", toggle)
        tv.bind("<Double-1>", edit)

        def save():
            self.cfg["ishida_fields"] = [dict(e) for e in entries.values()
                                         if e.get("enabled") or e.get("col") or str(e.get("extra", "")).strip()]
            energa = [e for e in self.cfg["ishida_fields"] if e.get("enabled")]
            self.log("Πεδία ζυγού Ishida: επιπλέον ενημερώνονται %d — %s" % (
                len(energa), ", ".join("%d %s" % (e["pos"], ISHIDA_PLU_BY_POS[e["pos"]][0]) for e in energa) or "κανένα"))
            win.destroy()
        ttk.Button(bar, text="Εναλλαγή ✓", command=toggle).pack(side="left")
        ttk.Button(bar, text="Επεξεργασία…", command=edit).pack(side="left", padx=6)
        ttk.Button(bar, text="Άκυρο", style="Ghost.TButton", command=win.destroy).pack(side="right")
        ttk.Button(bar, text="Καταχώρηση", style="Accent.TButton", command=save).pack(side="right", padx=8)
        fill()
        win.wait_window()

    def ishida_import_settings_dialog(self):
        """Οδηγίες για το «Setup Text Import» του ScaleLink Pro: πώς είναι το αρχείο μας.

        Το SLP κρατά τις ρυθμίσεις εισαγωγής σε δικό του δυαδικό αρχείο — δεν το
        γράφουμε εμείς. Του λέμε όμως ακριβώς τι να δηλώσει ο τεχνικός, από το
        προφίλ που βγάζει το δεύτερο αρχείο. (Με απευθείας αποστολή στο Βήμα 4
        δεν χρειάζεται τίποτα από αυτά.)
        """
        self.collect()
        name = self.v_s2b_profile.get().strip()
        _n, entry = resolve_profile(self.cfg.get("profiles") or {}, name) if name else ("", None)
        if not entry:
            messagebox.showinfo(APP_NAME, "Διάλεξε πρώτα προφίλ στο «Φτιάξε και δεύτερο αρχείο».")
            return
        fields = entry.get("fields", entry) if isinstance(entry, dict) else entry
        settings = dict(entry.get("settings", {})) if isinstance(entry, dict) else {}
        fmt = settings.get("step2_format", self.cfg.get("step2_format", "csv"))
        delim = {"csv": "κόμμα  ,", "tab": "TAB", "semicolon": "ερωτηματικό  ;",
                 "fixed": "ΣΤΑΘΕΡΟ ΠΛΑΤΟΣ (όχι διαχωριστικό)"}.get(
            fmt, "«%s»" % settings.get("step2_delimiter", self.cfg.get("step2_delimiter", ",")))
        out = (self.v_s2b_out.get() or "").strip()
        if not out:
            ext = ".csv" if fmt in ("csv", "semicolon") else ".txt"
            folder = self.cfg.get("output_dir") or os.path.dirname(self.cfg.get("watch_file", "") or "")
            out = os.path.join(folder, "host2" + ext)
        header = settings.get("step2_write_header", self.cfg.get("step2_write_header", True))
        enc = settings.get("step2_out_encoding", self.cfg.get("step2_out_encoding", "cp1253"))
        active = [f for f in fields if f.get("enabled")]

        lines = ["ScaleLink Pro 5  →  Setup → Text Import (ή Import From Text File)", "",
                 "%-26s %s" % ("Αρχείο (File):", out),
                 "%-26s %s" % ("Μορφή (Format):", delim),
                 "%-26s %s" % ("Επικεφαλίδες (Column titles):", "ΝΑΙ — η 1η γραμμή έχει ονόματα"
                                                                 if header else "ΟΧΙ — από την 1η γραμμή δεδομένα"),
                 "%-26s %s" % ("Κωδικοσελίδα:", enc),
                 "", "Σειρά πεδίων στο αρχείο (έτσι να τα βάλεις στη λίστα του SLP):", ""]
        if fmt == "fixed":
            lines.append("%-5s %-9s %-24s %s" % ("A/A", "ΘΕΣΕΙΣ", "ΠΕΔΙΟ", "ΤΙ ΠΕΡΙΕΧΕΙ"))
        else:
            lines.append("%-5s %-24s %s" % ("ΣΤΗΛΗ", "ΠΕΔΙΟ", "ΤΙ ΠΕΡΙΕΧΕΙ"))
        cursor = 1
        for i, f in enumerate(active, 1):
            pos = int(f.get("pos") or 0)
            ln = int(f.get("len") or 0)
            if pos:
                what = "από το ERP"
                if f.get("xform"):
                    what += " · " + XFORMS.get(f["xform"], f["xform"])
            elif str(f.get("extra", "")).strip():
                what = "σταθερό «%s»" % f["extra"]
            else:
                what = "κενό"
            if fmt == "fixed":
                lines.append("%-5d %3d-%-5d %-24s %s" % (i, cursor, cursor + ln - 1, f["name"], what))
                cursor += ln
            else:
                lines.append("%-5d %-24s %s" % (i, f["name"], what))
        lines += ["", "Η τιμή: %s" % ("σε ΛΕΠΤΑ (540 = 5,40 €)" if any(
            f.get("xform") == "tocents" for f in active) else "όπως στο ERP (με υποδιαστολή)"),
                  "", "Σημείωση: με «Απευθείας αποστολή» στο Βήμα 4 (θύρα 8071) το SLP δεν "
                      "χρειάζεται καθόλου — αυτά ισχύουν μόνο αν ο ζυγός ενημερώνεται μέσω SLP."]
        self._confirm_text("Τι να ρυθμίσεις στο ScaleLink (Ishida)", lines, yes="Κλείσιμο", no=None)

    def column_wizard(self):
        """Οδηγός: αρχείο ERP → στήλες με δείγματα → «τι είναι η καθεμιά» → προφίλ."""
        self.collect()
        win = tk.Toplevel(self)
        win.title("Οδηγός αντιστοίχισης στηλών — από το αρχείο του ERP")
        win.transient(self)
        win.grab_set()
        win.geometry("1060x820")
        outer = ttk.Frame(win, style="Card.TFrame")
        outer.pack(fill="both", expand=True)
        body = self._scrollable(outer)
        state = {"analysis": None, "cols": [], "vars": {}, "profiles": None}

        # ---- 1. το αρχείο
        ttk.Label(body, text="1.  Το αρχείο που βγάζει το ERP", style="Title.TLabel").pack(anchor="w", pady=(10, 2))
        v_path = tk.StringVar(value=(self.v_watch.get() or self.cfg.get("watch_file") or "").strip())
        row = ttk.Frame(body)
        row.pack(fill="x")
        self._pick_row(row, "Αρχείο:", v_path, "file", 0)
        v_header = tk.BooleanVar(value=False)
        v_info = tk.StringVar(value="Πάτα «Ανάλυση» για να διαβαστεί το αρχείο.")
        row2 = ttk.Frame(body)
        row2.pack(fill="x", pady=(4, 0))
        ttk.Button(row2, text="Ανάλυση αρχείου", style="Accent.TButton",
                   command=lambda: analyze()).pack(side="left")
        ttk.Checkbutton(row2, text="Η 1η γραμμή είναι επικεφαλίδες (ονόματα στηλών)",
                        variable=v_header, command=lambda: rebuild()).pack(side="left", padx=12)
        ttk.Label(body, textvariable=v_info, style="Hint.TLabel", wraplength=900,
                  justify="left").pack(anchor="w", pady=(4, 8))

        # ---- 2. οι στήλες
        ttk.Label(body, text="2.  Τι είναι κάθε στήλη", style="Title.TLabel").pack(anchor="w", pady=(6, 2))
        ttk.Label(body, style="Hint.TLabel", wraplength=900, justify="left",
                  text="Δίπλα σε κάθε στήλη βλέπεις πραγματικά δείγματα από το αρχείο. Διάλεξε "
                       "τι είναι — χρειάζονται τουλάχιστον Κωδικός και Τιμή· το Όνομα για να "
                       "ενημερώνονται και οι ετικέτες."
                  ).pack(anchor="w")
        cols_box = ttk.Frame(body)
        cols_box.pack(fill="x", pady=(4, 8))

        # ---- 3. τιμή, όνομα, ζυγοί
        ttk.Label(body, text="3.  Τιμή και ζυγοί", style="Title.TLabel").pack(anchor="w", pady=(6, 2))
        v_price = tk.StringVar(value="decimal")
        prow = ttk.Frame(body)
        prow.pack(fill="x")
        ttk.Label(prow, text="Η τιμή στο αρχείο είναι:").pack(side="left")
        ttk.Radiobutton(prow, text="με υποδιαστολή (5.40 ή 5,40)", value="decimal",
                        variable=v_price).pack(side="left", padx=10)
        ttk.Radiobutton(prow, text="σε λεπτά (540)", value="cents", variable=v_price).pack(side="left")
        nrow = ttk.Frame(body)
        nrow.pack(fill="x", pady=(6, 0))
        ttk.Label(nrow, text="Όνομα πελάτη / προφίλ:").pack(side="left")
        v_name = tk.StringVar(value="")
        ttk.Entry(nrow, textvariable=v_name, width=32).pack(side="left", padx=8)
        srow = ttk.Frame(body)
        srow.pack(fill="x", pady=(6, 0))
        ttk.Label(srow, text="Ζυγοί του καταστήματος:").pack(side="left")
        v_ts = tk.BooleanVar(value=bool(self.cfg.get("tscale_on", True)))
        v_ish = tk.BooleanVar(value=bool(self.cfg.get("ishida_on", False)))
        v_ils = tk.BooleanVar(value=bool(self.cfg.get("step2c_enabled", False)))
        for txt, var in (("T-Scale", v_ts), ("Ishida UNI-3", v_ish), ("ILS1100", v_ils)):
            ttk.Checkbutton(srow, text=txt, variable=var).pack(side="left", padx=8)
        ttk.Label(body, style="Hint.TLabel", wraplength=900, justify="left",
                  text="Οι IP των ζυγών μπαίνουν στο «Βήμα 4». Για ILS, μετά πάτα στο Βήμα 3 "
                       "«Field settings του ILS» για να γραφτεί το AutoTrans.CFG."
                  ).pack(anchor="w")

        # ---- 4. προεπισκόπηση
        ttk.Label(body, text="4.  Πώς θα βγουν τα αρχεία", style="Title.TLabel").pack(anchor="w", pady=(10, 2))
        prev = tk.Text(body, height=14, font=FONTS["mono"], wrap="none", bg=COLORS["console"],
                       fg=COLORS["console_fg"], relief="flat", padx=12, pady=10)
        prev.pack(fill="x")
        bar = ttk.Frame(body)
        bar.pack(fill="x", pady=10)
        ttk.Button(bar, text="Προεπισκόπηση", command=lambda: preview()).pack(side="left")
        ttk.Button(bar, text="Αποθήκευση και εφαρμογή", style="Accent.TButton",
                   command=lambda: apply()).pack(side="left", padx=8)
        ttk.Button(bar, text="Άκυρο", style="Ghost.TButton", command=win.destroy).pack(side="right")

        def set_preview(text):
            prev.configure(state="normal")
            prev.delete("1.0", "end")
            prev.insert("1.0", text)
            prev.configure(state="disabled")

        def analyze():
            path = v_path.get().strip()
            if not path or not os.path.isfile(path):
                messagebox.showerror(APP_NAME, "Διάλεξε πρώτα το αρχείο του ERP.", parent=win)
                return
            try:
                an = wizard_analyze_file(path)
            except Exception as exc:
                messagebox.showerror(APP_NAME, "Δεν διαβάστηκε το αρχείο.\n\n%s" % exc, parent=win)
                return
            state["analysis"] = an
            if an.get("fixed"):
                v_header.set(False)
                v_info.set("Κωδικοσελίδα %s · ΣΤΑΘΕΡΟ ΠΛΑΤΟΣ (χωρίς διαχωριστικό), γραμμή %d χαρακτήρων · "
                           "%d κομμάτια%s · %d γραμμές δείγμα. Διόρθωσε Από/Μήκος αν χρειάζεται και πάτα "
                           "«Ανανέωση δειγμάτων»." % (
                               an["enc"], max(len(l) for l in an["lines"]), len(an["segments"]),
                               " — αναγνωρίστηκε το κλασικό host της ICS (76 χαρ.)" if an["preset"] else "",
                               len(an["lines"])))
                if not v_name.get().strip():
                    v_name.set(os.path.splitext(os.path.basename(path))[0].upper())
                rebuild(guess=True)
                return
            v_header.set(bool(an["header"]))
            v_info.set("Κωδικοσελίδα %s · διαχωριστικό %s · %d στήλες%s · %d γραμμές δείγμα" % (
                an["enc"], {",": "κόμμα", ";": "ερωτηματικό", "\t": "TAB", "|": "κάθετος"}.get(
                    an["delimiter"], an["delimiter"]), an["ncols"],
                " (ο αριθμός αλλάζει ανά γραμμή: το διαχωριστικό υπάρχει και μέσα σε "
                "περιγραφές — οι στήλες μετά το όνομα θα μετρηθούν από το τέλος)"
                if an["varies"] else "", len(an["lines"])))
            if not v_name.get().strip():
                v_name.set(os.path.splitext(os.path.basename(path))[0].upper())
            rebuild(guess=True)

        def read_segments():
            """Οι θέσεις/μήκη όπως τα έγραψε ο τεχνικός στα πεδία (σταθερό πλάτος)."""
            an = state["analysis"]
            segs = []
            for i in sorted(state.get("segvars", {})):
                vp, vl = state["segvars"][i]
                try:
                    p, n = int(vp.get() or 0), int(vl.get() or 0)
                except ValueError:
                    continue
                if p > 0 and n > 0:
                    segs.append((p, n))
            if segs:
                an["segments"] = segs
                an["ncols"] = len(segs)

        def add_segment():
            an = state["analysis"]
            if not an or not an.get("fixed"):
                return
            read_segments()
            last = an["segments"][-1] if an["segments"] else (0, 1)
            an["segments"].append((last[0] + last[1], 1))
            an["ncols"] = len(an["segments"])
            rebuild()

        def remove_segment():
            an = state["analysis"]
            if not an or not an.get("fixed") or len(an["segments"]) <= 1:
                return
            read_segments()
            an["segments"].pop()
            an["ncols"] = len(an["segments"])
            state["vars"].pop(an["ncols"] + 1, None)
            rebuild()

        def refresh_segments():
            read_segments()
            rebuild()

        def rebuild(guess=False):
            an = state["analysis"]
            if not an or not (an.get("delimiter") or an.get("fixed")):
                return
            fixed = bool(an.get("fixed"))
            an["header"] = v_header.get()
            cols = wizard_columns(an)
            state["cols"] = cols
            old = {i: v.get() for i, v in state["vars"].items()}
            guessed = {}
            if guess or not old:
                guessed = dict(an.get("preset") or {})
                for i, m in wizard_guess_meanings(cols).items():
                    guessed.setdefault(i, m)
            for w in cols_box.winfo_children():
                w.destroy()
            labels = [lbl for _k, lbl in WIZ_MEANINGS]
            keys = [k for k, _l in WIZ_MEANINGS]
            hdr = ttk.Frame(cols_box)
            hdr.pack(fill="x")
            if fixed:
                heads = (("ΚΟΜΜΑΤΙ", 8), ("ΑΠΟ", 6), ("ΜΗΚΟΣ", 7), ("ΔΕΙΓΜΑΤΑ ΑΠΟ ΤΟ ΑΡΧΕΙΟ", 52), ("ΤΙ ΕΙΝΑΙ", 26))
            else:
                heads = (("ΣΤΗΛΗ", 8), ("ΕΠΙΚΕΦΑΛΙΔΑ", 16), ("ΔΕΙΓΜΑΤΑ ΑΠΟ ΤΟ ΑΡΧΕΙΟ", 52), ("ΤΙ ΕΙΝΑΙ", 26))
            for txt, w in heads:
                ttk.Label(hdr, text=txt, style="Hint.TLabel", width=w).pack(side="left")
            state["vars"] = {}
            state["segvars"] = {}
            for i, name, samples in cols:
                r = ttk.Frame(cols_box)
                r.pack(fill="x", pady=1)
                ttk.Label(r, text="%d" % i, width=8).pack(side="left")
                if fixed:
                    pos, ln = an["segments"][i - 1]
                    vp, vl = tk.StringVar(value=str(pos)), tk.StringVar(value=str(ln))
                    ttk.Entry(r, textvariable=vp, width=5).pack(side="left", padx=(0, 4))
                    ttk.Entry(r, textvariable=vl, width=5).pack(side="left", padx=(0, 6))
                    state["segvars"][i] = (vp, vl)
                else:
                    ttk.Label(r, text=name[:15], width=16).pack(side="left")
                deig = " | ".join(x[:22] for x in samples[:3])
                ttk.Label(r, text=deig[:70], width=52, font=FONTS["mono_sm"]).pack(side="left")
                key = old.get(i) if i in old else WIZ_MEANING_LABEL.get(guessed.get(i, ""), labels[0])
                v = tk.StringVar(value=key if key in labels else labels[0])
                cb = ttk.Combobox(r, textvariable=v, values=labels, state="readonly", width=24)
                cb.pack(side="left")
                state["vars"][i] = v
            if fixed:
                br = ttk.Frame(cols_box)
                br.pack(fill="x", pady=(4, 0))
                ttk.Button(br, text="Ανανέωση δειγμάτων", command=refresh_segments).pack(side="left")
                ttk.Button(br, text="+ Κομμάτι", command=add_segment).pack(side="left", padx=6)
                ttk.Button(br, text="− Κομμάτι", command=remove_segment).pack(side="left")
                ttk.Label(br, style="Hint.TLabel",
                          text="Από = θέση του 1ου χαρακτήρα (1 = πρώτος), Μήκος = πόσοι χαρακτήρες."
                          ).pack(side="left", padx=10)
            # τιμή: με υποδιαστολή ή σε λεπτά;
            for i, _n, samples in cols:
                if WIZ_MEANING_LABEL.get("price") == state["vars"][i].get():
                    v_price.set(wizard_price_mode_guess(samples))
            if fixed and an.get("preset"):
                v_price.set("cents")             # το host της ICS γράφει λεπτά (01200 = 12,00 €)
            state["_keys"] = (labels, keys)

        def meanings():
            labels, keys = state.get("_keys", ([], []))
            out = {}
            for i, v in state["vars"].items():
                k = keys[labels.index(v.get())] if v.get() in labels else ""
                if k:
                    if k in out.values():
                        raise ValueError("Το «%s» δόθηκε σε δύο στήλες." % WIZ_MEANING_LABEL[k])
                    out[i] = k
            return out

        def build():
            an = state["analysis"]
            if not an or not (an.get("delimiter") or an.get("fixed")):
                raise ValueError("Κάνε πρώτα «Ανάλυση αρχείου».")
            an["header"] = v_header.get()
            if an.get("fixed"):
                read_segments()
            return wizard_build_profiles(meanings(), an, v_price.get())

        def preview():
            try:
                profs = build()
            except ValueError as exc:
                messagebox.showerror(APP_NAME, str(exc), parent=win)
                return
            state["profiles"] = profs
            tmp = os.path.join(CONFIG_DIR, "preview_wizard")
            shutil.rmtree(tmp, ignore_errors=True)
            os.makedirs(tmp, exist_ok=True)
            out = []
            for key, var, title in (("tscale", v_ts, "T-Scale (product.csv)"),
                                    ("ishida", v_ish, "Ishida (host2.csv)"),
                                    ("ils", v_ils, "ILS (hostILS.txt)")):
                if not var.get():
                    continue
                sub = dict(self.cfg)
                sub.update(profs[key]["settings"])
                sub["step2_fields"] = profs[key]["fields"]
                sub["step2_input"] = v_path.get().strip()
                sub["step2_output"] = os.path.join(tmp, key + ".txt")
                logs = []
                try:
                    run_step2(sub, sub["step2_input"], logs.append)
                    with open(sub["step2_output"], "rb") as fh:
                        txt = fh.read().decode("cp1253", "replace")
                    lines = [l for l in txt.split("\r\n") if l][:3]
                    out.append("── %s" % title)
                    out += ["   " + _show(l, 110) for l in lines]
                    for l in logs:
                        if "ΠΡΟΣΟΧΗ" in l or "κόπηκαν" in l:
                            out.append("   " + l.strip())
                except StepError as exc:
                    out.append("── %s: ΣΦΑΛΜΑ %s" % (title, exc.message))
                out.append("")
            set_preview("\n".join(out) or "Δεν επιλέχθηκε κανένας ζυγός.")

        def apply():
            try:
                profs = build()
            except ValueError as exc:
                messagebox.showerror(APP_NAME, str(exc), parent=win)
                return
            name = v_name.get().strip().replace("★", "").strip() or "ΠΕΛΑΤΗΣ"
            if not messagebox.askyesno(
                    APP_NAME, "Να αποθηκευτούν τα προφίλ «%s · T-Scale», «%s · Ishida», «%s · ILS» "
                    "και να εφαρμοστούν στο Βήμα 3;\n\nΟ πίνακας του Βήματος 3 θα αντικατασταθεί."
                    % (name, name, name), parent=win):
                return
            user = load_user_profiles()
            full = {}
            for key, label in (("tscale", "T-Scale"), ("ishida", "Ishida"), ("ils", "ILS")):
                pname = "%s · %s" % (name, label)
                user[pname] = profs[key]
                full[key] = "★ " + pname
                self.cfg["profiles"]["★ " + pname] = profs[key]
            save_user_profiles(user)
            # Βήμα 3: κύριος πίνακας = T-Scale (από αυτό βγαίνει το product.csv)
            self.cfg["step2_fields"] = [dict(f) for f in profs["tscale"]["fields"]]
            self.cfg.update(profs["tscale"]["settings"])
            self.cfg["step2b_enabled"] = bool(v_ish.get())
            self.cfg["step2b_profile"] = full["ishida"]
            self.cfg["step2c_enabled"] = bool(v_ils.get())
            self.cfg["step2c_profile"] = full["ils"]
            self.cfg["tscale_on"] = bool(v_ts.get())
            self.cfg["ishida_on"] = bool(v_ish.get())
            self.cfg["ishida_price_cents"] = True
            if not (self.cfg.get("watch_file") or "").strip():
                self.cfg["watch_file"] = v_path.get().strip()
            self._load_into_widgets()
            self.refresh_profiles(full["tscale"])
            self.log("Οδηγός: αποθηκεύτηκαν τα προφίλ «%s» (T-Scale/Ishida/ILS) και εφαρμόστηκαν "
                     "στο Βήμα 3. Έλεγξε τις IP στο Βήμα 4 και πάτα «Αποθήκευση ρυθμίσεων»." % name)
            win.destroy()
            self.nb.select(3)

        if v_path.get() and os.path.isfile(v_path.get()):
            win.after(200, analyze)
        win.wait_window()

    def _ils_fields_for_settings(self):
        """Τα πεδία του προφίλ ILS που είναι επιλεγμένο — ή του κύριου πίνακα."""
        name = self.v_s2c_profile.get().strip()
        if name:
            _n, entry = resolve_profile(self.cfg.get("profiles") or {}, name)
            if entry:
                fields = entry.get("fields", entry) if isinstance(entry, dict) else entry
                settings = entry.get("settings", {}) if isinstance(entry, dict) else {}
                return name, fields, settings.get("step2_format")
        return "κύριος πίνακας", self.cfg.get("step2_fields", []), self.cfg.get("step2_format")

    def ils_field_settings_dialog(self):
        """Τι πρέπει να λέει το Field settings του ILS για το αρχείο που φτιάχνουμε."""
        self.collect()
        name, fields, fmt = self._ils_fields_for_settings()
        if fmt != "fixed":
            messagebox.showwarning(
                APP_NAME, "Το προφίλ «%s» δεν βγάζει αρχείο σταθερού πλάτους (μορφή: %s).\n\n"
                "Το ILS διαβάζει μόνο σταθερό πλάτος — διάλεξε προφίλ ILS στη γραμμή "
                "«Φτιάξε και αρχείο για ILS»." % (name, fmt or "—"))
            return
        settings, warnings = ils_field_settings(fields)
        _n2, entry2 = resolve_profile(self.cfg.get("profiles") or {}, name)
        psettings = entry2.get("settings", {}) if isinstance(entry2, dict) else {}
        options = ils_cfg_options(psettings or self.cfg, fields)
        total = sum(int(f.get("len") or 0) for f in fields if f.get("enabled"))
        lines = ["Προφίλ: %s   (γραμμή %d χαρακτήρων)" % (name, total), ""]
        lines += describe_ils_settings(settings)
        lines += ["", "Επιλογές:"] + ["  %-18s %s" % (k + "=" + v, ILS_CFG_OPTIONS.get(k, ""))
                                      for k, v in options]
        if warnings:
            lines += [""] + warnings
        lines += ["", "Γραμμές για το AutoTrans.CFG ([ImportPluSet]):"]
        lines += ["  %s=%s" % kv for kv in ils_cfg_values(settings) + options]

        win = tk.Toplevel(self)
        win.title("Field settings του ILS")
        win.transient(self)
        win.grab_set()
        txt = tk.Text(win, width=max(70, min(110, max(len(l) for l in lines) + 2)),
                      height=min(34, len(lines) + 1), font=FONTS["mono"], wrap="none",
                      bg=COLORS["card"], fg=COLORS["ink"], relief="flat", padx=14, pady=12)
        txt.insert("1.0", "\n".join(lines))
        txt.configure(state="disabled")
        txt.pack(fill="both", expand=True, padx=10, pady=(10, 4))
        ttk.Label(win, style="Hint.TLabel", wraplength=760, justify="left",
                  text="«Γράψε το AutoTrans.CFG» φτιάχνει το αρχείο στον φάκελο του ScaleAutoTrans "
                       "(συνήθως C:\\ScaleAutoTrans). Αν υπάρχει ήδη, αλλάζει μόνο τα πεδία και κρατά "
                       "αντίγραφο .bak· αλλιώς το φτιάχνει ολόκληρο. Κλείσε το ScaleAutoTrans πριν, "
                       "άνοιξέ το μετά και δες το Field settings.").pack(anchor="w", padx=10)
        bar = ttk.Frame(win)
        bar.pack(fill="x", padx=10, pady=(6, 10))

        def enimerosi():
            arxikos = r"C:\ScaleAutoTrans" if os.path.isdir(r"C:\ScaleAutoTrans") else None
            path = filedialog.asksaveasfilename(
                parent=win, title="Πού είναι (ή πού να γραφτεί) το AutoTrans.CFG του ScaleAutoTrans",
                initialdir=arxikos, initialfile="AutoTrans.CFG", defaultextension=".CFG",
                confirmoverwrite=False, filetypes=[("AutoTrans.CFG", "*.CFG *.cfg"), ("Όλα", "*.*")])
            if not path:
                return
            yparxei = os.path.isfile(path)
            try:
                backup, changed, added = write_autotrans_cfg(
                    settings, path, existing=path if yparxei else None, options=options)
            except Exception as exc:
                messagebox.showerror(APP_NAME, "Δεν γράφτηκε το CFG.\n\n%s\n%s" % (path, exc),
                                     parent=win)
                return
            if yparxei:
                self.log("AutoTrans.CFG ενημερώθηκε: %s (αντίγραφο: %s) — %d αλλαγές, %d νέα κλειδιά"
                         % (path, backup, len(changed), len(added)))
                for c in changed + added:
                    self.log("  " + c)
                minima = ("Ενημερώθηκε.\n\nΑρχείο: %s\nΑντίγραφο: %s\n\nΑλλαγές: %d\n%s%s"
                          % (path, backup, len(changed), "\n".join(changed[:12]) or "(ήταν ήδη σωστό)",
                             "\n\nΠροστέθηκαν: %d" % len(added) if added else ""))
            else:
                self.log("AutoTrans.CFG γράφτηκε από την αρχή: %s" % path)
                minima = ("Γράφτηκε ολόκληρο.\n\nΑρχείο: %s\n\nΆνοιξε το ScaleAutoTrans → System Set → "
                          "Field settings και δες ότι τα πεδία είναι όπως εδώ." % path)
            messagebox.showinfo(APP_NAME, minima, parent=win)
            win.destroy()

        ttk.Button(bar, text="Κλείσιμο", style="Ghost.TButton", command=win.destroy).pack(side="right")
        ttk.Button(bar, text="Γράψε το AutoTrans.CFG…", style="Accent.TButton",
                   command=enimerosi).pack(side="right", padx=8)
        win.wait_window()

    def ils_profile_from_cfg_dialog(self):
        """Διάλεξε AutoTrans.CFG → προφίλ ILS για τη συγκεκριμένη εγκατάσταση."""
        path = filedialog.askopenfilename(
            title="Διάλεξε το AutoTrans.CFG του ILS (φάκελος του ScaleAutoTrans)",
            filetypes=[("AutoTrans.CFG", "*.CFG *.cfg"), ("Όλα", "*.*")])
        if not path:
            return
        self.collect()
        try:
            ils_fields = parse_autotrans_cfg(path)
        except Exception as exc:
            messagebox.showerror(APP_NAME, "Δεν διαβάστηκε το AutoTrans.CFG.\n\n%s\n%s" % (path, exc))
            return
        fields, settings, warnings = ils_profile_from_cfg(
            ils_fields, self.cfg.get("step2_fields", []), self.cfg)
        store = os.path.basename(os.path.dirname(os.path.normpath(path))) or "ILS"
        name = "ILS · %s" % store
        lines = ["Από το %s" % path, "",
                 "Ενεργά πεδία στο ILS: %s" % ", ".join("%s(%d,%d)" % (n, p, l)
                                                        for n, p, l, _lbl in ils_fields), ""]
        lines += describe_ils_profile(fields)
        if warnings:
            lines += [""] + warnings
        lines += ["", "Πώς διαβάζεται το ERP: %s%s" % (
            "στήλες με «%s»" % settings["step2_input_delimiter"]
            if settings["step2_input_type"] == "delimited" else "σταθερές θέσεις",
            " — όπως ο κύριος πίνακας"), "",
                  "Να αποθηκευτεί ως προφίλ «%s» και να επιλεγεί για το αρχείο ILS;" % name,
                  "Μετά: Δοκιμή τώρα → σύγκρινε το hostILS με αρχείο που ήδη δέχεται ο ζυγός "
                  "(tools/dokimi_ils.py)."]
        if not self._confirm_text("Προφίλ ILS από AutoTrans.CFG", lines):
            return
        profiles = load_user_profiles()
        profiles[name] = {"settings": settings, "fields": fields}
        save_user_profiles(profiles)
        self.cfg["profiles"]["★ " + name] = profiles[name]
        self.refresh_profiles()
        self.v_s2c_profile.set("★ " + name)
        self.v_s2c.set(True)
        self.log("Προφίλ ILS «%s» από %s: %d πεδία, γραμμή %d χαρακτήρων%s"
                 % (name, path, len(fields), sum(int(f.get("len") or 0) for f in fields),
                    " — %d προειδοποιήσεις" % len(warnings) if warnings else ""))
        for w in warnings:
            self.log("  " + w)

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
        if hasattr(self, "status_ticker") and self.status_ticker:
            try:
                stamp = datetime.datetime.now().strftime("%H:%M:%S")
                self.status_ticker.configure(text=f"● {text}  ({stamp})")
            except Exception:
                pass

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
    def on_accept_beta(self):
        """Το τικ «Δέχομαι beta» θέλει κωδικό τεχνικού — όχι προσωπικό καταστήματος."""
        if self.v_accept_beta.get() and not self.ask_password():
            self.v_accept_beta.set(False)
            return
        self.cfg["accept_beta"] = bool(self.v_accept_beta.get())
        try:
            save_config(self.collect())
        except Exception:
            pass
        self.log("Δοκιμαστικές εκδόσεις: %s" % ("δεκτές" if self.cfg["accept_beta"] else "όχι"))

    def check_beta(self):
        """Βρίσκει τη νεότερη beta στο GitHub και την εγκαθιστά ΔΙΠΛΑ στην κανονική."""
        if not getattr(self, "v_accept_beta", None) or not self.v_accept_beta.get():
            messagebox.showinfo(APP_NAME, "Πρώτα τσέκαρε «Δέχομαι δοκιμαστικές (beta) εκδόσεις» "
                                          "στα Εργαλεία (θέλει κωδικό τεχνικού).")
            return
        self.set_status("Έλεγχος για beta…", COLORS["brand"])
        self._beta_result = None

        def job():
            try:
                self._beta_result = ("ok",) + fetch_latest_beta()
            except Exception as exc:
                self._beta_result = ("err", str(exc), "", "")
        threading.Thread(target=job, daemon=True).start()
        self.after(300, self._poll_beta)

    def _poll_beta(self):
        res = getattr(self, "_beta_result", None)
        if res is None:
            self.after(300, self._poll_beta)
            return
        self._beta_result = None
        self.set_status("Σε αναμονή", COLORS["muted"])
        kind, version, notes, url = res
        if kind == "err":
            messagebox.showwarning(APP_NAME, "Δεν ήταν δυνατός ο έλεγχος για beta.\n\n%s" % version)
            return
        if not version or not url:
            messagebox.showinfo(APP_NAME, "Δεν υπάρχει διαθέσιμη δοκιμαστική έκδοση αυτή τη στιγμή.")
            return
        target = beta_install_dir()
        if not messagebox.askyesno(
                APP_NAME, "Δοκιμαστική έκδοση: %s\n\n%s\n\nΘα εγκατασταθεί ΔΙΠΛΑ στην κανονική "
                "(δεν την αλλάζει), στον φάκελο:\n%s\n\nκαι θα ανοίξει. Συνέχεια;"
                % (version, notes or "", target)):
            return
        self.set_status("Λήψη beta…", COLORS["brand"])
        tmp = os.environ.get("TEMP") or target
        dest = os.path.join(tmp, BETA_ASSET)

        def job():
            try:
                log = lambda m: self.after(0, self.log, m)
                download_update(url, dest, log=log)
                exe = install_beta_side_by_side(dest, target, log=log)
                self.after(0, self._beta_ready, exe, version)
            except Exception as exc:
                self.after(0, self._beta_failed, str(exc))
        threading.Thread(target=job, daemon=True).start()

    def _beta_ready(self, exe, version):
        self.set_status("Σε αναμονή", COLORS["muted"])
        self.log("Η beta %s εγκαταστάθηκε: %s" % (version, exe))
        try:
            subprocess.Popen([exe], cwd=os.path.dirname(exe))
        except Exception as exc:
            messagebox.showwarning(APP_NAME, "Η beta εγκαταστάθηκε αλλά δεν άνοιξε μόνη της.\n\n%s\n%s"
                                   % (exe, exc))
            return
        messagebox.showinfo(APP_NAME, "Η δοκιμαστική έκδοση %s άνοιξε δίπλα στην κανονική.\n\n%s\n\n"
                            "Έχει δικές της ρυθμίσεις (αντιγράφει τις τρέχουσες στην πρώτη εκκίνηση, "
                            "με την αυτόματη έναρξη σβηστή)." % (version, exe))

    def _beta_failed(self, text):
        self.set_status("Σε αναμονή", COLORS["muted"])
        self.log("Η εγκατάσταση της beta απέτυχε: %s" % text)
        messagebox.showerror(APP_NAME, "Η εγκατάσταση της beta απέτυχε.\n\n%s" % text)

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
        """Γράφει τις IP στο ip.xml του προγράμματος T-Scale."""
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
            messagebox.showinfo(APP_NAME,
                                "Δεν βρέθηκαν IP στο ip.xml του προγράμματος T-Scale.")
            return
        self.v_ips.set(", ".join(ips))
        self.log("Διαβάστηκαν IP από το πρόγραμμα T-Scale: %s" % ", ".join(ips))

    def toggle_adv3m(self):
        if self.adv3m.winfo_ismapped():
            self.adv3m.pack_forget()
            self.btn_adv3m.configure(text="⚙  Για προχωρημένους  ▾")
        else:
            self.adv3m.pack(fill="x")
            self.btn_adv3m.configure(text="⚙  Για προχωρημένους  ▴")

    def refresh_pending_hint(self):
        """Δείχνει ποιοι ζυγοί περιμένουν ακόμα — αλλιώς δεν το μαθαίνει κανείς."""
        p = load_pending()
        if not p:
            self.lbl_pending.configure(text="καμία εκκρεμότητα")
            return
        self.lbl_pending.configure(
            text="εκκρεμούν: %s" % ", ".join("%s (από %s)" % (ip, d.get("since", "")[:16])
                                            for ip, d in sorted(p.items())))

    def retry_pending_now(self):
        """Χειροκίνητη δοκιμή, για να μην περιμένει ο τεχνικός το διάστημα."""
        if not load_pending():
            messagebox.showinfo(APP_NAME, "Δεν εκκρεμεί κανένας ζυγός.")
            return
        if self.worker and self.worker.is_alive():
            messagebox.showinfo(APP_NAME, "Τρέχει ήδη ενημέρωση — δοκίμασε σε λίγο.")
            return

        def ergasia():
            try:
                retry_pending_scales(self.collect(), lambda m: self.after(0, self.log, m),
                                     self.stop_event)
            except Exception as exc:
                self.after(0, self.log, "Επανάληψη εκκρεμών: σφάλμα (%s)" % exc)
            self.after(0, self.refresh_pending_hint)

        self.worker = threading.Thread(target=ergasia, daemon=True)
        self.worker.start()

    def on_rebuild_toggle(self):
        """Το τικ αλλάζει κάτι σοβαρό — να φαίνεται τι θα γίνει.

        Το «περιέχει ΟΛΑ τα προϊόντα» μετράει μόνο στην ανακατασκευή, οπότε
        γκριζάρει όταν δεν παίζει ρόλο: ένα τικ που δεν κάνει τίποτα μπερδεύει
        περισσότερο από ένα που λείπει.
        """
        self.chk_fullcat.configure(
            state="normal" if self.v_rebuild.get() else "disabled")
        if not self.v_rebuild.get():
            self.lbl_rebuild.configure(text="→ αλλάζουν μόνο οι τιμές")
        elif self.v_fullcat.get():
            self.lbl_rebuild.configure(
                text="→ ξαναγράφονται τα ονόματα ΚΑΙ σβήνονται όσα λείπουν")
        else:
            self.lbl_rebuild.configure(
                text="→ ξαναγράφονται τα ονόματα (τίποτα δεν σβήνεται)")

    def on_marka_toggle(self):
        """Ξε-τσεκαρισμένη μάρκα σημαίνει «δεν υπάρχει εδώ»: τα πεδία της κλείνουν.

        Έτσι φαίνεται με μια ματιά τι θα σταλεί, και κανείς δεν γράφει IP σε
        μάρκα που δεν θα χρησιμοποιηθεί.
        """
        tscale = self.v_tscale_on.get()
        ishida = self.v_ish_on.get()
        for w in (self.e_ips, self.btn_save_ips):
            try:
                w.configure(state="normal" if tscale else "disabled")
            except tk.TclError:
                pass
        for w in (self.e_ish_ips, self.chk_ish_cents, self.chk_ish_bc_code,
                  self.chk_ish_create, self.chk_ish_names, self.e_ish_width):
            try:
                w.configure(state="normal" if ishida else "disabled")
            except tk.TclError:
                pass
        try:
            self.cmb_ish_bc.configure(state="readonly" if ishida else "disabled")
        except tk.TclError:
            pass

    def on_direct_toggle(self):
        """Δείχνει τι θα γίνει με την τρέχουσα επιλογή."""
        if self.v_direct.get():
            self.lbl_direct.configure(text="→ στέλνουμε εμείς")
        else:
            self.lbl_direct.configure(
                text="→ θα ανοίγει το πρόγραμμα T-Scale του κατασκευαστή")

    def use_bundled_autoprocess(self):
        p = bundled_autoprocess()
        if not p:
            messagebox.showinfo(
                APP_NAME,
                "Δεν βρέθηκε το πρόγραμμα T-Scale δίπλα στο δικό μας.\n\nΕίναι "
                "λογισμικό του κατασκευαστή των ζυγών και δεν έρχεται μαζί μας. Διάλεξέ "
                "το με «Αναζήτηση…», ή αντίγραψε τον φάκελό του ως «autosend» δίπλα στο "
                "πρόγραμμα για να βρίσκεται αυτόματα.")
            return
        self.v_s3exe.set(p)
        self.log("Βρέθηκε το πρόγραμμα T-Scale δίπλα στο δικό μας: %s" % p)
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
                text="(αν αντιγράψεις τον φάκελο του προγράμματος T-Scale ως "
                     "«autosend» δίπλα στο δικό μας, βρίσκεται μόνο του)")
            self.btn_bundled.state(["disabled"])

    def scan_scales_now(self):
        """Ψάχνει μόνο του ζυγούς στο δίκτυο και συμπληρώνει τα πεδία IP."""
        if getattr(self, "_scanning", False):
            return
        self._scanning = True
        self.btn_scan.configure(text="Ψάχνω…")
        self.btn_scan.state(["disabled"])

        # Το tkinter δεν είναι thread-safe: το νήμα ΔΕΝ αγγίζει τίποτα γραφικό,
        # αφήνει το αποτέλεσμα σε μια θέση και το κύριο νήμα το παραλαμβάνει.
        self._scan_result = None
        apotelesma = {}

        def douleia():
            try:
                diktya = local_subnets()
                if not diktya:
                    apotelesma["sfalma"] = "Δεν βρέθηκε δίκτυο σε αυτό το μηχάνημα."
                else:
                    vrethentes = []
                    for net in diktya:
                        vrethentes += scan_for_scales(net)
                    apotelesma["zygoi"] = vrethentes
            except Exception as exc:
                apotelesma["sfalma"] = str(exc)
            apotelesma["telos"] = True

        threading.Thread(target=douleia, daemon=True).start()

        def perimene():
            if not apotelesma.get("telos"):
                self.after(250, perimene)
                return
            self._scan_done(apotelesma.get("zygoi"), apotelesma.get("sfalma"))

        self.after(250, perimene)

    def _scan_done(self, vrethentes, sfalma):
        self._scanning = False
        self.btn_scan.configure(text="🔍  Αυτόματη εύρεση ζυγαριών")
        self.btn_scan.state(["!disabled"])
        if sfalma:
            messagebox.showerror(APP_NAME, "Η αναζήτηση δεν ολοκληρώθηκε.\n\n%s" % sfalma)
            return
        if not vrethentes:
            messagebox.showinfo(
                APP_NAME,
                "Δεν βρέθηκε καμία ζυγαριά.\n\nΈλεγξε ότι οι ζυγοί είναι ανοιχτοί και "
                "στο ίδιο δίκτυο με αυτό το μηχάνημα. Μπορείς πάντα να γράψεις τις IP "
                "με το χέρι.")
            return

        # ΠΡΟΣΘΕΤΟΥΜΕ, δεν αντικαθιστούμε: ένας ζυγός που είναι σβηστός τώρα δεν
        # θα βρεθεί, και δεν υπάρχει λόγος να χαθεί η διεύθυνσή του.
        yparxon_ts = parse_ips(self.v_ips.get())
        yparxon_ish = parse_ips(self.v_ish_ips.get())
        nea_ts = [ip for ip, marka, _p in vrethentes
                  if marka == "T-Scale" and ip not in yparxon_ts]
        nea_ish = [ip for ip, marka, _p in vrethentes
                   if marka == "Ishida" and ip not in yparxon_ish]

        grammes = ["Βρέθηκαν %d ζυγαριές:" % len(vrethentes), ""]
        for ip, marka, port in vrethentes:
            simeiosi = "" if (ip in yparxon_ts or ip in yparxon_ish) else "   ← ΚΑΙΝΟΥΡΓΙΑ"
            grammes.append("   %-16s %-9s (θύρα %d)%s" % (ip, marka, port, simeiosi))
        if not nea_ts and not nea_ish:
            grammes += ["", "Όλες είναι ήδη στη λίστα σου — δεν χρειάζεται αλλαγή."]
            messagebox.showinfo(APP_NAME, "\n".join(grammes))
            return
        grammes += ["", "Να προστεθούν οι %d καινούργιες στη λίστα;"
                    % (len(nea_ts) + len(nea_ish)),
                    "(όσες έχεις ήδη γράψει μένουν όπως είναι)"]
        if not messagebox.askyesno(APP_NAME, "\n".join(grammes)):
            return

        if nea_ts:
            self.v_ips.set(", ".join(yparxon_ts + nea_ts))
            self.v_tscale_on.set(True)
        if nea_ish:
            self.v_ish_ips.set(", ".join(yparxon_ish + nea_ish))
            self.v_ish_on.set(True)
        self.on_marka_toggle()
        self.log("Προστέθηκαν ζυγοί — T-Scale: %s | Ishida: %s"
                 % (", ".join(nea_ts) or "καμία νέα", ", ".join(nea_ish) or "καμία νέα"))
        self.on_save()

    def show_scale_status(self):
        """Παράθυρο που δείχνει ποιοι ζυγοί απαντούν αυτή τη στιγμή."""
        win = tk.Toplevel(self)
        win.title("Κατάσταση ζυγών")
        win.geometry("640x440")
        win.minsize(560, 360)
        win.transient(self)
        try:
            win.iconbitmap(resource("logo.ico"))
        except Exception:
            pass

        top = ttk.Frame(win, padding=12)
        top.pack(fill="both", expand=True)
        ttk.Label(top, text="Κατάσταση ζυγών", style="Big.TCheckbutton").pack(anchor="w")
        lbl = ttk.Label(top, style="Hint.TLabel", text="")
        lbl.pack(anchor="w", pady=(2, 8))

        cols = ("ip", "marka", "katastasi", "simeiosi")
        tree = ttk.Treeview(top, columns=cols, show="headings", height=10)
        for c, t, w in (("ip", "Διεύθυνση", 130), ("marka", "Μάρκα", 90),
                        ("katastasi", "Κατάσταση", 110), ("simeiosi", "Σημείωση", 190)):
            tree.heading(c, text=t)
            tree.column(c, width=w, anchor="w")
        tree.pack(fill="both", expand=True)
        tree.tag_configure("anoixtos", foreground=COLORS.get("ok", "#1a7f37"))
        tree.tag_configure("kleistos", foreground=COLORS.get("err", "#b42318"))

        def ananeosi():
            if not win.winfo_exists():
                return
            lbl.configure(text="ελέγχω…")
            win.update_idletasks()
            # Το collect() διαβάζει πεδία του παραθύρου, άρα ΠΡΕΠΕΙ να τρέξει
            # εδώ, στο κύριο νήμα — όχι μέσα στο νήμα που ελέγχει το δίκτυο.
            cfg = self.collect()
            apotelesma = {}

            def douleia():
                try:
                    apotelesma["katastaseis"] = scales_status(cfg)
                except Exception as exc:
                    apotelesma["sfalma"] = str(exc)
                apotelesma["telos"] = True

            threading.Thread(target=douleia, daemon=True).start()

            def perimene():
                if not win.winfo_exists():
                    return
                if not apotelesma.get("telos"):
                    win.after(200, perimene)
                    return
                if apotelesma.get("sfalma"):
                    lbl.configure(text="σφάλμα: %s" % apotelesma["sfalma"])
                    return
                deixe(apotelesma["katastaseis"])

            win.after(200, perimene)

        def deixe(katastaseis):
            if not win.winfo_exists():
                return
            tree.delete(*tree.get_children())
            for ip, marka, anoixtos, ekkremotita in katastaseis:
                tree.insert("", "end", values=(
                    ip, marka,
                    "ανοιχτός" if anoixtos else "δεν απαντά",
                    "περιμένει ενημέρωση" if ekkremotita else ""),
                    tags=("anoixtos" if anoixtos else "kleistos",))
            anoixtoi = sum(1 for _i, _m, ok, _e in katastaseis if ok)
            lbl.configure(text="%d από %d ζυγαριές απαντούν · τελευταίος έλεγχος %s"
                          % (anoixtoi, len(katastaseis),
                             datetime.datetime.now().strftime("%H:%M:%S")))
            if not katastaseis:
                lbl.configure(text="Δεν έχουν οριστεί ζυγοί στο Βήμα 4.")

        bar = ttk.Frame(top)
        bar.pack(fill="x", pady=(10, 0))
        ttk.Button(bar, text="Έλεγχος τώρα", style="Accent.TButton",
                   command=ananeosi).pack(side="left")
        auto = tk.BooleanVar(value=True)
        ttk.Checkbutton(bar, text="αυτόματος έλεγχος κάθε 30 δευτ.",
                        variable=auto).pack(side="left", padx=12)
        ttk.Button(bar, text="Κλείσιμο", command=win.destroy).pack(side="right")

        def xronometro():
            if not win.winfo_exists():
                return
            if auto.get():
                ananeosi()
            win.after(30000, xronometro)

        ananeosi()
        win.after(30000, xronometro)

    def show_about(self):
        messagebox.showinfo(
            APP_NAME,
            "%s\n%s\n\n%s\n\nΡυθμίσεις: %s\nLog: %s"
            % (APP_NAME, APP_VERSION, APP_VENDOR, CONFIG_PATH, LOG_DIR))

    def check_update(self):
        """Ανοίγει το διάλογο επιλογής καναλιού (Stable, Beta Classic, Beta Redesign) και ενημέρωσης."""
        if not self.ask_password():
            return
        self.show_channel_update_dialog()

    def show_channel_update_dialog(self):
        import webbrowser
        win = tk.Toplevel(self)
        win.title("Ενημέρωση Εφαρμογής & Επιλογή Καναλιού — %s" % APP_NAME)
        win.geometry("740x580")
        win.minsize(680, 500)
        try:
            win.iconbitmap(resource("logo.ico"))
        except Exception:
            pass
        win.configure(bg=COLORS["bg"])
        win.transient(self)
        win.grab_set()

        # Header
        hdr = tk.Frame(win, bg=COLORS["card"], padx=20, pady=14,
                       highlightbackground=COLORS["line_subtle"], highlightthickness=1)
        hdr.pack(fill="x")
        tk.Label(hdr, text="🔄  Ενημέρωση Εφαρμογής & Επιλογή Έκδοσης", font=("Segoe UI", 13, "bold"),
                 fg=COLORS["ink"], bg=COLORS["card"]).pack(anchor="w")
        tk.Label(hdr, text="Τρέχουσα εγκατεστημένη έκδοση: %s   |   Επιλέξτε κανάλι για εγκατάσταση ή εναλλαγή." % APP_BUILD,
                 font=FONTS["sm"], fg=COLORS["muted"], bg=COLORS["card"]).pack(anchor="w", pady=(3, 0))

        # Main Container
        body = tk.Frame(win, bg=COLORS["bg"], padx=18, pady=12)
        body.pack(fill="both", expand=True)

        status_lbl = tk.Label(body, text="⏳ Ανάκτηση διαθέσιμων εκδόσεων από το GitHub…",
                              font=FONTS["base_bold"], fg=COLORS["brand_d"], bg=COLORS["bg"])
        status_lbl.pack(pady=12)

        content_frame = tk.Frame(body, bg=COLORS["bg"])

        # Notes section
        notes_box_frame = tk.Frame(content_frame, bg=COLORS["bg"])
        tk.Label(notes_box_frame, text="Σημειώσεις επιλεγμένης έκδοσης:",
                 font=FONTS["sm_bold"], fg=COLORS["muted"], bg=COLORS["bg"]).pack(anchor="w", pady=(8, 4))
        notes_txt = scrolledtext.ScrolledText(notes_box_frame, height=6, font=FONTS["sm"],
                                              bg=COLORS["card"], fg=COLORS["ink"], relief="flat",
                                              highlightbackground=COLORS["line_subtle"], highlightthickness=1)
        notes_txt.pack(fill="both", expand=True)

        selected_channel = tk.StringVar(value="beta_redesign")
        channel_data = {}

        def update_notes():
            ch = selected_channel.get()
            info = channel_data.get(ch)
            notes_txt.configure(state="normal")
            notes_txt.delete("1.0", "end")
            if info:
                t = f"Έκδοση: {info['tag']}  ({info.get('date', '')})\n"
                t += ("-" * 60) + "\n"
                t += info.get("notes") or "Δεν υπάρχουν πρόσθετες σημειώσεις."
                notes_txt.insert("end", t)
            else:
                notes_txt.insert("end", "Δεν βρέθηκαν διαθέσιμες πληροφορίες για αυτό το κανάλι.")
            notes_txt.configure(state="disabled")

        def on_data_loaded(channels):
            status_lbl.pack_forget()
            content_frame.pack(fill="both", expand=True)
            nonlocal channel_data
            channel_data = channels

            defs = [
                ("beta_redesign", "🌟  Beta Redesign (Σύγχρονο UI 2026)",
                 "Νέο γραφικό περιβάλλον με Navigation Rail, Executive Dashboard & KPI Cards",
                 channels.get("beta_redesign")),
                ("beta_classic", "🧪  Beta Classic (Προηγούμενη δοκιμαστική)",
                 "Κλασική δοκιμαστική έκδοση με οριζόντιες καρτέλες",
                 channels.get("beta_classic")),
                ("stable", "🏢  Stable (Έκδοση Παραγωγής καταστημάτων)",
                 "Επίσημη σταθερή έκδοση που τρέχει στα ζωντανά καταστήματα",
                 channels.get("stable")),
            ]

            cards_frame = tk.Frame(content_frame, bg=COLORS["bg"])
            cards_frame.pack(fill="x", pady=(0, 4))

            for key, title, desc, info in defs:
                card = tk.Frame(cards_frame, bg=COLORS["card"], padx=14, pady=10,
                                highlightbackground=COLORS["line_subtle"], highlightthickness=1)
                card.pack(fill="x", pady=4)

                top_line = tk.Frame(card, bg=COLORS["card"])
                top_line.pack(fill="x")

                rb = ttk.Radiobutton(top_line, text=title, value=key, variable=selected_channel,
                                     command=update_notes)
                rb.pack(side="left")

                ver_tag = info["tag"] if info else "—"
                is_curr = bool(info and info.get("version") == APP_BUILD)

                tag_box = tk.Frame(top_line, bg=COLORS["card"])
                tag_box.pack(side="right")

                if is_curr:
                    tk.Label(tag_box, text="[Τρέχουσα]", font=FONTS["sm_bold"],
                             fg=COLORS["ok"], bg=COLORS["ok_light"], padx=6, pady=1).pack(side="right", padx=(6, 0))

                tk.Label(tag_box, text=ver_tag, font=FONTS["base_bold"],
                         fg=COLORS["brand_d"], bg=COLORS["card"]).pack(side="right")

                tk.Label(card, text=desc, font=FONTS["sm"], fg=COLORS["muted"],
                         bg=COLORS["card"]).pack(anchor="w", padx=(24, 0), pady=(2, 0))

            notes_box_frame.pack(fill="both", expand=True, pady=(4, 0))
            update_notes()

        # Thread fetch
        def fetch_job():
            try:
                ch = fetch_available_channels(timeout=10)
                if not ch.get("beta_redesign") and "beta" in APP_BUILD.lower():
                    ch["beta_redesign"] = {
                        "tag": "v" + APP_BUILD,
                        "version": APP_BUILD,
                        "notes": "Ριζική ανανέωση γραφικού περιβάλλοντος 2026 (Navigation Rail, Dashboard, KPI cards).",
                        "url": "",
                        "date": datetime.datetime.now().strftime("%Y-%m-%d")
                    }
                win.after(0, lambda: on_data_loaded(ch))
            except Exception as e:
                win.after(0, lambda: status_lbl.configure(
                    text="❌ Αποτυχία σύνδεσης στο GitHub: %s" % e, fg=COLORS["err"]))

        threading.Thread(target=fetch_job, daemon=True).start()

        # Footer Buttons
        ftr = tk.Frame(win, bg=COLORS["card"], padx=18, pady=12,
                       highlightbackground=COLORS["line_subtle"], highlightthickness=1)
        ftr.pack(side="bottom", fill="x")

        def on_install_click():
            ch = selected_channel.get()
            info = channel_data.get(ch)
            if not info:
                messagebox.showerror(APP_NAME, "Δεν υπάρχουν διαθέσιμες πληροφορίες για το επιλεγμένο κανάλι.")
                return
            v = info.get("version", "")
            url = info.get("url", "")
            if v == APP_BUILD:
                if not messagebox.askyesno(APP_NAME, "Έχετε ήδη εγκατεστημένη την έκδοση %s.\n\nΘέλετε να γίνει επανεγκατάσταση;" % v):
                    return
            else:
                if not messagebox.askyesno(APP_NAME, "Επιλέξατε την έκδοση %s (%s).\n\nΝα προχωρήσει η λήψη και εγκατάσταση;" % (v, ch)):
                    return
            win.destroy()
            self.install_update(url, v)

        ttk.Button(ftr, text="🌐  Προβολή στο GitHub", style="Ghost.TButton",
                   command=lambda: webbrowser.open(UPDATE_PAGE_URL)).pack(side="left")
        ttk.Button(ftr, text="✕  Κλείσιμο", style="Ghost.TButton",
                   command=win.destroy).pack(side="right", padx=(8, 0))
        ttk.Button(ftr, text="▶  Εγκατάσταση Επιλεγμένης Έκδοσης", style="Accent.TButton",
                   command=on_install_click).pack(side="right")

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
        win.geometry("1040x680")
        try:
            win.iconbitmap(resource("logo.ico"))
        except Exception:
            pass
        box = self._console(win, 30, FONTS["mono"])
        box.pack(fill="both", expand=True, padx=14, pady=12)
        box.insert("1.0", report)
        box.configure(state="disabled")

        bar = ttk.Frame(win, style="Bar.TFrame", padding=(14, 10))
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
        if hasattr(self, "status_ticker") and self.status_ticker:
            try:
                self.status_ticker.configure(text=f"{stamp}  {msg[:110]}")
            except Exception:
                pass

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
        self.last_run = (datetime.datetime.now(), True, "")
        self.set_status("Επιτυχία", COLORS["ok"])
        # Ξέρουμε ότι ολοκληρώθηκε η δική μας ροή· αν ο ζυγός δέχτηκε τα δεδομένα
        # το λέει το log της εφαρμογής του ζυγού, όχι εμείς.
        if not silent and self.cfg.get("show_success_popup"):
            messagebox.showinfo(APP_NAME, "Τα βήματα ολοκληρώθηκαν και η εφαρμογή του ζυγού "
                                          "εκτελέστηκε.\n\nΑν η μεταφορά πέτυχε, φαίνεται στο "
                                          "log της εφαρμογής του ζυγού.")

    def _done_err(self, text, silent):
        self.last_run = (datetime.datetime.now(), False, text.strip().split("\n")[0][:120])
        self.set_status("Σφάλμα", COLORS["err"])
        self.log("ΣΦΑΛΜΑ -> " + text.replace("\n", "\n         "))
        self.notify_error(text)

    def is_hidden(self):
        try:
            return self.state() in ("withdrawn", "iconic")
        except tk.TclError:
            return True

    def notify_error(self, text):
        """Δείχνει το σφάλμα ΧΩΡΙΣ να σταματήσει το πρόγραμμα.

        Το πρόγραμμα τρέχει σε server καταστήματος, αφύλακτο. Ένα modal παράθυρο
        θα έμενε ανοιχτό μέχρι να το δει κάποιος — και ώσπου να πατηθεί το «ΟΚ»
        καμία επόμενη αλλαγή τιμών δεν θα περνούσε στους ζυγούς. Γι' αυτό το
        σφάλμα μένει σε μπάρα μέσα στο παράθυρο, στο log, και στο εικονίδιο
        κάτω δεξιά: φαίνεται, αλλά δεν μπλοκάρει τίποτα.
        """
        self.pending_error = text
        self.show_error_bar(text)
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

    def show_error_bar(self, text):
        """Κόκκινη λωρίδα με το τελευταίο σφάλμα — δεν περιμένει κανένα κλικ."""
        proti = text.strip().split("\n")[0]
        try:
            self.err_lbl.configure(
                text="⚠  %s   (%s)" % (proti[:150],
                                       datetime.datetime.now().strftime("%H:%M")))
            if hasattr(self, "workspace_bottom"):
                self.err_bar.pack(side="bottom", fill="x", before=self.workspace_bottom)
            elif hasattr(self, "txt_log") and self.txt_log.master == self.err_bar.master:
                self.err_bar.pack(side="bottom", fill="x", before=self.txt_log)
            else:
                self.err_bar.pack(side="bottom", fill="x")
        except Exception:
            pass

    def clear_error_bar(self):
        self.pending_error = None
        try:
            self.err_bar.pack_forget()
        except Exception:
            pass
        if getattr(self, "tray", None) is not None:
            try:
                self.tray.title = APP_NAME
            except Exception:
                pass

    def show_last_errors(self):
        """Τα σφάλματα των τελευταίων ημερών, από τα αρχεία log."""
        grammes = []
        try:
            arxeia = sorted(glob.glob(os.path.join(LOG_DIR, "*.log")))[-3:]
            for path in reversed(arxeia):
                with io.open(path, encoding="utf-8", errors="replace") as fh:
                    keimeno = fh.read()
                mera = os.path.basename(path)
                for blok in keimeno.split("\n"):
                    if "ΣΦΑΛΜΑ" in blok or "ΑΠΟΤΥΧΙΑ" in blok or "ΔΕΝ ΕΝΗΜΕΡΩΘΗΚΕ" in blok:
                        grammes.append("%s  %s" % (mera[-14:-4], blok.strip()))
        except Exception as exc:
            grammes = ["Δεν διαβάστηκαν τα log: %s" % exc]
        if not grammes:
            grammes = ["Κανένα σφάλμα στα τελευταία αρχεία log."]

        win = tk.Toplevel(self)
        win.title("Τελευταία σφάλματα")
        win.geometry("960x520")
        win.transient(self)
        f = ttk.Frame(win, padding=16)
        f.pack(fill="both", expand=True)
        ttk.Label(f, text="Τελευταία σφάλματα", style="Big.TCheckbutton").pack(anchor="w")
        ttk.Label(f, style="Hint.TLabel",
                  text="Από τα αρχεία log των τελευταίων ημερών. Το πρόγραμμα δεν "
                       "σταμάτησε για κανένα από αυτά."
                  ).pack(anchor="w", pady=(2, 8))
        box = self._console(f, 18, FONTS["mono"])
        box.pack(fill="both", expand=True)
        box.insert("1.0", "\n".join(grammes[-400:]))
        box.see("end")
        bar = ttk.Frame(f)
        bar.pack(fill="x", pady=(12, 0))
        ttk.Button(bar, text="Άνοιγμα αρχείου log",
                   command=self.open_log_file).pack(side="left")
        ttk.Button(bar, text="Κλείσιμο", command=win.destroy).pack(side="right")

    # ---------------- daemon ----------------
    def toggle_watch(self, quiet=False):
        """quiet=True από αυτόματη εκκίνηση: κανένα modal, μόνο λωρίδα και log."""
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
            msg = "Διάλεξε πρώτα το αρχείο που βγάζει το ERP (Βήμα 1)."
            if quiet:
                self.log("Η παρακολούθηση δεν ξεκίνησε: " + msg)
                self.show_error_bar("Η παρακολούθηση δεν ξεκίνησε — " + msg)
            else:
                messagebox.showerror(APP_NAME, msg)
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

    def _pending_interval(self):
        """Κάθε πόσο ξαναδοκιμάζουμε έναν κλειστό ζυγό (δευτερόλεπτα)."""
        try:
            lepta = int(self.cfg.get("pending_retry_minutes", 15) or 15)
        except (TypeError, ValueError):
            lepta = 15
        return max(60, lepta * 60)

    def _watch_loop(self):
        epomeni_dokimi = time.time() + self._pending_interval()
        while self.watching and not self.stop_event.is_set():
            time.sleep(max(1, int(self.cfg.get("poll_seconds", 3))))

            # Ζυγός που ήταν κλειστός δεν πρέπει να περιμένει την επόμενη αλλαγή
            # τιμών για να ενημερωθεί — μπορεί να αργήσει μέρες.
            if time.time() >= epomeni_dokimi:
                epomeni_dokimi = time.time() + self._pending_interval()
                if load_pending() and not (self.worker and self.worker.is_alive()):
                    try:
                        retry_pending_scales(
                            self.cfg,
                            lambda m: self.after(0, self.log, m),
                            self.stop_event)
                    except Exception as exc:
                        self.after(0, self.log, "Επανάληψη εκκρεμών: σφάλμα (%s)" % exc)

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
        app.after(900, lambda: None if app.watching else app.toggle_watch(quiet=True))
    app.mainloop()
