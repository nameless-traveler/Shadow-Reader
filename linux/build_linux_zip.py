#!/usr/bin/env python3
"""Builds the Linux download from this repository.

    python3 linux/build_linux_zip.py                  # writes dist/Shadow-Reader-<version>-linux.zip
    python3 linux/build_linux_zip.py --out some.zip

The zip holds only what is needed to read: the app, the launcher, the logo, a short README
(linux/README.md) and the licence. The same files always give a byte-identical zip.
"""
from __future__ import annotations

import argparse
import hashlib
import re
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ZIP_ROOT = "shadow-reader"
FIXED_ZIP_TIME = (2026, 1, 1, 0, 0, 0)

# (path in the zip, source file in the repository, is it executable)
FILES = [
    ("LICENSE", "LICENSE", False),
    ("README.md", "linux/README.md", False),
    ("assets/shadow-reader-logo.png", "assets/shadow-reader-logo.png", False),
    ("index.html", "index.html", False),
    ("run.sh", "run.sh", True),
    ("server.py", "server.py", False),
]


def app_version() -> str:
    match = re.search(r'ShadowReader/(\d+\.\d+\.\d+)', (ROOT / "server.py").read_text(encoding="utf-8"))
    if not match:
        raise SystemExit("could not read the version from server.py")
    return match.group(1)


def build(out: Path) -> str:
    entries = {}
    for name, source, executable in FILES:
        path = ROOT / source
        if not path.is_file():
            raise SystemExit(f"missing file: {source}")
        data = path.read_bytes()
        if name.endswith((".sh", ".py", ".md", ".html")) and b"\r\n" in data:
            raise SystemExit(f"{source} has Windows line endings; the Linux zip needs LF")
        entries[name] = (data, executable)

    out.parent.mkdir(parents=True, exist_ok=True)
    names = sorted(entries)
    folders = sorted({str(Path(n).parent) for n in names if "/" in n})
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as archive:
        for folder in [""] + folders:
            info = zipfile.ZipInfo(f"{ZIP_ROOT}/{folder}/" if folder else f"{ZIP_ROOT}/", FIXED_ZIP_TIME)
            info.external_attr = (0o40755 << 16) | 0x10
            archive.writestr(info, b"")
        for name in names:
            data, executable = entries[name]
            info = zipfile.ZipInfo(f"{ZIP_ROOT}/{name}", FIXED_ZIP_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = (0o100755 if executable else 0o100644) << 16
            archive.writestr(info, data)
    return hashlib.sha256(out.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()
    out = args.out or ROOT / "dist" / f"Shadow-Reader-{app_version()}-linux.zip"
    digest = build(out)
    print(f"Wrote {out}")
    print(f"SHA-256: {digest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
