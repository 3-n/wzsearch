import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  DEFAULT_SLUG, LEGACY, currentDistrict, dataBase, districtFromHash, districtTotals, feedPath, isCity, mapStart,
  recordIdFromHash, resolveDistrict, setDistrict,
} from '../../site/js/district.js';
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

test('which district a page shows: dz, then the id code, then the last choice, then Praga-Południe', () => {
  assert.equal(resolveDistrict(LIST, { hash: '#/?dz=wola', stored: 'bemowo' }).slug, 'wola');
  assert.equal(resolveDistrict(LIST, { hash: '#/?dz=nieznana', stored: 'bemowo' }).slug, 'bemowo');
  assert.equal(resolveDistrict(LIST, { hash: '#/wpis/wz-bem-2026-1' }).slug, 'bemowo');
  assert.equal(resolveDistrict(LIST, { hash: '#/wpis/wz-am-wol-2026-88' }).slug, 'wola');
  assert.equal(resolveDistrict(LIST, { hash: '#/wpis/ws-wol-6730-2026-12' }).slug, 'wola');
  // legacy permalinks (published before the other districts existed) are Praga-Południe's, whatever was stored
  assert.equal(resolveDistrict(LIST, { hash: '#/wpis/wz-2026-15', stored: 'wola' }).slug, DEFAULT_SLUG);
  assert.equal(resolveDistrict(LIST, { hash: '#/wpis/wz-am-2026-95', stored: 'wola' }).slug, DEFAULT_SLUG);
  // a permit id does not tell its district: the last choice wins
  assert.equal(resolveDistrict(LIST, { hash: '#/wpis/pb-st-mz-pa-2026-29594', stored: 'wola' }).slug, 'wola');
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
