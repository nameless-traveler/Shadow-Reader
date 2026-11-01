#!/usr/bin/env python3
"""Checks that the logo is served correctly, is cacheable, and has not bloated again."""
from __future__ import annotations

import http.client
import sys
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import server  # noqa: E402

MAX_LOGO_BYTES = 400_000  # the app shows it at 42px; anything bigger is wasted bandwidth
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def main() -> int:
    on_disk = (ROOT / "assets" / "shadow-reader-logo.png").read_bytes()

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
    httpd.daemon_threads = True
    port = httpd.server_address[1]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()

    try:
        connection = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
        connection.request("GET", "/assets/shadow-reader-logo.png")
        response = connection.getresponse()
        body = response.read()
        headers = {key.lower(): value for key, value in response.getheaders()}
        status = response.status
        connection.close()

        connection = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
        connection.request("GET", "/")
        page = connection.getresponse()
        page.read()
        page_cache = page.getheader("Cache-Control")
        connection.close()
    finally:
        httpd.shutdown()
        httpd.server_close()

    checks = [
        ("logo route returns 200", status == 200),
        ("logo is served as image/png", headers.get("content-type") == "image/png"),
        ("served bytes are a real PNG", body.startswith(PNG_SIGNATURE)),
        ("served bytes match assets/shadow-reader-logo.png", body == on_disk),
        ("logo is cacheable (max-age set)", "max-age=" in headers.get("cache-control", "")),
        ("app page itself is still never cached", page_cache == "no-store"),
        (f"logo is under {MAX_LOGO_BYTES // 1000} KB (is {len(on_disk) // 1000} KB)", len(on_disk) <= MAX_LOGO_BYTES),
    ]
    failed = False
    for name, ok in checks:
        print(("PASS: " if ok else "FAIL: ") + name)
        failed = failed or not ok
    if failed:
        return 1
    print(f"PASS: {len(checks)} logo route checks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
