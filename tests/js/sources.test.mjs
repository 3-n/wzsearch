import { test } from 'node:test';
import assert from 'node:assert/strict';
import { reconcile, splitByDataset, cityWideTotals } from '../../site/js/views/sources.js';

test('reconcile separates declared blocks, blocks without a declared count and mismatches', () => {
  const pages = [
    { period: '2020-12', blocks: [{ declared_count: 3, parsed_count: 1, count_mismatch: true }, { declared_count: 1, parsed_count: 1 }] },
    { period: '2020-10', blocks: [{ declared_count: null, parsed_count: 5 }, { declared_count: 0, parsed_count: 0 }] },
    { period: '2020-08', blocks: [{ declared_count: null, parsed_count: 9 }, { declared_count: null, parsed_count: null }] },
    { period: '2021-01', blocks: null },
  ];
  const files = [{ parsed_count: 1 }, { parsed_count: 1 }, { parsed_count: 5 }, { parsed_count: 0 }, { parsed_count: 9 }, { parsed_count: null }];
  assert.deepEqual(reconcile(pages, files), {
    declared: 4, parsedDeclared: 2, undeclaredRows: 14, undeclaredPeriods: ['2020-08', '2020-10'], rows: 16, mismatches: 1,
  });
  assert.deepEqual(reconcile([], []), { declared: 0, parsedDeclared: 0, undeclaredRows: 0, undeclaredPeriods: [], rows: 0, mismatches: 0 });
});

test('sources.json splits into datasets in tab order; files follow their first page', () => {
  const pages = [
    { page_id: 'rwdz', source: 'rwdz' }, { page_id: 'rejestry25', source: 'baipp' }, { page_id: 'p-2026-09' },
    { page_id: 'p-2026-08', source: 'district' },
  ];
  const files = [
    { file_id: 'a', page_ids: ['p-2026-09'] }, { file_id: 'b', page_ids: ['rejestry25'] }, { file_id: 'rwdz-wnioski', source: 'rwdz', page_ids: ['rwdz'] },
  ];
  const split = splitByDataset(pages, files);
  assert.deepEqual([...split.keys()], ['district', 'baipp', 'rwdz']);
  assert.deepEqual(split.get('district').pages.map((p) => p.page_id), ['p-2026-09', 'p-2026-08']);
  assert.deepEqual(split.get('baipp').files.map((f) => f.file_id), ['b']);
  assert.deepEqual(split.get('rwdz').files.map((f) => f.file_id), ['rwdz-wnioski']);
  assert.deepEqual([...splitByDataset([], []).keys()], []);
});

test('city-wide totals of the BAiPP files', () => {
  assert.deepEqual(cityWideTotals([{ rows_total: 162, parsed_count: 5 }, { rows_total: 85, parsed_count: 2 }, { parsed_count: 1 }]),
    { rowsTotal: 247, kept: 8, unknown: 1 });
});
