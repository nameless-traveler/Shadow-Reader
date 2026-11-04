#!/usr/bin/env python3
"""Checks how server.py finds pdftotext (a copy bundled next to the app wins) and how it starts it.

Runs on Linux and Windows. On Windows it also checks that the extractor is started without
opening a console window.
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import server  # noqa: E402


def same_file(a, b) -> bool:
    return a is not None and os.path.samefile(a, b)


def main() -> int:
    results: list[tuple[str, bool]] = []
    exe = "pdftotext.exe" if os.name == "nt" else "pdftotext"
    original_dir = server.BUNDLED_POPPLER_DIR
    original_path = os.environ.get("PATH", "")

    def make_fake(folder: Path) -> Path:
        folder.mkdir(parents=True, exist_ok=True)
        fake = folder / exe
        fake.write_bytes(b"not a real program; only its name and location matter here")
        fake.chmod(0o755)
        return fake

    with tempfile.TemporaryDirectory(prefix="shadow-reader-lookup-") as temp:
        root = Path(temp)
        empty = root / "empty"
        empty.mkdir()
        bundled_dir = root / "bundled"
        path_dir = root / "onpath"
        try:
            server.BUNDLED_POPPLER_DIR = bundled_dir
            os.environ["PATH"] = str(empty)
            results.append(("nothing bundled and nothing on PATH: no extractor found", server._find_extractor() is None))

            on_path = make_fake(path_dir)
            os.environ["PATH"] = str(path_dir)
            results.append(("only on PATH: that copy is used", same_file(server._find_extractor(), on_path)))

            bundled = make_fake(bundled_dir)
            results.append(("bundled and on PATH: the bundled copy wins", same_file(server._find_extractor(), bundled)))

            os.environ["PATH"] = str(empty)
            results.append(("bundled only: the bundled copy is used", same_file(server._find_extractor(), bundled)))
        finally:
            server.BUNDLED_POPPLER_DIR = original_dir
            os.environ["PATH"] = original_path

    results.append(("a plain path becomes a one-item command", server._extractor_command("pdftotext") == ["pdftotext"]))
    results.append(("a command list is kept as it is", server._extractor_command(["python", "fake.py"]) == ["python", "fake.py"]))

    options = server._popen_options()
    if os.name == "nt":
        results.append(("Windows: extractor starts without a console window", options == {"creationflags": 0x08000000}))
    else:
        results.append(("Linux: no special process options", options == {}))

    message = server._missing_extractor_message()
    if os.name == "nt":
        results.append(("Windows: missing-Poppler message points at the bundled folder", "poppler folder" in message))
    else:
        results.append(("Linux: missing-Poppler message points at the package manager", "package manager" in message))

    failed = False
    for name, ok in results:
        print(("PASS: " if ok else "FAIL: ") + name)
        failed = failed or not ok
    if failed:
        return 1
    print(f"PASS: {len(results)} extractor lookup checks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
