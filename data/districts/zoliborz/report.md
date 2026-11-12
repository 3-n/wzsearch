# wzSearch – data-quality report

Generated `2026-11-12T06:56:36Z` by `pipeline/build.py` from the district's [source index](https://zoliborz.um.warszawa.pl/-/informacja-o-wszczetych-postepowaniach-oraz-wydanych-decyzjach-administracyjnych-1), the [BAiPP lists](https://architektura.um.warszawa.pl/postepowania-i-decyzje) and GUNB's [RWDZ register](https://wyszukiwarka.gunb.gov.pl/pobranie.html). Regenerated on every build; do not edit.

## Totals

* Records per dataset: Dzielnica 12, BAiPP (miasto) 4, GUNB RWDZ 752 – `records.json` 16, `permits.json` 752.
* Monthly pages: **1** (– → –); source files: **17** (4 with rows, 13 empty templates, 0 unreadable/missing).
* Workbook data rows kept (district + BAiPP): **16** → records after merging duplicates: **16** (WZ 15, CP 0, Wszczęcie 1).
* Building permits and notifications (RWDZ): **752** (Pozwolenie 712, Zgłoszenie 40).
* Records listed in more than one source row: 0.
* Procedure (WZ vs public purpose, incl. initiated proceedings): cp 1, wz 15.
* Applicants (WZ/ULICP): natural persons 0, organisations 16, unknown 0.

WZ/ULICP records per year (decision / initiation date):

| Year | WZ | CP | Wszczęcie | Total |
|---|---:|---:|---:|---:|
| 2020 | 1 | 0 | 0 | 1 |
| 2021 | 7 | 0 | 0 | 7 |
| 2022 | 2 | 0 | 1 | 3 |
| 2023 | 5 | 0 | 0 | 5 |
| **all** | **15** | **0** | **1** | **16** |

## Declared vs parsed counts

Each monthly page states how many entries each list has ("3 pozycje"). `parsed` counts the data rows read from the files first published on that page (a leftover link to an earlier month's file is not counted twice).

| Kind | Declared (blocks with a number) | Parsed in those blocks | Parsed in blocks without a number | Parsed rows | Duplicates merged | Records |
|---|---:|---:|---:|---:|---:|---:|
| WZ | 0 | 0 | 12 | 11 | 0 | 11 |
| CP | 0 | 0 | 0 | 0 | 0 | 0 |
| Wszczęcie | 0 | 0 | 0 | 1 | 0 | 1 |

All blocks with a declared count match the parsed files.

Blocks that link a file but state no count (17; parsed rows are not checked): [Informacja o wszczętych postępowaniach oraz wydanych decyzjach administracyjnych](https://zoliborz.um.warszawa.pl/-/informacja-o-wszczetych-postepowaniach-oraz-wydanych-decyzjach-administracyjnych-1) WZ → 0; [Informacja o wszczętych postępowaniach oraz wydanych decyzjach administracyjnych](https://zoliborz.um.warszawa.pl/-/informacja-o-wszczetych-postepowaniach-oraz-wydanych-decyzjach-administracyjnych-1) WZ → 5; [Informacja o wszczętych postępowaniach oraz wydanych decyzjach administracyjnych](https://zoliborz.um.warszawa.pl/-/informacja-o-wszczetych-postepowaniach-oraz-wydanych-decyzjach-administracyjnych-1) CP → 0; [Informacja o wszczętych postępowaniach oraz wydanych decyzjach administracyjnych](https://zoliborz.um.warszawa.pl/-/informacja-o-wszczetych-postepowaniach-oraz-wydanych-decyzjach-administracyjnych-1) WZ → 0; [Informacja o wszczętych postępowaniach oraz wydanych decyzjach administracyjnych](https://zoliborz.um.warszawa.pl/-/informacja-o-wszczetych-postepowaniach-oraz-wydanych-decyzjach-administracyjnych-1) WZ → 0; [Informacja o wszczętych postępowaniach oraz wydanych decyzjach administracyjnych](https://zoliborz.um.warszawa.pl/-/informacja-o-wszczetych-postepowaniach-oraz-wydanych-decyzjach-administracyjnych-1) WZ → 0; [Informacja o wszczętych postępowaniach oraz wydanych decyzjach administracyjnych](https://zoliborz.um.warszawa.pl/-/informacja-o-wszczetych-postepowaniach-oraz-wydanych-decyzjach-administracyjnych-1) WZ → 0; [Informacja o wszczętych postępowaniach oraz wydanych decyzjach administracyjnych](https://zoliborz.um.warszawa.pl/-/informacja-o-wszczetych-postepowaniach-oraz-wydanych-decyzjach-administracyjnych-1) WZ → 0; [Informacja o wszczętych postępowaniach oraz wydanych decyzjach administracyjnych](https://zoliborz.um.warszawa.pl/-/informacja-o-wszczetych-postepowaniach-oraz-wydanych-decyzjach-administracyjnych-1) WZ → 0; [Informacja o wszczętych postępowaniach oraz wydanych decyzjach administracyjnych](https://zoliborz.um.warszawa.pl/-/informacja-o-wszczetych-postepowaniach-oraz-wydanych-decyzjach-administracyjnych-1) WZ → 0; [Informacja o wszczętych postępowaniach oraz wydanych decyzjach administracyjnych](https://zoliborz.um.warszawa.pl/-/informacja-o-wszczetych-postepowaniach-oraz-wydanych-decyzjach-administracyjnych-1) WZ → 0; [Informacja o wszczętych postępowaniach oraz wydanych decyzjach administracyjnych](https://zoliborz.um.warszawa.pl/-/informacja-o-wszczetych-postepowaniach-oraz-wydanych-decyzjach-administracyjnych-1) WZ → 2; [Informacja o wszczętych postępowaniach oraz wydanych decyzjach administracyjnych](https://zoliborz.um.warszawa.pl/-/informacja-o-wszczetych-postepowaniach-oraz-wydanych-decyzjach-administracyjnych-1) WZ → 1; [Informacja o wszczętych postępowaniach oraz wydanych decyzjach administracyjnych](https://zoliborz.um.warszawa.pl/-/informacja-o-wszczetych-postepowaniach-oraz-wydanych-decyzjach-administracyjnych-1) WZ → 0; [Informacja o wszczętych postępowaniach oraz wydanych decyzjach administracyjnych](https://zoliborz.um.warszawa.pl/-/informacja-o-wszczetych-postepowaniach-oraz-wydanych-decyzjach-administracyjnych-1) WZ → 0; [Informacja o wszczętych postępowaniach oraz wydanych decyzjach administracyjnych](https://zoliborz.um.warszawa.pl/-/informacja-o-wszczetych-postepowaniach-oraz-wydanych-decyzjach-administracyjnych-1) WZ → 0; [Informacja o wszczętych postępowaniach oraz wydanych decyzjach administracyjnych](https://zoliborz.um.warszawa.pl/-/informacja-o-wszczetych-postepowaniach-oraz-wydanych-decyzjach-administracyjnych-1) WZ → 4.

## Completeness: gaps in decision numbering

WZ and CP decisions are numbered consecutively per year, so a number that never appears in any file is a decision that was not published in these lists (or a refusal/discontinuation the office does not list). Numbering restarts every year at 1; in the first year only numbers after the lowest one seen count, because the publication started in August 2020. (District numbering only: BAiPP numbers its decisions city-wide.)

| Kind | Year | Published | Range seen | Missing | Missing numbers |
|---|---|---:|---|---:|---|

## BAiPP (city architecture bureau) lists

Biuro Architektury i Planowania Przestrzennego publishes the same three lists for the whole city, one file per year and list (the current year's files are replaced every month; every snapshot we downloaded is kept). Only rows whose address names Praga-Południe on its last line become records.

| Page | Year | List | File | City-wide rows | Praga-Południe rows | Records |
|---|---|---|---|---:|---:|---:|
| [Informacja o wszczętych postępowaniach i wydanych decyzjach administracyjnych](https://architektura.um.warszawa.pl/postepowania-i-decyzje) | 2026 | WZ | [informacja_o_wydanych_decyzjach_WZ_X_2026 +.xlsx](https://cdn.um.warszawa.pl/documents/12025039/173779387/informacja_o_wydanych_decyzjach_WZ_X_2026+%2B.xlsx/c03ab73b-eeab-e946-f4b2-bcc6a3181170?t=1794226314841) | 108 | 0 | 0 |
| [Informacja o wszczętych postępowaniach i wydanych decyzjach administracyjnych](https://architektura.um.warszawa.pl/postepowania-i-decyzje) | 2026 | WZ | [informacja_o_wydanych_decyzjach_WZ_IX_2026 +.xlsx](https://architektura.um.warszawa.pl/documents/12025039/171613001/informacja_o_wydanych_decyzjach_WZ_IX_2026+%2B.xlsx/1d75d6d6-239a-2dc1-843b-70184b23709c?t=1791798490945) (no longer linked since 2026-11-12) | 101 | 0 | 0 |
| [Informacja o wszczętych postępowaniach i wydanych decyzjach administracyjnych](https://architektura.um.warszawa.pl/postepowania-i-decyzje) | 2026 | wszczęte | [informacja_o_wszczętych_postępowaniach_o_WZ_LICP_X_2026 +.xlsx](https://cdn.um.warszawa.pl/documents/12025039/173779387/informacja_o_wszcz%C4%99tych_post%C4%99powaniach_o_WZ_LICP_X_2026+%2B.xlsx/13712e56-4b63-a2e6-3363-5daf98175dc8?t=1794226315093) | 107 | 0 | 0 |
| [Informacja o wszczętych postępowaniach i wydanych decyzjach administracyjnych](https://architektura.um.warszawa.pl/postepowania-i-decyzje) | 2026 | wszczęte | [informacja_o_wszczętych_postępowaniach_o_WZ_LICP_IX_2026 +.xlsx](https://architektura.um.warszawa.pl/documents/12025039/171613001/informacja_o_wszcz%C4%99tych_post%C4%99powaniach_o_WZ_LICP_IX_2026+%2B.xlsx/289a1962-288a-3179-aabf-643286f2a106?t=1791798491258) (no longer linked since 2026-11-12) | 85 | 0 | 0 |
| [Informacja o wszczętych postępowaniach i wydanych decyzjach administracyjnych](https://architektura.um.warszawa.pl/postepowania-i-decyzje) | 2026 | ULICP C2 | [informacja_o_wydanych_decyzjach_ustalenie_LICP_o_znaczeniu_powiatowym _i_gminnym_IX_2026 +.xlsx](https://architektura.um.warszawa.pl/documents/12025039/171613001/informacja_o_wydanych_decyzjach_ustalenie_LICP_o_znaczeniu_powiatowym+_i_gminnym_IX_2026+%2B.xlsx/7dbca2ea-686b-0157-caa3-134d35570f6b?t=1791798490447) (no longer linked since 2026-11-12) | 6 | 0 | 0 |
| [Informacja o wszczętych postępowaniach i wydanych decyzjach administracyjnych](https://architektura.um.warszawa.pl/postepowania-i-decyzje) | 2026 | ULICP C2 | [informacja_o_wydanych_decyzjach_ustalenie_LICP_o_znaczeniu_powiatowym _i_gminnym_X_2026+.xlsx](https://cdn.um.warszawa.pl/documents/12025039/173779387/informacja_o_wydanych_decyzjach_ustalenie_LICP_o_znaczeniu_powiatowym+_i_gminnym_X_2026%2B.xlsx/e0d771ec-dd75-b9be-a638-bd80fc8a8d6a?t=1794226314560) | – | – | 0 |
| [Informacja o wszczętych postępowaniach i wydanych decyzjach administracyjnych](https://architektura.um.warszawa.pl/postepowania-i-decyzje) | 2026 | ULICP C1 | [informacja_o_wydanych_decyzjach_o_ustaleniu_LICP_o_znaczeniu_krajowym_i_wojódzkim_IX_2026 +.xlsx](https://architektura.um.warszawa.pl/documents/12025039/171613001/informacja_o_wydanych_decyzjach_o_ustaleniu_LICP_o_znaczeniu_krajowym_i_woj%C3%B3dzkim_IX_2026+%2B.xlsx/fae00082-7a3e-6cb0-d96c-6a3104611a81?t=1791798491576) (no longer linked since 2026-11-12) | 5 | 0 | 0 |
| [Informacja o wszczętych postępowaniach i wydanych decyzjach administracyjnych](https://architektura.um.warszawa.pl/postepowania-i-decyzje) | 2026 | ULICP C1 | [informacja_o_wydanych_decyzjach_o_ustaleniu_LICP_o_znaczeniu_krajowym_i_wojódzkim_X_2026+.xlsx](https://cdn.um.warszawa.pl/documents/12025039/173779387/informacja_o_wydanych_decyzjach_o_ustaleniu_LICP_o_znaczeniu_krajowym_i_woj%C3%B3dzkim_X_2026%2B.xlsx/2bdca5a3-f93b-a6ec-d25f-d6aa76579389?t=1794226314259) | – | – | 0 |
| [Informacja o wszczętych postępowaniach i wydanych decyzjach (2025 r.)](https://architektura.um.warszawa.pl/-/rejestry25) | 2025 | WZ | [informacja o wydanych decyzjach_wz_XII_25 +.xlsx](https://architektura.um.warszawa.pl/documents/12025039/152228831/informacja+o+wydanych+decyzjach_wz_XII_25+%2B.xlsx/cb763523-543a-dc26-c549-da9e662d76c8?t=1768389582758) | 125 | 0 | 0 |
| [Informacja o wszczętych postępowaniach i wydanych decyzjach (2025 r.)](https://architektura.um.warszawa.pl/-/rejestry25) | 2025 | wszczęte | [informacja o wszczętych postępowaniach o wz,licp_XII_25.xlsx](https://architektura.um.warszawa.pl/documents/12025039/152228831/informacja+o+wszcz%C4%99tych+post%C4%99powaniach+o+wz%2Clicp_XII_25.xlsx/ec2f3679-1303-b07d-d372-2b59bbad3874?t=1768389583052) | 94 | 0 | 0 |
| [Informacja o wszczętych postępowaniach i wydanych decyzjach (2025 r.)](https://architektura.um.warszawa.pl/-/rejestry25) | 2025 | ULICP C2 | [informacja o wydanych decyzjach ws. ustalenia_licp_pow-gm_XII_25 +.xlsx](https://architektura.um.warszawa.pl/documents/12025039/152228831/informacja+o+wydanych+decyzjach+ws.+ustalenia_licp_pow-gm_XII_25+%2B.xlsx/b7892448-d604-fd62-1991-5e616a15c926?t=1768389582390) | 10 | 0 | 0 |
| [Informacja o wszczętych postępowaniach i wydanych decyzjach (2025 r.)](https://architektura.um.warszawa.pl/-/rejestry25) | 2025 | ULICP C1 | [informacja o wydanych decyzjach ws. ustalenia_licp_kraj-woj_XII_25 +.xlsx](https://architektura.um.warszawa.pl/documents/12025039/152228831/informacja+o+wydanych+decyzjach+ws.+ustalenia_licp_kraj-woj_XII_25+%2B.xlsx/2da6e58f-949a-53ac-753b-1c4c5ea66ec1?t=1768389583415) | 3 | 0 | 0 |
| [Informacja o wszczętych postępowaniach i wydanych decyzjach (2024 r.)](https://architektura.um.warszawa.pl/-/rejestry24) | 2024 | WZ | [ok informacja o wydanych decyzjach_wz_XII_24.xlsx](https://architektura.um.warszawa.pl/documents/12025039/126236715/ok+informacja+o+wydanych+decyzjach_wz_XII_24.xlsx/15e07f89-83f4-cfca-59c1-6d57315fa265?t=1736763576457) | 139 | 0 | 0 |
| [Informacja o wszczętych postępowaniach i wydanych decyzjach (2024 r.)](https://architektura.um.warszawa.pl/-/rejestry24) | 2024 | wszczęte | [informacja o wszczętych postępowaniach o wz,licp_XII_24.xlsx](https://architektura.um.warszawa.pl/documents/12025039/126431210/informacja+o+wszcz%C4%99tych+post%C4%99powaniach+o+wz%2Clicp_XII_24.xlsx/4a5a7f4b-0273-862c-797a-49db36efa218?t=1736871824094) | 79 | 0 | 0 |
| [Informacja o wszczętych postępowaniach i wydanych decyzjach (2024 r.)](https://architektura.um.warszawa.pl/-/rejestry24) | 2024 | ULICP C2 | [informacja o wydanych decyzjach ws. ustalenia_licp_pow-gm_XII_24.xlsx](https://architektura.um.warszawa.pl/documents/12025039/126431210/informacja+o+wydanych+decyzjach+ws.+ustalenia_licp_pow-gm_XII_24.xlsx/fcefbea9-393b-e177-186c-d7656b49a71b?t=1736871823203) | 20 | 0 | 0 |
| [Informacja o wszczętych postępowaniach i wydanych decyzjach (2024 r.)](https://architektura.um.warszawa.pl/-/rejestry24) | 2024 | ULICP C1 | [informacja o wydanych decyzjach ws. ustalenia_licp_kraj-woj_XII_24.xlsx](https://architektura.um.warszawa.pl/documents/12025039/126431210/informacja+o+wydanych+decyzjach+ws.+ustalenia_licp_kraj-woj_XII_24.xlsx/fbe4067e-4dd1-3f6b-3609-d0761c8c2cf4?t=1736871824369) | 1 | 0 | 0 |
| [Informacja o wszczętych postępowaniach i wydanych decyzjach (2023 r.)](https://architektura.um.warszawa.pl/-/rejestry23) | 2023 | WZ | [informacja o wydanych decyzjach_wz_XII_23 +.xlsx](https://architektura.um.warszawa.pl/documents/12025039/96120640/informacja+o+wydanych+decyzjach_wz_XII_23+%2B.xlsx/23cbd9fa-abb7-248d-4b9e-106e78a8cf5a?t=1705311090486) | 155 | 0 | 0 |
| [Informacja o wszczętych postępowaniach i wydanych decyzjach (2023 r.)](https://architektura.um.warszawa.pl/-/rejestry23) | 2023 | wszczęte | [ok informacja o wszczętych postępowaniach o wz,licp_XII_23+.xlsx](https://architektura.um.warszawa.pl/documents/12025039/96120640/ok+informacja+o+wszcz%C4%99tych+post%C4%99powaniach+o+wz%2Clicp_XII_23%2B.xlsx/d4c09d57-96e8-cca9-48a1-384eab9dca3a?t=1705311090763) | 123 | 0 | 0 |
| [Informacja o wszczętych postępowaniach i wydanych decyzjach (2023 r.)](https://architektura.um.warszawa.pl/-/rejestry23) | 2023 | ULICP C2 | [informacja o wydanych decyzjach ws. ustalenia_licp_pow-gm_XII_23+.xlsx](https://architektura.um.warszawa.pl/documents/12025039/96120640/informacja+o+wydanych+decyzjach+ws.+ustalenia_licp_pow-gm_XII_23%2B.xlsx/4a9fa06d-a879-922c-3526-ed698e82fa05?t=1705311089886) | 14 | 0 | 0 |
| [Informacja o wszczętych postępowaniach i wydanych decyzjach (2023 r.)](https://architektura.um.warszawa.pl/-/rejestry23) | 2023 | ULICP C1 | [informacja o wydanych decyzjach ws. ustalenia_licp_kraj-woj_XII_23+.xlsx](https://architektura.um.warszawa.pl/documents/12025039/96120640/informacja+o+wydanych+decyzjach+ws.+ustalenia_licp_kraj-woj_XII_23%2B.xlsx/1f343061-c89e-1e20-13e4-6292d3ed2a7a?t=1705311091046) | 1 | 0 | 0 |
| [Informacja o wszczętych postępowaniach i wydanych decyzjach (2022 r.)](https://architektura.um.warszawa.pl/-/rejestry2022) | 2022 | WZ | [informacja o wydanych decyzjach_wz_I-XII_22.xlsx](https://architektura.um.warszawa.pl/documents/12025039/69259400/informacja+o+wydanych+decyzjach_wz_I-XII_22.xlsx/5eb2c695-6228-1b14-4418-9dad94c8db7e?t=1673616553587) | 162 | 0 | 0 |
| [Informacja o wszczętych postępowaniach i wydanych decyzjach (2022 r.)](https://architektura.um.warszawa.pl/-/rejestry2022) | 2022 | wszczęte | [Informacja o wszczętych postępowaniach o wz,licp_I-XII_22.xlsx](https://architektura.um.warszawa.pl/documents/12025039/69259400/Informacja+o+wszcz%C4%99tych+post%C4%99powaniach+o+wz%2Clicp_I-XII_22.xlsx/23b3f50f-30ef-0cf0-7614-bcb5800f6b3d?t=1673616553796) | 86 | 0 | 0 |
| [Informacja o wszczętych postępowaniach i wydanych decyzjach (2022 r.)](https://architektura.um.warszawa.pl/-/rejestry2022) | 2022 | ULICP C2 | [informacja o wydanych decyzjach ws. ustalenia _licp pow-gm_I-XII_22.xlsx](https://architektura.um.warszawa.pl/documents/12025039/69259400/informacja+o+wydanych+decyzjach+ws.+ustalenia+_licp+pow-gm_I-XII_22.xlsx/a2e32ee9-3456-a724-ccf5-1c28d663d01d?t=1673616554019) | 13 | 0 | 0 |
| [Informacja o wszczętych postępowaniach i wydanych decyzjach (2022 r.)](https://architektura.um.warszawa.pl/-/rejestry2022) | 2022 | ULICP C1 | [informacja o wydanych decyzjach ws. ustalenia_licp_kraj-woj_I-XII_22.xlsx](https://architektura.um.warszawa.pl/documents/12025039/69259400/informacja+o+wydanych+decyzjach+ws.+ustalenia_licp_kraj-woj_I-XII_22.xlsx/4f9bfce6-cf90-180e-4f7d-8554d2bced70?t=1673616553272) | 5 | 0 | 0 |
| [Informacja o wszczętych postępowaniach i wydanych decyzjach (2021 r.)](https://architektura.um.warszawa.pl/-/rejestry2021) | 2021 | WZ | [informacja_decyzje_wz_I_XII_21+.xlsx](https://architektura.um.warszawa.pl/documents/12025039/41736355/informacja_decyzje_wz_I_XII_21%2B.xlsx/41a174fa-5a5b-2212-5eae-c0bc4d4b2a40?t=1642178443708) | 157 | 3 | 3 |
| [Informacja o wszczętych postępowaniach i wydanych decyzjach (2021 r.)](https://architektura.um.warszawa.pl/-/rejestry2021) | 2021 | wszczęte | [informacja_wnioski_wz _licp_I-XII_21.xlsx](https://architektura.um.warszawa.pl/documents/12025039/41736355/informacja_wnioski_wz+_licp_I-XII_21.xlsx/c32bf907-1784-ec79-c5c1-5a61265b8bf2?t=1642178443050) | 88 | 0 | 0 |
| [Informacja o wszczętych postępowaniach i wydanych decyzjach (2021 r.)](https://architektura.um.warszawa.pl/-/rejestry2021) | 2021 | ULICP C2 | [informacja_decyzje_licp_pow-gm_I-XII_21+.xlsx](https://architektura.um.warszawa.pl/documents/12025039/41736355/informacja_decyzje_licp_pow-gm_I-XII_21%2B.xlsx/c806117d-5072-c7f1-eef6-28d643a83cad?t=1642178443512) | 12 | 0 | 0 |
| [Informacja o wszczętych postępowaniach i wydanych decyzjach (2021 r.)](https://architektura.um.warszawa.pl/-/rejestry2021) | 2021 | ULICP C1 | [informacje_decyzje_licp_kraj-woj_I-XII_21+.xlsx](https://architektura.um.warszawa.pl/documents/12025039/41736355/informacje_decyzje_licp_kraj-woj_I-XII_21%2B.xlsx/599f76bc-3169-c175-6511-f5f75a015c5e?t=1642178443291) | 5 | 0 | 0 |
| [Informacja o wszczętych postępowaniach i wydanych decyzjach (sierpień - grudzień 2020 r.)](https://architektura.um.warszawa.pl/-/rejestry2020) | 2020 | WZ | [informacja_decyzje_wz_sierpien-grudzien_20.xlsx](https://architektura.um.warszawa.pl/documents/12025039/19717181/informacja_decyzje_wz_sierpien-grudzien_20.xlsx/d2a2aadb-492a-ceb6-4250-685e7ddfe11c?t=1634497931206) | 79 | 1 | 1 |
| [Informacja o wszczętych postępowaniach i wydanych decyzjach (sierpień - grudzień 2020 r.)](https://architektura.um.warszawa.pl/-/rejestry2020) | 2020 | wszczęte | [informacja_wnioski_wz__licp__sierpien-grudzien_20.xlsx](https://architektura.um.warszawa.pl/documents/12025039/19717181/informacja_wnioski_wz__licp__sierpien-grudzien_20.xlsx/efa0401d-4ae2-aec3-d6b6-536680e2e35f?t=1634497931212) | 55 | 0 | 0 |
| [Informacja o wszczętych postępowaniach i wydanych decyzjach (sierpień - grudzień 2020 r.)](https://architektura.um.warszawa.pl/-/rejestry2020) | 2020 | ULICP C2 | [informacja_dec._licp_pow_gmi_sierpien-grudzien_20.xlsx](https://architektura.um.warszawa.pl/documents/12025039/19717181/informacja_dec._licp_pow_gmi_sierpien-grudzien_20.xlsx/3f2da765-50ac-0efc-c47e-a02063a0d05c?t=1634497931200) | 6 | 0 | 0 |
| [Informacja o wszczętych postępowaniach i wydanych decyzjach (sierpień - grudzień 2020 r.)](https://architektura.um.warszawa.pl/-/rejestry2020) | 2020 | ULICP C1 | [informacja_decyzje_licp_kraj_woj_sierpien-_grudzien_20.xlsx](https://architektura.um.warszawa.pl/documents/12025039/19717181/informacja_decyzje_licp_kraj_woj_sierpien-_grudzien_20.xlsx/9fdd4da2-0828-b9a3-089e-f2c4d2dc2d37?t=1634497931193) | 6 | 0 | 0 |

* Records: 4 (WZ 4, CP 0, Wszczęcie 0); decision outcomes: Umorzenie postępowania 4.
* Listed in more than one snapshot / yearly file: 0.

## GUNB RWDZ (building permits and notifications)

GUNB publishes its register of building-permit decisions and notifications (*Rejestr wniosków, decyzji i zgłoszeń*, CC0 1.0) as three ZIP files rebuilt every night. Every case with a parcel in Praga-Południe (cadastral unit `146507_8`) is copied byte for byte into a committed extract (`data/raw/rwdz/`, mirrored to `site/sources/rwdz/`) and becomes one record in `permits.json`; the snapshot cited is the one the extract was taken from (a new GUNB file that changes nothing in the district is not adopted).

| File | Kind | Snapshot (Last-Modified) | Rows in the file | Praga-Południe rows | Records | Extract |
|---|---|---|---:|---:|---:|---|
| [wynik_mazowieckie.zip](https://wyszukiwarka.gunb.gov.pl/pliki_pobranie/wynik_mazowieckie.zip) | Pozwolenie | 2026-10-26T22:35:07Z | 695711 | 1386 | 712 | [`sources/d/zoliborz/rwdz/rwdz-wnioski.csv`](https://3-n.github.io/wzsearch/sources/d/zoliborz/rwdz/rwdz-wnioski.csv) |
| [wynik_zgloszenia_2016_2021.zip](https://wyszukiwarka.gunb.gov.pl/pliki_pobranie/wynik_zgloszenia_2016_2021.zip) | Zgłoszenie | 2026-10-26T22:36:03Z | 829354 | 126 | 34 | [`sources/d/zoliborz/rwdz/rwdz-zgloszenia-2016-2021.csv`](https://3-n.github.io/wzsearch/sources/d/zoliborz/rwdz/rwdz-zgloszenia-2016-2021.csv) |
| [wynik_zgloszenia_2022_up.zip](https://wyszukiwarka.gunb.gov.pl/pliki_pobranie/wynik_zgloszenia_2022_up.zip) | Zgłoszenie | 2026-10-26T22:36:07Z | 939616 | 34 | 6 | [`sources/d/zoliborz/rwdz/rwdz-zgloszenia-2022.csv`](https://3-n.github.io/wzsearch/sources/d/zoliborz/rwdz/rwdz-zgloszenia-2022.csv) |

Records per year (decision date for permits, filing date for notifications):

| Year | Pozwolenie | Zgłoszenie | Total |
|---|---:|---:|---:|
| 2016 | 104 | 3 | 107 |
| 2017 | 122 | 5 | 127 |
| 2018 | 72 | 7 | 79 |
| 2019 | 94 | 9 | 103 |
| 2020 | 51 | 9 | 60 |
| 2021 | 54 | 1 | 55 |
| 2022 | 49 | 1 | 50 |
| 2023 | 41 | 2 | 43 |
| 2024 | 49 | 2 | 51 |
| 2025 | 47 | 1 | 48 |
| 2026 | 29 | 0 | 29 |
| **all** | **712** | **40** | **752** |

* Issuer: Pozwolenie: Inny organ 687, Urząd m.st. Warszawy (Biuro Architektury i Planowania Przestrzennego) 20, Wojewoda Mazowiecki 5; Zgłoszenie: Inny organ 36, Wojewoda Mazowiecki 3, Urząd m.st. Warszawy (Biuro Architektury i Planowania Przestrzennego) 1.
* Scope of works: Pozwolenie: Inne roboty budowlane (np. przebudowa, remont) 491, Budowa nowego obiektu 108, Rozbudowa 73, Rozbiórka 25, Nadbudowa 10, nie podano 4, Odbudowa 1; Zgłoszenie: Budowa nowego obiektu 39, Rozbudowa 1.
* Object category: Pozwolenie: XIII 215, I 151, – 78, XXVI 68, IX 60, XVI 32, VIII 30, III 17, XVII 12, XI 10, XVIII 9, XII 6, X 5, VI 3, XXV 3, XV 2, XXII 2, XXIX 2, IV 1, V 1, VII 1, XIV 1, XXVII 1, XXVIII 1, XXX 1; Zgłoszenie: XXVI 38, IX 1, VIII 1.
* Investor: Pozwolenie: organisation 601, natural person (not named by GUNB) 111; Zgłoszenie: not published 40.
* Application → decision (permits): median 86 days, 90th percentile 197 days.
* Cubature given: 162 of 752 records (the placeholders 0 and 1 count as not given).
* Without a parcel in the register: 2 ([`pb-st-mz-zo-2024-35813`](https://3-n.github.io/wzsearch/#/wpis/pb-st-mz-zo-2024-35813?dz=zoliborz), [`pb-st-mz-zo-2024-28390`](https://3-n.github.io/wzsearch/#/wpis/pb-st-mz-zo-2024-28390?dz=zoliborz)).
* Cases that also cover parcels of other districts (kept whole, those parcels keep their unit): 2 ([`zg-pl-mz-2018-259`](https://3-n.github.io/wzsearch/#/wpis/zg-pl-mz-2018-259?dz=zoliborz), [`pb-st-mz-wa-2016-39019`](https://3-n.github.io/wzsearch/#/wpis/pb-st-mz-wa-2016-39019?dz=zoliborz)).

Register rows of the district office (*Prezydent Miasta Warszawa - Praga Płd.*) with a broken cadastral unit are kept and corrected to `146507_8` (a warning on the record), and so are the rows of the cases in `rwdz.UNIT_FIXES` (`listed`: register errors checked one by one in ULDK, any organ); a valid other Warsaw unit two or more edits away is genuine and not kept:

* `rwdz-wnioski`: kept – invalid 1, typo 8; not kept – none.
* `rwdz-zgloszenia-2016-2021`: kept – none; not kept – none.
* `rwdz-zgloszenia-2022`: kept – none; not kept – none.

## Related records across datasets

`related` links records that share a cadastral parcel or a street + house number, across all three datasets. A shared parcel is not necessarily the same project (a large housing-estate parcel carries many unrelated renovations).

* Dzielnica: 3 of 12 records relate to at least one permit or notification.
* BAiPP (miasto): 2 of 4 records relate to at least one permit or notification.
* GUNB RWDZ: 18 of 752 permits/notifications relate to a WZ/ULICP record.
* WZ decisions (not refused/discontinued) followed by a building permit on the same parcel: 0 of 9.
* Most related: [`pb-st-mz-zo-2017-889`](https://3-n.github.io/wzsearch/#/wpis/pb-st-mz-zo-2017-889?dz=zoliborz) (31), [`pb-st-mz-zo-2017-18968`](https://3-n.github.io/wzsearch/#/wpis/pb-st-mz-zo-2017-18968?dz=zoliborz) (23), [`pb-st-mz-zo-2016-6652`](https://3-n.github.io/wzsearch/#/wpis/pb-st-mz-zo-2016-6652?dz=zoliborz) (22), [`pb-st-mz-zo-2016-6659`](https://3-n.github.io/wzsearch/#/wpis/pb-st-mz-zo-2016-6659?dz=zoliborz) (22), [`pb-st-mz-zo-2016-41217`](https://3-n.github.io/wzsearch/#/wpis/pb-st-mz-zo-2016-41217?dz=zoliborz) (22).

## Geolocation

| Method | Dzielnica | BAiPP (miasto) | GUNB RWDZ |
|---|---:|---:|---:|
| parcel (ULDK centroid) | 12 (100.0%) | 3 (75.0%) | 710 (94.4%) |
| address point (UUG) | 0 (0.0%) | 0 (0.0%) | 29 (3.9%) |
| street / crossing (approximate) | 0 (0.0%) | 1 (25.0%) | 4 (0.5%) |
| not located | 0 (0.0%) | 0 (0.0%) | 9 (1.2%) |
| **located** | **12** (**100.0%**) | **4** (**100.0%**) | **743** (**98.8%**) |

* Unique parcel ids (all datasets): 953; found in ULDK 892 (93.6%), missing 61, lookup errors 0.
* Records with parcels: 766 – all found 679, some 40, none 47.
* Precinct of the source corrected by the parcel under the exact address (ULDK GetParcelByXY; a warning on the record): 13.
* Address vs parcel conflicts (> 300 m; parcel point kept): 3, of which the address lies on a parcel of another precinct (`geo.conflict`): 3; parcels > 1 km apart: 0; point moved onto the largest parcel (centroid on none of them): 71; point from the parcels in the district only (others lie in a neighbouring district): 0; points discarded outside the district: 0.
* Parcel ids ULDK does not know (first 20): `146519_8.0414.14`, `146519_8.0414.16/2`, `146519_8.0303.13/3`, `146519_8.0305.50/2`, `146519_8.0305.31`, `146519_8.0305.32`, `146519_8.0305.49/1`, `146519_8.0304.29/3`, `146519_8.0304.1/12`, `146519_8.0304.42`, `146519_8.0304.43`, `146519_8.0304.47`, `146519_8.0304.48`, `146519_8.0304.28`, `146519_8.0304.29/2`, `146519_8.0112.45`, `146519_8.0203.12/3`, `146519_8.0303.2/1`, `146519_8.0306.5/6`, `146519_8.0306.15/2`.
* Records per MSI area (Dzielnica): marymont-potok 10, sady-zoliborskie 1, stary-zoliborz 1.
* Records per MSI area (BAiPP (miasto)): marymont-potok 1, sady-zoliborskie 3.
* Records per MSI area (GUNB RWDZ): (none) 9, marymont-potok 89, sady-zoliborskie 206, stary-zoliborz 448.

GUNB RWDZ records without a location (9):

| Record | Address | Parcels (as in source) | Note |
|---|---|---|---|
| [`pb-st-mz-sr-2022-12880`](https://3-n.github.io/wzsearch/#/wpis/pb-st-mz-sr-2022-12880?dz=zoliborz) | Żurawia 6/12 | 146519_8 0502 99 | działek nie znaleziono w ewidencji gruntów (ULDK) – mogły zostać podzielone lub scalone; nie udało się ustalić lokalizacji |
| [`zg-st-mz-zo-2020-4141`](https://3-n.github.io/wzsearch/#/wpis/zg-st-mz-zo-2020-4141?dz=zoliborz) |  | 146519_8 0303 9/5 | działek nie znaleziono w ewidencji gruntów (ULDK) – mogły zostać podzielone lub scalone; nie udało się ustalić lokalizacji |
| [`zg-st-mz-zo-2020-589`](https://3-n.github.io/wzsearch/#/wpis/zg-st-mz-zo-2020-589?dz=zoliborz) |  | 146519_8 0303 9/8 \| 146519_8 0303 9/5 | działek nie znaleziono w ewidencji gruntów (ULDK) – mogły zostać podzielone lub scalone; nie udało się ustalić lokalizacji |
| [`pb-st-mz-sr-2019-38623`](https://3-n.github.io/wzsearch/#/wpis/pb-st-mz-sr-2019-38623?dz=zoliborz) | Górnośląska | 146519_8 0609 86/3 \| 146519_8 0609 45 \| 146519_8 0609 86/27 | działek nie znaleziono w ewidencji gruntów (ULDK) – mogły zostać podzielone lub scalone; nie udało się ustalić lokalizacji |
| [`pb-st-mz-wi-2019-23163`](https://3-n.github.io/wzsearch/#/wpis/pb-st-mz-wi-2019-23163?dz=zoliborz) |  | 146519_8 0538 134 | działek nie znaleziono w ewidencji gruntów (ULDK) – mogły zostać podzielone lub scalone; nie udało się ustalić lokalizacji |
| [`pb-st-mz-zo-2019-19259`](https://3-n.github.io/wzsearch/#/wpis/pb-st-mz-zo-2019-19259?dz=zoliborz) |  | 146519_8 0303 9/5 | działek nie znaleziono w ewidencji gruntów (ULDK) – mogły zostać podzielone lub scalone; nie udało się ustalić lokalizacji |
| [`pb-st-mz-sr-2019-23652`](https://3-n.github.io/wzsearch/#/wpis/pb-st-mz-sr-2019-23652?dz=zoliborz) | Czerniakowska 124 | 146519_8 0614 2 | działek nie znaleziono w ewidencji gruntów (ULDK) – mogły zostać podzielone lub scalone; nie udało się ustalić lokalizacji |
| [`pb-st-mz-sr-2017-2778`](https://3-n.github.io/wzsearch/#/wpis/pb-st-mz-sr-2017-2778?dz=zoliborz) | Wiślana 8 | 146519_8 0403 22 | działek nie znaleziono w ewidencji gruntów (ULDK) – mogły zostać podzielone lub scalone; nie udało się ustalić lokalizacji |
| [`pb-st-mz-sr-2016-6718`](https://3-n.github.io/wzsearch/#/wpis/pb-st-mz-sr-2016-6718?dz=zoliborz) | Długa | 146519_8 0208 30 | działek nie znaleziono w ewidencji gruntów (ULDK) – mogły zostać podzielone lub scalone; nie udało się ustalić lokalizacji |

Location notes:

| Note | Dzielnica | BAiPP (miasto) | GUNB RWDZ | Examples |
|---|---:|---:|---:|---|
| działek nie znaleziono w ewidencji gruntów (ULDK) – mogły zostać podzielone lub scalone | 0 | 1 | 40 | [`wz-am-zol-2021-49`](https://3-n.github.io/wzsearch/#/wpis/wz-am-zol-2021-49?dz=zoliborz), [`pb-st-mz-zo-2023-30639`](https://3-n.github.io/wzsearch/#/wpis/pb-st-mz-zo-2023-30639?dz=zoliborz), [`pb-st-mz-sr-2022-12880`](https://3-n.github.io/wzsearch/#/wpis/pb-st-mz-sr-2022-12880?dz=zoliborz), [`pb-st-mz-zo-2021-3398`](https://3-n.github.io/wzsearch/#/wpis/pb-st-mz-zo-2021-3398?dz=zoliborz), [`pb-st-mz-zo-2020-49844`](https://3-n.github.io/wzsearch/#/wpis/pb-st-mz-zo-2020-49844?dz=zoliborz) |
| w ewidencji gruntów (ULDK) znaleziono N z N działek | 4 | 1 | 35 | [`wz-zol-2023-3`](https://3-n.github.io/wzsearch/#/wpis/wz-zol-2023-3?dz=zoliborz), [`wz-zol-2023-1`](https://3-n.github.io/wzsearch/#/wpis/wz-zol-2023-1?dz=zoliborz), [`wz-zol-2021-4`](https://3-n.github.io/wzsearch/#/wpis/wz-zol-2021-4?dz=zoliborz), [`wz-zol-2021-3`](https://3-n.github.io/wzsearch/#/wpis/wz-zol-2021-3?dz=zoliborz), [`wz-am-zol-2020-90`](https://3-n.github.io/wzsearch/#/wpis/wz-am-zol-2020-90?dz=zoliborz) |
| nie udało się ustalić lokalizacji | 0 | 0 | 9 | [`pb-st-mz-sr-2022-12880`](https://3-n.github.io/wzsearch/#/wpis/pb-st-mz-sr-2022-12880?dz=zoliborz), [`zg-st-mz-zo-2020-4141`](https://3-n.github.io/wzsearch/#/wpis/zg-st-mz-zo-2020-4141?dz=zoliborz), [`zg-st-mz-zo-2020-589`](https://3-n.github.io/wzsearch/#/wpis/zg-st-mz-zo-2020-589?dz=zoliborz), [`pb-st-mz-sr-2019-38623`](https://3-n.github.io/wzsearch/#/wpis/pb-st-mz-sr-2019-38623?dz=zoliborz), [`pb-st-mz-wi-2019-23163`](https://3-n.github.io/wzsearch/#/wpis/pb-st-mz-wi-2019-23163?dz=zoliborz) |
| lokalizacja przybliżona – ulica w obrębie N | 0 | 0 | 4 | [`zg-st-mz-zo-2020-5702`](https://3-n.github.io/wzsearch/#/wpis/zg-st-mz-zo-2020-5702?dz=zoliborz), [`pb-st-mz-zo-2018-32171`](https://3-n.github.io/wzsearch/#/wpis/pb-st-mz-zo-2018-32171?dz=zoliborz), [`pb-st-mz-zo-2017-18971`](https://3-n.github.io/wzsearch/#/wpis/pb-st-mz-zo-2017-18971?dz=zoliborz), [`pb-st-mz-zo-2016-25462`](https://3-n.github.io/wzsearch/#/wpis/pb-st-mz-zo-2016-25462?dz=zoliborz) |
| adres … leży ok. N m od wskazanych działek | 0 | 0 | 3 | [`pb-st-mz-zo-2021-53045`](https://3-n.github.io/wzsearch/#/wpis/pb-st-mz-zo-2021-53045?dz=zoliborz), [`pb-st-mz-zo-2019-9468`](https://3-n.github.io/wzsearch/#/wpis/pb-st-mz-zo-2019-9468?dz=zoliborz), [`pb-st-mz-zo-2016-6703`](https://3-n.github.io/wzsearch/#/wpis/pb-st-mz-zo-2016-6703?dz=zoliborz) |
| działki N (…) nie ma już w ewidencji (…) – przyjęto jej części znane z innych wpisów: N | 0 | 0 | 3 | [`pb-st-mz-zo-2025-31294`](https://3-n.github.io/wzsearch/#/wpis/pb-st-mz-zo-2025-31294?dz=zoliborz), [`pb-st-mz-zo-2025-31294`](https://3-n.github.io/wzsearch/#/wpis/pb-st-mz-zo-2025-31294?dz=zoliborz), [`pb-st-mz-zo-2020-32383`](https://3-n.github.io/wzsearch/#/wpis/pb-st-mz-zo-2020-32383?dz=zoliborz) |
| lokalizacja przybliżona – budynek nr N | 0 | 0 | 2 | [`pb-st-mz-zo-2018-15881`](https://3-n.github.io/wzsearch/#/wpis/pb-st-mz-zo-2018-15881?dz=zoliborz), [`pb-st-mz-zo-2018-15886`](https://3-n.github.io/wzsearch/#/wpis/pb-st-mz-zo-2018-15886?dz=zoliborz) |
| działki N (…) nie ma już w ewidencji (…) – przyjęto jej części znane z innych wpisów: N, N | 0 | 0 | 1 | [`pb-st-mz-zo-2025-31294`](https://3-n.github.io/wzsearch/#/wpis/pb-st-mz-zo-2025-31294?dz=zoliborz) |
| działki N (…) nie ma już w ewidencji (…) – przyjęto jej część leżącą pod adresem: N | 0 | 0 | 1 | [`pb-st-mz-zo-2022-22478`](https://3-n.github.io/wzsearch/#/wpis/pb-st-mz-zo-2022-22478?dz=zoliborz) |
| lokalizacja przybliżona – ulica | 0 | 1 | 0 | [`wz-am-zol-2021-49`](https://3-n.github.io/wzsearch/#/wpis/wz-am-zol-2021-49?dz=zoliborz) |
| ulica nie przechodzi przez obręb z rejestru (…) | 0 | 1 | 0 | [`wz-am-zol-2021-49`](https://3-n.github.io/wzsearch/#/wpis/wz-am-zol-2021-49?dz=zoliborz) |

## Record warnings

35 records carry 44 warnings (shown in the UI next to the record).

| Warning type | Dzielnica | BAiPP (miasto) | GUNB RWDZ | Examples |
|---|---:|---:|---:|---|
| identyfikator jednostki ewidencyjnej w rejestrze „…” potraktowano jako 146519_8 (…) – sprawa urzędu dzielnicy, prawdopodobna literówka | 0 | 0 | 8 | [`pb-st-mz-zo-2023-23134`](https://3-n.github.io/wzsearch/#/wpis/pb-st-mz-zo-2023-23134?dz=zoliborz), [`pb-st-mz-zo-2022-21763`](https://3-n.github.io/wzsearch/#/wpis/pb-st-mz-zo-2022-21763?dz=zoliborz), [`pb-st-mz-zo-2022-12406`](https://3-n.github.io/wzsearch/#/wpis/pb-st-mz-zo-2022-12406?dz=zoliborz), [`pb-st-mz-zo-2019-32932`](https://3-n.github.io/wzsearch/#/wpis/pb-st-mz-zo-2019-32932?dz=zoliborz), [`pb-st-mz-zo-2019-3701`](https://3-n.github.io/wzsearch/#/wpis/pb-st-mz-zo-2019-3701?dz=zoliborz) |
| pominięto niezrozumiały fragment oznaczenia działek: „…” | 7 | 0 | 0 | [`wz-zol-2023-3`](https://3-n.github.io/wzsearch/#/wpis/wz-zol-2023-3?dz=zoliborz), [`wz-zol-2023-1`](https://3-n.github.io/wzsearch/#/wpis/wz-zol-2023-1?dz=zoliborz), [`wz-zol-2022-1-2`](https://3-n.github.io/wzsearch/#/wpis/wz-zol-2022-1-2?dz=zoliborz), [`wz-zol-2021-4`](https://3-n.github.io/wzsearch/#/wpis/wz-zol-2021-4?dz=zoliborz), [`wz-zol-2021-3`](https://3-n.github.io/wzsearch/#/wpis/wz-zol-2021-3?dz=zoliborz) |
| rodzaj pozycji przyjęto z opisu na stronie (…) | 4 | 0 | 0 | [`wz-zol-2021-4`](https://3-n.github.io/wzsearch/#/wpis/wz-zol-2021-4?dz=zoliborz), [`wz-zol-2021-3`](https://3-n.github.io/wzsearch/#/wpis/wz-zol-2021-3?dz=zoliborz), [`wz-zol-2021-2`](https://3-n.github.io/wzsearch/#/wpis/wz-zol-2021-2?dz=zoliborz), [`wz-zol-2021-1`](https://3-n.github.io/wzsearch/#/wpis/wz-zol-2021-1?dz=zoliborz) |
| ten sam numer (…) występuje w źródłach z inną treścią – rozdzielono na N pozycje | 2 | 0 | 0 | [`wz-zol-2022-1-2`](https://3-n.github.io/wzsearch/#/wpis/wz-zol-2022-1-2?dz=zoliborz), [`wz-zol-2022-1`](https://3-n.github.io/wzsearch/#/wpis/wz-zol-2022-1?dz=zoliborz) |
| wartość w kolumnie bez rozpoznanego pola: „…” | 2 | 0 | 0 | [`wz-zol-2021-4`](https://3-n.github.io/wzsearch/#/wpis/wz-zol-2021-4?dz=zoliborz), [`wz-zol-2021-2`](https://3-n.github.io/wzsearch/#/wpis/wz-zol-2021-2?dz=zoliborz) |
| wiersz rejestru (…) bez oznaczenia działki | 0 | 0 | 2 | [`pb-st-mz-zo-2024-35813`](https://3-n.github.io/wzsearch/#/wpis/pb-st-mz-zo-2024-35813?dz=zoliborz), [`pb-st-mz-zo-2024-28390`](https://3-n.github.io/wzsearch/#/wpis/pb-st-mz-zo-2024-28390?dz=zoliborz) |
| data z dodatkowym tekstem (…) | 1 | 0 | 0 | [`ws-zol-6733-2022-1`](https://3-n.github.io/wzsearch/#/wpis/ws-zol-6733-2022-1?dz=zoliborz) |
| działki zapisane po ostatnim obrębie przypisano do obrębu N | 1 | 0 | 0 | [`wz-zol-2021-2`](https://3-n.github.io/wzsearch/#/wpis/wz-zol-2021-2?dz=zoliborz) |
| kubatura zapisana w rejestrze w zaokrągleniu (…) | 0 | 0 | 1 | [`pb-st-mz-wa-2022-10413`](https://3-n.github.io/wzsearch/#/wpis/pb-st-mz-wa-2022-10413?dz=zoliborz) |
| numer decyzji wskazuje na CP, a plik na WZ | 1 | 0 | 0 | [`wz-zol-2022-1`](https://3-n.github.io/wzsearch/#/wpis/wz-zol-2022-1?dz=zoliborz) |
| obręb w źródle (…) prawdopodobnie błędny – działka N (…) pod adresem Adama Mickiewicza 36A leży w obrębie N | 0 | 0 | 1 | [`pb-st-mz-zo-2022-22478`](https://3-n.github.io/wzsearch/#/wpis/pb-st-mz-zo-2022-22478?dz=zoliborz) |
| obręb w źródle (…) prawdopodobnie błędny – działka N pod adresem Adama Mickiewicza 36A leży w obrębie N | 0 | 0 | 1 | [`pb-st-mz-zo-2020-49783`](https://3-n.github.io/wzsearch/#/wpis/pb-st-mz-zo-2020-49783?dz=zoliborz) |
| obręb w źródle (…) prawdopodobnie błędny – działka N pod adresem Adama Mickiewicza N leży w obrębie N | 0 | 0 | 1 | [`pb-st-mz-zo-2020-18368`](https://3-n.github.io/wzsearch/#/wpis/pb-st-mz-zo-2020-18368?dz=zoliborz) |
| obręb w źródle (…) prawdopodobnie błędny – działka N pod adresem Adolfa Dygasińskiego N leży w obrębie N | 0 | 0 | 1 | [`pb-st-mz-zo-2016-29966`](https://3-n.github.io/wzsearch/#/wpis/pb-st-mz-zo-2016-29966?dz=zoliborz) |
| obręb w źródle (…) prawdopodobnie błędny – działka N pod adresem Albina Jakiela N leży w obrębie N | 0 | 0 | 1 | [`pb-st-mz-zo-2021-4568`](https://3-n.github.io/wzsearch/#/wpis/pb-st-mz-zo-2021-4568?dz=zoliborz) |
| obręb w źródle (…) prawdopodobnie błędny – działka N pod adresem Alojzego Felińskiego N leży w obrębie N | 0 | 0 | 1 | [`pb-st-mz-zo-2020-553`](https://3-n.github.io/wzsearch/#/wpis/pb-st-mz-zo-2020-553?dz=zoliborz) |
| obręb w źródle (…) prawdopodobnie błędny – działka N pod adresem Augusta Cieszkowskiego N leży w obrębie N | 0 | 0 | 1 | [`pb-st-mz-zo-2022-36166`](https://3-n.github.io/wzsearch/#/wpis/pb-st-mz-zo-2022-36166?dz=zoliborz) |
| obręb w źródle (…) prawdopodobnie błędny – działka N pod adresem Elbląska N leży w obrębie N | 0 | 0 | 1 | [`pb-st-mz-zo-2026-22246`](https://3-n.github.io/wzsearch/#/wpis/pb-st-mz-zo-2026-22246?dz=zoliborz) |
| obręb w źródle (…) prawdopodobnie błędny – działka N pod adresem Gdańska N leży w obrębie N | 0 | 0 | 1 | [`pb-st-mz-zo-2016-17080`](https://3-n.github.io/wzsearch/#/wpis/pb-st-mz-zo-2016-17080?dz=zoliborz) |
| obręb w źródle (…) prawdopodobnie błędny – działka N pod adresem Juliusza Słowackiego N leży w obrębie N | 0 | 0 | 1 | [`pb-st-mz-zo-2016-21347`](https://3-n.github.io/wzsearch/#/wpis/pb-st-mz-zo-2016-21347?dz=zoliborz) |
| obręb w źródle (…) prawdopodobnie błędny – działka N pod adresem Kazimierza Promyka N leży w obrębie N | 0 | 0 | 1 | [`pb-st-mz-zo-2022-26046`](https://3-n.github.io/wzsearch/#/wpis/pb-st-mz-zo-2022-26046?dz=zoliborz) |
| obręb w źródle (…) prawdopodobnie błędny – działka N pod adresem Plac Słoneczny N leży w obrębie N | 0 | 0 | 1 | [`pb-st-mz-zo-2017-23277`](https://3-n.github.io/wzsearch/#/wpis/pb-st-mz-zo-2017-23277?dz=zoliborz) |
| obręb w źródle (…) prawdopodobnie błędny – działka N pod adresem Stefana Pogonowskiego N leży w obrębie N | 0 | 0 | 1 | [`pb-st-mz-zo-2017-27541`](https://3-n.github.io/wzsearch/#/wpis/pb-st-mz-zo-2017-27541?dz=zoliborz) |
| sprawa obejmuje też działki spoza Żoliborza – jednostka ewidencyjna 146504_8 (…): N | 0 | 0 | 1 | [`zg-pl-mz-2018-259`](https://3-n.github.io/wzsearch/#/wpis/zg-pl-mz-2018-259?dz=zoliborz) |
| sprawa obejmuje też działki spoza Żoliborza – jednostka ewidencyjna 146510_8 (…): N | 0 | 0 | 1 | [`pb-st-mz-wa-2016-39019`](https://3-n.github.io/wzsearch/#/wpis/pb-st-mz-wa-2016-39019?dz=zoliborz) |

## Classification

| Tag | Group | Dzielnica | BAiPP (miasto) | GUNB RWDZ |
|---|---|---:|---:|---:|
| Dom jednorodzinny (`jednorodzinny`) | funkcja | 1 | 0 | 147 |
| Budynek wielorodzinny (`wielorodzinny`) | funkcja | 5 | 3 | 217 |
| Adaptacja na mieszkanie (`adaptacja-mieszkalna`) | funkcja | 0 | 0 | 11 |
| Akademik, hostel, hotel (`zamieszkanie-zbiorowe`) | funkcja | 0 | 0 | 2 |
| Handel, usługi, biura (`uslugi`) | funkcja | 1 | 1 | 80 |
| Żłobek, przedszkole, szkoła (`oswiata`) | funkcja | 0 | 0 | 37 |
| Kultura (`kultura`) | funkcja | 0 | 0 | 19 |
| Zdrowie i opieka (`zdrowie-opieka`) | funkcja | 0 | 2 | 11 |
| Sport, rekreacja, zieleń (`sport-rekreacja-zielen`) | funkcja | 1 | 0 | 13 |
| Obiekt sakralny (`kult-religijny`) | funkcja | 0 | 0 | 7 |
| Sieci: woda, ciepło, prąd, gaz (`infrastruktura`) | funkcja | 0 | 0 | 104 |
| Instalacje w budynku (gaz, woda, c.o.) (`instalacje-wewnetrzne`) | funkcja | 0 | 0 | 95 |
| Telekomunikacja (`telekomunikacja`) | funkcja | 0 | 0 | 14 |
| Drogi i transport (`drogi-transport`) | funkcja | 1 | 0 | 15 |
| Parking, garaż (`parkingi-garaze`) | funkcja | 1 | 1 | 23 |
| Reklama (`reklama`) | funkcja | 0 | 0 | 1 |
| Przemysł, magazyny (`przemysl-magazyny`) | funkcja | 0 | 0 | 17 |
| Wiata, altana, budynek gospodarczy (`obiekty-pomocnicze`) | funkcja | 0 | 0 | 19 |
| Winda, dostępność (`windy-dostepnosc`) | funkcja | 0 | 0 | 10 |
| Nowa budowa (`nowa-budowa`) | roboty | 4 | 0 | 205 |
| Rozbudowa, nadbudowa, przebudowa (`rozbudowa-przebudowa`) | roboty | 1 | 1 | 368 |
| Remont, docieplenie (`remont`) | roboty | 0 | 0 | 159 |
| Zmiana sposobu użytkowania (`zmiana-sposobu-uzytkowania`) | roboty | 0 | 0 | 57 |
| Zmiana lub umorzenie (`zmiana-decyzji`) | roboty | 2 | 4 | 23 |
| Legalizacja (`legalizacja`) | roboty | 0 | 0 | 0 |
| Rozbiórka (`rozbiorka`) | roboty | 0 | 0 | 63 |

* Dzielnica – untagged records: 1 – [`wz-zol-2023-5`](https://3-n.github.io/wzsearch/#/wpis/wz-zol-2023-5?dz=zoliborz); without a "what is built" (funkcja) tag: 4 – [`wz-zol-2023-5`](https://3-n.github.io/wzsearch/#/wpis/wz-zol-2023-5?dz=zoliborz), [`wz-zol-2023-2`](https://3-n.github.io/wzsearch/#/wpis/wz-zol-2023-2?dz=zoliborz), [`wz-zol-2022-1`](https://3-n.github.io/wzsearch/#/wpis/wz-zol-2022-1?dz=zoliborz), [`ws-zol-6733-2022-1`](https://3-n.github.io/wzsearch/#/wpis/ws-zol-6733-2022-1?dz=zoliborz).
* BAiPP (miasto) – untagged records: 0; without a "what is built" (funkcja) tag: 0.
* GUNB RWDZ – untagged records: 12 – [`pb-st-mz-zo-2024-35813`](https://3-n.github.io/wzsearch/#/wpis/pb-st-mz-zo-2024-35813?dz=zoliborz), [`pb-st-mz-zo-2024-12951`](https://3-n.github.io/wzsearch/#/wpis/pb-st-mz-zo-2024-12951?dz=zoliborz), [`pb-st-mz-zo-2018-28415`](https://3-n.github.io/wzsearch/#/wpis/pb-st-mz-zo-2018-28415?dz=zoliborz), [`pb-st-mz-zo-2018-11930`](https://3-n.github.io/wzsearch/#/wpis/pb-st-mz-zo-2018-11930?dz=zoliborz), [`pb-st-mz-zo-2018-19072`](https://3-n.github.io/wzsearch/#/wpis/pb-st-mz-zo-2018-19072?dz=zoliborz), [`pb-st-mz-zo-2016-29948`](https://3-n.github.io/wzsearch/#/wpis/pb-st-mz-zo-2016-29948?dz=zoliborz), [`pb-st-mz-zo-2016-29983`](https://3-n.github.io/wzsearch/#/wpis/pb-st-mz-zo-2016-29983?dz=zoliborz), [`pb-st-mz-zo-2016-29975`](https://3-n.github.io/wzsearch/#/wpis/pb-st-mz-zo-2016-29975?dz=zoliborz), [`pb-st-mz-zo-2016-21379`](https://3-n.github.io/wzsearch/#/wpis/pb-st-mz-zo-2016-21379?dz=zoliborz), [`pb-st-mz-zo-2016-17286`](https://3-n.github.io/wzsearch/#/wpis/pb-st-mz-zo-2016-17286?dz=zoliborz), [`pb-st-mz-zo-2016-6703`](https://3-n.github.io/wzsearch/#/wpis/pb-st-mz-zo-2016-6703?dz=zoliborz), [`pb-st-mz-zo-2016-6646`](https://3-n.github.io/wzsearch/#/wpis/pb-st-mz-zo-2016-6646?dz=zoliborz); without a "what is built" (funkcja) tag: 58 – [`pb-st-mz-zo-2026-22246`](https://3-n.github.io/wzsearch/#/wpis/pb-st-mz-zo-2026-22246?dz=zoliborz), [`pb-st-mz-zo-2025-39250`](https://3-n.github.io/wzsearch/#/wpis/pb-st-mz-zo-2025-39250?dz=zoliborz), [`pb-st-mz-zo-2025-33157`](https://3-n.github.io/wzsearch/#/wpis/pb-st-mz-zo-2025-33157?dz=zoliborz), [`pb-st-mz-zo-2025-36357`](https://3-n.github.io/wzsearch/#/wpis/pb-st-mz-zo-2025-36357?dz=zoliborz), [`pb-st-mz-zo-2025-29327`](https://3-n.github.io/wzsearch/#/wpis/pb-st-mz-zo-2025-29327?dz=zoliborz), [`pb-st-mz-zo-2024-35813`](https://3-n.github.io/wzsearch/#/wpis/pb-st-mz-zo-2024-35813?dz=zoliborz), [`pb-st-mz-zo-2024-18611`](https://3-n.github.io/wzsearch/#/wpis/pb-st-mz-zo-2024-18611?dz=zoliborz), [`pb-st-mz-zo-2024-12943`](https://3-n.github.io/wzsearch/#/wpis/pb-st-mz-zo-2024-12943?dz=zoliborz), [`pb-st-mz-zo-2024-3646`](https://3-n.github.io/wzsearch/#/wpis/pb-st-mz-zo-2024-3646?dz=zoliborz), [`pb-st-mz-zo-2024-12951`](https://3-n.github.io/wzsearch/#/wpis/pb-st-mz-zo-2024-12951?dz=zoliborz), [`pb-st-mz-zo-2023-11978`](https://3-n.github.io/wzsearch/#/wpis/pb-st-mz-zo-2023-11978?dz=zoliborz), [`pb-st-mz-zo-2023-19530`](https://3-n.github.io/wzsearch/#/wpis/pb-st-mz-zo-2023-19530?dz=zoliborz), [`pb-st-mz-zo-2023-3837`](https://3-n.github.io/wzsearch/#/wpis/pb-st-mz-zo-2023-3837?dz=zoliborz), [`pb-st-mz-zo-2022-6669`](https://3-n.github.io/wzsearch/#/wpis/pb-st-mz-zo-2022-6669?dz=zoliborz), [`pb-st-mz-zo-2021-45784`](https://3-n.github.io/wzsearch/#/wpis/pb-st-mz-zo-2021-45784?dz=zoliborz), [`pb-st-mz-zo-2021-46948`](https://3-n.github.io/wzsearch/#/wpis/pb-st-mz-zo-2021-46948?dz=zoliborz), [`pb-st-mz-zo-2021-37020`](https://3-n.github.io/wzsearch/#/wpis/pb-st-mz-zo-2021-37020?dz=zoliborz), [`pb-st-mz-zo-2019-34557`](https://3-n.github.io/wzsearch/#/wpis/pb-st-mz-zo-2019-34557?dz=zoliborz), [`pb-st-mz-zo-2019-40841`](https://3-n.github.io/wzsearch/#/wpis/pb-st-mz-zo-2019-40841?dz=zoliborz), [`pb-st-mz-zo-2019-32887`](https://3-n.github.io/wzsearch/#/wpis/pb-st-mz-zo-2019-32887?dz=zoliborz), [`pb-st-mz-zo-2019-4138`](https://3-n.github.io/wzsearch/#/wpis/pb-st-mz-zo-2019-4138?dz=zoliborz), [`pb-st-mz-zo-2018-28415`](https://3-n.github.io/wzsearch/#/wpis/pb-st-mz-zo-2018-28415?dz=zoliborz), [`pb-st-mz-zo-2018-11930`](https://3-n.github.io/wzsearch/#/wpis/pb-st-mz-zo-2018-11930?dz=zoliborz), [`pb-st-mz-zo-2018-19072`](https://3-n.github.io/wzsearch/#/wpis/pb-st-mz-zo-2018-19072?dz=zoliborz), [`pb-st-mz-zo-2018-11430`](https://3-n.github.io/wzsearch/#/wpis/pb-st-mz-zo-2018-11430?dz=zoliborz), [`pb-st-mz-zo-2017-36275`](https://3-n.github.io/wzsearch/#/wpis/pb-st-mz-zo-2017-36275?dz=zoliborz), [`pb-st-mz-zo-2017-27552`](https://3-n.github.io/wzsearch/#/wpis/pb-st-mz-zo-2017-27552?dz=zoliborz), [`pb-st-mz-zo-2017-27567`](https://3-n.github.io/wzsearch/#/wpis/pb-st-mz-zo-2017-27567?dz=zoliborz), [`pb-st-mz-zo-2017-18966`](https://3-n.github.io/wzsearch/#/wpis/pb-st-mz-zo-2017-18966?dz=zoliborz), [`pb-st-mz-zo-2017-14058`](https://3-n.github.io/wzsearch/#/wpis/pb-st-mz-zo-2017-14058?dz=zoliborz) … and 28 more.

## Street names

* Streets: 102. One spelling per street in `address.street` (the site's street filter lists every spelling separately; `normalize.STREET_CANONICAL` maps 16 streets written in several ways to one, `address.display` keeps the source text).
* Still written in several ways (add them to `STREET_CANONICAL`): `gdanska`: „Gdańska” 17, „u. Gdańska” 1.

## Source files and pages

* Layouts: (none) 2, baipp-cp 12, baipp-cp-2020 2, baipp-ws 7, baipp-ws-2020 1, baipp-wz 7, baipp-wz-2020 1, old-unknown 1, old-ws 7, old-wz 9, rwdz-wnioski 1, rwdz-zgloszenia 2.
* Template rows skipped (only a pre-printed Lp number): 19.
* Files linked from more than one page: none.
* Download errors: `8df7eecf21` HTTPError: 403 Client Error: Forbidden for url: https://cdn.um.warszawa.pl/documents/12025039/173779387/informacja_o_wydanych_decyzjach_o_ustaleniu_LICP_o_znaczeniu_krajowym_i_woj%C3%B3dzkim_X_2026%2B.xlsx/2bdca5a3-f93b-a6ec-d25f-d6aa76579389?t=1794226314259; `a18f215831` HTTPError: 403 Client Error: Forbidden for url: https://cdn.um.warszawa.pl/documents/12025039/173779387/informacja_o_wydanych_decyzjach_ustalenie_LICP_o_znaczeniu_powiatowym+_i_gminnym_X_2026%2B.xlsx/e0d771ec-dd75-b9be-a638-bd80fc8a8d6a?t=1794226314560; `7349917c1f` HTTPError: 403 Client Error: Forbidden for url: https://cdn.um.warszawa.pl/documents/12025039/152228831/informacja+o+wszcz%C4%99tych+post%C4%99powaniach+o+wz%2Clicp_XII_25.xlsx/ec2f3679-1303-b07d-d372-2b59bbad3874?t=1768389583052; `62bd84cf3b` HTTPError: cdn.um.warszawa.pl odmówił pobierania (403) – ponowimy przy następnym pobieraniu; `3b7f9d6f99` HTTPError: cdn.um.warszawa.pl odmówił pobierania (403) – ponowimy przy następnym pobieraniu; `e8a03cd9a9` HTTPError: cdn.um.warszawa.pl odmówił pobierania (403) – ponowimy przy następnym pobieraniu; `c3eb081a44` HTTPError: cdn.um.warszawa.pl odmówił pobierania (403) – ponowimy przy następnym pobieraniu; `754e271735` HTTPError: cdn.um.warszawa.pl odmówił pobierania (403) – ponowimy przy następnym pobieraniu; `8f83cf64eb` HTTPError: cdn.um.warszawa.pl odmówił pobierania (403) – ponowimy przy następnym pobieraniu; `6774d0478d` HTTPError: cdn.um.warszawa.pl odmówił pobierania (403) – ponowimy przy następnym pobieraniu; `3e84585827` HTTPError: cdn.um.warszawa.pl odmówił pobierania (403) – ponowimy przy następnym pobieraniu; `a9a20fa57d` HTTPError: cdn.um.warszawa.pl odmówił pobierania (403) – ponowimy przy następnym pobieraniu; `da7da0bfca` HTTPError: cdn.um.warszawa.pl odmówił pobierania (403) – ponowimy przy następnym pobieraniu; `832bd8237b` HTTPError: cdn.um.warszawa.pl odmówił pobierania (403) – ponowimy przy następnym pobieraniu; `b65486632c` HTTPError: cdn.um.warszawa.pl odmówił pobierania (403) – ponowimy przy następnym pobieraniu; `10f399e85c` HTTPError: cdn.um.warszawa.pl odmówił pobierania (403) – ponowimy przy następnym pobieraniu; `46c3206dfa` HTTPError: cdn.um.warszawa.pl odmówił pobierania (403) – ponowimy przy następnym pobieraniu; `bd4dd6ed78` HTTPError: cdn.um.warszawa.pl odmówił pobierania (403) – ponowimy przy następnym pobieraniu; `508b5298d6` HTTPError: cdn.um.warszawa.pl odmówił pobierania (403) – ponowimy przy następnym pobieraniu; `4c11c59898` HTTPError: cdn.um.warszawa.pl odmówił pobierania (403) – ponowimy przy następnym pobieraniu; `c6d56452ea` HTTPError: cdn.um.warszawa.pl odmówił pobierania (403) – ponowimy przy następnym pobieraniu; `020cc57e6f` HTTPError: cdn.um.warszawa.pl odmówił pobierania (403) – ponowimy przy następnym pobieraniu; `c72152adf9` HTTPError: cdn.um.warszawa.pl odmówił pobierania (403) – ponowimy przy następnym pobieraniu; `8051b61e17` HTTPError: cdn.um.warszawa.pl odmówił pobierania (403) – ponowimy przy następnym pobieraniu; `8f6cecf83d` HTTPError: cdn.um.warszawa.pl odmówił pobierania (403) – ponowimy przy następnym pobieraniu; `b5fdcca9bd` HTTPError: cdn.um.warszawa.pl odmówił pobierania (403) – ponowimy przy następnym pobieraniu.
* Files no longer linked by the source (kept as snapshots): [informacja_o_wszczętych_postępowaniach_o_WZ_LICP_IX_2026 +.xlsx](https://architektura.um.warszawa.pl/documents/12025039/171613001/informacja_o_wszcz%C4%99tych_post%C4%99powaniach_o_WZ_LICP_IX_2026+%2B.xlsx/289a1962-288a-3179-aabf-643286f2a106?t=1791798491258) since 2026-11-12, [informacja_o_wydanych_decyzjach_WZ_IX_2026 +.xlsx](https://architektura.um.warszawa.pl/documents/12025039/171613001/informacja_o_wydanych_decyzjach_WZ_IX_2026+%2B.xlsx/1d75d6d6-239a-2dc1-843b-70184b23709c?t=1791798490945) since 2026-11-12, [informacja_o_wydanych_decyzjach_o_ustaleniu_LICP_o_znaczeniu_krajowym_i_wojódzkim_IX_2026 +.xlsx](https://architektura.um.warszawa.pl/documents/12025039/171613001/informacja_o_wydanych_decyzjach_o_ustaleniu_LICP_o_znaczeniu_krajowym_i_woj%C3%B3dzkim_IX_2026+%2B.xlsx/fae00082-7a3e-6cb0-d96c-6a3104611a81?t=1791798491576) since 2026-11-12, [informacja_o_wydanych_decyzjach_ustalenie_LICP_o_znaczeniu_powiatowym _i_gminnym_IX_2026 +.xlsx](https://architektura.um.warszawa.pl/documents/12025039/171613001/informacja_o_wydanych_decyzjach_ustalenie_LICP_o_znaczeniu_powiatowym+_i_gminnym_IX_2026+%2B.xlsx/7dbca2ea-686b-0157-caa3-134d35570f6b?t=1791798490447) since 2026-11-12.

File warnings:

* [WZ i cp wydane decyzje lipiec-grudzien 2023.xlsx](https://zoliborz.um.warszawa.pl/documents/46235/48738426/WZ+i+cp+wydane+decyzje+lipiec-grudzien+2023.xlsx/81529708-26f6-9ab5-079a-1b0f18a3f643?t=1721052574890): Plik jest podlinkowany na stronie jako lista CP, ale jego nagłówek wskazuje listę WZ – przyjęto treść pliku.
* [WZ i CP wszczecie postepow. styczeń - czerwiec  2023.xlsx](https://zoliborz.um.warszawa.pl/documents/46235/82377301/WZ+i+CP+wszczecie+postepow.+stycze%C5%84+-+czerwiec++2023.xlsx/5e39205f-1b10-df08-f170-1c7096f8714d?t=1688622115816): Plik jest podlinkowany na stronie jako lista WZ, ale jego nagłówek wskazuje listę Wszczęcie – przyjęto treść pliku.
* [WZ i CP wszczecie postepow. listopad-grudzien 2022.xlsx](https://zoliborz.um.warszawa.pl/documents/46235/75162133/WZ+i+CP+wszczecie+postepow.+listopad-grudzien+2022.xlsx/d925fb25-ef79-0073-e36b-e335cedbb935?t=1680154398943): Plik jest podlinkowany na stronie jako lista WZ, ale jego nagłówek wskazuje listę Wszczęcie – przyjęto treść pliku.
* [WZ i CP wszczecie postepow. sierpien pazdziernik 2022.xlsx](https://zoliborz.um.warszawa.pl/documents/46235/64436866/WZ+i+CP+wszczecie+postepow.+sierpien+pazdziernik+2022.xlsx/9d464988-8207-101e-1247-d9a075f61ded?t=1667476380370): Plik jest podlinkowany na stronie jako lista WZ, ale jego nagłówek wskazuje listę Wszczęcie – przyjęto treść pliku.
* [WZ i CP wszczecie postepow. czerwiec lipiec 2022.xlsx](https://zoliborz.um.warszawa.pl/documents/46235/58013967/WZ+i+CP+wszczecie+postepow.+czerwiec+lipiec+2022.xlsx/c274f18b-ffb2-166d-6df8-25ef515e3199?t=1660035352565): Plik jest podlinkowany na stronie jako lista WZ, ale jego nagłówek wskazuje listę Wszczęcie – przyjęto treść pliku.
* [WZ i CP wszczecie postepow. kwiecień - maj 2022.xlsx](https://zoliborz.um.warszawa.pl/documents/46235/52795484/WZ+i+CP+wszczecie+postepow.+kwiecie%C5%84+-+maj+2022.xlsx/845bec5f-dbf1-93d2-4c4c-5018345fe055?t=1654254699215): Plik jest podlinkowany na stronie jako lista WZ, ale jego nagłówek wskazuje listę Wszczęcie – przyjęto treść pliku.
* [WZ i CP wszczecie postepow. luty-marzec 2022.xlsx](https://zoliborz.um.warszawa.pl/documents/46235/48738448/WZ+i+CP+wszczecie+postepow.+luty-marzec+2022.xlsx/e43576d7-0ef8-e1d3-c456-940cdeab3a41?t=1650352562971): Plik jest podlinkowany na stronie jako lista WZ, ale jego nagłówek wskazuje listę Wszczęcie – przyjęto treść pliku.
* [WZ wszczecie postepow. styczeń 2022.xlsx](https://zoliborz.um.warszawa.pl/documents/46235/42890754/WZ+wszczecie+postepow.+stycze%C5%84+2022.xlsx/3dd80ec2-15ef-cdd8-6d9e-2d4ccf4fdf40?t=1643718977435): Plik jest podlinkowany na stronie jako lista WZ, ale jego nagłówek wskazuje listę Wszczęcie – przyjęto treść pliku.
* [rejestr dec. WZ i ZT za 2021_na strone.xlsx](https://zoliborz.um.warszawa.pl/documents/46235/48738426/rejestr+dec.+WZ+i+ZT+za+2021_na+strone.xlsx/b2ce456d-5fec-55b7-53db-ce0869878084?t=1721052630347): arkusz „Arkusz1”: nie rozpoznano rodzaju listy (WZ/CP/wszczęte); arkusz „Arkusz1”: kolumny E i H wyglądają na to samo pole (investment); użyto pierwszej; W pliku nie rozpoznano rodzaju listy – przyjęto rodzaj z opisu na stronie (WZ).
* [informacja_o_wydanych_decyzjach_o_ustaleniu_LICP_o_znaczeniu_krajowym_i_wojódzkim_X_2026+.xlsx](https://cdn.um.warszawa.pl/documents/12025039/173779387/informacja_o_wydanych_decyzjach_o_ustaleniu_LICP_o_znaczeniu_krajowym_i_woj%C3%B3dzkim_X_2026%2B.xlsx/2bdca5a3-f93b-a6ec-d25f-d6aa76579389?t=1794226314259): Brak lokalnej kopii pliku (nie udało się go pobrać) – pozycje nieodczytane.
* [informacja_o_wydanych_decyzjach_ustalenie_LICP_o_znaczeniu_powiatowym _i_gminnym_X_2026+.xlsx](https://cdn.um.warszawa.pl/documents/12025039/173779387/informacja_o_wydanych_decyzjach_ustalenie_LICP_o_znaczeniu_powiatowym+_i_gminnym_X_2026%2B.xlsx/e0d771ec-dd75-b9be-a638-bd80fc8a8d6a?t=1794226314560): Brak lokalnej kopii pliku (nie udało się go pobrać) – pozycje nieodczytane.
