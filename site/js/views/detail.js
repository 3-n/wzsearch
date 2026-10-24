/**
 * Record detail panel (route #/wpis/<id>): facts, investment, location & parcels, tags, data-quality
 * notes, related records as a mini timeline (incl. building permits on the same parcel – the
 * "WZ → pozwolenie na budowę" story) and a strong provenance block per dataset (every source row, verbatim).
 */
import { h, replaceChildren, copyText, safeUrl, prefersReducedMotion } from '../dom.js';
import { icon, kindGlyph } from '../icons.js';
import {
  formatDate, formatDateTime, formatMonth, formatMonthNumeric, formatBytes, formatNumber, plural, tidyCell,
  decisionAfter, formatLineList, formatCubature, DZIALKA, WPIS, WIERSZ,
} from '../format.js';
import { relatedChain, relationReason, datasetOf } from '../data.js';
import { missingPermitIds } from '../lazy.js';
import { DEFAULT_KINDS, OPT_IN_KINDS, withOptIn } from '../kinds.js';
import { kindBadge, outcomeBadge, precisionOf, precisionDescription, entryTitle, entryDate, displayCase } from '../components/card.js';
import { toast } from '../components/toast.js';
import {
  KIND_EXPLAINERS, KIND_STEP, KIND_PLURAL, DATE_LABEL, NUMBER_LABEL, APPLICANT_LABELS, PRECISION, DEMOLITION_STEP,
  OUTCOME_EMPHASIS, LICENCE_URLS, OUTCOME_STEP, OUTCOME_PLURAL, PROCEDURE_ACC, KIND_LIST_LABEL,
} from '../copy.js';
import { GEOPORTAL_PARCEL_URL, ISSUES_URL, INFO_REQUEST } from '../config.js';
import { infoRequest, mailtoHref } from '../request.js';

const PARCELS_COLLAPSED = 12;
/** What a refusal means for residents, per kind (outcome "refusal", docs/DATA_MODEL.md). */
const REFUSAL_TEXT = {
  wz: 'Urząd odmówił ustalenia warunków zabudowy – ta decyzja nie pozwala zbudować tego, o co wnioskowano.',
  cp: 'Urząd odmówił ustalenia lokalizacji tej inwestycji celu publicznego.',
  other: 'Urząd odmówił wydania decyzji, o którą wnioskowano.',
};
/** Related chains up to this length get the step-by-step summary ("wszczęcie 07.2022 → decyzja WZ 09.2022"). */
const CHAIN_STEPS_MAX = 6;
/** Collapsed long chains show this many records on each side of the current one. */
const CHAIN_WINDOW = 3;
const POWIAZANY = ['powiązany wpis', 'powiązane wpisy', 'powiązanych wpisów'];
const POZWOLENIE_NA_BUDOWE = ['pozwolenie na budowę', 'pozwolenia na budowę', 'pozwoleń na budowę'];
const own = (table, key) => (key != null && Object.hasOwn(table, key) ? table[key] : null);
const cap = (x) => (x ? x[0].toUpperCase() + x.slice(1) : x);

/** Show the address "as in the source" only when it says more than the cleaned display text. */
function rawAddressDiffers(addr) {
  if (!addr?.raw) return false;
  const norm = (x) => String(x || '').replace(/Praga\s*-?\s*Po[lł]ud\w*\.?|Warszawa|\bul\.\s*/gi, ' ')
    .replace(/[\s/,;-]+/g, ' ').trim().toLowerCase();
  return norm(addr.raw) !== norm(addr.display);
}

function section(title, body, { id, iconName, extra } = {}) {
  return h('section', { class: 'dsec', 'aria-labelledby': id },
    h('h3', { class: 'dsec__title', id }, iconName ? icon(iconName, { size: 16 }) : null, title, extra || null),
    body);
}

function extLink(href, label, iconName = 'external', cls = 'btn btn--secondary btn--sm') {
  const url = safeUrl(href);
  if (!url) return null;
  const external = /^https?:/i.test(url);
  return h('a', {
    class: cls, href: url, target: external ? '_blank' : null, rel: external ? 'noopener noreferrer' : null,
  }, icon(iconName, { size: 15 }), h('span', null, label), external ? h('span', { class: 'sr-only' }, ' (otwiera się w nowej karcie)') : null);
}

/** Collapse sources that point at the same file row (one file linked from several monthly pages). */
function groupSources(sources) {
  const groups = new Map();
  for (const s of sources) {
    const key = `${s.file_id}|${s.sheet}|${s.row}`;
    if (!groups.has(key)) groups.set(key, { ...s, page_ids: [] });
    const g = groups.get(key);
    if (s.page_id && !g.page_ids.includes(s.page_id)) g.page_ids.push(s.page_id);
  }
  return [...groups.values()];
}

function rawTable(raw) {
  const rows = Array.isArray(raw) ? raw : [];
  if (!rows.length) return h('p', { class: 'muted' }, 'Brak zapisanych danych źródłowych dla tego wiersza.');
  return h('table', { class: 'table table--raw' },
    h('caption', { class: 'sr-only' }, 'Komórki wiersza w kolejności kolumn pliku'),
    h('thead', null, h('tr', null, h('th', { scope: 'col' }, 'Kolumna w pliku'), h('th', { scope: 'col' }, 'Wartość'))),
    h('tbody', null, rows.map((pair) => {
      const [label, value] = Array.isArray(pair) ? pair : ['', pair];
      const v = value == null ? '' : String(value);
      return h('tr', null, h('th', { scope: 'row' }, label == null || label === '' ? '—' : String(label)),
        h('td', { class: v.trim() ? null : 'muted' }, v.trim() ? v : '(pusta komórka)'));
    })));
}

const rawDetails = (raw, hint = ' – dokładnie tak, jak w pliku') => h('details', { class: 'prov__raw' },
  h('summary', null, icon('table', { size: 15 }), 'Dane w źródle', h('span', { class: 'muted' }, hint)),
  rawTable(raw));

function fileMeta(file) {
  if (!file?.last_modified && !file?.sha256 && !(file?.history || []).length) return null;
  return h('p', { class: 'prov__meta' },
    file?.last_modified ? h('span', null, `Plik z dnia ${formatDateTime(file.last_modified, { time: false })}`) : null,
    (file?.history || []).length ? h('span', null, `Urząd podmieniał ten plik (${file.history.length}×) – archiwizujemy wcześniejsze wersje`) : null,
    file?.sha256 ? h('span', { title: `SHA-256: ${file.sha256}` }, 'SHA-256 ', h('code', null, `${String(file.sha256).slice(0, 12)}…`)) : null);
}

/** Spreadsheet provenance (district monthly lists and BAiPP yearly lists): page(s) + file + sheet/row + raw cells. */
function sheetSource(s, index, { dataset, compact = false } = {}) {
  const file = index.filesById.get(s.file_id);
  // Every page that links this file (a file may be re-linked in a later month).
  const pageIds = [...s.page_ids, ...((file?.page_ids || []).filter((p) => !s.page_ids.includes(p)))];
  const pages = pageIds.map((p) => index.pagesById.get(p) || { page_id: p });
  const fname = file?.filename || `plik ${s.file_id}`;
  const cityWide = dataset === 'baipp' && Number.isFinite(file?.rows_total);
  return h('article', { class: ['prov', compact && 'prov--compact'] },
    h('div', { class: 'prov__head' },
      h('span', { class: 'prov__icon' }, icon('sheet', { size: 20 })),
      h('div', { class: 'prov__file' },
        h('p', { class: 'prov__name' }, fname),
        h('p', { class: 'prov__loc' },
          s.sheet && String(s.sheet).trim() ? `Arkusz „${String(s.sheet).trim()}”` : (s.sheet != null ? 'Arkusz bez nazwy' : 'Arkusz nieznany'),
          s.row != null ? `, wiersz ${s.row}` : '',
          file?.size ? h('span', { class: 'muted' }, ` · ${formatBytes(file.size)}`) : null))),
    cityWide ? h('p', { class: 'prov__context' }, icon('info', { size: 14 }),
      h('span', null, `Plik ogólnomiejski: ${plural(file.rows_total, WIERSZ)}, dla Pragi-Południe: ${formatNumber(file.parsed_count ?? 0)}. `,
        'Pozostałe wiersze dotyczą innych dzielnic i ich nie pokazujemy.')) : null,
    compact ? null : h('ul', { class: 'prov__pages' }, pages.map((p, pi) => h('li', null,
      icon('globe', { size: 14 }),
      h('span', null, pi === 0 ? 'Opublikowano na stronie ' : 'Podlinkowany także na stronie ', h('strong', null, p.title || p.page_id),
        p.published_at ? ` · ${formatDateTime(p.published_at, { time: false })}` : '')))),
    h('div', { class: 'prov__actions' },
      compact ? null : pages.map((p, pi) => extLink(p.url, pages.length > 1 ? `Strona źródłowa (${p.title || pi + 1})` : 'Strona źródłowa', 'external')),
      extLink(file?.url, 'Plik XLSX (oryginał)', 'download'),
      file?.archive_path ? extLink(file.archive_path, 'Kopia archiwalna', 'archive') : null),
    (file?.warnings || []).length && compact ? h('p', { class: 'prov__meta' }, file.warnings.map((w) => h('span', null, String(w)))) : null,
    fileMeta(file),
    rawDetails(s.raw));
}

/**
 * BAiPP republishes its current-year file every month: the same row then appears in several snapshot files of
 * one page. The newest snapshot is shown in full, older ones collapsed.
 */
function snapshotSources(groups, index) {
  const byPage = new Map();
  for (const g of groups) {
    const file = index.filesById.get(g.file_id);
    const key = g.page_id || file?.page_ids?.[0] || g.file_id;
    if (!byPage.has(key)) byPage.set(key, []);
    byPage.get(key).push({ g, file });
  }
  const out = [];
  for (const items of byPage.values()) {
    items.sort((a, b) => String(b.file?.last_modified || '').localeCompare(String(a.file?.last_modified || '')));
    const [newest, ...older] = items;
    out.push(sheetSource(newest.g, index, { dataset: 'baipp' }));
    if (older.length) {
      out.push(h('details', { class: 'prov-older' },
        h('summary', null, icon('history', { size: 15 }),
          `Ten sam wiersz także w ${plural(older.length, ['wcześniejszej wersji', 'wcześniejszych wersjach', 'wcześniejszych wersjach'])} pliku`),
        h('p', { class: 'muted small' }, 'Biuro co miesiąc publikuje nowy plik z danymi od początku roku pod nowym adresem; zachowujemy każdą pobraną wersję.'),
        h('div', { class: 'prov-list' }, older.map(({ g }) => sheetSource(g, index, { dataset: 'baipp', compact: true })))));
    }
  }
  return out;
}

/** GUNB RWDZ provenance: the dataset, the snapshot (ZIP), the mirrored extract with line numbers, raw columns. */
function registerSource(s, index, datasetDict) {
  const file = index.filesById.get(s.file_id);
  const rows = Array.isArray(s.rows) && s.rows.length ? s.rows : (s.row != null ? [s.row] : []);
  const extractRows = Array.isArray(s.extract_rows) ? s.extract_rows : [];
  const licence = file?.licence || datasetDict?.licence || null;
  const licenceUrl = file?.licence_url || datasetDict?.licence_url || (licence ? LICENCE_URLS[licence] : null);
  const zipName = file?.url ? decodeURIComponent(String(file.url).split(/[?#]/)[0].split('/').pop() || '') : null;
  // The CSV inside GUNB's ZIP: `zip_member` when the pipeline records it, else a filename that is not the ZIP itself.
  const member = file?.zip_member || (file?.filename && file.filename !== zipName ? file.filename : null);
  return h('article', { class: 'prov prov--register' },
    h('div', { class: 'prov__head' },
      h('span', { class: 'prov__icon' }, icon('table', { size: 20 })),
      h('div', { class: 'prov__file' },
        h('p', { class: 'prov__name' }, datasetDict?.label || 'Rejestr GUNB'),
        h('p', { class: 'prov__loc' }, [datasetDict?.publisher, licence ? `licencja ${licence}` : null].filter(Boolean).join(' · ')))),
    h('dl', { class: 'prov__facts' },
      h('div', null, h('dt', null, 'Plik'), h('dd', null, member || zipName || file?.filename || s.file_id,
        member && zipName ? h('span', { class: 'muted' }, ` (w archiwum ${zipName}${file?.size_zip ? `, ${formatBytes(file.size_zip)}` : ''})`) : null)),
      rows.length ? h('div', null, h('dt', null, rows.length > 1 ? 'Wiersze w pliku GUNB' : 'Wiersz w pliku GUNB'),
        h('dd', null, h('span', { class: 'mono' }, formatLineList(rows)),
          rows.length > 1 ? h('span', { class: 'muted' }, ` (${plural(rows.length, WIERSZ)} – jeden na działkę)`) : null)) : null,
      extractRows.length ? h('div', null, h('dt', null, 'Wiersze w naszym wyciągu'), h('dd', { class: 'mono' }, formatLineList(extractRows))) : null,
      // The snapshot of GUNB's register our extract was cut from (the ZIP's Last-Modified) – not when we looked.
      file?.last_modified ? h('div', null, h('dt', null, 'Stan rejestru'), h('dd', null, `z ${formatDateTime(file.last_modified)}`,
        h('span', { class: 'muted' }, ' – ta wersja pliku GUNB posłużyła do wyciągu'))) : null,
      checkedAt(index) ? h('div', null, h('dt', null, 'Sprawdzono'), h('dd', null, formatDateTime(checkedAt(index)),
        h('span', { class: 'muted' }, ' – ostatnia aktualizacja danych wzSearch'))) : null),
    h('div', { class: 'prov__actions' },
      extLink(file?.archive_path, 'Wyciąg dla Pragi-Południe (CSV)', 'download'),
      extLink(file?.url, 'Plik ZIP (GUNB)', 'archive'),
      extLink(file?.dataset_url, 'Zbiór na dane.gov.pl', 'external'),
      licenceUrl ? extLink(licenceUrl, licence, 'book', 'btn btn--ghost btn--sm') : null),
    h('p', { class: 'notice notice--quiet' }, icon('info', { size: 15 }),
      h('span', null, 'GUNB nie udostępnia stałych linków do pojedynczych spraw (wyszukiwarka wymaga przepisania kodu CAPTCHA), dlatego wskazujemy plik i numery wierszy. ',
        'Sprawę można odszukać ręcznie w ', h('a', { class: 'link', href: 'https://wyszukiwarka.gunb.gov.pl/', target: '_blank', rel: 'noopener noreferrer' }, 'wyszukiwarce GUNB',
          h('span', { class: 'sr-only' }, ' (otwiera się w nowej karcie)')),
        ' po numerze z rejestru.')),
    (file?.etag || file?.sha256_zip || file?.sha256) ? h('p', { class: 'prov__meta' },
      file?.sha256 ? h('span', { title: `SHA-256 wyciągu: ${file.sha256}` }, 'SHA-256 wyciągu ', h('code', null, `${String(file.sha256).slice(0, 12)}…`)) : null,
      file?.sha256_zip ? h('span', { title: `SHA-256 archiwum ZIP: ${file.sha256_zip}` }, 'ZIP ', h('code', null, `${String(file.sha256_zip).slice(0, 12)}…`)) : null,
      file?.etag ? h('span', null, 'ETag ', h('code', null, String(file.etag))) : null) : null,
    rawDetails(s.raw, ' – kolumny rejestru (bez danych projektantów)'));
}

/** When the data was last built (= when the register was last checked): permits.json, else records.json. */
function checkedAt(index) {
  return index.permitsMeta?.generatedAt || index.meta?.generatedAt || null;
}

function provenance(entry, index) {
  const groups = groupSources(Array.isArray(entry.rec.sources) ? entry.rec.sources : []);
  if (!groups.length) {
    return h('p', { class: 'notice notice--warn' }, icon('alert', { size: 16 }), 'Brak informacji o źródle tego wpisu.');
  }
  const dsOf = (g) => datasetOf(index.filesById.get(g.file_id) || (g.page_id ? index.pagesById.get(g.page_id) : null), index.pagesById);
  const register = groups.filter((g) => dsOf(g) === 'rwdz');
  const baipp = groups.filter((g) => dsOf(g) === 'baipp');
  const other = groups.filter((g) => !register.includes(g) && !baipp.includes(g));
  return h('div', { class: 'prov-list' },
    other.map((g) => sheetSource(g, index, { dataset: dsOf(g) })),
    baipp.length ? snapshotSources(baipp, index) : null,
    register.map((g) => registerSource(g, index, index.dicts.datasets?.rwdz)));
}

/**
 * Step label in the related-records summary: "decyzja WZ 09.2023", "pozwolenie na rozbiórkę 05.2024"; a WZ/CP decision
 * whose source states a negative outcome is named by it ("odmowa WZ 03.2025", "umorzenie CP 10.2023").
 */
export function stepLabel(e) {
  const month = e.month ? formatMonthNumeric(e.month) : '?';
  const outcome = (e.kind === 'wz' || e.kind === 'cp') ? own(OUTCOME_STEP, e.outcome) : null;
  if (outcome) return `${outcome} ${e.kind === 'wz' ? 'WZ' : 'CP'} ${month}`;
  const base = e.kind === 'pb' && e.scope === 'rozbiorka' ? DEMOLITION_STEP : (KIND_STEP[e.kind] || e.kind);
  return `${base} ${month}`;
}

/** Count label of one kind in a long chain: "3 decyzje WZ (w tym 1 odmowa, 1 umorzenie)". Pure; exported for tests. */
export function kindCountLabel(kind, entries) {
  const n = entries.length;
  const base = KIND_PLURAL[kind] ? plural(n, KIND_PLURAL[kind]) : `${formatNumber(n)} × ${kind}`;
  if (kind !== 'wz' && kind !== 'cp') return base;
  const outcomes = new Map();
  for (const e of entries) if (own(OUTCOME_PLURAL, e.outcome)) outcomes.set(e.outcome, (outcomes.get(e.outcome) || 0) + 1);
  if (!outcomes.size) return base;
  return `${base} (w tym ${[...outcomes].map(([o, c]) => plural(c, OUTCOME_PLURAL[o])).join(', ')})`;
}

function relatedSection(entry, index, ctx) {
  const chain = relatedChain(index, entry);
  const missing = missingPermitIds(entry.rec, index.byId);
  const permitsState = ctx.permitsState ? ctx.permitsState() : 'loaded';
  const pending = missing.length > 0 && !index.permitsLoaded && permitsState !== 'error';
  const failed = missing.length > 0 && permitsState === 'error';
  if (chain.length < 2 && !pending && !failed) return null;
  const cur = chain.findIndex((e) => e.id === entry.id);
  const long = chain.length > CHAIN_STEPS_MAX;

  let summary = null;
  if (chain.length >= 2 && !long) {
    const text = chain.map(stepLabel).join(' → ');
    // Each arrow travels with the step it leads to, so a wrapped line always starts with "→ step".
    summary = h('p', { class: 'chain-summary', 'aria-label': `Przebieg: ${text}` }, chain.map((e, i) => h('span', { class: 'chain-summary__item' },
      i ? h('span', { class: 'chain-summary__arrow', 'aria-hidden': 'true' }, '→') : null,
      h('span', { class: ['chain-summary__step', e.id === entry.id && 'is-current', OPT_IN_KINDS.includes(e.kind) && 'is-permit'] }, kindGlyph(e.kind), stepLabel(e)))));
  } else if (long) {
    // Many records (typically one large parcel shared by a whole development): count them instead. The number is the
    // one in the section heading (the other records); the kind counts include this one.
    const byKind = new Map(index.kindCodes.map((k) => [k, []]));
    for (const e of chain) byKind.set(e.kind, [...(byKind.get(e.kind) || []), e]);
    for (const [k, list] of byKind) if (!list.length) byKind.delete(k);
    const years = chain.map((e) => (e.month || '').slice(0, 4)).filter(Boolean);
    const span = years.length ? (years[0] === years[years.length - 1] ? `z ${years[0]} r.` : `z lat ${years[0]}–${years[years.length - 1]}`) : '';
    summary = h('p', { class: 'chain-count' },
      h('strong', null, `${plural(chain.length - 1, POWIAZANY)} ${span}`.trim()),
      h('span', { class: 'chain-count__kinds' }, [...byKind].map(([k, list]) => h('span', { class: 'chain-count__kind' },
        kindGlyph(k), kindCountLabel(k, list)))));
  }

  let lo = 0;
  let hi = chain.length - 1;
  if (long) {
    lo = Math.max(0, Math.min(cur - CHAIN_WINDOW, chain.length - 1 - 2 * CHAIN_WINDOW));
    hi = Math.min(chain.length - 1, lo + 2 * CHAIN_WINDOW);
  }
  const list = h('ol', { class: 'chain', id: `chain-${entry.id}` });
  const items = [];
  const currentBody = () => list.querySelector('.chain__item.is-current .chain__body');
  // Long chains: "pokaż wszystkie" unfolds every record, "Zwiń listę" restores the window around this one.
  const expand = (e) => {
    const fromKeyboard = e && e.detail === 0;
    items.forEach((li) => { li.hidden = false; });
    list.querySelectorAll('.chain__gap').forEach((li) => li.remove());
    const collapseBtn = h('button', { type: 'button', class: 'btn btn--link btn--xs', 'aria-controls': list.id, onClick: () => collapse(true) },
      icon('chevronUp', { size: 14 }), 'Zwiń listę');
    list.appendChild(h('li', { class: 'chain__gap chain__gap--collapse' }, collapseBtn));
    currentBody()?.scrollIntoView({ block: 'nearest' });
    if (fromKeyboard) currentBody()?.focus({ preventScroll: true });
  };
  const gap = (n, earlier) => h('li', { class: 'chain__gap' },
    h('button', { type: 'button', class: 'btn btn--link btn--xs', 'aria-controls': list.id, onClick: expand },
      icon(earlier ? 'chevronUp' : 'chevronDown', { size: 14 }),
      `${earlier ? 'Wcześniejsze' : 'Późniejsze'}: ${plural(n, WPIS)} – pokaż wszystkie`));
  function collapse(focus = false) {
    list.querySelectorAll('.chain__gap').forEach((li) => li.remove());
    items.forEach((li, i) => { li.hidden = i < lo || i > hi; });
    if (lo > 0) list.insertBefore(gap(lo, true), items[0]);
    if (hi < chain.length - 1) list.appendChild(gap(chain.length - 1 - hi, false));
    if (focus) {
      const cur = currentBody();
      cur?.scrollIntoView({ block: 'nearest' });
      (list.querySelector('.chain__gap button') || cur)?.focus({ preventScroll: true });
    }
  }
  if (chain.length >= 2) {
    chain.forEach((e) => {
      const current = e.id === entry.id;
      const why = current ? null : relationReason(entry.rec, e.rec);
      const body = [
        h('span', { class: 'chain__date' }, entryDate(e)),
        h('span', { class: 'chain__title' }, `${index.dicts.kinds?.[e.kind]?.short || e.kind} · ${e.rec.number || 'bez numeru'}`,
          outcomeBadge(e, index.dicts)),
        // Register texts in capitals are sentence-cased in this one-line excerpt (display only, as on the cards).
        h('span', { class: 'chain__sub' }, e.rec.investment ? (OPT_IN_KINDS.includes(e.kind) ? displayCase(e.rec.investment) : e.rec.investment) : entryTitle(e)),
        why ? h('span', { class: 'chain__why' }, why) : null,
      ];
      const li = h('li', { class: ['chain__item', `chain__item--${e.kind}`, current && 'is-current'] },
        h('span', { class: 'chain__dot' }, kindGlyph(e.kind)),
        current
          ? h('div', { class: 'chain__body', 'aria-current': 'true', tabindex: '-1' }, body, h('span', { class: 'chain__here' }, 'ten wpis'))
          : h('a', {
            class: 'chain__body', href: ctx.recordHref(e.id),
            onClick: (ev) => { if (ev.metaKey || ev.ctrlKey || ev.shiftKey) return; ev.preventDefault(); ctx.onOpen(e.id); },
          }, body));
      items.push(li);
      list.appendChild(li);
    });
    collapse();
  }

  const permitNote = pending
    ? h('p', { class: 'chain-pending', role: 'status' }, h('span', { class: 'spinner', 'aria-hidden': 'true' }),
      `Wczytywanie powiązanych pozwoleń na budowę (${formatNumber(missing.length)})…`)
    : failed ? h('p', { class: 'chain-pending chain-pending--error' }, icon('alert', { size: 14 }),
      `Nie udało się wczytać powiązanych pozwoleń na budowę (${formatNumber(missing.length)}). `,
      ctx.onRetryPermits ? h('button', { type: 'button', class: 'btn btn--link btn--xs', onClick: () => ctx.onRetryPermits() }, 'Spróbuj ponownie') : null)
      : null;
  const hasPermits = chain.some((e) => OPT_IN_KINDS.includes(e.kind) && e.id !== entry.id) || pending;
  return section('Powiązane wpisy', [
    h('p', { class: 'dsec__lead' }, hasPermits
      ? 'Ta sama działka lub ten sam adres w innych publikacjach i w rejestrze pozwoleń na budowę:'
      : 'Ta sama działka lub ten sam adres w innych publikacjach:'),
    summary,
    permitNote,
    chain.length >= 2 ? list : null,
    hasPermits ? h('p', { class: 'muted small chain-caveat' }, 'Wspólna działka nie zawsze oznacza tę samą inwestycję – na dużych działkach (np. spółdzielczych) bywa wiele niezależnych spraw.') : null,
  ], { id: 'd-related', iconName: 'history', extra: long ? h('span', { class: 'count' }, formatNumber(chain.length - 1)) : null });
}

function parcelsBlock(entry) {
  const r = entry.rec;
  const parcels = Array.isArray(r.parcels) ? r.parcels : [];
  const found = new Set(r.geo?.parcels_found || []);
  if (!parcels.length) {
    return r.parcels_raw ? h('p', null, h('span', { class: 'muted' }, 'Oznaczenie w źródle: '), h('span', { class: 'pre' }, tidyCell(r.parcels_raw))) : h('p', { class: 'muted' }, 'Brak oznaczenia działek.');
  }
  const items = parcels.map((p, i) => h('li', { class: ['parcel', i >= PARCELS_COLLAPSED && 'parcel--extra'], hidden: i >= PARCELS_COLLAPSED },
    p.id ? h('a', {
      href: GEOPORTAL_PARCEL_URL + encodeURIComponent(p.id).replace(/%2F/g, '/'), target: '_blank', rel: 'noopener noreferrer',
      class: 'parcel__link', title: `Pokaż działkę ${p.id} w Geoportalu`,
    }, h('span', { class: 'parcel__no' }, `dz. ${p.number}`), h('span', { class: 'parcel__obr' }, `obr. ${p.obreb}`),
    p.partial ? h('span', { class: 'parcel__part' }, 'część') : null,
    p.access ? h('span', { class: 'parcel__access', title: 'Działka wskazana jako dojazd do inwestycji' }, 'dojazd') : null,
    found.has(p.id) ? icon('target', { size: 13, label: 'na mapie' }) : null,
    icon('external', { size: 12 }), h('span', { class: 'sr-only' }, ' (Geoportal, nowa karta)'))
      : h('span', null, `dz. ${p.number} obr. ${p.obreb}`)));
  const list = h('ul', { class: 'parcels' }, items);
  const more = parcels.length > PARCELS_COLLAPSED ? h('button', {
    type: 'button', class: 'btn btn--link btn--xs', 'aria-expanded': 'false',
    onClick: (e) => {
      const open = e.currentTarget.getAttribute('aria-expanded') !== 'true';
      list.querySelectorAll('.parcel--extra').forEach((li) => { li.hidden = !open; });
      e.currentTarget.setAttribute('aria-expanded', String(open));
      e.currentTarget.textContent = open ? 'Zwiń listę działek' : `Pokaż wszystkie ${plural(parcels.length, DZIALKA)}`;
    },
  }, `Pokaż wszystkie ${plural(parcels.length, DZIALKA)}`) : null;
  // Register parcel ids ("146507_8.0605.25/12") say nothing more than the list itself.
  const rawWorthShowing = r.parcels_raw && !/^[\d_.\/\s\n-]+$/.test(r.parcels_raw.replace(/146507_8/g, ''));
  return [list, more,
    rawWorthShowing ? h('details', { class: 'mini-details' }, h('summary', null, 'Oznaczenie działek w źródle'), h('p', { class: 'pre' }, tidyCell(r.parcels_raw))) : null];
}

const fact = (label, value, { wide = false, mono = false, sub = null } = {}) => (value == null || value === '' ? null
  : h('div', { class: wide ? 'facts__wide' : null }, h('dt', null, label), h('dd', { class: mono ? 'mono' : null }, value,
    sub ? h('span', { class: 'facts__sub' }, sub) : null)));

/** Facts specific to building permits / notifications (GUNB RWDZ). */
function permitFacts(entry, index) {
  const r = entry.rec;
  const p = r.permit && typeof r.permit === 'object' ? r.permit : {};
  const dicts = index.dicts;
  const scopeLabel = p.scope ? (dicts.scopes?.[p.scope]?.label || p.scope) : null;
  const catLabel = p.category ? (p.category_label || dicts.categories?.[p.category]?.label || null) : null;
  const filedThenDecided = entry.kind === 'pb' && r.filed_date && r.date;
  return [
    fact('Numer w rejestrze GUNB', p.register_id, { wide: true, mono: true }),
    // Notifications use the office case sign as their number: say it once.
    p.case_sign !== r.number ? fact('Znak sprawy w urzędzie', p.case_sign, { wide: (p.case_sign || '').length > 18, mono: true }) : null,
    filedThenDecided ? h('div', { class: 'facts__wide' }, h('dt', null, 'Wniosek → decyzja'),
      h('dd', { class: 'span-dates' },
        h('span', null, formatDate(r.filed_date)), h('span', { class: 'span-dates__arrow', 'aria-hidden': 'true' }, '→'),
        h('span', null, formatDate(r.date)),
        decisionAfter(r.filed_date, r.date) ? h('span', { class: 'span-dates__days' }, decisionAfter(r.filed_date, r.date)) : null)) : null,
    fact('Zakres robót', scopeLabel || p.scope_label, { sub: p.scope_label && scopeLabel && p.scope_label.toLowerCase() !== scopeLabel.toLowerCase() ? `w rejestrze: „${p.scope_label}”` : null }),
    fact('Kategoria obiektu', p.category ? `${p.category}${catLabel ? ` – ${catLabel}` : ''}` : null),
    typeof p.single_family === 'boolean' ? fact('Budynek jednorodzinny', p.single_family ? 'tak' : 'nie') : null,
    fact('Kubatura', formatCubature(p.cubature)),
    fact('Stan zgłoszenia', p.state),
  ];
}

/** What the request gets you, per kind (the list only has a summary; the office has the full file). */
const ASK_LEAD = {
  wz: 'Zestawienie podaje tylko streszczenie decyzji. Pełną treść – z załącznikiem graficznym i analizą urbanistyczną, która uzasadnia parametry zabudowy – urząd udostępnia na wniosek.',
  cp: 'Zestawienie podaje tylko streszczenie decyzji. Pełną treść – z załącznikiem graficznym – urząd udostępnia na wniosek.',
  ws: 'Sprawa jest w toku. Możesz poprosić o kopię wniosku, mapę terenu inwestycji i informację, na jakim etapie jest postępowanie.',
  pb: 'Rejestr GUNB podaje tylko podstawowe dane. Decyzję i rysunki z projektu (zagospodarowanie działki, elewacje) urząd udostępnia na wniosek.',
  zg: 'Rejestr GUNB podaje tylko podstawowe dane. Treść zgłoszenia i informację, czy urząd wniósł sprzeciw, możesz uzyskać na wniosek.',
};

/** "Zapytaj urząd": a prefilled request for public information, sent from the user's own mail program. */
function askSection(entry, kd) {
  const req = infoRequest(entry.kind, entry.rec, { kindLabel: kd.label });
  const text = h('textarea', {
    class: 'ask__text', id: 'ask-text', rows: '16', spellcheck: 'false', 'aria-label': 'Treść wniosku (możesz ją zmienić)',
  });
  text.value = req.body;
  const mail = h('a', { class: 'btn btn--primary btn--sm', href: mailtoHref(req) },
    icon('inbox', { size: 15 }), h('span', null, 'Wyślij e-mailem'));
  // Edits in the textarea (e.g. the signature) go into the e-mail too.
  text.addEventListener('input', () => { mail.href = mailtoHref({ ...req, body: text.value }); });
  const copyBtn = h('button', {
    type: 'button', class: 'btn btn--secondary btn--sm',
    onClick: async () => {
      const ok = await copyText(text.value);
      toast(ok ? 'Skopiowano treść wniosku.' : 'Nie udało się skopiować treści.', { kind: ok ? 'success' : 'error' });
    },
  }, icon('copy', { size: 15 }), h('span', null, 'Kopiuj treść'));
  return section('Zapytaj urząd o dokumenty', [
    h('p', { class: 'dsec__lead' }, ASK_LEAD[entry.kind] || 'Pełne dokumenty tej sprawy urząd udostępnia na wniosek.',
      ' Każdy może o nie poprosić, bez podawania powodu. Odpowiedź przychodzi w ciągu 14 dni (w uzasadnionych przypadkach do 2 miesięcy), zwykle bezpłatnie.'),
    entry.kind === 'ws' ? h('p', { class: 'muted small ask__party' },
      'Jeśli jesteś właścicielem lub użytkownikiem wieczystym sąsiedniej działki, możesz być stroną postępowania – wtedy masz prawo przeglądać całe akta sprawy i składać uwagi (art. 73 Kodeksu postępowania administracyjnego).') : null,
    req.note ? h('p', { class: 'notice notice--quiet', role: 'note' }, icon('info', { size: 15 }), h('span', null, req.note)) : null,
    h('details', { class: 'ask__details' },
      h('summary', null, 'Pokaż i edytuj treść wniosku'),
      h('p', { class: 'muted small' }, 'Przed wysłaniem wpisz na końcu swoje imię i nazwisko. Możesz dopisać, o co jeszcze chcesz zapytać.'),
      text),
    h('div', { class: 'prov__actions' }, mail, copyBtn),
    h('p', { class: 'muted small ask__how' },
      req.to ? ['Adresat: ', h('span', { class: 'mono' }, req.to), req.inbox ? ` (${req.inbox})` : null, '. '] : null,
      req.fallback ? ['Możesz też wysłać wniosek na ogólny adres Urzędu m.st. Warszawy: ', h('span', { class: 'mono' }, req.fallback), '. '] : null,
      'Strona niczego nie wysyła – wiadomość otwiera się w Twoim programie pocztowym. ',
      req.edelivery ? ['Wolisz ePUAP? Wklej treść jako „Pismo ogólne do podmiotu publicznego” albo wyślij przez e-Doręczenia na adres ',
        h('span', { class: 'mono' }, req.edelivery), '. '] : null,
      INFO_REQUEST.guideUrl ? h('a', { class: 'link', href: INFO_REQUEST.guideUrl, target: '_blank', rel: 'noopener noreferrer' },
        'Jak działa dostęp do informacji publicznej (warszawa19115.pl)', h('span', { class: 'sr-only' }, ' (otwiera się w nowej karcie)')) : null),
  ], { id: 'd-ask', iconName: 'inbox' });
}

/**
 * Render the detail panel.
 * @param {HTMLElement} host
 * @param {object} entry
 * @param {{
 *   index: object, position: {i: number, n: number}|null, prevId: string|null, nextId: string|null,
 *   recordHref: (id: string) => string, onOpen: (id: string) => void, onClose: () => void,
 *   onFilter: (patch: object) => void, onShowOnMap: (id: string) => void, modal: boolean,
 *   permitsState?: () => string, onRetryPermits?: () => void,
 *   hiddenKind?: boolean, onShowKind?: () => void,
 * }} ctx
 *   hiddenKind: the record's kind is not in the current kind selection (e.g. a permit while permits are hidden)
 */
export function renderDetail(host, entry, ctx) {
  const { index } = ctx;
  const r = entry.rec;
  const dicts = index.dicts;
  const kd = dicts.kinds?.[entry.kind] || {};
  const precision = precisionOf(entry);
  const prec = PRECISION[precision];
  const precText = precisionDescription(entry);
  const warnings = (Array.isArray(r.warnings) ? r.warnings : []).filter(Boolean);
  const tags = (Array.isArray(r.tags) ? r.tags : []);
  const procLabel = entry.kind === 'ws' && r.procedure ? (dicts.kinds?.[r.procedure]?.label || r.procedure) : null;
  const isPermit = OPT_IN_KINDS.includes(entry.kind);
  // Facet links from a permit keep permits switched on (otherwise the list would not contain this kind).
  const scopeKinds = isPermit ? { kinds: withOptIn(DEFAULT_KINDS, [entry.kind]) } : {};
  const outcome = entry.outcome ? dicts.outcomes?.[entry.outcome] : null;
  const issuer = entry.issuer ? dicts.issuers?.[entry.issuer] : null;
  const dataset = entry.dataset ? dicts.datasets?.[entry.dataset] : null;

  const navBtn = (dir) => {
    const id = dir < 0 ? ctx.prevId : ctx.nextId;
    const label = dir < 0 ? 'Poprzedni wpis (strzałka w lewo)' : 'Następny wpis (strzałka w prawo)';
    const title = dir < 0 ? 'Poprzedni wpis (←)' : 'Następny wpis (→)';
    const glyph = icon(dir < 0 ? 'chevronLeft' : 'chevronRight', { size: 20 });
    // No target: a disabled button (named, announced as unavailable), not an <a> without href.
    if (!id) return h('button', { type: 'button', class: 'btn btn--icon btn--ghost is-disabled', disabled: true, 'aria-label': label, title }, glyph);
    return h('a', {
      class: 'btn btn--icon btn--ghost', href: ctx.recordHref(id), 'aria-label': label, title,
      onClick: (e) => { e.preventDefault(); ctx.onOpen(id, { replace: true }); },
    }, glyph);
  };

  const applicantFact = entry.kind === 'zg' && !r.applicant
    ? fact('Inwestor', h('span', { class: 'muted' }, 'rejestr zgłoszeń nie podaje inwestora'))
    : h('div', null, h('dt', null, isPermit ? 'Inwestor' : 'Wnioskodawca'), h('dd', null,
      r.applicant || h('span', { class: 'muted' }, 'brak w źródle'),
      (r.applicant || '').toLowerCase().startsWith(APPLICANT_LABELS[entry.applicant].toLowerCase())
        ? null : h('span', { class: 'facts__sub' }, APPLICANT_LABELS[entry.applicant]),
      isPermit && entry.applicant === 'person' ? h('span', { class: 'facts__sub' }, 'GUNB nie publikuje danych osób fizycznych') : null));

  const facts = h('dl', { class: 'facts' },
    h('div', { class: (r.number || '').length > 18 ? 'facts__wide' : null },
      h('dt', null, NUMBER_LABEL[entry.kind] || 'Numer'), h('dd', { class: 'mono' }, r.number || h('span', { class: 'muted' }, 'brak w źródle'))),
    h('div', null, h('dt', null, DATE_LABEL[entry.kind] || 'Data'),
      h('dd', null, r.date ? formatDate(r.date) : h('span', { class: 'muted' }, r.date_raw ? `nieczytelna („${r.date_raw}”)` : 'brak w źródle'))),
    outcome ? fact('Rozstrzygnięcie', outcome.label) : null,
    procLabel ? h('div', null, h('dt', null, 'Wniosek o'), h('dd', null, own(PROCEDURE_ACC, r.procedure) || procLabel)) : null,
    isPermit ? permitFacts(entry, index) : null,
    applicantFact,
    issuer ? fact('Organ', issuer.label, { wide: (issuer.label || '').length > 28 }) : null,
    // District lists: the publication month says something the decision date does not. BAiPP: the period is the
    // date's month – shown only when the date itself is missing.
    r.period && !isPermit && (entry.dataset !== 'baipp' || !r.date) ? h('div', null,
      h('dt', null, entry.dataset === 'baipp' ? (entry.kind === 'ws' ? 'Miesiąc wszczęcia' : 'Miesiąc decyzji') : 'Opublikowano w zestawieniu'),
      h('dd', null, formatMonth(r.period, { capitalize: true }))) : null,
    r.area && dicts.areas?.[r.area] ? h('div', null, h('dt', null, 'Obszar'), h('dd', null,
      h('button', { type: 'button', class: 'link-btn', onClick: () => ctx.onFilter({ areas: [r.area], ...scopeKinds }) }, dicts.areas[r.area].label))) : null);

  const refusal = entry.outcome && OUTCOME_EMPHASIS[entry.outcome] === 'bad';
  // The WZ → permit story at a glance: permits on the same parcel/address dated after this decision.
  const laterPermits = isPermit ? 0 : relatedChain(index, entry).filter((e) => e.kind === 'pb' && e.ts > entry.ts).length;
  const scrollToSection = (sel) => {
    const t = host.querySelector(sel);
    if (!t) return;
    t.setAttribute('tabindex', '-1');
    t.scrollIntoView({ block: 'start', behavior: prefersReducedMotion() ? 'auto' : 'smooth' });
    t.focus({ preventScroll: true });
  };
  const toRelated = () => scrollToSection('#d-related');
  const toAsk = () => { host.querySelector('.ask__details')?.setAttribute('open', ''); scrollToSection('#d-ask'); };
  const listLabel = KIND_LIST_LABEL[entry.kind] || 'wpisy tego rodzaju';
  const leadByDataset = {
    district: 'Wpis pochodzi z pliku Excel opublikowanego przez Urząd Dzielnicy. W razie wątpliwości rozstrzyga oryginał.',
    baipp: 'Wpis pochodzi z ogólnomiejskiego zestawienia Biura Architektury i Planowania Przestrzennego (plik Excel) – wybraliśmy z niego wiersze dotyczące Pragi-Południe. W razie wątpliwości rozstrzyga oryginał.',
    rwdz: 'Wpis pochodzi z rejestru wniosków, decyzji i zgłoszeń prowadzonego przez Główny Urząd Nadzoru Budowlanego (otwarte dane). Rejestr nie podaje, czy decyzja była pozytywna, ani nie zawiera spraw w toku.',
  };

  const body = h('div', { class: 'detail__scroll' },
    h('div', { class: 'detail__intro' },
      h('div', { class: 'detail__badges' }, kindBadge(entry, dicts, { long: true }), outcomeBadge(entry, dicts, { all: true }),
        dataset && entry.dataset !== Object.keys(dicts.datasets || {})[0]
          ? h('span', { class: 'dbadge', title: dataset.label }, dataset.short || dataset.label) : null),
      h('h2', { class: 'detail__title', id: 'detail-title', tabindex: '-1' }, entryTitle(entry)),
      h('p', { class: 'detail__sub' }, [r.number, entryDate(entry)].filter(Boolean).join(' · ')),
      refusal ? h('p', { class: 'detail__refusal', role: 'note' }, icon('ban', { size: 16 }),
        h('span', null, h('strong', null, `${outcome?.label || 'Odmowa'}. `), REFUSAL_TEXT[entry.kind] || REFUSAL_TEXT.other,
          ' Od decyzji przysługuje odwołanie do Samorządowego Kolegium Odwoławczego, a wnioskodawca może złożyć nowy wniosek.')) : null,
      laterPermits ? h('p', { class: 'detail__later' }, icon('crane', { size: 15 }),
        h('button', { type: 'button', class: 'link-btn', onClick: toRelated },
          `Później na tej samej działce lub pod tym adresem: ${plural(laterPermits, POZWOLENIE_NA_BUDOWE)} – zobacz „Powiązane wpisy”`)) : null,
      entry.kind === 'ws' ? h('p', { class: 'detail__later' }, icon('inbox', { size: 15 }),
        h('button', { type: 'button', class: 'link-btn', onClick: toAsk },
          'Sprawa w toku – zapytaj urząd o wniosek i mapę terenu inwestycji')) : null,
      // Opened from a link or the related records while its kind is switched off: say so, one click switches it on.
      ctx.hiddenKind ? h('p', { class: 'notice notice--quiet detail__hidden', role: 'note' }, icon('info', { size: 15 }),
        h('span', null, `${cap(listLabel)} są teraz ukryte na liście wyników. `,
          ctx.onShowKind ? h('button', { type: 'button', class: 'link-btn', onClick: () => ctx.onShowKind() }, `Pokaż ${listLabel} na liście`) : null)) : null,
      (KIND_EXPLAINERS[entry.kind] || kd.description) ? h('p', { class: 'detail__explain' }, icon('info', { size: 15 }),
        h('span', null, KIND_EXPLAINERS[entry.kind] || kd.description, ' ', h('a', { href: '#/o-projekcie', class: 'link' }, 'Słowniczek pojęć'))) : null),
    section('Najważniejsze informacje', facts, { id: 'd-facts' }),
    section(entry.kind === 'ws' ? 'Inwestycja z wniosku' : isPermit ? 'Zamierzenie budowlane' : 'Streszczenie decyzji',
      r.investment ? h('p', { class: 'detail__text' }, r.investment) : h('p', { class: 'muted' }, 'Brak opisu w źródle.'), { id: 'd-inv' }),
    section('Lokalizacja', [
      h('p', { class: 'detail__addr' }, icon('pin', { size: 16 }), r.address?.display || h('span', { class: 'muted' }, 'Brak adresu w źródle')),
      rawAddressDiffers(r.address) && !isPermit ? h('p', { class: 'muted small' }, 'W źródle: ', h('span', { class: 'pre' }, r.address.raw.replace(/\n+/g, ' / ').replace(/\s{2,}/g, ' ').trim())) : null,
      r.address?.approximate ? h('p', { class: 'muted small' }, 'Adres opisowy („w rejonie”, „na wysokości”) – w źródle nie podano dokładnego adresu.') : null,
      h('p', { class: `precision precision--${precision}` }, icon(prec.icon, { size: 16 }),
        h('span', null, h('strong', null, precText.label), precText.note ? ` – ${precText.note}` : (precision === 'none' ? ' – nie udało się ustalić położenia na podstawie działki ani adresu.' : ''))),
      entry.hasGeo ? h('button', { type: 'button', class: 'btn btn--secondary btn--sm show-on-map', onClick: () => ctx.onShowOnMap(entry.id) }, icon('map', { size: 15 }), 'Pokaż na mapie') : null,
      h('h4', { class: 'dsec__sub' }, 'Działki ewidencyjne', (r.parcels || []).length ? h('span', { class: 'count' }, formatNumber(r.parcels.length)) : null),
      parcelsBlock(entry),
    ], { id: 'd-loc' }),
    tags.length ? section('Typ inwestycji', h('ul', { class: 'tag-list' }, tags.map((t) => h('li', null,
      h('button', { type: 'button', class: 'tag-btn', onClick: () => ctx.onFilter({ tags: [t], ...scopeKinds }), title: 'Pokaż wszystkie wpisy tego typu' },
        dicts.tags?.[t]?.label || t)))), { id: 'd-tags', extra: h('span', { class: 'dsec__hint' }, 'klasyfikacja automatyczna') }) : null,
    warnings.length ? section('Uwagi do danych', h('ul', { class: 'notes' }, warnings.map((w) => h('li', null, icon('info', { size: 15 }), h('span', null, w)))),
      { id: 'd-warn' }) : null,
    relatedSection(entry, index, ctx),
    askSection(entry, kd),
    section('Źródło', [
      h('p', { class: 'dsec__lead' }, leadByDataset[entry.dataset] || leadByDataset.district),
      provenance(entry, index),
    ], { id: 'd-src', iconName: 'sheet' }),
    h('footer', { class: 'detail__foot' },
      h('p', { class: 'muted small' }, 'Identyfikator wpisu: ', h('code', null, entry.id)),
      ISSUES_URL ? extLink(`${ISSUES_URL.replace(/\/$/, '')}/new?title=${encodeURIComponent(`Błąd w danych: ${entry.id}`)}&body=${encodeURIComponent(`Wpis: ${window.location.href}\n\nCo jest nie tak?\n`)}`, 'Zgłoś błąd w danych', 'alert', 'btn btn--ghost btn--sm') : null));

  const bar = detailBar(ctx, [
    // Position among the results; a record of a hidden kind is not among them at all (the note in the intro says why).
    ctx.hiddenKind && !ctx.position ? h('div', { class: 'detail__nav' }) : h('div', { class: 'detail__nav' },
      navBtn(-1),
      ctx.position
        ? h('span', { class: 'detail__pos' }, `${formatNumber(ctx.position.i + 1)} z ${formatNumber(ctx.position.n)}`)
        : h('span', { class: 'detail__pos', title: 'Ten wpis nie pasuje do bieżących filtrów' }, 'poza wynikami'),
      navBtn(1)),
    h('button', {
      type: 'button', class: 'btn btn--secondary btn--sm', title: 'Kopiuj link do tego wpisu',
      onClick: async () => {
        const ok = await copyText(window.location.href);
        toast(ok ? 'Skopiowano link do wpisu.' : 'Nie udało się skopiować linku.', { kind: ok ? 'success' : 'error' });
      },
    }, icon('link', { size: 15 }), h('span', { class: 'btn__label' }, 'Kopiuj link')),
    h('button', { type: 'button', class: 'btn btn--secondary btn--sm', title: 'Poproś urząd o pełne dokumenty tej sprawy', onClick: toAsk },
      icon('inbox', { size: 15 }), h('span', { class: 'btn__label' }, 'Zapytaj urząd'))]);

  replaceChildren(host, h('div', { class: `detail detail--${/^[a-z]+$/.test(entry.kind) ? entry.kind : 'other'}` }, bar, body));
  host.setAttribute('aria-labelledby', 'detail-title');
  return { title: entryTitle(entry), kindLabel: kd.short || entry.kind };
}

function detailBar(ctx, rest = []) {
  return h('header', { class: 'detail__bar' },
    // The accessible name starts with the visible word ("Wróć" on phones, "Zamknij" in the side panel).
    h('button', { type: 'button', class: 'btn btn--ghost btn--sm detail__close', onClick: () => ctx.onClose(), 'aria-label': ctx.modal ? 'Wróć – zamknij szczegóły (Esc)' : 'Zamknij szczegóły (Esc)' },
      icon(ctx.modal ? 'arrowLeft' : 'x', { size: 18 }), h('span', { class: 'detail__close-label' }, ctx.modal ? 'Wróć' : 'Zamknij')),
    rest);
}

/**
 * Permalink to a building permit opened before permits.json arrived: same layout, skeleton content
 * (`failed`: the register could not be loaded – say so and offer a retry instead of "not found").
 */
export function renderDetailLoading(host, id, ctx, { failed = false } = {}) {
  const intro = failed
    ? [h('h2', { class: 'empty__title', id: 'detail-title', tabindex: '-1' }, 'Nie udało się wczytać rejestru pozwoleń'),
      h('p', null, 'Wpis ', h('code', null, id), ' pochodzi z rejestru GUNB, którego nie udało się teraz pobrać.'),
      ctx.onRetryPermits ? h('button', { type: 'button', class: 'btn btn--secondary', onClick: () => ctx.onRetryPermits() }, icon('refresh', { size: 16 }), 'Spróbuj ponownie') : null]
    : [h('p', { class: 'chain-pending', role: 'status' }, h('span', { class: 'spinner', 'aria-hidden': 'true' }), 'Wczytywanie rejestru pozwoleń na budowę…'),
      h('h2', { class: 'detail__title sr-only', id: 'detail-title', tabindex: '-1' }, `Wczytywanie wpisu ${id}`),
      h('div', { class: 'sk sk--title sk--w70' }), h('div', { class: 'sk sk--line sk--w40' })];
  replaceChildren(host, h('div', { class: 'detail', 'aria-busy': failed ? null : 'true' },
    detailBar(ctx),
    h('div', { class: 'detail__scroll' },
      h('div', { class: failed ? 'empty' : 'detail__intro' }, intro),
      failed ? null : h('div', { class: 'dsec' }, h('div', { class: 'sk sk--line sk--w30' }), h('div', { class: 'sk sk--block' })),
      failed ? null : h('div', { class: 'dsec' }, h('div', { class: 'sk sk--line sk--w30' }), h('div', { class: 'sk sk--line sk--w90' }), h('div', { class: 'sk sk--line sk--w80' })))));
  host.setAttribute('aria-labelledby', 'detail-title');
}

/** "Record not found" state (stale permalink). */
export function renderDetailNotFound(host, id, ctx) {
  replaceChildren(host, h('div', { class: 'detail' },
    detailBar(ctx),
    h('div', { class: 'detail__scroll' },
      h('div', { class: 'empty' }, icon('search', { size: 40, class: 'empty__icon' }),
        h('h2', { class: 'empty__title', id: 'detail-title', tabindex: '-1' }, 'Nie znaleziono wpisu'),
        h('p', null, 'Wpis o identyfikatorze ', h('code', null, id), ' nie istnieje w bieżących danych. Mógł zostać poprawiony lub usunięty przy aktualizacji.'),
        h('p', null, `W bazie jest ${plural(ctx.index.entries.length, WPIS)}.`),
        h('button', { type: 'button', class: 'btn btn--secondary', onClick: () => ctx.onClose() }, 'Wróć do listy')))));
  host.setAttribute('aria-labelledby', 'detail-title');
}
