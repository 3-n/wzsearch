/**
 * Filters panel: built once from the dictionaries in records.json, then patched in place on every
 * state change (counts, checked state, which options exist), so keyboard focus and scroll position are
 * never lost. The only parts rebuilt later are the year buttons and month selects when the month axis
 * changes (e.g. building permits from 2016 are switched on).
 */
import { h, replaceChildren } from '../dom.js';
import { icon, kindGlyph } from '../icons.js';
import { formatNumber, formatMonth, formatMonthShort, formatDistance, monthRange, formatMonthRange, plural, WPIS } from '../format.js';
import { NEAR_RADII, resolvePeriod, hasActiveFilters, availableOptions, sameSplit } from '../filters.js';
import { fold } from '../search.js';
import { KIND_EXPLAINERS, APPLICANT_LABELS, UNOFFICIAL, TAG_GROUP_LABELS } from '../copy.js';
import { DEFAULT_KINDS, OPT_IN_KINDS, effectiveKinds, sameKinds, toggleKind } from '../kinds.js';
import { createCombobox } from '../components/combobox.js';

const TAGS_VISIBLE = 6;
const CATEGORIES_VISIBLE = 6;

let tipSeq = 0;

/** Toggletip: an info button that reveals a one-line explanation (announced via role=status). */
function infoTip(text, label) {
  tipSeq += 1;
  const id = `tip-${tipSeq}`;
  const bubble = h('span', { class: 'tip', id, role: 'status' });
  const btn = h('button', {
    type: 'button', class: 'info-btn', 'aria-label': `Wyjaśnienie: ${label}`, 'aria-expanded': 'false', 'aria-controls': id,
  }, icon('info', { size: 15 }));
  const close = () => {
    bubble.textContent = '';
    bubble.classList.remove('is-open');
    btn.setAttribute('aria-expanded', 'false');
  };
  btn.addEventListener('click', (e) => {
    e.preventDefault();
    if (bubble.classList.contains('is-open')) { close(); return; }
    document.querySelectorAll('.tip.is-open').forEach((t) => { t.textContent = ''; t.classList.remove('is-open'); });
    document.querySelectorAll('.info-btn[aria-expanded="true"]').forEach((b) => b.setAttribute('aria-expanded', 'false'));
    bubble.textContent = text;
    bubble.classList.add('is-open');
    btn.setAttribute('aria-expanded', 'true');
  });
  btn.addEventListener('keydown', (e) => { if (e.key === 'Escape' && bubble.classList.contains('is-open')) { e.stopPropagation(); close(); } });
  btn.addEventListener('blur', () => setTimeout(close, 150));
  return { btn, bubble };
}

function group(title, body, { id, hidden = false, extra = null } = {}) {
  return h('fieldset', { class: 'fgroup', id, hidden },
    h('legend', { class: 'fgroup__title' }, title, extra), body);
}

/**
 * List facets over dictionary keys (docs/DATA_MODEL.md v2): filters key, entry field, title, dictionary,
 * how many options must exist for the group to be worth showing, and how many are visible before "Pokaż wszystkie".
 */
const LIST_FACETS = [
  // Shown as a permanent note (not a toggletip): the filter sees only the records that state an outcome at all.
  { key: 'outcomes', field: 'outcome', title: 'Rozstrzygnięcie', dict: 'outcomes', min: 1,
    note: 'Podają je tylko zestawienia Biura Architektury (BAiPP) – Urząd Dzielnicy i rejestr GUNB rozstrzygnięcia nie podają, więc ich decyzji ten filtr nie obejmuje.' },
  { key: 'scopes', field: 'scope', title: 'Zakres robót', dict: 'scopes', min: 1, permitsOnly: true },
  { key: 'categories', field: 'category', title: 'Kategoria obiektu', dict: 'categories', min: 1, permitsOnly: true, visible: CATEGORIES_VISIBLE, byCount: true,
    info: 'Kategoria obiektu budowlanego z załącznika do ustawy Prawo budowlane, np. XIII – budynki wielorodzinne.' },
  { key: 'datasets', field: 'dataset', title: 'Źródło danych', dict: 'datasets', min: 2 },
  // Hidden while it splits the records exactly like "Źródło danych" (planning kinds only: district ↔ BAiPP).
  { key: 'issuers', field: 'issuer', title: 'Organ', dict: 'issuers', min: 2, sameAs: 'dataset',
    info: 'Kto wydał decyzję lub prowadzi sprawę: wydział dzielnicy, Biuro Architektury m.st. Warszawy albo wojewoda.' },
];

/**
 * @param {{
 *   index: object,
 *   onPatch: (patch: object, opts?: object) => void,
 *   onLocate: () => void, onPickPoint: () => void,
 *   onClose: () => void, onShowResults: () => void,
 *   onRetryPermits?: () => void,
 * }} ctx
 */
export function createFiltersPanel(ctx) {
  const { index } = ctx;
  const { dicts } = index;
  const refs = { kinds: new Map(), tags: new Map(), applicants: new Map(), areas: new Map() };
  for (const lf of LIST_FACETS) refs[lf.key] = new Map();
  let current = null; // last filters
  let facets = null;
  let permitsState = index.permitsLoaded ? 'loaded' : 'idle';
  let available = null;
  let availableKey = null;

  const checkboxRow = (map, key, label, { glyph = null, info = null, iconName = null, hint = null, only = null, onChange }) => {
    const input = h('input', { type: 'checkbox', class: 'opt__input', onChange: (e) => onChange(key, e.target.checked) });
    const count = h('span', { class: 'count', 'aria-hidden': 'true' });
    const srCount = h('span', { class: 'sr-only' });
    const tip = info ? infoTip(info, label) : null;
    const onlyBtn = only ? h('button', {
      type: 'button', class: 'opt__only', 'aria-label': `Pokaż tylko: ${label}`, title: `Pokaż tylko: ${label}`, onClick: only,
    }, 'tylko') : null;
    const row = h('div', { class: ['opt', onlyBtn && 'opt--only'] },
      h('label', { class: 'opt__label', title: hint }, input, glyph, iconName ? icon(iconName, { size: 15, class: 'opt__icon' }) : null,
        h('span', { class: 'opt__text' }, label), srCount),
      onlyBtn, tip ? tip.btn : null, count, tip ? tip.bubble : null);
    map.set(key, { input, count, srCount, row });
    return row;
  };

  // --- Rodzaj ------------------------------------------------------------------------------------
  // Planning kinds first; the opt-in register kinds (building permits) below a sub-heading.
  const kindRow = (k) => checkboxRow(refs.kinds, k, dicts.kinds[k]?.label || k, {
    glyph: kindGlyph(k), info: KIND_EXPLAINERS[k] || dicts.kinds[k]?.description || null,
    only: () => ctx.onPatch({ kinds: [k] }),
    onChange: (key, on) => ctx.onPatch({ kinds: toggleKind(current.kinds, key, on) }),
  });
  const baseKinds = index.kindCodes.filter((k) => !OPT_IN_KINDS.includes(k));
  const optKinds = index.kindCodes.filter((k) => OPT_IN_KINDS.includes(k));
  const permitsStatus = h('p', { class: 'kinds-status', role: 'status' });
  const kindRows = [
    baseKinds.map(kindRow),
    optKinds.length ? h('div', { class: 'kinds-optin' },
      h('p', { class: 'kinds-optin__title' }, icon('crane', { size: 14 }), 'Rejestr budowlany GUNB'),
      h('p', { class: 'kinds-optin__hint' }, 'domyślnie ukryte – zaznacz, aby pokazać'),
      optKinds.map(kindRow), permitsStatus) : null,
  ];
  const kindsReset = h('button', {
    type: 'button', class: 'btn btn--link btn--xs fgroup__reset', hidden: true, onClick: () => ctx.onPatch({ kinds: [...DEFAULT_KINDS] }),
  }, 'Domyślne');

  // --- Okres -------------------------------------------------------------------------------------
  const presetBtns = new Map();
  const presets = [[null, 'Cały okres'], ['3m', 'Ostatnie 3 mies.'], ['12m', 'Ostatnie 12 mies.']];
  const presetRow = h('div', { class: 'seg', role: 'group', 'aria-label': 'Szybki wybór okresu' },
    presets.map(([key, label]) => {
      const b = h('button', {
        type: 'button', class: 'seg__btn', 'aria-pressed': 'false',
        onClick: () => ctx.onPatch({ period: key, from: null, to: null }),
      }, label);
      presetBtns.set(key, b);
      return b;
    }));
  let bounds = { min: index.minMonth, max: index.maxMonth };
  /** Month ranges of the current preset per kind group (filters.periodSpans; one range when every kind shares it). */
  let spans = null;
  /** The range the month selects show: the preset's window across every kind (or the explicit od/do). */
  const shownRange = (f) => {
    if (f.period && spans && spans.length) {
      return { from: spans.map((x) => x.from).filter(Boolean).sort()[0] || null, to: spans.map((x) => x.to).filter(Boolean).sort().pop() || null };
    }
    return resolvePeriod(f, bounds.max);
  };
  let months = [];
  const yearBtns = new Map();
  const yearRow = h('div', { class: 'years', role: 'group', 'aria-label': 'Rok' });
  const fromSel = h('select', { class: 'select select--sm', id: 'f-from', onChange: (e) => onRange('from', e.target.value) });
  const toSel = h('select', { class: 'select select--sm', id: 'f-to', onChange: (e) => onRange('to', e.target.value) });
  function onRange(which, value) {
    const resolved = shownRange(current);
    let from = which === 'from' ? (value || null) : resolved.from;
    let to = which === 'to' ? (value || null) : resolved.to;
    if (from && to && from > to) [from, to] = [to, from];
    ctx.onPatch({ period: null, from, to });
  }
  /** (Re)build year buttons and month options for a month axis; cheap and only when the axis changes. */
  function setBounds(b) {
    bounds = b;
    const years = [];
    if (b.min && b.max) for (let y = Number(b.max.slice(0, 4)); y >= Number(b.min.slice(0, 4)); y -= 1) years.push(String(y));
    const focusedYear = [...yearBtns].find(([, v]) => v.b === document.activeElement)?.[0];
    yearBtns.clear();
    replaceChildren(yearRow, years.map((y) => {
      const count = h('span', { class: 'count' });
      const b2 = h('button', {
        type: 'button', class: 'year-btn', 'aria-pressed': 'false',
        onClick: () => {
          const on = current.from === `${y}-01` && current.to === `${y}-12` && !current.period;
          ctx.onPatch(on ? { period: null, from: null, to: null } : { period: null, from: `${y}-01`, to: `${y}-12` });
        },
      }, h('span', null, y), h('span', { class: 'sr-only' }, ': '), count); // name "2026: 48" = the visible label
      yearBtns.set(y, { b: b2, count });
      return b2;
    }));
    if (focusedYear && yearBtns.get(focusedYear)) yearBtns.get(focusedYear).b.focus({ preventScroll: true });
    months = b.min && b.max ? monthRange(b.min, b.max).reverse() : [];
    const monthOptions = (placeholder) => [h('option', { value: '' }, placeholder),
      ...months.map((m) => h('option', { value: m }, formatMonthShort(m)))];
    replaceChildren(fromSel, monthOptions('najstarsze'));
    replaceChildren(toSel, monthOptions('najnowsze'));
  }
  setBounds(bounds);
  const rangeRow = h('div', { class: 'range' },
    h('label', { class: 'range__field', for: 'f-from' }, h('span', { class: 'field-label' }, 'Od'), fromSel),
    h('span', { class: 'range__dash', 'aria-hidden': 'true' }, '–'),
    h('label', { class: 'range__field', for: 'f-to' }, h('span', { class: 'field-label' }, 'Do'), toSel));
  const periodNote = h('p', { class: 'fgroup__note' });

  // --- Typ inwestycji ----------------------------------------------------------------------------
  // Tags come from records.json; the classifier may group them (group: "funkcja" / "roboty").
  const tagGroups = [];
  for (const t of Object.keys(dicts.tags || {})) {
    const g = typeof dicts.tags[t]?.group === 'string' ? dicts.tags[t].group : '';
    let grp = tagGroups.find((x) => x.key === g);
    if (!grp) { grp = { key: g, keys: [], expanded: false }; tagGroups.push(grp); }
    grp.keys.push(t);
  }
  const globalTagCount = () => available?.tags || {};
  for (const grp of tagGroups) {
    grp.rows = grp.keys.map((t) => checkboxRow(refs.tags, t, dicts.tags[t]?.label || t, {
      hint: typeof dicts.tags[t]?.description === 'string' ? dicts.tags[t].description : null,
      onChange: (key, on) => ctx.onPatch({ tags: toggle(current.tags, key, on) }),
    }));
    grp.list = h('div', { class: 'tag-group__rows' }, grp.rows);
    grp.more = h('button', {
      type: 'button', class: 'btn btn--link btn--xs fgroup__more', 'aria-expanded': 'false',
      onClick: () => { grp.expanded = !grp.expanded; patchTagsVisibility(); },
    });
    grp.title = grp.key ? h('p', { class: 'tag-group__title' }, TAG_GROUP_LABELS[grp.key] || grp.key) : null;
  }
  const tagKeys = tagGroups.flatMap((g) => g.keys);
  const tagNodes = tagGroups.map((grp) => h('div', { class: 'tag-group' }, grp.title, grp.list, grp.more));
  function patchTagsVisibility() {
    const counts = globalTagCount();
    const live = tagGroups.filter((g) => g.keys.some((t) => counts[t]));
    for (const grp of tagGroups) {
      // Most frequent first (for the current kind selection); zero-count tags are hidden unless selected.
      const order = [...grp.keys].sort((a, b) => (counts[b] || 0) - (counts[a] || 0)
        || (dicts.tags[a]?.label || a).localeCompare(dicts.tags[b]?.label || b, 'pl'));
      const key = order.join('|');
      if (key !== grp.orderKey) {
        grp.orderKey = key;
        const focused = grp.list.contains(document.activeElement) ? document.activeElement : null;
        for (const t of order) grp.list.appendChild(refs.tags.get(t).row);
        focused?.focus({ preventScroll: true });
      }
      const shown = order.filter((t) => counts[t] || current?.tags.includes(t));
      grp.keys.forEach((t) => {
        const ref = refs.tags.get(t);
        const idx = shown.indexOf(t);
        ref.row.hidden = idx < 0 || (!grp.expanded && idx >= TAGS_VISIBLE && !current?.tags.includes(t));
      });
      grp.more.hidden = shown.length <= TAGS_VISIBLE;
      grp.more.setAttribute('aria-expanded', String(grp.expanded));
      grp.more.textContent = grp.expanded ? 'Pokaż mniej' : `Pokaż wszystkie (${shown.length})`;
      if (grp.title) grp.title.hidden = live.length < 2 || !shown.length;
    }
  }

  // --- list facets (Rozstrzygnięcie, Zakres robót, Kategoria obiektu, Źródło danych, Organ) ------
  const listGroups = new Map();
  for (const lf of LIST_FACETS) {
    const keys = Object.keys(dicts[lf.dict] || {});
    if (!keys.length) continue;
    const labelOf = (v) => {
      const d = dicts[lf.dict][v];
      return lf.key === 'categories' ? `${v} – ${d?.label || v}` : (d?.label || v);
    };
    const rows = keys.map((v) => checkboxRow(refs[lf.key], v, labelOf(v), {
      hint: dicts[lf.dict][v]?.description || null,
      onChange: (key, on) => ctx.onPatch({ [lf.key]: toggle(current[lf.key] || [], key, on) }),
    }));
    const list = h('div', { class: 'list-facet' }, rows);
    const state = { lf, keys, list, expanded: false, orderKey: null };
    state.more = lf.visible ? h('button', {
      type: 'button', class: 'btn btn--link btn--xs fgroup__more', 'aria-expanded': 'false',
      onClick: () => { state.expanded = !state.expanded; patchListGroup(state); },
    }) : null;
    const tip = lf.info ? infoTip(lf.info, lf.title) : null;
    const note = lf.note ? h('p', { class: 'fgroup__note fgroup__note--lead' }, lf.note) : null;
    state.el = group(lf.title, [note, list, state.more, tip ? tip.bubble : null], { hidden: true, extra: tip ? tip.btn : null });
    listGroups.set(lf.key, state);
  }
  function patchListGroup(state) {
    const { lf } = state;
    const counts = available?.[lf.field] || {};
    const selected = current?.[lf.key] || [];
    const order = lf.byCount
      ? [...state.keys].sort((a, b) => (counts[b] || 0) - (counts[a] || 0) || state.keys.indexOf(a) - state.keys.indexOf(b))
      : state.keys;
    const key = order.join('|');
    if (key !== state.orderKey) {
      state.orderKey = key;
      const focused = state.list.contains(document.activeElement) ? document.activeElement : null;
      for (const v of order) state.list.appendChild(refs[lf.key].get(v).row);
      focused?.focus({ preventScroll: true });
    }
    const shown = order.filter((v) => counts[v] || selected.includes(v));
    for (const v of state.keys) {
      const idx = shown.indexOf(v);
      refs[lf.key].get(v).row.hidden = idx < 0 || (lf.visible && !state.expanded && idx >= lf.visible && !selected.includes(v));
    }
    const kinds = effectiveKinds(current?.kinds);
    const permitsOn = kinds.some((k) => OPT_IN_KINDS.includes(k));
    const redundant = lf.sameAs && !selected.length && available?.same?.[lf.field];
    state.el.hidden = shown.length < lf.min || (lf.permitsOnly && !permitsOn && !selected.length) || Boolean(redundant);
    if (state.more) {
      state.more.hidden = shown.length <= lf.visible;
      state.more.setAttribute('aria-expanded', String(state.expanded));
      state.more.textContent = state.expanded ? 'Pokaż mniej' : `Pokaż wszystkie (${shown.length})`;
    }
  }

  // --- Wnioskodawca ------------------------------------------------------------------------------
  const applicantRows = ['person', 'organization', 'unknown'].map((a) => checkboxRow(refs.applicants, a, APPLICANT_LABELS[a], {
    iconName: a === 'person' ? 'user' : a === 'organization' ? 'building' : null,
    onChange: (key, on) => ctx.onPatch({ applicants: toggle(current.applicants, key, on) }),
  }));

  // --- Obszar ------------------------------------------------------------------------------------
  const areaKeys = Object.keys(dicts.areas || {}).filter((a) => !a.startsWith('_'))
    .sort((a, b) => (dicts.areas[a]?.label || a).localeCompare(dicts.areas[b]?.label || b, 'pl'));
  const areaRows = areaKeys.map((a) => checkboxRow(refs.areas, a, dicts.areas[a]?.label || a, {
    onChange: (key, on) => ctx.onPatch({ areas: toggle(current.areas, key, on) }),
  }));

  // --- Ulica -------------------------------------------------------------------------------------
  const streetList = h('ul', { class: 'mini-chips', 'aria-label': 'Wybrane ulice' });
  const combo = createCombobox({
    label: 'Ulica',
    placeholder: 'Wpisz nazwę ulicy…',
    emptyText: (q) => (q ? `Brak ulicy pasującej do „${q}”` : 'Brak ulic'),
    getOptions: (q) => streetOptions(q),
    onSelect: (key) => ctx.onPatch({ streets: [...current.streets.filter((s) => s !== key), key] }),
  });
  function streetOptions(q) {
    const fq = fold(q).trim();
    const out = [];
    for (const s of index.streets.values()) {
      if (current?.streets.includes(s.key)) continue;
      const count = facets?.streets?.[s.key] || 0;
      // Streets known only from records of switched-off kinds (e.g. permits) are not offered.
      if (!count) continue;
      const label = fold(s.label);
      let rank = -1;
      if (!fq) rank = 2;
      else if (label.startsWith(fq) || s.key.startsWith(fq)) rank = 0;
      else if (label.includes(` ${fq}`) || s.key.includes(` ${fq}`)) rank = 1;
      else if (label.includes(fq)) rank = 2;
      if (rank < 0) continue;
      out.push({ value: s.key, label: s.label, count, rank });
    }
    out.sort((a, b) => a.rank - b.rank || b.count - a.count || a.label.localeCompare(b.label, 'pl'));
    return out.slice(0, 8);
  }

  // --- Lokalizacja -------------------------------------------------------------------------------
  const geoRow = (() => {
    const m = new Map();
    const row = checkboxRow(m, 'geo', 'Tylko z lokalizacją na mapie', { onChange: (_k, on) => ctx.onPatch({ geoOnly: on }) });
    refs.geo = m.get('geo');
    return row;
  })();
  const bboxRow = (() => {
    const m = new Map();
    const row = checkboxRow(m, 'bbox', 'Tylko obszar widoczny na mapie', { onChange: (_k, on) => ctx.onPatch({ bbox: on ? 'VIEW' : null }) });
    refs.bbox = m.get('bbox');
    return row;
  })();
  const nearBody = h('div', { class: 'near' });
  const nearGroup = h('div', { class: 'near-wrap' },
    h('p', { class: 'field-label' }, 'W pobliżu punktu'), nearBody);
  // Both states are built once and patched in place (focus stays on a radius button after choosing it); only the
  // switch between "no point" and "point" swaps them – and "Usuń punkt" then hands the focus to "Moja lokalizacja".
  const locateBtn = h('button', { type: 'button', class: 'btn btn--secondary btn--sm', onClick: () => ctx.onLocate() }, icon('locate', { size: 15 }), 'Moja lokalizacja');
  const nearActions = h('div', { class: 'near__actions' }, locateBtn,
    h('button', { type: 'button', class: 'btn btn--secondary btn--sm', onClick: () => ctx.onPickPoint() }, icon('pin', { size: 15 }), 'Wskaż na mapie'));
  const radiusBtns = NEAR_RADII.map((r) => {
    const count = h('span', { class: 'count' });
    const b = h('button', {
      type: 'button', class: 'seg__btn', 'aria-pressed': 'false', 'data-r': String(r),
      onClick: () => ctx.onPatch({ near: { ...current.near, r } }),
    }, formatDistance(r), count);
    return { r, b, count };
  });
  let removedPoint = false;
  const nearPoint = [
    h('div', { class: 'seg seg--radius', role: 'group', 'aria-label': 'Promień' }, radiusBtns.map((x) => x.b)),
    h('p', { class: 'fgroup__note' }, 'Punkt zapisujemy w adresie strony z dokładnością ok. 100 m.'),
    h('button', {
      type: 'button', class: 'btn btn--link btn--xs',
      onClick: () => { removedPoint = true; ctx.onPatch({ near: null }); },
    }, icon('x', { size: 14 }), 'Usuń punkt'),
  ];
  let nearMode = null;

  function renderNear() {
    const near = current.near;
    const mode = near ? 'point' : 'none';
    if (mode !== nearMode) {
      const hadFocus = nearBody.contains(document.activeElement);
      nearMode = mode;
      replaceChildren(nearBody, near ? nearPoint : nearActions);
      if (!near && (removedPoint || hadFocus)) locateBtn.focus({ preventScroll: true });
      removedPoint = false;
    }
    if (!near) return;
    for (const { r, b, count } of radiusBtns) {
      b.setAttribute('aria-pressed', String(near.r === r));
      count.textContent = formatNumber(facets?.nearRadii?.[r] || 0);
    }
  }

  // --- Plik źródłowy (only when filtered by file) -----------------------------------------------
  const fileBody = h('div', { class: 'file-filter' });
  const fileGroup = group('Plik źródłowy', fileBody, { hidden: true });

  // --- assemble ----------------------------------------------------------------------------------
  const clearAll = h('button', { type: 'button', class: 'btn btn--link btn--sm', hidden: true, onClick: () => ctx.onPatch('CLEAR') }, 'Wyczyść');
  const closeBtn = h('button', { type: 'button', class: 'btn btn--icon filters__close', 'aria-label': 'Zamknij filtry', onClick: () => ctx.onClose() }, icon('x', { size: 20 }));
  const showBtn = h('button', { type: 'button', class: 'btn btn--primary btn--block', onClick: () => ctx.onShowResults() }, 'Pokaż wyniki');
  const lg = (key) => listGroups.get(key)?.el || null;

  const el = h('div', { class: 'filters__inner' },
    h('div', { class: 'filters__head' }, h('h2', { class: 'filters__title', id: 'filters-title', tabindex: '-1' }, icon('sliders', { size: 18 }), 'Filtry'), clearAll, closeBtn),
    h('div', { class: 'filters__body' },
      fileGroup,
      group('Rodzaj', kindRows, { extra: kindsReset }),
      group('Okres', [presetRow, yearRow, rangeRow, periodNote]),
      lg('outcomes'),
      tagKeys.length ? group('Typ inwestycji', tagNodes) : null,
      lg('scopes'),
      lg('categories'),
      group('Wnioskodawca', applicantRows),
      areaKeys.length ? group('Obszar', areaRows) : null,
      index.streets.size ? group('Ulica', [combo.el, streetList]) : null,
      lg('datasets'),
      lg('issuers'),
      group('Lokalizacja', [geoRow, bboxRow, nearGroup]),
      h('p', { class: 'filters__note' }, icon('info', { size: 14 }), UNOFFICIAL)),
    h('div', { class: 'filters__foot' }, showBtn));

  function patchRow(ref, checked, count, { estimate = false } = {}) {
    ref.input.checked = checked;
    ref.count.textContent = formatNumber(count);
    ref.srCount.textContent = estimate ? ` (łącznie ${formatNumber(count)})` : ` (${formatNumber(count)})`;
    ref.count.classList.toggle('is-estimate', estimate);
    ref.count.title = estimate ? 'Liczba wszystkich wpisów w rejestrze – dokładne liczby po włączeniu' : '';
    ref.row.classList.toggle('is-zero', !count && !checked);
    ref.row.classList.toggle('is-checked', checked);
  }

  function renderPermitsStatus() {
    if (!optKinds.length) return;
    if (permitsState === 'loading') {
      replaceChildren(permitsStatus, h('span', { class: 'spinner', 'aria-hidden': 'true' }), 'Wczytywanie rejestru…');
    } else if (permitsState === 'error') {
      replaceChildren(permitsStatus, icon('alert', { size: 14 }), 'Nie udało się wczytać rejestru. ',
        ctx.onRetryPermits ? h('button', { type: 'button', class: 'btn btn--link btn--xs', onClick: () => ctx.onRetryPermits() }, 'Spróbuj ponownie') : null);
    } else {
      permitsStatus.textContent = '';
    }
    permitsStatus.hidden = !permitsStatus.textContent;
  }

  return {
    el,
    combo,
    /** Month axis changed (kind selection with another time span, or permits loaded). */
    setBounds(b) {
      if (b.min === bounds.min && b.max === bounds.max) return;
      setBounds(b);
      if (current && facets) this.update(current, facets, null);
    },
    /** Month windows of a relative preset per kind group (filters.periodSpans), set before update(). */
    setPeriodSpans(next) {
      spans = Array.isArray(next) ? next : null;
    },
    /** 'idle' | 'loading' | 'loaded' | 'error' — state of the lazily loaded permits layer. */
    setPermitsState(s) {
      permitsState = s;
      availableKey = null;
      renderPermitsStatus();
    },
    /**
     * @param {object} f current filters
     * @param {object} fc facets from filters.evaluate
     * @param {number|null} resultCount (null keeps the button label)
     */
    update(f, fc, resultCount) {
      current = f;
      facets = fc;
      const kinds = effectiveKinds(f.kinds);
      const key = `${kinds.join(',')}|${index.entries.length}`;
      if (key !== availableKey) {
        availableKey = key;
        available = availableOptions(index.entries, kinds);
        available.same = Object.fromEntries(LIST_FACETS.filter((lf) => lf.sameAs)
          .map((lf) => [lf.field, sameSplit(index.entries, kinds, lf.field, lf.sameAs)]));
      }
      for (const [k, ref] of refs.kinds) {
        const estimate = OPT_IN_KINDS.includes(k) && !index.permitsLoaded;
        patchRow(ref, kinds.includes(k), estimate ? (index.countsByKind[k] || 0) : (fc.kinds[k] || 0), { estimate });
        // A kind known only from the dictionary, with no records anywhere, is hidden (unless selected).
        ref.row.hidden = !kinds.includes(k) && !estimate && !index.kindMonths[k];
      }
      kindsReset.hidden = sameKinds(kinds, DEFAULT_KINDS);
      for (const [t, ref] of refs.tags) patchRow(ref, f.tags.includes(t), fc.tags[t] || 0);
      for (const [a, ref] of refs.applicants) {
        patchRow(ref, f.applicants.includes(a), fc.applicants[a] || 0);
        if (a === 'unknown') ref.row.hidden = !(fc.applicants.unknown || f.applicants.includes('unknown'));
      }
      for (const [a, ref] of refs.areas) patchRow(ref, f.areas.includes(a), fc.areas[a] || 0);
      for (const state of listGroups.values()) {
        const { lf } = state;
        for (const [v, ref] of refs[lf.key]) patchRow(ref, (f[lf.key] || []).includes(v), fc[lf.field]?.[v] || 0);
        patchListGroup(state);
      }
      patchRow(refs.geo, f.geoOnly, fc.geo);
      patchRow(refs.bbox, Boolean(f.bbox), fc.bbox);
      patchTagsVisibility();
      // period
      const custom = !f.period && (f.from || f.to);
      for (const [pk, b] of presetBtns) b.setAttribute('aria-pressed', String(pk === null ? !f.period && !f.from && !f.to : f.period === pk));
      const yearCounts = {};
      for (const [m, c] of Object.entries(fc.months)) {
        const y = m.slice(0, 4);
        yearCounts[y] = (yearCounts[y] || 0) + Object.values(c).reduce((a, b) => a + b, 0);
      }
      for (const [y, { b, count }] of yearBtns) {
        b.setAttribute('aria-pressed', String(Boolean(custom) && f.from === `${y}-01` && f.to === `${y}-12`));
        count.textContent = formatNumber(yearCounts[y] || 0);
        b.classList.toggle('is-zero', !yearCounts[y]);
      }
      const resolved = shownRange(f);
      fromSel.value = resolved.from && months.includes(resolved.from) ? resolved.from : '';
      toSel.value = resolved.to && months.includes(resolved.to) ? resolved.to : '';
      // A preset counts back per kind group (planning lists vs the GUNB register): name both windows when they differ.
      const kindNames = (ks) => ks.map((k) => dicts.kinds?.[k]?.short || k).join(', ');
      periodNote.textContent = !f.period
        ? (bounds.max ? `Najnowszy miesiąc w danych: ${formatMonth(bounds.max)}.` : '')
        : spans && spans.length > 1
          ? `${spans.map((x) => `${kindNames(x.kinds)}: ${formatMonthRange(x.from, x.to)}`).join(' · ')} – każdy rodzaj liczony od swojego najnowszego miesiąca.`
          : `${formatMonthRange(resolved.from, resolved.to)} – licząc od najnowszego miesiąca w danych (${formatMonth(resolved.to || bounds.max)}).`;
      // streets
      replaceChildren(streetList, f.streets.map((s) => {
        const label = index.streets.get(s)?.label || s;
        return h('li', null, h('span', { class: 'mini-chip' }, h('span', null, label), h('span', { class: 'count' }, formatNumber(fc.streets[s] || 0)),
          h('button', {
            type: 'button', class: 'mini-chip__x', 'aria-label': `Usuń ulicę ${label}`,
            onClick: () => { ctx.onPatch({ streets: f.streets.filter((x) => x !== s) }); combo.input.focus(); },
          }, icon('x', { size: 12 }))));
      }));
      combo.refresh();
      renderNear();
      // file
      fileGroup.hidden = !f.file;
      if (f.file) {
        const file = index.filesById.get(f.file);
        replaceChildren(fileBody,
          h('p', { class: 'file-filter__name' }, icon('sheet', { size: 15 }), file?.filename || f.file),
          h('button', { type: 'button', class: 'btn btn--link btn--xs', onClick: () => ctx.onPatch({ file: null }) }, icon('x', { size: 14 }), 'Pokaż wszystkie pliki'));
      }
      clearAll.hidden = !hasActiveFilters(f);
      if (resultCount != null) showBtn.textContent = resultCount ? `Pokaż ${plural(resultCount, WPIS)}` : 'Brak wyników – zmień filtry';
    },
  };
}

function toggle(arr, key, on) {
  const set = new Set(arr);
  if (on) set.add(key); else set.delete(key);
  return [...set];
}
