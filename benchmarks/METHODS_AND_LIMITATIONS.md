# Shadow Reader performance benchmark - methods and limitations

## Purpose
This report compares a pre-virtualized reader baseline with Shadow Reader 1.0.0. The goal is to measure the combined impact of virtualized rendering and the later scroll-anchor corrections. It does not isolate individual source changes.

## Host environment
- OS: Debian GNU/Linux 13 (trixie), Linux x86_64, kernel 6.18.55; containerized environment.
- CPU presented to test: AMD EPYC 9V74 virtual CPU, 5 vCPUs available.
- Memory visible: 5.8 GiB; swap 0 B.
- Python 3.13.5; Node.js v22.16.0; headless Chromium 144.0.7559.96 (Debian build); Playwright Python 1.57.0; Poppler `pdftotext` 25.06.0.
- Viewport: 1366 x 768 CSS pixels.
- The target laptop uses different hardware and Firefox. These figures are not a direct benchmark of that machine.

## Workloads and methods
- Actual novel: Shadow Slave Volume 7 PDF converted locally to UTF-8 text via Poppler `pdftotext -layout`; 20,692 paragraphs reported by the reader.
- Synthetic workload: generated text with about 30,061 paragraphs.
- Opening time: time from local text submission to a readable view, measured with fresh browser contexts. Actual Shadow Slave Volume 7: 3 trials per build. Synthetic 30k: 2 trials per build. Medians are reported; small n means results are directional and should be reproduced on the target device.
- DOM footprint: count of child elements beneath `#prose` after the reader is ready. This is not a memory metric by itself.
- Memory: Linux process-tree proportional set size (PSS) summed over the Chromium root process and descendants (8 processes observed). PSS apportions shared pages; do not sum RSS as if it were unique memory. JavaScript heap alone was higher and variable in the virtualized candidate, so no claim is made that JS heap decreased.
- Scroll correctness: injected deterministic wheel events on Shadow Slave Volume 7 text (18 events of +250 px, followed by 6 events of -200 px). Requested vertical displacement is 4,500 px down and 1,200 px up. This is a reproducible scroll-position regression test, not a physical touchpad inertia test or user-perceived FPS benchmark.
- Stress: 8,000 synthetic paragraphs at 4x CPU throttle passed; 30,000 paragraphs at 2x CPU throttle completed one run. A 30,000-paragraph 4x-throttle run did not complete within the automation budget and is inconclusive, not a pass.

## Summary metrics
- Actual Shadow Slave Volume 7 median time-to-readable: 2,316.4 ms baseline vs 1,310.5 ms Shadow Reader (43.4% lower; n=3 each).
- Synthetic 30k median time-to-readable: 4,726.5 ms vs 2,224.8 ms (52.9% lower; n=2 each).
- Shadow Slave Volume 7 live reading-area child elements: 21,276 vs 45 (99.8% fewer).
- Synthetic 30k live reading-area child elements: 30,181 vs 45 (99.85% fewer).
- Shadow Slave Volume 7 median process-tree PSS: 497.8 MB vs 348.6 MB (30.0% lower).
- Synthetic 30k median process-tree PSS: 657.2 MB vs 492.0 MB (25.1% lower).
- Shadow Slave Volume 7 deterministic scrolling: pre-fix virtualized candidate median downward displacement 6,435 px for a 4,500 px request; reverse gesture resulted in -5,882 px signed displacement (wrong direction). Shadow Reader reached 4,500 px down and +1,200 px up, with zero application-issued `window.scrollTo()` corrections vs median 35 in the pre-fix build.

## Regression checks on final release source
- Parser regression: 296 groups, including 200 generated heading cases, 20 generated 10-chapter books, and the full text of Alice plus Shadow Slave Volumes 6 and 7.
- Continue Reading feature regression: 27 checks.
- Focus Here feature regression: 10 checks.
- Branding and compatibility regression: 10 checks.
- Server API regression: 12 checks.
- Virtualization browser smoke: passed.
- Deep-scroll performance smoke: 3,001 paragraphs, 40 live paragraphs / 43 reader-area nodes, 94 layout reads.
- Touchpad-like scroll regression: 8k paragraphs, expected displacement matched in both directions, zero app scroll corrections.
- Focus Here browser smoke: passed on Alice PDF.
- Resume browser smoke: passed on Alice PDF; same-passage progress Normal 43% -> Focus 43% -> chapter end 50%; legacy inflated 100% record recalculated to 35% from saved chapter/position.
- Python syntax compilation and shell syntax check passed.

## Important limits
- Headless Chromium timings do not model native Firefox on the user's Debian laptop, touchpad hardware, GPU, display refresh, or other running programs.
- No direct perceptual smoothness score or native touchpad FPS was measured. The scroll claim is precisely about direction/displacement correctness and removal of app-issued scroll corrections in the deterministic test.
- Sample counts are small (n=2 or n=3); no confidence interval or statistical significance claim is made.
- The harder 30k-paragraph / 4x CPU-throttle automation attempt did not complete and is explicitly inconclusive.
- PSS is a useful Linux process memory estimate but is not necessarily identical to system-wide RAM pressure or Firefox memory on another machine.
