#!/usr/bin/env python3
"""The Linux download: right files, run.sh is executable, nothing extra, same input gives the same bytes."""
from __future__ import annotations

import importlib.util
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("build_linux_zip", ROOT / "linux" / "build_linux_zip.py")
bl = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bl)


def main() -> int:
    results: list[tuple[str, bool]] = []
    with tempfile.TemporaryDirectory(prefix="shadow-reader-linux-zip-") as temp:
        one, two = Path(temp) / "one.zip", Path(temp) / "two.zip"
        bl.build(one)
        bl.build(two)
        with zipfile.ZipFile(one) as archive:
            files = {i.filename: i for i in archive.infolist() if not i.filename.endswith("/")}
            bad = archive.testzip()
        p = bl.ZIP_ROOT + "/"
        expected = {p + n for n in ("LICENSE", "README.md", "index.html", "run.sh", "server.py", "assets/shadow-reader-logo.png")}
        results.append(("zip holds exactly the app, launcher, logo, README and licence", set(files) == expected))
        results.append(("run.sh is executable inside the zip", (files[p + "run.sh"].external_attr >> 16) & 0o111 == 0o111))
        results.append(("no other file is executable", all(((i.external_attr >> 16) & 0o111) == 0 for n, i in files.items() if n != p + "run.sh")))
        results.append(("zip passes its own integrity check", bad is None))
        results.append(("same input gives a byte-identical zip", one.read_bytes() == two.read_bytes()))
        results.append(("zip contains no tests, caches or git files",
                        not any(("tests/" in n or "__pycache__" in n or ".git" in n) for n in files)))
    version = bl.app_version()
    results.append(("version is read from server.py", version.count(".") == 2 and version.replace(".", "").isdigit()))
    readme = (ROOT / "linux" / "README.md").read_text(encoding="utf-8")
    results.append(("zip README tells people to run ./run.sh", "./run.sh" in readme and "127.0.0.1:8765" in readme))

    failed = False
    for name, ok in results:
        print(("PASS: " if ok else "FAIL: ") + name)
        failed = failed or not ok
    if failed:
        return 1
    print(f"PASS: {len(results)} Linux packaging checks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
