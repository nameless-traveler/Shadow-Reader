# Shadow Reader — Touchpad Scrolling Investigation and Fix

## Summary

The supplied screen recording was sufficient to guide the investigation. It showed that Normal mode was much more prone to sticking than Focus mode. The code and a browser scroll trace identified two interacting problems in the first virtualized implementation:

1. Each virtual-window update rebuilt a cumulative-height prefix table across the entire book even though only a few paragraph heights had changed.
2. Virtual spacers change height as visible paragraphs are measured. The browser's native scroll anchoring responded to those DOM changes and could override touchpad input. In a repeatable scroll trace, after 20 downward inputs of 300 px each, the viewport ended at about 35,978 px instead of the requested 6,000 px; five reverse inputs then still moved it further downward to about 60,134 px. That is a real scroll-position defect, not just slow rendering.

## Fixes applied

- Replaced the per-window O(n) cumulative-height table rebuild with a Fenwick tree (binary indexed tree). Changing the height estimate for a paragraph now updates the cumulative index in O(log n). A full rebuild remains available for initial setup and deliberate global estimate resets.
- Disabled native browser scroll anchoring only on `.prose.virtualized-reader`. Height changes in virtualized spacers can no longer force the browser to compensate the scroll position independently of the user's gesture. Non-virtualized books retain their regular browser behavior.
- Normal scrolling measures only mounted paragraphs at or below the reading guide, avoiding revisions to paragraph estimates behind the user's current reading position. Explicit chapter jumps, restoration, and Focus Here retain their targeted navigation/anchor paths.
- Kept the prior fix that avoids application-issued `scrollTo()` corrections for ordinary scroll-window updates.
- Added `tests/touchpad-scroll-behavior.py` as a regression test using the actual reader UI, an 8,000-paragraph generated novel, small wheel deltas, reverse scrolling, bounded DOM assertions, and scroll-correction instrumentation.
- Removed the temporary debug scripts before packaging.

## Repeated benchmark

Three runs per version in headless Chromium, with an 8,000-paragraph generated novel and a deterministic wheel stream of 45 × +300 px, 10 × −260 px, and 22 × +340 px. The net requested displacement is 18,380 px. This is a reproducible approximation of touchpad input, not a physical touchpad hardware/inertia simulation.

| Metric | Previous virtualized build (median) | Updated build (median) | Result |
|---|---:|---:|---|
| Application `window.scrollTo()` calls during ordinary scrolling | 151 | 0 | No corrective scroll calls during the gesture |
| Virtual render calls during the gesture | 163 | 76 | 53.4% fewer window renders |
| Full prefix-table rebuilds | 164 | 0 | Removed from the scroll-window hot path |
| Net scroll displacement | 28,695 px | 18,380 px | Updated build follows the requested gesture distance |
| Full run elapsed (including initial opening) | 4.604 s | 3.714 s | 19.3% lower in this harness |
| Per-frame interval median | 16.6 ms | 16.7 ms | Essentially unchanged |
| Per-frame interval p95 | 18.9 ms | 19.4 ms | Slightly noisier; no claim of better frame cadence |

The most important improvement is that the old build overshot the requested net scroll displacement by 56.1% and the updated build matched it. The elapsed result also improved in this harness, but it includes document loading/opening and is not a standalone hardware benchmark. Frame interval measurements did not show an improvement, so the result should not be described as a general FPS increase.

## Touchpad-style regression tests

- Generated 8,000-paragraph novel: 20 × +300 px moved the viewport by exactly 6,000 px; five × −260 px moved it upward by exactly 1,300 px. There were zero application `scrollTo()` corrections, no page errors, and only 40 live paragraph/item nodes remained mounted.
- Actual selectable text extracted from Shadow Slave Volume 7: the same 6,000 px downward and 1,300 px upward input matched exactly, with zero application scroll corrections and no page errors. Virtualization was active.
- Three-run comparative benchmark: all runs of the old build finished at roughly 28.5–28.7k px; all updated runs finished at 18,380 px. The updated build made zero prefix-table rebuilds during scrolling.

## Regression tests rerun

- Parser/chapter detection: 296 test groups, 200 generated heading cases, 20 generated 10-chapter books, and all three complete text files (Alice 12 chapters; Shadow Slave Volume 6: 170; Shadow Slave Volume 7: 354).
- Continue Reading/progress static checks: 27 passed.
- Focus Here static checks: 10 passed.
- Virtualization browser smoke: passed (random scrolling, tail mounting, Focus Here, full-book search, Continue Reading).
- Large-document performance browser smoke: passed (3,001 source paragraphs, 40 live paragraph items, 43 DOM nodes, 94 layout reads on deep scroll).
- Continue Reading browser smoke: passed, including cross-mode progress and legacy inflated-100% recovery.
- Focus Here browser smoke: passed.
- Touchpad scroll behavior regression: passed on generated novel and actual Shadow Slave Volume 7 extracted text.
- Server/API regression: 12 checks passed.
- Inline JavaScript syntax, shell syntax, and Python compilation checks: passed.

## Limits

Automated browser tests ran in headless Chromium; the native Firefox GUI could not be driven in this environment. The touchpad regression uses small wheel events as a deterministic proxy, not a physical touchpad's complete momentum/inertia behavior. The uploaded video remains the qualitative reference, and the final feel should still be confirmed in Firefox on the Debian machine. Total extracted text and height metadata remain in memory; this fix targets scroll jumps and per-window work, not a guarantee of lower total process RAM.
