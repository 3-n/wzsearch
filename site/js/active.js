/**
 * Pure description of the active filters: one item per removable chip.
 * Used by the chips bar, the empty state ("remove this filter → N results") and tests.
 */
import { formatMonthRange, formatDistance } from './format.js';
import { resolvePeriod } from './filters.js';
import { APPLICANT_LABELS } from './copy.js';
import { DEFAULT_KINDS, effectiveKinds, isDefaultKinds, toggleKind } from './kinds.js';

/** Chip groups for list filters whose values are dictionary keys: filters key → [group, label, dictionary]. */
const LIST_CHIPS = [
  ['datasets', 'dataset', 'Źródło', 'datasets'],
  ['issuers', 'issuer', 'Organ', 'issuers'],
  ['outcomes', 'outcome', 'Rozstrzygnięcie', 'outcomes'],
  ['scopes', 'scope', 'Zakres', 'scopes'],
  ['categories', 'category', 'Kategoria', 'categories'],
];

/**
 * Kind chips. The default selection (wz, cp, ws) shows none. A selection that contains the default adds
 * one "+ <kind>" chip per opt-in kind ("Rodzaj: + Pozwolenie"); a narrower selection lists every selected
 * kind ("Rodzaj: WZ"). Removing a chip removes that kind (an empty selection falls back to the default).
 */
function kindChips(kinds, dicts) {
  const sel = effectiveKinds(kinds);
  if (isDefaultKinds(sel)) return [];
  const hasDefault = DEFAULT_KINDS.every((k) => sel.includes(k));
  const shown = hasDefault ? sel.filter((k) => !DEFAULT_KINDS.includes(k)) : sel;
  return shown.map((k) => ({
    group: 'kind', groupLabel: 'Rodzaj', label: `${hasDefault ? '+ ' : ''}${dicts.kinds?.[k]?.short || k}`,
    title: dicts.kinds?.[k]?.label, remove: { kinds: toggleKind(sel, k, false) },
  }));
}

const PERIOD_LABELS = { '3m': 'Ostatnie 3 miesiące', '12m': 'Ostatnie 12 miesięcy' };

/**
 * @param {object} f filter state
 * @param {{dicts?: object, streets?: Map, filesById?: Map, latestMonth?: string}} ctx
 * @returns {{group: string, groupLabel: string, label: string, remove: object, title?: string}[]}
 *   `remove` is a filters patch that removes exactly this item.
 */
export function describeActive(f, ctx = {}) {
  const dicts = ctx.dicts || {};
  const out = [];
  if (f.q && f.q.trim()) {
    out.push({ group: 'q', groupLabel: 'Szukaj', label: `„${f.q.trim()}”`, remove: { q: '' } });
  }
  out.push(...kindChips(f.kinds, dicts));
  if (f.period || f.from || f.to) {
    let label = PERIOD_LABELS[f.period];
    if (!label) label = formatMonthRange(f.from, f.to);
    const resolved = resolvePeriod(f, ctx.latestMonth);
    out.push({
      group: 'period', groupLabel: 'Okres', label,
      title: f.period ? formatMonthRange(resolved.from, resolved.to) : undefined,
      remove: { period: null, from: null, to: null },
    });
  }
  for (const t of f.tags) {
    out.push({ group: 'tag', groupLabel: 'Typ', label: dicts.tags?.[t]?.label || t, remove: { tags: f.tags.filter((x) => x !== t) } });
  }
  for (const a of f.applicants) {
    out.push({
      group: 'applicant', groupLabel: 'Wnioskodawca', label: APPLICANT_LABELS[a] || a,
      remove: { applicants: f.applicants.filter((x) => x !== a) },
    });
  }
  for (const a of f.areas) {
    out.push({ group: 'area', groupLabel: 'Obszar', label: dicts.areas?.[a]?.label || a, remove: { areas: f.areas.filter((x) => x !== a) } });
  }
  for (const [key, group, groupLabel, dict] of LIST_CHIPS) {
    for (const v of f[key] || []) {
      const d = dicts[dict]?.[v];
      const label = group === 'category' && d?.label ? `${v} – ${d.label}` : (d?.short || d?.label || v);
      out.push({ group, groupLabel, label, title: d?.label, remove: { [key]: f[key].filter((x) => x !== v) } });
    }
  }
  for (const s of f.streets) {
    out.push({
      group: 'street', groupLabel: 'Ulica', label: ctx.streets?.get(s)?.label || s,
      remove: { streets: f.streets.filter((x) => x !== s) },
    });
  }
  if (f.geoOnly) out.push({ group: 'geo', groupLabel: 'Lokalizacja', label: 'tylko z lokalizacją', remove: { geoOnly: false } });
  if (f.bbox) out.push({ group: 'bbox', groupLabel: 'Mapa', label: 'widoczny obszar', remove: { bbox: null } });
  if (f.near) {
    out.push({ group: 'near', groupLabel: 'W pobliżu', label: `promień ${formatDistance(f.near.r)}`, remove: { near: null } });
  }
  if (f.file) {
    const file = ctx.filesById?.get(f.file);
    out.push({ group: 'file', groupLabel: 'Plik', label: file?.filename || f.file, remove: { file: null } });
  }
  return out;
}
