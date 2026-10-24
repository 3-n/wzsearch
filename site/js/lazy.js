/**
 * Pure decisions about the lazily loaded permits layer (permits.json + parcels-permits.geojson).
 *
 * Building permits / notifications (kinds pb, zg) are opt-in and ~5× more numerous than the planning
 * records, so they are not part of the first paint. They are fetched:
 *   1. when the kind selection includes pb/zg                                  → 'kinds'
 *   2. when a permalink to a pb/zg record is opened                             → 'permalink'
 *   3. when an open record lists related pb/zg records (the WZ → permit story)  → 'related'
 *   4. when the explore view is filtered by an RWDZ source file                 → 'file'
 *   5. otherwise in idle time after the first render (skipped on phones, with Save-Data and on 2G)
 * DOM-free; unit-tested in tests/js/lazy.test.mjs.
 */
import { OPT_IN_ID, wantsOptIn } from './kinds.js';

/**
 * Why the permits layer is needed right now (null = not needed yet).
 * @param {{route: string, recordId: string|null, filters: object}} state  store state (url.js)
 * @param {{loaded?: boolean, byId?: Map<string, object>, filesById?: Map<string, object>,
 *          fileDataset?: (file: object) => string|null}} ctx
 * @returns {'kinds'|'permalink'|'related'|'file'|null}
 */
export function permitsNeeded(state, ctx = {}) {
  if (ctx.loaded || !state) return null;
  const f = state.filters || {};
  if (wantsOptIn(f.kinds)) return 'kinds';
  const route = state.route;
  if (route === 'record' && state.recordId) {
    const entry = ctx.byId?.get(state.recordId);
    if (!entry && OPT_IN_ID.test(state.recordId)) return 'permalink';
    if (entry && hasMissingPermits(entry.rec, ctx.byId)) return 'related';
  }
  if (f.file && ctx.filesById && ctx.fileDataset) {
    const file = ctx.filesById.get(f.file);
    if (file && ctx.fileDataset(file) === 'rwdz') return 'file';
  }
  return null;
}

/** Related ids that point at not-yet-loaded permit records. */
export function missingPermitIds(rec, byId) {
  const related = Array.isArray(rec?.related) ? rec.related : [];
  return related.filter((id) => typeof id === 'string' && OPT_IN_ID.test(id) && !byId?.has(id));
}

export function hasMissingPermits(rec, byId) {
  return missingPermitIds(rec, byId).length > 0;
}

/**
 * Prefetch in idle time unless the visitor asked to save data, is on a very slow connection or on a phone-sized
 * screen (the register is several MB; phones fetch it only when it is actually needed).
 * @param {{saveData?: boolean, effectiveType?: string}|undefined} connection navigator.connection
 * @param {{smallScreen?: boolean}} [opts]
 */
export function idlePrefetchAllowed(connection, { smallScreen = false } = {}) {
  if (smallScreen) return false;
  if (!connection) return true;
  if (connection.saveData) return false;
  return !/(^|-)2g$/.test(String(connection.effectiveType || ''));
}

/**
 * Should ensurePermits() start a request now? Never while loaded/loading/unavailable. After a failure only an explicit
 * retry ("Spróbuj ponownie") fetches again – except that a SILENT failure of the idle prefetch is retried once by the
 * first real need (the visitor never saw it fail). Otherwise every state change (each keystroke in the search box with
 * permits switched on) would send a new request and stack another error toast.
 * @param {string} state idle | loading | loaded | error | unavailable
 * @param {string} reason why it is needed now (permitsNeeded() reason, 'idle' or 'retry')
 * @param {string|null} lastFailReason the reason of the request that failed
 */
export function shouldFetchPermits(state, reason, lastFailReason = null) {
  if (state === 'loaded' || state === 'loading' || state === 'unavailable') return false;
  if (state === 'error') return reason === 'retry' || (lastFailReason === 'idle' && reason !== 'idle');
  return true;
}

/** Delay (ms) before the idle prefetch: long enough for the first render and the map to settle. */
export const IDLE_PREFETCH_DELAY = 2500;
