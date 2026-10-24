/**
 * Application state, synchronised with the URL hash (single source of truth).
 *
 * State shape: { route, recordId, tab, filters, mode, unknown }  (see url.js)
 * - navigate() updates state, writes the hash (push or replace) and notifies subscribers.
 * - Back/forward and hand-edited hashes are picked up via hashchange/popstate.
 */
import { parseHash, buildHash } from './url.js';

const listeners = new Set();
let state = parseHash('');
let lastHash = null;

export function getState() {
  return state;
}

/** Subscribe to state changes: fn(state, prevState, meta). Returns an unsubscribe function. */
export function subscribe(fn) {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

function emit(prev, meta) {
  for (const fn of listeners) fn(state, prev, meta);
}

function onLocationChange() {
  const h = window.location.hash;
  if (h === lastHash) return;
  lastHash = h;
  const prev = state;
  state = parseHash(h);
  emit(prev, { source: 'location' });
}

/** Read the initial state from the URL and start listening for navigation. */
export function initStore() {
  lastHash = window.location.hash;
  state = parseHash(lastHash);
  window.addEventListener('hashchange', onLocationChange);
  window.addEventListener('popstate', onLocationChange);
  return state;
}

/**
 * Navigate to a new state.
 * @param {Partial<{route: string, recordId: string|null, tab: string|null, filters: object, mode: string}>} patch
 * @param {{replace?: boolean, silent?: boolean, meta?: object}} [opts]
 *   replace → history.replaceState (no new history entry; for typing, map moves, prev/next)
 */
export function navigate(patch, { replace = false, meta = {} } = {}) {
  const prev = state;
  const next = { ...state, ...patch, unknown: false };
  if (next.route !== 'record') next.recordId = null;
  if (next.route !== 'sources') next.tab = null;
  const hash = buildHash(next);
  state = next;
  if (hash !== window.location.hash) {
    lastHash = hash;
    const url = `${window.location.pathname}${window.location.search}${hash}`;
    if (replace) window.history.replaceState(window.history.state, '', url);
    else window.history.pushState({ wz: true, depth: (window.history.state?.depth || 0) + 1 }, '', url);
  }
  emit(prev, { source: 'app', ...meta });
}

/** Merge a filters patch into the current filters. */
export function setFilters(patch, opts) {
  navigate({ filters: { ...state.filters, ...patch } }, opts);
}

/** True when the current history entry was pushed by this app (so history.back() stays in-app). */
export function canGoBackInApp() {
  return Boolean(window.history.state?.wz);
}
