#!/usr/bin/env python3
"""Integration checks for Shadow Reader's local HTTP and bounded PDF extraction path."""
from __future__ import annotations

import http.client
import json
import os
import sys
import tempfile
import threading
import time
from pathlib import Path
from http.server import ThreadingHTTPServer

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import server  # noqa: E402


FAKE_EXTRACTOR = r'''#!/usr/bin/env python3
import os
import sys
import time
mode = os.environ.get("SHADOW_READER_TEST_EXTRACTOR_MODE", "ok")
if mode == "ok":
    sys.stdout.buffer.write(b"Book title\fChapter 1: Start\nFirst paragraph.\fChapter 2: End\nLast paragraph.")
elif mode == "large":
    block = b"x" * 65536
    remaining = 25_000_001
    while remaining:
        part = block[:min(len(block), remaining)]
        sys.stdout.buffer.write(part)
        remaining -= len(part)
elif mode == "password":
    sys.stderr.write("Incorrect password: encrypted document\n")
    sys.exit(1)
elif mode == "failure":
    sys.stderr.write("Syntax Error: couldn't find trailer dictionary\n")
    sys.exit(1)
elif mode == "sleep":
    time.sleep(10)
'''


def request(port: int, method: str, path: str, body: bytes | None = None,
            headers: dict[str, str] | None = None) -> tuple[int, dict | bytes]:
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    connection.request(method, path, body=body, headers=headers or {})
    response = connection.getresponse()
    raw = response.read()
    status = response.status
    content_type = response.getheader("Content-Type", "")
    connection.close()
    if "application/json" in content_type:
        return status, json.loads(raw.decode("utf-8"))
    return status, raw


def main() -> int:
    passed: list[str] = []
    failures: list[str] = []
    original_path = os.environ.get("PATH", "")
    original_timeout = server.EXTRACTION_TIMEOUT_SECONDS
    original_poll = server.EXTRACTION_POLL_INTERVAL_SECONDS
    original_upload_timeout = server.UPLOAD_READ_TIMEOUT_SECONDS

    with tempfile.TemporaryDirectory(prefix="shadow-reader-api-test-") as temp_dir:
        extractor_dir = Path(temp_dir)
        extractor = extractor_dir / "pdftotext"
        extractor.write_text(FAKE_EXTRACTOR, encoding="utf-8")
        extractor.chmod(0o755)
        os.environ["PATH"] = str(extractor_dir) + os.pathsep + original_path
        os.environ["SHADOW_READER_TEST_EXTRACTOR_MODE"] = "ok"
        server.EXTRACTION_POLL_INTERVAL_SECONDS = 0.01
        httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        httpd.daemon_threads = True
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        port = httpd.server_port
        try:
            status, health = request(port, "GET", "/api/health")
            if status == 200 and health == {"ok": True, "extractor": True}:
                passed.append("health endpoint reports the local extractor")
            else:
                failures.append(f"health endpoint returned {status}: {health!r}")

            status, invalid_route = request(port, "GET", "/missing")
            if status == 404:
                passed.append("unknown routes return 404")
            else:
                failures.append(f"unknown route returned {status}: {invalid_route!r}")

            status, empty = request(port, "POST", "/api/extract", b"")
            if status == 400:
                passed.append("empty uploads are rejected")
            else:
                failures.append(f"empty upload returned {status}: {empty!r}")

            status, malformed = request(port, "POST", "/api/extract", b"not a PDF")
            if status == 400:
                passed.append("non-PDF upload signatures are rejected")
            else:
                failures.append(f"malformed upload returned {status}: {malformed!r}")

            status, result = request(
                port, "POST", "/api/extract?name=fixture.pdf", b"%PDF-fixture",
                {"Content-Type": "application/pdf"},
            )
            valid = (status == 200 and isinstance(result, dict)
                     and result.get("name") == "fixture.pdf"
                     and "Chapter 1: Start" in result.get("text", "")
                     and result.get("pages") == 3)
            if valid:
                passed.append("valid PDF uploads return UTF-8 text, filename, and page count")
            else:
                failures.append(f"valid PDF returned {status}: {result!r}")

            connection = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
            connection.putrequest("POST", "/api/extract")
            connection.putheader("Content-Length", str(server.MAX_UPLOAD + 1))
            connection.putheader("Content-Type", "application/pdf")
            connection.endheaders()
            response = connection.getresponse()
            body = response.read()
            too_big_status = response.status
            connection.close()
            if too_big_status == 413:
                passed.append("declared uploads above 80 MB are rejected before reading the body")
            else:
                failures.append(f"oversized upload returned {too_big_status}: {body[:200]!r}")

            os.environ["SHADOW_READER_TEST_EXTRACTOR_MODE"] = "password"
            status, password = request(port, "POST", "/api/extract", b"%PDF-fixture")
            if status == 422 and "password-protected" in password.get("error", ""):
                passed.append("password-protected PDF errors are translated into a useful message")
            else:
                failures.append(f"password failure returned {status}: {password!r}")

            os.environ["SHADOW_READER_TEST_EXTRACTOR_MODE"] = "large"
            started = time.monotonic()
            status, large = request(port, "POST", "/api/extract", b"%PDF-fixture")
            elapsed = time.monotonic() - started
            if status == 413 and "25 MB" in large.get("error", "") and elapsed < 8:
                passed.append("oversized extracted text is stopped without buffering an unbounded stdout response")
            else:
                failures.append(f"large extraction returned {status} after {elapsed:.2f}s: {large!r}")

            os.environ["SHADOW_READER_TEST_EXTRACTOR_MODE"] = "sleep"
            server.EXTRACTION_TIMEOUT_SECONDS = 0.35
            started = time.monotonic()
            status, timed_out = request(port, "POST", "/api/extract", b"%PDF-fixture")
            elapsed = time.monotonic() - started
            if status == 408 and elapsed < 3:
                passed.append("slow extraction is terminated at the configured timeout")
            else:
                failures.append(f"slow extraction returned {status} after {elapsed:.2f}s: {timed_out!r}")

            # An upload that announces more bytes than it sends should time out
            # rather than pinning a server thread forever.
            server.UPLOAD_READ_TIMEOUT_SECONDS = 0.35
            connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
            connection.putrequest("POST", "/api/extract")
            connection.putheader("Content-Length", "100")
            connection.putheader("Content-Type", "application/pdf")
            connection.endheaders(b"%PDF-partial")
            started = time.monotonic()
            partial_response = connection.getresponse()
            partial_body = partial_response.read()
            partial_status = partial_response.status
            partial_elapsed = time.monotonic() - started
            connection.close()
            if partial_status == 408 and partial_elapsed < 3:
                passed.append("stalled partial uploads time out without hanging a request thread")
            else:
                failures.append(f"partial upload returned {partial_status} after {partial_elapsed:.2f}s: {partial_body[:200]!r}")

            # Simulate a machine without Poppler: the normal handler reports the
            # missing optional dependency, and main() still starts in text-only mode.
            original_which = server.shutil.which
            original_http_server = server.ThreadingHTTPServer
            original_port = server.PORT
            original_browser_open = server.webbrowser.open
            server.shutil.which = lambda _command: None
            try:
                status, no_poppler_health = request(port, "GET", "/api/health")
                status_pdf, no_poppler_error = request(port, "POST", "/api/extract", b"%PDF-fixture")
                if status == 200 and no_poppler_health.get("extractor") is False and status_pdf == 503:
                    passed.append("health/API clearly reports PDF import unavailable when Poppler is missing")
                else:
                    failures.append(f"missing Poppler response was health={no_poppler_health!r}, PDF={status_pdf}: {no_poppler_error!r}")

                started_servers: list[ThreadingHTTPServer] = []
                startup_errors: list[BaseException] = []

                class TrackingServer(ThreadingHTTPServer):
                    def __init__(self, address, handler):
                        super().__init__(address, handler)
                        self.daemon_threads = True
                        started_servers.append(self)

                server.ThreadingHTTPServer = TrackingServer
                server.PORT = 0
                server.webbrowser.open = lambda *_args, **_kwargs: True

                def run_main() -> None:
                    try:
                        server.main()
                    except BaseException as exc:  # capture startup failure for the assertion below
                        startup_errors.append(exc)

                main_thread = threading.Thread(target=run_main, daemon=True)
                main_thread.start()
                deadline = time.monotonic() + 3
                while not started_servers and main_thread.is_alive() and time.monotonic() < deadline:
                    time.sleep(0.01)
                if started_servers:
                    no_poppler_server = started_servers[0]
                    status, startup_health = request(no_poppler_server.server_port, "GET", "/api/health")
                    no_poppler_server.shutdown()
                    no_poppler_server.server_close()
                    main_thread.join(timeout=2)
                    if status == 200 and startup_health.get("extractor") is False and not main_thread.is_alive() and not startup_errors:
                        passed.append("server main starts and serves .txt mode when Poppler is absent")
                    else:
                        failures.append(f"text-only startup returned {status}: health={startup_health!r}, errors={startup_errors!r}, alive={main_thread.is_alive()}")
                else:
                    failures.append(f"server main failed to start without Poppler: {startup_errors!r}")
            finally:
                server.shutil.which = original_which
                server.ThreadingHTTPServer = original_http_server
                server.PORT = original_port
                server.webbrowser.open = original_browser_open

        finally:
            httpd.shutdown()
            httpd.server_close()
            thread.join(timeout=2)
            server.EXTRACTION_TIMEOUT_SECONDS = original_timeout
            server.EXTRACTION_POLL_INTERVAL_SECONDS = original_poll
            server.UPLOAD_READ_TIMEOUT_SECONDS = original_upload_timeout
            os.environ["PATH"] = original_path
            os.environ.pop("SHADOW_READER_TEST_EXTRACTOR_MODE", None)

    if failures:
        print("FAIL: local server API regression test")
        for failure in failures:
            print(" - " + failure)
        print(f"Passed before failure: {len(passed)} checks")
        return 1
    print(f"PASS: {len(passed)} local server API checks")
    for item in passed:
        print(" - " + item)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
