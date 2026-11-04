#!/usr/bin/env python3
"""Runs the finished Windows zip the way a user would, on Windows, and checks that reading a PDF works.

    python windows/smoke_test_zip.py dist/Shadow-Reader-windows.zip

It extracts the zip, starts Shadow-Reader.bat (so the bundled Python and the bundled Poppler are used,
never the ones installed on this machine), sends a real PDF to the running server and checks the text.
"""
from __future__ import annotations

import http.client
import importlib.util
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_build_pdf():
    spec = importlib.util.spec_from_file_location("real_pdf_extraction", ROOT / "tests" / "real-pdf-extraction.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.build_pdf


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def request(port: int, method: str, path: str, body: bytes | None = None):
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=30)
    connection.request(method, path, body=body)
    response = connection.getresponse()
    data = response.read()
    status = response.status
    connection.close()
    return status, data


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: python windows/smoke_test_zip.py path/to/Shadow-Reader-windows.zip")
        return 2
    if sys.platform != "win32":
        print("SKIP: this check runs the Windows launcher, so it needs Windows.")
        return 0

    zip_path = Path(sys.argv[1]).resolve()
    results: list[tuple[str, bool]] = []
    with tempfile.TemporaryDirectory(prefix="shadow-reader-smoke-") as temp:
        with zipfile.ZipFile(zip_path) as archive:
            archive.extractall(temp)
        app = Path(temp) / "shadow-reader"
        results.append(("zip has the launcher, bundled Python and bundled Poppler",
                        (app / "Shadow-Reader.bat").is_file() and (app / "python" / "python.exe").is_file()
                        and (app / "poppler" / "bin" / "pdftotext.exe").is_file()))

        port = free_port()
        env = dict(os.environ, SHADOW_READER_PORT=str(port))
        # Make sure nothing installed on this machine can be used by accident.
        env["PATH"] = os.environ.get("SystemRoot", r"C:\Windows") + r"\System32"
        log = open(Path(temp) / "server.log", "wb")
        process = subprocess.Popen(["cmd", "/c", str(app / "Shadow-Reader.bat")], cwd=app, env=env,
                                   stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT)
        try:
            health = None
            deadline = time.monotonic() + 40
            while time.monotonic() < deadline and process.poll() is None:
                try:
                    status, data = request(port, "GET", "/api/health")
                    if status == 200:
                        health = json.loads(data)
                        break
                except OSError:
                    time.sleep(0.5)
            results.append(("launcher starts the server", health is not None and health.get("ok") is True))
            results.append(("server finds the bundled Poppler", bool(health) and health.get("extractor") is True))

            if health and health.get("extractor"):
                pdf = load_build_pdf()([["Chapter 1", "", "The lantern burned low over the harbour.", "Caf\u00e9 au lait at dawn."],
                                        ["Chapter 2", "", "By morning the fog had lifted."]])
                status, data = request(port, "POST", "/api/extract?name=sample.pdf", pdf)
                payload = json.loads(data) if data else {}
                text = payload.get("text", "")
                results += [
                    ("real PDF is extracted with the bundled Poppler (HTTP 200)", status == 200),
                    ("page count is right", payload.get("pages") == 2),
                    ("body text survives", "The lantern burned low over the harbour." in text),
                    ("non-ASCII text survives (Caf\u00e9)", "Caf\u00e9 au lait at dawn." in text),
                ]
        finally:
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(process.pid)], capture_output=True)
            log.close()
            if not all(ok for _, ok in results):
                print("----- server output -----")
                print((Path(temp) / "server.log").read_text(errors="replace"))
                print("-------------------------")

    failed = False
    for name, ok in results:
        print(("PASS: " if ok else "FAIL: ") + name)
        failed = failed or not ok
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
