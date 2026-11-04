Shadow Reader for Windows
=========================

A private reading space for long novels and text-based PDFs. Everything runs on your own computer;
nothing is uploaded anywhere.

Start reading
-------------
1. Extract ALL files from this zip (right-click the zip > Extract All). Do not run it from inside the zip.
2. Open the extracted folder and double-click  Shadow-Reader.bat
3. A black window opens and your browser opens on its own. If it does not, go to  http://127.0.0.1:8765/
4. Click "Open a PDF" and choose your book. Plain .txt files work too.

Keep the black window open while you read. Close it, or press Ctrl+C in it, to stop Shadow Reader.

Windows may say "Windows protected your PC" the first time, because this download is not code-signed.
Choose "More info", then "Run anyway". Shadow Reader only listens on your own computer (127.0.0.1).

What is inside
--------------
- Python (the official embeddable package from python.org), so you do not need to install anything.
- Poppler's pdftotext (in the "poppler" folder), which turns PDF pages into text. Poppler is free
  software under the GNU GPL; see THIRD-PARTY-NOTICES.txt for its licence and where to get its source code.

Good to know
------------
- Always open Shadow Reader at http://127.0.0.1:8765/ . Your reading progress is saved in your browser for
  that exact address; "localhost" counts as a different site and will not show it.
- The PDF needs a real text layer. Scanned, image-only PDFs need OCR first.
- If port 8765 is busy, open a Command Prompt in this folder and run:
      set SHADOW_READER_PORT=8766
      Shadow-Reader.bat
  then open http://127.0.0.1:8766/
- Windows download: Poppler's optional language data (extra character maps for some non-Latin PDFs) is not included.

Project page, source code and documentation: https://github.com/nameless-traveler/Shadow-Reader
Shadow Reader is released under the Apache License 2.0 (see LICENSE).
