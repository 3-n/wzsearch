# wzSearch – Praga-Południe planning decisions and building permits, searchable

What may be built in Praga-Południe (Warsaw), and what has been allowed? The answers are public but scattered over
three publishers and hundreds of files:

* the **district office** publishes every month what it decided about land development: **WZ decisions**
  (*decyzje o warunkach zabudowy*), **public-purpose location decisions** (*ULICP*, "CP") and **initiated WZ/CP
  proceedings** (*wszczęte postępowania*) – 73 monthly pages since August 2020, up to three Excel files each, in six
  layouts;
* the city's **architecture bureau** (BAiPP) publishes the same three lists for the cases it handles centrally, as
  city-wide yearly Excel files;
* **GUNB**, the national building control office, publishes its register of **building and demolition permits** and
  **notifications** (*pozwolenia na budowę / rozbiórkę, zgłoszenia* – RWDZ) as nightly bulk files for the whole country.

wzSearch turns all of it into one fast, static website:

* **every row of every file** – 578 WZ/ULICP records and 2,591 building permits and notifications as of October 2026 –
  searchable by address, street, parcel, applicant, decision number or text;
* filters by kind, source, month range, kind of investment (tags), outcome, applicant type, neighbourhood and – for
  permits – scope of works and object category;
* an **optional map** (parcel outlines from the national cadastre, neighbourhood boundaries, orthophoto);
* a page per record with a permanent link, the other cases on the same plot ("related": a WZ decision → the building
  permit that followed it), data-quality notes and **links to the original file, sheet and row** (for permits: the
  GUNB file and the line numbers, plus a byte-exact extract) – sources matter;
* a **sources view** of every page and file, with the count the office declared next to the count we read;
* downloads: CSV (opens in Polish Excel), JSON, GeoJSON and an Atom feed of new decisions.

It runs anywhere static files can be served (GitHub Pages, any web server, your laptop). There is no backend.

> Unofficial project. The published files are the authoritative source; wzSearch links to them from every record.

## Datasets

| Dataset | Publisher | Kinds | Records (Oct 2026) | Since | Licence | In the UI |
|---|---|---|---:|---|---|---|
| District lists | Urząd Dzielnicy Praga-Południe – Wydział Architektury i Budownictwa | WZ, ULICP, initiated proceedings | 474 | Aug 2020 | public information | shown |
| BAiPP lists | Urząd m.st. Warszawy – Biuro Architektury i Planowania Przestrzennego | WZ, ULICP, initiated proceedings | 104 (of ~1,600 city-wide rows) | Aug 2020 | public information | shown |
| GUNB RWDZ | Główny Urząd Nadzoru Budowlanego | building/demolition permits (`pb`), notifications (`zg`) | 2,365 + 226 | 2016 | **CC0 1.0** | opt-in |

The first two end up in `site/data/records.json`, the permits in `site/data/permits.json`, which the site loads only
when a permit kind is switched on (they are four times as many as the planning decisions and mostly small works).
Every record has the same shape, says which dataset it comes from (`dataset`) and who handled it (`issuer`); record
ids are namespaced per dataset (`wz-2026-15`, `wz-am-2026-95`, `pb-st-mz-pa-2026-29594`) and never change.

### Building permits (GUNB RWDZ) – what the register is and is not

* **What it is.** The national *Rejestr wniosków, decyzji i zgłoszeń* (art. 82b Prawa budowlanego), downloadable as
  three ZIP files rebuilt every night: permit cases of Mazowieckie that ended with a decision, and notifications for
  the whole country. wzSearch keeps every case with a parcel in Praga-Południe (cadastral unit `146507_8`) – also its
  rows on parcels of other districts – plus district-office rows whose unit id is a typo and a short hand-checked list
  of register errors under other organs (`rwdz.UNIT_FIXES`), all corrected with a note. Four kept cases turned out to
  lie in another district (3 in Praga-Północ, 1 in Wawer): they stay in the list with a note, but not on the map.
* **What it is not.** It has **no outcome column**: a permit record means "a first-instance decision was issued",
  usually a permit, but it can be a refusal or a discontinuation. It has no pending applications, no appeal
  decisions and no investments in closed areas (railway, military). The notification register is **incomplete by
  design** (detached single-family houses, small buildings, low-voltage and utility networks …; most small
  notifications are not in it). Natural-person investors are not named by GUNB ("osoba fizyczna").
* **How it is cited.** Each record links GUNB's file (with its ETag, Last-Modified and SHA-256), the line numbers of
  its rows in the original CSV, and our byte-exact extract (`site/sources/rwdz/<file>.csv`, the original header and
  lines) with its line map (`….meta.json`) – anyone can diff the extract against GUNB's file.
* **How it connects.** Permits share the cadastral parcel ids of the WZ/ULICP records, so `related` links them:
  87 of 188 WZ decisions (not refused or discontinued) were followed by a building permit on the same parcel, after
  a median of about nine months. A shared parcel is not always the same project (big housing-estate parcels carry many
  renovations): related records are other cases on the same plot, not necessarily one project's history.

## Quick start

Requirements: [uv](https://docs.astral.sh/uv/) (Python 3.12), optionally Node ≥ 22 for the frontend tests.

```sh
make install      # uv sync (+ npm install for the optional browser test)
make data         # crawl both lists, check GUNB, parse, geocode, write site/data (≈ 2 min when caches are warm)
make serve        # http://127.0.0.1:8000 (the Node dev server; python3 -m http.server without Node)
```

The repository already contains the downloaded files, the RWDZ extracts and the geocoding caches, so
`make data-offline` rebuilds the whole site in a few seconds without touching the network. The GUNB ZIPs themselves
are not committed (`data/cache/rwdz/` is git-ignored): in a fresh clone the first `make data` downloads them
(~93 MB) whenever GUNB has published a newer nightly file than the committed extracts.

Other targets: `make test` (pytest + `node --test`), `make e2e` (browser smoke test with the system Chrome),
`make rwdz` (refresh only the GUNB extracts and print their statistics), `make report` (print the data-quality report).

## Sources

| What | Where | Used for |
|---|---|---|
| District monthly lists (HTML pages + `.xlsx`) | [pragapld.um.warszawa.pl – informacja o wszczętych postępowaniach oraz wydanych decyzjach administracyjnych](https://pragapld.um.warszawa.pl/informacja-o-wszczetych-postepowaniach-oraz-wydanych-decyzjach-administracyjnych) | district records |
| BAiPP yearly lists (HTML pages + `.xlsx`) | [architektura.um.warszawa.pl/postepowania-i-decyzje](https://architektura.um.warszawa.pl/postepowania-i-decyzje) and the yearly archive pages | BAiPP records (filtered to Praga-Południe) |
| Building permits and notifications | GUNB [RWDZ bulk files](https://wyszukiwarka.gunb.gov.pl/pobranie.html) (also [dane.gov.pl dataset 3467](https://dane.gov.pl/pl/dataset/3467)) | permit records |
| Cadastral parcels | GUGiK [ULDK](https://uldk.gugik.gov.pl/) (`GetParcelById`) | parcel outlines and record locations |
| Addresses / streets | GUGiK [UUG](https://services.gugik.gov.pl/uug/) | fallback locations |
| Neighbourhoods (MSI) and district outline | © [OpenStreetMap](https://www.openstreetmap.org/copyright) contributors, ODbL, via Overpass | neighbourhood filter, map |
| Base map, orthophoto, parcel WMS | OpenStreetMap tiles; GUGiK Geoportal WMS | map layers in the browser |

Research notes on all three sources (layouts, pitfalls, what was checked and rejected):
[docs/research/building-permits.md](docs/research/building-permits.md).

## Architecture

```
   pragapld.um.warszawa.pl            architektura.um.warszawa.pl         wyszukiwarka.gunb.gov.pl
   (73 monthly pages → 176 .xlsx)     (7 pages → 28 yearly .xlsx)         (3 nightly ZIPs, ~93 MB)
                 │                               │                                  │
  pipeline/crawl.py ─ polite crawl, incremental downloads ─┐           pipeline/rwdz.py ─ conditional GET,
                 ▼                                          ▼           streamed filter to Praga-Południe
       data/manifest.json, data/raw/<file_id>.xlsx                     data/raw/rwdz/<file>.csv (+ .meta.json)
                 │                                                                  │
  pipeline/parse.py ──── header-driven parsing (district + BAiPP layouts)           │
  pipeline/baipp.py ──── district filter, number/outcome split, ULDK zone check     │
  pipeline/normalize.py ─ ids, dates, addresses, parcels, privacy redaction         │
  pipeline/classify.py ── tags (what is built / kind of works) ◄────────────────────┤
                 │                                                                  │
  pipeline/build.py ───── merge → geocode all datasets → related → outputs (deterministic)
        │                    │
        │      pipeline/geocode.py ── ULDK parcels → UUG address → street ──► data/cache/{uldk,uug}.json
        │      pipeline/areas.py ──── OSM neighbourhoods ──────────────────► data/cache/areas.json
        ▼
  site/data/records.json  permits.json  sources.json  parcels.geojson  parcels-permits.geojson  areas.geojson
  site/data/records.csv  permits.csv  site/feed.xml  site/sources/  data/report.md
                 │
  site/ (static HTML + ES modules + Leaflet, no build step) ──► GitHub Pages / any static host
```

* Module contracts and every data format: **[docs/DATA_MODEL.md](docs/DATA_MODEL.md)**.
* Frontend structure, routes and UX decisions: **[docs/FRONTEND.md](docs/FRONTEND.md)**.
* Data-quality dashboard, regenerated by every build: **[data/report.md](data/report.md)**.
* Continuing the work (status, invariants, playbooks, next steps): **[docs/HANDOFF.md](docs/HANDOFF.md)**;
  summary for the owner: [docs/MVP-REPORT.md](docs/MVP-REPORT.md).

The build is **deterministic**: stable ordering everywhere, and `generated_at` only changes when the JSON/GeoJSON
data does (a rebuild that finds nothing new rewrites nothing – also when GUNB answers "304 Not Modified" or publishes
a new nightly file that changes nothing in the district). A different `SITE_URL` rewrites only the CSVs, the feed and
the report; without `SITE_URL` the build reuses the base URL of the committed `site/feed.xml`, so local builds and CI
agree. Monthly updates therefore show up as small, readable diffs.

Build command: `uv run python -m pipeline.build [--offline] [--skip-crawl] [--refresh] [--refresh-misses]`
(`--skip-crawl` and `--offline` reuse the manifest and the committed RWDZ extracts). Exit code 3 means a live source
failed and the previous data was used – the district crawl, a monthly page served without its file list, a file that
gave records last time but cannot be read now, or GUNB changed its file format; 1 means nothing could be built.
CI commits and deploys only on exit code 0.

## Deploying to GitHub Pages

1. Push the repository to GitHub.
2. *Settings → Pages → Build and deployment → Source:* **GitHub Actions**.
3. Optionally set `REPO_URL` / `ISSUES_URL` in [`site/js/config.js`](site/js/config.js) (shown on the „O projekcie”
   page and, for `ISSUES_URL`, as a „Zgłoś błąd w danych” button under every record).
4. Run the **Update data & deploy** workflow once (*Actions → Update data & deploy → Run workflow*).

[`.github/workflows/update.yml`](.github/workflows/update.yml) then runs daily at 06:00 UTC on the 9th–16th of
each month (the office publishes around the 10th) and weekly otherwise. It crawls, checks GUNB (no secrets needed;
the ZIPs are downloaded to the runner and never committed – only the small extracts and `data/cache/rwdz.json` are),
rebuilds, runs the tests, commits changed data back to the repository and deploys `site/`. Permalinks in the CSV
and the feed use the Pages URL (`SITE_URL`). If the build or the tests fail, nothing is committed or deployed and the
previous site stays online; GitHub e-mails the repository owner about the failed run.
[`.github/workflows/test.yml`](.github/workflows/test.yml) runs the tests on every push and pull request and
checks that the committed site data matches an offline rebuild.

Any other static host works too: `SITE_URL=https://example.org/path/ make data` (or `--site-url`), then upload the
`site/` directory. Without it the downloadable CSVs carry relative permalinks (`./#/wpis/…`); the feed's relative
links are fine, feed readers resolve them against the feed's own URL.

## Data quality – what to keep in mind

The source files are typed by hand and it shows. The pipeline never guesses silently: every correction is a
warning shown next to the record, and the original row is always one click away. State as of October 2026 (see
[data/report.md](data/report.md) for the live numbers):

* **Declared vs parsed counts reconcile exactly** (district lists). The pages declare 443 entries; we read 474 rows.
  The difference is fully explained: 33 rows sit in Aug–Oct 2020 blocks that state no number, and one file (WZ,
  December 2020) declares 3 entries but contains 1. Files declared "0 pozycji" are empty templates.
* **BAiPP lists are city-wide**: only rows whose address names Praga-Południe are kept (104 of ~1,600 since August 2020).
  One of them lies in Praga-Północ according to the cadastre; it is kept with a note but not put on the district map.
* **Locations are approximate by design.** WZ/ULICP: 548 of 578 records (95%) sit on their cadastral parcels, 6 on
  an address point, 23 on a street (marked "lokalizacja przybliżona"), 1 is not on the map (its parcels lie in
  Praga-Północ). Permits: 2,469 of 2,591 (95%) on parcels, 79 on an address, 37 on a street, 6 not located.
  When the parcels' common centroid would lie on none of them, the point goes to the largest parcel. ULDK only knows
  *current* parcels: when a parcel from an old decision has since been subdivided, its known sub-parcels stand in for
  it (with a note). A street point is placed on the stretch of the street inside the record's stated precinct, and the
  record says how far the real site may be.
* **Precinct typos are caught by the address.** When the parcel under the exact address has a stated parcel number in
  another precinct, the precinct is corrected with a warning (38 records); when the address and the parcels still
  disagree, the marker is drawn hollow as "lokalizacja niepewna" (9 records).
* **The same plot often appears several times** (initiated proceeding → decision → building permit); the
  "related" list links records that share a parcel or a street + house number, across all datasets.
* **Tags are heuristic** (rules over the free-text description; for permits also the register's scope and object
  category).
* Typos in the sources (street names, precinct numbers, years in decision numbers, cadastral unit ids in the GUNB
  register) are corrected with a warning; the display text keeps the original spelling.
* Initiated proceedings (*wszczęcia*) are applications, not decisions; GUNB permit records carry no outcome.

## Privacy

* The district office normally anonymises natural persons as "osoba fizyczna", but some older files name people
  ("Pani … reprezentowana przez pełnomocnika"). wzSearch replaces such names with "osoba fizyczna (dane usunięte)"
  in the applicant field, the investment text **and** the "as in source" row view. BAiPP writes "dane osobowe";
  GUNB leaves natural-person investors blank – both are shown as "osoba fizyczna".
* **Designers' names and licence numbers** from the GUNB register (`projektant_*`) are never put into records, the
  search index or the CSV (data minimisation – they are not needed to understand a case); they remain only in the
  byte-exact extract that documents the source.
* Company and institution names are kept, including sole-proprietorship trade names (public business names).
  The mirrored original files are unchanged copies of what the offices published (they remain linkable for
  verification).

## Licences and attribution

* District and BAiPP lists: public information published by Urząd Dzielnicy Praga-Południe m.st. Warszawy and
  Urząd m.st. Warszawy (Biuro Architektury i Planowania Przestrzennego).
* Building permits and notifications: Główny Urząd Nadzoru Budowlanego, RWDZ, **CC0 1.0**
  ([dane.gov.pl dataset 3467](https://dane.gov.pl/pl/dataset/3467)). Object category names: annex to Prawo budowlane
  (Dz.U. 2026 poz. 524).
* Parcels and addresses: Główny Urząd Geodezji i Kartografii (ULDK, UUG, Geoportal WMS).
* Neighbourhood boundaries and base map: © OpenStreetMap contributors, [ODbL 1.0](https://opendatacommons.org/licenses/odbl/1-0/).
* Bundled libraries: [Leaflet](https://leafletjs.com) 1.9.4 (BSD-2-Clause) and Leaflet.markercluster (MIT),
  licences in `site/vendor/*/LICENSE`.
* Code: MIT (as declared in `package.json`).

## Project layout

```
pipeline/        crawl, parse, baipp, normalize, classify, rwdz, geocode, areas, build, export (+ http, geo, textutil);
                 data/praga_poludnie_obreby.json – the 96 precincts that exist in Praga-Południe (from ULDK)
scripts/         census.py – per-file statistics of the parsed workbooks; pp_obreby.py – the district's precinct list
site/            the static website (index.html, js/, css/, vendor/, data/, sources/ (+ rwdz/), feed.xml)
data/            manifest.json, raw/ (original .xlsx + rwdz/ extracts), cache/ (ULDK, UUG, OSM, rwdz.json), report.md
tests/           pytest suites, fixtures (real workbooks, pages and GUNB lines), js/ unit tests, e2e/ browser test
docs/            HANDOFF.md (start here), MVP-REPORT.md, DATA_MODEL.md (contracts), FRONTEND.md, research/
```

## Open questions and known limitations

See **[BACKLOG.md](BACKLOG.md)** – decisions taken while the product owner was away, known limitations and
next steps.
