#!/usr/bin/env node
'use strict';
// Standalone regression harness for Shadow Reader's in-page parser helpers.
// Run from any working directory: node tests/parser-regression.cjs [v6.txt] [v7.txt]
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const htmlPath = path.resolve(__dirname, '..', 'index.html');
const html = fs.readFileSync(htmlPath, 'utf8');
const start = html.indexOf('      function stripWatermarks(');
const stop = html.indexOf('      function renderParagraphs(', start);
assert(start >= 0 && stop > start, 'Could not locate parser helper block in index.html');
const sandbox = {};
vm.runInNewContext(html.slice(start, stop) + `\nthis.api = {
  isChapterHeadingLine, parseChapterHeading, parseSpecialSectionHeading,
  parseUnnumberedChapterCandidate, extractParagraphs, detectChapters,
  findContentsSkipIndexes, hasBodyAfterHeading
};`, sandbox, { filename: 'quiet-reader-parser.js' });
const api = sandbox.api;
let checks = 0;
function test(name, fn) {
  try { fn(); checks++; }
  catch (error) { console.error(`FAIL: ${name}\n${error.stack || error}`); process.exitCode = 1; }
}
function roman(value) {
  const pairs = [[10,'X'],[9,'IX'],[5,'V'],[4,'IV'],[1,'I']];
  let n = value, out = '';
  for (const [v, label] of pairs) while (n >= v) { out += label; n -= v; }
  return out;
}
const smallNumbers = ['One','Two','Three','Four','Five','Six','Seven','Eight','Nine','Ten'];
const longBody = 'A long paragraph of story text follows this chapter heading, with enough ordinary prose to distinguish the chapter from a table-of-contents entry.';

const sourceStyleManifest = require('./source-style-manifest.json');
for (const item of sourceStyleManifest) {
  test(`online source style: ${item.title}`, () => {
    if (item.expect === 'chapter') {
      assert.ok(api.parseChapterHeading(item.sample), `Parser did not recognize source pattern: ${item.sample}`);
    } else if (item.expect === 'unnumbered') {
      assert.ok(api.parseUnnumberedChapterCandidate(item.sample), `Title-only chapter fallback failed for: ${item.sample}`);
    } else if (item.expect === 'not-chapter') {
      assert.equal(api.parseChapterHeading(item.sample), null, `Book division should not be interpreted as an individual chapter: ${item.sample}`);
    } else {
      assert.fail(`Unknown expectation in source manifest: ${item.expect}`);
    }
  });
}

const examples = [
  ['explicit colon', 'CHAPTER 1061: DIRE STRAIT', '1061', 'DIRE STRAIT'],
  ['explicit dash', 'Chapter 95 - The Black Skull', '95', 'The Black Skull'],
  ['short ch abbreviation', 'ch. 17', '17', ''],
  ['chapter no prefix', 'Chapter No. 9: The Secret', '9', 'The Secret'],
  ['chapter hash prefix', 'Chapter #8 The Beginning', '8', 'The Beginning'],
  ['roman explicit', 'CHAPTER I.', 'I', ''],
  ['written number', 'Chapter One', 'One', ''],
  ['compound written number', 'Chapter Twenty-One: The Long Walk', 'Twenty-One', 'The Long Walk'],
  ['letter section', 'Letter 1', '1', ''],
  ['letter roman', 'Letter II: A Reply', 'II', 'A Reply'],
  ['web novel long number', '1231 Once More, With Feeling', '1231', 'Once More, With Feeling'],
  ['arabic dot', '1. The Beginning', '1', 'The Beginning'],
  ['arabic close paren', '2) THE BEGINNING', '2', 'THE BEGINNING'],
  ['arabic colon', '3: The Beginning', '3', 'The Beginning'],
  ['arabic hyphen', '4 - The Beginning', '4', 'The Beginning'],
  ['arabic em dash', '5 — The Beginning', '5', 'The Beginning'],
  ['arabic space', '6 The Beginning', '6', 'The Beginning'],
  ['roman all caps', 'I. THE PRISON DOOR', 'I', 'THE PRISON DOOR'],
  ['roman no dot', 'II The Machine', 'II', 'The Machine'],
  ['Alice contents style', 'CHAPTER I. Down the Rabbit-Hole', 'I', 'Down the Rabbit-Hole'],
  ['Moby Dick numeric title style', 'CHAPTER 1. Loomings.', '1', 'Loomings.'],
  ['long roman numeral', 'CHAPTER LXXXI.', 'LXXXI', ''],
  ['mixed-case classic title', 'I. The strange Man’s Arrival', 'I', 'The strange Man’s Arrival'],
  ['all-caps roman title without dot', 'I TREATS OF THE PLACE...', 'I', 'TREATS OF THE PLACE...'],
  ['case-sensitive false friend', 'child. So I let her ride away.', null, null],
  ['roman-like prose sentence', 'I. That thing, meanwhile, was flooding the place.', null, null],
  ['roman token close paren', 'VI)', null, null],
  ['body text mentions chapter', 'Chapter 2 will begin tomorrow.', null, null],
  ['year followed by prose', '1984 Winston Smith was not sure what to do.', null, null],
  ['plain numeral only', '123', null, null],
  ['ordinary sentence numeral prefix', '1. At first, Sunny was tired from walking.', null, null],
];
for (const [name, line, expectedNumber, expectedTitle] of examples) {
  test(name, () => {
    const got = api.parseChapterHeading(line);
    if (expectedNumber === null) assert.equal(got, null, `${line} should not be a heading`);
    else {
      assert.ok(got, `${line} should be detected`);
      assert.equal(got.number, expectedNumber);
      assert.equal(got.title, expectedTitle);
    }
  });
}

// 20 heading styles x 10 chapter numbers = 200 generated chapter-heading cases.
const styles = [
  n => `Chapter ${n}: The Hidden Gate ${n}`,
  n => `CHAPTER ${n} - THE HIDDEN GATE ${n}`,
  n => `Chapter ${n}. The Hidden Gate ${n}`,
  n => `ch. ${n}: The Hidden Gate ${n}`,
  n => `Ch ${n} — The Hidden Gate ${n}`,
  n => `Chapter No. ${n}: The Hidden Gate ${n}`,
  n => `Chapter #${n} The Hidden Gate ${n}`,
  n => `Chapter ${roman(n)}: THE HIDDEN GATE ${n}`,
  n => `CHAPTER ${smallNumbers[n-1].toUpperCase()}: THE HIDDEN GATE ${n}`,
  n => `Chapter ${n} The Hidden Gate ${n}`,
  n => `${n}. The Hidden Gate ${n}`,
  n => `${n}) THE HIDDEN GATE ${n}`,
  n => `${n}: The Hidden Gate ${n}`,
  n => `${n} - The Hidden Gate ${n}`,
  n => `${n} — The Hidden Gate ${n}`,
  n => `${n} The Hidden Gate ${n}`,
  n => `${1000+n} The Hidden Gate ${n}`,
  n => `${roman(n)}. THE HIDDEN GATE ${n}`,
  n => `${roman(n)} The Hidden Gate ${n}`,
  n => `Letter ${n}: The Hidden Gate ${n}`,
];
let generatedHeadingCases = 0;
for (let styleIndex = 0; styleIndex < styles.length; styleIndex++) {
  for (let n = 1; n <= 10; n++) {
    const line = styles[styleIndex](n);
    test(`generated style ${styleIndex + 1}, chapter ${n}: ${line}`, () => {
      const got = api.parseChapterHeading(line);
      assert.ok(got, `Failed to parse generated heading: ${line}`);
      assert.ok(got.title, `Title missing from generated heading: ${line}`);
    });
    generatedHeadingCases++;
  }
}

// Separate-line and wrapped title recovery, including a page break.
test('chapter number followed by separate title attaches', () => {
  const paragraphs = api.extractParagraphs('CHAPTER 1:\n\nTHE BEGINNING\n\n' + longBody);
  assert.equal(paragraphs[0], 'CHAPTER 1: THE BEGINNING');
  assert.equal(api.detectChapters(paragraphs).filter(c => c.heading).length, 1);
  assert.equal(api.detectChapters(paragraphs).filter(c => c.heading)[0].heading.title, 'THE BEGINNING');
});
test('wrapped four-digit chapter title joins', () => {
  const paragraphs = api.extractParagraphs('1233 Coming to Terms With the\n                    End of the World\n\n' + longBody);
  assert.equal(paragraphs[0], '1233 Coming to Terms With the End of the World');
  assert.equal(api.parseChapterHeading(paragraphs[0]).title, 'Coming to Terms With the End of the World');
});
test('hyphenated title split across lines rejoins without a space', () => {
  const paragraphs = api.extractParagraphs('CHAPTER VIII. THE QUEEN’S CROQUET-\nGROUND\n\n' + longBody);
  assert.equal(paragraphs[0], 'CHAPTER VIII. THE QUEEN’S CROQUET-GROUND');
  assert.equal(api.parseChapterHeading(paragraphs[0]).title, 'THE QUEEN’S CROQUET-GROUND');
});
test('title separated by page break attaches', () => {
  const paragraphs = api.extractParagraphs('CHAPTER 2:\fTHE MACHINE\n\n' + longBody);
  assert.equal(paragraphs[0], 'CHAPTER 2: THE MACHINE');
});

// TOC should not be treated as actual chapter starts when the headings repeat in the body.
test('numbered TOC entries are excluded, body copy retained', () => {
  const paragraphs = [
    'Novel Title', 'Contents', 'CHAPTER I. FIRST CHAPTER', 'CHAPTER II. SECOND CHAPTER',
    'CHAPTER I. FIRST CHAPTER', longBody,
    'CHAPTER II. SECOND CHAPTER', longBody
  ];
  const chapters = api.detectChapters(paragraphs).filter(c => c.heading);
  assert.equal(chapters.length, 2);
  assert.equal(chapters[0].start, 4);
  assert.equal(chapters[1].start, 6);
});
test('unnumbered named-chapter TOC is excluded', () => {
  const paragraphs = [
    'Contents', 'STORY OF THE DOOR', 'SEARCH FOR MR. HYDE',
    'STORY OF THE DOOR', longBody,
    'SEARCH FOR MR. HYDE', longBody
  ];
  const chapters = api.detectChapters(paragraphs).filter(c => c.heading);
  assert.equal(chapters.length, 2);
  assert.equal(chapters[0].start, 3);
  assert.equal(chapters[1].start, 5);
});
test('TOC with number-only entries does not swallow first real chapter', () => {
  const paragraphs = [
    'Table of Contents', 'Chapter 1', 'Chapter 2', 'Chapter 1: The First Door', longBody,
    'Chapter 2: The Second Door', longBody
  ];
  const chapters = api.detectChapters(paragraphs).filter(c => c.heading);
  assert.equal(chapters.length, 2);
  assert.equal(chapters[0].start, 3);
});

test('repeated page-number plus book-title running headers are not chapters', () => {
  const paragraphs = [
    '2 Alice’s Adventures in Wonderland', longBody,
    '4 Alice’s Adventures in Wonderland', longBody,
    'Chapter I. The First Chapter', longBody,
    '6 Alice’s Adventures in Wonderland', longBody,
    'Chapter II. The Second Chapter', longBody,
    '8 Alice’s Adventures in Wonderland', longBody,
    '10 Alice’s Adventures in Wonderland', longBody,
  ];
  const chapters = api.detectChapters(paragraphs).filter(c => c.heading);
  assert.deepEqual(Array.from(chapters, c => c.heading.number), ['I', 'II']);
});
test('three repeated page-number + running-title lines are suppressed', () => {
  const paragraphs = [
    '2 Alice’s Adventures in Wonderland', longBody,
    '4 Alice’s Adventures in Wonderland', longBody,
    '6 Alice’s Adventures in Wonderland', longBody,
    '8 Alice’s Adventures in Wonderland', longBody,
    'Chapter I. The First Chapter', longBody,
    'Chapter II. The Second Chapter', longBody,
  ];
  const chapters = api.detectChapters(paragraphs).filter(c => c.heading);
  assert.deepEqual(Array.from(chapters, c => c.heading.number), ['I', 'II']);
});
test('hundreds of page-number running headers do not inflate the chapter count', () => {
  const paragraphs = [];
  let chapter = 1;
  for (let page = 1; page <= 180; page++) {
    paragraphs.push(`${page} Alice’s Adventures in Wonderland`, longBody);
    if (page % 15 === 0 && chapter <= 12) {
      paragraphs.push(`Chapter ${roman(chapter)}. Chapter Title ${chapter}`, longBody);
      chapter++;
    }
  }
  const chapters = api.detectChapters(paragraphs).filter(c => c.heading);
  assert.equal(chapters.length, 12);
  assert.deepEqual(Array.from(chapters, c => c.heading.number), ['I','II','III','IV','V','VI','VII','VIII','IX','X','XI','XII']);
});

test('distinct unpunctuated short-number headings remain eligible', () => {
  const paragraphs = [
    '1 The Beginning', longBody,
    '2 The Long Journey', longBody,
    '3 The Final Door', longBody,
  ];
  const chapters = api.detectChapters(paragraphs).filter(c => c.heading);
  assert.equal(chapters.length, 3);
});

test('special prologue and epilogue detected alongside numbered chapters', () => {
  const paragraphs = ['PROLOGUE', longBody, 'CHAPTER 1: FIRST', longBody, 'EPILOGUE', longBody];
  const chapters = api.detectChapters(paragraphs).filter(c => c.heading);
  assert.deepEqual(Array.from(chapters, c => c.heading.kind), ['Section', 'Chapter', 'Section']);
});
test('all-caps title-only chapters detected as fallback', () => {
  const paragraphs = ['STORY OF THE DOOR', longBody, 'SEARCH FOR MR. HYDE', longBody];
  const chapters = api.detectChapters(paragraphs).filter(c => c.heading);
  assert.equal(chapters.length, 2);
  assert.equal(chapters[0].heading.title, 'STORY OF THE DOOR');
});
test('repeated all-caps running header inside chapter is suppressed', () => {
  const paragraphs = ['CHAPTER 1: FIRST', longBody, 'CHAPTER 1: FIRST', 'A shorter continuation of the same chapter.'];
  const chapters = api.detectChapters(paragraphs).filter(c => c.heading);
  assert.equal(chapters.length, 1);
});
test('document with no headings falls back without crashing', () => {
  const chapters = api.detectChapters(['Just a story paragraph.', 'Another paragraph.']);
  assert.equal(chapters.length, 1);
  assert.equal(chapters[0].heading, null);
});

// Each style family is also passed through full chapter segmentation as a tiny book.
let generatedBookCases = 0;
for (let styleIndex = 0; styleIndex < styles.length; styleIndex++) {
  const paragraphs = [];
  for (let n = 1; n <= 10; n++) paragraphs.push(styles[styleIndex](n), longBody);
  test(`generated 10-chapter book style ${styleIndex + 1}`, () => {
    const chapters = api.detectChapters(paragraphs).filter(c => c.heading);
    assert.equal(chapters.length, 10);
  });
  generatedBookCases++;
}

// Optional, repeatable full-document regression on extracted text from user PDFs.
for (const file of process.argv.slice(2)) {
  const raw = fs.readFileSync(path.resolve(file), 'utf8');
  const paragraphs = api.extractParagraphs(raw);
  const chapters = api.detectChapters(paragraphs).filter(c => c.heading);
  const name = path.basename(file).toLowerCase();
  if (name.includes('v6') || name.includes('volume_6') || name.includes('volume-6')) {
    test('full Shadow Slave Volume 6 regression', () => {
      assert.equal(chapters.length, 170);
      assert.equal(chapters[0].heading.number, '1061');
      assert.deepEqual(Array.from(chapters, c => Number(c.heading.number)), Array.from({length: 170}, (_, i) => 1061 + i));
      assert.ok(chapters.every(c => String(c.heading.title || '').trim()), 'Every Volume 6 chapter should have a detected title');
      assert.equal(chapters[0].heading.displayTitle, 'Dire Strait');
      assert.equal(chapters.at(-1).heading.number, '1230');
      assert.equal(chapters.at(-1).heading.displayTitle, 'Hell Is Empty');
    });
  } else if (name.includes('v7') || name.includes('volume_7') || name.includes('volume-7')) {
    test('full Shadow Slave Volume 7 regression', () => {
      assert.equal(chapters.length, 354);
      assert.equal(chapters[0].heading.number, '1231');
      assert.deepEqual(Array.from(chapters, c => Number(c.heading.number)), Array.from({length: 354}, (_, i) => 1231 + i));
      assert.ok(chapters.every(c => String(c.heading.title || '').trim()), 'Every Volume 7 chapter should have a detected title');
      assert.equal(chapters[0].heading.displayTitle, 'Once More, With Feeling');
      assert.equal(chapters.at(-1).heading.number, '1584');
      assert.equal(chapters.at(-1).heading.displayTitle, 'Sevenfold');
    });
  } else if (name.includes('alice')) {
    test('full Alice’s Adventures in Wonderland regression', () => {
      assert.ok(paragraphs.length > 0);
      assert.equal(chapters.length, 12, 'Alice should have 12 chapters, not page-number false positives');
      assert.deepEqual(Array.from(chapters, c => c.heading.number), ['I','II','III','IV','V','VI','VII','VIII','IX','X','XI','XII']);
      assert.deepEqual(Array.from(chapters, c => c.heading.displayTitle), [
        'Down the Rabbit-Hole', 'The Pool of Tears', 'A Caucus-Race and a Long Tale',
        'The Rabbit Sends in a Little Bill', 'Advice from a Caterpillar', 'Pig and Pepper',
        'A Mad Tea-Party', 'The Queen’s Croquet-Ground', 'The Mock Turtle’s Story',
        'The Lobster Quadrille', 'Who Stole the Tarts?', 'Alice’s Evidence'
      ]);
    });
  } else {
    test(`full document smoke regression: ${path.basename(file)}`, () => {
      assert.ok(paragraphs.length > 0);
      assert.ok(chapters.length > 0);
    });
  }
}

if (process.exitCode) {
  console.error(`\nRegression failed. Successful test groups: ${checks}; generated heading cases: ${generatedHeadingCases}; generated book styles: ${generatedBookCases}.`);
  process.exit(process.exitCode);
}
console.log(`PASS: ${checks} test groups, ${generatedHeadingCases} generated heading cases, ${generatedBookCases} generated 10-chapter books${process.argv.length > 2 ? `, ${process.argv.length-2} full-text file(s)` : ''}.`);
