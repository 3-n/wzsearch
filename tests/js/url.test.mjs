import { test } from 'node:test';
import assert from 'node:assert/strict';
import { parseHash, buildHash, buildQuery } from '../../site/js/url.js';
import { defaultFilters } from '../../site/js/filters.js';

test('routes', () => {
  assert.equal(parseHash('').route, 'explore');
  assert.equal(parseHash('#').route, 'explore');
  assert.equal(parseHash('#/').route, 'explore');
  assert.equal(parseHash('#/?q=a').route, 'explore');
  assert.equal(parseHash('#/zrodla').route, 'sources');
  assert.equal(parseHash('#/o-projekcie').route, 'about');
  const r = parseHash('#/wpis/wz-2026-15?rodzaj=wz');
  assert.equal(r.route, 'record');
  assert.equal(r.recordId, 'wz-2026-15');
  assert.deepEqual(r.filters.kinds, ['wz']);
  const u = parseHash('#/cokolwiek');
  assert.equal(u.route, 'explore');
  assert.equal(u.unknown, true);
});

test('full round trip of every parameter', () => {
  const f = {
    ...defaultFilters(),
    q: 'Grochowska 5 „Nila”',
    kinds: ['wz', 'cp'],
    from: '2024-01',
    to: '2026-09',
    tags: ['wielorodzinny', 'zmiana-uzytkowania'],
    applicants: ['organization', 'person'],
    areas: ['gocław', 'saska-kepa'],
    streets: ['grochowska', 'stanow zjednoczonych'],
    geoOnly: true,
    bbox: [21.05, 52.22, 21.1, 52.26],
    near: { lat: 52.235, lon: 21.088, r: 1000 },
    file: 'a1b2c3d4e5',
    sort: 'street',
    datasets: ['baipp'],
    issuers: ['city', 'voivode'],
    outcomes: ['refusal'],
    scopes: ['budowa', 'rozbiorka'],
    categories: ['XIII'],
  };
  const hash = buildHash({ route: 'record', recordId: 'ws-6730-2026-29', filters: f, mode: 'map' });
  assert.match(hash, /^#\/wpis\/ws-6730-2026-29\?/);
  const back = parseHash(hash);
  assert.equal(back.route, 'record');
  assert.equal(back.recordId, 'ws-6730-2026-29');
  assert.equal(back.mode, 'map');
  assert.deepEqual(back.filters, f);
});

test('readable Polish param names and defaults omitted', () => {
  const qs = buildQuery({ ...defaultFilters(), q: 'przedszkole', kinds: ['ws'], period: '3m', applicants: ['person'], geoOnly: true, sort: 'oldest' });
  assert.equal(qs, 'q=przedszkole&rodzaj=ws&okres=3m&wnioskodawca=osoba&lokalizacja=1&sort=najstarsze');
  assert.equal(buildQuery(defaultFilters()), '');
  assert.equal(buildHash({ route: 'explore', filters: defaultFilters() }), '#/');
  assert.equal(buildHash({ route: 'sources' }), '#/zrodla');
  assert.equal(buildHash({ route: 'about' }), '#/o-projekcie');
});

test('preset period wins over od/do; od/do swapped when reversed', () => {
  const a = parseHash('#/?okres=12m&od=2020-01&do=2020-02');
  assert.equal(a.filters.period, '12m');
  assert.equal(a.filters.from, null);
  const b = parseHash('#/?od=2026-01&do=2024-05');
  assert.equal(b.filters.from, '2024-05');
  assert.equal(b.filters.to, '2026-01');
});

test('invalid values are dropped, never thrown', () => {
  const { filters } = parseHash('#/?od=2024-13&do=x&okres=7y&wnioskodawca=kosmita,osoba&mapa=1,2,3&blisko=999,1&sort=zle&promien=7&plik=../../etc&q=%E0%A4%A');
  assert.equal(filters.from, null);
  assert.equal(filters.to, null);
  assert.equal(filters.period, null);
  assert.deepEqual(filters.applicants, ['person']);
  assert.equal(filters.bbox, null);
  assert.equal(filters.near, null);
  assert.equal(filters.sort, null);
  assert.equal(filters.file, null);
  assert.equal(typeof filters.q, 'string');
  const n = parseHash('#/?blisko=52.2,21.1&promien=7').filters.near;
  assert.deepEqual(n, { lat: 52.2, lon: 21.1, r: 500 }, 'unknown radius falls back to 500 m');
});

test('street params are normalised to folded keys', () => {
  assert.deepEqual(parseHash('#/?ulica=ul.%20Grochowska,Żółkiewskiego').filters.streets, ['grochowska', 'zolkiewskiego']);
});

test('plus and %20 both decode to spaces in q', () => {
  assert.equal(parseHash('#/?q=ul+Grochowska').filters.q, 'ul Grochowska');
  assert.equal(parseHash('#/?q=ul%20Grochowska').filters.q, 'ul Grochowska');
  assert.equal(parseHash('#/?q=a%2Bb').filters.q, 'a+b');
});

test('kinds: an absent `rodzaj` means the default selection; the default is never written', () => {
  assert.deepEqual(parseHash('#/').filters.kinds, ['wz', 'cp', 'ws']);
  assert.deepEqual(parseHash('#/?rodzaj=').filters.kinds, ['wz', 'cp', 'ws']);
  assert.deepEqual(parseHash('#/?rodzaj=!!,%%').filters.kinds, ['wz', 'cp', 'ws']);
  assert.deepEqual(parseHash('#/?rodzaj=pb').filters.kinds, ['pb']);
  assert.deepEqual(parseHash('#/?rodzaj=pb,wz,cp,ws').filters.kinds, ['wz', 'cp', 'ws', 'pb'], 'ordered');
  assert.equal(buildQuery({ ...defaultFilters(), kinds: ['ws', 'wz', 'cp'] }), '');
  assert.equal(buildQuery({ ...defaultFilters(), kinds: ['pb', 'wz', 'cp', 'ws'] }), 'rodzaj=wz,cp,ws,pb');
  assert.equal(buildQuery({ ...defaultFilters(), kinds: ['wz'] }), 'rodzaj=wz', 'v1 links keep working');
});

test('v2 list filters use readable Polish parameter names', () => {
  const qs = buildQuery({ ...defaultFilters(), datasets: ['baipp'], issuers: ['voivode'], outcomes: ['refusal'], scopes: ['rozbiorka'], categories: ['XIII'] });
  assert.equal(qs, 'zrodlo=baipp&organ=voivode&rozstrzygniecie=refusal&zakres=rozbiorka&kategoria=XIII');
  assert.deepEqual(parseHash('#/?zakres=budowa,<script>&kategoria=XIII').filters.scopes, ['budowa']);
});

test('"W pobliżu" points are rounded to 3 decimals (~100 m) in both directions', () => {
  const f = { ...defaultFilters(), near: { lat: 52.254936, lon: 21.076218, r: 250 } };
  assert.equal(buildQuery(f), 'blisko=52.255,21.076&promien=250');
  assert.deepEqual(parseHash('#/?blisko=52.254936,21.076218&promien=250').filters.near, { lat: 52.255, lon: 21.076, r: 250 });
  assert.deepEqual(parseHash('#/?blisko=52.25,21.1').filters.near, { lat: 52.25, lon: 21.1, r: 500 });
});

test('sources tabs live in the path', () => {
  assert.equal(parseHash('#/zrodla/rwdz').tab, 'rwdz');
  assert.equal(parseHash('#/zrodla').tab, null);
  assert.equal(parseHash('#/zrodla/../../x').tab, null);
  assert.equal(buildHash({ route: 'sources', tab: 'baipp' }), '#/zrodla/baipp');
  assert.equal(buildHash({ route: 'sources' }), '#/zrodla');
});

test('Object.prototype names in the URL are not values (okres, wnioskodawca, sort)', () => {
  for (const name of ['constructor', '__proto__', 'toString', 'hasOwnProperty']) {
    const s = parseHash(`#/?okres=${name}&wnioskodawca=${name},firma&sort=${name}`);
    assert.equal(s.filters.period, null, name);
    assert.deepEqual(s.filters.applicants, ['organization'], name);
    assert.equal(s.filters.sort, null, name);
    const h = buildHash(s);
    assert.ok(!h.includes('undefined') && !h.includes(name), h);
  }
  assert.equal(buildHash({ route: 'explore', filters: { ...parseHash('#/').filters, sort: 'constructor' } }), '#/');
});
