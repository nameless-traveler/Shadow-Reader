#!/usr/bin/env python3
"""Regression guard for the reading-position hot path on long text documents."""
from __future__ import annotations

import shutil
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
HTML = (ROOT / "index.html").read_text(encoding="utf-8")
PARAGRAPH_COUNT = 3000


def main() -> int:
    blocks = ["Shadow Reader: Long-document performance fixture"]
    blocks.extend(
        f"Paragraph {index}. A compact but readable paragraph used to exercise scroll-position tracking deep in a long document."
        for index in range(1, PARAGRAPH_COUNT + 1)
    )
    text = "\n\n".join(blocks)
    failures: list[str] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            executable_path=shutil.which("chromium") or shutil.which("chromium-browser") or None,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        page = browser.new_page(viewport={"width": 1200, "height": 800})
        errors: list[str] = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.set_content(HTML, wait_until="domcontentloaded")
        page.locator("#fileInput").set_input_files({
            "name": "long-document-performance.txt",
            "mimeType": "text/plain",
            "buffer": text.encode("utf-8"),
        })
        page.wait_for_function("!document.querySelector('#reader').classList.contains('hidden')", timeout=20_000)
        page.wait_for_timeout(200)
        paragraph_count = page.locator("#prose p").count()
        dom_nodes = page.locator("#prose *").count()
        footer_summary = page.locator("#footerPages").inner_text()
        if paragraph_count > 500:
            failures.append(f"virtualized reader kept too many live paragraphs: {paragraph_count}")
        if dom_nodes > 600:
            failures.append(f"virtualized reader kept too many live DOM elements: {dom_nodes}")
        if "3,001 paragraphs" not in footer_summary:
            failures.append(f"full source content count was lost in the footer: {footer_summary!r}")

        # Count layout reads triggered by scrolling near the end. A linear scan of
        # every paragraph would exceed this threshold by an order of magnitude.
        page.evaluate("""() => {
          window.__shadowReaderRectReadCount = 0;
          const original = Element.prototype.getBoundingClientRect;
          Element.prototype.getBoundingClientRect = function (...args) {
            window.__shadowReaderRectReadCount++;
            return original.apply(this, args);
          };
          document.documentElement.classList.add('instant-scroll');
          window.scrollTo({ top: document.documentElement.scrollHeight, behavior: 'auto' });
          window.dispatchEvent(new Event('scroll'));
        }""")
        page.wait_for_timeout(700)
        rect_reads = page.evaluate("window.__shadowReaderRectReadCount")
        max_source = page.evaluate("Math.max(-1, ...Array.from(document.querySelectorAll('#prose [data-reader-paragraph-index]')).map(node => Number(node.dataset.readerParagraphIndex) || 0))")
        if rect_reads > 300:
            failures.append(f"virtual window scroll update made {rect_reads} layout reads for {PARAGRAPH_COUNT + 1} source paragraphs; expected bounded work")
        if max_source < PARAGRAPH_COUNT - 50:
            failures.append(f"scrolling to the document bottom did not render the tail: highest mounted source index was {max_source}")
        if errors:
            failures.append("browser JavaScript errors: " + "; ".join(errors))
        browser.close()

    if failures:
        print("FAIL: long-document performance smoke test")
        for failure in failures:
            print(" - " + failure)
        return 1
    print(f"PASS: {PARAGRAPH_COUNT + 1} source paragraphs; {paragraph_count} live paragraphs / {dom_nodes} DOM nodes; deep-scroll update used {rect_reads} layout reads; tail index {max_source}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
