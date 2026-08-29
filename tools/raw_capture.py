# Κρατάει ΑΥΤΟΥΣΙΟ το σώμα του αιτήματος, για σύγκριση byte-προς-byte.
# Αγνοεί τις κενές συνδέσεις (π.χ. τον γρήγορο έλεγχο «απαντά ο ζυγός;»).
import socket, sys, re
srv = socket.socket(); srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
srv.bind(("0.0.0.0", 1235)); srv.listen(5)
while True:
    c, _ = srv.accept()
    c.settimeout(30)
    data = b""
    try:
        while b"\r\n\r\n" not in data:
            chunk = c.recv(65536)
            if not chunk: break
            data += chunk
    except Exception:
        pass
    if b"\r\n\r\n" not in data:      # κενή σύνδεση: προχώρα στην επόμενη
        c.close(); continue
    head, _, body = data.partition(b"\r\n\r\n")
    m = re.search(rb"Content-Length:\s*(\d+)", head, re.I)
    need = int(m.group(1)) if m else 0
    while len(body) < need:
        chunk = c.recv(65536)
        if not chunk: break
        body += chunk
    sys.stdout.buffer.write(body); sys.stdout.buffer.flush()
    ok = b'{"result":"success","code":0,"msg":"ok"}'
    c.sendall(b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: %d\r\n\r\n%s" % (len(ok), ok))
    c.close()
    break
