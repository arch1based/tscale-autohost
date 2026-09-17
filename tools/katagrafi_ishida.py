# -*- coding: utf-8 -*-
"""Καταγραφέας για ζυγούς Ishida: παριστάνει τον ζυγό και κρατά ΤΑ ΠΑΝΤΑ.

Ιδέα ίδια με το fake_scale.py, αλλά δεν ξέρουμε ακόμα ούτε θύρα ούτε
πρωτόκολλο. Γι' αυτό ανοίγουμε ΠΟΛΛΕΣ θύρες ταυτόχρονα (TCP + UDP) και
κρατάμε τα ωμά bytes όπως ήρθαν — χωρίς καμία ερμηνεία.

Χρήση (στο VM με το πρόγραμμα της Ishida, ή σε άλλο μηχάνημα του δικτύου):
    python katagrafi_ishida.py                 (οι συνηθισμένες θύρες)
    python katagrafi_ishida.py 21 5001 9100    (μόνο αυτές)

Μετά, στο πρόγραμμα της Ishida βάζεις για IP ζυγού αυτό το μηχάνημα
(127.0.0.1 αν τρέχει στο ίδιο) και πατάς αποστολή.

Βγάζει:
  katagrafi_ishida.txt   - αναγνώσιμο ημερολόγιο (hex + κείμενο)
  oma/<θύρα>-<αρ>.bin    - τα ωμά bytes κάθε σύνδεσης, ατόφια
"""

import io
import os
import socket
import sys
import threading
import datetime

# Θύρες που χρησιμοποιούν συνήθως ζυγοί/ετικετογράφοι. Ό,τι δεν ανοίξει,
# απλώς το προσπερνάμε (μπορεί να το κρατά κάτι άλλο ή να θέλει root).
TCP_PORTS = [21, 23, 80, 443, 502, 1235, 2000, 2001, 3000, 4000, 5000,
             5001, 5002, 6000, 8000, 8080, 8888, 9000, 9100, 9200, 10000]
UDP_PORTS = [161, 5000, 5001, 9000, 30718, 31000]

OUT = "katagrafi_ishida.txt"
RAW_DIR = "oma"
_lock = threading.Lock()
_n = [0]


def log(text):
    with _lock:
        print(text)
        with io.open(OUT, "a", encoding="utf-8") as fh:
            fh.write(text + "\n")


def ora():
    return datetime.datetime.now().strftime("%H:%M:%S")


def hexdump(raw, limit=4096):
    lines = []
    for off in range(0, min(len(raw), limit), 16):
        chunk = raw[off:off + 16]
        hexa = " ".join("%02x" % b for b in bytearray(chunk))
        text = "".join(chr(b) if 32 <= b < 127 else "." for b in bytearray(chunk))
        lines.append("%08x  %-47s  %s" % (off, hexa, text))
    if len(raw) > limit:
        lines.append("... (+%d bytes ακόμα, όλα στο αρχείο .bin)" % (len(raw) - limit))
    return "\n".join(lines)


def apothikefsi(port, raw):
    if not os.path.isdir(RAW_DIR):
        os.makedirs(RAW_DIR)
    _n[0] += 1
    path = os.path.join(RAW_DIR, "%s-%03d.bin" % (port, _n[0]))
    with open(path, "wb") as fh:
        fh.write(raw)
    return path


def mantepse(raw):
    """Μια πρόχειρη εικασία για το τι πρωτόκολλο είναι."""
    head = raw[:16].upper()
    if head.startswith(b"POST") or head.startswith(b"GET") or head.startswith(b"PUT"):
        return "HTTP"
    if raw[:1] == b"{" or raw[:1] == b"[":
        return "JSON"
    if raw[:5] == b"<?xml":
        return "XML"
    if b"," in raw[:200] and b"\n" in raw[:400]:
        return "κείμενο με κόμματα (CSV)"
    return "δυαδικό / άγνωστο"


def apantisi_ftp(sock, raw, log_):
    """Πολύ απλός FTP ώστε το πρόγραμμα να φτάσει να στείλει το αρχείο."""
    # Μόνο ο έλεγχος· τα δεδομένα έρχονται σε άλλη σύνδεση (passive 2121).
    sock.sendall(b"220 ICS capture\r\n")
    data_sock = None
    while True:
        line = b""
        while not line.endswith(b"\n"):
            chunk = sock.recv(1)
            if not chunk:
                return
            line += chunk
        cmd = line.strip()
        log_("    FTP > %s" % cmd.decode("latin-1"))
        up = cmd.upper()
        if up.startswith(b"USER") or up.startswith(b"PASS"):
            sock.sendall(b"230 ok\r\n")
        elif up.startswith(b"TYPE") or up.startswith(b"CWD") or up.startswith(b"MODE"):
            sock.sendall(b"200 ok\r\n")
        elif up.startswith(b"PWD"):
            sock.sendall(b'257 "/"\r\n')
        elif up.startswith(b"PASV"):
            srv = socket.socket()
            srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            srv.bind(("0.0.0.0", 2121))
            srv.listen(1)
            sock.sendall(b"227 Entering Passive Mode (127,0,0,1,8,73)\r\n")
            data_sock = srv
        elif up.startswith(b"STOR") or up.startswith(b"APPE"):
            sock.sendall(b"150 ok\r\n")
            raw_all = b""
            if data_sock is not None:
                conn, _ = data_sock.accept()
                while True:
                    part = conn.recv(65536)
                    if not part:
                        break
                    raw_all += part
                conn.close()
            onoma = cmd.split(b" ", 1)[-1].decode("latin-1")
            path = apothikefsi("ftp", raw_all)
            log_("    FTP: αρχείο '%s' (%d bytes) -> %s" % (onoma, len(raw_all), path))
            log_(hexdump(raw_all))
            sock.sendall(b"226 ok\r\n")
        elif up.startswith(b"QUIT"):
            sock.sendall(b"221 bye\r\n")
            return
        else:
            sock.sendall(b"200 ok\r\n")


def cheiristis(sock, addr, port):
    sock.settimeout(8.0)
    log("\n" + "=" * 78)
    log("ΣΥΝΔΕΣΗ  θύρα %s  από %s:%s   %s" % (port, addr[0], addr[1], ora()))
    log("=" * 78)
    try:
        if port == 21:
            apantisi_ftp(sock, b"", log)
            return
        raw = b""
        while True:
            try:
                part = sock.recv(65536)
            except socket.timeout:
                break
            if not part:
                break
            raw += part
            # Αν είναι HTTP, απαντάμε ΟΚ ώστε να μη θεωρήσει αποτυχία.
            if raw[:4] in (b"POST", b"GET ", b"PUT ") and b"\r\n\r\n" in raw:
                length = 0
                for line in raw.split(b"\r\n"):
                    if line.lower().startswith(b"content-length:"):
                        length = int(line.split(b":")[1].strip())
                soma = raw.split(b"\r\n\r\n", 1)[1]
                if len(soma) >= length:
                    sock.sendall(b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nOK")
                    break
        if not raw:
            log("(τίποτα — μόνο σύνδεση, καμία αποστολή)")
            return
        path = apothikefsi(port, raw)
        log("ΜΕΓΕΘΟΣ: %d bytes   ΕΙΚΑΣΙΑ: %s   ΩΜΑ: %s"
            % (len(raw), mantepse(raw), path))
        log("-" * 78)
        log(hexdump(raw))
        for enc in ("utf-8", "cp1253", "latin-1"):
            try:
                log("\n--- ως %s ---\n%s" % (enc, raw.decode(enc)[:4000]))
                break
            except UnicodeDecodeError:
                continue
    except Exception as exc:
        log("(σφάλμα: %s)" % exc)
    finally:
        try:
            sock.close()
        except Exception:
            pass


def akou_tcp(port):
    srv = socket.socket()
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        srv.bind(("0.0.0.0", port))
    except Exception as exc:
        log("(θύρα TCP %s δεν άνοιξε: %s)" % (port, exc))
        return
    srv.listen(5)
    while True:
        sock, addr = srv.accept()
        threading.Thread(target=cheiristis, args=(sock, addr, port),
                         daemon=True).start()


def akou_udp(port):
    srv = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        srv.bind(("0.0.0.0", port))
    except Exception as exc:
        log("(θύρα UDP %s δεν άνοιξε: %s)" % (port, exc))
        return
    while True:
        raw, addr = srv.recvfrom(65535)
        log("\n" + "=" * 78)
        log("UDP  θύρα %s  από %s:%s   %s   (%d bytes)"
            % (port, addr[0], addr[1], ora(), len(raw)))
        log("=" * 78)
        log(hexdump(raw))
        apothikefsi("udp%s" % port, raw)


def main():
    args = [int(a) for a in sys.argv[1:] if a.isdigit()]
    tcp = args or TCP_PORTS
    udp = [] if args else UDP_PORTS
    log("\n########## ΝΕΑ ΚΑΤΑΓΡΑΦΗ  %s ##########"
        % datetime.datetime.now().strftime("%d/%m/%Y %H:%M:%S"))
    log("Ακούω TCP: %s" % ", ".join(str(p) for p in tcp))
    if udp:
        log("Ακούω UDP: %s" % ", ".join(str(p) for p in udp))
    log("Βάλε στο πρόγραμμα της Ishida αυτό το μηχάνημα ως IP ζυγού και στείλε.")
    log("Σταμάτημα: Ctrl+C\n")
    for p in tcp:
        threading.Thread(target=akou_tcp, args=(p,), daemon=True).start()
    for p in udp:
        threading.Thread(target=akou_udp, args=(p,), daemon=True).start()
    try:
        while True:
            threading.Event().wait(1)
    except KeyboardInterrupt:
        log("\nΤέλος καταγραφής. Δες το %s και τον φάκελο %s/." % (OUT, RAW_DIR))


if __name__ == "__main__":
    main()
