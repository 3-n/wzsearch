import { test } from 'node:test';
import assert from 'node:assert/strict';
import { safeUrl } from '../../site/js/dom.js';

test('safeUrl rejects script URLs however they are disguised (tab, newline, CR, C0, spaces)', () => {
  for (const u of ['javascript:alert(1)', 'java\tscript:alert(1)', 'java\nscript:x', 'jav\rascript:x', '\u0001javascript:x', ' javascript:x',
    'JaVaScRiPt:x', 'data:text/html,x', 'vbscript:x', '//evil.example/x', '/\\evil.example/x', '\\\\evil.example', '']) {
    assert.equal(safeUrl(u), null, JSON.stringify(u));
  }
  assert.equal(safeUrl(null), null);
});

test('safeUrl keeps http(s) and relative links', () => {
  assert.equal(safeUrl('https://a.pl/b'), 'https://a.pl/b');
  assert.equal(safeUrl(' https://a.pl/b '), 'https://a.pl/b');
  assert.equal(safeUrl('sources/abc.xlsx'), 'sources/abc.xlsx');
  assert.equal(safeUrl('#/wpis/x'), '#/wpis/x');
  assert.equal(safeUrl('http://pragapld.um.warszawa.pl/-/lipiec-2026'), 'http://pragapld.um.warszawa.pl/-/lipiec-2026');
});
