# -*- coding: utf-8 -*-
"""Γέφυρα ανάμεσα στο ScaleLink Pro 5 και σε αληθινό ζυγό Ishida UNI-3.

Το SLP-5 νομίζει ότι μιλάει στον ζυγό, ο ζυγός ότι μιλάει στο SLP-5, κι εμείς
βλέπουμε κάθε byte και προς τις δύο κατευθύνσεις. Η ενημέρωση γίνεται κανονικά
— δεν χάνεται τίποτα, ο ζυγός παίρνει ό,τι θα έπαιρνε έτσι κι αλλιώς.

Πλεονέκτημα σε σχέση με τον ψεύτικο ζυγό: βλέπουμε τις **αληθινές απαντήσεις**
του ζυγού, μαζί με τους κωδικούς σφάλματος όταν κάτι δεν του αρέσει.

Χρήση:
    python3 gefyra_ishida.py 10.130.20.89              (θύρα 8071 και στα δύο)
    python3 gefyra_ishida.py 10.130.20.89 8071 8071

Στο SLP-5 βάζεις για IP του ζυγού **αυτό το μηχάνημα** αντί για τον ζυγό.

Δομή (από τον κώδικα του SLP-5, κλάση Slp4000Scale):
  Κεφαλίδα 8 bytes: [0:2] μήνυμα BCD · [2] συσκευή · [3] αποτέλεσμα · [4:8] μέγεθος+8
  Υπο-κεφαλίδα 10 bytes (UNI-7/UNI-3): [0:2] μήνυμα · [2] συνέχεια · [6:10] μέγεθος
  Απάντηση 12 bytes: [0] κατάσταση · [4:6] ελήφθησαν · [6:8] ενημερώθηκαν
                     · [8:10] με σφάλμα · [10:12] κωδικός σφάλματος
"""

import io
import os
import socket
import sys
import threading
import datetime

SUBHEADER = 10
OUT = "katagrafi_gefyras.txt"
RAW_DIR = "oma_gefyra"
_lock = threading.Lock()
_syn = [0]


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
        lines.append("    %08x  %-47s  %s" % (off, hexa, text))
    if len(raw) > limit:
        lines.append("    ... (+%d bytes· όλα στο .bin)" % (len(raw) - limit))
    return "\n".join(lines)


def bcd2num(raw, offset, psifia):
    num = 0
    for b in bytearray(raw[offset:offset + (psifia + 1) // 2]):
        num = num * 100 + (b >> 4) * 10 + (b & 0x0F)
    return num


def apothikefsi(syn, onoma, raw):
    fakelos = os.path.join(RAW_DIR, "syndesi%03d" % syn)
    if not os.path.isdir(fakelos):
        os.makedirs(fakelos)
    path = os.path.join(fakelos, onoma)
    with open(path, "ab") as fh:
        fh.write(raw)
    return path


class Katagrafeas(object):
    """Μαζεύει τη ροή μιας κατεύθυνσης και τη σπάει σε μηνύματα."""

    def __init__(self, syn, katefthynsi):
        self.syn = syn
        self.k = katefthynsi              # "SLP->ΖΥΓΟΣ" ή "ΖΥΓΟΣ->SLP"
        self.buf = b""
        self.perimeno = 0                 # bytes σώματος που λείπουν
        self.trexon_msg = None
        self.arithmos = 0

    def prosthese(self, raw):
        self.buf += raw
        while True:
            if self.perimeno > 0:
                if len(self.buf) < self.perimeno:
                    return
                soma = self.buf[:self.perimeno]
                self.buf = self.buf[self.perimeno:]
                self.perimeno = 0
                self._soma(soma)
                continue
            if len(self.buf) < 8:
                return
            head = self.buf[:8]
            self.buf = self.buf[8:]
            self._kefalida(head)

    def _kefalida(self, head):
        self.arithmos += 1
        msg = bcd2num(head, 0, 4)
        syskevi = bcd2num(head, 2, 2)
        apotelesma = bytearray(head)[3]
        megethos = int.from_bytes(head[4:8], "big")
        self.trexon_msg = msg
        self.perimeno = max(megethos - 8, 0)
        log("\n[%s] #%d  ΜΗΝΥΜΑ %d  συσκευή %d  αποτέλεσμα %d  σώμα %d bytes"
            % (self.k, self.arithmos, msg, syskevi, apotelesma, self.perimeno))
        log(hexdump(head))

    def _soma(self, soma):
        apothikefsi(self.syn, "%s-msg%d.bin" % (self.k.replace("->", "_"),
                                                self.trexon_msg or 0), soma)
        if self.k.startswith("ΖΥΓΟΣ") and len(soma) == 12:
            self._apantisi(soma)
            return
        off = 0
        eggrafes = 0
        while off + SUBHEADER <= len(soma):
            sub = soma[off:off + SUBHEADER]
            sub_msg = bcd2num(sub, 0, 4)
            synecheia = bytearray(sub)[2]
            sub_len = int.from_bytes(sub[6:10], "big")
            if sub_msg != self.trexon_msg or sub_len <= 0 \
                    or off + SUBHEADER + sub_len > len(soma):
                break
            eggrafi = soma[off + SUBHEADER:off + SUBHEADER + sub_len]
            eggrafes += 1
            log("  ΕΓΓΡΑΦΗ %d — %d bytes%s"
                % (eggrafes, sub_len, "  (ακολουθεί κι άλλο)" if synecheia else ""))
            log(hexdump(eggrafi))
            try:
                log("    ως cp1253: %s" % eggrafi.decode("cp1253").replace("\x00", "·"))
            except UnicodeDecodeError:
                pass
            off += SUBHEADER + sub_len
        if eggrafes == 0:
            log("  (σώμα χωρίς υπο-κεφαλίδες)")
            log(hexdump(soma))
        else:
            log("  ΣΥΝΟΛΟ: %d εγγραφές" % eggrafes)

    def _apantisi(self, soma):
        log("  ΑΠΑΝΤΗΣΗ: κατάσταση %d · ελήφθησαν %d · ενημερώθηκαν %d · "
            "με σφάλμα %d · κωδικός σφάλματος %d"
            % (bcd2num(soma, 0, 2), bcd2num(soma, 4, 4), bcd2num(soma, 6, 4),
               bcd2num(soma, 8, 4), int.from_bytes(soma[10:12], "big")))
        log(hexdump(soma))


def antigrafi(apo, pros, katagrafeas, alli_akri):
    try:
        while True:
            raw = apo.recv(65536)
            if not raw:
                break
            pros.sendall(raw)
            katagrafeas.prosthese(raw)
    except Exception as exc:
        log("[%s] διακοπή: %s" % (katagrafeas.k, exc))
    finally:
        for s in (apo, pros, alli_akri):
            try:
                s.close()
            except Exception:
                pass


def cheiristis(client, addr, zygos_ip, zygos_port):
    _syn[0] += 1
    syn = _syn[0]
    ora = datetime.datetime.now().strftime("%H:%M:%S")
    log("\n" + "=" * 78)
    log("ΣΥΝΔΕΣΗ %d  από %s:%s  ->  ζυγός %s:%d   %s"
        % (syn, addr[0], addr[1], zygos_ip, zygos_port, ora))
    log("=" * 78)
    try:
        zygos = socket.create_connection((zygos_ip, zygos_port), timeout=15)
    except Exception as exc:
        log("ΔΕΝ ΣΥΝΔΕΘΗΚΑ ΣΤΟΝ ΖΥΓΟ: %s" % exc)
        client.close()
        return
    pros_zygo = Katagrafeas(syn, "SLP->ΖΥΓΟΣ")
    pros_slp = Katagrafeas(syn, "ΖΥΓΟΣ->SLP")
    threading.Thread(target=antigrafi, args=(client, zygos, pros_zygo, zygos),
                     daemon=True).start()
    antigrafi(zygos, client, pros_slp, client)
    log("\n[σύνδεση %d έκλεισε]" % syn)


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return
    zygos_ip = sys.argv[1]
    akou_port = int(sys.argv[2]) if len(sys.argv) > 2 else 8071
    zygos_port = int(sys.argv[3]) if len(sys.argv) > 3 else akou_port
    srv = socket.socket()
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("0.0.0.0", akou_port))
    srv.listen(5)
    log("\n########## ΓΕΦΥΡΑ  %s ##########"
        % datetime.datetime.now().strftime("%d/%m/%Y %H:%M:%S"))
    log("Ακούω στη θύρα %d και προωθώ στον ζυγό %s:%d."
        % (akou_port, zygos_ip, zygos_port))
    log("Στο SLP-5 βάλε για IP ζυγού αυτό το μηχάνημα. Σταμάτημα: Ctrl+C\n")
    try:
        while True:
            client, addr = srv.accept()
            threading.Thread(target=cheiristis,
                             args=(client, addr, zygos_ip, zygos_port),
                             daemon=True).start()
    except KeyboardInterrupt:
        log("\nΤέλος. Δες το %s και τον φάκελο %s/." % (OUT, RAW_DIR))


if __name__ == "__main__":
    main()
