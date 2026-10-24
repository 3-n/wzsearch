import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  pluralForm, plural, WPIS, formatDate, formatDateNumeric, formatMonth, formatMonthShort, formatMonthRange,
  formatDateTime, addMonths, monthRange, formatBytes, formatDistance, truncate, formatNumber, tidyCell, formatMonthSpan,
  daysBetween, decisionAfter, formatLineList, formatCubature,
} from '../../site/js/format.js';

test('Polish plural forms for "wpis"', () => {
  const cases = {
    0: 'wpisów', 1: 'wpis', 2: 'wpisy', 3: 'wpisy', 4: 'wpisy', 5: 'wpisów', 11: 'wpisów', 12: 'wpisów',
    13: 'wpisów', 14: 'wpisów', 21: 'wpisów', 22: 'wpisy', 24: 'wpisy', 25: 'wpisów', 101: 'wpisów',
    102: 'wpisy', 112: 'wpisów', 122: 'wpisy', 1000: 'wpisów',
  };
  for (const [n, form] of Object.entries(cases)) assert.equal(pluralForm(Number(n), WPIS), form, `n=${n}`);
});

test('plural() prefixes the formatted number', () => {
  assert.equal(plural(37, WPIS), '37 wpisów');
  assert.equal(plural(1, WPIS), '1 wpis');
  assert.equal(plural(23, WPIS), '23 wpisy');
  assert.equal(formatNumber(12345).replace(/\s/g, ' '), '12 345');
});

test('dates in Polish', () => {
  assert.equal(formatDate('2026-07-09'), '9 lipca 2026');
  assert.equal(formatDate('2020-12-31'), '31 grudnia 2020');
  assert.equal(formatDate('2026-02-01T10:00:00Z'), '1 lutego 2026');
  assert.equal(formatDate(null), '');
  assert.equal(formatDate('nonsense'), '');
  assert.equal(formatDate('2026-13-01'), '');
  assert.equal(formatDateNumeric('2026-07-09'), '09.07.2026');
});

test('months and ranges', () => {
  assert.equal(formatMonth('2026-07'), 'lipiec 2026');
  assert.equal(formatMonth('2026-07', { capitalize: true }), 'Lipiec 2026');
  assert.equal(formatMonth('2021-10'), 'październik 2021');
  assert.equal(formatMonthShort('2025-10'), 'paź 2025');
  assert.equal(formatMonthRange('2024-01', '2024-12'), '2024');
  assert.equal(formatMonthRange('2023-01', '2024-12'), '2023–2024');
  assert.equal(formatMonthRange('2024-03', '2024-03'), 'marzec 2024');
  assert.equal(formatMonthRange('2024-03', '2024-05'), 'mar 2024 – maj 2024');
  assert.equal(formatMonthRange('2024-03', null), 'od mar 2024');
  assert.equal(formatMonthRange(null, '2024-03'), 'do mar 2024');
  assert.equal(formatMonthRange(null, null), '');
});

test('month arithmetic', () => {
  assert.equal(addMonths('2026-01', -1), '2025-12');
  assert.equal(addMonths('2026-09', -11), '2025-10');
  assert.equal(addMonths('2025-12', 1), '2026-01');
  assert.equal(addMonths('bad', 1), null);
  assert.deepEqual(monthRange('2025-11', '2026-02'), ['2025-11', '2025-12', '2026-01', '2026-02']);
  assert.deepEqual(monthRange('2026-02', '2025-11'), []);
});

test('date-time in Warsaw time zone', () => {
  // 02:00Z on 23 Oct 2026 is 04:00 CEST
  const s = formatDateTime('2026-10-23T02:00:00Z');
  assert.match(s, /^23 października 2026, 04:00$/);
  assert.equal(formatDateTime('2026-10-23T02:00:00Z', { time: false }), '23 października 2026');
  assert.equal(formatDateTime(null), '');
  assert.equal(formatDateTime('x'), '');
});

test('misc formatting', () => {
  assert.equal(formatBytes(512), '512 B');
  assert.equal(formatBytes(13036), '12,7 kB');
  assert.equal(formatBytes(null), '');
  assert.equal(formatDistance(250), '250 m');
  assert.equal(formatDistance(1000), '1 km');
  assert.equal(formatDistance(1500), '1,5 km');
  assert.equal(truncate('budowa budynku mieszkalnego jednorodzinnego', 20), 'budowa budynku…');
  assert.equal(truncate('krótki', 20), 'krótki');
  assert.equal(truncate(null, 5), '');
});

test('tidyCell turns the office\'s space-run line breaks into real ones, wording untouched', () => {
  assert.equal(tidyCell('33/1cz.                                                3-06-06'), '33/1cz.\n3-06-06');
  assert.equal(tidyCell('dz. 46/4\n3-01-24'), 'dz. 46/4\n3-01-24');
  assert.equal(tidyCell('  dz. 38/1 ,43/4  \n\n 3-02-06 '), 'dz. 38/1 ,43/4\n3-02-06');
  assert.equal(tidyCell(null), '');
});

test('formatMonthSpan spells months out for prose', () => {
  assert.equal(formatMonthSpan('2020-08', '2020-10'), 'sierpień–październik 2020');
  assert.equal(formatMonthSpan('2020-12', '2021-02'), 'grudzień 2020 – luty 2021');
  assert.equal(formatMonthSpan('2021-05', '2021-05'), 'maj 2021');
  assert.equal(formatMonthSpan(null, null), '');
});

test('application → decision span ("decyzja po 66 dniach")', () => {
  assert.equal(daysBetween('2026-09-24', '2026-10-14'), 20);
  assert.equal(daysBetween('2024-02-28', '2024-03-01'), 2, 'leap year');
  assert.equal(daysBetween('2026-03-28', '2026-03-30'), 2, 'across the DST change');
  assert.equal(daysBetween(null, '2026-01-01'), null);
  assert.equal(decisionAfter('2023-11-08', '2024-01-30'), 'decyzja po 83 dniach');
  assert.equal(decisionAfter('2024-01-30', '2024-01-30'), 'decyzja tego samego dnia');
  assert.equal(decisionAfter('2024-01-30', '2024-01-31'), 'decyzja po 1 dniu');
  assert.equal(decisionAfter('2024-02-01', '2024-01-30'), null, 'inconsistent dates are not shown');
  assert.equal(decisionAfter('2016-01-01', '2026-01-01'), 'decyzja po 3653 dniach');
});

test('line numbers as compact ranges', () => {
  assert.equal(formatLineList([14, 12, 13, 20, 20]), '12–14, 20');
  assert.equal(formatLineList([338664]), '338664', 'line numbers are references: no digit grouping');
  assert.equal(formatLineList([96620, 96621, 96622, 96633, 358120, 358121]), '96620–96622, 96633, 358120–358121');
  assert.equal(formatLineList([]), '');
  assert.equal(formatLineList([0, -1, 2.5, 7]), '7');
});

test('cubature', () => {
  assert.equal(formatCubature(1234.5), '1234,5 m³');
  assert.equal(formatCubature(12502).replace(/\s/g, ' '), '12 502 m³');
  assert.equal(formatCubature(0), '');
  assert.equal(formatCubature(null), '');
});
