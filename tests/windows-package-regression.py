#!/usr/bin/env python3
"""Checks the logic that builds the Windows zip, using small fake Poppler and Python zips.

No Windows machine and no download is needed, so this runs everywhere. The real build and a real run of the
finished zip happen in the "Build Windows ZIP" workflow (windows/build_windows_zip.py, windows/smoke_test_zip.py).
"""
from __future__ import annotations

import importlib.util
import re
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("build_windows_zip", ROOT / "windows" / "build_windows_zip.py")
bw = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bw)

FAKE_IMPORTS = {
    "pdftotext.exe": ["poppler.dll", "KERNEL32.dll", "ZLIB.DLL"],
    "poppler.dll": ["freetype.dll", "zlib.dll", "ws2_32.dll"],
    "freetype.dll": ["poppler.dll", "libpng16.dll"],  # a cycle on purpose
    "libpng16.dll": [],
    "zlib.dll": [],
    "unused.dll": ["libpng16.dll"],
}


def make_poppler_zip(path: Path, with_exe: bool = True, with_licence: bool = True) -> None:
    prefix = "poppler-9.9.9/"
    with zipfile.ZipFile(path, "w") as z:
        if with_exe:
            z.writestr(prefix + "Library/bin/pdftotext.exe", b"MZ exe")
        for name in ("poppler.dll", "freetype.dll", "libpng16.dll", "zlib.dll", "unused.dll"):
            z.writestr(prefix + "Library/bin/" + name, b"MZ " + name.encode())
        z.writestr(prefix + "Library/bin/pdftoppm.exe", b"MZ other tool")
        if with_licence:
            for name in ("COPYING", "COPYING.gpl2", "COPYING.adobe"):
                z.writestr(prefix + "share/poppler/" + name, b"licence " + name.encode())
        z.writestr(prefix + "share/poppler/cMap/big.bin", b"x" * 100)


def make_python_zip(path: Path) -> None:
    with zipfile.ZipFile(path, "w") as z:
        for name in ("python.exe", "python313.dll", "python313.zip", "python313._pth", "LICENSE.txt"):
            z.writestr(name, b"fake " + name.encode())


def fake_imports_of(path: Path):
    return FAKE_IMPORTS.get(path.name.lower(), [])


def main() -> int:
    results: list[tuple[str, bool]] = []

    # --- DLL closure
    closure = bw.dll_closure("pdftotext.exe", ["poppler.dll", "freetype.dll", "libpng16.dll", "zlib.dll", "unused.dll"],
                             lambda n: FAKE_IMPORTS[n.lower()])
    results.append(("closure follows imports through other bundled DLLs",
                    closure == ["freetype.dll", "libpng16.dll", "poppler.dll", "zlib.dll"]))
    results.append(("closure ignores Windows system DLLs and DLLs nobody needs",
                    "unused.dll" not in closure and not any("kernel32" in n.lower() for n in closure)))
    results.append(("closure matches names without regard to case and survives import cycles",
                    "zlib.dll" in closure and len(closure) == len(set(closure))))

    with tempfile.TemporaryDirectory(prefix="shadow-reader-pkg-test-") as temp:
        temp_dir = Path(temp)
        poppler = temp_dir / "poppler.zip"
        python = temp_dir / "python.zip"
        make_poppler_zip(poppler)
        make_python_zip(python)

        out1 = temp_dir / "one.zip"
        out2 = temp_dir / "two.zip"
        dlls = bw.build(poppler, python, out1, "3.13.9", fake_imports_of)
        bw.build(poppler, python, out2, "3.13.9", fake_imports_of)
        with zipfile.ZipFile(out1) as opened:
            names = set(opened.namelist())
        p = bw.ZIP_ROOT + "/"

        results.append(("build bundles exactly the DLLs pdftotext needs", dlls == closure))
        results.append(("zip has the app files and the logo",
                        {p + "index.html", p + "server.py", p + "LICENSE", p + "assets/shadow-reader-logo.png"} <= names))
        results.append(("zip has the launcher, README, version and notices",
                        {p + "Shadow-Reader.bat", p + "README.txt", p + "VERSION.txt", p + "THIRD-PARTY-NOTICES.txt"} <= names))
        results.append(("zip has pdftotext.exe and only the needed DLLs in poppler/bin",
                        p + "poppler/bin/pdftotext.exe" in names and p + "poppler/bin/poppler.dll" in names
                        and p + "poppler/bin/unused.dll" not in names and p + "poppler/bin/pdftoppm.exe" not in names))
        results.append(("zip has Poppler's licence files",
                        all(p + "poppler/licenses/" + n in names for n in ("COPYING", "COPYING.gpl2", "COPYING.adobe"))))
        results.append(("zip has the bundled Python with its licence",
                        p + "python/python.exe" in names and p + "python/LICENSE.txt" in names))
        results.append(("zip has no tests, build scripts, git files or caches",
                        not any(("/tests/" in n or "/windows/" in n or ".git" in n or "__pycache__" in n or n.endswith(".pyc")) for n in names)))

        with zipfile.ZipFile(out1) as archive:
            bat = archive.read(p + "Shadow-Reader.bat")
            notice = archive.read(p + "THIRD-PARTY-NOTICES.txt").decode("utf-8")
        results.append(("launcher uses Windows (CRLF) line endings", b"\r\n" in bat and b"\n" not in bat.replace(b"\r\n", b"")))
        results.append(("notices name Poppler's licence, its source and every bundled library",
                        "GNU General Public License" in notice and bw.POPPLER_SOURCE_URL in notice
                        and all(name in notice for name in dlls)))
        results.append(("same input gives a byte-identical zip", out1.read_bytes() == out2.read_bytes()))

        # --- error handling
        bad = temp_dir / "bad.zip"
        make_poppler_zip(bad, with_exe=False)
        try:
            bw.build(bad, python, temp_dir / "x.zip", "3.13.9", fake_imports_of)
            results.append(("a Poppler zip without pdftotext.exe is rejected", False))
        except bw.BuildError as exc:
            results.append(("a Poppler zip without pdftotext.exe is rejected", "pdftotext.exe" in str(exc)))

        no_licence = temp_dir / "nolicence.zip"
        make_poppler_zip(no_licence, with_licence=False)
        try:
            bw.build(no_licence, python, temp_dir / "y.zip", "3.13.9", fake_imports_of)
            results.append(("a Poppler zip without licence files is rejected", False))
        except bw.BuildError as exc:
            results.append(("a Poppler zip without licence files is rejected", "licence" in str(exc)))

        try:
            bw.verify_sha256(poppler, "0" * 64, "test file")
            results.append(("a wrong SHA-256 stops the build", False))
        except bw.BuildError:
            results.append(("a wrong SHA-256 stops the build", True))
        bw.verify_sha256(poppler, bw.sha256_of(poppler), "test file")
        results.append(("the right SHA-256 is accepted", True))

    # The Python version the release workflow builds with must have a pinned SHA-256.
    workflow = (ROOT / ".github" / "workflows" / "windows-zip.yml").read_text(encoding="utf-8")
    match = re.search(r'python-version:\s*"?(\d+\.\d+\.\d+)"?', workflow)
    results.append(("windows-zip.yml builds with an exact Python version", match is not None))
    results.append(("that Python version has a pinned SHA-256 in the build script",
                    bool(match) and re.fullmatch(r"[0-9a-f]{64}", bw.PYTHON_EMBED_SHA256.get(match.group(1), "")) is not None))

    version = bw.app_version()
    results.append(("version is read from server.py", version.count(".") == 2 and version.replace(".", "").isdigit()))

    failed = False
    for name, ok in results:
        print(("PASS: " if ok else "FAIL: ") + name)
        failed = failed or not ok
    if failed:
        return 1
    print(f"PASS: {len(results)} Windows packaging checks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
