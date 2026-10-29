#!/bin/sh
set -eu
cd "$(dirname "$0")"

if ! command -v pdftotext >/dev/null 2>&1; then
  echo "Shadow Reader needs Poppler's pdftotext command to turn PDF pages into flowing text."
  printf "Install poppler-utils with apt now? [y/N] "
  read answer || answer=""
  case "$answer" in
    y|Y|yes|YES)
      if command -v sudo >/dev/null 2>&1; then
        sudo apt update
        sudo apt install -y poppler-utils
      else
        echo "Please install it manually: apt install poppler-utils (as root)."
        exit 1
      fi
      ;;
    *)
      echo "Continuing without PDF import. Plain-text (.txt) files will still work."
      echo "Install later for PDF support: sudo apt update && sudo apt install poppler-utils"
      ;;
  esac
fi

exec python3 server.py
