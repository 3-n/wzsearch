/**
 * Explore view (route #/ and #/wpis/<id>): search, filters, timeline, result cards, map, detail host.
 *
 * Layout (CSS decides by width):
 *   ≥1200 px  filters | results | map        (detail panel covers the results column)
 *   768–1199  results | map, filters in a drawer
 *   <768      one column, list/map toggle, filters + detail as full-screen sheets
 */
import { h, replaceChildren, debounce, isMobile, isDesktopWide, trapFocus, downloadText, mq } from '../dom.js';
import { icon } from '../icons.js';
import { tokenize } from '../search.js';
import {
  evaluate, sortResults, effectiveSort, hasActiveFilters, defaultFilters, periodSpans, outcomeCoverage,
} from '../filters.js';
import { buildHash, NEAR_DECIMALS } from '../url.js';
import { monthBounds, nearestAddressPoint } from '../data.js';
import { plural, formatNumber, formatDateTime, formatMonthRange, WPIS, WYNIK } from '../format.js';
import { UNOFFICIAL, promoText } from '../copy.js';
import { OPT_IN_KINDS, DEFAULT_KINDS, effectiveKinds, isOptInKind, orderKinds, withOptIn } from '../kinds.js';
import { describeActive } from '../active.js';
import { recordsToCSV, csvFileName } from '../csv.js';
import { PAGE_SIZE } from '../config.js';
import { createFiltersPanel } from './filters-panel.js';
import { createTimeline } from '../components/timeline.js';
import { renderCard, skeletonCard } from '../components/card.js';
import { createMap } from '../components/map.js';
import { toast } from '../components/toast.js';

/** Approximate district bbox [w, s, e, n] used when the map is not available. */
const DISTRICT_BBOX = [21.03, 52.205, 21.165, 52.262];

/** Per-viewer convenience: the "show permits too" promo can be dismissed (localStorage, best effort). */
const PROMO_KEY = 'wzsearch:promo-permits-dismissed';
/** Per-viewer convenience: the "what is this" intro strip above the results can be dismissed (best effort). */
const INTRO_KEY = 'wzsearch:intro-dismissed';
function stored(key) {
  try { return window.localStorage.getItem(key) === '1'; } catch { return false; }
}
function store(key) {
  try { window.localStorage.setItem(key, '1'); } catch { /* private mode – fine */ }
}
const promoDismissed = () => stored(PROMO_KEY);
const dismissPromo = () => store(PROMO_KEY);

/** Round a coordinate for the "near" filter (privacy, see url.js). */
const roundNear = (x) => Number(x.toFixed(NEAR_DECIMALS));

const SORT_OPTIONS = [
  ['relevance', 'Trafność'],
  ['newest', 'Najnowsze'],
  ['oldest', 'Najstarsze'],
  ['street', 'Ulica A–Z'],
];

/**
 * @param {HTMLElement} section
 * @param {{
 *   index: object, getState: () => object,
 *   navigate: (patch: object, opts?: object) => void,
 *   openRecord: (id: string) => void,
 *   permits: {state: () => string, retry: () => void},
 * }} ctx
 *   permits.state(): 'idle' | 'loading' | 'loaded' | 'error' of the lazily loaded permits layer (main.js)
 */
export function createExplore(section, ctx) {
  const { index } = ctx;
  const { dicts } = index;
  const kindShort = (k) => dicts.kinds?.[k]?.short || k;
  const kindLabel = (k) => dicts.kinds?.[k]?.label || k;

  let state = ctx.getState();
  let filters = state.filters;
  let tokens = [];
  let results = [];
  let facets = null;
  let lastKey = null;
  let limit = PAGE_SIZE;
  let mapApi = null;
  const parcelsGeo = [];
  let areasGeo = null;
  let selectedId = null;
  let pendingFocusId = null;
  let typingSession = false;
  let drawerRelease = null;
  let lastBbox = null;
  let initialFitDone = false;
  let nearFit = false; // fit the map to the "near" circle after the next update
  let bounds = { min: index.minMonth, max: index.maxMonth };
  /** Newest month per selected kind: relative presets count back per kind (filters.periodRanges). */
  let latestByKind = null;
  let promoHidden = promoDismissed();
  /**
   * A "mapa=" area that came from the URL (a shared link, back/forward) is authoritative until the visitor pans or
   * zooms: the fit to the receiver's screen must not rewrite the link (filters.bbox) by itself.
   */
  let urlBboxPinned = false;
  let pickBanner = null;
  let peekId = null;
  /** Shared evaluate() context: latest month(s) for the period presets, query tokens. */
  const evalCtx = (extra = {}) => ({ latestMonth: bounds.max, latestByKind, tokens, ...extra });

  const setFilters = (patch, opts = {}) => {
    if (patch === 'CLEAR') {
      ctx.navigate({ filters: { ...defaultFilters(), sort: filters.sort } }, opts);
      return;
    }
    if (patch.kinds) patch = { ...patch, kinds: orderKinds(patch.kinds) };
    const next = { ...filters, ...patch };
    if (next.bbox === 'VIEW') next.bbox = mapApi ? mapApi.getBbox() : (lastBbox || DISTRICT_BBOX);
    ctx.navigate({ filters: next }, opts);
  };

  // --- filters pane ------------------------------------------------------------------------------
  const panel = createFiltersPanel({
    index,
    onPatch: (patch) => setFilters(patch),
    onLocate: () => locate(),
    onPickPoint: () => pickPoint(),
    onClose: () => closeDrawer(),
    onShowResults: () => closeDrawer({ toResults: true }),
    onPickCenter: () => pickCenter(),
    onRetryPermits: () => ctx.permits.retry(),
  });
  // A named region; role=dialog while it is the drawer/sheet (<aside> may not take that role).
  const filtersPane = h('div', { class: 'pane pane--filters', id: 'filters', role: 'region', 'aria-labelledby': 'filters-title' }, panel.el);

  // --- results pane ------------------------------------------------------------------------------
  const searchInput = h('input', {
    id: 'q', class: 'search__input', type: 'search', autocomplete: 'off', spellcheck: 'false', enterkeyhint: 'search',
    placeholder: 'Adres, ulica, numer decyzji, wnioskodawca, działka…',
    'aria-describedby': 'search-hint',
  });
  const searchClear = h('button', { type: 'button', class: 'search__clear', 'aria-label': 'Wyczyść wyszukiwanie', hidden: true }, icon('x', { size: 16 }));
  const searchBox = h('div', { class: 'search', role: 'search' },
    h('label', { for: 'q', class: 'sr-only' }, 'Szukaj we wszystkich wpisach'),
    icon('search', { size: 20, class: 'search__icon' }),
    searchInput, searchClear,
    h('kbd', { class: 'search__kbd', 'aria-hidden': 'true', title: 'Naciśnij /, aby wyszukać' }, '/'));
  const searchHint = h('p', { id: 'search-hint', class: 'sr-only' },
    'Wyszukiwanie działa od razu, bez polskich znaków i wielkości liter, także w innej formie słowa (np. „budynek” znajdzie „budynku”). Kilka słów musi wystąpić jednocześnie.');

  const filtersBtnCount = h('span', { class: 'badge-count', hidden: true });
  const filtersBtn = h('button', {
    type: 'button', class: 'btn btn--secondary btn--sm filters-toggle', 'aria-controls': 'filters', 'aria-expanded': 'false',
    onClick: () => openDrawer(),
  }, icon('sliders', { size: 16 }), h('span', null, 'Filtry'), filtersBtnCount);

  const timeline = createTimeline({
    kinds: effectiveKinds(filters.kinds),
    kindLabel: kindShort,
    onSelect: (from, to) => setFilters({ period: null, from, to }),
    onClear: () => setFilters({ period: null, from: null, to: null }),
  });

  const countEl = h('p', { class: 'results-count', id: 'results-count' });
  const liveEl = h('p', { class: 'sr-only', 'aria-live': 'polite', 'aria-atomic': 'true', id: 'results-live' });
  const sortSel = h('select', { class: 'select select--sm', id: 'sort', onChange: (e) => setFilters({ sort: e.target.value || null }) });
  const csvBtn = h('button', { type: 'button', class: 'btn btn--secondary btn--sm', onClick: () => downloadCsv(), title: 'Pobierz bieżące wyniki jako CSV (Excel)' },
    icon('download', { size: 16 }), h('span', { class: 'csv-label' }, 'CSV'));
  const chipsEl = h('div', { class: 'chips', hidden: true });
  // First visit: what this is, in one breath (phones show neither the district name nor "nieoficjalny" up top).
  const introEl = stored(INTRO_KEY) ? null : h('div', { class: 'intro', role: 'note' },
    icon('info', { size: 16, class: 'intro__icon' }),
    h('p', { class: 'intro__text' },
      'Decyzje o warunkach zabudowy (WZ), o lokalizacji celu publicznego (CP) i wszczęte sprawy z Pragi-Południe – z list urzędów, z linkiem do źródła przy każdym wpisie. ',
      h('strong', null, 'Decyzja WZ to jeszcze nie pozwolenie na budowę.'), ' Serwis nieoficjalny. ',
      h('a', { class: 'link', href: '#/o-projekcie' }, 'Co to znaczy?\u00a0→')),
    h('button', {
      type: 'button', class: 'btn btn--icon btn--ghost btn--sm intro__x', 'aria-label': 'Ukryj wprowadzenie',
      onClick: () => { store(INTRO_KEY); introEl.remove(); searchInput.focus(); },
    }, icon('x', { size: 16 })));
  // Opt-in discovery: "Pokaż też pozwolenia na budowę (2 340)" – the count follows the other filters once loaded.
  const promoEl = h('div', { class: 'promo', hidden: true });
  // Loading strip while the permits layer is fetched for a selection that includes pb/zg.
  const pendingEl = h('p', { class: 'pending', role: 'status', hidden: true });
  // The outcome filter covers only the records that state an outcome (BAiPP): say how many decisions it leaves out.
  const outcomeNoteEl = h('p', { class: 'outcome-note', role: 'note', hidden: true });
  const listEl = h('ol', { class: 'cards', id: 'results', 'aria-labelledby': 'results-count' });
  const moreBtn = h('button', { type: 'button', class: 'btn btn--secondary btn--block more-btn', hidden: true, onClick: () => showMore(true) });
  const emptyEl = h('div', { class: 'empty', hidden: true });
  const nogeoEl = h('p', { class: 'nogeo', hidden: true });

  const footEl = h('footer', { class: 'results-foot' },
    h('p', null, icon('clock', { size: 14 }),
      h('span', null, index.meta.generatedAt ? `Dane z dnia ${formatDateTime(index.meta.generatedAt, { time: false })}` : 'Data aktualizacji nieznana'),
      h('span', { 'aria-hidden': 'true' }, '·'), h('a', { class: 'link', href: '#/zrodla' }, 'Źródła danych'),
      h('span', { 'aria-hidden': 'true' }, '·'), h('a', { class: 'link', href: '#/o-projekcie' }, 'Jak czytać dane'),
      h('span', { 'aria-hidden': 'true' }, '·'), h('a', { class: 'link', href: '#/o-projekcie', title: 'Kanał nowych wpisów – adres do czytnika RSS w sekcji „Pobierz dane”' }, 'Nowe wpisy (RSS)')),
    h('p', { class: 'results-foot__note' }, `${UNOFFICIAL}. Wiążące są wyłącznie dokumenty urzędowe.`));

  const resultsPane = h('section', { class: 'pane pane--results', 'aria-label': 'Wyniki' },
    h('div', { class: 'results-head' },
      h('div', { class: 'search-row' }, searchBox, filtersBtn), searchHint,
      timeline.el,
      // Heading outline: the cards (h3) belong to "Lista wyników", not to the timeline's h2.
      h('h2', { class: 'sr-only', id: 'results-heading' }, 'Lista wyników'),
      h('div', { class: 'results-bar' }, countEl, liveEl,
        h('div', { class: 'results-actions' },
          h('label', { for: 'sort', class: 'sr-only' }, 'Sortowanie'), icon('history', { size: 16, class: 'results-actions__icon' }), sortSel, csvBtn)),
      chipsEl),
    introEl,
    pendingEl,
    outcomeNoteEl,
    promoEl,
    emptyEl,
    listEl,
    moreBtn,
    footEl);

  // --- map pane ----------------------------------------------------------------------------------
  const mapEl = h('div', { class: 'map', id: 'map' });
  const mapPane = h('section', { class: 'pane pane--map', 'aria-label': 'Mapa wyników' }, mapEl, nogeoEl,
    h('div', { class: 'map-fallback', hidden: true }, 'Mapa jest niedostępna.'));

  // --- detail host ---------------------------------------------------------------------------------
  const detailPane = h('div', { class: 'pane pane--detail', id: 'detail', hidden: true, tabindex: '-1' });

  // --- mobile: list/map toggle + peek ------------------------------------------------------------
  const modeBtn = h('button', { type: 'button', class: 'fab', onClick: () => ctx.navigate({ mode: state.mode === 'map' ? 'list' : 'map' }) });
  const peek = h('div', { class: 'peek', hidden: true });

  const scrim = h('div', { class: 'scrim', hidden: true, onClick: () => closeDrawer() });
  // DOM order = keyboard order: the detail panel (shown in the results column) precedes the map.
  const root = h('div', { class: 'explore', 'data-mode': 'list' },
    h('h1', { class: 'sr-only' }, 'Przeglądaj wpisy'), filtersPane, resultsPane, detailPane, mapPane, scrim, modeBtn, peek);
  replaceChildren(section, root);

  for (const [v, label] of SORT_OPTIONS) sortSel.appendChild(h('option', { value: v }, label));

  // Shorter placeholder on phones so it is not cut mid-word.
  const phoneMq = mq('(max-width: 479.98px)');
  const setPlaceholder = () => {
    searchInput.placeholder = phoneMq.matches ? 'Adres, ulica, numer, firma…' : 'Adres, ulica, numer decyzji, wnioskodawca, działka…';
  };
  setPlaceholder();
  phoneMq.addEventListener('change', setPlaceholder);

  // --- search input wiring -----------------------------------------------------------------------
  searchInput.addEventListener('input', () => {
    searchClear.hidden = !searchInput.value;
    setFilters({ q: searchInput.value }, { replace: typingSession });
    typingSession = true;
  });
  searchInput.addEventListener('blur', () => { typingSession = false; });
  searchInput.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && searchInput.value) {
      e.preventDefault();
      e.stopPropagation();
      searchInput.value = '';
      searchClear.hidden = true;
      setFilters({ q: '' });
    } else if (e.key === 'Enter') {
      e.preventDefault();
      if (isMobile()) searchInput.blur();
      const first = listEl.querySelector('.card__link');
      if (first && !isMobile()) first.focus();
    }
  });
  searchClear.addEventListener('click', () => {
    searchInput.value = '';
    searchClear.hidden = true;
    setFilters({ q: '' });
    searchInput.focus();
  });

  // --- incremental rendering via IntersectionObserver ---------------------------------------------
  const io = new IntersectionObserver((items) => {
    if (items.some((i) => i.isIntersecting) && !moreBtn.hidden) showMore(false);
  }, { rootMargin: '400px 0px' });
  io.observe(moreBtn);

  // --- map ---------------------------------------------------------------------------------------
  function mapVisible() {
    return mapPane.offsetWidth > 0 && mapPane.offsetHeight > 0;
  }

  function ensureMap() {
    if (mapApi || !mapVisible()) return mapApi;
    try {
      mapApi = createMap(mapEl, {
        kinds: legendKinds(),
        kindShort,
        kindLabel,
        onSelect: (id) => onMarkerSelect(id),
        onHover: (id) => hotCard(id),
        onMoveEnd: (bbox) => onMapMove(bbox),
        onUserMove: () => { urlBboxPinned = false; },
        onToggleBbox: (on) => { urlBboxPinned = false; setFilters({ bbox: on ? 'VIEW' : null }); },
        onLocate: () => locate(),
      });
    } catch (err) {
      console.error(err);
      mapPane.querySelector('.map-fallback').hidden = false;
      return null;
    }
    mapApi.setEntries(index.entries);
    if (areasGeo) mapApi.setAreas(areasGeo);
    for (const g of parcelsGeo) mapApi.addParcels(g);
    mapApi.setResults(results.map((r) => r.entry));
    mapApi.setNear(filters.near);
    mapApi.setActiveAreas(filters.areas);
    if (filters.bbox) {
      urlBboxPinned = true;
      mapApi.fitBbox(filters.bbox);
    } else initialFit();
    const sel = selectedId ? index.byId.get(selectedId) : null;
    if (sel) mapApi.select(sel, { fit: true });
    syncBboxToggle();
    return mapApi;
  }

  /** The open record, when there is one (it may not be loaded yet: a permit permalink). */
  const selectedEntry = () => (selectedId ? index.byId.get(selectedId) || null : null);
  /** Is the open record of a kind the selection hides (e.g. a permit while permits are switched off)? */
  const selectedHidden = () => {
    const sel = selectedEntry();
    return Boolean(sel && !effectiveKinds(filters.kinds).includes(sel.kind));
  };
  /** Kinds drawn on the map: the selection, plus the kind of an open record shown on its own (▲ of a permit). */
  function legendKinds() {
    const ks = effectiveKinds(filters.kinds);
    const sel = selectedEntry();
    return index.kindCodes.filter((k) => ks.includes(k) || (sel && sel.hasGeo && sel.kind === k));
  }
  /** "Tylko widoczny obszar N" counts the list's results: no number while the open record is not one of them. */
  function syncBboxToggle() {
    mapApi?.setBboxToggle(Boolean(filters.bbox), selectedHidden() ? null : facets?.bbox);
  }

  function initialFit() {
    if (!mapApi || initialFitDone) return;
    if (filters.bbox || selectedId) { initialFitDone = true; return; }
    // A shared link with filters opens on its results; otherwise on the whole district.
    if (hasActiveFilters(filters) && results.some((r) => r.entry.hasGeo)) {
      if (filters.near) mapApi.setNear(filters.near, { fit: true });
      else mapApi.fitEntries(results.map((r) => r.entry), { animate: false });
      initialFitDone = true;
      return;
    }
    const d = mapApi.districtBounds();
    if (d) {
      mapApi.map.fitBounds(d, { padding: [8, 8], animate: false });
      initialFitDone = true;
    } else if (!areasGeo) {
      mapApi.fitEntries(index.entries, { animate: false, maxZoom: 14 });
    }
  }

  function onMapMove(bbox) {
    lastBbox = bbox;
    if (filters.bbox) {
      // The area from the URL stays as shared until the visitor moves the map (see urlBboxPinned).
      if (urlBboxPinned) return;
      const same = filters.bbox.every((v, i) => Math.abs(v - bbox[i]) < 1e-5);
      if (!same) setFilters({ bbox }, { replace: true, meta: { from: 'map' } });
      return;
    }
    // Only the "visible area" facet count depends on the view: refresh counts, keep the list.
    const res = evaluate(index.entries, filters, evalCtx({ viewBbox: bbox }));
    facets = res.facets;
    panel.update(filters, facets, results.length);
    syncBboxToggle();
  }

  const autoFit = debounce(() => {
    if (!mapApi || filters.bbox || selectedId || !mapVisible()) return;
    if (filters.near) return;
    mapApi.fitEntries(results.map((r) => r.entry));
  }, 450);

  // --- hover link list <-> map --------------------------------------------------------------------
  let hotId = null;
  function hotCard(id) {
    if (hotId === id) return;
    if (hotId) listEl.querySelector(`[data-id="${CSS.escape(hotId)}"]`)?.classList.remove('is-hot');
    hotId = id;
    if (id) listEl.querySelector(`[data-id="${CSS.escape(id)}"]`)?.classList.add('is-hot');
  }
  const onCardHover = (id) => {
    mapApi?.highlight(id);
    hotCard(id);
  };

  function onMarkerSelect(id) {
    if (isMobile() && state.mode === 'map') {
      showPeek(id);
      return;
    }
    pendingFocusId = id;
    ctx.openRecord(id);
  }

  // --- peek (mobile map) -------------------------------------------------------------------------
  function showPeek(id) {
    const entry = index.byId.get(id);
    if (!entry) return;
    peekId = id;
    replaceChildren(peek,
      h('button', { type: 'button', class: 'btn btn--icon peek__close', 'aria-label': 'Zamknij podgląd', onClick: () => hidePeek() }, icon('x', { size: 18 })),
      renderCard(entry, {
        dicts, tokens, tag: 'div', href: recordHref(entry.id), activeTags: filters.tags,
        onOpen: (e) => { e.preventDefault(); hidePeek({ refocus: false }); pendingFocusId = entry.id; ctx.openRecord(entry.id); },
      }));
    peek.hidden = false;
    mapApi?.select(entry, { fit: false });
    peek.querySelector('.card__link')?.focus({ preventScroll: true });
  }
  /** Close the peek card; when it had the keyboard focus, give it back to the record's marker (else the map). */
  function hidePeek({ refocus = true } = {}) {
    if (peek.hidden) return;
    const had = peek.contains(document.activeElement);
    peek.hidden = true;
    if (!selectedId) mapApi?.select(null);
    if (had && refocus) {
      if (mapApi) mapApi.focusMarker(peekId);
      else mapEl.focus({ preventScroll: true });
    }
  }

  // --- drawer (filters on <1200 px) ---------------------------------------------------------------
  function isDrawerMode() {
    return !isDesktopWide();
  }
  function openDrawer() {
    if (!isDrawerMode()) return;
    cancelPicking();
    root.classList.add('is-drawer-open');
    filtersPane.setAttribute('role', 'dialog');
    filtersPane.setAttribute('aria-modal', 'true');
    filtersBtn.setAttribute('aria-expanded', 'true');
    scrim.hidden = false;
    setInertOutside(filtersPane, true);
    drawerRelease = trapFocus(filtersPane);
    requestAnimationFrame(() => panel.el.querySelector('.filters__title')?.focus());
  }
  /**
   * @param {{toResults?: boolean, focus?: boolean}} [opts] focus: false when the page changes underneath (browser
   *   Back) – the "Filtry" button may not even be visible then.
   */
  function closeDrawer({ toResults = false, focus = true } = {}) {
    if (!root.classList.contains('is-drawer-open')) return;
    root.classList.remove('is-drawer-open');
    filtersPane.setAttribute('role', 'region');
    filtersPane.removeAttribute('aria-modal');
    filtersBtn.setAttribute('aria-expanded', 'false');
    scrim.hidden = true;
    setInertOutside(filtersPane, false);
    drawerRelease?.();
    drawerRelease = null;
    if (toResults) {
      resultsPane.scrollTo?.({ top: 0 });
      if (isMobile()) countEl.scrollIntoView({ block: 'start' });
    }
    if (focus) filtersBtn.focus({ preventScroll: toResults });
  }
  function setInertOutside(keep, on) {
    const others = [document.querySelector('.topbar'), document.querySelector('.skip-link'), resultsPane, mapPane, detailPane, modeBtn, peek];
    for (const el of others) if (el && el !== keep) el.inert = on;
  }
  mq('(min-width: 1200px)').addEventListener('change', () => { closeDrawer(); setTimeout(() => { ensureMap(); mapApi?.invalidate(); }, 50); });
  mq('(max-width: 767.98px)').addEventListener('change', () => setTimeout(() => { applyMode(); ensureMap(); mapApi?.invalidate(); }, 50));

  // --- geolocation / pick point -----------------------------------------------------------------
  function locate() {
    if (!('geolocation' in navigator)) {
      toast('Twoja przeglądarka nie udostępnia lokalizacji. Wskaż punkt na mapie.', { kind: 'error' });
      return;
    }
    mapApi?.setLocating(true);
    navigator.geolocation.getCurrentPosition((pos) => {
      mapApi?.setLocating(false);
      // Rounded to ~100 m before it reaches the URL (shared links must not pin down someone's home).
      const lat = roundNear(pos.coords.latitude);
      const lon = roundNear(pos.coords.longitude);
      const [w, s, e, n] = DISTRICT_BBOX;
      if (lon < w - 0.02 || lon > e + 0.02 || lat < s - 0.02 || lat > n + 0.02) {
        toast('Jesteś poza Pragą-Południe – w pobliżu może nie być żadnych wpisów.', { kind: 'info', timeout: 5000 });
      }
      nearFit = true;
      closeDrawer();
      setFilters({ near: { lat, lon, r: filters.near?.r || 500 } });
    }, (err) => {
      mapApi?.setLocating(false);
      const msg = err.code === 1 ? 'Brak zgody na udostępnienie lokalizacji.' : 'Nie udało się ustalić lokalizacji.';
      toast(`${msg} Możesz wskazać punkt na mapie.`, { kind: 'error', timeout: 5000 });
    }, { enableHighAccuracy: true, timeout: 12000, maximumAge: 60000 });
  }
  /**
   * "Wskaż na mapie": a persistent banner on the map (touch screens have no Esc and no crosshair cursor) with
   * "Środek mapy" (keyboard: pan with the arrows, then pick the centre) and "Anuluj". A tap on a marker or a group
   * picks that place too (map.js). Picking ends with the pick, Anuluj/Esc, the list view or an opened record.
   */
  function pickPoint() {
    closeDrawer({ focus: false });
    hidePeek({ refocus: false });
    if (isMobile() && state.mode !== 'map') ctx.navigate({ mode: 'map' });
    setTimeout(() => {
      const m = ensureMap();
      if (!m) return;
      m.startPick((lat, lon) => {
        endPickBanner();
        nearFit = true;
        setFilters({ near: { lat: roundNear(lat), lon: roundNear(lon), r: filters.near?.r || 500 } });
      });
      showPickBanner();
      mapEl.focus({ preventScroll: true });
    }, 80);
  }
  function showPickBanner() {
    endPickBanner();
    const touch = mq('(hover: none)').matches;
    pickBanner = h('div', { class: 'pick-banner', role: 'status' },
      icon('pin', { size: 16, class: 'pick-banner__icon' }),
      h('p', { class: 'pick-banner__text' }, touch
        ? 'Dotknij mapy w miejscu, wokół którego chcesz szukać.'
        : 'Kliknij mapę w miejscu, wokół którego chcesz szukać – albo przesuń ją strzałkami i naciśnij Enter, aby wybrać jej środek (Esc – anuluj).'),
      h('div', { class: 'pick-banner__actions' },
        h('button', { type: 'button', class: 'btn btn--secondary btn--sm', onClick: () => pickCenter() }, icon('target', { size: 15 }), 'Środek mapy'),
        h('button', { type: 'button', class: 'btn btn--secondary btn--sm', onClick: () => { cancelPicking(); filtersBtnOrSearch().focus({ preventScroll: true }); } }, 'Anuluj')));
    mapPane.appendChild(pickBanner);
  }
  function endPickBanner() {
    pickBanner?.remove();
    pickBanner = null;
  }
  function cancelPicking() {
    if (mapApi?.isPicking()) mapApi.cancelPick();
    endPickBanner();
  }
  /** "Środek mapy" / keyboard: the centre of the current view becomes the point. */
  function pickCenter() {
    if (!mapApi?.isPicking()) {
      const m = ensureMap();
      if (!m) return;
      const c = m.map.getCenter();
      nearFit = true;
      setFilters({ near: { lat: roundNear(c.lat), lon: roundNear(c.lng), r: filters.near?.r || 500 } });
      return;
    }
    mapApi.pickCenter();
  }
  const filtersBtnOrSearch = () => (filtersBtn.offsetParent ? filtersBtn : searchInput);

  // --- CSV ---------------------------------------------------------------------------------------
  function downloadCsv() {
    const recs = results.map((r) => r.entry.rec);
    if (!recs.length) { toast('Brak wyników do pobrania.', { kind: 'error' }); return; }
    const baseUrl = `${window.location.origin}${window.location.pathname}`;
    const csv = recordsToCSV(recs, { dicts, filesById: index.filesById, pagesById: index.pagesById, baseUrl });
    downloadText(csv, csvFileName());
    toast(`Pobrano ${plural(recs.length, WPIS)} (CSV, separator „;”).`, { kind: 'success' });
  }

  // --- rendering ---------------------------------------------------------------------------------
  function recordHref(id) {
    return buildHash({ route: 'record', recordId: id, filters, mode: state.mode });
  }

  function onCardOpen(e, entry) {
    e.preventDefault();
    pendingFocusId = entry.id;
    ctx.openRecord(entry.id);
  }

  function renderCards(from, to) {
    const frag = document.createDocumentFragment();
    for (let i = from; i < to; i += 1) {
      const { entry } = results[i];
      const card = renderCard(entry, { dicts, tokens, href: recordHref(entry.id), onOpen: onCardOpen, onHover: onCardHover, activeTags: filters.tags });
      if (entry.id === selectedId) card.classList.add('is-selected');
      frag.appendChild(card);
    }
    listEl.appendChild(frag);
  }

  /** @param {number} [keep] render at least this many cards (pages already shown before new data arrived) */
  function renderList(keep = 0) {
    listEl.textContent = '';
    hotId = null;
    const selIdx = selectedId ? results.findIndex((r) => r.entry.id === selectedId) : -1;
    const want = Math.max(keep, selIdx + 1);
    limit = Math.max(PAGE_SIZE, Math.ceil(want / PAGE_SIZE) * PAGE_SIZE);
    renderCards(0, Math.min(limit, results.length));
    updateMore();
  }

  function showMore(focusFirst) {
    const start = listEl.children.length;
    limit = Math.min(results.length, limit + PAGE_SIZE);
    renderCards(start, limit);
    updateMore();
    if (focusFirst) listEl.children[start]?.querySelector('.card__link')?.focus();
  }

  function updateMore() {
    const shown = listEl.children.length;
    const rest = results.length - shown;
    moreBtn.hidden = rest <= 0;
    moreBtn.textContent = rest > 0 ? `Pokaż kolejne ${formatNumber(Math.min(PAGE_SIZE, rest))} (pozostało ${formatNumber(rest)})` : '';
  }

  function renderCount() {
    const n = results.length;
    // Only pb/zg selected and permits.json still on its way: not "no results" (the list shows skeleton cards).
    if (!n && permitsPending()) {
      replaceChildren(countEl, h('strong', null, 'Wczytywanie…'));
      return;
    }
    // Denominator = records of the selected kinds (the planning records by default, + permits when on).
    const total = facets?.scopeTotal ?? index.entries.length;
    const active = hasActiveFilters(filters) && n !== total;
    replaceChildren(countEl,
      n ? [h('strong', null, formatNumber(n)), ` ${plural(n, WPIS).replace(/^\S+\s/, '')}`] : h('strong', null, 'Brak wyników'),
      active && n ? h('span', { class: 'muted' }, ` z ${formatNumber(total)}`) : null);
  }
  const announce = debounce(() => {
    const n = results.length;
    const note = outcomeNoteEl.hidden ? '' : ` ${outcomeNoteEl.textContent}`;
    liveEl.textContent = !n && permitsPending() ? 'Wczytywanie pozwoleń na budowę…'
      : `${n ? `Znaleziono ${plural(n, WPIS)}.` : 'Nie znaleziono żadnych wpisów.'}${note}`;
  }, 700);

  /**
   * The outcome filter only sees records whose source states an outcome (the BAiPP lists): name how many of the
   * matching WZ/CP decisions that is, so "2 wpisy" is not read as "2 refusals in the district".
   */
  function renderOutcomeNote() {
    if (!filters.outcomes.length) { outcomeNoteEl.hidden = true; return; }
    const cov = outcomeCoverage(index.entries, filters, evalCtx());
    outcomeNoteEl.hidden = !cov.unknown;
    if (!cov.unknown) return;
    const ks = effectiveKinds(filters.kinds);
    const which = ['wz', 'cp'].filter((k) => ks.includes(k)).map((k) => k.toUpperCase()).join(' i ') || 'WZ i CP';
    replaceChildren(outcomeNoteEl, icon('info', { size: 15 }),
      h('span', null, `Rozstrzygnięcie podają tylko zestawienia Biura Architektury (BAiPP): znamy je dla ${formatNumber(cov.known)} z ${formatNumber(cov.decisions)} decyzji ${which} pasujących do pozostałych filtrów. `,
        `Pozostałych ${formatNumber(cov.unknown)} (listy Urzędu Dzielnicy go nie podają) ten filtr nie obejmuje. `,
        h('a', { class: 'link', href: '#/o-projekcie' }, 'Dlaczego?')));
  }

  function renderChips() {
    const items = describeActive(filters, { dicts, streets: index.streets, filesById: index.filesById, latestMonth: bounds.max });
    // A preset counted back per kind group: the chip's tooltip names each window.
    const spans = periodSpans(filters, bounds.max, latestByKind, filters.kinds);
    if (filters.period && spans.length > 1) {
      const period = items.find((it) => it.group === 'period');
      if (period) period.title = spans.map((x) => `${x.kinds.map(kindShort).join(', ')}: ${formatMonthRange(x.from, x.to)}`).join(' · ');
    }
    chipsEl.hidden = !items.length;
    filtersBtnCount.hidden = !items.length;
    filtersBtnCount.textContent = String(items.filter((i) => i.group !== 'q').length || '');
    if (!items.filter((i) => i.group !== 'q').length) filtersBtnCount.hidden = true;
    replaceChildren(chipsEl,
      h('ul', { class: 'chips__list', 'aria-label': 'Aktywne filtry' }, items.map((it, i) => h('li', null,
        h('span', { class: `chip chip--${it.group}`, title: it.title || null },
          h('span', { class: 'chip__group' }, `${it.groupLabel}:`), h('span', { class: 'chip__label' }, it.label),
          h('button', {
            type: 'button', class: 'chip__x', 'aria-label': `Usuń filtr ${it.groupLabel} ${it.label}`,
            onClick: () => {
              setFilters(it.remove);
              requestAnimationFrame(() => {
                const btns = chipsEl.querySelectorAll('.chip__x');
                (btns[Math.min(i, btns.length - 1)] || searchInput).focus();
              });
            },
          }, icon('x', { size: 12 })))))),
      items.length > 1 ? h('button', { type: 'button', class: 'btn btn--link btn--xs chips__clear', onClick: () => { setFilters('CLEAR'); searchInput.focus(); } }, 'Wyczyść filtry') : null);
  }

  /** Is a pb/zg selection waiting for permits.json? Then the list shows skeletons, never "no results". */
  function permitsPending() {
    const st = ctx.permits.state();
    return effectiveKinds(filters.kinds).some(isOptInKind) && !index.permitsLoaded && st !== 'error' && st !== 'unavailable';
  }

  function renderPending() {
    const kinds = effectiveKinds(filters.kinds);
    const state = ctx.permits.state();
    const wanted = kinds.some(isOptInKind) && !index.permitsLoaded;
    pendingEl.hidden = !wanted;
    if (!wanted) return;
    if (state === 'unavailable') {
      replaceChildren(pendingEl, icon('info', { size: 15 }),
        h('span', null, 'Ta wersja danych nie zawiera pozwoleń na budowę ani zgłoszeń – pokazujemy pozostałe wpisy.'));
      pendingEl.classList.add('pending--error');
    } else if (state === 'error') {
      // "Pokazujemy pozostałe wpisy" only when other kinds are selected at all.
      const others = kinds.some((k) => !isOptInKind(k));
      replaceChildren(pendingEl, icon('alert', { size: 15 }),
        h('span', null, others ? 'Nie udało się wczytać pozwoleń na budowę. Pokazujemy pozostałe wpisy. ' : 'Nie udało się wczytać rejestru pozwoleń GUNB. '),
        h('button', { type: 'button', class: 'btn btn--link btn--xs', onClick: () => ctx.permits.retry() }, 'Spróbuj ponownie'));
      pendingEl.classList.add('pending--error');
    } else {
      replaceChildren(pendingEl, h('span', { class: 'spinner', 'aria-hidden': 'true' }),
        h('span', null, 'Wczytywanie pozwoleń na budowę i zgłoszeń z rejestru GUNB…'));
      pendingEl.classList.remove('pending--error');
    }
  }

  /** Count of opt-in records matching everything else (exact once loaded; total from counts_by_kind before). */
  function optInCount(k) {
    if (index.permitsLoaded) return facets?.kinds?.[k] || 0;
    return index.countsByKind[k] || 0;
  }

  function renderPromo() {
    const kinds = effectiveKinds(filters.kinds);
    const missing = OPT_IN_KINDS.filter((k) => index.kindCodes.includes(k) && !kinds.includes(k));
    const covers = DEFAULT_KINDS.every((k) => kinds.includes(k));
    const pb = missing.includes('pb') ? optInCount('pb') : 0;
    const zg = missing.includes('zg') ? optInCount('zg') : 0;
    // With no results the empty state offers the same switch among its suggestions; a failed register: no offer.
    const show = !promoHidden && covers && (pb > 0 || zg > 0) && !permitsPending() && results.length > 0
      && ctx.permits.state() !== 'error';
    promoEl.hidden = !show;
    if (!show) return;
    // Before loading only register totals are known: next to a search they are not shown as if they matched.
    const main = pb ? 'pb' : 'zg';
    const t = promoText({
      loaded: index.permitsLoaded, filtered: hasActiveFilters({ ...filters, kinds: [...DEFAULT_KINDS] }), main, pb, zg,
    });
    replaceChildren(promoEl,
      h('span', { class: 'promo__icon' }, icon('crane', { size: 18 })),
      h('div', { class: 'promo__body' },
        h('button', { type: 'button', class: 'promo__btn', onClick: () => setFilters({ kinds: withOptIn(kinds, [main]) }) },
          // The count never wraps onto a line of its own: it is glued to the last word.
          t.lead, h('span', { class: 'nowrap' }, t.tail, t.count ? ['\u00a0', h('span', { class: 'promo__count' }, t.count)] : null)),
        h('p', { class: 'promo__note' }, `${t.note} `,
          t.more ? h('button', { type: 'button', class: 'btn btn--link btn--xs promo__more', onClick: () => setFilters({ kinds: withOptIn(kinds, ['pb', 'zg']) }) },
            t.more) : null)),
      h('button', {
        type: 'button', class: 'btn btn--icon btn--ghost btn--sm promo__x', 'aria-label': 'Ukryj podpowiedź o pozwoleniach',
        onClick: () => { promoHidden = true; dismissPromo(); renderPromo(); searchInput.focus(); },
      }, icon('x', { size: 16 })));
  }

  function renderEmpty() {
    const n = results.length;
    const pending = permitsPending();
    emptyEl.hidden = n > 0 || pending;
    if (pending && !n) {
      // Only pb/zg selected and still loading: keep the layout, show skeleton cards.
      listEl.textContent = '';
      for (let i = 0; i < 4; i += 1) listEl.appendChild(skeletonCard());
      return;
    }
    if (n > 0) return;
    if (!index.entries.length) {
      replaceChildren(emptyEl, icon('inbox', { size: 40, class: 'empty__icon' }),
        h('h2', { class: 'empty__title' }, 'Brak danych'),
        h('p', null, 'Zbiór danych jest pusty. Sprawdź stronę „Źródła danych”.'),
        h('a', { class: 'btn btn--secondary', href: '#/zrodla' }, 'Źródła danych'));
      return;
    }
    const items = describeActive(filters, { dicts, streets: index.streets, filesById: index.filesById, latestMonth: bounds.max });
    const groupCounts = facets?.without || {};
    const suggestions = [];
    const registerDown = ctx.permits.state() === 'error';
    // Nothing among the planning records, but building permits match: offer to switch them on.
    const kinds = effectiveKinds(filters.kinds);
    if (index.permitsLoaded) {
      for (const k of OPT_IN_KINDS) {
        const c = !kinds.includes(k) ? (facets?.kinds?.[k] || 0) : 0;
        if (c) suggestions.push({ label: `Pokaż też: ${dicts.kinds?.[k]?.label || k}`, count: c, patch: { kinds: withOptIn(kinds, [k]) }, keeps: true });
      }
    }
    // Not loaded yet (phones never prefetch it): a register number or an address may only be in the permits.
    const offered = OPT_IN_KINDS.filter((k) => index.kindCodes.includes(k) && !kinds.includes(k));
    const permitsSuggestion = !index.permitsLoaded && offered.length && ctx.permits.state() !== 'unavailable' && !registerDown
      ? {
        label: 'Szukaj też w pozwoleniach na budowę i zgłoszeniach (rejestr GUNB)',
        note: `łącznie ${formatNumber(offered.reduce((a, k) => a + (index.countsByKind[k] || 0), 0))}`,
        patch: { kinds: withOptIn(kinds, offered) },
      } : null;
    for (const it of items) {
      const c = groupCounts[it.group] || 0;
      if (!c) continue;
      // removing one item of a multi-item group is not the same as removing the group; only suggest single items
      const sameGroup = items.filter((x) => x.group === it.group).length;
      if (sameGroup > 1 && it.group !== 'q') continue;
      // The chip wording: Usuń filtr „W pobliżu: promień 250 m”.
      const label = it.group === 'q' ? `Usuń wyszukiwanie ${it.label}` : `Usuń filtr „${it.groupLabel}: ${it.label}”`;
      suggestions.push({ label, count: c, patch: it.remove });
    }
    if (tokens.length > 1) {
      for (const t of tokens) {
        const rest = filters.q.split(/\s+/).filter((w) => tokenize(w)[0] !== t).join(' ');
        const res = evaluate(index.entries, { ...filters, q: rest }, evalCtx({ tokens: tokenize(rest) }));
        if (res.results.length) suggestions.push({ label: `Szukaj bez słowa „${t}”`, count: res.results.length, patch: { q: rest } });
      }
    }
    // Suggestions that keep everything the visitor asked for (only add permits) come first, then the
    // loosening ones by the number of results they would give.
    suggestions.sort((a, b) => Number(Boolean(b.keeps)) - Number(Boolean(a.keeps)) || b.count - a.count);
    if (permitsSuggestion) suggestions.unshift(permitsSuggestion);
    // "Grochowska 300" is not in any list, but its neighbours may be: offer the area around the nearest house number.
    const hit = filters.q?.trim() && !filters.near ? nearestAddressPoint(index, filters.q) : null;
    if (hit) {
      const near = { lat: roundNear(hit.lat), lon: roundNear(hit.lon), r: 500 };
      const res = evaluate(index.entries, { ...filters, q: '', near }, evalCtx({ tokens: [] }));
      if (res.results.length) {
        suggestions.unshift({
          label: `Pokaż wpisy w promieniu 500 m od „${filters.q.trim()}”`,
          note: `punkt przybliżony: ${hit.entry.rec.address?.display || hit.number}`,
          patch: { q: '', near }, near: true,
        });
      }
    }
    const onlyRegister = effectiveKinds(filters.kinds).every(isOptInKind);
    if (registerDown && onlyRegister) {
      // The register failed to load and only its kinds are selected: offer the planning records instead.
      const planning = evaluate(index.entries, { ...filters, kinds: [...DEFAULT_KINDS] }, evalCtx()).results.length;
      if (planning) suggestions.unshift({ label: 'Pokaż decyzje WZ, CP i wszczęte postępowania', count: planning, patch: { kinds: [...DEFAULT_KINDS] } });
    }
    replaceChildren(emptyEl,
      icon(registerDown && onlyRegister ? 'alert' : 'search', { size: 40, class: 'empty__icon' }),
      h('h2', { class: 'empty__title' }, registerDown && onlyRegister ? 'Rejestr pozwoleń jest chwilowo niedostępny'
        : filters.q?.trim() ? `Nic nie znaleziono dla „${filters.q.trim()}”` : 'Żaden wpis nie spełnia wszystkich warunków'),
      registerDown && onlyRegister ? h('button', { type: 'button', class: 'btn btn--secondary', onClick: () => ctx.permits.retry() }, icon('refresh', { size: 16 }), 'Spróbuj ponownie') : null,
      h('p', { class: 'empty__text' }, registerDown && onlyRegister
        ? 'Decyzje WZ, CP i wszczęte postępowania działają normalnie.'
        : suggestions.length ? 'Spróbuj poluzować kryteria:' : 'Sprawdź pisownię lub wyczyść filtry. Wyszukiwarka ignoruje polskie znaki, wielkość liter i typowe końcówki słów.'),
      suggestions.length ? h('ul', { class: 'suggestions' }, suggestions.slice(0, 5).map((sg) => h('li', null,
        h('button', { type: 'button', class: 'suggestion', onClick: () => { if (sg.near) nearFit = true; setFilters(sg.patch); } },
          h('span', null, sg.label), h('span', { class: 'suggestion__count' }, sg.note || plural(sg.count, WYNIK), icon('arrowRight', { size: 14 })))))) : null,
      items.length ? h('button', { type: 'button', class: 'btn btn--secondary', onClick: () => { setFilters('CLEAR'); searchInput.focus(); } }, icon('refresh', { size: 16 }), 'Wyczyść wszystkie filtry') : null);
  }

  /**
   * The note on the map. With a record open (side panel) it speaks about that record – a record without a location
   * says so (the map shows the whole district) – not about the list behind the panel; otherwise it counts the
   * results that are only on the list.
   */
  function renderNogeo() {
    const sel = selectedEntry();
    if (selectedId && !isMobile()) {
      const none = Boolean(sel && !sel.hasGeo);
      nogeoEl.hidden = !none;
      nogeoEl.textContent = none ? 'Ten wpis nie ma lokalizacji na mapie – widać całą dzielnicę.' : '';
      return;
    }
    const missing = results.filter((r) => !r.entry.hasGeo).length;
    nogeoEl.hidden = !missing || !results.length;
    if (!missing) { nogeoEl.textContent = ''; return; }
    nogeoEl.textContent = missing === results.length
      ? (missing === 1 ? 'Ten wynik nie ma lokalizacji – jest tylko na liście' : `Żaden z ${formatNumber(missing)} wyników nie ma lokalizacji – są tylko na liście`)
      : `${formatNumber(missing)} z ${formatNumber(results.length)} wyników bez lokalizacji – ${missing === 1 ? 'jest' : 'są'} tylko na liście`;
  }

  function renderSort() {
    const eff = effectiveSort(filters.sort, tokens.length > 0);
    sortSel.querySelector('option[value="relevance"]').hidden = tokens.length === 0;
    sortSel.querySelector('option[value="relevance"]').disabled = tokens.length === 0;
    sortSel.value = eff;
  }

  function renderTimeline() {
    // Relative presets count back per kind: the band spans every kind's window.
    const spans = periodSpans(filters, bounds.max, latestByKind, filters.kinds);
    const from = spans.map((x) => x.from).filter(Boolean).sort()[0] || null;
    const to = spans.map((x) => x.to).filter(Boolean).sort().pop() || null;
    timeline.setKinds(index.kindCodes.filter((k) => effectiveKinds(filters.kinds).includes(k)));
    timeline.update({ min: bounds.min, max: bounds.max, counts: facets.months, from, to });
  }

  function applyMode() {
    const mode = isMobile() ? state.mode : 'list';
    if (root.dataset.mode !== mode && mode === 'map') window.scrollTo(0, 0);
    root.dataset.mode = mode;
    replaceChildren(modeBtn, mode === 'map'
      ? [icon('list', { size: 18 }), h('span', null, 'Lista')]
      : [icon('map', { size: 18 }), h('span', null, 'Mapa')]);
    // The accessible name starts with the visible word (voice control: "naciśnij Mapa").
    modeBtn.setAttribute('aria-label', mode === 'map' ? 'Lista – pokaż listę wyników' : 'Mapa – pokaż wyniki na mapie');
    if (mode !== 'map') {
      hidePeek({ refocus: false });
      // A forgotten "Wskaż na mapie" must never set a radius later.
      if (isMobile()) cancelPicking();
    }
  }

  function recompute() {
    tokens = tokenize(filters.q);
    // The month axis and "latest month" follow the kind selection (building permits reach back to 2016) …
    const kinds = effectiveKinds(filters.kinds);
    bounds = monthBounds(index, kinds);
    if (!bounds.min) bounds = { min: index.minMonth, max: index.maxMonth };
    // … but a relative preset counts back per kind: the planning lists from their newest month (they are published
    // with a lag), each register kind from its own – adding permits never hides planning records.
    const planning = kinds.filter((k) => !isOptInKind(k));
    const planningMax = planning.length ? monthBounds(index, planning).max : null;
    latestByKind = {};
    for (const k of kinds) latestByKind[k] = isOptInKind(k) ? (index.kindMonths[k]?.max || null) : planningMax;
    panel.setBounds(bounds);
    panel.setPeriodSpans(periodSpans(filters, bounds.max, latestByKind, kinds));
    // Without a visible map (phones in list mode) the "visible area" count uses the same fallback as the toggle.
    const viewBbox = mapApi && mapVisible() ? mapApi.getBbox() : (lastBbox || DISTRICT_BBOX);
    const res = evaluate(index.entries, filters, evalCtx({ viewBbox }));
    results = sortResults(res.results, effectiveSort(filters.sort, tokens.length > 0));
    facets = res.facets;
  }

  /** Which filter changes should move the map to the results. */
  function locationChanged(a, b) {
    if (!a) return false;
    return a.q !== b.q || a.streets.join() !== b.streets.join() || a.areas.join() !== b.areas.join() || a.file !== b.file;
  }

  /**
   * Re-render everything that depends on the result set (filters changed or new data arrived).
   * New data (meta.source 'data', e.g. the idle prefetch of permits.json) must not disturb the visitor: when the
   * result list is unchanged its cards stay as they are (scroll position, pages already shown, keyboard focus);
   * otherwise as many cards as were shown are rendered again and a focused card keeps the focus.
   */
  function renderAll(meta = {}) {
    const fromData = meta.source === 'data';
    const prevIds = fromData ? results.map((r) => r.entry.id).join('|') : null;
    const shown = listEl.querySelectorAll('.card:not(.card--skeleton)').length;
    const focusedId = fromData ? document.activeElement?.closest?.('#results .card')?.dataset.id || null : null;
    recompute();
    const sameList = fromData && shown > 0 && prevIds === results.map((r) => r.entry.id).join('|');
    renderCount();
    announce();
    renderChips();
    renderSort();
    renderTimeline();
    renderPending();
    renderOutcomeNote();
    renderPromo();
    renderNogeo();
    panel.update(filters, facets, results.length);
    if (!sameList) {
      renderList(fromData ? shown : 0);
      renderEmpty();
      if (focusedId) listEl.querySelector(`[data-id="${CSS.escape(focusedId)}"] .card__link`)?.focus({ preventScroll: true });
    }
    if (mapApi) {
      mapApi.setLegendKinds(legendKinds());
      mapApi.setResults(results.map((r) => r.entry));
      mapApi.setNear(filters.near, { fit: nearFit });
      mapApi.setActiveAreas(filters.areas);
      syncBboxToggle();
      if (filters.bbox && meta.source === 'location') {
        urlBboxPinned = true;
        mapApi.fitBbox(filters.bbox);
      }
      nearFit = false;
    }
  }

  // --- public API --------------------------------------------------------------------------------
  const api = {
    el: root,
    get results() { return results; },
    get mapApi() { return mapApi; },
    searchInput,
    /** Called on every state change. */
    update(nextState, prevState, meta = {}) {
      const prevFilters = filters;
      state = nextState;
      filters = nextState.filters;
      const key = buildHash({ route: 'explore', filters, mode: 'list' });
      const changed = key !== lastKey;
      const fromMap = meta.from === 'map';
      if (changed) {
        lastKey = key;
        if (document.activeElement !== searchInput || meta.source === 'location') {
          searchInput.value = filters.q || '';
        }
        searchClear.hidden = !searchInput.value;
        renderAll(meta);
        // New result set → back to the top of the list (not while typing or panning the map).
        if (!fromMap && meta.source === 'app' && document.activeElement !== searchInput) resultsPane.scrollTo?.({ top: 0 });
        if (mapApi && !fromMap && locationChanged(prevFilters, filters)) autoFit();
      }
      // selection
      const nextSel = nextState.route === 'record' ? nextState.recordId : null;
      if (nextSel !== selectedId) {
        if (selectedId) listEl.querySelector(`[data-id="${CSS.escape(selectedId)}"]`)?.classList.remove('is-selected');
        selectedId = nextSel;
        if (selectedId) {
          const card = listEl.querySelector(`[data-id="${CSS.escape(selectedId)}"]`);
          if (card) card.classList.add('is-selected');
          else if (results.some((r) => r.entry.id === selectedId)) renderList();
        }
        const entry = selectedEntry();
        // Opening a record ends a pending "Wskaż na mapie".
        if (selectedId) cancelPicking();
        mapApi?.select(entry, { fit: Boolean(entry) });
        mapApi?.setLegendKinds(legendKinds());
        syncBboxToggle();
        renderNogeo();
      }
      applyMode();
      // the map may become visible (route switch, mobile map mode) → init lazily, then fix its size
      requestAnimationFrame(() => {
        ensureMap();
        mapApi?.invalidate();
      });
    },
    setAreas(geo) {
      areasGeo = geo;
      if (mapApi) {
        mapApi.setAreas(geo);
        mapApi.setActiveAreas(filters.areas);
        initialFit();
      }
    },
    /** Parcel outlines (parcels.geojson, later parcels-permits.geojson). */
    addParcels(geo) {
      if (!geo) return;
      parcelsGeo.push(geo);
      mapApi?.addParcels(geo);
    },
    /**
     * New records arrived (permits.json): register their markers and re-render the current view
     * in place (list, counts, facets, timeline, promo), keeping the open record selected.
     */
    dataChanged(added = []) {
      if (mapApi && added.length) mapApi.setEntries(added);
      renderAll({ source: 'data' });
      // The open record has just arrived (a permit permalink): now the map can go to it. Otherwise (the idle
      // prefetch) the map stays where the visitor left it.
      const sel = selectedEntry();
      if (sel && mapApi) mapApi.select(sel, { fit: added.some((e) => e.id === selectedId) });
    },
    /** The permits layer started/finished/failed loading. */
    permitsStateChanged() {
      panel.setPermitsState(ctx.permits.state());
      if (facets) panel.update(filters, facets, results.length);
      renderPending();
      renderPromo();
      renderCount();
      announce();
      if (!results.length) { renderList(); renderEmpty(); }
    },
    detailPane,
    resultsPane,
    /** After closing a record: focus its card (rendering more cards if needed). */
    restoreFocus() {
      const id = pendingFocusId;
      pendingFocusId = null;
      if (!id) return false;
      let card = listEl.querySelector(`[data-id="${CSS.escape(id)}"]`);
      if (!card) {
        const idx = results.findIndex((r) => r.entry.id === id);
        if (idx >= 0) {
          renderCards(listEl.children.length, Math.min(results.length, idx + 1));
          limit = Math.max(limit, listEl.children.length);
          updateMore();
          card = listEl.querySelector(`[data-id="${CSS.escape(id)}"]`);
        }
      }
      const link = card?.querySelector('.card__link');
      if (link) {
        link.focus({ preventScroll: true });
        card.scrollIntoView({ block: 'nearest' });
        return true;
      }
      return false;
    },
    rememberFocus(id) { pendingFocusId = id; },
    focusSearch() {
      searchInput.focus();
      searchInput.select();
    },
    /** Esc handling: returns true when something was closed (hover tips first – WCAG 1.4.13). */
    escape() {
      if (mapApi?.closeTooltips()) return true;
      if (timeline.hideTip()) return true;
      if (mapApi?.isPicking()) { cancelPicking(); toast('Anulowano wskazywanie punktu.'); return true; }
      if (root.classList.contains('is-drawer-open')) { closeDrawer(); return true; }
      if (!peek.hidden) { hidePeek(); return true; }
      return false;
    },
    closeDrawer,
    showOnMap(id) {
      if (isMobile()) ctx.navigate({ route: 'explore', recordId: null, mode: 'map' });
      setTimeout(() => {
        const m = ensureMap();
        const entry = index.byId.get(id);
        if (m && entry) {
          m.invalidate();
          if (isMobile()) showPeek(id);
          m.select(entry, { fit: true });
        }
      }, 120);
    },
  };
  return api;
}
