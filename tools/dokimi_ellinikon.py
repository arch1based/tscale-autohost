# -*- coding: utf-8 -*-
"""Βρίσκει ΠΟΙΑ κωδικοσελίδα θέλει η ζυγαριά, ρωτώντας την ίδια τη ζυγαριά.

Στέλνει τρία δοκιμαστικά προϊόντα με διαδοχικούς κωδικούς. Το καθένα γράφει το
ίδιο ελληνικό όνομα, αλλά με άλλο τρόπο στο καλώδιο. Μετά κοιτάς στη ζυγαριά
ποιο από τα τρία διαβάζεται σωστά — αυτό είναι το σωστό.

    python dokimi_ellinikon.py 10.130.20.51

Τα δοκιμαστικά προϊόντα έχουν κωδικούς 90001-90003 για να ξεχωρίζουν και να
σβήνονται εύκολα μετά.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import autohost as A                                          # noqa: E402

# Γράμματα που «σπάνε» χαρακτηριστικά σε κάθε λάθος κωδικοσελίδα.
DOKIMI = "ΚΙΤΡΙΝΟΡΙΖΑ ΑΒΓΔ"

PARALLAGES = [
    ("90001", False, "utf-8",  "καθαρό UTF-8         («Κ» = ce 9a)"),
    ("90002", True,  "utf-8",  "mojibake UTF-8       («Κ» = c3 8a)"),
    ("90003", True,  "cp1252", "αυτούσια cp1253      («Κ» = ca)"),
]


def dokimastiko_proion(kodikos, onoma):
    """Ένα προϊόν με όλα τα πεδία που περιμένει ο ζυγός."""
    row = dict(A.MODEL_FIELDS)
    row["product_number"] = kodikos
    row["product_code"] = kodikos
    row["product_name"] = onoma
    row["product_abbr"] = onoma
    row["original_price"] = "1.00"
    row["price_unit_index"] = "0"
    return row


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    ip = sys.argv[1].strip()

    ok, giati = A.scale_reachable(ip)
    if not ok:
        print("Ο ζυγός %s δεν απαντά: %s" % (ip, giati))
        return 1

    print("Ζυγός %s — στέλνονται %d δοκιμαστικά προϊόντα.\n" % (ip, len(PARALLAGES)))
    for kodikos, quirk, wire, perigrafi in PARALLAGES:
        items = [dokimastiko_proion(kodikos, DOKIMI)]
        soma = A.encode_body(items, quirk, wire)
        deigma = soma.split(b'"product_name":"')[1][:12].hex(" ")
        ok, apantisi = A.send_to_scale(ip, items, print, quirk=quirk, wire=wire)
        print("  %s  %s" % (kodikos, perigrafi))
        print("         bytes στο καλώδιο: %s" % deigma)
        print("         %s\n" % ("ΕΠΙΤΥΧΙΑ — " + apantisi if ok else "ΑΠΟΤΥΧΙΑ — " + apantisi))

    print("Τώρα κοίτα στη ζυγαριά τα προϊόντα 90001, 90002 και 90003.")
    print("Ψάξε ποιο δείχνει καθαρά: %s" % DOKIMI)
    print()
    print("  δείχνει σωστά το 90001  ->  direct_quirk = false, direct_wire_encoding = utf-8")
    print("  δείχνει σωστά το 90002  ->  direct_quirk = true,  direct_wire_encoding = utf-8")
    print("  δείχνει σωστά το 90003  ->  direct_quirk = true,  direct_wire_encoding = cp1252")
    print()
    print("Πες μου ποιο ήταν, και το κλειδώνουμε στις ρυθμίσεις.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
