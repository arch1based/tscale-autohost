# -*- coding: utf-8 -*-
"""Γενική γέφυρα: μπαίνει ανάμεσα σε πρόγραμμα ζυγού και αληθινό ζυγό.

Ό,τι κάνει η gefyra_ishida.py, αλλά για οποιαδήποτε μάρκα και για πολλές θύρες
ταυτόχρονα — χρήσιμο όταν δεν ξέρουμε ακόμα ποια θύρα κάνει τι.

Ο ζυγός ενημερώνεται κανονικά· εμείς βλέπουμε κάθε byte και προς τις δύο
κατευθύνσεις, ωμό.

    python3 gefyra.py 10.130.20.86 5001 5002 5100

Στο πρόγραμμα του ζυγού βάζεις για IP **αυτό το μηχάνημα**.
Βγάζει: katagrafi_gefyras.txt (αναγνώσιμο) και oma/<θύρα>/<αρ>-<κατεύθυνση>.bin
"""

import datetime
import io
import os
import socket
import sys
import threading

OUT = "katagrafi_gefyras.txt"
RAW_DIR = "oma"
_lock = threading.Lock()
_syn = [0]


def log(text):
    with _lock:
        print(text)
        with io.open(OUT, "a", encoding="utf-8") as fh:
            fh.write(text + "\n")


def hexdump(raw, limit=1024):
    lines = []
    for off in range(0, min(len(raw), limit), 16):
        chunk = raw[off:off + 16]
        hexa = " ".join("%02x" % b for b in bytearray(chunk))
        text = "".join(chr(b) if 32 <= b < 127 else "." for b in bytearray(chunk))
        lines.append("    %08x  %-47s  %s" % (off, hexa, text))
    if len(raw) > limit:
        lines.append("    ... (+%d bytes· όλα στο .bin)" % (len(raw) - limit))
    return "\n".join(lines)


def save(port, syn, katefthynsi, raw):
    fakelos = os.path.join(RAW_DIR, str(port))
    if not os.path.isdir(fakelos):
        os.makedirs(fakelos)
    path = os.path.join(fakelos, "%03d-%s.bin" % (syn, katefthynsi))
    with open(path, "ab") as fh:
        fh.write(raw)
    return path


def antigrafi(apo, pros, port, syn, katefthynsi, alli_akri):
    synolo = 0
    try:
        while True:
            raw = apo.recv(65536)
            if not raw:
                break
            pros.sendall(raw)
            synolo += len(raw)
            save(port, syn, katefthynsi, raw)
            log("\n[%s] θύρα %d · σύνδεση %d · %d bytes" % (katefthynsi, port, syn, len(raw)))
            log(hexdump(raw))
            for enc in ("cp1253", "latin-1"):
                try:
                    keimeno = raw.decode(enc)
                    ektyposimo = sum(1 for c in keimeno if c.isprintable() or c in "\r\n\t")
                    if ektyposimo > len(keimeno) * 0.7:
                        log("    ως %s: %r" % (enc, keimeno[:300]))
                    break
                except UnicodeDecodeError:
                    continue
    except Exception as exc:
        log("[%s] θύρα %d διακοπή: %s" % (katefthynsi, port, exc))
    finally:
        log("[%s] θύρα %d · σύνολο %d bytes" % (katefthynsi, port, synolo))
        for s in (apo, pros, alli_akri):
            try:
                s.close()
            except Exception:
                pass


def cheiristis(client, addr, zygos_ip, port):
    with _lock:
        _syn[0] += 1
        syn = _syn[0]
    log("\n" + "=" * 78)
    log("ΣΥΝΔΕΣΗ %d  θύρα %d  από %s:%s  ->  %s:%d   %s"
        % (syn, port, addr[0], addr[1], zygos_ip, port,
           datetime.datetime.now().strftime("%H:%M:%S")))
    log("=" * 78)
    try:
        zygos = socket.create_connection((zygos_ip, port), timeout=15)
    except Exception as exc:
        log("ΔΕΝ ΣΥΝΔΕΘΗΚΑ ΣΤΟΝ ΖΥΓΟ: %s" % exc)
        client.close()
        return
    threading.Thread(target=antigrafi,
                     args=(client, zygos, port, syn, "ΠΡΟΓΡΑΜΜΑ->ΖΥΓΟΣ", zygos),
                     daemon=True).start()
    antigrafi(zygos, client, port, syn, "ΖΥΓΟΣ->ΠΡΟΓΡΑΜΜΑ", client)


def akou(port, zygos_ip):
    srv = socket.socket()
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        srv.bind(("0.0.0.0", port))
    except Exception as exc:
        log("(η θύρα %d δεν άνοιξε: %s)" % (port, exc))
        return
    srv.listen(5)
    while True:
        client, addr = srv.accept()
        threading.Thread(target=cheiristis, args=(client, addr, zygos_ip, port),
                         daemon=True).start()


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        return
    zygos_ip = sys.argv[1]
    portes = [int(p) for p in sys.argv[2:]]
    log("\n########## ΓΕΦΥΡΑ  %s ##########"
        % datetime.datetime.now().strftime("%d/%m/%Y %H:%M:%S"))
    log("Ζυγός: %s · θύρες: %s" % (zygos_ip, ", ".join(str(p) for p in portes)))
    log("Στο πρόγραμμα του ζυγού βάλε για IP αυτό το μηχάνημα. Σταμάτημα: Ctrl+C\n")
    for p in portes:
        threading.Thread(target=akou, args=(p, zygos_ip), daemon=True).start()
    try:
        while True:
            threading.Event().wait(1)
    except KeyboardInterrupt:
        log("\nΤέλος. Δες το %s και τον φάκελο %s/." % (OUT, RAW_DIR))


if __name__ == "__main__":
    main()
