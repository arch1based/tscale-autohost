# -*- coding: utf-8 -*-
"""Απενεργοποιεί προϊόντα στον ζυγό (disabled=1), με backup πριν από κάθε αλλαγή.

    python disable_proionta.py 10.130.20.51 --lista
    python disable_proionta.py 10.130.20.51 4547 4548 4549
    python disable_proionta.py 10.130.20.51 4547 --kai-onoma
    python disable_proionta.py 10.130.20.51 4547 --anairesi

Δεν υπάρχει εντολή διαγραφής στο πρωτόκολλο του ζυγού: το «σβήσιμο» γίνεται
θέτοντας disabled=1 στην ίδια την εγγραφή. Το προϊόν μένει στη βάση αλλά δεν
πουλιέται. Πλήρης διαγραφή μόνο από το μενού του ζυγού.

Η εγγραφή στέλνεται ΟΠΩΣ ΤΗ ΔΙΑΒΑΣΑΜΕ, με αλλαγμένο μόνο το disabled — έτσι το
ελληνικό όνομα δεν ξαναγράφεται και δεν κινδυνεύει να χαλάσει.
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import autohost as A                                           # noqa: E402


def post(ip, rows, timeout=120):
    body = json.dumps(rows, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    req = urllib.request.Request(
        "http://%s:%d/products" % (ip, A.SCALE_PORT), data=body, method="POST",
        headers={"Content-Type": "application/json",
                 "User-Agent": "RestSharp 102.7.0.0",
                 "Accept": "application/json",
                 "Accept-Encoding": "gzip, deflate"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return True, "HTTP %d" % resp.status
    except urllib.error.HTTPError as exc:
        return False, "HTTP %d %s" % (exc.code, exc.reason)
    except Exception as exc:
        return False, str(exc)


def main():
    args = [a for a in sys.argv[1:]]
    if not args:
        print(__doc__)
        return 2
    ip = args.pop(0)
    kai_onoma = "--kai-onoma" in args
    anairesi = "--anairesi" in args
    mono_lista = "--lista" in args
    kodikoi = [a.lstrip("0") or "0" for a in args if not a.startswith("--")]

    print("Ανάγνωση βάσης από %s …" % ip)
    yparxonta = A.fetch_scale_products(ip)
    energa = [k for k, v in yparxonta.items() if str(v.get("disabled")) != "1"]
    print("   %d προϊόντα συνολικά, %d ενεργά\n" % (len(yparxonta), len(energa)))

    # Backup ΠΑΝΤΑ, πριν από οποιαδήποτε αλλαγή.
    bak = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "backup_zygou_%s_%s.json" % (ip.replace(".", "_"),
                                                    time.strftime("%Y%m%d_%H%M%S")))
    with open(bak, "w", encoding="utf-8") as fh:
        json.dump(list(yparxonta.values()), fh, ensure_ascii=False, indent=1)
    print("Backup: %s\n" % bak)

    if mono_lista:
        print("%-10s %-34s %-8s %s" % ("ΚΩΔΙΚΟΣ", "ΟΝΟΜΑ", "ΤΙΜΗ", "ΚΑΤΑΣΤΑΣΗ"))
        for k in sorted(yparxonta, key=lambda x: int(x) if x.isdigit() else 0):
            v = yparxonta[k]
            print("%-10s %-34s %-8s %s"
                  % (k, (v.get("product_name") or "")[:34], v.get("original_price"),
                     "ΑΝΕΝΕΡΓΟ" if str(v.get("disabled")) == "1" else "ενεργό"))
        return 0

    if not kodikoi:
        print("Δώσε κωδικούς προϊόντων, ή --lista για να δεις τι υπάρχει.")
        return 2

    rows, agnosta = [], []
    for k in kodikoi:
        palia = yparxonta.get(k)
        if palia is None:
            agnosta.append(k)
            continue
        row = dict(palia)                     # ΟΠΩΣ το διαβάσαμε
        row["disabled"] = "0" if anairesi else "1"
        if kai_onoma and not anairesi:
            row["product_name"] = ""
            row["product_abbr"] = ""
            row["original_price"] = "0"
        rows.append(row)

    if agnosta:
        print("Δεν βρέθηκαν στον ζυγό (αγνοούνται): %s" % ", ".join(agnosta))
    if not rows:
        return 1

    energeia = "ΕΠΑΝΕΝΕΡΓΟΠΟΙΗΣΗ" if anairesi else "ΑΠΕΝΕΡΓΟΠΟΙΗΣΗ"
    print("\n%s %d προϊόντων:" % (energeia, len(rows)))
    for r in rows:
        print("   %-8s %s" % (r["product_number"], (r.get("product_name") or "(κενό)")[:40]))

    apantisi = input("\nΝα σταλεί; (ναι/οχι): ").strip().lower()
    if apantisi not in ("ναι", "nai", "ν", "y", "yes"):
        print("Ακυρώθηκε — δεν στάλθηκε τίποτα.")
        return 0

    time.sleep(A.RATE_LIMIT_WAIT)             # ο ζυγός απαντά 429 σε γρήγορα αιτήματα
    ok, msg = post(ip, rows)
    print("%s — %s" % ("ΕΠΙΤΥΧΙΑ" if ok else "ΑΠΟΤΥΧΙΑ", msg))
    if not ok:
        print("Η βάση δεν άλλαξε. Επαναφορά από: %s" % bak)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
