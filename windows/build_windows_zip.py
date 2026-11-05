#!/usr/bin/env python3
"""Builds the Windows download of Shadow Reader (Shadow-Reader-windows.zip).

The zip is portable: extract it and double-click Shadow-Reader.bat. It contains

  * the app (index.html, server.py, the logo, LICENSE),
  * the official embeddable Python from python.org (so nothing has to be installed),
  * Poppler's pdftotext.exe plus only the DLLs it really needs, taken from the prebuilt
    "poppler-windows" release (built from conda-forge), with Poppler's licence files and a notice.

Usage (any OS; the Windows CI job runs it on Windows):

    python windows/build_windows_zip.py                       # downloads Python and Poppler, writes dist/Shadow-Reader-windows.zip
    python windows/build_windows_zip.py --poppler-zip P.zip --python-embed E.zip --out out.zip   # use local files

Needs the `pefile` package (pip install pefile) to work out which DLLs pdftotext.exe needs.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import re
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Set

ROOT = Path(__file__).resolve().parents[1]

# --- Poppler for Windows: a pinned release, checked by SHA-256 --------------------------------------
POPPLER_VERSION = "26.09.0"
POPPLER_BUILD = "0"
POPPLER_URL = (
    "https://github.com/oschwartz10612/poppler-windows/releases/download/"
    f"v{POPPLER_VERSION}-{POPPLER_BUILD}/Release-{POPPLER_VERSION}-{POPPLER_BUILD}.zip"
)
POPPLER_SHA256 = "7a6f256a0ddf7536182246a5733331bf4677cbcc34f4663774947ad34556c8d0"
POPPLER_SOURCE_URL = f"https://poppler.freedesktop.org/poppler-{POPPLER_VERSION}.tar.xz"
POPPLER_BINARY_ORIGIN = "https://github.com/oschwartz10612/poppler-windows"
POPPLER_RECIPE_URL = "https://github.com/conda-forge/poppler-feedstock"

# --- Python: the embeddable package of the same version as the interpreter running this script -------
# The download is checked against the hash pinned here. For a new Python version the hash is printed
# during the build ("is not pinned. SHA-256 = ..."); compare it with python.org, then add it below.
# The version in windows-zip.yml must be one of these (tests/windows-package-regression.py checks that).
PYTHON_EMBED_SHA256: Dict[str, str] = {
    "3.13.17": "9e35319bffedab8b36ad44d8f377cb4f1733bcec257a0b6d04d94f01486ddb38",
}

ZIP_ROOT = "shadow-reader"
FIXED_ZIP_TIME = (2026, 1, 1, 0, 0, 0)  # same input -> byte-identical zip

APP_FILES = ["index.html", "server.py", "LICENSE"]
APP_ASSETS = ["assets/shadow-reader-logo.png"]


class BuildError(Exception):
    pass


# ----------------------------------------------------------------------------- helpers
def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def verify_sha256(path: Path, expected: Optional[str], label: str) -> None:
    actual = sha256_of(path)
    if expected is None:
        print(f"  note: {label} is not pinned. SHA-256 = {actual}  (put it in the build script to pin it)")
        return
    if actual.lower() != expected.lower():
        raise BuildError(f"{label} does not match its pinned SHA-256.\n  expected {expected}\n  actual   {actual}")


def download(url: str, dest: Path) -> None:
    print(f"  downloading {url}")
    request = urllib.request.Request(url, headers={"User-Agent": "Shadow-Reader-build"})
    with urllib.request.urlopen(request, timeout=120) as response, open(dest, "wb") as out:
        while True:
            block = response.read(1024 * 1024)
            if not block:
                break
            out.write(block)


def app_version() -> str:
    text = (ROOT / "server.py").read_text(encoding="utf-8")
    match = re.search(r"ShadowReader/(\d+\.\d+\.\d+)", text)
    if not match:
        raise BuildError("Could not read the version from server.py (expected ShadowReader/x.y.z).")
    return match.group(1)


def to_crlf(data: bytes) -> bytes:
    return data.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")


# ----------------------------------------------------------------------------- DLL closure
def read_imports(path: Path) -> List[str]:
    """Names of the DLLs a Windows program or DLL imports (needs the pefile package)."""
    try:
        import pefile
    except ImportError as exc:  # pragma: no cover - environment problem, not logic
        raise BuildError("The pefile package is needed: pip install pefile") from exc
    pe = pefile.PE(str(path), fast_load=True)
    try:
        pe.parse_data_directories(directories=[
            pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_IMPORT"],
            pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_DELAY_IMPORT"],
        ])
        names = []
        for attribute in ("DIRECTORY_ENTRY_IMPORT", "DIRECTORY_ENTRY_DELAY_IMPORT"):
            for entry in getattr(pe, attribute, []):
                names.append(entry.dll.decode("ascii", "replace"))
        return names
    finally:
        pe.close()


def dll_closure(start: str, available: Iterable[str], imports_of: Callable[[str], Iterable[str]]) -> List[str]:
    """Every DLL (by its real file name) that `start` needs, directly or through other bundled DLLs.

    `available` are the DLL files that ship with Poppler; anything not in it (kernel32.dll and other Windows
    system libraries) is ignored. Names are compared without regard to case, as Windows does.
    """
    by_lower = {name.lower(): name for name in available}
    needed: Dict[str, str] = {}
    pending = [start]
    while pending:
        current = pending.pop()
        for imported in imports_of(current):
            key = imported.lower()
            if key in by_lower and key not in needed:
                needed[key] = by_lower[key]
                pending.append(by_lower[key])
    return sorted(needed.values(), key=str.lower)


# ----------------------------------------------------------------------------- notices
def notices_text(version: str, python_version: str, dlls: List[str]) -> str:
    dll_lines = "\n".join(f"  - {name}" for name in dlls)
    return f"""Shadow Reader {version} for Windows - third-party notices
=====================================================

Shadow Reader itself is released under the Apache License 2.0 (see LICENSE).

This download also contains software written by others. It is not part of Shadow Reader's own code,
and each piece stays under its own licence.

Poppler {POPPLER_VERSION} (pdftotext.exe), in the "poppler" folder
------------------------------------------------------------------
Poppler is free software licensed under the GNU General Public License, version 2 or (at your option) any
later version. The licence texts are in poppler/licenses/ (COPYING, COPYING.gpl2, COPYING.adobe).

Shadow Reader runs pdftotext.exe as a separate program to read PDF text. Shadow Reader's code is not linked
with Poppler.

Source code for this exact Poppler version: {POPPLER_SOURCE_URL}
These Windows binaries come from: {POPPLER_BINARY_ORIGIN} (a repackaging of the conda-forge build)
Build recipe used by conda-forge: {POPPLER_RECIPE_URL}

Libraries pdftotext.exe needs (all in poppler/bin, each under its own licence; their source and licences are
available from the conda-forge feedstocks and the upstream projects):
{dll_lines}

Python {python_version}, in the "python" folder
-------------------------------------------------
The official embeddable Python package from python.org, under the Python Software Foundation License
(python/LICENSE.txt).
"""


# ----------------------------------------------------------------------------- build
def build(poppler_zip: Path, python_embed_zip: Path, out_zip: Path, python_version: str,
          imports_of_file: Optional[Callable[[Path], Iterable[str]]] = None) -> List[str]:
    """Assemble the Windows zip. Returns the list of bundled DLL names."""
    imports_of_file = imports_of_file or read_imports
    version = app_version()

    with tempfile.TemporaryDirectory(prefix="shadow-reader-build-") as temp:
        stage = Path(temp) / ZIP_ROOT
        stage.mkdir(parents=True)

        # 1. the app itself
        for name in APP_FILES + APP_ASSETS:
            source = ROOT / name
            if not source.is_file():
                raise BuildError(f"App file missing: {name}")
            target = stage / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(source.read_bytes())

        # 2. launcher and user-facing text (Windows text files must use CRLF line endings)
        for name, target in (("Shadow-Reader.bat", "Shadow-Reader.bat"), ("README.txt", "README.txt")):
            source = ROOT / "windows" / name
            if not source.is_file():
                raise BuildError(f"windows/{name} is missing")
            (stage / target).write_bytes(to_crlf(source.read_bytes()))

        # 3. Poppler: pdftotext.exe and only the DLLs it needs
        poppler_bin = stage / "poppler" / "bin"
        licences = stage / "poppler" / "licenses"
        poppler_bin.mkdir(parents=True)
        licences.mkdir(parents=True)
        with zipfile.ZipFile(poppler_zip) as archive:
            names = archive.namelist()
            exe_member = next((n for n in names if n.endswith("Library/bin/pdftotext.exe")), None)
            if exe_member is None:
                raise BuildError("pdftotext.exe was not found in the Poppler zip (expected Library/bin/pdftotext.exe).")
            prefix = exe_member[: -len("Library/bin/pdftotext.exe")]
            bin_members = {
                Path(n).name: n for n in names
                if n.startswith(prefix + "Library/bin/") and not n.endswith("/") and Path(n).name.lower().endswith(".dll")
            }
            scratch = Path(temp) / "poppler-scan"
            scratch.mkdir()
            (scratch / "pdftotext.exe").write_bytes(archive.read(exe_member))
            for name, member in bin_members.items():
                (scratch / name).write_bytes(archive.read(member))

            dlls = dll_closure("pdftotext.exe", bin_members.keys(), lambda n: imports_of_file(scratch / n))

            (poppler_bin / "pdftotext.exe").write_bytes((scratch / "pdftotext.exe").read_bytes())
            for name in dlls:
                (poppler_bin / name).write_bytes((scratch / name).read_bytes())

            found_licence = False
            for member in names:
                base = Path(member).name
                if member.startswith(prefix + "share/poppler/") and base in ("COPYING", "COPYING.gpl2", "COPYING.adobe"):
                    (licences / base).write_bytes(archive.read(member))
                    found_licence = True
            if not found_licence:
                raise BuildError("Poppler's licence files (COPYING) were not found in the Poppler zip.")

        (stage / "THIRD-PARTY-NOTICES.txt").write_bytes(
            to_crlf(notices_text(version, python_version, dlls).encode("utf-8")))

        # 4. Python (the embeddable package, extracted as it is)
        python_dir = stage / "python"
        with zipfile.ZipFile(python_embed_zip) as archive:
            if "python.exe" not in archive.namelist():
                raise BuildError("python.exe was not found at the top of the Python embeddable zip.")
            archive.extractall(python_dir)

        (stage / "VERSION.txt").write_bytes(to_crlf(
            f"Shadow Reader {version}\nPython {python_version} (embeddable)\n"
            f"Poppler {POPPLER_VERSION} (build {POPPLER_BUILD})\n".encode("utf-8")))

        # 5. write the zip: sorted, fixed timestamps, so the same input always gives the same bytes
        out_zip.parent.mkdir(parents=True, exist_ok=True)
        files = sorted(p for p in stage.rglob("*") if p.is_file())
        with zipfile.ZipFile(out_zip, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as out:
            for path in files:
                info = zipfile.ZipInfo(f"{ZIP_ROOT}/{path.relative_to(stage).as_posix()}", FIXED_ZIP_TIME)
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o644 << 16
                out.writestr(info, path.read_bytes())
    return dlls


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", default=str(ROOT / "dist" / "Shadow-Reader-windows.zip"))
    parser.add_argument("--poppler-zip", help="use this Poppler zip instead of downloading it")
    parser.add_argument("--python-embed", help="use this Python embeddable zip instead of downloading it")
    parser.add_argument("--python-version", default="{}.{}.{}".format(*sys.version_info[:3]),
                        help="Python version to bundle (default: the version running this script)")
    args = parser.parse_args(argv)

    try:
        with tempfile.TemporaryDirectory(prefix="shadow-reader-dl-") as temp:
            temp_dir = Path(temp)
            print("Poppler for Windows")
            poppler_zip = Path(args.poppler_zip) if args.poppler_zip else temp_dir / "poppler.zip"
            if not args.poppler_zip:
                download(POPPLER_URL, poppler_zip)
            verify_sha256(poppler_zip, POPPLER_SHA256, "Poppler zip")

            print("Python embeddable package")
            embed_zip = Path(args.python_embed) if args.python_embed else temp_dir / "python-embed.zip"
            if not args.python_embed:
                download(f"https://www.python.org/ftp/python/{args.python_version}/"
                         f"python-{args.python_version}-embed-amd64.zip", embed_zip)
            verify_sha256(embed_zip, PYTHON_EMBED_SHA256.get(args.python_version), f"Python {args.python_version} embed zip")

            print("Building")
            out_zip = Path(args.out)
            dlls = build(poppler_zip, embed_zip, out_zip, args.python_version)
    except BuildError as exc:
        print(f"BUILD FAILED: {exc}")
        return 1

    size = out_zip.stat().st_size
    print(f"Done: {out_zip} ({size / 1e6:.1f} MB), {len(dlls)} Poppler DLLs bundled")
    print(f"SHA-256: {sha256_of(out_zip)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
