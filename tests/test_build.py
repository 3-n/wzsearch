"""Tests for the build stage (pipeline/build.py), the exports (pipeline/export.py) and the
integration fixes it needed in pipeline/geocode.py.

* unit tests for every pure helper (kind decision, block counts, merging, relations, JSON writer);
* an end-to-end ``run_build`` on a throw-away project made of real fixture workbooks and real GUNB
  RWDZ register lines (offline, synthetic caches): outputs of all three datasets, determinism, the
  "no diff on a no-op rebuild" guarantee, mirroring, RWDZ failure modes;
* consistency checks of the REAL generated site data (skipped when it is absent or a fixture).
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import shutil
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

import pytest
import requests
from requests.structures import CaseInsensitiveDict

from pipeline import build, export, geo
from pipeline import crawl as crawl_mod
from pipeline import geocode as gc
from pipeline import rwdz as rwdz_mod
from pipeline.areas import AreaIndex

ROOT = Path(__file__).resolve().parents[1]
FIX = ROOT / "tests" / "fixtures" / "xlsx"
RWDZ_FIX = ROOT / "tests" / "fixtures" / "rwdz"
RWDZ_FIXTURES = {"rwdz-wnioski": "wnioski.csv", "rwdz-zgloszenia-2016-2021": "zgloszenia_2016_2021.csv",
                 "rwdz-zgloszenia-2022": "zgloszenia_2022.csv"}
ATOM = "{http://www.w3.org/2005/Atom}"
NOW = "2026-10-23T00:00:00Z"


# =============================================================================
# Helpers
# =============================================================================


def square(lon: float, lat: float, size: float = 0.0005) -> dict:
    return {"type": "Polygon", "coordinates": [[[lon, lat], [lon + size, lat], [lon + size, lat + size],
                                                [lon, lat + size], [lon, lat]]]}


def uldk_ok(lon: float, lat: float, size: float = 0.0005) -> dict:
    return {"status": "ok", "geometry": square(lon, lat, size), "centroid": [lon + size / 2, lat + size / 2],
            "bbox": [lon, lat, lon + size, lat + size], "area_m2": 1900.0, "fetched_at": NOW}


def uldk_missing() -> dict:
    return {"status": "missing", "fetched_at": NOW}


DISTRICT = {"type": "Polygon", "coordinates": [[[21.03, 52.20], [21.13, 52.20], [21.13, 52.265], [21.03, 52.265],
                                                [21.03, 52.20]]]}


def rec(rid, *, date="2026-01-01", parcels=(), street=None, number=None, parts=None):
    return {
        "id": rid, "date": date,
        "parcels": [{"id": p, "number": p.split(".", 2)[-1], "obreb": None, "partial": False} for p in parcels],
        "address": {"street": street, "number": number, "display": street, "raw": street or "",
                    **({"parts": parts} if parts is not None else {})},
    }


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# =============================================================================
# Small helpers of build.py
# =============================================================================


class TestHelpers:
    def test_natural_sort_and_record_order(self):
        assert sorted(["wz-2026-15", "wz-2026-9", "wz-2025-30"], key=build.natural_key) == [
            "wz-2025-30", "wz-2026-9", "wz-2026-15"]
        recs = [{"id": "wz-2026-9", "date": "2026-07-01", "period": "2026-07"},
                {"id": "wz-2026-15", "date": "2026-07-09", "period": "2026-07"},
                {"id": "wz-2026-10", "date": "2026-07-01", "period": "2026-07"},
                {"id": "wz-2020-1", "date": None, "period": "2020-08"}]
        assert [r["id"] for r in build.sort_records(recs)] == ["wz-2026-15", "wz-2026-10", "wz-2026-9", "wz-2020-1"]

    def test_dumps_json_is_valid_one_element_per_line(self):
        doc = {"generated_at": NOW, "count": 2, "empty": [], "records": [{"id": "a", "t": "Żółć"}, {"id": "b"}]}
        text = build.dumps_json(doc, ("records", "empty")).decode("utf-8")
        assert json.loads(text) == doc
        assert "Żółć" in text  # no ASCII escaping
        lines = text.splitlines()
        assert '{"id":"a","t":"Żółć"},' in lines and '{"id":"b"}' in lines
        assert '"empty":[],' in lines

    def test_dumps_json_rejects_nan(self):
        with pytest.raises(ValueError):
            build.dumps_json({"x": float("nan")})

    def test_write_atomic_skips_identical(self, tmp_path):
        p = tmp_path / "sub" / "f.json"
        assert build.write_atomic(p, b"one") is True
        assert build.write_atomic(p, b"one") is False
        assert build.write_atomic(p, b"two") is True and p.read_bytes() == b"two"
        assert sorted(x.name for x in p.parent.iterdir()) == ["f.json"]  # no temp files left

    @pytest.mark.parametrize("detected, category, kind, warns", [
        ("wz", "wz", "wz", 0), ("ws", "wz", "ws", 1), (None, "cp", "cp", 1), ("cp", None, "cp", 0), (None, None, None, 1),
    ])
    def test_decide_kind(self, detected, category, kind, warns):
        got, warnings = build.decide_kind(detected, category)
        assert got == kind and len(warnings) == warns

    def test_numbering_gaps(self):
        ids = ["wz-2020-16", "wz-2020-17", "wz-2020-20", "wz-2020-18-2", "cp-2021-1", "ws-6730-2021-5",
               "wz-f0123456789-r7", "wz-2021-3", "wz-2021-5"]
        assert build.numbering_gaps([{"id": i} for i in ids]) == {
            ("wz", "2020"): ([16, 17, 20], [18, 19]),       # first year: from the lowest number seen
            ("wz", "2021"): ([3, 5], [1, 2, 4]),            # later years: from 1
            ("cp", "2021"): ([1], [])}

    def test_warning_category(self):
        assert build.warning_category("poprawiono pisownię ulicy: „Chdakowska” → „Chodakowska”") == \
            "poprawiono pisownię ulicy: „…” → „…”"
        assert build.warning_category("adres Mińska 46 leży ok. 950 m od wskazanych działek") == \
            "adres … leży ok. N m od wskazanych działek"
        assert build.warning_category("w ewidencji gruntów (ULDK) znaleziono 2 z 3 działek") == (
            "w ewidencji gruntów (ULDK) znaleziono N z N działek")


# =============================================================================
# Merging and relations
# =============================================================================


def _raw(rid, file_id, row, investment="budowa budynku", date="2026-07-09", period="2026-07"):
    return {"id": rid, "kind": "wz", "number": rid, "date": date, "period": period, "investment": investment,
            "sources": [{"file_id": file_id, "page_id": f"p-{file_id}", "sheet": "S", "row": row, "raw": []}],
            "warnings": []}


class TestMerge:
    def test_same_decision_in_two_files_becomes_one_record(self):
        out = build.merge_records([_raw("wz-2026-15", "old", 6), _raw("wz-2026-15", "new", 9, period="2026-08")])
        assert len(out) == 1
        assert [s["file_id"] for s in out[0]["sources"]] == ["old", "new"]
        assert out[0]["period"] == "2026-07"  # the first (oldest) listing wins

    def test_same_number_different_content_is_split(self):
        out = build.merge_records([_raw("wz-2026-15", "a", 6), _raw("wz-2026-15", "b", 6, investment="rozbiórka")])
        ids = sorted(r["id"] for r in out)
        assert ids == ["wz-2026-15", "wz-2026-15-2"]
        assert all(any("inną treścią" in w for w in r["warnings"]) for r in out)


class TestRelated:
    def test_parcels_and_addresses(self):
        records = [
            rec("ws-1", date="2021-01-01", parcels=["146507_8.0101.1"], street="Mińska", number="46"),
            rec("wz-1", date="2021-06-01", parcels=["146507_8.0101.1", "146507_8.0101.2"]),
            rec("wz-2", date="2022-01-01", street="ul. Mińska", number="46"),          # same address
            rec("wz-3", date="2020-01-01", street="Mińska"),                           # no number → not related
            rec("cp-1", date="2023-01-01", parcels=["146507_8.0101.2"]),
            rec("wz-4", date="2024-01-01", street="Gen. Fieldorfa Nila", number="5"),
            rec("wz-5", date="2019-01-01", street="Fieldorfa", number="5 "),          # spelling/whitespace
            rec("wz-6", date="2025-01-01", street="Grochowska", number="1",
                parts=[{"street": "Grochowska", "number": "1", "numbers": ["1"]},
                       {"street": "Mińska", "number": "46", "numbers": ["46"]}]),     # second street matches
        ]
        build.compute_related(records)
        rel = {r["id"]: r["related"] for r in records}
        assert rel["ws-1"] == ["wz-1", "wz-2", "wz-6"]  # chronological
        assert rel["wz-1"] == ["ws-1", "cp-1"]
        assert rel["wz-3"] == []
        assert rel["wz-4"] == ["wz-5"] and rel["wz-5"] == ["wz-4"]
        assert "wz-6" in rel["wz-2"]
        for r in records:  # symmetric, never self
            assert r["id"] not in r["related"]
            for other in r["related"]:
                assert r["id"] in rel[other]

    def test_across_datasets(self):
        """A WZ decision and the building permit on the same parcel / address relate both ways."""
        records = [rec("wz-2021-3", date="2021-03-01", parcels=["146507_8.0406.137"]),
                   rec("pb-st-mz-pa-2022-1", date="2022-05-01", parcels=["146507_8.0406.137", "146510_8.0407.10/1"]),
                   rec("zg-st-mz-pa-2023-2", date="2023-01-01", street="Grochowska", number="230"),
                   rec("ws-am-6730-2020-1", date="2020-01-01", street="ul. Grochowska", number="230")]
        build.compute_related(records)
        rel = {r["id"]: r["related"] for r in records}
        assert rel["wz-2021-3"] == ["pb-st-mz-pa-2022-1"] and rel["pb-st-mz-pa-2022-1"] == ["wz-2021-3"]
        assert rel["zg-st-mz-pa-2023-2"] == ["ws-am-6730-2020-1"]

    def test_split_parcels(self):
        features = [{"id": "a", "properties": {"records": ["pb-1", "wz-2026-15"]}},
                    {"id": "b", "properties": {"records": ["pb-1"]}},
                    {"id": "c", "properties": {"records": ["ws-6730-2025-1"]}}]
        planning, permits_only = build.split_parcels(features, {"wz-2026-15", "ws-6730-2025-1"})
        assert [f["id"] for f in planning] == ["a", "c"] and [f["id"] for f in permits_only] == ["b"]

    def test_address_keys(self):
        r = rec("x", street="Serocka", number="21",
                parts=[{"street": "Serocka", "number": "21", "numbers": ["21", "23"]},
                       {"street": "Lubartowska", "number": None, "numbers": []}])
        assert build.address_keys(r) == {("serocka", "21"), ("serocka", "23")}


# =============================================================================
# Declared vs parsed counts per block
# =============================================================================


class TestBlockCounts:
    def setup_method(self):
        self.files = {"sep": {"page_ids": ["p-sep", "p-oct"]}, "oct": {"page_ids": ["p-oct"]},
                      "gone": {"page_ids": ["p-x"]}}
        self.results = {"sep": build.FileResult(parsed_count=2), "oct": build.FileResult(parsed_count=1),
                        "gone": build.FileResult(parsed_count=None)}

    def count(self, page_id, block, counted=None):
        return build.block_counts({"page_id": page_id}, block, self.files, self.results,
                                  set() if counted is None else counted)

    def test_leftover_link_to_last_month_not_counted(self):
        # Oct 2025: "1 pozycja" next to links to both the Sep and the Oct file.
        assert self.count("p-oct", {"category": "wz", "declared_count": 1, "file_ids": ["sep", "oct"]}) == (1, False)
        assert self.count("p-sep", {"category": "wz", "declared_count": 2, "file_ids": ["sep"]}) == (2, False)

    def test_block_linking_only_foreign_files_counts_them(self):
        assert self.count("p-oct", {"category": "wz", "declared_count": 2, "file_ids": ["sep"]}) == (2, False)

    def test_mismatch_and_unknowns(self):
        assert self.count("p-oct", {"category": "wz", "declared_count": 3, "file_ids": ["oct"]}) == (1, True)
        assert self.count("p-oct", {"category": "wz", "declared_count": None, "file_ids": ["oct"]}) == (1, False)
        assert self.count("p-x", {"category": "ws", "declared_count": 4, "file_ids": ["gone"]}) == (None, False)
        assert self.count("p-oct", {"category": "cp", "declared_count": 0, "file_ids": []}) == (0, False)
        assert self.count("p-oct", {"category": "cp", "declared_count": 2, "file_ids": []}) == (0, True)
        assert self.count("p-oct", {"category": None, "declared_count": None, "file_ids": []}) == (None, False)

    def test_file_counted_once_per_page(self):
        counted: set = set()
        block = {"category": "wz", "declared_count": 1, "file_ids": ["oct"]}
        assert self.count("p-oct", block, counted) == (1, False)
        assert self.count("p-oct", block, counted) == (0, True)


# =============================================================================
# Exports
# =============================================================================


def _csv_rows(text: str) -> list[list[str]]:
    assert text.startswith(export.BOM)
    return list(csv.reader(io.StringIO(text[1:], newline=""), delimiter=";"))


class TestCsv:
    @pytest.mark.parametrize("value, expected", [
        (None, ""), ("abc", "abc"), (12, "12"), ("a;b", '"a;b"'), ('say "hi"', '"say ""hi"""'),
        ("two\nlines", '"two\nlines"'), ("=SUM(A1)", "'=SUM(A1)"), ("+48", "'+48"), ("@x", "'@x"),
        ("-x", "'-x"), ("-5", "-5"), ("=a;b", "\"'=a;b\""),
        # same rule as csv.js: "-<digit>" is only safe when the whole cell is a plain number
        ("-12,5", "-12,5"), ("-12.5", "-12.5"), ("-1+1", "'-1+1"),
        ("-2+3+cmd|' /C calc'!A0", "'-2+3+cmd|' /C calc'!A0"),
        ('-1+HYPERLINK("http://x";"y")', '"\'-1+HYPERLINK(""http://x"";""y"")"'),
    ])
    def test_escape_cell(self, value, expected):
        assert export.escape_cell(value) == expected

    def test_decimal_comma(self):
        assert export.decimal_comma(52.223054) == "52,223054"
        assert export.decimal_comma(None) == "" and export.decimal_comma(True) == "" and export.decimal_comma(3) == "3"

    def test_to_csv_bom_crlf(self):
        text = export.to_csv(["a", "b"], [[1, "x;y"]])
        assert text == "﻿a;b\r\n1;\"x;y\"\r\n"

    def test_columns_match_the_browser_export(self):
        js = (ROOT / "site" / "js" / "csv.js").read_text(encoding="utf-8")
        m = re.search(r"CSV_COLUMNS\s*=\s*\[(.*?)\];", js, re.S)
        if not m:
            pytest.skip("site/js/csv.js has no CSV_COLUMNS")
        assert re.findall(r"'([^']+)'", m.group(1)) == export.CSV_COLUMNS

    def test_record_row(self):
        r = {"id": "wz-2026-15", "kind": "ws", "procedure": "wz", "number": "N", "date": "2026-07-09",
             "applicant_type": "person", "address": {"display": "Marokańska 1"}, "area": "goclaw",
             "parcels": [{"number": "46/4", "obreb": "3-01-24", "partial": True}], "tags": ["jednorodzinny"],
             "geo": {"lat": 52.2, "lon": 21.07, "method": "street"}, "warnings": ["w1", "w2"], "related": ["a", "b"],
             "sources": [{"file_id": "f1", "page_id": "p1", "sheet": "ROK", "row": 6}]}
        text = export.records_to_csv(
            [r], kinds=build.KINDS, tags={"jednorodzinny": {"label": "Dom jednorodzinny"}},
            areas={"goclaw": {"label": "Gocław"}},
            files_by_id={"f1": {"filename": "plik.xlsx", "url": "https://x/f1", "archive_path": "sources/f1.xlsx"}},
            pages_by_id={"p1": {"title": "Lipiec 2026", "url": "https://x/p1"}}, site_url="https://ex.org/wz")
        header, row = _csv_rows(text)
        cell = dict(zip(header, row))
        assert len(row) == len(export.CSV_COLUMNS)
        assert cell["rodzaj"] == "Wszczęcie" and cell["postepowanie"] == "WZ"
        assert cell["dzialki"] == "46/4 (część) obr. 3-01-24" and cell["obszar"] == "Gocław"
        assert cell["szerokosc_geogr"] == "52,2" and cell["dokladnosc_lokalizacji"] == "ulica (przybliżona)"
        assert cell["uwagi"] == "w1 | w2" and cell["powiazane_wpisy"] == "a, b"
        assert cell["link"] == "https://ex.org/wz/#/wpis/wz-2026-15"
        assert cell["kopia_archiwalna_url"] == "https://ex.org/wz/sources/f1.xlsx"
        assert cell["arkusz_wiersz"] == "ROK!6" and cell["typ_wnioskodawcy"] == "osoba fizyczna"

    def test_v2_cells_of_a_permit_and_a_refusal(self):
        permit = {"id": "pb-st-mz-pa-2026-29594", "kind": "pb", "procedure": "pb", "dataset": "rwdz",
                  "issuer": "district", "outcome": None, "filed_date": "2026-09-24", "applicant_type": "person",
                  "sources": [{"file_id": "rwdz-wnioski", "page_id": "rwdz", "sheet": None, "row": 4}],
                  "permit": {"register_id": "ST-MZ-PA/WNIOSEK/29594/2026", "case_sign": "RPW/142815/2026-1B/FSO",
                             "scope": "inne", "scope_label": "wykonanie robót budowlanych innych niż wymienione "
                                                             "powyżej", "category": "XIII",
                             "category_label": "pozostałe budynki mieszkalne", "cubature": 1234.5}}
        refusal = {"id": "wz-am-2026-95", "kind": "wz", "procedure": "wz", "dataset": "baipp", "issuer": "city",
                   "outcome": "refusal", "permit": None, "sources": []}
        text = export.records_to_csv(
            [permit, refusal], kinds=build.KINDS, tags={}, areas={}, site_url="./",
            files_by_id={"rwdz-wnioski": {"filename": "wynik_mazowieckie.zip", "url": "https://gunb/z.zip",
                                          "archive_path": "sources/rwdz/rwdz-wnioski.csv"}},
            pages_by_id={"rwdz": {"title": "Rejestr", "url": "https://gunb/p"}},
            datasets=build.DATASETS, issuers=build.ISSUERS, outcomes=build.OUTCOMES,
            categories=build.PERMIT_CATEGORIES)
        header, p_row, r_row = _csv_rows(text)
        p, r = dict(zip(header, p_row)), dict(zip(header, r_row))
        assert (p["rodzaj"], p["postepowanie"]) == ("Pozwolenie", "Pozwolenie")
        assert p["zrodlo_danych"] == build.DATASETS["rwdz"]["label"] and p["organ"] == build.ISSUERS["district"]["label"]
        assert (p["rozstrzygniecie"], p["data_wniosku"]) == ("", "2026-09-24")
        assert (p["nr_w_rejestrze"], p["znak_sprawy_urzedu"]) == ("ST-MZ-PA/WNIOSEK/29594/2026", "RPW/142815/2026-1B/FSO")
        assert p["zakres_robot"].startswith("wykonanie robót") and p["kubatura_m3"] == "1234,5"
        assert p["kategoria_obiektu"] == "XIII – pozostałe budynki mieszkalne"
        assert p["arkusz_wiersz"] == "!4" and p["kopia_archiwalna_url"] == "./sources/rwdz/rwdz-wnioski.csv"
        assert (r["zrodlo_danych"], r["organ"], r["rozstrzygniecie"]) == (
            build.DATASETS["baipp"]["label"], build.ISSUERS["city"]["label"], "Odmowa")
        assert r["nr_w_rejestrze"] == r["kategoria_obiektu"] == r["kubatura_m3"] == ""

    def test_category_text_like_the_browser(self):
        assert export.category_text({"category": "IX"}, {"IX": {"label": "kultura"}}) == "IX – kultura"
        assert export.category_text({"category": "IX", "category_label": "budynki kultury"}) == "IX – budynki kultury"
        assert export.category_text({"category": "IX"}) == "IX"
        assert export.category_text(None) == "" and export.category_text({"category": None}) == ""

    def test_links(self):
        assert export.site_link(None, "feed.xml") == "./feed.xml"
        assert export.site_link("https://a.b/c", "/sources/x") == "https://a.b/c/sources/x"
        assert export.permalink("./", "wz-2026-15") == "./#/wpis/wz-2026-15"
        assert export.permalink("https://a.b/", "a b/c") == "https://a.b/#/wpis/a%20b%2Fc"


class TestFeed:
    def _records(self, n):
        return [{"id": f"wz-2026-{i}", "kind": "wz", "number": f"{i}/PPD/WZ/2026", "date": f"2026-01-{i % 28 + 1:02d}",
                 "investment": "budowa <budynku> & „garażu”" + " bardzo długi opis" * 30,
                 "address": {"display": "Mińska 46"}, "parcels": [], "tags": ["t1"], "warnings": ["uwaga"],
                 "sources": [{"file_id": "f", "page_id": "p", "sheet": "ROK", "row": i}]} for i in range(n)]

    def _feed(self, records, site_url="https://ex.org/wz/"):
        return export.atom_feed(records, kinds=build.KINDS, tags={"t1": {"label": "Tag"}}, areas={},
                                files_by_id={"f": {"filename": "a.xlsx", "url": "https://src/a?t=1",
                                                   "archive_path": "sources/f.xlsx"}},
                                pages_by_id={"p": {"title": "Styczeń 2026", "url": "https://src/p",
                                                   "published_at": "2026-02-10T08:00:00Z"}},
                                generated_at=NOW, site_url=site_url)

    def test_valid_atom_newest_first_and_limited(self):
        xml = self._feed(self._records(150))
        root = ET.fromstring(xml.encode("utf-8"))
        entries = root.findall(f"{ATOM}entry")
        assert len(entries) == export.FEED_LIMIT
        assert root.find(f"{ATOM}updated").text == NOW
        first = entries[0]
        assert first.find(f"{ATOM}link[@rel='alternate']").get("href").startswith("https://ex.org/wz/#/wpis/")
        assert first.find(f"{ATOM}link[@rel='related']").get("href") == "https://src/a?t=1"
        assert first.find(f"{ATOM}updated").text == "2026-02-10T08:00:00Z"
        content = first.find(f"{ATOM}content").text  # HTML, after one round of XML unescaping
        assert content.startswith("<p><strong>") and "&lt;budynku&gt; &amp; „garażu”" in content
        assert first.find(f"{ATOM}title").text.endswith("…")
        ids = [e.find(f"{ATOM}id").text for e in entries]
        assert len(set(ids)) == len(ids)
        dates = [e.find(f"{ATOM}link[@rel='alternate']").get("href") for e in entries]
        assert dates[0].endswith("wz-2026-139")  # newest date (2026-01-28: i = 27, 55, …, 139), highest number first

    def test_deterministic_and_stable_ids(self):
        recs = self._records(3)
        assert self._feed(recs) == self._feed(list(reversed(recs)))
        a = ET.fromstring(self._feed(recs).encode()).find(f"{ATOM}entry/{ATOM}id").text
        b = ET.fromstring(self._feed(recs, site_url="./").encode()).find(f"{ATOM}entry/{ATOM}id").text
        assert a == b and a.startswith("urn:uuid:")

    def test_refusal_is_named_and_dataset_shown(self):
        recs = self._records(1)
        recs[0].update(outcome="refusal", dataset="baipp")
        xml = export.atom_feed(recs, kinds=build.KINDS, tags={}, areas={}, files_by_id={}, pages_by_id={},
                               generated_at=NOW, datasets=build.DATASETS, outcomes=build.OUTCOMES)
        entry = ET.fromstring(xml.encode("utf-8")).find(f"{ATOM}entry")
        assert entry.find(f"{ATOM}title").text.startswith("WZ (odmowa) · ")
        content = entry.find(f"{ATOM}content").text
        assert "Rozstrzygnięcie: Odmowa" in content and build.DATASETS["baipp"]["label"] in content
        recs[0]["outcome"] = "granted"   # a positive decision reads as before
        xml = export.atom_feed(recs, kinds=build.KINDS, tags={}, areas={}, files_by_id={}, pages_by_id={},
                               generated_at=NOW, outcomes=build.OUTCOMES)
        assert ET.fromstring(xml.encode()).find(f"{ATOM}entry/{ATOM}title").text.startswith("WZ · ")

    def test_control_characters_are_dropped(self):
        recs = self._records(1)
        recs[0]["investment"] = "zły\x0bznak"
        ET.fromstring(self._feed(recs).encode("utf-8"))  # must parse


# =============================================================================
# geocode.py integration fixes (regression tests)
# =============================================================================


class _Resp:
    def __init__(self, payload):
        self.status_code = 200
        self._payload = payload
        self.text = json.dumps(payload)
        self.headers = {}

    def json(self):
        return self._payload


class _UugSession:
    def __init__(self, addresses):
        self.addresses = addresses

    def get(self, url, params=None, timeout=None):
        assert url == gc.UUG_URL
        return _Resp(self.addresses.get(params["address"], {"type": "street", "found objects": 0, "results": None}))


def _street(name, wkt, x, y):
    return {"type": "street", "results": {"1": {"street": f"ulica {name}", "x": str(x), "y": str(y),
                                                "accuracy": "0.7", "geometry_wkt": wkt}}}


class TestGeocodeIntegration:
    def test_crossing_uses_normalised_parts(self):
        """The normaliser keeps only the first street in ``street``; the others are in ``parts``."""
        sess = _UugSession({
            "Warszawa, Aaa": _street("Aaa", "LINESTRING(21.07 52.23,21.09 52.23)", 21.08, 52.23),
            "Warszawa, Bbb": _street("Bbb", "LINESTRING(21.085 52.225,21.085 52.24)", 21.085, 52.235),
        })
        address = {"street": "Aaa", "number": None, "display": "Aaa / Bbb",
                   "parts": [{"street": "Aaa", "number": None, "numbers": []},
                             {"street": "Bbb", "number": None, "numbers": []}]}
        r = gc.geocode_record_address(address, {}, sess, DISTRICT)
        assert r["note"] == gc.NOTE_CROSSING
        assert (r["lon"], r["lat"]) == pytest.approx((21.085, 52.23), abs=1e-6)
        # Without parts the first street alone is used (old behaviour for plain addresses).
        single = gc.geocode_record_address({"street": "Aaa", "number": None}, {}, sess, DISTRICT)
        assert single["note"] == gc.NOTE_STREET

    def test_known_subparcels(self):
        cache = {"146507_8.0203.3": uldk_missing(), "146507_8.0203.3/1": uldk_ok(21.06, 52.25),
                 "146507_8.0203.3/10": uldk_ok(21.061, 52.25), "146507_8.0203.30": uldk_ok(21.07, 52.25),
                 "146507_8.0203.3/2": {"status": "missing"}, "146507_8.0202.1/9": uldk_missing(),
                 "146507_8.0202.1/9/1": uldk_ok(21.0, 52.0), "146507_8.0203.4": uldk_missing()}
        results = {k: v for k, v in cache.items()}
        got = gc.known_subparcels(["146507_8.0203.3", "146507_8.0202.1/9", "146507_8.0203.4"], results, cache)
        assert got == {"146507_8.0203.3": ["146507_8.0203.3/1", "146507_8.0203.3/10"]}

    def _locate(self, tmp_path, records, uug=None):
        (tmp_path / "uldk.json").write_text(json.dumps({
            "146507_8.0203.3": uldk_missing(),
            "146507_8.0203.3/1": uldk_ok(21.068, 52.253),
            "146507_8.0203.3/2": uldk_ok(21.0685, 52.253),
            "146507_8.0101.1": uldk_ok(21.05, 52.24),
        }))
        (tmp_path / "uug.json").write_text(json.dumps(uug or {}))
        index = AreaIndex(DISTRICT, [("grochow", "Grochów", DISTRICT)])
        return gc.locate_records(records, str(tmp_path), online=False, log=lambda *_: None, area_index=index)

    def test_subdivided_parcel_located_by_its_parts(self, tmp_path):
        records = [rec("wz-1", parcels=["146507_8.0203.3"], street="Chodakowska"),
                   rec("cp-1", parcels=["146507_8.0203.3/1"]), rec("cp-2", parcels=["146507_8.0203.3/2"])]
        out = self._locate(tmp_path, records)
        g = records[0]["geo"]
        assert g["method"] == "parcel"
        assert g["parcels_found"] == ["146507_8.0203.3/1", "146507_8.0203.3/2"]
        assert "została podzielona" in g["note"] and "3/1, 3/2" in g["note"]
        assert g["lon"] == pytest.approx(21.0685, abs=1e-4) and records[0]["area"] == "grochow"
        assert out["stats"]["records_via_subparcels"] == 1
        feature = next(f for f in out["parcels_geojson"]["features"] if f["id"] == "146507_8.0203.3/1")
        assert feature["properties"]["records"] == ["cp-1", "wz-1"]

    def test_exact_address_beats_subparcel_approximation(self, tmp_path):
        uug = {"Warszawa, Chodakowska 5": {
            "status": "ok", "type": "address", "fetched_at": NOW,
            "candidates": [{"street": "ulica Chodakowska", "number": "5", "lon": 21.066, "lat": 52.249,
                            "accuracy": 0.8, "city": "Warszawa"}]}}
        records = [rec("wz-1", parcels=["146507_8.0203.3"], street="Chodakowska", number="5")]
        self._locate(tmp_path, records, uug)
        g = records[0]["geo"]
        assert g["method"] == "address" and (g["lon"], g["lat"]) == (21.066, 52.249)
        assert "nie znaleziono w ewidencji gruntów (ULDK)" in g["note"]

    @staticmethod
    def _parcel(geometry: dict) -> dict:
        return {"status": "ok", "geometry": geometry, "centroid": geo.centroid(geometry), "bbox": geo.bbox(geometry),
                "area_m2": round(geo.area_m2(geometry), 1), "fetched_at": NOW}

    def _locate_parcels(self, tmp_path, parcels: dict[str, dict]) -> dict:
        (tmp_path / "uldk.json").write_text(json.dumps({pid: self._parcel(g) for pid, g in parcels.items()}))
        (tmp_path / "uug.json").write_text("{}")
        records = [rec("pb-1", parcels=list(parcels))]
        out = gc.locate_records(records, str(tmp_path), online=False, log=lambda *_: None,
                                area_index=AreaIndex(DISTRICT, [("grochow", "Grochów", DISTRICT)]))
        return {"geo": records[0]["geo"], "stats": out["stats"]}

    def test_separate_parcels_point_goes_to_the_largest(self, tmp_path):
        """Two plots 200 m apart: their weighted centroid lies on neither – use the larger plot."""
        big, small = square(21.060, 52.250, 0.0010), square(21.0645, 52.250, 0.0005)
        got = self._locate_parcels(tmp_path, {"146507_8.0101.1": small, "146507_8.0101.2": big})
        g = got["geo"]
        assert (g["lon"], g["lat"]) == pytest.approx((21.0605, 52.2505), abs=1e-7)
        assert geo.point_in_polygon([g["lon"], g["lat"]], big)
        assert g["method"] == "parcel" and g["note"] is None   # no new note
        assert g["parcels_found"] == ["146507_8.0101.1", "146507_8.0101.2"]
        assert g["bbox"] == pytest.approx([21.06, 52.25, 21.065, 52.251])   # still covers both
        assert got["stats"]["records_point_on_largest_parcel"] == 1

    def test_adjacent_parcels_keep_the_weighted_centroid(self, tmp_path):
        a, b = square(21.060, 52.250, 0.0005), square(21.0605, 52.250, 0.0010)   # b has 4× the area of a
        got = self._locate_parcels(tmp_path, {"146507_8.0101.1": a, "146507_8.0101.2": b})
        assert (got["geo"]["lon"], got["geo"]["lat"]) == pytest.approx((21.06085, 52.25045), abs=1e-5)
        assert got["stats"]["records_point_on_largest_parcel"] == 0

    def test_parcels_partly_outside_the_district_place_the_point_on_the_district_ones(self, tmp_path):
        """A sewer from a neighbouring district: big parcels just east of the district, a small one inside."""
        outside = {"146509_8.0702.1": square(21.1350, 52.230, 0.002), "146509_8.0702.2": square(21.1350, 52.232, 0.002)}
        inside = {"146507_8.0303.35": square(21.1280, 52.231, 0.0005)}
        got = self._locate_parcels(tmp_path, {**outside, **inside})
        g = got["geo"]
        assert g["method"] == "parcel" and (g["lon"], g["lat"]) == pytest.approx((21.12825, 52.23125), abs=1e-6)
        assert g["note"] == gc.NOTE_PARCELS_IN_DISTRICT
        assert g["parcels_found"] == [*outside, *inside]        # every parcel still drawn
        assert got["stats"]["records_parcels_in_district_only"] == 1
        assert got["stats"]["outside_district_discarded"] == 0
        # all parcels outside: discarded as before
        got = self._locate_parcels(tmp_path, outside)
        assert got["geo"]["method"] is None and got["stats"]["outside_district_discarded"] == 1

    def test_concave_parcel_point_lies_on_it(self, tmp_path):
        """A U-shaped plot (a bent road): its centroid falls in the gap – the point moves onto the plot."""
        u = {"type": "Polygon", "coordinates": [[[21.060, 52.250], [21.063, 52.250], [21.063, 52.253],
                                                 [21.062, 52.253], [21.062, 52.251], [21.061, 52.251],
                                                 [21.061, 52.253], [21.060, 52.253], [21.060, 52.250]]]}
        assert not geo.point_in_polygon(geo.centroid(u), u)
        g = self._locate_parcels(tmp_path, {"146507_8.0101.1": u})["geo"]
        assert geo.point_in_polygon([g["lon"], g["lat"]], u) and g["note"] is None


# =============================================================================
# End-to-end run_build on a throw-away project
# =============================================================================


FILES = {
    # file_id: (fixture, period, category, page_ids)
    "aaaaaaaaaa": ("new-wz-2026-07", "2026-07", "wz", ["p-2026-07", "p-2026-08"]),
    "bbbbbbbbbb": ("new-wz-2026-07", "2026-08", "wz", ["p-2026-08"]),     # same decisions listed again
    "cccccccccc": ("new-ws-2025-11-numbering-gap", "2025-11", "ws", ["p-2025-11"]),
    "dddddddddd": ("old-ws-2020-10-empty-template", "2020-10", "ws", ["p-2020-10"]),
    "eeeeeeeeee": (None, "2020-10", "wz", ["p-2020-10"]),                 # never downloaded
}


def _page(page_id, period, title, blocks, published_at="2026-08-10T08:32:00Z"):
    return {"page_id": page_id, "url": f"https://src.example/-/{page_id}", "title": title, "period": period,
            "published_at": published_at, "summary": None, "index_page": 1, "warnings": [],
            "blocks": [{"text": t, "category": c, "declared_count": n, "file_ids": f} for t, c, n, f in blocks]}


#: a permit that shares parcel 46/4 (obręb 3-01-24) with the district's wz-2026-15 fixture decision
SHARED_PARCEL = (b";146507_8;0605;25/12;", b";146507_8;0124;46/4;")


def gunb_zip(file: rwdz_mod.RwdzFile, data: bytes, directory: Path) -> Path:
    """A fake GUNB archive (one CSV member, as on the server) holding ``data``."""
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / file.zip_name
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(file.zip_name.replace(".zip", ".csv"), data)
    return path


def rwdz_fixture(file_id: str) -> bytes:
    data = (RWDZ_FIX / RWDZ_FIXTURES[file_id]).read_bytes()
    return data.replace(*SHARED_PARCEL) if file_id == "rwdz-wnioski" else data


def add_rwdz_extracts(root: Path, zips: Path) -> None:
    """Commit RWDZ extracts (+ sidecars) the way a live run leaves them, from real register lines."""
    for f in rwdz_mod.FILES:
        zip_path = gunb_zip(f, rwdz_fixture(f.file_id), zips)
        snapshot = {"url": f.url, "etag": '"fixture"', "last_modified": "2026-10-22T21:35:08Z",
                    "sha256_zip": sha(zip_path), "size": zip_path.stat().st_size, "downloaded_at": NOW}
        rwdz_mod.extract_csv(f, zip_path, root / rwdz_mod.LOCAL_DIR, snapshot, log=lambda *_: None)


def make_project(tmp_path: Path, *, rwdz: bool = True) -> build.Paths:
    root = tmp_path / "proj"
    raw = root / "data" / "raw"
    raw.mkdir(parents=True)
    files = []
    for fid, (fixture, period, category, page_ids) in FILES.items():
        entry = {"file_id": fid, "url": f"https://src.example/documents/{fid}.xlsx?t=1", "document_path": f"/d/{fid}",
                 "filename": f"{fixture or 'brak'}.xlsx", "ext": "xlsx", "category": category, "period": period,
                 "page_ids": page_ids, "local_path": f"data/raw/{fid}.xlsx", "sha256": None, "size": None,
                 "downloaded_at": None, "last_modified": None, "history": []}
        if fixture:
            dst = raw / f"{fid}.xlsx"
            shutil.copyfile(FIX / f"{fixture}.xlsx", dst)
            entry.update(sha256=sha(dst), size=dst.stat().st_size, downloaded_at=NOW)
        else:
            entry["error"] = "HTTPError: 503"
        files.append(entry)
    pages = [
        _page("p-2026-08", "2026-08", "Sierpień 2026", [
            ("Wydane decyzje o warunkach zabudowy: 3 pozycje", "wz", 3, ["aaaaaaaaaa", "bbbbbbbbbb"]),
            ("Wydane decyzje CP: 0 pozycji", "cp", 0, [])]),
        _page("p-2026-07", "2026-07", "Lipiec 2026", [
            ("Wydane decyzje o warunkach zabudowy: 3 pozycje", "wz", 3, ["aaaaaaaaaa"])]),
        _page("p-2025-11", "2025-11", "Listopad 2025", [
            ("Informacje o wszczętych postępowaniach: 4 pozycje", "ws", 4, ["cccccccccc"])], published_at=None),
        _page("p-2020-10", "2020-10", "Październik 2020", [
            ("Informacja o wszczętych postępowaniach – brak", "ws", 0, ["dddddddddd"]),
            ("Wydane decyzje o warunkach zabudowy: 2 pozycje", "wz", 2, ["eeeeeeeeee"])], published_at=None),
    ]
    manifest = {"generated_at": "2026-10-01T00:00:00Z", "index_url": "https://src.example/index",
                "pages": pages, "files": files}
    crawl_mod.write_manifest(manifest, root / "data" / "manifest.json")

    cache = root / "data" / "cache"
    cache.mkdir(parents=True)
    (cache / "uldk.json").write_text(json.dumps({"146507_8.0124.46/4": uldk_ok(21.0745, 52.223),
                                                 "146507_8.0203.27/1": uldk_missing(),
                                                 "146507_8.0406.137": uldk_ok(21.09, 52.24)}))   # a permit's
    if rwdz:
        add_rwdz_extracts(root, tmp_path / "gunb")
    (cache / "uug.json").write_text("{}")
    site_data = root / "site" / "data"
    site_data.mkdir(parents=True)
    areas = {"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {"slug": "_district", "label": "Praga-Południe"}, "geometry": DISTRICT},
        {"type": "Feature", "properties": {"slug": "testowo", "label": "Testowo"}, "geometry": DISTRICT}]}
    (site_data / "areas.geojson").write_text(json.dumps(areas))
    return build.Paths(root)


@pytest.fixture()
def project(tmp_path):
    return make_project(tmp_path)


def _load(paths: build.Paths):
    return (json.loads(paths.records_json.read_text(encoding="utf-8")),
            json.loads(paths.sources_json.read_text(encoding="utf-8")))


class TestRunBuild:
    def _run(self, paths, now=NOW, **kw):
        return build.run_build(paths, crawl=False, online=False, site_url="https://ex.org/wz/",
                               now=lambda: now, **kw)

    def test_outputs(self, project):
        areas_before = project.areas_geojson.read_bytes()
        result = self._run(project)
        assert result.exit_code == build.EXIT_OK and result.generated_at == NOW
        records_doc, sources_doc = _load(project)

        # records.json
        assert records_doc["count"] == len(records_doc["records"]) == 6
        assert list(records_doc["kinds"]) == ["wz", "cp", "ws", "pb", "zg"] and "jednorodzinny" in records_doc["tags"]
        assert records_doc["kinds"]["pb"]["short"] == "Pozwolenie" and records_doc["kinds"]["zg"]["description"]
        assert records_doc["areas"] == {"testowo": {"label": "Testowo"}}
        by_id = {r["id"]: r for r in records_doc["records"]}
        assert list(by_id) == ["wz-2026-17", "wz-2026-16", "wz-2026-15",
                               "ws-6730-2025-51", "ws-6730-2025-48", "ws-6730-2025-40"]  # newest first
        r15 = by_id["wz-2026-15"]
        assert list(r15)[:7] == ["id", "kind", "procedure", "dataset", "issuer", "outcome", "number"]
        assert (r15["dataset"], r15["issuer"], r15["outcome"], r15["filed_date"], r15["permit"]) == (
            "district", "district", None, None, None)
        assert list(records_doc["datasets"]) == ["district", "baipp", "rwdz"]
        assert records_doc["datasets"]["rwdz"]["licence"] == "CC0 1.0"
        assert records_doc["outcomes"]["refusal"]["label"] == "Odmowa" and "city" in records_doc["issuers"]
        assert records_doc["counts_by_kind"] == {"wz": 3, "cp": 0, "ws": 3, "pb": 12, "zg": 4}
        assert records_doc["permit_scopes"]["rozbiorka"] == {"label": "Rozbiórka"} and len(records_doc["permit_scopes"]) == 6
        assert len(records_doc["permit_categories"]) == 30
        assert records_doc["permit_categories"]["XIII"]["description"].startswith("Kategoria XIII – ")
        assert [s["file_id"] for s in r15["sources"]] == ["aaaaaaaaaa", "bbbbbbbbbb"]  # merged across files
        assert r15["sources"][0]["page_id"] == "p-2026-07" and r15["period"] == "2026-07"
        assert r15["geo"]["method"] == "parcel" and r15["area"] == "testowo"
        assert by_id["wz-2026-16"]["geo"]["method"] is None  # parcel missing, no address cache offline
        # the permit on the same parcel is related (across datasets); nothing else relates
        assert r15["related"] == ["pb-st-mz-pa-2026-29594"]
        assert all(r["related"] == [] for r in records_doc["records"] if r["id"] != "wz-2026-15")

        # permits.json – GUNB RWDZ, built offline from the committed extracts
        permits_doc = json.loads(project.permits_json.read_text(encoding="utf-8"))
        assert list(permits_doc) == ["generated_at", "count", "records"] and permits_doc["generated_at"] == NOW
        permits = {r["id"]: r for r in permits_doc["records"]}
        assert permits_doc["count"] == len(permits) == 16
        assert list(permits)[:3] == ["pb-st-mz-pa-2026-29594", "zg-st-mz-pa-2026-6161", "pb-st-mz-pa-2024-10219"]
        pb = permits["pb-st-mz-pa-2026-29594"]
        assert list(pb) == list(build.RECORD_FIELDS)
        assert (pb["kind"], pb["procedure"], pb["dataset"], pb["issuer"], pb["number"], pb["filed_date"]) == (
            "pb", "pb", "rwdz", "district", "163/PPD/PB/2026", "2026-09-24")
        assert pb["permit"]["register_id"] == "ST-MZ-PA/WNIOSEK/29594/2026" and pb["permit"]["category"] == "XIII"
        assert pb["related"] == ["wz-2026-15"]
        assert pb["geo"]["method"] == "parcel" and pb["area"] == "testowo"
        assert pb["sources"][0]["file_id"] == "rwdz-wnioski" and pb["sources"][0]["page_id"] == "rwdz"
        assert permits["pb-st-mz-pa-2020-12384"]["geo"]["parcels_found"] == ["146507_8.0406.137"]
        assert not set(permits) & set(by_id)

        # sources.json
        files = {f["file_id"]: f for f in sources_doc["files"]}
        assert files["aaaaaaaaaa"]["parsed_count"] == 3 and files["aaaaaaaaaa"]["kind_detected"] == "wz"
        assert files["aaaaaaaaaa"]["rows_total"] == 3 and files["eeeeeeeeee"]["rows_total"] is None
        assert files["aaaaaaaaaa"]["record_ids"] == ["wz-2026-15", "wz-2026-16", "wz-2026-17"]
        assert files["aaaaaaaaaa"]["archive_path"] == "sources/aaaaaaaaaa.xlsx"
        assert files["dddddddddd"]["parsed_count"] == 0 and files["dddddddddd"]["skipped_rows"] > 0
        assert files["eeeeeeeeee"]["parsed_count"] is None and files["eeeeeeeeee"]["archive_path"] is None
        assert files["eeeeeeeeee"]["warnings"]
        blocks = {(p["page_id"], b["category"]): b for p in sources_doc["pages"] for b in p["blocks"]}
        assert blocks[("p-2026-08", "wz")]["parsed_count"] == 3  # only the file first published there
        assert blocks[("p-2026-08", "wz")]["count_mismatch"] is False
        assert blocks[("p-2026-08", "cp")]["parsed_count"] == 0
        assert blocks[("p-2025-11", "ws")]["parsed_count"] == 3 and blocks[("p-2025-11", "ws")]["count_mismatch"]
        assert blocks[("p-2020-10", "ws")]["parsed_count"] == 0  # empty template, "brak"
        assert blocks[("p-2020-10", "ws")]["count_mismatch"] is False
        assert blocks[("p-2020-10", "wz")]["parsed_count"] is None
        assert sources_doc["generated_at"] == records_doc["generated_at"] == NOW
        # … and the RWDZ pseudo-page + one entry per GUNB archive, after the manifest's pages and files
        assert sources_doc["pages"][-1]["page_id"] == "rwdz" and sources_doc["pages"][-1]["source"] == "rwdz"
        assert [f["file_id"] for f in sources_doc["files"][-3:]] == [f.file_id for f in rwdz_mod.FILES]
        wn = files["rwdz-wnioski"]
        assert (wn["source"], wn["licence"], wn["parsed_count"], wn["rows_total"]) == ("rwdz", "CC0 1.0", 21, 25)
        assert wn["archive_path"] == "sources/rwdz/rwdz-wnioski.csv"
        assert wn["archive_meta_path"] == "sources/rwdz/rwdz-wnioski.meta.json"
        assert wn["record_ids"][0] == "pb-st-mz-pa-2026-29594" and len(wn["record_ids"]) == 12
        assert blocks[("rwdz", "pb")]["parsed_count"] == 21

        # parcels.geojson, mirror, CSV, feed, report
        # a parcel used by both files lives in parcels.geojson (listing both); permit-only parcels go apart
        parcels = json.loads(project.parcels_geojson.read_text(encoding="utf-8"))
        assert [f["id"] for f in parcels["features"]] == ["146507_8.0124.46/4"]
        assert parcels["features"][0]["properties"]["records"] == ["pb-st-mz-pa-2026-29594", "wz-2026-15"]
        assert "attribution" in parcels
        permit_parcels = json.loads(project.parcels_permits_geojson.read_text(encoding="utf-8"))
        assert [f["id"] for f in permit_parcels["features"]] == ["146507_8.0406.137"]
        assert permit_parcels["features"][0]["properties"]["records"] == ["pb-st-mz-pa-2020-12384"]
        assert permit_parcels["attribution"] == parcels["attribution"]
        for fid in ("aaaaaaaaaa", "bbbbbbbbbb", "cccccccccc", "dddddddddd"):
            copy = project.mirror / f"{fid}.xlsx"
            assert copy.read_bytes() == (project.raw / f"{fid}.xlsx").read_bytes()
        assert not (project.mirror / "eeeeeeeeee.xlsx").exists()
        for f in rwdz_mod.FILES:   # extracts and their line maps, byte for byte
            for name in (f"{f.file_id}.csv", f"{f.file_id}.meta.json"):
                assert (project.rwdz_mirror / name).read_bytes() == (project.rwdz_raw / name).read_bytes()
        rows = _csv_rows(project.records_csv.read_text(encoding="utf-8"))
        assert rows[0] == export.CSV_COLUMNS and len(rows) == 7
        assert rows[1][export.CSV_COLUMNS.index("link")] == "https://ex.org/wz/#/wpis/wz-2026-17"
        assert rows[1][export.CSV_COLUMNS.index("zrodlo_danych")] == build.DATASETS["district"]["label"]
        prow = _csv_rows(project.permits_csv.read_text(encoding="utf-8"))
        assert prow[0] == export.CSV_COLUMNS and [r[0] for r in prow[1:]] == list(permits)
        cell = dict(zip(prow[0], prow[1]))
        assert cell["nr_w_rejestrze"] == "ST-MZ-PA/WNIOSEK/29594/2026" and cell["rodzaj"] == "Pozwolenie"
        assert cell["kategoria_obiektu"] == "XIII – pozostałe budynki mieszkalne"
        assert cell["plik_url"] == rwdz_mod.FILES[0].url
        assert cell["kopia_archiwalna_url"] == "https://ex.org/wz/sources/rwdz/rwdz-wnioski.csv"
        feed = ET.fromstring(project.feed.read_bytes())
        assert len(feed.findall(f"{ATOM}entry")) == 6   # planning records only
        report = project.report.read_text(encoding="utf-8")
        assert "## Declared vs parsed counts" in report and "Listopad 2025" in report
        assert "[`wz-2026-16`](https://ex.org/wz/#/wpis/wz-2026-16)" in report
        assert "## GUNB RWDZ (building permits and notifications)" in report
        assert "## Related records across datasets" in report
        assert "| 2026 | 1 | 1 | 2 |" in report   # permits per year: pb, zg, total

        # the areas file belongs to the geocoding stage and is never rewritten by the build
        assert project.areas_geojson.read_bytes() == areas_before

    def test_noop_rebuild_changes_nothing(self, project):
        self._run(project)
        snapshot = {p: p.read_bytes() for p in project.site.rglob("*") if p.is_file()}
        snapshot[project.report] = project.report.read_bytes()
        again = self._run(project, now="2099-01-01T00:00:00Z")
        assert again.written == [] and again.generated_at == NOW
        assert {p: p.read_bytes() for p in snapshot} == snapshot

    def test_site_url_change_keeps_generated_at(self, project):
        # update.yml builds with the Pages URL, test.yml rebuilds with "./": only the CSVs, the feed and the
        # report embed it, so the JSON (compared by test.yml) and generated_at must not change.
        self._run(project)
        data = (project.records_json, project.permits_json, project.sources_json, project.parcels_geojson,
                project.parcels_permits_geojson)
        snapshot = {p: p.read_bytes() for p in data}
        again = build.run_build(project, crawl=False, online=False, site_url="./", now=lambda: "2099-01-01T00:00:00Z")
        assert again.generated_at == NOW
        assert {p: p.read_bytes() for p in data} == snapshot
        assert project.records_csv in again.written and project.feed in again.written
        assert not set(again.written) & set(data)
        assert "https://ex.org/wz/" not in project.records_csv.read_text(encoding="utf-8")
        third = self._run(project, now="2099-01-02T00:00:00Z")
        assert third.generated_at == NOW and not set(third.written) & set(data)
        assert "https://ex.org/wz/#/wpis/" in project.records_csv.read_text(encoding="utf-8")

    def test_default_site_url_comes_from_the_committed_feed(self, project, monkeypatch):
        monkeypatch.delenv("SITE_URL", raising=False)
        self._run(project)   # as CI leaves it: absolute links
        assert build.committed_site_url(project) == "https://ex.org/wz/"
        again = build.run_build(project, crawl=False, online=False, now=lambda: "2099-01-01T00:00:00Z")
        assert again.written == [] and again.generated_at == NOW
        project.feed.unlink()
        assert build.committed_site_url(project) is None
        build.run_build(project, crawl=False, online=False, now=lambda: "2099-01-01T00:00:00Z")
        assert "./#/wpis/" in project.records_csv.read_text(encoding="utf-8")

    def test_changed_data_gets_new_timestamp_and_prunes_mirror(self, project):
        self._run(project)
        manifest = json.loads(project.manifest.read_text(encoding="utf-8"))
        manifest["files"] = [f for f in manifest["files"] if f["file_id"] != "cccccccccc"]
        for page in manifest["pages"]:
            for block in page["blocks"]:
                block["file_ids"] = [f for f in block["file_ids"] if f != "cccccccccc"]
        crawl_mod.write_manifest(manifest, project.manifest)
        result = self._run(project, now="2026-11-12T06:00:00Z")
        assert result.generated_at == "2026-11-12T06:00:00Z" and project.records_json in result.written
        records_doc, _ = _load(project)
        assert records_doc["count"] == 3
        assert not (project.mirror / "cccccccccc.xlsx").exists()

    def test_deterministic_across_fresh_projects(self, tmp_path):
        a = make_project(tmp_path / "a")
        b = make_project(tmp_path / "b")
        self._run(a)
        self._run(b)
        for rel in ("site/data/records.json", "site/data/sources.json", "site/data/parcels.geojson",
                    "site/data/records.csv", "site/data/permits.json", "site/data/parcels-permits.geojson",
                    "site/data/permits.csv", "site/feed.xml", "data/report.md"):
            assert (a.root / rel).read_bytes() == (b.root / rel).read_bytes(), rel

    def test_cli_offline(self, project):
        assert build.main(["--offline", "--root", str(project.root), "-q"]) == build.EXIT_OK
        assert project.records_json.is_file()

    def test_cli_without_manifest(self, tmp_path):
        assert build.main(["--offline", "--root", str(tmp_path), "-q"]) == build.EXIT_FATAL


class TestManifestStage:
    def test_crawl_failure_falls_back_to_previous_manifest(self, project):
        class Down:
            def get(self, url, **kw):
                raise requests.ConnectionError("down")

        result = build.run_build(project, crawl=True, online=True, site_url="./", session=Down(),
                                 geo_session=object(), now=lambda: NOW)
        assert result.exit_code == build.EXIT_STALE and "ConnectionError" in result.crawl_error
        assert "live crawl failed" in project.report.read_text(encoding="utf-8")
        assert json.loads(project.records_json.read_text(encoding="utf-8"))["count"] == 6

    def test_unchanged_crawl_keeps_manifest_timestamp(self, project, monkeypatch):
        previous = json.loads(project.manifest.read_text(encoding="utf-8"))

        def fake_run_crawl(out_path, raw_dir, refresh=False, session=None):
            fresh = {**previous, "generated_at": "2099-01-01T00:00:00Z"}
            crawl_mod.write_manifest(fresh, out_path)
            return fresh

        monkeypatch.setattr(build.crawl_mod, "run_crawl", fake_run_crawl)
        manifest, error = build.obtain_manifest(project, crawl=True)
        assert error is None and manifest["generated_at"] == previous["generated_at"]
        assert json.loads(project.manifest.read_text(encoding="utf-8")) == previous


    def test_page_without_its_file_list_fails_the_build(self, project, monkeypatch):
        # the crawler kept a maintenance-page month from the previous crawl (stale_pages): exit 3, no deploy
        previous = json.loads(project.manifest.read_text(encoding="utf-8"))

        def fake_run_crawl(out_path, raw_dir, refresh=False, session=None):
            fresh = {**previous, "stale_pages": ["p-2026-08"]}
            crawl_mod.write_manifest(fresh, out_path)
            return fresh

        monkeypatch.setattr(build.crawl_mod, "run_crawl", fake_run_crawl)
        result = build.run_build(project, crawl=True, online=True, site_url="./", session=object(),
                                 geo_session=object(), rwdz=False, now=lambda: NOW)
        assert result.exit_code == build.EXIT_STALE and "p-2026-08" in result.crawl_error
        assert json.loads(project.records_json.read_text(encoding="utf-8"))["count"] == 6

    def test_a_file_that_gave_records_and_is_unreadable_now_fails_the_build(self, project):
        TestRunBuild()._run(project)
        (project.raw / "cccccccccc.xlsx").write_bytes(b"PK\x03\x04 truncated")
        result = TestRunBuild()._run(project, now="2026-11-12T06:00:00Z")
        assert result.exit_code == build.EXIT_STALE and result.lost_files == ["cccccccccc"]
        assert "cannot be read now" in project.report.read_text(encoding="utf-8")
        again = TestRunBuild()._run(project, now="2026-11-13T06:00:00Z")   # still unreadable, nothing gave rows
        assert again.lost_files == [] and again.exit_code == build.EXIT_OK


# =============================================================================
# The RWDZ stage inside the build (download modes, failures)
# =============================================================================


class _ZipResponse:
    def __init__(self, status: int, content: bytes = b"", headers: dict | None = None):
        self.status_code, self.content, self.headers = status, content, CaseInsensitiveDict(headers or {})

    def iter_content(self, chunk_size: int = 1):
        yield self.content

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class FakeGunb:
    """GUNB's download server: one archive per URL, ETag ``"fixture"``; a matching If-None-Match → 304."""

    ETAG = '"fixture"'

    def __init__(self, archives: dict[str, bytes], etag: str = ETAG):
        self.archives, self.etag, self.calls = archives, etag, []

    def get(self, url, headers=None, stream=False, timeout=None):
        self.calls.append(url)
        if (headers or {}).get("If-None-Match") == self.etag:
            return _ZipResponse(304, headers={"ETag": self.etag})
        data = self.archives[url]
        return _ZipResponse(200, data, {"ETag": self.etag, "Last-Modified": "Fri, 23 Oct 2026 21:35:08 GMT",
                                        "Content-Length": str(len(data))})

    def head(self, url, timeout=None):
        return _ZipResponse(200, headers={"ETag": self.etag, "Last-Modified": "Fri, 23 Oct 2026 21:35:08 GMT"})


class _NoNetwork:
    """A geocoding session that must not be needed (every lookup becomes a non-cached error)."""

    def get(self, *a, **kw):
        raise requests.ConnectionError("no network in tests")


@pytest.fixture()
def unchanged_crawl(monkeypatch):
    """The district/BAiPP crawl finds nothing new (the manifest on disk is returned)."""
    def fake_run_crawl(out_path, raw_dir, refresh=False, session=None):
        return json.loads(Path(out_path).read_text(encoding="utf-8"))

    monkeypatch.setattr(build.crawl_mod, "run_crawl", fake_run_crawl)


class TestRwdzStage:
    def _offline(self, paths, now=NOW):
        return build.run_build(paths, crawl=False, online=False, site_url="./", now=lambda: now)

    def _online(self, paths, gunb, now="2099-01-01T00:00:00Z"):
        return build.run_build(paths, crawl=True, online=True, site_url="./", session=gunb,
                               geo_session=_NoNetwork(), now=lambda: now)

    def test_unchanged_gunb_files_rewrite_nothing(self, project, unchanged_crawl):
        """A live run whose conditional GETs all answer 304 reproduces the offline build byte for byte."""
        self._offline(project)
        before = {p: p.read_bytes() for p in [*project.site.rglob("*"), *project.rwdz_raw.iterdir()] if p.is_file()}
        gunb = FakeGunb({})
        result = self._online(project, gunb)
        assert sorted(gunb.calls) == sorted(f.url for f in rwdz_mod.FILES)   # one conditional GET per archive
        assert result.exit_code == build.EXIT_OK and result.written == [] and result.generated_at == NOW
        assert {p: p.read_bytes() for p in before} == before
        assert len(result.permits) == 16

    def test_format_drift_falls_back_to_the_committed_extracts(self, project, unchanged_crawl, tmp_path):
        self._offline(project)
        drifted = rwdz_fixture("rwdz-wnioski").replace(b"numer_gunb", b"numer_systemowy", 1)
        archives = {f.url: gunb_zip(f, drifted if f.file_id == "rwdz-wnioski" else rwdz_fixture(f.file_id),
                                    tmp_path / "new").read_bytes() for f in rwdz_mod.FILES}
        extracts = {p.name: p.read_bytes() for p in project.rwdz_raw.iterdir()}
        result = self._online(project, FakeGunb(archives, etag='"next-night"'))
        assert result.exit_code == build.EXIT_STALE and "nagłówek pliku GUNB się zmienił" in result.rwdz_error
        assert len(result.permits) == 16   # the committed snapshot, untouched
        assert {p.name: p.read_bytes() for p in project.rwdz_raw.iterdir()} == extracts
        assert "GUNB's RWDZ file format changed" in project.report.read_text(encoding="utf-8")

    def test_edited_committed_extract_is_fatal(self, project):
        path = project.rwdz_raw / "rwdz-zgloszenia-2022.csv"
        path.write_bytes(path.read_bytes().replace(b"Lubelska", b"Lubelsk4", 1))
        with pytest.raises(build.BuildError, match="SHA-256"):
            self._offline(project)
        assert build.main(["--offline", "--root", str(project.root), "-q"]) == build.EXIT_FATAL

    def test_skip_crawl_uses_the_committed_extracts(self, project):
        class Forbidden:
            def get(self, *a, **kw):
                raise AssertionError("--skip-crawl must not download anything")

        result = build.run_build(project, crawl=False, online=True, site_url="./", session=Forbidden(),
                                 geo_session=_NoNetwork(), now=lambda: NOW)
        assert result.exit_code == build.EXIT_OK and len(result.permits) == 16

    def test_project_without_rwdz_builds_without_permits(self, tmp_path):
        paths = make_project(tmp_path, rwdz=False)
        result = self._offline(paths)
        records_doc, sources_doc = _load(paths)
        assert result.permits == [] and list(records_doc["kinds"]) == ["wz", "cp", "ws"]
        assert records_doc["counts_by_kind"] == {"wz": 3, "cp": 0, "ws": 3} and "rwdz" not in records_doc["datasets"]
        assert records_doc["permit_scopes"] == {} == records_doc["permit_categories"]
        assert all(p["source"] != "rwdz" for p in sources_doc["pages"] if "source" in p)
        assert json.loads(paths.permits_json.read_text(encoding="utf-8"))["count"] == 0
        assert not paths.rwdz_mirror.exists() or not any(paths.rwdz_mirror.iterdir())

    def test_rwdz_can_be_left_out_explicitly(self, project):
        result = build.run_build(project, crawl=False, online=False, site_url="./", rwdz=False, now=lambda: NOW)
        records_doc, _ = _load(project)
        assert result.permits == [] and "pb" not in records_doc["counts_by_kind"]

    def test_stale_mirror_copies_are_removed(self, project):
        self._offline(project)
        stale = project.rwdz_mirror / "rwdz-old-file.csv"
        stale.write_text("x")
        keep = project.rwdz_mirror / "README.txt"   # not ours: never touched
        keep.write_text("x")
        self._offline(project)
        assert not stale.exists() and keep.exists()


# =============================================================================
# The REAL generated site data (skipped if absent or a frontend fixture)
# =============================================================================


REAL = build.Paths(ROOT)


@pytest.fixture(scope="module")
def real():
    try:
        records_doc, sources_doc = _load(REAL)
    except (OSError, ValueError):
        pytest.skip("site/data has not been built")
    if records_doc.get("fixture") or sources_doc.get("fixture"):
        pytest.skip("site/data holds fixture data")
    parcels = json.loads(REAL.parcels_geojson.read_text(encoding="utf-8"))
    try:
        permits_doc = json.loads(REAL.permits_json.read_text(encoding="utf-8"))
        permit_parcels = json.loads(REAL.parcels_permits_geojson.read_text(encoding="utf-8"))
    except FileNotFoundError:
        permits_doc, permit_parcels = {"count": 0, "records": []}, {"features": []}
    return records_doc, sources_doc, parcels, permits_doc, permit_parcels


class TestRealData:
    def test_records_are_consistent(self, real):
        records_doc, sources_doc, parcels, permits_doc, permit_parcels = real
        records, permits = records_doc["records"], permits_doc["records"]
        ids = [r["id"] for r in (*records, *permits)]
        assert records_doc["count"] == len(records) > 0 and permits_doc["count"] == len(permits)
        assert len(set(ids)) == len(ids) and all(re.fullmatch(r"[a-z0-9-]+", i) for i in ids)
        assert records_doc["generated_at"] == sources_doc["generated_at"]
        assert not permits or permits_doc["generated_at"] == records_doc["generated_at"]
        assert all(r["kind"] in build.KIND_ORDER for r in records) and all(r["kind"] in build.PERMIT_KINDS
                                                                          for r in permits)
        assert records_doc["counts_by_kind"] == {k: sum(r["kind"] == k for r in (*records, *permits))
                                                 for k in records_doc["kinds"]}
        files = {f["file_id"]: f for f in sources_doc["files"]}
        pages = {p["page_id"] for p in sources_doc["pages"]}
        parcel_ids = {f["id"] for f in parcels["features"]}
        permit_parcel_ids = {f["id"] for f in permit_parcels["features"]}
        assert not parcel_ids & permit_parcel_ids
        by_id = {r["id"]: r for r in (*records, *permits)}
        for r in by_id.values():
            assert r["kind"] in records_doc["kinds"] and r["sources"] and r["dataset"] in records_doc["datasets"]
            assert set(r["tags"]) <= set(records_doc["tags"])
            assert r["area"] is None or r["area"] in records_doc["areas"]
            for s in r["sources"]:
                assert s["file_id"] in files and s["page_id"] in pages and r["id"] in files[s["file_id"]]["record_ids"]
            assert set(r["geo"]["parcels_found"]) <= parcel_ids | permit_parcel_ids
            if r["kind"] in build.KIND_ORDER:   # the planning records' outlines load with records.json
                assert set(r["geo"]["parcels_found"]) <= parcel_ids
            assert (r["geo"]["lat"] is None) == (r["geo"]["method"] is None)
            for other in r["related"]:
                assert other != r["id"] and r["id"] in by_id[other]["related"]
        planning = {r["id"] for r in records}
        for f in parcels["features"]:
            assert f["properties"]["records"] and set(f["properties"]["records"]) <= set(by_id)
            assert set(f["properties"]["records"]) & planning
        for f in permit_parcels["features"]:
            assert f["properties"]["records"] and not set(f["properties"]["records"]) & planning

    def test_counts_reconcile(self, real):
        records_doc, sources_doc, _, permits_doc, _ = real
        workbook = [f for f in sources_doc["files"] if f.get("source") != "rwdz"]
        sources = sum(len(r["sources"]) for r in records_doc["records"])
        parsed = sum(f["parsed_count"] or 0 for f in workbook)
        assert parsed == sources  # every parsed row ends up as exactly one source of one record
        for f in sources_doc["files"]:
            if f.get("source") == "rwdz":   # one source per case, listing every register row of it
                rows = [n for r in permits_doc["records"] for s in r["sources"] if s["file_id"] == f["file_id"]
                        for n in s["rows"]]
                assert len(rows) == len(set(rows)) == (f["parsed_count"] or 0) <= (f["rows_total"] or 0)
        blocks = [b for p in sources_doc["pages"] for b in p["blocks"]]
        linked = {fid for b in blocks for fid in b["file_ids"]}
        for f in sources_doc["files"]:  # only BAiPP snapshots the source no longer links are unlinked
            assert f["file_id"] in linked or (f["source"] == "baipp" and f["removed_from_source_at"]), f["file_id"]
        linked_parsed = sum(f["parsed_count"] or 0 for f in sources_doc["files"] if f["file_id"] in linked)
        assert sum(b["parsed_count"] or 0 for b in blocks) == linked_parsed  # each file counted on exactly one page
        for b in blocks:
            if b["declared_count"] is not None and b["parsed_count"] is not None:
                assert b["count_mismatch"] == (b["declared_count"] != b["parsed_count"])

    def test_mirror_matches_manifest(self, real):
        _, sources_doc, _, _, _ = real
        for f in sources_doc["files"]:
            if f["archive_path"]:
                assert sha(REAL.site / f["archive_path"]) == f["sha256"]
            if f.get("archive_meta_path"):
                meta = json.loads((REAL.site / f["archive_meta_path"]).read_text(encoding="utf-8"))
                assert meta["sha256"] == f["sha256"] and meta["file_id"] == f["file_id"]

    def test_exports(self, real):
        records_doc, _, _, permits_doc, _ = real
        rows = _csv_rows(REAL.records_csv.read_text(encoding="utf-8"))
        assert rows[0] == export.CSV_COLUMNS and len(rows) == records_doc["count"] + 1
        assert [row[0] for row in rows[1:]] == [r["id"] for r in records_doc["records"]]
        if permits_doc["records"]:
            rows = _csv_rows(REAL.permits_csv.read_text(encoding="utf-8"))
            assert rows[0] == export.CSV_COLUMNS and [row[0] for row in rows[1:]] == [r["id"] for r in
                                                                                     permits_doc["records"]]
        feed = ET.fromstring(REAL.feed.read_bytes())
        entries = feed.findall(f"{ATOM}entry")
        assert 0 < len(entries) <= export.FEED_LIMIT
        assert not any("/wpis/pb-" in e.find(f"{ATOM}link[@rel='alternate']").get("href") for e in entries)
