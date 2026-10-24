import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  fold, foldWithMap, tokenize, findToken, buildSearchDoc, scoreDoc, highlightRanges, highlightSegments, stem,
} from '../../site/js/search.js';

test('fold removes Polish diacritics, lowercases and collapses whitespace', () => {
  assert.equal(fold('Żółć Gęślą JAŹŃ'), 'zolc gesla jazn');
  assert.equal(fold('Łódź ŁÓDŹ łabędź'), 'lodz lodz labedz');
  assert.equal(fold('Kamionkowska 29        Praga-Południe'), 'kamionkowska 29 praga-poludnie');
  assert.equal(fold('dz. 46/4\n3-01-24'), 'dz. 46/4 3-01-24');
  assert.equal(fold('„Nila”'), '"nila"');
  assert.equal(fold(null), '');
});

test('foldWithMap maps folded offsets back to the original string', () => {
  const s = 'Ż  ółw';
  const { folded, map } = foldWithMap(s);
  assert.equal(folded, 'z olw');
  assert.equal(map.length, folded.length + 1);
  assert.equal(s[map[2]], 'ó');
  assert.equal(map[folded.length], s.length);
});

test('tokenize: AND tokens, punctuation trimmed, stopwords dropped, dedup', () => {
  assert.deepEqual(tokenize('  ul. Grochowska  12 '), ['grochowska', '12']);
  assert.deepEqual(tokenize('al. Stanów Zjednoczonych'), ['stanow', 'zjednoczonych']);
  assert.deepEqual(tokenize('15/PPD/WZ/2026,'), ['15/ppd/wz/2026']);
  assert.deepEqual(tokenize('"przedszkole" przedszkole'), ['przedszkole']);
  assert.deepEqual(tokenize('UD-VI-WAB-U.6730.29.2026.AKU'), ['ud-vi-wab-u.6730.29.2026.aku']);
  assert.deepEqual(tokenize('—'), []);
  assert.deepEqual(tokenize(''), []);
  assert.deepEqual(tokenize('w rejonie ulicy Grochowskiej i Mińskiej'), ['rejonie', 'grochowskiej', 'minskiej'], 'prepositions dropped');
  assert.deepEqual(tokenize('dz. 46/4 obr. 3-01-24'), ['46/4', '3-01-24'], 'parcel as printed in the detail panel');
  assert.deepEqual(tokenize('działka nr 46/4, obręb 3-01-24'), ['46/4', '3-01-24']);
  assert.deepEqual(tokenize('146507_8.0605.25/12'), ['146507_8.0605.25/12'], 'cadastral parcel id stays one token');
});

test('a parcel is found the way the UI prints it and by its cadastral id (Geoportal)', () => {
  const rec = {
    id: 'pb-st-mz-pa-2026-29594', number: '163/PPD/PB/2026', address: { display: 'Salamandry 3', street: 'Salamandry' },
    parcels: [{ number: '25/12', obreb: '3-06-05', id: '146507_8.0605.25/12' }],
  };
  const doc = buildSearchDoc(rec, {});
  for (const q of ['dz. 25/12 obr. 3-06-05', 'działka 25/12', 'obręb 3-06-05', '146507_8.0605.25/12', '0605.25/12']) {
    assert.ok(scoreDoc(doc, tokenize(q)) > 0, q);
  }
  assert.equal(scoreDoc(doc, tokenize('dz. 25/13')), 0);
});

test('stem: one inflectional ending, mobile "e" of -ek, words with digits untouched', () => {
  const same = (a, b) => assert.equal(stem(fold(a)), stem(fold(b)), `${a} ~ ${b}`);
  same('stacja', 'stacji');
  same('bazowa', 'bazowej');
  same('budynek', 'budynku');
  same('żłobek', 'żłobka');
  same('Kamionek', 'Kamionku');
  same('mieszkalny', 'mieszkalnego');
  same('Grochowska', 'Grochowskiej');
  same('Saska', 'Saskiej');
  same('Kępa', 'Kępie');
  same('Grochów', 'Grochowie');
  same('przedszkole', 'przedszkola');
  same('szkoła', 'szkoły');
  assert.equal(stem('park'), 'park');
  assert.equal(stem('46/4'), '46/4');
  assert.equal(stem('war2380a'), 'war2380a');
  assert.equal(stem('dom'), 'dom');
  assert.notEqual(stem('parku'), stem('parking'), 'no false friends');
});

test('inflected query words match other grammatical forms (and are highlighted)', () => {
  const doc = buildSearchDoc({
    id: 'cp-2021-2',
    investment: 'Budowa stacji bazowej telefonii komórkowej na dachu budynku mieszkalnego',
    address: { display: 'Chrzanowskiego 12', street: 'Chrzanowskiego' },
  });
  assert.ok(scoreDoc(doc, tokenize('stacja bazowa')) > 0);
  assert.ok(scoreDoc(doc, tokenize('budynek mieszkalny')) > 0);
  assert.ok(scoreDoc(doc, tokenize('telefonia komórkowa')) > 0);
  assert.equal(scoreDoc(doc, tokenize('stacja paliw')), 0, 'AND semantics still apply');
  assert.equal(scoreDoc(doc, tokenize('parking')), 0);
  const text = doc.fields.find((f) => f.key === 'investment').text;
  const hits = highlightSegments(text, tokenize('stacja bazowa')).filter((s) => s.hit).map((s) => s.text);
  assert.deepEqual(hits, ['stacji', 'bazowej']);
});

test('exact matches outrank inflected ones', () => {
  const exact = buildSearchDoc({ id: 'a', investment: 'budowa stacji transformatorowej' });
  const inflected = buildSearchDoc({ id: 'b', investment: 'budowa stacja transformatorowa' });
  assert.ok(scoreDoc(exact, tokenize('stacji')) > scoreDoc(inflected, tokenize('stacji')));
});

test('numeric tokens match only at a digit boundary', () => {
  assert.deepEqual(findToken('domeyki 5', '5'), [8]);
  assert.deepEqual(findToken('domeyki 15', '5'), []);
  assert.deepEqual(findToken('nr 5a', '5'), [3]);
  assert.deepEqual(findToken('2025', '5'), []);
  assert.deepEqual(findToken('dz. 46/4 3-01-24', '46/4'), [4]);
  assert.deepEqual(findToken('grochowska', 'grochow'), [0]);
  assert.deepEqual(findToken('', 'x'), []);
});

const dicts = {
  tags: { oswiata: { label: 'Przedszkole lub szkoła' }, budowa: { label: 'Nowa budowa' } },
  areas: { grochow: { label: 'Grochów' } },
};
const rec = {
  id: 'wz-2026-17',
  number: '17/PPD/WZ/2026',
  applicant: 'Fundacja Żółty Dom',
  investment: 'zmiana sposobu użytkowania lokalu na przedszkole',
  address: { display: 'Drwęcka 18', street: 'Drwęcka', number: '18' },
  parcels: [{ number: '2/10', obreb: '3-02-11' }],
  tags: ['oswiata'],
  area: 'grochow',
};

test('search doc covers all searchable fields incl. tag & area labels', () => {
  const doc = buildSearchDoc(rec, dicts);
  const keys = doc.fields.map((f) => f.key);
  assert.deepEqual(keys, ['number', 'address', 'street', 'applicant', 'investment', 'parcels', 'tags', 'area']);
  assert.ok(scoreDoc(doc, tokenize('drwecka')) > 0);
  assert.ok(scoreDoc(doc, tokenize('ZOLTY dom')) > 0);
  assert.ok(scoreDoc(doc, tokenize('2/10 3-02-11')) > 0);
  assert.ok(scoreDoc(doc, tokenize('szkoła')) > 0, 'tag label');
  assert.ok(scoreDoc(doc, tokenize('grochów przedszkole')) > 0, 'area label + investment');
  assert.equal(scoreDoc(doc, tokenize('drwecka kamionek')), 0, 'AND semantics');
  assert.equal(scoreDoc(doc, []), 1, 'empty query matches everything');
});

test('normalised street names of every address part are searchable (declension in display)', () => {
  const doc = buildSearchDoc({
    id: 'cp', address: { display: 'w rejonie ul. Drwęckiej i Grochowskiej', street: 'Drwęcka', parts: [{ street: 'Drwęcka' }, { street: 'Grochowska' }] },
  });
  assert.ok(scoreDoc(doc, tokenize('drwecka')) > 0);
  assert.ok(scoreDoc(doc, tokenize('grochowska')) > 0);
});

test('search doc tolerates null fields', () => {
  const doc = buildSearchDoc({ id: 'x', address: null, parcels: null, tags: null }, {});
  assert.deepEqual(doc.fields, []);
  assert.equal(scoreDoc(doc, ['a']), 0);
});

test('relevance prefers number/address matches over investment text', () => {
  const a = buildSearchDoc({ id: 'a', address: { display: 'Grochowska 5' }, investment: 'x' });
  const b = buildSearchDoc({ id: 'b', address: { display: 'Kinowa 1' }, investment: 'przy ul. Grochowskiej' });
  assert.ok(scoreDoc(a, ['grochowsk']) > scoreDoc(b, ['grochowsk']));
});

test('highlight ranges are projected onto the original (diacritics, whitespace)', () => {
  const text = 'Budowa PRZEDSZKOLA przy  ul. Żółkiewskiego';
  const ranges = highlightRanges(text, tokenize('przedszkola zolkiewskiego'));
  assert.deepEqual(ranges.map(([a, b]) => text.slice(a, b)), ['PRZEDSZKOLA', 'Żółkiewskiego']);
  const segs = highlightSegments('Łąkowa 5', ['lak']);
  assert.deepEqual(segs, [{ text: 'Łąk', hit: true }, { text: 'owa 5', hit: false }]);
  assert.deepEqual(highlightSegments('abc', []), [{ text: 'abc', hit: false }]);
  assert.deepEqual(highlightSegments(null, ['a']), []);
});

test('overlapping highlight ranges are merged', () => {
  assert.deepEqual(highlightRanges('grochowska', ['groch', 'chowska']), [[0, 10]]);
});
