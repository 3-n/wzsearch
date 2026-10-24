import { test } from 'node:test';
import assert from 'node:assert/strict';
import { promoText, PROCEDURE_ACC } from '../../site/js/copy.js';

test('promo: before permits load, a total next to a search is never shown as a match count', () => {
  const t = promoText({ loaded: false, filtered: true, main: 'pb', pb: 2361, zg: 226 });
  assert.equal(`${t.lead}${t.tail}`, 'Sprawdź też pozwolenia na budowę dla tego wyszukiwania');
  assert.equal(t.count, null);
  assert.equal(t.more, 'Razem ze zgłoszeniami (łącznie 226)');
  const u = promoText({ loaded: false, filtered: false, main: 'pb', pb: 2361, zg: 226 });
  assert.equal(`${u.lead}${u.tail}`, 'Pokaż też pozwolenia na budowę');
  assert.equal(u.count, '(łącznie 2361)');
  assert.match(u.note, /domyślnie ukryte/);
});

test('promo: once loaded, counts follow the filters', () => {
  const t = promoText({ loaded: true, filtered: true, main: 'pb', pb: 6, zg: 2 });
  assert.equal(t.count, '(6)');
  assert.equal(t.note, 'Pasujące do tych kryteriów: 6 pozwoleń na budowę.');
  assert.equal(t.more, 'Razem ze zgłoszeniami (2)');
  assert.equal(promoText({ loaded: true, filtered: false, main: 'zg', pb: 0, zg: 1 }).more, null);
  assert.equal(`${promoText({ loaded: true, filtered: false, main: 'zg', pb: 0, zg: 1 }).lead}budowy`, 'Pokaż też zgłoszenia budowy');
});

test('an initiated proceeding asks for a decision in the accusative', () => {
  assert.equal(PROCEDURE_ACC.wz, 'decyzję o warunkach zabudowy (WZ)');
  assert.equal(PROCEDURE_ACC.cp, 'decyzję o lokalizacji inwestycji celu publicznego (CP)');
});
