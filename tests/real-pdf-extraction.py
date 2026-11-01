#!/usr/bin/env python3
"""End-to-end check of POST /api/extract using the REAL Poppler `pdftotext`.

tests/server-api-regression.py uses a fake extractor on purpose (to test limits and
timeouts). This test is the complement: it builds a small valid PDF in memory, sends
it to the real request handler, and checks what the real Poppler binary returns.
Needs `poppler-utils`; fails loudly if it is missing so CI cannot pass without it.
"""
from __future__ import annotations

import http.client
import json
import shutil
import sys
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import server  # noqa: E402


def build_pdf(pages: list[list[str]]) -> bytes:
    """Return a minimal valid PDF: standard Helvetica (no embedded fonts), one text block per page."""
    kids = " ".join(f"{4 + 2 * i} 0 R" for i in range(len(pages)))
    objects: list[bytes] = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        f"<< /Type /Pages /Kids [{kids}] /Count {len(pages)} >>".encode(),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
    ]
    for i, lines in enumerate(pages):
        content_obj = 5 + 2 * i
        objects.append(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            f"/Resources << /Font << /F1 3 0 R >> >> /Contents {content_obj} 0 R >>".encode()
        )
        ops = ["BT", "/F1 12 Tf", "72 720 Td", "16 TL"]
        for line in lines:
            escaped = line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
            ops.append(f"({escaped}) Tj T*")
        ops.append("ET")
        stream = "\n".join(ops).encode("cp1252")
        objects.append(b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream")

    out = bytearray(b"%PDF-1.4\n")
    offsets: list[int] = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n".encode() + body + b"\nendobj\n"
    xref_at = len(out)
    out += f"xref\n0 {len(objects) + 1}\n".encode() + b"0000000000 65535 f \n"
    for offset in offsets:
        out += f"{offset:010d} 00000 n \n".encode()
    out += (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_at}\n%%EOF\n"
    ).encode()
    return bytes(out)


def post(port: int, body: bytes, name: str = "sample.pdf") -> tuple[int, dict]:
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=30)
    connection.request("POST", f"/api/extract?name={name}", body=body)
    response = connection.getresponse()
    payload = json.loads(response.read().decode("utf-8"))
    status = response.status
    connection.close()
    return status, payload


def main() -> int:
    if shutil.which("pdftotext") is None:
        print("FAIL: pdftotext not found. Install it with: sudo apt-get install -y poppler-utils")
        return 1

    pages = [
        ["Chapter 1", "", "The lantern burned low over the harbour.", "Café au lait at dawn."],
        ["Chapter 2", "", "By morning the fog had lifted."],
    ]
    pdf = build_pdf(pages)

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
    httpd.daemon_threads = True
    port = httpd.server_address[1]
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()

    results: list[tuple[str, bool]] = []
    try:
        status, payload = post(port, pdf)
        text = payload.get("text", "")
        results += [
            ("valid PDF returns HTTP 200", status == 200),
            ("filename is echoed back", payload.get("name") == "sample.pdf"),
            ("page count comes from real Poppler (2 pages)", payload.get("pages") == 2),
            ("chapter headings survive extraction", "Chapter 1" in text and "Chapter 2" in text),
            ("body text survives extraction", "The lantern burned low over the harbour." in text),
            ("non-ASCII text is UTF-8 (Café)", "Café au lait at dawn." in text),
            ("pages are separated by a form feed", "\f" in text),
        ]

        status, payload = post(port, b"this is plain text, not a PDF at all")
        results.append(("non-PDF body is rejected with 400", status == 400))

        status, payload = post(port, b"%PDF-1.4\nthis is not a real pdf, just a header\n")
        results.append(("corrupt PDF gets a clear 4xx error, not a 500", status == 422 and "error" in payload))
    finally:
        httpd.shutdown()
        httpd.server_close()

    failed = False
    for name, ok in results:
        print(("PASS: " if ok else "FAIL: ") + name)
        failed = failed or not ok
    if failed:
        return 1
    print(f"PASS: {len(results)} real-Poppler extraction checks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
