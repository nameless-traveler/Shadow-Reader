#!/usr/bin/env node
'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const html = fs.readFileSync(path.resolve(__dirname, '..', 'index.html'), 'utf8');
const checks = [];
function test(name, fn) { fn(); checks.push(name); }

test('uses a minimal open-book icon rather than the scan glyph', () => {
  assert.match(html, /id="focusHereButton"[\s\S]*?<svg viewBox="0 0 24 24"/);
  assert.doesNotMatch(html, /id="focusHereButton"[\s\S]*?<icon name="scan-text"/);
});
test('label and tooltip explain the intended action without covering the reading text', () => {
  assert.match(html, /aria-label="Open this passage in Focus mode"/);
  assert.match(html, /left:calc\(100% \+ 8px\); right:auto/);
  assert.match(html, /--focus-tooltip-max-width/);
  assert.equal(html.match(/<span class="focus-here-tooltip"[^>]*>([^<]*)<\/span>/)?.[1], 'Open this passage in Focus mode');
});
test('side action requires detected chapters and a usable reading margin', () => {
  assert.match(html, /function shouldOfferFocusHere\(\)/);
  assert.match(html, /window\.innerWidth - readerRect\.right < 145/);
  assert.match(html, /proseRect\.top > guideY \+ 35/);
});
test('margin interaction is intentional, bounded to reading guide, and delayed on hide', () => {
  assert.match(html, /function pointerIsInReadingMargin\(event\)/);
  assert.match(html, /window\.addEventListener\('mouseleave', scheduleFocusHereHide\)/);
  assert.match(html, /focusHereButton\.addEventListener\('focus'/);
  assert.match(html, /focusHereButton\.addEventListener\('blur', scheduleFocusHereHide\)/);
  assert.match(html, /Math\.abs\(event\.clientY - guideY\) <= 48/);
  assert.match(html, /\}, 520\)/);
});
test('button is absent in Focus mode, print, and narrow mobile layouts', () => {
  assert.match(html, /\.focus-mode \.focus-here-control \{ display:none !important; \}/);
  assert.match(html, /\.focus-here-control \{ display:none; \}/);
  assert.match(html, /reader-footer, \.focus-toolbar, \.focus-here-control \{ display:none !important; \}/);
});
test('start/end primary Focus actions suppress duplicate side control', () => {
  assert.match(html, /if \(nearStart && elementIntersectsViewport\(fileFocusBtn\)\) return false/);
  assert.match(html, /if \(nearEnd && elementIntersectsViewport\(\$\('#focusBtn'\)\)\) return false/);
});
test('click maps the source paragraph to its owning chapter', () => {
  assert.match(html, /function openFocusAtCurrentPassage\(\)/);
  assert.match(html, /getChapterIndexForParagraph\(sourceIndex\)/);
  assert.match(html, /data-reader-paragraph-index=\"\$\{sourceIndex\}\"/);
  assert.match(html, /targetPoint - readingGuideY\(\)/);
  assert.match(html, /const extraTailRoom = Math\.ceil/);
  assert.match(html, /focusTransitionInProgress = true/);
});
test('Focus-here is removed from the tab order until the passage is eligible', () => {
  assert.match(html, /id="focusHereButton"[^>]*tabindex="-1"/);
  assert.match(html, /function refreshFocusHereTabStop\(\)/);
  assert.match(html, /focusHereButton\.tabIndex = available \? 0 : -1/);
});
test('reduced-motion preference disables smooth programmatic scrolling', () => {
  assert.match(html, /function preferredScrollBehavior\(\)/);
  assert.match(html, /prefers-reduced-motion: reduce/);
  assert.match(html, /behavior: preferredScrollBehavior\(\)/);
});
test('transition updates progress using source-text model and saves the passage', () => {
  assert.match(html, /updateScrollProgress\(\);/);
  assert.match(html, /scheduleReadingSave\(\);/);
  assert.match(html, /const READING_PROGRESS_MODEL = 'source-text-v2'/);
});
console.log(`PASS: ${checks.length} Focus-here feature checks`);
