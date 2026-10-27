"""Offline tests for pipeline.egib (GUGiK's county parcel package) and its use by the geocoder.

The package is a GeoPackage (SQLite); the tests build a tiny one with the same tables. The reference
coordinates are real: parcel 146507_8.0124.46/4 as ULDK returns it (EPSG:4326) and as the Warsaw package
(1465.gpkg, 27 X 2026) stores it (EPSG:2180).
"""

import io
import json
import sqlite3
import struct
import zipfile
from datetime import datetime, timedelta, timezone

import pytest
import requests

from pipeline import egib, geo
from pipeline import geocode as gc
from tests.test_geocode import ULDK_OK, area_index

# 146507_8.0124.46/4 in the package (EPSG:2180) – the same polygon as test_geocode.ULDK_OK
PARCEL_2180 = [(641642.2235293301, 486140.03469692264), (641642.3989675303, 486132.22951022815),
               (641642.5670219222, 486125.0541220736), (641658.5646180285, 486125.5056863278),
               (641671.5464331822, 486125.80400901847), (641670.6349936307, 486151.5789502319),
               (641641.7702512131, 486151.02222657483), (641642.2235293301, 486140.03469692264)]
# ... and two of its vertices as ULDK gives them (EPSG:4326)
ULDK_VERTICES = [((21.0742930848836, 52.2230733832611), PARCEL_2180[0]),
                 ((21.0747162388377, 52.2229379409399), PARCEL_2180[4])]


def gpkg_blob(polys):
    """GeoPackage geometry: ``GP`` header (little-endian, xy envelope, SRS 2180) + WKB MultiPolygon."""
    xs = [x for p in polys for r in p for x, _ in r]
    ys = [y for p in polys for r in p for _, y in r]
    wkb = struct.pack("<BII", 1, 6, len(polys))
    for poly in polys:
        wkb += struct.pack("<BII", 1, 3, len(poly))
        for ring in poly:
            wkb += struct.pack("<I", len(ring)) + b"".join(struct.pack("<dd", x, y) for x, y in ring)
    return b"GP" + bytes([0, 0b011]) + struct.pack("<i", 2180) + struct.pack("<4d", min(xs), max(xs), min(ys), max(ys)) + wkb


def square(x, y, size=20.0):
    return [[(x, y), (x + size, y), (x + size, y + size), (x, y + size), (x, y)]]


def make_package(path, rows):
    """``rows``: (id, polygons, data) – written like GUGiK's package (``dzialki`` + R-tree)."""
    db = sqlite3.connect(path)
    db.execute('CREATE TABLE dzialki (fid INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL, geometry GEOMETRY, '
               'id_dzialki TEXT, numer_dzialki TEXT, numer_obrebu TEXT, data TEXT)')
    db.execute("CREATE VIRTUAL TABLE rtree_dzialki_geometry USING rtree(id, minx, maxx, miny, maxy)")
    for pid, polys, data in rows:
        cur = db.execute("INSERT INTO dzialki (geometry, id_dzialki, numer_dzialki, numer_obrebu, data) VALUES (?, ?, ?, ?, ?)",
                         (gpkg_blob(polys), pid, pid.rsplit(".", 1)[1], pid.split(".")[1], data))
        xs = [x for p in polys for r in p for x, _ in r]
        ys = [y for p in polys for r in p for _, y in r]
        db.execute("INSERT INTO rtree_dzialki_geometry VALUES (?, ?, ?, ?, ?)", (cur.lastrowid, min(xs), max(xs), min(ys), max(ys)))
    db.commit()
    db.close()
    return path


ROWS = [
    ("146507_8.0124.46/4", [[PARCEL_2180]], "2026-10-23 21:03:51+00:00"),
    ("146507_8.0124.47", [square(641700, 486130)], "2026-10-23 21:03:51+00:00"),
    # a hole: the point in it lies on no parcel
    ("146507_8.0124.48", [square(641800, 486130, 40) + [[(641810, 486140), (641820, 486140), (641820, 486150),
                                                         (641810, 486150), (641810, 486140)]]], "2026-10-23 21:03:51+00:00"),
    # a "duplicate" (same id, other attributes): the newest row wins
    ("146507_8.0124.49", [square(641900, 486130)], "2026-10-20 00:00:00+00:00"),
    ("146507_8.0124.49", [square(641950, 486130)], "2026-10-23 21:03:51+00:00"),
]


@pytest.fixture
def package(tmp_path):
    pkg = egib.ParcelPackage(make_package(tmp_path / "1465.gpkg", ROWS))
    yield pkg
    pkg.close()


# ------------------------------------------------------------------ projection


class TestProjection:
    def test_uldk_vertices_are_the_package_vertices(self):
        for (lon, lat), (x, y) in ULDK_VERTICES:
            px, py = geo.wgs84_to_puwg1992(lon, lat)
            assert abs(px - x) < 0.001 and abs(py - y) < 0.001       # under a millimetre
            back = geo.puwg1992_to_wgs84(x, y)
            assert abs(back[0] - lon) < 1e-8 and abs(back[1] - lat) < 1e-8

    def test_round_trip_across_poland(self):
        for lon, lat in [(14.12, 54.8), (24.15, 49.0), (19.0, 52.0), (21.0, 52.2)]:
            x, y = geo.wgs84_to_puwg1992(lon, lat)
            back = geo.puwg1992_to_wgs84(x, y)
            assert geo.haversine_m(back, [lon, lat]) < 0.002

    def test_central_meridian(self):
        x, _ = geo.wgs84_to_puwg1992(19.0, 52.0)
        assert x == pytest.approx(500_000.0, abs=1e-6)


# --------------------------------------------------------------------- package


class TestParcelPackage:
    def test_geometry_by_id(self, package):
        g = package.geometry("146507_8.0124.46/4")
        assert g["type"] == "Polygon"
        assert g["coordinates"][0][0] == pytest.approx([21.0742930848836, 52.2230733832611], abs=1e-8)
        assert package.geometry("146507_8.0124.999") is None
        assert len(package) == 4
        assert package.as_of == "2026-10-23 21:03:51+00:00"

    def test_duplicate_ids_newest_row_wins(self, package):
        g = package.geometry("146507_8.0124.49")
        assert geo.wgs84_to_puwg1992(*g["coordinates"][0][0])[0] == pytest.approx(641950, abs=0.01)

    def test_parcel_under_a_point(self, package):
        lon, lat = geo.puwg1992_to_wgs84(641655, 486140)
        pid, g = package.at_point(lon, lat)
        assert pid == "146507_8.0124.46/4" and g["type"] == "Polygon"
        assert package.at_point(*geo.puwg1992_to_wgs84(641710, 486140))[0] == "146507_8.0124.47"
        assert package.at_point(*geo.puwg1992_to_wgs84(641815, 486145)) is None    # in the hole
        assert package.at_point(*geo.puwg1992_to_wgs84(641680, 486200)) is None    # between parcels

    def test_precincts(self, package):
        assert package.has_region("146507_8.0124")
        assert not package.has_region("146507_8.0125")
        assert not package.has_region("146508_8.0124")


# -------------------------------------------------------------------- download


class _Resp:
    def __init__(self, status, body=b""):
        self.status_code, self.body = status, body
        self.headers = {"Content-Length": str(len(body)), "Last-Modified": "Tue, 27 Oct 2026 00:25:00 GMT"}

    def iter_content(self, n):
        for i in range(0, len(self.body), n):
            yield self.body[i:i + n]

    def close(self):
        pass


class _Session:
    def __init__(self, resp):
        self.resp, self.calls = resp, []

    def request(self, method, url, **kw):
        self.calls.append(url)
        if isinstance(self.resp, Exception):
            raise self.resp
        return self.resp


def zipped(path):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.write(path, "1465.gpkg")
    return buf.getvalue()


class TestOpenPackage:
    NOW = datetime(2026, 10, 27, 12, tzinfo=timezone.utc)

    def test_downloads_unpacks_and_records_when(self, tmp_path):
        body = zipped(make_package(tmp_path / "src.gpkg", ROWS))
        s = _Session(_Resp(200, body))
        pkg = egib.open_package(tmp_path / "cache", s, now=self.NOW, log=lambda m: None)
        assert s.calls == ["https://opendata.geoportal.gov.pl/InneDane/latest_exports/eziudp_wfs/GPKG/1465.gpkg.zip"]
        assert pkg.geometry("146507_8.0124.47") is not None
        meta = json.loads((tmp_path / "cache" / "1465.json").read_text())
        assert meta["downloaded_at"] == self.NOW.isoformat() and meta["bytes"] == len(body)
        assert not list((tmp_path / "cache").glob("*.part")) and not list((tmp_path / "cache").glob("*.tmp"))

    def test_fresh_copy_is_not_downloaded_again(self, tmp_path):
        egib.open_package(tmp_path, _Session(_Resp(200, zipped(make_package(tmp_path / "src.gpkg", ROWS)))),
                          now=self.NOW, log=lambda m: None)
        s = _Session(_Resp(500))
        assert egib.open_package(tmp_path, s, now=self.NOW + timedelta(days=6), log=lambda m: None) is not None
        assert s.calls == []
        assert egib.open_package(tmp_path, None, online=False, now=self.NOW + timedelta(days=30), log=lambda m: None)

    def test_stale_copy_is_kept_when_the_download_fails(self, tmp_path):
        egib.open_package(tmp_path, _Session(_Resp(200, zipped(make_package(tmp_path / "src.gpkg", ROWS)))),
                          now=self.NOW, log=lambda m: None)
        logs = []
        s = _Session(requests.ConnectionError("down"))
        pkg = egib.open_package(tmp_path, s, now=self.NOW + timedelta(days=8), log=logs.append)
        assert s.calls and pkg is not None and any("download failed" in m for m in logs)

    def test_nothing_without_a_copy_or_network(self, tmp_path):
        assert egib.open_package(tmp_path, None, online=False, log=lambda m: None) is None
        assert egib.open_package(tmp_path, _Session(_Resp(404)), log=lambda m: None) is None
        assert not (tmp_path / "1465.gpkg").exists()


# ------------------------------------------------------------- geocoder wiring


class _NoNetwork:
    """A session that must not be asked: the package answers."""

    def __init__(self, package):
        self.parcel_package = package

    def get(self, *a, **kw):
        raise AssertionError("ULDK asked although the package is attached")


class TestGeocoderUsesThePackage:
    def test_lookup_parcels(self, package):
        cache = {}
        res = gc.lookup_parcels(["146507_8.0124.46/4", "146507_8.0124.999"], cache, _NoNetwork(package), True)
        hit, miss = res["146507_8.0124.46/4"], res["146507_8.0124.999"]
        assert hit["status"] == "ok" and hit["source"] == "egib"
        # the same centroid as the ULDK answer for this parcel (test_geocode.ULDK_OK)
        uldk = gc._uldk_entry(ULDK_OK, datetime.now(timezone.utc))
        assert geo.haversine_m(hit["centroid"], uldk["centroid"]) < 0.05
        assert hit["area_m2"] == pytest.approx(uldk["area_m2"], rel=0.002)
        assert miss["status"] == "missing" and cache["146507_8.0124.999"]["source"] == "egib"

    def test_cached_answers_win(self, package):
        cache = {"146507_8.0124.47": {"status": "ok", "geometry": None, "centroid": [1, 2], "fetched_at": "2026-10-01T00:00:00Z"}}
        res = gc.lookup_parcels(["146507_8.0124.47"], cache, _NoNetwork(package), True)
        assert res["146507_8.0124.47"]["centroid"] == [1, 2]

    def test_parcel_at_point_and_regions(self, package):
        cache = {}
        lon, lat = geo.puwg1992_to_wgs84(641710, 486140)
        at = gc.parcel_at_point(lon, lat, cache, _NoNetwork(package), True)
        assert at["status"] == "ok" and at["id"] == "146507_8.0124.47"
        assert cache["146507_8.0124.47"]["status"] == "ok"       # known like a looked-up parcel
        assert gc.parcel_at_point(*geo.puwg1992_to_wgs84(641680, 486200), cache, _NoNetwork(package), True)["status"] == "missing"
        regions = gc.lookup_regions(["146507_8.0124", "146507_8.0125"], cache, _NoNetwork(package), True)
        assert regions["146507_8.0124"]["status"] == "ok" and regions["146507_8.0125"]["status"] == "missing"

    def test_locate_records_attaches_the_package_for_many_unknown_parcels(self, package, tmp_path, monkeypatch):
        opened = []
        monkeypatch.setattr(egib, "MIN_PARCELS", 2)
        monkeypatch.setattr(egib, "open_package", lambda d, s, online, log: opened.append(d) or package)
        records = [{"id": "wz-1", "parcels": [{"id": "146507_8.0124.46/4"}, {"id": "146507_8.0124.47"}]}]
        session = _NoNetwork(None)
        out = gc.locate_records(records, cache_dir=str(tmp_path), online=True, log=lambda m: None, session=session,
                                area_index=area_index(), cross_check=False, package_dir=str(tmp_path / "egib"))
        assert opened == [str(tmp_path / "egib")] and session.parcel_package is package
        assert records[0]["geo"]["method"] == "parcel"
        assert out["stats"]["parcels_from_package"] == 2

    def test_few_unknown_parcels_ask_uldk(self, package, tmp_path, monkeypatch):
        monkeypatch.setattr(egib, "open_package", lambda *a, **kw: pytest.fail("package opened for one parcel"))

        class Uldk:
            def get(self, url, params=None, timeout=None):
                return type("R", (), {"status_code": 200, "text": ULDK_OK})()

        records = [{"id": "wz-1", "parcels": [{"id": "146507_8.0124.46/4"}]}]
        out = gc.locate_records(records, cache_dir=str(tmp_path), online=True, log=lambda m: None, session=Uldk(),
                                area_index=area_index(), cross_check=False, package_dir=str(tmp_path / "egib"))
        assert out["stats"]["parcels_ok"] == 1 and out["stats"]["parcels_from_package"] == 0


# ------------------------------------------------------------------ ULDK limits


class TestUldkLimits:
    def test_night_and_day_intervals(self):
        s = gc.PoliteSession(max_rps=2)
        day = datetime(2026, 10, 27, 12, tzinfo=gc.WARSAW)
        night = datetime(2026, 10, 27, 22, tzinfo=gc.WARSAW)
        assert s._interval("uldk.gugik.gov.pl", day) == pytest.approx(0.5)      # our own 2/s is below 200/min
        assert s._interval("uldk.gugik.gov.pl", night) == pytest.approx(1.5)    # 40/min after 18:00
        assert s._interval("services.gugik.gov.pl", night) == pytest.approx(0.5)

    def test_daily_cap(self, monkeypatch):
        monkeypatch.setitem(gc.PoliteSession.HOST_LIMITS, "uldk.gugik.gov.pl",
                            {"day_per_min": 10**6, "night_per_min": 10**6, "per_day": 2})

        class Raw:
            headers = {}

            def request(self, method, url, **kw):
                return type("R", (), {"status_code": 200})()

        s = gc.PoliteSession(max_rps=10**6, session=Raw())
        s.get("https://uldk.gugik.gov.pl/")
        s.get("https://uldk.gugik.gov.pl/")
        with pytest.raises(gc.DailyLimitReached):
            s.get("https://uldk.gugik.gov.pl/")
        assert s.get("https://services.gugik.gov.pl/uug/").status_code == 200
        # a capped lookup is an error, not a cached miss: the next run asks again
        cache = {}
        assert gc.lookup_parcels(["146507_8.0124.46/4"], cache, s, True)["146507_8.0124.46/4"]["status"] == "error"
        assert cache == {}
