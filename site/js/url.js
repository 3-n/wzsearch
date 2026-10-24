/**
 * Pure hash-URL (de)serialisation. Every filter, search, sort, view mode and the
 * open record live in the hash, with readable Polish parameter names
 * (documented in docs/FRONTEND.md):
 *
 *   #/?q=przedszkole&rodzaj=wz,cp&od=2024-01&do=2026-09&typ=wielorodzinny
 *   #/wpis/wz-2026-15?rodzaj=wz
 *   #/?rodzaj=wz,cp,ws,pb&zakres=budowa        (building permits switched on)
 *   #/zrodla   #/zrodla/rwdz   #/o-projekcie
 *
 * Unknown/invalid values are dropped silently, so old or hand-edited links never break.
 */
import { defaultFilters, NEAR_RADII, PERIOD_PRESETS } from './filters.js';
import { streetKey } from './data.js';
import { DEFAULT_KINDS, isDefaultKinds, orderKinds } from './kinds.js';

/**
 * "W pobliżu" points are stored with 3 decimals (≈ 110 m north–south, ≈ 70 m east–west in Warsaw):
 * precise enough for a 250 m radius, coarse enough not to pin down someone's home in a shared link.
 */
export const NEAR_DECIMALS = 3;

export const ROUTES = {
  explore: '',
  record: 'wpis',
  sources: 'zrodla',
  about: 'o-projekcie',
};

const APPLICANT_TO_URL = { person: 'osoba', organization: 'firma', unknown: 'nieustalony' };
const APPLICANT_FROM_URL = Object.fromEntries(Object.entries(APPLICANT_TO_URL).map(([k, v]) => [v, k]));
const SORT_TO_URL = { newest: 'najnowsze', oldest: 'najstarsze', street: 'ulica', relevance: 'trafnosc' };
const SORT_FROM_URL = Object.fromEntries(Object.entries(SORT_TO_URL).map(([k, v]) => [v, k]));
const MONTH = /^\d{4}-(0[1-9]|1[0-2])$/;
/** Dictionary keys used as URL values (dataset, issuer, outcome, scope slugs, roman category numerals). */
const DICT_KEY = /^[\p{L}\p{N}_-]{1,40}$/u;
/** List filters whose values are dictionary keys: URL name → filters key. */
const LIST_PARAMS = [['zrodlo', 'datasets'], ['organ', 'issuers'], ['rozstrzygniecie', 'outcomes'], ['zakres', 'scopes'], ['kategoria', 'categories']];

/** Encode a single value; keep a few safe, readable characters unescaped. */
function enc(v) {
  return encodeURIComponent(v).replace(/%2F/g, '/').replace(/%3A/g, ':').replace(/%20/g, '+');
}

function dec(v) {
  try {
    return decodeURIComponent(v.replace(/\+/g, ' '));
  } catch {
    return v;
  }
}

function encList(arr) {
  return arr.map((x) => encodeURIComponent(x).replace(/%2F/g, '/')).join(',');
}

function decList(raw) {
  return raw.split(',').map(dec).map((s) => s.trim()).filter(Boolean);
}

function uniq(arr) {
  return [...new Set(arr)];
}

function num(s, digits) {
  const n = Number(s);
  return Number.isFinite(n) ? Number(n.toFixed(digits)) : null;
}

/** Own-key lookup in a small table: "constructor", "__proto__" or "toString" from a URL are not keys. */
const lookup = (table, key) => (Object.hasOwn(table, key) ? table[key] : undefined);

/** Parse the query part ("a=1&b=2", raw, still encoded) into a {name: rawValue} map (no prototype). */
function parseQuery(qs) {
  const out = Object.create(null);
  if (!qs) return out;
  for (const part of qs.split('&')) {
    if (!part) continue;
    const i = part.indexOf('=');
    const k = dec(i < 0 ? part : part.slice(0, i));
    const v = i < 0 ? '' : part.slice(i + 1);
    if (!(k in out)) out[k] = v;
  }
  return out;
}

/**
 * Parse a location hash.
 * @param {string} hash e.g. "#/wpis/wz-2026-15?rodzaj=wz"
 * @returns {{route: string, recordId: string|null, tab: string|null, filters: object, mode: 'list'|'map', unknown: boolean}}
 */
export function parseHash(hash) {
  let h = (hash || '').replace(/^#/, '');
  const qi = h.indexOf('?');
  const path = (qi < 0 ? h : h.slice(0, qi)).replace(/^\/+|\/+$/g, '');
  const qs = qi < 0 ? '' : h.slice(qi + 1);
  h = null;

  let route = 'explore';
  let recordId = null;
  let tab = null;
  let unknown = false;
  const segs = path ? path.split('/') : [];
  if (segs.length === 0) route = 'explore';
  else if (segs[0] === ROUTES.record && segs[1]) {
    route = 'record';
    recordId = dec(segs.slice(1).join('/'));
  } else if (segs[0] === ROUTES.sources) {
    route = 'sources';
    // #/zrodla/<dataset> opens one tab of the Sources page (dataset keys from records.json)
    if (segs[1] && /^[a-z0-9-]{1,32}$/.test(segs[1])) tab = segs[1];
  } else if (segs[0] === ROUTES.about) route = 'about';
  else unknown = true;

  const p = parseQuery(qs);
  const f = defaultFilters();
  if (p.q) f.q = dec(p.q).slice(0, 200);
  if (p.rodzaj) {
    // An absent or empty/invalid `rodzaj` means the default selection (wz, cp, ws), never "every kind".
    const kinds = orderKinds(decList(p.rodzaj).filter((k) => /^[a-z]{1,8}$/.test(k)));
    f.kinds = kinds.length ? kinds : [...DEFAULT_KINDS];
  }
  if (p.okres && lookup(PERIOD_PRESETS, dec(p.okres))) f.period = dec(p.okres);
  if (p.od && MONTH.test(dec(p.od))) f.from = dec(p.od);
  if (p.do && MONTH.test(dec(p.do))) f.to = dec(p.do);
  if (f.from && f.to && f.from > f.to) [f.from, f.to] = [f.to, f.from];
  if (f.period) { f.from = null; f.to = null; }
  if (p.typ) f.tags = uniq(decList(p.typ));
  if (p.wnioskodawca) {
    f.applicants = uniq(decList(p.wnioskodawca).map((v) => lookup(APPLICANT_FROM_URL, v)).filter(Boolean));
  }
  if (p.obszar) f.areas = uniq(decList(p.obszar));
  for (const [name, key] of LIST_PARAMS) if (p[name]) f[key] = uniq(decList(p[name]).filter((v) => DICT_KEY.test(v)));
  if (p.ulica) f.streets = uniq(decList(p.ulica).map(streetKey).filter(Boolean));
  if (p.lokalizacja === '1' || p.lokalizacja === 'tak') f.geoOnly = true;
  if (p.mapa) {
    const b = dec(p.mapa).split(',').map((x) => num(x, 5));
    if (b.length === 4 && b.every((x) => x != null) && b[0] < b[2] && b[1] < b[3]) f.bbox = b;
  }
  if (p.blisko) {
    const [lat, lon] = dec(p.blisko).split(',').map((x) => num(x, NEAR_DECIMALS));
    if (lat != null && lon != null && Math.abs(lat) <= 90 && Math.abs(lon) <= 180) {
      const r = Number(p.promien);
      f.near = { lat, lon, r: NEAR_RADII.includes(r) ? r : 500 };
    }
  }
  if (p.plik && /^[0-9a-z_-]{1,64}$/i.test(dec(p.plik))) f.file = dec(p.plik);
  if (p.sort && lookup(SORT_FROM_URL, dec(p.sort))) f.sort = lookup(SORT_FROM_URL, dec(p.sort));
  const mode = p.tryb === 'mapa' ? 'map' : 'list';
  return { route, recordId, tab, filters: f, mode, unknown };
}

/**
 * Serialise filters (+ mode) into a query string (without "?"), in a stable order.
 * Defaults are omitted to keep links short.
 */
export function buildQuery(f, mode = 'list') {
  const parts = [];
  const push = (k, v) => parts.push(`${k}=${v}`);
  if (f.q && f.q.trim()) push('q', enc(f.q.trim()));
  if (f.kinds?.length && !isDefaultKinds(f.kinds)) push('rodzaj', encList(orderKinds(f.kinds)));
  if (f.period && lookup(PERIOD_PRESETS, f.period)) push('okres', enc(f.period));
  else {
    if (f.from) push('od', f.from);
    if (f.to) push('do', f.to);
  }
  if (f.tags?.length) push('typ', encList(f.tags));
  if (f.applicants?.length) push('wnioskodawca', f.applicants.map((a) => lookup(APPLICANT_TO_URL, a)).filter(Boolean).join(','));
  if (f.areas?.length) push('obszar', encList(f.areas));
  for (const [name, key] of LIST_PARAMS) if (f[key]?.length) push(name, encList(f[key]));
  if (f.streets?.length) push('ulica', encList(f.streets));
  if (f.geoOnly) push('lokalizacja', '1');
  if (f.bbox) push('mapa', f.bbox.map((x) => Number(x).toFixed(5)).join(','));
  if (f.near) {
    push('blisko', `${roundCoord(f.near.lat)},${roundCoord(f.near.lon)}`);
    push('promien', String(f.near.r));
  }
  if (f.file) push('plik', enc(f.file));
  if (f.sort && lookup(SORT_TO_URL, f.sort)) push('sort', SORT_TO_URL[f.sort]);
  if (mode === 'map') push('tryb', 'mapa');
  return parts.join('&');
}

/** Round a coordinate for the URL (NEAR_DECIMALS) and drop trailing zeros: 52.25 → "52.25". */
export function roundCoord(x) {
  return String(Number(Number(x).toFixed(NEAR_DECIMALS)));
}

/**
 * Build a full hash for a route.
 * @param {{route: string, recordId?: string|null, tab?: string|null, filters?: object, mode?: string}} s
 */
export function buildHash({ route = 'explore', recordId = null, tab = null, filters = null, mode = 'list' }) {
  if (route === 'sources') return `#/${ROUTES.sources}${tab ? `/${encodeURIComponent(tab)}` : ''}`;
  if (route === 'about') return `#/${ROUTES.about}`;
  const qs = filters ? buildQuery(filters, mode) : (mode === 'map' ? 'tryb=mapa' : '');
  const path = route === 'record' && recordId ? `/${ROUTES.record}/${encodeURIComponent(recordId)}` : '/';
  return `#${path}${qs ? `?${qs}` : ''}`;
}
