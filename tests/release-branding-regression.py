#!/usr/bin/env python3
"""Release checks for Shadow Reader branding and non-destructive storage compatibility."""
from __future__ import annotations
import os
import subprocess
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
index = (ROOT / "index.html").read_text(encoding="utf-8")
server = (ROOT / "server.py").read_text(encoding="utf-8")
readme = (ROOT / "README.md").read_text(encoding="utf-8")
checks = []
checks.append(("document title uses Shadow Reader", "<title>Shadow Reader — local novel reader</title>" in index))
checks.append(("visible brand uses Shadow Reader", 'class="brand-name">Shadow Reader</div>' in index))
checks.append(("no old product name remains in app UI", "Quiet Reader" not in index and "Quiet reader" not in index))
checks.append(("progress storage key preserved for existing saves", "'quietReaderProgressV1'" in index))
checks.append(("preferences storage key preserved", "'quietReaderPrefs'" in index))
checks.append(("new port variable documented", "SHADOW_READER_PORT=8766 ./run.sh" in readme))
checks.append(("legacy port variable documented", "QUIET_READER_PORT" in readme))
checks.append(("new port variable has precedence", 'os.environ.get("SHADOW_READER_PORT", os.environ.get("QUIET_READER_PORT", "8765"))' in server))
# Verify import-time configuration in isolated interpreters without opening a socket.
for var, value, expected in [("SHADOW_READER_PORT", "8766", "8766"), ("QUIET_READER_PORT", "8767", "8767")]:
    env = os.environ.copy()
    env.pop("SHADOW_READER_PORT", None); env.pop("QUIET_READER_PORT", None)
    env[var] = value
    proc = subprocess.run([sys.executable, "-c", "import server; print(server.PORT)"], cwd=ROOT, env=env, capture_output=True, text=True)
    checks.append((f"{var} configures the requested port", proc.returncode == 0 and proc.stdout.strip().endswith(expected)))
failed = [name for name, ok in checks if not ok]
for name, ok in checks:
    print(("PASS" if ok else "FAIL") + ": " + name)
if failed:
    raise SystemExit(1)
print(f"PASS: {len(checks)} release branding/compatibility checks")
