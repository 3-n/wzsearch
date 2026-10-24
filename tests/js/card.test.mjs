import { test } from 'node:test';
import assert from 'node:assert/strict';
import { matchContext, precisionDescription, cardTags, displayCase, CARD_TAGS } from '../../site/js/components/card.js';
import { snippetAround, tokenize } from '../../site/js/search.js';

const dicts = { tags: { infrastruktura: { label: 'Sieci: woda, ciepło, prąd, gaz' } }, areas: { grochow: { label: 'Grochów' } } };
const entry = (rec) => ({ rec: { tags: [], parcels: [], address: {}, ...rec } });

test('snippetAround cuts at word boundaries and marks dropped text', () => {
  const t = 'Miejskie Przedsiębiorstwo Wodociągów i Kanalizacji w m.st. Warszawie S.A. Pl. Starynkiewicza 5, 02-015 Warszawa';
  const i = t.indexOf('Starynkiewicza');
  const s = snippetAround(t, i, i + 14, 10);
  assert.ok(s.startsWith('…') && s.endsWith('…'), s);
  assert.ok(s.includes('Starynkiewicza 5'), s);
  assert.equal(snippetAround('krótki tekst', 0, 6), 'krótki tekst');
});

test('matchContext explains matches the card does not show', () => {
  const rec = {
    kind: 'cp', address: { display: 'Dudziarska', street: 'Dudziarska' }, number: '18/CP/PPd/2022',
    applicant: 'Miejskie Przedsiębiorstwo Wodociągów i Kanalizacji w m.st. Warszawie S.A. Pl. Starynkiewicza 5',
    investment: 'Budowa sieci wodociągowej DN 100', area: 'grochow', tags: ['infrastruktura'],
    parcels: [{ number: '34', obreb: '3-03-02', id: '146507_8.0302.34' }, { number: '6/1', obreb: '3-03-03', id: '146507_8.0303.6/1' }],
  };
  assert.equal(matchContext(entry(rec), tokenize('dudziarska'), dicts), null, 'visible in the title');
  assert.equal(matchContext(entry(rec), [], dicts), null);
  assert.deepEqual(matchContext(entry(rec), tokenize('6/1'), dicts), { label: 'Działki', text: 'dz. 34 obr. 3-03-02, dz. 6/1 obr. 3-03-03' });
  assert.equal(matchContext(entry(rec), tokenize('146507_8.0303.6/1'), dicts)?.label, 'Identyfikator działki', 'pasted Geoportal id');
  const a = matchContext(entry(rec), tokenize('starynkiewicza'), dicts);
  assert.equal(a.label, 'Wnioskodawca');
  assert.match(a.text, /^….*Starynkiewicza 5$/);
  assert.equal(matchContext(entry(rec), tokenize('miejskie'), dicts), null, 'start of applicant is visible');
});

test('matchContext shows the corrected street name for a misspelt address', () => {
  const rec = { kind: 'ws', address: { display: 'gen. Augusta Emila Fieldora Nila 41A', street: 'gen. Augusta Emila Fieldorfa Nila' } };
  assert.deepEqual(matchContext(entry(rec), tokenize('fieldorfa'), dicts), { label: 'Ulica', text: 'gen. Augusta Emila Fieldorfa Nila' });
});

test('precisionDescription folds the street-level caveat into the label', () => {
  const e = (method, note) => ({ hasGeo: true, rec: { geo: { method, note } } });
  assert.deepEqual(precisionDescription(e('street', 'działek nie znaleziono w ULDK (mogły zostać podzielone lub scalone); lokalizacja przybliżona – ulica')),
    { label: 'Lokalizacja przybliżona (ulica)', note: 'działek nie znaleziono w ULDK (mogły zostać podzielone lub scalone)' });
  assert.deepEqual(precisionDescription(e('street', 'lokalizacja przybliżona – skrzyżowanie ulic')), { label: 'Lokalizacja przybliżona (skrzyżowanie ulic)', note: null });
  assert.deepEqual(precisionDescription(e('address', 'lokalizacja przybliżona – budynek nr 3')), { label: 'Lokalizacja według adresu', note: 'lokalizacja przybliżona – budynek nr 3' });
  assert.deepEqual(precisionDescription(e('parcel', null)), { label: 'Lokalizacja według działki', note: null });
  assert.deepEqual(precisionDescription({ hasGeo: false, rec: { geo: { method: null, note: 'nie udało się ustalić lokalizacji' } } }),
    { label: 'Brak lokalizacji na mapie', note: 'nie udało się ustalić lokalizacji' });
});

test('cards list the tags of the active tag filter first, then those the search matches (phones show CARD_TAGS + "+N")', () => {
  const d = { tags: Object.fromEntries(['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h'].map((k) => [k, { label: `Tag ${k.toUpperCase()}` }])) };
  const rec = { tags: ['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h'] };
  assert.equal(CARD_TAGS, 3);
  assert.deepEqual(cardTags(rec, d).slice(0, 3), ['Tag A', 'Tag B', 'Tag C']);
  assert.deepEqual(cardTags(rec, d, { activeTags: ['g'] }).slice(0, 2), ['Tag G', 'Tag A']);
  assert.deepEqual(cardTags(rec, d, { tokens: tokenize('tag h') }).length, 8);
  assert.equal(cardTags({ tags: ['wielorodzinny', 'x'] }, { tags: { wielorodzinny: { label: 'Budynek wielorodzinny' } } }, { tokens: tokenize('wielorodzinny') })[0], 'Budynek wielorodzinny');
  assert.equal(cardTags({ tags: ['x', 'wielorodzinny'] }, { tags: { wielorodzinny: { label: 'Budynek wielorodzinny' } } }, { tokens: tokenize('wielorodzinny') })[0], 'Budynek wielorodzinny');
});

test('register texts in capitals are sentence-cased for display; acronyms, numerals and street names stay', () => {
  assert.equal(displayCase('BUDYNEK MIESZKALNY WIELORODZINNY Z GARAŻEM PODZIEMNYM'), 'Budynek mieszkalny wielorodzinny z garażem podziemnym');
  assert.equal(displayCase('BUDOWA SIECI SN I NN ORAZ STACJI TRAFO'), 'Budowa sieci SN i NN oraz stacji trafo');
  assert.equal(displayCase('PRZEBUDOWA BUDYNKU PRZY UL. GROCHOWSKIEJ'), 'Przebudowa budynku przy ul. Grochowskiej');
  assert.equal(displayCase('Budowa budynku przy ul. Grochowskiej'), 'Budowa budynku przy ul. Grochowskiej', 'mixed case untouched');
  assert.equal(displayCase('KAT. XIII'), 'KAT. XIII', 'too short to judge');
});

test('precision note: no repeated "nie pokazano na mapie"; a stated uncertainty is named', () => {
  assert.deepEqual(precisionDescription({ hasGeo: false, rec: { geo: { note: 'działki poza dzielnicą Praga-Południe wg ULDK – nie pokazano na mapie' } } }),
    { label: 'Brak lokalizacji na mapie', note: 'działki poza dzielnicą Praga-Południe wg ULDK' });
  assert.equal(precisionDescription({ hasGeo: false, rec: { geo: { note: 'działka poza dzielnicą Praga-Południe wg ULDK – nie pokazujemy jej na mapie' } } }).note,
    'działka poza dzielnicą Praga-Południe wg ULDK');
  assert.deepEqual(precisionDescription({ hasGeo: true, rec: { geo: { method: 'street', uncertainty_m: 687, note: 'lokalizacja przybliżona – ulica' } } }),
    { label: 'Lokalizacja przybliżona (ulica)', note: 'miejsce może leżeć w promieniu ok. 700 m od punktu' });
});

test('geo.conflict: parcels far from the stated address give an "uncertain" location, drawn hollow', async () => {
  const { precisionOf } = await import('../../site/js/components/card.js');
  const { buildIndex } = await import('../../site/js/data.js');
  const geo = { lat: 52.24, lon: 21.08, method: 'parcel', conflict: true, note: 'adres Abrahama 4 leży ok. 2190 m od wskazanych działek' };
  const entry = { hasGeo: true, rec: { geo } };
  assert.equal(precisionOf(entry), 'conflict');
  assert.deepEqual(precisionDescription(entry),
    { label: 'Lokalizacja niepewna – adres i działki się różnią', note: 'adres Abrahama 4 leży ok. 2190 m od wskazanych działek' });
  assert.equal(precisionOf({ hasGeo: true, rec: { geo: { ...geo, conflict: false } } }), 'parcel');
  const doc = { generated_at: 'x', kinds: { wz: { label: 'WZ' } }, records: [
    { id: 'a', kind: 'wz', sources: [], parcels: [], geo },
    { id: 'b', kind: 'wz', sources: [], parcels: [], geo: { ...geo, conflict: undefined } },
  ] };
  const idx = buildIndex(doc, { files: [], pages: [] });
  assert.equal(idx.byId.get('a').approx, true);
  assert.equal(idx.byId.get('a').conflict, true);
  assert.equal(idx.byId.get('b').approx, false);
});
