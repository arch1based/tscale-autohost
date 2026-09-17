# -*- coding: utf-8 -*-
"""Ψεύτικος ζυγός Ishida UNI-3 (πρωτόκολλο UNI-7), θύρα 8071.

Παριστάνει τον ζυγό απέναντι στο ScaleLink Pro 5 και κρατά ΑΥΤΟΥΣΙΑ κάθε
byte που του στέλνει — για να μάθουμε τη μορφή των εγγραφών PLU και να τη
στέλνουμε μόνοι μας, χωρίς να ανοίγει το πρόγραμμα της Ishida.

Η δομή βγήκε από τον κώδικα του ίδιου του SLP-5 (Slp4000Scale):

  Κεφαλίδα, 8 bytes
    [0:2]  αριθμός μηνύματος, BCD 4 ψηφίων
    [2]    τύπος συσκευής, BCD
    [3]    αποτέλεσμα (0 = εντάξει)
    [4:8]  μέγεθος, big-endian 4 bytes — δεδομένα ΣΥΝ 8

  Υπο-κεφαλίδα, 10 bytes (μόνο τα UNI-7/UNI-3· τα άλλα μοντέλα 8)
    [0:2]  αριθμός μηνύματος, BCD
    [2]    1 όταν ακολουθεί κι άλλο κομμάτι
    [6:10] μέγεθος εγγραφής, big-endian 4 bytes

  Απάντηση, 12 bytes (τη στέλνουμε εμείς μαζί με μια κεφαλίδα)
    [0]     κατάσταση    [4:6]  εγγραφές που ελήφθησαν
    [6:8]   ενημερώθηκαν [8:10] με σφάλμα      [10:12] κωδικός σφάλματος

Χρήση:
    python3 psefti_ishida_uni3.py           (θύρα 8071)
    python3 psefti_ishida_uni3.py 9071      (άλλη θύρα)

Στο SLP-5 βάζεις τον ζυγό με IP 127.0.0.1 και πατάς αποστολή.
"""

import io
import os
import socket
import sys
import threading
import datetime

PORT = 8071
SUBHEADER = 10          # UNI-7 / UNI-3
OUT = "katagrafi_uni3.txt"
RAW_DIR = "oma_uni3"
_lock = threading.Lock()
_n = [0]


def log(text):
    with _lock:
        print(text)
        with io.open(OUT, "a", encoding="utf-8") as fh:
            fh.write(text + "\n")


def hexdump(raw, limit=2048):
    lines = []
    for off in range(0, min(len(raw), limit), 16):
        chunk = raw[off:off + 16]
        hexa = " ".join("%02x" % b for b in bytearray(chunk))
        text = "".join(chr(b) if 32 <= b < 127 else "." for b in bytearray(chunk))
        lines.append("%08x  %-47s  %s" % (off, hexa, text))
    if len(raw) > limit:
        lines.append("... (+%d bytes ακόμα· όλα στο αρχείο .bin)" % (len(raw) - limit))
    return "\n".join(lines)


def bcd2num(raw, offset, psifia):
    """Διαβάζει BCD, όπως η Bcd2Num του SLP-5: 4 ψηφία = 2 bytes."""
    plithos = (psifia + 1) // 2
    num = 0
    for b in bytearray(raw[offset:offset + plithos]):
        num = num * 100 + (b >> 4) * 10 + (b & 0x0F)
    return num


def num2bcd(value, plithos_bytes):
    out = bytearray(plithos_bytes)
    for i in range(plithos_bytes - 1, -1, -1):
        out[i] = (value % 10) | ((value // 10 % 10) << 4)
        value //= 100
    return bytes(out)


def recv_exact(sock, n):
    raw = b""
    while len(raw) < n:
        part = sock.recv(n - len(raw))
        if not part:
            break
        raw += part
    return raw


def apothikefsi(onoma, raw):
    if not os.path.isdir(RAW_DIR):
        os.makedirs(RAW_DIR)
    _n[0] += 1
    path = os.path.join(RAW_DIR, "%03d-%s.bin" % (_n[0], onoma))
    with open(path, "wb") as fh:
        fh.write(raw)
    return path


def apantisi(sock, msg_no, eggrafes):
    """Κεφαλίδα + απάντηση 12 bytes: όλα καλά, καμία εγγραφή με σφάλμα."""
    soma = bytearray(12)
    soma[0] = 0                                  # κατάσταση: εντάξει
    soma[4:6] = num2bcd(eggrafes, 2)             # ελήφθησαν
    soma[6:8] = num2bcd(eggrafes, 2)             # ενημερώθηκαν
    soma[8:10] = num2bcd(0, 2)                   # με σφάλμα
    soma[10:12] = b"\x00\x00"                    # κωδικός σφάλματος
    head = bytearray(8)
    head[0:2] = num2bcd(msg_no, 2)
    head[3] = 0                                  # αποτέλεσμα: εντάξει
    total = len(soma) + 8
    head[4:8] = bytes([(total >> 24) & 255, (total >> 16) & 255,
                       (total >> 8) & 255, total & 255])
    sock.sendall(bytes(head) + bytes(soma))
    log("  <- απάντησα: εντάξει, %d εγγραφές" % eggrafes)


def cheiristis(sock, addr):
    ora = datetime.datetime.now().strftime("%H:%M:%S")
    log("\n" + "=" * 78)
    log("ΣΥΝΔΕΣΗ από %s:%s   %s" % (addr[0], addr[1], ora))
    log("=" * 78)
    sock.settimeout(60.0)
    try:
        while True:
            head = recv_exact(sock, 8)
            if len(head) < 8:
                log("(η σύνδεση έκλεισε)")
                return
            msg_no = bcd2num(head, 0, 4)
            syskevi = bcd2num(head, 2, 2)
            apotelesma = bytearray(head)[3]
            megethos = int.from_bytes(head[4:8], "big")
            soma_len = max(megethos - 8, 0)
            log("\n--- ΜΗΝΥΜΑ %d   συσκευή %d   αποτέλεσμα %d   δεδομένα %d bytes"
                % (msg_no, syskevi, apotelesma, soma_len))
            log(hexdump(head))

            if soma_len == 0:                     # σκέτη εντολή
                apantisi(sock, msg_no, 0)
                continue

            soma = recv_exact(sock, soma_len)
            path = apothikefsi("msg%d" % msg_no, head + soma)
            log("ΩΜΑ: %s" % path)

            # Χωρίζουμε σε εγγραφές με βάση τις υπο-κεφαλίδες.
            off = 0
            eggrafes = 0
            while off + SUBHEADER <= len(soma):
                sub = soma[off:off + SUBHEADER]
                sub_msg = bcd2num(sub, 0, 4)
                synecheia = bytearray(sub)[2]
                sub_len = int.from_bytes(sub[6:10], "big")
                if sub_msg != msg_no or sub_len <= 0 or off + SUBHEADER + sub_len > len(soma):
                    break                          # δεν έχει υπο-κεφαλίδες
                eggrafi = soma[off + SUBHEADER:off + SUBHEADER + sub_len]
                eggrafes += 1
                log("\n  ΕΓΓΡΑΦΗ %d — %d bytes%s"
                    % (eggrafes, sub_len, "  (ακολουθεί κι άλλο)" if synecheia else ""))
                log(hexdump(eggrafi))
                for enc in ("cp1253", "latin-1"):
                    try:
                        log("  ως %s: %s" % (enc, eggrafi.decode(enc).replace("\x00", "·")))
                        break
                    except UnicodeDecodeError:
                        continue
                off += SUBHEADER + sub_len

            if eggrafes == 0:
                log("(χωρίς υπο-κεφαλίδες — όλο το σώμα μαζί)")
                log(hexdump(soma))
                eggrafes = 1
            apantisi(sock, msg_no, eggrafes)
    except socket.timeout:
        log("(τέλος χρόνου αναμονής)")
    except Exception as exc:
        log("(σφάλμα: %s)" % exc)
    finally:
        try:
            sock.close()
        except Exception:
            pass


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else PORT
    srv = socket.socket()
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("0.0.0.0", port))
    srv.listen(5)
    log("\n########## ΨΕΥΤΙΚΟΣ UNI-3 στη θύρα %d  %s ##########"
        % (port, datetime.datetime.now().strftime("%d/%m/%Y %H:%M:%S")))
    log("Βάλε στο SLP-5 ζυγό UNI-3 με IP 127.0.0.1 και στείλε. Σταμάτημα: Ctrl+C")
    try:
        while True:
            sock, addr = srv.accept()
            threading.Thread(target=cheiristis, args=(sock, addr), daemon=True).start()
    except KeyboardInterrupt:
        log("\nΤέλος. Δες το %s και τον φάκελο %s/." % (OUT, RAW_DIR))


if __name__ == "__main__":
    main()
