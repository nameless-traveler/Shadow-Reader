#!/bin/sh
# Real-install test. Meant to run INSIDE a fresh, minimal Linux container (see the
# "distro-tests" job in .github/workflows/ci.yml). It starts from a system with no
# Poppler (and, on some distributions, no Python), runs ./run.sh the way a user would,
# and checks that the launcher installs what is missing with that distribution's own
# package manager, starts the server, and that a real PDF can be extracted.
#
# Usage (from the repository root, on a machine with Docker):
#   docker run --rm -v "$PWD":/src:ro alpine:latest sh /src/tests/distro-smoke.sh /src
set -eu

SRC=${1:-/src}
PORT=8799
WORK=$(mktemp -d)
cp -R "$SRC/." "$WORK/"
cd "$WORK"

fail() {
  echo "FAIL: $1"
  if [ -f run.log ]; then
    echo "----- run.sh output -----"
    cat run.log
    echo "-------------------------"
  fi
  [ -z "${SERVER_PID:-}" ] || kill "$SERVER_PID" 2>/dev/null || true
  exit 1
}

echo "Distribution:"
head -n 3 /etc/os-release 2>/dev/null || true

if command -v pdftotext >/dev/null 2>&1; then
  fail "this test needs a system WITHOUT Poppler, but pdftotext is already installed"
fi
[ -x ./run.sh ] || fail "run.sh is not executable (git mode 100755 is needed so ./run.sh works)"

# A fresh Arch image has no package databases yet; a real Arch system has them from
# its normal updates. This is test setup, not part of run.sh.
if command -v pacman >/dev/null 2>&1; then
  pacman -Syu --noconfirm >/dev/null 2>&1 || fail "could not prepare the Arch package databases"
fi

# Run the launcher exactly as a user would, answering "yes" to the install question.
SHADOW_READER_ASSUME_YES=1 SHADOW_READER_PORT=$PORT ./run.sh >run.log 2>&1 &
SERVER_PID=$!

ready=""
tries=0
while [ "$tries" -lt 300 ]; do
  status=0
  if command -v python3 >/dev/null 2>&1; then
    # exit 0 = server up with PDF support, 2 = server up but no PDF support, 1 = not reachable yet
    python3 -c "
import sys, urllib.request
try:
    body = urllib.request.urlopen('http://127.0.0.1:$PORT/api/health', timeout=2).read()
except Exception:
    sys.exit(1)
sys.exit(0 if b'\"extractor\": true' in body else 2)
" 2>/dev/null || status=$?
  else
    status=1
  fi
  if [ "$status" -eq 0 ]; then
    ready=1
    break
  fi
  [ "$status" -ne 2 ] || fail "the server is running but reports no PDF support: Poppler was not installed"
  kill -0 "$SERVER_PID" 2>/dev/null || break
  sleep 1
  tries=$((tries + 1))
done

[ -n "$ready" ] || fail "the server did not come up with PDF support after run.sh installed the missing packages"
echo "PASS: run.sh installed what was missing and the server reports PDF support"

grep -q "SHADOW_READER_ASSUME_YES is set" run.log || fail "run.sh did not go through its install path"
echo "PASS: run.sh used its install path"

kill "$SERVER_PID" 2>/dev/null || true
wait "$SERVER_PID" 2>/dev/null || true
SERVER_PID=""

python3 tests/real-pdf-extraction.py || fail "real PDF extraction failed with this distribution's Poppler"
echo "PASS: real PDF extraction works with this distribution's Poppler"
