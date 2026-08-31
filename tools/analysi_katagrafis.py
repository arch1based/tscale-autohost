# -*- coding: utf-8 -*-
"""Λέει με ΠΟΙΑ κωδικοσελίδα γράφει τα ελληνικά μια καταγραφή του AutoProcess.

    python analysi_katagrafis.py katagrafi.bin

Η καταγραφή πρέπει να είναι το ΩΜΟ σώμα του αιτήματος (το βγάζει το
raw_capture.py) — όχι αντιγραμμένο κείμενο από οθόνη, γιατί η αντιγραφή
καταστρέφει ακριβώς την πληροφορία που ψάχνουμε.

Γιατί χρειάζεται: το «καθαρό UTF-8» και το «mojibake UTF-8» πιάνουν και τα δύο
2 bytes ανά ελληνικό γράμμα και δείχνουν και τα δύο «ÊÉÔÑÉÍÏÑÉÆÁ» όταν τα
κοιτάξεις. Ξεχωρίζουν ΜΟΝΟ από τα bytes.
"""
import re
import sys

# Πώς γράφεται το «Κ» σε κάθε υποψήφια κωδικοσελίδα.
YPOPSIFIES = [
    ("καθαρό UTF-8",     "utf-8",   False, "direct_quirk=false, direct_wire_encoding=utf-8"),
    ("mojibake UTF-8",   "utf-8",   True,  "direct_quirk=true,  direct_wire_encoding=utf-8"),
    ("αυτούσια cp1253",  "cp1252",  True,  "direct_quirk=true,  direct_wire_encoding=cp1252"),
    ("κινεζικό GB2312",  "gb2312",  False, "direct_quirk=false, direct_wire_encoding=gb2312"),
    ("κινεζικό Big5",    "big5",    False, "direct_quirk=false, direct_wire_encoding=big5"),
]


def moji(text):
    """cp1253 διαβασμένο ως cp1252 — το «σφάλμα» που υποθέταμε για το AutoProcess."""
    try:
        return text.encode("cp1253").decode("cp1252", "replace")
    except UnicodeEncodeError:
        return text


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    raw = open(sys.argv[1], "rb").read()
    print("Καταγραφή: %s bytes\n" % format(len(raw), ",d").replace(",", "."))

    m = re.search(rb'"product_name":"([^"]{4,})"', raw)
    if not m:
        print("Δεν βρέθηκε πεδίο product_name. Σίγουρα είναι ωμό σώμα αιτήματος;")
        return 1
    deigma = m.group(1)
    print("Πρώτο όνομα προϊόντος, ωμά bytes:")
    print("   %s\n" % deigma[:24].hex(" "))

    print("Δοκιμή κάθε κωδικοσελίδας:")
    vrethike = []
    for onoma, enc, quirk, rythmisi in YPOPSIFIES:
        try:
            keimeno = deigma.decode(enc)
        except Exception:
            print("   %-18s δεν αποκωδικοποιείται" % onoma)
            continue
        if quirk:
            # Γύρνα το mojibake πίσω: cp1252 -> bytes -> cp1253. Χωρίς «replace»:
            # αν το κείμενο έχει ήδη κανονικά ελληνικά, δεν είναι mojibake και
            # πρέπει να απορριφθεί, όχι να «διορθωθεί» σιωπηλά.
            try:
                keimeno = keimeno.encode("cp1252").decode("cp1253")
            except Exception:
                print("   %-18s δεν είναι αυτή" % onoma)
                continue
        ellinika = sum(1 for ch in keimeno if "Ά" <= ch <= "ώ")
        simadi = "  <-- ΕΛΛΗΝΙΚΑ" if ellinika >= 3 else ""
        print("   %-18s %s%s" % (onoma, keimeno[:34], simadi))
        if ellinika >= 3:
            vrethike.append((onoma, rythmisi))

    print()
    if len(vrethike) == 1:
        onoma, rythmisi = vrethike[0]
        print("ΑΠΑΝΤΗΣΗ: το AutoProcess στέλνει %s." % onoma)
        print("Βάλε στις ρυθμίσεις:  %s" % rythmisi)
    elif not vrethike:
        print("Καμία κωδικοσελίδα δεν έδωσε ελληνικά — στείλε μου την καταγραφή.")
    else:
        print("Ταιριάζουν %d — στείλε μου την καταγραφή να τις ξεχωρίσω."
              % len(vrethike))
    return 0


if __name__ == "__main__":
    sys.exit(main())
