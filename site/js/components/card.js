/**
 * Result card (list item) and small shared record UI bits (kind badge, location-precision icon).
 */
import { h, highlighted } from '../dom.js';
import { icon, kindGlyph } from '../icons.js';
import { highlightSegments, highlightRanges, snippetAround } from '../search.js';
import { streetsOf } from '../data.js';
import { formatDate, formatMonth, formatNumber, formatDistance, truncate } from '../format.js';
import { APPLICANT_LABELS, PRECISION, OUTCOME_EMPHASIS } from '../copy.js';

/** Kind badge: shape glyph + short label (+ procedure for initiated proceedings). Text stays ink-coloured. */
export function kindBadge(entry, dicts, { long = false } = {}) {
  const k = entry.kind;
  const kd = dicts.kinds?.[k] || {};
  const label = long ? (kd.label || kd.short || k) : (kd.short || k);
  const proc = entry.rec.procedure;
  const procShort = k === 'ws' && proc && dicts.kinds?.[proc]?.short ? dicts.kinds[proc].short : null;
  return h('span', { class: `kbadge kbadge--${/^[a-z]+$/.test(k) ? k : 'other'}` },
    kindGlyph(k), h('span', null, label), procShort ? h('span', { class: 'kbadge__proc' }, `· ${procShort}`) : null);
}

/**
 * Outcome badge ("Odmowa", "Umorzenie postępowania"…) when the source states one. Positive outcomes get no
 * badge on cards (`all: false`): most sources do not state the outcome at all, so only exceptions stand out.
 */
export function outcomeBadge(entry, dicts, { all = false } = {}) {
  const o = entry.outcome;
  if (!o || (!all && OUTCOME_EMPHASIS[o] === 'good')) return null;
  const d = dicts.outcomes?.[o];
  const tone = OUTCOME_EMPHASIS[o] || 'neutral';
  return h('span', { class: `obadge obadge--${tone}`, title: d?.label || o },
    tone === 'bad' ? icon('ban', { size: 13 }) : null, h('span', null, d?.short || d?.label || o));
}

/** Short dataset marker for records that do not come from the primary (first) dataset, e.g. "BAiPP". */
export function datasetBadge(entry, dicts) {
  const keys = Object.keys(dicts.datasets || {});
  if (!entry.dataset || !keys.length || entry.dataset === keys[0] || entry.kind === 'pb' || entry.kind === 'zg') return null;
  const d = dicts.datasets[entry.dataset];
  return h('span', { class: 'dbadge', title: d?.label || entry.dataset }, d?.short || entry.dataset);
}

/** One line for permits: scope of works · building category · cubature ("Budowa · kat. XIII · 1 234 m³"). */
export function permitSummary(entry, dicts) {
  const p = entry.rec.permit;
  if (!p || typeof p !== 'object') return null;
  const parts = [
    p.scope ? (dicts.scopes?.[p.scope]?.label || p.scope_label || p.scope) : (p.scope_label || null),
    p.category ? `kat. ${p.category}` : null,
    p.single_family ? 'dom jednorodzinny' : null,
    typeof p.cubature === 'number' && p.cubature > 0 ? `${formatNumber(Math.round(p.cubature))} m³` : null,
  ].filter(Boolean);
  return parts.length ? parts.join(' · ') : null;
}

/** Location precision key: parcel | address | street | none. */
export function precisionOf(entry) {
  if (!entry.hasGeo) return 'none';
  const m = entry.rec.geo?.method;
  if (m === 'parcel' && entry.rec.geo?.conflict === true) return 'conflict';
  return PRECISION[m] ? m : 'street';
}

/**
 * Label + caveat for the detail panel. For street-level points the pipeline's note repeats the label
 * ("…; lokalizacja przybliżona – ulica"): that segment becomes the label's qualifier instead
 * ("Lokalizacja przybliżona (skrzyżowanie ulic)").
 * @returns {{label: string, note: string|null}}
 */
export function precisionDescription(entry) {
  const p = precisionOf(entry);
  let label = PRECISION[p].label;
  const parts = String(entry.rec.geo?.note || '').split(/;\s*/).map((x) => x.trim()).filter(Boolean);
  const rest = [];
  for (const part of parts) {
    const m = p === 'street' ? /^lokalizacja przybliżona\s*[–-]\s*(.+)$/i.exec(part) : null;
    if (m) label = `Lokalizacja przybliżona (${m[1]})`;
    // "Brak lokalizacji na mapie – … – nie pokazano na mapie": the label already says it.
    else if (p === 'none') {
      const x = part.replace(/\s*[–-]?\s*nie (?:pokazano|pokazujemy)(?: (?:jej|ich|go))? na mapie\.?$/i, '').trim();
      if (x) rest.push(x);
    }
    else rest.push(part);
  }
  // Optional pipeline field: how far the real site may be from a street-level point.
  const u = entry.rec.geo?.uncertainty_m;
  if (p === 'street' && typeof u === 'number' && u > 0) {
    rest.push(`miejsce może leżeć w promieniu ok. ${formatDistance(u < 1000 ? Math.round(u / 50) * 50 || 50 : Math.round(u / 100) * 100)} od punktu`);
  }
  return { label, note: rest.length ? rest.join('; ') : null };
}

/** Short words a register text in capitals keeps in lower case once sentence-cased ("Z GARAŻEM" → "z garażem"). */
const LOWER_WORDS = new Set(['a', 'i', 'o', 'u', 'w', 'z', 'we', 'ze', 'na', 'do', 'od', 'po', 'pod', 'nad', 'przy', 'dla', 'bez',
  'oraz', 'wraz', 'lub', 'albo', 'ul', 'al', 'pl', 'os', 'nr', 'dz', 'obr', 'wg', 'tj', 'm.in', 'itp', 'np']);
const ROMAN = /^[IVXLCDM]+$/;
const NAME_BEFORE = new Set(['ul', 'al', 'pl', 'os', 'ulicy', 'ulica', 'ulic', 'alei', 'aleja', 'placu', 'plac', 'rondo', 'osiedle', 'osiedlu']);

/**
 * Display-only sentence case for register texts written in capitals ("BUDYNEK MIESZKALNY WIELORODZINNY Z GARAŻEM"
 * → "Budynek mieszkalny wielorodzinny z garażem"). Short capitalised tokens (≤ 4 letters: "SN", "GPZ", "PCV") and roman
 * numerals stay as they are; texts with any lower-case letter are returned unchanged. Never used for names.
 */
export function displayCase(text) {
  const t = String(text ?? '');
  const letters = t.match(/\p{L}/gu) || [];
  if (letters.length < 12 || /\p{Ll}/u.test(t)) return t;
  let first = true;
  let name = false; // the word after "ul.", "al.", "os."… is a proper name
  return t.replace(/[\p{L}][\p{L}.]*/gu, (w) => {
    const bare = w.replace(/\.+$/, '');
    const low = bare.toLowerCase();
    let out;
    if (LOWER_WORDS.has(low)) out = w.toLowerCase();
    else if (ROMAN.test(bare) || bare.length <= 4) out = w;
    else out = w.toLowerCase();
    if ((first || name) && out === out.toLowerCase()) out = out[0].toUpperCase() + out.slice(1);
    first = false;
    name = NAME_BEFORE.has(low);
    return out;
  });
}

/** Cards show at most this many tag chips (+N); the detail lists all of them. */
export const CARD_TAGS = 3;

/**
 * Tags in card order: tags of the active tag filter first, then tags the search matches, then the rest (source order).
 * Pure; returns labels.
 */
export function cardTags(rec, dicts, { activeTags = [], tokens = [] } = {}) {
  const tags = (rec.tags || []).map((t, i) => {
    const label = dicts.tags?.[t]?.label || t;
    const rank = activeTags.includes(t) ? 0 : (tokens.length && highlightRanges(label, tokens).length ? 1 : 2);
    return { label, rank, i };
  });
  return tags.sort((a, b) => a.rank - b.rank || a.i - b.i).map((x) => x.label);
}

export function precisionIcon(entry) {
  const p = PRECISION[precisionOf(entry)];
  return h('span', { class: `loc loc--${precisionOf(entry)}`, title: p.label }, icon(p.icon, { size: 15 }), h('span', { class: 'sr-only' }, p.label));
}

/** Date label for an entry: exact date or reporting month. */
export function entryDate(entry) {
  if (entry.rec.date) return formatDate(entry.rec.date);
  if (entry.month) return formatMonth(entry.month);
  return 'brak daty';
}

/** Best title for a record: address, else a snippet of the investment, else the number. */
export function entryTitle(entry) {
  const r = entry.rec;
  return r.address?.display || (r.investment ? truncate(r.investment, 60) : null) || r.number || 'Wpis bez danych';
}

/** How many leading characters of a field a card shows before truncating it (see .card__inv / .card__applicant). */
const VISIBLE_CHARS = { title: 90, investment: 110, applicant: 38 };

/**
 * "Why did this match?" line for search results: when a query word has no visible hit on the card
 * (parcel numbers, the normalised street name of a misspelt address, the tail of a long applicant or
 * investment text), show a short highlighted excerpt of the field that matched.
 * @returns {{label: string, text: string}|null}
 */
export function matchContext(entry, tokens, dicts) {
  if (!tokens.length) return null;
  const r = entry.rec;
  const visible = [
    [r.address?.display, VISIBLE_CHARS.title], [r.number, Infinity],
    [r.investment, VISIBLE_CHARS.investment], [r.applicant, VISIBLE_CHARS.applicant],
    [r.area ? dicts.areas?.[r.area]?.label : null, Infinity],
    ...(r.tags || []).map((t) => [dicts.tags?.[t]?.label || t, Infinity]),
  ];
  const hidden = tokens.filter((t) => !visible.some(([text, limit]) => text && highlightRanges(text, [t]).some(([a]) => a < limit)));
  if (!hidden.length) return null;
  const parcels = (Array.isArray(r.parcels) ? r.parcels : []).map((p) => `dz. ${p.number} obr. ${p.obreb}`).join(', ');
  const permit = r.permit && typeof r.permit === 'object' ? r.permit : {};
  const candidates = [
    ['Nr w rejestrze GUNB', [permit.register_id, permit.case_sign].filter(Boolean).join(' · ')],
    ['Działki', parcels || r.parcels_raw],
    ['Identyfikator działki', (Array.isArray(r.parcels) ? r.parcels : []).map((p) => p.id).filter(Boolean).join(', ')],
    ['Ulica', streetsOf(r).join(', ')],
    ['Wnioskodawca', r.applicant],
    [r.kind === 'ws' ? 'Inwestycja' : 'Streszczenie', r.investment],
  ];
  for (const [label, text] of candidates) {
    if (!text) continue;
    const ranges = highlightRanges(String(text).replace(/\s+/g, ' '), hidden);
    if (!ranges.length) continue;
    return { label, text: snippetAround(String(text).replace(/\s+/g, ' '), ranges[0][0], ranges[0][1]) };
  }
  return null;
}

/**
 * Render a result card.
 * @param {object} entry index entry
 * @param {{dicts: object, tokens: string[], href: string, onOpen: (e: Event, entry: object) => void,
 *          onHover?: (id: string|null) => void, tag?: string, activeTags?: string[]}} opts
 *   activeTags: the tag filter (those tags are listed first, so a card never hides why it matched)
 */
export function renderCard(entry, { dicts, tokens = [], href, onOpen, onHover, tag = 'li', activeTags = [] }) {
  const r = entry.rec;
  const hl = (text) => highlighted(highlightSegments(text, tokens));
  const hasAddress = Boolean(r.address?.display);
  const tags = cardTags(r, dicts, { activeTags, tokens });
  const extraTags = Math.max(0, tags.length - CARD_TAGS);
  const isPermit = entry.kind === 'pb' || entry.kind === 'zg';
  const areaLabel = r.area ? (dicts.areas?.[r.area]?.label || null) : null;
  // Notifications (zg) never name the investor: say nothing rather than "Nieustalony".
  const applicantText = r.applicant || (entry.kind === 'zg' ? null : APPLICANT_LABELS[entry.applicant]);
  const context = matchContext(entry, tokens, dicts);
  const permitLine = permitSummary(entry, dicts);
  const card = h(tag, {
    class: 'card', 'data-id': entry.id, 'data-kind': entry.kind,
    onMouseenter: onHover ? () => onHover(entry.id) : null,
    onMouseleave: onHover ? () => onHover(null) : null,
  },
  h('div', { class: 'card__top' },
    kindBadge(entry, dicts),
    outcomeBadge(entry, dicts),
    datasetBadge(entry, dicts),
    h('time', { class: 'card__date', datetime: r.date || entry.month || null }, entryDate(entry)),
    precisionIcon(entry)),
  h('h3', { class: 'card__title' },
    h('a', {
      class: 'card__link', href,
      onClick: (e) => {
        if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey || e.button !== 0) return;
        onOpen(e, entry);
      },
      onFocus: onHover ? () => onHover(entry.id) : null,
      onBlur: onHover ? () => onHover(null) : null,
    }, hasAddress ? hl(r.address.display) : h('span', { class: 'card__title--muted' }, hl(entryTitle(entry))))),
  r.investment && hasAddress ? h('p', { class: 'card__inv' }, hl(isPermit ? displayCase(r.investment) : r.investment)) : null,
  permitLine ? h('p', { class: 'card__permit' }, icon('crane', { size: 14 }), h('span', null, permitLine)) : null,
  context ? h('p', { class: 'card__match' }, h('span', { class: 'card__match-label' }, `${context.label}: `), hl(context.text)) : null,
  h('div', { class: 'card__meta' },
    applicantText ? h('span', { class: 'card__applicant' }, icon(entry.applicant === 'person' ? 'user' : 'building', { size: 14 }),
      h('span', null, hl(applicantText))) : null,
    r.number ? h('span', { class: 'card__number' }, hl(r.number)) : null,
    areaLabel ? h('span', { class: 'card__area' }, icon('pin', { size: 14 }), hl(areaLabel)) : null),
  // Phones show the first CARD_TAGS chips and "+N" (CSS); wider screens show every chip.
  tags.length ? h('ul', { class: 'card__tags', 'aria-label': 'Typ inwestycji' },
    tags.map((t, i) => h('li', { class: i >= CARD_TAGS ? 'card__tag--extra' : null }, hl(t))),
    extraTags ? h('li', { class: 'card__tags-more' }, h('span', { 'aria-hidden': 'true' }, `+${extraTags}`),
      h('span', { class: 'sr-only' }, `i ${extraTags} więcej`)) : null) : null,
  (r.warnings || []).length ? h('span', { class: 'card__warn', title: 'Uwagi do jakości danych' }, icon('alert', { size: 13 }),
    h('span', { class: 'sr-only' }, 'Ma uwagi do jakości danych')) : null);
  return card;
}

/** Skeleton card for loading states. */
export function skeletonCard() {
  return h('li', { class: 'card card--skeleton', 'aria-hidden': 'true' },
    h('div', { class: 'sk sk--line sk--w30' }), h('div', { class: 'sk sk--title sk--w60' }),
    h('div', { class: 'sk sk--line sk--w90' }), h('div', { class: 'sk sk--line sk--w70' }));
}
