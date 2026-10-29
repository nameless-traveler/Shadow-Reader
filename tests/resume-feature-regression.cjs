#!/usr/bin/env node
'use strict';
// Regression checks for Continue Reading state compatibility with evolving chapter detection.
// These tests exercise the chapter-identity resolver and assert the UI/save/restore wiring is present.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const html = fs.readFileSync(path.resolve(__dirname, '..', 'index.html'), 'utf8');
const checks = [];
function test(name, fn) { fn(); checks.push(name); }

const requiredFragments = [
  ['resume dialog', 'id="resumeDialog"'],
  ['Continue reading action', 'id="resumeBtn"'],
  ['Start from the beginning action', 'id="startOverBtn"'],
  ['local saved state store', "const READING_PROGRESS_KEY = 'quietReaderProgressV1'"],
  ['canonical source-text progress model', "const READING_PROGRESS_MODEL = 'source-text-v2'"],
  ['source paragraph offsets for mode-independent progress', 'function buildSourceParagraphOffsets(paragraphs)'],
  ['focus-mode source index preservation', 'bodySourceIndices'],
  ['automatic save on page exit', "window.addEventListener('pagehide', saveReadingState)"],
  ['automatic save on tab hide', "document.addEventListener('visibilitychange'"],
  ['stable source-paragraph anchors', 'data-reader-paragraph-index'],
  ['reading position restore action', 'function restoreReadingState(state)'],
  ['resume prompt on re-open', 'showResumeDialog(savedReadingState)'],
  ['legacy state fallback', 'Backward compatibility with reading positions saved by earlier builds.'],
  ['cached ordered reader anchors', 'let renderedReaderItems = []'],
  ['binary-search reading position', 'while (low <= high)'],
  ['map-based chapter-start lookup', 'new Map(chapters.map((chapter, index) => [chapter.start, index]))']
];
for (const [name, fragment] of requiredFragments) {
  test(name, () => assert.ok(html.includes(fragment), `Missing ${name}: ${fragment}`));
}

function extractFunction(name) {
  const escaped = name.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const re = new RegExp(`      function ${escaped}\\([^\\n]*\\) \\{[\\s\\S]*?\\n      \\}`, 'm');
  const match = html.match(re);
  assert.ok(match, `Could not extract ${name} from index.html`);
  return match[0];
}
const helpers = extractFunction('stateHasMeaningfulProgress') + '\n'
  + extractFunction('shouldPreserveMeaningfulProgress') + '\n'
  + extractFunction('normalizedResumeTitle') + '\n'
  + extractFunction('resolveSavedChapterIndex') + '\n'
  + extractFunction('buildSourceParagraphOffsets') + '\n'
  + extractFunction('clampPercent') + '\n'
  + extractFunction('sourceProgressPercent') + '\n'
  + extractFunction('estimateSavedSourceProgress') + '\n'
  + 'this.stateHasMeaningfulProgress = stateHasMeaningfulProgress;\n'
  + 'this.shouldPreserveMeaningfulProgress = shouldPreserveMeaningfulProgress;\n'
  + 'this.resolveSavedChapterIndex = resolveSavedChapterIndex;\n'
  + 'this.buildSourceParagraphOffsets = buildSourceParagraphOffsets;\n'
  + 'this.sourceProgressPercent = sourceProgressPercent;\n'
  + 'this.estimateSavedSourceProgress = estimateSavedSourceProgress;';
const chapters = [
  { start: 0, end: 10, heading: { number: '1', title: 'The Beginning', displayTitle: 'The Beginning' } },
  { start: 10, end: 20, heading: { number: '2', title: 'The Middle', displayTitle: 'The Middle' } },
  { start: 20, end: 30, heading: { number: '3', title: 'The End', displayTitle: 'The End' } }
];
const sandbox = { chapters, hasDetectedChapters: true, documentParagraphs: [], sourceParagraphOffsets: [], totalSourceCharacters: 0, READING_PROGRESS_MODEL: 'source-text-v2' };
vm.runInNewContext(helpers, sandbox, { filename: 'quiet-reader-resume-resolver.js' });

test('stable source paragraph selects correct chapter after detector changes', () => {
  // Simulate a saved chapter index from an older detector, but a stable paragraph
  // location that clearly belongs to the third chapter in this detector.
  assert.equal(sandbox.resolveSavedChapterIndex({ chapterIndex: 0, paragraphIndex: 25, chapterNumber: '1', chapterTitle: 'The Beginning' }), 2);
});
test('chapter number and title recover a saved chapter without paragraph index', () => {
  assert.equal(sandbox.resolveSavedChapterIndex({ chapterIndex: 0, chapterNumber: '2', chapterTitle: 'The Middle' }), 1);
});
test('legacy save records still fall back to chapter index', () => {
  assert.equal(sandbox.resolveSavedChapterIndex({ chapterIndex: 1, itemIndex: 7 }), 1);
});
test('repeated Roman numbers resolve by title', () => {
  sandbox.chapters = [
    { start: 0, end: 10, heading: { number: 'I', title: 'First Part', displayTitle: 'First Part' } },
    { start: 10, end: 20, heading: { number: 'I', title: 'Second Part', displayTitle: 'Second Part' } }
  ];
  assert.equal(sandbox.resolveSavedChapterIndex({ chapterNumber: 'I', chapterTitle: 'Second Part' }), 1);
});


test('source-text progress gives the same percentage for the same passage independent of reading mode', () => {
  sandbox.documentParagraphs = ['opening words', 'a much longer chapter paragraph', 'the ending'];
  sandbox.buildSourceParagraphOffsets(sandbox.documentParagraphs);
  const sameSourcePositionNormal = sandbox.sourceProgressPercent(1, 0.5);
  const sameSourcePositionFocus = sandbox.sourceProgressPercent(1, 0.5);
  assert.equal(sameSourcePositionNormal, sameSourcePositionFocus);
  assert.ok(sameSourcePositionNormal > 10 && sameSourcePositionNormal < 90);
});

test('legacy inflated 100 percent is estimated from its stable source paragraph anchor', () => {
  sandbox.documentParagraphs = ['opening words', 'the actual current passage', 'later words that have not been reached yet'];
  sandbox.buildSourceParagraphOffsets(sandbox.documentParagraphs);
  const migrated = sandbox.estimateSavedSourceProgress({ paragraphIndex: 1, progressPercent: 100, furthestProgressPercent: 100 });
  assert.ok(migrated > 0 && migrated < 80, `Expected source-based progress below 80%, got ${migrated}`);
});


test('legacy Focus-mode index uses chapter identity and within-chapter ratio', () => {
  sandbox.chapters = [
    { start: 0, end: 1, heading: { number: '1', title: 'One', displayTitle: 'One' } },
    { start: 1, end: 2, heading: { number: '2', title: 'Two', displayTitle: 'Two' } },
    { start: 2, end: 3, heading: { number: '3', title: 'Three', displayTitle: 'Three' } }
  ];
  sandbox.documentParagraphs = ['A'.repeat(100), 'B'.repeat(100), 'C'.repeat(100)];
  sandbox.buildSourceParagraphOffsets(sandbox.documentParagraphs);
  const legacyFocus = { focusMode: true, chapterIndex: 0, chapterNumber: '2', chapterTitle: 'Two', paragraphIndex: 0, scrollRatio: 0.35, progressPercent: 100, furthestProgressPercent: 100 };
  assert.equal(sandbox.resolveSavedChapterIndex(legacyFocus), 1, 'chapter identity must override the old filtered/local paragraph index');
  const migrated = sandbox.estimateSavedSourceProgress(legacyFocus);
  assert.ok(migrated > 30 && migrated < 60, `Expected a within-chapter estimate, got ${migrated}%`);
});

test('meaningful saved progress is not overwritten by an accidental top-of-page save', () => {
  const previous = { version: 1, itemIndex: 36, paragraphIndex: 36, scrollY: 5060, scrollRatio: 0.22, progressPercent: 30, focusMode: false, chapterIndex: 0 };
  const accidentalTopState = { version: 1, itemIndex: 0, paragraphIndex: 0, scrollY: 306, scrollRatio: 0.0001, progressPercent: 0, focusMode: false, chapterIndex: 0 };
  assert.equal(sandbox.shouldPreserveMeaningfulProgress(previous, accidentalTopState), true);
});

test('a long-document toolbar at y=306 is still recognized as the beginning', () => {
  const prior = { version: 1, itemIndex: 1200, paragraphIndex: 1202, scrollY: 612132, scrollRatio: 0.33, progressPercent: 34, focusMode: false, chapterIndex: 120 };
  const toolbarTop = { version: 1, itemIndex: 0, paragraphIndex: 0, scrollY: 306, scrollRatio: 0.00016, progressPercent: 0, focusMode: false, chapterIndex: 0 };
  assert.equal(sandbox.stateHasMeaningfulProgress(toolbarTop), false);
  assert.equal(sandbox.shouldPreserveMeaningfulProgress(prior, toolbarTop), true);
});

test('Start from the beginning can explicitly replace a previous position', () => {
  const previous = { version: 1, itemIndex: 36, paragraphIndex: 36, scrollY: 5060, scrollRatio: 0.22, progressPercent: 30, focusMode: false, chapterIndex: 0 };
  const beginning = { version: 1, itemIndex: 0, paragraphIndex: 0, scrollY: 306, scrollRatio: 0.0001, progressPercent: 0, focusMode: false, chapterIndex: 0 };
  assert.equal(sandbox.shouldPreserveMeaningfulProgress(previous, beginning, true), false);
});

test('a newer meaningful position can replace an older saved position', () => {
  const previous = { version: 1, itemIndex: 36, paragraphIndex: 36, scrollY: 5060, scrollRatio: 0.22, progressPercent: 30, focusMode: false, chapterIndex: 0 };
  const next = { version: 1, itemIndex: 58, paragraphIndex: 58, scrollY: 8120, scrollRatio: 0.35, progressPercent: 40, focusMode: false, chapterIndex: 1 };
  assert.equal(sandbox.shouldPreserveMeaningfulProgress(previous, next), false);
});

console.log(`PASS: ${checks.length} Continue Reading/progress checks (UI wiring, autosave, restore compatibility, chapter identity, source-text progress and legacy migration).`);
