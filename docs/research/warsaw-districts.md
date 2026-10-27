# Research: the same sources for all 18 Warsaw districts

Status: research note, 2026-10-27. Every URL below was fetched live that day from a home connection (the district
sites answer cloud IP ranges with 403, see BACKLOG). Sample files were downloaded and opened. Throwaway scripts and
downloads lived in the session scratchpad, not in the repo. Nothing here is wired into `main`.

## What we use for Praga-Południe, and what each one becomes

| Praga-Południe source today | City-wide equivalent | Work |
|---|---|---|
| District monthly lists (WZ, ULICP, initiated proceedings), `pragapld.um.warszawa.pl/informacja-o-wszczetych-…` | **17 other district pages**, all publishing under the same Zarządzenie nr 1129/2020 Prezydenta m.st. Warszawy (same 3–4 lists). Page layout, file format and update rhythm differ per district (table below). | New crawler strategies and a PDF parser. |
| BAiPP city-wide lists, `architektura.um.warszawa.pl/postepowania-i-decyzje` + `/-/rejestry2020…25` | **The same files.** They already cover all of Warsaw (1,635 rows since Aug 2020). Today we keep only the 104 Praga-Południe rows. | Drop the filter and assign a district from the address's last line. |
| GUNB RWDZ permits + notifications, `wyszukiwarka.gunb.gov.pl/pliki_pobranie/wynik_mazowieckie.zip` + 2 zgłoszenia ZIPs | **The same three ZIPs.** Filter on the 18 Warsaw cadastral units `146502_8`…`146519_8` instead of `146507_8`. | Small change. |
| GUGiK ULDK (parcels) and UUG (addresses) | Same services, all units. | Larger first run (see sizes). |
| OSM MSI neighbourhoods + district outline (relation 2544288) | Same Overpass query for all 18 `admin_level=9` districts and their `admin_level=10` MSI areas. | Small change. |
| `pipeline/data/praga_poludnie_obreby.json` (96 precincts, from ULDK) | One precinct list per district from `scripts/pp_obreby.py`, generalised. | Small change. Needed because precinct codes like `3-07-xx` are split between districts (Rembertów/Praga-Południe). |

The BAiPP page has a box, "Informacja o wszczętych postępowaniach i wydanych decyzjach w serwisach dzielnicowych",
that links the official page of every district. That box is the authoritative entry list and the crawler can
re-check it every run. The 18 entry points below are the box's links. Where the box points to a hub page, the
second column gives the real list pages found under it.

## Summary

Kinds: **ws** = initiated WZ/ULICP proceedings (zał. 1, sometimes split into 1a WZ / 1b ULICP), **wz** = WZ decisions
(zał. 2), **cp** = ULICP decisions (zał. 3 local/gminne+powiatowe, zał. 4 national/voivodeship).
"Template" = the 1129/2020 Excel layout we already parse (header in row 4: `Lp.` · `Znak sprawy`/`Nr decyzji` ·
`data` · `Nazwa wnioskodawcy` · …). Volumes: the **GUNB column** is measured (permit cases with a decision since
2016 / notifications) from the 25 Oct 2026 ZIPs. The planning volume is a rough estimate from sample files.

| # | District | Unit | List page(s) | Format | Granularity | Since | Planning volume | GUNB pb / zg | Parser fit |
|---|---|---|---|---|---|---|---|---|---|
| 1 | Bemowo | 146502_8 | [jawnosc-procesu-inwestycyjnego](https://bemowo.um.warszawa.pl/jawnosc-procesu-inwestycyjnego) (one page) | xlsx (2020+), pdf (2018–20) | yearly, cumulative, replaced during the year | IX 2020 | medium | 1,097 / 205 | template |
| 2 | Białołęka | 146503_8 | hub [decyzje-architektoniczne](https://bialoleka.um.warszawa.pl/decyzje-architektoniczne) → [warunki-zabudowy-wnioski](https://bialoleka.um.warszawa.pl/warunki-zabudowy-wnioski), [warunki-zabudowy-decyzje](https://bialoleka.um.warszawa.pl/warunki-zabudowy-decyzje), [inwestycje-celu-publicznego-decyzje](https://bialoleka.um.warszawa.pl/inwestycje-celu-publicznego-decyzje) | **pdf** (generated report), 2019 wnioski xlsx | yearly, cumulative | 2009 (WZ 2010) | **very high** (332 WZ decisions I–IX 2026) | 4,810 / 1,134 | **PDF "system report" layout** |
| 3 | Bielany | 146504_8 | hub [architektura](https://bielany.um.warszawa.pl/architektura) → [/-/warunki_zabudowy](https://bielany.um.warszawa.pl/-/warunki_zabudowy), [/-/wszczete_postepowania](https://bielany.um.warszawa.pl/-/wszczete_postepowania), [/-/lokalizacja_inwestycji_celu_publicznego](https://bielany.um.warszawa.pl/-/lokalizacja_inwestycji_celu_publicznego) | **pdf**; xlsx "WCAG" copies only for 2021–22 | yearly, cumulative | 2014 | medium (81 WZ I–IX 2026) | 1,611 / 203 | **PDF system report** (same generator as Białołęka) |
| 4 | Mokotów | 146505_8 | [wykazy-i-informacje-o-decyzjach](https://mokotow.um.warszawa.pl/wykazy-i-informacje-o-decyzjach) (current year) + 2 archive pages: [wnioski 2018–2025](https://mokotow.um.warszawa.pl/-/archiwum-informacje-o-wnioskach-o-wydanie-decyzji-o-warunkach-zabudowy-i-zagospodarowania-terenu), [decyzje 2018–2025](https://mokotow.um.warszawa.pl/-/archiwum-informacje-o-wydanych-decyzjach-o-warunkach-zabudowy-i-zagospodarowania-terenu) | **pdf** since 2021/22; xlsx/xls 2018–2021 | monthly | 2018 | medium-high | 3,682 / 560 | PDF system report (+ template xlsx for 2020–21, old xls) |
| 5 | Ochota | 146506_8 | [warunki-zabudowy](https://ochota.um.warszawa.pl/warunki-zabudowy) | **pdf** (Excel template printed to PDF) | 3 cumulative files since 2020, replaced monthly (`…_14.09.2026.pdf`) | IX 2020 | low (mostly local plans) | 1,085 / 37 | **PDF template layout** |
| 6 | Praga-Południe | 146507_8 | already ingested | xlsx | monthly pages | VIII 2020 | 474 + 104 BAiPP | 2,340 / 225 | done |
| 7 | Praga-Północ | 146508_8 | [/-/ogloszenia-2](https://pragapn.um.warszawa.pl/-/ogloszenia-2) (one long page, 152 files) | xlsx (3 pdf in V 2021) | monthly | V 2021 | medium | 1,463 / 85 | template |
| 8 | Rembertów | 146509_8 | [/-/informacja-o-wszczetych-postepowaniach-i-wydanych-decyzjach-administracyjnych](https://rembertow.um.warszawa.pl/-/informacja-o-wszczetych-postepowaniach-i-wydanych-decyzjach-administracyjnych) (one page, 204 files) | xlsx | monthly | 2020 | low-medium | 807 / 62 | template |
| 9 | Śródmieście | 146510_8 | hub [wszczete-postepowania-i-wydane-decyzje](https://srodmiescie.um.warszawa.pl/wszczete-postepowania-i-wydane-decyzje) → [/-/wszczete-postepowania](https://srodmiescie.um.warszawa.pl/-/wszczete-postepowania), [/-/decyzje-warunki-zabudowy](https://srodmiescie.um.warszawa.pl/-/decyzje-warunki-zabudowy), [/-/decyzje-cel-publiczny-powiat](https://srodmiescie.um.warszawa.pl/-/decyzje-cel-publiczny-powiat), [/-/decyzje-cel-publiczny-kraj](https://srodmiescie.um.warszawa.pl/-/decyzje-cel-publiczny-kraj) | xlsx | monthly (link text = month only, year from filename `09_DECYZJE_WZ_2026.xlsx`) | IX 2020 | medium | 4,091 / 70 | template (2020 = old 2-row header, already handled for PP) |
| 10 | Targówek | 146511_8 | [/-/warunki-zabudowy-postepowania-decyzje](https://targowek.um.warszawa.pl/-/warunki-zabudowy-postepowania-decyzje) | **pdf** (Excel template printed) | yearly, cumulative, replaced every few months (2026 file "czerwiec") | 2021 | medium | 1,698 / 160 | PDF template layout |
| 11 | Ursus | 146512_8 | hub [decyzje-architektoniczne](https://ursus.um.warszawa.pl/decyzje-architektoniczne) → `wykazy-za-rok-2019` … [`/waw/ursus/wykazy-za-rok-2026`](https://ursus.um.warszawa.pl/waw/ursus/wykazy-za-rok-2026) (one page per year) | xlsx | yearly, cumulative | 2019 | medium | 957 / 213 | **own register layout** (not the template; headers do not match the contents, see below) |
| 12 | Ursynów | 146513_8 | [/-/rejestr-wnioskow-decyzji](https://ursynow.um.warszawa.pl/-/rejestr-wnioskow-decyzji) (one page, 212 files) | xlsx (+ csv copies in 2021) | monthly | 2021 (`1129_1009zal*_2021`) | medium-high | 1,887 / 269 | template |
| 13 | Wawer | 146514_8 | [dokumenty-budowlane](https://wawer.um.warszawa.pl/dokumenty-budowlane) (one page) | xlsx (2026 monthly); **zip of 12 monthly xlsx** per year 2021–25; xlsx 2020; pdf 2019 | monthly | 2019 | **high** (58 initiated in I 2026 alone) | 5,730 / 589 | template, plus unzip |
| 14 | Wesoła | 146515_8 | hub [architektura](https://wesola.um.warszawa.pl/architektura) → [wszczęte](https://wesola.um.warszawa.pl/-/informacje-o-wszczetych-postepowaniach-o-warunkach-zabudowy), [WZ](https://wesola.um.warszawa.pl/-/informacje-o-wydanych-decyzjach-w-sprawie-warunkow-zabudowy), [CP](https://wesola.um.warszawa.pl/-/informacje-o-wydanych-decyzjach) | xlsx | monthly | IX 2020 | low-medium | 1,423 / 158 | template (precinct written as `07-07 dz. 6/25`, zone digit dropped) |
| 15 | Wilanów | 146516_8 | hub [/-/nowe-procedury-…](https://wilanow.um.warszawa.pl/-/nowe-procedury-zwiazane-z-jawnoscia-procesu-inwestycyjnego) → [/-/informacje-o-wszczetych-postepowaniach-oraz-wydanych-decyzjach](https://wilanow.um.warszawa.pl/-/informacje-o-wszczetych-postepowaniach-oraz-wydanych-decyzjach) | xlsx **and** pdf of the same 4 files | 4 cumulative files since 2020 (zał. 1a, 1b, 2, 3), "2020 rok" separator rows | IX 2020 | medium-high (1,446 rows since 2020) | 2,077 / 332 | template (+ skip year-separator rows) |
| 16 | Włochy | 146517_8 | hub [architektura](https://wlochy.um.warszawa.pl/architektura) → [decyzje-architektoniczne](https://wlochy.um.warszawa.pl/decyzje-architektoniczne) → [warunki-zabudowy-wnioski](https://wlochy.um.warszawa.pl/warunki-zabudowy-wnioski), [warunki-zabudowy-decyzje](https://wlochy.um.warszawa.pl/warunki-zabudowy-decyzje), [inwestycje-celu-publicznego-decyzje](https://wlochy.um.warszawa.pl/inwestycje-celu-publicznego-decyzje) | **pdf** | yearly to 2025, then I–IV + monthly 2026; WZ refusals in separate files | 2010 (wnioski IX 2020) | low-medium | 907 / 77 | PDF template layout |
| 17 | Wola | 146518_8 | hub [wykazy-i-informacje-o-decyzjach](https://wola.um.warszawa.pl/wykazy-i-informacje-o-decyzjach) → [wnioski](https://wola.um.warszawa.pl/waw/wola/-/wnioski-o-wydanie-decyzji-urbanistycznych), [decyzje WZ](https://wola.um.warszawa.pl/waw/wola/-/decyzje-o-warunkach-zabudowy), [decyzje CP](https://wola.um.warszawa.pl/waw/wola/-/decyzje-o-ustaleniu-lokalizacji-inwestycji-celu-publicznego) | xlsx registers (yearly, cumulative) **plus the anonymised text of every decision** (docx/pdf, 373 + 93 files) | yearly register; one document per decision | 2019 | medium | 1,969 / 141 | template (+ match decision documents by number) |
| 18 | Żoliborz | 146519_8 | [/-/informacja-o-wszczetych-postepowaniach-oraz-wydanych-decyzjach-administracyjnych-1](https://zoliborz.um.warszawa.pl/-/informacja-o-wszczetych-postepowaniach-oraz-wydanych-decyzjach-administracyjnych-1) | xlsx (2021+), ods (2015–2020) | 2-monthly / half-yearly | 2015 | very low (mostly local plans) | 704 / 40 | template; **stale since VI 2024** (see 📮) |
| – | BAiPP (all districts) | – | already ingested | xlsx | yearly + current year | VIII 2020 | 1,635 rows total | – | done (drop filter) |
| – | GUNB RWDZ (all units) | 18 units | already ingested | csv in zip | nightly | 2016 | – | **38,352 / 4,560** | done (widen unit filter) |

Totals: 11 districts publish **xlsx** that follow the template (Bemowo, Praga-Północ, Rembertów, Śródmieście,
Ursynów, Wawer, Wesoła, Wilanów, Wola, Żoliborz, plus Praga-Południe), 1 publishes xlsx in its **own register layout**
(Ursus), and **6 publish only PDF** for recent years (Białołęka, Bielany, Mokotów, Ochota, Targówek, Włochy). The
PDFs are text PDFs exported from Excel or from the case system (`pdftotext -layout` gives clean text, no OCR needed),
but tables are only recoverable from word positions.

## Expected data volume (for the plan)

| | Praga-Południe today | All of Warsaw (estimate) | Factor |
|---|---:|---:|---:|
| Planning records (WZ/CP/ws, since 2020) | 578 | 15,000–25,000 (Białołęka and Wawer alone ≈ 1,000/yr each) | ×25–40 |
| Permit cases (GUNB, since 2016) | 2,340 | 38,352 | ×16 |
| Notifications (GUNB) | 225 | 4,560 | ×20 |
| `records.json` + `permits.json` (raw / gzip) | 8.1 MB / ~1 MB | ~150 MB / ~20 MB if built the same way | – |
| Source files mirrored (`site/sources`) | 4.9 MB (+2 MB RWDZ) | ~60–90 MB of xlsx/pdf, more with yearly re-uploads | – |
| Unique parcels to geocode (ULDK, 2 req/s) | ~5,000 | ~60,000 (measured after the draft's crawl; Wawer 11,200, Białołęka 9,500) → **~8–10 h first run**, minutes per month afterwards | – |

By field, 30 % of `records.json` and 47 % of `permits.json` is `sources[].raw`, the "as in source" cells. Only the
detail view needs it.

## Per-district notes

Each block: how to crawl, what the files look like, pitfalls, source problems worth raising (📮).

### 1. Bemowo (`146502_8`)
* One Liferay page with 29 attachments. 2020+ xlsx (template, sheet names `Tabela licp 1` / `Rok`), 2018–2020 decisions
  as PDF (pre-1129 period, can be skipped like PP's pre-VIII-2020).
* Files are **yearly cumulative**: "stan na 31 grudnia 2023 r." for closed years, the current year's file is replaced
  in place. Numbers `1/BEM/WZ/2024`, `1/BEM/CP/2026/U` (outcome suffix as BAiPP: `/O /U /P /W`). Case signs
  `UD-I-WAB-B.6730.82.2025.KBO`. Parcels `dz. 5/40 z ob. 6-11-10`.
* 📮 The link labelled "Informacja o wydanych decyzjach w sprawie warunków zabudowy **2026**" points to
  `…warunków zabudowy 2024.xlsx` (2024 decisions only), and a "Rejestr decyzji o warunkach zabudowy" link further down
  opens a CP file, so the 2026 WZ decisions are effectively not published. Kind and period must come from the file's
  contents, never from the link text.

### 2. Białołęka (`146503_8`)
* Hub page → 3 list pages (wnioski WZ, decyzje WZ, decyzje CP) + "Pozwolenia na budowę – decyzje" + "Decyzje ZRID".
  No separate CP-initiated list (the WZ "wnioski" PDF may include CP; to verify).
* **PDF only** since 2020 (2019 wnioski = xlsx). One cumulative PDF per year, replaced monthly (`Decyzje WZ (3).pdf`).
  Large: 2026 WZ = 43 pages, 332 decisions in nine months, the biggest WZ volume in Warsaw (single-family housing).
* Layout = **case-system report** ("Decyzje o Warunkach Zabudowy wydane: 2026"): columns `Nr decyzji i data jej
  wydania (rrrr mm dd)` · `Rodzaj inwestycji` · `Nazwa i adres wnioskodawcy` · `Oznaczenie nieruchomości` (precinct ¬
  parcels ¬ street, `¬` as the line separator) · `Streszczenie ustaleń decyzji` · `Wygaśnięcie, stwierdzenie
  nieważności lub zmiana decyzji` · `Uwagi`. The **outcome is stated** under the number ("Pozytywna", "Umarzająca",
  "Odmowna"), which is better than the template.
* The extra "Pozwolenia na budowę – decyzje" list overlaps GUNB. Not needed.

### 3. Bielany (`146504_8`)
* Hub → 3 list pages. **Same case-system PDF report** as Białołęka and Mokotów ("wydane: 2026-01-01~2026-09-30").
  Accessible xlsx copies ("wersja zgodna z WCAG 2.1") exist only for 2021–2022.
* Yearly cumulative, replaced in place, with a date prefix in the filename (`7.01.2026 Rejestr …`). Older years
  split into "…" and "… – pozostałe". The CP "wnioski" list exists for 2024 and 2026 only.

### 4. Mokotów (`146505_8`)
* Current page (2026, 31 monthly PDFs) + two archive pages (2018–2025). **Monthly PDFs since 2021/2022**. Before that:
  monthly xlsx (2020–21, template) and yearly xls registers (2018, 2019, old `.xls` = needs `xlrd` or LibreOffice).
* PDF = case-system report like Bielany ("Informacja o wydanych decyzjach o Warunkach Zabudowy 2026-09"), with
  outcome under the number ("Umarzająca", "Odmowna"). Wnioski split into "WZ i WZ70" and "CP".
* 📮 Filenames mislabelled: `rejestr decyzji WZ_07_2027.pdf` for July 2026; the September 2025 "wz"/"cp" wnioski links
  are swapped (the "wz" link opens the CP file).

### 5. Ochota (`146506_8`)
* One page, **3 PDFs** (zał. 1a wnioski, zał. 2 WZ, zał. 3 CP), each **cumulative since 2020** with "ROK 2020"
  separator rows, replaced monthly (`WZ_zal2_14.09.2026a.pdf`). Old versions vanish, so keep every snapshot like BAiPP.
* Layout = the Excel template printed to PDF (two-row header "Nr decyzji i data jej wydania › nr / data").
  `LICP_zal3.14.09.2026.xlsx.pdf` suggests an xlsx exists. Asking the office to publish it is cheaper than PDF parsing.
* 📮 Header cell prints a date `1900-01-03` in the numbering row ("3" formatted as a date). Few WZ: Ochota is almost
  fully covered by local plans.

### 6. Praga-Południe (`146507_8`)
Already ingested; see `docs/research/building-permits.md` and BACKLOG.

### 7. Praga-Północ (`146508_8`)
* One "Ogłoszenia" page with 152 attachments (all months on one page, no pagination seen). Template xlsx since
  V 2021. Sheet title rows name "Zarząd Dzielnicy Praga-Północ". Numbers `20/PPN/WZ/2026`, case signs
  `UD-VII-WAB-U.6730.12.2026.AZU`. Parcels `11/26, 11/20, 4-18-09`.
* 📮 No lists for IX 2020 – IV 2021 on the page. Filenames like `listopad wz 2024 — kopia.xlsx` / `… pop.xlsx`
  (corrected versions?). Use the file's own title for kind and period.

### 8. Rembertów (`146509_8`)
* One page, 204 xlsx (monthly; link text = month only, year from the section heading / filename
  `…_01_2026_rembertow.xlsx`). Template. Case signs `UD-VIII-WAU.6733.1.2026.KRO`. Parcels
  `5/2, 4 (cz.) w obrębie 3-09-07`. Precinct sections `3-07-07`, `3-08-…`, `3-09-…` (zone 3 is shared with
  Praga-Południe and Wawer).
* Many `Kopia …` / `— kopia (3) — kopia.xlsx` names. Also an empty CP month means no file, not a "0" file.

### 9. Śródmieście (`146510_8`)
* Hub → 4 pages (ws, WZ, CP local, CP national). Monthly xlsx since IX 2020, ~72 per kind. Link text is only the
  month ("wrzesień (plik xlsx 22 KB)"); the year is in the filename and in the page's year headings.
* 2020 files use the old 2-row header (`Nr decyzji i data jej wydania`, merged), which the PP parser handles.
  Template since 2021. Address `Elektoralna 13, 13A; Śródmieście`, parcels `18/1, 18/3; 5-03-03`.
* Volume: GUNB has 4,091 permit cases (many small works in old buildings) but few WZ (local plans).

### 10. Targówek (`146511_8`)
* One page, 18 PDFs = 3 per year 2021–2026 (yearly cumulative, the current file replaced every few months: the
  2026 WZ file is "czerwiec" and holds I–V). Excel template printed to PDF. Case signs `…6730.10…`.
* 📮 Publication lag: on 27 Oct 2026 the 2026 files end in May/June.

### 11. Ursus (`146512_8`)
* Hub → one page per year (`wykazy-za-rok-2019` … `2026`; the 2026 page lives under `/waw/ursus/`). Each year: up to
  8 xlsx registers: WZ applications, WZ decisions, CP applications, CP decisions, ZRID, **PnB applications, PnB
  decisions, zgłoszenia**.
* **Own layout**, not the template, and the headers are copied between registers without being adapted: the WZ
  decisions sheet's column 2 is labelled "Data wpływu wniosku" but holds `2/URS/WZ/2026/O z dnia 09.01.2026`; extra
  columns are "Kolumna6…10"; outcome in words ("odmawiam", "umarzam"). Needs a dedicated layout map per register
  (by sheet name: `rejestr decyzji wz`, `rejestr wniosków wz`, `rejestr cp`, `rejestr lcp`). The "wnioski" registers are
  applications by filing date, the closest thing to "wszczęte postępowania".
* 📮 Ursus does not publish the 1129/2020 information in its prescribed form. Its PnB/zgłoszenia registers have
  outcomes (useful to cross-check GUNB, out of scope).

### 12. Ursynów (`146513_8`)
* One page, 212 files: monthly template xlsx since 2021 (`Wszczęte postępowania 09.2026.xlsx`, `Wydane decyzje WZ
  09.2026.xlsx`, `Wydane decyzje ULICP …`), 2021 also as `1129_1009zal1_2021.xlsx` and 14 CSV copies (skip; same data).
  Case signs without the office prefix (`6733.9.2026`). Parcels `dz. 10/2, część 12/3 obr. 1-09-79`.

### 13. Wawer (`146514_8`)
* One page. 2026: 4 monthly xlsx (ws, WZ, CP, **and PnB**). 2021–2025: one **zip per kind per year** containing the 12
  monthly xlsx (`1. decyzje_WZ_01_2025_1129_1009zal2.xlsx` …). 2020: yearly xlsx. 2019: PDF.
* Template, but sheet title rows hold the month (`styczeń 2026`) and headers are simplified ("Nr decyzji", "data
  wydania", "Oznaczenie nieruchomości" twice). Positional fallback needed for the two "Oznaczenie nieruchomości"
  columns (address vs parcels). Precinct `3-12-100` (3-digit precinct numbers exist).
* High volume (single-family housing, like Białołęka).

### 14. Wesoła (`146515_8`)
* Hub → 3 pages, monthly template xlsx since IX 2020 (first file covers IX 2020 – I 2021).
* 📮 Pages mix kinds: the "wszczęte" page links a WZ-decision file (`2 wz dec. wrzesień 2026.xlsx`), the WZ page links
  `3 decyzje icp marzec 2026`. Kind must come from file contents (our parser already does that).
* Precinct written without the zone digit: ` 07-07 dz. 6/25 `, `03-03 dz. 142`. Needs the zone (8 = Wesoła) added.
* Address `Armii Krajowej;Wesoła`.

### 15. Wilanów (`146516_8`)
* Hub page → one list page with **4 cumulative xlsx (+ identical PDFs)** since 2020: zał. 1a (WZ initiated, 870
  rows), 1b (CP initiated, 136), 2 (WZ decisions, 322), 3 (CP decisions, 118). Year separator rows ("2020 rok")
  between blocks need to be skipped like note rows. Replaced in place, so keep snapshots.
* Also on the hub: "Informacje o złożonych wnioskach oraz wydanych decyzjach o pozwoleniu na budowę" and
  "Informacje o zgłoszeniach budowy" (GUNB covers these).

### 16. Włochy (`146517_8`)
* Hub → 3 list pages + PnB decisions + zgłoszenia. **PDF only**, Excel template printed ("ulica, Dzielnica Włochy" ·
  "nr działki, obręb"). Yearly cumulative to 2025, then "I–IV 2026", "05 2026", "VI 2026", "VII 2026". **WZ refusals
  are in separate files** ("REJESTR DECYZJI WZ – ODMOWY …"), so the outcome comes from the file.
* 📮 The link "Rejestr decyzji CP I-VIII 2020" opens `REJESTR DECYZJI WZ I_IV 2026 r.pdf`. Filenames do not always
  match their labels (`…I-VI 2025` labelled I–XII 2025).

### 17. Wola (`146518_8`)
* Hub → wnioski page (yearly WZ+CP register, xlsx, filename = upload date `24.09.26.WZ i CP 2026.xlsx`), WZ page,
  CP page. Registers are template xlsx (2020 part 2 + CP 2020 use the old 2-row header). Numbers `1/WOL/WZ/2024/U`,
  older `1/U/um/2019/wz` (letters = outcome: `um` umorzenie, `o` odmowa, `w` wygaśnięcie, `z` zmiana).
* **Unique: the anonymised full text of every decision** (373 WZ + 93 CP documents, docx/pdf, plus "analiza"
  urban-analysis attachments), linked as "19/WOL/WZ/2026, ul. Chmielna 102". Matching them by decision number to our
  records gives a "Treść decyzji" link. That is a strong "sources matter" feature, and a good example to show other
  offices.
* Also: PnB decisions 2019–2023 and 2024+, demolitions, zgłoszenia decisions. GUNB covers these.

### 18. Żoliborz (`146519_8`)
* One page; 2-monthly/half-yearly template xlsx 2021–VI 2024 (`WZ i cp wydane decyzje styczeń-czerwiec 2024.xlsx`),
  `.ods` registers 2015–2020 (needs an ODS reader). Empty periods are files whose rows say `brak` (skip like
  template rows).
* 📮 **Stale**: the page says no WZ decision was issued "od lipca 2024 r. do kwietnia 2025 r." and nothing after that
  is published (27 Oct 2026). Initiated-proceedings lists stop at 2023. The page also says building notifications are
  on BIP (`bip.warszawa.pl/Menu_przedmiotowe/ogloszenia/zgloszenia_budowy`).

## City-level sources (unchanged, wider filter)

### BAiPP (`architektura.um.warszawa.pl`)
* 1,635 rows since VIII 2020, all districts. District = last line of the address cell ("Praga Południe", "Bielany",
  "Wola" …), cross-checked with the district code in numbers (`/AM/BIE/WZ/`, `/AM/PPD/`) and the planning unit in case
  signs (`AM-ZP-P` Praga, `ZP-E` east, `ZP-N` …) and, finally, ULDK (as today for Praga-Południe).
* 📮 Duplicate numbers across districts in the city-wide numbering (`33/AM/BIE/WZ/2025/P` and `33/AM/PPD/WZ/2025/P`).
  Record ids must include the district for non-Praga-Południe rows (see plan).

### GUNB RWDZ
* Same three ZIPs. 38,352 permit cases + 2,493 (2016–21) + 2,067 (2022+) notifications located in the 18 Warsaw units.
  A handful of rows carry other `1465xx_8` units (typos, 6 cases with the city-level `146501_8`). The typo rules and
  `UNIT_FIXES` generalise from "near 146507_8" to "near any Warsaw unit".
* Byte-exact extracts grow from 2 MB to ~30 MB. Split them per district so monthly diffs stay local.

### ULDK / UUG / OSM
* Parcel ids: `<unit>.<SSOO>.<number>`. The 4-digit precinct code drops the zone digit, and a zone is shared by 1–3
  districts (`OBREB_ZONES` in `pipeline/baipp.py`), so the unit of a parcel needs the per-district precinct lists
  (generalise `scripts/pp_obreby.py`).
* MSI neighbourhoods: OSM has `admin_level=10` areas for every district (e.g. Kamionek, Gocław). One Overpass query for
  the city relation (Warszawa, `admin_level=6`) and its 18 `admin_level=9` districts.

## Optional extras found on the way (not equivalents, not in the plan's first phases)

* District PnB / zgłoszenia lists with **outcomes** (Ursus, Wawer, Białołęka, Wola, Wilanów, Włochy). GUNB lacks the
  outcome column, so these could later fill `outcome` for permits in those districts.
* Wola's decision texts and urban analyses (see 17).
* ZRID (road-permit) registers (Ursus, Białołęka): another decision type.
* Pre-2020 registers (Białołęka from 2009, Włochy 2010, Bielany 2014, Żoliborz 2015, Mokotów 2018). They predate the
  1129/2020 template, so different formats.

## 📮 Source problems worth raising (new, beyond BACKLOG §2)

* Six districts publish the 1129/2020 information only as PDF (Białołęka, Bielany, Mokotów, Ochota, Targówek, Włochy),
  although the template is an Excel file and BAiPP/most districts publish xlsx. The zarządzenie's appendix is a
  spreadsheet; asking for the xlsx alongside the PDF (as Wilanów and Bielany 2021–22 do) is the cheapest fix.
* Ursus uses its own register layout with mislabelled headers.
* Żoliborz has published nothing since mid-2024. Praga-Północ starts in V 2021. Targówek lags 4–5 months.
* Mislinked files (Bemowo 2026 WZ → 2024 file, Włochy CP 2020 → WZ 2026, Mokotów Sep 2025 wz/cp swapped, Wesoła
  kinds mixed between pages).
* Nobody publishes these lists on dane.gov.pl. A single city-wide open-data feed of the 1129/2020 lists would replace
  19 scrapers.
