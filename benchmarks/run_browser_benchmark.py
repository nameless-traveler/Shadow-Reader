#!/usr/bin/env python3
"""Compare two local Shadow Reader HTML builds using a local UTF-8 .txt fixture.

Requires Python Playwright, Chromium, and (optionally) psutil for Linux process-tree PSS/RSS.
This is a deterministic wheel-event benchmark, not a physical touchpad inertia test.
"""
from __future__ import annotations
import argparse
import csv
import json
import shutil
import statistics
import time
from pathlib import Path
from typing import Any
from playwright.sync_api import sync_playwright

try:
    import psutil  # type: ignore
except ImportError:
    psutil = None


def chromium_tree_memory(launch_time: float) -> dict[str, Any] | None:
    if psutil is None:
        return None
    roots = []
    for proc in psutil.process_iter(["name", "cmdline", "create_time"]):
        try:
            argv = proc.info.get("cmdline") or []
            name = (proc.info.get("name") or "").lower()
            if (proc.info.get("create_time", 0) >= launch_time - 0.5
                and "chromium" in name
                and any(a.startswith("--user-data-dir=") for a in argv)
                and not any(a.startswith("--type=") for a in argv)):
                roots.append(proc)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    if not roots:
        return None
    root = max(roots, key=lambda p: p.create_time())
    try:
        processes = [root] + root.children(recursive=True)
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        processes = [root]
    rss = pss = 0
    count = 0
    for proc in processes:
        try:
            info = proc.memory_full_info()
            rss += info.rss
            pss += getattr(info, "pss", 0)
            count += 1
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return {"rss_bytes": rss, "pss_bytes": pss if pss else None, "process_count": count}


def run_trial(playwright, build_name: str, html_path: Path, text_bytes: bytes, text_name: str,
              cpu_throttle: float, viewport: tuple[int, int]) -> dict[str, Any]:
    executable = shutil.which("chromium") or shutil.which("chromium-browser")
    launch_time = time.time()
    browser = playwright.chromium.launch(
        headless=True,
        executable_path=executable,
        args=["--no-sandbox", "--disable-dev-shm-usage", "--enable-precise-memory-info"],
    )
    page = browser.new_page(viewport={"width": viewport[0], "height": viewport[1]})
    if cpu_throttle != 1:
        cdp = page.context.new_cdp_session(page)
        cdp.send("Emulation.setCPUThrottlingRate", {"rate": cpu_throttle})
    page_errors: list[str] = []
    page.on("pageerror", lambda error: page_errors.append(str(error)))
    page.set_content(html_path.read_text(encoding="utf-8"), wait_until="domcontentloaded")

    started = time.perf_counter()
    page.locator("#fileInput").set_input_files({
        "name": text_name,
        "mimeType": "text/plain",
        "buffer": text_bytes,
    })
    page.wait_for_function("!document.querySelector('#reader').classList.contains('hidden')", timeout=180_000)
    page.wait_for_function("document.querySelector('#footerPages').innerText.length > 0", timeout=30_000)
    open_to_readable_ms = (time.perf_counter() - started) * 1000
    page.wait_for_timeout(300)
    initial = page.evaluate("""() => ({
      footer: document.querySelector('#footerPages').innerText,
      virtualized: !!document.querySelector('#prose .virtual-window'),
      readerAreaElements: document.querySelectorAll('#prose *').length,
      liveParagraphItems: document.querySelectorAll('#prose [data-reader-paragraph-index]').length,
      jsHeapUsedBytes: performance.memory ? performance.memory.usedJSHeapSize : null,
      documentScrollHeight: document.documentElement.scrollHeight
    })""")
    memory_after_open = chromium_tree_memory(launch_time)

    page.evaluate("""() => {
      window.__shadowBenchmark = {scrollToCalls: 0, scrollIntoViewCalls: 0};
      const original = window.scrollTo.bind(window);
      window.scrollTo = (...args) => { window.__shadowBenchmark.scrollToCalls++; return original(...args); };
      const originalIntoView = Element.prototype.scrollIntoView;
      Element.prototype.scrollIntoView = function(...args) {
        window.__shadowBenchmark.scrollIntoViewCalls++;
        return originalIntoView.apply(this, args);
      };
    }""")
    start_y = page.evaluate("scrollY")
    for _ in range(18):
        page.mouse.wheel(0, 250)
        page.wait_for_timeout(22)
    down_y = page.evaluate("scrollY")
    for _ in range(6):
        page.mouse.wheel(0, -200)
        page.wait_for_timeout(22)
    final_y = page.evaluate("scrollY")
    after = page.evaluate("""() => ({
      appScrollToCalls: window.__shadowBenchmark.scrollToCalls,
      appScrollIntoViewCalls: window.__shadowBenchmark.scrollIntoViewCalls,
      readerAreaElements: document.querySelectorAll('#prose *').length,
      liveParagraphItems: document.querySelectorAll('#prose [data-reader-paragraph-index]').length,
      jsHeapUsedBytes: performance.memory ? performance.memory.usedJSHeapSize : null
    })""")
    memory_after_scroll = chromium_tree_memory(launch_time)
    record = {
        "build": build_name,
        "html_path": str(html_path.resolve()),
        "cpu_throttle_rate": cpu_throttle,
        "viewport": f"{viewport[0]}x{viewport[1]}",
        "open_to_readable_ms": round(open_to_readable_ms, 1),
        "initial": initial,
        "memory_after_open": memory_after_open,
        "requested_down_px": 4500,
        "actual_down_px": round(down_y - start_y),
        "requested_up_px": 1200,
        "signed_actual_up_px": round(down_y - final_y),
        "after_scroll": after,
        "memory_after_scroll": memory_after_scroll,
        "page_errors": page_errors,
    }
    browser.close()
    return record


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-index", type=Path, required=True)
    parser.add_argument("--candidate-index", type=Path, required=True)
    parser.add_argument("--text-file", type=Path, required=True, help="Locally extracted UTF-8 text; it is not sent to a remote service")
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--cpu-throttle", type=float, default=1.0)
    parser.add_argument("--viewport-width", type=int, default=1366)
    parser.add_argument("--viewport-height", type=int, default=768)
    parser.add_argument("--output-dir", type=Path, default=Path("benchmark-output"))
    args = parser.parse_args()
    for path in (args.baseline_index, args.candidate_index, args.text_file):
        if not path.is_file(): parser.error(f"file not found: {path}")
    if args.runs < 1: parser.error("--runs must be >= 1")
    if args.cpu_throttle < 1: parser.error("--cpu-throttle must be >= 1")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    text_bytes = args.text_file.read_bytes()
    results: list[dict[str, Any]] = []
    builds = [("baseline", args.baseline_index), ("candidate", args.candidate_index)]
    with sync_playwright() as playwright:
        for build_name, html_path in builds:
            for run_no in range(1, args.runs + 1):
                print(f"{build_name}: trial {run_no}/{args.runs}", flush=True)
                row = run_trial(playwright, build_name, html_path, text_bytes, args.text_file.name,
                                args.cpu_throttle, (args.viewport_width, args.viewport_height))
                row["trial"] = run_no
                results.append(row)
                print(json.dumps(row, ensure_ascii=False), flush=True)
    (args.output_dir / "raw-results.json").write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    with (args.output_dir / "summary.csv").open("w", newline="", encoding="utf-8") as f:
        fields = ["build", "trial", "cpu_throttle_rate", "viewport", "open_to_readable_ms", "reader_area_elements",
                  "live_paragraph_items", "requested_down_px", "actual_down_px", "requested_up_px", "signed_actual_up_px",
                  "app_scrollTo_calls", "process_tree_pss_bytes", "process_tree_rss_bytes", "page_error_count"]
        writer = csv.DictWriter(f, fieldnames=fields); writer.writeheader()
        for row in results:
            mem = row.get("memory_after_open") or {}
            writer.writerow({
                "build": row["build"], "trial": row["trial"], "cpu_throttle_rate": row["cpu_throttle_rate"],
                "viewport": row["viewport"], "open_to_readable_ms": row["open_to_readable_ms"],
                "reader_area_elements": row["initial"]["readerAreaElements"],
                "live_paragraph_items": row["initial"]["liveParagraphItems"],
                "requested_down_px": row["requested_down_px"], "actual_down_px": row["actual_down_px"],
                "requested_up_px": row["requested_up_px"], "signed_actual_up_px": row["signed_actual_up_px"],
                "app_scrollTo_calls": row["after_scroll"]["appScrollToCalls"],
                "process_tree_pss_bytes": mem.get("pss_bytes"), "process_tree_rss_bytes": mem.get("rss_bytes"),
                "page_error_count": len(row["page_errors"]),
            })
    for name in ("baseline", "candidate"):
        subset = [r for r in results if r["build"] == name]
        median = statistics.median(r["open_to_readable_ms"] for r in subset)
        print(f"{name} median open-to-readable: {median:.1f} ms", flush=True)
    print(f"Results written to {args.output_dir}")
    return 0 if not any(r["page_errors"] for r in results) else 1

if __name__ == "__main__":
    raise SystemExit(main())
