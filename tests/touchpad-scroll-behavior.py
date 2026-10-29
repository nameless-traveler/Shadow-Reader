#!/usr/bin/env python3
"""Regression test for native scroll anchoring fighting touchpad-like input.

Uses a generated 8,000-paragraph text novel and streams small wheel deltas through
Chromium. This is a deterministic approximation of touchpad input (not physical
hardware inertia), intended to catch scroll-position corrections caused by virtual
spacer changes.
"""
from pathlib import Path
import shutil
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
HTML = (ROOT / "index.html").read_text(encoding="utf-8")
COUNT = 8000
PARAGRAPH = (
    "The reader moved along the passage with quiet focus, noticing the old stone "
    "bridge and the winter mist over the river. A small detail at the edge of the "
    "scene gave the traveler a reason to keep going."
)
TEXT = "Touchpad scroll regression fixture\n\n" + "\n\n".join(
    f"Paragraph {i}. {PARAGRAPH}" for i in range(COUNT)
)
PAYLOAD = {
    "name": "touchpad-scroll-regression.txt",
    "mimeType": "text/plain",
    "buffer": TEXT.encode("utf-8"),
}

with sync_playwright() as p:
    browser = p.chromium.launch(
        headless=True,
        executable_path=shutil.which("chromium") or shutil.which("chromium-browser") or None,
        args=["--no-sandbox", "--disable-dev-shm-usage"],
    )
    page = browser.new_page(viewport={"width": 1366, "height": 768})
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.set_content(HTML, wait_until="domcontentloaded")
    page.locator("#fileInput").set_input_files(PAYLOAD)
    page.wait_for_function(
        "!document.querySelector('#reader').classList.contains('hidden')", timeout=120_000
    )
    page.wait_for_timeout(300)
    assert page.locator("#prose.virtualized-reader").count() == 1, "large novel should use virtualization"
    assert page.evaluate("getComputedStyle(document.querySelector('#prose')).overflowAnchor") == "none", \
        "virtualized prose must disable native anchoring that fights touchpad gestures"

    # Instrument app-level scrollTo calls after initial opening. Ordinary user scroll
    # must not be redirected by per-window corrections.
    page.evaluate("""() => {
      const nativeScrollTo = window.scrollTo.bind(window);
      window.__touchpadTest = { programmaticScrollCalls: 0 };
      window.scrollTo = (...args) => {
        window.__touchpadTest.programmaticScrollCalls++;
        return nativeScrollTo(...args);
      };
    }""")
    start_y = page.evaluate("scrollY")
    start_errors = len(errors)
    for _ in range(20):
        page.mouse.wheel(0, 300)
        page.wait_for_timeout(30)
    down_y = page.evaluate("scrollY")
    down_calls = page.evaluate("window.__touchpadTest.programmaticScrollCalls")
    assert 5_300 <= down_y - start_y <= 6_700, \
        f"downward input was amplified or swallowed: expected ~6000 px, got {down_y-start_y:.0f}px"
    assert down_calls == 0, f"normal scroll triggered {down_calls} programmatic scroll corrections"

    for _ in range(5):
        page.mouse.wheel(0, -260)
        page.wait_for_timeout(30)
    up_y = page.evaluate("scrollY")
    assert 1_050 <= down_y - up_y <= 1_550, \
        f"reverse input did not move upward by the expected amount: {down_y-up_y:.0f}px"
    assert len(errors) == start_errors, f"browser errors during scroll: {errors}"
    mounted = page.locator("#prose .virtual-window > *").count()
    assert mounted < 100, f"virtualized DOM grew unexpectedly: {mounted} items mounted"
    browser.close()

print(
    "PASS: touchpad-like 8k-paragraph scroll follows input without native anchor jumps; "
    f"down={down_y-start_y:.0f}px (expected ~6000), up={down_y-up_y:.0f}px "
    f"(expected ~1300), 0 scrollTo corrections, {mounted} mounted items."
)
