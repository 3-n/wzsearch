/**
 * Pure helpers for record kinds (docs/DATA_MODEL.md): the only codes the UI may assume.
 *
 *   wz / cp / ws  – planning decisions and initiated proceedings (records.json), shown by default
 *   pb / zg       – building permits and notifications from GUNB RWDZ (permits.json, lazy), OPT-IN
 *
 * A kind selection is an explicit list of kinds; the default selection is DEFAULT_KINDS
 * (an absent `rodzaj` URL parameter means the default, not "every kind").
 * DOM-free; unit-tested in tests/js/kinds.test.mjs.
 */

/** Display / stacking order of every known kind. */
export const KIND_ORDER = ['wz', 'cp', 'ws', 'pb', 'zg'];

/** Kinds included when the URL does not say otherwise. */
export const DEFAULT_KINDS = ['wz', 'cp', 'ws'];

/** Kinds the user has to switch on (their records live in the lazily loaded permits.json). */
export const OPT_IN_KINDS = ['pb', 'zg'];

/** Record ids of opt-in kinds are namespaced with the kind code ("pb-st-mz-pa-2026-29594"). */
export const OPT_IN_ID = new RegExp(`^(?:${OPT_IN_KINDS.join('|')})-`);

export const isOptInKind = (k) => OPT_IN_KINDS.includes(k);

/** Sort kind codes in KIND_ORDER (unknown codes last, alphabetically) and drop duplicates. */
export function orderKinds(kinds) {
  const rank = (k) => {
    const i = KIND_ORDER.indexOf(k);
    return i < 0 ? KIND_ORDER.length : i;
  };
  return [...new Set(kinds || [])].sort((a, b) => rank(a) - rank(b) || a.localeCompare(b));
}

/** Same members, any order. */
export function sameKinds(a, b) {
  const x = orderKinds(a);
  const y = orderKinds(b);
  return x.length === y.length && x.every((k, i) => k === y[i]);
}

/** True when the selection is the default one (nothing to show in the URL or as a chip). */
export function isDefaultKinds(kinds) {
  return sameKinds(kinds, DEFAULT_KINDS);
}

/** An empty or missing selection means the default one. */
export function effectiveKinds(kinds) {
  return Array.isArray(kinds) && kinds.length ? kinds : DEFAULT_KINDS;
}

/** Does the selection include any opt-in kind (→ permits.json is needed)? */
export function wantsOptIn(kinds) {
  return effectiveKinds(kinds).some(isOptInKind);
}

/**
 * Toggle one kind in a selection. Unticking the last kind falls back to the default selection
 * (an empty selection would always show nothing).
 */
export function toggleKind(kinds, kind, on) {
  const set = new Set(effectiveKinds(kinds));
  if (on) set.add(kind); else set.delete(kind);
  return set.size ? orderKinds([...set]) : [...DEFAULT_KINDS];
}

/** The default selection plus the given opt-in kinds ("Pokaż też pozwolenia"). */
export function withOptIn(kinds, extra) {
  return orderKinds([...effectiveKinds(kinds), ...extra]);
}
