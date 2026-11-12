"""City-wide draft (docs/plans/all-districts.md): the district registry, precincts, and the pipeline run for a
district other than Praga-Południe (ids, parcels, addresses, BAiPP rows, crawler helpers, ZIP archives).

Praga-Południe's behaviour is covered by the rest of the suite, which runs with the default (legacy) district.
"""

from __future__ import annotations

import io
import json
import shutil
import zipfile
from pathlib import Path

import pytest

from pipeline import baipp, crawl, districts, normalize, rwdz
from pipeline.build import DistrictPaths, Paths
from pipeline.parse import parse_source, parse_workbook
from pipeline.textutil import fold

FIX = Path(__file__).parent / "fixtures" / "districts"


# =========================================================================== registry


def test_registry_has_18_districts_with_unique_identity():
    ds = list(districts.DISTRICTS.values())
    assert len(ds) == 18
    assert len({d.unit for d in ds}) == 18
    assert len({d.slug for d in ds}) == 18
    assert [d.code for d in ds if d.legacy] == [""] and len({d.code for d in ds}) == 18
    assert {d.unit for d in ds} == set(rwdz.WARSAW_UNITS)
    for d in ds:
        assert d.zones and all(d.unit in baipp.OBREB_ZONES[z] for z in d.zones), d.slug
        assert d.status in ("enabled", "pending")
        assert d.strategy != "attachments" or d.pages, d.slug


def test_legacy_district_is_the_default():
    assert districts.current().slug == "praga-poludnie"
    with districts.use("wola") as d:
        assert districts.current() is d
        with districts.use("bemowo"):
            assert districts.current().name == "Bemowo"
        assert districts.current().name == "Wola"
    assert districts.current().legacy


@pytest.mark.parametrize("slug,text,matches", [
    ("wola", "Wola", True), ("wola", "na Woli", True), ("wola", "ul. Wolska 1", False),
    ("wawer", "Wawer", True), ("wawer", "w Wawrze", True), ("wawer", "Wawerska 3", False),
    ("wilanow", "Wilanów", True), ("wilanow", "al. Wilanowska", False),
    ("targowek", "Targówek", True), ("targowek", "ul. Targowa 5", False),
    ("praga-polnoc", "Praga-Północ", True), ("praga-polnoc", "Praga Płn.", True), ("praga-polnoc", "Praga Pn", True),
    ("praga-polnoc", "Praga-Południe", False), ("praga-poludnie", "Praga Południe", True),
    ("srodmiescie", "Śródmieście", True), ("bialoleka", "Białołęka", True), ("bialoleka", "na Białołęce", True),
])
def test_district_names_but_not_street_names(slug, text, matches):
    assert bool(districts.get(slug).pattern.search(fold(text))) is matches


def test_gunb_office_names_per_district():
    assert districts.get("bemowo").organ_pattern.search(fold("Prezydent Miasta Warszawa - Bemowo"))
    assert districts.get("praga-polnoc").organ_pattern.search(fold("Prezydent Miasta Warszawa - Praga Pn."))
    assert not districts.get("praga-polnoc").organ_pattern.search(fold("Prezydent Miasta Warszawa - Praga Płd."))
    with districts.use("bemowo"):
        assert rwdz.is_district_office("Prezydent Miasta Warszawa - Bemowo")
        assert not rwdz.is_district_office("Prezydent Miasta Warszawa - Praga Płd.")
        assert rwdz.match_location("146502_8", "Wojewoda Mazowiecki") == "unit"
        assert rwdz.match_location("146507_8", "Prezydent Miasta Warszawa - Praga Płd.") is None
        assert rwdz.match_location("146052_8", "Prezydent Miasta Warszawa - Bemowo") == "typo"
    assert rwdz.is_district_office("Prezydent Miasta Warszawa - Praga Płd.")   # the cache knows the district


# =========================================================================== precincts


@pytest.mark.parametrize("precinct,prefer,unit", [
    ("6-11-10", None, "146502_8"),         # Bemowo
    ("3-07-07", None, "146509_8"),         # Rembertów – zone 3 is shared with Praga-Południe and Wawer
    ("3-07-18", None, "146507_8"),         # Praga-Południe
    ("8-07-07", None, "146515_8"),         # Wesoła
    ("6-11-11", None, None),               # Wola and Bemowo both have rows in the register: no 3:1 majority
    ("6-11-11", "146518_8", "146518_8"),   # … the record's own district decides
    ("1-99-99", "146513_8", "146513_8"),   # unknown precinct of the district's zone: the district's unit
    ("1-99-99", "146518_8", None),         # … but not across zones
    ("x-01-01", None, None),
])
def test_unit_for_precinct(precinct, prefer, unit):
    assert districts.unit_for_precinct(precinct, prefer) == unit


# =========================================================================== normalisation in another district


def test_parcels_take_the_unit_of_their_precinct():
    with districts.use("bemowo"):
        parcels, warnings = normalize.parse_parcels("dz. 25/2 z ob. 6-10-07; dz. 3 i 6 z ob. 6-08-11")
    assert [p["id"] for p in parcels] == ["146502_8.1007.25/2", "146502_8.0811.3", "146502_8.0811.6"]
    assert warnings == []
    with districts.use("wola"):
        parcels, warnings = normalize.parse_parcels("42, obr. 6-02-05")
    assert [p["id"] for p in parcels] == ["146518_8.0205.42"]


def test_wesola_writes_the_precinct_first_and_without_its_zone():
    with districts.use("wesola"):
        parcels, warnings = normalize.parse_parcels(" 07-15 dz. 94/3 07-15 dz. 75/8 07-16 dz. 1/2 ")
    assert [(p["obreb"], p["number"]) for p in parcels] == [("8-07-15", "94/3"), ("8-07-15", "75/8"),
                                                            ("8-07-16", "1/2")]
    assert all(p["id"].startswith("146515_8.07") for p in parcels)
    assert not any("bez numerów" in w for w in warnings)


def test_address_drops_the_district_only_as_a_separate_segment():
    with districts.use("praga-polnoc"):
        assert normalize.parse_address("Kowieńska 4, Praga-Północ")["display"] == "Kowieńska 4"
    with districts.use("srodmiescie"):
        assert normalize.parse_address("Elektoralna 13, 13A; Śródmieście")["street"] == "Elektoralna"
    with districts.use("wesola"):
        assert normalize.parse_address("ul. Wesoła 5")["street"] == "Wesoła"
        assert normalize.parse_address(" Armii Krajowej;Wesoła ")["display"] == "Armii Krajowej"


def test_address_with_an_elided_house_number_keeps_the_street():
    # Targówek writes "ul. Oliwska …" / "ul. Poleska ..." – the street is still known (located street-level)
    with districts.use("targowek"):
        for raw in ("ul. Oliwska…; dzielnica Targówek", "ul. Poleska ...; dzielnica Targowek"):
            a = normalize.parse_address(raw)
            assert a["street"] in ("Oliwska", "Poleska") and a["number"] is None
            assert a["display"].endswith(("…", "..."))


def test_records_of_another_district_get_namespaced_ids_outcomes_and_periods():
    pf = parse_workbook(FIX / "bemowo-cp-2026.xlsx")
    assert pf["kind"] == "cp"
    with districts.use("bemowo"):
        recs = [normalize.normalize_row(r, pf["kind"], {"file_id": "c74a518590", "page_id": "bem-x", "period": "2026"})
                for r in pf["rows"]]
    first = recs[0]
    assert first["id"] == "cp-bem-2026-1"
    assert first["number"] == "1/BEM/CP/2026/U"
    assert first["outcome"] == "discontinued"          # the /U letter, like BAiPP's numbers
    assert first["period"] == "2026-01"                # the file is yearly: the period is the decision's month
    assert first["parcels"][0]["id"] == "146502_8.0805.3/24"
    assert recs[1]["outcome"] is None                  # no letter: not stated
    assert len({r["id"] for r in recs}) == len(recs)


def test_case_signs_keep_their_clerk_suffix():
    row = {"cells": {"number": "UD-I-WAB-B.6730.82.2025.KBO", "date": "2026-02-03", "applicant": "osoba fizyczna",
                     "investment": "budowa wiaty", "address": "ul. Czumy 3", "parcels": "dz. 5/40 z ob. 6-11-10"},
           "raw": [], "row": 6, "sheet": "Tabela licp 1"}
    with districts.use("bemowo"):
        rec = normalize.normalize_row(row, "ws", {"file_id": "f", "page_id": "p", "period": "2026"})
    assert rec["number"] == "UD-I-WAB-B.6730.82.2025.KBO"
    assert rec["id"] == "ws-bem-6730-2025-82"


def test_cumulative_lists_of_another_district_merge_by_newest_snapshot():
    base = {"id": "wz-bem-2026-1", "dataset": "district", "date": "2026-01-15", "investment": "budowa",
            "number": "1/BEM/WZ/2026", "warnings": []}
    old = {**base, "sources": [{"file_id": "a", "sheet": "Rok", "row": 6}]}
    new = {**base, "investment": "budowa – poprawione", "sources": [{"file_id": "b", "sheet": "Rok", "row": 6}]}
    with districts.use("bemowo"):
        merged = normalize.merge_duplicates([old, new])
    assert len(merged) == 1 and merged[0]["investment"] == "budowa – poprawione"
    assert {s["file_id"] for s in merged[0]["sources"]} == {"a", "b"}
    assert len(normalize.merge_duplicates([old, new])) == 2   # Praga-Południe: first listing wins, variants split


# =========================================================================== BAiPP


def test_baipp_rows_are_assigned_by_the_address_line_and_namespaced():
    with districts.use("bielany"):
        assert baipp.in_district("Wólczyńska 133\nBielany")
        assert not baipp.in_district("Ostrobramska 73\nPraga Południe")
        assert baipp.strip_district("Wólczyńska 133\nBielany") == "Wólczyńska 133"
        assert baipp.namespace_id("wz-2025-33", "wz", "33/AM/BIE/WZ/2025/P", None)[0] == "wz-am-bie-2025-33"
        assert baipp.namespace_id("cp-2022-1", "cp", "1/BIE/C2/22", None)[0] == "cp-am-bie-2022-c2-1"
        assert baipp.namespace_id("ws-6730-2025-5", "ws", "AM-ZP-N.6730.5.2025", None)[0] == "ws-am-bie-zp-n-6730-2025-5"
    assert baipp.namespace_id("wz-2025-33", "wz", "33/AM/PPD/WZ/2025/P", None)[0] == "wz-am-2025-33"   # legacy


# =========================================================================== crawler helpers


@pytest.mark.parametrize("text,period", [
    ("wrzesień (plik xlsx 22 KB) 09_WSZCZETE_2026.xlsx", "2026-09"),
    ("styczeń Kopia informacja_wszczęcia_wz_cp_01_2026_rembertow.xlsx", "2026-01"),
    ("1129_1009zal1_2023_12", "2023-12"),
    ("1129_1009zal1_2023_11a", "2023-11"),
    ("1129_1009zal1_2021", "2021"),
    ("Wydane decyzje ULICP 08.2026.xlsx", "2026-08"),
    ("Zał. 1a - Rejestr wniosków o WZ.xlsx", None),
])
def test_guess_period(text, period):
    assert crawl.guess_period(text) == period


@pytest.mark.parametrize("text,kind", [
    ("Informacja wnioski sierpień 2026.xlsx", "ws"), ("Rejestr wniosków – 2026 rok", "ws"),
    ("maj icp 2026.xlsx", "cp"), ("04_DECYZJE_CP_G_P_2026.xlsx", "cp"),
    ("Rejestr decyzji o warunkach zabudowy (styczeń)", "wz"), ("2 wz dec. wrzesień 2026.xlsx", "wz"),
])
def test_attachment_kind_hints(text, kind):
    assert crawl.detect_attachment_category(text) == kind


def test_attachments_page_keeps_the_districts_lists_only():
    # Liferay markup as on the district sites (link texts and paths from the Wawer page, 2026-10-27)
    html = """<html><head><title>Dokumenty budowlane - Wawer</title></head><body>
      <div class="journal-content-article" data-analytics-asset-title="Dokumenty budowlane">
        <a href="/documents/47611/1/decyzje_PB_01_2026.xlsx/00000000-0000-0000-0000-000000000001?t=1">Pozwolenia na budowę (styczeń), 20KB, .xlsx</a>
        <a href="/documents/47611/1/decyzje_WZ_01_2026_1129_1009zal2.xlsx/00000000-0000-0000-0000-000000000002?t=2">Rejestr decyzji o warunkach zabudowy (styczeń), 17 KB, .xlsx</a>
        <a href="/documents/47611/126478500/Rejestr+decyzji+o+warunkach+zabudowy_2025.zip/b9431d10-4c0b-7666-0b5c-6347f1050b27?t=1770730439035">Rejestr decyzji o warunkach zabudowy (178 kB, .zip)</a>
        <a href="/documents/47611/3/rejestr_decyzji_2019.pdf/00000000-0000-0000-0000-000000000004?t=4">Rejestr decyzji (133 kb, .pdf)</a>
        <a href="https://example.org/documents/x.xlsx">obcy plik</a>
      </div></body></html>"""
    page = crawl.parse_attachments_page(html, "https://wawer.um.warszawa.pl/dokumenty-budowlane", districts.get("wawer"))
    assert page["page_id"] == "waw-dokumenty-budowlane"
    assert page["title"] == "Dokumenty budowlane"
    assert [(b["category"], b["period"]) for b in page["blocks"]] == [("wz", "2026-01"), ("wz", "2025")]
    assert [link["ext"] for link in page["links"]] == ["xlsx", "zip"]
    assert page["skipped_attachments"] == {"excluded": 1, "pdf": 1}


def test_attachments_before_2020_are_left_out():
    # Białołęka links its PDF registers back to 2009; the 1129/2020 lists start in IX 2020
    html = """<html><body><div class="journal-content-article" data-analytics-asset-title="Warunki zabudowy - decyzje">
        <a href="/documents/40771/1/Decyzje+WZ+%283%29.pdf/00000000-0000-0000-0000-000000000001?t=1">Warunki zabudowy decyzje 2026 (143 KB, PDF)</a>
        <a href="/documents/40771/2/Decyzje+WZ+2020.pdf/00000000-0000-0000-0000-000000000002?t=2">Warunki zabudowy decyzje 2020 (90 KB, PDF)</a>
        <a href="/documents/40771/3/Decyzje+WZ+2019.pdf/00000000-0000-0000-0000-000000000003?t=3">Warunki zabudowy decyzje 2019 (90 KB, PDF)</a>
      </div></body></html>"""
    page = crawl.parse_attachments_page(html, "https://bialoleka.um.warszawa.pl/warunki-zabudowy-decyzje",
                                        districts.get("bialoleka"))
    assert [b["period"] for b in page["blocks"]] == ["2026", "2020"]
    assert page["skipped_attachments"] == {"before 2020": 1}


# =========================================================================== ZIP archives


def test_zip_archives_are_parsed_member_by_member(tmp_path):
    archive = tmp_path / "lista.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.write(FIX / "bemowo-cp-2026.xlsx", "1. decyzje_CP_01_2026.xlsx")
        zf.writestr("readme.txt", "nie arkusz")
    parsed = parse_source(archive)
    single = parse_workbook(FIX / "bemowo-cp-2026.xlsx")
    assert parsed["kind"] == "cp"
    assert len(parsed["rows"]) == len(single["rows"])
    assert parsed["rows"][0]["sheet"] == f"1. decyzje_CP_01_2026.xlsx › {single['rows'][0]['sheet']}"
    assert any("readme.txt" in w for w in parsed["warnings"])


# =========================================================================== paths


def test_district_paths(tmp_path):
    legacy = DistrictPaths(tmp_path, slug="praga-poludnie")
    for name in ("manifest", "raw", "report", "site_data", "feed", "mirror", "rwdz_raw", "cache", "records_json"):
        assert getattr(legacy, name) == getattr(Paths(tmp_path), name), name
    assert legacy.mirror_url == "sources" and legacy.rwdz_state is None
    wola = DistrictPaths(tmp_path, slug="wola")
    assert wola.manifest == tmp_path / "data/districts/wola/manifest.json"
    assert wola.records_json == tmp_path / "site/data/d/wola/records.json"
    assert wola.mirror_url == "sources/d/wola"
    assert wola.cache == tmp_path / "data/cache/districts/wola"
    assert wola.rwdz_cache == tmp_path / "data/cache"


# =========================================================================== Wawer's oddities


def test_three_digit_precincts_use_the_register_codes():
    # Wawer's 3-12-100 and 3-12-101 are "2100"/"2101" in the land register (GUGiK's county package)
    with districts.use(districts.get("wawer")):
        assert [p["id"] for p in normalize.parse_parcels("dz. ew. nr 83, obręb 3-12-101")[0]] == ["146514_8.2101.83"]
        assert normalize.parse_parcels("obręb 3-12-100, dz.ew.nr 119/2")[0][0]["id"] == "146514_8.2100.119/2"
    assert districts.unit_for_precinct("3-12-101", "146514_8") == "146514_8"


def test_street_from_the_parcels_cell_and_filing_date():
    row = {"cells": {"number": "2/2020\nOdmowa", "date": "03.01.2020", "applicant": "osoba fizyczna",
                     "investment": "Zmiana sposobu użytkowania", "address": None,
                     "parcels": "Marsa 56, dz. Ew .nr. 14/4 obręb 3-07-15", "filed": "2019-11-04"},
           "row": 3, "sheet": "styczeń-grudzień 2020", "raw": []}
    with districts.use(districts.get("wawer")):
        rec = normalize.normalize_row(row, "wz", {"file_id": "f1", "period": "2020"})
    assert (rec["id"], rec["outcome"], rec["date"], rec["filed_date"]) == ("wz-waw-2020-2", "refusal", "2020-01-03",
                                                                          "2019-11-04")
    assert (rec["address"]["street"], rec["address"]["number"]) == ("Marsa", "56")
    assert [p["id"] for p in rec["parcels"]] == ["146514_8.0715.14/4"]


def test_ursus_register_with_misleading_headers():
    # Ursus's own register (27 X 2026): "Data wpływu wniosku" holds "1/URS/WZ/2026 z dnia 08.01.2026" and the outcome
    # is a verb in an unnamed column ("Kolumna6": ustalam / odmawiam / umarzam)
    pf = parse_source(FIX / "ursus-wz-2026.xlsx")
    assert pf["kind"] == "wz"
    first = pf["rows"][0]["cells"]
    assert (first["number"], first["date"], first["address"]) == ("1/URS/WZ/2026\nustalam", "08.01.2026", "Górna Droga")
    with districts.use(districts.get("ursus")):
        recs = [normalize.normalize_row(row, "wz", {"file_id": "u1", "period": None}) for row in pf["rows"]]
    assert recs[0]["id"] == "wz-urs-2026-1" and recs[0]["outcome"] == "granted"
    assert recs[1]["outcome"] == "refusal"                      # "2/URS/WZ/2026/O" + "odmawiam"
    assert sum(bool(r["parcels"]) for r in recs) == len(recs)


def test_dataset_descriptions_name_the_district():
    from pipeline.build import DATASETS, district_datasets   # noqa: PLC0415
    with districts.use("wola"):
        ds = district_datasets()
    assert "na Woli (jednostka ewidencyjna 146518_8)" in ds["rwdz"]["description"]
    assert "Pradze" not in ds["rwdz"]["description"] and "Pragę" not in ds["baipp"]["description"]
    with districts.use("praga-poludnie"):
        assert district_datasets() is DATASETS


def test_a_date_after_the_files_publication_is_a_typo_and_dropped():
    row = {"sheet": "S", "row": 4, "cells": {"number": "108/WZ/MOK/2021", "date": "24.11.2201", "address": "Lipowa 5"},
           "raw": []}
    meta = {"file_id": "f", "page_id": "p", "period": "2026-09", "published_at": "2026-10-05T06:55:01Z"}
    with districts.use("mokotow"):
        rec = normalize.normalize_row(row, "ws", meta)
        assert rec["date"] is None and rec["date_raw"] == "24.11.2201" and rec["period"] == "2026-09"
        assert any("późniejsza niż publikacja pliku (2026-10-05)" in w for w in rec["warnings"])
        ok = normalize.normalize_row({**row, "cells": {**row["cells"], "date": "06.10.2026"}}, "ws", meta)
        assert ok["date"] == "2026-10-06"   # the next day still counts (a UTC stamp, a Warsaw date)
    with districts.use("praga-poludnie"):   # the legacy district keeps its own rule (a warning, the date kept)
        assert normalize.normalize_row(row, "ws", meta)["date"] == "2201-11-24"


def test_city_failure_policy():
    # plan §7 #5: up to three districts may keep their previous data; a fourth, or a GUNB format change, fails the run
    from pipeline import city
    from pipeline.build import EXIT_FATAL, EXIT_OK, EXIT_STALE
    ok = {s: EXIT_OK for s in ("praga-poludnie", "wola", "bemowo", "ursus", "wesola")}
    three = {"wola": "down", "bemowo": "down", "ursus": "down"}
    assert city.city_exit_code(ok, {}, None) == EXIT_OK
    assert city.city_exit_code({**ok, **{s: EXIT_STALE for s in three}}, three, None) == EXIT_OK
    four = {**three, "wesola": "down"}
    assert city.city_exit_code({**ok, **{s: EXIT_STALE for s in four}}, four, None) == EXIT_STALE
    assert city.city_exit_code(ok, {}, "RWDZ columns changed") == EXIT_STALE
    assert city.city_exit_code({"wola": EXIT_FATAL}, {"wola": "no manifest"}, None) == EXIT_FATAL
