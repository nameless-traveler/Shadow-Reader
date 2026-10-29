# Shadow Reader — review and test report

Reviewed: 26 October 2026

## Improvements made in this review

- **Safer resume shortcut:** pressing `Esc` on the Continue Reading prompt restores the saved location. Only the explicit **Start from the beginning** action resets progress.
- **Accessible resume prompt:** keyboard focus stays inside the modal while it is open.
- **Context-aware Focus Here keyboard access:** the discreet margin control is removed from the tab order when it is unavailable, and becomes keyboard-accessible when the current passage makes it relevant. Keyboard focus positions it at the reading guide.
- **Reduced-motion support:** programmatic chapter/mode scrolling becomes immediate when `prefers-reduced-motion: reduce` is enabled. Smooth scrolling remains the default otherwise.
- **Clearer failed-import behavior:** if a new document cannot be opened, the reader explains that the previous document is still open instead of leaving a misleading generic status.
- **Long-book scroll performance:** the reader caches its ordered anchor elements and binary-searches for the current reading position, instead of calling `getBoundingClientRect()` on every preceding paragraph for every scroll event. Normal rendering also uses a chapter-start map rather than repeatedly scanning the chapter list for each paragraph.
- **Lower-risk PDF extraction:** uploads stream to a temporary file instead of being held as one large in-memory byte string. `pdftotext` writes to a temporary output file, and the reader terminates extraction that exceeds 25,000,000 UTF-8 bytes or runs longer than 150 seconds. Stalled uploads have a 60-second read timeout. Temporary files are removed afterward.
- **Text-only fallback:** if Poppler is not installed, the local server still starts and `.txt` files remain usable. PDF import returns an installation hint until Poppler is available.
- **Repeatable API tests:** added `tests/server-api-regression.py` with a fake extractor to test input validation, failure messages, size limits, upload/extraction timeouts, and missing-Poppler behavior without including a large PDF fixture.

## Tests run

All tests below passed in the review environment.

| Check | Result |
| --- | --- |
| `node tests/parser-regression.cjs` | 293 parser test groups passed, including 200 generated heading cases and 20 generated 10-chapter books |
| `node tests/resume-feature-regression.cjs` | 27 Continue Reading/progress and rendering-performance checks passed |
| `node tests/focus-here-feature-regression.cjs` | 10 Focus Here static feature checks passed |
| `python3 tests/server-api-regression.py` | 12 local HTTP API checks passed |
| `python3 tests/performance-browser-smoke.py` | 3,001 paragraphs rendered; 36 layout reads during deep-scroll progress tracking |
| `python3 tests/focus-here-browser-smoke.py` | Browser interaction, source anchor/progress, duplicate-control, tab-stop, and reduced-motion checks passed |
| `python3 tests/resume-browser-smoke.py` | Resume, modal focus trap, safe Escape, legacy progress migration, explicit reset, failed-import recovery, and `.txt` import checks passed |
| `python3 -m py_compile server.py tests/*.py` | Passed |
| `sh -n run.sh` | Passed |
| Real Poppler integration | A generated two-page PDF was uploaded to the real handler; both chapter headings and the 2-page count were returned correctly |
| Responsive layout smoke check | No horizontal document overflow at 1200, 768, 390, or 320 CSS pixels, in Normal and Focus modes |

The browser interaction tests use headless Chromium. The current environment does not have Firefox installed, so a native Firefox run was not possible here. See `VIRTUALIZATION_PERFORMANCE_REPORT.md` for the follow-up long-book virtualization benchmarks and the final regression run performed on 27 October 2026.

## Limits of this test run

The ZIP includes the parser harness but not the complete Alice's Adventures in Wonderland or Shadow Slave Volumes 6 and 7 PDFs mentioned in `tests/TESTING.md`. Therefore, the optional whole-book exact chapter-count/title checks against those specific books were **not** run. The generated parser cases and browser fixture passed, and the real local server was tested with a generated PDF; this is not a substitute for re-running the exact-volume corpus checks with the original PDFs.

## Highest-value next improvements

1. **Virtualization follow-up.** Large books now use a viewport-sized DOM window, including large Focus-mode chapters, and full-book search works on unmounted source text. In the current benchmark, DOM size and initial rendering time improved substantially. The extracted text remains resident in JavaScript memory, and measured JS heap increased slightly for very large books due to virtual-position metadata; if total memory becomes a concern, profile the full Firefox process before attempting a more complex text-store architecture.
2. **A chapter-outline correction UI.** The detector intentionally prefers cautious heuristics to avoid false positives. A small per-book outline editor—rename a detected heading, add a missing boundary, or disable a false positive—would address unusual PDFs more robustly than endlessly broadening heading regexes. Save these overrides by document fingerprint, without copying the book into browser storage.
3. **Run the full golden corpus in Firefox.** The target browser is Firefox, and the current ZIP's tests explicitly support exact chapter-sequence verification when the three PDFs are supplied. Add a repeatable local release checklist for those PDFs plus a Firefox smoke run.
4. **Export/import reading state.** Positions and preferences are stored in this Firefox profile's local storage and can be lost if site data is cleared. A small JSON export/import for preferences and progress (never book contents) would provide a low-cost backup path.


## Follow-up: virtualized long-book rendering (27 October 2026)

The renderer now virtualizes views with at least 1,600 source paragraphs. It preserves source-paragraph identity, measured/estimated block extents, chapter-level selection, Focus Here anchoring, progress and resume restoration. Large Focus-mode chapters are virtualized too. `Ctrl+F` uses a reader-owned full-text search because browser find only indexes mounted DOM.

Regression coverage added in `tests/virtualization-browser-smoke.py` covers random deep scrolling, tail mounting, hidden-paragraph search, resume restoration, starting a new book at the top, Focus Here in a huge chapter, leaving Focus mode, and moving to another huge chapter. The test originally caught a queued-scroll race during Focus Here in a >1,600-paragraph chapter; `updateVirtualReaderWindow` now declines to remount during the mode transition so the requested target paragraph can be aligned first.
