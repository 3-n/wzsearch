/**
 * Pure formatting helpers for Polish UI copy: plurals, dates, months, numbers.
 * DOM-free; unit-tested in tests/js/format.test.mjs.
 */

export const MONTHS_NOMINATIVE = [
  'styczeń', 'luty', 'marzec', 'kwiecień', 'maj', 'czerwiec',
  'lipiec', 'sierpień', 'wrzesień', 'październik', 'listopad', 'grudzień',
];
export const MONTHS_GENITIVE = [
  'stycznia', 'lutego', 'marca', 'kwietnia', 'maja', 'czerwca',
  'lipca', 'sierpnia', 'września', 'października', 'listopada', 'grudnia',
];
export const MONTHS_SHORT = ['sty', 'lut', 'mar', 'kwi', 'maj', 'cze', 'lip', 'sie', 'wrz', 'paź', 'lis', 'gru'];

/**
 * Pick the Polish plural form for an integer.
 * @param {number} n
 * @param {[string, string, string]} forms [one, few, many] e.g. ['wpis', 'wpisy', 'wpisów']
 * @returns {string}
 */
export function pluralForm(n, [one, few, many]) {
  const abs = Math.abs(Math.trunc(n));
  if (abs === 1) return one;
  const mod10 = abs % 10;
  const mod100 = abs % 100;
  if (mod10 >= 2 && mod10 <= 4 && !(mod100 >= 12 && mod100 <= 14)) return few;
  return many;
}

const NUMBER_FMT = new Intl.NumberFormat('pl-PL');

/** Format an integer the Polish way (thin grouping from 10 000 upwards, as Intl does). */
export function formatNumber(n) {
  return NUMBER_FMT.format(n);
}

/** "5 wpisów", "1 wpis", "22 wpisy". */
export function plural(n, forms) {
  return `${formatNumber(n)} ${pluralForm(n, forms)}`;
}

export const WPIS = ['wpis', 'wpisy', 'wpisów'];
export const PLIK = ['plik', 'pliki', 'plików'];
export const STRONA = ['strona', 'strony', 'stron'];
export const DZIALKA = ['działka', 'działki', 'działek'];
export const POZYCJA = ['pozycja', 'pozycje', 'pozycji'];
export const MIESIAC = ['miesiąc', 'miesiące', 'miesięcy'];
export const WYNIK = ['wynik', 'wyniki', 'wyników'];

const ISO_DATE = /^(\d{4})-(\d{2})-(\d{2})/;
const ISO_MONTH = /^(\d{4})-(\d{2})$/;

/** "2026-07-09" → "9 lipca 2026"; null/invalid → "". */
export function formatDate(iso) {
  const m = ISO_DATE.exec(iso || '');
  if (!m) return '';
  const month = Number(m[2]);
  if (month < 1 || month > 12) return '';
  return `${Number(m[3])} ${MONTHS_GENITIVE[month - 1]} ${m[1]}`;
}

/** "2026-07-09" → "09.07.2026". */
export function formatDateNumeric(iso) {
  const m = ISO_DATE.exec(iso || '');
  return m ? `${m[3]}.${m[2]}.${m[1]}` : '';
}

/** "2026-07" → "lipiec 2026" (capitalize=true → "Lipiec 2026"). */
export function formatMonth(ym, { capitalize = false } = {}) {
  const m = ISO_MONTH.exec(ym || '');
  if (!m) return '';
  const name = MONTHS_NOMINATIVE[Number(m[2]) - 1];
  if (!name) return '';
  const s = `${name} ${m[1]}`;
  return capitalize ? s[0].toUpperCase() + s.slice(1) : s;
}

/** Spelled-out month span for prose: "sierpień–październik 2020", "grudzień 2020 – luty 2021", "maj 2021". */
export function formatMonthSpan(from, to) {
  if (!from || !to || from === to) return formatMonth(from || to);
  if (from.slice(0, 4) === to.slice(0, 4)) return `${formatMonth(from).split(' ')[0]}–${formatMonth(to)}`;
  return `${formatMonth(from)} – ${formatMonth(to)}`;
}

/** "2026-07" → "lip 2026". */
export function formatMonthShort(ym) {
  const m = ISO_MONTH.exec(ym || '');
  if (!m) return '';
  const name = MONTHS_SHORT[Number(m[2]) - 1];
  return name ? `${name} ${m[1]}` : '';
}

/** "2026-07" → "07.2026". */
export function formatMonthNumeric(ym) {
  const m = ISO_MONTH.exec(ym || '');
  return m ? `${m[2]}.${m[1]}` : '';
}

/**
 * Human label for a month range.
 * ("2024-01","2024-12") → "2024"; ("2024-03","2024-03") → "marzec 2024";
 * ("2024-03","2024-05") → "mar 2024 – maj 2024"; open ends → "od …" / "do …".
 */
export function formatMonthRange(from, to) {
  if (!from && !to) return '';
  if (from && to) {
    if (from === to) return formatMonth(from);
    if (from.slice(5) === '01' && to.slice(5) === '12' && from.slice(0, 4) === to.slice(0, 4)) return from.slice(0, 4);
    if (from.slice(5) === '01' && to.slice(5) === '12') return `${from.slice(0, 4)}–${to.slice(0, 4)}`;
    return `${formatMonthShort(from)} – ${formatMonthShort(to)}`;
  }
  if (from) return `od ${formatMonthShort(from)}`;
  return `do ${formatMonthShort(to)}`;
}

const DATETIME_FMT = new Intl.DateTimeFormat('pl-PL', {
  timeZone: 'Europe/Warsaw', day: 'numeric', month: 'numeric', year: 'numeric', hour: '2-digit', minute: '2-digit',
  hourCycle: 'h23',
});

/** ISO timestamp → "23 października 2026, 04:00" (Warsaw time); invalid → "". */
export function formatDateTime(iso, { time = true } = {}) {
  if (!iso) return '';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '';
  const parts = Object.fromEntries(DATETIME_FMT.formatToParts(d).map((p) => [p.type, p.value]));
  const date = `${Number(parts.day)} ${MONTHS_GENITIVE[Number(parts.month) - 1]} ${parts.year}`;
  return time ? `${date}, ${parts.hour}:${parts.minute}` : date;
}

/** 12345 → "12,1 kB". */
export function formatBytes(bytes) {
  if (bytes == null || Number.isNaN(bytes)) return '';
  if (bytes < 1024) return `${bytes} B`;
  const units = ['kB', 'MB', 'GB'];
  let v = bytes / 1024;
  let i = 0;
  while (v >= 1024 && i < units.length - 1) { v /= 1024; i += 1; }
  return `${v.toLocaleString('pl-PL', { maximumFractionDigits: v < 100 ? 1 : 0 })} ${units[i]}`;
}

/** Distance in metres → "250 m" / "1 km" / "1,5 km". */
export function formatDistance(m) {
  if (m == null) return '';
  if (m < 1000) return `${Math.round(m)} m`;
  return `${(m / 1000).toLocaleString('pl-PL', { maximumFractionDigits: 1 })} km`;
}

/** Add `delta` months to "YYYY-MM". */
export function addMonths(ym, delta) {
  const m = ISO_MONTH.exec(ym || '');
  if (!m) return null;
  const idx = Number(m[1]) * 12 + (Number(m[2]) - 1) + delta;
  const y = Math.floor(idx / 12);
  const mo = (idx % 12) + 1;
  return `${y}-${String(mo).padStart(2, '0')}`;
}

/** Inclusive list of months between two "YYYY-MM" values. */
export function monthRange(from, to) {
  const out = [];
  if (!ISO_MONTH.test(from || '') || !ISO_MONTH.test(to || '') || from > to) return out;
  let cur = from;
  while (cur <= to && out.length < 1200) {
    out.push(cur);
    cur = addMonths(cur, 1);
  }
  return out;
}

/** Truncate a string to n chars on a word boundary, adding an ellipsis. */
export function truncate(s, n) {
  if (!s || s.length <= n) return s || '';
  const cut = s.slice(0, n);
  const sp = cut.lastIndexOf(' ');
  return `${(sp > n * 0.6 ? cut.slice(0, sp) : cut).replace(/[\s,.;:–-]+$/, '')}…`;
}

/**
 * Render a raw spreadsheet cell for reading: the office uses runs of spaces as visual line breaks
 * ("33/1cz.            3-06-06"), so runs of ≥ 3 spaces become line breaks; wording is untouched.
 */
export function tidyCell(text) {
  return String(text ?? '').split(/\n|[ \t\u00a0]{3,}/).map((l) => l.replace(/[ \t\u00a0]+/g, ' ').trim()).filter(Boolean).join('\n');
}

export const DZIEN = ['dzień', 'dni', 'dni'];
export const WIERSZ = ['wiersz', 'wiersze', 'wierszy'];

/** Whole days from ISO date `a` to ISO date `b` (null when either is missing/invalid). */
export function daysBetween(a, b) {
  const ma = ISO_DATE.exec(a || '');
  const mb = ISO_DATE.exec(b || '');
  if (!ma || !mb) return null;
  const ta = Date.UTC(Number(ma[1]), Number(ma[2]) - 1, Number(ma[3]));
  const tb = Date.UTC(Number(mb[1]), Number(mb[2]) - 1, Number(mb[3]));
  return Math.round((tb - ta) / 86400000);
}

/**
 * "decyzja po 66 dniach" / "decyzja tego samego dnia" / "decyzja po 1 dniu" for an application → decision span;
 * null when unknown or negative (inconsistent source dates).
 */
export function decisionAfter(filed, decided) {
  const d = daysBetween(filed, decided);
  if (d == null || d < 0) return null;
  if (d === 0) return 'decyzja tego samego dnia';
  if (d === 1) return 'decyzja po 1 dniu';
  return `decyzja po ${formatNumber(d)} dniach`;
}

/**
 * Line numbers as compact ranges: [12, 13, 14, 20] → "12–14, 20" (sorted, de-duplicated). Digits are NOT grouped:
 * a line number is a reference to copy ("sed -n 338664p"), and "96 620–96 631, 96 633" would read as more numbers.
 */
export function formatLineList(nums) {
  const xs = [...new Set((nums || []).filter((n) => Number.isInteger(n) && n > 0))].sort((a, b) => a - b);
  const out = [];
  for (let i = 0; i < xs.length; i += 1) {
    let j = i;
    while (j + 1 < xs.length && xs[j + 1] === xs[j] + 1) j += 1;
    out.push(j > i ? `${xs[i]}–${xs[j]}` : String(xs[i]));
    i = j;
  }
  return out.join(', ');
}

/** 1234.5 → "1 234,5 m³" (null/0 → ""). */
export function formatCubature(v) {
  if (typeof v !== 'number' || !Number.isFinite(v) || v <= 0) return '';
  return `${v.toLocaleString('pl-PL', { maximumFractionDigits: 1 })} m³`;
}
