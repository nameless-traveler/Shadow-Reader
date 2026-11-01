#!/usr/bin/env python3
"""Optional browser-level Continue Reading regression test.

Usage:
  python3 tests/resume-browser-smoke.py
  python3 tests/resume-browser-smoke.py /path/to/novel.pdf

Requires Python Playwright and a Chromium browser. The PDF is converted with
Poppler when supplied, then the app's extraction endpoint is stubbed so this
smoke test can run without starting the local server. The reader UI, storage,
scroll tracking, button behavior, modal, and restore logic are real.
"""
from __future__ import annotations

import json
import subprocess
import sys
import shutil
from pathlib import Path

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    raise SystemExit("Install optional test dependency: python3 -m pip install playwright; then playwright install chromium")

ROOT = Path(__file__).resolve().parents[1]
HTML = (ROOT / "index.html").read_text(encoding="utf-8")


def make_book() -> str:
    blocks = ["Sample Novel: Continue Reading Regression Fixture", "An introductory note."]
    for chapter in range(1, 13):
        blocks.append(f"CHAPTER {chapter}: The Long Chapter {chapter}")
        for paragraph in range(1, 46):
            blocks.append(
                f"In chapter {chapter}, paragraph {paragraph}, the reader follows a long "
                "narrative through the city and its quiet streets. This deliberately lengthy "
                "paragraph ensures that the rendered document is tall enough for meaningful "
                "scroll positions, and provides a stable text anchor for restoration."
            )
    return "\n\n".join(blocks)


def pdf_text(path: Path) -> tuple[str, int]:
    result = subprocess.run(
        ["pdftotext", "-enc", "UTF-8", "-layout", str(path), "-"],
        check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    text = result.stdout.decode("utf-8", "replace")
    pages = sum(1 for page in text.split("\f") if page.strip())
    return text, pages


def main() -> int:
    sample_pdf = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else None
    if sample_pdf and not sample_pdf.is_file():
        raise SystemExit(f"PDF not found: {sample_pdf}")
    if sample_pdf:
        text, pages = pdf_text(sample_pdf)
        filename = sample_pdf.name
        file_payload = {"name": filename, "mimeType": "application/pdf", "buffer": b"%PDF mocked upload"}
    else:
        text, pages = make_book(), 12
        filename = "sample-novel.pdf"
        file_payload = {"name": filename, "mimeType": "application/pdf", "buffer": b"%PDF mocked upload"}

    text_json = json.dumps(text, ensure_ascii=False)
    failures: list[str] = []
    focus_same_point = 0
    end_of_focus_chapter = 0
    migrated_percent = None

    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(headless=True, executable_path=shutil.which("chromium") or shutil.which("chromium-browser") or None, args=["--no-sandbox", "--disable-dev-shm-usage"])
        except Exception as exc:
            raise SystemExit(f"Could not launch Chromium. Install it with `playwright install chromium`. Detail: {exc}")
        page = browser.new_page(viewport={"width": 1200, "height": 800})
        page_errors: list[str] = []
        page.on("pageerror", lambda error: page_errors.append(str(error)))
        page.set_content(HTML, wait_until="domcontentloaded")
        page.evaluate(f"""() => {{
          const store = {{}};
          Object.defineProperty(window, 'localStorage', {{ configurable: true, value: {{
            getItem(key) {{ return Object.prototype.hasOwnProperty.call(store, key) ? store[key] : null; }},
            setItem(key, value) {{ store[key] = String(value); }},
            removeItem(key) {{ delete store[key]; }},
            clear() {{ for (const key of Object.keys(store)) delete store[key]; }}
          }} }});
          window.__pdfFetchCalls = 0;
          window.fetch = async () => {{ window.__pdfFetchCalls++; return {{ ok: true, status: 200, json: async () => ({{ text: {text_json}, pages: {pages} }}) }}; }};
        }}""")

        def upload_direct() -> None:
            page.locator("#fileInput").set_input_files(file_payload)
            page.wait_for_function("!document.querySelector('#reader').classList.contains('hidden')", timeout=20_000)
            page.wait_for_timeout(700)

        upload_direct()
        # Simulate reaching roughly 40% in Normal mode.
        page.evaluate("document.documentElement.classList.add('instant-scroll'); const max = document.documentElement.scrollHeight - window.innerHeight; window.scrollTo({top: Math.max(6000, max * 0.40), behavior: 'auto'}); window.dispatchEvent(new Event('scroll'));")
        page.wait_for_timeout(800)
        normal_state_raw = page.evaluate("localStorage.getItem('shadowReaderProgressV1')")
        normal_store = json.loads(normal_state_raw or "{}")
        normal_key = next(iter(normal_store), "")
        normal_state = normal_store.get(normal_key, {})
        normal_furthest = round(float(normal_state.get("furthestProgressPercent", 0)))
        initial_toast_shown = "show" in (page.locator("#progressToast").get_attribute("class") or "").split()
        if not 25 <= normal_furthest <= 60:
            failures.append(f"Normal-mode progress should be near 40%, got {normal_furthest}% ({normal_state})")

        # Regression for the reported issue: return to the top, enter Focus mode,
        # revisit the very same source paragraph, and read to the bottom of that
        # chapter. The percent must stay anchored to original-book text position,
        # not add the chapter's local scroll ratio to the previous Normal percent.
        target_info = page.evaluate("""() => {
          const stateStore = JSON.parse(localStorage.getItem('shadowReaderProgressV1') || '{}');
          const key = Object.keys(stateStore)[0]; const state = stateStore[key] || {};
          const markers = Array.from(document.querySelectorAll('.chapter-opening[data-chapter-index][data-reader-paragraph-index]'));
          let targetChapter = 0;
          for (const marker of markers) {
            if (Number(marker.dataset.readerParagraphIndex) <= Number(state.paragraphIndex || 0)) targetChapter = Number(marker.dataset.chapterIndex) || 0;
          }
          const options = Array.from(document.querySelectorAll('#chapterOptions option')).map(option => option.value);
          return { key, state, targetChapter, targetValue: options[targetChapter] || '' };
        }""")
        # Walk back to the top; the saved furthest percentage must not regress.
        page.evaluate("window.scrollTo({top: 0, behavior: 'auto'}); window.dispatchEvent(new Event('scroll'))")
        page.wait_for_timeout(650)
        if round(float(page.locator('#readProgress').inner_text().replace('% reached', '').strip() or 0)) < normal_furthest:
            failures.append('returning to the top reduced furthest progress')
        page.evaluate("document.querySelector('#fileFocusBtn').click()")
        page.wait_for_timeout(250)
        if target_info.get('targetValue'):
            page.locator('#chapterSelect').fill(target_info['targetValue'])
            page.locator('#chapterSelect').press('Enter')
            page.wait_for_timeout(250)
        paragraph_index = target_info.get('state', {}).get('paragraphIndex')
        anchor_top = float(target_info.get('state', {}).get('anchorTop', 150))
        if paragraph_index is not None:
            positioned = page.evaluate("""({paragraphIndex, anchorTop}) => {
              const wanted = Number(paragraphIndex);
              let el = document.querySelector(`[data-reader-paragraph-index="${wanted}"]`);
              if (!el) {
                const candidates = Array.from(document.querySelectorAll('[data-reader-paragraph-index]'));
                el = candidates.find(item => Number(item.dataset.readerParagraphIndex) >= wanted) || null;
              }
              if (!el) return false;
              const y = el.getBoundingClientRect().top + window.scrollY - Number(anchorTop || 150);
              window.scrollTo({top: Math.max(0, y), behavior: 'auto'});
              window.dispatchEvent(new Event('scroll'));
              return true;
            }""", {"paragraphIndex": paragraph_index, "anchorTop": anchor_top})
            if not positioned:
                failures.append(f'could not revisit original source paragraph {paragraph_index} in Focus mode')
        page.wait_for_timeout(800)
        focus_same_point = round(float(page.evaluate("JSON.parse(localStorage.getItem('shadowReaderProgressV1') || '{}')[Object.keys(JSON.parse(localStorage.getItem('shadowReaderProgressV1') || '{}'))[0]].furthestProgressPercent || 0")))
        if focus_same_point > normal_furthest + 5:
            failures.append(f"revisiting the same passage inflated progress from {normal_furthest}% to {focus_same_point}% in Focus mode")
        page.evaluate("const max = document.documentElement.scrollHeight - window.innerHeight; window.scrollTo({top: max, behavior: 'auto'}); window.dispatchEvent(new Event('scroll'))")
        page.wait_for_timeout(850)
        end_of_focus_chapter = round(float(page.evaluate("JSON.parse(localStorage.getItem('shadowReaderProgressV1') || '{}')[Object.keys(JSON.parse(localStorage.getItem('shadowReaderProgressV1') || '{}'))[0]].furthestProgressPercent || 0")))
        if end_of_focus_chapter > normal_furthest + 18 or end_of_focus_chapter >= 80:
            failures.append(f"scrolling to the end of one Focus-mode chapter incorrectly looks like whole-book progress: started {normal_furthest}%, now {end_of_focus_chapter}%")
        # Return to Normal mode so the regular open-file/resume path can be tested too.
        page.locator('#exitFocus').click(timeout=10_000)
        page.wait_for_timeout(700)

        # pagehide runs synchronously in browsers when the tab/window is left.
        page.evaluate("window.dispatchEvent(new Event('pagehide'))")
        saved_raw = page.evaluate("localStorage.getItem('shadowReaderProgressV1')")
        saved_store = json.loads(saved_raw or "{}")
        saved_state = saved_store.get(next(iter(saved_store), ""), {})
        if int(saved_state.get("scrollY", 0)) < 1000:
            failures.append(f"progress was not saved at a meaningful position: {saved_state}")
        if float(saved_state.get("furthestProgressPercent", 0)) < 10:
            failures.append(f"furthest reading progress was not persisted: {saved_state}")
        if saved_state.get('progressModel') != 'source-text-v2':
            failures.append('saved reading state did not use the canonical source-text progress model')
        saved_furthest = round(float(saved_state.get("furthestProgressPercent", 0)))
        if page.locator("#readProgress").inner_text().strip() != f"{saved_furthest}% reached":
            failures.append("progress indicator does not show the furthest reached position")
        if normal_furthest >= 10 and not initial_toast_shown:
            failures.append("the milestone toast did not appear after reaching a new 10% milestone")

        # Clicking the top toolbar from deep in the text scrolls the document up.
        # This used to overwrite the existing progress with a zero-position record.
        with page.expect_file_chooser() as chooser_info:
            page.locator("#openBtn").click(timeout=10_000)
        chooser_info.value.set_files(file_payload)
        page.wait_for_timeout(900)
        dialog_class = page.locator("#resumeDialog").get_attribute("class") or ""
        after_raw = page.evaluate("localStorage.getItem('shadowReaderProgressV1')")
        after_store = json.loads(after_raw or "{}")
        after_state = after_store.get(next(iter(after_store), ""), {})
        if "show" not in dialog_class.split():
            failures.append(f"Continue reading prompt did not appear after reopening; dialog class={dialog_class!r}")
        if int(after_state.get("scrollY", 0)) < 1000:
            failures.append(f"the toolbar/open-file interaction overwrote the saved position: before={saved_state}; after={after_state}")
        if round(float(after_state.get("furthestProgressPercent", 0))) != saved_furthest:
            failures.append("furthest reading progress changed after returning to the top")

        if "show" in dialog_class.split():
            page.locator("#resumeBtn").click()
            page.wait_for_timeout(650)
            restored_y = page.evaluate("window.scrollY")
            if restored_y < 1000:
                failures.append(f"Continue reading did not restore the saved position; got scrollY={restored_y}; saved={after_state}")

            # Simulate a saved record from the previous release: its scroll-height
            # percentage is corrupt (100%), but the original source paragraph anchor
            # still points to the actual reading location. Reopen after clearing the
            # current in-memory book so openFile cannot first normalize it in-place.
            page.locator('#clearBtn').click()
            page.wait_for_timeout(200)
            legacy_payload = page.evaluate("""() => {
              const store = JSON.parse(localStorage.getItem('shadowReaderProgressV1') || '{}');
              const key = Object.keys(store)[0];
              const state = store[key];
              if (!state) return null;
              delete state.progressModel;
              state.focusMode = true;
              state.scrollRatio = 0.35;
              state.furthestProgressPercent = 100;
              state.progressPercent = 100;
              store[key] = state;
              localStorage.setItem('shadowReaderProgressV1', JSON.stringify(store));
              return { key, paragraphIndex: state.paragraphIndex };
            }""")
            page.locator('#fileInput').set_input_files(file_payload)
            page.wait_for_timeout(850)
            migration_dialog = page.locator('#resumeDialog').get_attribute('class') or ''
            migration_details = page.locator('#resumeDialogDetails').inner_text()
            if legacy_payload and 'show' not in migration_dialog.split():
                failures.append('legacy saved reading location did not offer Continue Reading after reopening')
            if '100%' in migration_details or ('through the document' in migration_details and '100' in migration_details):
                failures.append(f'legacy inflated 100% progress was not migrated from the source anchor: {migration_details!r}')
            if 'show' in migration_dialog.split():
                page.locator('#resumeBtn').click()
                page.wait_for_timeout(650)
                migrated_store = json.loads(page.evaluate("localStorage.getItem('shadowReaderProgressV1')") or '{}')
                migrated_state = migrated_store.get(legacy_payload['key'] if legacy_payload else next(iter(migrated_store), ''), {})
                if migrated_state.get('progressModel') != 'source-text-v2':
                    failures.append('legacy reading progress was not rewritten using source-text-v2 after restoration')
                migrated_percent = round(float(migrated_state.get('furthestProgressPercent', 0)))
                if migrated_percent >= 80:
                    failures.append(f'legacy inflated progress stayed near completion after migration: {migrated_percent}%')
                if 'focus-mode' in (page.locator('body').get_attribute('class') or '').split():
                    page.locator('#exitFocus').click(timeout=10_000)
                    page.wait_for_timeout(450)

            # Escape is a common way to dismiss a dialog. It must not silently throw
            # away the saved location; the safe behavior is to continue from it.
            page.locator("#openBtn").click(timeout=10_000)
            page.locator("#fileInput").set_input_files(file_payload)
            page.wait_for_timeout(750)
            escape_dialog = page.locator("#resumeDialog").get_attribute("class") or ""
            if "show" not in escape_dialog.split():
                failures.append("reopening a book with a saved location did not show the resume dialog before Escape testing")
            else:
                # The aria-modal resume prompt should keep keyboard focus inside it.
                page.locator("#resumeBtn").focus()
                page.keyboard.press("Tab")
                first_focus_id = page.evaluate("document.activeElement && document.activeElement.id")
                page.keyboard.press("Shift+Tab")
                last_focus_id = page.evaluate("document.activeElement && document.activeElement.id")
                if first_focus_id != "startOverBtn" or last_focus_id != "resumeBtn":
                    failures.append(f"resume dialog did not trap keyboard focus correctly: Tab={first_focus_id!r}, Shift+Tab={last_focus_id!r}")
                before_escape = json.loads(page.evaluate("localStorage.getItem('shadowReaderProgressV1')") or "{}")
                before_escape_state = before_escape.get(legacy_payload['key'] if legacy_payload else next(iter(before_escape), ''), {})
                page.keyboard.press("Escape")
                page.wait_for_timeout(700)
                after_escape_dialog = page.locator("#resumeDialog").get_attribute("class") or ""
                escaped_y = page.evaluate("window.scrollY")
                after_escape = json.loads(page.evaluate("localStorage.getItem('shadowReaderProgressV1')") or "{}")
                after_escape_state = after_escape.get(legacy_payload['key'] if legacy_payload else next(iter(after_escape), ''), {})
                if "show" in after_escape_dialog.split():
                    failures.append("Escape did not resolve the resume dialog")
                if escaped_y < 1000:
                    failures.append(f"Escape did not restore the saved reading position: scrollY={escaped_y}")
                if float(after_escape_state.get("furthestProgressPercent", 0)) < 10:
                    failures.append("Escape unexpectedly reset meaningful saved reading progress")
                if before_escape_state.get("paragraphIndex") is not None and after_escape_state.get("paragraphIndex") is None:
                    failures.append("Escape discarded the stable source-paragraph anchor")

            # Explicit reset should replace the saved position/progress so the next
            # open starts at the beginning rather than using either legacy or v2 data.
            # Set the hidden file input directly because Escape correctly restores the
            # prior mode, which may be Focus mode (where the top Open control is hidden).
            page.locator("#fileInput").set_input_files(file_payload)
            page.wait_for_timeout(750)
            if "show" in (page.locator("#resumeDialog").get_attribute("class") or "").split():
                page.locator("#startOverBtn").click()
                page.wait_for_timeout(200)
                reset_store = json.loads(page.evaluate("localStorage.getItem('shadowReaderProgressV1')") or '{}')
                reset_state = reset_store.get(legacy_payload['key'] if legacy_payload else next(iter(reset_store), ''), {})
                if round(float(reset_state.get('furthestProgressPercent', 0))) > 2:
                    failures.append(f'Start from the beginning left a nonzero progress value: {reset_state.get("furthestProgressPercent")}%')

            # A failed attempt to open another file must not make the still-rendered
            # current book look as though it disappeared; plain text must also open
            # without ever calling the PDF extraction endpoint.
            existing_name = page.locator("#fileName").inner_text()
            fetches_before_text = page.evaluate("window.__pdfFetchCalls")
            page.locator("#fileInput").set_input_files({"name": "too-short.txt", "mimeType": "text/plain", "buffer": b"too short"})
            page.wait_for_timeout(250)
            if page.locator("#reader").evaluate("el => el.classList.contains('hidden')"):
                failures.append("a failed short-text import unexpectedly hid the currently open book")
            if page.locator("#fileName").inner_text() != existing_name:
                failures.append("a failed import overwrote the name of the still-open document")
            if "previous document is still open" not in page.locator("#statusText").inner_text().lower():
                failures.append("a failed replacement did not explain that the previous document remains open")

            txt = ("A Plain Text Reading Fixture\n\nCHAPTER 1: The Beginning\n\n"
                   + "This plain text document should open locally without PDF extraction. " * 5
                   + "\n\nCHAPTER 2: The Next Step\n\n"
                   + "The second chapter confirms that normal text parsing still works. " * 5)
            page.locator("#fileInput").set_input_files({"name": "plain-text-test.txt", "mimeType": "text/plain", "buffer": txt.encode("utf-8")})
            page.wait_for_timeout(500)
            if page.locator("#reader").evaluate("el => el.classList.contains('hidden')"):
                failures.append("a valid .txt file did not open in the reading view")
            if page.locator("#fileName").inner_text() != "plain-text-test.txt":
                failures.append("the valid .txt file name was not applied")
            if "This plain text document should open locally" not in page.locator("#prose").inner_text():
                failures.append("plain-text content did not reach the rendered prose")
            if page.evaluate("window.__pdfFetchCalls") != fetches_before_text:
                failures.append("opening a .txt file unnecessarily called the PDF extraction endpoint")

        if page_errors:
            failures.append("browser JavaScript errors: " + "; ".join(page_errors))
        browser.close()

    if failures:
        print("FAIL: Continue Reading browser smoke test")
        for failure in failures:
            print(" -", failure)
        return 1
    suffix = f" using {sample_pdf.name}" if sample_pdf else " using a generated 12-chapter book"
    print("PASS: resume, modal keyboard trap, safe Escape, legacy migration, explicit reset, failed-import recovery, and plain-text import" + suffix)
    print(f"Cross-mode progress regression: Normal {normal_furthest}% → same Focus passage {focus_same_point}% → end of that Focus chapter {end_of_focus_chapter}%.")
    if migrated_percent is not None:
        print(f"Legacy inflated 100% migration: recalculated to {migrated_percent}% from the saved chapter/position.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
