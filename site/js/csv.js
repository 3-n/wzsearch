/**
 * Pure CSV export tuned for Polish Excel:
 *  - UTF-8 with BOM (so Excel detects the encoding),
 *  - semicolon delimiter (Excel in the Polish locale expects ';' because ',' is the decimal separator),
 *  - decimal comma in coordinates, CRLF line endings,
 *  - RFC 4180 quoting (fields containing ; " CR or LF are wrapped in quotes, quotes doubled),
 *  - formula-injection guard: cells starting with = + - @ TAB CR get a leading apostrophe – unless the whole cell is
 *    a plain number ("-5", "-12,5"): "-1+1" or "-2+3+cmd|…" would otherwise run as a formula in Excel.
 * DOM-free; unit-tested in tests/js/csv.test.mjs.
 */

export const BOM = '﻿';
export const DELIMITER = ';';
export const EOL = '\r\n';

const FORMULA_START = /^[=+\-@\t\r]/;
const PLAIN_NUMBER = /^-?\d+(?:[.,]\d+)?$/;

/**
 * Sheet name for `arkusz_wiersz`, the same rule as pipeline/export.py: as printed (trimmed), "(arkusz bez nazwy)" for a
 * blank one (some BAiPP workbooks name a sheet " "), "" without a sheet (RWDZ rows: "!<line>").
 */
export function sheetName(source) {
  const sheet = source?.sheet;
  return String(sheet ?? '').trim() || (sheet != null ? '(arkusz bez nazwy)' : '');
}

/** Escape one cell value. */
export function escapeCell(value, delimiter = DELIMITER) {
  if (value == null) return '';
  let s = typeof value === 'string' ? value : String(value);
  if (FORMULA_START.test(s) && !PLAIN_NUMBER.test(s)) s = `'${s}`;
  if (s.includes(delimiter) || s.includes('"') || s.includes('\n') || s.includes('\r')) {
    s = `"${s.replace(/"/g, '""')}"`;
  }
  return s;
}

/**
 * Serialise rows to CSV text.
 * @param {string[]} header
 * @param {Array<Array<unknown>>} rows
 * @param {{bom?: boolean, delimiter?: string}} [opts]
 */
export function toCSV(header, rows, { bom = true, delimiter = DELIMITER } = {}) {
  const lines = [header, ...rows].map((r) => r.map((c) => escapeCell(c, delimiter)).join(delimiter));
  return (bom ? BOM : '') + lines.join(EOL) + EOL;
}

/** 52.223054 → "52,223054" (Polish decimal comma). */
export function decimalComma(n) {
  return typeof n === 'number' && Number.isFinite(n) ? String(n).replace('.', ',') : '';
}

const PRECISION = { parcel: 'działka', address: 'adres', street: 'ulica (przybliżona)' };
const APPLICANT = { person: 'osoba fizyczna', organization: 'firma lub instytucja', unknown: 'nieustalony' };

/**
 * Column contract shared with pipeline/export.py (a pytest parses this list): the v1 columns unchanged and in
 * the same order, then the v2 columns appended (docs/DATA_MODEL.md, "CSV columns v2").
 */
export const CSV_COLUMNS = [
  'id', 'rodzaj', 'rodzaj_opis', 'postepowanie', 'numer', 'data', 'data_w_zrodle', 'okres_sprawozdawczy',
  'wnioskodawca', 'typ_wnioskodawcy', 'inwestycja', 'adres', 'ulica', 'numer_budynku', 'dzialki',
  'dzialki_w_zrodle', 'typy_inwestycji', 'obszar', 'szerokosc_geogr', 'dlugosc_geogr', 'dokladnosc_lokalizacji',
  'uwagi', 'powiazane_wpisy', 'link', 'plik_zrodlowy', 'plik_url', 'kopia_archiwalna_url', 'strona_zrodlowa',
  'strona_zrodlowa_url', 'arkusz_wiersz',
  'zrodlo_danych', 'organ', 'rozstrzygniecie', 'data_wniosku', 'nr_w_rejestrze', 'znak_sprawy_urzedu',
  'zakres_robot', 'kategoria_obiektu', 'kubatura_m3',
];

/** "XIII – budynki mieszkalne wielorodzinne" (label from the record, else from the dictionary); "XIII" alone. */
export function categoryText(permit, categories = {}) {
  const cat = permit?.category;
  if (!cat) return '';
  const label = permit.category_label || categories?.[cat]?.label || '';
  return label ? `${cat} – ${label}` : String(cat);
}

function absolute(path, base) {
  if (!path) return '';
  try {
    return new URL(path, base).href;
  } catch {
    return path;
  }
}

/**
 * Build CSV text for a list of records.
 * @param {object[]} records Records (DATA_MODEL.md)
 * @param {{dicts: object, filesById: Map, pagesById: Map, baseUrl: string}} ctx
 *   baseUrl = absolute URL of the site's index page (for permalinks and archive copies)
 */
export function recordsToCSV(records, { dicts = {}, filesById = new Map(), pagesById = new Map(), baseUrl = '' } = {}) {
  const join = (arr, sep = ' | ') => arr.filter((x) => x != null && x !== '').join(sep);
  const rows = records.map((r) => {
    const sources = Array.isArray(r.sources) ? r.sources : [];
    const files = sources.map((s) => filesById.get(s.file_id));
    const pages = sources.map((s) => pagesById.get(s.page_id));
    const geo = r.geo || {};
    const parcels = Array.isArray(r.parcels) ? r.parcels : [];
    const permit = r.permit && typeof r.permit === 'object' ? r.permit : {};
    return [
      r.id,
      dicts.kinds?.[r.kind]?.short || r.kind,
      dicts.kinds?.[r.kind]?.label || '',
      r.procedure ? (dicts.kinds?.[r.procedure]?.short || r.procedure) : '',
      r.number,
      r.date,
      r.date_raw,
      r.period,
      r.applicant,
      APPLICANT[r.applicant_type] || APPLICANT.unknown,
      r.investment,
      r.address?.display,
      r.address?.street,
      r.address?.number,
      join(parcels.map((p) => `${p.number}${p.partial ? ' (część)' : ''} obr. ${p.obreb}`), ', '),
      r.parcels_raw,
      join((r.tags || []).map((t) => dicts.tags?.[t]?.label || t), ', '),
      r.area ? (dicts.areas?.[r.area]?.label || r.area) : '',
      decimalComma(geo.lat),
      decimalComma(geo.lon),
      geo.method ? (PRECISION[geo.method] || geo.method) : '',
      join(r.warnings || []),
      join(r.related || [], ', '),
      baseUrl ? `${baseUrl.replace(/#.*$/, '')}#/wpis/${encodeURIComponent(r.id)}` : '',
      join(files.map((f, i) => f?.filename || sources[i].file_id)),
      join(files.map((f) => f?.url)),
      join(files.map((f) => (f?.archive_path ? absolute(f.archive_path, baseUrl) : ''))),
      join(pages.map((p) => p?.title)),
      join(pages.map((p) => p?.url)),
      join(sources.map((s) => `${sheetName(s)}!${s.row ?? ''}`)),
      r.dataset ? (dicts.datasets?.[r.dataset]?.label || r.dataset) : '',
      r.issuer ? (dicts.issuers?.[r.issuer]?.label || r.issuer) : '',
      r.outcome ? (dicts.outcomes?.[r.outcome]?.label || r.outcome) : '',
      r.filed_date,
      permit.register_id,
      permit.case_sign,
      permit.scope_label,
      categoryText(permit, dicts.categories),
      decimalComma(permit.cubature),
    ];
  });
  return toCSV(CSV_COLUMNS, rows);
}

/** "YYYY-MM-DD" in Warsaw time (like every date in the UI): a download at 00:30 is not named after yesterday. */
const WARSAW_DAY = new Intl.DateTimeFormat('sv-SE', { timeZone: 'Europe/Warsaw', year: 'numeric', month: '2-digit', day: '2-digit' });

/** File name like "wzsearch-praga-poludnie-2026-10-23.csv". */
export function csvFileName(date = new Date()) {
  return `wzsearch-praga-poludnie-${WARSAW_DAY.format(date)}.csv`;
}
