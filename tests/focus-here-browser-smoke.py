#!/usr/bin/env python3
"""Browser-level test for the discreet Focus-here margin control.

Runs the actual reader UI with a generated book and mocked local PDF extraction.
Requires Python Playwright and Chromium.
"""
from __future__ import annotations
import json
import shutil
import subprocess
import sys
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
HTML = (ROOT / "index.html").read_text(encoding="utf-8")


def make_book() -> str:
    blocks = ["Sample Novel: Focus Here Regression", "Opening note before the story starts."]
    for chapter in range(1, 13):
        blocks.append(f"CHAPTER {chapter}: The Long Chapter {chapter}")
        for paragraph in range(1, 46):
            blocks.append(
                f"Chapter {chapter}, paragraph {paragraph}. A winding path passes the old stone wall, "
                "the moonlit river and the quiet village beyond. This long test paragraph ensures "
                "stable reading positions through a sufficiently tall novel and realistic wrapping. "
                "The traveler pauses, considers the next step, and continues deeper into the story."
            )
    return "\n\n".join(blocks)


def main() -> int:
    sample_pdf = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else None
    if sample_pdf and not sample_pdf.is_file():
        raise SystemExit(f"PDF not found: {sample_pdf}")
    if sample_pdf:
        result = subprocess.run(
            ["pdftotext", "-enc", "UTF-8", "-layout", str(sample_pdf), "-"],
            check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        text = result.stdout.decode("utf-8", "replace")
        filename = sample_pdf.name
        file_buffer = sample_pdf.read_bytes()[:1024]
        pages = sum(1 for chunk in text.split("\f") if chunk.strip())
    else:
        text = make_book()
        filename = "focus-here-test.pdf"
        file_buffer = b"%PDF mocked"
        pages = 12
    payload = json.dumps(text, ensure_ascii=False)
    failures: list[str] = []
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            executable_path=shutil.which("chromium") or shutil.which("chromium-browser") or None,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        page = browser.new_page(viewport={"width": 1200, "height": 800})
        page_errors: list[str] = []
        page.on("pageerror", lambda err: page_errors.append(str(err)))
        page.set_content(HTML, wait_until="domcontentloaded")
        page.evaluate(f"""() => {{
          const store = {{}};
          Object.defineProperty(window, 'localStorage', {{ configurable:true, value: {{
            getItem(k) {{ return Object.prototype.hasOwnProperty.call(store,k) ? store[k] : null; }},
            setItem(k,v) {{ store[k] = String(v); }}, removeItem(k) {{ delete store[k]; }}, clear() {{ for(const k of Object.keys(store)) delete store[k]; }}
          }} }});
          window.fetch = async () => ({{ ok:true, status:200, json:async() => ({{ text:{payload}, pages:{pages} }}) }});
        }}""")
        page.locator("#fileInput").set_input_files({"name":filename,"mimeType":"application/pdf","buffer":file_buffer})
        page.wait_for_function("!document.querySelector('#reader').classList.contains('hidden')", timeout=20_000)
        page.wait_for_timeout(500)

        button = page.locator("#focusHereButton")
        if button.get_attribute("aria-label") != "Open this passage in Focus mode":
            failures.append("Focus-here control has an incorrect or missing accessible label")
        if button.locator(".focus-here-tooltip").text_content() != "Open this passage in Focus mode":
            failures.append("Focus-here tooltip is missing or incorrect")
        if "is-visible" in (button.get_attribute("class") or "").split():
            failures.append("Focus-here icon was visible before deliberate margin interaction")
        if button.get_attribute("tabindex") != "-1":
            failures.append("Focus-here control should not be a hidden keyboard tab stop before a passage is eligible")

        guide_y = page.evaluate("Math.min(155, Math.max(80, window.innerHeight * 0.23))")
        initial_rect = page.locator("#reader").bounding_box()
        page.mouse.move(initial_rect["x"] + initial_rect["width"] + 40, guide_y)
        page.wait_for_timeout(100)
        if "is-visible" in (button.get_attribute("class") or "").split():
            failures.append("Focus-here control appeared beside page chrome before prose reached the reading guide")

        # Place the same passage near the reading guide with instant scrolling to avoid
        # making the result dependent on an in-flight smooth-scroll animation.
        page.evaluate("""() => {
          document.documentElement.classList.add('instant-scroll');
          const max = document.documentElement.scrollHeight - window.innerHeight;
          window.scrollTo({top: max * 0.38, behavior:'auto'});
          window.dispatchEvent(new Event('scroll'));
        }""")
        page.wait_for_timeout(500)
        before = page.evaluate("""() => {
          const guideY = Math.min(155, Math.max(80, window.innerHeight * 0.23));
          const readerRect = document.querySelector('#reader').getBoundingClientRect();
          const items = [...document.querySelectorAll('#prose [data-reader-item-index][data-reader-paragraph-index]')];
          let anchor = items[0] || null;
          for (const item of items) { if (item.getBoundingClientRect().top <= guideY) anchor = item; else break; }
          if (!anchor) return null;
          const rect = anchor.getBoundingClientRect();
          const sourceIndex = Number(anchor.dataset.readerParagraphIndex);
          const fraction = rect.height > 0 ? Math.max(0, Math.min(1, (guideY - rect.top) / rect.height)) : 0;
          // A detected chapter title is not repeated inside Focus mode. In that case the
          // expected landing point is the first real paragraph after the title.
          let targetSourceIndex = sourceIndex;
          let targetFraction = fraction;
          if (anchor.classList.contains('chapter-opening')) {
            const nextParagraph = [...document.querySelectorAll('#prose p[data-reader-paragraph-index]')]
              .find(item => Number(item.dataset.readerParagraphIndex) > sourceIndex);
            if (nextParagraph) { targetSourceIndex = Number(nextParagraph.dataset.readerParagraphIndex); targetFraction = 0; }
          }
          const markers = [...document.querySelectorAll('.chapter-opening[data-chapter-index][data-reader-paragraph-index]')];
          let chapterMarker = markers[0] || null;
          for (const marker of markers) { if (Number(marker.dataset.readerParagraphIndex) <= sourceIndex) chapterMarker = marker; else break; }
          const store = JSON.parse(localStorage.getItem('quietReaderProgressV1') || '{}');
          const state = store[Object.keys(store)[0]] || {};
          return { readerRight: readerRect.right, guideY, sourceIndex, fraction, targetSourceIndex, targetFraction, anchorText: anchor.textContent,
            expectedTitle: chapterMarker ? chapterMarker.querySelector('.chapter-opening-title').textContent : '',
            beforePercent: parseInt(document.querySelector('#readProgress').textContent, 10) || Number(state.furthestProgressPercent) || 0 };
        }""")
        if not before:
            failures.append("Could not establish the current source-paragraph reading anchor")
            browser.close()
            return 1
        if not (before["readerRight"] < 1140):
            failures.append("Test viewport did not leave enough right-side reading margin")
        # Moving into the text itself should not reveal it; moving toward the right-side
        # reading margin at the fixed guide should reveal it.
        page.mouse.move(before["readerRight"] - 15, before["guideY"])
        page.wait_for_timeout(80)
        if "is-visible" in (button.get_attribute("class") or "").split():
            failures.append("Focus-here control appeared when the pointer was inside the text area")
        page.mouse.move(before["readerRight"] + 38, before["guideY"])
        page.wait_for_timeout(150)
        if "is-visible" not in (button.get_attribute("class") or "").split():
            failures.append("Focus-here control did not appear after deliberate right-margin interaction")
        else:
            if not button.is_enabled():
                failures.append("Focus-here control is disabled despite detected chapters")
            # Tooltip should be available when the pointer hovers the visible icon.
            if not button.locator('.focus-here-tooltip').is_visible():
                failures.append("Tooltip did not appear when the icon was hovered")

        # Leaving the margin should make the icon disappear after a short grace period.
        page.mouse.move(before["readerRight"] - 30, before["guideY"])
        page.wait_for_timeout(650)
        if "is-visible" in (button.get_attribute("class") or "").split():
            failures.append("Focus-here control stayed visible after the pointer left the margin")

        # Re-enter the margin and click; the exact source paragraph/fraction should be
        # carried into the chapter-only Focus view, rather than restarting at the top.
        page.mouse.move(before["readerRight"] + 38, before["guideY"])
        page.wait_for_timeout(120)
        if "is-visible" in (button.get_attribute("class") or "").split():
            button.click()
            page.wait_for_timeout(700)
            transition = page.evaluate("""({sourceIndex, fraction, targetSourceIndex, targetFraction, guideY}) => {
              const exact = document.querySelector(`#prose [data-reader-paragraph-index="${targetSourceIndex}"]`);
              const title = document.querySelector('#documentHeading').textContent;
              const focus = document.body.classList.contains('focus-mode');
              const store = JSON.parse(localStorage.getItem('quietReaderProgressV1') || '{}');
              const state = store[Object.keys(store)[0]] || {};
              if (!exact) return {focus, exact:false, title, percent:Number(state.furthestProgressPercent)||0};
              const rect = exact.getBoundingClientRect();
              const point = rect.top + rect.height * targetFraction;
              return {focus, exact:true, title, point, guideY,
                percent:Number(state.furthestProgressPercent)||0, savedParagraphIndex:state.paragraphIndex};
            }""", {"sourceIndex":before["sourceIndex"], "fraction":before["fraction"], "targetSourceIndex":before["targetSourceIndex"], "targetFraction":before["targetFraction"], "guideY":before["guideY"]})
            if not transition["focus"]:
                failures.append("Clicking Focus-here did not enter Focus mode")
            if not transition["exact"]:
                failures.append(f"Focus mode did not render the same original source paragraph: {transition}")
            elif abs(float(transition["point"]) - float(before["guideY"])) > 22:
                failures.append(f"Same source passage was not aligned to the reading guide: {transition}")
            if transition.get("title") != before["expectedTitle"]:
                failures.append(f"Focus-here opened the wrong chapter: expected {before['expectedTitle']!r}, got {transition.get('title')!r}")
            if transition["percent"] > before["beforePercent"] + 3:
                failures.append(f"Switching modes inflated furthest progress {before['beforePercent']}% → {transition['percent']}%")
            if "is-visible" in (button.get_attribute("class") or "").split():
                failures.append("Focus-here control remained visible inside Focus mode")
        else:
            failures.append("Focus-here control was not available for the click/anchor test")

        # Restore Normal mode, go to the end, and ensure the side action doesn't compete
        # with the existing footer Focus-mode button when it is in view.
        if page.locator("body").evaluate("el => el.classList.contains('focus-mode')"):
            page.locator('#exitFocus').click()
            page.wait_for_timeout(350)
        page.evaluate("""() => { document.documentElement.classList.add('instant-scroll');
          window.scrollTo({top:document.documentElement.scrollHeight-window.innerHeight, behavior:'auto'});
          window.dispatchEvent(new Event('scroll')); }""")
        page.wait_for_timeout(250)
        end = page.evaluate("""() => ({
          right:document.querySelector('#reader').getBoundingClientRect().right,
          guideY:Math.min(155,Math.max(80,window.innerHeight*.23)),
          footerVisible:(() => {const r=document.querySelector('#focusBtn').getBoundingClientRect();return r.bottom>0&&r.top<innerHeight;})()
        })""")
        page.mouse.move(end["right"] + 38, end["guideY"])
        page.wait_for_timeout(150)
        end_visible = "is-visible" in (button.get_attribute("class") or "").split()
        if not end["footerVisible"]:
            failures.append("Could not bring the existing footer Focus button into view for the end-duplicate regression")
        elif end_visible:
            failures.append("Side Focus-here control duplicated the footer Focus button at the end of the novel")

        # Honor the OS/browser reduced-motion preference for scripted chapter and
        # mode changes, while retaining smooth scrolling for users who allow motion.
        page.evaluate("""() => {
          window.__quietReaderScrollBehaviors = [];
          const originalScrollTo = window.scrollTo.bind(window);
          window.scrollTo = function (options, y) {
            if (options && typeof options === 'object') window.__quietReaderScrollBehaviors.push(options.behavior || 'auto');
            return originalScrollTo(options, y);
          };
        }""")
        page.emulate_media(reduced_motion="reduce")
        page.locator("#fileFocusBtn").evaluate("el => el.click()")
        page.wait_for_timeout(100)
        reduced_calls = page.evaluate("window.__quietReaderScrollBehaviors.slice()")
        if "auto" not in reduced_calls:
            failures.append(f"reduced-motion preference did not switch scripted scrolling to auto: {reduced_calls!r}")
        page.emulate_media(reduced_motion="no-preference")
        page.locator("#exitFocus").click(timeout=10_000)
        page.wait_for_timeout(150)
        normal_calls = page.evaluate("window.__quietReaderScrollBehaviors.slice()")
        if "smooth" not in normal_calls:
            failures.append(f"normal motion preference did not retain smooth scrolling: {normal_calls!r}")

        if page_errors:
            failures.append("Browser JavaScript errors: " + "; ".join(page_errors))
        browser.close()

    if failures:
        print("FAIL: Focus-here browser smoke test")
        for failure in failures:
            print(" - " + failure)
        return 1
    print("PASS: Focus-here interaction, source passage/progress preservation, duplicate-control avoidance, and reduced-motion behavior.")
    suffix = f" using {sample_pdf.name}" if sample_pdf else " using the generated 12-chapter fixture"
    print(f"Passage anchor: source paragraph {before['targetSourceIndex']} ({before['expectedTitle']}); progress remained mode-independent{suffix}.")
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
