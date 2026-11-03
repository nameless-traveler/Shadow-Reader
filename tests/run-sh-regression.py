#!/usr/bin/env python3
"""Tests run.sh's package-manager detection without installing anything.

Each case builds a throwaway PATH that holds only fake commands (a fake apt-get,
dnf, pacman, ... that just log what they were asked to do). run.sh therefore
"sees" a system with exactly the tools we choose, and we check which package it
asks for and how. The interactive prompt is tested through a real pseudo-terminal.
Runs under every POSIX shell found on the machine (dash, bash, busybox ash).
"""
from __future__ import annotations

import os
import pty
import select
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUN_SH = ROOT / "run.sh"

# package manager -> (binary on PATH, expected install lines for poppler)
POPPLER_CASES = {
    "apt-get": ["apt-get update", "apt-get install -y poppler-utils"],
    "dnf": ["dnf install -y poppler-utils"],
    "yum": ["yum install -y poppler-utils"],
    "pacman": ["pacman -S --needed --noconfirm poppler"],
    "zypper": ["zypper --non-interactive install poppler-tools"],
    "apk": ["apk add --no-cache poppler-utils"],
    "xbps-install": ["xbps-install -Sy poppler"],
    "emerge": ["emerge --ask=n app-text/poppler"],
}
# Python is missing as well: both packages are requested in one command.
PYTHON_CASES = {
    "apt-get": "apt-get install -y python3 poppler-utils",
    "dnf": "dnf install -y python3 poppler-utils",
    "pacman": "pacman -S --needed --noconfirm python poppler",
    "zypper": "zypper --non-interactive install python3 poppler-tools",
    "apk": "apk add --no-cache python3 poppler-utils",
    "xbps-install": "xbps-install -Sy python3 poppler",
    "emerge": "emerge --ask=n dev-lang/python app-text/poppler",
}


def find_shells() -> list[list[str]]:
    shells = []
    for name in ("dash", "bash"):
        path = shutil.which(name)
        if path:
            shells.append([path])
    busybox = shutil.which("busybox")
    if busybox:
        shells.append([busybox, "sh"])
    return shells


class Sandbox:
    """A temp dir holding run.sh, a fake PATH, and a log of every fake command run."""

    def __init__(self, tools: list[str], uid: str = "1000", with_python: bool = True,
                 with_pdftotext: bool = False):
        self.dir = Path(tempfile.mkdtemp(prefix="run-sh-test-"))
        self.bin = self.dir / "bin"
        self.bin.mkdir()
        self.log = self.dir / "log.txt"
        self.log.write_text("")
        # So an unprivileged child (see drop_privileges) can write the log and "install" stubs.
        self.dir.chmod(0o755)
        self.bin.chmod(0o777)
        self.log.chmod(0o666)
        shutil.copy(RUN_SH, self.dir / "run.sh")
        self.uid = uid
        # Real helpers run.sh needs; everything else on the machine is hidden.
        for helper in ("dirname", "chmod"):
            os.symlink(shutil.which(helper), self.bin / helper)
        self._stub("id", f'echo "{uid}"', log=False)
        if with_python:
            self._stub("python3", 'echo "PYTHON-STARTED $*"', log=False)
        for tool in tools:
            self._stub(tool, self._tool_body(tool))
        if with_pdftotext:
            self._stub("pdftotext", "exit 0", log=False)

    def _stub(self, name: str, body: str, log: bool = True) -> None:
        lines = ["#!/bin/sh"]
        if log:
            lines.append(f'echo "{name} $*" >> "{self.log}"')
        lines.append(body)
        path = self.bin / name
        path.write_text("\n".join(lines) + "\n")
        path.chmod(0o755)

    def _tool_body(self, tool: str) -> str:
        if tool in ("sudo", "doas"):
            return 'exec "$@"'
        # A package manager: pretend that installing poppler/python worked.
        return (
            f'case "$*" in *poppler*) printf "#!/bin/sh\\nexit 0\\n" > "{self.bin}/pdftotext"; '
            f'chmod +x "{self.bin}/pdftotext";; esac\n'
            f'case "$*" in *python*) printf "#!/bin/sh\\necho PYTHON-STARTED \\"\\$*\\"\\n" > "{self.bin}/python3"; '
            f'chmod +x "{self.bin}/python3";; esac'
        )

    def env(self) -> dict[str, str]:
        return {"PATH": str(self.bin), "HOME": str(self.dir)}

    def logged(self) -> list[str]:
        return [line.strip() for line in self.log.read_text().splitlines() if line.strip()]

    def cleanup(self) -> None:
        shutil.rmtree(self.dir, ignore_errors=True)


def drop_privileges(box: Sandbox) -> None:
    """busybox ash runs its own built-in `id`, ignoring our fake one, so for a "normal
    user" case under busybox we really become an unprivileged user (when we are root)."""
    if box.uid != "0" and os.getuid() == 0:
        os.setgid(65534)
        os.setuid(65534)


def run_plain(shell: list[str], box: Sandbox, extra_env: dict[str, str] | None = None) -> tuple[int, str]:
    """Run run.sh with no terminal attached (stdin is /dev/null)."""
    result = subprocess.run(
        shell + [str(box.dir / "run.sh")], env={**box.env(), **(extra_env or {})}, stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=30,
        preexec_fn=lambda: drop_privileges(box),
    )
    return result.returncode, result.stdout


def run_tty(shell: list[str], box: Sandbox, answer: str) -> tuple[int, str]:
    """Run run.sh inside a pseudo-terminal and type `answer` at the prompt."""
    pid, fd = pty.fork()
    if pid == 0:
        drop_privileges(box)
        os.execve(shell[0], shell + [str(box.dir / "run.sh")], box.env())
    output = b""
    sent = False
    while True:
        ready, _, _ = select.select([fd], [], [], 15)
        if not ready:
            os.kill(pid, 9)
            break
        try:
            chunk = os.read(fd, 4096)
        except OSError:
            break
        if not chunk:
            break
        output += chunk
        if not sent and b"[y/N]" in output:
            os.write(fd, (answer + "\n").encode())
            sent = True
    _, status = os.waitpid(pid, 0)
    return os.waitstatus_to_exitcode(status), output.decode("utf-8", "replace").replace("\r", "")


def main() -> int:
    shells = find_shells()
    if not shells:
        print("FAIL: no POSIX shell found to test run.sh with")
        return 1

    results: list[tuple[str, bool]] = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        results.append((name, ok))
        if not ok and detail:
            print(f"--- detail for failed check: {name}\n{detail}\n---")

    for shell in shells:
        label = Path(shell[0]).name + (" sh" if len(shell) > 1 else "")

        # Everything is already installed: no prompt, nothing installed, server starts.
        box = Sandbox(["apt-get"], with_pdftotext=True)
        code, out = run_plain(shell, box)
        check(f"[{label}] nothing missing: starts server, installs nothing",
              code == 0 and "PYTHON-STARTED server.py" in out and box.logged() == [], out)
        box.cleanup()

        # Each package manager: sudo user answers y at the prompt.
        for pm, expected in POPPLER_CASES.items():
            box = Sandbox([pm, "sudo"])
            code, out = run_tty(shell, box, "y")
            commands = [line for line in box.logged() if line.startswith(pm)]
            via_sudo = [line for line in box.logged() if line.startswith("sudo")]
            check(f"[{label}] {pm}: installs the right Poppler package and starts",
                  commands == expected and "PYTHON-STARTED server.py" in out and code == 0,
                  f"expected {expected}, got {commands}\n{out}")
            check(f"[{label}] {pm}: runs the installer through sudo as a normal user",
                  len(via_sudo) == len(expected), str(box.logged()))
            box.cleanup()

        # Answering no: nothing is installed, server still starts for .txt files.
        box = Sandbox(["pacman", "sudo"])
        code, out = run_tty(shell, box, "n")
        check(f"[{label}] answering no installs nothing and still starts",
              all(not line.startswith("pacman") for line in box.logged())
              and "PYTHON-STARTED server.py" in out and "Continuing without PDF import" in out and code == 0, out)
        box.cleanup()

        # Root: no sudo prefix is used. (busybox reads the real uid, so it needs a real root.)
        if os.getuid() == 0 or len(shell) == 1:
            box = Sandbox(["apk"], uid="0")
            code, out = run_tty(shell, box, "y")
            check(f"[{label}] root runs the installer directly",
                  box.logged() == ["apk add --no-cache poppler-utils"] and code == 0, f"{box.logged()}\n{out}")
            box.cleanup()

        # doas instead of sudo (common on Alpine/Void).
        box = Sandbox(["xbps-install", "doas"])
        code, out = run_tty(shell, box, "y")
        check(f"[{label}] doas is used when sudo is absent",
              box.logged() == ["doas xbps-install -Sy poppler", "xbps-install -Sy poppler"] and code == 0,
              f"{box.logged()}\n{out}")
        box.cleanup()

        # No privilege tool at all: print the command, run nothing, still start.
        box = Sandbox(["dnf"])
        code, out = run_plain(shell, box)
        check(f"[{label}] no sudo/doas: prints the command, installs nothing, still starts",
              all(not line.startswith("dnf") for line in box.logged())
              and "dnf install -y poppler-utils" in out and "PYTHON-STARTED server.py" in out and code == 0, out)
        box.cleanup()

        # No terminal (cron, pipe, CI): never blocks on a prompt, never installs.
        box = Sandbox(["apt-get", "sudo"])
        code, out = run_plain(shell, box)
        check(f"[{label}] without a terminal it does not prompt or install",
              box.logged() == [] and "not an interactive terminal" in out
              and "PYTHON-STARTED server.py" in out and code == 0, out)
        box.cleanup()

        # SHADOW_READER_ASSUME_YES (used by the container tests): installs with no terminal and no question.
        box = Sandbox(["apk", "sudo"])
        code, out = run_plain(shell, box, {"SHADOW_READER_ASSUME_YES": "1"})
        check(f"[{label}] SHADOW_READER_ASSUME_YES installs without a terminal or a prompt",
              [line for line in box.logged() if line.startswith("apk")] == ["apk add --no-cache poppler-utils"]
              and "[y/N]" not in out and "PYTHON-STARTED server.py" in out and code == 0, f"{box.logged()}\n{out}")
        box.cleanup()

        # Unknown package manager: helpful message, still starts.
        box = Sandbox([])
        code, out = run_plain(shell, box)
        check(f"[{label}] unknown package manager: explains what to install, still starts",
              "could not recognise" in out and "pdftotext" in out
              and "PYTHON-STARTED server.py" in out and code == 0, out)
        box.cleanup()

        # Python missing too: both packages requested in one command.
        for pm, line in PYTHON_CASES.items():
            box = Sandbox([pm, "sudo"], with_python=False)
            code, out = run_tty(shell, box, "y")
            commands = [entry for entry in box.logged() if entry.startswith(pm)]
            check(f"[{label}] {pm}: Python and Poppler requested together",
                  line in commands and "PYTHON-STARTED server.py" in out and code == 0,
                  f"expected {line}\n{box.logged()}\n{out}")
            box.cleanup()

        # Python missing and declined: exits with a clear message, does not crash.
        box = Sandbox(["apt-get", "sudo"], with_python=False, with_pdftotext=True)
        code, out = run_tty(shell, box, "n")
        check(f"[{label}] Python missing and declined: stops with a clear message",
              code == 1 and "Python 3 is still missing" in out and "PYTHON-STARTED" not in out, out)
        box.cleanup()

    failed = False
    for name, ok in results:
        print(("PASS: " if ok else "FAIL: ") + name)
        failed = failed or not ok
    if failed:
        return 1
    print(f"PASS: {len(results)} run.sh checks across {len(shells)} shell(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
