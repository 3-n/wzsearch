/**
 * Pure filtering, faceting and sorting over the prepared record index (see data.js).
 *
 * Semantics: OR within a facet group (e.g. two tags), AND across groups.
 * Facet counts for a group reflect all OTHER active filters ("what would I get
 * if I also ticked this?"). Computed in a single pass: an entry failing exactly
 * one group only contributes to that group's facet.
 *
 * DOM-free; unit-tested in tests/js/filters.test.mjs.
 */
import { addMonths } from './format.js';
import { scoreDoc } from './search.js';
import { DEFAULT_KINDS, effectiveKinds, isDefaultKinds, orderKinds } from './kinds.js';

/** Allowed radii (metres) for the "near me" filter. */
export const NEAR_RADII = [250, 500, 1000];

/** Relative period presets (relative to the newest month in the data). */
export const PERIOD_PRESETS = { '3m': 3, '12m': 12 };

/** A fresh, empty filter state. */
export function defaultFilters() {
  return {
    q: '',
    kinds: [...DEFAULT_KINDS], // explicit selection; pb/zg are opt-in (kinds.js)
    period: null, // '3m' | '12m' | null
    from: null, // 'YYYY-MM'
    to: null,
    tags: [],
    applicants: [], // person | organization | unknown
    areas: [],
    datasets: [], // records.json → datasets keys
    issuers: [], // issuers keys
    outcomes: [], // outcomes keys
    scopes: [], // permit_scopes keys (pb/zg only)
    categories: [], // permit_categories keys (pb/zg only)
    streets: [], // folded street keys
    geoOnly: false,
    bbox: null, // [west, south, east, north] — "only visible map area"
    near: null, // { lat, lon, r }
    file: null, // file_id
    sort: null, // null (auto) | newest | oldest | street | relevance
  };
}

/** Facet groups backed by a plain list of dictionary keys: filter key → entry field. */
export const LIST_GROUPS = {
  datasets: 'dataset',
  issuers: 'issuer',
  outcomes: 'outcome',
  scopes: 'scope',
  categories: 'category',
};

/** True when any narrowing filter (not sort) is active. A non-default kind selection counts as one. */
export function hasActiveFilters(f) {
  return Boolean(
    (f.q && f.q.trim()) || !isDefaultKinds(effectiveKinds(f.kinds)) || f.period || f.from || f.to || f.tags.length
      || f.applicants.length || f.areas.length || f.streets.length || f.geoOnly || f.bbox
      || f.near || f.file || Object.keys(LIST_GROUPS).some((k) => (f[k] || []).length),
  );
}

/** Resolve presets into a concrete inclusive month range {from, to}. */
export function resolvePeriod(f, latestMonth) {
  if (f.period && Object.hasOwn(PERIOD_PRESETS, f.period) && latestMonth) {
    return { from: addMonths(latestMonth, -(PERIOD_PRESETS[f.period] - 1)), to: latestMonth };
  }
  return { from: f.from || null, to: f.to || null };
}

/**
 * Month ranges of a relative preset per kind: each kind counts back from its own newest month (`latestByKind`), so
 * switching building permits on (register data reaching the current month) never moves the window of the planning
 * lists (published with a lag). Without `latestByKind`, or for an explicit range, every kind shares `base`.
 * @returns {{base: {from: string|null, to: string|null}, byKind: Object<string, {from: string, to: string}>|null}}
 */
export function periodRanges(f, latestMonth, latestByKind = null) {
  const base = resolvePeriod(f, latestMonth);
  if (!f.period || !Object.hasOwn(PERIOD_PRESETS, f.period) || !latestByKind) return { base, byKind: null };
  const byKind = {};
  for (const [k, m] of Object.entries(latestByKind)) if (m) byKind[k] = resolvePeriod(f, m);
  return { base, byKind: Object.keys(byKind).length ? byKind : null };
}

/** The distinct month ranges of a kind selection (one when every kind shares it), newest window last. */
export function periodSpans(f, latestMonth, latestByKind, kinds) {
  const { base, byKind } = periodRanges(f, latestMonth, latestByKind);
  if (!byKind) return [base];
  const out = [];
  for (const k of effectiveKinds(kinds)) {
    const r = byKind[k] || base;
    if (!out.some((x) => x.from === r.from && x.to === r.to)) out.push({ ...r, kinds: [] });
    out.find((x) => x.from === r.from && x.to === r.to).kinds.push(k);
  }
  return out.sort((a, b) => String(a.to).localeCompare(String(b.to)));
}

/** Great-circle distance in metres. */
export function distanceMeters(lat1, lon1, lat2, lon2) {
  const R = 6371008.8;
  const toRad = (d) => (d * Math.PI) / 180;
  const dLat = toRad(lat2 - lat1);
  const dLon = toRad(lon2 - lon1);
  const a = Math.sin(dLat / 2) ** 2 + Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLon / 2) ** 2;
  return 2 * R * Math.asin(Math.min(1, Math.sqrt(a)));
}

/** Is the entry's point inside [w, s, e, n]? */
export function inBbox(e, bbox) {
  if (!bbox || !e.hasGeo) return false;
  const [w, s, east, n] = bbox;
  return e.lon >= w && e.lon <= east && e.lat >= s && e.lat <= n;
}

/**
 * Build the list of active predicates.
 * Each predicate returns a truthy value when the entry passes; the 'q' predicate
 * returns the relevance score (> 0).
 * @param {object} f filter state
 * @param {{latestMonth?: string, tokens?: string[]}} ctx
 * @returns {{group: string, test: (e: object) => number|boolean}[]}
 */
export function buildPredicates(f, ctx = {}) {
  const preds = [];
  const tokens = ctx.tokens || [];
  if (tokens.length) preds.push({ group: 'q', test: (e) => scoreDoc(e.doc, tokens) });
  {
    const set = new Set(effectiveKinds(f.kinds));
    preds.push({ group: 'kind', test: (e) => set.has(e.kind) });
  }
  const { base, byKind } = periodRanges(f, ctx.latestMonth, ctx.latestByKind);
  if (base.from || base.to || byKind) {
    preds.push({
      group: 'period',
      test: (e) => {
        const { from, to } = (byKind && byKind[e.kind]) || base;
        return Boolean(e.month) && (!from || e.month >= from) && (!to || e.month <= to);
      },
    });
  }
  if (f.tags.length) {
    const set = new Set(f.tags);
    preds.push({ group: 'tag', test: (e) => e.tags.some((t) => set.has(t)) });
  }
  if (f.applicants.length) {
    const set = new Set(f.applicants);
    preds.push({ group: 'applicant', test: (e) => set.has(e.applicant) });
  }
  if (f.areas.length) {
    const set = new Set(f.areas);
    preds.push({ group: 'area', test: (e) => e.area != null && set.has(e.area) });
  }
  for (const [key, field] of Object.entries(LIST_GROUPS)) {
    const values = f[key] || [];
    if (!values.length) continue;
    const set = new Set(values);
    preds.push({ group: field, test: (e) => e[field] != null && set.has(e[field]) });
  }
  if (f.streets.length) {
    const set = new Set(f.streets);
    preds.push({ group: 'street', test: (e) => e.streetKeys.some((k) => set.has(k)) });
  }
  if (f.geoOnly) preds.push({ group: 'geo', test: (e) => e.hasGeo });
  if (f.bbox) preds.push({ group: 'bbox', test: (e) => inBbox(e, f.bbox) });
  if (f.near) preds.push({ group: 'near', test: (e) => nearHit(e, f.near, f.near.r) });
  if (f.file) preds.push({ group: 'file', test: (e) => e.fileIds.includes(f.file) });
  return preds;
}

/**
 * Is the entry within `r` metres of the point? A street-level location with a stated uncertainty (`geo.uncertainty_m`,
 * optional) may be near when its circle reaches the radius – such entries are flagged by `approx` on the card.
 */
export function nearHit(e, near, r) {
  if (!e.hasGeo || !near) return false;
  const d = distanceMeters(near.lat, near.lon, e.lat, e.lon);
  return d <= r || (e.uncertainty != null && d - e.uncertainty <= r);
}

function inc(obj, key, by = 1) {
  obj[key] = (obj[key] || 0) + by;
}

/**
 * Filter entries and compute facet counts in one pass.
 * @param {object[]} entries prepared index entries (data.js)
 * @param {object} f filter state
 * @param {{latestMonth?: string, tokens?: string[], viewBbox?: number[]}} ctx
 *   viewBbox = current map bounds, used for the "visible area" facet count even when inactive
 * @returns {{results: {entry: object, score: number}[], facets: object}}
 */
export function evaluate(entries, f, ctx = {}) {
  const preds = buildPredicates(f, ctx);
  const facets = {
    total: entries.length,
    kinds: {},
    months: {}, // month -> {kind: n}
    tags: {},
    applicants: {},
    areas: {},
    dataset: {},
    issuer: {},
    outcome: {},
    scope: {},
    category: {},
    streets: {},
    geo: 0,
    /** entries of the selected kinds (the denominator of "N z M") */
    scopeTotal: 0,
    bbox: 0,
    nearRadii: {},
    /** group -> number of results if that group's filter were removed */
    without: {},
  };
  const viewBbox = f.bbox || ctx.viewBbox || null;
  const near = f.near;
  const results = [];
  const kindSet = new Set(effectiveKinds(f.kinds));
  const listFields = Object.values(LIST_GROUPS);
  for (const e of entries) {
    if (kindSet.has(e.kind)) facets.scopeTotal += 1;
    let failed = null;
    let nFailed = 0;
    let score = 1;
    for (const p of preds) {
      const ok = p.test(e);
      if (!ok) {
        nFailed += 1;
        failed = p.group;
        if (nFailed > 1) break;
      } else if (p.group === 'q') {
        score = ok;
      }
    }
    if (nFailed > 1) continue;
    if (nFailed === 0) results.push({ entry: e, score });
    const all = nFailed === 0;
    if (all) {
      for (const p of preds) inc(facets.without, p.group);
    } else {
      inc(facets.without, failed);
    }
    if (all || failed === 'kind') inc(facets.kinds, e.kind);
    if ((all || failed === 'period') && e.month) {
      const m = facets.months[e.month] || (facets.months[e.month] = {});
      inc(m, e.kind);
    }
    if (all || failed === 'tag') for (const t of e.tags) inc(facets.tags, t);
    if (all || failed === 'applicant') inc(facets.applicants, e.applicant);
    if ((all || failed === 'area') && e.area != null) inc(facets.areas, e.area);
    for (const field of listFields) if ((all || failed === field) && e[field] != null) inc(facets[field], e[field]);
    if (all || failed === 'street') for (const k of e.streetKeys) inc(facets.streets, k);
    if ((all || failed === 'geo') && e.hasGeo) facets.geo += 1;
    if ((all || failed === 'bbox') && viewBbox && inBbox(e, viewBbox)) facets.bbox += 1;
    if ((all || failed === 'near') && near && e.hasGeo) {
      for (const r of NEAR_RADII) if (nearHit(e, near, r)) inc(facets.nearRadii, r);
    }
  }
  return { results, facets };
}

/**
 * Which facet options exist at all for a kind selection (ignoring every other filter): used to show only
 * options that can match ("Źródło danych" with one dataset is hidden, "Zakres robót" only with permits).
 * @returns {{dataset: object, issuer: object, outcome: object, scope: object, category: object, tags: object}}
 *   field → {value: count}
 */
export function availableOptions(entries, kinds) {
  const set = new Set(effectiveKinds(kinds));
  const out = { tags: {} };
  for (const field of Object.values(LIST_GROUPS)) out[field] = {};
  for (const e of entries) {
    if (!set.has(e.kind)) continue;
    for (const field of Object.values(LIST_GROUPS)) if (e[field] != null) inc(out[field], e[field]);
    for (const t of e.tags) inc(out.tags, t);
  }
  return out;
}

/**
 * Do two fields split the entries of these kinds into the same groups (a one-to-one mapping of values)?
 * E.g. with the planning kinds only, "Organ" (district office / city bureau) repeats "Źródło danych"
 * (district list / BAiPP list) exactly – the panel then shows just one of them.
 */
export function sameSplit(entries, kinds, fieldA, fieldB) {
  const set = new Set(effectiveKinds(kinds));
  const ab = new Map();
  const ba = new Map();
  for (const e of entries) {
    if (!set.has(e.kind)) continue;
    const a = e[fieldA] ?? null;
    const b = e[fieldB] ?? null;
    if ((ab.has(a) && ab.get(a) !== b) || (ba.has(b) && ba.get(b) !== a)) return false;
    ab.set(a, b);
    ba.set(b, a);
  }
  return true;
}

/**
 * Outcome coverage for the "Rozstrzygnięcie" filter: among the WZ/CP decisions matching every OTHER filter, how many
 * state an outcome at all (only the BAiPP lists do; the district lists never say). Pure.
 * @returns {{decisions: number, known: number, unknown: number}}
 */
export function outcomeCoverage(entries, f, ctx = {}) {
  const base = evaluate(entries, { ...f, outcomes: [] }, ctx).results
    .filter((r) => r.entry.kind === 'wz' || r.entry.kind === 'cp');
  const known = base.filter((r) => r.entry.outcome).length;
  return { decisions: base.length, known, unknown: base.length - known };
}

/**
 * Drop filter values the data does not know (a stale or hand-edited link: a renamed tag, a replaced file, a typo),
 * so the page degrades to the remaining filters instead of showing "no results" with a raw-slug chip. Only
 * dictionaries that exist are checked (old data without e.g. `outcomes` keeps what the URL says). Street keys are
 * kept: a street may be known only from the lazily loaded permits. Pure; returns the same object when nothing changed.
 * @param {object} f filter state
 * @param {{kindCodes?: string[], dicts?: object, filesById?: Map<string, object>}} ctx
 */
export function sanitizeFilters(f, ctx = {}) {
  const dicts = ctx.dicts || {};
  const known = (dict) => (dict && typeof dict === 'object' && Object.keys(dict).length ? (v) => Object.hasOwn(dict, v) : null);
  const out = { ...f };
  let changed = false;
  const keep = (key, test) => {
    if (!test || !Array.isArray(f[key]) || !f[key].length) return;
    const next = f[key].filter(test);
    if (next.length !== f[key].length) { out[key] = next; changed = true; }
  };
  if (Array.isArray(ctx.kindCodes) && ctx.kindCodes.length) {
    const kinds = effectiveKinds(f.kinds).filter((k) => ctx.kindCodes.includes(k));
    if (kinds.length !== effectiveKinds(f.kinds).length) { out.kinds = kinds.length ? orderKinds(kinds) : [...DEFAULT_KINDS]; changed = true; }
  }
  keep('tags', known(dicts.tags));
  keep('areas', known(dicts.areas));
  keep('datasets', known(dicts.datasets));
  keep('issuers', known(dicts.issuers));
  keep('outcomes', known(dicts.outcomes));
  keep('scopes', known(dicts.scopes));
  keep('categories', known(dicts.categories));
  if (f.file && ctx.filesById && ctx.filesById.size && !ctx.filesById.has(f.file)) { out.file = null; changed = true; }
  return changed ? out : f;
}

/** Sort mode actually applied: `null` means relevance while searching, newest otherwise. */
export function effectiveSort(sort, hasQuery) {
  if (!sort) return hasQuery ? 'relevance' : 'newest';
  if (sort === 'relevance' && !hasQuery) return 'newest';
  return sort;
}

const collator = new Intl.Collator('pl', { sensitivity: 'base', numeric: true });

function cmpNewest(a, b) {
  if (a.entry.ts !== b.entry.ts) return a.entry.ts < b.entry.ts ? 1 : -1;
  return a.entry.id < b.entry.id ? 1 : a.entry.id > b.entry.id ? -1 : 0;
}

function cmpStreet(a, b) {
  const sa = a.entry.streetSort;
  const sb = b.entry.streetSort;
  if (!sa && !sb) return cmpNewest(a, b);
  if (!sa) return 1;
  if (!sb) return -1;
  const c = collator.compare(sa, sb);
  if (c) return c;
  const na = a.entry.houseNumber;
  const nb = b.entry.houseNumber;
  if (na !== nb) {
    if (!na) return -1;
    if (!nb) return 1;
    const cn = collator.compare(na, nb);
    if (cn) return cn;
  }
  return cmpNewest(a, b);
}

/**
 * Sort results in place and return them.
 * @param {{entry: object, score: number}[]} results
 * @param {string} mode newest | oldest | street | relevance
 */
export function sortResults(results, mode) {
  switch (mode) {
    case 'oldest':
      return results.sort((a, b) => -cmpNewest(a, b));
    case 'street':
      return results.sort(cmpStreet);
    case 'relevance':
      return results.sort((a, b) => b.score - a.score || cmpNewest(a, b));
    case 'newest':
    default:
      return results.sort(cmpNewest);
  }
}
