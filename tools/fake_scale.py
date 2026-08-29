# -*- coding: utf-8 -*-
"""Ψεύτικος ζυγός: καταγράφει ΑΚΡΙΒΩΣ τι του στέλνει το AutoProcess.

Ιδέα: αντί να κρυφακούμε το δίκτυο, βάζουμε το AutoProcess να στείλει σε εμάς.
Στο ip.xml βάζουμε 127.0.0.1, τρέχουμε αυτό, και βλέπουμε το αίτημα καθαρό —
διεύθυνση, κεφαλίδες και ολόκληρο το JSON.

Χρήση (στα Windows, με Python εγκατεστημένη):
    python fake_scale.py            (θύρα 80)
    python fake_scale.py 8080       (άλλη θύρα, αν η 80 είναι πιασμένη)
"""

import io
import json
import sys
import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer

OUT = "katagrafi_zygou.txt"
_n = [0]


def log(text):
    print(text)
    with io.open(OUT, "a", encoding="utf-8") as fh:
        fh.write(text + "\n")


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _record(self, method):
        _n[0] += 1
        raw = b""
        length = int(self.headers.get("Content-Length") or 0)
        if length:
            raw = self.rfile.read(length)

        log("\n" + "=" * 78)
        log("ΑΙΤΗΜΑ #%d   %s" % (_n[0], datetime.datetime.now().strftime("%H:%M:%S")))
        log("=" * 78)
        log("%s %s %s" % (method, self.path, self.request_version))
        log("\n--- ΚΕΦΑΛΙΔΕΣ ---")
        for k, v in self.headers.items():
            log("%s: %s" % (k, v))

        if raw:
            log("\n--- ΣΩΜΑ (%d bytes) ---" % len(raw))
            text = None
            for enc in ("utf-8", "cp1253", "gb2312"):
                try:
                    text = raw.decode(enc)
                    log("(αποκωδικοποιήθηκε ως %s)" % enc)
                    break
                except UnicodeDecodeError:
                    continue
            if text is None:
                log("(δυαδικά δεδομένα) %r" % raw[:400])
            else:
                try:                       # αν είναι JSON, το δείχνουμε με σειρά
                    data = json.loads(text)
                    log(json.dumps(data, ensure_ascii=False, indent=2)[:6000])
                    log("\n--- ΣΥΝΟΨΗ ---")
                    if isinstance(data, list):
                        log("πίνακας με %d αντικείμενα" % len(data))
                        if data:
                            log("κλειδιά 1ου: %s" % ", ".join(sorted(data[0])))
                    elif isinstance(data, dict):
                        log("κλειδιά: %s" % ", ".join(sorted(data)))
                        for k, v in data.items():
                            if isinstance(v, list):
                                log("το «%s» είναι πίνακας με %d στοιχεία" % (k, len(v)))
                                if v and isinstance(v[0], dict):
                                    log("κλειδιά 1ου: %s" % ", ".join(sorted(v[0])))
                except ValueError:
                    log(text[:6000])
        else:
            log("\n(χωρίς σώμα)")

        # Απαντάμε «οκ» με διάφορες μορφές, μήπως και συνεχίσει σε επόμενο βήμα
        body = json.dumps({"result": "success", "code": 0, "msg": "ok",
                           "status": "success"}).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        self._record("POST")

    def do_GET(self):
        self._record("GET")

    def do_PUT(self):
        self._record("PUT")

    def log_message(self, *args):
        pass                                # κρατάμε μόνο τη δική μας καταγραφή


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 80
    open(OUT, "w", encoding="utf-8").close()
    log("Ψεύτικος ζυγός σε http://127.0.0.1:%d" % port)
    log("Βάλε 127.0.0.1 στο ip.xml, τρέξε το AutoProcess, και θα δεις εδώ το αίτημα.")
    log("Η καταγραφή γράφεται και στο αρχείο: %s" % OUT)
    log("Σταμάτημα: Ctrl+C\n")
    try:
        HTTPServer(("0.0.0.0", port), Handler).serve_forever()
    except KeyboardInterrupt:
        log("\nΤέλος καταγραφής. Στείλε το αρχείο %s" % OUT)
    except PermissionError:
        log("Η θύρα %d δεν επιτρέπεται. Δοκίμασε: python fake_scale.py 8080" % port)
    except OSError as exc:
        log("Η θύρα %d είναι πιασμένη (%s). Δοκίμασε άλλη: python fake_scale.py 8080"
            % (port, exc))


if __name__ == "__main__":
    main()
