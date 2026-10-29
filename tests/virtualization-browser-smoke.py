#!/usr/bin/env python3
"""Browser regression coverage for windowed rendering on long documents."""
from __future__ import annotations
import shutil
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
HTML = (ROOT / "index.html").read_text(encoding="utf-8")
CHAPTERS = 12
PARAGRAPHS_PER_CHAPTER = 250


def make_text() -> str:
    parts = ["Virtualization Test Novel"]
    for chapter in range(1, CHAPTERS + 1):
        parts.extend(["", f"Chapter {chapter}: The Test Chapter {chapter}", ""])
        for paragraph in range(PARAGRAPHS_PER_CHAPTER):
            marker = f"unique-search-marker-chapter-{chapter:02d}-paragraph-{paragraph:03d}" if (chapter, paragraph) == (11, 213) else ""
            parts.append(
                f"Chapter {chapter}, paragraph {paragraph}. The traveler walked beside an old stone wall, "
                f"recording each detail in a small notebook. {marker} This sentence provides enough text "
                "to wrap naturally and exercise virtual window measurement."
            )
            parts.append("")
    return "\n".join(parts)


def fail(msg: str) -> None:
    raise AssertionError(msg)


def read_anchor(page):
    return page.evaluate("""() => {
      const guide = Math.min(155, Math.max(80, innerHeight * .23));
      const nodes = [...document.querySelectorAll('#prose [data-reader-paragraph-index]')];
      let winner = null, distance = Infinity;
      for (const node of nodes) {
        const rect = node.getBoundingClientRect();
        const d = rect.top <= guide && rect.bottom >= guide ? 0 : Math.min(Math.abs(rect.top-guide), Math.abs(rect.bottom-guide));
        if (d < distance) { distance = d; winner = node; }
      }
      return winner ? {index:Number(winner.dataset.readerParagraphIndex), text:winner.textContent.slice(0,300), top:winner.getBoundingClientRect().top} : null;
    }""")


def main() -> int:
    failures: list[str] = []
    payload = {"name": "virtualization-test-novel.txt", "mimeType": "text/plain", "buffer": make_text().encode("utf-8")}
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            executable_path=shutil.which("chromium") or shutil.which("chromium-browser") or None,
            args=["--no-sandbox", "--disable-dev-shm-usage", "--js-flags=--expose-gc"],
        )
        page = browser.new_page(viewport={"width": 1280, "height": 850})
        errors: list[str] = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.set_content(HTML, wait_until="domcontentloaded")
        page.evaluate("""() => {
          const values = new Map();
          Object.defineProperty(window, 'localStorage', { configurable:true, value:{
            getItem:key => values.has(String(key)) ? values.get(String(key)) : null,
            setItem:(key,value) => values.set(String(key), String(value)),
            removeItem:key => values.delete(String(key)),
            clear:() => values.clear()
          }});
        }""")
        page.locator("#fileInput").set_input_files(payload)
        page.wait_for_function("!document.querySelector('#reader').classList.contains('hidden')", timeout=30000)
        page.wait_for_timeout(200)

        live = page.evaluate("""() => ({
          paragraphs:document.querySelectorAll('#prose p').length,
          elements:document.querySelectorAll('#prose *').length,
          virtual:!!document.querySelector('#prose .virtual-window'),
          footer:document.querySelector('#footerPages').textContent,
          status:document.querySelector('#statusText').textContent
        })""")
        if not live["virtual"]:
            failures.append("large document did not activate virtual window rendering")
        if live["paragraphs"] > 500 or live["elements"] > 600:
            failures.append(f"too many live nodes for {CHAPTERS * PARAGRAPHS_PER_CHAPTER} paragraphs: {live}")
        if "3,013 paragraphs" not in live["footer"]:
            failures.append(f"source paragraph count isn't preserved in the UI: {live['footer']}")
        if "12 chapter" not in live["status"]:
            failures.append(f"test document's 12 chapter headings were not detected: {live['status']}")

        # Arbitrary scrollbar jumps must cause the correct nearby source window to mount.
        source_counts = []
        for fraction in (0.05, 0.25, 0.50, 0.75, 0.95, 1.0, 0.50, 0.0):
            page.evaluate("f => { document.documentElement.classList.add('instant-scroll'); window.scrollTo(0, (document.documentElement.scrollHeight-innerHeight)*f); }", fraction)
            page.wait_for_timeout(110)
            anchor = read_anchor(page)
            if not anchor:
                failures.append(f"no readable source anchor at scroll fraction {fraction}")
                continue
            source_counts.append(anchor["index"])
            mounted = page.evaluate("""() => ({count:document.querySelectorAll('#prose [data-reader-paragraph-index]').length,
              min:Math.min(...[...document.querySelectorAll('#prose [data-reader-paragraph-index]')].map(n=>Number(n.dataset.readerParagraphIndex))),
              max:Math.max(...[...document.querySelectorAll('#prose [data-reader-paragraph-index]')].map(n=>Number(n.dataset.readerParagraphIndex)))})""")
            if mounted["count"] > 500:
                failures.append(f"DOM window grew unexpectedly at {fraction}: {mounted}")
            if fraction == 1.0 and mounted["max"] < (CHAPTERS * PARAGRAPHS_PER_CHAPTER) - 30:
                failures.append(f"bottom-of-book window did not include the document tail: {mounted}")
        # 50% should map back near the same source position when revisited.
        if len(source_counts) >= 8 and abs(source_counts[2] - source_counts[6]) > 130:
            failures.append(f"revisiting the same scroll position changed source anchor too much: {source_counts[2]} vs {source_counts[6]}")

        # Focus Here must map the current source anchor to the correct chapter without duplicating progress.
        page.evaluate("f => {document.documentElement.classList.add('instant-scroll'); window.scrollTo(0,(document.documentElement.scrollHeight-innerHeight)*f);}", 0.43)
        page.wait_for_timeout(150)
        before_anchor = read_anchor(page)
        before_percent = page.locator("#readProgress").inner_text().strip()
        rect = page.locator("#reader").bounding_box()
        guide_y = min(155, max(80, 850 * .23))
        if rect:
            page.mouse.move(rect["x"] + rect["width"] + 18, guide_y)
            page.wait_for_timeout(120)
            if not page.locator("#focusHereButton").evaluate("el => el.classList.contains('is-visible')"):
                failures.append("Focus Here did not appear in the reading margin for a middle passage")
            else:
                page.locator("#focusHereButton").click(force=True)
                page.wait_for_timeout(160)
                if not page.locator("body").evaluate("el => el.classList.contains('focus-mode')"):
                    failures.append("Focus Here did not switch the reader to Focus mode")
                focus_anchor = read_anchor(page)
                if before_anchor and focus_anchor and abs(before_anchor["index"] - focus_anchor["index"]) > 50:
                    failures.append(f"Focus Here lost the intended source paragraph: {before_anchor} -> {focus_anchor}")
                after_percent = page.locator("#readProgress").inner_text().strip()
                if before_percent != after_percent:
                    failures.append(f"Focus Here changed progress while switching modes: {before_percent} -> {after_percent}")
        else:
            failures.append("reader geometry wasn't available for the Focus Here test")

        # Full-text Ctrl+F searches the original text even when its target paragraph is unmounted.
        page.keyboard.press("Escape")
        page.keyboard.press("Control+f")
        page.locator("#bookSearchInput").fill("unique-search-marker-chapter-11-paragraph-213")
        page.wait_for_timeout(100)
        meta = page.locator("#bookSearchMeta").inner_text()
        if "1 match" not in meta:
            failures.append(f"full-text search failed to find unrendered content: {meta}")
        page.keyboard.press("Enter")
        page.wait_for_timeout(200)
        if page.locator("#bookSearchDialog").evaluate("el => el.classList.contains('show')"):
            failures.append("search result navigation didn't close the search dialog")
        search_anchor = read_anchor(page)
        if not search_anchor or "unique-search-marker-chapter-11-paragraph-213" not in search_anchor["text"]:
            failures.append(f"search did not jump to the exact unrendered match: {search_anchor}")

        # Re-open the same text file; the same fingerprint should offer Continue Reading and restore the source anchor.
        page.wait_for_timeout(650)
        saved_before = page.evaluate("""() => { const all=JSON.parse(localStorage.getItem('quietReaderProgressV1')||'{}'); return all[Object.keys(all)[0]] || null; }""")
        if not saved_before or not saved_before.get("paragraphIndex", -1) >= 0:
            failures.append(f"the virtual source position was not saved: {saved_before}")
        page.locator("#fileInput").set_input_files(payload)
        page.wait_for_function("document.querySelector('#resumeDialog').classList.contains('show')", timeout=10000)
        page.locator("#resumeBtn").click()
        page.wait_for_timeout(250)
        restored = read_anchor(page)
        saved_index = int(saved_before["paragraphIndex"]) if saved_before and saved_before.get("paragraphIndex") is not None else -1
        if not restored or (saved_index >= 0 and abs(restored["index"] - saved_index) > 12):
            failures.append(f"Continue Reading didn't restore the virtualized paragraph: saved={saved_index}, restored={restored}")

        # Switching from a deeply scrolled large book to a different large book must
        # mount its top window instead of inheriting the previous document's scrollY.
        huge_parts = ["Two Huge Chapters"]
        for chapter in (1, 2):
            huge_parts.extend(["", f"Chapter {chapter}: Huge Chapter {chapter}", ""])
            for paragraph in range(1700):
                huge_parts.extend([f"Huge chapter {chapter}, paragraph {paragraph}. Long-chapter virtualization check content repeats with enough prose to wrap over several lines.", ""])
        huge_payload = {"name": "two-huge-chapters.txt", "mimeType": "text/plain", "buffer": "\n".join(huge_parts).encode("utf-8")}
        page.locator("#fileInput").set_input_files(huge_payload)
        page.wait_for_function("!document.querySelector('#reader').classList.contains('hidden')", timeout=30000)
        page.wait_for_timeout(120)
        initial_new_book = read_anchor(page)
        if not initial_new_book or initial_new_book["index"] > 8:
            failures.append(f"opening a new long book didn't mount its start window: {initial_new_book}")
        if not page.locator("#prose .virtual-window").count():
            failures.append("the second large book didn't activate virtualization")

        # Focus Here in a chapter longer than the virtualization threshold must preserve
        # the chosen source passage even though Focus mode itself is windowed.
        page.evaluate("f => {document.documentElement.classList.add('instant-scroll'); window.scrollTo(0,(document.documentElement.scrollHeight-innerHeight)*f);}", 0.32)
        page.wait_for_timeout(130)
        huge_before = read_anchor(page)
        rect = page.locator("#reader").bounding_box()
        if rect:
            page.mouse.move(rect["x"] + rect["width"] + 18, 150)
            page.wait_for_timeout(100)
            if page.locator("#focusHereButton").evaluate("el => el.classList.contains('is-visible')"):
                page.locator("#focusHereButton").click(force=True)
                page.wait_for_timeout(180)
                if not page.locator("#prose .virtual-window").count():
                    failures.append("a >1,600-paragraph Focus-mode chapter wasn't virtualized")
                huge_focus = read_anchor(page)
                if huge_before and huge_focus and abs(huge_before["index"] - huge_focus["index"]) > 70:
                    failures.append(f"Focus Here lost the anchor in a huge chapter: {huge_before} -> {huge_focus}")
                if page.locator("#prose [data-reader-paragraph-index]").count() > 500:
                    failures.append("huge Focus mode rendered too many live paragraph nodes")
                page.locator("#exitFocus").click(force=True)
                page.wait_for_timeout(140)
                if not page.locator("#prose .virtual-window").count():
                    failures.append("exiting a virtualized Focus chapter didn't restore the virtual normal view")
                page.locator("#fileFocusBtn").click(force=True)
                page.wait_for_timeout(120)
                page.locator("#nextChapterBtn").click(force=True)
                page.wait_for_timeout(140)
                if "2 of 2" not in page.locator("#readerTitle").inner_text().lower():
                    failures.append(f"jumping to another large chapter failed: {page.locator('#readerTitle').inner_text()}")
                if page.locator("#prose [data-reader-paragraph-index]").count() > 500:
                    failures.append("chapter jump rendered an entire huge chapter into the DOM")
            else:
                failures.append("Focus Here wasn't available mid-way through the first huge chapter")
        else:
            failures.append("reader geometry unavailable during huge-chapter regression")

        if errors:
            failures.append("browser JavaScript errors: " + "; ".join(errors))
        browser.close()

    if failures:
        print("FAIL: virtualized reader browser regression")
        for failure in failures:
            print(" - " + failure)
        return 1
    print("PASS: 3,000+ paragraphs virtualized; random scrolling, tail mounting, Focus Here, full-text search, and Continue Reading all verified")
    print("Scroll anchors by fraction:", source_counts)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
