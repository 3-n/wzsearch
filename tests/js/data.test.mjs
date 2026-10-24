import { test } from 'node:test';
import assert from 'node:assert/strict';
import { streetKey, streetSortKey, relationReason } from '../../site/js/data.js';

test('street prefixes are stripped only when they are prefixes (dot or space after them)', () => {
  for (const name of ['Algierska', 'Aldony', 'Genewska', 'Alzacka', 'Księcia Józefa Poniatowskiego', 'Świętosławska', 'Generała Abrahama', 'Placówka']) {
    assert.equal(streetSortKey(name), name, name);
  }
  assert.equal(streetKey('Algierska'), 'algierska');
  assert.equal(streetSortKey('Plac Przymierza'), 'Przymierza');
  assert.equal(streetSortKey('pl. Szembeka'), 'Szembeka');
  assert.equal(streetSortKey('gen. Augusta Emila Fieldorfa'), 'Augusta Emila Fieldorfa');
  assert.equal(streetSortKey('al. Stanów Zjednoczonych'), 'Stanów Zjednoczonych');
  assert.equal(streetSortKey('ul.Grochowska'), 'Grochowska');
  assert.equal(streetSortKey('Rondo Wiatraczna'), 'Wiatraczna');
  assert.equal(streetKey('św. Wincentego'), 'wincentego');
});

test('relationReason: "i 1 inna / 2 inne / 5 innych" działki', () => {
  const rec = (n) => ({ parcels: Array.from({ length: n }, (_, i) => ({ id: `p${i}`, number: String(i + 1), obreb: '3-05-11' })) });
  assert.equal(relationReason(rec(4), rec(4)), 'wspólne działki 1, 2, 3 i 1 inna (obr. 3-05-11)');
  assert.equal(relationReason(rec(5), rec(5)), 'wspólne działki 1, 2, 3 i 2 inne (obr. 3-05-11)');
  assert.equal(relationReason(rec(8), rec(8)), 'wspólne działki 1, 2, 3 i 5 innych (obr. 3-05-11)');
  assert.equal(relationReason(rec(3), rec(3)), 'wspólne działki 1, 2, 3 (obr. 3-05-11)');
});
