import { test } from 'node:test';
import assert from 'node:assert/strict';
import { bucketOf, bucketUrl, cellsSet, fnv1a32, loadCells } from '../../site/js/cells.js';
import { buildIndex, addPermits } from '../../site/js/data.js';

// The same vectors as tests/test_cells.py (the first three are FNV's published ones): the pipeline and the page
// must pick the same bucket, also for ids with non-ASCII characters.
const VECTORS = [['', 0x811c9dc5], ['a', 0xe40c292c], ['foobar', 0xbf9cf968], ['ws-waw-6730-2026-624', 0x8dc9a2b2],
  ['pb-zażółć', 0xb763106e]];

test('FNV-1a matches the pipeline', () => {
  for (const [text, hash] of VECTORS) assert.equal(fnv1a32(text), hash, text);
  assert.equal(bucketOf('a', 16), 0xe40c292c % 16);
});

test('bucket URLs and sets', () => {
  const set = cellsSet({ prefix: 'cells/r-', buckets: 16 });
  assert.deepEqual(set, { prefix: 'cells/r-', buckets: 16 });
  assert.equal(bucketUrl('data/d/wawer/', set, 'a'), `data/d/wawer/cells/r-0${(0xe40c292c % 16).toString(16)}.json`);
  assert.equal(cellsSet(null), null);
  assert.equal(cellsSet({ prefix: '../x', buckets: 4 }), null);
  assert.equal(cellsSet({ prefix: 'cells/r-', buckets: 0 }), null);
  assert.equal(cellsSet({ prefix: 'cells/r-', buckets: 1.5 }), null);
});

test('loadCells fetches a bucket once and retries after a failure', async () => {
  const set = { prefix: 'cells/p-', buckets: 1 };
  let calls = 0;
  const ok = (doc) => async () => { calls += 1; return { ok: true, status: 200, json: async () => doc }; };
  const doc = { 'pb-1': [[['Kolumna', 'x']], null] };
  assert.deepEqual(await loadCells('t1/', set, 'pb-1', ok(doc)), doc['pb-1']);
  assert.equal(await loadCells('t1/', set, 'pb-2', ok(doc)), null);   // same bucket, not listed
  assert.equal(calls, 1);
  const fail = async () => { calls += 1; return { ok: false, status: 503 }; };
  await assert.rejects(loadCells('t2/', set, 'pb-1', fail), /503/);
  assert.deepEqual(await loadCells('t2/', set, 'pb-1', ok(doc)), doc['pb-1']);
  assert.equal(calls, 3);
});

test('the index keeps the cell sets of both record files', () => {
  const index = buildIndex({ records: [{ id: 'wz-1', kind: 'wz' }], cells: { prefix: 'cells/r-', buckets: 8 } }, {});
  assert.deepEqual(index.cells, { records: { prefix: 'cells/r-', buckets: 8 }, permits: null });
  addPermits(index, { records: [], cells: { prefix: 'cells/p-', buckets: 2 } });
  assert.deepEqual(index.cells.permits, { prefix: 'cells/p-', buckets: 2 });
  assert.equal(buildIndex({ records: [] }, {}).cells.records, null);
});
