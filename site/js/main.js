/**
 * Bootstrap + router. Loads data, mounts views and keeps them in sync with the URL state (store.js).
 */
import { initStore, getState, subscribe, navigate, canGoBackInApp } from './store.js';
import { loadIndex, loadGeo, loadPermits, addPermits, prepareEntries, fileDataset } from './data.js';
import { permitsNeeded, idlePrefetchAllowed, shouldFetchPermits, IDLE_PREFETCH_DELAY } from './lazy.js';
import { OPT_IN_ID, OPT_IN_KINDS, effectiveKinds, withOptIn } from './kinds.js';
import { buildHash } from './url.js';
import { defaultFilters, sanitizeFilters } from './filters.js';
import { h, replaceChildren, isMobile, trapFocus, isTyping } from './dom.js';
import { icon } from './icons.js';
import { formatNumber } from './format.js';
import { createExplore } from './views/explore.js';
import { renderDetail, renderDetailNotFound, renderDetailLoading } from './views/detail.js';
import { createSources } from './views/sources.js';
import { renderAbout, setAreasAttribution, slashShortcutEnabled } from './views/about.js';
import { toast, initToasts } from './components/toast.js';
import { SOURCE_INDEX_URL, BAIPP_URL } from './config.js';

const BASE_TITLE = 'wzSearch – decyzje WZ, celu publicznego i pozwolenia na budowę, Praga-Południe';

const els = {
  main: document.getElementById('main'),
  explore: document.getElementById('view-explore'),
  sources: document.getElementById('view-sources'),
  about: document.getElementById('view-about'),
  banner: document.getElementById('banner'),
  nav: document.querySelectorAll('[data-nav]'),
};

let index = null;
let explore = null;
let sourcesView = null;
/**
 * Lazily loaded permits layer (permits.json + parcels-permits.geojson):
 * idle | loading | loaded | error | unavailable (this data has no opt-in kinds at all).
 */
let permitsState = 'idle';
let permitsPromise = null;
/** Why the last failed request was made ('idle' = the silent prefetch; see lazy.shouldFetchPermits). */
let permitsFailReason = null;
let aboutRendered = false;
let areasGeo = null;
let detailOpenId = null;
let openedFromList = false;
let releaseTrap = null;
let lastExploreHash = '#/';

/** The data could not be loaded: say so plainly, point to the official lists, keep the technical details folded. */
function showError(err) {
  document.body.classList.remove('is-loading');
  document.body.classList.add('has-error');
  els.explore.hidden = false;
  const ext = (href, label) => h('a', { class: 'link', href, target: '_blank', rel: 'noopener noreferrer' }, label,
    h('span', { class: 'sr-only' }, ' (nowa karta)'));
  const local = /^(localhost|127\.0\.0\.1|\[::1\])$/.test(window.location.hostname);
  replaceChildren(els.explore, h('div', { class: 'page page--error' },
    h('div', { class: 'error-state', role: 'alert' },
      icon('alert', { size: 40, class: 'error-state__icon' }),
      h('h1', { class: 'page__title' }, 'Nie udało się wczytać danych'),
      h('p', { class: 'lead' }, 'Nie udało się wczytać danych wyszukiwarki. Spróbuj ponownie za chwilę.'),
      h('p', null, 'Do tego czasu oryginalne listy znajdziesz na stronie ', ext(SOURCE_INDEX_URL, 'Urzędu Dzielnicy Praga-Południe'),
        ' i ', ext(BAIPP_URL, 'Biura Architektury'), '.'),
      h('div', { class: 'error-state__actions' },
        h('button', { type: 'button', class: 'btn btn--primary', onClick: () => window.location.reload() }, icon('refresh', { size: 16 }), 'Spróbuj ponownie')),
      h('details', { class: 'error-state__details' }, h('summary', null, 'Szczegóły techniczne'),
        h('p', { class: 'muted small' }, h('code', null, err?.message || String(err))),
        local ? h('p', { class: 'muted small' }, 'Uruchamiasz stronę lokalnie? Dane muszą leżeć w katalogu ', h('code', null, 'site/data/'),
          ', a strona musi być serwowana przez serwer WWW, np. ', h('code', null, 'npm run serve'), ' albo ',
          h('code', null, 'python3 -m http.server -d site 8000'), '.') : null))));
}

function setTitle(t) {
  document.title = t ? `${t} – wzSearch` : BASE_TITLE;
}

function updateNav(route) {
  const current = route === 'record' ? 'explore' : route;
  for (const a of els.nav) {
    if (a.dataset.nav === current) a.setAttribute('aria-current', 'page');
    else a.removeAttribute('aria-current');
    if (a.dataset.nav === 'explore') a.setAttribute('href', lastExploreHash);
  }
}

function showView(route) {
  const isExplore = route === 'explore' || route === 'record';
  els.explore.hidden = !isExplore;
  els.sources.hidden = route !== 'sources';
  els.about.hidden = route !== 'about';
  document.body.dataset.route = isExplore ? 'explore' : route;
}

// --- detail panel ----------------------------------------------------------------------------------
function openDetail(state, prev) {
  const host = explore.detailPane;
  const entry = index.byId.get(state.recordId);
  const results = explore.results;
  const i = entry ? results.findIndex((r) => r.entry.id === entry.id) : -1;
  const modal = isMobile();
  const recordChanged = detailOpenId !== state.recordId;
  // A record of a kind that is switched off (a permit from a link or the related records): not among the results.
  const hiddenKind = Boolean(entry && !effectiveKinds(state.filters.kinds).includes(entry.kind));
  const ctx = {
    index,
    modal,
    hiddenKind,
    onShowKind: () => navigate({ filters: { ...state.filters, kinds: withOptIn(state.filters.kinds, [entry.kind]) } }, { replace: true }),
    position: i >= 0 ? { i, n: results.length } : null,
    prevId: i > 0 ? results[i - 1].entry.id : null,
    nextId: i >= 0 && i < results.length - 1 ? results[i + 1].entry.id : null,
    recordHref: (id) => buildHash({ route: 'record', recordId: id, filters: state.filters, mode: state.mode }),
    onOpen: (id) => {
      explore.rememberFocus(id);
      navigate({ route: 'record', recordId: id }, { replace: true });
    },
    onClose: () => closeRecord(),
    onFilter: (patch) => {
      openedFromList = false;
      navigate({ route: 'explore', recordId: null, filters: { ...defaultFilters(), ...patch } });
    },
    onShowOnMap: (id) => {
      if (isMobile()) {
        openedFromList = false;
        explore.rememberFocus(null);
      }
      explore.showOnMap(id);
    },
    permitsState: () => permitsState,
    onRetryPermits: () => ensurePermits('retry'),
  };
  // Re-rendering the same record (filters changed underneath): keep scroll position and focus.
  const focusables = recordChanged ? [] : [...host.querySelectorAll('a[href], button, summary, [tabindex="-1"]')];
  const focusIdx = focusables.indexOf(document.activeElement);
  const scrollTop = recordChanged ? 0 : host.scrollTop;
  const openDetails = recordChanged ? [] : [...host.querySelectorAll('details')].map((d) => d.open);
  if (entry) {
    const info = renderDetail(host, entry, ctx);
    setTitle(`${info.title} (${info.kindLabel})`);
  } else if (OPT_IN_ID.test(state.recordId) && !index.permitsLoaded && permitsState !== 'error' && permitsState !== 'unavailable') {
    // A permalink to a building permit: the permits layer is on its way (see ensurePermits).
    renderDetailLoading(host, state.recordId, ctx);
    setTitle('Wczytywanie wpisu…');
  } else if (OPT_IN_ID.test(state.recordId) && permitsState === 'error') {
    renderDetailLoading(host, state.recordId, ctx, { failed: true });
    setTitle('Nie udało się wczytać wpisu');
  } else {
    renderDetailNotFound(host, state.recordId, ctx);
    setTitle('Nie znaleziono wpisu');
  }
  host.hidden = false;
  explore.el.classList.add('has-detail');
  host.classList.toggle('is-modal', modal);
  if (modal) {
    host.setAttribute('role', 'dialog');
    host.setAttribute('aria-modal', 'true');
    setInert(true);
    releaseTrap?.();
    releaseTrap = trapFocus(host);
  } else {
    // Side panel: a named region (a generic element may not carry aria-labelledby).
    host.setAttribute('role', 'region');
    host.removeAttribute('aria-modal');
    setInert(false);
    explore.resultsPane.inert = true;
  }
  if (recordChanged) {
    host.scrollTop = 0;
    // Move focus into the panel only when the user navigated inside the app (not on first load).
    if (prev) requestAnimationFrame(() => host.querySelector('#detail-title')?.focus({ preventScroll: true }));
  } else {
    host.querySelectorAll('details').forEach((d, k) => { if (openDetails[k]) d.open = true; });
    host.scrollTop = scrollTop;
    if (focusIdx >= 0) host.querySelectorAll('a[href], button, summary, [tabindex="-1"]')[focusIdx]?.focus({ preventScroll: true });
  }
  detailOpenId = state.recordId;
}

function setInert(on) {
  for (const sel of ['.topbar', '.skip-link', '#banner']) {
    const el = document.querySelector(sel);
    if (el) el.inert = on;
  }
  for (const el of [explore.resultsPane, explore.el.querySelector('.pane--filters'), explore.el.querySelector('.pane--map'), explore.el.querySelector('.fab')]) {
    if (el) el.inert = on;
  }
}

function closeDetailPanel() {
  if (!detailOpenId) return false;
  const host = explore.detailPane;
  host.hidden = true;
  host.textContent = '';
  explore.el.classList.remove('has-detail');
  releaseTrap?.();
  releaseTrap = null;
  setInert(false);
  explore.resultsPane.inert = false;
  detailOpenId = null;
  return true;
}

function closeRecord() {
  if (openedFromList && canGoBackInApp()) {
    openedFromList = false;
    window.history.back();
  } else {
    openedFromList = false;
    navigate({ route: 'explore', recordId: null });
  }
}

function openRecord(id) {
  const s = getState();
  openedFromList = s.route === 'explore';
  navigate({ route: 'record', recordId: id }, { replace: s.route === 'record' });
}

// --- permits layer (lazy) -------------------------------------------------------------------------
/**
 * Fetch permits.json (+ parcel outlines) once, merge them into the index and refresh whatever is on screen.
 * @param {string} reason 'kinds' | 'permalink' | 'related' | 'file' | 'idle' | 'retry' (see lazy.js)
 */
function ensurePermits(reason) {
  if (!shouldFetchPermits(permitsState, reason, permitsFailReason)) return permitsPromise;
  permitsState = 'loading';
  document.body.dataset.permits = 'loading';
  explore.permitsStateChanged();
  rerenderDetail();
  permitsPromise = loadPermits().then(async ({ doc, parcels }) => {
    // Search documents are built in slices (no long task), then merged in one go.
    const prepared = await prepareEntries(doc?.records, index.dicts);
    const added = addPermits(index, doc, prepared);
    permitsState = 'loaded';
    permitsFailReason = null;
    // records.json (kept by the browser) and permits.json (fetched now) from two different builds: say so.
    if (doc?.generated_at && index.meta.generatedAt && doc.generated_at !== index.meta.generatedAt) {
      toast('Dane zostały w międzyczasie zaktualizowane – odśwież stronę, aby zobaczyć jedną, spójną wersję.', { timeout: 8000 });
    }
    document.body.dataset.permits = 'loaded';
    if (parcels) explore.addParcels(parcels);
    explore.permitsStateChanged();
    explore.dataChanged(added);
    rerenderDetail();
    sourcesView?.dataChanged();
    try { performance.mark('wz:permits'); } catch { /* old browsers */ }
  }).catch((err) => {
    // A failure after the merge is a bug in rendering, not a missing register: report it, keep the data.
    if (permitsState === 'loaded') { console.error(err); return; }
    permitsState = 'error';
    permitsFailReason = reason;
    document.body.dataset.permits = 'error';
    console.warn('Permits layer not available:', err?.message || err);
    explore.permitsStateChanged();
    rerenderDetail();
    if (reason !== 'idle') toast('Nie udało się wczytać pozwoleń na budowę. Pozostałe dane działają normalnie.', { kind: 'error', timeout: 5000 });
  });
  return permitsPromise;
}

/** Re-render an open record in place (keeps scroll and focus), e.g. once related permits arrived. */
function rerenderDetail() {
  const s = getState();
  if (s.route === 'record' && detailOpenId === s.recordId) openDetail(s, s);
}

/** Does this deployment have opt-in kinds at all (dictionary or counts)? Data without permits: never fetch. */
function hasPermitsLayer() {
  return OPT_IN_KINDS.some((k) => index.dicts.kinds?.[k] || index.countsByKind[k] > 0);
}

function schedulePrefetch() {
  if (!hasPermitsLayer() || !idlePrefetchAllowed(navigator.connection, { smallScreen: isMobile() })) return;
  const run = () => { if (permitsState === 'idle') ensurePermits('idle'); };
  setTimeout(() => {
    if ('requestIdleCallback' in window) window.requestIdleCallback(run, { timeout: 4000 });
    else run();
  }, IDLE_PREFETCH_DELAY);
}

// --- state → views ---------------------------------------------------------------------------------
function onState(state, prev, meta = {}) {
  if (state.unknown) {
    toast('Nie ma takiej strony – pokazujemy listę wpisów.');
    navigate({ route: 'explore', recordId: null }, { replace: true });
    return;
  }
  // A stale or hand-edited link: drop values the data does not know (see filters.sanitizeFilters), then render.
  if (meta.source === 'location') {
    const clean = sanitizeFilters(state.filters, { kindCodes: index.kindCodes, dicts: index.dicts, filesById: index.filesById });
    if (clean !== state.filters) {
      navigate({ filters: clean }, { replace: true });
      return;
    }
  }
  const route = state.route;
  const prevRoute = prev?.route;
  // Browser Back (or a link) while the filters drawer is open: close it, or the inert top bar and the focus trap
  // would outlive it on the next page. Filter edits inside the drawer keep the route and the record.
  if (prev && (route !== prevRoute || state.recordId !== prev.recordId)) explore.closeDrawer({ focus: false });
  showView(route);
  if (route === 'explore' || route === 'record') {
    lastExploreHash = buildHash({ route: 'explore', filters: state.filters, mode: state.mode });
    explore.update(state, prev, meta);
    if (route === 'record') {
      openDetail(state, prev);
    } else {
      const wasOpen = closeDetailPanel();
      setTitle(null);
      if (wasOpen) requestAnimationFrame(() => { if (!explore.restoreFocus()) explore.searchInput.focus({ preventScroll: true }); });
    }
  } else {
    closeDetailPanel();
    if (route === 'sources') {
      if (!sourcesView) sourcesView = createSources(els.sources, index);
      sourcesView.show(state.tab);
      setTitle('Źródła danych');
    } else if (route === 'about') {
      if (!aboutRendered) {
        renderAbout(els.about, index);
        aboutRendered = true;
        if (areasGeo) setAreasAttribution(els.about, areasGeo);
      }
      setTitle('O projekcie');
    }
  }
  updateNav(route);
  if (hasPermitsLayer()) {
    const reason = permitsNeeded(state, {
      loaded: index.permitsLoaded, byId: index.byId, filesById: index.filesById, fileDataset: (f) => fileDataset(index, f),
    });
    if (reason) ensurePermits(reason);
  }
  // Page-level navigation: reset scroll and move focus to the new page heading (screen readers).
  const pageChanged = prev && (prevRoute === 'explore' || prevRoute === 'record' ? 'explore' : prevRoute) !== (route === 'record' ? 'explore' : route);
  if (pageChanged) {
    window.scrollTo(0, 0);
    if (route === 'sources' || route === 'about') {
      requestAnimationFrame(() => (route === 'sources' ? els.sources : els.about).querySelector('h1')?.focus({ preventScroll: true }));
    }
  }
}

// --- keyboard --------------------------------------------------------------------------------------
function onKeydown(e) {
  if (!index) return;
  const state = getState();
  // "/" → search. Never while a record is open (it must not close the record or jump away from it).
  if (e.key === '/' && !e.ctrlKey && !e.metaKey && !e.altKey && !isTyping(e.target) && state.route !== 'record' && slashShortcutEnabled()) {
    e.preventDefault();
    if (state.route !== 'explore') navigate({ route: 'explore', recordId: null });
    requestAnimationFrame(() => explore.focusSearch());
    return;
  }
  if (e.key === 'Escape') {
    if (explore?.escape()) { e.preventDefault(); return; }
    if (state.route === 'record' && !isTyping(e.target)) { e.preventDefault(); closeRecord(); }
    return;
  }
  if ((e.key === 'ArrowLeft' || e.key === 'ArrowRight') && state.route === 'record' && !e.altKey && !e.metaKey && !e.ctrlKey) {
    if (isTyping(e.target) || e.target.closest?.('.leaflet-container, .timeline__chart, select')) return;
    const results = explore.results;
    const i = results.findIndex((r) => r.entry.id === state.recordId);
    if (i < 0) return;
    const j = e.key === 'ArrowLeft' ? i - 1 : i + 1;
    if (j < 0 || j >= results.length) return;
    e.preventDefault();
    explore.rememberFocus(results[j].entry.id);
    navigate({ route: 'record', recordId: results[j].entry.id }, { replace: true });
    requestAnimationFrame(() => explore.detailPane.querySelector('#detail-title')?.focus({ preventScroll: true }));
  }
}

function renderBanner() {
  const parts = [];
  if (index.meta.fixture) {
    parts.push(h('div', { class: 'banner banner--fixture', role: 'note' }, icon('alert', { size: 15 }),
      h('span', null, h('strong', null, 'Dane przykładowe. '),
        h('span', { class: 'banner__long' }, `Pokazujemy ${formatNumber(index.entries.length)} wybranych wpisów (fixture) – pełne dane pojawią się po uruchomieniu potoku.`),
        h('span', { class: 'banner__short' }, `${formatNumber(index.entries.length)} wybranych wpisów (fixture).`))));
  }
  replaceChildren(els.banner, parts);
  els.banner.hidden = !parts.length;
}

async function boot() {
  initStore();
  initToasts();
  try {
    index = await loadIndex();
  } catch (err) {
    console.error(err);
    showError(err);
    return;
  }
  document.body.classList.remove('is-loading');
  if (!hasPermitsLayer()) {
    permitsState = 'unavailable';
    document.body.dataset.permits = 'unavailable';
  }
  renderBanner();
  // A stale or hand-edited link opened cold: clean its filters before the first render (no history entry).
  const first = getState();
  const clean = sanitizeFilters(first.filters, { kindCodes: index.kindCodes, dicts: index.dicts, filesById: index.filesById });
  if (clean !== first.filters) navigate({ filters: clean }, { replace: true });
  explore = createExplore(els.explore, {
    index, getState, navigate, openRecord,
    permits: { state: () => permitsState, retry: () => ensurePermits('retry') },
  });
  subscribe((s, p, m) => onState(s, p, m));
  onState(getState(), null, { source: 'init' });
  document.addEventListener('keydown', onKeydown);
  // Side panel ⇄ full-screen sheet when the viewport crosses the mobile breakpoint.
  window.matchMedia('(max-width: 767.98px)').addEventListener('change', () => {
    const s = getState();
    if (s.route === 'record' && detailOpenId) openDetail(s, s);
  });
  document.querySelector('.skip-link')?.addEventListener('click', (e) => {
    e.preventDefault();
    const route = getState().route;
    if (route === 'explore' || route === 'record') explore.focusSearch();
    else els.main.querySelector('h1')?.focus();
  });
  // Optional layers, loaded after first paint.
  loadGeo('areas.geojson').then((geo) => {
    if (!geo) return;
    areasGeo = geo;
    explore.setAreas(geo);
    if (aboutRendered) setAreasAttribution(els.about, geo);
  });
  loadGeo('parcels.geojson').then((geo) => { if (geo) explore.addParcels(geo); });
  document.body.dataset.ready = 'true';
  try { performance.mark('wz:ready'); } catch { /* old browsers */ }
  schedulePrefetch();
}

if (window.location.protocol !== 'file:') boot();

