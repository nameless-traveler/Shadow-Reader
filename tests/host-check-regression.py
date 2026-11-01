#!/usr/bin/env python3
"""The local server must only answer requests addressed to itself.

Without this, a web page on another site can reach the server through the user's browser
(directly, or via DNS rebinding where the page's hostname is pointed at 127.0.0.1) and make
it run pdftotext on attacker-supplied files.
"""
from __future__ import annotations

import http.client
import socket
import sys
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import server  # noqa: E402


def main() -> int:
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
    httpd.daemon_threads = True
    port = httpd.server_address[1]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()

    def call(method: str, path: str, headers: dict[str, str], body: bytes | None = None) -> int:
        connection = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
        connection.request(method, path, body=body, headers=headers)
        status = connection.getresponse().status
        connection.close()
        return status

    def raw_without_host() -> int:
        with socket.create_connection(("127.0.0.1", port), timeout=10) as sock:
            sock.sendall(b"GET /api/health HTTP/1.0\r\n\r\n")
            return int(sock.recv(64).split()[1])

    own, local = f"127.0.0.1:{port}", f"localhost:{port}"
    checks = [
        ("Host 127.0.0.1:port is served", call("GET", "/api/health", {"Host": own}) == 200),
        ("Host localhost:port is served", call("GET", "/api/health", {"Host": local}) == 200),
        ("page itself is served on its own address", call("GET", "/", {"Host": own}) == 200),
        ("foreign Host is refused (DNS rebinding)", call("GET", "/api/health", {"Host": f"evil.example:{port}"}) == 403),
        ("foreign Host without port is refused", call("GET", "/api/health", {"Host": "evil.example"}) == 403),
        ("foreign Host cannot fetch the page", call("GET", "/", {"Host": f"evil.example:{port}"}) == 403),
        ("missing Host header is refused", raw_without_host() == 403),
        ("own Origin is accepted", call("GET", "/api/health", {"Host": own, "Origin": f"http://{own}"}) == 200),
        ("foreign Origin is refused", call("GET", "/api/health", {"Host": own, "Origin": "http://evil.example"}) == 403),
        ("Origin 'null' is refused", call("GET", "/api/health", {"Host": own, "Origin": "null"}) == 403),
        ("cross-site upload is refused before it is read",
            call("POST", "/api/extract?name=x.pdf", {"Host": own, "Origin": "http://evil.example"}, b"%PDF-1.4 x") == 403),
        ("same-site upload gets past the check (rejected only as not-a-PDF)",
            call("POST", "/api/extract?name=x.txt", {"Host": own, "Origin": f"http://{own}"}, b"plain text") == 400),
    ]
    httpd.shutdown()
    httpd.server_close()

    failed = False
    for name, ok in checks:
        print(("PASS: " if ok else "FAIL: ") + name)
        failed = failed or not ok
    if failed:
        return 1
    print(f"PASS: {len(checks)} host/origin checks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
