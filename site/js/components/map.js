/* global L */
/**
 * Leaflet map: clustered markers per record (shape + colour by kind, hollow when approximate),
 * parcel highlight for the selected record, district/neighbourhood outlines, GUGiK WMS layers,
 * "near me" circle, visible-area filter toggle and a legend.
 * Leaflet 1.9.4 and Leaflet.markercluster 1.5.3 are vendored globals (site/vendor/).
 */
import { h, mq, prefersReducedMotion, replaceChildren } from '../dom.js';
import { icon, kindGlyph, shapeOf } from '../icons.js';
import { MAP_CENTER, MAP_ZOOM, BASEMAP, WMS } from '../config.js';
import { formatDate, formatMonth, plural, WPIS } from '../format.js';

const KIND_CLASS = (k) => (/^[a-z]+$/.test(k || '') ? k : 'other');

/** Markers closer than this (degrees, ≈ 1 m) count as one place: such clusters open a list instead of zooming. */
const SAME_SPOT = 1e-5;

/** Do all these markers sit on (practically) the same point? Pure; exported for tests. */
export function sameSpot(latlngs) {
  if (latlngs.length < 2) return false;
  let minLat = Infinity;
  let maxLat = -Infinity;
  let minLon = Infinity;
  let maxLon = -Infinity;
  for (const p of latlngs) {
    const lat = Array.isArray(p) ? p[0] : p.lat;
    const lon = Array.isArray(p) ? p[1] : p.lng;
    if (lat < minLat) minLat = lat;
    if (lat > maxLat) maxLat = lat;
    if (lon < minLon) minLon = lon;
    if (lon > maxLon) maxLon = lon;
  }
  return maxLat - minLat <= SAME_SPOT && maxLon - minLon <= SAME_SPOT;
}

function cssVar(name, fallback) {
  const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return v || fallback;
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);
}

/**
 * @param {HTMLElement} el
 * @param {{
 *   kinds: string[], kindShort: (k: string) => string, kindLabel: (k: string) => string,
 *   onSelect: (id: string) => void, onHover: (id: string|null) => void,
 *   onMoveEnd: (bbox: number[]) => void, onToggleBbox: (on: boolean) => void,
 *   onLocate: () => void, onUserMove?: () => void,
 * }} cfg
 */
export function createMap(el, cfg) {
  if (typeof L === 'undefined') throw new Error('Leaflet not loaded');
  // A focused marker is panned clear of the map controls below (Leaflet's own auto-pan pads only by the icon size,
  // leaving keyboard focus under the legend or the attribution). Applies to cluster markers as well.
  L.Marker.prototype.options.autoPanOnFocus = false;
  const map = L.map(el, {
    zoomControl: false,
    minZoom: 10,
    maxZoom: 19,
    zoomSnap: 0.5,
    worldCopyJump: false,
    fadeAnimation: !prefersReducedMotion(),
    zoomAnimation: !prefersReducedMotion(),
    markerZoomAnimation: !prefersReducedMotion(),
  }).setView(MAP_CENTER, MAP_ZOOM);
  map.attributionControl.setPrefix('<a href="https://leafletjs.com" title="Biblioteka map">Leaflet</a>');

  const darkMq = mq('(prefers-color-scheme: dark)');
  const base = L.tileLayer(BASEMAP.url, {
    attribution: BASEMAP.attribution, maxZoom: 20, maxNativeZoom: BASEMAP.maxNativeZoom || 19,
    className: BASEMAP.muted ? 'tiles-muted' : '',
  }).addTo(map);
  darkMq.addEventListener('change', () => restyleVectors());
  const ortho = L.tileLayer.wms(WMS.ortho.url, {
    layers: WMS.ortho.layers, format: WMS.ortho.format, version: '1.3.0', attribution: WMS.ortho.attribution, maxZoom: 20,
  });
  const parcelsWms = L.tileLayer.wms(WMS.parcels.url, {
    layers: WMS.parcels.layers, format: WMS.parcels.format, transparent: true, version: '1.3.0',
    minZoom: WMS.parcels.minZoom, maxZoom: 20, attribution: WMS.parcels.attribution,
  });
  const areasLayer = L.layerGroup().addTo(map);
  const districtLayer = L.layerGroup().addTo(map);

  L.control.zoom({ position: 'topright', zoomInTitle: 'Przybliż', zoomOutTitle: 'Oddal' }).addTo(map);
  const layersControl = L.control.layers(
    { 'Mapa (OpenStreetMap)': base, 'Ortofotomapa (GUGiK)': ortho },
    { 'Granice działek (GUGiK) – widoczne po przybliżeniu': parcelsWms },
    { position: 'topright', collapsed: true },
  ).addTo(map);
  const layersToggle = el.querySelector('.leaflet-control-layers-toggle');
  if (layersToggle) {
    layersToggle.setAttribute('title', 'Warstwy mapy');
    layersToggle.setAttribute('aria-label', 'Warstwy mapy');
    layersToggle.setAttribute('role', 'button');
    layersToggle.setAttribute('aria-expanded', 'false');
    // Keyboard: Enter expands the list (Leaflet hides the toggle then) – focus goes to the first layer instead of
    // <body>; Esc or leaving the list collapses it and returns the focus to the toggle.
    const box = layersControl.getContainer();
    // Leaflet expands/collapses on hover, click and map clicks too: mirror its class into aria-expanded.
    new MutationObserver(() => {
      layersToggle.setAttribute('aria-expanded', String(box.classList.contains('leaflet-control-layers-expanded')));
    }).observe(box, { attributes: true, attributeFilter: ['class'] });
    layersToggle.addEventListener('keydown', (ev) => {
      if (ev.key !== 'Enter' && ev.key !== ' ') return;
      ev.preventDefault();
      layersControl.expand();
      requestAnimationFrame(() => box.querySelector('.leaflet-control-layers-selector')?.focus({ preventScroll: true }));
    });
    box.addEventListener('keydown', (ev) => {
      if (ev.key !== 'Escape' || !box.classList.contains('leaflet-control-layers-expanded')) return;
      ev.preventDefault();
      ev.stopPropagation();
      layersControl.collapse();
      layersToggle.focus({ preventScroll: true });
    });
    box.addEventListener('focusout', (ev) => {
      if (ev.relatedTarget && !box.contains(ev.relatedTarget)) layersControl.collapse();
    });
  }

  // --- top-left controls: near me + visible-area filter -------------------------------------------
  const bboxInput = h('input', { type: 'checkbox', id: 'map-bbox-toggle' });
  const bboxCount = h('span', { class: 'count' });
  const locateBtn = h('button', { type: 'button', class: 'map-btn', title: 'Pokaż wpisy w pobliżu mojej lokalizacji' },
    icon('locate', { size: 16 }), h('span', null, 'W pobliżu mnie'));
  const tools = h('div', { class: 'map-tools leaflet-bar-like' },
    locateBtn,
    h('label', { class: 'map-btn map-btn--check', for: 'map-bbox-toggle' }, bboxInput,
      h('span', null, 'Tylko widoczny obszar'), bboxCount));
  L.DomEvent.disableClickPropagation(tools);
  L.DomEvent.disableScrollPropagation(tools);
  locateBtn.addEventListener('click', () => cfg.onLocate());
  bboxInput.addEventListener('change', () => cfg.onToggleBbox(bboxInput.checked));
  const ToolsControl = L.Control.extend({ onAdd: () => tools });
  new ToolsControl({ position: 'topleft' }).addTo(map);

  // --- legend (kinds of the current selection; updated by setLegendKinds) ---------------------------
  // The cluster ring and its spoken mix follow the same list, so kinds switched on after the map was created
  // (building permits) get their colour instead of the neutral remainder.
  let ringKinds = [...cfg.kinds];
  const legendGlyphs = h('span', { class: 'map-legend__glyphs', 'aria-hidden': 'true' });
  const legendKinds = h('ul', { class: 'map-legend__kinds' });
  const legend = h('details', { class: 'map-legend' },
    h('summary', null, legendGlyphs, 'Legenda', icon('chevronDown', { size: 14, class: 'map-legend__chev' })),
    legendKinds,
    h('ul', null,
      h('li', null, kindGlyph('any', { approx: true }), 'lokalizacja przybliżona'),
      h('li', null, h('span', { class: 'legend-cluster', 'aria-hidden': 'true' }), 'grupa – pierścień pokazuje rodzaje'),
      h('li', null, h('span', { class: 'legend-swatch legend-swatch--parcel', 'aria-hidden': 'true' }), 'działka zaznaczonego wpisu'),
      h('li', { class: 'legend-areas', hidden: true }, h('span', { class: 'legend-swatch legend-swatch--area', 'aria-hidden': 'true' }), 'granice osiedli')));
  function setLegendKinds(kinds) {
    ringKinds = [...kinds];
    replaceChildren(legendGlyphs, kinds.map((k) => kindGlyph(k)));
    replaceChildren(legendKinds, kinds.map((k) => h('li', null, kindGlyph(k), cfg.kindLabel(k))));
  }
  setLegendKinds(cfg.kinds);
  L.DomEvent.disableClickPropagation(legend);
  const LegendControl = L.Control.extend({ onAdd: () => legend });
  new LegendControl({ position: 'bottomleft' }).addTo(map);

  // --- markers ------------------------------------------------------------------------------------
  const cluster = L.markerClusterGroup({
    showCoverageOnHover: false,
    // Both off: the plugin's own click handler stays unbound; onCluster() below zooms, spiderfies or – for
    // markers on one point – opens a list.
    spiderfyOnMaxZoom: false,
    zoomToBoundsOnClick: false,
    maxClusterRadius: (z) => (z >= 16 ? 28 : 44),
    chunkedLoading: true,
    animate: !prefersReducedMotion(),
    iconCreateFunction(c) {
      const kids = c.getAllChildMarkers();
      const n = kids.length;
      const counts = {};
      for (const m of kids) counts[m.options.kind] = (counts[m.options.kind] || 0) + 1;
      let acc = 0;
      const stops = [];
      // Kinds of the selection first (legend order), then any other kind present (never a grey remainder).
      const order = [...ringKinds, ...Object.keys(counts).filter((k) => k !== 'undefined' && !ringKinds.includes(k)).sort()];
      for (const k of order) {
        if (!counts[k]) continue;
        const start = (acc / n) * 100;
        acc += counts[k];
        stops.push(`var(--c-${KIND_CLASS(k)}) ${start.toFixed(2)}% ${((acc / n) * 100).toFixed(2)}%`);
      }
      if (acc < n) stops.push(`var(--text-3) ${((acc / n) * 100).toFixed(2)}% 100%`);
      const size = n < 10 ? 34 : n < 50 ? 40 : 46;
      const here = sameSpot(kids.map((m) => m.getLatLng()));
      const mix = order.filter((k) => counts[k]).map((k) => `${counts[k]} ${cfg.kindShort(k)}`).join(', ');
      return L.divIcon({
        className: `cl-wrap${here ? ' cl-wrap--spot' : ''}`,
        html: `<div class="cl" style="background:conic-gradient(${stops.join(',')})" aria-hidden="true"><span>${n}</span></div>`
          + `<span class="sr-only">${here ? 'W tym samym miejscu' : 'Grupa'}: ${plural(n, WPIS)} (${escapeHtml(mix)}) – ${here ? 'pokaż listę' : 'przybliż mapę'}</span>`,
        iconSize: [size, size],
      });
    },
  });
  map.addLayer(cluster);

  // Cluster click / Enter: a list of records when every marker sits on the same point (many decisions on
  // one parcel centroid), otherwise zoom in – or spiderfy when zooming further cannot split the group.
  function onCluster(e) {
    if (e.type === 'clusterkeypress' && e.originalEvent && e.originalEvent.key !== 'Enter' && e.originalEvent.keyCode !== 13) return;
    const c = e.layer;
    // Picking a point for "W pobliżu": a tap on a group picks that place (clusters cover most of the district map).
    if (pickCb) { pickAt(e.latlng || c.getLatLng()); return; }
    const kids = c.getAllChildMarkers();
    if (sameSpot(kids.map((m) => m.getLatLng()))) {
      openSpotList(c, kids);
      return;
    }
    // Keyboard: the focused group icon disappears when the map zooms – focus the marker nearest to it afterwards.
    const keyboard = e.type === 'clusterkeypress' || (c._icon && c._icon === document.activeElement);
    let bottom = c;
    while (bottom._childClusters && bottom._childClusters.length === 1) [bottom] = bottom._childClusters;
    if (bottom._zoom === map.getMaxZoom() && bottom._childCount === c._childCount) {
      if (keyboard) refocusNear(c.getLatLng(), 'spiderfied');
      c.spiderfy();
    } else {
      if (keyboard) refocusNear(c.getLatLng());
      c.zoomToBounds({ padding: [24, 24] });
    }
  }

  /** After a zoom/spiderfy started from the keyboard: focus the visible marker or group nearest to `ll` (else the map). */
  function refocusNear(ll, clusterEvent = 'animationend') {
    let done = false;
    const run = () => {
      if (done) return;
      done = true;
      requestAnimationFrame(() => {
        const box = el.getBoundingClientRect();
        const p = map.latLngToContainerPoint(ll);
        let best = null;
        let bestD = Infinity;
        for (const ic of el.querySelectorAll('.leaflet-marker-icon[tabindex="0"]')) {
          const r = ic.getBoundingClientRect();
          if (!r.width || r.right < box.left || r.left > box.right || r.bottom < box.top || r.top > box.bottom) continue;
          const d = Math.hypot(r.left + r.width / 2 - box.left - p.x, r.top + r.height / 2 - box.top - p.y);
          if (d < bestD) { best = ic; bestD = d; }
        }
        (best || el).focus({ preventScroll: true });
      });
    };
    cluster.once(clusterEvent, run);
    map.once('moveend', () => setTimeout(run, prefersReducedMotion() ? 0 : 350));
    setTimeout(run, 1200);
  }
  cluster.on('clusterclick', onCluster);
  cluster.on('clusterkeypress', onCluster);

  function openSpotList(c, kids) {
    const entries = kids.map((m) => m.options.entry).filter(Boolean)
      .sort((a, b) => (a.ts < b.ts ? 1 : a.ts > b.ts ? -1 : 0));
    const list = h('ul', { class: 'spot-list__items' }, entries.map((entry) => {
      const r = entry.rec;
      return h('li', null, h('button', {
        type: 'button', class: 'spot-list__item',
        onClick: () => { map.closePopup(); cfg.onSelect(entry.id); },
        onMouseenter: () => cfg.onHover(entry.id), onMouseleave: () => cfg.onHover(null),
      },
      kindGlyph(entry.kind, { approx: entry.approx }),
      h('span', { class: 'spot-list__text' },
        h('span', { class: 'spot-list__meta' }, cfg.kindShort(entry.kind), ' · ', r.date ? formatDate(r.date) : formatMonth(entry.month)),
        h('span', { class: 'spot-list__title' }, r.investment || r.address?.display || r.number || 'Wpis bez opisu'))));
    }));
    const head = entries[0]?.rec?.address?.display;
    const box = h('div', { class: 'spot-list', role: 'dialog', 'aria-label': `${plural(entries.length, WPIS)} w tym samym miejscu` },
      h('p', { class: 'spot-list__head' }, h('strong', null, `${plural(entries.length, WPIS)} w tym samym miejscu`),
        head ? h('span', { class: 'muted' }, ` · ${head}`) : null),
      list);
    L.DomEvent.disableScrollPropagation(box);
    // Pan clear of the map tools (top left: "W pobliżu mnie", "Tylko widoczny obszar") and the legend (bottom left).
    const popup = L.popup({
      className: 'spot-popup', maxWidth: 320, minWidth: 240, offset: [0, -12],
      autoPanPaddingTopLeft: [24, 132], autoPanPaddingBottomRight: [24, 64],
    });
    // Keyboard: Esc closes the list (and only the list – not an open record behind it); closing it while the
    // focus is inside (Esc, the × button) returns the focus to the group marker that opened it.
    const opener = c._icon || null;
    let focusInside = false;
    box.addEventListener('keydown', (ev) => {
      if (ev.key !== 'Escape') return;
      ev.preventDefault();
      ev.stopPropagation();
      map.closePopup(popup);
    });
    popup.on('add', () => {
      const wrap = popup.getElement();
      wrap?.addEventListener('focusin', () => { focusInside = true; });
      wrap?.addEventListener('focusout', (ev) => { focusInside = Boolean(ev.relatedTarget && wrap.contains(ev.relatedTarget)); });
    });
    popup.on('remove', () => {
      if (!focusInside) return;
      focusInside = false;
      (opener?.isConnected ? opener : el).focus({ preventScroll: true });
    });
    popup.setLatLng(c.getLatLng()).setContent(box).openOn(map);
    requestAnimationFrame(() => box.querySelector('.spot-list__item')?.focus({ preventScroll: true }));
  }

  const markers = new Map(); // id -> L.Marker
  let shownKey = '';
  let hotEl = null;

  function markerIcon(entry, extra = '') {
    const k = KIND_CLASS(entry.kind);
    const shape = shapeOf(k);
    const halo = extra.includes('mk--selected') ? `<g class="mk__halo">${shape}</g>` : '';
    return L.divIcon({
      className: 'mk-wrap',
      html: `<svg class="mk mk--${k}${entry.approx ? ' mk--approx' : ''}${extra}" viewBox="-2 -2 24 24" aria-hidden="true">${halo}<g class="mk__shape">${shape}</g></svg>`,
      iconSize: [22, 22],
      iconAnchor: [11, 11],
    });
  }

  /** Tooltip / spoken caveat of a hollow marker. */
  function approxNote(entry) {
    return entry.conflict ? 'lokalizacja niepewna – adres i działki się różnią' : 'lokalizacja przybliżona';
  }

  function tooltipContent(entry) {
    const r = entry.rec;
    return h('div', { class: 'mk-tip__inner' },
      h('div', { class: 'mk-tip__meta' }, kindGlyph(entry.kind, { approx: entry.approx }), cfg.kindShort(entry.kind),
        h('span', { class: 'mk-tip__date' }, r.date ? formatDate(r.date) : formatMonth(entry.month))),
      h('div', { class: 'mk-tip__title' }, r.address?.display || r.number || 'Bez adresu'),
      entry.approx ? h('div', { class: 'mk-tip__note' }, approxNote(entry)) : null);
  }

  function ensureMarker(entry) {
    let m = markers.get(entry.id);
    if (m || !entry.hasGeo) return m;
    m = L.marker([entry.lat, entry.lon], {
      icon: markerIcon(entry), kind: entry.kind, id: entry.id, entry, keyboard: true, riseOnHover: true,
    });
    // Visible markers are keyboard-focusable buttons (Enter/Space open the record, see below) with a spoken name.
    const r = entry.rec;
    const spoken = [cfg.kindShort(entry.kind), r.address?.display || r.number || 'bez adresu',
      r.date ? formatDate(r.date) : formatMonth(entry.month), entry.approx ? approxNote(entry) : null].filter(Boolean).join(', ');
    m.on('add', () => {
      const elm = m.getElement();
      if (!elm) return;
      elm.setAttribute('aria-label', spoken);
      elm.addEventListener('focus', () => cfg.onHover(entry.id));
      elm.addEventListener('blur', () => cfg.onHover(null));
    });
    m.bindTooltip(() => tooltipContent(entry), { direction: 'top', offset: [0, -10], opacity: 1, className: 'mk-tip', interactive: true });
    // Hoverable tooltip (WCAG 1.4.13): the pointer may move onto it; it closes a moment after leaving both.
    m.off('mouseout', m.closeTooltip, m);
    let closeTimer = null;
    const cancelClose = () => clearTimeout(closeTimer);
    const scheduleClose = () => {
      cancelClose();
      closeTimer = setTimeout(() => { m.closeTooltip(); cfg.onHover(null); }, 300);
    };
    m.on('tooltipopen', (ev) => {
      const tipEl = ev.tooltip?.getElement();
      if (!tipEl || tipEl.dataset.hoverable) return;
      tipEl.dataset.hoverable = '1';
      tipEl.addEventListener('pointerenter', cancelClose);
      tipEl.addEventListener('pointerleave', scheduleClose);
    });
    m.on('click', (ev) => {
      if (pickCb) { pickAt(ev.latlng || m.getLatLng()); return; }
      cfg.onSelect(entry.id);
    });
    // Visible markers are role=button: Enter and Space open the record (Leaflet handles Enter only for popups).
    m.on('keydown', (ev) => {
      const k = ev.originalEvent;
      if (!k || (k.key !== 'Enter' && k.key !== ' ') || k.repeat) return;
      k.preventDefault();
      if (pickCb) { pickAt(m.getLatLng()); return; }
      cfg.onSelect(entry.id);
    });
    m.on('mouseover', () => { cancelClose(); cfg.onHover(entry.id); });
    m.on('mouseout', scheduleClose);
    markers.set(entry.id, m);
    return m;
  }

  // --- selection / parcels ------------------------------------------------------------------------
  const selection = L.layerGroup().addTo(map);
  let parcelIndex = null; // id -> feature
  let selected = null;
  const nearLayer = L.layerGroup().addTo(map);

  function selectionStyle() {
    return {
      color: cssVar('--map-select', '#b4235a'), weight: 2.5, opacity: 1,
      fillColor: cssVar('--map-select', '#b4235a'), fillOpacity: 0.18,
    };
  }

  function drawSelection({ fit }) {
    selection.clearLayers();
    const entry = selected;
    if (!entry) return;
    if (!entry.hasGeo) {
      // A record without a location: never leave the map on an unrelated spot – show the whole district.
      if (fit) fitDistrict();
      return;
    }
    const geo = entry.rec.geo || {};
    const ids = Array.isArray(geo.parcels_found) ? geo.parcels_found : [];
    const feats = parcelIndex ? ids.map((id) => parcelIndex.get(id)).filter(Boolean) : [];
    let bounds = null;
    if (feats.length) {
      const layer = L.geoJSON({ type: 'FeatureCollection', features: feats }, { style: selectionStyle, interactive: false });
      layer.addTo(selection);
      bounds = layer.getBounds();
    } else if (Array.isArray(geo.bbox) && geo.bbox.length === 4 && !entry.approx) {
      const [w, s, e, n] = geo.bbox;
      const rect = L.rectangle([[s, w], [n, e]], { ...selectionStyle(), dashArray: '4 4', interactive: false });
      rect.addTo(selection);
      bounds = rect.getBounds();
    }
    // Street-level points: the possible error is drawn only when the data states it (geo.uncertainty_m, optional) –
    // a fixed radius would understate it (street midpoints are typically ~700 m from the site); address points
    // need none. The hollow marker and "lokalizacja przybliżona" say the rest.
    const u = entry.rec.geo?.uncertainty_m;
    if (entry.approx && geo.method === 'street' && typeof u === 'number' && u > 0) {
      const circle = L.circle([entry.lat, entry.lon], {
        radius: u, color: cssVar('--map-select', '#b4235a'), weight: 1.5, dashArray: '5 5', fillOpacity: 0.04, interactive: false,
      }).addTo(selection);
      if (!bounds) bounds = circle.getBounds();
    }
    L.marker([entry.lat, entry.lon], {
      icon: markerIcon(entry, ' mk--selected'), keyboard: false, interactive: false, zIndexOffset: 2000,
    }).addTo(selection);
    if (fit) {
      const opts = { animate: !prefersReducedMotion(), maxZoom: 18, padding: [48, 48] };
      if (bounds && bounds.isValid()) map.fitBounds(bounds, opts);
      else map.setView([entry.lat, entry.lon], entry.approx ? 16 : 17, { animate: !prefersReducedMotion() });
    }
  }

  // --- areas --------------------------------------------------------------------------------------
  let areasGeo = null;
  let areasOverlayAdded = false;
  const areaLayers = new Map(); // slug -> L.GeoJSON
  let activeAreas = [];
  function areaStyle(slug) {
    const on = activeAreas.includes(slug);
    return on
      ? { color: cssVar('--map-select', '#b4235a'), weight: 2.5, opacity: 0.9, dashArray: null, fill: true, fillColor: cssVar('--map-select', '#b4235a'), fillOpacity: 0.05 }
      : { color: cssVar('--map-area', '#6b6f78'), weight: 1, opacity: 0.6, dashArray: '3 4', fill: false };
  }
  function restyleVectors() {
    drawAreas();
    drawSelection({ fit: false });
  }
  function drawAreas() {
    areasLayer.clearLayers();
    districtLayer.clearLayers();
    areaLayers.clear();
    if (!areasGeo) return;
    const outline = cssVar('--map-outline', '#1b1d22');
    let hasAreas = false;
    for (const f of areasGeo.features || []) {
      const slug = f?.properties?.slug;
      if (!f?.geometry) continue;
      if (slug === '_district') {
        L.geoJSON(f, { style: { color: outline, weight: 2, opacity: 0.55, fill: false }, interactive: false }).addTo(districtLayer);
      } else {
        hasAreas = true;
        const layer = L.geoJSON(f, { style: () => areaStyle(slug), interactive: false });
        layer.addTo(areasLayer);
        areaLayers.set(slug, layer);
        const label = f.properties?.label;
        if (label) {
          const c = layer.getBounds().getCenter();
          L.tooltip({ permanent: true, direction: 'center', className: 'area-label', interactive: false })
            .setLatLng(c).setContent(escapeHtml(label)).addTo(areasLayer);
        }
      }
    }
    legend.querySelector('.legend-areas').hidden = !hasAreas;
    if (hasAreas && !areasOverlayAdded) {
      layersControl.addOverlay(areasLayer, 'Granice osiedli');
      areasOverlayAdded = true;
    }
  }

  function updateZoomClass() {
    el.classList.toggle('is-zoomed-in', map.getZoom() >= 15.5);
    el.classList.toggle('is-zoomed-out', map.getZoom() < 12.5);
  }
  map.on('zoomend', updateZoomClass);
  updateZoomClass();

  map.on('moveend', (e) => cfg.onMoveEnd(api.getBbox(), e));
  // A real pan/zoom by the visitor (not a programmatic fit): mouse, touch, wheel or keyboard on the map.
  for (const type of ['mousedown', 'touchstart', 'wheel']) el.addEventListener(type, () => cfg.onUserMove?.(), { passive: true });
  el.addEventListener('keydown', (ev) => { if (/^(Arrow\w+|[+\-=_])$/.test(ev.key)) cfg.onUserMove?.(); });

  // A marker or group focused from the keyboard is panned into view clear of the map tools (top), the legend and the
  // attribution (bottom). Not on a mouse press: panning between mousedown and mouseup would swallow the click.
  el.addEventListener('focusin', (ev) => {
    const t = ev.target;
    if (!(t instanceof Element) || !t.classList.contains('leaflet-marker-icon')) return;
    try { if (!t.matches(':focus-visible')) return; } catch { /* no :focus-visible – pan anyway */ }
    // The icon's own layer position (the browser may have scrolled the container to reveal it, so the DOM rect lies).
    const pos = L.DomUtil.getPosition(t);
    if (!pos) return;
    const ll = map.layerPointToLatLng(pos);
    const phone = mq('(max-width: 767.98px)').matches;
    map.panInside(ll, { paddingTopLeft: [24, 132], paddingBottomRight: [24, phone ? 124 : 72], animate: !prefersReducedMotion() });
  });

  // Picking a point for the "near" filter: a click/tap anywhere (also on a marker or a group), or – keyboard – Enter
  // on the focused map picks its centre (after panning with the arrows).
  let pickCb = null;
  function pickAt(ll) {
    const cb = pickCb;
    api.cancelPick();
    if (cb) cb(ll.lat, ll.lng);
  }
  map.on('click', (e) => { if (pickCb) pickAt(e.latlng); });
  el.addEventListener('keydown', (ev) => {
    if (!pickCb || ev.target !== el || (ev.key !== 'Enter' && ev.key !== ' ')) return;
    ev.preventDefault();
    pickAt(map.getCenter());
  });

  function fitDistrict() {
    const d = api.districtBounds();
    if (d) map.fitBounds(d, { padding: [16, 16], animate: !prefersReducedMotion() });
    else map.setView(MAP_CENTER, MAP_ZOOM, { animate: !prefersReducedMotion() });
  }

  const api = {
    map,
    setEntries(entries) {
      for (const e of entries) ensureMarker(e);
    },
    /** Show markers for the given (filtered) entries. */
    setResults(entries) {
      const ids = [];
      for (const e of entries) if (e.hasGeo) ids.push(e.id);
      const key = ids.join('|');
      if (key === shownKey) return;
      shownKey = key;
      hotEl = null;
      cluster.clearLayers();
      cluster.addLayers(entries.filter((e) => e.hasGeo).map((e) => ensureMarker(e)).filter(Boolean));
    },
    highlight(id) {
      if (hotEl) { hotEl.classList.remove('is-hot'); hotEl = null; }
      if (!id) return;
      const m = markers.get(id);
      if (!m || !cluster.hasLayer(m)) return;
      const visible = cluster.getVisibleParent(m);
      const iconEl = visible?._icon;
      if (iconEl) { iconEl.classList.add('is-hot'); hotEl = iconEl; }
    },
    select(entry, { fit = true } = {}) {
      selected = entry || null;
      drawSelection({ fit });
    },
    /** Add parcel outlines (parcels.geojson, later parcels-permits.geojson); ids already known are kept. */
    addParcels(geojson) {
      parcelIndex = parcelIndex || new Map();
      for (const f of geojson?.features || []) {
        const id = f?.properties?.id;
        if (id && f.geometry && !parcelIndex.has(id)) parcelIndex.set(id, f);
      }
      if (selected) drawSelection({ fit: false });
    },
    setLegendKinds,
    setAreas(geojson) {
      areasGeo = geojson;
      drawAreas();
      // Boundaries from OpenStreetMap are already covered by the base map's OSM credit (ODbL);
      // any other source gets its own attribution.
      const attr = typeof geojson?.attribution === 'string' ? geojson.attribution : '';
      if (attr && !/openstreetmap/i.test(attr)) map.attributionControl.addAttribution(`granice osiedli ${escapeHtml(attr)}`);
    },
    /** Outline the neighbourhoods selected in the "Obszar" filter. */
    setActiveAreas(slugs) {
      activeAreas = Array.isArray(slugs) ? slugs : [];
      for (const [slug, layer] of areaLayers) layer.setStyle(areaStyle(slug));
    },
    districtBounds() {
      let b = null;
      districtLayer.eachLayer((l) => { b = l.getBounds(); });
      return b;
    },
    setNear(near, { fit = false } = {}) {
      nearLayer.clearLayers();
      if (!near) return;
      const color = cssVar('--map-select', '#b4235a');
      const circle = L.circle([near.lat, near.lon], {
        radius: near.r, color, weight: 2, dashArray: '6 6', fillColor: color, fillOpacity: 0.05, interactive: false,
      }).addTo(nearLayer);
      L.circleMarker([near.lat, near.lon], { radius: 6, color: '#fff', weight: 2, fillColor: color, fillOpacity: 1, interactive: false })
        .addTo(nearLayer);
      if (fit) map.fitBounds(circle.getBounds(), { padding: [24, 24], animate: !prefersReducedMotion() });
    },
    setBboxToggle(on, count) {
      bboxInput.checked = Boolean(on);
      bboxCount.textContent = count != null ? String(count) : '';
    },
    getBbox() {
      const b = map.getBounds();
      const r = (x) => Number(x.toFixed(5));
      return [r(b.getWest()), r(b.getSouth()), r(b.getEast()), r(b.getNorth())];
    },
    fitBbox(bbox) {
      map.fitBounds([[bbox[1], bbox[0]], [bbox[3], bbox[2]]], { animate: false });
    },
    /** Fit to the given entries (or the district) — used after filter changes. */
    fitEntries(entries, { animate = true, maxZoom = 16 } = {}) {
      const pts = entries.filter((e) => e.hasGeo).map((e) => [e.lat, e.lon]);
      if (!pts.length) {
        const d = api.districtBounds();
        if (d) map.fitBounds(d, { padding: [16, 16], animate: animate && !prefersReducedMotion() });
        return;
      }
      const b = L.latLngBounds(pts);
      map.fitBounds(b, { padding: [40, 40], maxZoom, animate: animate && !prefersReducedMotion() });
    },
    startPick(cb) {
      pickCb = cb;
      el.classList.add('is-picking');
      map.closePopup();
    },
    cancelPick() {
      pickCb = null;
      el.classList.remove('is-picking');
    },
    /** Pick the centre of the current view (keyboard / "Środek mapy" button). */
    pickCenter() {
      if (pickCb) pickAt(map.getCenter());
    },
    isPicking: () => Boolean(pickCb),
    /** Close an open marker tooltip (Esc); true when one was open. */
    closeTooltips() {
      let closed = false;
      for (const m of markers.values()) {
        if (m.isTooltipOpen?.()) { m.closeTooltip(); closed = true; }
      }
      if (closed) cfg.onHover(null);
      return closed;
    },
    /** Focus the marker (or the group holding it) of a record, else the map itself. */
    focusMarker(id) {
      const m = id ? markers.get(id) : null;
      const vis = m && cluster.hasLayer(m) ? cluster.getVisibleParent(m) : null;
      const target = vis?._icon && vis._icon.isConnected ? vis._icon : el;
      target.focus({ preventScroll: true });
    },
    fitDistrict,
    invalidate() {
      map.invalidateSize({ pan: false });
    },
    setLocating(on) {
      locateBtn.classList.toggle('is-busy', Boolean(on));
      locateBtn.disabled = Boolean(on);
      replaceChildren(locateBtn, icon('locate', { size: 16 }), h('span', null, on ? 'Ustalanie…' : 'W pobliżu mnie'));
    },
  };
  return api;
}
