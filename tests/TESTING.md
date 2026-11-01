# Shadow Reader parser regression tests

Run in the extracted `shadow-reader` directory:

```bash
node tests/parser-regression.cjs
node tests/resume-feature-regression.cjs
node tests/focus-here-feature-regression.cjs
python3 tests/server-api-regression.py
python3 tests/real-pdf-extraction.py      # needs Poppler: sudo apt install -y poppler-utils
python3 tests/release-branding-regression.py
python3 tests/logo-route-regression.py
python3 tests/host-check-regression.py
python3 tests/performance-browser-smoke.py
python3 tests/virtualization-browser-smoke.py
```

To include full-document checks for the supplied Alice PDF and Shadow Slave Volumes 6 and 7, first extract selectable text, then pass all three files:

```bash
pdftotext -enc UTF-8 -layout /path/to/alices-adventures-in-wonderland.pdf /tmp/alice.txt
pdftotext -enc UTF-8 -layout /path/to/Shadow-Slave-Volume-6.pdf /tmp/v6.txt
pdftotext -enc UTF-8 -layout /path/to/Shadow-Slave-Volume-7.pdf /tmp/v7.txt
node tests/parser-regression.cjs /tmp/alice.txt /tmp/v6.txt /tmp/v7.txt
```

The suite contains 27 individual heading-style fixtures from 26 public-domain source entries, 200 generated heading cases, 20 generated 10-chapter books, TOC and false-positive checks, and a synthetic 180-page running-header test. When you provide the extracted text from the complete PDFs, the full-document checks assert exact counts and sequences: Alice 12 chapters, Shadow Slave Volume 6 170 chapters, and Shadow Slave Volume 7 354 chapters. The PDFs/text files are optional local test inputs and are not bundled with this project. All 12 Alice chapter titles are checked exactly, including titles split over multiple lines.

The 26 online source entries contribute individual format examples, not full-book runs. External text downloads were unavailable in the build runtime, so the end-to-end novel corpus here is the three complete local PDFs. To expand the corpus, add a text file and expected chapter count/title assertions to the harness.


The Continue Reading checks verify the resume dialog/actions, autosave hooks, stable source-paragraph anchors, chapter-identity mapping, canonical source-text progress, legacy progress migration, and protection against a false top-of-book state on long PDFs. The browser smoke test reproduces the reported Normal-mode ~40% → scroll to top → Focus mode → revisit the same source passage → finish that chapter flow. It verifies that the same passage does not add its chapter-local scroll ratio a second time, and checks restoration, explicit start-over, and an intentionally corrupted legacy `100%` record. For a browser-driven smoke test, install optional test dependencies (Python Playwright plus Chromium) and run:

```bash
python3 tests/resume-browser-smoke.py
python3 tests/resume-browser-smoke.py /path/to/alices-adventures-in-wonderland.pdf
python3 tests/performance-browser-smoke.py
```

The browser test runs the actual reader HTML and UI in headless Chromium, simulates the local PDF extraction response, and tests save → click the top Open a PDF control while reading → reopen the same book → Continue reading → safe Escape behavior → Start from the beginning. When a PDF path is supplied, its text is extracted using Poppler before being provided to the reader UI. This is a frontend interaction test, not a test of the local HTTP extraction endpoint or a substitute for testing in Firefox.

## Focus-here side control

Run the static feature checks and browser interaction test:

```bash
node tests/focus-here-feature-regression.cjs
python3 tests/focus-here-browser-smoke.py
```

The browser test uses the actual reader interface and a generated 12-chapter novel. To exercise the same flow against a complete PDF (Poppler's `pdftotext` must be installed), pass its path:

```bash
python3 tests/focus-here-browser-smoke.py /path/to/alices-adventures-in-wonderland.pdf
```

The checks cover: control hidden by default; no reveal while the prose is not at the reading guide; intentional right-margin reveal; tooltip placement in the outer margin instead of over text; hide after leaving; switching into Focus mode at the same source paragraph/reading guide; progress not increasing from a transient chapter-bottom scroll; hiding the side control in Focus mode; avoiding a duplicate beside the final Focus button; reduced-motion-aware scripted scrolling, and a tab order that skips an unavailable/invisible Focus-here control. The resume-dialog browser test also checks keyboard focus trapping and the non-destructive Escape action.

The local API integration test starts the real request handler on an ephemeral loopback port and uses a tiny fake `pdftotext` executable to test upload validation, health/error responses, page counts, oversized extraction termination, upload/extraction timeouts, and text-only startup without needing a bundled PDF fixture. The long-document performance smoke test renders 3,000 paragraphs and guards against progress tracking falling back to a full-DOM scan on each scroll. That fake extractor is deliberate (it lets the test provoke oversized output, timeouts and password errors), so it cannot show that Poppler really reads a PDF. `tests/real-pdf-extraction.py` covers that: it builds a small valid PDF in memory, sends it through the real request handler to the real `pdftotext`, and checks page count, text, UTF-8 and the error paths.

`tests/logo-route-regression.py` checks that the logo is served as a real PNG, is cacheable, and stays under 400 KB. `tests/host-check-regression.py` checks that the server answers only requests addressed to its own address (`127.0.0.1` or `localhost` on its own port) and refuses foreign Host or Origin headers, which blocks DNS-rebinding and cross-site uploads.

CI runs all of these, including the five browser tests (see `.github/workflows/ci.yml`).



## Virtualized long-book rendering

The reader activates virtualization when the current reading view contains at least 1,600 source paragraphs. It retains a viewport-sized window with overscan and spacer elements for off-screen content; large chapters are virtualized in Focus mode too. Source paragraph indices remain the stable bridge for progress, resume restoration, chapter selection, Focus Here, and search. Since native browser text search cannot find unmounted DOM text, `Ctrl+F` opens the reader's full-book search, which searches the extracted source paragraphs and mounts the selected match.

Run the browser smoke tests with Playwright and Chromium installed:

```bash
python3 tests/performance-browser-smoke.py
python3 tests/virtualization-browser-smoke.py
```

The performance test checks a 3,001-paragraph document, bounded live DOM size, deep-scroll window mounting, and progress tracking. The virtualization interaction test checks random deep scrolling, the end of the document, full-text search for a paragraph outside the current DOM window, Continue Reading restoration, opening a second large book from the top, Focus Here into a >1,600-paragraph chapter, exiting Focus mode, and jumping to another large chapter.

The release review separately compares the original non-virtualized build with the virtualized build using selectable text extracted from Alice's Adventures in Wonderland and Shadow Slave Volumes 6 and 7, plus a generated 30,000-paragraph document. These browser benchmarks use `.txt` upload into the actual reader frontend; the server API is tested separately. Heap values reported by Chromium are approximate JavaScript heap usage, not total browser/process memory, and should not be interpreted as proof that all memory usage decreases.


## Touchpad scroll regression

Run `python3 tests/touchpad-scroll-behavior.py`. It loads an 8,000-paragraph generated novel into the actual reader UI, streams small wheel deltas down and up, and verifies that the viewport moves by approximately the requested distance. The test also asserts that virtualized content has `overflow-anchor: none`, ordinary scrolling causes no application `scrollTo()` corrections, the live DOM remains bounded, and no page errors occur. This wheel stream is a deterministic proxy for touchpad gesture input, not a simulation of every physical touchpad's inertia; confirm final feel with Firefox on the target machine.
