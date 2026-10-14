# -*- coding: utf-8 -*-
"""Δημοσίευση νέας έκδοσης.

Από οποιοδήποτε σύστημα (Linux/Mac/Windows) — το exe το χτίζει το GitHub Actions:
    python3 release.py 1.1.0 "Τι άλλαξε"

Δοκιμαστική έκδοση (beta) — ΜΟΝΟ από το branch «beta», ποτέ από το main:
    python3 release.py 2.20.0-beta.1 "Τι δοκιμάζουμε"
Βγαίνει ως pre-release με δικό της exe (ICSautoScaleUpdater-beta). Οι κανονικές
εγκαταστάσεις δεν τη βλέπουν· τη βλέπουν μόνο όσες τρέχουν ήδη beta.

Από Windows, με τοπικό build και gh:
    python release.py 1.1.0 "Τι άλλαξε" --local

Χωρίς να αλλάξει τίποτα στο GitHub:
    python3 release.py 1.1.0 "..." --dry-run
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


def current_branch():
    out = subprocess.check_output(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=HERE)
    return out.decode("utf-8", "replace").strip()


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    dry = "--dry-run" in sys.argv
    if not args:
        raise SystemExit('Χρήση: python release.py 1.1.0 "Τι άλλαξε" [--dry-run]')
    version = args[0].lstrip("vV")
    notes = args[1] if len(args) > 1 else ""

    if not re.match(r"^\d+\.\d+(\.\d+)?(-beta\.\d+)?$", version):
        raise SystemExit("Ο αριθμός έκδοσης θέλει μορφή 1.1.0 (ή 1.1.0-beta.1 για δοκιμαστική)")

    beta = "-beta." in version
    branch = current_branch()
    # Δικλείδα: μια beta δεν ανεβαίνει ποτέ στο main (θα την έβλεπαν όλα τα
    # καταστήματα μέσω του VERSION), και μια τελική δεν βγαίνει από άλλο branch.
    if beta and branch == "main":
        raise SystemExit("Beta έκδοση από το main; Όχι. Πήγαινε στο branch beta: git checkout beta")
    if not beta and branch != "main":
        raise SystemExit("Τελική έκδοση από το branch «%s»; Οι τελικές βγαίνουν μόνο από το main."
                         % branch)

    bump(version, notes)
    if dry:
        print("--dry-run: σταματάω πριν από commit/push. (branch: %s, %s)"
              % (branch, "BETA" if beta else "τελική"))
        return

    run(["git", "add", "-A"])
    run(["git", "commit", "-m", "Έκδοση %s" % version])
    run(["git", "push", "origin", branch])

    if "--local" not in sys.argv:
        # Το exe το χτίζει το GitHub Actions με το που ανέβει το tag.
        run(["git", "tag", "-a", "v" + version, "-m", "Έκδοση %s" % version])
        run(["git", "push", "origin", "v" + version])
        print("\nΤο tag v%s ανέβηκε. Το GitHub χτίζει το exe (~3 λεπτά) και το ανεβάζει "
              "στο Release%s." % (version, " ως pre-release (beta)" if beta else ""))
        print("Παρακολούθηση:  gh run watch")
        print("Έλεγχος:        gh release view v%s" % version)
        return

    app_id = APP_ID + ("-beta" if beta else "")
    run([os.path.join(HERE, "build.bat")], shell=True)
    exe = os.path.join(HERE, "dist", app_id, app_id + ".exe")
    if not os.path.isfile(exe):
        raise SystemExit("Δεν βρέθηκε το %s — απέτυχε το build;" % exe)

    run(["gh", "release", "create", "v" + version, exe,
         "--title", "Έκδοση %s" % version, "--notes", notes or "Νέα έκδοση"]
        + (["--prerelease"] if beta else []))
    print("\nΈτοιμο. Οι εγκαταστάσεις θα δουν την %s με το «Έλεγχος ενημέρωσης»." % version)


if __name__ == "__main__":
    main()
