# -*- coding: utf-8 -*-
"""Δοκιμή της αποστολής σε Ishida, χωρίς να χρειάζεται αληθινός ζυγός.

Σηκώνει έναν ψεύτικο UNI-3 που απαντά όπως ο αληθινός και ελέγχει ολόκληρη τη
ροή: χειραψία, ανάγνωση με σελιδοποίηση, αλλαγή μόνο των τιμών, αποστολή.

Το πιο σημαντικό που ελέγχει: ότι μετά την αποστολή **μόνο η τιμή** έχει
αλλάξει σε κάθε εγγραφή. Αν κάποτε πειράξουμε κατά λάθος όνομα ή ετικέτα,
εδώ θα φανεί.

Αν υπάρχει καταγραφή από αληθινό ζυγό (φάκελος oma_gefyra της γέφυρας),
τη δίνεις ως πρώτο όρισμα και δοκιμάζει με τα αληθινά δεδομένα του πελάτη:

    python3 dokimi_ishida.py /δρόμος/προς/oma_gefyra
    python3 dokimi_ishida.py            (με λίγες πλαστές εγγραφές)
"""

import glob
import os
import socket
import sys
import threading

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import autohost as A                                           # noqa: E402

PORT = 18071
SUB = 10


def bcd(value, nbytes):
    out = bytearray(nbytes)
    for i in range(nbytes - 1, -1, -1):
        out[i] = (value % 10) | ((value // 10 % 10) << 4)
        value //= 100
    return bytes(out)


def header(msg, data, result=0):
    h = bytearray(8)
    h[0:2] = bcd(msg, 2)
    h[3] = result
    h[4:8] = (data + 8).to_bytes(4, "big")
    return bytes(h)


def recvall(sock, n):
    raw = b""
    while len(raw) < n:
        part = sock.recv(n - len(raw))
        if not part:
            break
        raw += part
    return raw


def plastes_eggrafes():
    """Λίγες εγγραφές 118 πεδίων, με όνομα και τιμή στις σωστές θέσεις."""
    out = []
    for kodikos, onoma, timi in (("50", "ΕΛ ΚΟΝΤΡΑ Μ/Ο", "790"),
                                 ("51", "ΕΛ ΜΠΡΙΖΟΛΕΣ Μ/Ο", "790"),
                                 ("52", "ΕΛ ΠΑΝΣΕΤΑ Μ/Ο", "680")):
        p = ["0"] * A.ISHIDA_FIELDS
        p[A.ISHIDA_CODE_FIELD] = kodikos
        p[68] = '"\\x0d\\x08\\x02%s\\x02"' % onoma
        p[A.ISHIDA_PRICE_FIELD] = timi
        p[86] = "16"
        p[89] = kodikos
        out.append(",".join(p).encode("cp1253"))
    return out


def fortose_katagrafi(fakelos):
    arxeia = glob.glob(os.path.join(fakelos, "*", "*msg2001.bin"))
    arxeia = [f for f in arxeia if not os.path.basename(f).startswith("SLP")]
    if not arxeia:
        return None
    raw = open(arxeia[0], "rb").read()
    out, off = [], 0
    while off + SUB <= len(raw):
        n = int.from_bytes(raw[off + 6:off + SUB], "big")
        if n <= 0 or off + SUB + n > len(raw):
            break
        out.append(raw[off + SUB:off + SUB + n])
        off += SUB + n
    return out


class PsefticosZygos(object):
    """Απαντά όπως ο αληθινός: χειραψία, σελιδοποίηση, επιβεβαίωση."""

    def __init__(self, eggrafes, ana_selida=213, arnisi=False):
        self.eggrafes = eggrafes
        self.ana_selida = ana_selida
        self.arnisi = arnisi           # για να δοκιμάσουμε και την άρνηση
        self.pire = []
        self.xeirapsies = 0
        self.srv = socket.socket()
        self.srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.srv.bind(("127.0.0.1", PORT))
        self.srv.listen(5)
        threading.Thread(target=self._loop, daemon=True).start()

    def _loop(self):
        while True:
            try:
                sock, _ = self.srv.accept()
            except OSError:
                return
            threading.Thread(target=self._syndesi, args=(sock,), daemon=True).start()

    def _syndesi(self, sock):
        try:
            while True:
                head = recvall(sock, 8)
                if len(head) < 8:
                    return
                msg = int(head[0:2].hex())
                size = int.from_bytes(head[4:8], "big") - 8
                soma = recvall(sock, size) if size > 0 else b""

                if msg == A.ISHIDA_MSG_STATUS:
                    self.xeirapsies += 1
                    sock.sendall(header(msg, 12) + bytes(12))
                elif msg == A.ISHIDA_MSG_READ:
                    if self.arnisi:
                        sock.sendall(header(msg, 0, result=3))
                        continue
                    apo = int(soma[SUB:].decode("cp1253").rstrip(",") or 0)
                    epil = [e for e in self.eggrafes
                            if int(e.split(b",")[0]) > apo][:self.ana_selida]
                    if not epil:
                        sock.sendall(header(msg, 0, result=1))
                        continue
                    body = b""
                    for e in epil:
                        sh = bytearray(SUB)
                        sh[0:2] = bcd(msg, 2)
                        sh[6:10] = len(e).to_bytes(4, "big")
                        body += bytes(sh) + e
                    sock.sendall(header(msg, len(body)) + body)
                elif msg == A.ISHIDA_MSG_SEND:
                    off, n = 0, 0
                    while off + SUB <= len(soma):
                        ln = int.from_bytes(soma[off + 6:off + SUB], "big")
                        if ln <= 0 or off + SUB + ln > len(soma):
                            break
                        self.pire.append(soma[off + SUB:off + SUB + ln].decode("cp1253"))
                        off += SUB + ln
                        n += 1
                    r = bytearray(12)
                    r[4:6] = bcd(n, 2)
                    r[6:8] = bcd(n, 2)
                    sock.sendall(header(msg, 12) + bytes(r))
                else:
                    sock.sendall(header(msg, 12) + bytes(12))
        except Exception:
            pass
        finally:
            sock.close()


def sygkrisi_me_katagrafi(fakelos):
    """Συγκρίνει ό,τι στέλνουμε με ό,τι έστελνε το ScaleLink Pro 5, byte προς byte.

    Δεν αρκεί να «δουλεύει»: πρέπει ο ζυγός να βλέπει ακριβώς ό,τι συνήθιζε.
    Μια σημαία που λείπει από την υπο-κεφαλίδα τον κάνει να απαντήσει ότι δεν
    έχει προϊόντα — χωρίς κανένα σφάλμα πουθενά.
    """
    arxeia = glob.glob(os.path.join(fakelos, "*", "SLP_*msg2001.bin"))
    if not arxeia:
        return []
    raw = open(arxeia[0], "rb").read()
    lathi, off = [], 0
    while off + SUB <= len(raw):
        n = int.from_bytes(raw[off + 6:off + SUB], "big")
        if n <= 0 or off + SUB + n > len(raw):
            break
        slp = raw[off:off + SUB + n]
        aitima = raw[off + SUB:off + SUB + n]
        diko_mas = A._ishida_subheader(A.ISHIDA_MSG_READ, n, zitao_ki_alla=True) + aitima
        simadi = "✓" if slp == diko_mas else "✗ ΔΙΑΦΕΡΕΙ"
        print("   %-8s %s" % (repr(aitima.decode("cp1253")), simadi))
        if slp != diko_mas:
            lathi.append("το αίτημα %r δεν είναι ίδιο με του SLP-5"
                         % aitima.decode("cp1253"))
        off += SUB + n
    return lathi


def main():
    A.ISHIDA_PORT = PORT
    fakelos = sys.argv[1] if len(sys.argv) > 1 else None
    eggrafes = fortose_katagrafi(fakelos) if fakelos else None
    if eggrafes:
        print("δεδομένα: %d αληθινές εγγραφές από %s\n" % (len(eggrafes), fakelos))
    else:
        eggrafes = plastes_eggrafes()
        print("δεδομένα: %d πλαστές εγγραφές\n" % len(eggrafes))

    zygos = PsefticosZygos(eggrafes)
    log = lambda m: print("   " + m)
    lathi = []

    if fakelos:
        print("0) ΤΑ ΑΙΤΗΜΑΤΑ ΜΑΣ, ΔΙΠΛΑ ΣΕ ΑΥΤΑ ΤΟΥ SCALELINK PRO 5")
        lathi += sygkrisi_me_katagrafi(fakelos)
        print()

    print("1) ΑΝΑΓΝΩΣΗ")
    yparxonta = A.ishida_fetch_plus("127.0.0.1", log=log)
    print("   -> %d προϊόντα, %d χειραψίες" % (len(yparxonta), zygos.xeirapsies))
    if len(yparxonta) != len(eggrafes):
        lathi.append("χάθηκαν εγγραφές στην ανάγνωση")
    if zygos.xeirapsies < 1:
        lathi.append("δεν έγινε η χειραψία 3013")

    print("\n2) ΑΛΛΑΓΗ ΤΙΜΩΝ")
    kodikoi = sorted(yparxonta, key=lambda k: int(k))[:3]
    items = [{"product_number": k, "original_price": str(int(
        A.ishida_split_fields(yparxonta[k])[A.ISHIDA_PRICE_FIELD] or 0) + 60)}
        for k in kodikoi]
    items.append({"product_number": "999999", "original_price": "500"})   # άγνωστο
    pros = A.ishida_merge_prices(yparxonta, items, log)
    print("   -> %d προς αποστολή (περιμέναμε %d)" % (len(pros), len(kodikoi)))
    if len(pros) != len(kodikoi):
        lathi.append("λάθος πλήθος εγγραφών προς αποστολή")

    print("\n3) ΑΠΟΣΤΟΛΗ")
    ok, msg = A.ishida_send_plus("127.0.0.1", pros, log)
    print("   -> %s (%s)" % ("ΕΠΙΤΥΧΙΑ" if ok else "ΑΠΟΤΥΧΙΑ", msg))
    if not ok:
        lathi.append("η αποστολή απέτυχε")

    print("\n4) ΑΛΛΑΞΕ ΜΟΝΟ Η ΤΙΜΗ;")
    for grammi in zygos.pire:
        nea = A.ishida_split_fields(grammi)
        palia = A.ishida_split_fields(yparxonta[nea[0].lstrip("0") or "0"])
        diafores = [i for i in range(len(palia)) if palia[i] != nea[i]]
        print("   PLU %-7s άλλαξαν τα πεδία %s   (%s -> %s)"
              % (nea[0], diafores, palia[A.ISHIDA_PRICE_FIELD],
                 nea[A.ISHIDA_PRICE_FIELD]))
        if diafores != [A.ISHIDA_PRICE_FIELD]:
            lathi.append("PLU %s: άλλαξε και πεδίο εκτός της τιμής" % nea[0])
        if len(nea) != A.ISHIDA_FIELDS:
            lathi.append("PLU %s: λάθος πλήθος πεδίων" % nea[0])

    print("\n5) ΑΡΝΗΣΗ ΤΟΥ ΖΥΓΟΥ — πρέπει να το πει καθαρά")
    zygos.arnisi = True
    try:
        A.ishida_fetch_plus("127.0.0.1", log=lambda m: None)
        lathi.append("η άρνηση του ζυγού πέρασε σαν «δεν έχει προϊόντα»")
        print("   ✗ πέρασε σιωπηλά")
    except A.StepError as exc:
        print("   ✓ %s" % exc.message)

    print("\n5β) ΑΛΛΑΓΗ ΟΝΟΜΑΤΟΣ — να αλλάξει ΜΟΝΟ το όνομα, όχι τα υπόλοιπα")
    k = kodikoi[0]
    palia = A.ishida_split_fields(yparxonta[k])
    idia_timi = palia[A.ISHIDA_PRICE_FIELD]
    nea = A.ishida_merge_prices(
        yparxonta, [{"product_number": k, "original_price": idia_timi,
                     "product_name": "ΝΕΟ ΟΝΟΜΑ ΔΟΚΙΜΗΣ"}], lambda m: None, True)
    if len(nea) != 1:
        lathi.append("η αλλαγή ονόματος δεν έστειλε το προϊόν")
        print("   ✗ δεν στάλθηκε")
    else:
        np_ = A.ishida_split_fields(nea[0])
        diaf = [i for i in range(len(palia)) if palia[i] != np_[i]]
        print("   PLU %s: άλλαξαν τα πεδία %s -> %s" % (k, diaf, np_[68]))
        if diaf != [68]:
            lathi.append("η αλλαγή ονόματος πείραξε κι άλλα πεδία: %s" % diaf)
    idio = A.ishida_merge_prices(
        yparxonta, [{"product_number": k, "original_price": idia_timi,
                     "product_name": A.ishida_name_text(palia[68])}],
        lambda m: None, True)
    print("   με ίδιο όνομα και ίδια τιμή -> %d προς αποστολή (σωστό: 0)" % len(idio))
    if idio:
        lathi.append("στάλθηκε προϊόν χωρίς καμία αλλαγή")

    print("\n6) ΑΔΕΙΑ ΖΥΓΑΡΙΑ — πρέπει να γεμίσει, όχι να βγάλει σφάλμα")
    kena = A.ishida_merge_prices(
        {}, [{"product_number": "4242", "original_price": "1250",
              "product_name": "ΔΟΚΙΜΑΣΤΙΚΟ ΠΡΟΪΟΝ", "tax": "13"}],
        lambda m: None, True, dimiourgia=True)
    if not kena:
        lathi.append("σε άδειο ζυγό δεν φτιάχτηκε καμία εγγραφή")
        print("   ✗ δεν φτιάχτηκε τίποτα")
    else:
        pedia = A.ishida_split_fields(kena[0])
        print("   ✓ φτιάχτηκε εγγραφή %d πεδίων: κωδ=%s τιμή=%s ΦΠΑ=%s όνομα=%s"
              % (len(pedia), pedia[A.ISHIDA_CODE_FIELD],
                 pedia[A.ISHIDA_PRICE_FIELD], pedia[A.ISHIDA_TAX_FIELD], pedia[68]))
        if len(pedia) != A.ISHIDA_FIELDS:
            lathi.append("η νέα εγγραφή δεν έχει %d πεδία" % A.ISHIDA_FIELDS)
        if "" == pedia[A.ISHIDA_BCFORMAT_FIELD]:
            lathi.append("η νέα εγγραφή έχει κενή μορφή barcode")

    print("\n" + ("ΟΛΑ ΚΑΛΑ" if not lathi else "ΠΡΟΒΛΗΜΑΤΑ:\n  - " + "\n  - ".join(lathi)))
    return 1 if lathi else 0


if __name__ == "__main__":
    sys.exit(main())
