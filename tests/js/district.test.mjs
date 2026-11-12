import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  CITY_SLUG, DEFAULT_SLUG, LEGACY, areaWords, cityEntry, currentDistrict, dataBase, districtFromHash, districtOf,
  districtTotals, feedPath, isCity, isCityMode, mapStart, recordIdFromHash, resolveDistrict, setDistrict,
} from '../../site/js/district.js';
import { carryFilters } from '../../site/js/filters.js';
import { unofficial } from '../../site/js/copy.js';
import { csvFileName } from '../../site/js/csv.js';
import { buildHash, parseHash, setHashDistrict } from '../../site/js/url.js';
import { defaultFilters } from '../../site/js/filters.js';
import { ADDRESSEES } from '../../site/js/request.js';

const LIST = [
  { slug: 'bemowo', name: 'Bemowo', code: 'bem', genitive: 'Bemowa', bbox: [20.87, 52.22, 20.95, 52.27] },
  { slug: 'praga-poludnie', name: 'Praga-Południe', code: '' },
  { slug: 'wola', name: 'Wola', code: 'wol' },
];

test('dz and record ids of a hash', () => {
  assert.equal(districtFromHash('#/?q=x&dz=wola'), 'wola');
  assert.equal(districtFromHash('#/zrodla?dz=bemowo'), 'bemowo');
  assert.equal(districtFromHash('#/?dz=../etc'), null);
  assert.equal(districtFromHash('#/'), null);
  assert.equal(recordIdFromHash('#/wpis/wz-bem-2026-1?dz=bemowo'), 'wz-bem-2026-1');
  assert.equal(recordIdFromHash('#/?q=wpis'), null);
});

test('which district a page shows: dz, then the id code, then Praga-Południe (no remembered choice)', () => {
  assert.equal(resolveDistrict(LIST, { hash: '#/?dz=wola' }).slug, 'wola');
  assert.equal(resolveDistrict(LIST, { hash: '#/?dz=nieznana' }).slug, DEFAULT_SLUG);
  assert.equal(resolveDistrict(LIST, { hash: '#/wpis/wz-bem-2026-1' }).slug, 'bemowo');
  assert.equal(resolveDistrict(LIST, { hash: '#/wpis/wz-am-wol-2026-88' }).slug, 'wola');
  assert.equal(resolveDistrict(LIST, { hash: '#/wpis/ws-wol-6730-2026-12' }).slug, 'wola');
  // legacy permalinks (published before the other districts existed) are Praga-Południe's
  assert.equal(resolveDistrict(LIST, { hash: '#/wpis/wz-2026-15' }).slug, DEFAULT_SLUG);
  assert.equal(resolveDistrict(LIST, { hash: '#/wpis/wz-am-2026-95' }).slug, DEFAULT_SLUG);
  // a permit id does not tell its district: without dz it is Praga-Południe's (new links always carry dz)
  assert.equal(resolveDistrict(LIST, { hash: '#/wpis/pb-st-mz-pa-2026-29594' }).slug, DEFAULT_SLUG);
  assert.equal(resolveDistrict(LIST, { hash: '#/wpis/pb-st-mz-pa-2026-29594?dz=wola' }).slug, 'wola');
  // a bare link opens Praga-Południe even for a visitor who picked another district before (plan §7 #2)
  assert.equal(resolveDistrict(LIST, { hash: '#/' }).slug, DEFAULT_SLUG);
  assert.equal(resolveDistrict(LIST, {}).slug, DEFAULT_SLUG);
  assert.equal(resolveDistrict([], {}).slug, DEFAULT_SLUG);
});

test('data base and map start follow the district; Praga-Południe keeps data/', () => {
  setDistrict(LEGACY, []);
  assert.equal(isCity(), false);
  assert.equal(dataBase(), 'data/');
  setDistrict(LIST[1], [LIST[1]]);
  assert.equal(isCity(), false, 'a list with one district is a single-district site');
  setDistrict(LIST[0], LIST);
  assert.equal(isCity(), true);
  assert.equal(currentDistrict().name, 'Bemowo');
  assert.equal(currentDistrict().locative, LEGACY.locative, 'missing fields fall back to the legacy entry');
  assert.equal(dataBase(), 'data/d/bemowo/');
  assert.equal(feedPath(), 'data/d/bemowo/feed.xml');
  const start = mapStart();
  assert.deepEqual(start.bounds, [[52.22, 20.87], [52.27, 20.95]]);
  assert.equal(start.zoom, 13);
  setDistrict(LIST[1], LIST);
  assert.equal(dataBase(), 'data/');
  assert.equal(feedPath(), 'feed.xml');
  setDistrict(LEGACY, []);
});

test('every hash carries the district; links into another district override it', () => {
  setHashDistrict('wola');
  const f = { ...defaultFilters(), q: 'Górczewska' };
  assert.equal(buildHash({ route: 'explore', filters: f }), '#/?q=G%C3%B3rczewska&dz=wola');
  assert.equal(buildHash({ route: 'record', recordId: 'wz-wol-2026-1', filters: defaultFilters() }), '#/wpis/wz-wol-2026-1?dz=wola');
  assert.equal(buildHash({ route: 'sources' }), '#/zrodla?dz=wola');
  assert.equal(buildHash({ route: 'about' }), '#/o-projekcie?dz=wola');
  assert.equal(buildHash({ route: 'explore', filters: f, district: 'bemowo' }), '#/?q=G%C3%B3rczewska&dz=bemowo');
  // dz is not a filter: parsing ignores it, the round trip keeps the filters
  assert.deepEqual(parseHash('#/?q=G%C3%B3rczewska&dz=wola').filters, f);
  setHashDistrict(null);
  assert.equal(buildHash({ route: 'sources' }), '#/zrodla');
  assert.equal(buildHash({ route: 'explore', filters: defaultFilters() }), '#/');
});

test('district totals and the request addressee of the district shown', () => {
  assert.deepEqual(districtTotals({ counts_by_kind: { wz: 3, cp: 1, ws: 2, pb: 10, zg: 1 } }), { planning: 6, permits: 11 });
  assert.deepEqual(districtTotals({}), { planning: 0, permits: 0 });
  setDistrict(LEGACY, []);
  assert.match(ADDRESSEES.district.lines[2], /Dzielnicy Praga-Południe$/);
  assert.equal(ADDRESSEES.district.inbox, 'Urząd Dzielnicy Praga-Południe');
  setDistrict(LIST[2], LIST);
  assert.match(ADDRESSEES.district.lines[2], /Dzielnicy Wola$/);
  assert.equal(ADDRESSEES.district.fallback, '', 'the general inbox is the address itself, not an alternative');
  setDistrict(LEGACY, []);
});

const CITY = { slug: 'warszawa', name: 'Cała Warszawa', genitive: 'Warszawy', locative: 'w Warszawie', city: true, code: '',
  counts_by_kind: { wz: 5, cp: 1, ws: 4 }, bbox: [20.85, 52.09, 21.26, 52.37] };

test('"Cała Warszawa" is a scope of its own; a record never opens in it', () => {
  assert.equal(resolveDistrict(LIST, { hash: '#/?dz=warszawa', cityItem: CITY }).slug, CITY_SLUG);
  assert.equal(resolveDistrict(LIST, { cityItem: CITY }).slug, DEFAULT_SLUG, 'a bare link is never the city');
  assert.equal(resolveDistrict(LIST, { hash: '#/?dz=warszawa' }).slug, DEFAULT_SLUG, 'no city index: not a scope');
  // a record link into the city scope (typed, or from an old tab) opens in the record's district
  assert.equal(resolveDistrict(LIST, { hash: '#/wpis/wz-bem-2026-1?dz=warszawa', cityItem: CITY }).slug, 'bemowo');
  assert.equal(resolveDistrict(LIST, { hash: '#/wpis/wz-2026-15?dz=warszawa', cityItem: CITY }).slug, DEFAULT_SLUG);
});

test('the city scope: its own data base, no feed, districts as areas', () => {
  setDistrict(CITY, LIST, CITY);
  assert.equal(isCityMode(), true);
  assert.equal(cityEntry().slug, CITY_SLUG);
  assert.equal(dataBase(), 'data/warszawa/');
  assert.equal(feedPath(), null);
  assert.equal(mapStart().zoom, 11);
  assert.equal(areaWords().facet, 'Dzielnica');
  assert.equal(districtOf({ district: 'wola' }).name, 'Wola');
  assert.equal(districtOf({ district: 'nieznana' }), null);
  assert.equal(unofficial(currentDistrict()), 'Serwis nieoficjalny – dane z publikacji urzędów dzielnic, Urzędu m.st. Warszawy i GUNB');
  setDistrict(LIST[2], LIST, CITY);
  assert.equal(isCityMode(), false);
  assert.equal(areaWords().facet, 'Obszar');
  assert.match(unofficial(currentDistrict()), /Urzędu Dzielnicy Wola,/);
  assert.match(unofficial('Bemowo'), /Urzędu Dzielnicy Bemowo,/);
  setDistrict(LEGACY, []);
  assert.equal(cityEntry(), null);
});

test('filters tied to one district do not carry over; CSV files are named after the scope', () => {
  const f = { ...defaultFilters(), q: 'szkoła', streets: ['grochowska'], areas: ['gocław'], bbox: [1, 2, 3, 4], near: { lat: 1, lon: 2, r: 500 }, file: 'abc' };
  assert.deepEqual(carryFilters(f), { ...f, streets: [], areas: [], bbox: null, near: null, file: null });
  const day = new Date('2026-10-23T12:00:00Z');
  assert.equal(csvFileName(day), 'wzsearch-praga-poludnie-2026-10-23.csv');
  assert.equal(csvFileName(day, 'warszawa'), 'wzsearch-warszawa-2026-10-23.csv');
});
