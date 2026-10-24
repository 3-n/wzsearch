import { test } from 'node:test';
import assert from 'node:assert/strict';
import { stepLabel, kindCountLabel } from '../../site/js/views/detail.js';

test('related-records steps name permits ("pozwolenie na budowę 05.2024", demolition separately)', () => {
  assert.equal(stepLabel({ kind: 'ws', month: '2023-03' }), 'wszczęcie 03.2023');
  assert.equal(stepLabel({ kind: 'wz', month: '2023-09' }), 'decyzja WZ 09.2023');
  assert.equal(stepLabel({ kind: 'pb', scope: 'budowa', month: '2024-05' }), 'pozwolenie na budowę 05.2024');
  assert.equal(stepLabel({ kind: 'pb', scope: 'rozbiorka', month: '2024-05' }), 'pozwolenie na rozbiórkę 05.2024');
  assert.equal(stepLabel({ kind: 'zg', month: null }), 'zgłoszenie ?');
});

test('a refusal or a discontinuation is not "decyzja WZ" in the related-records summary', () => {
  assert.equal(stepLabel({ kind: 'wz', outcome: 'refusal', month: '2025-03' }), 'odmowa WZ 03.2025');
  assert.equal(stepLabel({ kind: 'wz', outcome: 'discontinued', month: '2023-10' }), 'umorzenie WZ 10.2023');
  assert.equal(stepLabel({ kind: 'cp', outcome: 'transfer', month: '2023-10' }), 'przeniesienie CP 10.2023');
  assert.equal(stepLabel({ kind: 'wz', outcome: 'granted', month: '2023-10' }), 'decyzja WZ 10.2023');
  assert.equal(stepLabel({ kind: 'wz', outcome: null, month: '2023-10' }), 'decyzja WZ 10.2023');
  assert.equal(stepLabel({ kind: 'wz', outcome: 'constructor', month: '2023-10' }), 'decyzja WZ 10.2023');
});

test('long chains count outcomes within the WZ/CP decisions', () => {
  assert.equal(kindCountLabel('wz', [{ outcome: 'refusal' }, { outcome: 'discontinued' }, { outcome: null }]), '3 decyzje WZ (w tym 1 odmowa, 1 umorzenie)');
  assert.equal(kindCountLabel('wz', [{ outcome: 'refusal' }, { outcome: 'refusal' }]), '2 decyzje WZ (w tym 2 odmowy)');
  assert.equal(kindCountLabel('cp', [{ outcome: 'granted' }]), '1 decyzja CP');
  assert.equal(kindCountLabel('pb', [{}, {}, {}, {}, {}]), '5 pozwoleń');
});
