# -*- coding: utf-8 -*-
"""Δημοσίευση νέας έκδοσης: ανεβάζει τον αριθμό, χτίζει το exe, φτιάχνει GitHub Release.

Χρήση (από Windows, με εγκατεστημένο gh):
    python release.py 1.1.0 "Τι άλλαξε σε αυτή την έκδοση"
    python release.py 1.1.0 "..." --dry-run      (χωρίς build/upload)
"""

import io
import os
import re
import sys
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
APP_ID = "ICSautoScaleUpdater"


def bump(version, notes):
    """Γράφει τη νέα έκδοση σε VERSION και autohost.py."""
    with io.open(os.path.join(HERE, "VERSION"), "w", encoding="utf-8") as fh:
        fh.write(version + "\n" + (notes or "") + "\n")

    src = os.path.join(HERE, "autohost.py")
    with io.open(src, encoding="utf-8") as fh:
        text = fh.read()
    new_text, n = re.subn(r'APP_BUILD = "[^"]*"', 'APP_BUILD = "%s"' % version, text, count=1)
    if n != 1:
        raise SystemExit("Δεν βρέθηκε το APP_BUILD στο autohost.py")
    with io.open(src, "w", encoding="utf-8") as fh:
        fh.write(new_text)
    print("Έκδοση -> %s (VERSION + autohost.py)" % version)


def run(cmd, **kw):
    print("$ " + " ".join(cmd))
    if subprocess.call(cmd, cwd=HERE, **kw) != 0:
        raise SystemExit("Απέτυχε: %s" % " ".join(cmd))


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    dry = "--dry-run" in sys.argv
    if not args:
        raise SystemExit('Χρήση: python release.py 1.1.0 "Τι άλλαξε" [--dry-run]')
    version = args[0].lstrip("vV")
    notes = args[1] if len(args) > 1 else ""

    if not re.match(r"^\d+\.\d+(\.\d+)?$", version):
        raise SystemExit("Ο αριθμός έκδοσης θέλει μορφή 1.1.0")

    bump(version, notes)
    if dry:
        print("--dry-run: σταματάω πριν από build και upload.")
        return

    run([os.path.join(HERE, "build.bat")], shell=True)
    exe = os.path.join(HERE, "dist", APP_ID + ".exe")
    if not os.path.isfile(exe):
        raise SystemExit("Δεν βρέθηκε το %s — απέτυχε το build;" % exe)

    run(["git", "add", "-A"])
    run(["git", "commit", "-m", "Έκδοση %s" % version])
    run(["git", "push", "origin", "main"])
    run(["gh", "release", "create", "v" + version, exe,
         "--title", "Έκδοση %s" % version, "--notes", notes or "Νέα έκδοση"])
    print("\nΈτοιμο. Οι εγκαταστάσεις θα δουν την %s με το «Έλεγχος ενημέρωσης»." % version)


if __name__ == "__main__":
    main()
