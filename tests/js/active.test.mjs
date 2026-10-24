import { test } from 'node:test';
import assert from 'node:assert/strict';
import { describeActive } from '../../site/js/active.js';
import { defaultFilters } from '../../site/js/filters.js';
import { streetsOf } from '../../site/js/data.js';

const dicts = {
  kinds: {
    wz: { label: 'Decyzja o warunkach zabudowy', short: 'WZ' }, cp: { label: 'Decyzja o lokalizacji…', short: 'CP' },
    ws: { label: 'Wszczęte postępowanie', short: 'Wszczęcie' }, pb: { label: 'Pozwolenie na budowę lub rozbiórkę', short: 'Pozwolenie' },
    zg: { label: 'Zgłoszenie', short: 'Zgłoszenie' },
  },
  outcomes: { refusal: { label: 'Odmowa' } },
  datasets: { baipp: { label: 'Biuro Architektury…', short: 'BAiPP' } },
  issuers: { voivode: { label: 'Wojewoda Mazowiecki' } },
  scopes: { rozbiorka: { label: 'Rozbiórka' } },
  categories: { XIII: { label: 'budynki wielorodzinne' } },
  tags: { wielorodzinny: { label: 'Budynek wielorodzinny' } },
  areas: { kamionek: { label: 'Kamionek' } },
};
const streets = new Map([['grochowska', { key: 'grochowska', label: 'Grochowska', count: 3 }]]);
const filesById = new Map([['abc1234567', { filename: 'wydane decyzje wz - lipiec 2026.xlsx' }]]);

test('no chips for default filters', () => {
  assert.deepEqual(describeActive(defaultFilters(), { dicts }), []);
  assert.deepEqual(describeActive({ ...defaultFilters(), q: '   ', sort: 'oldest' }, { dicts }), []);
});

test('one chip per removable item with readable labels from the dictionaries', () => {
  const f = {
    ...defaultFilters(), q: 'przedszkole', kinds: ['wz', 'cp'], from: '2024-01', to: '2024-12', tags: ['wielorodzinny'],
    applicants: ['person'], areas: ['kamionek'], streets: ['grochowska'], geoOnly: true, bbox: [1, 2, 3, 4],
    near: { lat: 52.2, lon: 21.1, r: 1000 }, file: 'abc1234567',
  };
  const items = describeActive(f, { dicts, streets, filesById, latestMonth: '2026-09' });
  const labels = items.map((i) => `${i.groupLabel}: ${i.label}`);
  assert.deepEqual(labels, [
    'Szukaj: „przedszkole”', 'Rodzaj: WZ', 'Rodzaj: CP', 'Okres: 2024', 'Typ: Budynek wielorodzinny',
    'Wnioskodawca: Osoba fizyczna', 'Obszar: Kamionek', 'Ulica: Grochowska', 'Lokalizacja: tylko z lokalizacją',
    'Mapa: widoczny obszar', 'W pobliżu: promień 1 km', 'Plik: wydane decyzje wz - lipiec 2026.xlsx',
  ]);
});

test('each chip removes exactly its own item', () => {
  const f = { ...defaultFilters(), kinds: ['wz', 'cp'], tags: ['wielorodzinny'] };
  const items = describeActive(f, { dicts });
  const wz = items.find((i) => i.label === 'WZ');
  assert.deepEqual(wz.remove, { kinds: ['cp'] });
  const cpOnly = describeActive({ ...defaultFilters(), kinds: ['cp'] }, { dicts });
  assert.deepEqual(cpOnly[0].remove, { kinds: ['wz', 'cp', 'ws'] }, 'removing the last kind restores the default');
  const tag = items.find((i) => i.group === 'tag');
  assert.deepEqual(tag.remove, { tags: [] });
});

test('relative period chips explain the resolved range', () => {
  const [item] = describeActive({ ...defaultFilters(), period: '3m' }, { dicts, latestMonth: '2026-09' });
  assert.equal(item.label, 'Ostatnie 3 miesiące');
  assert.equal(item.title, 'lip 2026 – wrz 2026');
  assert.deepEqual(item.remove, { period: null, from: null, to: null });
});

test('unknown dictionary keys fall back to the raw value', () => {
  const items = describeActive({ ...defaultFilters(), tags: ['nieznany'], areas: ['x'], streets: ['y'], file: 'zzz' }, { dicts });
  assert.deepEqual(items.map((i) => i.label), ['nieznany', 'x', 'y', 'zzz']);
});

test('streetsOf lists the main street and every part, without duplicates', () => {
  assert.deepEqual(streetsOf({ address: { street: 'Groszowicka', parts: [{ street: 'Groszowicka' }, { street: 'Chodakowska' }] } }),
    ['Groszowicka', 'Chodakowska']);
  assert.deepEqual(streetsOf({ address: null }), []);
  assert.deepEqual(streetsOf({ address: { street: '  ', parts: [null, { street: null }] } }), []);
});

test('opt-in kinds on top of the default show as "+ kind" chips only', () => {
  const items = describeActive({ ...defaultFilters(), kinds: ['wz', 'cp', 'ws', 'pb', 'zg'] }, { dicts });
  assert.deepEqual(items.map((i) => i.label), ['+ Pozwolenie', '+ Zgłoszenie']);
  assert.deepEqual(items[0].remove, { kinds: ['wz', 'cp', 'ws', 'zg'] });
  const narrow = describeActive({ ...defaultFilters(), kinds: ['wz', 'pb'] }, { dicts });
  assert.deepEqual(narrow.map((i) => i.label), ['WZ', 'Pozwolenie']);
});

test('chips for the v2 dictionary filters', () => {
  const f = { ...defaultFilters(), outcomes: ['refusal'], datasets: ['baipp'], issuers: ['voivode'], scopes: ['rozbiorka'], categories: ['XIII'] };
  const labels = describeActive(f, { dicts }).map((i) => `${i.groupLabel}: ${i.label}`);
  assert.deepEqual(labels, ['Źródło: BAiPP', 'Organ: Wojewoda Mazowiecki', 'Rozstrzygnięcie: Odmowa', 'Zakres: Rozbiórka', 'Kategoria: XIII – budynki wielorodzinne']);
  const outcome = describeActive(f, { dicts }).find((i) => i.group === 'outcome');
  assert.deepEqual(outcome.remove, { outcomes: [] });
});
