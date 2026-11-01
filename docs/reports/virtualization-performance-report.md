# Shadow Reader — Virtualized Reading Benchmark and Regression Report

**Date:** 27 October 2026  
**Result:** Adopted for large reading views; small books remain non-virtualized.

## Decision

Virtualization produced a substantial and repeatable improvement for large books: initial reader rendering was about 37% faster for Shadow Slave Volume 6, 45% faster for Shadow Slave Volume 7, and 47% faster for a generated 30,000-paragraph document. The live DOM fell from 9,774 to 47 nodes for Shadow Slave Volume 6, from 21,276 to 45 for Shadow Slave Volume 7, and from 30,000 to 43 for the synthetic book. I therefore merged the virtualized renderer into this build.

One caveat matters: these results **do not demonstrate a reduction in total browser memory**. The measured JavaScript heap was unchanged for Shadow Slave Volume 6, about 3.7 MB higher for Shadow Slave Volume 7, and about 1.6 MB higher for the synthetic 30,000-paragraph document. Virtualization reduces mounted DOM and rendering work, but the complete extracted text remains in memory and the source-position metadata adds overhead. The memory result is mixed, so the report does not claim lower overall RAM usage.

## Benchmark method

- Compared the earlier, pre-virtualization build with the virtualized candidate.
- Ran both in headless Chromium at a 1280 × 850 viewport.
- Used two open/render trials per document and reported the median.
- Used selectable text extracted from the three supplied PDFs via Poppler (`pdftotext -layout -enc UTF-8`), fed through the reader's text-file UI. The separate local server API suite was also run; the direct PDF-extraction endpoint was not driven by the browser benchmark itself.
- After opening, waited for the reader to settle, forced Chromium GC where available, measured DOM counts, and sampled `performance.memory.usedJSHeapSize`. That is a JavaScript-heap estimate, **not** total Firefox/Chromium process memory or native DOM memory.
- Also ran interaction tests on synthetic long novels designed to expose bugs that real books do not necessarily contain, including chapters longer than the virtualization threshold.

## Results

| Document | Source paragraphs | Open/render, baseline | Open/render, virtualized | DOM nodes, baseline → virtualized | Live paragraphs, baseline → virtualized | JS heap, baseline → virtualized |
|---|---:|---:|---:|---:|---:|---:|
| Alice's Adventures in Wonderland | 1,103 | 269 ms | 250 ms | 1,071 → 1,071 | 1,035 → 1,035 | 10.0 → 10.0 MB |
| Shadow Slave Volume 6 | 9,438 | 954 ms | 602 ms (**36.9% faster**) | 9,774 → 47 (**99.5% fewer**) | 9,264 → 38 (**99.6% fewer**) | 10.0 → 10.0 MB |
| Shadow Slave Volume 7 | 20,692 | 1,943 ms | 1,071 ms (**44.9% faster**) | 21,276 → 45 (**99.8% fewer**) | 20,214 → 39 (**99.8% fewer**) | 13.4 → 17.1 MB |
| Synthetic long novel | 30,000 | 3,066 ms | 1,622 ms (**47.1% faster**) | 30,000 → 43 (**99.9% fewer**) | 30,000 → 40 (**99.9% fewer**) | 26.0 → 27.6 MB |

Alice is below the 1,600-source-paragraph threshold, so it remains normally rendered; the small difference in its open timing is within the range where environmental noise matters. The performance gain is specifically for long books/chapters.

The steady-state virtual window generally keeps around 36–40 source items mounted plus spacer/container nodes. The 3,001-paragraph performance smoke test reported 40 live paragraphs and 43 nodes after a deep-scroll/tail-mount check. Its measured deep-scroll update used 113 layout reads in this run; that value is bounded by the mounted window and local measurements, rather than requiring each of the 3,001 paragraphs to be in the DOM.

## Implementation

- Virtualization activates at **1,600 source paragraphs** in the current reading view. Smaller books stay on the simpler full-DOM path.
- Normal mode and Focus mode both use virtualization when their current view is large enough, including individual chapters with more than 1,600 paragraphs.
- A viewport-sized paragraph window plus overscan stays mounted. Top/bottom spacer blocks represent off-screen content; paragraph extents use estimates and are corrected from mounted node measurements.
- Stable original source-paragraph indices bridge the virtual window to chapter selection, Focus Here, saved reading position, and book-relative progress.
- Because native browser Find only searches mounted DOM, `Ctrl+F` opens Shadow Reader's full-book search. It searches source text, and selecting a match mounts and scrolls to the matching passage.
- Changing typography resets virtual height estimates. Opening another document and explicitly resetting reading position mount the start window rather than inheriting the prior document's deep scroll state.

## Bugs found and fixed during testing

1. **New-document/top-of-book mount:** opening a new long document after being deep in another book could inherit the old `scrollY` long enough to mount an incorrect window. New views now explicitly mount their start window.
2. **Focus Here within an oversized chapter:** a queued scroll event during the mode transition could remount the top window before the chosen paragraph was aligned. Window updates are suppressed while the Focus transition is in progress. The large-chapter regression caught this; after the fix, the selected source passage remains near the reading guide.
3. **Focus-mode chapter jump test:** made a title assertion case-insensitive; that test failure was an assertion capitalization issue, not a reader bug.
4. **Search in unmounted content:** added a reader-owned full-book search so matches do not depend on whether the target paragraph currently exists in the DOM.

## Regression results

- `node tests/parser-regression.cjs /path/to/alice.txt /path/to/shadow-slave-v6.txt /path/to/shadow-slave-v7.txt` — **296 test groups passed**; the full documents retained the expected chapters and sequences: Alice 12, Shadow Slave Volume 6 170, Shadow Slave Volume 7 354.
- `node tests/resume-feature-regression.cjs` — **27 checks passed**.
- `node tests/focus-here-feature-regression.cjs` — **10 checks passed**.
- `python3 tests/performance-browser-smoke.py` — **passed**: 3,001 source paragraphs; 40 live paragraphs / 43 DOM nodes; tail window mounted at source index 3,000.
- `python3 tests/resume-browser-smoke.py` — **passed**: saved-position restoration, safe Escape, legacy migration, explicit reset, failed-import recovery, and text import.
- `python3 tests/focus-here-browser-smoke.py` — **passed**: exact passage, progress preservation, reveal/hide, keyboard access, duplicate-control handling, reduced motion.
- `python3 tests/virtualization-browser-smoke.py` — **passed**: random deep scrolling, tail mounting, full-text search of an unmounted paragraph, Continue Reading restore, switching to a second long book from a deep previous scroll, Focus Here into a 1,700-paragraph chapter, exiting Focus mode, and jumping to another large chapter.
- `python3 tests/server-api-regression.py` — **12 API checks passed**: local upload validation, limits, timeouts, missing Poppler fallback, and text-only startup.
- `python3 -m py_compile server.py tests/*.py`, `bash -n run.sh`, and inline JavaScript syntax check — **passed**.
- Actual full-text frontend smoke: Alice detected **12** chapters with **1,103** source paragraphs and remained non-virtualized; Shadow Slave Volume 6 detected **170** chapters over **9,438** source paragraphs and mounted about 40 live items; Shadow Slave Volume 7 detected **354** chapters over **20,692** source paragraphs and mounted about 40 live items. No browser page errors were observed in those runs.

The browser UI tests were run with headless Chromium, not native Firefox. The server API test was run separately. The actual whole-PDF text was extracted from the supplied PDFs and fed through the frontend as `.txt` for the UI benchmark; the browser benchmark did not claim to exercise the HTTP PDF-upload endpoint.

## Limitations and follow-up

- Full text and source text metadata remain resident in JavaScript memory; only mounted DOM is bounded. Total process RAM/Firefox native DOM memory has not been measured here.
- Virtual scroll height is estimated from paragraph extents; font, spacing, and width changes rebuild estimates. Very unusual layouts should be reported with a reproducible document.
- `Ctrl+F` is now a Shadow Reader search dialog, not the browser's built-in Find UI. It supports the full extracted text even when paragraphs are unmounted.
- Run a short manual Firefox check on Debian after installation, particularly opening a long PDF, searching for a late-book phrase, opening it via Focus Here, changing font/width, and resuming after restart.
