# Backlog & issue log

Problems found and decisions made while building the MVP without the product owner around.
Newest round at the bottom of each section.

Legend: 🔴 decision taken by the lead **without the owner** – please review · 🟠 known limitation / follow-up work ·
🟢 handled (logged for transparency) · 📮 issue in the *source data* worth raising with the office

---

## 1. Decisions to review (🔴)

Scope & sources
- 🔴 **"Building permits" are not on the source page → added from a second, official source.** The district page
  only publishes WZ decisions, public-purpose location (ULICP / "CP") decisions and initiated WZ/ULICP proceedings.
  Building permits live in GUNB's national register RWDZ (CC0 bulk CSV). They are ingested as **opt-in** kinds
  `pb` (permit, 2,365 cases) / `zg` (notification, 226) – hidden by default so the ~580 planning records are not
  drowned. See `docs/research/building-permits.md`.
- 🔴 **Second source of the same data: BAiPP lists.** The district page itself says cases handled by the city's
  Biuro Architektury i Planowania Przestrzennego are published separately. Those city-wide lists contain 104
  Praga-Południe rows (no overlap with the district files). Included, filtered to Praga-Południe by the address
  line, with their own id namespace (`wz-am-…`) and a "data source" / "issuer" facet.
- 🔴 **Newest BAiPP snapshot wins.** The same BAiPP case appearing in several files (monthly snapshots, yearly file)
  is one record whose values come from the newest snapshot (with a warning naming changed fields; all sources
  listed). District records keep "first listing wins". Chosen because the bureau corrects rows between
  republications.
- 🔴 **Feed (`feed.xml`) carries planning records only** (WZ / ULICP / initiated), not permits – ~150 permit
  cases a year would bury them. A separate permits feed or per-neighbourhood feeds could follow.

Privacy
- 🔴 (a) Explicit natural-person names in old district files ("Pani … reprezentowana przez pełnomocnika") are
  redacted to "osoba fizyczna (dane usunięte)" in the index and in the "as in source" view; the original file stays
  linked. (b) Business names that contain a person's name (sole proprietorships) are **kept**, like any company
  name (public CEIDG/KRS data). (c) GUNB designer names and licence numbers are **not** put into the index/UI (data
  minimisation). They **do** remain in the byte-exact mirrored extract of the CC0 register (`site/sources/rwdz/`),
  which is published so provenance can be checked byte for byte. Blanking them there would break byte-exactness.

Presentation
- 🔴 **Neighbourhood filter uses the 6 official MSI areas** (Gocław, Gocławek, Grochów, Kamionek, Olszynka
  Grochowska, Saska Kępa) from OpenStreetMap (ODbL). Przyczółek Grochowski is part of Gocław in MSI. Finer "osiedla"
  or Rada Osiedla boundaries could be added if wanted.
- 🔴 **Base map = OpenStreetMap standard tiles** (CARTO now requires an API key). Fine for low traffic under OSM's
  tile policy; for real traffic pick a keyed provider (one setting: `site/js/config.js → BASEMAP`).
- 🔴 **Kind filter with opt-in permits.** WZ/CP/initiated are ticked by default; "only WZ" is the "tylko" button
  (hover/focus; hidden on touch screens – there you untick the others). Old `rodzaj=wz` links still work.
  "Wyczyść filtry" also switches permits off.
- 🔴 **Phones, first visit:** a dismissible intro strip (what WZ is, "Serwis nieoficjalny") and the permits promo
  come before the first card (it starts ~615 of 844 px). Both stay dismissed. Option: show the intro once / merge.
- 🔴 **Outcome badges only for non-positive outcomes on cards** ("Odmowa" red; umorzenie / przekazanie / wygaszenie
  neutral). No green "granted" badge: district records never state an outcome, so a badge on BAiPP records only would
  mislead. All outcomes appear in the detail. The "Rozstrzygnięcie" facet explains that only BAiPP lists state
  outcomes; the CSV leaves the column empty for district rows (a value like "nie podano w źródle" would need both CSV
  writers changed together).
- 🔴 **Issuer labels name the handling office**: "Urząd Dzielnicy Praga-Południe (Wydział Architektury i
  Budownictwa)" and "Urząd m.st. Warszawy (Biuro Architektury i Planowania Przestrzennego)". Legally the authority for
  both is the Prezydent m.st. Warszawy. Shown in the CSV column `organ` and the issuer facet.
- 🔴 **Two new investment tags for permit texts**: "Instalacje w budynku" (431 permits, previously counted as
  "Sieci") and "Remont, docieplenie" (406). Labels and usefulness to review.

Geography
- 🔴 **Related records = same parcel or same street + house number, across all datasets.** With permits included
  this is dense: 343 of 474 district records relate to ≥1 permit; the longest list has 63 entries
  (`wz-am-2020-123`). On estate/co-op parcels many are unrelated renovations. The UI collapses long chains and states
  the reason. Options: rank permits filed after the WZ date first, ignore address-only links for permits, or a
  heuristic "project timeline".
- 🔴 **Address/parcel contradictions in the source.** When the exact address lies on a parcel with the *stated
  number* in another obręb, the source obręb is treated as a typo and corrected with a visible warning (38 records,
  e.g. Busolowa 16A). Otherwise the parcel point stays; 9 records are flagged `geo.conflict` and drawn hollow as
  "Lokalizacja niepewna – adres i działki się różnią"; 8 stay unflagged because the address lies in an obręb the
  record names. Alternative: show both points.
- 🔴 **Out-of-district permits are kept and counted** (4 cases registered under the Praga-Południe unit but lying in
  Praga-Północ or Wawer): corrected parcel id, warning, no map point – like the Port Praski BAiPP record. Alternative:
  drop them from the selection.
- 🔴 **Multi-parcel records: point on the largest parcel** when the weighted centroid falls on none of the parcels
  (201 records). Compared to the plain centroid, 64 planning records moved (max ~560 m, ULICP networks over several
  road parcels) and 3 changed neighbourhood (`cp-am-2023-c2-2`, `ws-am-6733-2022-9` Saska Kępa → Kamionek,
  `wz-am-2021-6` Grochów → Kamionek). Alternative for linear investments: a line / bbox instead of a point.

Operations
- 🔴 **Failure policy of the monthly build.** District index unreachable → exit 3, nothing deployed. BAiPP site
  down → previous BAiPP data kept with a visible page warning, build continues. GUNB download failure → committed
  extract used with a file warning, build continues; GUNB format change → exit 3; an edited committed extract →
  exit 1. The owner may prefer failing on BAiPP/GUNB outages too.
- 🔴 **Licence not declared.** README assumes MIT for code; data attribution: public information (Urząd Dzielnicy,
  Urząd m.st. Warszawy), GUGiK services, OSM (ODbL), GUNB RWDZ (CC0). Add a LICENSE file once confirmed.
- 🔴 **Deployment needs the owner:** create the GitHub repo, set Settings → Pages → Source "GitHub Actions", allow
  Actions to push (data commits), fill `REPO_URL` / `ISSUES_URL` in `site/js/config.js` (enables "Zgłoś błąd"
  buttons), make `og:image` absolute.

## 2. Source-data issues worth raising with the office (📮)

District office (Urząd Dzielnicy Praga-Południe)
- 📮 **Missing month: no page for August 2022** (index jumps from July to September 2022).
- 📮 **December 2020 WZ file declares 3 decisions but contains 1** (30/WZ/PPd/2020); rows 8–11 hold only Lp numbers.
- 📮 **43 WZ/CP decision numbers never appear in any list** (WZ 2024: 11 numbers, WZ 2025: 16, CP 2024: 5, CP 2025: 4,
  …; full list in `data/report.md`). Refusals or discontinued cases may be omitted from the lists – or entries are missing.
- 📮 Editing leftovers: Oct 2025 page links the Sep 2025 WZ file; Oct 2022 page has an invisible link to the Sep 2022
  CP file; 8 blocks declaring "0 pozycji" link empty template files. Handled (de-duplicated, flagged as page warnings).
- 📮 Typos in decision numbers, obręb codes, JRWA symbols and street names (corrected with a visible warning on the
  record; source spelling kept for display). 4 initiated proceedings carry the public-purpose symbol 6733 on housing.
- 📮 2020 – Feb 2021 pages have no publication date and no declared counts; their files were re-uploaded in May 2021.
- 📮 Obręb typos (found by checking the parcel under the exact address; corrected with a warning): Busolowa 16A
  'dz. 35, 36-cz. 3-06-03' is in 3-05-26 (wz-2023-23, ws-6730-2023-74); Chłodnicza 11 '88 3-06-07' is in 3-04-05
  (ws-6730-2024-2); Szklanych Domów 5b 'dz. 10/2, 10/9, 10/32 3-04-05' is in 3-04-04 (ws-6730-2026-2).

City (BAiPP lists)
- 📮 **Port Praski case labelled "Praga Południe"** (AM-ZP-P.6730.27.2025, Sokola / Wybrzeże Szczecińskie) lies on
  parcel 18/5 obr. 4-15-08, which exists only in Praga-Północ. Kept with a warning, corrected parcel id, no marker.
- 📮 **Duplicate WZ number 33 in the 2025 list** ('33/AM/BIE/WZ/2025/P' Bielany and '33/AM/PPD/WZ/2025/P'
  Praga-Południe; 34 missing; also 91 twice / 92 missing for other districts). If the office renumbers to 34, our
  id changes.
- 📮 Parcel/obręb typos: '77 3-06-02' (does not exist; 3-06-01 does), obręb cut to '3-05-2', '12/;', 'cz. 43/1r',
  'c. 68', 14/1 in 3-06-05 vs 3-06-06 for the same plot, 'Jugosławiańska'. Obręb `3-07-07` is in Rembertów, so the
  obręb prefix is not a district key.
- 📮 District code inside BAiPP numbers is unreliable (110/PRN/20 is a Praga-Południe case with the Praga-Północ code;
  21/AM/PRD/WZ/2025/O mixes codes). Our filter uses the address line.
- 📮 The 2025 page labels its .xlsx attachments "(xml, 37 KB)"; some workbooks have a sheet named " ".
- 📮 wz-am-2021-100 cites obręb 3-05-16, which does not exist in Praga-Południe.

GUNB (RWDZ register)
- 📮 Unit typos in district-office rows (148507_8 ×9, 146517_8 ×3, 146057_8 ×2, 146078_8, 146407_8, 140507_8,
  146506_8, 146508_8, 146509_8, 086101_1) – corrected with a warning. Four cases with a *valid* but wrong unit are
  kept through the hand-checked list `rwdz.UNIT_FIXES`: Szaserów 133 (ST-MZ-PA/WNIOSEK/14200/2024, 146510_8),
  Zwycięzców 34 (ST-MZ-WA/WNIOSEK/37134/2018, 146510_8), Ostrobramska (ST-MZ-WA/WNIOSEK/19454/2023, 146508_8),
  PL-MZ/WNIOSEK/15131/2026 (146507_5).
- 📮 146507_8 rows that belong elsewhere: Kijowska and Kawęczyńska 161 (Praga-Północ), ZGN Praga Pn.
  (146508_8.1507.3), one Wawer case – kept off the map (see §1). Other rows with obręb codes not in the district are
  flagged; ~25 district-office cases give the parcel number in the wrong obręb (list in `data/report.md`).
- 📮 Odd rows: nr_domu '146507_8' (a unit id) in ST-MZ-PA/WNIOSEK/18593/2019; the investor's address
  (Nowoursynowska 145D, Ursynów) given as the object address in pb-st-mz-pa-2016-42590.
- 📮 4 cases without any parcel; 189 cases with kubatura "1" (placeholder, shown as empty), 4 in scientific notation;
  "Jana Jeziorańskiego" instead of "Nowaka-Jeziorańskiego" in 19 rows; the download page says the separator is "#"
  (it is ";").

General
- 📮 Nobody in Warsaw publishes these lists as open data (CSV on dane.gov.pl), unlike e.g. Gliwice or Zabrze.
  Worth a formal request.

## 3. Known limitations / follow-ups (🟠)

Data & pipeline
- 🟠 ~10% of parcel ids are unknown to ULDK (only current parcels exist; old ones were subdivided/merged). Fallbacks:
  known sub-parcels → exact address (with `GetParcelByXY` obręb check) → street stretch inside the record's obręb
  (with `geo.uncertainty_m`, drawn as a dashed circle). Ideas: probe children `3/1…3/N`; a one-digit obręb
  correction with a street-proximity check (e.g. pb-st-mz-pa-2021-33529, 0707 → 0607); use the "former parcel
  numbers" in 104 permit applications (`stara_numeracja_*`) for matching and related records; a note when the
  register gives an investor address outside the district (pb-st-mz-pa-2016-42590).
- 🟠 `data/report.md` lists 4 RWDZ cases *not* kept although their case sign points to Praga-Południe
  (ST-MZ-WA/WNIOSEK/43874/2016, 27690/2025, 32369/2024, 23628/2022). Check each in ULDK; confirmed register errors go
  into `rwdz.UNIT_FIXES` (never automatic).
- 🟠 Stale-page / lost-file guard: a monthly page served without its file list (maintenance/WAF page) or a previously
  parsed file that becomes unreadable makes the build exit 3 (CI commits nothing). A second *local* run accepts the
  loss, because the comparison is with the previous `sources.json`.
- 🟠 Parcel cache hits never expire (subdivisions after the first lookup are not noticed) – add a yearly refresh.
- 🟠 Rows removed from a re-uploaded district file disappear from the site (old bytes are archived in
  `site/sources/history/`). Could keep them flagged "usunięte ze źródła". (BAiPP snapshots are already retained.)
- 🟠 BAiPP 2026 monthly snapshots before IX.2026 were never seen (the page links only the latest cumulative file);
  retention starts with this crawl.
- 🟠 Category/count detection on monthly pages is a heuristic over Polish headings; a brand-new wording yields
  `null` (surfaced in CLI summary and page warnings).
- 🟠 `STREET_TYPOS` and `STREET_CANONICAL` (16 streets written several ways, e.g. Fieldorfa ×6) are hand-kept
  tables; the report lists streets still written several ways. TERYT ULIC would be the long-term source.
- 🟠 The out-of-district probe relies on the obręb-zone table (1 Mokotów/Ursynów/Wilanów … 8 Wesoła) because ULDK's
  4-digit obręb code drops the zone digit.
- 🟠 Initiated proceedings cannot be linked to their final decision by number (different numbering systems); only the
  generic same-parcel/address relation connects them.
- 🟠 Classification gaps: 6 BAiPP and 27 permit records get no tag; "umorzenie postępowania" texts get the
  "zmiana lub umorzenie" tag by design; permit tags partly fall back on the building category. No hand-labelled
  evaluation set.
- 🟠 RWDZ has no outcome column (granted/refused) and only cases with a first-instance decision; number suffixes
  `/R` (64) and `/Z` (47) are undocumented and unused. The GUNB web search (the only place with outcomes and
  per-case pages) was in maintenance and needs a captcha – provenance = dataset file + mirrored extract + line numbers.
- 🟠 Building-category labels (I–XXX) must be verified against the official annex of Prawo budowlane.
- 🟠 `permits.json` is 6.9 MB (0.8 MB gzip), 40% of it the raw register columns needed only for "Dane w źródle".
  Lazy-loaded; phones skip the idle prefetch. If it grows: move raw rows to an on-demand file or split by year.
- 🟠 CI re-downloads ~93 MB from GUNB whenever GUNB regenerates its ZIPs (practically nightly; ~20 s of filtering,
  nothing committed if Praga-Południe lines are unchanged). Check weekly if bandwidth matters. `--skip-crawl` also
  skips the GUNB check (`make rwdz` refreshes it alone).
- 🟠 CSV column `arkusz_wiersz` reads `!<line>` for RWDZ rows (no sheet). A clearer "linia N" needs a coordinated
  change in `csv.js` + `export.py`.
- 🟠 Overpass (OSM) is sometimes over capacity; areas are cached and rebuilt only on demand.
- 🟠 Two HTTP helpers (crawler vs geocoder) differ in threading semantics; no repo-level ruff config.

Frontend
- 🟠 Accessibility: axe reports 0 violations in 14 states × 2 themes; keyboard flows (incl. map markers and "Wskaż na
  mapie") are covered by e2e. Not done: a real screen-reader pass (NVDA/VoiceOver), Safari on a physical device
  (WebKit tested via Playwright), individual timeline-bar descriptions (a table alternative exists), font sizes in
  px (~180 declarations; page zoom works, the browser's default-font-size setting does not).
- 🟠 Long related lists: the count matches the badge and "Zwiń listę" restores the 7-item window; clickable kind
  chips to filter the list are not done.
- 🟠 Street filter keys were canonicalised: links with old keys (e.g. `ulica=gierska`) resolve to nothing – only
  matters for links shared before deployment. Junk hash values (`okres=constructor`) are ignored but stay in the URL.
- 🟠 Search uses a light Polish stemming heuristic (budynek/budynku, Kamionek/Kamionku …); misses some forms
  (kościół/kościele) and adds a few loose prefix hits. A Morfologik-based index would be more precise.
- 🟠 On phones permit counts are totals until permits are loaded (no preload on purpose); search offers "Szukaj też
  w pozwoleniach…" instead of an exact count.
- 🟠 Up to 16 records share one parcel centroid; a same-spot list popup lists them.
- 🟠 "W pobliżu mnie" stores the point in the URL (rounded to ~100 m) so links are shareable.
- 🟠 Sources page lists every month (very long); year jump buttons and a "only mismatches" toggle exist.
- 🟠 `hyphens: auto` depends on the browser's Polish dictionary; long words always break safely anyway.
- 🟠 The e2e browser test (162 checks incl. a WebKit group) is not run in CI (needs browsers); `npm run e2e`
  (fixture) overwrites the real-data screenshots in `tests/e2e/output`. The OG image shows only planning kinds.

## 4. Handled during the build (🟢)

- 🟢 Six district spreadsheet layouts + six BAiPP layouts; columns mapped by header text; 474 district rows → 474
  records, nothing dropped; template rows (Lp-only) and note rows skipped; every value kept in the "as in source" view.
- 🟢 One file linked from two pages; records de-duplicated by decision number with all sources listed.
- 🟢 Declared vs parsed counts reconciled (443 declared + 33 rows in pages without counts − 2 missing = 474).
- 🟢 BAiPP: 7 pages, 28 workbooks, 1,635 city-wide rows → 104 Praga-Południe records (33 initiated, 56 WZ, 15 ULICP),
  counts identical to the manual research table; snapshots retained.
- 🟢 RWDZ: 2,463,002 register rows → Praga-Południe rows → 2,591 cases; byte-exact extracts mirrored with a line
  map; designer columns never reach the index.
- 🟢 Location: planning 577/578 (548 parcel, 6 address, 23 street; 1 deliberately off-map), permits 2,585/2,591
  (2,469 parcel, 79 address, 37 street). Addresses validated against the district polygon (rejects e.g. "Pińska 46" for "Mińska 46");
  subdivided parcels located via known sub-parcels; out-of-district BAiPP parcels detected by a zone-restricted
  ULDK probe.
- 🟢 Incremental, polite crawler; replaced files archived with history; pages removed from the source kept.
- 🟢 Deterministic outputs (no-op rebuilds produce no diff); CI for tests + monthly rebuild + Pages deploy prepared.
- 🟢 Search handles Polish inflection, parcel notations ("dz. 46/4 obr. 3-01-24", cadastral ids) and register numbers,
  and explains hidden matches.
- 🟢 Real-data sweep: every one of 3,165 details at 1440 px and 320 px, every card at 498/288 px – no errors, no
  overflow; permit merge sliced so no main-thread task exceeds ~75 ms on a throttled phone.
- 🟢 Independent audit round (6 auditors + 6 adversarial verifiers, 73 confirmed findings, 70 fixed, 2 partly, 1 to
  backlog). Highlights: every source cell re-extracted independently (4,045/4,046 present; the 1 is the documented
  redaction), RWDZ extract lines byte-identical to the GUNB ZIPs, every parcel point inside its parcel; fixed CI
  ping-pong of `generated_at` with `SITE_URL`, silent record loss on a maintenance page or corrupt file, CSV
  formula injection guard aligned in both writers, crawler accepts only http(s) links on *.um.warszawa.pl, street
  name variants merged in the street filter, keyboard access to map markers and "Wskaż na mapie", focus not hidden
  under sticky bars, WebKit map tiles, Back with the filter drawer open, honest outcome-facet wording, permit
  permalinks while permits are hidden, `make serve` uses the Node server.
