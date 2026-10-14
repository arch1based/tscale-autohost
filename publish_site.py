# -*- coding: utf-8 -*-
"""Βγάζει στο itnow.gr την έκδοση που έχτισε το GitHub Actions — από εκεί ενημερώνονται τα καταστήματα.

    python3 publish_site.py            # τελευταία έκδοση (Latest) του GitHub
    python3 publish_site.py 2.20.0     # συγκεκριμένη έκδοση

1. κατεβάζει το ICSautoScaleUpdater.zip από το release v<έκδοση> (gh CLI — δουλεύει και με ιδιωτικό repo),
2. το ανεβάζει στο /www/keys/downloads/ICSautoScaleUpdater.zip (+ το εγχειρίδιο PDF),
3. γράφει το /www/keys/downloads/tscale.json → αυτό διαβάζει το «Έλεγχος ενημέρωσης».

Τα στοιχεία FTP διαβάζονται από το upload.py του itnow-web (gitignored). Ένα μόνο login.
"""
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import zipfile
from ftplib import FTP

HERE = os.path.dirname(os.path.abspath(__file__))
CREDS = os.environ.get("ITNOW_UPLOAD_PY", os.path.expanduser("~/projects/itnow-web/upload.py"))
REMOTE = "/www/keys/downloads"
ZIP_URL = "https://itnow.gr/keys/downloads/ICSautoScaleUpdater.zip"
PDF = os.path.join(HERE, "docs", "Egxeiridio_ICSautoScaleUpdater.pdf")


def gh(*args):
    return subprocess.run(["gh", *args], cwd=HERE, check=True, capture_output=True, text=True).stdout.strip()


version = (sys.argv[1] if len(sys.argv) > 1 else
           gh("release", "view", "--json", "tagName", "-q", ".tagName")).lstrip("vV")
notes = gh("release", "view", "v" + version, "--json", "body", "-q", ".body")
tmp = tempfile.mkdtemp()
gh("release", "download", "v" + version, "-p", "ICSautoScaleUpdater.zip", "-D", tmp)
zpath = os.path.join(tmp, "ICSautoScaleUpdater.zip")
with zipfile.ZipFile(zpath) as z:
    if "ICSautoScaleUpdater.exe" not in z.namelist() or os.path.getsize(zpath) < 5_000_000:
        sys.exit("Το zip δεν φαίνεται έγκυρο — σταματάω.")

manifest = json.dumps({"version": version, "notes": notes, "url": ZIP_URL},
                      ensure_ascii=False, indent=2).encode("utf-8")

src = io.open(CREDS, encoding="utf-8").read()
get = lambda k: re.search(rf"^{k}\s*=\s*['\"](.*?)['\"]", src, re.M).group(1)
ftp = FTP(get("host"), timeout=120)
ftp.login(get("user"), get("password"))
with open(zpath, "rb") as f:  # πρώτα το zip, μετά η δήλωση έκδοσης — ποτέ το αντίστροφο
    ftp.storbinary(f"STOR {REMOTE}/ICSautoScaleUpdater.zip", f)
if os.path.isfile(PDF):
    with open(PDF, "rb") as f:
        ftp.storbinary(f"STOR {REMOTE}/Egxeiridio_ICSautoScaleUpdater.pdf", f)
ftp.storbinary(f"STOR {REMOTE}/tscale.json", io.BytesIO(manifest))
ftp.quit()
print(f"✔ ICSautoScaleUpdater {version} στο itnow.gr ({ZIP_URL})")
