# wzSearch – data-quality report

Generated `2026-10-24T21:00:09Z` by `pipeline/build.py` from the district's [source index](https://pragapld.um.warszawa.pl/informacja-o-wszczetych-postepowaniach-oraz-wydanych-decyzjach-administracyjnych), the [BAiPP lists](https://architektura.um.warszawa.pl/postepowania-i-decyzje) and GUNB's [RWDZ register](https://wyszukiwarka.gunb.gov.pl/pobranie.html). Regenerated on every build; do not edit.

## Totals

* Records per dataset: Dzielnica 474, BAiPP (miasto) 104, GUNB RWDZ 2591 – `records.json` 578, `permits.json` 2591.
* Monthly pages: **73** (2020-08 → 2026-09); source files: **176** (168 with rows, 8 empty templates, 0 unreadable/missing).
* Workbook data rows kept (district + BAiPP): **578** → records after merging duplicates: **578** (WZ 232, CP 97, Wszczęcie 249).
* Building permits and notifications (RWDZ): **2591** (Pozwolenie 2365, Zgłoszenie 226).
* Records listed in more than one source row: 0.
* Procedure (WZ vs public purpose, incl. initiated proceedings): cp 138, wz 440.
* Applicants (WZ/ULICP): natural persons 195, organisations 383, unknown 0.

WZ/ULICP records per year (decision / initiation date):

| Year | WZ | CP | Wszczęcie | Total |
|---|---:|---:|---:|---:|
| 2020 | 17 | 11 | 21 | 49 |
| 2021 | 62 | 14 | 58 | 134 |
| 2022 | 40 | 27 | 45 | 112 |
| 2023 | 44 | 18 | 43 | 105 |
| 2024 | 22 | 11 | 17 | 50 |
| 2025 | 31 | 13 | 36 | 80 |
| 2026 | 16 | 3 | 29 | 48 |
| **all** | **232** | **97** | **249** | **578** |

## Declared vs parsed counts

Each monthly page states how many entries each list has ("3 pozycje"). `parsed` counts the data rows read from the files first published on that page (a leftover link to an earlier month's file is not counted twice).

| Kind | Declared (blocks with a number) | Parsed in those blocks | Parsed in blocks without a number | Parsed rows | Duplicates merged | Records |
|---|---:|---:|---:|---:|---:|---:|
| WZ | 169 | 167 | 9 | 176 | 0 | 176 |
| CP | 72 | 72 | 10 | 82 | 0 | 82 |
| Wszczęcie | 202 | 202 | 14 | 216 | 0 | 216 |

**1 block(s) where the declared count differs from the file:**

| Month | Block text | Declared | Parsed | Files |
|---|---|---:|---:|---|
| [Grudzień 2020 r.](https://pragapld.um.warszawa.pl/-/informacje-o-wszczetych-postepowaniach-grudzien-2020) | Wydane decyzje o warunkach zabudowy za grudzień 2020r. – 3 pozycje – plik do pobrania | 3 | 1 | [wydane decyzje o warunkach zabudowy grudzień-1.xlsx](https://pragapld.um.warszawa.pl/documents/50051/23254498/wydane+decyzje+o+warunkach+zabudowy+grudzie%C5%84-1.xlsx/ffb5b4eb-999d-17df-2ed2-d282be6f2f95?t=1621240835806) |

Blocks that link a file but state no count (8; parsed rows are not checked): [Październik 2020 r.](https://pragapld.um.warszawa.pl/-/informacje-o-wszczetych-postepowaniach-pazdziernik-2020) CP → 2; [Październik 2020 r.](https://pragapld.um.warszawa.pl/-/informacje-o-wszczetych-postepowaniach-pazdziernik-2020) WZ → 5; [Wrzesień 2020 r.](https://pragapld.um.warszawa.pl/-/informacje-o-wszczetych-postepowaniach-wrzesien-2020) Wszczęcie → 5; [Wrzesień 2020 r.](https://pragapld.um.warszawa.pl/-/informacje-o-wszczetych-postepowaniach-wrzesien-2020) WZ → 3; [Wrzesień 2020 r.](https://pragapld.um.warszawa.pl/-/informacje-o-wszczetych-postepowaniach-wrzesien-2020) CP → 3; [Sierpień 2020 r.](https://pragapld.um.warszawa.pl/-/informacje-o-wszczetych-postepowaniach-sierpien-2020) Wszczęcie → 9; [Sierpień 2020 r.](https://pragapld.um.warszawa.pl/-/informacje-o-wszczetych-postepowaniach-sierpien-2020) WZ → 1; [Sierpień 2020 r.](https://pragapld.um.warszawa.pl/-/informacje-o-wszczetych-postepowaniach-sierpien-2020) CP → 5.

Blocks linking several files (the extra link points to an earlier month's file, counted on its own page): [Październik 2025](https://pragapld.um.warszawa.pl/-/artykul-93) WZ; [Październik 2022 r.](https://pragapld.um.warszawa.pl/-/pazdziernik-2022) CP.

## Completeness: gaps in decision numbering

WZ and CP decisions are numbered consecutively per year, so a number that never appears in any file is a decision that was not published in these lists (or a refusal/discontinuation the office does not list). Numbering restarts every year at 1; in the first year only numbers after the lowest one seen count, because the publication started in August 2020. (District numbering only: BAiPP numbers its decisions city-wide.)

| Kind | Year | Published | Range seen | Missing | Missing numbers |
|---|---|---:|---|---:|---|
| CP | 2020 | 11 | 24–34 | 0 | — |
| CP | 2021 | 13 | 1–14 | 1 | 11 |
| CP | 2022 | 21 | 1–22 | 1 | 17 |
| CP | 2023 | 11 | 1–11 | 0 | — |
| CP | 2024 | 11 | 4–16 | 5 | 1, 2, 3, 8, 10 |
| CP | 2025 | 12 | 1–16 | 4 | 7, 9, 10, 12 |
| CP | 2026 | 3 | 1–3 | 0 | — |
| WZ | 2020 | 13 | 16–30 | 2 | 28, 29 |
| WZ | 2021 | 52 | 1–52 | 0 | — |
| WZ | 2022 | 35 | 1–35 | 0 | — |
| WZ | 2023 | 26 | 1–27 | 1 | 26 |
| WZ | 2024 | 13 | 3–24 | 11 | 1, 2, 4, 5, 7, 13, 15, 16, 18, 22, 23 |
| WZ | 2025 | 22 | 1–38 | 16 | 2, 3, 6, 8, 9, 10, 14, 15, 19, 21, 27, 28, 31, 32, 34, 37 |
| WZ | 2026 | 15 | 1–17 | 2 | 10, 14 |

Initiated proceedings use case signs whose numbering is shared with other cases of the same JRWA symbol, so gaps there are expected and not listed.

## BAiPP (city architecture bureau) lists

Biuro Architektury i Planowania Przestrzennego publishes the same three lists for the whole city, one file per year and list (the current year's files are replaced every month; every snapshot we downloaded is kept). Only rows whose address names Praga-Południe on its last line become records.

| Page | Year | List | File | City-wide rows | Praga-Południe rows | Records |
|---|---|---|---|---:|---:|---:|
| [Informacja o wszczętych postępowaniach i wydanych decyzjach administracyjnych](https://architektura.um.warszawa.pl/postepowania-i-decyzje) | 2026 | WZ | [informacja_o_wydanych_decyzjach_WZ_IX_2026 +.xlsx](https://architektura.um.warszawa.pl/documents/12025039/171613001/informacja_o_wydanych_decyzjach_WZ_IX_2026+%2B.xlsx/1d75d6d6-239a-2dc1-843b-70184b23709c?t=1791798490945) | 101 | 1 | 1 |
| [Informacja o wszczętych postępowaniach i wydanych decyzjach administracyjnych](https://architektura.um.warszawa.pl/postepowania-i-decyzje) | 2026 | wszczęte | [informacja_o_wszczętych_postępowaniach_o_WZ_LICP_IX_2026 +.xlsx](https://architektura.um.warszawa.pl/documents/12025039/171613001/informacja_o_wszcz%C4%99tych_post%C4%99powaniach_o_WZ_LICP_IX_2026+%2B.xlsx/289a1962-288a-3179-aabf-643286f2a106?t=1791798491258) | 85 | 2 | 2 |
| [Informacja o wszczętych postępowaniach i wydanych decyzjach administracyjnych](https://architektura.um.warszawa.pl/postepowania-i-decyzje) | 2026 | ULICP C2 | [informacja_o_wydanych_decyzjach_ustalenie_LICP_o_znaczeniu_powiatowym _i_gminnym_IX_2026 +.xlsx](https://architektura.um.warszawa.pl/documents/12025039/171613001/informacja_o_wydanych_decyzjach_ustalenie_LICP_o_znaczeniu_powiatowym+_i_gminnym_IX_2026+%2B.xlsx/7dbca2ea-686b-0157-caa3-134d35570f6b?t=1791798490447) | 6 | 0 | 0 |
| [Informacja o wszczętych postępowaniach i wydanych decyzjach administracyjnych](https://architektura.um.warszawa.pl/postepowania-i-decyzje) | 2026 | ULICP C1 | [informacja_o_wydanych_decyzjach_o_ustaleniu_LICP_o_znaczeniu_krajowym_i_wojódzkim_IX_2026 +.xlsx](https://architektura.um.warszawa.pl/documents/12025039/171613001/informacja_o_wydanych_decyzjach_o_ustaleniu_LICP_o_znaczeniu_krajowym_i_woj%C3%B3dzkim_IX_2026+%2B.xlsx/fae00082-7a3e-6cb0-d96c-6a3104611a81?t=1791798491576) | 5 | 0 | 0 |
| [Informacja o wszczętych postępowaniach i wydanych decyzjach (2025 r.)](https://architektura.um.warszawa.pl/-/rejestry25) | 2025 | WZ | [informacja o wydanych decyzjach_wz_XII_25 +.xlsx](https://architektura.um.warszawa.pl/documents/12025039/152228831/informacja+o+wydanych+decyzjach_wz_XII_25+%2B.xlsx/cb763523-543a-dc26-c549-da9e662d76c8?t=1768389582758) | 125 | 9 | 9 |
| [Informacja o wszczętych postępowaniach i wydanych decyzjach (2025 r.)](https://architektura.um.warszawa.pl/-/rejestry25) | 2025 | wszczęte | [informacja o wszczętych postępowaniach o wz,licp_XII_25.xlsx](https://architektura.um.warszawa.pl/documents/12025039/152228831/informacja+o+wszcz%C4%99tych+post%C4%99powaniach+o+wz%2Clicp_XII_25.xlsx/ec2f3679-1303-b07d-d372-2b59bbad3874?t=1768389583052) | 94 | 3 | 3 |
| [Informacja o wszczętych postępowaniach i wydanych decyzjach (2025 r.)](https://architektura.um.warszawa.pl/-/rejestry25) | 2025 | ULICP C2 | [informacja o wydanych decyzjach ws. ustalenia_licp_pow-gm_XII_25 +.xlsx](https://architektura.um.warszawa.pl/documents/12025039/152228831/informacja+o+wydanych+decyzjach+ws.+ustalenia_licp_pow-gm_XII_25+%2B.xlsx/b7892448-d604-fd62-1991-5e616a15c926?t=1768389582390) | 10 | 1 | 1 |
| [Informacja o wszczętych postępowaniach i wydanych decyzjach (2025 r.)](https://architektura.um.warszawa.pl/-/rejestry25) | 2025 | ULICP C1 | [informacja o wydanych decyzjach ws. ustalenia_licp_kraj-woj_XII_25 +.xlsx](https://architektura.um.warszawa.pl/documents/12025039/152228831/informacja+o+wydanych+decyzjach+ws.+ustalenia_licp_kraj-woj_XII_25+%2B.xlsx/2da6e58f-949a-53ac-753b-1c4c5ea66ec1?t=1768389583415) | 3 | 0 | 0 |
| [Informacja o wszczętych postępowaniach i wydanych decyzjach (2024 r.)](https://architektura.um.warszawa.pl/-/rejestry24) | 2024 | WZ | [ok informacja o wydanych decyzjach_wz_XII_24.xlsx](https://architektura.um.warszawa.pl/documents/12025039/126236715/ok+informacja+o+wydanych+decyzjach_wz_XII_24.xlsx/15e07f89-83f4-cfca-59c1-6d57315fa265?t=1736763576457) | 139 | 8 | 8 |
| [Informacja o wszczętych postępowaniach i wydanych decyzjach (2024 r.)](https://architektura.um.warszawa.pl/-/rejestry24) | 2024 | wszczęte | [informacja o wszczętych postępowaniach o wz,licp_XII_24.xlsx](https://architektura.um.warszawa.pl/documents/12025039/126431210/informacja+o+wszcz%C4%99tych+post%C4%99powaniach+o+wz%2Clicp_XII_24.xlsx/4a5a7f4b-0273-862c-797a-49db36efa218?t=1736871824094) | 79 | 2 | 2 |
| [Informacja o wszczętych postępowaniach i wydanych decyzjach (2024 r.)](https://architektura.um.warszawa.pl/-/rejestry24) | 2024 | ULICP C2 | [informacja o wydanych decyzjach ws. ustalenia_licp_pow-gm_XII_24.xlsx](https://architektura.um.warszawa.pl/documents/12025039/126431210/informacja+o+wydanych+decyzjach+ws.+ustalenia_licp_pow-gm_XII_24.xlsx/fcefbea9-393b-e177-186c-d7656b49a71b?t=1736871823203) | 20 | 0 | 0 |
| [Informacja o wszczętych postępowaniach i wydanych decyzjach (2024 r.)](https://architektura.um.warszawa.pl/-/rejestry24) | 2024 | ULICP C1 | [informacja o wydanych decyzjach ws. ustalenia_licp_kraj-woj_XII_24.xlsx](https://architektura.um.warszawa.pl/documents/12025039/126431210/informacja+o+wydanych+decyzjach+ws.+ustalenia_licp_kraj-woj_XII_24.xlsx/fbe4067e-4dd1-3f6b-3609-d0761c8c2cf4?t=1736871824369) | 1 | 0 | 0 |
| [Informacja o wszczętych postępowaniach i wydanych decyzjach (2023 r.)](https://architektura.um.warszawa.pl/-/rejestry23) | 2023 | WZ | [informacja o wydanych decyzjach_wz_XII_23 +.xlsx](https://architektura.um.warszawa.pl/documents/12025039/96120640/informacja+o+wydanych+decyzjach_wz_XII_23+%2B.xlsx/23cbd9fa-abb7-248d-4b9e-106e78a8cf5a?t=1705311090486) | 155 | 19 | 19 |
| [Informacja o wszczętych postępowaniach i wydanych decyzjach (2023 r.)](https://architektura.um.warszawa.pl/-/rejestry23) | 2023 | wszczęte | [ok informacja o wszczętych postępowaniach o wz,licp_XII_23+.xlsx](https://architektura.um.warszawa.pl/documents/12025039/96120640/ok+informacja+o+wszcz%C4%99tych+post%C4%99powaniach+o+wz%2Clicp_XII_23%2B.xlsx/d4c09d57-96e8-cca9-48a1-384eab9dca3a?t=1705311090763) | 123 | 5 | 5 |
| [Informacja o wszczętych postępowaniach i wydanych decyzjach (2023 r.)](https://architektura.um.warszawa.pl/-/rejestry23) | 2023 | ULICP C2 | [informacja o wydanych decyzjach ws. ustalenia_licp_pow-gm_XII_23+.xlsx](https://architektura.um.warszawa.pl/documents/12025039/96120640/informacja+o+wydanych+decyzjach+ws.+ustalenia_licp_pow-gm_XII_23%2B.xlsx/4a9fa06d-a879-922c-3526-ed698e82fa05?t=1705311089886) | 14 | 7 | 7 |
| [Informacja o wszczętych postępowaniach i wydanych decyzjach (2023 r.)](https://architektura.um.warszawa.pl/-/rejestry23) | 2023 | ULICP C1 | [informacja o wydanych decyzjach ws. ustalenia_licp_kraj-woj_XII_23+.xlsx](https://architektura.um.warszawa.pl/documents/12025039/96120640/informacja+o+wydanych+decyzjach+ws.+ustalenia_licp_kraj-woj_XII_23%2B.xlsx/1f343061-c89e-1e20-13e4-6292d3ed2a7a?t=1705311091046) | 1 | 0 | 0 |
| [Informacja o wszczętych postępowaniach i wydanych decyzjach (2022 r.)](https://architektura.um.warszawa.pl/-/rejestry2022) | 2022 | WZ | [informacja o wydanych decyzjach_wz_I-XII_22.xlsx](https://architektura.um.warszawa.pl/documents/12025039/69259400/informacja+o+wydanych+decyzjach_wz_I-XII_22.xlsx/5eb2c695-6228-1b14-4418-9dad94c8db7e?t=1673616553587) | 162 | 5 | 5 |
| [Informacja o wszczętych postępowaniach i wydanych decyzjach (2022 r.)](https://architektura.um.warszawa.pl/-/rejestry2022) | 2022 | wszczęte | [Informacja o wszczętych postępowaniach o wz,licp_I-XII_22.xlsx](https://architektura.um.warszawa.pl/documents/12025039/69259400/Informacja+o+wszcz%C4%99tych+post%C4%99powaniach+o+wz%2Clicp_I-XII_22.xlsx/23b3f50f-30ef-0cf0-7614-bcb5800f6b3d?t=1673616553796) | 86 | 9 | 9 |
| [Informacja o wszczętych postępowaniach i wydanych decyzjach (2022 r.)](https://architektura.um.warszawa.pl/-/rejestry2022) | 2022 | ULICP C2 | [informacja o wydanych decyzjach ws. ustalenia _licp pow-gm_I-XII_22.xlsx](https://architektura.um.warszawa.pl/documents/12025039/69259400/informacja+o+wydanych+decyzjach+ws.+ustalenia+_licp+pow-gm_I-XII_22.xlsx/a2e32ee9-3456-a724-ccf5-1c28d663d01d?t=1673616554019) | 13 | 6 | 6 |
| [Informacja o wszczętych postępowaniach i wydanych decyzjach (2022 r.)](https://architektura.um.warszawa.pl/-/rejestry2022) | 2022 | ULICP C1 | [informacja o wydanych decyzjach ws. ustalenia_licp_kraj-woj_I-XII_22.xlsx](https://architektura.um.warszawa.pl/documents/12025039/69259400/informacja+o+wydanych+decyzjach+ws.+ustalenia_licp_kraj-woj_I-XII_22.xlsx/4f9bfce6-cf90-180e-4f7d-8554d2bced70?t=1673616553272) | 5 | 0 | 0 |
| [Informacja o wszczętych postępowaniach i wydanych decyzjach (2021 r.)](https://architektura.um.warszawa.pl/-/rejestry2021) | 2021 | WZ | [informacja_decyzje_wz_I_XII_21+.xlsx](https://architektura.um.warszawa.pl/documents/12025039/41736355/informacja_decyzje_wz_I_XII_21%2B.xlsx/41a174fa-5a5b-2212-5eae-c0bc4d4b2a40?t=1642178443708) | 157 | 10 | 10 |
| [Informacja o wszczętych postępowaniach i wydanych decyzjach (2021 r.)](https://architektura.um.warszawa.pl/-/rejestry2021) | 2021 | wszczęte | [informacja_wnioski_wz _licp_I-XII_21.xlsx](https://architektura.um.warszawa.pl/documents/12025039/41736355/informacja_wnioski_wz+_licp_I-XII_21.xlsx/c32bf907-1784-ec79-c5c1-5a61265b8bf2?t=1642178443050) | 88 | 8 | 8 |
| [Informacja o wszczętych postępowaniach i wydanych decyzjach (2021 r.)](https://architektura.um.warszawa.pl/-/rejestry2021) | 2021 | ULICP C2 | [informacja_decyzje_licp_pow-gm_I-XII_21+.xlsx](https://architektura.um.warszawa.pl/documents/12025039/41736355/informacja_decyzje_licp_pow-gm_I-XII_21%2B.xlsx/c806117d-5072-c7f1-eef6-28d643a83cad?t=1642178443512) | 12 | 0 | 0 |
| [Informacja o wszczętych postępowaniach i wydanych decyzjach (2021 r.)](https://architektura.um.warszawa.pl/-/rejestry2021) | 2021 | ULICP C1 | [informacje_decyzje_licp_kraj-woj_I-XII_21+.xlsx](https://architektura.um.warszawa.pl/documents/12025039/41736355/informacje_decyzje_licp_kraj-woj_I-XII_21%2B.xlsx/599f76bc-3169-c175-6511-f5f75a015c5e?t=1642178443291) | 5 | 1 | 1 |
| [Informacja o wszczętych postępowaniach i wydanych decyzjach (sierpień - grudzień 2020 r.)](https://architektura.um.warszawa.pl/-/rejestry2020) | 2020 | WZ | [informacja_decyzje_wz_sierpien-grudzien_20.xlsx](https://architektura.um.warszawa.pl/documents/12025039/19717181/informacja_decyzje_wz_sierpien-grudzien_20.xlsx/d2a2aadb-492a-ceb6-4250-685e7ddfe11c?t=1634497931206) | 79 | 4 | 4 |
| [Informacja o wszczętych postępowaniach i wydanych decyzjach (sierpień - grudzień 2020 r.)](https://architektura.um.warszawa.pl/-/rejestry2020) | 2020 | wszczęte | [informacja_wnioski_wz__licp__sierpien-grudzien_20.xlsx](https://architektura.um.warszawa.pl/documents/12025039/19717181/informacja_wnioski_wz__licp__sierpien-grudzien_20.xlsx/efa0401d-4ae2-aec3-d6b6-536680e2e35f?t=1634497931212) | 55 | 4 | 4 |
| [Informacja o wszczętych postępowaniach i wydanych decyzjach (sierpień - grudzień 2020 r.)](https://architektura.um.warszawa.pl/-/rejestry2020) | 2020 | ULICP C2 | [informacja_dec._licp_pow_gmi_sierpien-grudzien_20.xlsx](https://architektura.um.warszawa.pl/documents/12025039/19717181/informacja_dec._licp_pow_gmi_sierpien-grudzien_20.xlsx/3f2da765-50ac-0efc-c47e-a02063a0d05c?t=1634497931200) | 6 | 0 | 0 |
| [Informacja o wszczętych postępowaniach i wydanych decyzjach (sierpień - grudzień 2020 r.)](https://architektura.um.warszawa.pl/-/rejestry2020) | 2020 | ULICP C1 | [informacja_decyzje_licp_kraj_woj_sierpien-_grudzien_20.xlsx](https://architektura.um.warszawa.pl/documents/12025039/19717181/informacja_decyzje_licp_kraj_woj_sierpien-_grudzien_20.xlsx/9fdd4da2-0828-b9a3-089e-f2c4d2dc2d37?t=1634497931193) | 6 | 0 | 0 |

* Records: 104 (WZ 56, CP 15, Wszczęcie 33); decision outcomes: Ustalenie (decyzja pozytywna) 21, Odmowa 5, Umorzenie postępowania 37, Przeniesienie decyzji 6, Wygaśnięcie decyzji 2.
* Listed in more than one snapshot / yearly file: 0.
* Labelled Praga-Południe, but ULDK places the parcels in another district (kept, not on the map): `ws-am-6730-2025-27`.

## GUNB RWDZ (building permits and notifications)

GUNB publishes its register of building-permit decisions and notifications (*Rejestr wniosków, decyzji i zgłoszeń*, CC0 1.0) as three ZIP files rebuilt every night. Every case with a parcel in Praga-Południe (cadastral unit `146507_8`) is copied byte for byte into a committed extract (`data/raw/rwdz/`, mirrored to `site/sources/rwdz/`) and becomes one record in `permits.json`; the snapshot cited is the one the extract was taken from (a new GUNB file that changes nothing in the district is not adopted).

| File | Kind | Snapshot (Last-Modified) | Rows in the file | Praga-Południe rows | Records | Extract |
|---|---|---|---:|---:|---:|---|
| [wynik_mazowieckie.zip](https://wyszukiwarka.gunb.gov.pl/pliki_pobranie/wynik_mazowieckie.zip) | Pozwolenie | 2026-10-23T21:35:17Z | 695500 | 3416 | 2365 | [`sources/rwdz/rwdz-wnioski.csv`](../site/sources/rwdz/rwdz-wnioski.csv) |
| [wynik_zgloszenia_2016_2021.zip](https://wyszukiwarka.gunb.gov.pl/pliki_pobranie/wynik_zgloszenia_2016_2021.zip) | Zgłoszenie | 2026-10-22T21:36:00Z | 829354 | 366 | 121 | [`sources/rwdz/rwdz-zgloszenia-2016-2021.csv`](../site/sources/rwdz/rwdz-zgloszenia-2016-2021.csv) |
| [wynik_zgloszenia_2022_up.zip](https://wyszukiwarka.gunb.gov.pl/pliki_pobranie/wynik_zgloszenia_2022_up.zip) | Zgłoszenie | 2026-10-23T21:36:55Z | 938942 | 213 | 105 | [`sources/rwdz/rwdz-zgloszenia-2022.csv`](../site/sources/rwdz/rwdz-zgloszenia-2022.csv) |

Records per year (decision date for permits, filing date for notifications):

| Year | Pozwolenie | Zgłoszenie | Total |
|---|---:|---:|---:|
| 2016 | 310 | 20 | 330 |
| 2017 | 323 | 15 | 338 |
| 2018 | 292 | 27 | 319 |
| 2019 | 335 | 24 | 359 |
| 2020 | 224 | 22 | 246 |
| 2021 | 201 | 13 | 214 |
| 2022 | 157 | 11 | 168 |
| 2023 | 143 | 7 | 150 |
| 2024 | 141 | 18 | 159 |
| 2025 | 132 | 31 | 163 |
| 2026 | 107 | 38 | 145 |
| **all** | **2365** | **226** | **2591** |

* Issuer: Pozwolenie: Urząd Dzielnicy Praga-Południe (Wydział Architektury i Budownictwa) 2234, Urząd m.st. Warszawy (Biuro Architektury i Planowania Przestrzennego) 121, Wojewoda Mazowiecki 9, Inny organ 1; Zgłoszenie: Urząd Dzielnicy Praga-Południe (Wydział Architektury i Budownictwa) 217, Urząd m.st. Warszawy (Biuro Architektury i Planowania Przestrzennego) 6, Wojewoda Mazowiecki 3.
* Scope of works: Pozwolenie: Inne roboty budowlane (np. przebudowa, remont) 1458, Budowa nowego obiektu 490, Rozbiórka 240, Rozbudowa 133, Nadbudowa 40, Odbudowa 3, nie podano 1; Zgłoszenie: Budowa nowego obiektu 185, Rozbudowa 39, Odbudowa 2.
* Object category: Pozwolenie: XIII 946, VIII 501, I 285, XXVI 112, XVII 111, XI 87, IX 61, XVI 60, XVIII 58, III 45, XIV 20, XII 13, IV 8, X 8, XXV 8, V 7, XV 7, XXII 7, XX 5, XIX 4, XXVIII 3, VII 2, XXIX 2, XXX 2, XXIII 1, XXIV 1, – 1; Zgłoszenie: XXVI 161, XIII 28, VIII 16, I 8, IX 4, XVII 3, IV 2, XVI 2, XVIII 2.
* Investor: Pozwolenie: organisation 1620, natural person (not named by GUNB) 745; Zgłoszenie: not published 226.
* Application → decision (permits): median 52 days, 90th percentile 133 days.
* Cubature given: 1096 of 2591 records (the placeholders 0 and 1 count as not given).
* Without a parcel in the register: 5 (`pb-st-mz-pa-2025-785`, `pb-st-mz-pa-2018-42053`, `pb-st-mz-pa-2018-18856`, `pb-st-mz-pa-2016-6351`, `pb-st-mz-pa-2016-6365`).
* Cases that also cover parcels of other districts (kept whole, those parcels keep their unit): 3 (`pb-st-mz-wa-2017-11062`, `pb-st-mz-wa-2016-41260`, `pb-st-mz-wa-2016-19462`).

Register rows of the district office (*Prezydent Miasta Warszawa - Praga Płd.*) with a broken cadastral unit are kept and corrected to `146507_8` (a warning on the record), and so are the rows of the cases in `rwdz.UNIT_FIXES` (`listed`: register errors checked one by one in ULDK, any organ); a valid other Warsaw unit two or more edits away is genuine and not kept:

* `rwdz-wnioski`: kept – empty 4, invalid 2, listed 6, typo 15; not kept – `146514_8` (Wawer) 19.
* `rwdz-zgloszenia-2016-2021`: kept – typo 2; not kept – none.
* `rwdz-zgloszenia-2022`: kept – typo 1; not kept – none.
* Records with a corrected unit: 27 (`pb-st-mz-pa-2026-16095`, `pb-st-mz-pa-2026-13353`, `pb-pl-mz-2026-15131`, `pb-st-mz-pa-2025-36484`, `pb-st-mz-pa-2024-14200`, `pb-st-mz-pa-2024-8401`, `pb-st-mz-wa-2023-19454`, `zg-st-mz-pa-2023-8611`, `pb-st-mz-pa-2023-20999`, `pb-st-mz-pa-2023-11975`, `pb-st-mz-pa-2023-4701`, `pb-st-mz-pa-2020-25855`, `pb-st-mz-pa-2020-25862`, `pb-st-mz-pa-2020-25846`, `pb-st-mz-pa-2020-25840`, `pb-st-mz-pa-2020-25833`, `pb-st-mz-pa-2020-25838`, `zg-st-mz-pa-2020-3106`, `pb-st-mz-pa-2018-42053`, `pb-st-mz-wa-2018-37134` … and 7 more).
* Unit `146507_8` in the register with a precinct Praga-Południe does not have; ULDK places the parcel (or its precinct) in the district the case names (kept, not on the map): 4 (`pb-st-mz-wa-2022-11434`, `pb-st-mz-pa-2021-49120`, `pb-st-mz-wa-2019-27453`, `pb-st-mz-pg-2016-6120`).
* Not kept, but the case sign (`UD-VI-…`) or the decision number (`…/PPD/…`, `…/PRD/…`) points to Praga-Południe – check the parcel in ULDK and add a register error to `rwdz.UNIT_FIXES` (4): `ST-MZ-WA/WNIOSEK/43874/2016` (`rwdz-wnioski` line 101690, unit `146510_8`), `ST-MZ-WA/WNIOSEK/27690/2025` (`rwdz-wnioski` line 257059, unit `146508_8`), `ST-MZ-WA/WNIOSEK/32369/2024` (`rwdz-wnioski` line 342029, unit `146508_8`), `ST-MZ-WA/WNIOSEK/23628/2022` (`rwdz-wnioski` line 587074, unit `146508_8`).

## Related records across datasets

`related` links records that share a cadastral parcel or a street + house number, across all three datasets. A shared parcel is not necessarily the same project (a large housing-estate parcel carries many unrelated renovations).

* Dzielnica: 339 of 474 records relate to at least one permit or notification.
* BAiPP (miasto): 84 of 104 records relate to at least one permit or notification.
* GUNB RWDZ: 442 of 2591 permits/notifications relate to a WZ/ULICP record.
* WZ decisions (not refused/discontinued) followed by a building permit on the same parcel: 87 of 188 (median 284 days to the first such permit).
* CP decisions (not refused/discontinued) followed by a building permit on the same parcel: 62 of 91 (median 244 days to the first such permit).
* Most related: `wz-am-2020-123` (63), `cp-2022-3` (54), `ws-6733-2022-7` (54), `ws-6733-2022-10` (53), `ws-6733-2022-11` (53).

## Geolocation

| Method | Dzielnica | BAiPP (miasto) | GUNB RWDZ |
|---|---:|---:|---:|
| parcel (ULDK centroid) | 451 (95.1%) | 97 (93.3%) | 2469 (95.3%) |
| address point (UUG) | 6 (1.3%) | 0 (0.0%) | 79 (3.0%) |
| street / crossing (approximate) | 17 (3.6%) | 6 (5.8%) | 37 (1.4%) |
| not located | 0 (0.0%) | 1 (1.0%) | 6 (0.2%) |
| **located** | **474** (**100.0%**) | **103** (**99.0%**) | **2585** (**99.8%**) |

* Unique parcel ids (all datasets): 2678; found in ULDK 2408 (89.9%), missing 270, lookup errors 0.
* Records with parcels: 3163 – all found 2794, some 156, none 213.
* Precinct of the source corrected by the parcel under the exact address (ULDK GetParcelByXY; a warning on the record): 38.
* Address vs parcel conflicts (> 300 m; parcel point kept): 17, of which the address lies on a parcel of another precinct (`geo.conflict`): 9; parcels > 1 km apart: 1; point moved onto the largest parcel (centroid on none of them): 202; point from the parcels in the district only (others lie in a neighbouring district): 1; points discarded outside the district: 0.
* Parcel ids ULDK does not know (first 20): `146507_8.0405.10/2`, `146507_8.0405.10/9`, `146507_8.0405.10/32`, `146507_8.0532.68`, `146507_8.0206.43/4`, `146507_8.0206.86/1`, `146507_8.0212.315`, `146507_8.0212.160`, `146507_8.0606.12`, `146507_8.0607.3/16`, `146507_8.0524.7/3`, `146507_8.0212.8/2`, `146507_8.0212.17/3`, `146507_8.0605.14/1`, `146507_8.0203.15`, `146507_8.0202.1/9`, `146507_8.0202.11/1`, `146507_8.0202.32`, `146507_8.0607.88`, `146507_8.0603.36`.
* Records per MSI area (Dzielnica): goclaw 125, goclawek 50, grochow 210, kamionek 55, olszynka-grochowska 11, saska-kepa 23.
* Records per MSI area (BAiPP (miasto)): (none) 1, goclaw 55, grochow 22, kamionek 19, saska-kepa 7.
* Records per MSI area (GUNB RWDZ): (none) 6, goclaw 334, goclawek 473, grochow 774, kamionek 355, olszynka-grochowska 17, saska-kepa 632.

BAiPP (miasto) records without a location (1):

| Record | Address | Parcels (as in source) | Note |
|---|---|---|---|
| `ws-am-6730-2025-27` | Sokola / Zamoście / Wybrzeże Szczecińskie | 18/5; 4-15-08 | działki poza dzielnicą Praga-Południe według ewidencji gruntów (ULDK) – nie pokazano na mapie |

GUNB RWDZ records without a location (6):

| Record | Address | Parcels (as in source) | Note |
|---|---|---|---|
| `pb-st-mz-wa-2022-11434` | Kijowska | 146507_8 1406 36/2 | działki poza dzielnicą Praga-Południe według ewidencji gruntów (ULDK) – nie pokazano na mapie |
| `pb-st-mz-pa-2021-49120` |  | 146507_8 1122 117/50 | działki poza dzielnicą Praga-Południe według ewidencji gruntów (ULDK) – nie pokazano na mapie |
| `pb-st-mz-wa-2019-27453` | Kawęczyńska 161 | 146507_8 1406 11 | działki poza dzielnicą Praga-Południe według ewidencji gruntów (ULDK) – nie pokazano na mapie |
| `pb-st-mz-wa-2018-40659` |  | 146507_8 0202 18/16 | działek nie znaleziono w ewidencji gruntów (ULDK) – mogły zostać podzielone lub scalone; nie udało się ustalić lokalizacji |
| `pb-st-mz-wa-2018-7500` |  | 146507_8 0524 35/4 | działek nie znaleziono w ewidencji gruntów (ULDK) – mogły zostać podzielone lub scalone; nie udało się ustalić lokalizacji |
| `pb-st-mz-pg-2016-6120` |  | 146507_8 1507 3 | działki poza dzielnicą Praga-Południe według ewidencji gruntów (ULDK) – nie pokazano na mapie |

Location notes:

| Note | Dzielnica | BAiPP (miasto) | GUNB RWDZ | Examples |
|---|---:|---:|---:|---|
| działek nie znaleziono w ewidencji gruntów (ULDK) – mogły zostać podzielone lub scalone | 23 | 6 | 110 | `wz-2025-36`, `wz-am-2024-128`, `wz-2024-20`, `ws-6730-2024-17`, `cp-2024-9` |
| w ewidencji gruntów (ULDK) znaleziono N z N działek | 24 | 18 | 85 | `cp-am-2025-c2-10`, `cp-2025-14`, `ws-am-6733-2025-4`, `cp-2025-13`, `wz-am-2025-33` |
| lokalizacja przybliżona – ulica w obrębie N | 17 | 5 | 28 | `wz-am-2024-128`, `ws-6730-2024-17`, `cp-2024-9`, `cp-2024-5`, `cp-2024-4` |
| działki N (…) nie ma już w ewidencji (…) – przyjęto jej części znane z innych wpisów: N | 2 | 4 | 22 | `wz-am-2024-41`, `wz-am-2024-25`, `wz-am-2023-154`, `wz-am-2023-147`, `cp-2022-12` |
| działki N (…) nie ma już w ewidencji (…) – przyjęto jej części znane z innych wpisów: N, N, N, N, N, N, N, N, N, N, N, N | 21 | 3 | 3 | `wz-am-2023-127`, `ws-6733-2022-12`, `ws-6733-2022-11`, `ws-6733-2022-10`, `cp-2022-3` |
| działki N (…) nie ma już w ewidencji (…) – przyjęto jej części znane z innych wpisów: N, N | 7 | 4 | 9 | `wz-am-2022-65`, `cp-am-2022-c2-2`, `cp-2021-8`, `ws-6733-2021-13`, `wz-am-2021-33` |
| adres … leży ok. N m od wskazanych działek | 1 | 0 | 16 | `cp-2020-25`, `pb-st-mz-pa-2022-22273`, `pb-st-mz-pa-2021-13497`, `pb-st-mz-pa-2020-11437`, `pb-st-mz-pa-2019-46492` |
| działki N (…) nie ma już w ewidencji (…) – przyjęto jej części znane z innych wpisów: N, N, N | 0 | 0 | 16 | `pb-st-mz-pa-2018-48505`, `zg-st-mz-pa-2019-4508`, `zg-st-mz-pa-2019-4507`, `pb-st-mz-wa-2018-33613`, `pb-st-mz-pa-2018-24437` |
| lokalizacja przybliżona – ulica | 0 | 0 | 9 | `pb-st-mz-pa-2021-33529`, `zg-st-mz-pa-2019-2475`, `pb-st-mz-pa-2019-17355`, `pb-st-mz-pa-2019-18593`, `pb-st-mz-wa-2018-15822` |
| ulica nie przechodzi przez obręb z rejestru (…) | 0 | 0 | 8 | `zg-st-mz-pa-2019-2475`, `pb-st-mz-pa-2019-17355`, `pb-st-mz-pa-2019-18593`, `pb-st-mz-wa-2018-15822`, `pb-st-mz-pa-2018-39914` |
| lokalizacja przybliżona – budynek nr N | 0 | 0 | 6 | `pb-st-mz-pa-2024-10227`, `pb-st-mz-pa-2022-26417`, `pb-st-mz-pa-2017-43844`, `pb-st-mz-wa-2017-7165`, `pb-st-mz-pa-2016-9105` |
| działki poza dzielnicą Praga-Południe według ewidencji gruntów (ULDK) – nie pokazano na mapie | 0 | 1 | 4 | `ws-am-6730-2025-27`, `pb-st-mz-wa-2022-11434`, `pb-st-mz-pa-2021-49120`, `pb-st-mz-wa-2019-27453`, `pb-st-mz-pg-2016-6120` |
| działek nie znaleziono w ewidencji gruntów (ULDK) | 0 | 0 | 3 | `pb-st-mz-wa-2017-31479`, `pb-st-mz-pa-2016-6446`, `pb-st-mz-pa-2016-760` |
| pod adresem leży działka N obr. N – obręb w źródle prawdopodobnie błędny | 0 | 0 | 3 | `pb-st-mz-wa-2017-31479`, `pb-st-mz-pa-2016-6446`, `pb-st-mz-pa-2016-760` |
| działki N (…) nie ma już w ewidencji (…) – przyjęto jej część leżącą pod adresem: N | 0 | 0 | 2 | `pb-st-mz-wa-2016-26373`, `pb-st-mz-pa-2016-23406` |
| nie udało się ustalić lokalizacji | 0 | 0 | 2 | `pb-st-mz-wa-2018-40659`, `pb-st-mz-wa-2018-7500` |
| część działek leży poza dzielnicą – punkt wyznaczono z działek na Pradze-Południe | 0 | 0 | 1 | `pb-st-mz-wa-2016-41260` |
| działki N (…) nie ma już w ewidencji (…) – przyjęto jej części znane z innych wpisów: N, N, N, N, N, N | 0 | 0 | 1 | `pb-st-mz-pa-2019-16265` |
| działki N (…) nie ma już w ewidencji (…) – przyjęto jej części znane z innych wpisów: N, N, N, N, N, N, N, N, N, N, N, N, N, N, N | 0 | 0 | 1 | `zg-st-mz-pa-2016-678` |
| działki odległe od siebie o ponad N km – punkt dla największej grupy (…) | 1 | 0 | 0 | `cp-2024-15` |
| lokalizacja przybliżona – skrzyżowanie ulic | 0 | 1 | 0 | `ws-am-6730-2020-15` |
| numer działki w źródle niepełny (…) – przyjęto działki N/… znane z innych wpisów: N, N, N, N | 0 | 1 | 0 | `wz-am-2025-42` |

## Record warnings

125 records carry 138 warnings (shown in the UI next to the record).

| Warning type | Dzielnica | BAiPP (miasto) | GUNB RWDZ | Examples |
|---|---:|---:|---:|---|
| obręb „…” nie występuje na Pradze-Południe (…) – możliwy błąd w rejestrze | 0 | 0 | 15 | `pb-st-mz-pa-2025-2520`, `pb-st-mz-pa-2024-15954`, `pb-st-mz-pa-2024-8401`, `pb-st-mz-pa-2021-33529`, `pb-st-mz-pa-2021-10534` |
| identyfikator jednostki ewidencyjnej w rejestrze „…” potraktowano jako 146507_8 (…) – sprawa urzędu dzielnicy, prawdopodobna literówka | 0 | 0 | 13 | `pb-st-mz-pa-2026-16095`, `pb-st-mz-pa-2026-13353`, `pb-st-mz-pa-2024-8401`, `zg-st-mz-pa-2023-8611`, `pb-st-mz-pa-2023-20999` |
| poprawiono pisownię ulicy: „…” → „…” | 9 | 1 | 0 | `ws-6730-2026-17`, `wz-2025-1`, `ws-6730-2024-20`, `ws-6730-2024-19`, `wz-2023-21` |
| identyfikator jednostki ewidencyjnej w rejestrze „…” (…) potraktowano jako 146507_8 (…) – sprawa urzędu dzielnicy, prawdopodobna literówka | 0 | 0 | 6 | `pb-st-mz-pa-2025-36484`, `pb-st-mz-pa-2023-4701`, `pb-st-mz-pa-2017-36048`, `pb-st-mz-pa-2016-39711`, `pb-st-mz-pa-2016-39708` |
| nazwę ulicy z rejestru (…) dopasowano do „…” | 0 | 0 | 6 | `pb-st-mz-wa-2023-4225`, `pb-st-mz-pa-2020-21660`, `pb-st-mz-pa-2020-11247`, `pb-st-mz-pa-2017-23502`, `pb-st-mz-pa-2017-14451` |
| wiersz rejestru (…) bez oznaczenia działki | 0 | 0 | 5 | `pb-st-mz-pa-2025-785`, `pb-st-mz-pa-2018-42053`, `pb-st-mz-pa-2018-18856`, `pb-st-mz-pa-2016-6351`, `pb-st-mz-pa-2016-6365` |
| działki zapisane po ostatnim obrębie przypisano do obrębu N | 4 | 0 | 0 | `ws-6730-2023-78`, `wz-2023-13`, `ws-6730-2023-29`, `ws-6730-2023-28` |
| kubatura zapisana w rejestrze w zaokrągleniu (…) | 0 | 0 | 4 | `pb-st-mz-pa-2021-3253`, `pb-st-mz-pa-2020-12384`, `pb-st-mz-pa-2018-15514`, `pb-st-mz-pa-2016-4712` |
| obręb w źródle (…) prawdopodobnie błędny – działka N pod adresem Grochowska N leży w obrębie N | 0 | 0 | 4 | `pb-st-mz-pa-2023-20027`, `pb-st-mz-pa-2019-23598`, `pb-st-mz-pa-2019-16240`, `pb-st-mz-pa-2016-19947` |
| sprawa urzędu dzielnicy Praga-Południe bez oznaczenia działki w rejestrze – przyjęto, że dotyczy Pragi-Południe | 0 | 0 | 4 | `pb-st-mz-pa-2018-42053`, `pb-st-mz-pa-2018-18856`, `pb-st-mz-pa-2016-6351`, `pb-st-mz-pa-2016-6365` |
| znak sprawy ma symbol N (…), a opis wskazuje na zabudowę mieszkaniową – możliwa pomyłka w źródle | 4 | 0 | 0 | `ws-6733-2022-81`, `ws-6733-2021-60`, `ws-6733-2021-28`, `ws-6733-2021-68` |
| identyfikator jednostki ewidencyjnej w rejestrze „…” (…) potraktowano jako 146507_8 (…) – według ewidencji gruntów (ULDK) ta działka lub obręb istnieje tylko na Pradze-Południe; błąd w rejestrze | 0 | 0 | 3 | `pb-st-mz-pa-2024-14200`, `pb-st-mz-wa-2023-19454`, `pb-st-mz-wa-2018-37134` |
| obręb w źródle (…) prawdopodobnie błędny – działka N pod adresem Szaserów N leży w obrębie N | 0 | 0 | 3 | `pb-st-mz-pa-2020-4514`, `pb-st-mz-pa-2019-10725`, `pb-st-mz-pa-2016-19750` |
| działka poza dzielnicą Praga-Południe według ewidencji gruntów (ULDK): N obr. N: obręb 146508_8.N (…), działki już w nim nie ma – w rejestrze z identyfikatorem jednostki 146507_8 (…); nie zaznaczono jej na mapie dzielnicy | 0 | 0 | 2 | `pb-st-mz-wa-2022-11434`, `pb-st-mz-wa-2019-27453` |
| kropkę w „…” potraktowano jako separator działek | 2 | 0 | 0 | `ws-6730-2022-83`, `ws-6730-2022-49` |
| obręb w źródle (…) prawdopodobnie błędny – działka N pod adresem Busolowa 16A leży w obrębie N | 2 | 0 | 0 | `wz-2023-23`, `ws-6730-2023-74` |
| obręb w źródle (…) prawdopodobnie błędny – działka N pod adresem Francuska N leży w obrębie N | 0 | 0 | 2 | `pb-st-mz-pa-2020-32288`, `pb-st-mz-pa-2020-13545` |
| obręb w źródle (…) prawdopodobnie błędny – działka N pod adresem Kiprów N leży w obrębie N | 0 | 0 | 2 | `pb-st-mz-pa-2020-24159`, `pb-st-mz-pa-2018-30630` |
| obręb w źródle (…) prawdopodobnie błędny – działka N pod adresem Paryska N leży w obrębie N | 0 | 0 | 2 | `pb-st-mz-pa-2019-37470`, `pb-st-mz-pa-2017-25623` |
| obręb w źródle (…) prawdopodobnie błędny – działka N pod adresem Saska N leży w obrębie N | 0 | 0 | 2 | `pb-st-mz-pa-2020-22119`, `pb-st-mz-pa-2016-12452` |
| pominięto niezrozumiały fragment oznaczenia działek: „…” | 0 | 2 | 0 | `ws-am-6733-2025-4`, `wz-am-2021-87` |
| poprawiono zapis obrębu „…” na N | 2 | 0 | 0 | `ws-6730-2022-85`, `wz-2021-32` |
| sprawa obejmuje też działki spoza Pragi-Południe – jednostka ewidencyjna 146510_8 (…): N | 0 | 0 | 2 | `pb-st-mz-wa-2017-11062`, `pb-st-mz-wa-2016-19462` |
| brak roku w numerze decyzji – przyjęto rok z daty | 1 | 0 | 0 | `wz-2020-19` |
| działka N – w źródle podano jej obecne numery: N, N, N | 0 | 1 | 0 | `wz-am-2023-110` |
| działka poza dzielnicą Praga-Południe według ewidencji gruntów (ULDK): N obr. N: Praga-Północ, 146508_8.N – w rejestrze z identyfikatorem jednostki 146507_8 (…); nie zaznaczono jej na mapie dzielnicy | 0 | 0 | 1 | `pb-st-mz-pg-2016-6120` |
| działka poza dzielnicą Praga-Południe według ewidencji gruntów (ULDK): N obr. N: Praga-Północ, 146508_8.N – w źródle opisana jako Praga-Południe; nie zaznaczono jej na mapie dzielnicy | 0 | 1 | 0 | `ws-am-6730-2025-27` |
| działka poza dzielnicą Praga-Południe według ewidencji gruntów (ULDK): N obr. N: Wawer, 146514_8.N – w rejestrze z identyfikatorem jednostki 146507_8 (…); nie zaznaczono jej na mapie dzielnicy | 0 | 0 | 1 | `pb-st-mz-pa-2021-49120` |
| identyfikator jednostki ewidencyjnej w rejestrze „…” potraktowano jako 146507_8 (…) – według ewidencji gruntów (ULDK) ta działka lub obręb istnieje tylko na Pradze-Południe; błąd w rejestrze | 0 | 0 | 1 | `pb-pl-mz-2026-15131` |
| niepełny numer działki „…” w źródle | 0 | 1 | 0 | `wz-am-2025-42` |
| niepełny numer obrębu „…” – pominięto działki zapisane przed nim (…) | 0 | 1 | 0 | `cp-am-2022-c2-2` |
| nieprawidłowy rok w numerze decyzji (…) – przyjęto rok z daty | 1 | 0 | 0 | `wz-2021-42` |
| numer decyzji kończy się na „…” – w numeracji urzędów m.st. Warszawy oznacza to zwykle odmowę; rejestr GUNB nie podaje rodzaju rozstrzygnięcia | 0 | 0 | 1 | `pb-st-mz-pa-2024-10219` |
| obręb N nie istnieje w ewidencji gruntów Pragi-Południe – możliwy błąd w źródle | 0 | 1 | 0 | `wz-am-2021-100` |
| obręb w źródle (…) prawdopodobnie błędny – działka N (…) pod adresem Bliska N leży w obrębie N | 0 | 0 | 1 | `pb-st-mz-wa-2016-26373` |
| obręb w źródle (…) prawdopodobnie błędny – działka N (…) pod adresem Jarocińska N leży w obrębie N | 0 | 0 | 1 | `pb-st-mz-pa-2016-23406` |
| obręb w źródle (…) prawdopodobnie błędny – działka N pod adresem Algierska N leży w obrębie N | 0 | 0 | 1 | `pb-st-mz-pa-2018-30825` |
| obręb w źródle (…) prawdopodobnie błędny – działka N pod adresem Andrzeja Frycza Modrzewskiego N leży w obrębie N | 0 | 0 | 1 | `pb-st-mz-pa-2021-11713` |
| obręb w źródle (…) prawdopodobnie błędny – działka N pod adresem Chłodnicza N leży w obrębie N | 1 | 0 | 0 | `ws-6730-2024-2` |
| obręb w źródle (…) prawdopodobnie błędny – działka N pod adresem Czechowicka 11A leży w obrębie N | 0 | 0 | 1 | `pb-st-mz-pa-2017-30537` |
| obręb w źródle (…) prawdopodobnie błędny – działka N pod adresem Francuska 11A leży w obrębie N | 0 | 0 | 1 | `pb-st-mz-pa-2016-19162` |
| obręb w źródle (…) prawdopodobnie błędny – działka N pod adresem Janusza Meissnera 8b leży w obrębie N | 0 | 0 | 1 | `pb-st-mz-pa-2020-46833` |
| obręb w źródle (…) prawdopodobnie błędny – działka N pod adresem Jarocińska N leży w obrębie N | 0 | 0 | 1 | `pb-st-mz-pa-2019-34184` |
| obręb w źródle (…) prawdopodobnie błędny – działka N pod adresem Jugosłowiańska N leży w obrębie N | 0 | 1 | 0 | `wz-am-2023-114` |
| obręb w źródle (…) prawdopodobnie błędny – działka N pod adresem Józefa Chłopickiego N leży w obrębie N | 0 | 0 | 1 | `pb-st-mz-pa-2021-1453` |
| obręb w źródle (…) prawdopodobnie błędny – działka N pod adresem Kutnowska N leży w obrębie N | 0 | 0 | 1 | `pb-st-mz-pa-2026-2126` |
| obręb w źródle (…) prawdopodobnie błędny – działka N pod adresem Omulewska N leży w obrębie N | 0 | 0 | 1 | `pb-st-mz-pa-2017-7217` |
| obręb w źródle (…) prawdopodobnie błędny – działka N pod adresem Ostrobramska N leży w obrębie N | 0 | 0 | 1 | `pb-st-mz-pa-2019-12607` |
| obręb w źródle (…) prawdopodobnie błędny – działka N pod adresem Poselska N leży w obrębie N | 0 | 0 | 1 | `zg-st-mz-pa-2026-4586` |
| obręb w źródle (…) prawdopodobnie błędny – działka N pod adresem Serocka N leży w obrębie N | 0 | 0 | 1 | `pb-st-mz-pa-2018-30453` |
| obręb w źródle (…) prawdopodobnie błędny – działka N pod adresem Szklanych Domów 5b leży w obrębie N | 1 | 0 | 0 | `ws-6730-2026-2` |
| obręb w źródle (…) prawdopodobnie błędny – działka N pod adresem Wiarusów N, N leży w obrębie N | 0 | 0 | 1 | `pb-st-mz-pa-2025-8078` |
| obręb w źródle (…) prawdopodobnie błędny – działka N pod adresem Zwycięzców N leży w obrębie N | 0 | 0 | 1 | `pb-st-mz-pa-2023-21507` |
| obręb w źródle (…) prawdopodobnie błędny – działka N pod adresem Złotej Wilgi N leży w obrębie N | 0 | 1 | 0 | `ws-am-6730-2024-9` |
| obręb w źródle (…) prawdopodobnie błędny – działka N pod adresem Łukowska N leży w obrębie N | 0 | 0 | 1 | `pb-st-mz-wa-2017-7167` |
| rok w numerze decyzji (…) różni się od roku daty (…) | 1 | 0 | 0 | `wz-2023-27` |
| sprawa obejmuje też działki spoza Pragi-Południe – jednostka ewidencyjna 146509_8 (…): N | 0 | 0 | 1 | `pb-st-mz-wa-2016-41260` |
| symbol JRWA „…” w znaku sprawy potraktowano jako N (…) | 1 | 0 | 0 | `ws-6730-2021-16` |
| ten sam numer porządkowy (…) nosi w zestawieniu także inna decyzja; brak numeru N – możliwa pomyłka w numeracji źródła | 0 | 1 | 0 | `wz-am-2025-33` |
| w rejestrze zamiast numeru budynku wpisano kod jednostki ewidencyjnej (…) – pominięto | 0 | 0 | 1 | `pb-st-mz-pa-2019-18593` |

## Classification

| Tag | Group | Dzielnica | BAiPP (miasto) | GUNB RWDZ |
|---|---|---:|---:|---:|
| Dom jednorodzinny (`jednorodzinny`) | funkcja | 70 | 0 | 254 |
| Budynek wielorodzinny (`wielorodzinny`) | funkcja | 172 | 66 | 874 |
| Adaptacja na mieszkanie (`adaptacja-mieszkalna`) | funkcja | 54 | 0 | 21 |
| Akademik, hostel, hotel (`zamieszkanie-zbiorowe`) | funkcja | 7 | 4 | 31 |
| Handel, usługi, biura (`uslugi`) | funkcja | 42 | 6 | 276 |
| Żłobek, przedszkole, szkoła (`oswiata`) | funkcja | 22 | 0 | 53 |
| Kultura (`kultura`) | funkcja | 2 | 0 | 2 |
| Zdrowie i opieka (`zdrowie-opieka`) | funkcja | 2 | 0 | 84 |
| Sport, rekreacja, zieleń (`sport-rekreacja-zielen`) | funkcja | 10 | 0 | 23 |
| Obiekt sakralny (`kult-religijny`) | funkcja | 1 | 0 | 6 |
| Sieci: woda, ciepło, prąd, gaz (`infrastruktura`) | funkcja | 81 | 3 | 347 |
| Instalacje w budynku (gaz, woda, c.o.) (`instalacje-wewnetrzne`) | funkcja | 0 | 0 | 431 |
| Telekomunikacja (`telekomunikacja`) | funkcja | 8 | 5 | 18 |
| Drogi i transport (`drogi-transport`) | funkcja | 16 | 16 | 48 |
| Parking, garaż (`parkingi-garaze`) | funkcja | 21 | 1 | 78 |
| Reklama (`reklama`) | funkcja | 9 | 0 | 23 |
| Przemysł, magazyny (`przemysl-magazyny`) | funkcja | 7 | 1 | 88 |
| Wiata, altana, budynek gospodarczy (`obiekty-pomocnicze`) | funkcja | 16 | 1 | 96 |
| Winda, dostępność (`windy-dostepnosc`) | funkcja | 11 | 0 | 58 |
| Nowa budowa (`nowa-budowa`) | roboty | 304 | 33 | 938 |
| Rozbudowa, nadbudowa, przebudowa (`rozbudowa-przebudowa`) | roboty | 112 | 22 | 915 |
| Remont, docieplenie (`remont`) | roboty | 0 | 0 | 407 |
| Zmiana sposobu użytkowania (`zmiana-sposobu-uzytkowania`) | roboty | 97 | 0 | 139 |
| Zmiana lub umorzenie (`zmiana-decyzji`) | roboty | 3 | 37 | 87 |
| Legalizacja (`legalizacja`) | roboty | 1 | 0 | 0 |
| Rozbiórka (`rozbiorka`) | roboty | 0 | 1 | 299 |

* Dzielnica – untagged records: 0; without a "what is built" (funkcja) tag: 11 – `wz-2025-5`, `ws-6730-2024-31`, `ws-6730-2024-12`, `ws-6730-2023-95`, `wz-2023-24`, `wz-2023-22`, `ws-6730-2023-75`, `ws-6730-2023-69`, `ws-6730-2022-25`, `wz-2022-2`, `ws-6730-2021-34`.
* BAiPP (miasto) – untagged records: 6 – `ws-am-6730-2026-2`, `wz-am-2024-87`, `wz-am-2023-154`, `cp-am-2023-c2-8`, `wz-am-2022-32`, `ws-am-6730-2020-13`; without a "what is built" (funkcja) tag: 10 – `ws-am-6730-2026-2`, `wz-am-2024-87`, `wz-am-2024-41`, `wz-am-2023-154`, `cp-am-2023-c2-8`, `ws-am-6733-2023-2`, `wz-am-2022-148`, `wz-am-2022-32`, `wz-am-2021-109`, `ws-am-6730-2020-13`.
* GUNB RWDZ – untagged records: 27 – `pb-st-mz-pa-2023-21515`, `pb-st-mz-pa-2022-559`, `pb-st-mz-pa-2021-22381`, `pb-st-mz-pa-2020-46645`, `pb-st-mz-pa-2020-24189`, `pb-st-mz-pa-2020-41922`, `pb-st-mz-pa-2020-36301`, `pb-st-mz-pa-2020-37734`, `pb-st-mz-pa-2020-25158`, `pb-st-mz-pa-2019-44349`, `pb-st-mz-pa-2019-36343`, `pb-st-mz-pa-2019-35216`, `pb-st-mz-pa-2019-29154`, `pb-st-mz-pa-2018-37272`, `pb-st-mz-pa-2018-29952`, `pb-st-mz-pa-2018-22030`, `pb-st-mz-pa-2018-21841`, `pb-st-mz-pa-2017-44918`, `pb-st-mz-pa-2018-12444`, `pb-st-mz-pa-2018-9861`, `pb-st-mz-pa-2017-44753`, `pb-st-mz-pa-2017-28644`, `pb-st-mz-pa-2017-31572`, `pb-st-mz-pa-2017-12439`, `pb-st-mz-pa-2017-12442`, `pb-st-mz-pa-2017-9746`, `pb-st-mz-pa-2016-26504`; without a "what is built" (funkcja) tag: 135 – `pb-st-mz-pa-2026-20543`, `pb-st-mz-pa-2026-20538`, `pb-st-mz-pa-2026-16669`, `pb-st-mz-wa-2026-18625`, `pb-pl-mz-2026-17778`, `pb-st-mz-pa-2026-7917`, `pb-st-mz-pa-2026-4689`, `pb-st-mz-pa-2025-29137`, `pb-st-mz-pa-2025-30498`, `pb-st-mz-pa-2025-31151`, `pb-st-mz-pa-2025-16571`, `pb-st-mz-pa-2025-10090`, `pb-st-mz-pa-2025-5283`, `pb-st-mz-pa-2024-36133`, `pb-st-mz-pa-2024-17803`, `pb-st-mz-pa-2024-6937`, `pb-st-mz-pa-2024-1744`, `pb-st-mz-pa-2023-23777`, `pb-st-mz-pa-2023-21515`, `pb-st-mz-pa-2023-20999`, `pb-st-mz-pa-2023-6700`, `pb-st-mz-pa-2023-11975`, `pb-st-mz-pa-2023-6994`, `pb-st-mz-pa-2023-4628`, `pb-st-mz-pa-2023-4544`, `pb-st-mz-pa-2023-401`, `pb-st-mz-pa-2022-32263`, `pb-st-mz-pa-2022-29409`, `pb-st-mz-pa-2022-22273`, `pb-st-mz-pa-2022-20962` … and 105 more.

## Street names

* Streets: 292. One spelling per street in `address.street` (the site's street filter lists every spelling separately; `normalize.STREET_CANONICAL` maps 16 streets written in several ways to one, `address.display` keeps the source text).
* Still written in several ways (add them to `STREET_CANONICAL`): none.

## Source files and pages

* Layouts: baipp-cp 12, baipp-cp-2020 2, baipp-ws 6, baipp-ws-2020 1, baipp-wz 6, baipp-wz-2020 1, new-cp 9, new-ws 20, new-wz 15, old-cp 40, old-ws 48, old-wz 44, rwdz-wnioski 1, rwdz-zgloszenia 2.
* Template rows skipped (only a pre-printed Lp number): 401.
* Files linked from more than one page: [wydane decyzje wz - wrzesień  2025.xlsx](https://pragapld.um.warszawa.pl/documents/50051/145189586/wydane+decyzje+wz+-+wrzesie%C5%84++2025.xlsx/198aa886-f4b9-8292-a213-95e491eefd12?t=1760011064914), [wydane decyzje celu publicznego wrzesień -22.xlsx](https://pragapld.um.warszawa.pl/documents/50051/63077970/wydane+decyzje+celu+publicznego+wrzesie%C5%84+-22.xlsx/8b372269-abb0-42a4-9229-0adaff059c95?t=1665733161974).

Page warnings from the crawler (12):

* [Październik 2025](https://pragapld.um.warszawa.pl/-/artykul-93): Blok „Wydane decyzje o warunkach zabudowy: 1 pozycja” linkuje 2 pliki: „wydane decyzje wz - wrzesień  2025.xlsx”, „wydane decyzje wz - październik  2025.xlsx”.
* [Październik 2025](https://pragapld.um.warszawa.pl/-/artykul-93): Plik „wydane decyzje wz - wrzesień  2025.xlsx” dotyczy innego miesiąca (2025-09) niż strona (2025-10).
* [Październik 2022 r.](https://pragapld.um.warszawa.pl/-/pazdziernik-2022): Blok „Wydane decyzje w sprawie lokalizacji celu publicznego – 1 pozycja” linkuje 2 pliki: „wydane decyzje celu publicznego wrzesień -22.xlsx”, „wydane decyzje celu publicznego październik-22.xlsx”.
* [Październik 2022 r.](https://pragapld.um.warszawa.pl/-/pazdziernik-2022): Plik „wydane decyzje celu publicznego wrzesień -22.xlsx” dotyczy innego miesiąca (2022-09) niż strona (2022-10).
* [Luty 2022 r.](https://pragapld.um.warszawa.pl/-/luty-2022): Blok „Wydane decyzje w sprawie lokalizacji celu publicznego – 0 pozycji” deklaruje 0 pozycji, ale linkuje plik (zwykle pusty wzór tabeli).
* [Październik 2021r.](https://pragapld.um.warszawa.pl/-/pazdziernika-2021): Blok „Wydane decyzje w sprawie lokalizacji celu publicznego – 0 pozycji” deklaruje 0 pozycji, ale linkuje plik (zwykle pusty wzór tabeli).
* [Marzec 2021 r.](https://pragapld.um.warszawa.pl/-/informacje-o-wszczetych-postepowaniach-marzec-2021): Blok „Wydane decyzje w sprawie ustalenia lokalizacji celu publicznego marzec 2021 r. – 0 pozycji – plik do pobrania” deklaruje 0 pozycji, ale linkuje plik (zwykle pusty wzór tabeli).
* [Luty 2021 r.](https://pragapld.um.warszawa.pl/-/informacje-o-wszczetych-postepowaniach-luty-2021): Blok „Wydane decyzje o warunkach zabudowy za luty 2021 r. – 0 pozycji – plik do pobrania” deklaruje 0 pozycji, ale linkuje plik (zwykle pusty wzór tabeli).
* [Luty 2021 r.](https://pragapld.um.warszawa.pl/-/informacje-o-wszczetych-postepowaniach-luty-2021): Blok „Wydane decyzje w sprawie ustalenia lokalizacji celu publicznego luty 2021 r. – 0 pozycji – plik do pobrania” deklaruje 0 pozycji, ale linkuje plik (zwykle pusty wzór tabeli).
* [Styczeń 2021 r.](https://pragapld.um.warszawa.pl/-/informacje-o-wszczetych-postepowaniach-styczen-2021): Blok „Wydane decyzje w sprawie ustalenia lokalizacji celu publicznego styczeń 2021 r. – 0 pozycji –plik do pobrania” deklaruje 0 pozycji, ale linkuje plik (zwykle pusty wzór tabeli).
* [Listopad 2020 r.](https://pragapld.um.warszawa.pl/-/informacje-o-wszczetych-postepowaniach-listopad-2020): Blok „Wydane decyzje w sprawie ustalenia lokalizacji inwestycji celu publicznego – BRAK w LISTOPADZIE 2020 – plik do pobrania” deklaruje 0 pozycji, ale linkuje plik (zwykle pusty wzór tabeli).
* [Październik 2020 r.](https://pragapld.um.warszawa.pl/-/informacje-o-wszczetych-postepowaniach-pazdziernik-2020): Blok „Informacja o wszczętych postępowaniach o warunkach zabudowy i ustaleniu lokalizacji inwestycji celu publicznego- w miesiącu październiku brak wszczętych postępowań – pilk do pobrania” deklaruje 0 pozycji, ale linkuje plik (zwykle pusty wzór tabeli).
