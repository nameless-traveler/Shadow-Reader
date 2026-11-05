#!/usr/bin/env python3
"""Runs the finished Windows zip the way a user would, on Windows, and checks that it works end to end.

    python windows/smoke_test_zip.py dist/Shadow-Reader-windows.zip

It extracts the zip, starts Shadow-Reader.bat (so the bundled Python and the bundled Poppler are used,
never the ones installed on this machine), then checks the page, the logo, a real PDF, a 300-page PDF,
a second copy on the same port, and stopping and starting again.
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


def request(port: int, method: str, path: str, body: bytes | None = None, timeout: int = 30):
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=timeout)
    connection.request(method, path, body=body)
    response = connection.getresponse()
    data = response.read()
    status = response.status
    content_type = response.getheader("Content-Type", "")
    connection.close()
    return status, data, content_type


def clean_env(port: int) -> dict:
    env = dict(os.environ, SHADOW_READER_PORT=str(port))
    # Make sure nothing installed on this machine can be used by accident.
    env["PATH"] = os.environ.get("SystemRoot", r"C:\Windows") + r"\System32"
    return env


def start_launcher(app: Path, port: int, log) -> subprocess.Popen:
    return subprocess.Popen(["cmd", "/c", str(app / "Shadow-Reader.bat")], cwd=app, env=clean_env(port),
                            stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT)


def stop_launcher(process: subprocess.Popen) -> None:
    subprocess.run(["taskkill", "/F", "/T", "/PID", str(process.pid)], capture_output=True)


def wait_for_health(port: int, process: subprocess.Popen, seconds: int = 40):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline and process.poll() is None:
        try:
            status, data, _ = request(port, "GET", "/api/health")
            if status == 200:
                return json.loads(data)
        except OSError:
            time.sleep(0.5)
    return None


def port_is_closed(port: int, seconds: int = 15) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        try:
            request(port, "GET", "/api/health")
        except OSError:
            return True
        time.sleep(0.5)
    return False


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: python windows/smoke_test_zip.py path/to/Shadow-Reader-windows.zip")
        return 2
    if sys.platform != "win32":
        print("SKIP: this check runs the Windows launcher, so it needs Windows.")
        return 0

    zip_path = Path(sys.argv[1]).resolve()
    results: list[tuple[str, bool]] = []
    with tempfile.TemporaryDirectory(prefix="shadow-reader-smoke-", ignore_cleanup_errors=True) as temp:
        with zipfile.ZipFile(zip_path) as archive:
            archive.extractall(temp)
        app = Path(temp) / "shadow-reader"
        results.append(("zip has the launcher, bundled Python and bundled Poppler",
                        (app / "Shadow-Reader.bat").is_file() and (app / "python" / "python.exe").is_file()
                        and (app / "poppler" / "bin" / "pdftotext.exe").is_file()))

        build_pdf = load_build_pdf()
        port = free_port()
        log = open(Path(temp) / "server.log", "wb")
        process = start_launcher(app, port, log)
        restarted = None
        try:
            health = wait_for_health(port, process)
            results.append(("launcher starts the server", health is not None and health.get("ok") is True))
            results.append(("server finds the bundled Poppler", bool(health) and health.get("extractor") is True))

            if health:
                # The page and its static files.
                status, data, content_type = request(port, "GET", "/")
                results.append(("the reader page is served", status == 200 and "text/html" in content_type
                                and b"Shadow Reader" in data and b"<html" in data.lower()))
                status, data, content_type = request(port, "GET", "/assets/shadow-reader-logo.png")
                results.append(("the logo is served and is the file from the zip",
                                status == 200 and "image/png" in content_type and data.startswith(b"\x89PNG")
                                and data == (app / "assets" / "shadow-reader-logo.png").read_bytes()))
                status, _, _ = request(port, "GET", "/no-such-page")
                results.append(("an unknown page gives 404", status == 404))

            if health and health.get("extractor"):
                pdf = build_pdf([["Chapter 1", "", "The lantern burned low over the harbour.", "Caf\u00e9 au lait at dawn."],
                                 ["Chapter 2", "", "By morning the fog had lifted."]])
                status, data, _ = request(port, "POST", "/api/extract?name=sample.pdf", pdf)
                payload = json.loads(data) if data else {}
                text = payload.get("text", "")
                results += [
                    ("real PDF is extracted with the bundled Poppler (HTTP 200)", status == 200),
                    ("page count is right", payload.get("pages") == 2),
                    ("body text survives", "The lantern burned low over the harbour." in text),
                    ("non-ASCII text survives (Caf\u00e9)", "Caf\u00e9 au lait at dawn." in text),
                ]

                # A long book: 300 pages of 30 lines each.
                pages = [[f"Chapter {n}", ""] + [f"Page {n} line {i} of the long book." for i in range(28)] for n in range(1, 301)]
                big = build_pdf(pages)
                started = time.monotonic()
                status, data, _ = request(port, "POST", "/api/extract?name=long.pdf", big, timeout=120)
                seconds = time.monotonic() - started
                payload = json.loads(data) if data else {}
                text = payload.get("text", "")
                results += [
                    (f"a 300-page PDF is extracted ({len(big) // 1024} KB, {seconds:.1f} s)", status == 200 and seconds < 60),
                    ("long PDF: page count is right", payload.get("pages") == 300),
                    ("long PDF: first and last pages are both there",
                     "Page 1 line 0 of the long book." in text and "Page 300 line 27 of the long book." in text),
                ]

            if health:
                # A second copy on the same port must refuse clearly and leave the first one alone.
                second = subprocess.run([str(app / "python" / "python.exe"), "server.py"], cwd=app, env=clean_env(port),
                                        stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=60)
                results.append(("a second copy on the same port exits with a clear message",
                                second.returncode == 1 and "already in use" in second.stdout))
                results.append(("the first copy keeps working after that", wait_for_health(port, process, 10) is not None))

                # Stopping must leave nothing behind, and starting again must work straight away.
                stop_launcher(process)
                results.append(("after stopping, nothing is left holding the port", port_is_closed(port)))
                restarted = start_launcher(app, port, log)
                again = wait_for_health(port, restarted)
                results.append(("starting again on the same port works right away", again is not None and again.get("ok") is True))
        finally:
            for running in (process, restarted):
                if running is not None:
                    stop_launcher(running)
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
