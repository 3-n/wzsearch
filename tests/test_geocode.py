"""Offline tests for pipeline.geocode: parsing, caching, validation, locating.

Network calls are replaced by a fake session that serves recorded real
responses from GUGiK ULDK / UUG (captured 2026-10-23).
"""

import json
import os
from datetime import datetime, timedelta, timezone

import pytest
import requests

from pipeline import areas, geo
from pipeline import geocode as gc

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ----------------------------------------------------------- real responses

ULDK_OK = (
    "0\n146507_8.0124.46/4|SRID=4326;POLYGON((21.0742930848836 52.2230733832611,21.0742923823575 52.223003189656,"
    "21.074291835629 52.2229386582119,21.0745261360371 52.2229386003857,21.0747162388377 52.2229379409399,"
    "21.0747137010726 52.2231698255707,21.0742910546665 52.2231722493929,21.0742930848836 52.2230733832611))\n"
)
ULDK_MISS = (
    "-1 brak wyników\nbłędny format odpowiedzi XML, usługa zwróciła odpowiedźZbiorcza baza danych "
    "obsłużyła zapytanie. "
)
UUG_MINSKA_46 = json.loads(
    '{"type":"address","max results limit":15,"min accuracy limit":0.40000000000000002,"only exact numbers":1,'
    '"found objects":15,"returned objects":2,"results":{"1":{"city":"Warszawa","citypart":null,'
    '"street":"ulica Mi\\u0144ska","number":"46","teryt":"146501","simc":"0918123","ulic":"12989","code":"03-808",'
    '"jednostka":"{Polska,mazowieckie,Warszawa,Warszawa}","x":"21.06429797542","y":"52.2494393793207",'
    '"geometry_wkt":"POINT(21.06429797542 52.2494393793207)","accuracy":"0.76","city_accuracy":"1",'
    '"street_part_accuracy":"1","street_accuracy":"0.538462","id":1},"2":{"city":"Warszawa","citypart":null,'
    '"street":"ulica Pi\\u0144ska","number":"46","teryt":"146501","simc":"0918123","ulic":"16286","code":"03-523",'
    '"jednostka":"{Polska,mazowieckie,Warszawa,Warszawa}","x":"21.037823323174","y":"52.2736155108931",'
    '"geometry_wkt":"POINT(21.037823323174 52.2736155108931)","accuracy":"0.571429","city_accuracy":"1",'
    '"street_part_accuracy":"0.4","street_accuracy":"0.25","id":2}},"request time":0.0083660324414571129}'
)
UUG_MAROKANSKA = json.loads(
    '{"type":"street","found objects":1,"results":{"1":{"street":"ulica Maroka\\u0144ska","teryt":"146501",'
    '"simc":"0918123","ulic":"12388","city":"Warszawa","x":"21.0756456386407","y":"52.2232121792465",'
    '"geometry_wkt":"MULTILINESTRING((21.0786377888107 52.2240351436092,21.0786477348567 52.22402858208,'
    "21.0786747666389 52.2240052590677,21.0786951535095 52.2239776456769,21.0787095156451 52.2239527469186,"
    "21.0787221060222 52.2239118686526,21.0787236569619 52.2238447402111,21.0787195229195 52.2232828186904,"
    "21.0787244535188 52.2232002496083,21.0789045261045 52.2232017540793,21.0793832531401 52.2231973653853,"
    "21.0794904887945 52.2231979039556),(21.0711532659811 52.2232324810059,21.0721776191824 52.2232229494631,"
    "21.0730849315792 52.2232224815367,21.0734573779547 52.2232223229654,21.0745628663996 52.2232126939976,"
    "21.0748115526913 52.2232125484834,21.0756456386407 52.2232121792465,21.0767432191138 52.2232025790077,"
    "21.0776943393022 52.2231930292898,21.0784705016756 52.2231911415577,21.0785760237961 52.2231957588011,"
    '21.0787244535188 52.2232002496083))","accuracy":"0.647059","id":1,"jednostka":"{Warszawa,146501}"}},'
    '"request time":0.0015404502550760905}'
)
UUG_NONE = json.loads(
    '{"type":"address","max results limit":15,"min accuracy limit":0.40000000000000002,"only exact numbers":1,'
    '"found objects":null,"returned objects":0,"results":null,"request time":0.0029584169387817383}'
)
UUG_STREET_NONE = {"type": "street", "found objects": 0, "results": None}

# A rectangle roughly covering Praga-Południe (Pińska 46 on Targówek lies north of it).
DISTRICT = {
    "type": "Polygon",
    "coordinates": [[[21.03, 52.20], [21.13, 52.20], [21.13, 52.265], [21.03, 52.265], [21.03, 52.20]]],
}
WEST = {"type": "Polygon", "coordinates": [[[21.03, 52.20], [21.07, 52.20], [21.07, 52.265], [21.03, 52.265], [21.03, 52.20]]]}
EAST = {"type": "Polygon", "coordinates": [[[21.07, 52.20], [21.13, 52.20], [21.13, 52.265], [21.07, 52.265], [21.07, 52.20]]]}


def area_index():
    return areas.AreaIndex(DISTRICT, [("kamionek", "Kamionek", WEST), ("goclaw", "Gocław", EAST)])


def square_wkt(lon, lat, size=0.0005):
    return (
        f"SRID=4326;POLYGON(({lon} {lat},{lon + size} {lat},{lon + size} {lat + size},"
        f"{lon} {lat + size},{lon} {lat}))"
    )


# ------------------------------------------------------------ fake session


class FakeResponse:
    def __init__(self, status_code=200, text="", payload=None, headers=None):
        self.status_code = status_code
        self.text = text if payload is None else json.dumps(payload)
        self._payload = payload
        self.headers = headers or {}

    def json(self):
        if self._payload is None:
            return json.loads(self.text)
        return self._payload


class FakeSession:
    """Serves ULDK responses by parcel id and UUG responses by address string."""

    def __init__(self, parcels=None, addresses=None):
        self.parcels = parcels or {}
        self.addresses = addresses or {}
        self.calls = []

    def get(self, url, params=None, timeout=None):
        self.calls.append((url, dict(params or {})))
        if url == gc.ULDK_URL:
            text = self.parcels.get(params["id"], ULDK_MISS)
            if isinstance(text, Exception):
                raise text
            return FakeResponse(text=text)
        if url == gc.UUG_URL:
            addr = params["address"]
            payload = self.addresses.get(addr)
            if payload is None:
                payload = UUG_NONE if any(ch.isdigit() for ch in addr) else UUG_STREET_NONE
            return FakeResponse(payload=payload)
        raise AssertionError(f"unexpected URL {url}")

    def count(self, url):
        return sum(1 for u, _ in self.calls if u == url)


# =================================================================== ULDK


class TestUldkParsing:
    def test_real_hit(self):
        status, results = gc.parse_uldk_response(ULDK_OK)
        assert status == "ok"
        (pid, g), = results
        assert pid == "146507_8.0124.46/4"
        assert g["type"] == "Polygon"

    def test_real_miss(self):
        assert gc.parse_uldk_response(ULDK_MISS) == ("missing", [])

    @pytest.mark.parametrize("text", ["", "garbage", "-1 usługa powiatowa niedostępna", "0\n"])
    def test_errors(self, text):
        with pytest.raises(ValueError):
            gc.parse_uldk_response(text)

    def test_entry_from_hit(self):
        now = datetime(2026, 10, 23, tzinfo=timezone.utc)
        e = gc._uldk_entry(ULDK_OK, now)
        assert e["status"] == "ok" and e["fetched_at"] == "2026-10-23T00:00:00Z"
        assert e["area_m2"] == pytest.approx(744, rel=0.01)
        assert geo.point_in_polygon(e["centroid"], e["geometry"])
        assert all(c == [round(c[0], 6), round(c[1], 6)] for c in geo.all_coords(e["geometry"]))

    def test_multiple_rows_merge_to_multipolygon(self):
        text = "0\nA|" + square_wkt(21.0, 52.0) + "\nA|" + square_wkt(21.01, 52.0) + "\n"
        e = gc._uldk_entry(text, datetime.now(timezone.utc))
        assert e["geometry"]["type"] == "MultiPolygon"

    @pytest.mark.parametrize(
        "raw,expected",
        [(" 146507_8.0124.46/4 ", "146507_8.0124.46/4"), ("146507_8.0413.1", "146507_8.0413.1"),
         ("146507_8..46/4", None), (None, None), ("dz. 46/4", None)],
    )
    def test_normalize_parcel_id(self, raw, expected):
        assert gc.normalize_parcel_id(raw) == expected


NOW = datetime(2026, 10, 23, 12, 0, tzinfo=timezone.utc)


class TestLookupCache:
    def test_miss_then_hit_from_cache(self):
        sess = FakeSession(parcels={"146507_8.0124.46/4": ULDK_OK})
        cache = {}
        ids = ["146507_8.0124.46/4", "146507_8.0999.1"]
        r = gc.lookup_parcels(ids, cache, sess, now=NOW)
        assert r["146507_8.0124.46/4"]["status"] == "ok"
        assert r["146507_8.0999.1"]["status"] == "missing"
        assert r["146507_8.0999.1"]["geometry"] is None
        assert set(cache) == set(ids)
        assert cache["146507_8.0999.1"]["fetched_at"] == "2026-10-23T12:00:00Z"
        assert "geometry" not in cache["146507_8.0999.1"]  # results are copies
        assert sess.count(gc.ULDK_URL) == 2
        params = sess.calls[0][1]
        assert params["srid"] == "4326" and params["result"] == "id,geom_wkt"

        r2 = gc.lookup_parcels(ids + ids, cache, sess, now=NOW + timedelta(days=10))
        assert sess.count(gc.ULDK_URL) == 2  # both served from cache, duplicates collapsed
        assert r2["146507_8.0124.46/4"]["centroid"] == r["146507_8.0124.46/4"]["centroid"]

    def test_stale_miss_is_retried(self):
        sess = FakeSession(parcels={"146507_8.0999.1": ULDK_OK.replace("0124.46/4", "0999.1")})
        cache = {"146507_8.0999.1": {"status": "missing", "fetched_at": "2026-09-01T00:00:00Z"}}
        r = gc.lookup_parcels(["146507_8.0999.1"], cache, sess, now=NOW)  # 52 days old
        assert sess.count(gc.ULDK_URL) == 1
        assert r["146507_8.0999.1"]["status"] == "ok" and cache["146507_8.0999.1"]["status"] == "ok"

    def test_fresh_miss_kept_unless_refresh(self):
        cache = {"146507_8.0999.1": {"status": "missing", "fetched_at": "2026-10-13T00:00:00Z"}}
        sess = FakeSession()
        gc.lookup_parcels(["146507_8.0999.1"], cache, sess, now=NOW)
        assert sess.count(gc.ULDK_URL) == 0
        gc.lookup_parcels(["146507_8.0999.1"], cache, sess, now=NOW, refresh_misses=True)
        assert sess.count(gc.ULDK_URL) == 1
        assert cache["146507_8.0999.1"]["fetched_at"] == "2026-10-23T12:00:00Z"

    def test_hits_never_expire(self):
        cache = {"146507_8.0124.46/4": {"status": "ok", "geometry": None, "centroid": [21, 52], "fetched_at": "2020-01-01T00:00:00Z"}}
        sess = FakeSession()
        gc.lookup_parcels(["146507_8.0124.46/4"], cache, sess, now=NOW)
        assert sess.count(gc.ULDK_URL) == 0

    def test_errors_are_not_cached(self):
        sess = FakeSession(parcels={"146507_8.0124.46/4": requests.ConnectionError("boom")})
        cache = {}
        r = gc.lookup_parcels(["146507_8.0124.46/4", "146507_8.0101.1"], cache, sess, now=NOW)
        assert r["146507_8.0124.46/4"]["status"] == "error" and "boom" in r["146507_8.0124.46/4"]["error"]
        assert "146507_8.0124.46/4" not in cache and "146507_8.0101.1" in cache

    def test_offline_uses_cache_only(self):
        cache = {"146507_8.0999.1": {"status": "missing", "fetched_at": "2020-01-01T00:00:00Z"}}
        r = gc.lookup_parcels(["146507_8.0999.1", "146507_8.0101.1"], cache, None, online=False, now=NOW)
        assert r["146507_8.0999.1"]["status"] == "missing"  # stale, but offline: still used
        assert r["146507_8.0101.1"]["status"] == "error"

    def test_invalid_ids(self):
        r = gc.lookup_parcels(["dz. 12"], {}, FakeSession(), now=NOW)
        assert r["dz. 12"]["status"] == "error"


class TestCacheFiles:
    def test_save_is_sorted_and_atomic(self, tmp_path):
        path = tmp_path / "sub" / "uldk.json"
        gc.save_cache(str(path), {"b": {"z": 1, "a": 2}, "a": {"status": "missing"}})
        text = path.read_text(encoding="utf-8")
        assert text.index('"a"') < text.index('"b"')
        assert '{"a":2,"z":1}' in text
        assert text.count("\n") == 4  # one entry per line
        assert gc.load_cache(str(path)) == {"a": {"status": "missing"}, "b": {"a": 2, "z": 1}}
        assert [p.name for p in path.parent.iterdir()] == ["uldk.json"]  # no temp files left
        gc.save_cache(str(path), gc.load_cache(str(path)))
        assert path.read_text(encoding="utf-8") == text  # deterministic
        assert oct(path.stat().st_mode & 0o777) == "0o644"

    def test_load_missing_or_corrupt(self, tmp_path):
        assert gc.load_cache(str(tmp_path / "nope.json")) == {}
        bad = tmp_path / "bad.json"
        bad.write_text("{not json", encoding="utf-8")
        assert gc.load_cache(str(bad)) == {}


# ==================================================================== UUG


class TestUugParsing:
    def test_real_address_response(self):
        rtype, cands = gc.parse_uug_response(UUG_MINSKA_46)
        assert rtype == "address"
        assert [c["street"] for c in cands] == ["ulica Mińska", "ulica Pińska"]
        assert cands[0]["number"] == "46"
        assert cands[0]["lon"] == pytest.approx(21.06429797542)
        assert cands[0]["accuracy"] == pytest.approx(0.76)
        assert "geometry" not in cands[0]

    def test_real_street_response(self):
        rtype, (cand,) = gc.parse_uug_response(UUG_MAROKANSKA)
        assert rtype == "street" and cand["number"] is None
        assert cand["geometry"]["type"] == "MultiLineString"
        assert len(cand["geometry"]["coordinates"]) == 2

    def test_empty(self):
        assert gc.parse_uug_response(UUG_NONE) == ("address", [])
        with pytest.raises(ValueError):
            gc.parse_uug_response(["x"])


class TestMatching:
    @pytest.mark.parametrize(
        "query,candidate,ok",
        [
            ("Mińska", "ulica Mińska", True),
            ("Mińska", "ulica Pińska", False),
            ("minska", "ulica Mińska", True),
            ("ul. Mińska", "ulica Mińska", True),
            ("Gen. Fieldorfa Nila", "ulica gen. Augusta Emila Fieldorfa „Nila”", True),
            ("Jana Nowaka Jeziorańskiego", "ulica Jana Nowaka-Jeziorańskiego", True),
            ("J. Nowaka-Jeziorańskiego", "ulica Jana Nowaka-Jeziorańskiego", True),
            ("Jana Nowaka Jeziorańskiego", "ulica Jana Jeziorańskiego", False),
            ("Chłopickiego", "ulica gen. Józefa Chłopickiego", True),
            ("Żółkiewskiego", "ulica Stanisława Żółkiewskiego", True),
            ("Waszyngtona", "Aleja Jerzego Waszyngtona", True),
            ("al. Stanów Zjednoczonych", "Aleja Stanów Zjednoczonych", True),
            ("Kamionkowska Praga-Południe", "ulica Kamionkowska", True),
            ("Wał Miedzeszyński", "ulica Wał Miedzeszyński", True),
            ("Lubartowska", "ulica Lubieszowska", False),
            ("Kamionkowska", "ulica Kaniowska", False),
            ("", "ulica Mińska", False),
        ],
    )
    def test_street_matches(self, query, candidate, ok):
        assert gc.street_matches(query, candidate) is ok

    def test_number_matches(self):
        assert gc.number_matches("53a", "53A")
        assert gc.number_matches(" 46 ", "46")
        assert not gc.number_matches("46", "46/48")
        assert not gc.number_matches(None, "46")

    def test_query_variants(self):
        assert gc.street_query_variants("Gen. Fieldorfa Nila") == [
            "Gen. Fieldorfa Nila", "Fieldorfa Nila", "Fieldorfa-Nila", "Fieldorfa"
        ]
        v = gc.street_query_variants("Jana Nowaka Jeziorańskiego")
        assert "Jana Nowaka-Jeziorańskiego" in v
        assert gc.street_query_variants("ul. Mińska") == ["Mińska"]
        assert gc.street_query_variants("  ") == []

    @pytest.mark.parametrize(
        "text,street,number",
        [("Mińska 46", "Mińska", "46"), ("Serocka 53a", "Serocka", "53a"), ("Marokańska", "Marokańska", None),
         ("11 Listopada", "11 Listopada", None), ("11 Listopada 22", "11 Listopada", "22"),
         ("Kinowa 19/21", "Kinowa", "19/21"), ("Wał Miedzeszyński 646", "Wał Miedzeszyński", "646")],
    )
    def test_split_address(self, text, street, number):
        assert gc.split_address(text) == (street, number)


class TestGeocodeAddress:
    def test_exact_address_rejects_lookalike(self):
        sess = FakeSession(addresses={"Warszawa, Mińska 46": UUG_MINSKA_46})
        cache = {}
        r = gc.geocode_address("Mińska", "46", cache, sess, DISTRICT)
        assert r["method"] == "address" and r["matched"] == "ulica Mińska 46"
        assert (r["lon"], r["lat"]) == pytest.approx((21.06429797542, 52.2494393793207))
        assert "Warszawa, Mińska 46" in cache
        # second call: cached
        gc.geocode_address("Mińska", "46", cache, sess, DISTRICT)
        assert sess.count(gc.UUG_URL) == 1

    def test_wrong_district_rejected(self):
        only_pinska = json.loads(json.dumps(UUG_MINSKA_46))
        only_pinska["results"] = {"1": only_pinska["results"]["2"]}
        sess = FakeSession(addresses={"Warszawa, Pińska 46": only_pinska})
        stats = {}
        # Correct name, but Pińska 46 is on Targówek, outside the district polygon.
        assert gc.geocode_address("Pińska", "46", {}, sess, DISTRICT, stats=stats) is None
        assert stats["uug_rejected_outside"] == 1
        # Without a district polygon the same hit is accepted.
        assert gc.geocode_address("Pińska", "46", {}, sess, None)["method"] == "address"

    def test_name_mismatch_falls_back_to_street(self):
        only_pinska = json.loads(json.dumps(UUG_MINSKA_46))
        only_pinska["results"] = {"1": only_pinska["results"]["2"]}
        street = json.loads(json.dumps(UUG_MAROKANSKA))
        street["results"]["1"]["street"] = "ulica Mińska"
        sess = FakeSession(addresses={"Warszawa, Mińska 46": only_pinska, "Warszawa, Mińska": street})
        r = gc.geocode_address("Mińska", "46", {}, sess, DISTRICT)
        assert r["method"] == "street" and r["note"] == gc.NOTE_STREET

    def test_street_only(self):
        sess = FakeSession(addresses={"Warszawa, Marokańska": UUG_MAROKANSKA})
        r = gc.geocode_address("Marokańska", None, {}, sess, DISTRICT)
        assert r["method"] == "street" and r["matched"] == "ulica Marokańska"
        assert (r["lon"], r["lat"]) == pytest.approx((21.0756456386407, 52.2232121792465))

    def test_street_point_clipped_to_district(self):
        # UUG's point lies east of a district that only contains the western part of the street.
        small = {"type": "Polygon", "coordinates": [[[21.070, 52.22], [21.073, 52.22], [21.073, 52.226], [21.070, 52.226], [21.070, 52.22]]]}
        sess = FakeSession(addresses={"Warszawa, Marokańska": UUG_MAROKANSKA})
        r = gc.geocode_address("Marokańska", None, {}, sess, small)
        assert r is not None and r["method"] == "street"
        assert geo.point_in_polygon([r["lon"], r["lat"]], small)
        far = {"type": "Polygon", "coordinates": [[[20.0, 50.0], [20.1, 50.0], [20.1, 50.1], [20.0, 50.0]]]}
        assert gc.geocode_address("Marokańska", None, {}, sess, far) is None

    def test_house_number_base_fallback(self):
        payload = json.loads(json.dumps(UUG_MINSKA_46))
        payload["results"] = {"1": payload["results"]["1"]}
        sess = FakeSession(addresses={"Warszawa, Mińska 46": payload})
        r = gc.geocode_address("Mińska", "46A", {}, sess, DISTRICT)
        assert r["method"] == "address" and "budynek nr 46" in r["note"]

    def test_spelling_variant_used_for_number(self):
        street = json.loads(json.dumps(UUG_MAROKANSKA))
        street["results"]["1"]["street"] = "ulica Jana Nowaka-Jeziorańskiego"
        addr = json.loads(json.dumps(UUG_MINSKA_46))
        addr["results"] = {"1": dict(addr["results"]["1"], street="ulica Jana Nowaka-Jeziorańskiego", number="7")}
        sess = FakeSession(addresses={
            "Warszawa, Jana Nowaka-Jeziorańskiego": street,
            "Warszawa, Jana Nowaka-Jeziorańskiego 7": addr,
        })
        r = gc.geocode_address("Jana Nowaka Jeziorańskiego", "7", {}, sess, DISTRICT)
        assert r["method"] == "address" and r["query"] == "Warszawa, Jana Nowaka-Jeziorańskiego 7"

    def test_offline_without_cache(self):
        assert gc.geocode_address("Mińska", "46", {}, None, DISTRICT, online=False) is None

    def test_errors_not_cached(self):
        class Boom(FakeSession):
            def get(self, url, params=None, timeout=None):
                raise requests.ConnectionError("down")

        cache, stats = {}, {}
        assert gc.geocode_address("Mińska", "46", cache, Boom(), DISTRICT, stats=stats) is None
        assert cache == {} and stats["uug_errors"] >= 1

    def test_corner_address_crossing(self):
        a = {"type": "street", "results": {"1": {"street": "ulica Aaa", "x": "21.08", "y": "52.23", "accuracy": "0.7",
                                                  "geometry_wkt": "LINESTRING(21.07 52.23,21.09 52.23)"}}}
        b = {"type": "street", "results": {"1": {"street": "ulica Bbb", "x": "21.085", "y": "52.235", "accuracy": "0.7",
                                                  "geometry_wkt": "LINESTRING(21.085 52.225,21.085 52.24)"}}}
        sess = FakeSession(addresses={"Warszawa, Aaa": a, "Warszawa, Bbb": b})
        r = gc.geocode_record_address({"street": "Aaa / Bbb", "number": None}, {}, sess, DISTRICT)
        assert r["note"] == gc.NOTE_CROSSING
        assert (r["lon"], r["lat"]) == pytest.approx((21.085, 52.23), abs=1e-6)


# ============================================================ locate_records


def _rec(rid, pids=(), street=None, number=None):
    return {
        "id": rid,
        "parcels": [{"id": p, "number": p.split(".", 2)[-1], "obreb": None, "partial": False} for p in pids],
        "address": {"street": street, "number": number, "raw": "", "display": street},
    }


class TestLocateRecords:
    def _session(self):
        return FakeSession(
            parcels={
                "146507_8.0124.46/4": ULDK_OK,
                "146507_8.0101.1": "0\n146507_8.0101.1|" + square_wkt(21.050, 52.240),
                "146507_8.0101.2": "0\n146507_8.0101.2|" + square_wkt(21.0506, 52.240),
                "146507_8.0101.3": "0\n146507_8.0101.3|" + square_wkt(21.0512, 52.240),
                "146507_8.0601.9": "0\n146507_8.0601.9|" + square_wkt(21.100, 52.240),  # ~3.4 km east
                "146507_8.0701.1": "0\n146507_8.0701.1|" + square_wkt(20.90, 52.10),  # far outside
            },
            addresses={"Warszawa, Mińska 46": UUG_MINSKA_46, "Warszawa, Marokańska": UUG_MAROKANSKA},
        )

    def _records(self):
        return [
            _rec("wz-1", ["146507_8.0124.46/4"], "Marokańska"),
            _rec("wz-2", ["146507_8.0101.1", "146507_8.0101.2", "146507_8.0601.9", "146507_8.0101.3"]),
            _rec("wz-3", ["146507_8.0999.1"], "Mińska", "46"),
            _rec("wz-4", [], "Marokańska"),
            _rec("wz-5"),
            _rec("wz-6", ["146507_8.0701.1"]),
            _rec("wz-7", ["146507_8.0124.46/4", "146507_8.0999.2"]),
        ]

    def test_end_to_end(self, tmp_path):
        sess = self._session()
        recs = self._records()
        logs = []
        out = gc.locate_records(recs, str(tmp_path), online=True, log=logs.append, session=sess, area_index=area_index())
        by = {r["id"]: r for r in recs}

        g1 = by["wz-1"]["geo"]
        assert g1["method"] == "parcel" and g1["parcels_found"] == ["146507_8.0124.46/4"]
        assert g1["note"] is None and g1["bbox"][0] < g1["lon"] < g1["bbox"][2]
        assert by["wz-1"]["area"] == "goclaw"

        g2 = by["wz-2"]["geo"]
        assert g2["method"] == "parcel" and len(g2["parcels_found"]) == 4
        assert "ponad 1 km" in g2["note"] and "(3 z 4)" in g2["note"]
        assert g2["lon"] == pytest.approx(21.05085, abs=1e-4)  # centre of the 3 adjacent squares
        assert g2["bbox"][2] > 21.1  # bbox still covers all found parcels
        assert by["wz-2"]["area"] == "kamionek"

        g3 = by["wz-3"]["geo"]
        assert g3["method"] == "address" and g3["parcels_found"] == [] and g3["bbox"] is None
        assert "nie znaleziono w ewidencji gruntów (ULDK)" in g3["note"]
        assert (g3["lon"], g3["lat"]) == pytest.approx((21.06429797542, 52.2494393793207))

        g4 = by["wz-4"]["geo"]
        assert g4["method"] == "street" and g4["note"] == gc.NOTE_STREET

        g5 = by["wz-5"]["geo"]
        assert g5 == {"lat": None, "lon": None, "method": None, "parcels_found": [], "bbox": None,
                      "note": "brak działek i adresu w źródle"}
        assert by["wz-5"]["area"] is None

        g6 = by["wz-6"]["geo"]
        assert g6["method"] is None and "poza granicami dzielnicy" in g6["note"]

        g7 = by["wz-7"]["geo"]
        assert g7["method"] == "parcel" and g7["note"] == "w ewidencji gruntów (ULDK) znaleziono 1 z 2 działek"

        st = out["stats"]
        assert st["methods"] == {"parcel": 3, "address": 1, "street": 1, "none": 2}
        assert st["parcels_unique"] == 8 and st["parcels_ok"] == 6 and st["parcels_missing"] == 2
        assert st["outside_district_discarded"] == 1 and st["records_spread_parcels"] == 1
        assert any("wz-6" in w for w in st["warnings"])

        fc = out["parcels_geojson"]
        ids = [f["id"] for f in fc["features"]]
        assert ids == sorted(ids) and "146507_8.0701.1" not in ids and len(ids) == 5
        f = next(f for f in fc["features"] if f["id"] == "146507_8.0124.46/4")
        assert f["properties"] == {"id": "146507_8.0124.46/4", "obreb": "3-01-24", "number": "46/4",
                                   "records": ["wz-1", "wz-7"]}

        # Caches were written; an offline rerun reproduces everything without requests.
        assert (tmp_path / "uldk.json").exists() and (tmp_path / "uug.json").exists()
        recs2 = self._records()
        n_calls = len(sess.calls)
        out2 = gc.locate_records(recs2, str(tmp_path), online=False, log=lambda *_: None, area_index=area_index())
        assert len(sess.calls) == n_calls
        assert [r["geo"] for r in recs2] == [r["geo"] for r in recs]
        assert out2["parcels_geojson"] == fc

    def test_without_district(self, tmp_path):
        recs = [_rec("wz-1", ["146507_8.0124.46/4"])]
        out = gc.locate_records(recs, str(tmp_path), log=lambda *_: None, session=self._session(),
                                area_index=areas.AreaIndex(None, []))
        assert recs[0]["geo"]["method"] == "parcel" and recs[0]["area"] is None
        assert any("district polygon unavailable" in w for w in out["stats"]["warnings"])

    def test_cluster_parcels(self):
        items = [{"bbox": [21.0, 52.0, 21.001, 52.001], "area_m2": 10},
                 {"bbox": [21.05, 52.0, 21.051, 52.001], "area_m2": 1000},
                 {"bbox": [21.0015, 52.0, 21.002, 52.001], "area_m2": 10}]
        clusters = gc.cluster_parcels(items)
        assert [len(c) for c in clusters] == [2, 1]


# ========================================================== PoliteSession


class _Raw:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.headers = {}
        self.calls = 0

    def request(self, method, url, **kw):
        self.calls += 1
        o = self.outcomes.pop(0)
        if isinstance(o, Exception):
            raise o
        return FakeResponse(status_code=o, text="ok")


class TestPoliteSession:
    def test_retries_then_succeeds(self):
        raw = _Raw([503, requests.ConnectionError("x"), 200])
        s = gc.PoliteSession(max_rps=1000, backoff_s=0, session=raw)
        assert s.get("https://example.invalid/").status_code == 200
        assert raw.calls == 3
        assert "wzSearch" in raw.headers["User-Agent"]

    def test_gives_up(self):
        raw = _Raw([500, 500, 500])
        s = gc.PoliteSession(max_rps=1000, retries=2, backoff_s=0, session=raw)
        with pytest.raises(requests.HTTPError):
            s.get("https://example.invalid/")

    def test_non_retryable_status_returned(self):
        raw = _Raw([404])
        s = gc.PoliteSession(max_rps=1000, backoff_s=0, session=raw)
        assert s.get("https://example.invalid/").status_code == 404

    def test_rate_limit(self):
        import time

        raw = _Raw([200] * 5)
        s = gc.PoliteSession(max_rps=20, backoff_s=0, session=raw)
        t0 = time.monotonic()
        for _ in range(5):
            s.get("https://example.invalid/")
        assert time.monotonic() - t0 >= 4 / 20 - 0.01


# ================================================== source-text robustness


class TestSourceQuirks:
    @pytest.mark.parametrize(
        "raw,clean",
        [
            ("ul. Mińska", "Mińska"),
            ("gen.Fieldorfa „Nila”", "gen. Fieldorfa Nila"),
            ("ul. Jana Nowaka -Jeziorańskiego", "Jana Nowaka-Jeziorańskiego"),
            ("Wiatraczna (Kozia Górka)", "Wiatraczna"),
            ("rejon ul. Drwęckiej", "Drwęcka"),
            ("w rejonie ulicy Chodakowskiej", "Chodakowska"),
            ("Kamionkowska Praga-Południe", "Kamionkowska"),
            ("al.Stanów Zjednoczonych", "al. Stanów Zjednoczonych"),
            ("Bitwy Warszawskiej 1920 r.", "Bitwy Warszawskiej 1920 r."),  # genitive kept outside "rejon"
        ],
    )
    def test_clean_street(self, raw, clean):
        assert gc.clean_street(raw) == clean

    @pytest.mark.parametrize(
        "query,candidate,kind",
        [
            ("Borlemowska", "ulica Boremlowska", "fuzzy"),  # transposition typo in a 2024 file
            ("Chdakowska", "ulica Chodakowska", "fuzzy"),
            ("Feildorfa Nila", "ulica gen. Augusta Emila Fieldorfa „Nila”", "fuzzy"),
            ("Mińska", "ulica Mińska", "exact"),
            ("Mińska", "ulica Pińska", None),
            ("Grochowska", "ulica Grochowa", None),
            ("Sygietyńska", "ulica Tadeusza Sygietyńskiego", None),
        ],
    )
    def test_fuzzy_kind(self, query, candidate, kind):
        assert gc.street_match_kind(query, candidate) == kind
        assert gc.street_matches(query, candidate) is (kind == "exact")

    def test_split_streets(self):
        assert gc._split_streets("Mińska 20,Głucha", None) == [("Mińska", "20"), ("Głucha", None)]
        assert gc._split_streets("Drwęcka i Siennicka", "5") == [("Drwęcka", "5"), ("Siennicka", None)]
        assert gc._split_streets("Gen. Fieldorfa Nila / Jana Nowaka-Jeziorańskiego", None) == [
            ("Gen. Fieldorfa Nila", None), ("Jana Nowaka-Jeziorańskiego", None)]
        assert gc._split_streets("Serocka 21,23", None) == [("Serocka", "21")]

    def test_fuzzy_address_gets_note(self):
        payload = json.loads(json.dumps(UUG_MINSKA_46))
        payload["results"] = {"1": dict(payload["results"]["1"], street="ulica Boremlowska", number="49")}
        sess = FakeSession(addresses={"Warszawa, Borlemowska 49": payload})
        r = gc.geocode_address("Borlemowska", "49", {}, sess, DISTRICT)
        assert r["method"] == "address" and "w przybliżeniu (ulica Boremlowska)" in r["note"]

    def test_invalid_query_cached_as_miss(self):
        class Blad(FakeSession):
            def get(self, url, params=None, timeout=None):
                self.calls.append((url, params))
                return FakeResponse(text="Blad zapytania.")

        cache, stats = {}, {}
        sess = Blad()
        assert gc.uug_query("Warszawa, x „ y“41A", cache, sess, stats=stats)["status"] == "missing"
        assert cache["Warszawa, x „ y“41A"]["type"] == "invalid-query"
        gc.uug_query("Warszawa, x „ y“41A", cache, sess, stats=stats)
        assert len(sess.calls) == 1 and "uug_errors" not in stats

    def test_vicinity_and_genitive_list(self):
        rybna = json.loads(json.dumps(UUG_MAROKANSKA))
        rybna["results"]["1"]["street"] = "ulica Rybna"
        sess = FakeSession(addresses={"Warszawa, Rybna": rybna})
        r = gc.geocode_record_address({"street": "w rejonie ulic Chodakowskiej/ Rybnej", "number": None}, {}, sess, DISTRICT)
        assert r["method"] == "street" and r["matched"] == "ulica Rybna"

    def test_cross_check_flags_distant_address(self, tmp_path):
        # Parcel ~1.9 km west of Mińska 46 → address/parcel conflict note, parcel point kept.
        sess = FakeSession(
            parcels={"146507_8.0101.1": "0\n146507_8.0101.1|" + square_wkt(21.036, 52.249)},
            addresses={"Warszawa, Mińska 46": UUG_MINSKA_46},
        )
        recs = [_rec("wz-1", ["146507_8.0101.1"], "Mińska", "46"), _rec("wz-2", ["146507_8.0101.1"], "Mińska", None)]
        out = gc.locate_records(recs, str(tmp_path), log=lambda *_: None, session=sess, area_index=area_index())
        g = recs[0]["geo"]
        assert g["method"] == "parcel" and g["lon"] == pytest.approx(21.03625, abs=1e-5)
        assert g["note"].startswith("adres Mińska leży ok. 1") and "m od wskazanych działek" in g["note"]
        assert recs[1]["geo"]["note"] is None  # no house number → no cross-check
        assert out["stats"]["address_parcel_conflicts"] == 1


# ================================================= address vs parcels: wrong precinct in the source


def uug_address(street, number, lon, lat):
    return {"type": "address", "results": {"1": {
        "city": "Warszawa", "street": f"ulica {street}", "number": number, "x": str(lon), "y": str(lat),
        "geometry_wkt": f"POINT({lon} {lat})", "accuracy": "1", "simc": "0918123", "ulic": "1"}}}


class XYSession(FakeSession):
    """FakeSession + ULDK GetParcelByXY (by "lon,lat" with 6 decimals)."""

    def __init__(self, parcels=None, addresses=None, xy=None):
        super().__init__(parcels, addresses)
        self.xy = xy or {}

    def get(self, url, params=None, timeout=None):
        if url == gc.ULDK_URL and (params or {}).get("request") == "GetParcelByXY":
            self.calls.append((url, dict(params)))
            lon, lat, _srid = params["xy"].split(",")
            return FakeResponse(text=self.xy.get(f"{lon},{lat}", ULDK_MISS))
        return super().get(url, params, timeout)


def parcel_text(pid, lon, lat):
    return f"0\n{pid}|{square_wkt(lon, lat)}"


ADDR = (21.0829, 52.2316)          # the address point; the stated parcels lie ~600 m east of it
FAR = (21.0919, 52.2316)


class TestAddressRevealsWrongPrecinct:
    def _locate(self, tmp_path, recs, **session):
        sess = XYSession(**session)
        out = gc.locate_records(recs, str(tmp_path), log=lambda *_: None, session=sess, area_index=area_index())
        return sess, out["stats"]

    def test_same_number_in_another_precinct_rewrites_the_parcels(self, tmp_path):
        # "Busolowa 16A, 35, 36-cz 3-06-03": 0603.35 exists far away, the parcel under the address is 0526.35
        rec = _rec("wz-2023-23", ["146507_8.0603.35", "146507_8.0603.36"], "Busolowa", "16A")
        rec["parcels"][0]["obreb"] = rec["parcels"][1]["obreb"] = "3-06-03"
        rec["address"]["display"], rec["warnings"] = "Busolowa 16A", []
        sess, stats = self._locate(
            tmp_path, [rec],
            parcels={"146507_8.0603.35": parcel_text("146507_8.0603.35", *FAR),
                     "146507_8.0526.36": parcel_text("146507_8.0526.36", ADDR[0] + 0.0005, ADDR[1])},
            addresses={"Warszawa, Busolowa 16A": uug_address("Busolowa", "16A", *ADDR)},
            xy={"21.082900,52.231600": parcel_text("146507_8.0526.35", ADDR[0] - 0.0002, ADDR[1] - 0.0002)})
        g = rec["geo"]
        assert [p["id"] for p in rec["parcels"]] == ["146507_8.0526.35", "146507_8.0526.36"]
        assert [p["obreb"] for p in rec["parcels"]] == ["3-05-26", "3-05-26"]
        assert g["method"] == "parcel" and g["parcels_found"] == ["146507_8.0526.35", "146507_8.0526.36"]
        assert abs(g["lon"] - ADDR[0]) < 0.001 and "conflict" not in g
        assert g["note"] is None or "leży ok." not in g["note"]
        assert rec["warnings"] == ["obręb w źródle (3-06-03) prawdopodobnie błędny – działka 35 pod adresem Busolowa "
                                   "16A leży w obrębie 3-05-26"]
        assert stats["obreb_corrected_by_address"] == 1 and stats["address_parcel_conflicts"] == 0
        # cached: an offline rerun of the same source rows gives the same result without requests
        again = _rec("wz-2023-23", ["146507_8.0603.35", "146507_8.0603.36"], "Busolowa", "16A")
        n = len(sess.calls)
        gc.locate_records([again], str(tmp_path), online=False, log=lambda *_: None, area_index=area_index())
        assert again["geo"] == g and [p["id"] for p in again["parcels"]] == [p["id"] for p in rec["parcels"]]
        assert len(sess.calls) == n

    def test_no_number_match_in_another_precinct_flags_the_conflict(self, tmp_path):
        rec = _rec("pb-1", ["146507_8.0101.1"], "Mińska", "46")
        lon, lat = 21.06429797542, 52.2494393793207
        _sess, stats = self._locate(
            tmp_path, [rec],
            parcels={"146507_8.0101.1": parcel_text("146507_8.0101.1", 21.036, 52.249)},
            addresses={"Warszawa, Mińska 46": UUG_MINSKA_46},
            xy={f"{lon:.6f},{lat:.6f}": parcel_text("146507_8.0605.99", lon, lat)})
        g = rec["geo"]
        assert g["method"] == "parcel" and g["conflict"] is True and "leży ok." in g["note"]
        assert [p["id"] for p in rec["parcels"]] == ["146507_8.0101.1"]
        assert stats["address_parcel_conflicts"] == stats["address_parcel_conflicts_flagged"] == 1

    def test_address_on_a_stated_precinct_is_no_conflict_flag(self, tmp_path):
        # a large site ("Ostrobramska 75"): the address lies on another parcel of the same precinct
        rec = _rec("pb-2", ["146507_8.0524.7"], "Ostrobramska", "75")
        _sess, stats = self._locate(
            tmp_path, [rec],
            parcels={"146507_8.0524.7": parcel_text("146507_8.0524.7", *FAR)},
            addresses={"Warszawa, Ostrobramska 75": uug_address("Ostrobramska", "75", *ADDR)},
            xy={"21.082900,52.231600": parcel_text("146507_8.0524.50", *ADDR)})
        g = rec["geo"]
        assert g["method"] == "parcel" and "conflict" not in g and "leży ok." in g["note"]
        assert stats["address_parcel_conflicts"] == 1 and stats["address_parcel_conflicts_flagged"] == 0

    def test_unknown_parcels_located_by_the_parcel_under_the_address(self, tmp_path):
        # "Chłodnicza 11, 88 3-06-07": 0607.88 does not exist; the address lies on 0405.88
        rec = _rec("ws-6730-2024-2", ["146507_8.0607.88"], "Chłodnicza", "11")
        _sess, stats = self._locate(
            tmp_path, [rec],
            addresses={"Warszawa, Chłodnicza 11": uug_address("Chłodnicza", "11", *ADDR)},
            xy={"21.082900,52.231600": parcel_text("146507_8.0405.88", ADDR[0] - 0.0002, ADDR[1] - 0.0002)})
        g = rec["geo"]
        assert g["method"] == "parcel" and g["parcels_found"] == ["146507_8.0405.88"]
        assert rec["parcels"][0]["id"] == "146507_8.0405.88" and rec["parcels"][0]["obreb"] == "3-04-05"
        assert "scalone" not in (g["note"] or "")
        assert any("obręb w źródle (3-06-07) prawdopodobnie błędny – działka 88" in w for w in rec["warnings"])
        assert stats["obreb_corrected_by_address"] == 1

    def test_only_the_base_number_matches_gives_a_hint(self, tmp_path):
        rec = _rec("pb-3", ["146507_8.0306.43/1"], "Chodakowska", "19/31")
        self._locate(
            tmp_path, [rec],
            addresses={"Warszawa, Chodakowska 19/31": uug_address("Chodakowska", "19/31", *ADDR)},
            xy={"21.082900,52.231600": parcel_text("146507_8.0206.43/7", *ADDR)})
        g = rec["geo"]
        assert g["method"] == "address" and rec["parcels"][0]["id"] == "146507_8.0306.43/1"
        assert "pod adresem leży działka 43/7 obr. 3-02-06 – obręb w źródle prawdopodobnie błędny" in g["note"]
        assert "scalone" not in g["note"]

    def test_part_of_a_subdivided_parcel_under_the_address(self, tmp_path):
        # "Jarocińska 15, 137 3-04-09": 0409.137 exists far away; under the address 0509.137/2, and 0509.137 is gone
        rec = _rec("pb-4", ["146507_8.0409.137"], "Jarocińska", "15")
        rec["address"]["display"] = "Jarocińska 15"
        self._locate(
            tmp_path, [rec],
            parcels={"146507_8.0409.137": parcel_text("146507_8.0409.137", *FAR)},
            addresses={"Warszawa, Jarocińska 15": uug_address("Jarocińska", "15", *ADDR)},
            xy={"21.082900,52.231600": parcel_text("146507_8.0509.137/2", *ADDR)})
        g = rec["geo"]
        assert rec["parcels"][0]["id"] == "146507_8.0509.137"
        assert g["method"] == "parcel" and g["parcels_found"] == ["146507_8.0509.137/2"]
        assert "została podzielona) – przyjęto jej część leżącą pod adresem: 137/2" in g["note"]
        assert any("działka 137/2 (część działki 137) pod adresem Jarocińska 15 leży w obrębie 3-05-09" in w
                   for w in rec["warnings"])


def test_incomplete_number_note(tmp_path):
    rec = _rec("wz-am-2025-42", ["146507_8.0606.12"])
    rec["parcels"][0]["incomplete"] = True
    sess = FakeSession(parcels={"146507_8.0606.12/1": parcel_text("146507_8.0606.12/1", *ADDR)})
    cache = {}
    gc.lookup_parcels(["146507_8.0606.12/1"], cache, sess)
    gc.save_cache(str(tmp_path / "uldk.json"), cache)
    other = _rec("wz-am-2025-1", ["146507_8.0606.12/1"])       # stand-ins are parcels other records name
    gc.locate_records([rec, other], str(tmp_path), log=lambda *_: None, session=sess, area_index=area_index())
    assert rec["geo"]["method"] == "parcel"
    assert "numer działki w źródle niepełny („12/”, obręb 3-06-06)" in rec["geo"]["note"]
    assert "została podzielona" not in rec["geo"]["note"]


def test_parcel_at_point_and_regions_are_cached(tmp_path):
    sess = XYSession(xy={"21.082900,52.231600": parcel_text("146507_8.0526.35", *ADDR)})
    cache = {}
    hit = gc.parcel_at_point(21.0829, 52.2316, cache, sess)
    assert hit["status"] == "ok" and hit["id"] == "146507_8.0526.35"
    assert cache["146507_8.0526.35"]["status"] == "ok"                      # the geometry, like GetParcelById
    assert gc.parcel_at_point(21.0829, 52.2316, cache, None, online=False)["id"] == "146507_8.0526.35"
    assert gc.parcel_at_point(21.1, 52.2, {}, None, online=False)["status"] == "error"

    class Regions(FakeSession):
        def get(self, url, params=None, timeout=None):
            self.calls.append((url, dict(params)))
            return FakeResponse(text="0\n146508_8.1406|\n" if params["id"] == "146508_8.1406" else "-1 brak wyników\n")

    regions = Regions()
    got = gc.lookup_regions(["146508_8.1406", "146507_8.1406"], cache, regions)
    assert {k: v["status"] for k, v in got.items()} == {"146508_8.1406": "ok", "146507_8.1406": "missing"}
    assert "region:146508_8.1406" in cache
    gc.lookup_regions(["146508_8.1406"], cache, regions)
    assert len(regions.calls) == 2


def region_text(rid, lon0, lat0, lon1, lat1):
    return (f"0\n{rid}|SRID=4326;POLYGON(({lon0} {lat0},{lon1} {lat0},{lon1} {lat1},{lon0} {lat1},{lon0} {lat0}))\n")


def test_street_fallback_is_narrowed_to_the_stated_precinct(tmp_path):
    street = {"type": "street", "results": {"1": {"street": "ulica Testowa", "x": "21.06", "y": "52.23",
                                                  "accuracy": "0.7",
                                                  "geometry_wkt": "LINESTRING(21.05 52.23,21.11 52.23)"}}}
    sess = FakeSession(parcels={"146507_8.0602": region_text("146507_8.0602", 21.09, 52.225, 21.11, 52.235),
                                "146507_8.0603": region_text("146507_8.0603", 21.09, 52.25, 21.11, 52.26)},
                       addresses={"Warszawa, Testowa": street})
    inside = _rec("pb-1", ["146507_8.0602.5"], "Testowa")        # the parcel is gone; its precinct is known
    apart = _rec("pb-2", ["146507_8.0603.5"], "Testowa")         # the street does not cross this precinct
    plain = _rec("pb-3", [], "Testowa")
    out = gc.locate_records([inside, apart, plain], str(tmp_path), log=lambda *_: None, session=sess,
                            area_index=area_index())
    g = inside["geo"]
    assert g["method"] == "street" and 21.09 < g["lon"] < 21.11 and g["lat"] == pytest.approx(52.23)
    assert "lokalizacja przybliżona – ulica w obrębie 3-06-02" in g["note"]
    assert 600 < g["uncertainty_m"] < 750                         # half of the 1.4 km stretch in the precinct
    assert inside["area"] == "goclaw"
    g2 = apart["geo"]
    assert (g2["lon"], g2["lat"]) == (21.06, 52.23)               # UUG's own street point stays
    assert "ulica nie przechodzi przez obręb z rejestru (3-06-03)" in g2["note"] and g2["uncertainty_m"] > 3000
    assert plain["geo"]["note"] == gc.NOTE_STREET and plain["geo"]["uncertainty_m"] > 3000
    assert out["stats"]["street_clipped_to_precinct"] == 1
    # the precinct polygons are cached: offline, the same points
    again = _rec("pb-1", ["146507_8.0602.5"], "Testowa")
    gc.locate_records([again], str(tmp_path), online=False, log=lambda *_: None, area_index=area_index())
    assert again["geo"] == g


def test_parcels_learnt_under_an_address_never_move_other_records(tmp_path):
    # A's address lies on 0203.3/1 (GetParcelByXY caches it); B names the subdivided 0203.3, which no record names
    # a part of: B must be located the same way in the online run and in an offline rerun (no stand-in from A)
    def records():
        a = _rec("pb-a", ["146507_8.0101.1"], "Testowa", "1")
        b = _rec("pb-b", ["146507_8.0203.3"])
        return [a, b]
    sess = XYSession(parcels={"146507_8.0101.1": parcel_text("146507_8.0101.1", *FAR)},
                     addresses={"Warszawa, Testowa 1": uug_address("Testowa", "1", *ADDR)},
                     xy={"21.082900,52.231600": parcel_text("146507_8.0203.3/1", *ADDR)})
    first = records()
    gc.locate_records(first, str(tmp_path), log=lambda *_: None, session=sess, area_index=area_index())
    second = records()
    gc.locate_records(second, str(tmp_path), online=False, log=lambda *_: None, area_index=area_index())
    assert [r["geo"] for r in second] == [r["geo"] for r in first]
    assert first[1]["geo"]["method"] is None


def test_border_street_point_takes_the_neighbourhood_of_its_precinct():
    # Kamionek | Gocław border at lon 21.07; the precinct lies wholly in Gocław
    precinct = {"type": "Polygon", "coordinates": [[[21.07, 52.22], [21.09, 52.22], [21.09, 52.24], [21.07, 52.24],
                                                    [21.07, 52.22]]]}
    idx = area_index()
    assert idx.locate([21.0699, 52.23]) == "kamionek"
    assert gc._precinct_area([21.0699, 52.23], [precinct], idx) == "goclaw"      # 7 m from Gocław
    assert gc._precinct_area([21.0650, 52.23], [precinct], idx) is None          # 340 m away: the point decides
    assert gc._precinct_area([21.0800, 52.23], [precinct], idx) is None          # already in Gocław
