import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import {
  defaultFilters, evaluate, sortResults, effectiveSort, resolvePeriod, hasActiveFilters, distanceMeters, inBbox, availableOptions,
  sameSplit, outcomeCoverage, periodRanges, periodSpans, sanitizeFilters, nearHit,
} from '../../site/js/filters.js';
import {
  buildIndex, addPermits, prepareEntries, monthBounds, streetKey, streetSortKey, relatedChain, relationReason, datasetOf, fileDataset,
  nearestAddressPoint,
} from '../../site/js/data.js';
import { tokenize } from '../../site/js/search.js';

const load = (name) => JSON.parse(readFileSync(new URL(`../fixtures/site-data/${name}`, import.meta.url)));
const index = buildIndex(load('records.json'), load('sources.json'));
/** A second index with the lazily loaded permits merged in (as the browser does after permits.json). */
const full = buildIndex(load('records.json'), load('sources.json'));
const permitsDoc = load('permits.json');
const added = addPermits(full, permitsDoc);
const runFull = (patch) => {
  const f = { ...defaultFilters(), ...patch };
  const b = monthBounds(full, f.kinds);
  return evaluate(full.entries, f, { latestMonth: b.max, tokens: tokenize(f.q) });
};
const ctx = (f) => ({ latestMonth: index.maxMonth, tokens: tokenize(f.q) });
const run = (patch) => {
  const f = { ...defaultFilters(), ...patch };
  return evaluate(index.entries, f, ctx(f));
};

test('index is built from the fixture', () => {
  assert.equal(index.entries.length, index.meta.count);
  assert.ok(index.entries.length >= 80);
  // every kind of the dictionary, in display order – pb/zg known before permits.json is loaded
  assert.deepEqual(index.kindCodes, ['wz', 'cp', 'ws', 'pb', 'zg']);
  assert.deepEqual(index.baseKinds.sort(), ['cp', 'ws', 'wz']);
  assert.ok(index.countsByKind.pb > 0 && index.countsByKind.zg > 0);
  assert.equal(index.permitsLoaded, false);
  assert.ok(index.meta.fixture);
  assert.ok(index.minMonth <= '2020-12');
  assert.equal(index.maxMonth, '2026-09');
  assert.ok(index.streets.size > 10);
});

test('no filters → everything, facets add up', () => {
  const { results, facets } = run({});
  assert.equal(results.length, index.entries.length);
  const kindSum = Object.values(facets.kinds).reduce((a, b) => a + b, 0);
  assert.equal(kindSum, index.entries.length);
  const monthSum = Object.values(facets.months).reduce((a, m) => a + Object.values(m).reduce((x, y) => x + y, 0), 0);
  assert.equal(monthSum, index.entries.filter((e) => e.month).length);
  assert.equal(facets.geo, index.entries.filter((e) => e.hasGeo).length);
});

test('kind facet counts ignore the kind filter itself but respect others', () => {
  const all = run({});
  const onlyWz = run({ kinds: ['wz'] });
  assert.ok(onlyWz.results.every((r) => r.entry.kind === 'wz'));
  assert.deepEqual(onlyWz.facets.kinds, all.facets.kinds, 'kind facet unaffected by kind selection');
  const tagged = run({ kinds: ['wz'], tags: ['oswiata'] });
  const expectedWsInOswiata = index.entries.filter((e) => e.kind === 'ws' && e.tags.includes('oswiata')).length;
  assert.equal(tagged.facets.kinds.ws || 0, expectedWsInOswiata);
  // tag facet reflects the kind filter
  const wzOswiata = index.entries.filter((e) => e.kind === 'wz' && e.tags.includes('oswiata')).length;
  assert.equal(tagged.facets.tags.oswiata, wzOswiata);
  assert.equal(tagged.results.length, wzOswiata);
});

test('OR within a group, AND across groups', () => {
  const a = run({ tags: ['oswiata'] }).results.length;
  const b = run({ tags: ['reklama'] }).results.length;
  const both = run({ tags: ['oswiata', 'reklama'] }).results.length;
  const overlap = index.entries.filter((e) => e.tags.includes('oswiata') && e.tags.includes('reklama')).length;
  assert.equal(both, a + b - overlap);
});

test('search: przedszkole finds records via investment text', () => {
  const { results } = run({ q: 'przedszkole' });
  assert.ok(results.length >= 5);
  for (const r of results) assert.match(r.entry.doc.fields.map((f) => f.folded).join(' '), /przedszkol/);
});

test('search ignores diacritics and case', () => {
  const a = run({ q: 'DRWĘCKA' }).results.map((r) => r.entry.id).sort();
  const b = run({ q: 'drwecka' }).results.map((r) => r.entry.id).sort();
  assert.ok(a.length > 0);
  assert.deepEqual(a, b);
});

test('period filter: explicit range and relative presets', () => {
  const y2022 = run({ from: '2022-01', to: '2022-12' }).results;
  assert.ok(y2022.length > 0);
  assert.ok(y2022.every((r) => r.entry.month >= '2022-01' && r.entry.month <= '2022-12'));
  assert.deepEqual(resolvePeriod({ period: '3m' }, '2026-09'), { from: '2026-07', to: '2026-09' });
  assert.deepEqual(resolvePeriod({ period: '12m' }, '2026-09'), { from: '2025-10', to: '2026-09' });
  assert.deepEqual(resolvePeriod({ from: '2024-01', to: null }, '2026-09'), { from: '2024-01', to: null });
  const last3 = run({ period: '3m' });
  assert.ok(last3.results.every((r) => r.entry.month >= '2026-07'));
  // month facet ignores the period filter (histogram shows everything else)
  assert.deepEqual(last3.facets.months, run({}).facets.months);
});

test('applicant, area, street, geo and file filters', () => {
  const persons = run({ applicants: ['person'] }).results;
  assert.ok(persons.length > 0 && persons.every((r) => r.entry.applicant === 'person'));
  const area = Object.keys(index.dicts.areas).find((a) => index.entries.some((e) => e.area === a));
  assert.ok(run({ areas: [area] }).results.every((r) => r.entry.area === area));
  const key = streetKey('Drwęcka');
  const st = run({ streets: [key] }).results;
  assert.ok(st.length >= 4 && st.every((r) => r.entry.streetKeys.includes(key)));
  const geo = run({ geoOnly: true }).results;
  assert.ok(geo.every((r) => r.entry.hasGeo));
  assert.ok(geo.length < index.entries.length, 'fixture includes records without location');
  const file = index.files.find((f) => (f.record_ids || []).length > 1);
  const byFile = run({ file: file.file_id }).results.map((r) => r.entry.id).sort();
  assert.deepEqual(byFile, [...file.record_ids].sort());
});

test('street filter matches every street of an intersection/list address', () => {
  const multi = index.entries.find((e) => e.streetKeys.length > 1);
  assert.ok(multi, 'fixture has an address with several streets');
  for (const k of multi.streetKeys) {
    const ids = run({ streets: [k] }).results.map((r) => r.entry.id);
    assert.ok(ids.includes(multi.id), `${multi.id} not found under ${k}`);
    assert.ok(run({}).facets.streets[k] >= 1);
  }
});

test('near filter and per-radius facet counts', () => {
  const e = index.entries.find((x) => x.hasGeo);
  const { results, facets } = run({ near: { lat: e.lat, lon: e.lon, r: 250 } });
  assert.ok(results.some((r) => r.entry.id === e.id));
  assert.ok(facets.nearRadii[250] <= facets.nearRadii[500]);
  assert.ok(facets.nearRadii[500] <= facets.nearRadii[1000]);
  assert.equal(facets.nearRadii[250], results.length);
});

test('bbox filter and visible-area facet', () => {
  const bbox = [21.06, 52.24, 21.09, 52.26];
  const { results } = run({ bbox });
  assert.ok(results.length > 0 && results.every((r) => inBbox(r.entry, bbox)));
  const viaCtx = evaluate(index.entries, defaultFilters(), { latestMonth: index.maxMonth, tokens: [], viewBbox: bbox });
  assert.equal(viaCtx.facets.bbox, results.length);
});

test('"without" counts tell how many results removing a filter would give', () => {
  const f = { kinds: ['cp'], q: 'przedszkole' };
  const { results, facets } = run(f);
  assert.equal(results.length, 0);
  assert.equal(facets.without.kind, run({ q: 'przedszkole' }).results.length);
  assert.equal(facets.without.q, run({ kinds: ['cp'] }).results.length);
});

test('sorting', () => {
  const { results } = run({});
  const newest = sortResults([...results], 'newest').map((r) => r.entry.ts);
  assert.deepEqual(newest, [...newest].sort().reverse());
  const oldest = sortResults([...results], 'oldest').map((r) => r.entry.ts);
  assert.deepEqual(oldest, [...oldest].sort());
  const byStreet = sortResults([...results], 'street').map((r) => r.entry.streetSort).filter(Boolean);
  const coll = new Intl.Collator('pl', { sensitivity: 'base', numeric: true });
  for (let i = 1; i < byStreet.length; i += 1) assert.ok(coll.compare(byStreet[i - 1], byStreet[i]) <= 0);
  const rel = run({ q: 'drwecka' }).results;
  const relSorted = sortResults([...rel], 'relevance');
  for (let i = 1; i < relSorted.length; i += 1) assert.ok(relSorted[i - 1].score >= relSorted[i].score);
});

test('effective sort', () => {
  assert.equal(effectiveSort(null, false), 'newest');
  assert.equal(effectiveSort(null, true), 'relevance');
  assert.equal(effectiveSort('relevance', false), 'newest');
  assert.equal(effectiveSort('street', true), 'street');
});

test('hasActiveFilters', () => {
  assert.equal(hasActiveFilters(defaultFilters()), false);
  assert.equal(hasActiveFilters({ ...defaultFilters(), q: '  ' }), false);
  assert.equal(hasActiveFilters({ ...defaultFilters(), sort: 'oldest' }), false);
  assert.equal(hasActiveFilters({ ...defaultFilters(), geoOnly: true }), true);
});

test('street helpers', () => {
  assert.equal(streetSortKey('gen. Fieldorfa "Nila"'), 'Fieldorfa "Nila"');
  assert.equal(streetSortKey('Al. Stanów Zjednoczonych'), 'Stanów Zjednoczonych');
  assert.equal(streetKey('ul. Żółkiewskiego'), 'zolkiewskiego');
  assert.equal(streetKey('Gen. A.E. Fieldorfa „Nila”'), 'a e fieldorfa nila');
  assert.equal(streetKey(null), null);
});

test('distance', () => {
  const d = distanceMeters(52.2297, 21.0122, 52.2297, 21.0268);
  assert.ok(d > 950 && d < 1050, `≈1 km, got ${d}`);
});

test('related chain is chronological and includes the record', () => {
  const e = index.entries.find((x) => (x.rec.related || []).length >= 2);
  const chain = relatedChain(index, e);
  assert.ok(chain.some((x) => x.id === e.id));
  for (let i = 1; i < chain.length; i += 1) assert.ok(chain[i - 1].ts <= chain[i].ts);
});

test('index tolerates broken input', () => {
  const idx = buildIndex({ records: [null, { id: 'x' }, { nope: 1 }], kinds: null }, null);
  assert.equal(idx.entries.length, 1);
  const { results } = evaluate(idx.entries, { ...defaultFilters(), q: 'abc', kinds: ['wz'] }, { tokens: ['abc'] });
  assert.equal(results.length, 0);
  const empty = buildIndex(null, null);
  assert.equal(empty.entries.length, 0);
});

test('relationReason names the shared parcel(s) or the shared address', () => {
  const p = (number, obreb = '3-02-03') => ({ number, obreb, id: `146507_8.${obreb.slice(2).replace('-', '')}.${number}` });
  const a = { parcels: [p('3'), p('11')], address: { street: 'Chodakowska', number: '19', parts: [{ street: 'Chodakowska', number: '19', numbers: ['19'] }] } };
  assert.equal(relationReason(a, { parcels: [p('3')] }), 'wspólna działka 3 (obr. 3-02-03)');
  assert.equal(relationReason(a, { parcels: [p('3'), p('11')] }), 'wspólne działki 3, 11 (obr. 3-02-03)');
  assert.equal(relationReason(a, { parcels: [p('7')], address: { street: 'ul. Chodakowska', number: '19' } }), 'ten sam adres');
  assert.equal(relationReason(a, { parcels: [p('7')], address: { street: 'Chodakowska', number: '21' } }), null);
  assert.equal(relationReason({}, {}), null);
});

// --- v2: datasets, opt-in permits, new facets ---------------------------------------------------

test('records of the second dataset (BAiPP) carry dataset, issuer and outcome', () => {
  const baipp = index.entries.filter((e) => e.dataset === 'baipp');
  assert.ok(baipp.length >= 10);
  assert.ok(baipp.every((e) => e.issuer === 'city'));
  assert.ok(baipp.some((e) => e.outcome === 'refusal'));
  assert.equal(index.byId.get('wz-am-2026-95').outcome, 'refusal');
  assert.ok(index.entries.filter((e) => e.dataset === 'district').every((e) => e.outcome === null));
});

test('addPermits merges permits.json once; counts_by_kind matches the file', () => {
  assert.equal(added.length, permitsDoc.records.length);
  assert.equal(full.entries.length, index.entries.length + permitsDoc.records.length);
  assert.equal(full.permitsLoaded, true);
  assert.equal(addPermits(full, permitsDoc).length, 0, 'idempotent');
  for (const k of ['pb', 'zg']) assert.equal(full.entries.filter((e) => e.kind === k).length, full.countsByKind[k]);
  const p = full.byId.get('pb-st-mz-pa-2026-29594');
  assert.equal(p.scope, 'inne');
  assert.equal(p.category, 'XIII');
  assert.equal(p.dataset, 'rwdz');
});

test('prepareEntries builds the permit entries in slices without touching the index; addPermits then merges them', async () => {
  const fresh = buildIndex(load('records.json'), load('sources.json'));
  let pauses = 0;
  const prepared = await prepareEntries(permitsDoc.records, fresh.dicts, { slice: 10, pause: async () => { pauses += 1; } });
  assert.equal(prepared.size, permitsDoc.records.length);
  assert.equal(pauses, Math.ceil(permitsDoc.records.length / 10) - 1, 'one pause between slices');
  assert.equal(fresh.permitsLoaded, false, 'index untouched until the merge');
  assert.equal(fresh.entries.length, index.entries.length);
  const merged = addPermits(fresh, permitsDoc, prepared);
  assert.equal(merged.length, permitsDoc.records.length);
  assert.equal(merged[0], prepared.get(merged[0].id), 'the prepared entry objects are used');
  assert.deepEqual(fresh.entries.map((e) => e.id), full.entries.map((e) => e.id), 'same index as the one-shot merge');
  assert.deepEqual(fresh.byId.get('pb-st-mz-pa-2026-29594').doc, full.byId.get('pb-st-mz-pa-2026-29594').doc);
  assert.deepEqual([...fresh.streets.keys()].sort(), [...full.streets.keys()].sort());
  assert.deepEqual(fresh.kindMonths, full.kindMonths);
});

test('default kinds exclude permits even when loaded; the kind facet still counts them', () => {
  const def = runFull({});
  assert.equal(def.results.length, index.entries.length);
  assert.ok(def.results.every((r) => !['pb', 'zg'].includes(r.entry.kind)));
  assert.equal(def.facets.kinds.pb, full.countsByKind.pb, 'what ticking "pb" would add');
  assert.equal(def.facets.scopeTotal, index.entries.length);
  // other facets are not polluted by switched-off permits
  assert.deepEqual(def.facets.tags, run({}).facets.tags);
  assert.deepEqual(def.facets.months, run({}).facets.months);
  assert.equal(def.facets.scope.budowa, undefined);
});

test('switching pb on adds exactly the permits and their facets', () => {
  const on = runFull({ kinds: ['wz', 'cp', 'ws', 'pb'] });
  assert.equal(on.results.length, index.entries.length + full.countsByKind.pb);
  assert.ok(on.facets.scope.budowa > 0);
  assert.ok(on.facets.category.XIII > 0);
  assert.equal(on.facets.scopeTotal, on.results.length);
  const onlyPb = runFull({ kinds: ['pb'], scopes: ['rozbiorka'] });
  assert.ok(onlyPb.results.length > 0 && onlyPb.results.every((r) => r.entry.kind === 'pb' && r.entry.scope === 'rozbiorka'));
});

test('dataset, issuer and outcome filters', () => {
  const refusals = run({ outcomes: ['refusal'] }).results;
  assert.ok(refusals.length >= 2 && refusals.every((r) => r.entry.outcome === 'refusal'));
  const city = run({ issuers: ['city'] }).results;
  assert.ok(city.every((r) => r.entry.issuer === 'city'));
  const both = run({ datasets: ['baipp', 'district'] }).results;
  assert.equal(both.length, index.entries.length);
  const { facets } = run({ datasets: ['baipp'] });
  assert.equal(facets.dataset.district, index.entries.filter((e) => e.dataset === 'district').length, 'own group ignores itself');
});

test('availableOptions lists the options that exist for a kind selection', () => {
  const def = availableOptions(full.entries, defaultFilters().kinds);
  assert.deepEqual(Object.keys(def.dataset).sort(), ['baipp', 'district']);
  assert.equal(Object.keys(def.scope).length, 0, 'no permit scopes without permits');
  const pb = availableOptions(full.entries, ['wz', 'cp', 'ws', 'pb']);
  assert.ok(pb.dataset.rwdz > 0 && pb.scope.budowa > 0 && pb.issuer.voivode > 0);
});

test('sameSplit: "Organ" repeats "Źródło danych" for the planning kinds, not once permits are in', () => {
  assert.equal(sameSplit(full.entries, defaultFilters().kinds, 'issuer', 'dataset'), true, 'district ↔ district, baipp ↔ city');
  assert.equal(sameSplit(full.entries, ['wz', 'cp', 'ws', 'pb'], 'issuer', 'dataset'), false, 'permits: several issuers in rwdz');
  const e = (dataset, issuer, kind = 'wz') => ({ kind, dataset, issuer });
  assert.equal(sameSplit([e('a', 'x'), e('b', 'x')], ['wz'], 'issuer', 'dataset'), false, 'one issuer, two datasets');
  assert.equal(sameSplit([e('a', 'x'), e('a', 'y')], ['wz'], 'issuer', 'dataset'), false, 'two issuers, one dataset');
  assert.equal(sameSplit([e('a', 'x'), e('b', 'y', 'pb')], ['wz'], 'issuer', 'dataset'), true, 'other kinds ignored');
});

test('monthBounds follows the kind selection (permits reach back to 2016)', () => {
  assert.deepEqual(monthBounds(full, ['wz', 'cp', 'ws']), { min: index.minMonth, max: '2026-09' });
  const b = monthBounds(full, ['wz', 'cp', 'ws', 'pb']);
  assert.ok(b.min < '2017-01', b.min);
  assert.equal(b.max, '2026-10');
  // relative periods count back from the newest month of the selected kinds
  const last3 = runFull({ kinds: ['pb'], period: '3m' }).results;
  assert.ok(last3.every((r) => r.entry.month >= '2026-08'));
});

test('hasActiveFilters treats the default kind selection as no filter', () => {
  assert.equal(hasActiveFilters({ ...defaultFilters(), kinds: ['ws', 'cp', 'wz'] }), false);
  assert.equal(hasActiveFilters({ ...defaultFilters(), kinds: ['wz', 'cp', 'ws', 'pb'] }), true);
  assert.equal(hasActiveFilters({ ...defaultFilters(), outcomes: ['refusal'] }), true);
});

test('related chains cross datasets once permits are loaded (WZ → pozwolenie na budowę)', () => {
  const wz = full.byId.get('wz-2023-12');
  const chain = relatedChain(full, wz);
  assert.ok(chain.some((e) => e.kind === 'pb'), 'related permits present');
  assert.ok(relatedChain(index, index.byId.get('wz-2023-12')).every((e) => e.kind !== 'pb'), 'skipped while not loaded');
  for (let i = 1; i < chain.length; i += 1) assert.ok(chain[i - 1].ts <= chain[i].ts);
});

test('dataset of pages and files (file inherits from its first page)', () => {
  const pagesById = new Map([['p1', { page_id: 'p1', source: 'baipp' }], ['p2', { page_id: 'p2' }]]);
  assert.equal(datasetOf({ page_ids: ['p1'] }, pagesById), 'baipp');
  assert.equal(datasetOf({ page_ids: ['p2'] }, pagesById), 'district');
  assert.equal(datasetOf({ source: 'rwdz', page_ids: ['p1'] }, pagesById), 'rwdz');
  assert.equal(fileDataset(index, index.filesById.get('rwdz-wnioski')), 'rwdz');
});

test('search finds permits by GUNB register number and records by outcome label', () => {
  const byRegister = runFull({ kinds: ['pb'], q: 'WNIOSEK/29594/2026' }).results;
  assert.deepEqual(byRegister.map((r) => r.entry.id), ['pb-st-mz-pa-2026-29594']);
  const odmowa = run({ q: 'odmowa' }).results.map((r) => r.entry.id);
  assert.ok(odmowa.includes('wz-am-2026-95') && odmowa.includes('wz-am-2022-148'));
});

test('outcome coverage: the outcome filter sees only the WZ/CP decisions that state an outcome (BAiPP)', () => {
  const f = { ...defaultFilters(), outcomes: ['refusal'] };
  const cov = outcomeCoverage(index.entries, f, ctx(f));
  const decisions = index.entries.filter((e) => e.kind === 'wz' || e.kind === 'cp');
  assert.equal(cov.decisions, decisions.length);
  assert.equal(cov.known, decisions.filter((e) => e.outcome).length);
  assert.equal(cov.unknown, decisions.filter((e) => !e.outcome).length);
  assert.ok(cov.unknown > 0 && cov.known > 0);
  // other filters narrow the base set; the outcome filter itself does not
  const wz = outcomeCoverage(index.entries, { ...f, kinds: ['wz'] }, ctx(f));
  assert.equal(wz.decisions, index.entries.filter((e) => e.kind === 'wz').length);
});

test('relative presets count back per kind: switching permits on never hides planning records', () => {
  const entries = [
    { id: 'wz-1', kind: 'wz', month: '2026-07', tags: [], streetKeys: [], fileIds: [], doc: {} },
    { id: 'pb-1', kind: 'pb', month: '2026-10', tags: [], streetKeys: [], fileIds: [], doc: {} },
    { id: 'pb-0', kind: 'pb', month: '2026-07', tags: [], streetKeys: [], fileIds: [], doc: {} },
  ];
  const f = { ...defaultFilters(), period: '3m', kinds: ['wz', 'cp', 'ws', 'pb'] };
  const latestByKind = { wz: '2026-09', cp: '2026-09', ws: '2026-09', pb: '2026-10' };
  const ids = (ff, c) => evaluate(entries, ff, c).results.map((r) => r.entry.id).sort();
  assert.deepEqual(ids(f, { latestMonth: '2026-10', latestByKind }), ['pb-1', 'wz-1'], 'wz Jul–Sep, pb Aug–Oct');
  assert.deepEqual(ids({ ...f, kinds: ['wz', 'cp', 'ws'] }, { latestMonth: '2026-09', latestByKind: { wz: '2026-09' } }), ['wz-1']);
  // the old behaviour (one anchor for every kind) hid the July WZ
  assert.deepEqual(ids(f, { latestMonth: '2026-10' }), ['pb-1']);
  const { byKind } = periodRanges(f, '2026-10', latestByKind);
  assert.deepEqual(byKind.wz, { from: '2026-07', to: '2026-09' });
  assert.deepEqual(byKind.pb, { from: '2026-08', to: '2026-10' });
  const spans = periodSpans(f, '2026-10', latestByKind, f.kinds);
  assert.equal(spans.length, 2);
  assert.deepEqual(spans[0].kinds, ['wz', 'cp', 'ws']);
  assert.deepEqual(spans[1].kinds, ['pb']);
  // an explicit range is shared by every kind
  assert.equal(periodRanges({ ...f, period: null, from: '2026-01', to: '2026-03' }, '2026-10', latestByKind).byKind, null);
});

test('sanitizeFilters drops values the data does not know (stale or hand-edited links)', () => {
  const c = { kindCodes: index.kindCodes, dicts: index.dicts, filesById: index.filesById };
  const clean = defaultFilters();
  assert.equal(sanitizeFilters(clean, c), clean, 'nothing to drop: same object');
  const tag = Object.keys(index.dicts.tags)[0];
  const dirty = {
    ...clean, kinds: ['zz'], tags: ['nieistniejacy-typ', tag], areas: ['xyz'], outcomes: ['refusal', 'constructor'],
    datasets: ['foo'], file: 'deadbeef00', streets: ['jakas-ulica'],
  };
  const out = sanitizeFilters(dirty, c);
  assert.deepEqual(out.kinds, ['wz', 'cp', 'ws'], 'no known kind left → the default selection');
  assert.deepEqual(out.tags, [tag]);
  assert.deepEqual(out.areas, []);
  assert.deepEqual(out.outcomes, ['refusal']);
  assert.deepEqual(out.datasets, []);
  assert.equal(out.file, null);
  assert.deepEqual(out.streets, ['jakas-ulica'], 'streets may come from the lazily loaded permits: kept');
  assert.deepEqual(sanitizeFilters({ ...clean, kinds: ['wz', 'pb'] }, c).kinds, ['wz', 'pb'], 'opt-in kinds are known before loading');
  const rwdz = [...index.filesById.keys()].find((k) => k.startsWith('rwdz-'));
  assert.equal(sanitizeFilters({ ...clean, file: rwdz }, c).file, rwdz, 'register files are listed in sources.json');
});

test('near filter: a street-level point with a stated uncertainty may be near (optional geo.uncertainty_m)', () => {
  const at = { lat: 52.24, lon: 21.08 };
  const far = { hasGeo: true, lat: 52.2454, lon: 21.08, uncertainty: null }; // ~600 m north
  assert.equal(nearHit(far, at, 500), false);
  assert.equal(nearHit({ ...far, uncertainty: 700 }, at, 500), true);
  assert.equal(nearHit({ ...far, uncertainty: 50 }, at, 500), false);
  assert.equal(nearHit({ hasGeo: false }, at, 500), false);
});

test('nearestAddressPoint: "what is near Drwęcka 23" → the nearest house number on that street', () => {
  const hit = nearestAddressPoint(index, 'Drwęcka 23');
  assert.ok(hit, 'no point for a known street');
  assert.equal(hit.entry.streetKeys.includes(streetKey('Drwęcka')), true);
  assert.equal(parseInt(hit.number, 10), 18);
  assert.ok(Number.isFinite(hit.lat) && Number.isFinite(hit.lon));
  assert.equal(nearestAddressPoint(index, 'ul. Drwęcka 23')?.number, hit.number, 'street prefix ignored');
  assert.equal(nearestAddressPoint(index, 'Nieistniejąca 5'), null, 'unknown street');
  assert.equal(nearestAddressPoint(index, 'Drwęcka 300'), null, 'house number too far away');
  assert.equal(nearestAddressPoint(index, 'Drwęcka'), null, 'no house number');
  assert.equal(nearestAddressPoint(index, 'przedszkole'), null);
  // same parity wins a tie: 73 and 97 on Ostrobramska → 85 is 12 from both; 85 is odd like both, then the closest
  assert.equal(parseInt(nearestAddressPoint(index, 'Ostrobramska 79').number, 10), 73);
});
