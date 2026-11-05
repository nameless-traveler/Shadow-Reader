# Shadow Reader

*An invaluable companion on your reading journey.*

A private reading space for long novels and text-based PDFs. Shadow Reader reflows your book into a comfortable layout, finds the chapters, and remembers where you stopped. Everything runs on your own computer; nothing is uploaded anywhere.

## Start reading

1. Extract this ZIP.
2. Open a terminal in the extracted `shadow-reader` folder (the one containing `run.sh`).
3. Run:

   ```sh
   ./run.sh
   ```

4. Your browser should open on its own. If it doesn't, go to **http://127.0.0.1:8765/**.
5. Click **Open a PDF** and choose your book. Plain `.txt` files work too.

Keep the terminal open while you read. Press **Ctrl+C** in it to stop Shadow Reader.

If you get "permission denied", run `chmod +x run.sh` once and try again.

## What you need

- **Linux** with **Python 3** and a desktop browser. Firefox is recommended. Tested on fresh installs of Debian 13, Fedora, Arch Linux, Alpine and openSUSE Tumbleweed; Ubuntu, Mint and other relatives should behave the same.
- **Poppler** (`pdftotext`) to read PDFs. If Python 3 or Poppler is missing, `run.sh` shows the install command for your system and asks before running it. Without Poppler, `.txt` files still work.

To install Poppler yourself:

| Distribution | Command |
|---|---|
| Debian, Ubuntu, Mint | `sudo apt update && sudo apt install -y poppler-utils` |
| Fedora | `sudo dnf install -y poppler-utils` |
| Arch, Manjaro | `sudo pacman -S --needed poppler` |
| openSUSE | `sudo zypper install poppler-tools` |
| Alpine | `doas apk add poppler-utils` (or `sudo`, or as root) |
| Void | `sudo xbps-install -S poppler` |
| Gentoo | `sudo emerge app-text/poppler` |

## Good to know

- **Normal mode** shows the whole book as one page. **Focus mode** shows one chapter at a time. In Normal mode, move the pointer into the right margin and click the small open-book button to jump into Focus mode at the passage you are reading.
- **Ctrl+F** searches the whole book.
- Reading progress and your display choices (text size, spacing, width, theme) are saved **in your browser**, not in the book. Always open Shadow Reader at the same address, `http://127.0.0.1:8765/`. Using `localhost` instead looks like a different site to the browser and will not show your saved progress.
- The PDF needs a real text layer. Scanned, image-only PDFs need OCR first. Shadow Reader is a reflowed reading view, not an exact copy of the printed page, so tables, columns and footnotes are not preserved.
- Chapter detection uses careful guesses. If a heading is missed, Normal mode still works.
- Files up to 80 MB are accepted.

## If something goes wrong

| Problem | Try |
|---|---|
| The browser didn't open | Open http://127.0.0.1:8765/ yourself while the terminal is still running |
| "Port already in use" | `SHADOW_READER_PORT=8766 ./run.sh`, then open `http://127.0.0.1:8766/` |
| PDF import says Poppler is missing | Install it with the table above, then restart `./run.sh` |
| Saved progress seems gone | Use the same address and browser as before, and don't clear the site's data |

## About

Project page, source code, tests and documentation: https://github.com/nameless-traveler/Shadow-Reader

Shadow Reader is released under the Apache License 2.0 (see `LICENSE`). Copyright © 2026 nameless-traveler.
