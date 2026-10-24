/**
 * Timeline histogram: entries per month, stacked by kind, reflecting all filters except the period.
 * Click a month or drag across months to select a range. Fully keyboard operable:
 *   ←/→ move the cursor month, Shift+←/→ extend a range, Home/End jump, Enter applies,
 *   Esc clears the period filter. A data table view is available as the accessible alternative.
 */
import { h, replaceChildren } from '../dom.js';
import { icon, kindGlyph } from '../icons.js';
import { formatMonth, formatMonthShort, formatMonthRange, formatNumber, monthRange, plural, WPIS } from '../format.js';

const SVGNS = 'http://www.w3.org/2000/svg';
const CHART_H = 56;
const AXIS_H = 18;

function svg(tag, attrs = {}) {
  const el = document.createElementNS(SVGNS, tag);
  for (const [k, v] of Object.entries(attrs)) if (v != null) el.setAttribute(k, String(v));
  return el;
}

/** Path for a rect with rounded top corners only (data-end rounded, square at the baseline). */
function topRoundedRect(x, y, w, hgt, r) {
  const rr = Math.max(0, Math.min(r, w / 2, hgt));
  return `M${x},${y + hgt}V${y + rr}Q${x},${y} ${x + rr},${y}H${x + w - rr}Q${x + w},${y} ${x + w},${y + rr}V${y + hgt}Z`;
}

/**
 * @param {{
 *   kinds: string[], kindLabel: (k: string) => string,
 *   onSelect: (from: string, to: string) => void, onClear: () => void,
 * }} cfg
 */
export function createTimeline(cfg) {
  let kinds = [...cfg.kinds];
  const legend = h('ul', { class: 'timeline__legend', 'aria-label': 'Legenda' });
  const renderLegend = () => replaceChildren(legend, kinds.map((k) => h('li', null, kindGlyph(k), cfg.kindLabel(k))));
  renderLegend();
  const status = h('p', { class: 'timeline__status' });
  const tableBtn = h('button', {
    type: 'button', class: 'btn btn--ghost btn--xs', 'aria-expanded': 'false',
    onClick: () => toggleTable(),
  }, icon('table', { size: 14 }), h('span', null, 'Tabela'));
  const live = h('p', { class: 'sr-only', 'aria-live': 'polite' });
  const chart = h('div', {
    class: 'timeline__chart', tabindex: '0', role: 'group',
    'aria-roledescription': 'histogram',
    'aria-label': 'Liczba wpisów w kolejnych miesiącach. Strzałki w lewo i w prawo wybierają miesiąc, Shift ze strzałką rozszerza zakres, Enter filtruje, Escape czyści okres.',
  });
  const tip = h('div', { class: 'timeline__tip', hidden: true, 'aria-hidden': 'true' });
  const tableWrap = h('div', { class: 'timeline__table', hidden: true });
  const root = h('section', { class: 'timeline', 'aria-label': 'Oś czasu' },
    h('div', { class: 'timeline__head' },
      h('h2', { class: 'timeline__title' }, 'Wpisy w czasie'), legend,
      h('div', { class: 'timeline__right' }, status, tableBtn)),
    h('div', { class: 'timeline__body' }, chart, tip),
    live, tableWrap);

  let data = { months: [], counts: {}, from: null, to: null };
  let width = 0;
  let cursor = -1; // keyboard cursor index
  let anchor = -1; // drag / shift-range anchor index
  let drag = null; // {start, end}
  let hover = -1;

  const ro = new ResizeObserver(() => {
    const w = chart.clientWidth;
    if (w && Math.abs(w - width) > 1) { width = w; draw(); }
  });
  ro.observe(chart);

  function totalOf(m) {
    const c = data.counts[m];
    if (!c) return 0;
    let t = 0;
    for (const k of kinds) t += c[k] || 0;
    return t;
  }

  function selectedRange() {
    if (drag) return [Math.min(drag.start, drag.end), Math.max(drag.start, drag.end)];
    if (!data.from && !data.to) return null;
    const a = data.from ? data.months.indexOf(data.from) : 0;
    const b = data.to ? data.months.indexOf(data.to) : data.months.length - 1;
    const lo = a < 0 ? (data.from < data.months[0] ? 0 : data.months.length) : a;
    const hi = b < 0 ? (data.to > data.months[data.months.length - 1] ? data.months.length - 1 : -1) : b;
    return [lo, hi];
  }

  function draw() {
    const n = data.months.length;
    if (!n || !width) { chart.textContent = ''; return; }
    const slot = width / n;
    const gapX = slot >= 6 ? 1 : 0.5;
    const barW = Math.max(1, Math.min(24, slot - gapX * 2));
    const max = Math.max(1, ...data.months.map(totalOf));
    const sel = selectedRange();
    const s = svg('svg', {
      width, height: CHART_H + AXIS_H, viewBox: `0 0 ${width} ${CHART_H + AXIS_H}`, class: 'timeline__svg', 'aria-hidden': 'true',
    });
    if (sel && sel[0] <= sel[1]) {
      s.appendChild(svg('rect', {
        x: sel[0] * slot, y: 0, width: (sel[1] - sel[0] + 1) * slot, height: CHART_H, class: 'timeline__band', rx: 3,
      }));
    }
    if (hover >= 0 || cursor >= 0) {
      const i = hover >= 0 ? hover : cursor;
      s.appendChild(svg('rect', { x: i * slot, y: 0, width: slot, height: CHART_H, class: 'timeline__hover' }));
    }
    s.appendChild(svg('line', { x1: 0, x2: width, y1: CHART_H + 0.5, y2: CHART_H + 0.5, class: 'timeline__base' }));
    const gapY = 1;
    data.months.forEach((m, i) => {
      const c = data.counts[m] || {};
      const total = totalOf(m);
      if (!total) return;
      const dim = sel && (i < sel[0] || i > sel[1]);
      const g = svg('g', { class: dim ? 'is-dim' : null });
      const x = i * slot + (slot - barW) / 2;
      const fullH = Math.max(3, (total / max) * (CHART_H - 4));
      let y = CHART_H;
      const segs = kinds.filter((k) => c[k]);
      segs.forEach((k, si) => {
        let hgt = (c[k] / total) * fullH;
        const isTop = si === segs.length - 1;
        if (!isTop) hgt = Math.max(1, hgt - gapY);
        y -= hgt;
        const r = isTop ? Math.min(3, barW / 2) : 0;
        g.appendChild(svg('path', { d: topRoundedRect(x, y, barW, hgt, r), class: `timeline__bar timeline__bar--${k}` }));
        if (!isTop) y -= gapY;
      });
      s.appendChild(g);
    });
    // Year ticks
    let lastLabelX = -100;
    data.months.forEach((m, i) => {
      if (!(m.endsWith('-01') || i === 0)) return;
      const x = i * slot;
      if (m.endsWith('-01')) s.appendChild(svg('line', { x1: x + 0.5, x2: x + 0.5, y1: CHART_H, y2: CHART_H + 4, class: 'timeline__tick' }));
      const label = m.slice(0, 4);
      const lx = m.endsWith('-01') ? x + 2 : x;
      if (lx - lastLabelX < 34) return;
      if (lx > width - 26) return;
      const t = svg('text', { x: lx, y: CHART_H + 14, class: 'timeline__year' });
      t.textContent = label;
      s.appendChild(t);
      lastLabelX = lx;
    });
    chart.replaceChildren(s);
  }

  function indexAt(clientX) {
    const rect = chart.getBoundingClientRect();
    const n = data.months.length;
    const i = Math.floor(((clientX - rect.left) / rect.width) * n);
    return Math.max(0, Math.min(n - 1, i));
  }

  function describe(i) {
    const m = data.months[i];
    const c = data.counts[m] || {};
    const parts = kinds.filter((k) => c[k]).map((k) => `${cfg.kindLabel(k)}: ${c[k]}`);
    return `${formatMonth(m, { capitalize: true })} – ${plural(totalOf(m), WPIS)}${parts.length ? ` (${parts.join(', ')})` : ''}`;
  }

  function showTip(i) {
    if (i < 0) { tip.hidden = true; return; }
    const m = data.months[i];
    const c = data.counts[m] || {};
    replaceChildren(tip,
      h('div', { class: 'timeline__tip-total' }, h('strong', null, formatNumber(totalOf(m))), ` ${plural(totalOf(m), WPIS).replace(/^\S+\s/, '')}`),
      h('div', { class: 'timeline__tip-month' }, formatMonth(m, { capitalize: true })),
      kinds.filter((k) => c[k]).map((k) => h('div', { class: 'timeline__tip-row' },
        h('span', { class: `timeline__key timeline__key--${k}` }), h('strong', null, formatNumber(c[k])), ' ', cfg.kindLabel(k))));
    tip.hidden = false;
    const n = data.months.length;
    const x = ((i + 0.5) / n) * chart.clientWidth;
    const tw = tip.offsetWidth || 140;
    tip.style.left = `${Math.max(0, Math.min(chart.clientWidth - tw, x - tw / 2))}px`;
  }

  chart.addEventListener('pointerdown', (e) => {
    if (e.button !== 0 || !data.months.length) return;
    const i = indexAt(e.clientX);
    drag = { start: i, end: i };
    chart.setPointerCapture(e.pointerId);
    draw();
  });
  chart.addEventListener('pointermove', (e) => {
    if (!data.months.length) return;
    clearTimeout(leaveTimer);
    const i = indexAt(e.clientX);
    if (drag) drag.end = i;
    if (i !== hover || drag) { hover = i; draw(); showTip(i); }
  });
  chart.addEventListener('pointerup', (e) => {
    if (!drag) return;
    const a = Math.min(drag.start, drag.end);
    const b = Math.max(drag.start, drag.end);
    drag = null;
    try { chart.releasePointerCapture(e.pointerId); } catch { /* not captured */ }
    commit(a, b);
  });
  chart.addEventListener('pointercancel', () => { drag = null; draw(); });
  // The tip is hoverable (WCAG 1.4.13): moving the pointer onto it keeps it; leaving both hides it (after a moment,
  // so the pointer can cross the small gap between the chart and the tip).
  let leaveTimer = null;
  const leave = () => { if (!drag) { hover = -1; tip.hidden = true; draw(); } };
  const leaveSoon = () => { clearTimeout(leaveTimer); leaveTimer = setTimeout(leave, 200); };
  const stay = () => clearTimeout(leaveTimer);
  chart.addEventListener('pointerenter', stay);
  tip.addEventListener('pointerenter', stay);
  chart.addEventListener('pointerleave', (e) => { if (!(e.relatedTarget && tip.contains(e.relatedTarget))) leaveSoon(); });
  tip.addEventListener('pointerleave', (e) => { if (!(e.relatedTarget && chart.contains(e.relatedTarget))) leaveSoon(); });

  function commit(a, b) {
    const from = data.months[a];
    const to = data.months[b];
    if (a === b && data.from === from && data.to === to) {
      cfg.onClear();
      return;
    }
    cfg.onSelect(from, to);
  }

  chart.addEventListener('focus', () => {
    if (cursor < 0) {
      const sel = selectedRange();
      cursor = sel ? Math.max(0, Math.min(data.months.length - 1, sel[1])) : data.months.length - 1;
    }
    draw();
    showTip(cursor);
    live.textContent = describe(cursor);
  });
  chart.addEventListener('blur', () => { anchor = -1; tip.hidden = true; const c = cursor; cursor = -1; if (c >= 0) draw(); });
  chart.addEventListener('keydown', (e) => {
    const n = data.months.length;
    if (!n) return;
    let next = cursor;
    switch (e.key) {
      case 'ArrowLeft': next = Math.max(0, cursor - 1); break;
      case 'ArrowRight': next = Math.min(n - 1, cursor + 1); break;
      case 'Home': next = 0; break;
      case 'End': next = n - 1; break;
      case 'PageUp': next = Math.max(0, cursor - 12); break;
      case 'PageDown': next = Math.min(n - 1, cursor + 12); break;
      case 'Enter':
      case ' ':
        e.preventDefault();
        if (anchor >= 0) commit(Math.min(anchor, cursor), Math.max(anchor, cursor));
        else commit(cursor, cursor);
        anchor = -1;
        return;
      case 'Escape':
        if (data.from || data.to) { e.preventDefault(); e.stopPropagation(); cfg.onClear(); }
        else if (!tip.hidden) { e.preventDefault(); e.stopPropagation(); tip.hidden = true; }
        anchor = -1;
        return;
      default: return;
    }
    e.preventDefault();
    if (e.shiftKey) {
      if (anchor < 0) anchor = cursor;
    } else {
      anchor = -1;
    }
    cursor = next;
    drag = anchor >= 0 ? { start: anchor, end: cursor } : null;
    draw();
    drag = null;
    showTip(cursor);
    live.textContent = anchor >= 0
      ? `Zakres: ${formatMonthRange(data.months[Math.min(anchor, cursor)], data.months[Math.max(anchor, cursor)])}. Enter, aby zastosować.`
      : describe(cursor);
  });

  function toggleTable(force) {
    const open = force ?? tableWrap.hidden;
    tableWrap.hidden = !open;
    tableBtn.setAttribute('aria-expanded', String(open));
    if (open) renderTable();
  }

  function renderTable() {
    const rows = data.months.filter((m) => totalOf(m) > 0).reverse();
    // The month itself is the button that selects it (no separate action column: with five kinds the table
    // must still fit the results column).
    replaceChildren(tableWrap, h('table', { class: ['table table--compact', kinds.length > 3 && 'table--dense'] },
      h('caption', { class: 'sr-only' }, 'Liczba wpisów w miesiącach (z uwzględnieniem pozostałych filtrów); kliknij miesiąc, aby go wybrać'),
      h('thead', null, h('tr', null, h('th', { scope: 'col' }, 'Miesiąc'),
        kinds.map((k) => h('th', { scope: 'col', class: 'num' }, cfg.kindLabel(k))), h('th', { scope: 'col', class: 'num' }, 'Razem'))),
      h('tbody', null, rows.length ? rows.map((m) => h('tr', null,
        h('th', { scope: 'row' }, h('button', {
          type: 'button', class: 'btn btn--link btn--xs timeline__month', onClick: () => cfg.onSelect(m, m),
          title: `Pokaż wpisy z miesiąca: ${formatMonth(m)}`,
        }, formatMonth(m, { capitalize: true }))),
        kinds.map((k) => h('td', { class: 'num' }, formatNumber(data.counts[m]?.[k] || 0))),
        h('td', { class: 'num' }, formatNumber(totalOf(m))))) : h('tr', null, h('td', { colspan: kinds.length + 2 }, 'Brak wpisów.')))));
  }

  return {
    el: root,
    /** Kinds stacked in the bars and named in the legend (the current kind selection, in display order). */
    setKinds(next) {
      if (next.join() === kinds.join()) return;
      kinds = [...next];
      renderLegend();
      draw();
      if (!tableWrap.hidden) renderTable();
    },
    /**
     * @param {{min: string, max: string, counts: object, from: string|null, to: string|null}} d
     */
    update(d) {
      data = { months: monthRange(d.min, d.max), counts: d.counts || {}, from: d.from, to: d.to };
      if (cursor >= data.months.length) cursor = data.months.length - 1;
      replaceChildren(status, d.from || d.to
        ? [h('span', { class: 'timeline__sel' }, icon('calendar', { size: 14 }), formatMonthRange(d.from, d.to)),
          h('button', { type: 'button', class: 'btn btn--ghost btn--xs btn--icon', onClick: () => cfg.onClear(), 'aria-label': 'Wyczyść okres' }, icon('x', { size: 14 }))]
        : h('span', { class: 'timeline__hint' }, 'Kliknij lub przeciągnij, aby wybrać okres'));
      width = chart.clientWidth || width;
      draw();
      if (!tableWrap.hidden) renderTable();
      if (cursor >= 0 && document.activeElement === chart) showTip(cursor);
    },
    /** Hide the hover/focus tip (Esc); true when it was shown. */
    hideTip() {
      if (tip.hidden) return false;
      tip.hidden = true;
      hover = -1;
      draw();
      return true;
    },
    /** Short summary for screen readers / tests. */
    describeMonth: (m) => formatMonthShort(m),
  };
}
