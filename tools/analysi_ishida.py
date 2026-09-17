# -*- coding: utf-8 -*-
"""Διαβάζει την καταγραφή της γέφυρας και βγάζει τη δομή των PLU του Ishida.

Δίνε του τον φάκελο `oma_gefyra` που άφησε η gefyra_ishida.py:

    python3 analysi_ishida.py /δρόμος/προς/oma_gefyra
    python3 analysi_ishida.py oma_gefyra --plu 50      (μία εγγραφή, πεδίο-πεδίο)

Τι δείχνει:
  * πόσες εγγραφές στάλθηκαν και πόσες διαβάστηκαν
  * αν όλες έχουν το ίδιο πλήθος πεδίων
  * ποια πεδία διαφέρουν ανάμεσα σε ανάγνωση και αποστολή για το ίδιο PLU
  * τα γνωστά πεδία (κωδικός, όνομα, τιμή, ΦΠΑ) για δείγμα εγγραφών
"""

import csv
import glob
import os
import sys

SUBHEADER = 10

# Όσα πεδία έχουν ταυτοποιηθεί σε ζυγό UNI-3 του πελάτη ERGON, 17/9/2026.
GNOSTA = {
    0: "κωδικός PLU",
    7: "ταχύτητα/βάρος (1000)",
    68: "όνομα (cp1253, με \\x0d\\x08\\x02)",
    70: "ΤΙΜΗ σε λεπτά (790 = 7,90 €)",
    88: "ΦΠΑ (21)",
    89: "κωδικός PLU, δεύτερη φορά",
}


def eggrafes(path):
    """Σπάει το σώμα ενός μηνύματος σε εγγραφές, με τις υπο-κεφαλίδες."""
    raw = open(path, "rb").read()
    off = 0
    out = []
    while off + SUBHEADER <= len(raw):
        ln = int.from_bytes(raw[off + 6:off + SUBHEADER], "big")
        if ln <= 0 or off + SUBHEADER + ln > len(raw):
            break
        out.append(raw[off + SUBHEADER:off + SUBHEADER + ln].decode("cp1253"))
        off += SUBHEADER + ln
    return out


def pedia(grammi):
    return next(csv.reader([grammi]))


def mazepse(fakelos):
    stalthikan, diavastikan = [], []
    for f in sorted(glob.glob(os.path.join(fakelos, "*", "*msg1001.bin"))):
        if os.path.basename(f).startswith("SLP"):
            stalthikan += eggrafes(f)
    for f in sorted(glob.glob(os.path.join(fakelos, "*", "*msg2001.bin"))):
        if not os.path.basename(f).startswith("SLP"):
            diavastikan += eggrafes(f)
    return stalthikan, diavastikan


def mia_eggrafi(eg, kodikos):
    for r in eg:
        a = pedia(r)
        if a and a[0] == kodikos:
            print("PLU %s — %d πεδία\n" % (kodikos, len(a)))
            for i, v in enumerate(a):
                simeiosi = GNOSTA.get(i, "")
                if v == "" and not simeiosi:
                    continue
                print("  [%3d] %-40s %s" % (i, repr(v)[:40], simeiosi))
            return True
    return False


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return
    fakelos = sys.argv[1]
    stalthikan, diavastikan = mazepse(fakelos)
    print("εστάλησαν: %d εγγραφές · διαβάστηκαν: %d εγγραφές"
          % (len(stalthikan), len(diavastikan)))

    if "--plu" in sys.argv:
        kodikos = sys.argv[sys.argv.index("--plu") + 1]
        if not mia_eggrafi(stalthikan, kodikos) and not mia_eggrafi(diavastikan, kodikos):
            print("Δεν βρέθηκε PLU %s." % kodikos)
        return

    plithi = set(len(pedia(r)) for r in stalthikan + diavastikan)
    print("πλήθος πεδίων ανά εγγραφή: %s%s"
          % (sorted(plithi), "  ✓ σταθερό" if len(plithi) == 1 else "  ⚠ ΔΕΝ είναι σταθερό"))

    d = {pedia(r)[0]: pedia(r) for r in diavastikan}
    diafores, koina = {}, 0
    for r in stalthikan:
        a = pedia(r)
        b = d.get(a[0])
        if not b:
            continue
        koina += 1
        for i in range(min(len(a), len(b))):
            if a[i] != b[i]:
                diafores.setdefault(i, []).append((b[i], a[i]))
    print("κοινά PLU σε ανάγνωση και αποστολή: %d" % koina)
    if diafores:
        print("\nπεδία που διαφέρουν (ανάγνωση -> αποστολή):")
        for i, v in sorted(diafores.items()):
            zeugi = set(v)
            athoo = all(b in ("", "0") and a in ("", "0", "1") for b, a in zeugi)
            print("  [%3d] σε %d PLU · %s%s"
                  % (i, len(v), sorted(zeugi)[:3],
                     "   (κενό/μηδέν — αθώο)" if athoo else "   ⚠ ΟΥΣΙΑΣΤΙΚΗ"))

    print("\nδείγμα εγγραφών:")
    for r in (stalthikan or diavastikan)[:8]:
        a = pedia(r)
        print("  PLU %-6s τιμή %-8s ΦΠΑ %-4s %s"
              % (a[0], a[70] if len(a) > 70 else ";",
                 a[88] if len(a) > 88 else ";",
                 (a[68] if len(a) > 68 else "")[:44]))


if __name__ == "__main__":
    main()
