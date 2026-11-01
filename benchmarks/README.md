# Shadow Reader performance benchmark materials

This folder accompanies **Shadow Reader 1.0.0**. It separates comparative measurements from regression tests and documents the limitations of each claim.

## Key measured outcomes

- On the extracted 20,692-paragraph Shadow Slave Volume 7 text, median time from text upload to a readable view was **2,316.4 ms** in the pre-virtualized baseline and **1,310.5 ms** in the candidate (**43.4% lower**; three fresh-browser trials per build).
- Reading-area element count changed from **21,276 to 45** (**99.8% fewer live DOM child elements**) for the same Shadow Slave Volume 7 text.
- Linux Chromium process-tree PSS changed from a median **497.8 MB to 348.6 MB** (**30.0% lower**) on Shadow Slave Volume 7. This sums PSS over the browser process and its children (8 processes); it is an estimate for this headless Chromium environment, not a result from Firefox on the target laptop.
- In the deterministic scroll sequence (18 x +250 px, then 6 x -200 px), the pre-scroll-fix build overshot the 4,500 px downward gesture and moved in the wrong direction on reverse input. The candidate tracked the requested **4,500 px down and 1,200 px up**, with **zero application-issued `window.scrollTo()` corrections** in each of the three Shadow Slave Volume 7 trials.
- A 30,000-paragraph synthetic book also reduced the reader-area DOM from 30,181 elements to 45 and the median browser process-tree PSS from 657.2 MB to 492.0 MB (25.1% lower, two trials each).

## Included charts

- `charts/opening-time.png` - time to readable view
- `charts/dom-footprint.png` - live reading-area DOM elements (log scale)
- `charts/process-tree-pss.png` - Chromium process-tree PSS memory estimates
- `charts/scroll-correctness.png` - directional scrolling and app-issued corrections


## Files

- `benchmark-results.csv` contains the individual trial observations.
- `environment.json` records the browser, runtime, operating system, memory, CPU, view size, source documents, and relevant source hashes.
- `run_browser_benchmark.py` is a reusable Playwright harness. Use an extracted `.txt` version of a novel (the test never uploads content to a remote service).
- `charts/` contains the chart images embedded in the PDF.

## How to reproduce the browser benchmark

Install Python Playwright, Chromium, and `psutil` on a Linux test system. Provide the pre-virtualization HTML and candidate HTML from separate source trees plus a locally extracted UTF-8 `.txt` novel:

```bash
python3 benchmarks/run_browser_benchmark.py \
  --baseline-index /path/to/baseline/shadow-reader/index.html \
  --candidate-index ./index.html \
  --text-file /path/to/extracted-novel.txt \
  --runs 3 \
  --output-dir ./benchmark-output
```

The script records open-to-readable time, child-element and paragraph counts, process-tree RSS/PSS where supported, and directional scroll behaviour. Use the same viewport, browser version, CPU load, and text file for both builds. It runs a deterministic wheel sequence; this is a reproducible scroll-position regression, **not** a physical touchpad inertia or subjective smoothness test. For an additional strain run, supply `--cpu-throttle 2` (or another rate) and report it as a separate scenario rather than mixing it with the default-speed numbers.

## Important qualifications

- The before/after opening comparison is **pre-virtualization baseline vs the current virtualized candidate**, so it measures the combined build difference; it cannot attribute all of the load-time reduction to a single source-code change.
- The scroll-correction comparison uses the previous virtualized build before the touchpad fix vs the candidate.
- Frame interval samples in headless Chromium stayed close to the browser's scheduling cadence and are not advertised as an FPS increase. No physical touchpad hardware capture or native Firefox GUI trace was available in this environment.
- JavaScript heap snapshots alone were higher and variable in the virtualized build. The memory claim uses Linux process-tree PSS instead, because it includes the browser and child processes; it still needs remeasurement on the target user's Firefox machine before making a universal RAM claim.
- A 30,000-paragraph / 4x-CPU-throttle automation attempt did not complete within the run budget and is **inconclusive**, not a pass. The 8,000-paragraph 4x scenario and 30,000-paragraph 2x scenario completed.
- The test environment is a 5-vCPU AMD EPYC VM with 5.8 GiB visible RAM, not the target computer. Results will differ with CPU, Firefox version, display refresh, touchpad driver, text length, and other open tabs.

## Release branding and compatibility

The product name in the UI is **Shadow Reader**. `SHADOW_READER_PORT` sets the server port. The environment/source hashes are recorded in `environment.json`.
