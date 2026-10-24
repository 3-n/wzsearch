/**
 * Data loading (fetch) and index building (pure).
 * Reads ONLY the files described in docs/DATA_MODEL.md:
 *   data/records.json, data/sources.json (required),
 *   data/parcels.geojson, data/areas.geojson (optional, loaded after first paint),
 *   data/permits.json + data/parcels-permits.geojson (optional, loaded lazily – see lazy.js).
 */
import { fold, buildSearchDoc } from './search.js';
import { KIND_ORDER } from './kinds.js';
import { pluralForm } from './format.js';

/**
 * Strip honorific/type prefixes so "gen. Fieldorfa" sorts under F, "al. Stanów…" under S. An abbreviation needs its
 * dot, a full word (or an undotted "ul"/"al"/"pl") a space after it – "Algierska", "Aldony", "Genewska", "Księcia…"
 * and "Plac…ówka" are names, not prefixes.
 */
const STREET_PREFIX = /^(?:(?:ul|al|gen|ks|św|pl|marsz|prof|płk)\.\s*|(?:ulica|aleja|aleje|plac|rondo|bulwar|ul|al|pl)\s+)/iu;

export function streetSortKey(street) {
  if (!street) return null;
  let s = String(street).trim();
  let prev;
  do {
    prev = s;
    s = s.replace(STREET_PREFIX, '');
  } while (s !== prev && s);
  return s.replace(/^[^\p{L}\p{N}]+/u, '') || String(street).trim();
}

/** Folded key used to group spellings of the same street ("Grochowska" ≡ "grochowska"). */
export function streetKey(street) {
  if (!street) return null;
  const k = fold(streetSortKey(street)).replace(/[^\p{L}\p{N} ]+/gu, ' ').replace(/\s+/g, ' ').trim();
  return k || null;
}

/** Street names of a record: the main street plus every part of an intersection/list. */
export function streetsOf(rec) {
  const a = rec?.address || {};
  const out = [];
  for (const name of [a.street, ...(Array.isArray(a.parts) ? a.parts.map((p) => p && p.street) : [])]) {
    if (typeof name === 'string' && name.trim() && !out.includes(name.trim())) out.push(name.trim());
  }
  return out;
}

function isNum(v) {
  return typeof v === 'number' && Number.isFinite(v);
}

const obj = (v) => (v && typeof v === 'object' && !Array.isArray(v) ? v : {});
const str = (v) => (typeof v === 'string' && v ? v : null);
const MONTH = /^\d{4}-\d{2}$/;

/** Dataset of a source page or file: its own `source`, else the source of its first linking page. */
export function datasetOf(item, pagesById) {
  if (!item) return null;
  if (typeof item.source === 'string' && item.source) return item.source;
  const pid = Array.isArray(item.page_ids) ? item.page_ids[0] : null;
  const page = pid && pagesById ? pagesById.get(pid) : null;
  if (page && typeof page.source === 'string' && page.source) return page.source;
  return 'district';
}

/**
 * Prepare one index entry for a record (folded search document, month, geo flags, facet keys).
 * @param {object} rec Record (DATA_MODEL.md)
 * @param {object} dicts dictionaries (buildIndex)
 */
function makeEntry(rec, dicts) {
  const date = typeof rec.date === 'string' ? rec.date : null;
  const month = (date && /^\d{4}-\d{2}/.test(date) ? date.slice(0, 7) : null)
    || (typeof rec.period === 'string' && MONTH.test(rec.period) ? rec.period : null);
  const geo = rec.geo || {};
  const hasGeo = isNum(geo.lat) && isNum(geo.lon);
  const street = rec.address?.street || null;
  const streetKeys = [];
  for (const name of streetsOf(rec)) {
    const k = streetKey(name);
    if (k && !streetKeys.includes(k)) streetKeys.push(k);
  }
  const sources = Array.isArray(rec.sources) ? rec.sources : [];
  const applicant = ['person', 'organization'].includes(rec.applicant_type) ? rec.applicant_type : 'unknown';
  const permit = obj(rec.permit);
  return {
    id: rec.id,
    rec,
    kind: rec.kind,
    month,
    ts: date || (month ? `${month}-00` : '0000-00-00'),
    tags: Array.isArray(rec.tags) ? rec.tags : [],
    applicant,
    area: rec.area ?? null,
    dataset: str(rec.dataset),
    issuer: str(rec.issuer),
    outcome: str(rec.outcome),
    scope: str(permit.scope),
    category: str(permit.category),
    streetKey: streetKey(street),
    streetKeys,
    streetSort: street ? streetSortKey(street) : (rec.address?.display || null),
    houseNumber: rec.address?.number || null,
    hasGeo,
    // Street-level points: how far the real site may be (metres; optional pipeline field, null when not stated).
    uncertainty: hasGeo && isNum(geo.uncertainty_m) && geo.uncertainty_m > 0 ? geo.uncertainty_m : null,
    lat: hasGeo ? geo.lat : null,
    lon: hasGeo ? geo.lon : null,
    // Hollow marker: not placed by a parcel, or placed by parcels that lie far from the stated exact address
    // (geo.conflict, set by the pipeline when the address and the parcels disagree – see DATA_MODEL.md).
    approx: hasGeo && (geo.method !== 'parcel' || geo.conflict === true),
    conflict: hasGeo && geo.conflict === true,
    fileIds: [...new Set(sources.map((s) => s.file_id).filter(Boolean))],
    doc: buildSearchDoc(rec, dicts),
  };
}

/**
 * Add entries to the index (records.json at build time, permits.json later). Mutates `index`.
 * @param {Map<string, object>|null} prepared entries already made by prepareEntries() (by record id)
 */
function addEntries(index, records, prepared = null) {
  const added = [];
  for (const rec of records) {
    if (!rec || !rec.id || index.byId.has(rec.id)) continue;
    const e = (prepared && prepared.get(rec.id)) || makeEntry(rec, index.dicts);
    index.entries.push(e);
    index.byId.set(e.id, e);
    added.push(e);
    for (const name of streetsOf(rec)) {
      const k = streetKey(name);
      if (!k) continue;
      if (!index.streetSpellings.has(k)) index.streetSpellings.set(k, new Map());
      const m = index.streetSpellings.get(k);
      m.set(name, (m.get(name) || 0) + 1);
    }
    if (e.month && e.kind) {
      const b = index.kindMonths[e.kind] || (index.kindMonths[e.kind] = { min: e.month, max: e.month });
      if (e.month < b.min) b.min = e.month;
      if (e.month > b.max) b.max = e.month;
    }
  }
  rebuildStreets(index);
  return added;
}

/** Pick the most frequent spelling as the label of each street. */
function rebuildStreets(index) {
  index.streets.clear();
  for (const [key, spellings] of index.streetSpellings) {
    let best = null;
    let bestN = -1;
    let total = 0;
    for (const [label, n] of spellings) {
      total += n;
      if (n > bestN) { best = label; bestN = n; }
    }
    index.streets.set(key, { key, label: best, count: total });
  }
}

/**
 * Turn records.json + sources.json into an index the UI can query instantly.
 * Robust to missing/null fields everywhere.
 * @param {object} recordsDoc parsed records.json
 * @param {object} sourcesDoc parsed sources.json
 */
export function buildIndex(recordsDoc, sourcesDoc) {
  const records = Array.isArray(recordsDoc?.records) ? recordsDoc.records.filter((r) => r && r.id) : [];
  const kinds = obj(recordsDoc?.kinds);
  const dicts = {
    kinds,
    tags: obj(recordsDoc?.tags),
    areas: obj(recordsDoc?.areas),
    datasets: obj(recordsDoc?.datasets),
    issuers: obj(recordsDoc?.issuers),
    outcomes: obj(recordsDoc?.outcomes),
    scopes: obj(recordsDoc?.permit_scopes),
    categories: obj(recordsDoc?.permit_categories),
  };
  const countsByKind = {};
  for (const [k, n] of Object.entries(obj(recordsDoc?.counts_by_kind))) if (Number.isFinite(n)) countsByKind[k] = n;

  const pages = Array.isArray(sourcesDoc?.pages) ? sourcesDoc.pages : [];
  const files = Array.isArray(sourcesDoc?.files) ? sourcesDoc.files : [];
  const pagesById = new Map(pages.map((p) => [p.page_id, p]));
  const filesById = new Map(files.map((f) => [f.file_id, f]));

  const index = {
    meta: {
      generatedAt: recordsDoc?.generated_at || sourcesDoc?.generated_at || null,
      sourceIndexUrl: recordsDoc?.source_index_url || sourcesDoc?.index_url || null,
      fixture: Boolean(recordsDoc?.fixture || sourcesDoc?.fixture),
      count: 0,
    },
    dicts,
    kindCodes: [],
    countsByKind,
    entries: [],
    byId: new Map(),
    streets: new Map(),
    streetSpellings: new Map(),
    kindMonths: {},
    minMonth: null,
    maxMonth: null,
    pagesMaxMonth: null,
    baseKinds: [],
    permitsLoaded: false,
    permitsMeta: null,
    pages,
    files,
    pagesById,
    filesById,
  };
  addEntries(index, records);
  index.meta.count = index.entries.length;
  index.baseKinds = Object.keys(index.kindMonths);
  // Kinds: every kind of the dictionary (incl. opt-in kinds known only from counts_by_kind) plus any in the data.
  index.kindCodes = orderedKinds([...Object.keys(kinds), ...Object.keys(index.kindMonths)]);

  // The newest reporting month also considers the monthly source pages (a month may have 0 entries).
  for (const p of pages) {
    if (p.period && MONTH.test(p.period) && (!index.pagesMaxMonth || p.period > index.pagesMaxMonth)) index.pagesMaxMonth = p.period;
  }
  const b = monthBounds(index, index.baseKinds);
  index.minMonth = b.min;
  index.maxMonth = b.max;
  return index;
}

function orderedKinds(codes) {
  const set = [...new Set(codes)];
  return [...KIND_ORDER.filter((k) => set.includes(k)), ...set.filter((k) => !KIND_ORDER.includes(k)).sort()];
}

/**
 * Make the index entries of many records in slices, yielding to the browser between slices, so that merging
 * permits.json (≈ 2,600 records: ~70 ms of search-document building on a laptop, ~280 ms on a slow phone)
 * never blocks input or scrolling in one long task. Pure apart from the pauses; the index is not touched, so
 * the UI never sees a half-merged register. Pass the result to addPermits().
 * @param {object[]} records
 * @param {object} dicts index.dicts
 * @param {{slice?: number, pause?: () => Promise<void>}} [opts]
 * @returns {Promise<Map<string, object>>} entries by record id
 */
export async function prepareEntries(records, dicts, { slice = 250, pause = yieldToBrowser } = {}) {
  const out = new Map();
  const list = Array.isArray(records) ? records : [];
  for (let i = 0; i < list.length; i += slice) {
    for (const rec of list.slice(i, i + slice)) if (rec && rec.id && !out.has(rec.id)) out.set(rec.id, makeEntry(rec, dicts));
    if (i + slice < list.length) await pause();
  }
  return out;
}

/** Let the browser handle input and paint (scheduler.yield where available, else a macrotask). */
function yieldToBrowser() {
  if (typeof globalThis.scheduler?.yield === 'function') return globalThis.scheduler.yield();
  return new Promise((resolve) => setTimeout(resolve, 0));
}

/**
 * Add the records of permits.json (pb/zg) to an index built from records.json. Mutates `index`;
 * idempotent (records already present are skipped). Returns the new entries.
 * @param {Map<string, object>} [prepared] entries made beforehand by prepareEntries()
 */
export function addPermits(index, permitsDoc, prepared = null) {
  const records = Array.isArray(permitsDoc?.records) ? permitsDoc.records.filter((r) => r && r.id) : [];
  const added = addEntries(index, records, prepared);
  index.kindCodes = orderedKinds([...index.kindCodes, ...added.map((e) => e.kind).filter(Boolean)]);
  index.permitsLoaded = true;
  index.permitsMeta = { generatedAt: permitsDoc?.generated_at || null, count: records.length };
  return added;
}

/**
 * Month axis for a kind selection: earliest and latest month of the entries of those kinds
 * (the district's monthly pages extend the latest month for the planning kinds).
 * @returns {{min: string|null, max: string|null}}
 */
export function monthBounds(index, kinds) {
  let min = null;
  let max = null;
  const list = Array.isArray(kinds) && kinds.length ? kinds : Object.keys(index.kindMonths);
  for (const k of list) {
    const b = index.kindMonths[k];
    if (!b) continue;
    if (!min || b.min < min) min = b.min;
    if (!max || b.max > max) max = b.max;
  }
  if (index.pagesMaxMonth && list.some((k) => index.baseKinds.includes(k)) && (!max || index.pagesMaxMonth > max)) {
    max = index.pagesMaxMonth;
  }
  return { min, max };
}

/** Dataset of a source file (sources.json). */
export function fileDataset(index, file) {
  return datasetOf(file, index.pagesById);
}

/**
 * Records related to `entry`: the explicit `related` ids plus the entry itself,
 * sorted chronologically. Unknown ids (e.g. permits not loaded yet) are skipped.
 */
export function relatedChain(index, entry) {
  const ids = new Set([entry.id, ...((entry.rec.related || []).filter((id) => typeof id === 'string'))]);
  const out = [];
  for (const id of ids) {
    const e = index.byId.get(id);
    if (e) out.push(e);
  }
  return out.sort((a, b) => (a.ts < b.ts ? -1 : a.ts > b.ts ? 1 : a.id.localeCompare(b.id)));
}

/** "street key|house number" pairs of every street the address names (for "same address" reasons). */
function addressKeys(rec) {
  const a = rec?.address || {};
  const parts = Array.isArray(a.parts) && a.parts.length ? a.parts : [{ street: a.street, number: a.number }];
  const out = new Set();
  for (const p of parts) {
    const k = streetKey(p?.street);
    const nums = [p?.number, ...(Array.isArray(p?.numbers) ? p.numbers : [])].filter(Boolean);
    for (const n of nums) if (k) out.add(`${k}|${String(n).toLowerCase()}`);
  }
  return out;
}

/** Why two records are related: shared parcel(s) or the same address (null when it cannot be told). */
export function relationReason(current, other) {
  const mine = new Set((current.parcels || []).map((p) => p?.id).filter(Boolean));
  const shared = (other.parcels || []).filter((p) => p?.id && mine.has(p.id));
  if (shared.length === 1) return `wspólna działka ${shared[0].number} (obr. ${shared[0].obreb})`;
  if (shared.length > 1) {
    const nums = shared.slice(0, 3).map((p) => p.number).join(', ');
    const obreby = new Set(shared.map((p) => p.obreb));
    const n = shared.length - 3;
    const more = n > 0 ? ` i ${n} ${pluralForm(n, ['inna', 'inne', 'innych'])}` : '';
    return `wspólne działki ${nums}${more}${obreby.size === 1 && shared[0].obreb ? ` (obr. ${shared[0].obreb})` : ''}`;
  }
  const a = addressKeys(current);
  for (const k of addressKeys(other)) if (a.has(k)) return 'ten sam adres';
  return null;
}

/** "Grochowska 300", "ul. Grochowska 12a", "Grochowska 7/9": street part + house number. */
const ADDRESS_QUERY = /^(.*?\D)\s+(\d+)[a-z]?(?:\/\d+[a-z]?)?$/i;
/** A neighbouring house number further away than this is no longer "near address X". */
const NEAREST_NUMBER_MAX = 20;

/**
 * "What is near address X?": for a query of a known street + house number, the located record on that street whose
 * house number is closest (same side of the street – parity – on ties). Street-midpoint locations do not count
 * (they are not at any house). Pure; null when the query is not an address or nothing is close enough.
 * @returns {{entry: object, lat: number, lon: number, number: string}|null}
 */
export function nearestAddressPoint(index, q) {
  const m = ADDRESS_QUERY.exec(String(q || '').trim());
  if (!m) return null;
  const key = streetKey(m[1]);
  if (!key || !index.streets.has(key)) return null;
  const target = Number(m[2]);
  let best = null;
  let bestScore = Infinity;
  for (const e of index.entries) {
    if (!e.hasGeo || e.rec.geo?.method === 'street' || !e.streetKeys.includes(key)) continue;
    const n = parseInt(e.houseNumber, 10);
    if (!Number.isFinite(n)) continue;
    const d = Math.abs(n - target);
    // Same parity wins a tie (the same side of the street); then the parcel-located record, then the newest.
    const score = d * 4 + ((n - target) % 2 ? 2 : 0) + (e.approx ? 1 : 0);
    if (score < bestScore || (score === bestScore && best && e.ts > best.ts)) { best = e; bestScore = score; }
  }
  if (!best || Math.abs(parseInt(best.houseNumber, 10) - target) > NEAREST_NUMBER_MAX) return null;
  return { entry: best, lat: best.lat, lon: best.lon, number: String(best.houseNumber) };
}

class DataError extends Error {
  constructor(message, { url, status } = {}) {
    super(message);
    this.name = 'DataError';
    this.url = url;
    this.status = status;
  }
}

/**
 * The request index.html started early for this file (window.__wzEarly, see its inline script), used once: a retry
 * fetches again. Replaces <link rel=preload as=fetch>, which ignored `cache: 'no-cache'` (stale data after a deploy)
 * and which WebKit did not reuse (every file downloaded twice).
 */
function takeEarly(url) {
  const early = globalThis.__wzEarly;
  if (!early || !early[url]) return null;
  const p = early[url];
  delete early[url];
  return p;
}

async function fetchJson(url, { optional = false } = {}) {
  let res;
  try {
    res = await (takeEarly(url) || fetch(url, { cache: 'no-cache' }));
  } catch (err) {
    if (optional) return null;
    throw new DataError(`Brak połączenia przy pobieraniu ${url}`, { url });
  }
  if (!res.ok) {
    if (optional) return null;
    throw new DataError(`Serwer zwrócił błąd ${res.status} dla ${url}`, { url, status: res.status });
  }
  let doc = null;
  try {
    const text = await res.text();
    doc = text.trim() ? JSON.parse(text) : null;
  } catch {
    doc = null;
  }
  if (doc == null && !optional) throw new DataError(`Pusty lub niepoprawny plik ${url}`, { url });
  return doc;
}

/** Load the required data files and build the index. */
export async function loadIndex(base = 'data/') {
  const [recordsDoc, sourcesDoc] = await Promise.all([
    fetchJson(`${base}records.json`),
    fetchJson(`${base}sources.json`),
  ]);
  return buildIndex(recordsDoc, sourcesDoc);
}

/** Optional GeoJSON layers; resolve to null when absent/empty/invalid. */
export async function loadGeo(name, base = 'data/') {
  const doc = await fetchJson(`${base}${name}`, { optional: true });
  if (!doc || !Array.isArray(doc.features) || !doc.features.length) return null;
  return doc;
}

/**
 * The permits layer: permits.json (required for this layer – rejects when missing) and its parcel
 * outlines (optional). Both requests start together.
 * @returns {Promise<{doc: object, parcels: object|null}>}
 */
export async function loadPermits(base = 'data/') {
  const [doc, parcels] = await Promise.all([
    fetchJson(`${base}permits.json`),
    loadGeo('parcels-permits.geojson', base),
  ]);
  return { doc, parcels };
}

/** Check whether an optional download exists (HEAD, falling back to GET). */
export async function exists(url) {
  try {
    let res = await fetch(url, { method: 'HEAD', cache: 'no-cache' });
    if (res.status === 405 || res.status === 501) res = await fetch(url, { cache: 'no-cache' });
    return res.ok;
  } catch {
    return false;
  }
}

export { DataError };
