# Frontend (`site/`)

A static, build-free web app that makes every row of the Praga-Południe planning spreadsheets – and, on
request, every building permit and notification from GUNB's register – searchable, filterable, mappable and
traceable to its source file. Polish UI, vanilla ES modules, plain CSS, two vendored libraries (Leaflet 1.9.4,
Leaflet.markercluster 1.5.3). No framework, no bundler, no runtime CDN.

Three datasets (docs/DATA_MODEL.md, "v2 extension"): the district's monthly lists (`district`) and the city
architecture office's yearly lists filtered to Praga-Południe (`baipp`) are in `records.json` (kinds `wz`, `cp`,
`ws`, shown by default); GUNB RWDZ building permits `pb` and notifications `zg` are in `permits.json`, **opt-in**
and loaded lazily.

## Run it

```sh
npm install                 # once: playwright-core for the e2e tests (no browser download)
npm run serve               # http://127.0.0.1:8000/ – serves site/ with the real data in site/data/ (= make serve)
python3 -m http.server --bind 127.0.0.1 -d site 8000   # any static server works (make serve without Node)
```

Opening `site/index.html` from disk (`file://`) shows a Polish page explaining how to start a server
(browsers block `fetch()` and ES modules there).

`tests/e2e/server.mjs` options: `--port=8000`, `--data=fixture` (serve `tests/fixtures/site-data/` as `data/`, and
`tests/fixtures/site-data/sources/` as `sources/` first), `--base=/wzSearch/` (mount under a sub-path like GitHub
Pages). When `site/sources/` is missing it serves archive copies from `data/raw/`. It sends `Cache-Control: no-cache`,
listens on 127.0.0.1 only and answers a malformed URL with 404 instead of crashing. Prefer it to Python's
`http.server`, which on macOS resets a module request in about one of 30 cold loads (the page then shows
"Nie udało się wczytać strony – Odśwież" instead of the app).

### Deploy (GitHub Pages or any static host)

Publish the `site/` directory as is. All URLs are relative (works under `https://<user>.github.io/<repo>/`),
routing uses the URL hash (no server rewrites needed), `site/.nojekyll` disables Jekyll processing.
Set `REPO_URL` / `ISSUES_URL` in `site/js/config.js` to show repository and "report an error" links
(empty strings hide them). `og:image` is the relative `img/og.png`; some link-preview crawlers need an
absolute URL — set it once the public URL is known (`npm run og` regenerates the image from current data).

## Architecture

```
site/
  index.html            shell: header/nav, skeleton of the explore layout, file:// guard, early data fetch,
                        module-load failure message, OG/meta
  css/app.css           design tokens (light + dark), layouts for 3 breakpoints, components
  js/config.js          deploy-time settings (repo links, map providers, Geoportal URL, page size)
  js/main.js            bootstrap + router: loads data, mounts views, keyboard shortcuts, detail panel lifecycle
  js/store.js           state ⇄ URL hash (single source of truth), push/replace history, subscribers
  js/url.js             PURE  parse/build of the hash (#/…?q=…)
  js/kinds.js           PURE  kind codes, default (wz, cp, ws) vs opt-in (pb, zg) selection helpers
  js/lazy.js            PURE  when the permits layer is needed (kinds / permalink / related / file / idle) and
                              whether to (re)fetch after a failure (shouldFetchPermits)
  js/data.js            load JSON (+ optional GeoJSON, lazy permits), PURE buildIndex()/addPermits()/monthBounds():
                              prepared entries, street dictionary, per-kind month axis
  js/search.js          PURE  Polish folding (ł→l, ą→a…), tokenizer, AND matching with a light inflection
                              fallback (stem()), relevance, highlight ranges, match snippets
  js/filters.js         PURE  predicates, single-pass facet counts, period presets (per kind group), distance,
                              sorting, outcome coverage, sanitizeFilters (unknown URL values)
  js/active.js          PURE  active-filter chips (labels + exact "remove" patches)
  js/format.js          PURE  Polish plurals, dates ("9 lipca 2026"), months, bytes, distances
  js/csv.js             PURE  CSV export for Polish Excel
  js/copy.js            PURE  UI copy not coming from data (kind explanations, labels, promo wording)
  js/request.js         PURE  "Zapytaj urząd": prefilled request for public information per record (addressee, mailto)
  js/dom.js, icons.js   tiny DOM helpers (text-only insertion of data), focus trap, inline SVG icons
  js/views/explore.js   search, timeline, results, chips, empty state, CSV, map wiring, mobile modes
  js/views/filters-panel.js  facet panel built once from the dictionaries, patched in place (focus-safe)
  js/views/detail.js    record detail: facts (+ permit facts), parcels → Geoportal, related timeline across datasets,
                        provenance per dataset (district / BAiPP snapshots / RWDZ register)
  js/views/sources.js   one tab per dataset: monthly pages (collapsed years), BAiPP pages + snapshots, RWDZ files
  js/views/about.js     glossary, method, limitations, downloads, licences
  js/components/        map.js (Leaflet), timeline.js (SVG histogram), combobox.js (ARIA 1.2), card.js, toast.js
  vendor/               leaflet@1.9.4, leaflet.markercluster@1.5.3 dist files + LICENSE
  img/og.png            Open Graph preview (generated by tests/e2e/og-image.mjs)
```

Data flow: `main.js` → `loadIndex()` (records.json + sources.json in parallel) → `buildIndex()` prepares one
*entry* per record (`month`, `ts`, folded search document, street keys, geo flags, file ids, `dataset`, `issuer`,
`outcome`, permit `scope`/`category`) → every state change runs `evaluate()` once: results **and** all facet counts
in a single pass (an entry failing exactly one filter group only feeds that group's facet). `parcels.geojson` and
`areas.geojson` load after first paint.

### Building permits: opt-in and lazy (`lazy.js`, `main.js → ensurePermits`)

`permits.json` (≈ 2,600 records, 6.9 MB raw / 0.78 MB gzip) and `parcels-permits.geojson` (1.0 MB / 0.17 MB) are
fetched together, once, by `loadPermits()`. `prepareEntries()` then builds their index entries (folded search
documents) in slices of 250 records, yielding to the browser between slices (`scheduler.yield()` or a macrotask) without
touching the index, and `addPermits(index, doc, prepared)` merges them in one go (entries, street dictionary, per-kind
month bounds) – so the UI never sees a half-merged register and no single long task blocks input (a slow phone took
~280 ms in one task before). The pure `permitsNeeded(state)` names the trigger:

| reason | when |
|---|---|
| `kinds` | the kind selection contains `pb`/`zg` (checkbox, promo, permalink with `rodzaj=…,pb`) |
| `permalink` | `#/wpis/pb-…` / `zg-…` is opened before the file is in (detail shows a skeleton panel, never "not found") |
| `related` | an open WZ/CP/ws record lists related `pb-`/`zg-` ids (the related timeline shows "Wczytywanie powiązanych pozwoleń…") |
| `file` | the explore view is filtered by an RWDZ file (`plik=rwdz-…`) |
| idle | ≈ 2.5 s after first render via `requestIdleCallback` – **not** on phones (< 768 px), with Save-Data or on 2G |

States `idle → loading → loaded | error`, plus `unavailable` when the data has no opt-in kinds at all (old data:
never fetched). `body[data-permits]` mirrors it (tests wait on it). While loading with pb/zg selected the list
keeps the other kinds, shows a status strip and – when nothing else matches – skeleton cards, the count reads
"Wczytywanie…" and the live region "Wczytywanie pozwoleń na budowę…" (no "no results" flash);
on error a retry button (filters panel, list strip, related section). After a failure nothing is re-requested by
itself (`shouldFetchPermits()`): only "Spróbuj ponownie" fetches again – except that a *silent* failure of the idle
prefetch is retried once by the first real need – so typing with permits switched on never stacks requests and error
toasts. In the error state the promo and the "Szukaj też w pozwoleniach" suggestion are not offered; with only pb/zg
selected the strip says "Nie udało się wczytać rejestru pozwoleń GUNB" and the empty state "Rejestr pozwoleń jest
chwilowo niedostępny" (with a retry and "Pokaż decyzje WZ, CP i wszczęte postępowania"). When permits.json comes
from another build than the records.json in the page (`generated_at` differs) a toast asks to reload. After loading, `explore.dataChanged()`
re-renders facets/timeline/map/promo in place; the **list is left untouched when its result set did not change** (the
usual case of the idle prefetch with permits switched off: the cards already shown, the scroll position and the
keyboard focus stay), otherwise as many cards as were shown are rendered again and a focused card keeps the focus. An
open detail is re-rendered keeping scroll and focus. The Sources page re-renders a tab only when its own "Pokaż N
wpisów" numbers change (never the district/BAiPP tab a visitor is reading; register files show the case count from
`sources.json` before the merge, so their tab does not change either).

Before the file is loaded the **Rodzaj** facet shows pb/zg with the totals from `records.json → counts_by_kind`
(italic, "łącznie N"); afterwards the counts follow the other filters like every facet. Because switched-off
permits fail only the kind group, they never leak into other facets, the timeline or the "N z M" total (which is the
number of records of the selected kinds, `facets.scopeTotal`). Measured on the real data (3,165 entries):
`addPermits` ≈ 80 ms (now in 10–20 ms slices), `evaluate` 0.4 ms (default) – 2.7 ms (two-word search with permits on).

Load timing on the real data (Chrome, gzip like GitHub Pages, 150 ms RTT, 16 Mbit/s; phone = 390 px with 4× CPU
slowdown; first-party files only): first contentful paint ≈ 0.4 s, data interactive ≈ 1.24 s desktop / 1.38 s phone
(≈ 450 kB transferred); with permits on, the register is in ≈ 2.1 s desktop / 2.5 s phone (≈ 1.4 MB in total).
Longest main-thread task after the merge: desktop none over 50 ms, phone 73 ms (before: 98 ms / 342 ms).

The month axis, year buttons and month selects follow the kind selection (`monthBounds()`): permits reach back to
2016 and forward to the current month, the planning lists start in 2020. The relative presets ("Ostatnie 3/12 mies.")
count back **per kind group** (`periodRanges()`): the planning kinds from their newest month (incl. the newest monthly
page), each register kind from its own – so switching permits on never hides July's WZ because the register already
has October. The period note names both windows when they differ ("WZ, CP, Wszczęcie: lip 2026 – wrz 2026 · Pozwolenie:
sie 2026 – paź 2026"); the timeline band spans both.

Loading without a bundler: a tiny inline script in `<head>` starts `fetch('data/records.json'|'data/sources.json',
{cache: 'no-cache'})` at once and leaves the promises in `window.__wzEarly`; `data.js` takes each one once (a retry
fetches again). It replaced `<link rel=preload as=fetch>`, which ignored `cache: 'no-cache'` (a new tab could show
the previous build's records next to a fresh permits.json for up to max-age after a deploy) and which WebKit did not
reuse (every file downloaded twice). `index.html` also `modulepreload`s **every** module in `site/js/`, so the data
download and the whole ES-module graph start in parallel with the HTML instead of after a 4-level import waterfall
(measured at 150 ms RTT / 16 Mbit/s: data ready after ~1.34 s instead of ~2.0 s). If a module fails to load
(`onerror` on the main module script) the skeleton is replaced by "Nie udało się wczytać strony" with "Odśwież".
`tests/js/index-html.test.mjs` fails when a module is added/renamed without updating the hints.
`<link rel="alternate" type="application/atom+xml">` advertises `feed.xml` to feed readers.

### Search

* Folding: case, Polish diacritics, typographic quotes/dashes. Tokens are AND-ed; street prefixes (`ul.`, `ulicy`, `al.`)
  and short prepositions/conjunctions (`w`, `na`, `i`, `z`, `przy`…) are ignored.
* Street keys and the "Ulica A–Z" order strip a prefix only when it is one: an abbreviation needs its dot
  (`ul.`, `al.`, `gen.`, `ks.`, `św.`, `pl.`…), a word a space (`Plac `, `Aleja `, `Rondo `) – "Algierska", "Aldony",
  "Genewska", "Księcia Józefa Poniatowskiego" keep their names (`streetSortKey()`).
* "What is near address X": a query of a known street + house number that finds nothing ("Grochowska 300") offers
  first "Pokaż wpisy w promieniu 500 m od „Grochowska 300”" around the located record with the nearest house number on
  that street (same side wins a tie; street-midpoint points never count; at most 20 numbers away;
  `nearestAddressPoint()`).
* Matching: a token matches a field as a substring (so prefixes work while typing: `grochow` → Grochowska), or — for
  words of ≥ 4 letters — by **inflection**: `stem()` strips one Polish ending (`-ego`, `-iej`, `-ach`, `-a`, `-y`…) and the
  mobile *e* of `-ek`, and a token stem matches a word stem when equal, or as a prefix when ≥ 5 letters. So
  „stacja bazowa” finds „stacji bazowej”, „budynek mieszkalny” finds „budynku mieszkalnego” (41 → 233 records on the
  real data), „Kamionku” finds Kamionek, „na Saskiej Kępie” finds Saska Kępa. Inflected hits score below exact ones
  and are highlighted as whole words. Evaluation stays < 1 ms for 474 records.
* Searchable fields (v2): permit register number and office case sign (weight just below decision numbers), and at
  low weight the outcome label ("odmowa"), dataset short label ("BAiPP") and permit scope ("rozbiórka").
* Parcels can be searched the way the detail panel prints them or Geoportal shows them: the designators `dz.`,
  `działka/działki/działek`, `obr.`, `obręb`, `nr` are ignored like `ul.` („dz. 46/4 obr. 3-01-24”, „działka 46/4”), and
  the cadastral id is searchable („146507_8.0605.25/12”; the card then explains „Identyfikator działki: …”).
* Match context on cards: when a query word has no *visible* hit on a card (parcel numbers, the typo-corrected street
  name of a misspelt address, the tail of a truncated applicant/investment), the card shows one highlighted excerpt,
  e.g. „Działki: dz. **46/4** obr. 3-01-24” or „Wnioskodawca: …Pl. **Starynkiewicza** 5…” (`matchContext()` in card.js).
  Card titles are clamped to three lines (multi-street ULICP addresses run to 200 characters); a hit beyond the first
  90 characters of the address counts as hidden and gets the „Ulica: …” excerpt.

Data from the spreadsheets is untrusted: it is only ever inserted with `textContent`/attributes (never
`innerHTML`); URLs from data pass `safeUrl()` – normalised the way the browser's URL parser reads them (tab/CR/LF
removed, C0 and spaces trimmed: "java\tscript:" is a javascript: URL), then accepted only when the *parsed* scheme is
http(s) (relative links included; protocol-relative `//host` rejected); map tooltips get DOM nodes; the area
attribution is HTML-escaped.

### Layout

| width | layout |
|---|---|
| ≥ 1200 px | filters (312 px, 328 px ≥ 1680) │ results │ map; the record detail covers the results column (map keeps showing the parcel) |
| 768–1199 px | results │ map; filters in a modal drawer ("Filtry" button with active-filter badge) |
| < 768 px | one column; floating **Mapa/Lista** toggle; filters and record detail are full-screen modal sheets; tapping a marker shows a peek card; the brand shows "Praga-Południe" from 390 px |

The filters host and the detail host are `div`s – named regions, `role=dialog` (+ `aria-modal`) while they are the
drawer/sheet. The explore view has an (sr-only) `h1` "Przeglądaj wpisy" and an sr-only `h2` "Lista wyników" before
the cards, so the cards are not filed under the timeline's heading. A dismissible intro strip above the results
(first visit; `localStorage` `wzsearch:intro-dismissed`, best effort) says what WZ/CP/wszczęcia are, that a WZ is not
a building permit and that the service is unofficial – phones show neither the top-bar note nor the glossary.

## URL (hash) parameters

Routes: `#/` (explore), `#/wpis/<id>` (record detail on top of the explore state), `#/zrodla` (sources),
`#/o-projekcie` (about). Unknown routes fall back to `#/` with a toast. Invalid values are dropped silently: malformed
ones while parsing (lookups are own-key only – `okres=constructor` or `sort=__proto__` are not values), and values the
data does not know (a renamed tag, a replaced file, `rodzaj=zz`) once records.json is in (`sanitizeFilters()`, the
hash is then replaced without a history entry). Street keys are kept (a street may come only from the permits).

| param | example | meaning |
|---|---|---|
| `q` | `q=przedszkole+grochowska` | search (all words must match; case/diacritics-insensitive) |
| `rodzaj` | `rodzaj=wz,cp` | kind selection, ordered `wz, cp, ws, pb, zg`. **Absent = the default `wz,cp,ws`** (never written to the URL); `rodzaj=wz,cp,ws,pb` switches building permits on; an empty/invalid value falls back to the default |
| `okres` | `okres=3m` / `okres=12m` | relative period, counted back per kind group from its newest month (planning lists / each register kind) |
| `od`, `do` | `od=2024-01&do=2024-12` | month range (inclusive); a whole year shows as "2024" |
| `typ` | `typ=wielorodzinny,nowa-budowa` | tag slugs from `records.json → tags` |
| `wnioskodawca` | `wnioskodawca=osoba,firma` | applicant type: `osoba`, `firma`, `nieustalony` |
| `obszar` | `obszar=kamionek` | area slugs from `records.json → areas` |
| `zrodlo` | `zrodlo=baipp` | dataset keys from `records.json → datasets` |
| `organ` | `organ=city,voivode` | issuer keys from `issuers` |
| `rozstrzygniecie` | `rozstrzygniecie=refusal` | outcome keys from `outcomes` |
| `zakres` | `zakres=budowa,rozbiorka` | permit scope keys from `permit_scopes` (only pb/zg have one) |
| `kategoria` | `kategoria=XIII` | building category keys from `permit_categories` |
| `ulica` | `ulica=grochowska` | folded street keys (`ul. Grochowska`, `Grochowska` work too) |
| `lokalizacja=1` | | only records with a map location |
| `mapa` | `mapa=21.05,52.22,21.10,52.26` | "only the visible map area" (west,south,east,north); updated as the visitor moves the map – a shared link keeps its area until then (the fit to another screen does not rewrite it) |
| `blisko`, `promien` | `blisko=52.255,21.076&promien=500` | near a point, **rounded to 3 decimals (≈ 100 m)** in both directions (privacy of shared links); radius 250 / 500 / 1000 m |
| `plik` | `plik=a1b2c3d4e5` | only records from one source file (links from the Sources page) |
| `sort` | `sort=najstarsze` | `najnowsze` (default), `najstarsze`, `ulica`, `trafnosc` (default while searching) |
| `tryb=mapa` | | mobile: show the map instead of the list |

Sources tabs live in the path: `#/zrodla` (first dataset), `#/zrodla/baipp`, `#/zrodla/rwdz`.

Within one parameter values are OR-ed, different parameters are AND-ed. History: filter changes push a
history entry (typing in the search box pushes once, then replaces); map panning, prev/next in the detail panel
replace. Closing a detail opened from the list goes *back* (so the browser Back button behaves as expected).

## What the UI reads from the data contract (`docs/DATA_MODEL.md`)

* `records.json`: `generated_at`, `source_index_url`, `fixture` (shows a "sample data" banner), dictionaries
  `kinds{label, short, description?}`, `tags{label, description?, group?}`, `areas{label}`, and (v2)
  `datasets{label, short, publisher, url, licence?, description}`, `issuers{label, short?}`, `outcomes{label}`,
  `permit_scopes{label}`, `permit_categories{label}`, `counts_by_kind`. All labels come from the dictionaries.
  Codes the UI does assume (all fixed by DATA_MODEL): the kind codes `wz/cp/ws/pb/zg` (colours, shapes, explanations,
  default vs opt-in), the outcome codes for emphasis only (`refusal` → red badge + callout; `granted` gets no card
  badge), the dataset codes `district/baipp/rwdz` for the layout of the Sources tabs and the provenance block, and the
  permit scope `rozbiorka` (step label "pozwolenie na rozbiórkę"). Tags are grouped by `group`
  (`funkcja` → "Co powstaje", `roboty` → "Rodzaj robót"); tags with no records are hidden.
* Facet visibility: options without any record for the current kind selection are hidden (`availableOptions()`);
  "Źródło danych" and "Organ" need ≥ 2 options, "Rozstrzygnięcie" ≥ 1, "Zakres robót" / "Kategoria obiektu" only
  with pb/zg switched on (categories: top 6 + "Pokaż wszystkie"). "Organ" is also hidden while it splits the records
  exactly like "Źródło danych" (`sameSplit()`: with the planning kinds only, district office ↔ district lists and city
  bureau ↔ BAiPP) – it appears with the permits (district office, city, voivode, other in one dataset).
* v2 record fields: `dataset`, `issuer`, `outcome`, `filed_date`, `permit{register_id, case_sign, scope, scope_label,
  category, category_label, single_family, cubature, state}`; sources of pb/zg: `rows`, `extract_rows`, `sheet: null`.
  Optional geo fields: `geo.uncertainty_m` (street points: dashed circle, "w promieniu ok. N m", widens "W pobliżu")
  and `geo.conflict` (hollow marker, „Lokalizacja niepewna”); both are read only when present.
* Record fields: all of the schema, plus the documented extensions `address.parts` (every street of an
  intersection/list is searchable and filterable), `address.approximate`, `parcels[].access` ("dojazd" badge).
  Every field may be null/missing; the UI degrades (e.g. title falls back to investment text or number).
* `sources.json`: `pages[]` (title, period, published_at, url, `source`, blocks with declared/parsed counts,
  `warnings`), `files[]` (filename, url, archive_path, size, sha256, last_modified, history, error, page_ids,
  parsed_count, warnings; BAiPP `rows_total`; RWDZ `source`, `dataset_url`, `licence`, `etag`, `sha256_zip`,
  `size_zip`?, `zip_member`?). A file's dataset is its own `source`, else the `source` of its first linking page,
  else `district`. The record detail lists **every** page that links a record's file.
* `parcels.geojson` (optional) + `parcels-permits.geojson` (lazy, merged into the same parcel index): polygons for
  `geo.parcels_found`; without them the selection falls back to `geo.bbox`. `areas.geojson` (optional): `_district`
  outline + neighbourhoods, `attribution` shown on the map; the About page credits OpenStreetMap in Polish with the
  optional `copyright_url`, `licence`, `licence_url` and `fetched_at` (the English `source` stays as a tooltip).
* Optional downloads probed on the About page: `data/records.csv`, `data/permits.json`, `data/permits.csv`,
  `data/parcels-permits.geojson`, `feed.xml` (a missing file shows "niedostępne w tej wersji"; the browser console
  logs the 404 of the probe).

## Record detail and Sources page (real-data behaviour)

* **Outcome** (BAiPP only states it): a badge next to the kind ("Odmowa" in red with a ⊘ icon; other non-positive
  outcomes neutral; positive ones get no card badge), a "Rozstrzygnięcie" fact and, for refusals, a callout that says
  what it means for residents (no building on that basis; appeal to SKO). Dataset marker ("BAiPP") on cards and detail
  for records outside the primary dataset. The "Rozstrzygnięcie" facet carries a permanent note (only BAiPP states
  it), and while it is active a note above the list says how many of the matching WZ/CP decisions state an outcome at
  all ("znamy je dla 30 z 61 decyzji WZ…; pozostałych 31 ten filtr nie obejmuje", `outcomeCoverage()`; also spoken by
  the live region). In the related-records summary a negative outcome names the step ("umorzenie WZ 10.2023 → odmowa
  WZ 03.2025"); long chains count them ("3 decyzje WZ (w tym 1 odmowa, 1 umorzenie)").
* **Facts wording**: initiated proceedings say "Wniosek o: decyzję o warunkach zabudowy (WZ)" (accusative). The period
  row is "Opublikowano w zestawieniu" for the district lists; for BAiPP (period = the date's month) it appears only
  when the date is missing ("Miesiąc wszczęcia" / "Miesiąc decyzji").
* **A record whose kind is switched off** (a permit permalink or a permit clicked in "Powiązane wpisy" while permits are
  hidden): the bar shows no "N z M" / "poza wynikami" (it is not among the results), the intro says "Pozwolenia są
  teraz ukryte na liście wyników" with "Pokaż pozwolenia na liście" (adds the kind, keeps the record open), the map
  legend lists its kind, the map's list note and the visible-area count are not shown. A record outside the current
  filters says "poza wynikami" (title "Ten wpis nie pasuje do bieżących filtrów"). Missing prev/next targets are
  disabled `<button>`s (named), not `<a>`s without href.
* **A WZ/CP/ws record with later building permits** on its parcel/address gets one line under the title: "Później na
  tej samej działce lub pod tym adresem: N pozwoleń na budowę – zobacz „Powiązane wpisy”" (scrolls there).
* **Permits (pb/zg)**: register number (GUNB), office case sign, "Wniosek → decyzja" with the duration
  ("decyzja po 66 dniach", `decisionAfter()`), scope (dictionary label + the register's wording), category
  ("XIII – …"), single-family flag, cubature, notification state, issuer; investor shown as GUNB publishes it
  (natural persons are blank → "osoba fizyczna", zg has no investor column). A notification's number *is* its office
  case sign, so it is shown once. The pb explainer says what the register holds ("zakończona decyzją urzędu – zwykle
  pozwoleniem"; WZ precedes it only where there is no local plan – most permits in Saska Kępa need none).
* **Provenance per dataset**: district – page(s) + file + sheet/row + raw cells (as before); BAiPP – the same plus
  "Plik ogólnomiejski: N wierszy, dla Pragi-Południe: M" and, when a row appears in several monthly snapshots of the
  current-year file, the newest snapshot in full and the older ones collapsed; RWDZ – dataset name, publisher,
  licence (CC0 link), file (CSV in the GUNB ZIP), original line numbers ("96620–96631, 96633", digits not grouped –
  they are references for `sed -n 96620p`, `formatLineList()`) and the lines in our extract,
  "Stan rejestru: z <ZIP Last-Modified> – ta wersja pliku GUNB posłużyła do wyciągu" and, separately, "Sprawdzono:
  <permits/records generated_at>", links "Wyciąg dla Pragi-Południe (CSV)", "Plik ZIP (GUNB)", "Zbiór na dane.gov.pl", the raw columns
  (no designer columns) and an honest note that GUNB has no stable per-case links (CAPTCHA search).
* **Related records across datasets**: the timeline includes permits on the same parcel/address
  ("wszczęcie 09.2022 → decyzja WZ 01.2023 → … → pozwolenie na budowę 01.2024"; demolition permits are named as such);
  permits load on demand for it even when pb/zg are switched off. A caveat notes that a shared parcel is not always the
  same investment. Links from a permit's detail to a tag/area keep permits switched on.
* **Related records** (`related` ids + the record, chronological): up to 6 records get the step summary
  („wszczęcie 07.2022 → decyzja WZ 09.2022”). Longer chains — on the real data one large subdivided parcel
  (dz. 3, obr. 3-02-03) links 34 records of the Chodakowska/Żupnicza development — get a counted summary
  („33 powiązane wpisy z lat 2021–2022: 14 decyzji WZ · 9 decyzji CP · 11 wszczęć” – the same number as the section
  heading; the kind counts include the record itself) and show 7 records around the current one, with
  „Wcześniejsze/Późniejsze: N wpisów – pokaż wszystkie” to expand and „Zwiń listę” to restore the window. Every item
  says *why* it is related („wspólna działka 3 (obr. 3-02-03)”, „wspólne działki 35, 36, 37 i 2 inne (obr. 3-06-03)”,
  „ten sam adres”; `relationReason()`).
* **Location caveat**: for street-level points the pipeline note's „lokalizacja przybliżona – ulica / skrzyżowanie ulic”
  becomes the label („Lokalizacja przybliżona (skrzyżowanie ulic)”) instead of being repeated after it; with the
  optional `geo.uncertainty_m` it adds „miejsce może leżeć w promieniu ok. 700 m od punktu”. For records without a
  location the note's „– nie pokazano/pokazujemy … na mapie” is dropped (the label already says it). A parcel point
  whose stated address lies on a parcel of another precinct (`geo.conflict`, 9 permits) reads „Lokalizacja niepewna –
  adres i działki się różnią” plus the pipeline's distance note, and its marker is hollow; the stated parcels are
  still outlined. Precincts the pipeline corrected by the address come with a record warning
  („obręb w źródle (3-06-03) prawdopodobnie błędny – …”).
* „Oznaczenie działek w źródle” renders the raw cell with the office's space-run line breaks turned into real ones
  (`tidyCell()`); the raw-row table already uses the pipeline's tidied `sources[].raw`.
* **Sources page = tabs per dataset** (`#/zrodla/<dataset>`, ARIA tabs with ←/→/Home/End, each panel rendered on
  first visit). District: years older than the latest two are collapsed `<details>` rendered only when opened
  (summary: months · rows · mismatches); "Tylko niezgodności" opens the years with mismatches; year buttons open and
  scroll. BAiPP: yearly pages with their four files ("plik ogólnomiejski: 162 wiersze, dla Pragi-Południe: 5"),
  older snapshot files of a page collapsed, totals city-wide vs kept. RWDZ: dataset description, licence, coverage
  caveats, and one card per register snapshot (title without the repeated ZIP name; "wynik_mazowieckie.zip (44,3 MB) ·
  w środku wynik_mazowieckie.csv"; "Stan rejestru: z <Last-Modified of the ZIP>" and "Sprawdzono: <records generated_at>",
  rows in the file, Praga-Południe rows, cases, ETag, SHA-256 of the ZIP, ZIP / extract / dane.gov.pl links,
  "Pokaż N wpisów" → explore with that kind switched on). District years are `<h2>` headings inside their `<summary>`
  (page outline h1 → h2 year → h3 month); the year buttons jump instantly with reduced motion and move the focus to
  that year. The page's `scroll-padding-top` follows the bottom of the sticky top bar + tabs + toolbar
  (`--sticky-top`, measured with a ResizeObserver – the toolbar wraps on phones), so keyboard focus never lands
  under them.
* **Sources page reconciliation** (`reconcile()` in sources.js, per dataset): declared counts are compared only where the office
  stated one („Urząd zadeklarował 443 pozycje – w tych blokach odczytaliśmy 441 wierszy (różnica w 1 bloku)”); rows
  from pages that state no count (Aug–Oct 2020: 33 rows) are reported separately, then the total
  („Razem 474 wiersze → 474 wpisy”). Blocks without a declared count show a neutral „liczby nie podano · odczytano N”
  pill instead of a green check with „deklarowano ?”.

## Explore view: discovering permits

* **Rodzaj** facet: the three planning kinds (ticked by default), then "Rejestr budowlany GUNB" with pb/zg (unticked).
  A "tylko" button on each kind row (on hover/focus, in place of the count; hidden on touch screens) keeps just that
  kind; "Domyślne" restores the default selection. Kind chips: "Rodzaj: + Pozwolenie" when added to the default,
  plain "Rodzaj: WZ" when narrower; removing the last kind restores the default.
* **Promo** above the results (`promoText()`): before permits.json is loaded only register totals are known, so
  without other filters it reads "Pokaż też pozwolenia na budowę (łącznie 2365)" (+ "Razem ze zgłoszeniami (łącznie
  226)"), and next to an active search/filter – where a total would read as matches – "Sprawdź też pozwolenia na budowę
  dla tego wyszukiwania" with no number (phones never prefetch). Once loaded, the counts follow the filters
  ("Pasujące do tych kryteriów: 4 pozwolenia na budowę", "Razem ze zgłoszeniami (2)"). Dismissible (remembered in
  `localStorage`, best effort); hidden when there are no results (the empty state then suggests "Pokaż też:
  Pozwolenie…" with its count) or the register failed to load. The count is glued to the last word, so it never wraps
  onto a line of its own on phones; the secondary link wraps (no sideways scroll below 320 px).
* **Cards**: at most three tag chips on phones plus "+N" (tags of the active tag filter first, then those the search
  matches; wider screens and the detail list all of them). Register texts written in capitals are sentence-cased for
  display on permit cards and in their one-line excerpts under "Powiązane wpisy" ("Budynek mieszkalny wielorodzinny z
  garażem podziemnym"; acronyms ≤ 4 letters, roman
  numerals and the name after "ul."/"al." keep their case; names and the detail/raw views are untouched).
* **Empty state**: suggestions that keep the visitor's query and filters and only add permits ("Pokaż też: …", exact
  counts once loaded) come first, then the loosening ones by result count ("Usuń filtr „W pobliżu: promień 250 m””,
  the chip wording). Before the register is loaded (phones never prefetch it) the first suggestion is "Szukaj też w
  pozwoleniach na budowę i zgłoszeniach (rejestr GUNB)" with the total – a GUNB register number or a permit-only
  address is otherwise "not found" on a phone. A street + house number query gets "Pokaż wpisy w promieniu 500 m od …"
  first (see Search).

## CSV export ("Pobierz wyniki (CSV)")

Exactly the filtered set, in the current sort order. UTF-8 **with BOM**, `;` delimiter and decimal **comma** in
coordinates (what Polish Excel expects on double-click), CRLF line endings, RFC 4180 quoting, cells starting
with `= + - @`, TAB or CR prefixed with `'` against formula injection – unless the whole cell is a plain number
(`-5`, `-12,5`), so "-1+1" or "-2+3+cmd|…" cannot run (the same rule in `pipeline/export.py`) – multiple values joined
with ` | `. `arkusz_wiersz` is `<sheet>!<row>`: a blank sheet name (some BAiPP workbooks name a sheet " ") reads
`(arkusz bez nazwy)!26`, RWDZ rows have no sheet (`!<line>`). The file name carries the
Warsaw date ("wzsearch-praga-poludnie-2026-10-23.csv", also after midnight). Columns (`CSV_COLUMNS` in `site/js/csv.js`, mirrored by `pipeline/export.py` for `data/records.csv`):
`id, rodzaj, rodzaj_opis, postepowanie, numer, data, data_w_zrodle, okres_sprawozdawczy, wnioskodawca,
typ_wnioskodawcy, inwestycja, adres, ulica, numer_budynku, dzialki, dzialki_w_zrodle, typy_inwestycji, obszar,
szerokosc_geogr, dlugosc_geogr, dokladnosc_lokalizacji, uwagi, powiazane_wpisy, link, plik_zrodlowy, plik_url,
kopia_archiwalna_url, strona_zrodlowa, strona_zrodlowa_url, arkusz_wiersz` and (v2, appended in this order)
`zrodlo_danych` (dataset label), `organ` (issuer label), `rozstrzygniecie` (outcome label or empty), `data_wniosku`
(filed_date), `nr_w_rejestrze`, `znak_sprawy_urzedu`, `zakres_robot` (scope_label as printed), `kategoria_obiektu`
("XIII – label", `categoryText()`), `kubatura_m3` (decimal comma). Permits switched on are exported like any record.

## Map

* Base map: OpenStreetMap standard tiles muted with a CSS filter (inverted for dark mode) – set on every tile
  (`.tiles-muted .leaflet-tile`), not on Leaflet's 0×0 layer container: WebKit (Safari, every iOS browser) does not
  paint filtered children at negative offsets of that container, leaving the map blank west/north of its origin.
  **CARTO Positron was planned but CARTO now returns an "API KEY REQUIRED" tile to keyless requests**
  (verified 2026-10-23 for `light_all`, `dark_all`, `voyager`) — swap providers in `config.js → BASEMAP`.
* "Ortofotomapa": GUGiK WMS `https://mapy.geoportal.gov.pl/wss/service/PZGIK/ORTO/WMS/StandardResolution`,
  layer `Raster`, WMS 1.3.0, EPSG:3857 (verified with GetMap).
* "Granice działek" overlay: GUGiK KIEG WMS `https://integracja.gugik.gov.pl/cgi-bin/KrajowaIntegracjaEwidencjiGruntow`,
  layers `dzialki,numery_dzialek`, from zoom 16 (verified; the host answers with a 302 to `integracja01…`, which
  browsers follow).
* Parcel links: `https://mapy.geoportal.gov.pl/imapnext/imap/?identifyParcel=<id>` — verified in Chrome: the
  current Geoportal zooms to the parcel and opens its identification panel (the legacy
  `imap/Imgp_2.html?identifyParcel=` also works; configurable).
* Markers: inline SVG, shape + colour per kind – WZ circle/indigo `#4f46e5`, CP diamond/teal `#0d9488`, wszczęcie
  square/amber `#d97706`, pozwolenie triangle ▲/plum `#86198f`, zgłoszenie inverted triangle ▼/green `#116611`
  (dark: `#7a80f0 #12a596 #c0820f #bb33aa #117711`); the same shapes are used by the glyphs in filters, legend and
  badges (`icons.js → KIND_SHAPES`). The five colours pass the dataviz validator **all-pairs** (scatter rule): light
  on white – CVD ΔE ≥ 12.5, normal-vision ΔE ≥ 18.1, all ≥ 3:1; dark on `#191b1f` – CVD ΔE ≥ 9.3, normal ΔE ≥ 18.6,
  all ≥ 3:1. Hollow = approximate location (address or street point, or parcels that disagree with the stated address,
  `geo.conflict` – tooltip „lokalizacja niepewna – adres i działki się różnią”); a 2 px surface ring separates overlapping markers; the selected marker gets
  a halo. The legend lists the kinds drawn on the map: the current selection plus the kind of an open record shown on
  its own (the ▲ of a permit opened while permits are hidden). The selection draws the parcels (or the bbox); a dashed
  circle only when the data states the possible error of a street-level point (`geo.uncertainty_m`, optional) – no
  fixed radius (street midpoints are typically ~700 m from the site; address points need none). Opening a record
  without a location fits the map to the district outline and the map note says "Ten wpis nie ma lokalizacji na mapie
  – widać całą dzielnicę" (with a record open the note speaks about it, not about the list behind the panel; otherwise
  "N z M wyników bez lokalizacji – są tylko na liście" / "Ten wynik nie ma lokalizacji – jest tylko na liście").
  A permit permalink fits the map to the permit once permits.json arrives (the idle prefetch never moves the map).
* Clusters show the kind mix as a ring and speak it ("Grupa: 12 wpisów (5 WZ, 7 Pozwolenie) – przybliż mapę"); ring
  and spoken mix follow the **current** kind selection (`setLegendKinds()`), also for kinds switched on after the map
  was created. A cluster whose markers all share one point (many records on one parcel centroid; `sameSpot()`) has a
  stacked look and opens a **list popup** instead of zooming to the maximum: the map pans it clear of the map tools and
  the legend, focus moves into it, Esc closes only the list (not a record open beside it) and – like its × button –
  returns the focus to the group marker. Other clusters zoom in, or spiderfy when zooming cannot split them. Selecting a record highlights its parcels (permit parcels come from
  `parcels-permits.geojson`). "W pobliżu mnie" uses browser geolocation (or "Wskaż na mapie"); the point is rounded to
  3 decimals (≈ 100 m) before it reaches the URL.
* **Keyboard on the map**: single markers are role=button – Enter/Space open the record (Leaflet itself handles Enter
  only for popups); a group zoomed or spiderfied from the keyboard hands the focus to the nearest marker afterwards; a
  focused marker or group is panned clear of the map tools, legend and attribution (`map.panInside` with padding;
  Leaflet's own auto-pan is off); "Warstwy mapy" has `aria-expanded`, Enter moves into the list, Esc/leaving collapses
  it back to the toggle; Esc on a phone peek returns the focus to the record's marker. Marker tooltips and the timeline
  tip are hoverable (they stay while the pointer is on them) and Esc closes them first (WCAG 1.4.13).
* **"Wskaż na mapie"**: a banner on the map stays until the pick ("Dotknij mapy…" on touch screens, "Kliknij mapę… albo
  przesuń ją strzałkami i naciśnij Enter, aby wybrać jej środek (Esc – anuluj)" elsewhere) with "Środek mapy" and
  "Anuluj"; the map gets the focus. A tap/click on a marker or a group picks that place (markers ignore the pointer
  while picking); Enter on the focused map picks its centre (crosshair shown). Switching to the list or opening a
  record ends a pending pick.

## Accessibility & quality

What the app does: landmarks (`header`, `nav`, `main`, labelled regions), one `h1` per view, skip link, a visible focus
ring on every control, logical tab order (detail panel before the map), modal drawer/sheets trap focus and close with
Esc (focus returns to the opener / originating card) – and close by themselves when the route or the record changes
underneath (browser Back), so the inert top bar and the focus trap never outlive them; a trap whose dialog has gone
never swallows Tab. `/` focuses search (not while a record is open; switchable on the About page, `localStorage`
`wz:slash`), `←/→` move through results in the detail panel, live result count (`aria-live`, debounced), combobox per
ARIA 1.2, timeline operable by keyboard with a table view, kind never conveyed by colour alone, keyboard on the map
(see Map: markers, groups, layers control, "Wskaż na mapie"), accessible names that start with the visible label
(Mapa/Lista, Wróć, brand, year buttons), keyboard focus kept clear of sticky bars (`scroll-padding` on the page, the
filters drawer/sheet head and footer, the detail bar; Sources measures its sticky stack), the toast live region
created at boot, `prefers-reduced-motion` (CSS animations, Leaflet zoom, and the JS jumps of the About table of
contents and the Sources years, which also move the focus to the target heading), forced-colours styles for
pressed/selected states and focus rings, skeleton layout identical to the final one (no layout shift), print styles.
Contrast: all text meets WCAG AA in both themes; form-field borders use `--border-input` (≥ 3:1); the categorical
palette was validated for colour-vision deficiency **on white** (light) and on `#191b1f` (dark), and the timeline
bars sit on the surface colour so that condition holds. The data error page names the official lists (district
office, BAiPP) and folds the technical details (the local-server hint only on localhost).

How it was verified (2026-10-23, real data and fixture): axe-core 4.10 with the `wcag2a`, `wcag2aa`, `wcag21a`,
`wcag21aa` and `best-practice` tags on 14 states (list, outcome filter, planning and permit detail incl. a
`geo.conflict` record, the three Sources tabs, About, phone list/map/detail sheet, 600 px modal) × light/dark – 0
violations (a scratch run; axe is not a dependency of the suite); the e2e suite's keyboard checks (map markers,
groups, layers control, keyboard pick, focus never under sticky bars on Sources and the filters sheet, Back with the
drawer open, radius focus, Esc on tooltips), forced colours (pressed year differs) and a WebKit pass (Playwright's
WebKit build, not a physical Safari).

Known gaps: font sizes are in `px`, so the browser's default font-size setting does not enlarge the text (page zoom
does; no sideways scroll down to 300 px); no test with a real screen reader (NVDA, VoiceOver) – live regions and
names are checked only through the accessibility tree; the timeline is a chart with a table alternative, its bars
are not individually described.

## Real-data verification (2026-10-23)

* Every record's detail opened in the app (all 3,165 of the 578 + 2,587 records of that sweep, at 1440 px and on a
  320 px phone): no page error, no console
  error, no sideways overflow, no "undefined/NaN/null" text, a title, a provenance block and raw cells everywhere; every
  permit shows its register number, GUNB line numbers and register provenance. Every card rendered at 498 px and
  288 px, with and without a search: no overflow. (The sweep found register texts without spaces –
  "Przeworskiej,Siennickiej,Podskarbińskiej,Chrzanowskiego", capitals like "ELEKTROENERGETYCZNYCH" in a title, GUNB
  column names like `jednostka_stara_numeracja_z_wniosku` – widening the phone sheet by up to 100 px; user text in the
  detail panel, cards and the spot list now wraps (`overflow-wrap: break-word`, inherited) and the raw table has a fixed
  layout. The 320 px e2e check now also opens the permit with the longest unbroken text and the one with most parcels.)
* The browser CSV (`csv.js`) equals the pipeline's `records.csv` / `permits.csv` cell for cell for every record (only
  the base URL of the links differs) – re-checked on the final data, 578 + 2,591 rows, 0 differences.
* Six records traced to their sources (2 per dataset): the cited sheet/row of the mirrored workbook holds every raw
  cell, the number, date, address and parcels; for RWDZ the extract lines are byte-equal to the cited lines inside
  GUNB's ZIP, the sidecar line map agrees, and register id, number, date, investment, parcels and category match.

## Tests

```sh
npm test            # unit tests (node --test 'tests/js/*.test.mjs'): folding/search/stemming/highlight, filters+facets
                    # (incl. permits merged/opt-in, v2 facets, month bounds, per-kind presets, outcome coverage,
                    # unknown-value cleanup, near uncertainty), sorting, plurals/dates/durations/line lists, URL round-trip
                    # (default kinds, v2 params, ~100 m rounding, sources tabs, prototype names), CSV v2 (formula guard,
                    # Warsaw file date), active-filter chips, kinds helpers, lazy-load triggers + refetch rule, card match
                    # context/tag order/display case, related-record reasons and steps (outcomes), street keys, nearest
                    # address point, safeUrl, promo wording, sources reconciliation/dataset split, same-spot clusters,
                    # index.html early fetch + boot-failure hook, sliced permit merge, "Organ" = "Źródło" detection,
                    # blank sheet name "(arkusz bez nazwy)", geo.conflict label, dev server survives a malformed URL
npm run e2e         # Playwright (system Chrome) on the FIXTURE under a sub-path, screenshots; plus a short WebKit
                    # pass when Playwright's WebKit is installed (skipped otherwise)
npm run e2e:real    # the same against site/data (real pipeline output; permit checks run when permits.json exists)
node tests/e2e/smoke.mjs --only=desktop-light|mobile-dark|robustness|webkit   # one group
```

Screenshots land in `tests/e2e/output/` (git-ignored): `desktop-{light,dark}-{explore,search,detail,sources,about,
permits,permit,related,refusal,sources-rwdz,spot}.png` (1440×900) and `mobile-{light,dark}-{list,filters,map,detail,
permit,sources}.png` (390×844 @2x). Besides the v1 checks (inflected search, parcel-number match line, collapsed long
chains with reasons, worst-case records on a 320 px sheet) the suite covers: pb/zg counts and promo **before**
permits.json arrives (the request is held), switching permits on (loading strip, no empty-state flash, exactly one
request, timeline/map legend), permit facets, the WZ → permit story loading on demand, a cold permit permalink
(loading panel, never "not found"), permit provenance (extract downloadable, ZIP/dane.gov.pl links, line numbers,
no designer columns), the BAiPP refusal badge/facet/callout, sources tabs (keyboard), RWDZ "Pokaż N wpisów", the
same-spot cluster list (no zoom, clear of the map tools, Esc + focus back on the marker), the ~100 m rounding of "W
pobliżu mnie", collapsed source years, permits on mobile (timeline "Tabela" stays on screen), a missing permits.json
(planning records keep working, retry offered), and – added in the real-data round – the idle prefetch leaving the
list (cards shown, focus) and an open Sources page alone, cluster rings/labels with permits switched on after the map
was created (no grey segment, Polish plurals), "Organ" hidden for the planning kinds, the "search permits too"
suggestion before loading, register-number search, the Excel file count on About, no ZIP name repeated in RWDZ titles,
and the result count clear of the top bar after "Pokaż N wpisów" on a phone. Added with the review fixes: a record
without a location (district fit + map note), Enter/Esc on map markers, the layers control by keyboard, focused
markers panned clear of the map controls, "Wskaż na mapie" by keyboard (banner, Enter picks the centre) and on a phone
(persistent banner, "Anuluj", a tap on a group picks), radius focus, the outcome note, a stale link cleaned up, a
shared `mapa=` area kept, outcome steps / "Wniosek o" / BAiPP period row, disabled arrows, headings, focus never
under sticky bars (Sources 1440 px, filters sheet), RWDZ "Stan rejestru"/"Sprawdzono", About (feed copy, "/" switch,
UUG, tile servers), forced colours, no fixed circle around street points, the hoverable timeline tip, a permit opened
while permits are hidden (map fit, legend ▲, note + "Pokaż pozwolenia na liście"), per-kind presets, "Wczytywanie…"
while only permits are selected, the intro strip, tag "+N" chips, label-in-name of the Mapa/Lista and Wróć buttons, "/"
inside a record, 300 px and 568×320 screens, the promo next to a search on a phone, the data error page links, a
module that fails to load, Back with the drawer open, no re-request/toast storm after a permits failure, and – in
WebKit – one request per data file and the tile filter. The suite fails on any console error (third-party tile
errors and the expected 404s of optional files are reported separately).

`tests/fixtures/site-data/` is a frozen subset in the v2 format. The 71 district records were produced with the
project's own pipeline modules (parse → normalize → classify → geocode from caches) from the real spreadsheets,
including edge cases (56 parcels, far-apart parcels, access-road parcel, intersections, descriptive address,
redacted applicant, a file linked from two monthly pages, typos in decision numbers) plus one clearly labelled
synthetic record with nearly all fields empty. v2 additions (built once from the real downloads with the pipeline's
`normalize`/`classify`/`geo` helpers; ULDK geometry from the cache or looked up once):

* 15 BAiPP records from the real 2020–2026 workbooks (ids like `wz-am-2026-95` refusal, `cp-am-2025-c2-10`,
  `ws-am-6730-2020-14`; outcomes refusal / discontinued / transfer / expiry / granted; the Port Praski row whose
  parcel lies in Praga-Północ, with its warning), all 7 BAiPP pages and 28 files (real URLs, sizes, SHA-256,
  Last-Modified, `rows_total`), plus **one synthetic older snapshot** of the current-year file (file id
  `f1x7ure0vi`, no URL, labelled in its warnings) so the snapshot UI is testable; the workbooks used by records are
  mirrored in `sources/<file_id>.xlsx`;
* `permits.json`: 54 pb + 8 zg real RWDZ cases (2016–2026; picked to share parcels with fixture records, plus a
  voivode, a city, a Praga-Północ office case and the latest decision), with `rows` = real line numbers in GUNB's
  CSV; `parcels-permits.geojson`; `related` recomputed across all three datasets;
* `sources.json`: `source` on every page, the `rwdz` pseudo-page and 3 register files (real ZIP SHA-256/size/
  Last-Modified, `rows_total` = rows in GUNB's CSV); `sources/rwdz/*.csv` are **reduced** extracts (header + the
  fixture cases' lines, designer columns emptied, re-quoted) – not byte-exact like the real ones;
* `records.json`: v2 fields on every record and the dictionaries `datasets`, `issuers`, `outcomes`, `permit_scopes`,
  `permit_categories`, `counts_by_kind` (fixture labels – the pipeline's wording may differ; the UI takes whatever the
  dictionaries say).

Every fixture JSON carries `"fixture": true`.
