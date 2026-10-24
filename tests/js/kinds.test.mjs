import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  KIND_ORDER, DEFAULT_KINDS, OPT_IN_KINDS, OPT_IN_ID, orderKinds, sameKinds, isDefaultKinds, effectiveKinds, wantsOptIn,
  toggleKind, withOptIn, isOptInKind,
} from '../../site/js/kinds.js';

test('the default selection is the planning kinds; permits and notifications are opt-in', () => {
  assert.deepEqual(DEFAULT_KINDS, ['wz', 'cp', 'ws']);
  assert.deepEqual(OPT_IN_KINDS, ['pb', 'zg']);
  assert.deepEqual(KIND_ORDER, ['wz', 'cp', 'ws', 'pb', 'zg']);
  assert.ok(isOptInKind('pb') && isOptInKind('zg') && !isOptInKind('wz'));
  assert.ok(OPT_IN_ID.test('pb-st-mz-pa-2026-29594') && OPT_IN_ID.test('zg-pl-mz-2025-12'));
  assert.ok(!OPT_IN_ID.test('wz-2026-15') && !OPT_IN_ID.test('wz-am-2026-95') && !OPT_IN_ID.test('pbx-1'));
});

test('kind selections are ordered and compared as sets', () => {
  assert.deepEqual(orderKinds(['zg', 'ws', 'wz', 'ws', 'xx']), ['wz', 'ws', 'zg', 'xx']);
  assert.ok(sameKinds(['ws', 'cp', 'wz'], DEFAULT_KINDS));
  assert.ok(!sameKinds(['wz', 'cp'], DEFAULT_KINDS));
  assert.ok(isDefaultKinds(['cp', 'wz', 'ws']));
  assert.ok(!isDefaultKinds(['wz', 'cp', 'ws', 'pb']));
});

test('an empty selection means the default, never "everything"', () => {
  assert.deepEqual(effectiveKinds([]), DEFAULT_KINDS);
  assert.deepEqual(effectiveKinds(undefined), DEFAULT_KINDS);
  assert.equal(wantsOptIn([]), false);
  assert.equal(wantsOptIn(['wz', 'pb']), true);
});

test('toggling kinds; unticking the last one falls back to the default', () => {
  assert.deepEqual(toggleKind(DEFAULT_KINDS, 'pb', true), ['wz', 'cp', 'ws', 'pb']);
  assert.deepEqual(toggleKind(DEFAULT_KINDS, 'cp', false), ['wz', 'ws']);
  assert.deepEqual(toggleKind(['wz'], 'wz', false), DEFAULT_KINDS);
  assert.deepEqual(withOptIn(DEFAULT_KINDS, ['zg', 'pb']), ['wz', 'cp', 'ws', 'pb', 'zg']);
  assert.deepEqual(withOptIn(['wz'], ['pb']), ['wz', 'pb']);
});
