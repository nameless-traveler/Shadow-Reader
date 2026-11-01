# Shadow Reader — release notes

## 1.0.1 — 1 November 2026

- **Logo included.** The download now ships `assets/shadow-reader-logo.png`, and the landing page shows it.
- **Simpler landing page.** Shorter intro text and a smaller headline.
- **Safer local server.** It now answers only requests addressed to `127.0.0.1` or `localhost` on its own port, refusing other hosts and cross-site uploads.
- **Leaner download.** The ZIP contains only what is needed to read: the app, the logo, a short README and the licence.
- **Renamed storage.** Browser storage keys are now `shadowReaderProgressV1` and `shadowReaderPrefs`, and the older alias for the port setting is gone (use `SHADOW_READER_PORT`). **Reading progress and display settings saved by 1.0.0 do not carry over;** the reader starts fresh once.
- CI now also tests real PDF extraction with Poppler and runs the browser tests.

## 1.0.0 — 27 October 2026

**Platform:** Debian Trixie / XFCE, Firefox-friendly local web UI

### Included

- Balanced chapter-heading detection with full-document regression coverage for the three validation PDFs.
- Continue Reading with saved source-paragraph anchors and a deliberate Start from the beginning action.
- Book-relative progress that remains consistent between Normal and Focus modes.
- Discreet Focus Here control, keyboard accessibility, and reduced-motion support.
- Virtualized rendering for long views and chapters, full-book search over unmounted text, and a Fenwick-tree height index.
- Touchpad scroll fix: virtualized layout changes no longer fight normal scroll input through native scroll anchoring or routine app-issued scroll corrections.
- Bounded local PDF extraction, input limits/timeouts, and `.txt` fallback if Poppler is unavailable.

### Compatibility notes

The application is named **Shadow Reader**. Reading progress and display preferences are stored in the browser under `shadowReaderProgressV1` and `shadowReaderPrefs`, and the port can be set with `SHADOW_READER_PORT`. Keep using the same address (`http://127.0.0.1:8765/` by default), because browser storage is tied to it.

### Validation summary

- Parser regression: 296 groups pass with Alice (12 chapters), Shadow Slave Volume 6 (170), and Shadow Slave Volume 7 (354).
- Continue Reading static checks: 27 pass; browser restoration/progress tests pass against Alice.
- Focus Here static checks: 10 pass; browser interaction tests pass against Alice.
- Local server/API tests: 12 pass.
- Virtualization browser tests: pass for random/deep scrolling, tail rendering, full-book search, resume, book switching, large chapter Focus Here, exit, and chapter jump.
- Touchpad-like scroll regression: passes for an 8,000-paragraph novel under simulated 4× CPU slowdown; requested directional movement is preserved and no ordinary-scroll correction calls occur.
- 30,000-paragraph synthetic stress run under simulated 2× CPU slowdown opened successfully and retained correct scroll direction. A 30,000-paragraph/4× trial did not complete within the automation window and is reported as inconclusive, not a pass.
- See `benchmarks/` for the method, environment, raw observations, and limitations. See the separate Performance Benchmark PDF for charts.

All browser-driven tests were run in headless Chromium. A manual native Firefox check on the target Debian laptop remains recommended because touchpad hardware/inertia and full browser-process memory were not measured in this environment.

### Performance validation materials

This release includes `PERFORMANCE_BENCHMARK.pdf` and the `benchmarks/` directory with raw CSV results, test environment/source hashes, chart images, methods/limitations, and a reproducible Playwright benchmark harness. Performance claims are explicitly limited to the measured headless Chromium environment; native Firefox/touchpad performance on the target laptop still requires a local run.
