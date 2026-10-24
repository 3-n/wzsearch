/**
 * Sources view (#/zrodla, #/zrodla/<dataset>): one tab per dataset (docs/DATA_MODEL.md v2):
 *   district – every monthly page (newest first) with its blocks and files, declared vs parsed counts
 *              (mismatches highlighted and explained); years older than the latest two are collapsed and
 *              rendered only when opened (the page stays fast with 70+ months);
 *   baipp    – the yearly pages of the city's architecture office and every snapshot file, city-wide rows
 *              vs the Praga-Południe rows we keep;
 *   rwdz     – the three GUNB register snapshots (ZIP), licence, Last-Modified, our extract, counts.
 * Every file links to the original, the archived copy and the records read from it (→ explore filtered by file).
 */
import { h, replaceChildren, safeUrl, prefersReducedMotion } from '../dom.js';
import { icon, kindGlyph } from '../icons.js';
import {
  formatDateTime, formatNumber, formatBytes, formatMonth, formatMonthSpan, plural, WPIS, STRONA, POZYCJA, PLIK, WIERSZ,
} from '../format.js';
import { buildHash } from '../url.js';
import { defaultFilters } from '../filters.js';
import { datasetOf } from '../data.js';
import { isOptInKind } from '../kinds.js';
import { SOURCE_INDEX_URL } from '../config.js';
import { UNOFFICIAL, LICENCE_URLS } from '../copy.js';

function ext(href, label, iconName = 'external', cls = 'btn btn--ghost btn--xs') {
  const url = safeUrl(href);
  if (!url) return null;
  const external = /^https?:/i.test(url);
  return h('a', { class: cls, href: url, target: external ? '_blank' : null, rel: external ? 'noopener noreferrer' : null },
    icon(iconName, { size: 14 }), h('span', null, label), external ? h('span', { class: 'sr-only' }, ' (nowa karta)') : null);
}

const SPRAWA = ['sprawa', 'sprawy', 'spraw'];
/** Tab order; datasets present in sources.json but unknown here follow alphabetically. */
const DATASET_ORDER = ['district', 'baipp', 'rwdz'];

const escapeRegExp = (x) => String(x).replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

/**
 * Reconcile the counts the office declares on its pages with the rows read from the files.
 * Uses the block-level `parsed_count` from sources.json (each file counted once, on the page that first
 * published it) and the file-level `parsed_count` for the overall total.
 * @returns {{declared: number, parsedDeclared: number, undeclaredRows: number, undeclaredPeriods: string[],
 *            rows: number, mismatches: number}}
 */
export function reconcile(pages, files) {
  let declared = 0;
  let parsedDeclared = 0;
  let undeclaredRows = 0;
  let mismatches = 0;
  const undeclaredPeriods = new Set();
  for (const p of pages) {
    for (const b of (Array.isArray(p.blocks) ? p.blocks : [])) {
      if (b.count_mismatch) mismatches += 1;
      const parsed = Number.isFinite(b.parsed_count) ? b.parsed_count : 0;
      if (Number.isFinite(b.declared_count)) {
        declared += b.declared_count;
        parsedDeclared += parsed;
      } else if (parsed > 0) {
        undeclaredRows += parsed;
        if (p.period) undeclaredPeriods.add(p.period);
      }
    }
  }
  const rows = files.reduce((a, f) => a + (Number.isFinite(f.parsed_count) ? f.parsed_count : 0), 0);
  return { declared, parsedDeclared, undeclaredRows, undeclaredPeriods: [...undeclaredPeriods].sort(), rows, mismatches };
}

/**
 * Split sources.json into datasets (page.source; a file inherits the dataset of its first linking page).
 * @returns {Map<string, {pages: object[], files: object[]}>} in tab order
 */
export function splitByDataset(pages, files, pagesById = new Map(pages.map((p) => [p.page_id, p]))) {
  const out = new Map();
  const bucket = (ds) => {
    if (!out.has(ds)) out.set(ds, { pages: [], files: [] });
    return out.get(ds);
  };
  for (const p of pages) bucket(datasetOf(p, pagesById)).pages.push(p);
  for (const f of files) bucket(datasetOf(f, pagesById)).files.push(f);
  const rank = (k) => (DATASET_ORDER.includes(k) ? DATASET_ORDER.indexOf(k) : DATASET_ORDER.length);
  return new Map([...out].sort((a, b) => rank(a[0]) - rank(b[0]) || a[0].localeCompare(b[0])));
}

/**
 * BAiPP: totals over every snapshot file. City-wide rows and the Praga-Południe rows kept;
 * the same case in several monthly snapshots is one record.
 */
export function cityWideTotals(files) {
  let rowsTotal = 0;
  let kept = 0;
  let unknown = 0;
  for (const f of files) {
    if (Number.isFinite(f.rows_total)) rowsTotal += f.rows_total; else unknown += 1;
    if (Number.isFinite(f.parsed_count)) kept += f.parsed_count;
  }
  return { rowsTotal, kept, unknown };
}

const MISMATCH_HELP = 'Liczba pozycji podana na stronie urzędu różni się od liczby wierszy odczytanych z pliku. '
  + 'Najczęstsze przyczyny: puste lub scalone wiersze w arkuszu, ten sam plik podlinkowany w kilku miesiącach, '
  + 'pomyłka w opisie na stronie albo błąd odczytu po naszej stronie. Sprawdź plik źródłowy.';

/**
 * @param {HTMLElement} host
 * @param {object} index
 * @returns {{show: (tab: string|null) => void, dataChanged: () => void}}
 */
export function createSources(host, index) {
  const { dicts } = index;
  const groups = splitByDataset(index.pages, index.files, index.pagesById);
  const datasetKeys = [...groups.keys()];
  let active = null;
  const panels = new Map(); // dataset → rendered panel element (rendered on first visit)

  const dsLabel = (ds) => dicts.datasets?.[ds]?.short || { district: 'Urząd Dzielnicy', baipp: 'BAiPP', rwdz: 'GUNB RWDZ' }[ds] || ds;
  const dsTitle = (ds) => dicts.datasets?.[ds]?.label || dsLabel(ds);

  function recordCounts() {
    const m = new Map();
    for (const e of index.entries) for (const fid of e.fileIds) m.set(fid, (m.get(fid) || 0) + 1);
    return m;
  }
  let recordCountByFile = recordCounts();

  /** Explore link for the records of one file; register files need their (opt-in) kind switched on. */
  function fileHref(f) {
    const kinds = new Set();
    for (const id of f?.record_ids || []) {
      const e = index.byId.get(id);
      if (e) kinds.add(e.kind);
    }
    if (!kinds.size) for (const k of [f?.kind_detected, f?.category]) if (typeof k === 'string' && isOptInKind(k)) kinds.add(k);
    const filters = { ...defaultFilters(), file: f.file_id };
    if ([...kinds].some(isOptInKind)) filters.kinds = [...kinds];
    return buildHash({ route: 'explore', filters });
  }

  function fileActions(f, { register = false } = {}) {
    const n = recordCountByFile.get(f.file_id) || 0;
    const known = (f.record_ids || []).length;
    return h('div', { class: 'src-file__actions' },
      n ? h('a', { class: 'btn btn--secondary btn--xs', href: fileHref(f) }, h('span', null, `Pokaż ${plural(n, WPIS)}`), icon('arrowRight', { size: 14 }))
        // Register files before permits.json is loaded: the cases listed in sources.json (one record each).
        : known && register ? h('a', { class: 'btn btn--secondary btn--xs', href: fileHref(f) }, h('span', null, `Pokaż ${plural(known, WPIS)}`), icon('arrowRight', { size: 14 }))
          : h('span', { class: 'muted small' }, 'brak wpisów'),
      register ? null : ext(f?.url, 'Oryginał', 'download'),
      f?.archive_path ? ext(f.archive_path, register ? 'Wyciąg CSV' : 'Kopia', register ? 'download' : 'archive') : null,
      (f?.history || []).filter((v) => v?.archive_path).map((v, i) => ext(v.archive_path,
        `Wersja ${i + 1}${v.downloaded_at ? ` (${formatDateTime(v.downloaded_at, { time: false })})` : ''}`, 'history')));
  }

  function fileRow(fid, { cityWide = false } = {}) {
    const f = index.filesById.get(fid) || { file_id: fid };
    return h('li', { class: 'src-file' },
      h('span', { class: 'src-file__icon' }, icon('sheet', { size: 18 })),
      h('div', { class: 'src-file__main' },
        h('p', { class: 'src-file__name' }, f?.filename || fid),
        h('p', { class: 'src-file__meta' },
          f?.size ? formatBytes(f.size) : null,
          f?.size && Number.isFinite(f?.parsed_count) ? ' · ' : null,
          cityWide && Number.isFinite(f?.rows_total)
            ? h('span', { class: 'src-file__ratio' }, `plik ogólnomiejski: ${plural(f.rows_total, WIERSZ)}, dla Pragi-Południe: ${formatNumber(f.parsed_count ?? 0)}`)
            : (Number.isFinite(f?.parsed_count) ? `odczytano ${plural(f.parsed_count, POZYCJA)}` : null),
          (f?.page_ids || []).length > 1 ? h('span', { class: 'src-file__multi' }, ` · podlinkowany na ${plural(f.page_ids.length, STRONA)}`) : null),
        f?.last_modified ? h('p', { class: 'src-file__meta' }, `plik z dnia ${formatDateTime(f.last_modified, { time: false })}`,
          (f.history || []).length ? ` · podmieniany ${f.history.length}× (poprzednie wersje w archiwum)` : '') : null,
        f?.error ? h('p', { class: 'src-file__meta src-file__error' }, icon('alert', { size: 13 }), ` Ostatnia próba pobrania nie powiodła się: ${f.error}`) : null,
        (f?.warnings || []).length ? h('ul', { class: 'src-file__warn' }, f.warnings.map((w) => h('li', null, icon('info', { size: 13 }), String(w)))) : null),
      fileActions(f));
  }

  function blockRow(b, { cityWide = false } = {}) {
    const fileIds = Array.isArray(b.file_ids) ? b.file_ids : [];
    const hasCounts = Number.isFinite(b.declared_count) || Number.isFinite(b.parsed_count);
    const ok = !b.count_mismatch;
    const undeclared = !Number.isFinite(b.declared_count);
    const cat = b.category && /^[a-z]+$/.test(b.category) ? b.category : null;
    return h('li', { class: ['src-block', b.count_mismatch && 'is-mismatch', !fileIds.length && 'is-empty'] },
      h('div', { class: 'src-block__head' },
        cat ? kindGlyph(cat) : h('span', { class: 'glyph glyph--other', 'aria-hidden': 'true' }),
        h('p', { class: 'src-block__text' }, b.text || '(blok bez opisu)'),
        hasCounts && !cityWide ? h('p', {
          class: ['src-count', undeclared ? 'src-count--na' : ok ? 'src-count--ok' : 'src-count--bad'],
          title: undeclared ? 'Urząd nie podał na stronie liczby pozycji – nie ma z czym porównać' : null,
        },
        icon(undeclared ? 'info' : ok ? 'check' : 'alert', { size: 14 }),
        h('span', null, undeclared ? 'liczby nie podano' : `deklarowano ${formatNumber(b.declared_count)}`),
          h('span', { class: 'src-count__sep', 'aria-hidden': 'true' }, '·'),
          h('span', null, `odczytano ${Number.isFinite(b.parsed_count) ? formatNumber(b.parsed_count) : '?'}`)) : null,
        cityWide && Number.isFinite(b.parsed_count) ? h('p', { class: 'src-count src-count--na' }, icon('pin', { size: 14 }),
          h('span', null, `Praga-Południe: ${formatNumber(b.parsed_count)}`)) : null),
      b.count_mismatch ? h('p', { class: 'src-block__help' }, icon('info', { size: 14 }), MISMATCH_HELP) : null,
      fileIds.length ? h('ul', { class: 'src-files' }, fileIds.map((fid) => fileRow(fid, { cityWide }))) : null);
  }

  function pageCard(p, { cityWide = false, files = [] } = {}) {
    const pBlocks = Array.isArray(p.blocks) ? p.blocks : [];
    const pMismatch = pBlocks.some((b) => b.count_mismatch);
    // Snapshot files of this page no block links any more (BAiPP republishes the current-year file monthly).
    const linked = new Set(pBlocks.flatMap((b) => b.file_ids || []));
    const older = files.filter((f) => (f.page_ids || []).includes(p.page_id) && !linked.has(f.file_id));
    return h('li', { class: ['src-page', pMismatch && 'has-mismatch'] },
      h('header', { class: 'src-page__head' },
        h('div', null,
          h('h3', { class: 'src-page__title' }, p.title || formatMonth(p.period, { capitalize: true }) || p.page_id),
          h('p', { class: 'src-page__meta' }, p.published_at ? `Opublikowano ${formatDateTime(p.published_at, { time: false })}` : (cityWide ? 'Strona aktualizowana na bieżąco' : 'Data publikacji nieznana'),
            p.period && p.title && formatMonth(p.period) && !p.title.toLowerCase().startsWith(formatMonth(p.period).split(' ')[0])
              ? ` · okres ${formatMonth(p.period)}` : '')),
        ext(p.url, 'Strona źródłowa', 'external', 'btn btn--secondary btn--xs')),
      Array.isArray(p.warnings) && p.warnings.length ? h('ul', { class: 'src-page__warn', 'aria-label': 'Uwagi do strony' },
        p.warnings.map((w) => h('li', null, icon('info', { size: 14 }), h('span', null, String(w))))) : null,
      pBlocks.length ? h('ul', { class: 'src-blocks' }, pBlocks.map((b) => blockRow(b, { cityWide }))) : h('p', { class: 'muted' }, 'Strona nie zawiera bloków z danymi.'),
      older.length ? h('details', { class: 'src-older' },
        h('summary', null, icon('history', { size: 14 }), `Wcześniejsze wersje plików z tej strony (${formatNumber(older.length)})`),
        h('p', { class: 'muted small' }, 'Biuro co miesiąc zastępuje plik bieżącego roku nowym (pod nowym adresem). Każdą pobraną wersję zachowujemy jako źródło.'),
        h('ul', { class: 'src-files' }, older.map((f) => fileRow(f.file_id, { cityWide })))) : null);
  }

  function statList(items) {
    return h('dl', { class: 'stats' }, items.filter(Boolean).map(([label, value, warn]) => h('div', { class: ['stat', warn && 'stat--warn'] },
      h('dt', null, label), h('dd', null, value))));
  }

  // --- district -----------------------------------------------------------------------------------
  function districtPanel(ds, { pages: dsPages, files }) {
    const pages = [...dsPages].sort((a, b) => (b.period || '').localeCompare(a.period || '') || (b.published_at || '').localeCompare(a.published_at || ''));
    const rec = reconcile(pages, files);
    const { mismatches } = rec;
    const entries = index.entries.filter((e) => e.dataset === ds || (!e.dataset && ds === 'district')).length;
    let onlyMismatch = false;
    const years = [...new Set(pages.map((p) => (p.period || '').slice(0, 4)).filter(Boolean))];
    const openYears = new Set(years.slice(0, 2)); // the latest two years start expanded
    const listHost = h('div', { class: 'src-years' });
    const toggle = h('button', {
      type: 'button', class: 'seg__btn', 'aria-pressed': 'false',
      onClick: () => { onlyMismatch = !onlyMismatch; toggle.setAttribute('aria-pressed', String(onlyMismatch)); allBtn.setAttribute('aria-pressed', String(!onlyMismatch)); renderList(); },
    }, icon('alert', { size: 14 }), `Tylko niezgodności (${formatNumber(mismatches)})`);
    const allBtn = h('button', {
      type: 'button', class: 'seg__btn', 'aria-pressed': 'true',
      onClick: () => { onlyMismatch = false; toggle.setAttribute('aria-pressed', 'false'); allBtn.setAttribute('aria-pressed', 'true'); renderList(); },
    }, 'Wszystkie miesiące');
    const pagesOf = (y) => pages.filter((p) => (p.period || '').startsWith(y) && (!onlyMismatch || (p.blocks || []).some((b) => b.count_mismatch)));

    function yearSection(y) {
      const yp = pagesOf(y);
      if (!yp.length) return null;
      const n = yp.reduce((a, p) => a + (p.blocks || []).reduce((x, b) => x + (Number.isFinite(b.parsed_count) ? b.parsed_count : 0), 0), 0);
      const bad = yp.filter((p) => (p.blocks || []).some((b) => b.count_mismatch)).length;
      const list = h('ol', { class: 'src-pages' });
      const details = h('details', { class: 'src-year', id: `src-year-${y}`, open: openYears.has(y) || onlyMismatch || null },
        h('summary', { class: 'src-year__title' },
          // A heading inside the summary: the page outline reads h1 → h2 (year) → h3 (month).
          h('h2', { class: 'src-year__name' }, y),
          h('span', { class: 'count' }, `${plural(yp.length, ['miesiąc', 'miesiące', 'miesięcy'])} · ${plural(n, WIERSZ)}`),
          bad ? h('span', { class: 'src-year__bad' }, icon('alert', { size: 13 }), plural(bad, ['niezgodność', 'niezgodności', 'niezgodności'])) : null,
          icon('chevronDown', { size: 18, class: 'src-year__chev' })),
        list);
      // Collapsed years are rendered when first opened (fast first paint with 70+ monthly pages).
      const fill = () => { if (!list.childElementCount) list.append(...yp.map((p) => pageCard(p))); };
      if (details.open) fill();
      details.addEventListener('toggle', () => {
        if (details.open) { openYears.add(y); fill(); } else openYears.delete(y);
      });
      return details;
    }

    function renderList() {
      const nodes = years.map(yearSection).filter(Boolean);
      const undated = pages.filter((p) => !p.period && (!onlyMismatch || (p.blocks || []).some((b) => b.count_mismatch)));
      if (undated.length) nodes.push(h('section', { class: 'src-year' }, h('h2', { class: 'src-year__title' }, 'Bez ustalonego okresu'), h('ol', { class: 'src-pages' }, undated.map((p) => pageCard(p)))));
      replaceChildren(listHost, nodes.length ? nodes : h('p', { class: 'muted' }, 'Brak stron do pokazania.'));
    }
    renderList();
    const indexUrl = dicts.datasets?.[ds]?.url || index.meta.sourceIndexUrl || SOURCE_INDEX_URL;

    return [
      h('p', { class: 'src-intro' }, dicts.datasets?.[ds]?.description || 'Comiesięczne zestawienia Urzędu Dzielnicy Praga-Południe (pliki Excel).', ' ',
        ext(indexUrl, 'Wykaz na stronie urzędu', 'external', 'link')),
      statList([
        ['Strony miesięczne', formatNumber(pages.length)],
        ['Pliki Excel', formatNumber(files.length)],
        ['Wpisy w wyszukiwarce', formatNumber(entries)],
        ['Niezgodne liczby pozycji', formatNumber(mismatches), mismatches > 0],
      ]),
      h('div', { class: 'callout' }, icon('info', { size: 18 }),
        h('div', null,
          h('p', null, h('strong', null, 'Jak to czytać? '),
            'Przy każdym bloku strony pokazujemy liczbę pozycji podaną przez urząd („deklarowano”) i liczbę wierszy odczytanych z pliku („odczytano”). ',
            `Urząd zadeklarował łącznie ${plural(rec.declared, POZYCJA)} – w tych blokach odczytaliśmy ${plural(rec.parsedDeclared, WIERSZ)}`,
            mismatches ? ` (${mismatches === 1 ? 'różnica w 1 bloku, oznaczona niżej' : `różnice w ${formatNumber(mismatches)} blokach, oznaczone niżej`})` : '',
            '. ',
            rec.undeclaredRows ? `Strony za ${formatMonthSpan(rec.undeclaredPeriods[0], rec.undeclaredPeriods[rec.undeclaredPeriods.length - 1])} nie podają liczby pozycji; z ich plików odczytaliśmy ${plural(rec.undeclaredRows, WIERSZ)}. ` : '',
            `Razem ${plural(rec.rows, WIERSZ)} → ${plural(entries, WPIS)} w wyszukiwarce`,
            rec.rows !== entries ? ' (ta sama decyzja opublikowana w kilku plikach to jeden wpis).' : '.'))),
      h('div', { class: 'src-toolbar' },
        h('div', { class: 'seg', role: 'group', 'aria-label': 'Pokaż' }, allBtn, toggle),
        years.length > 1 ? h('nav', { class: 'year-jump', 'aria-label': 'Przejdź do roku' }, years.map((y) => h('button', {
          type: 'button', class: 'year-btn',
          onClick: () => {
            const d = document.getElementById(`src-year-${y}`);
            if (!d) return;
            d.open = true;
            d.scrollIntoView({ behavior: prefersReducedMotion() ? 'auto' : 'smooth', block: 'start' });
            // The keyboard focus follows the jump (the next Tab continues inside that year).
            d.querySelector('summary')?.focus({ preventScroll: true });
          },
        }, y))) : null),
      listHost,
    ];
  }

  // --- BAiPP --------------------------------------------------------------------------------------
  function cityPanel(ds, { pages: dsPages, files }) {
    const pages = [...dsPages].sort((a, b) => String(b.period || '').localeCompare(String(a.period || '')));
    const totals = cityWideTotals(files);
    const entries = index.entries.filter((e) => e.dataset === ds).length;
    const d = dicts.datasets?.[ds] || {};
    return [
      h('p', { class: 'src-intro' }, d.description || 'Ogólnomiejskie zestawienia Biura Architektury i Planowania Przestrzennego; pokazujemy tylko wiersze dotyczące Pragi-Południe.', ' ',
        ext(d.url, 'Strona Biura', 'external', 'link')),
      statList([
        ['Strony roczne', formatNumber(pages.length)],
        ['Pliki (z wersjami)', formatNumber(files.length)],
        ['Wiersze w plikach (cała Warszawa)', formatNumber(totals.rowsTotal)],
        ['Wpisy z Pragi-Południe', formatNumber(entries)],
      ]),
      h('div', { class: 'callout' }, icon('info', { size: 18 }),
        h('div', null,
          h('p', null, h('strong', null, 'Jak to czytać? '),
            `Biuro publikuje jedno zestawienie dla całej Warszawy. W ${formatNumber(files.length)} ${files.length === 1 ? 'pliku' : 'plikach'} jest łącznie ${plural(totals.rowsTotal, WIERSZ)}; `,
            `dla Pragi-Południe (według adresu w zestawieniu) odczytaliśmy ${plural(totals.kept, WIERSZ)} → ${plural(entries, WPIS)} w wyszukiwarce`,
            totals.kept !== entries ? ' (ta sama sprawa w kolejnych wersjach pliku bieżącego roku to jeden wpis).' : '.',
            ' Strony nie podają liczby pozycji, więc nie ma czego porównać – przy każdym pliku pokazujemy obie liczby.'),
          h('p', { class: 'muted small' }, 'Plik bieżącego roku zawiera dane od stycznia i jest co miesiąc zastępowany nowym; starsze wersje znajdziesz pod każdą stroną.'))),
      // Outline h1 → h2 → h3 (page cards), like the district tab's years.
      h('h2', { class: 'src-section__title' }, 'Strony roczne i pliki'),
      h('ol', { class: 'src-pages' }, pages.map((p) => pageCard(p, { cityWide: true, files }))),
    ];
  }

  // --- GUNB RWDZ ----------------------------------------------------------------------------------
  function registerPanel(ds, { pages, files }) {
    const d = dicts.datasets?.[ds] || {};
    const checked = index.meta.generatedAt ? formatDateTime(index.meta.generatedAt) : null;
    const licence = d.licence || files.find((f) => f.licence)?.licence || null;
    const licenceUrl = d.licence_url || (licence ? LICENCE_URLS[licence] : null);
    const rowsTotal = files.reduce((a, f) => a + (Number.isFinite(f.rows_total) ? f.rows_total : 0), 0);
    const kept = files.reduce((a, f) => a + (Number.isFinite(f.parsed_count) ? f.parsed_count : 0), 0);
    const cases = files.reduce((a, f) => a + (f.record_ids || []).length, 0);
    const page = pages[0] || {};
    const blockOf = (fid) => (page.blocks || []).find((b) => (b.file_ids || []).includes(fid));
    const datasetUrl = files.find((f) => f.dataset_url)?.dataset_url;
    return [
      h('p', { class: 'src-intro' }, d.description || 'Rejestr wniosków, decyzji i zgłoszeń w sprawach budowlanych prowadzony przez GUNB.', ' ',
        d.publisher ? `Wydawca: ${d.publisher}. ` : '',
        licence ? ['Licencja ', licenceUrl ? ext(licenceUrl, licence, 'book', 'link') : licence, ' – dane można dowolnie wykorzystywać. '] : null),
      statList([
        ['Pliki rejestru', formatNumber(files.length)],
        ['Wiersze w plikach GUNB', formatNumber(rowsTotal)],
        ['Wiersze z Pragi-Południe', formatNumber(kept)],
        ['Sprawy w wyszukiwarce', formatNumber(cases)],
      ]),
      h('div', { class: 'callout' }, icon('info', { size: 18 }),
        h('div', null,
          h('p', null, h('strong', null, 'Jak to czytać? '),
            `GUNB publikuje cały rejestr (województwo lub kraj) – razem ${plural(rowsTotal, WIERSZ)}. `,
            `Wybieramy wiersze z działkami w jednostce ewidencyjnej Praga-Południe (${plural(kept, WIERSZ)}); jeden wiersz to jedna działka, więc sprawa z kilkoma działkami ma kilka wierszy → ${plural(cases, SPRAWA)}.`),
          h('ul', { class: 'src-caveats' },
            h('li', null, 'Rejestr obejmuje sprawy od 2016 r. i tylko decyzje pierwszej instancji – bez spraw w toku.'),
            h('li', null, 'Nie ma w nim informacji, czy decyzja była pozytywna (brak kolumny z rozstrzygnięciem).'),
            h('li', null, 'Zgłoszenia są w rejestrze tylko dla części rodzajów robót (m.in. domy jednorodzinne, sieci, małe budynki).'),
            h('li', null, 'Nazwiska projektantów pomijamy (zostają tylko w wyciągu, tak jak opublikował je GUNB); inwestorów będących osobami fizycznymi GUNB nie publikuje.')))),
      h('h2', { class: 'src-section__title' }, 'Pliki rejestru'),
      h('ul', { class: 'src-register' }, files.map((f) => {
        const b = blockOf(f.file_id);
        const zipName = f.url ? decodeURIComponent(String(f.url).split(/[?#]/)[0].split('/').pop() || '') : null;
        // The block text names the ZIP in parentheses; the line below says it again with its size – once is enough.
        const title = String(b?.text || f.filename || f.file_id).replace(zipName ? new RegExp(`\\s*\\(${escapeRegExp(zipName)}\\)\\s*$`) : /$^/, '');
        const member = f.zip_member && f.zip_member !== zipName ? f.zip_member : null;
        return h('li', { class: 'src-page src-page--register' },
          h('header', { class: 'src-page__head' },
            h('div', null,
              h('h3', { class: 'src-page__title' }, b?.category ? kindGlyph(b.category) : null, h('span', null, title)),
              h('p', { class: 'src-page__meta' },
                [zipName ? `${zipName}${f.size_zip ? ` (${formatBytes(f.size_zip)})` : ''}` : null, member ? `w środku ${member}` : null]
                  .filter(Boolean).join(' · ') || f.filename)),
            ext(f.url, 'Plik ZIP (GUNB)', 'download', 'btn btn--secondary btn--xs')),
          h('dl', { class: 'src-facts' },
            // The register snapshot the extract was cut from (the ZIP's Last-Modified), and – separately – when we checked.
            f.last_modified ? h('div', null, h('dt', null, 'Stan rejestru'), h('dd', null, `z ${formatDateTime(f.last_modified)}`)) : null,
            checked ? h('div', null, h('dt', null, 'Sprawdzono'), h('dd', null, checked)) : null,
            Number.isFinite(f.rows_total) ? h('div', null, h('dt', null, 'Wiersze w pliku'), h('dd', null, formatNumber(f.rows_total))) : null,
            Number.isFinite(f.parsed_count) ? h('div', null, h('dt', null, 'Z Pragi-Południe'), h('dd', null, formatNumber(f.parsed_count))) : null,
            h('div', null, h('dt', null, 'Sprawy'), h('dd', null, formatNumber((f.record_ids || []).length))),
            f.etag ? h('div', null, h('dt', null, 'ETag'), h('dd', { class: 'mono' }, String(f.etag))) : null,
            f.sha256_zip ? h('div', null, h('dt', null, 'SHA-256 archiwum'), h('dd', { class: 'mono', title: f.sha256_zip }, `${String(f.sha256_zip).slice(0, 16)}…`)) : null),
          (f.warnings || []).length ? h('ul', { class: 'src-file__warn' }, f.warnings.map((w) => h('li', null, icon('info', { size: 13 }), String(w)))) : null,
          h('div', { class: 'src-register__actions' },
            fileActions(f, { register: true }),
            ext(f.dataset_url, 'Zbiór na dane.gov.pl', 'external')));
      })),
      h('p', { class: 'muted small' }, 'Wyciąg (CSV) zawiera oryginalny wiersz nagłówka i wszystkie wiersze dotyczące Pragi-Południe w niezmienionej postaci i kolejności – można go porównać z plikiem GUNB. ',
        page.url ? ext(page.url, 'Strona pobierania GUNB', 'external', 'link') : null,
        datasetUrl ? [' · ', ext(datasetUrl, 'dane.gov.pl', 'external', 'link')] : null),
    ];
  }

  /** Dataset codes are fixed by docs/DATA_MODEL.md; an unknown dataset gets the monthly-list layout. */
  function panelFor(ds) {
    const g = groups.get(ds) || { pages: [], files: [] };
    if (ds === 'rwdz') return registerPanel(ds, g);
    if (ds === 'baipp') return cityPanel(ds, g);
    return districtPanel(ds, g);
  }

  const tabsEl = h('div', { class: 'tabs', role: 'tablist', 'aria-label': 'Zbiory danych' });
  const panelHost = h('div', { class: 'tabpanel', role: 'tabpanel', tabindex: '-1' });
  const tabLinks = new Map();
  for (const ds of datasetKeys) {
    const g = groups.get(ds);
    const n = ds === 'rwdz' ? plural(g.files.length, PLIK) : plural(g.pages.length, STRONA);
    const a = h('a', {
      class: 'tab', role: 'tab', id: `tab-${ds}`, href: buildHash({ route: 'sources', tab: ds }), 'aria-selected': 'false', tabindex: '-1',
      'aria-controls': 'src-panel',
    }, h('span', { class: 'tab__label' }, dsLabel(ds)), h('span', { class: 'tab__count' }, n));
    a.addEventListener('keydown', (e) => {
      const i = datasetKeys.indexOf(ds);
      let j = null;
      if (e.key === 'ArrowRight') j = (i + 1) % datasetKeys.length;
      else if (e.key === 'ArrowLeft') j = (i - 1 + datasetKeys.length) % datasetKeys.length;
      else if (e.key === 'Home') j = 0;
      else if (e.key === 'End') j = datasetKeys.length - 1;
      if (j == null) return;
      e.preventDefault();
      const next = tabLinks.get(datasetKeys[j]);
      window.location.replace(next.getAttribute('href'));
      next.focus();
    });
    tabLinks.set(ds, a);
    tabsEl.appendChild(a);
  }
  panelHost.id = 'src-panel';

  const generated = index.meta.generatedAt ? formatDateTime(index.meta.generatedAt) : null;
  replaceChildren(host, h('div', { class: 'page page--sources' },
    h('header', { class: 'page__head' },
      h('p', { class: 'eyebrow' }, 'Źródła danych'),
      h('h1', { class: 'page__title', tabindex: '-1' }, 'Każdy wpis ma swoje źródło'),
      h('p', { class: 'lead' }, datasetKeys.length > 1
        ? `Dane pochodzą z ${datasetKeys.length === 3 ? 'trzech' : formatNumber(datasetKeys.length)} publikacji: ${datasetKeys.map(dsTitle).join('; ')}. `
        : 'Wszystkie dane pochodzą z plików Excel publikowanych co miesiąc przez Urząd Dzielnicy Praga-Południe. ',
      'Poniżej jest pełna lista stron i plików – z liczbami, które podaje źródło, i liczbą wierszy, które odczytaliśmy.'),
      h('p', { class: 'updated' }, icon('clock', { size: 15 }),
        h('span', null, generated ? `Dane z dnia ${generated}` : 'Data aktualizacji nieznana')),
      h('p', { class: 'muted small' }, `${UNOFFICIAL}.`)),
    datasetKeys.length > 1 ? tabsEl : null,
    panelHost,
    index.meta.fixture ? h('p', { class: 'notice notice--warn' }, icon('alert', { size: 16 }), 'To są dane przykładowe (fixture) – liczba wpisów jest ograniczona.') : null));

  /**
   * Keyboard focus must not land under the sticky tabs and toolbar (WCAG 2.4.11): the page's scroll padding
   * (`--sticky-top`, used by app.css on the Sources route) follows the bottom edge of that sticky stack, which grows
   * when the toolbar wraps on a phone.
   */
  const stickyObserver = typeof ResizeObserver === 'function' ? new ResizeObserver(() => updateStickyTop()) : null;
  function updateStickyTop() {
    let bottom = 0;
    for (const el of [tabsEl, panels.get(active)?.querySelector('.src-toolbar')]) {
      if (!el || !el.isConnected || !el.offsetHeight) continue;
      const top = parseFloat(getComputedStyle(el).top) || 0;
      bottom = Math.max(bottom, top + el.offsetHeight);
    }
    if (bottom) document.documentElement.style.setProperty('--sticky-top', `${Math.round(bottom + 8)}px`);
  }
  if (stickyObserver) stickyObserver.observe(tabsEl);

  function show(tab) {
    const ds = tab && groups.has(tab) ? tab : datasetKeys[0];
    if (!ds) return;
    for (const [k, a] of tabLinks) {
      a.setAttribute('aria-selected', String(k === ds));
      a.tabIndex = k === ds ? 0 : -1;
    }
    panelHost.setAttribute('aria-labelledby', `tab-${ds}`);
    if (active === ds && panels.has(ds)) return;
    active = ds;
    if (!panels.has(ds)) panels.set(ds, h('div', { class: `src-panel src-panel--${ds}` }, panelFor(ds)));
    replaceChildren(panelHost, panels.get(ds));
    const toolbar = panels.get(ds).querySelector('.src-toolbar');
    if (toolbar && stickyObserver) stickyObserver.observe(toolbar);
    requestAnimationFrame(updateStickyTop);
  }

  return {
    show,
    /**
     * New records (permits) arrived. Only panels whose "Pokaż N wpisów" counts change are dropped (re-rendered
     * on next show); the panel on screen is re-rendered only if its own numbers changed – opened years, scroll
     * position and focus of a visitor reading the district tab are not disturbed by the idle prefetch.
     */
    dataChanged() {
      const before = recordCountByFile;
      recordCountByFile = recordCounts();
      const shown = (m, f) => m.get(f.file_id) || (f.record_ids || []).length;
      const changed = (ds) => (groups.get(ds)?.files || []).some((f) => shown(before, f) !== shown(recordCountByFile, f));
      for (const ds of [...panels.keys()]) if (changed(ds)) panels.delete(ds);
      if (active && !panels.has(active) && host.offsetParent !== null) {
        const cur = active;
        active = null;
        show(cur);
      }
    },
  };
}
