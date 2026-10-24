# Research: building permits and the second WZ/ULICP source for Praga-Południe

Status: research note, 2026-10-23. Everything below was checked live on that date (HEAD/GET requests,
full downloads of files under 50 MB, streamed parsing of the large CSVs). Nothing in this note is
wired into the pipeline yet; it is input for the lead / next iteration.

## TL;DR

| # | Source | What | Machine-readable? | Praga-Południe volume | Verdict |
|---|--------|------|-------------------|-----------------------|---------|
| A | **BAiPP lists** – `architektura.um.warszawa.pl/postepowania-i-decyzje` + yearly archive pages | The **same three record types** we already ingest (WZ, ULICP, initiated WZ/ULICP proceedings), but for cases handled centrally by Biuro Architektury i Planowania Przestrzennego | `.xlsx`, city-wide, one row per case, 7 columns, cumulative year-to-date | **104 rows** Aug 2020 – Sep 2026 (33 initiated, 56 WZ, 15 ULICP); **zero overlap** with the district files | **In scope – integrate next.** ~1 day. |
| B | **GUNB RWDZ bulk files** – `wyszukiwarka.gunb.gov.pl/pobranie.html` (mirrored on dane.gov.pl, dataset 3467) | Building-permit and demolition-permit decisions (*pozwolenia na budowę / rozbiórkę*) and some *zgłoszenia* (notifications), nationwide since 2016 | CSV in ZIP, `;`-separated, UTF-8 with BOM, one row per case × parcel, **CC0 1.0**, refreshed nightly | **2,340 permit decisions** (942 since Aug 2020) + **225 zgłoszenia** | **The answer to "building permits".** Integrate as new kinds `pb` / `zg`. ~1.5–2 days. |
| C | Warsaw city WMS `wms.um.warszawa.pl/serwis` layers `DECYZJE_O_WARUNKACH_ZABUDOWY`, `DECYZJE_O_POZWOLENIU_NA_BUDOWE` | Legacy point layers of WZ decisions (2008–2022 in our sample) and building permits | WMS raster + GetFeatureInfo only (no WFS), no decision numbers, CORS `*` | ~390 points per 4×4 km tile | Optional historical **map overlay** only. Not a data source. |
| – | e-Budownictwo, Warsaw BIP notices, dane.gov.pl (Warsaw), district website | – | No usable permit data | – | Not useful (details below). |

Key cross-source fact: RWDZ identifies parcels exactly the way our data model does
(`jednosta_numer_ew` + `obreb_numer` + `numer_dzialki` → `146507_8.0605.25/12`). A naive parcel match
links **282 of 445** district WZ/CP/initiated rows to at least one RWDZ permit case, i.e. permits
plug straight into the existing `related` mechanism and the existing ULDK geometry cache.

---

## 1. Scope clarification

The owner wrote about "building permits and development condition permits". The district page
(`pragapld.um.warszawa.pl/informacja-o-wszczetych-postepowaniach-oraz-wydanych-decyzjach-administracyjnych`)
publishes only what Zarządzenie nr 1129/2020 Prezydenta m.st. Warszawy requires:

1. initiated WZ / ULICP proceedings,
2. issued WZ decisions,
3. issued ULICP decisions (local, and national/voivodeship significance).

There are **no building permits** on that page or anywhere else on the district website (site search for
"pozwolenia na budowę" returns only unrelated news). Building permits for Praga-Południe are issued by the same
department (Wydział Architektury i Budownictwa dla Dzielnicy Praga-Południe, `UD-VI-WAB`), and the only public,
structured record of them is GUNB's national register RWDZ (art. 82b Prawo budowlane).

The same page carries a footnote: *"oddzielne zestawienia, dotyczące spraw prowadzonych przez Biuro Architektury
i Planowania Przestrzennego Urzędu m.st. Warszawy publikowane jest na stronie w/w biura"*. That page exists and
contains Praga-Południe cases of exactly our three types (section 2).

---

## 2. Source A – BAiPP (city architecture office) WZ / ULICP lists [IN SCOPE]

### 2.1 Where

| Page | URL | Period | Published (`<time>`) |
|------|-----|--------|----------------------|
| Current year | <https://architektura.um.warszawa.pl/postepowania-i-decyzje> | I–IX 2026 (cumulative, replaced monthly) | files modified 2026-10-05…12 |
| 2025 | <https://architektura.um.warszawa.pl/-/rejestry25> | I–XII 2025 | 2026-01-14 |
| 2024 | <https://architektura.um.warszawa.pl/-/rejestry24> | I–XII 2024 | 2025-02-12 |
| 2023 | <https://architektura.um.warszawa.pl/-/rejestry23> | I–XII 2023 | 2024-02-16 |
| 2022 | <https://architektura.um.warszawa.pl/-/rejestry2022> | I–XII 2022 | 2023-02-10 |
| 2021 | <https://architektura.um.warszawa.pl/-/rejestry2021> | I–XII 2021 | 2022-02-16 |
| 2020 | <https://architektura.um.warszawa.pl/-/rejestry2020> | VIII–XII 2020 | 2022-02-16 |

Slugs are irregular (`rejestry2022` vs `rejestry23`; `rejestry2023`, `rejestry2026`, `rejestry26` all 404).
**Do not guess slugs** – discover them from the "Dane z ubiegłych lat" box on the current page: it is a second
`journal-content-article` on `/postepowania-i-decyzje` whose `<a href="/-/rejestry…">` links are labelled
"Informacja o wszczętych postępowaniach i wydanych decyzjach w YYYY r.". The same box links all 18 district
pages (Praga-Południe → our current source), which is a handy cross-check.

`robots.txt` only disallows `/szukaj`. Files are served with `Last-Modified`, `Content-Disposition` and
`access-control-allow-origin: https://architektura.um.warszawa.pl` (so build-time fetching only, like the district).

### 2.2 Page structure (Liferay, same CMS as the district site)

Each page has exactly 4 attachment links inside the first `journal-content-article`, always in this order:

| # | Link text (prefix) | Our `kind` |
|---|--------------------|-----------|
| 1 | `1. Informacja o wszczętych postępowaniach o warunkach zabudowy i ustaleniu lokalizacji inwestycji celu publicznego …` | `ws` |
| 2 | `2. Informacja o wydanych decyzjach w sprawie warunków zabudowy …` | `wz` |
| 3 | `3. Informacja o wydanych decyzjach w spr. ust. lokalizacji inwestycji celu publ. o znaczeniu powiatowym i gminnym …` | `cp` (local, numbers contain `CP2`/`C2`) |
| 4 | `4. Informacja o wydanych decyzjach w spr. ust. lokalizacji inwestycji celu publ. o znaczeniu krajowym i wojewódzkim …` | `cp` (national/voivodeship, `CP1`/`C1`) |

Links are site-relative Liferay document paths, same shape as the district ones, e.g. (current page):

```
/documents/12025039/171613001/informacja_o_wszcz%C4%99tych_post%C4%99powaniach_o_WZ_LICP_IX_2026+%2B.xlsx/289a1962-288a-3179-aabf-643286f2a106?t=1791798491258
/documents/12025039/171613001/informacja_o_wydanych_decyzjach_WZ_IX_2026+%2B.xlsx/1d75d6d6-239a-2dc1-843b-70184b23709c?t=1791798490945
/documents/12025039/171613001/informacja_o_wydanych_decyzjach_ustalenie_LICP_o_znaczeniu_powiatowym+_i_gminnym_IX_2026+%2B.xlsx/7dbca2ea-686b-0157-caa3-134d35570f6b?t=1791798490447
/documents/12025039/171613001/informacja_o_wydanych_decyzjach_o_ustaleniu_LICP_o_znaczeniu_krajowym_i_woj%C3%B3dzkim_IX_2026+%2B.xlsx/fae00082-7a3e-6cb0-d96c-6a3104611a81?t=1791798491576
```

The `file_id = sha1(document_path)[:10]` rule from `DATA_MODEL.md` can be reused unchanged: Liferay group ids
(`50051` district vs `12025039` BAiPP) are unique across the `*.um.warszawa.pl` portal, so paths never collide.
The file-type label on the 2025 page says "(xml, 37 KB)" but the files are `.xlsx` – trust the extension /
`Content-Type`, not the label.

**Cumulative snapshots.** The current-year file is year-to-date (the "IX.2026" WZ file has decisions dated
2026-01-05 … 2026-09-x; the yearly files have I–XII). Every month the current page links a *new* document
(new folder id + uuid) and the previous month's link disappears. Consequences:

* rows reappear in every monthly snapshot → de-duplicate by case sign / decision number (we do that already);
* the source link for a current-year row changes monthly → keep every snapshot we ever downloaded
  (`data/raw/`, mirrored to `site/sources/`) and list all of them in `sources[]`; the newest is "current";
* previous snapshots may still be downloadable from Liferay (not verified – we never saw their URLs).

### 2.3 Workbook layout (28 files inspected: 2020–2026 × 4)

All files: one sheet, column A empty, title rows 1–3 ("nazwa organu: Prezydent m.st. Warszawy, Biuro
Architektury i Planowania Przestrzennego", list title), **header in row 4**, numbering row `1..7` in row 5
(missing the first number in some WZ files), **data from row 6**. Dates are real Excel dates (cleaner than the
district files). Header texts (whitespace-collapsed):

| Kind | Layout (2021–2026) | Columns B…H |
|------|--------------------|-------------|
| `ws` | `baipp-ws` | `Lp.` · `Znak sprawy` · `Data wszczęcia postępowania (rrrr-mm-dd)` · `Nazwa wnioskodawcy` · `Nazwa inwestycji z wniosku` · `Adres inwestycji (ulica, dzielnica)` · `Oznaczenie nieruchomości (nr działki ew., obręb)` |
| `wz` | `baipp-wz` | `L.P.`/`Lp.` · `Nr decyzji` · `data (rrrr-mm-dd)` · `Nazwa wnioskodawcy` · `Oznaczenie nieruchomości (ulica, dzielnica)` · `Oznaczenie nieruchomości (nr działki ewid., obręb)` · `Streszczenie ustaleń decyzji` |
| `cp` | `baipp-cp` | `Lp.` · `Nr decyzji` · `data (rrrr-mm-dd)` · `Nazwa wnioskodawcy` · `Streszczenie ustaleń decyzji` · `Oznaczenie nieruchomości (ulica, dzielnica)` · `Oznaczenie nieruchomości (nr działki ewid., obręb)` |

2020 files use the old "Załącznik do zarządzenia 1129/2020" header: `Nr decyzji i data jej wydania` (merged over
2 columns: number, date) and `Oznaczenie nieruchomości (ulica, dzielnica, nr działki ew., obręb)` (merged over
2 columns: street+district, parcels) – i.e. the same 2-row-header idea as the district's old layout, so
`parse.py`'s header-text mapping should handle it with a few extra synonyms. One 2022 WZ file has an extra
empty trailing header column; one 2020 CP file has 13 columns (empty extras).

Value conventions worth knowing:

* **District** = last non-empty line of the address cell: `"Ostrobramska 73 \nPraga Południe \n\n"`.
  Spelled `Praga Południe` (no hyphen); one typo `Parga Południe` (2021).
* **Decision number + outcome in one cell**: `"95/AM/PPD/WZ/2026/O\n\nodmowa "`,
  `"33/AM/PPD/WZ/2025/P\nprzeniesienie"`, `"6/PRD/21\nwz"`, `"1/PRD/C2/22\numorzenie  licp"`.
  Suffix letter (2024+): `/O` odmowa (refusal), `/U` umorzenie (discontinued), `/P` przeniesienie (transfer),
  `/W` wygaśnięcie (expiry); no suffix = granted. The second line repeats it in words (`wz`/`licp` = granted).
  This is richer than the district files – worth surfacing as an "outcome" facet.
* **District code in the number**: `PPD` (2024+: `n/AM/PPD/WZ/yyyy`), `PRD` (2020–2023: `n/PRD/yy`,
  `n/PRD/C2/yy`). Not reliable alone: one 2020 row for Podskarbińska (Praga-Południe) is numbered `110/PRN/20`,
  and one 2023 CP row numbered `10/PRD/C2/23` lies in Śródmieście.
* **Case signs** for initiated proceedings: `AM-ZP-P.6730.14.2020` (6730 = WZ, 6733 = ULICP; `ZP-P` = the
  "Praga" planning unit, which also covers Praga-Północ; `ZP-E` covers Rembertów/Wawer/Wesoła).
* **Applicant privacy**: natural persons are written as `dane osobowe` (not `osoba fizyczna`). No `Pan/Pani …`
  names found in any Praga-Południe row. Map `dane osobowe` → `applicant_type: person`, display "osoba fizyczna".
* **Parcels**: `"cz. 7/5; 3-05-24"`, `"43/1, 43/2 3-02-06"`, `"14 3-02-03 8; 10; 11; 12; 21 3-02-02"` – same
  grammar as the district files.

### 2.4 Filtering to Praga-Południe – three signals, verified

Rows per file (all city-wide rows / Praga-Południe rows by the recommended *address* rule below):

| Year | ws | wz | cp (local) | cp (national) |
|------|----|----|-----------|---------------|
| 2020 (VIII–XII) | 55 / 4 | 80 / 4 | 7 / 0 | 7 / 0 |
| 2021 | 88 / 8 | 157 / 10 | 12 / 0 | 5 / 1 |
| 2022 | 86 / 9 | 162 / 5 | 13 / 6 | 5 / 0 |
| 2023 | 123 / 5 | 155 / 19 | 14 / 7 | 1 / 0 |
| 2024 | 79 / 2 | 139 / 8 | 20 / 0 | 2 / 0 |
| 2025 | 94 / 3 | 125 / 9 | 10 / 1 | 3 / 0 |
| 2026 (I–IX) | 85 / 2 | 101 / 1 | 6 / 0 | 5 / 0 |
| **Total PP** | **33** | **56** | **14** | **1** |

(A naive "address OR obręb section 3-01…3-07" rule gives 107 – the 3 extra rows are Rembertów, see below; one
of the 104 is the mislabelled Port Praski case.)

Pitfalls found (all confirmed with ULDK `GetParcelById`):

* **Obręb section is not a district key.** `3-07-07` belongs to **Rembertów** (`146509_8.0707.22/4` exists,
  `146507_8.0707.22/4` does not), while `3-07-18` is Praga-Południe. So "3-0x" ≠ Praga-Południe. Two 2025
  Rembertów rows (Chełmżyńska, `AM-ZP-E.6730.5/6.2025`) and one 2026 Rembertów WZ row would be false positives.
* **Source errors exist.** `AM-ZP-P.6730.27.2025` (Port Praski, Sokola / Wybrzeże Szczecińskie) is labelled
  "Praga Południe" but its parcel `18/5; 4-15-08` is in **Praga-Północ** (`146508_8.1508.18/5`).
* An applicant name can contain the district ("Spółdzielnia Spożywców Praga Południe") – match the
  **address column only**, never the whole row.

Recommended rule: `in_district = address_last_line ~ /praga[\s-]*(po[lł]udnie|p[lł]d)|parga po[lł]udnie/i`;
then, during geocoding, if none of the row's parcels resolves under `146507_8` but they resolve under another
Warsaw unit (`146502_8` … `146519_8`), keep the record but add a warning
("działka poza dzielnicą Praga-Południe wg ULDK") – sources matter, so we show what the office published and
flag the inconsistency rather than silently dropping it.

### 2.5 Sample rows (verbatim values, `\n` shown as ⏎)

```
ws  AM-ZP-P.6730.14.2020 | 2020-08-05 | Eiffage Immobilier  Polska Sp. z o. o. | wniosek o wydanie decyzji o wz - budowa zespołu budynków o funkcji mieszkalnej wielorodzin… | Chodakowska⏎Wawerska⏎Praga Południe | 43/1, 43/2 3-02-06
wz  95/AM/PPD/WZ/2026/O⏎⏎odmowa | 2026-09-16 | Inicjatywa Projektowa ⏎sp. z o.o. | Ostrobramska 73 ⏎Praga Południe | cz. 7/5; 3-05-24⏎ | odmowa ustalenia warunków zabudowy dotyczy budowy budynku mieszkalnego wielorodzinnego z u…
cp  10/AM/PPD/CP2/2025⏎licp⏎ | 2025-12-12 | Stoen Operator ⏎sp. z o. o. | ustalenie lokalizacji inwestycji celu publicznego dotyczy budowy sieci elektroenergetyczne… | Waszyngtona⏎Praga Południe | cz.:  110 ; 3-05-01, ⏎50 ,  47; 3-05-31, …
```

### 2.6 Integration notes for the pipeline (proposal – not yet in DATA_MODEL.md)

* **Crawl**: fetch `/postepowania-i-decyzje`, take the 4 attachment links from the first article + the
  `/-/rejestry…` links from the second article, fetch each yearly page, take its 4 links. 7 pages, 28 files,
  ~700 kB total. Store as manifest `pages[]` with `page_id` = slug (`postepowania-i-decyzje`, `rejestry25`, …),
  `period` = `YYYY` (or `YYYY-01..YYYY-09` for the current page – see below) and a new
  `source: "baipp"` (district pages get `source: "district"`).
* **Kind detection**: block/link text or the sheet title text ("Informacja o wszczętych…", "…warunków
  zabudowy", "…lokalizacji inwestycji celu publicznego…"), same as for district files.
* **Record id collisions – must namespace.** City-wide numbering (`95/AM/PPD/WZ/2026`) would map to
  `wz-2026-95` under the current rule and can collide with the district's own `95/PPD/WZ/2026`; likewise
  `AM-ZP-P.6730.2.2026` → `ws-6730-2026-2` collides with district `UD-VI-WAB-U.6730.2.2026`. Proposed ids:
  `wz-am-2026-95`, `cp-am-2025-10`, `ws-am-6730-2026-2` (the `AM` prefix appears in every BAiPP number/sign since
  2024; for 2020–2023 numbers like `6/PRD/21` the source is known from the file). Add a record field
  `issuer: "district" | "baipp"` (UI label: "Wydział Architektury i Budownictwa dla Dzielnicy Praga-Południe"
  vs "Biuro Architektury i Planowania Przestrzennego (Urząd m.st. Warszawy)").
* **period** for BAiPP rows = month of the decision / initiation date (the files are yearly/cumulative, not
  monthly).
* **No overlap with district files**: none of the 176 district workbooks mentions `AM-ZP`, `/AM/` or "Biuro
  Architektury", and the BAiPP PP cases are different cases (e.g. district declared 0 WZ in Sep 2026, BAiPP has
  one). So these 104 rows are genuinely new datapoints for the same map.
* **Effort**: ~1 day (crawler branch for a second index, 3 header synonyms + outcome parsing in `parse.py`,
  district filter, id namespace, UI label/facet for issuer and outcome). **Risk**: low – same CMS, same row
  grammar; main risks are the irregular archive slugs (mitigated by link discovery) and the monthly
  re-publication of the current-year file.

---

## 3. Source B – GUNB RWDZ (Rejestr Wniosków, Decyzji i Zgłoszeń) [BUILDING PERMITS]

### 3.1 Where / what

* Bulk download page: <https://wyszukiwarka.gunb.gov.pl/pobranie.html> ("Dane obejmują okres od 01.01.2016 r.
  z codzienną aktualizacją w godzinach nocnych"). 16 voivodeship ZIPs (*wnioski i decyzje* = permit
  applications that ended with a decision) + 2 nationwide ZIPs of *zgłoszenia*.
* Mirror / metadata: dane.gov.pl dataset **3467** "Rejestr Wniosków, Decyzji i Zgłoszeń w sprawach budowlanych"
  (<https://dane.gov.pl/pl/dataset/3467>), resource for Mazowieckie **2835391**. Licence **CC0 1.0**,
  `has_high_value_data: true`, harvested weekly from the GUNB feed
  `https://wyszukiwarka.gunb.gov.pl/pliki_pobranie/rwdz.xml` (harvester XML listing all 18 resource URLs).
  dane.gov.pl has no tabular API for it (`/resources/2835391/data` returns nothing) – it only re-hosts the ZIP.
* Dataset notes (verbatim, abridged): data entered after 01.01.2016; building-permit applications and decisions,
  plus zgłoszenia for detached single-family houses whose impact area stays within the plot, small (≤35 m²)
  buildings / transformer stations, and ≤1 kV power, water, sewage, heat and telecom networks; **only
  first-instance decisions**; struck-through entries mean the decision was eliminated from legal circulation;
  **no investments in closed areas** (*tereny zamknięte*, e.g. military/rail).

| File (`https://wyszukiwarka.gunb.gov.pl/pliki_pobranie/…`) | ZIP size | CSV size | Rows | Last-Modified |
|---|---|---|---|---|
| `wynik_mazowieckie.zip` | 46,486,656 B | 331.9 MB | 695,247 | Thu, 22 Oct 2026 21:35:08 GMT |
| `wynik_zgloszenia_2022_up.zip` | 25,982,070 B | 350.7 MB | 938,401 | Thu, 22 Oct 2026 21:36:04 GMT |
| `wynik_zgloszenia_2016_2021.zip` | 20,964,045 B | 296.5 MB | 829,354 | Thu, 22 Oct 2026 21:36:00 GMT |

HTTP: Apache, `ETag` + `Last-Modified`, `Accept-Ranges: bytes`; conditional GET with `If-None-Match` /
`If-Modified-Since` returns **304** (cheap change detection). **No CORS headers** on GUNB or on the dane.gov.pl
copy → download at build time only (fine for a monthly-rebuilt static site). No rate limiting observed; one
download per rebuild is polite. Streaming the Mazowieckie ZIP through Python's `zipfile` + `csv` and filtering
to the district takes **~2.3 s** on a laptop (no need to unzip to disk).

### 3.2 Format gotchas

* The page says the separator is `#` – **it is `;`**. Quote char `"`, empty values often written as `""`.
* UTF-8 **with BOM** (`encoding="utf-8-sig"`). No embedded newlines broke the 695k-row parse.
* Header has a **duplicate column name** (`cecha;cecha`) → read by position or rename on read.
* **One row per case × parcel**: 3,372 Praga-Południe rows = 2,340 cases (max 25 parcels in one case). Within a
  case only `numer_dzialki` / `obreb_numer` vary.
* Dates are `YYYY-MM-DD 00:00:00`.
* The *wnioski* file contains only cases **with a decision** (`data_wydania_decyzji` is never empty in 695k
  rows; max = yesterday). Pending applications are visible only in the (captcha-protected) web search.
* There is **no outcome column** (granted / refused / discontinued). The web search distinguishes "Decyzja
  pozytywna / odmowna / umarzająca", the bulk CSV does not. Decision-number suffixes hint at it
  (`/R` rozbiórka, `/Z` zmiana, one `66/PPD/PB/2025/O` – `/O` is odmowa in the city's numbering) but this is
  not documented → show "decyzja (rodzaj rozstrzygnięcia nieznany w danych GUNB)" unless a suffix is known.

### 3.3 Columns

*Wnioski i decyzje* (31 columns):

```
numer_urzad; numer_gunb; nazwa_organu; adres_organu; data_wplywu_wniosku; numer_decyzji_urzedu;
data_wydania_decyzji; nazwa_inwestor; wojewodztwo; miasto; terc; cecha; cecha; ulica; ulica_dalej; nr_domu;
rodzaj_inwestycji; kategoria; nazwa_zamierzenia_bud; nazwa_zam_budowlanego; kubatura; projektant_nazwisko;
projektant_imie; projektant_numer_uprawnien; jednosta_numer_ew; obreb_numer; numer_dzialki;
numer_arkusza_dzialki; jednostka_stara_numeracja_z_wniosku; stara_numeracja_obreb_z_wnioskiu;
stara_numeracja_dzialka_z_wniosku
```

*Zgłoszenia* (26 columns – note: **no investor column**, adds `stan`, postcode, `projektant_pozostali`):

```
numer_ewidencyjny_system; numer_ewidencyjny_urzad; data_wplywu_wniosku_do_urzedu; nazwa_organu;
wojewodztwo_objekt; obiekt_kod_pocztowy; miasto; terc; cecha; cecha; ulica; ulica_dalej; nr_domu; kategoria;
nazwa_zam_budowlanego; rodzaj_zam_budowlanego; kubatura; stan; jednostki_numer; obreb_numer; numer_dzialki;
numer_arkusza_dzialki; nazwisko_projektanta; imie_projektanta; projektant_numer_uprawnien; projektant_pozostali
```

Mapping to our `Record`:

| Record field | RWDZ permits (`pb`) | RWDZ zgłoszenia (`zg`) |
|---|---|---|
| `number` | `numer_decyzji_urzedu` (e.g. `163/PPD/PB/2026`) | `numer_ewidencyjny_urzad` |
| case sign (new `case_sign`) | `numer_urzad` (e.g. `UD-VI-WOM-ROB/16676/26/PHO`, older `K2/…`) | – |
| stable id source | `numer_gunb` (`ST-MZ-PA/WNIOSEK/29594/2026`, unique per case; 0 collisions) | `numer_ewidencyjny_system` (`ST-MZ-PA/ZGŁOSZENIE/6160/2026`) |
| `date` | `data_wydania_decyzji` (also keep `data_wplywu_wniosku` → `filed_date`) | `data_wplywu_wniosku_do_urzedu` |
| `applicant` | `nazwa_inwestor` – **empty for natural persons** (737 of 2,340 cases) → "inwestor prywatny (dane niepublikowane)" | not published |
| `investment` | `nazwa_zam_budowlanego` (free text) | same |
| scope / tags | `nazwa_zamierzenia_bud` (budowa / rozbudowa / nadbudowa / odbudowa / rozbiórka / roboty inne), `rodzaj_inwestycji` (jednorodzinny vs inny), `kategoria` (I–XXX), `kubatura` | `rodzaj_zam_budowlanego`, `kategoria`, `stan` |
| `address` | `cecha` + `ulica_dalej` + `ulica` + `nr_domu` (`ulica_dalej` is the patron's first name: `Czapskiego` + `Andrzeja`) | same + `obiekt_kod_pocztowy` |
| `parcels[].id` | `jednosta_numer_ew` + `.` + `obreb_numer` + `.` + `numer_dzialki` → **`146507_8.0605.25/12`** (identical to DATA_MODEL) | `jednostki_numer` + … |
| issuer | `nazwa_organu`: "Prezydent Miasta Warszawa - Praga Płd." (district WAB), "Prezydent Miasta Warszawa" (BAiPP), "Wojewoda Mazowiecki" | same |

`kategoria` labels (annex to Prawo budowlane; secondary source blog.ongeo.pl – verify against ISAP before
shipping): I jednorodzinne · II gospodarstwa rolne · III małe budynki pomocnicze · IV elementy dróg i kolei ·
V sport/rekreacja na zewnątrz · VI cmentarze · VII nawigacja wodna · VIII pozostałe budowle · IX kultura,
nauka, oświata · X kult religijny · XI zdrowie, opieka społeczna · XII administracja, sądy, wojsko ·
XIII pozostałe budynki mieszkalne (wielorodzinne) · XIV zakwaterowanie turystyczne · XV sport pod dachem ·
XVI biura · XVII handel, gastronomia, usługi · XVIII przemysł, magazyny · XIX zbiorniki · XX stacje paliw ·
XXI transport wodny · XXII place, parkingi · XXIII lotniska · XXIV gospodarka wodna · XXV drogi i tory ·
XXVI sieci · XXVII hydrotechnika · XXVIII mosty, tunele · XXIX kominy, maszty · XXX ujęcia, oczyszczalnie.

### 3.4 Filtering to Praga-Południe

Filter on **location**, not on the issuing office: `jednosta_numer_ew == "146507_8"` (zgłoszenia:
`jednostki_numer`). `terc` is the city (`1465011`) for every Warsaw row, so it cannot be used.

| Issuer of cases located in 146507_8 | permit cases | zgłoszenia 2016–21 | zgłoszenia 2022+ |
|---|---|---|---|
| Prezydent Miasta Warszawa - Praga Płd. (district) | 2,212 | 113 | 103 |
| Prezydent Miasta Warszawa (BAiPP, `AM.AB.6740…`) | 119 | 6 | – |
| Wojewoda Mazowiecki (+ Radom delegation; networks, rail) | 8 | 1 | 2 |
| Prezydent Miasta Warszawa - Praga Pn. | 1 | – | – |
| **Total** | **2,340** | **120** | **105** |

The district office also has 41 rows with another unit: `146514_8` (Wawer, 19 – genuine neighbouring parcels),
typos such as `148507_8` (6), `146057_8`, `146078_8`, and 4 empty. Recommendation: include
`unit == 146507_8`; additionally include district-office rows whose unit is empty or within edit distance 1 of
`146507_8`, with a warning ("nieprawidłowy identyfikator jednostki w RWDZ: …").

Volumes for planning (permit cases by decision year): 2016 307 · 2017 320 · 2018 290 · 2019 334 · 2020 218 ·
2021 201 · 2022 157 · 2023 140 · 2024 138 · 2025 132 · 2026 (to 14 Oct) 103. Since Aug 2020 (our WZ coverage):
942 permit cases (210 new builds, 107 demolitions, 75 extensions, 15 add-storey, 534 "other works"; 99 new
multi-family buildings in category XIII) and 124 zgłoszenia. Median application→decision time 66 days
(p90 179). Raw JSON of the post-2020 subset ≈ 1.6 MB before normalisation; normalised records will be well
under 1 MB (gzip ≈ 200 kB) – fine to ship, ideally as a separate lazily loaded `permits.json`.

Sample (latest decision in the file; designer columns elided here although GUNB publishes them):

```
numer_urzad            RPW/142815/2026-1B/FSO
numer_gunb             ST-MZ-PA/WNIOSEK/29594/2026
nazwa_organu           Prezydent Miasta Warszawa - Praga Płd.   (ul. Grochowska 274, 03-841 Warszawa)
data_wplywu_wniosku    2026-09-24 00:00:00
numer_decyzji_urzedu   163/PPD/PB/2026
data_wydania_decyzji   2026-10-14 00:00:00
nazwa_inwestor         ""   (natural person – not published)
adres                  ul. Salamandry 3, Warszawa
rodzaj_inwestycji      Obiekt budowlany inny niż budynek mieszkalny jednorodzinny
kategoria              XIII
nazwa_zamierzenia_bud  wykonanie robót budowlanych innych niż wymienione powyżej
nazwa_zam_budowlanego  Projekt przebudowy lokalu mieszkalnego nr 46 w budynku mieszkalnym wielorodzinnym
działka                146507_8 / 0605 / 25/12
```

### 3.5 Linking back to the source ("sources matter")

There is no stable public per-case URL: detail pages are `https://wyszukiwarka.gunb.gov.pl/captcha/wniosek/<uuid>/`
(uuid not in the CSV, captcha required, `/wniosek/` disallowed in `robots.txt`). Recommended source block per
record:

1. **The dataset file itself**: the GUNB ZIP URL + dane.gov.pl resource page, with the snapshot's
   `Last-Modified`, `ETag`, SHA-256 and the **line number** of each contributing row.
2. **A verifiable mirror**: write `site/sources/rwdz/wnioski_146507_8_<YYYY-MM-DD>.csv` containing the original
   header and the original lines (byte-for-byte, including the parcel rows), so anyone can diff our extract
   against GUNB's file. ~0.5 MB; no need to mirror the 46 MB ZIP into git.
3. **"Sprawdź w rejestrze GUNB" deep link** pre-filled by parcel (the user solves the captcha on GUNB's side).
   Query format reconstructed from Wayback captures of the search form (2024–2026):
   `https://wyszukiwarka.gunb.gov.pl/?document_type=rwd&rwd_document_type=Dowolny&request_number=&decision_number=&date_min=&date_max=&decision_date_min=&decision_date_max=&organ_region=all&org=all&region=all&city=&street=&house_nr=&ew_parcel=25%2F12&ew_organ=146507_8.0605&ew_sheet=&invest_purpose=all&invest=all&intention_name=&sec_code=&submit=submit`
   (`ew_organ` = `<unit>.<obręb>`, `ew_parcel` = parcel number; `request_number` takes the office case sign).
   **Not verifiable today**: the search UI shows "Trwa przerwa serwisowa" (maintenance page, Last-Modified
   2026-10-22) while the bulk files keep updating. This link works for *every* record type (also WZ/CP), so it
   is a cheap, high-value addition.
4. Per-parcel map context: Geoportal `https://mapy.geoportal.gov.pl/imapnext/imap/?identifyParcel=146507_8.0605.25/12`
   (documented parameter); its "Raport o działce" includes an RWDZ section with permits within 150/300/500 m.

### 3.6 Privacy

* GUNB blanks natural-person investors; the column still contains trade names of sole proprietorships that
  include a person's name (≈160 of 2,340 cases do not look like company/institution names; most are housing
  co-ops/abbreviations, a minority are "FIRMA Imię Nazwisko"). Those are public business names (CEIDG), consistent
  with our rule of keeping organisation names – but the owner may want to treat them like `Pan/Pani` names.
* **Designer names and licence numbers** (`projektant_*`) are published by GUNB under CC0, but they are not
  needed for the product's purpose. Recommendation: do **not** put them in the index / UI (data minimisation);
  they remain visible in the mirrored source extract. Owner decision.

### 3.7 Integration design (proposal)

* New kinds: `pb` = "Pozwolenie na budowę / rozbiórkę (RWDZ)", `zg` = "Zgłoszenie budowy (RWDZ)". `procedure` = `pb`
  / `zg`. Record id: `pb-` / `zg-` + slug of the GUNB system number without the type word, e.g.
  `ST-MZ-PA/WNIOSEK/29594/2026` → `pb-st-mz-pa-2026-29594`; `PL-MZ/ZGŁOSZENIE/12/2025` → `zg-pl-mz-2025-12`
  (0 collisions in the PP subset; stable across rebuilds).
* New module `pipeline/rwdz.py`: conditional download (ETag cache in `data/cache/rwdz.json`), stream-filter the
  three ZIPs, group rows by case, normalise, emit records + the mirrored CSV extracts; register each snapshot as a
  "file" in `sources.json` (`url`, `dataset_url`, `last_modified`, `sha256`, `archive_path`, `row_count`).
  The 2016–2021 zgłoszenia file is frozen → download once, keep the extract.
* Geocoding: reuse the ULDK parcel cache (same ids); RWDZ addresses are well-formed (97% have a street, 84% a
  house number), so the address fallback works better than for WZ.
* `related`: link `pb`/`zg` ↔ `wz`/`cp`/`ws` by shared parcel id (already the mechanism in DATA_MODEL). Naive
  estimate: 282 of 445 district rows share ≥1 parcel with an RWDZ case (255 distinct permit cases). Shared
  parcel ≠ same project (big co-op parcels carry many unrelated renovations), so label it "inne sprawy na tej
  działce", optionally favouring permits with `data_wplywu_wniosku` after the WZ date.
* UI: default filter = WZ/CP/initiated (the original product); permits as an opt-in kind chip, because 2,340
  mostly small "roboty budowlane" cases would otherwise drown the ~600 WZ datapoints. Useful facets: scope
  (`nazwa_zamierzenia_bud`), single-family vs other, category, issuer.
* **Effort**: 1.5–2 days including tests on the real ZIPs. **Risks**: (1) GUNB format drift (documented
  separator already wrong; duplicate header) → validate header on every run and fail loudly; (2) GUNB
  service outages (search UI currently in maintenance) → bulk files are separate and kept updating, and we keep
  the last good extract; (3) size growth – fine for years at +5 MB/yr; (4) no outcome column; (5) the
  zgłoszenia register is **incomplete by design** (only the categories listed in 3.1; ~20 PP cases/year) – the UI
  must say so.

---

## 4. Source C – Warsaw city WMS (legacy decision layers)

* Service: `https://wms.um.warszawa.pl/serwis` (Oracle MapViewer, WMS 1.1.1/1.3.0, `AccessConstraints: None
  whatsoever`, `Fees: None`, **`Access-Control-Allow-Origin: *`**). WFS requests just return WMS capabilities –
  no vector access. SVG output is disabled ("SVG map format is no longer supported").
* Layers (queryable, CRS EPSG:2178/2180, visible from 1:40 000): `DECYZJE_O_WARUNKACH_ZABUDOWY`
  ("Warstwa wydanych decyzji o warunkach zabudowy"), `DECYZJE_O_POZWOLENIU_NA_BUDOWE`.
* GetFeatureInfo (`INFO_FORMAT=text/xml`) attributes:
  * WZ: `DATA_WZ`, `TYP_INW` (symbol, e.g. `MN`, `MW`, `U…`, `I…`), `OPIS` (Nowa / Rozbudowa / Zm_sposob_uzytk /
    Odmowa), `ULICA`, `NR_P`, `NAZWA` (investor type: "Inw. prywatny", "Sp. z o.o." …).
  * PB: `DEC_WZ` (internal code, mostly blank), `TYP_INW`, `OPIS_RODZ_`, `NAZWA_UL`, `NR_P` – **no date, no number**.
* Sample over a 4×4 km tile of Praga-Południe: 388 WZ symbols / 372 PB symbols; 39 sampled WZ features dated
  **2008-01-18 … 2022-09-19** → looks unmaintained since ~2022.
* Verdict: no decision numbers, no source documents, raster only – not a datapoint source. Possible
  low-effort extra: an optional "historyczne decyzje (warstwa m.st. Warszawy, 2008–2022)" WMS overlay in the map
  (`L.tileLayer.wms`, EPSG:3857 is *not* advertised, so it would need proj4leaflet/EPSG:2180 or a pre-rendered
  overlay – probably not worth it for the MVP).

## 5. Checked and not useful

* **e-Budownictwo** (`e-budownictwo.gunb.gov.pl`): filing portal for investors/officials (eBudownictwo Wnioski,
  EDB, c-KOB, CEEB, e-CRUB, SNRWB…). Its only public permit data is RWDZ itself.
* **Warsaw BIP** (`bip.warszawa.pl/ogloszenia-obwieszczenia-zawiadomienia`): 85k mixed notices
  (obwieszczenia, "Karty informacyjne (środowisko)"); category/district filters are not GET-addressable (the
  page ignored them), content is HTML/PDF prose. The environmental "karty informacyjne" list some decisions with
  case signs but coverage is partial (only cases with environmental relevance). Not worth scraping.
* **dane.gov.pl, Warsaw publishers** (Urząd m.st. Warszawy, ids 7621 and 65): 22 datasets (transport, AED,
  consultations, real-estate price register…) – nothing on WZ/permits. Other cities (Zabrze, Gliwice, Dąbrowa
  Górnicza) do publish WZ/ULICP datasets there – a good argument to ask Warsaw for one.
* **District website search** (`pragapld.um.warszawa.pl/szukaj?q=pozwolenia+na+budowę`): no permit lists.
* **Geoportal "Raport o działce"**: per-parcel UI that shows RWDZ entries around a parcel; no bulk access, but
  the `identifyParcel` deep link is useful (3.5).

## 6. Recommendation and order of work

1. **BAiPP lists (Source A)** – same data types as the MVP, 104 extra Praga-Południe rows, ~1 day, low risk.
   Needs the record-id namespace (`-am-`) and the issuer field *before* first publication so permalinks stay
   stable.
2. **"Sprawdź w RWDZ / Geoportal" links for every record** – a few lines in the UI, immediate value.
3. **RWDZ permits + zgłoszenia (Source B)** – answers the owner's "building permits" ask with an official CC0
   source, ~1.5–2 days; ship as opt-in kinds with a clear "co obejmuje ten rejestr" note.
4. Optional / later: WMS historical overlay; ask Warsaw (BAiPP / Biuro Cyfryzacji) to publish the 1129/2020 lists
   on dane.gov.pl as CSV.

Monthly schedule fits all sources: district pages appear ~9th–10th of the following month, BAiPP files
~5th–12th, RWDZ nightly. A cron on the **15th** (plus manual dispatch) catches each month in one run;
RWDZ change detection is a cheap 304.

## 7. Open questions / backlog (for the lead to merge)

* 🔴 Include building permits at all, and as opt-in or default? (Proposal: opt-in kind chip.)
* 🔴 Show designer names from RWDZ? (Proposal: no.) Treat sole-proprietor trade names as personal data? (Proposal: keep, like companies.)
* 🟠 RWDZ CSV has no outcome (positive/refusal/discontinued) column; pending applications are not in the bulk files.
* 🟠 GUNB search UI is in maintenance (2026-10-22/23); the pre-filled deep-link format is reconstructed from
  Wayback captures and must be re-tested when it is back.
* 🟠 BAiPP republishes the current-year file monthly under a new URL; older monthly snapshots vanish from the page.
* 🟠 BAiPP data errors: a Praga-Północ parcel labelled "Praga Południe" (`AM-ZP-P.6730.27.2025`), a Praga-Południe
  WZ numbered `110/PRN/20`; obręb sections are not district keys (3-07-07 is Rembertów) → verify via ULDK.
* 🟠 Record-id namespace needed for BAiPP (`wz-am-…`, `ws-am-…`) to avoid collisions with district numbering.
* 🟠 `kategoria` labels come from a secondary source – verify against the Prawo budowlane annex (ISAP) before use.

## 8. How this was checked (reproducible)

* `curl -I` / conditional GETs against GUNB (`pliki_pobranie/*.zip`, `rwdz.xml`), dane.gov.pl API
  (`/1.4/datasets/3467`, `/1.4/resources/2835391`, `/1.4/search`, `/1.4/institutions/{7621,65}/datasets`),
  architektura.um.warszawa.pl pages and files, `wms.um.warszawa.pl/serwis` capabilities / GetMap / GetFeatureInfo,
  ULDK `GetParcelById` (e.g. `146509_8.0707.22/4`, `146508_8.1508.18/5`), Wayback CDX for
  `wyszukiwarka.gunb.gov.pl/*`.
* Downloaded in full (all < 50 MB): the Mazowieckie and both zgłoszenia ZIPs, all 28 BAiPP workbooks; CSVs were
  stream-parsed with Python `zipfile` + `csv`, workbooks with `openpyxl`. Throwaway scripts and downloads live in
  the session scratchpad, not in the repo.
