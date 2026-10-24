import { test } from 'node:test';
import assert from 'node:assert/strict';
import { permitsNeeded, missingPermitIds, hasMissingPermits, idlePrefetchAllowed, shouldFetchPermits } from '../../site/js/lazy.js';
import { defaultFilters } from '../../site/js/filters.js';

const wz = { id: 'wz-2023-12', rec: { id: 'wz-2023-12', related: ['ws-6730-2023-1', 'pb-st-mz-pa-2023-30125', 'zg-st-mz-pa-2022-1'] } };
const plain = { id: 'cp-2020-1', rec: { id: 'cp-2020-1', related: ['ws-6733-2020-1'] } };
const byId = new Map([[wz.id, wz], [plain.id, plain], ['ws-6730-2023-1', {}]]);
const files = new Map([['rwdz-wnioski', { file_id: 'rwdz-wnioski', source: 'rwdz' }], ['abc1234567', { file_id: 'abc1234567' }]]);
const ctx = { loaded: false, byId, filesById: files, fileDataset: (f) => f.source || 'district' };
const state = (patch = {}, filters = {}) => ({ route: 'explore', recordId: null, ...patch, filters: { ...defaultFilters(), ...filters } });

test('nothing is needed for the default view (the idle prefetch covers it)', () => {
  assert.equal(permitsNeeded(state(), ctx), null);
  assert.equal(permitsNeeded(state({}, { kinds: ['wz'] }), ctx), null);
  assert.equal(permitsNeeded(state({ route: 'record', recordId: 'cp-2020-1' }), ctx), null);
});

test('switching pb/zg on needs the permits layer', () => {
  assert.equal(permitsNeeded(state({}, { kinds: ['wz', 'cp', 'ws', 'pb'] }), ctx), 'kinds');
  assert.equal(permitsNeeded(state({}, { kinds: ['zg'] }), ctx), 'kinds');
});

test('a permalink to a permit, or a record with related permits, needs it', () => {
  assert.equal(permitsNeeded(state({ route: 'record', recordId: 'pb-st-mz-pa-2026-29594' }), ctx), 'permalink');
  assert.equal(permitsNeeded(state({ route: 'record', recordId: 'wz-1999-1' }), ctx), null, 'unknown planning id: just "not found"');
  assert.equal(permitsNeeded(state({ route: 'record', recordId: 'wz-2023-12' }), ctx), 'related');
});

test('filtering by an RWDZ file needs it; district files do not', () => {
  assert.equal(permitsNeeded(state({}, { file: 'rwdz-wnioski' }), ctx), 'file');
  assert.equal(permitsNeeded(state({}, { file: 'abc1234567' }), ctx), null);
});

test('once loaded nothing is requested again', () => {
  assert.equal(permitsNeeded(state({}, { kinds: ['pb'] }), { ...ctx, loaded: true }), null);
});

test('missing related permit ids', () => {
  assert.deepEqual(missingPermitIds(wz.rec, byId), ['pb-st-mz-pa-2023-30125', 'zg-st-mz-pa-2022-1']);
  assert.equal(hasMissingPermits(plain.rec, byId), false);
  const loaded = new Map([...byId, ['pb-st-mz-pa-2023-30125', {}], ['zg-st-mz-pa-2022-1', {}]]);
  assert.deepEqual(missingPermitIds(wz.rec, loaded), []);
  assert.deepEqual(missingPermitIds({ related: null }, byId), []);
});

test('idle prefetch respects phones, Save-Data and very slow connections', () => {
  assert.equal(idlePrefetchAllowed(undefined), true);
  assert.equal(idlePrefetchAllowed({ effectiveType: '4g' }), true);
  assert.equal(idlePrefetchAllowed({ saveData: true, effectiveType: '4g' }), false);
  assert.equal(idlePrefetchAllowed({ effectiveType: 'slow-2g' }), false);
  assert.equal(idlePrefetchAllowed({ effectiveType: '2g' }), false);
  assert.equal(idlePrefetchAllowed({ effectiveType: '3g' }), true);
  assert.equal(idlePrefetchAllowed({ effectiveType: '4g' }, { smallScreen: true }), false, 'phones load it on demand only');
});

test('after a failure only a retry fetches again (no request + toast per keystroke); a silent idle failure is retried once', () => {
  assert.equal(shouldFetchPermits('idle', 'kinds'), true);
  for (const st of ['loaded', 'loading', 'unavailable']) assert.equal(shouldFetchPermits(st, 'retry'), false, st);
  assert.equal(shouldFetchPermits('error', 'kinds', 'kinds'), false);
  assert.equal(shouldFetchPermits('error', 'permalink', 'related'), false);
  assert.equal(shouldFetchPermits('error', 'retry', 'kinds'), true);
  assert.equal(shouldFetchPermits('error', 'kinds', 'idle'), true, 'the visitor never saw the idle prefetch fail');
  assert.equal(shouldFetchPermits('error', 'idle', 'idle'), false);
});
