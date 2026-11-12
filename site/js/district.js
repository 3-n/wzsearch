/**
 * The district this page shows (docs/plans/all-districts.md §1). A deployment with data/districts.json has one
 * data shard per Warsaw district (data/d/<slug>/…); the page loads exactly one of them, chosen at boot from the
 * `dz` hash parameter, the district code of a record permalink (wz-bem-2026-1 → Bemowo), or Praga-Południe (a link
 * without `dz` – every link shared before the other districts existed – always means Praga-Południe). Switching
 * district reloads the page (draft). Without data/districts.json (the single-district deployment) everything stays
 * as before: Praga-Południe, data/.
 *
 * "Cała Warszawa" (`dz=warszawa`, districts.json's `city` entry) is one more scope: the planning records of every
 * district in a lighter shape (data/warszawa/, pipeline/city_index.py), no permits; a record opens in its district.
 *
 * Pure helpers plus one module-level "current district" that the views read for their copy.
 */
import { MAP_CENTER, MAP_ZOOM } from './config.js';
import { formatMonth, formatNumber } from './format.js';

export const DEFAULT_SLUG = 'praga-poludnie';
export const CITY_SLUG = 'warszawa';
const SLUG = /^[a-z-]{2,32}$/;

/** Praga-Południe, as the single-district deployment knows it (also the fallback for missing fields). */
export const LEGACY = Object.freeze({
  slug: DEFAULT_SLUG,
  name: 'Praga-Południe',
  genitive: 'Pragi-Południe',
  locative: 'na Pradze-Południe',
  instrumental: 'Pragą-Południe',
  code: '',
  status: 'enabled',
  note: null,
  entry_url: 'https://pragapld.um.warszawa.pl/informacja-o-wszczetych-postepowaniach-oraz-wydanych-decyzjach-administracyjnych',
  office: 'Urząd Dzielnicy Praga-Południe m.st. Warszawy – Wydział Architektury i Budownictwa',
  available: true,
  counts_by_kind: {},
  bbox: null,
});

let current = LEGACY;
let all = [];
let city = null;

/** The district shown by this page. */
export function currentDistrict() {
  return current;
}

/** Every district of the deployment (empty in a single-district deployment). */
export function allDistricts() {
  return all;
}

/** True when the deployment has several districts (data/districts.json lists more than one). */
export function isCity() {
  return all.length > 1;
}

/** The "Cała Warszawa" entry of districts.json (null without a city index). */
export function cityEntry() {
  return city;
}

/** True when the page shows the whole city ("Cała Warszawa") rather than one district. */
export function isCityMode() {
  return current.city === true;
}

/** The district a record belongs to (city mode: where its detail opens), by slug; null when unknown. */
export function districtOf(rec) {
  const slug = rec?.district;
  return all.find((d) => d.slug === slug) || null;
}

/** `dz` value of a location hash ("#/?q=x&dz=wola" → "wola"), or null. */
export function districtFromHash(hash) {
  const h = String(hash || '');
  const qi = h.indexOf('?');
  if (qi < 0) return null;
  for (const part of h.slice(qi + 1).split('&')) {
    const [k, v] = part.split('=');
    if (k === 'dz' && v && SLUG.test(v)) return v;
  }
  return null;
}

/** Record id of a permalink hash ("#/wpis/wz-bem-2026-1?…" → "wz-bem-2026-1"), or null. */
export function recordIdFromHash(hash) {
  const m = /^#?\/wpis\/([^?]+)/.exec(String(hash || ''));
  if (!m) return null;
  try {
    return decodeURIComponent(m[1]);
  } catch {
    return m[1];
  }
}

/**
 * Pick the district to show. Pure.
 * @param {object[]} districts entries of data/districts.json
 * @param {{hash?: string, cityItem?: object|null}} where `cityItem`: districts.json's `city`
 * @returns {object} the district entry
 */
export function resolveDistrict(districts, { hash = '', cityItem = null } = {}) {
  const list = Array.isArray(districts) ? districts.filter((d) => d && SLUG.test(d.slug || '')) : [];
  const bySlug = new Map(list.map((d) => [d.slug, d]));
  if (cityItem?.slug === CITY_SLUG) bySlug.set(CITY_SLUG, cityItem);
  const id = recordIdFromHash(hash);
  const fromHash = bySlug.get(districtFromHash(hash));
  // A record never opens in the city scope: its full data (sources, related records) is in its district.
  if (fromHash && !(fromHash.city && id)) return fromHash;
  // wz-bem-2026-1, ws-wol-6730-2026-12, wz-am-bie-2025-33: the code after the kind (and "am") names the district
  if (id) {
    const parts = id.split('-');
    const code = parts[1] === 'am' ? parts[2] : parts[1];
    const byCode = list.find((d) => d.code && d.code === code);
    if (byCode) return byCode;
    if (/^(?:wz|cp|ws)-(?:am-)?\d/.test(id)) return bySlug.get(DEFAULT_SLUG) || list[0];   // legacy ids: Praga-Południe
  }
  return bySlug.get(DEFAULT_SLUG) || list[0] || LEGACY;
}

/** Make `district` (an entry of data/districts.json) the current one; `list` = all districts, `cityItem` = its city. */
export function setDistrict(district, list = all, cityItem = null) {
  current = { ...LEGACY, ...(district || {}) };
  all = Array.isArray(list) ? list : [];
  city = cityItem?.slug === CITY_SLUG ? cityItem : null;
}

/** Base URL of the current district's data files (Praga-Południe's shard is the single-district data/). */
export function dataBase() {
  if (isCityMode()) return `data/${CITY_SLUG}/`;
  return isCity() && current.slug !== DEFAULT_SLUG ? `data/d/${current.slug}/` : 'data/';
}

/** The Atom feed of the current district (Praga-Południe's – like a single-district site's – is feed.xml); the city
 * has none yet (null). */
export function feedPath() {
  if (isCityMode()) return null;
  return dataBase() === 'data/' ? 'feed.xml' : `${dataBase()}feed.xml`;
}

/** The page's "areas": a district's neighbourhoods (OSM), or – for the whole city – its districts. */
export function areaWords() {
  return isCityMode()
    ? { facet: 'Dzielnica', layer: 'Granice dzielnic', legend: 'granice dzielnic' }
    : { facet: 'Obszar', layer: 'Granice osiedli', legend: 'granice osiedli' };
}

/** Initial map view: the district's bounding box centre (city deployments), else the configured centre. */
export function mapStart() {
  const b = current.bbox;
  if (Array.isArray(b) && b.length === 4 && b.every(Number.isFinite)) {
    const span = Math.max(b[2] - b[0], (b[3] - b[1]) * 1.6);
    const zoom = span > 0.32 ? 11 : span > 0.16 ? 12 : span > 0.08 ? 13 : 14;
    return { center: [(b[1] + b[3]) / 2, (b[0] + b[2]) / 2], zoom, bounds: [[b[1], b[0]], [b[3], b[2]]] };
  }
  const c = current.center;   // approximate centre, before the district has been geocoded
  if (Array.isArray(c) && c.length === 2 && c.every(Number.isFinite)) return { center: c, zoom: 13, bounds: null };
  return { center: MAP_CENTER, zoom: MAP_ZOOM, bounds: null };
}

/** Total records of a district entry (planning kinds and permits). */
export function districtTotals(d) {
  const c = d?.counts_by_kind || {};
  const planning = (c.wz || 0) + (c.cp || 0) + (c.ws || 0);
  const permits = (c.pb || 0) + (c.zg || 0);
  return { planning, permits };
}

/**
 * "Niepełne dane" (plan §7): what a district's own lists lack, from districts.json → `gaps` (pipeline/district_index.py)
 * – files the city's server refused to hand out, or a newest list long ago. Pure; null when nothing is missing.
 */
export function districtGapNote(d) {
  const g = d?.gaps;
  if (!g || typeof g !== 'object') return null;
  const parts = [];
  if (g.missing_files > 0) {
    const y = Array.isArray(g.missing_years) && g.missing_years.length ? g.missing_years : null;
    const years = y ? ` (${y[0] === y[y.length - 1] ? y[0] : `${y[0]}–${y[y.length - 1]}`})` : '';
    parts.push(`brak ${formatNumber(g.missing_files)} z ${formatNumber(g.files)} plików urzędu${years} – serwer miasta odmówił ich pobrania, ponowimy`);
  }
  if (g.newest_list) parts.push(`najnowsza lista na stronie urzędu: ${formatMonth(g.newest_list)}`);
  return parts.length ? `Niepełne dane: ${parts.join('; ')}` : null;
}
