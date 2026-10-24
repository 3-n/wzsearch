import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { escapeCell, toCSV, decimalComma, recordsToCSV, CSV_COLUMNS, csvFileName, BOM, categoryText, sheetName } from '../../site/js/csv.js';
import { buildIndex } from '../../site/js/data.js';

/** Minimal RFC 4180 reader for the tests (';' delimiter, quoted cells may contain ; " and newlines). */
function parseCSV(text) {
  const rows = [];
  let row = [];
  let cell = '';
  let quoted = false;
  for (let i = 0; i < text.length; i += 1) {
    const c = text[i];
    if (quoted) {
      if (c === '"' && text[i + 1] === '"') { cell += '"'; i += 1; } else if (c === '"') quoted = false; else cell += c;
    } else if (c === '"') quoted = true;
    else if (c === ';') { row.push(cell); cell = ''; } else if (c === '\r' && text[i + 1] === '\n') {
      row.push(cell); rows.push(row); row = []; cell = ''; i += 1;
    } else cell += c;
  }
  if (cell || row.length) { row.push(cell); rows.push(row); }
  return rows;
}

test('escapeCell quotes delimiters, quotes and newlines', () => {
  assert.equal(escapeCell('plain'), 'plain');
  assert.equal(escapeCell('a;b'), '"a;b"');
  assert.equal(escapeCell('say "hi"'), '"say ""hi"""');
  assert.equal(escapeCell('line1\nline2'), '"line1\nline2"');
  assert.equal(escapeCell('a,b'), 'a,b', 'comma is not special with ; delimiter');
  assert.equal(escapeCell(null), '');
  assert.equal(escapeCell(undefined), '');
  assert.equal(escapeCell(5), '5');
});

test('escapeCell neutralises spreadsheet formulas', () => {
  assert.equal(escapeCell('=HYPERLINK("x")'), '"\'=HYPERLINK(""x"")"');
  assert.equal(escapeCell('+48 123'), "'+48 123");
  assert.equal(escapeCell('@cmd'), "'@cmd");
  assert.equal(escapeCell('-cz.'), "'-cz.");
  assert.equal(escapeCell('-5'), '-5', 'negative numbers stay numbers');
  assert.equal(escapeCell('-12,5'), '-12,5');
  assert.equal(escapeCell('-12.5'), '-12.5');
});

test('escapeCell: a leading "-" with a digit is still a formula unless the whole cell is a number', () => {
  assert.equal(escapeCell('-1+1'), "'-1+1");
  assert.equal(escapeCell("-2+3+cmd|' /C calc'!A0"), "'-2+3+cmd|' /C calc'!A0");
  assert.equal(escapeCell('-1+HYPERLINK("http://x","y")'), '"\'-1+HYPERLINK(""http://x"",""y"")"');
  assert.equal(escapeCell('\t1'), "'\t1");
});

test('toCSV adds BOM, uses ; and CRLF', () => {
  const s = toCSV(['a', 'b'], [[1, 'x;y'], [null, 'z']]);
  assert.ok(s.startsWith(BOM));
  assert.equal(s.slice(1), 'a;b\r\n1;"x;y"\r\n;z\r\n');
  assert.equal(toCSV(['a'], [], { bom: false }), 'a\r\n');
});

test('decimalComma', () => {
  assert.equal(decimalComma(52.223054), '52,223054');
  assert.equal(decimalComma(null), '');
  assert.equal(decimalComma(NaN), '');
});

test('recordsToCSV exports every record with source URLs', () => {
  const recordsDoc = JSON.parse(readFileSync(new URL('../fixtures/site-data/records.json', import.meta.url)));
  const sourcesDoc = JSON.parse(readFileSync(new URL('../fixtures/site-data/sources.json', import.meta.url)));
  const index = buildIndex(recordsDoc, sourcesDoc);
  const records = index.entries.map((e) => e.rec);
  const csv = recordsToCSV(records, {
    dicts: index.dicts, filesById: index.filesById, pagesById: index.pagesById,
    baseUrl: 'https://example.org/wz/index.html#/?q=x',
  });
  const lines = csv.slice(1).split('\r\n').filter(Boolean);
  assert.equal(lines[0], CSV_COLUMNS.join(';'));
  // multi-line cells are quoted, so count records by the permalink column instead of lines
  const permalinks = csv.match(/https:\/\/example\.org\/wz\/index\.html#\/wpis\//g) || [];
  assert.equal(permalinks.length, records.length);
  assert.ok(csv.includes('https://pragapld.um.warszawa.pl/documents/'), 'original file URL');
  assert.ok(csv.includes('https://example.org/wz/sources/'), 'absolute archive copy URL');
  assert.ok(csv.includes('https://pragapld.um.warszawa.pl/-/'), 'source page URL');
  // a record with two sources joins them with " | "
  const two = records.find((r) => r.sources.length > 1);
  assert.ok(two, 'fixture has a multi-source record');
  const row = csv.split('\r\n').find((l) => l.startsWith(`${two.id};`));
  assert.match(row, / \| /);
});

test('CSV columns v2: the v1 columns unchanged, then the v2 columns in contract order', () => {
  const v1 = ['id', 'rodzaj', 'rodzaj_opis', 'postepowanie', 'numer', 'data', 'data_w_zrodle', 'okres_sprawozdawczy',
    'wnioskodawca', 'typ_wnioskodawcy', 'inwestycja', 'adres', 'ulica', 'numer_budynku', 'dzialki',
    'dzialki_w_zrodle', 'typy_inwestycji', 'obszar', 'szerokosc_geogr', 'dlugosc_geogr', 'dokladnosc_lokalizacji',
    'uwagi', 'powiazane_wpisy', 'link', 'plik_zrodlowy', 'plik_url', 'kopia_archiwalna_url', 'strona_zrodlowa',
    'strona_zrodlowa_url', 'arkusz_wiersz'];
  assert.deepEqual(CSV_COLUMNS.slice(0, v1.length), v1);
  assert.deepEqual(CSV_COLUMNS.slice(v1.length), ['zrodlo_danych', 'organ', 'rozstrzygniecie', 'data_wniosku', 'nr_w_rejestrze',
    'znak_sprawy_urzedu', 'zakres_robot', 'kategoria_obiektu', 'kubatura_m3']);
});

test('v2 cells: dataset/issuer/outcome labels, permit fields, category text, decimal comma', () => {
  const recordsDoc = JSON.parse(readFileSync(new URL('../fixtures/site-data/records.json', import.meta.url)));
  const sourcesDoc = JSON.parse(readFileSync(new URL('../fixtures/site-data/sources.json', import.meta.url)));
  const permitsDoc = JSON.parse(readFileSync(new URL('../fixtures/site-data/permits.json', import.meta.url)));
  const index = buildIndex(recordsDoc, sourcesDoc);
  const col = (name) => CSV_COLUMNS.indexOf(name);
  const permit = { ...permitsDoc.records.find((r) => r.id === 'pb-st-mz-pa-2026-29594') };
  permit.permit = { ...permit.permit, cubature: 1234.5 };
  const refusal = recordsDoc.records.find((r) => r.id === 'wz-am-2026-95');
  const csv = recordsToCSV([permit, refusal], { dicts: index.dicts, filesById: index.filesById, pagesById: index.pagesById });
  const rows = parseCSV(csv.slice(1));
  assert.equal(rows.length, 3);
  assert.ok(rows.every((row) => row.length === CSV_COLUMNS.length));
  const [p, r] = [rows[1], rows[2]];
  assert.equal(p[col('zrodlo_danych')], recordsDoc.datasets.rwdz.label);
  assert.equal(p[col('organ')], recordsDoc.issuers.district.label);
  assert.equal(p[col('rozstrzygniecie')], '');
  assert.equal(p[col('data_wniosku')], '2026-09-24');
  assert.equal(p[col('nr_w_rejestrze')], 'ST-MZ-PA/WNIOSEK/29594/2026');
  assert.equal(p[col('znak_sprawy_urzedu')], 'RPW/142815/2026-1B/FSO');
  assert.equal(p[col('zakres_robot')], 'wykonanie robót budowlanych innych niż wymienione powyżej');
  assert.equal(p[col('kategoria_obiektu')], 'XIII – pozostałe budynki mieszkalne (wielorodzinne)');
  assert.equal(p[col('kubatura_m3')], '1234,5');
  assert.equal(p[col('plik_url')], 'https://wyszukiwarka.gunb.gov.pl/pliki_pobranie/wynik_mazowieckie.zip');
  assert.equal(r[col('rozstrzygniecie')], 'Odmowa');
  assert.equal(r[col('zrodlo_danych')], recordsDoc.datasets.baipp.label);
  assert.equal(r[col('nr_w_rejestrze')], '');
  assert.equal(categoryText({ category: 'IX' }, { IX: { label: 'kultura' } }), 'IX – kultura');
  assert.equal(categoryText({ category: 'IX' }), 'IX');
  assert.equal(categoryText(null), '');
});

test('arkusz_wiersz: a blank sheet name reads "(arkusz bez nazwy)" (as pipeline/export.py writes records.csv)', () => {
  assert.equal(sheetName({ sheet: ' ', row: 26 }), '(arkusz bez nazwy)');
  assert.equal(sheetName({ sheet: '', row: 26 }), '(arkusz bez nazwy)');
  assert.equal(sheetName({ sheet: ' Rok ', row: 3 }), 'Rok');
  assert.equal(sheetName({ sheet: null, row: 7 }), '', 'RWDZ rows have no sheet: "!<line>"');
  assert.equal(sheetName({ row: 7 }), '');
  const rec = { id: 'x', kind: 'wz', sources: [{ file_id: 'f', sheet: ' ', row: 26 }, { file_id: 'g', sheet: null, row: 5 }] };
  const rows = parseCSV(recordsToCSV([rec], { dicts: {}, filesById: new Map(), pagesById: new Map() }).slice(1));
  assert.equal(rows[1][CSV_COLUMNS.indexOf('arkusz_wiersz')], '(arkusz bez nazwy)!26 | !5');
});

test('csvFileName uses the Warsaw date (a download after midnight is not named after yesterday)', () => {
  assert.equal(csvFileName(new Date('2026-10-23T10:00:00Z')), 'wzsearch-praga-poludnie-2026-10-23.csv');
  assert.equal(csvFileName(new Date('2026-10-23T00:30:00+02:00')), 'wzsearch-praga-poludnie-2026-10-23.csv');
  assert.equal(csvFileName(new Date('2026-01-15T00:59:00+01:00')), 'wzsearch-praga-poludnie-2026-01-15.csv');
});
