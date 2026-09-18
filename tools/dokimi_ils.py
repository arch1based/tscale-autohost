# -*- coding: utf-8 -*-
"""Συγκρίνει το hostILS που φτιάχνουμε με αρχείο που ήδη δέχεται το ILS.

Το ILS διαβάζει αρχείο **σταθερού πλάτους**: κάθε πεδίο κάθεται σε
συγκεκριμένες θέσεις χαρακτήρων, και οι θέσεις ορίζονται στο «Field settings»
του (αποθηκεύονται στο AutoTrans.CFG). Αν μετακινηθεί έστω ένας χαρακτήρας,
ο ζυγός διαβάζει λάθος τιμή — χωρίς να παραπονεθεί.

Γι' αυτό δεν αρκεί «βγήκε αρχείο»: το βάζουμε δίπλα σε ένα αληθινό και
ελέγχουμε θέση προς θέση.

    python3 dokimi_ils.py ΔΙΚΟ_ΜΑΣ.txt ΑΛΗΘΙΝΟ.plu [AutoTrans.CFG]
"""

import io
import re
import sys

# Τα ενεργά πεδία, όπως τα διαβάζει το ILS. Αν δοθεί AutoTrans.CFG, τα παίρνουμε
# από εκεί — είναι η αλήθεια της συγκεκριμένης εγκατάστασης.
DEFAULT_FIELDS = (("Code", 2, 5), ("PluName", 7, 30), ("PluNameExtent", 37, 10),
                  ("UnitPrice", 64, 5), ("WeightPos", 69, 1))


def fields_from_cfg(path):
    """Διαβάζει θέσεις και μήκη από το AutoTrans.CFG του ILS."""
    try:
        keimeno = io.open(path, encoding="cp1253", errors="replace").read()
    except Exception as exc:
        print("δεν διαβάστηκε το CFG (%s) — χρησιμοποιώ τις προεπιλογές" % exc)
        return list(DEFAULT_FIELDS)
    val = dict(re.findall(r"^(\w+)=(.*)$", keimeno, re.M))
    zeugaria = (("PluName", "ChkPluName", "CboxPluName", "PluName_Len"),
                ("PluNameExtent", "ChkPluNameExtent", "PluNameExtent", "PluNameExtent_Len"),
                ("LfCode", "ChkLfCode", "CboxLfcode", "lfCode_Len"),
                ("Code", "ChkCode", "CboxCode", "Code_Len"),
                ("UnitPrice", "ChkUnitPrice", "CboxUnitPrice", "UnitPrice_Len"),
                ("Department", "ChkDeptMent", "CboxDeptMent", "Department_Len"),
                ("Tare", "ChkTare", "CboxTare", "Tare_Len"),
                ("WeightUnit", "ChkWeightUnit", "CboxWeightPos", "WeightUnit_Len"))
    out = []
    for onoma, chk, cbox, ln in zeugaria:
        if val.get(chk, "0").strip() != "1":
            continue
        try:
            out.append((onoma, int(val[cbox]), int(val[ln])))
        except (KeyError, ValueError):
            continue
    return out or list(DEFAULT_FIELDS)


def grammes(path):
    raw = open(path, "rb").read()
    raw = raw.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    return [l.decode("cp1253", "replace") for l in raw.split(b"\n") if l.strip()]


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        return 1
    diko_mas = grammes(sys.argv[1])
    alithino = grammes(sys.argv[2])
    pedia = fields_from_cfg(sys.argv[3]) if len(sys.argv) > 3 else list(DEFAULT_FIELDS)

    lathi = []
    mikoi_mas = {len(l) for l in diko_mas}
    mikoi_tou = {len(l) for l in alithino}
    print("μήκος γραμμής — δικό μας %s · αληθινό %s"
          % (sorted(mikoi_mas), sorted(mikoi_tou)))
    if mikoi_mas != mikoi_tou:
        lathi.append("το μήκος της γραμμής δεν ταιριάζει")
    if len(mikoi_mas) != 1:
        lathi.append("οι δικές μας γραμμές δεν έχουν όλες το ίδιο μήκος")

    print("\nτα πεδία που διαβάζει το ILS:")
    for onoma, pos, ln in pedia:
        a = alithino[0][pos - 1:pos - 1 + ln]
        d = diko_mas[0][pos - 1:pos - 1 + ln]
        gemato = "✓" if d.strip() else "✗ ΚΕΝΟ"
        print("   %-14s θέση %-3d μήκος %-3d  αληθινό %-32r δικό μας %-32r %s"
              % (onoma, pos, ln, a, d, gemato))
        if not d.strip():
            lathi.append("το πεδίο %s βγαίνει κενό" % onoma)

    print("\nέλεγχος ότι κάθε γραμμή μας γεμίζει τα πεδία:")
    for onoma, pos, ln in pedia:
        adeia = sum(1 for g in diko_mas if not g[pos - 1:pos - 1 + ln].strip())
        if adeia:
            print("   %-14s %d γραμμές με κενό πεδίο" % (onoma, adeia))
            lathi.append("%s: %d γραμμές με κενό" % (onoma, adeia))
    if not lathi:
        print("   όλα τα πεδία γεμάτα σε όλες τις γραμμές")

    print("\n" + ("ΟΛΑ ΚΑΛΑ — το αρχείο μας διαβάζεται όπως το αληθινό"
                 if not lathi else "ΠΡΟΒΛΗΜΑΤΑ:\n  - " + "\n  - ".join(lathi)))
    return 1 if lathi else 0


if __name__ == "__main__":
    sys.exit(main())
