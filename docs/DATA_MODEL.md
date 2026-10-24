# Data model & module contracts

This is the coordination contract between the pipeline stages (`pipeline/*.py`)
and the static frontend (`site/`). All modules must conform. If a stage needs to
deviate, it must document the deviation here.

## Source structure (as observed 2026-10-23)

* Index: `https://pragapld.um.warszawa.pl/informacja-o-wszczetych-postepowaniach-oraz-wydanych-decyzjach-administracyjnych?_AssetPublisher_nS01Fh02AyOr_cur=N`
  (N = 1..19, 4 monthly pages per index page, "Następna" link exists while more pages remain).
  Each item: `<a href="https://pragapld.um.warszawa.pl/-/<slug>" ... class="event__link ..." title="Lipiec 2026">`
  followed by `<p class="event__excerpt cut-text">…summary…</p>`.
* Monthly page (73 of them, Aug 2020 → Sep 2026): article body inside `journal-content-article`,
  optional `<time datetime="2026-08-10T08:32:00Z">` (publication date), and `<li>`/`<p>` blocks like
  `Wydane decyzje o warunkach zabudowy: <a href="/documents/50051/165304801/wydane+decyzje+wz+-++lipiec+2026.xlsx/a1c72448-...?t=1786350734551">3 pozycje</a>`.
  The text of the block gives the **category** and the **declared row count** ("3 pozycje", "0 pozycji", "BRAK").
  A block may contain >1 link (e.g. Oct 2025 WZ block links both the Sep and Oct files); one file can be linked
  from several pages. 178 links / 176 unique files total (Oct 2022 has an invisible extra link to the Sep 2022 CP file).
* Period of a monthly page = parsed from its **title** ("Grudzień 2021 r." → `2021-12`), NOT the slug
  (slug `styczen-2022-r` is titled "Grudzień 2021 r.").
* Excel files: 6 header layouts (see `tests/fixtures/xlsx/`). New layout (2025+): header row
  `Lp | Numer decyzji | Data wydania decyzji | Nazwa wnioskodawcy | Adres inwestycji | Oznaczenie nieruchomości | Streszczenie`,
  then a numbering row `1..7`, then data. Old layout (2020–2024): column A empty, 2-row header with merged cells
  (`Nr decyzji i data jej wydania` → sub-columns `nr`, `data`; `Oznaczenie nieruchomości (ulica, dzielnica, nr działki ew., obręb)`
  → sub-columns `ulica, dzielnica`, `nr dz. ew., obręb`). Column order differs between WZ and CP layouts.
  Cells often contain `\n` or long runs of spaces as separators ("Kamionkowska 29        Praga-Południe",
  "49          3-02-06", "dz. 46/4\n3-01-24").

## Identifiers

* `file_id` = first 10 hex chars of `sha1(document_path)` where `document_path` is the HTML-unescaped `href`
  **without** the query string, exactly as it appears in the page (still URL-encoded), e.g.
  `/documents/50051/165304801/wydane+decyzje+wz+-++lipiec+2026.xlsx/a1c72448-169b-c0ca-59b6-70e2da95d18a`.
* `page_id` = the slug after `/-/` in the monthly page URL (e.g. `informacje-o-wszczetych-postepowaniach-07-2026`).
* `kind`: `wz` = decyzja o warunkach zabudowy; `cp` = decyzja o ustaleniu lokalizacji inwestycji celu publicznego
  (ULICP); `ws` = wszczęte postępowanie (initiated proceeding, WZ or CP).
* Record `id` (stable across rebuilds, URL-safe, used in permalinks):
  * `wz`/`cp`: `<kind>-<year>-<seq>` from the decision number (`15/PPD/WZ/2026` → `wz-2026-15`;
    `18/WZ/PPd/20` → `wz-2020-18`; `19/WZ/PPD` (no year) → year from the decision date, plus a warning).
  * `ws`: `ws-<jrwa>-<year>-<seq>` from the case sign (`UD-VI-WAB-U.6730.29.2026.AKU` → `ws-6730-2026-29`).
  * Fallback when the number is unparseable: `<kind>-f<file_id>-r<excel_row>`.
  * Collision with different content → suffix `-2`, `-3`… and a warning on both.
* Parcel id (ULDK / TERYT format): `146507_8.<obreb4>.<number>` where Praga-Południe TERYT = `146507_8` and obręb
  `3-01-24` → `0124` (drop the leading `3-`, remove dashes). Example `146507_8.0124.46/4`.
  Verified live: `https://uldk.gugik.gov.pl/?request=GetParcelById&id=146507_8.0124.46/4&result=id,geom_wkt&srid=4326`.

## `data/manifest.json` (written by `pipeline/crawl.py`)

```jsonc
{
  "generated_at": "2026-10-23T00:00:00Z",
  "index_url": "https://pragapld.um.warszawa.pl/informacja-o-wszczetych-postepowaniach-oraz-wydanych-decyzjach-administracyjnych",
  "pages": [{
    "page_id": "informacje-o-wszczetych-postepowaniach-07-2026",
    "url": "https://pragapld.um.warszawa.pl/-/informacje-o-wszczetych-postepowaniach-07-2026",
    "title": "Lipiec 2026",
    "period": "2026-07",
    "published_at": "2026-08-10T08:32:00Z",      // null when the page has no <time>
    "summary": "Wydane decyzje o warunkach zabudowy: 3 pozycje …",   // index excerpt
    "index_page": 1,
    "blocks": [{                                   // one per <li>/<p> in the article body that has text
      "text": "Wydane decyzje o warunkach zabudowy: 3 pozycje",
      "category": "wz",                            // wz | cp | ws | null (from block text)
      "declared_count": 3,                         // int | null ("BRAK" → 0)
      "file_ids": ["a1b2c3d4e5"]
    }],
    "warnings": ["Plik „…wrzesień 2025.xlsx” dotyczy innego miesiąca (2025-09) niż strona (2025-10)."],  // Polish, may be []
    "removed_from_source_at": "2026-11-05"        // OPTIONAL: page no longer listed in the index (kept from the previous manifest)
  }],
  "files": [{
    "file_id": "a1b2c3d4e5",
    "url": "https://pragapld.um.warszawa.pl/documents/…/…xlsx/<uuid>?t=1786350734551",   // full URL incl. ?t=
    "document_path": "/documents/…/<uuid>",
    "filename": "wydane decyzje wz -  lipiec 2026.xlsx",  // URL-decoded, '+' → ' '
    "ext": "xlsx",                                  // lower-case extension of filename ("bin" if none)
    "category": "wz",                               // from the linking block (first page wins); may be null
    "period": "2026-07",                            // period of the first (= oldest) linking page
    "page_ids": ["informacje-o-wszczetych-postepowaniach-07-2026"],   // oldest page first
    "local_path": "data/raw/a1b2c3d4e5.xlsx",       // data/raw/<file_id>.<ext>, project-relative
    "sha256": "…", "size": 12345,                   // null if the file is not available locally
    "downloaded_at": "…", "last_modified": "…",    // HTTP Last-Modified (ISO UTC); for files not downloaded by us
                                                    // derived from ?t= (Liferay ms timestamp, verified equal to Last-Modified)
    "history": [{                                   // earlier versions replaced by a re-download; usually []
      "url": "…?t=<old>", "sha256": "…", "downloaded_at": "…",
      "archived_path": "data/raw/history/a1b2c3d4e5-<sha12>.xlsx"   // only when the bytes changed
    }],
    "error": "HTTPError: 503 …"                     // OPTIONAL: last download attempt failed
  }]
}
```

Crawler rules (`pipeline/crawl.py`, extensions to the original contract are marked *ext*):

* *ext:* **index links** (monthly pages and "Następna") count only as http(s) links on `um.warszawa.pl` or a
  subdomain; they are stored normalised (`urlsplit`/`urlunsplit`, which drops TAB/CR/LF), anything else is skipped with
  a log warning – a `javascript:` link (also one hidden with a TAB entity) never reaches `sources.json`.

* **Blocks** are the `<li>`/`<p>` (any block element) of `.journal-content-article .article-description`.
  *ext:* a `<p>` that packs several categories into `<br>`-separated lines (May 2023) is split into one block
  per categorised line. Every `<a href>` to `/documents/…` on a `*.um.warszawa.pl` host counts, relative or
  absolute, even if its text is empty (Oct 2022 links the Sep 2022 CP file through an invisible `&nbsp;` link).
  A block may therefore link several files.
* **category**: `ws` if the text mentions *wszczęte postępowania* (wins, because those headings name both
  procedures), else `cp` for *celu publicznego* / `CP`, else `wz` for *warunki zabudowy* / `WZ`.
* **declared_count**: the number before `poz…` (`3 pozycje`, `5 pozcji`, `1 Pozycja`); `brak`/`BRAK` → 0; two
  different numbers → null; no number → null (all Aug–Oct 2020 blocks).
  Blocks declaring 0 entries may still link a file — those files are empty templates (headers + `Lp` 1..N rows only).
* **published_at** comes only from the `<time datetime>` inside the article (null for Aug 2020 – Feb 2021).
* **files[].url** is the link with the highest `?t=` seen on any page; **category/period** come from the oldest
  linking page (the original publication), e.g. the Sep 2025 WZ file is also linked from the Oct 2025 page.
* **pages[].warnings** (*ext*) are human-readable Polish notes about source anomalies (block linking several
  files, file named after another month, file name suggesting another category, declared entries but no file,
  0 declared but a file, unparseable title, links outside `/documents/`). Safe to show in the UI as-is.
* **Incremental downloads**: an existing `data/raw/<file_id>.<ext>` is kept when the previous manifest has the
  same URL (incl. `?t=`) and sha256; adopted (hashed, not downloaded) when there is no previous entry;
  re-downloaded when missing, when `?t=` changed (old version appended to `history`, old bytes copied to
  `data/raw/history/` if they differ), or with `--refresh`. Downloads are validated (zip magic, and for zip-based
  formats such as .xlsx the whole archive – every member's CRC) and written atomically; a failed or broken download
  keeps the previous copy *and* its metadata (old `url` incl. `?t=`, so the new version is tried again next time)
  plus `error`. Pages that fail to load or disappear from the index are kept from the previous manifest; so is a
  page that loads but lists no file although it did before, under a title that is not the index's month (a
  maintenance / error page): page warning, and its id goes to the *ext* top-level **`stale_pages`** (only present
  when non-empty), which makes the build exit with code 3.
* **Ordering** (deterministic): pages newest period first; files by `period` desc, then `filename`, then `file_id`.

## Parser output (`pipeline/parse.py`)

`parse_workbook(path) -> ParsedFile` (plain dicts):

```jsonc
{
  "kind": "wz",                       // detected from title/header text: wz | cp | ws | null
  "title": "Informacja o wydanych decyzjach w sprawie warunków zabudowy",
  "period_label": "Lipiec 2026",      // as printed in the file, if any
  "layout": "new-wz",                 // layout id (for diagnostics)
  "rows": [{
    "sheet": "Decyzje o warunkach zabudowy",
    "row": 6,                         // 1-based Excel row number
    "cells": {                        // canonical fields, raw values (str | datetime | int | None)
      "lp": 1, "number": "15/PPD/WZ/2026\n", "date": "09.07.2026r.", "applicant": "osoba fizyczna ",
      "investment": "budowa budynku …", "address": "Marokańska\nPraga-Południe\n", "parcels": "dz. 46/4\n3-01-24"
    },
    "raw": [["Lp", 1], ["Numer decyzji", "15/PPD/WZ/2026\n"], …],  // [header label as printed, value] in column order;
                                                                   // datetimes serialised ISO; for 2-row headers label = "parent › child"
    "warnings": []                    // ext: row-level notes, e.g. a value in a column that maps to no field
  }],
  "sheets": [{"name": "ROK", "max_row": 12, "header_row": 4, "kind": "wz", "layout": "old-wz", "rows": 3}],  // ext
  "skipped": [{"sheet": "ROK", "row": 10, "reason": "tylko numer Lp"}],   // ext: template rows (pre-printed Lp only)
  "warnings": ["…"]                   // file-level, Polish (unrecognised column, missing header, mixed kinds …)
}
```

Parser rules (*ext* = beyond the original contract):

* Layout ids: `old-wz`, `old-cp`, `old-ws` (2020–2024 "Załącznik nr 1/2/3" sheets, header on row 4, empty column A,
  2-row merged headers for wz/cp), `new-wz`, `new-cp`, `new-ws` (2025+, header on row 4, column A = Lp).
* The header row is the first row (within 40) with an `Lp`/`Lp.` cell and ≥3 text cells. Kind comes from the
  title rows above it (`wszczęt…` → ws first, then *celu publicznego* → cp, then *warunków zabudowy* → wz), else
  the sheet name, else the headers. Column → field mapping is by header text only (`classify_header`); the 2025+
  CP header "Streszczenie ustaleń decyzji\nulica, dzielnica" maps to `investment`.
* Rows with nothing but the pre-printed Lp number are template padding → `skipped`, not rows, not warnings.
  Every other non-blank row becomes a row (also when some fields are empty). Values in unlabelled/unmapped
  columns stay in `raw` and add a row warning; sheets with content but no header are emitted cell-by-cell with
  a warning. Whitespace-only cells count as empty.

`normalize_row(row, kind, file_meta) -> Record` (without `geo`, `related`, `area`); `file_meta` =
`{"file_id", "page_id", "period"}` (period of the oldest linking page). `kind` is the ParsedFile kind; when it is
null the row's kind is inferred from its number (with a warning).

Normaliser rules (`pipeline/normalize.py`; Record fields beyond the `records.json` schema below are marked *ext*):

* `number`: as printed with **all** whitespace removed (signs are wrapped/padded in the files, e.g.
  `"UD-VI-WAB-\nU.6730.36.2026.AZM"` → `UD-VI-WAB-U.6730.36.2026.AZM`).
* `id`: per *Identifiers*. Typo `730`/`733` in a case sign is read as `6730`/`6733` (warning). Two-digit years are
  expanded (`/20` → 2020). Number year ≠ date year → warning (id keeps the number's year).
* `date`: datetime cells or strings `09.07.2026r.`, `2020.09.23`, `24.07.2026 r.`, `2021-01-08.`, `22.06.2023R.`;
  warning when unparseable or more than 62 days outside the file's period month. `date_raw` = cell text (ISO for
  datetime cells).
* `applicant`: single-spaced, wording as printed, privacy-redacted. `applicant_type` = `person` when it starts with
  "osoba/osoby fizyczna/-e" in any case/spacing (incl. redacted names), else `organization`; `unknown` if empty.
  Sole-proprietorship business names that contain a person's name ("MJS Studio Michał Spisak") are kept.
* `investment`: single-spaced, privacy-redacted, wording kept (typos included).
* `address` (*ext* keys `parts`, `approximate`): district/city suffixes ("Praga-Południe", "Praga Południe",
  "Praga-Poludnie", "Praga- Południe", "Praga-Południw", "Praga Płd.", "Warszawa") removed; `street` is the first
  street without "ul."/"al." (known misspellings fixed with a warning, e.g. Chdakowska → Chodakowska — `display`
  keeps the source spelling); `number` the first house number ("25", "3A", "46/48"; unit suffixes like "nr 419",
  "lok. U6", "/U4" dropped); `parts` = every `{street, number, numbers}` of intersections/lists ("A/B", "A róg B",
  "A i B", "A, B", line breaks); `approximate` = true for "w rejonie ul. …", "na wysokości …" (street then given in
  the nominative: "Chodakowskiej" → "Chodakowska"). `display` is the cleaned source text ("Lubartowska 23 i
  Serocka 21", "Gen. Fieldorfa Nila / Jana Nowaka Jeziorańskiego", "al. Stanów Zjednoczonych 32").
  `street_key(street)` (folded; no ul./al./gen./ks./św., initials or leading first names; "Fieldorfa Nila" →
  "fieldorfa") is the matching key for `related` and address geocoding. *ext (2026-10-23):* `street` and every
  `parts[].street` use one spelling per street, `normalize.STREET_CANONICAL` (`street_key` → name: "gen. A. E.
  Fieldorfa Nila" / "Augusta Emila Fieldorfa" → "Fieldorfa", "Jana Nowaka Jeziorańskiego" → "Nowaka-Jeziorańskiego",
  "St. Augusta" → "Stanisława Augusta"; no warning, `display` and `raw` keep the source text), so the site's street
  filter shows one entry per street; the report lists streets still written several ways.
* `parcels` (*ext* optional key `access: true` for parcels listed after "z dojazdem poprzez" = access road):
  an obręb `3-XX-XX` closes the list written before it; parcels after the last obręb inherit it (warning); without
  any obręb no parcel is emitted (warning, `parcels_raw` kept). Suffix markers (`16-cz`, `4/42-cz.`, `2/1 cz.`,
  `2/5cz.`, `8/4-część`) mark one parcel partial; a prefix (`cz.`, `część dz.`, `na części dz.`) marks every
  following parcel of the group until "dz." is repeated; `32/26 (cz.)` marks 32/26. Former numbers ("(dawnej 14)",
  "dawnej 3") and comments in parentheses are ignored; the current numbers of a subdivided parcel, `3-cz. (obecnie
  3/1, 3/3, 3/4)`, replace it (they inherit its partial flag; warning "działka 3 – w źródle podano jej obecne
  numery: …"); a number cut short (`12/;`) gets *ext* `incomplete: true` and a warning; obręb typos ("30-05-11",
  "3-04-012") and "60/25.1" (dot as separator) are corrected with a warning; a `3-…` obręb that does not exist in
  Praga-Południe (`normalize.PP_OBREBY`, e.g. 3-05-16) gets the warning "obręb 3-05-16 nie istnieje w ewidencji
  gruntów Pragi-Południe – możliwy błąd w źródle". A parcel listed both whole and partial is whole. Duplicates are
  merged.
* `sources[0].raw`: `[label, text]` with each cell rendered by `textutil.tidy_cell` (runs of ≥3 spaces — the
  office's visual line breaks — and real line breaks become `\n`, other whitespace squeezed, wording untouched),
  privacy-redacted.
* `procedure` for ws follows the JRWA symbol as printed (6730 → wz, 6733 → cp; any other symbol → null + warning).
  A ws record with 6733 whose description is housing gets a "możliwa pomyłka w źródle" warning (4 such in 2021–22).
* `warnings`: short Polish notes, de-duplicated, safe to show in the UI.
* `merge_duplicates(records)` (optional helper for build.py): same `id` + same date + same investment text → one
  record with all sources; same `id` but different content → `-2`, `-3`… suffixes and a warning on each.

Classification (`pipeline/classify.py`): `TAGS` = ordered `slug → {label, description, group}` (*ext* `group`:
`funkcja` = what is built, `roboty` = kind of works); `classify(text) → [slug…]` in `TAGS` order. Function tags
come from the main object of each clause (text before "z …"/"wraz z …"/"dla potrzeb …"), or for "zmiana sposobu
użytkowania X na Y" from the target Y. `rozbiorka` has no records yet (UI should hide zero-count tags).

## `site/data/records.json` (written by `pipeline/build.py`)

```jsonc
{
  "generated_at": "2026-10-23T00:00:00Z",       // time of the build that last CHANGED the data (see Build stage)
  "source_index_url": "…",
  "count": 474,
  "kinds": { "wz": {"label": "Decyzja o warunkach zabudowy", "short": "WZ", "description": "…"}, "cp": {…}, "ws": {…} },
  "tags":  { "jednorodzinny": {"label": "Dom jednorodzinny", "description": "…", "group": "funkcja"}, … },  // = classify.TAGS, in order
  "areas": { "goclaw": {"label": "Gocław"}, … },                           // from areas.json/areas.geojson, sorted by slug; may be empty
  "records": [Record]                                                       // newest first (date, period, id desc)
}
```

`Record`:

```jsonc
{
  "id": "wz-2026-15",
  "kind": "wz",                               // wz | cp | ws
  "procedure": "wz",                          // wz | cp | null — for ws from JRWA 6730→wz, 6733→cp; for wz/cp = kind
  "number": "15/PPD/WZ/2026",                 // decision number / case sign, whitespace-collapsed, as printed
  "date": "2026-07-09",                       // ISO date of decision (wz/cp) or initiation (ws); null if unparseable
  "date_raw": "09.07.2026r.",
  "period": "2026-07",                        // reporting month of the (first = oldest) source page
  "applicant": "osoba fizyczna",              // cleaned; natural persons' names redacted (see Privacy)
  "applicant_type": "person",                 // person | organization | unknown
  "investment": "budowa budynku mieszkalnego jednorodzinnego",   // cleaned text (streszczenie / nazwa inwestycji)
  "address": {
    "raw": "Marokańska\nPraga-Południe\n",
    "street": "Marokańska",                   // normalized street name without "ul."; null if none
    "number": null,                           // house number like "25", "3A", "46/48"; null if none
    "display": "Marokańska",                  // human display, e.g. "Żupnicza 25" or "Gen. Fieldorfa Nila / Jana Nowaka-Jeziorańskiego"
    "parts": [{"street": "Marokańska", "number": null, "numbers": []}],   // ext (normaliser): every street named
    "approximate": false                      // ext (normaliser): "w rejonie ul. …"
  },
  "parcels": [{ "number": "46/4", "obreb": "3-01-24", "partial": false, "id": "146507_8.0124.46/4" }],
  "parcels_raw": "dz. 46/4\n3-01-24",
  "tags": ["jednorodzinny", "nowa-budowa"],
  "area": "goclaw",                           // ASCII slug from areas.geojson via point-in-polygon; null if unknown
  "geo": {
    "lat": 52.2230, "lon": 21.0745,           // null if not located
    "method": "parcel",                       // parcel | address | street | null
    "parcels_found": ["146507_8.0124.46/4"],  // parcel ids whose geometry exists in parcels.geojson
    "bbox": [minLon, minLat, maxLon, maxLat], // of found parcels, or null
    "note": null                              // human-readable caveat, e.g. "lokalizacja przybliżona – ulica"
  },
  "sources": [{                               // every source row listing this decision, oldest file first
    "file_id": "a1b2c3d4e5", "page_id": "informacje-o-wszczetych-postepowaniach-07-2026",   // page_id = file's first linking page
    "sheet": "Decyzje o warunkach zabudowy", "row": 6,
    "raw": [["Lp", "1"], ["Numer decyzji", "15/PPD/WZ/2026"], …]   // stringified cells as in the file (tidied, privacy-redacted)
  }],
  "related": ["ws-6730-2026-11"],             // other records sharing a parcel id or the same street_key + house number,
                                              // chronological (date, then id); symmetric; never the record itself
  "warnings": ["…"]                           // data-quality notes shown in the UI ("brak roku w numerze decyzji")
}
```

Keys appear in the order above; the file has one record per line (diff-friendly, still plain JSON).

## `site/data/sources.json` (written by `pipeline/build.py`)

`{"generated_at", "index_url", "pages": [...], "files": [...]}` = manifest `pages` + `files` (as above), one per line,
enriched with:

* `files[].archive_path` — `sources/<file_id>.<ext>`, the site-relative mirrored copy (null if no local copy);
  `files[].history[].archive_path` — `sources/history/<file_id>-<sha12>.<ext>` for archived old versions (else null);
* `files[].record_ids` (natural order), `files[].parsed_count` (data rows read; **null** = file missing/unreadable,
  0 = empty template), `files[].kind_detected` (parser), `files[].warnings` (Polish, parser + build notes such as
  "linked as WZ but the file is a ws list", "no local copy");
  *ext:* `files[].layout` (parser layout id) and `files[].skipped_rows` (template rows holding only an Lp number);
* `pages[].blocks[].parsed_count` and `pages[].blocks[].count_mismatch` (bool):
  * the declared count belongs to the files **first published on that page** (`files[].page_ids[0]`); a leftover
    link to an earlier month's file (Oct 2025 WZ, Oct 2022 CP) is not counted again; if a block links only files
    first published elsewhere, those are counted; a file counts once per page;
  * no files: `0` when the block has a category, else `null`; any counted file with `parsed_count` null → `null`;
  * `count_mismatch` = declared and parsed both known and different (never true when either is null).

Kind of a file's rows: the workbook's own title/headers (`kind_detected`, per sheet) win over the linking block's
category, with a file warning when they disagree; the category is the fallback when the file does not say.

## `site/data/parcels.geojson` (written by `pipeline/build.py` from `locate_records`)

FeatureCollection of parcel polygons (EPSG:4326, coordinates rounded to 6 decimals), one feature per line, sorted
by id, top-level `attribution` + `source` (GUGiK ULDK); `properties`:
`{ "id": "146507_8.0124.46/4", "obreb": "3-01-24", "number": "46/4", "records": ["wz-2026-15", …] }`.
Also contains sub-parcels used for a subdivided parcel (see Geolocation stage).

## Exports, mirror and report (written by `pipeline/build.py` / `pipeline/export.py`)

* `site/data/records.csv` — every record, columns **identical** to the in-browser CSV button (`site/js/csv.js`
  `CSV_COLUMNS`; a test keeps them in sync): UTF-8 with BOM, `;` delimiter, CRLF, decimal comma in coordinates,
  RFC 4180 quoting, formula-injection guard (`'` before a leading `= + - @`, TAB or CR, unless the whole cell is a plain
  number such as `-5` or `-12,5`; the same rule as `csv.js`, so "-1+1" cannot run as a formula). Multi-valued
  cells are joined with ` | `. Includes permalink, official file URL, archive-copy URL, page title/URL, sheet!row.
* `site/feed.xml` — Atom 1.0, newest 100 records (date desc, id desc). Entry `id` = `urn:uuid:` UUIDv5 of the record
  id (stable whatever the site URL); `published`/`updated` = `published_at` of the record's first source page (else
  its date); links: `alternate` = permalink `<SITE_URL>#/wpis/<id>`, `related` = each source Excel file.
* `SITE_URL` (env, or `--site-url`) is the public base URL used in CSV/feed/report links. CI sets it from
  `actions/configure-pages`. Without it the build takes the absolute base of the committed `site/feed.xml`
  (`<link rel="self">` minus `feed.xml`), so a local rebuild after a CI data commit renders the same links; else `./`
  (relative — correct for the feed, which readers resolve against its own URL).
* `site/sources/<file_id>.<ext>` (+ `history/`) — byte-identical copies of `data/raw/`, rewritten only when the bytes
  differ; copies of files no longer in the manifest are removed.
* `data/report.md` — data-quality dashboard: totals per kind/year, declared-vs-parsed reconciliation per kind and
  every mismatching block (with links), gaps in WZ/CP decision numbering per year (numbers never published),
  geolocation methods and notes, records without a location, record
  warnings by type, classification coverage, file/page warnings. No timings or request counts (deterministic).

## Build stage (`pipeline/build.py`)

`uv run python -m pipeline.build [--offline] [--skip-crawl] [--refresh] [--refresh-misses] [--site-url URL] [-q]`;
`run_build(Paths(root), *, crawl, online, refresh, refresh_misses, site_url, session, geo_session, now) -> BuildResult`.

1. `crawl.run_crawl` (skipped with `--skip-crawl`/`--offline`); a failed crawl falls back to the previous manifest
   (exit code 3 after writing outputs), and so does a crawl with `stale_pages`; an unchanged crawl keeps the
   manifest's previous `generated_at`. A district/BAiPP file that gave records in the previous build
   (`sources.json` `parsed_count` > 0) but cannot be read now (no local copy, broken workbook) is named in the
   report and `BuildResult.lost_files`, and the build exits with code 3 (CI then commits and deploys nothing).
2. Every manifest file is parsed once, oldest publication first (`period`, `filename`, `file_id`), and its rows are
   normalised with `file_meta = {file_id, page_id: page_ids[0], period: files[].period}`.
3. `normalize.merge_duplicates`: the same decision in several files → one record with several `sources` (first
   listing wins for field values and `period`); same id with different content → `-2`, `-3` + warnings.
4. `geocode.locate_records` (online or caches only); 5. `related`; 6.–8. outputs above.

**Determinism:** stable ordering everywhere; `generated_at` is the only timestamp. The build first renders every
output with the previous `generated_at`; if the data documents (`records.json`, `permits.json`, `sources.json`,
`parcels.geojson`, `parcels-permits.geojson`) are byte-identical to what is on disk, the timestamp stays and only
outputs whose bytes differ are written (a different `SITE_URL` re-renders just the CSVs, the feed and the report,
which embed it). Otherwise all outputs get the current time. A no-op scheduled run therefore makes no diff, and
`generated_at` changes only when the data does.

## `site/data/areas.geojson` (written by `pipeline/areas.py`)

Neighbourhood polygons of Praga-Południe plus the district outline, EPSG:4326, coordinates rounded to 6 decimals,
lightly simplified (1.5 m, per OSM way, so shared borders stay identical).

**Deviation (decided 2026-10-23):** the city's Miejski System Informacji (MSI) divides Praga-Południe into **6** areas,
not 7: Gocław, Gocławek, Grochów, Kamionek, Olszynka Grochowska, Saska Kępa. Przyczółek Grochowski is part of the MSI
area *Gocław* (it is only a housing estate / OSM `admin_level=11` "osiedle"). The 6 polygons tile the district exactly.

```jsonc
{
  "type": "FeatureCollection",
  "attribution": "© OpenStreetMap contributors (ODbL 1.0)",      // show on the map
  "licence": "ODbL 1.0", "licence_url": "https://opendatacommons.org/licenses/odbl/1-0/",
  "copyright_url": "https://www.openstreetmap.org/copyright",
  "source": "OpenStreetMap via Overpass API: Praga-Południe (relation 2544288) and its admin_level=10 MSI areas",
  "osm_base": "2026-10-23T00:51:20Z", "fetched_at": "2026-10-23T00:52:12Z",
  "features": [{
    "type": "Feature", "id": "saska-kepa",
    "properties": {
      "slug": "saska-kepa",                 // ASCII kebab-case; "_district" for the outline (first feature)
      "label": "Saska Kępa",
      "source": "© OpenStreetMap contributors, ODbL 1.0 – OSM relation 2544287",
      "source_url": "https://www.openstreetmap.org/relation/2544287",
      "osm_id": 2544287, "admin_level": "10"   // "9" for the district
    },
    "geometry": { "type": "Polygon", "coordinates": [...] }
  }]
}
```

Slugs: `goclaw`, `goclawek`, `grochow`, `kamionek`, `olszynka-grochowska`, `saska-kepa` (+ `_district`).
The OSM district outline agrees with the official ULDK cadastral precincts (obręby) to within 2 m.

## Geolocation stage (`pipeline/geocode.py`)

`locate_records(records, cache_dir="data/cache", online=True, log=print, *, session=None, area_index=None,
areas_out="site/data/areas.geojson", refresh_misses=False, cross_check=True)
-> {"parcels_geojson": FeatureCollection, "stats": {...}}` fills `record["geo"]` and `record["area"]` **in place**
(it reads only `id`, `parcels[].id/obreb/number` and `address.street/number/display/parts`).
*Integration changes (build stage, 2026-10-23):* streets for crossings/lists come from `address.parts` when the
normaliser gives ≥ 2 (it keeps only the first street in `address.street`); a whole-number parcel ULDK no longer
knows ("3") is replaced by its cached sub-parcels ("3/1", "3/2"… — named by other records), unless an exact,
validated address point exists (`stats.records_via_subparcels`).

`geo.method` priority and `geo.note` texts (Polish, shown in the UI; several notes are joined with `"; "`):

| method | point | typical notes |
|---|---|---|
| `parcel` | area-weighted centroid of the found parcels (= centroid of their union); if they are > 1 km apart, of the largest cluster | `w ULDK znaleziono 2 z 3 działek`, `działki odległe od siebie o ponad 1 km – punkt dla największej grupy (2 z 3)`, `adres Mińska 46 leży ok. 950 m od wskazanych działek` (source inconsistency; parcel point kept), `działki 3 (obręb 3-02-03) nie ma już w ewidencji (została podzielona) – przyjęto jej części znane z innych wpisów: 3/1, 3/2` |
| `address` | GUGiK UUG address point, street name + house number validated, inside the district | `lokalizacja przybliżona – budynek nr 3` (asked 3A), `nazwa ulicy dopasowana w przybliżeniu (ulica Boremlowska)` (typo in source) |
| `street` | UUG's own street point when it lies in the district, else the midpoint of the street axis clipped to the district; *ext:* narrowed to the record's stated precinct(s) when the street crosses them (midpoint of the longest stretch inside, ULDK `GetRegionById` polygons); or the crossing of two streets for "A / B" | `lokalizacja przybliżona – ulica`, `lokalizacja przybliżona – ulica w obrębie 3-05-24`, `ulica nie przechodzi przez obręb z rejestru (3-06-08)`, `lokalizacja przybliżona – skrzyżowanie ulic` |
| `null` | `lat`/`lon` null | `brak działek i adresu w źródle`, `nie udało się ustalić lokalizacji`, `działek nie znaleziono w ewidencji gruntów (ULDK) – mogły zostać podzielone lub scalone` |

*ext (2026-10-23):* notes say "ewidencja gruntów (ULDK)" instead of the bare "ULDK" (`w ewidencji gruntów (ULDK)
znaleziono 2 z 3 działek`). **Wrong precinct in the source:** when a record's exact, validated address lies more
than 300 m from all its found parcels – or none of its parcels exists but the address is found exactly – ULDK
`GetParcelByXY` gives the parcel under the address (cached as `xy:<lon>,<lat>`, 6 dp). If it has a stated number in
another precinct (or is a part of a stated whole-number parcel ULDK no longer has there, `137/2` for `137`), the
source's precinct is taken as a typo: the record's `parcels[].id/obreb` are rewritten (also the other stated
parcels of that precinct that exist in the new one; `parcels_raw` keeps the source), the record is located by them
(`method: "parcel"`) and gets the warning "obręb w źródle (3-06-03) prawdopodobnie błędny – działka 35 pod adresem
Busolowa 16A leży w obrębie 3-05-26" (`stats.obreb_corrected_by_address`). If the address lies in a stated
precinct (a large site such as Ostrobramska 75) the parcel point and the distance note stay; otherwise (another
number in another precinct) they stay too and `geo.conflict = true` is set (`stats.address_parcel_conflicts_flagged`).
For a record without found parcels, a match of the number before "/" only (`43/7` for `43/1`) replaces the
"mogły zostać podzielone" note with "… pod adresem leży działka 43/7 obr. 3-02-06 – obręb w źródle prawdopodobnie
błędny". So `locate_records` may also change `parcels[].id/obreb` and append to `warnings`. Sub-parcels stand in
for a subdivided parent only when a record names them (parcels learnt under address points never move other
records, which keeps rebuilds deterministic); for a number cut short in the source the stand-in note reads "numer
działki w źródle niepełny („12/”, obręb 3-06-06) – przyjęto działki 12/… znane z innych wpisów: …".

Every point lies inside the district polygon + 50 m (otherwise discarded with a warning). `geo.bbox` is the bbox of
all found parcels (null for address/street). `geo.parcels_found` lists ids present in `parcels.geojson`.
`record.area` = slug of the containing neighbourhood (nearest within 50 m for border points), else null.

Cache formats (one entry per line, sorted keys, atomic writes; misses re-tried after 30 days or with
`refresh_misses=True`; network errors are never cached):

* `data/cache/uldk.json`: `{"146507_8.0124.46/4": {"status": "ok", "geometry": {GeoJSON, 6 dp}, "centroid": [lon, lat],
  "bbox": [...], "area_m2": 743.7, "fetched_at": "…Z"}, "146507_8.0999.1": {"status": "missing", "fetched_at": "…Z"}}`;
  *ext:* `"xy:21.082880,52.231582": {"status": "ok", "id": "146507_8.0526.35", "fetched_at"}` (parcel under a point;
  its geometry is stored under its id unless that id is cached already) and `"region:146508_8.1406": {"status",
  "geometry"?, "bbox"?, "fetched_at"}` (precinct exists; with the polygon, simplified to ~2 m, when it was needed
  for a street).
* `data/cache/uug.json`: keyed by the exact query (`"Warszawa, Mińska 46"`): `{"status": "ok"|"missing", "type":
  "address"|"street"|…, "candidates": [{"street", "number", "lon", "lat", "accuracy", "simc", "ulic", "code", "city",
  "geometry"?}], "fetched_at"}` (`geometry` = street axis for street results).
* `data/cache/areas.json`: `{"fetched_at", "source": {...licence...}, "warnings", "features": [{"slug", "label",
  "osm_id", "admin_level", "geometry" (7 dp, unsimplified)}], "overpass": <raw response>}`.

## Privacy

The office anonymises natural persons as "osoba fizyczna", but some older files contain names
("Pani Agata X reprezentowana przez pełnomocnika"). We redact explicit natural-person names
(patterns like `Pan`, `Pani`, `Państwo` + name) to `osoba fizyczna (dane usunięte)` in `applicant` AND in `sources[].raw`.
Company/institution names are kept. The original file stays linked for verification.

## Generated, git-tracked caches

* `data/raw/<file_id>.xlsx` — downloaded originals (also copied to `site/sources/`; git stores identical blobs once).
* `data/cache/uldk.json` — parcel lookups keyed by parcel id (hits AND misses, with `fetched_at`).
* `data/cache/uug.json` — address geocoding keyed by query string.
* `data/cache/areas.json` / `site/data/areas.geojson` — neighbourhood boundaries.

Caches make rebuilds offline-capable and polite to public APIs.

## Frontend (`site/`, consumer of the files above)

Details in `docs/FRONTEND.md`. What the UI relies on, so producers know what matters:

* Required: `site/data/records.json` and `site/data/sources.json`. Optional (loaded lazily, 404/empty tolerated):
  `parcels.geojson`, `areas.geojson`, and the downloads `data/records.csv`, `feed.xml` (probed on the About page).
* Dictionaries drive the UI: `kinds{label, short, description?}`, `tags{label, description?, group?}` (grouped by
  `group`; zero-count tags hidden), `areas{label}`. Only the kind codes `wz/cp/ws` are assumed (colour/shape).
* Used extensions: `address.parts` (every street is searchable/filterable), `address.approximate`,
  `parcels[].access`, `pages[].warnings`, `files[].{last_modified, sha256, history[].archive_path, error, warnings}`.
  Every field may be null; nothing breaks on missing keys.
* `files[].page_ids` is used to list every monthly page that links a record's file in the provenance block.
* URL contract for permalinks: `#/wpis/<record id>` (record ids must stay URL-safe and stable).
* `CSV_COLUMNS` in `site/js/csv.js` is the column contract shared with `pipeline/export.py`.
* A top-level `"fixture": true` in records/sources marks sample data (the UI shows a banner);
  the frozen test fixture lives in `tests/fixtures/site-data/`.
* *v2 (frontend round, 2026-10-23):* `permits.json` + `parcels-permits.geojson` are fetched lazily (pb/zg switched
  on, a pb/zg permalink, a record with related `pb-`/`zg-` ids, an RWDZ file filter, or idle time on desktop); a
  missing `permits.json` only disables the permits layer. Before it loads the pb/zg facet counts come from
  `records.json → counts_by_kind`, so it must count every record of `permits.json`. Codes the UI assumes besides the
  kinds `wz/cp/ws/pb/zg`: outcome `refusal` (warning style), dataset `district/baipp/rwdz` (Sources tab layout,
  provenance block; a file's dataset = `files[].source`, else its first page's `source`), permit scope `rozbiorka`.
  Labels always come from the dictionaries. Used optional RWDZ file keys: `dataset_url`, `licence`, `etag`,
  `sha256_zip`, `size_zip`, `zip_member` (the CSV inside the ZIP when `filename` names the ZIP), `rows_total`;
  BAiPP files: `rows_total`. Related ids of other kinds are expected to be namespaced as documented
  (`pb-…`, `zg-…`) – the UI uses the prefix to decide whether to load permits for a detail.
* *v2 real-data round (2026-10-23):* nothing new is required. Optional `areas.geojson` top-level keys now used on the
  About page: `copyright_url`, `licence`, `licence_url`, `fetched_at` (OpenStreetMap credit in Polish; `source` is
  shown as a tooltip). The RWDZ page's `blocks[].text` may end with "(<ZIP name>)": the UI drops that suffix when it
  equals the file's ZIP name, which it shows with `size_zip` and `zip_member` underneath.
* *final round (2026-10-23):* optional `geo.conflict` (hollow marker, "Lokalizacja niepewna") and `geo.uncertainty_m`
  (dashed circle, "W pobliżu" tolerance) are used when present – see "Pipeline round 3" below.

---

## v2 extension: three datasets (decided 2026-10-23 by the lead)

Research: `docs/research/building-permits.md`. Two more sources join the district lists. All three end up as the
same `Record` shape so the UI, search, map, related-records and provenance work uniformly.

| `dataset` | Publisher / source | Kinds | Output file | Default in UI |
|---|---|---|---|---|
| `district` | Urząd Dzielnicy Praga-Południe – monthly Excel lists (the original source) | `wz`, `cp`, `ws` | `records.json` | shown |
| `baipp` | Biuro Architektury i Planowania Przestrzennego (Urząd m.st. Warszawy) – yearly/YTD Excel lists, `architektura.um.warszawa.pl/postepowania-i-decyzje` + `/-/rejestry…` archive pages, **filtered to Praga-Południe** | `wz`, `cp`, `ws` | `records.json` | shown |
| `rwdz` | GUNB Rejestr Wniosków, Decyzji i Zgłoszeń – bulk CSV in ZIP (CC0 1.0), filtered to parcels in unit `146507_8` | `pb` (pozwolenie na budowę / rozbiórkę), `zg` (zgłoszenie) | `permits.json` (lazy) | **opt-in** (kind chips off by default) |

### New / extended Record fields (all records)

```jsonc
{
  "dataset": "district",          // district | baipp | rwdz
  "issuer": "district",           // district | city | voivode | other  — who issued/handles the case
                                  //   district lists → "district"; BAiPP lists → "city";
                                  //   RWDZ: nazwa_organu "… - Praga Płd." → district, "Prezydent Miasta Warszawa" → city,
                                  //   "Wojewoda Mazowiecki" → voivode, anything else → other
  "outcome": null,                // null (not stated in source) | granted | refusal | discontinued | transfer | expiry
                                  //   BAiPP number suffix /O odmowa, /U umorzenie, /P przeniesienie, /W wygaśnięcie,
                                  //   second-line words ("odmowa", "umorzenie", "wz", "licp" = granted); district → null
  "filed_date": null,             // ISO date the application was filed (RWDZ data_wplywu_wniosku); else null
  "permit": null                  // only for pb/zg, see below
}
```

`kind` gains `pb` and `zg`; `procedure` = `pb`/`zg` for them. The `kinds` dictionary in records.json lists all five
(`pb`: label "Pozwolenie na budowę lub rozbiórkę", short "Pozwolenie"; `zg`: label "Zgłoszenie budowy lub robót",
short "Zgłoszenie"), each with a plain-language `description`.

`permit` (pb/zg only):

```jsonc
{
  "register_id": "ST-MZ-PA/WNIOSEK/29594/2026",   // numer_gunb / numer_ewidencyjny_system (stable, unique)
  "case_sign": "RPW/142815/2026-1B/FSO",           // numer_urzad / numer_ewidencyjny_urzad (office case sign), may be null
  "scope": "budowa",                               // nazwa_zamierzenia_bud normalised: budowa | rozbudowa | nadbudowa |
                                                   //   odbudowa | rozbiorka | przebudowa | inne (zg: rodzaj_zam_budowlanego)
  "scope_label": "budowa",                         // as printed in the register
  "category": "XIII",                              // kategoria obiektu budowlanego (roman numeral) or null
  "category_label": "budynki mieszkalne wielorodzinne …",  // from an official-annex table in the pipeline (verify!) or null
  "single_family": false,                          // rodzaj_inwestycji == jednorodzinny (pb); null if unknown
  "cubature": 1234.5,                              // m³ or null
  "state": null                                    // zg only: "stan" column as printed
}
```

RWDZ mapping notes: `number` = office decision number (`numer_decyzji_urzedu`, e.g. `163/PPD/PB/2026`) or for zg the
office number; `date` = `data_wydania_decyzji` (pb) / `data_wplywu_wniosku_do_urzedu` (zg); `period` = month of
`date`; `applicant` = `nazwa_inwestor` (empty → `"osoba fizyczna"` with `applicant_type: "person"`; zg has no investor
column → `null`/`"unknown"`); `investment` = `nazwa_zam_budowlanego`; address from `cecha ulica_dalej ulica nr_domu`
(display e.g. "Czapskiego Andrzeja 3" → prefer "Andrzeja Czapskiego 3"); parcels = all case×parcel rows grouped by
case (`<unit>.<obręb>.<numer_dzialki>` — same id format as everywhere, obręb 4 digits); tags from `classify()` on
the investment text plus the scope/category. **Designer columns (`projektant_*`, `nazwisko_projektanta`,
`imie_projektanta`, `projektant_pozostali`) are never put into records or `sources[].raw`** (data minimisation);
they remain only in the byte-exact mirrored extract.

### Record ids (namespaced, stable)

* district: unchanged (`wz-2026-15`, `cp-2025-8`, `ws-6730-2026-29`).
* BAiPP: `wz-am-<year>-<seq>`, `cp-am-<year>-<series>-<seq>` where series = `c1` (krajowe/wojewódzkie) or `c2`
  (powiatowe/gminne) when known, `ws-am-<jrwa>-<year>-<seq>`; e.g. `95/AM/PPD/WZ/2026/O` → `wz-am-2026-95`,
  `6/PRD/21` → `wz-am-2021-6`, `1/PRD/C2/22` → `cp-am-2022-c2-1`, `AM-ZP-P.6730.14.2020` → `ws-am-6730-2020-14`.
  Must never collide with district ids. Fallback `<kind>-am-f<file_id>-r<row>`.
* RWDZ: `pb-<slug(register_id without the type word)>`, e.g. `ST-MZ-PA/WNIOSEK/29594/2026` → `pb-st-mz-pa-2026-29594`;
  `PL-MZ/ZGŁOSZENIE/12/2025` → `zg-pl-mz-2025-12` (ASCII, lowercase, `[a-z0-9-]` only).

### Sources for the new datasets

* BAiPP pages/files go into `data/manifest.json` / `sources.json` like district ones, with `pages[].source = "baipp"`
  (district pages get `"district"`), `period` = `YYYY` for yearly pages (title-derived; the current page is the
  running year). Because the current-year file is republished monthly under a new URL, **every snapshot ever
  downloaded is kept** in `data/raw/` and stays a source; records are de-duplicated by id across snapshots
  (sources[] lists every snapshot row, newest snapshot first is NOT required — keep oldest first like district).
  BAiPP rows outside Praga-Południe are never stored as records; per file we record `rows_total` (city-wide) and
  `parsed_count` (= Praga-Południe rows kept). District filter = last line of the address cell
  (`/praga[\s-]*(po[lł]udnie|p[lł]d)|parga po[lł]udnie/i`), never the applicant; if none of a kept row's parcels
  resolves under `146507_8` but one resolves under another Warsaw unit, keep it with a warning
  ("działka poza dzielnicą Praga-Południe wg ULDK").
* RWDZ: each snapshot is a `files[]` entry with `source: "rwdz"`, `file_id` = `rwdz-wnioski` /
  `rwdz-zgloszenia-2016-2021` / `rwdz-zgloszenia-2022`, `url` = GUNB ZIP URL, `dataset_url` =
  `https://dane.gov.pl/pl/dataset/3467`, `licence: "CC0 1.0"`, `etag`, `last_modified`, `sha256_zip`, `rows_total`
  (whole CSV), `parsed_count` (Praga-Południe rows), `archive_path` = `sources/rwdz/<file_id>.csv` — a byte-exact
  extract: the original header line + every original line kept (same bytes, same order) — and `sha256` of that
  extract. One pseudo-page in `pages[]`: `{page_id: "rwdz", source: "rwdz", url: "https://wyszukiwarka.gunb.gov.pl/pobranie.html",
  title: "Rejestr wniosków, decyzji i zgłoszeń (GUNB)", period: null, blocks: [one per file, declared_count: null]}`.
  `sources[]` entry of a pb/zg record: `{file_id, page_id: "rwdz", sheet: null, row: <first CSV line number in the
  ORIGINAL file (1 = header)>, rows: [all line numbers of this case], extract_rows: [line numbers in the mirrored
  extract], raw: [[column, value], …] (case-level columns + all parcels joined with " | ", designer columns removed)}`.
* Big ZIPs are downloaded to `data/cache/rwdz/` (git-ignored, conditional GET with ETag/If-Modified-Since stored in
  `data/cache/rwdz.json`, which IS tracked); only the small extracts are committed (`data/raw/rwdz/*.csv`, mirrored to
  `site/sources/rwdz/`). `--offline` builds from the committed extracts.

### BAiPP ingestion – as implemented (crawl.py, parse.py, normalize.py, baipp.py, build.py; 2026-10-23)

Details and extensions of the rules above, decided while implementing the `baipp` dataset:

* **Manifest** (`crawl.run_crawl(…, sources=("district", "baipp"), baipp_url=…)`; CLI `--skip-district` /
  `--skip-baipp`; requests ≤ 2/s per host, `DEFAULT_DELAY = 0.5` s):
  * every page and file has `source` (`district` | `baipp`); pages and files are grouped by source (district first),
    each group ordered as before;
  * BAiPP pages: `page_id` = slug (`postepowania-i-decyzje`, `rejestry2020`, `rejestry23`, …; the archive slugs are
    read from the "Dane z ubiegłych lat" box, never guessed), `title` as printed, `period` = `YYYY` from the title
    ("(2025 r.)", "(sierpień - grudzień 2020 r.)"), else the year of the attachment texts ("IX.2026"), else the running
    year (with a warning); `published_at` from the article's `<time>` (null on the current page); `summary` and
    `index_page` null; one block per attachment link `{text, category, declared_count: null, file_ids: [id], series}`
    with `series` = `c1` (krajowe/wojewódzkie) | `c2` (powiatowe/gminne) | null (from the link text / file name);
  * BAiPP files carry `series` too; **`files[].removed_from_source_at`** (*ext*): a BAiPP snapshot the pages no
    longer link is kept in the manifest (and in `data/raw/`, mirrored) with the date of the first crawl that missed
    it; a file linked again loses the mark;
  * BAiPP failures never abort the crawl: an unreachable page is taken from the previous manifest with a warning;
    after an incomplete BAiPP crawl (current page down, no archive box) nothing is marked removed.
* **Parser**: layouts `baipp-ws`, `baipp-wz`, `baipp-cp` (title mentions "Biuro Architektury"; header in row 4,
  column A empty) and `baipp-ws-2020` / `baipp-wz-2020` / `baipp-cp-2020` (2020 "Załącznik" files with merged 2-row
  headers); a numbering row may lack its first number (`_ 2 3 4 5 6 7`); a table note in place of data
  ("brak decyzji wydanych w grudniu") goes to `skipped` with `reason: "adnotacja: „…”"`; *ext* `ParsedFile.series`
  (`c1`/`c2` for ULICP lists, from the title; null otherwise). Every one of the 28 published workbooks parses with
  no warning and no dropped row.
* **Filter + counts** (`build.parse_sources`, `baipp.in_district`): only rows whose address cell's last visual line
  (line breaks and 3+-space gaps) matches the district regex become records. `sources.json files[].rows_total` (*ext*,
  every file) = data rows in the file (city-wide for BAiPP; = `parsed_count` for district files); `parsed_count` = rows
  kept as records.
* **Normaliser** (`normalize_row(row, kind, {…, "dataset": "baipp", "series": "c1"|"c2"|None})`):
  * `number` = the printed number without the outcome words (`"95/AM/PPD/WZ/2026/O\n\nodmowa"` →
    `95/AM/PPD/WZ/2026/O`, spaces around slashes removed); ws: the first case sign (an `EZD …` second sign → warning);
  * `outcome`: the cell's words win ("odmowa…" → refusal, "umorzenie…" → discontinued, "przeniesienie" → transfer,
    "wygaśnięcie"/"wygaszenie" → expiry, "wz"/"licp" alone → granted; `/P` + "odmowa przeniesienia decyzji" is a
    refusal), then the 2024+ suffix (`/O /U /P /W`), then a `…/AM/…` number with neither = granted; unrecognised words
    ("inna", "uchylenie decyzji i zawieszenie postępowania") or suffixes (`/I`, `/X`) → a warning and, without a known
    suffix, null; ws → null;
  * `applicant` "dane osobowe" → "osoba fizyczna" (`person`); "Kancelaria Adwokacka dane osobowe" → "Kancelaria
    Adwokacka (dane osobowe)" (`organization`);
  * `address`: the district line is removed before parsing (also "Parga Południe"), `raw` stays the full cell;
    *generic*: a road stretch "X na odcinku [od] A – B" / "od ul. A do ul. B" → `parts` = X, A, B (nominative),
    `approximate: true`, `display` keeps the phrase;
  * `parcels`: obręby of every Warsaw zone 1–8 (`4-15-08`; ids still assume `146507_8` until the ULDK check below);
    *generic*: an obręb cut short (`3-05-2`) closes its group, whose parcels are dropped with a warning;
  * `period` = month of the record's own `date` (null without a date); a date outside the file's year → warning;
  * ids as above; ULICP series from the number (`C2`/`CP2`), else the file's; **ws signs of another BAiPP planning
    unit than ZP-P** (numbering is per unit) get the unit: `AM-ZP-E.6730.5.2025` → `ws-am-zp-e-6730-2025-5`
    (all Praga-Południe signs 2020–2026 are ZP-P, so the contract form applies to every current record).
* **Merging** (`merge_duplicates`): the same BAiPP id in different files = the same case in another snapshot / yearly
  file → always one record; build passes BAiPP files ordered by `period`, then `last_modified`, so the **newest
  snapshot's values win** (the office corrects rows between monthly snapshots), `sources` list every snapshot row
  oldest first, and changed content adds "treść pozycji różni się między wersjami zestawienia BAiPP (…) – pokazano
  wersję z najnowszego pliku". The same id twice within one file still splits into `-2`.
* **Parcels outside the district** (`baipp.check_out_of_district`, run by build before geocoding): for a BAiPP record
  none of whose parcels exists under `146507_8`, the same obręb/number is looked up under the other units of the
  obręb's **zone** only (the 4-digit ULDK obręb code drops the zone digit, so `0203` exists in Mokotów (1-02-03) and
  Praga-Południe (3-02-03); zones: 1 Mokotów/Ursynów/Wilanów, 2 Ochota/Ursus/Włochy, 3 Praga-Południe/Rembertów/Wawer,
  4 Praga-Północ/Targówek/Białołęka, 5 Śródmieście, 6 Wola/Bemowo, 7 Żoliborz/Bielany – verified on 2,000+ BAiPP rows –
  and 8 Wesoła (ULDK names 146515_8.0602 "8-06-02")). A hit corrects the parcel `id` (`146508_8.1508.18/5`), adds the warning "działka poza
  dzielnicą Praga-Południe według ewidencji gruntów (ULDK): …" (`baipp.OUTSIDE_WARNING`), and the record is **not
  geocoded**: `geo` all null with note "działki poza dzielnicą Praga-Południe według ewidencji gruntów (ULDK) – nie
  pokazano na mapie", `area` null, its parcels not in `parcels.geojson`.
  Hits and misses are cached in `data/cache/uldk.json` (geocode cache helpers; offline: cache only).
  *ext (2026-10-23):* the same for **GUNB RWDZ** records (`baipp.check_out_of_district_permits`, run by build
  **after** geocoding): a permit with a `146507_8` parcel whose precinct is no Praga-Południe precinct
  (`normalize.PP_OBREBY`) and that could not be placed in the district (a located record is a district case with a
  mistyped precinct and is never moved) is probed under every other Warsaw unit, parcel (`GetParcelById`) and
  precinct (`GetRegionById`). The register's 4-digit code has no zone digit and repeats across zones (1507.3 exists
  in Praga-Północ *and* Wawer), so the case must name the unit: organ "… - Praga Pn." or a Praga-Północ number code
  (`/PRN/`, `/PPN/`) → Praga-Północ; the district office → Rembertów/Wawer; then the hinted unit that has the
  parcel wins, else the hinted unit that has the precinct (the parcel itself gone: "obręb 146508_8.1406
  (Praga-Północ), działki już w nim nie ma"); without a hint only a precinct that exists under exactly one unit
  counts. A moved record keeps its data and counts (sources matter), gets the corrected `id`/`obreb` (`4-15-07`),
  the outside warning in place of the "obręb nie występuje" one, and `geo` = the unplaced note.
* **Record key order** in `records.json`: `id, kind, procedure, dataset, issuer, outcome, number, date, date_raw,
  filed_date, period, applicant, applicant_type, investment, address, parcels, parcels_raw, tags, permit, area, geo,
  sources, related, warnings`.
* **Dictionaries** in `records.json`: `datasets` (all three, `{label, short, publisher, url, licence?, description}`),
  `issuers {label}`, `outcomes {label, description}`; `permit_scopes` / `permit_categories` are `{}` until the RWDZ
  integration; `counts_by_kind` lists wz/cp/ws (pb/zg added with RWDZ).
* `data/report.md` gets a "BAiPP (city architecture bureau) lists" section (city-wide vs Praga-Południe rows per
  file, outcomes, records listed in several snapshots, records outside the district); its declared-vs-parsed section
  covers the district pages only (BAiPP declares no counts).

### RWDZ ingestion – as implemented (`pipeline/rwdz.py`, 2026-10-23)

`run_rwdz(cache_dir="data/cache", raw_dir="data/raw/rwdz", online=True, refresh=False, session=None, log=print)
-> {"records", "files", "page", "stats"}`: records newest first (the `build.sort_records` key), in the record key
order above, with `area`/`geo` null and `related` `[]`. It raises `RwdzFormatError` **before writing anything** when
GUNB's format drifts (header ≠ the expected 31 / 26 columns, a malformed row that mentions the district, > 1 %
malformed rows) or when a committed extract was edited (SHA-256 ≠ sidecar). Dictionaries for `records.json`:
`KIND_META` (pb/zg `{label, short, description}`), `DATASET_META` (= `datasets.rwdz`, plus `dataset_url`,
`licence_url`), `PERMIT_SCOPES` (`{slug: {label, register}}` – ship `label`), `PERMIT_CATEGORIES`
(`{roman: {label, description}}`: `label` = our short UI label, `description` = the official wording
`CATEGORY_LABELS` of the annex to Prawo budowlane, Dz.U. 2026 poz. 524 – `CATEGORY_SOURCE`, ISAP WDU20260000524).
By hand: `uv run python -m pipeline.rwdz [--offline] [--refresh]` (prints the stats).

Refinements of the contract above:

* **Selection** (per archive, two streaming passes over the CSV): a case (GUNB system number) is kept **whole** –
  every row, also rows on parcels of other units (a city permit for Most Łazienkowski lists Śródmieście parcels: they
  keep their own unit, and the record notes "sprawa obejmuje też działki spoza Pragi-Południe – jednostka ewidencyjna
  146510_8 (Śródmieście): 9") – when one of its rows has unit `146507_8`, or is a row of the district office
  ("… - Praga Płd.") whose unit is empty, one edit or one adjacent swap away from `146507_8` (`148507_8`,
  `146057_8`, `146517_8` …) or not a Warsaw district unit at all (`146078_8`, `086101_1`). Those units are corrected
  to `146507_8` with a warning (all such rows of 2026-10-22 have Praga-Południe streets). A **valid** other Warsaw
  unit two or more edits away is genuine (the office handled Wawer cases `146514_8` in 2020) and is not kept; such
  rows are counted per unit in the sidecar (`office_rows_not_kept`). *ext (2026-10-23, `EXTRACT_VERSION` 2):* the
  cases in `rwdz.UNIT_FIXES` (GUNB case number → the wrong unit as printed; each verified in ULDK: the parcel or
  precinct exists only under `146507_8` – Szaserów 133 with the Śródmieście unit, three more) are kept with reason
  `listed`, for any organ, and corrected with the warning "… potraktowano jako 146507_8 (Praga-Południe) – według
  ewidencji gruntów (ULDK) ta działka lub obręb istnieje tylko na Pradze-Południe; błąd w rejestrze". Unkept cases
  with a Praga-Południe sign – the district office's case sign `UD-VI-…` or a `…/PPD/…`, `…/PRD/…` decision number –
  are listed in the sidecar (`signal_cases_not_kept`: `[case, first line, unit]`) and the report for review (never
  kept automatically: `94/AM/PPD/PB/2025` is a genuine Praga-Północ parcel).
* **Line numbers** are physical lines split on `\n` only (as `sed -n Np` shows them), 1 = header. A record may span
  several lines (quoted designer values with line breaks, zgłoszenia only): `row`/`rows` are the first lines of the
  records, `extract_rows` the same in the extract.
* **Extract** `data/raw/rwdz/<file_id>.csv` = BOM + the original header line + every kept record's lines, byte for
  byte, in file order. **Sidecar** `<file_id>.meta.json`: `file_id, source, url, dataset_url, licence, zip_name,
  zip_member, etag, last_modified (ISO UTC), sha256_zip, size_zip, downloaded_at, encoding, delimiter, layout, header,
  rows_total, rows_malformed, filter (Polish), extract_version, parsed_count (rows), cases, office_rows_not_kept,
  sha256, size, lines` – `lines[i]` = original line of extract line `i + 2`.
* **Snapshot stability:** the extract, its sidecar and `data/cache/rwdz.json` change only when the extract changes
  (its bytes or its line map). GUNB rebuilds the files every night; a night without news for the district leaves the
  repository untouched, so `etag` / `last_modified` / `sha256_zip` / `rows_total` describe the snapshot the extract
  was **taken from** (not necessarily GUNB's newest file – the cited lines are the same). `data/cache/rwdz.json`
  (tracked) = `{"files": {file_id: {url, etag, last_modified, size, sha256_zip, downloaded_at}}}`, mirroring the
  sidecars; `data/cache/rwdz/local.json` (git-ignored, next to the ZIPs) holds the validators of the local ZIP copies.
* **Requests** (one GET per archive and run): with a local ZIP its own validators (`If-None-Match` +
  `If-Modified-Since`); with a ZIP but no validators (copied by hand) `If-Modified-Since` = its mtime, and a 304
  adopts it (ETag from the 304, Last-Modified from one HEAD); otherwise (CI) the validators of the committed snapshot –
  a 304 then means "the committed extract is current" and no ZIP is needed. `refresh`: unconditional. A failed
  download falls back to the committed extract (a file warning; `stats.files[id].status = "stale"`); with nothing at
  all the `files[]` entry gets `error` and there are no records. `EXTRACT_VERSION` (bumped when the selection rules
  change) re-makes outdated extracts from the ZIP.
* **Record fields**: `number` whitespace-collapsed as printed (zg: `numer_ewidencyjny_urzad`, also `case_sign`);
  `date_raw` as printed (`2026-10-14 00:00:00`); zg `filed_date` = `date`; `period` = month of `date`.
  `parcels[].obreb` in the Warsaw notation `Z-SS-NN` (zone digit of the unit, as in `baipp.OBREB_ZONES`): `3-06-05`,
  Śródmieście `5-06-11`; as printed for a `146507_8` code that is no Praga-Południe precinct (`normalize.PP_OBREBY`;
  warning "obręb „0002” nie występuje na Pradze-Południe (nie ma go w ewidencji gruntów dzielnicy) – możliwy błąd w
  rejestrze") or a unit outside Warsaw; `partial` always false; a row without obręb/number gives no parcel (warning). `parcels_raw` = the
  register's "unit obręb number" per row, joined " | ". `address.display` = [cecha unless "ul."/"inne" or already in
  the name] + `ulica_dalej` + `ulica` + `nr_domu` ("Andrzeja Czapskiego 3", "Aleja Jerzego Waszyngtona 96",
  `gen. Augusta Emila Fieldorfa "Nila" 12`, "os. Przyjaźni 3"); `address.street` = `ulica` without quotes
  ("Fieldorfa Nila"), for "Aleja X Y" names also without "Aleja" and leading first names ("Waszyngtona"); register
  spellings that would not match the other datasets are mapped with a warning (`STREET_FIXES`: "Jeziorańskiego" →
  "Nowaka-Jeziorańskiego"), and the street gets the one spelling of `normalize.STREET_CANONICAL` ("Fieldorfa Nila" →
  "Fieldorfa"); a cadastral unit id typed as `nr_domu` ("146507_8") is dropped with a warning; `address.raw` =
  "ul. Andrzeja Czapskiego 3".
* **permit**: `scope` from the register vocabulary – exactly 6 values nationwide: `budowa | rozbudowa | nadbudowa |
  odbudowa | rozbiorka | inne` ("wykonanie robót budowlanych innych niż wymienione powyżej"); the register has no
  "przebudowa" value (it falls under `inne`); unknown wording → null + warning. `category_label` = the official
  wording. `cubature`: a number (int when integral); `2.03804e+06` is accepted with a "zaokrąglenie" warning; the
  placeholders `0` / `1` (189 cases) → null. `outcome` is always null; a `/O` number suffix only adds a warning.
* **tags** = `classify(investment)` ∪ the scope's works tag (budowa → `nowa-budowa`, rozbudowa/nadbudowa →
  `rozbudowa-przebudowa`, rozbiorka → `rozbiorka`) ∪ – only when the text names no function – the category's function
  tag (`CATEGORY_TAGS`: I `jednorodzinny`, XIII `wielorodzinny`, XXVI `infrastruktura`, XVII `uslugi` …) or else
  `jednorodzinny` for `single_family`; a `nowa-budowa` read from a text that merely starts with "budynek…" is dropped
  when the scope is not budowa. `classify.TAGS` gained `instalacje-wewnetrzne` (funkcja: gas/water/heating
  installations inside buildings, ~430 permits, no longer counted as `infrastruktura` networks) and `remont` (roboty);
  the tags of every district record are unchanged.
* `sources[0].raw`: header order, designer columns removed, parcel-level columns (unit, obręb, parcel, sheet, old
  numbering) joined " | " (`""` when all empty), case-level columns de-duplicated (rows that differ → warning).
* Ids as in the contract (digits as printed; another shape → the whole number slugged); the same register number in
  two archives would be merged into one record, different numbers with the same slug get `-2` (none on 2026-10-22).
* `files[]` entry: `file_id, source, url, dataset_url, licence, filename (the ZIP), zip_member, ext "csv",
  category (pb|zg), period null, page_ids ["rwdz"], local_path "data/raw/rwdz/<id>.csv", archive_path
  "sources/rwdz/<id>.csv", sha256, size (of the extract), etag, last_modified, sha256_zip, size_zip, downloaded_at,
  rows_total, parsed_count, record_ids (file order), kind_detected, layout "rwdz-wnioski"|"rwdz-zgloszenia",
  history [], warnings[, error]`; the `rwdz` page's blocks also carry `parsed_count` and `count_mismatch: false`.
* For the build: mirror `data/raw/rwdz/*.csv` **and** `*.meta.json` (the line map) to `site/sources/rwdz/`.

### Output files

* `records.json`: district + BAiPP records (kinds wz/cp/ws) + dictionaries for ALL kinds and new dictionaries:
  `datasets {district|baipp|rwdz: {label, short, publisher, url, licence?, description}}`,
  `issuers {district|city|voivode|other: {label}}`, `outcomes {granted|refusal|…: {label}}`,
  `permit_scopes {slug: {label}}`, `permit_categories {"XIII": {label}}`, and `counts_by_kind {wz: n, …, pb: n, zg: n}`
  (so the UI can show opt-in chip counts before permits.json is loaded).
* `permits.json`: `{generated_at, count, records: [Record…]}` — pb + zg only, same Record schema, newest first.
* `parcels.geojson`: parcels of records.json records; `parcels-permits.geojson`: parcels used only by permits.json
  records (lazy). A parcel used by both lives in `parcels.geojson`; feature `properties.records` lists ids from both files.
* `related` is computed across ALL datasets (a WZ decision may relate to a pb permit on the same parcel and vice
  versa). The UI loads `permits.json` on demand to render related permits.
* `records.csv` gets the new columns (dataset, issuer, outcome, filed_date, permit scope/category); `permits.csv`
  holds pb/zg (same columns). Feed: district + BAiPP only (permits would flood it).
* CSV columns v2 (browser export `site/js/csv.js CSV_COLUMNS` and `pipeline/export.py` must stay identical — a
  pytest parses csv.js): the v1 columns unchanged and in the same order, then appended:
  `zrodlo_danych` (datasets[].label), `organ` (issuers[].label), `rozstrzygniecie` (outcomes[].label or empty),
  `data_wniosku` (filed_date), `nr_w_rejestrze` (permit.register_id), `znak_sprawy_urzedu` (permit.case_sign),
  `zakres_robot` (permit.scope_label), `kategoria_obiektu` ("XIII – label"), `kubatura_m3` (decimal comma).

### Build integration v2 – as implemented (`build.py`, `export.py`, `geocode.py`; 2026-10-23)

How the three datasets come together, and the small extensions of the "Output files" rules above:

* **Stage order** (`run_build`): crawl (district + BAiPP) → parse/normalise/merge the workbooks → **RWDZ**
  (`build.obtain_permits` → `rwdz.run_rwdz`) → BAiPP out-of-district check → **one** `geocode.locate_records` pass over
  the planning records (minus the out-of-district ones) **and** the permits (shared caches, one polite session) →
  RWDZ out-of-district check (unplaced permits) → `related` over all datasets (with the corrected parcel ids) →
  outputs. Record ids must be unique across datasets (namespaced by design; a duplicate
  is a `BuildError`).
* **RWDZ modes**: the GUNB files are downloaded with the crawl (`online = crawl and online`); `--skip-crawl` and
  `--offline` build from the committed extracts. `run_build(rwdz=None)` includes the dataset whenever possible (online,
  or when `data/raw/rwdz/` exists); an offline build of a project that never fetched RWDZ leaves it out entirely
  (`kinds`, `counts_by_kind` and `datasets` then omit pb/zg/rwdz, `permit_*` are `{}`, `permits.json` is empty).
  `RwdzFormatError` while online → the committed extracts are used, the report starts with a warning and the exit code
  is **3** (CI then commits/deploys nothing); an edited committed extract (SHA-256 ≠ sidecar) → exit code **1**.
  `run_build(session=…)` serves the crawler and the RWDZ download.
* **records.json**: `kinds` lists all five (`pb`/`zg` = `rwdz.KIND_META`); `datasets.rwdz` = `rwdz.DATASET_META`
  (adds `dataset_url`, `licence_url`); `permit_scopes` = `{slug: {label}}`; `permit_categories` = `{roman: {label,
  description}}` (`description` = "Kategoria XIII – <official annex wording>"); `counts_by_kind` counts both files.
  `issuers` labels name the handling office ("Urząd Dzielnicy Praga-Południe (Wydział Architektury i Budownictwa)",
  "Urząd m.st. Warszawy (Biuro Architektury i Planowania Przestrzennego)") – the legal authority of both is the
  Prezydent m.st. Warszawy, which is also how GUNB names them.
* **permits.json** `{generated_at, count, records}` shares `generated_at` with records.json (one timestamp per build).
* **parcels.geojson / parcels-permits.geojson** (`build.split_parcels`): a feature goes to `parcels.geojson` when any
  id in its `properties.records` belongs to records.json (the list keeps the permit ids too), else to
  `parcels-permits.geojson`. Both have the same `attribution`/`source`. Parcels of other units named by a permit
  (`146510_8.…`) are ordinary ULDK features.
* **sources.json**: `pages` = manifest pages, then the `rwdz` pseudo-page; `files` = manifest files, then the three RWDZ
  entries as `run_rwdz` returns them, with `archive_path` set only when the mirrored copy exists and *ext*
  **`archive_meta_path`** = `sources/rwdz/<file_id>.meta.json` (the mirrored sidecar: snapshot metadata and the original
  line number of every extract line). The build never parses a manifest file whose `source` is not district/BAiPP.
* **Mirror**: `site/sources/rwdz/<file_id>.csv` + `.meta.json` = byte copies of `data/raw/rwdz/` (rewritten only when
  different); stale `rwdz-*.csv` / `rwdz-*.meta.json` copies are removed, other files there are left alone.
* **CSV** (`export.records_to_csv(…, datasets, issuers, outcomes, categories)`): `records.csv` = records.json,
  `permits.csv` = permits.json, both with the v2 columns. Dictionary labels fall back to the code like `csv.js`;
  `kategoria_obiektu` = `export.category_text` ("XIII – " + the record's `category_label`, else the dictionary label;
  "XIII" alone without one); `arkusz_wiersz` of an RWDZ source is `"!<original line>"` (no sheet), exactly as
  `csv.js` renders it; *ext (2026-10-23):* a blank sheet name (BAiPP's sheet " ") reads `"(arkusz bez nazwy)!26"`
  (and "(arkusz bez nazwy, wiersz 26)" in the feed); `csv.js` renders it the same way (`sheetName()`), so the browser
  CSV and `records.csv` agree cell for cell.
* **Feed**: district + BAiPP records only. An outcome other than `granted` is named in the entry title
  ("WZ (odmowa) · 95/AM/PPD/WZ/2026/O · …") and content ("Rozstrzygnięcie: Odmowa"); the content also names the
  dataset ("Źródło danych: …"). Subtitle/rights mention both publishers.
* **Geolocation tweak** (`geocode._parcel_geo`): when the area-weighted centroid of the found parcels lies on none of
  them (two separate plots, a bent road), the point goes to the **largest** parcel of the main cluster (preferring
  parcels whose centroid is in the district): its centroid, or – for a concave parcel whose centroid falls outside it –
  the middle of the widest inside stretch of the horizontal line through that centroid. `geo.note`, `parcels_found`
  and `bbox` are unchanged; `stats.records_point_on_largest_parcel` counts these records. When the point falls
  outside the district but some found parcels lie in it (permits whose case also covers Rembertów or Śródmieście
  parcels), the point is computed from the in-district parcels alone (same rules) with the note "część działek leży
  poza dzielnicą – punkt wyznaczono z działek na Pradze-Południe" (`stats.records_parcels_in_district_only`);
  `parcels_found` still lists every parcel. Only when no found parcel is in the district is the point discarded.
* **Report** (`data/report.md`): totals per dataset; district declared-vs-parsed and numbering gaps (district only);
  the BAiPP section; a **GUNB RWDZ** section (snapshot per archive: Last-Modified, rows in the file vs Praga-Południe
  rows vs records, link to the extract; records per year × kind; issuer, scope, category and investor type per kind;
  application → decision time; cubature coverage; rows kept / not kept by the district-office unit rule and
  `UNIT_FIXES`, unkept cases with Praga-Południe signs, permits moved out of the district; cases with
  parcels in other districts); **related records across datasets** (how many WZ/ULICP records relate to permits, WZ/CP
  decisions followed by a building permit on the same parcel and the median delay); geolocation, location notes,
  warnings and tags **per dataset**; *ext:* street names still written several ways, precincts corrected by
  the address, flagged address/parcel conflicts, files that cannot be read any more. Still no timings or request counts, and nothing that differs between an online
  run answered with 304 and an offline run (a test asserts that such a run writes nothing).

### Pipeline round 3 – additive fields (2026-10-23)

All optional (absent = as before); the frontend reads `geo.conflict` and `geo.uncertainty_m` only when present.

* `geo.conflict: true` – only on records whose exact address lies > 300 m from their parcels **and** on a parcel of a
  precinct the record does not name (another number): the parcel point is kept but is less certain than an exact
  address point. The UI draws a hollow marker and reads "Lokalizacja niepewna – adres i działki się różnią" (9 permits
  today).
* `geo.uncertainty_m` – `street` method only: the largest distance (m, rounded to 10) from the point to the street
  stretch it stands for (the stretch in the stated precinct, else the street in the district). The UI draws it as a
  dashed circle, names it ("w promieniu ok. N m") and lets "W pobliżu" match a point whose circle reaches the radius.
* `parcels[].incomplete: true` – the number was cut short in the source (`12/`).
* manifest `stale_pages` (crawler → build), sidecar `signal_cases_not_kept` (RWDZ), `BuildResult.lost_files`.
* Rewritten values (no new keys): `parcels[].id/obreb` of records whose precinct the address corrected, or that lie in
  another district (RWDZ); `address.street`/`parts[].street` in the canonical spelling; note and warning wording
  ("na Pradze-Południe", "ewidencja gruntów (ULDK)"); the CP wording of the dataset/kind descriptions and the feed
  title ("decyzje celu publicznego (CP)").
