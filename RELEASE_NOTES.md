# Shadow Reader — release notes

## 2.1.0 — 5 November 2026

- **Windows download (experimental).** `Shadow-Reader-2.1.0-windows.zip` runs without installing anything: extract all, then double-click `Shadow-Reader.bat`. It bundles Python 3.13.17 and Poppler 26.09.0 (GPL; licence and source link are in `THIRD-PARTY-NOTICES.txt`). The Windows ZIP is built and run for real on Windows Server 2022 and 2025 in CI, including PDF extraction, a 300-page PDF, a busy-port check and a stop-and-restart check. It has **not yet been tried on a Windows 10 or 11 desktop** and is not code-signed, so Windows may show a SmartScreen warning.
- **Clear message when the port is busy.** Starting a second copy, or starting while another program uses the port, now stops with a short explanation and the `SHADOW_READER_PORT` setting instead of a long error.
- **Tests.** CI now runs the shared tests on Windows, and adds port-conflict and shutdown tests. Python 3.10 is the minimum supported version.
- The Linux download is unchanged apart from the port message above.
- **Poppler source code.** The Windows download includes Poppler 26.09.0 (GNU GPL). The corresponding source archive, `poppler-26.09.0.tar.xz`, is available from the [official Poppler releases page](https://poppler.freedesktop.org/releases/).

**Downloads and SHA-256 checksums**

| File | SHA-256 |
|---|---|
| `Shadow-Reader-2.1.0-linux.zip` | `03e347fbcbd503687b2041450eee6d2572f8324193337b025eefb3ff2d0f8755` |
| `Shadow-Reader-2.1.0-windows.zip` | `2a3cda774ff05d6bef4348b96d5398d66e9941a7dabd44c743eae3b098184342` |

## 2.0.2 — 3 November 2026

- **Tab icon.** The browser tab now shows the Shadow Reader icon.

## 2.0.1 — 3 November 2026

- **Tested on real systems.** CI now starts a fresh Debian 13, Fedora, Arch Linux, Alpine and openSUSE Tumbleweed container, lets `run.sh` install Python and Poppler, starts the server and extracts a real PDF.
- **Unattended installs.** Set `SHADOW_READER_ASSUME_YES=1` to let `run.sh` install without asking (used by those tests).
- **Alpine on a fresh system.** The launcher now uses `apk add --no-cache`, so it works without a prior `apk update`.

## 2.0.0 — 2 November 2026

- **Works beyond Debian.** `run.sh` now detects `apt`, `dnf`, `yum`, `pacman`, `zypper`, `apk`, `xbps` and `emerge`, shows the exact install command for Python 3 and Poppler, and asks before running it. It uses `sudo` or `doas`, or prints the command if neither exists.
- **Safer in scripts.** Without an interactive terminal the launcher never prompts or installs; it prints the command and starts for `.txt` files.
- **Neutral messages.** Error texts no longer assume Debian.
- New launcher tests run under dash, bash and busybox ash with fake package managers.

## 1.0.1 — 1 November 2026

- **Logo included.** The download now ships `assets/shadow-reader-logo.png`, and the landing page shows it.
- **Simpler landing page.** Shorter intro text and a smaller headline.
- **Safer local server.** It now answers only requests addressed to `127.0.0.1` or `localhost` on its own port, refusing other hosts and cross-site uploads.
- **Leaner download.** The ZIP contains only what is needed to read: the app, the logo, a short README and the licence.
- **Renamed storage.** Browser storage keys are now `shadowReaderProgressV1` and `shadowReaderPrefs`, and the older alias for the port setting is gone (use `SHADOW_READER_PORT`). **Reading progress and display settings saved by 1.0.0 do not carry over;** the reader starts fresh once.
- CI now also tests real PDF extraction with Poppler and runs the browser tests.

## 1.0.0 — 30 October 2026

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
