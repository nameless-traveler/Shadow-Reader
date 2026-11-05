#!/usr/bin/env python3
"""Starting Shadow Reader when its port is taken must fail with a clear message, and a normal start
must stop cleanly. Runs on Linux, macOS and Windows (the Ctrl+C check is skipped on Windows)."""
from __future__ import annotations

import os
import signal
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def start(port: int, **kwargs) -> subprocess.Popen:
    env = dict(os.environ, SHADOW_READER_PORT=str(port), BROWSER="true")
    return subprocess.Popen([sys.executable, str(ROOT / "server.py")], cwd=ROOT, env=env, stdin=subprocess.DEVNULL,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, **kwargs)


def wait_healthy(port: int, process: subprocess.Popen) -> bool:
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline and process.poll() is None:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health", timeout=2) as response:
                return response.status == 200
        except OSError:
            time.sleep(0.2)
    return False


def main() -> int:
    results: list[tuple[str, bool]] = []

    # 1. Some other program already listens on the port.
    port = free_port()
    with socket.socket() as blocker:
        blocker.bind(("127.0.0.1", port))
        blocker.listen()
        process = start(port)
        try:
            output, _ = process.communicate(timeout=20)
        except subprocess.TimeoutExpired:
            process.kill()
            output, _ = process.communicate()
            output = "(still running after 20 s)\n" + output
    results.append(("port taken by another program: exits with an error instead of starting", process.returncode == 1))
    results.append(("port taken: the message names the port and the SHADOW_READER_PORT setting",
                    f"Port {port} is already in use" in output and "SHADOW_READER_PORT" in output and "Traceback" not in output))

    # 2. A second Shadow Reader while the first is running; the first must be left alone.
    port = free_port()
    first = start(port)
    try:
        up = wait_healthy(port, first)
        results.append(("first instance starts", up))
        second = start(port)
        try:
            output, _ = second.communicate(timeout=20)
        except subprocess.TimeoutExpired:
            second.kill()
            output, _ = second.communicate()
        results.append(("second instance on the same port exits with the clear message",
                        second.returncode == 1 and "already in use" in output))
        results.append(("first instance still answers after the second one failed", up and wait_healthy(port, first)))
    finally:
        first.kill()
        first.communicate()

    # 3. Ctrl+C stops the server cleanly and frees the port (POSIX; Windows has no portable way to send it).
    if os.name != "nt":
        port = free_port()
        process = start(port)
        up = wait_healthy(port, process)
        process.send_signal(signal.SIGINT)
        try:
            output, _ = process.communicate(timeout=20)
        except subprocess.TimeoutExpired:
            process.kill()
            output, _ = process.communicate()
        results.append(("Ctrl+C: stops cleanly with a goodbye message", up and process.returncode == 0 and "Shadow Reader stopped." in output))
        with socket.socket() as probe:
            results.append(("Ctrl+C: the port is free again", probe.connect_ex(("127.0.0.1", port)) != 0))

    failed = False
    for name, ok in results:
        print(("PASS: " if ok else "FAIL: ") + name)
        failed = failed or not ok
    if failed:
        return 1
    print(f"PASS: {len(results)} port and shutdown checks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
