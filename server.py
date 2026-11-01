#!/usr/bin/env python3
"""Tiny localhost server for Shadow Reader. PDF extraction is handled by Poppler's pdftotext."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

APP_DIR = Path(__file__).resolve().parent
HOST = "127.0.0.1"
PORT = int(os.environ.get("SHADOW_READER_PORT", "8765"))
MAX_UPLOAD = 80 * 1024 * 1024
MAX_EXTRACTED_TEXT_BYTES = 25_000_000
EXTRACTION_TIMEOUT_SECONDS = 150
EXTRACTION_POLL_INTERVAL_SECONDS = 0.025
UPLOAD_READ_TIMEOUT_SECONDS = 60


def _run_bounded_extraction(extractor: str, pdf_path: str) -> tuple[str, bytes | str | None]:
    """Run pdftotext without buffering an unbounded extraction in RAM.

    Returns ("ok", utf8_bytes), ("too_large", None), ("timeout", None), or
    ("error", stderr_text). Output is written to a temporary file and watched
    while Poppler runs, so a malformed PDF cannot fill memory with stdout.
    """
    command = [extractor, "-enc", "UTF-8", "-layout", pdf_path, "-"]
    with tempfile.TemporaryFile() as output, tempfile.TemporaryFile() as errors:
        process = subprocess.Popen(command, stdout=output, stderr=errors)
        started = time.monotonic()
        while process.poll() is None:
            if os.fstat(output.fileno()).st_size > MAX_EXTRACTED_TEXT_BYTES:
                process.kill()
                process.wait()
                return "too_large", None
            if time.monotonic() - started >= EXTRACTION_TIMEOUT_SECONDS:
                process.kill()
                process.wait()
                return "timeout", None
            time.sleep(EXTRACTION_POLL_INTERVAL_SECONDS)

        output_size = os.fstat(output.fileno()).st_size
        if output_size > MAX_EXTRACTED_TEXT_BYTES:
            return "too_large", None
        if process.returncode != 0:
            errors.seek(0)
            detail = errors.read(64_000).decode("utf-8", "replace").strip()
            return "error", detail
        output.seek(0)
        extracted = output.read(MAX_EXTRACTED_TEXT_BYTES + 1)
        if len(extracted) > MAX_EXTRACTED_TEXT_BYTES:
            return "too_large", None
        return "ok", extracted


class Handler(BaseHTTPRequestHandler):
    server_version = "ShadowReader/1.0.0"

    def log_message(self, fmt: str, *args) -> None:
        # Keep the terminal calm; server errors are reported by the relevant handler.
        if args and str(args[1:]).startswith("('GET', '/api"):
            super().log_message(fmt, *args)

    def _send(self, status: int, body: bytes, content_type: str = "text/plain; charset=utf-8",cache_control: str = "no-store") -> None:
        self.close_connection = True
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Cache-Control", cache_control)
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status: int, payload: dict) -> None:
        self._send(status, json.dumps(payload, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

    def do_GET(self) -> None:
        route = urlsplit(self.path).path
        if route in ("/", "/index.html"):
            try:
                data = (APP_DIR / "index.html").read_bytes()
            except OSError:
                self._send(500, b"Shadow Reader index.html could not be read.")
                return
            self._send(200, data, "text/html; charset=utf-8")
            return
        if route == "/assets/shadow-reader-logo.png":
            try:
                data = (APP_DIR / "assets" / "shadow-reader-logo.png").read_bytes()
            except OSError:
                self._send(404, b"Shadow Reader logo was not found.")
                return
            self._send(200, data, "image/png", "public, max-age=86400")
            return
        if route == "/api/health":
            self._json(200, {"ok": True, "extractor": shutil.which("pdftotext") is not None})
            return
        self._send(404, b"Not found")

    def do_POST(self) -> None:
        if urlsplit(self.path).path != "/api/extract":
            self._json(404, {"error": "Not found"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self._json(400, {"error": "Invalid upload size."})
            return
        if length <= 0:
            self._json(400, {"error": "The uploaded file was empty."})
            return
        if length > MAX_UPLOAD:
            self._json(413, {"error": "File exceeds the 80 MB size limit."})
            return
        filename = parse_qs(urlsplit(self.path).query).get("name", ["document.pdf"])[0]
        extractor = shutil.which("pdftotext")
        if not extractor:
            self._json(503, {"error": "The Poppler text extractor is missing. Install it with: sudo apt update && sudo apt install poppler-utils"})
            return
        tmp_name = None
        try:
            # Stream the upload to disk in bounded chunks rather than holding an
            # 80 MB PDF in memory. A timeout prevents a stalled local client from
            # occupying a request thread indefinitely.
            self.connection.settimeout(UPLOAD_READ_TIMEOUT_SECONDS)
            remaining = length
            header = bytearray()
            with tempfile.NamedTemporaryFile(prefix="shadow-reader-", suffix=".pdf", delete=False) as tmp:
                tmp_name = tmp.name
                while remaining:
                    chunk = self.rfile.read(min(1024 * 1024, remaining))
                    if not chunk:
                        self._json(400, {"error": "The upload ended unexpectedly. Try opening the file again."})
                        return
                    if len(header) < 4:
                        header.extend(chunk[:4 - len(header)])
                    tmp.write(chunk)
                    remaining -= len(chunk)

            if not bytes(header).startswith(b"%PDF"):
                self._json(400, {"error": "This does not look like a PDF file. Choose a PDF or a plain-text file."})
                return

            outcome, result = _run_bounded_extraction(extractor, tmp_name)
            if outcome == "too_large":
                self._json(413, {"error": "The extracted text is unusually large (over 25 MB). Try splitting the PDF into smaller parts."})
                return
            if outcome == "timeout":
                self._json(408, {"error": "Text extraction took too long. Try a smaller PDF or split it into parts."})
                return
            if outcome == "error":
                detail = str(result or "")
                if "incorrect password" in detail.lower() or "password" in detail.lower():
                    self._json(422, {"error": "This PDF may be password-protected. Unlock it first, then open it here."})
                else:
                    self._json(422, {"error": "Poppler could not read this PDF. It may be damaged or password-protected."})
                return

            text = bytes(result or b"").decode("utf-8", "replace")
            pages = sum(1 for page in text.split("\f") if page.strip())
            self._json(200, {"name": filename, "text": text, "pages": pages})
        except (TimeoutError, OSError) as exc:
            if isinstance(exc, TimeoutError):
                self._json(408, {"error": "The upload took too long or ended unexpectedly. Try opening the file again."})
            else:
                self._json(500, {"error": f"A local extraction error occurred: {type(exc).__name__}."})
        except Exception as exc:  # graceful response to unexpected local errors
            self._json(500, {"error": f"A local extraction error occurred: {type(exc).__name__}."})
        finally:
            if tmp_name:
                try:
                    os.unlink(tmp_name)
                except OSError:
                    pass


def main() -> None:
    if not shutil.which("pdftotext"):
        print("Poppler's pdftotext command is missing; PDF import is disabled for this run.")
        print("Plain-text (.txt) files still work. Install PDF support with:")
        print("sudo apt update && sudo apt install poppler-utils")
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    url = f"http://{HOST}:{PORT}/"
    print("\nShadow Reader is running locally.")
    print(f"Open: {url}")
    print("Your PDF is processed on this computer; the server listens only on 127.0.0.1.")
    print("Keep this terminal open while reading. Press Ctrl+C to stop.\n")
    threading.Timer(0.8, lambda: webbrowser.open(url, new=1, autoraise=True)).start()
    try:
        server.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        print("\nShadow Reader stopped.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
