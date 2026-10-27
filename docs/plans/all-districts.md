# Plan: from Praga-Południe to all 18 Warsaw districts

Status: plan, 2026-10-27. Branch `feature/all-districts`. Source inventory: `docs/research/warsaw-districts.md`.
Owner decisions are marked 🔴 and listed together at the end.

## 0. The problem in three numbers

* **~20× the data.** ~15–25k planning records instead of 578, and 38k permit cases + 4.6k notifications instead of
  2.6k. Built the way it is today, `records.json` + `permits.json` would weigh ~150 MB (≈20 MB gzip). The
  committed source mirror would grow from 7 MB to ~100 MB.
* **19 publishers instead of 3**, in four formats. Template xlsx (11 districts), the case-system **PDF** report
  (Białołęka, Bielany, Mokotów), the template **printed to PDF** (Ochota, Targówek, Włochy), and Ursus's own xlsx
  registers. Each district has its own page structure and update rhythm.
* **The UI is already dense.** One more facet with 18 values on top of kind/period/tags/applicant/area/source/
  issuer/outcome/scope/category would make it worse.

Guiding idea: **a district is a scope, not a filter.** People look at "their" district. Everything they see today
stays per district and the same size as Praga-Południe's view now. The city-wide view is an explicit,
lighter mode.

## 1. UX

### 1.1 District as the scope (not one more facet)
* The header subtitle, today the static "Praga-Południe", becomes a **district switcher button**
  ("Praga-Południe ▾"). It opens a small dialog (sheet on phones) with the 18 districts in alphabetical order. Each
  row shows a count and a short "z jakich źródeł" note (e.g. "listy PDF – wkrótce" for districts not yet ingested).
  At the bottom: **"Cała Warszawa"**.
* URL: `dz=<slug>` (`dz=mokotow`, `dz=warszawa`). It is always written, so shared links are unambiguous. A link
  without `dz` (every link shared so far) means the visitor's last choice from `localStorage`, else Praga-Południe.
  Record permalinks `#/wpis/<id>` work without `dz`: the id tells the district (§3.2).
* Switching district keeps the other filters that still make sense (kind, period, search text, tags, applicant). It
  drops the ones that do not (street, neighbourhood, map area, "near me"), and a toast names what was dropped.
* No district facet in the filter panel. In "Cała Warszawa" mode the **neighbourhood facet** becomes a district
  facet, the same slot with the same control, so the panel does not grow.
* Cards show a district badge only in "Cała Warszawa" mode.

### 1.2 What changes per district, and what stays put
* Map: starts on the district's bounding box and shows its outline; the other districts' outlines are faint and
  clickable ("Pokaż Mokotów"). The neighbourhood layer comes from the district's MSI areas.
* "Źródła danych": the district tab shows that district's pages/files. BAiPP and GUNB tabs are filtered to the
  district (same files, fewer rows).
* About page, intro strip, empty states, "Zapytaj urząd": the district's office name and inbox come from a district
  dictionary (`INFO_REQUEST` grows a per-district map; addresses to collect from each district's contact page).
* Feeds: `feed.xml` stays Praga-Południe (existing subscribers). New `feeds/<slug>.xml` plus `feeds/warszawa.xml`
  (planning only; the head of the list, not everything).
* Downloads: per-district CSVs. A whole-city CSV per dataset is generated, but only linked on the About page.

### 1.3 "Cała Warszawa" (city-wide) mode, deliberately lighter
* Planning kinds (WZ/CP/ws) of all districts: 15–25k records. That is feasible with a slim index (§2.2): ~1–2 MB
  gzip, and filtering stays well under 50 ms per keystroke.
* Permits city-wide (43k): opt-in, desktop only, with the same lazy pattern as today ("Wczytaj pozwolenia dla całej
  Warszawy – ok. 4 MB"). On phones the toggle explains it and offers "wybierz dzielnicę".
* Map in city mode: clusters only below zoom 14, no parcel outlines (they load per district when zoomed in).

### 1.4 Districts without data yet
Districts still being onboarded appear in the switcher with what *is* available. GUNB permits and BAiPP records exist
for every district from day one. The district's own lists are marked "w przygotowaniu" with a link to the office page.
So the app is useful city-wide before the PDF parsers exist.

### 1.5 Keeping complexity down (things we will not do)
* No multi-select of arbitrary district sets (only one district or the whole city). The map's "only the visible
  area" covers "my district and the neighbouring street".
* No second filter for issuer-district vs location-district: a record belongs to the district where its parcels are
  (ULDK); the issuing office is in the detail.
* No district-specific columns. All sources map onto the same record shape; district-only extras (Wola's decision
  texts, stated outcomes in PDF reports) fill existing fields (`outcome`, a source link).

## 2. Size and speed

### 2.1 Budgets (per district view, phone, gzip)
| | today PP | target per district | target city (planning) |
|---|---:|---:|---:|
| First data download | 0.45 MB | ≤ 0.5 MB (median district), ≤ 1.2 MB (Białołęka) | ≤ 2 MB |
| Permits layer | 0.8 MB | ≤ 1 MB median, ≤ 2.5 MB Białołęka/Wawer | desktop only, ≤ 5 MB |
| `evaluate()` per keystroke | 0.4–2.7 ms | ≤ 10 ms | ≤ 50 ms |
| Longest task after load | 73 ms | ≤ 100 ms | ≤ 200 ms (desktop) |

### 2.2 Data files: shard by district, split index from detail
```
site/data/
  districts.json                  dictionaries (kinds, tags, datasets, issuers, outcomes, scopes, categories),
                                  the 18 districts (name, unit, bbox, counts per kind, newest month, status,
                                  office + inbox), generated_at — ~40 kB
  d/<slug>/records.json           planning records of the district, WITHOUT sources[].raw ("lite")
  d/<slug>/permits.json           GUNB records of the district, lite
  d/<slug>/sources.json           the district's pages/files + the BAiPP/GUNB files that feed it
  d/<slug>/areas.geojson          district outline + MSI areas
  d/<slug>/parcels.geojson, parcels-permits.geojson
  raw/<bb>.json                   sources[].raw of every record, bucketed by hash(id) (256 buckets, ~5–20 kB gz)
  warszawa/records.json           city-wide planning index (lite; a slimmer field set than per district)
```
* `sources[].raw` is 30 % of planning and 47 % of permit bytes and is shown only in the detail's "Dane w źródle"
  panel. It moves to hash buckets and is fetched when that panel opens. One request, any record, no district needed.
  The rest of the record keeps its current shape, so search, cards, CSV and related lists do not change.
* A record's `district` (new field) decides its shard. GUNB/BAiPP rows go to the district where their parcels are.
  Rows whose parcels span two districts go to the first parcel's district and appear in the other district's
  "related" lists.
* `related` stays global (by parcel id / address). Its ids may point into another shard. The detail resolves them
  with the `raw` buckets' sibling `idx/<bb>.json` (id → district, kind, date, title) when the target shard is not
  loaded.

### 2.3 Frontend mechanics
* `data.js` takes a `base` already (`loadIndex(base)`, `loadPermits(base)`, `loadGeo(name, base)`). The district
  picks the base: `data/d/<slug>/`. The early-fetch script in `index.html` reads `dz` from the hash (or
  `localStorage`) to start the right download.
* Switching district re-initialises the index (draft: a reload of the page with the new hash; final: an in-place swap
  that keeps the map instance).
* City mode builds the index from `warszawa/records.json`. Its search documents are built in slices (the
  `prepareEntries` pattern already exists) and the facet pass stays single.
* If city-mode filtering exceeds the budget, move `evaluate()` into a Worker. It is pure and data-only, so this is
  mechanical.

## 3. Pipeline

### 3.1 District registry (`pipeline/districts.py`)
One dictionary of 18 entries replaces the Praga-Południe constants scattered over 8 modules. Each entry has slug,
names (nominative + forms seen in addresses, e.g. "Praga Płn.", "Pragi-Północ"), TERYT unit, precinct zone(s), OSM
relation, id code, office label, office inbox, and the **crawl strategy + entry URLs**. Today's Praga-Południe
constants (`INDEX_URL`, `TERYT_PRAGA_POLUDNIE`, `DISTRICT_TERYT`, `DISTRICT_RE`, `DISTRICT_RELATION_ID`, …) become
lookups.

### 3.2 Record ids (permalinks must not change)
* Praga-Południe district records keep `wz-2026-15`, `ws-6730-2026-29`. BAiPP Praga-Południe records keep
  `wz-am-2026-95`. **Frozen legacy namespace.**
* Every other district: `<kind>-<code>-<rest>` with a fixed 3-letter code: `wz-bem-2026-1`, `ws-wol-6730-2026-12`,
  `cp-mok-2026-4`. BAiPP outside Praga-Południe: `wz-am-bie-2025-33`. This resolves the city-wide duplicate numbers
  (📮 `33/AM/BIE/WZ/2025` vs `33/AM/PPD/WZ/2025`).
* GUNB ids are register numbers, already unique (`pb-st-mz-pa-2026-29594`). Unchanged.
* So the district of a planning id is readable from the id. For permits it is not, which is why the `idx/<bb>.json`
  bucket exists.

### 3.3 Crawl strategies (one per page shape, not one per district)
| Strategy | Districts | What it does |
|---|---|---|
| `monthly-pages` | Praga-Południe | today's paginated index → monthly pages |
| `attachments` | Bemowo, Praga-Północ, Rembertów, Ursynów, Wawer, Wilanów, Żoliborz, Ochota, Targówek | fetch 1–n configured pages, take every `/documents/` attachment (xlsx, xls, ods, zip, pdf) in the article body; period/kind come from the **file contents** (several pages mislabel links), link text and filename are only hints |
| `hub` | Białołęka, Bielany, Śródmieście, Wesoła, Włochy, Wola, Mokotów | like `attachments`, but the list pages are discovered from a hub page by link-text rules (configured allow-list), never guessed |
| `yearly-pages` | Ursus | hub → `wykazy-za-rok-YYYY` pages |
| `baipp` | city | unchanged; now keeps every district |
| GUNB | city | unchanged download; filter = the 18 units (+ typo rules generalised) |

Every downloaded file keeps today's guarantees: sha256, history on replacement, snapshots of files that are replaced
in place (cumulative yearly files are the norm outside Praga-Południe), "removed from source" flags.

### 3.4 Parsers
1. **Template xlsx** (11 districts): the existing header-text parser. Additions: year-separator rows ("2020 rok"),
   `brak` rows, Wawer's duplicated "Oznaczenie nieruchomości" headers (positional fallback), ZIP containers (Wawer),
   `.ods` (Żoliborz 2015–20, optional), `.xls` (Mokotów 2018–19, optional; skip pre-IX-2020 in phase 1 as for PP).
2. **Ursus registers**: a per-sheet column map keyed by sheet name. The headers lie, so this is the one positional
   parser.
3. **PDF, template printed** (Ochota, Targówek, Włochy) *(in the draft: `pipeline/pdftable.py`)*: words with their
   boxes from poppler's `pdftotext -tsv` (a system binary, no Python dependency; CI installs `poppler-utils`).
   The header and its "1 2 3 4 5 6 7" row are printed on page 1 only. Columns = the x-ranges no word of the table
   ever covers (Excel keeps text inside its cell), named by the numbering row – its numbers are centred in some
   columns and left-aligned in others, so midpoints between them mis-split columns. Cells are centred vertically:
   a row is anchored at its Lp number and each cell's block of lines goes to the anchor it is centred on (touching
   blocks are split so that each part is centred on its anchor). Rows printed without an Lp (Włochy) show up as a
   second date in a row and get an anchor of their own. Year separators ("ROK 2021"), "Stan na …" footers and a
   header repeated over a later year's table are skipped.
4. **PDF, case-system report** (Białołęka, Bielany, Mokotów) *(in the draft)*: the header is repeated on every page,
   cells are top-aligned, rows run across page breaks. Header cells are centred in some reports, so columns are
   where cell text starts on the rows' first lines (a word after a gap wider than a space, at the same x in several
   rows, never crossed by a word on any line); the header only names them. The outcome word under the number
   ("Pozytywna/Odmowna/Umarzająca") fills `outcome` (a /P or /W letter wins over "Pozytywna"). The `¬` separators in
   the property column give precinct / parcels / street.
5. Source references for PDF rows: `sheet` = "strona N" (the page the row starts on), `row` = the row's ordinal in
   the file, `raw` = the cells as printed (composite ones too). Byte-exact provenance is the PDF itself (sha256).
   Output is the xlsx parser's `ParsedFile`, so normalisation does not know the difference.
6. Every new layout gets real fixtures under `tests/fixtures/<district>/` and a parse test against an independent
   oracle, as the PP layouts did.

### 3.5 Normalisation and geography
* Parcel ids: `(zone, SSOO) → unit` from a **Warsaw precinct table** generated from the GUNB register (1,832
  unit/precinct pairs; majority wins on 26 typo collisions; ambiguous ones are verified once with ULDK
  `GetRegionById`). It replaces `praga_poludnie_obreby.json`, which stays as Praga-Południe's ULDK-verified subset.
* Address cleaning strips any district name, not just "Praga-Południe". Precincts without the zone digit (Wesoła
  `07-07`) get the district's zone.
* Records get `district` = the district of their parcels. If parcels are unknown: the district of the publishing
  office, or the BAiPP address line. Today's "out of district" logic (Port Praski case) becomes "published by X,
  lies in Y", shown in Y with a note.
* **Parcels of a first run come from GUGiK's county package, not from ULDK** *(in the draft: `pipeline/egib.py`)*.
  GUGiK publishes every county's parcels as a GeoPackage rebuilt daily (geoportal.gov.pl → Pobierz dane → "Dane
  powiatowe", since IX 2025); Warsaw is one 107 MB ZIP (474 MB unpacked, 287,747 parcels, EPSG:2180). It is the same
  register: on the draft's 6,693 found parcels every one is in it with the centroid within 3 cm (median; 37 m at
  most, boundaries edited since), and none of the 1,012 parcels ULDK did not know is. Python's `sqlite3` reads it
  (id index, R-tree for "parcel under a point", precinct existence); EPSG:2180 → 4326 is a 30-line Krüger series
  (sub-millimetre). The geocoder downloads it when ≥ 300 parcels are unknown (a district's first run), keeps it a
  week, and answers ULDK's three questions from it; precinct outlines still come from ULDK (a handful). A district's
  parcels take under a second instead of hours.
  The old estimate ("~60,000 parcels ≈ 8–10 h at 2 req/s") was wrong: ULDK's published limits are 10,000 requests a
  day per IP, 200/min by day and 40/min after 18:00 (uldk.gugik.gov.pl/opis.html, which itself points bulk users to
  these packages) – a week of lookups. The geocoder's session now keeps those limits (it ran at 4/s before).
* ULDK cache sharded per unit (`data/cache/uldk/<unit>.json`), so a monthly run rewrites a few small files instead
  of one 25 MB file. Monthly runs (~1–3k new parcels city-wide) can use the package too; small runs ask ULDK.
* Addresses (records without parcels, and the address-vs-parcel cross-check) still go to UUG, ~0.3 requests per
  record at ~2/s: the first city-wide run is ~1–2 h, later runs minutes. PRG address points (also downloadable per
  county) could replace most of it – not needed yet.
* Neighbourhoods: one Overpass query for all MSI areas (admin_level 10) inside Warsaw's 18 districts.

### 3.6 Build orchestration and failure policy
* `pipeline.build --districts bemowo,wola` builds a subset. Other districts' outputs and caches stay as they are.
  The default builds every district whose status is `enabled`.
* Per-district manifests: `data/districts/<slug>/manifest.json` + `raw/`. Praga-Południe stays at `data/` until a
  later `git mv`.
* 🔴 Failure policy: today any district-site failure = exit 3, nothing deployed. With 18 sites, one office being down
  should not freeze the other 17. Proposal: a failed district keeps its previous data with a visible warning on its
  sources page (like BAiPP today), and exit 3 only when more than N districts fail or GUNB's format changes.

## 4. Repository and deployment

* **Stop committing generated outputs.** Today `site/data/` (13 MB) and `site/sources/` (7 MB) are committed and
  rewritten by every data refresh. At 20× this bloats git by tens of MB a month. Proposal: commit **inputs only**
  (`data/**/manifest.json`, `data/**/raw/`, caches, RWDZ extracts). `deploy.yml` runs `make data-offline` (minutes,
  no network) and uploads `site/` + the mirror assembled from `data/raw` as the Pages artifact. `test.yml`'s
  "committed data = offline rebuild" check becomes "offline rebuild succeeds and is deterministic (two runs, same
  bytes)".
* **Do not mirror the same bytes twice.** `site/sources/` is a copy of `data/raw/`. Assemble it at deploy time
  (above), or link to the original URL + sha256 and keep only our copy in `data/raw`.
* Raw inputs at ~100 MB, growing with cumulative re-uploads: fine for git for a few years. Revisit (GitHub Release
  assets per year, or a separate `wzsearch-data` repo) once `data/` passes ~500 MB.
* RWDZ extracts per district (`data/raw/rwdz/<unit>/…`) keep the byte-exact guarantee with small, local diffs.
* Local refresh stays the operating model (district sites block cloud runners). One `make data` covers all
  districts: ~19 sites × ~5–20 requests at ≤ 2 req/s per host. Hosts are crawled **in parallel across hosts**
  (politeness is per host), so this takes minutes.
* GitHub Pages limits (1 GB site, 100 MB per file): with sharding the largest file is a few MB and the site is
  ~250–400 MB uncompressed with mirrors. Without mirrors it is ~120 MB. Fine.

## 5. Phases

| Phase | Content | Result |
|---|---|---|
| **1. Foundations** *(in the draft)* | district registry; precinct table; `district` field; id namespaces; BAiPP + GUNB for all districts; per-district shards + `districts.json`; `--districts`; district switcher + `dz` param; legacy links keep working | every district shows GUNB permits + BAiPP cases |
| **2. Template-xlsx districts** *(in the draft, partly)* | `attachments`/`hub` crawlers; parser additions (separator rows, `brak`, zip, duplicated headers); per-district sources tab | 11 districts with full planning lists |
| 3. Slim index | `sources[].raw` → buckets; `idx` buckets for cross-shard related; `warszawa/records.json`; city mode | city-wide search of planning records |
| 4. PDF districts *(in the draft)* | `pdftable.py` (2 layouts, poppler), fixtures; ask the 6 offices for xlsx in parallel (📮) | 17 of 18 districts |
| 5. Ursus + extras | Ursus positional parser; Wola decision-text links; stated outcomes from PDF reports | richer records |
| 6. Deploy model | inputs-only commits, build-in-CI deploy, per-district failure policy, per-district feeds | sustainable monthly refresh |

## 5a. Draft status (branch `feature/all-districts`, 2026-10-27)

Built and working end to end on real data (phases 1 and most of 2):

* `pipeline/districts.py` (registry, current-district context, precinct table), `pipeline/data/warsaw_obreby.json`
  (`scripts/warsaw_obreby.py`), `pipeline/city.py` (`make city`, `make city-offline`, `--districts`,
  `--geocode-cache-only`), `crawl.crawl_attachments`, `parse.parse_source` (ZIP), `brak` rows,
  `build.DistrictPaths`, per-district datasets/issuers/feeds/permalinks, GUNB per-district extracts from one
  shared download.
* Frontend: `district.js`, the header district picker (`components/district-picker.js`), `dz` in every hash,
  district-aware copy, map start, "Zapytaj urząd" addressee, downloads and feed paths.
* Praga-Południe is unchanged byte for byte (`make data-offline` → no changes; its shard *is* `site/data/`). The
  whole test suite passes plus `tests/test_districts.py` and `tests/js/district.test.mjs`.
* Measured on the first crawl (27 Oct 2026; planning = district lists + BAiPP rows; not yet geocoded):

  | District | planning | of which district lists | permits + notif. | records.json gz | permits.json gz |
  |---|---:|---:|---:|---:|---:|
  | Praga-Południe (legacy, unchanged) | 578 | 474 | 2,591 | 0.2 MB | 0.8 MB |
  | Bemowo | 1,236 | 1,125 | 1,326 | 246 kB | 370 kB |
  | Praga-Północ | 632 | 603 | 1,567 | 105 kB | 374 kB |
  | Rembertów | 620 | 601 | 879 | 104 kB | 182 kB |
  | Śródmieście | 1,666 | 1,364 | 4,563 | 356 kB | 1,331 kB |
  | Ursynów | 1,628 | 1,534 | 2,181 | 277 kB | 588 kB |
  | Wawer | 5,650 | 5,600 | 6,344 | 764 kB | 1,336 kB |
  | Wesoła (CDN refused most downloads, see BACKLOG) | 15 | 15 | 1,584 | 7 kB | 290 kB |
  | Wilanów | 1,449 | 1,442 | 2,429 | 207 kB | 610 kB |
  | Wola | 754 | 558 | 2,119 | 149 kB | 606 kB |
  | Żoliborz (stale since 2024) | 16 | 12 | 752 | 9 kB | 202 kB |
  | 6 PDF districts + Ursus (`pending`: BAiPP + GUNB only) | 27–167 each | – | 1,020–5,953 | 11–39 kB | 246–1,258 kB |
  | **All 18** | **14,953** | 13,328 | **43,564** | | |

  Every district's planning layer fits the §2.1 budget (largest: Wawer, 0.76 MB gz). The permit layers of
  Białołęka, Śródmieście, Wawer and Mokotów (1.2–1.3 MB gz) exceed it – the reason to do the slim index
  (phase 3) next. Geocoding needs ~60,000 unique parcels city-wide (≈ 8–10 h at 2 ULDK requests/s, once);
  Wawer alone has 11,200 and Białołęka 9,500.

Update, evening of 27 X 2026 (second commit): the six PDF districts are read (`pipeline/pdftable.py`, phase 4) and
the first geocoding takes its parcels from GUGiK's county package (`pipeline/egib.py`, §3.5) – every district's
parcels in seconds, addresses via UUG at ~2/s. The city's file CDN refused most downloads of Białołęka, Bielany,
Włochy, Wesoła and Ursus that day (403 even at one request per 10 s for uncached files), so those districts hold
only what was fetched; the next crawls retry. Ursus's own xlsx layout (phase 5) waits for its files.

Not done in the draft (next steps, in order): OSM areas per
district (Overpass was overloaded on 27 Oct); a per-attachment size cap in the crawler (Wola links a 135 MB ZIP of
decision PDFs on a list page – excluded by configuration now); on phones ≤ 390 px the district icon makes "O projekcie" wrap in the top bar (needs a shorter label or a menu – a copy/layout decision); phase 3 (slim index, city mode); phase 4 (PDF
parsers); e2e checks for the district picker; in-place district switch instead of a reload.

## 6. Testing
* Each new layout: real fixture + oracle test (as for PP's six layouts). Each district: a reconciliation test
  "rows in files = records + documented skips".
* Determinism per shard (rebuild twice → same bytes) and "PP shard ≡ today's PP output", apart from the new
  `district` field, so the migration cannot silently change Praga-Południe.
* e2e: district switch, legacy link without `dz`, permalink to another district's record, city mode on desktop +
  the phone refusal of city-wide permits.

## 7. Owner decisions (🔴)
1. District as scope + "Cała Warszawa" mode (vs a district facet). **Recommended: scope.**
2. Default district for links without `dz`: last choice, else Praga-Południe. Alternative: a district chooser page.
3. City-wide permits only on desktop, opt-in.
4. Commit inputs only and build in CI (changes the deploy model and `test.yml`).
5. Per-district failure policy (§3.6).
6. Pre-2020 registers (Białołęka from 2009, Mokotów 2018–19, Żoliborz 2015–20): out of scope at first, as for PP.
7. Writing to the six PDF-only offices (and Ursus, Żoliborz) to ask for xlsx: the PDF reader works, but it
   depends on print layouts (Mokotów changed its six times since 2021) and loses clipped cell text (Ochota).
8. Branding: "wzSearch Praga-Południe" → "wzSearch Warszawa", with the district in the switcher.
9. Two new runtime dependencies: poppler's `pdftotext` (a system package; CI installs `poppler-utils`) and GUGiK's
   county parcel package (a 107 MB download, not committed, refreshed when a run has ≥ 300 unknown parcels).
10. Asking the city how to download its documents in bulk (the file CDN refuses crawlers; §5a).
