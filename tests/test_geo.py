"""Unit tests for pipeline.geo (pure geometry) and pipeline.areas (pure parts)."""

import json
import math
import os

import pytest

from pipeline import areas, geo

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Real ULDK geometry of parcel 146507_8.0124.46/4 (Marokańska, Saska Kępa).
PARCEL_WKT = (
    "SRID=4326;POLYGON((21.0742930848836 52.2230733832611,21.0742923823575 52.223003189656,"
    "21.074291835629 52.2229386582119,21.0745261360371 52.2229386003857,21.0747162388377 52.2229379409399,"
    "21.0747137010726 52.2231698255707,21.0742910546665 52.2231722493929,21.0742930848836 52.2230733832611))"
)


def square(x0, y0, size, hole=None):
    ring = [[x0, y0], [x0 + size, y0], [x0 + size, y0 + size], [x0, y0 + size], [x0, y0]]
    coords = [ring]
    if hole:
        hx, hy, hs = hole
        coords.append([[hx, hy], [hx, hy + hs], [hx + hs, hy + hs], [hx + hs, hy], [hx, hy]])
    return {"type": "Polygon", "coordinates": coords}


# ------------------------------------------------------------------ WKT


class TestParseWkt:
    def test_real_uldk_polygon_with_srid(self):
        g = geo.parse_wkt(PARCEL_WKT)
        assert g["type"] == "Polygon"
        ring = g["coordinates"][0]
        assert len(ring) == 8
        assert ring[0] == ring[-1] == [21.0742930848836, 52.2230733832611]

    def test_multipolygon_with_hole(self):
        g = geo.parse_wkt("MULTIPOLYGON(((0 0,4 0,4 4,0 4,0 0),(1 1,1 2,2 2,2 1,1 1)),((10 10,11 10,11 11,10 10)))")
        assert g["type"] == "MultiPolygon"
        assert len(g["coordinates"]) == 2
        assert len(g["coordinates"][0]) == 2  # outer + hole

    def test_lines_and_points(self):
        assert geo.parse_wkt("POINT(21.06 52.24)") == {"type": "Point", "coordinates": [21.06, 52.24]}
        ml = geo.parse_wkt("MULTILINESTRING((0 0,1 1),(2 2,3 3,4 4))")
        assert ml["type"] == "MultiLineString" and len(ml["coordinates"][1]) == 3
        assert geo.parse_wkt("LINESTRING (0 0, 1 1)")["coordinates"] == [[0.0, 0.0], [1.0, 1.0]]
        assert geo.parse_wkt("MULTIPOINT((1 2),(3 4))")["coordinates"] == [[1.0, 2.0], [3.0, 4.0]]
        assert geo.parse_wkt("MULTIPOINT(1 2, 3 4)")["coordinates"] == [[1.0, 2.0], [3.0, 4.0]]

    def test_z_ordinate_dropped_and_lowercase(self):
        g = geo.parse_wkt("srid=2180;polygon z((0 0 5,1 0 5,1 1 5,0 0 5))")
        assert g["coordinates"][0][1] == [1.0, 0.0]

    def test_unclosed_ring_is_closed(self):
        g = geo.parse_wkt("POLYGON((0 0,1 0,1 1,0 1))")
        assert g["coordinates"][0][0] == g["coordinates"][0][-1]

    @pytest.mark.parametrize(
        "bad",
        ["", "   ", "POLYGON EMPTY", "CIRCLE((0 0))", "POLYGON((0 0,1 0,1 1,0 0)", "POINT(1)", "POLYGON((a b,1 1,1 0,0 0))",
         "POLYGON((0 0,1 1))", "-1 brak wyników"],
    )
    def test_invalid(self, bad):
        with pytest.raises(ValueError):
            geo.parse_wkt(bad)


# --------------------------------------------------------- measurements


class TestMeasurements:
    def test_area_of_real_parcel(self):
        # ULDK/EGiB reports 0.0744 ha for this parcel.
        g = geo.parse_wkt(PARCEL_WKT)
        assert geo.area_m2(g) == pytest.approx(744, rel=0.01)

    def test_area_subtracts_holes(self):
        full = geo.area_m2(square(21.0, 52.0, 0.01))
        holed = geo.area_m2(square(21.0, 52.0, 0.01, hole=(21.0025, 52.0025, 0.005)))
        assert holed == pytest.approx(full * 0.75, rel=1e-3)

    def test_centroid_square(self):
        c = geo.centroid(square(21.0, 52.0, 0.01))
        assert c == pytest.approx([21.005, 52.005], abs=1e-9)

    def test_centroid_ignores_ring_orientation(self):
        cw = {"type": "Polygon", "coordinates": [list(reversed(square(21.0, 52.0, 0.01)["coordinates"][0]))]}
        assert geo.centroid(cw) == pytest.approx([21.005, 52.005], abs=1e-9)

    def test_centroid_with_hole_shifts_away(self):
        # Hole in the left half pushes the centroid right.
        c = geo.centroid(square(21.0, 52.0, 0.01, hole=(21.001, 52.004, 0.002)))
        assert c[0] > 21.005
        assert c[1] == pytest.approx(52.005, abs=1e-6)

    def test_multipolygon_area_weighted(self):
        big = square(21.0, 52.0, 0.02)["coordinates"]
        small = square(21.1, 52.0, 0.01)["coordinates"]
        c = geo.centroid({"type": "MultiPolygon", "coordinates": [big, small]})
        # 4:1 area ratio → centroid is 1/5 of the way from big (21.01) to small (21.105).
        assert c[0] == pytest.approx(21.01 + (21.105 - 21.01) / 5, abs=2e-4)

    def test_centroid_of_lines_and_degenerate(self):
        line = {"type": "LineString", "coordinates": [[21.0, 52.0], [21.0, 52.002]]}
        assert geo.centroid(line) == pytest.approx([21.0, 52.001])
        flat = {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [2, 0], [0, 0]]]}
        assert geo.centroid(flat) == pytest.approx([0.75, 0.0])  # vertex mean fallback

    def test_weighted_centroid(self):
        assert geo.weighted_centroid([([0, 0], 1), ([10, 0], 3)]) == pytest.approx([7.5, 0])
        assert geo.weighted_centroid([([0, 0], 0), ([10, 0], 0)]) == pytest.approx([5, 0])
        with pytest.raises(ValueError):
            geo.weighted_centroid([])

    def test_bbox_and_union(self):
        assert geo.bbox(square(1, 2, 3)) == [1, 2, 4, 5]
        assert geo.bbox_union([None, [0, 0, 1, 1], [2, -1, 3, 0.5], []]) == [0, -1, 3, 1]
        assert geo.bbox_union([None]) is None

    def test_haversine(self):
        # One degree of latitude ≈ 111.2 km.
        assert geo.haversine_m([21.0, 52.0], [21.0, 53.0]) == pytest.approx(111_195, rel=1e-3)
        # Pałac Kultury → Stadion Narodowy ≈ 2.6 km.
        assert geo.haversine_m([21.0067, 52.2318], [21.0454, 52.2395]) == pytest.approx(2_770, rel=0.05)
        assert geo.haversine_m([21, 52], [21, 52]) == 0


class TestPointInPolygon:
    def test_simple_and_hole(self):
        g = square(0, 0, 10, hole=(4, 4, 2))
        assert geo.point_in_polygon([1, 1], g)
        assert not geo.point_in_polygon([5, 5], g)  # in the hole
        assert not geo.point_in_polygon([11, 5], g)

    def test_multipolygon(self):
        g = {"type": "MultiPolygon", "coordinates": [square(0, 0, 1)["coordinates"], square(5, 5, 1)["coordinates"]]}
        assert geo.point_in_polygon([5.5, 5.5], g)
        assert not geo.point_in_polygon([3, 3], g)

    def test_non_polygon_is_never_inside(self):
        assert not geo.point_in_polygon([0, 0], {"type": "Point", "coordinates": [0, 0]})

    def test_distance_to_polygon(self):
        g = square(21.0, 52.0, 0.01)
        assert geo.distance_to_polygon_m([21.005, 52.005], g) == 0
        # 0.001° of longitude at 52°N ≈ 68.5 m.
        d = geo.distance_to_polygon_m([21.011, 52.005], g)
        assert d == pytest.approx(68.5, rel=0.02)


# ------------------------------------------------------- rounding / simplify


class TestRoundingSimplify:
    def test_round_geometry_dedupes(self):
        g = {"type": "Polygon", "coordinates": [[[0.1234567, 0], [0.1234568, 0], [1, 0], [1, 1], [0.1234567, 0]]]}
        r = geo.round_geometry(g, 6)
        assert r["coordinates"][0] == [[0.123457, 0], [1, 0], [1, 1], [0.123457, 0]]

    def test_round_keeps_min_ring(self):
        g = {"type": "Polygon", "coordinates": [[[0, 0], [1e-9, 0], [0, 1e-9], [0, 0]]]}
        r = geo.round_geometry(g, 6)
        assert len(r["coordinates"][0]) == 4

    def test_douglas_peucker_drops_collinear(self):
        pts = [[0, 0], [1, 0.0001], [2, 0], [3, 0]]
        assert geo.douglas_peucker(pts, 0.01) == [[0, 0], [3, 0]]
        assert geo.douglas_peucker([[0, 0], [1, 5], [2, 0]], 1) == [[0, 0], [1, 5], [2, 0]]

    def test_simplify_line_tolerance_in_metres(self):
        # A 1 m bump is removed at 2 m tolerance and kept at 0.5 m.
        bump = 1 / 111_000
        line = [[21.0, 52.0], [21.001, 52.0 + bump], [21.002, 52.0]]
        assert len(geo.simplify_line(line, 2.0)) == 2
        assert len(geo.simplify_line(line, 0.5)) == 3

    def test_simplify_ring_stays_closed(self):
        n = 50
        ring = [[21 + 0.01 * math.cos(2 * math.pi * k / n), 52 + 0.01 * math.sin(2 * math.pi * k / n)] for k in range(n)]
        ring.append(ring[0])
        g = geo.simplify_geometry({"type": "Polygon", "coordinates": [ring]}, 50)
        out = g["coordinates"][0]
        assert out[0] == out[-1] and 4 <= len(out) < len(ring)


# ---------------------------------------------------------- ring assembly


class TestAssembly:
    def test_assemble_reversed_ways(self):
        ways = [[[0, 0], [1, 0], [1, 1]], [[0, 1], [1, 1]], [[0, 1], [0, 0]]]
        rings = geo.assemble_rings(ways)
        assert len(rings) == 1
        r = rings[0]
        assert r[0] == r[-1] and len(r) == 5

    def test_two_rings(self):
        ways = [[[0, 0], [1, 0], [1, 1], [0, 0]], [[5, 5], [6, 5]], [[6, 5], [6, 6], [5, 5]]]
        assert len(geo.assemble_rings(ways)) == 2

    def test_dangling_raises(self):
        with pytest.raises(ValueError):
            geo.assemble_rings([[[0, 0], [1, 0]], [[1, 0], [1, 1]]])

    def test_rings_to_geometry_attaches_holes(self):
        outer = square(0, 0, 10)["coordinates"][0]
        other = square(20, 0, 5)["coordinates"][0]
        hole = square(2, 2, 1)["coordinates"][0]
        g = geo.rings_to_geometry([outer, other], [hole])
        assert g["type"] == "MultiPolygon"
        assert len(g["coordinates"][0]) == 2 and len(g["coordinates"][1]) == 1
        assert geo.rings_to_geometry([outer])["type"] == "Polygon"


# ------------------------------------------------------------- line tools


class TestLineTools:
    def test_lines_inside_and_midpoint(self):
        district = square(21.0, 52.0, 0.01)
        street = {"type": "LineString", "coordinates": [[20.99, 52.005], [21.002, 52.005], [21.008, 52.005], [21.02, 52.005]]}
        parts = geo.lines_inside(street, district)
        assert parts == [[[21.002, 52.005], [21.008, 52.005]]]
        mid = geo.midpoint_along(parts)
        assert mid == pytest.approx([21.005, 52.005])
        assert geo.midpoint_along([]) is None

    def test_lines_inside_buffer(self):
        district = square(21.0, 52.0, 0.01)
        street = {"type": "LineString", "coordinates": [[21.0003 + 0.01, 52.002], [21.0003 + 0.01, 52.008]]}  # ~20 m east
        assert geo.lines_inside(street, district) == []
        assert len(geo.lines_inside(street, district, buffer_m=50)[0]) == 2

    def test_closest_approach_crossing(self):
        a = {"type": "LineString", "coordinates": [[21.0, 52.0], [21.01, 52.01]]}
        b = {"type": "MultiLineString", "coordinates": [[[21.0, 52.01], [21.01, 52.0]]]}
        pt, d = geo.closest_approach(a, b)
        assert d == 0 and pt == pytest.approx([21.005, 52.005], abs=1e-6)

    def test_closest_approach_parallel(self):
        a = {"type": "LineString", "coordinates": [[21.0, 52.0], [21.01, 52.0]]}
        b = {"type": "LineString", "coordinates": [[21.0, 52.001], [21.01, 52.001]]}
        pt, d = geo.closest_approach(a, b)
        assert d == pytest.approx(111.2, rel=0.01)
        assert pt[1] == pytest.approx(52.0005)
        assert geo.closest_approach(a, {"type": "Point", "coordinates": [0, 0]}) is None


# ================================================================== areas


def _rel(rel_id, name, level, rings, **tags):
    members = []
    for k, ring in enumerate(rings):
        # Split each ring into two ways to exercise stitching.
        half = len(ring) // 2
        for j, part in enumerate((ring[: half + 1], ring[half:])):
            members.append({"type": "way", "ref": rel_id * 10 + k * 2 + j, "role": "outer",
                            "geometry": [{"lon": x, "lat": y} for x, y in part]})
    members.append({"type": "node", "ref": 1, "role": "label", "lat": 0, "lon": 0})
    return {"type": "relation", "id": rel_id, "members": members,
            "tags": {"name": name, "admin_level": level, "boundary": "administrative", **tags}}


def _fake_overpass():
    d = [[21.0, 52.0], [21.02, 52.0], [21.02, 52.01], [21.0, 52.01], [21.0, 52.0]]
    west = [[21.0, 52.0], [21.01, 52.0], [21.01, 52.01], [21.0, 52.01], [21.0, 52.0]]
    east = [[21.01, 52.0], [21.02, 52.0], [21.02, 52.01], [21.01, 52.01], [21.01, 52.0]]
    outside = [[21.03, 52.0], [21.04, 52.0], [21.04, 52.01], [21.03, 52.01], [21.03, 52.0]]
    return {
        "osm3s": {"timestamp_osm_base": "2026-10-23T00:00:00Z"},
        "elements": [
            _rel(areas.DISTRICT_RELATION_ID, "Praga-Południe", "9", [d], **{"teryt:terc": "1465078"}),
            _rel(2, "Saska Kępa", "10", [west]),
            _rel(3, "Gocławek", "10", [east]),
            _rel(4, "Wawer-Somewhere", "10", [outside]),  # touches nothing → filtered out
        ],
    }


class TestAreas:
    @pytest.mark.parametrize(
        "label,slug",
        [("Saska Kępa", "saska-kepa"), ("Gocław", "goclaw"), ("Olszynka Grochowska", "olszynka-grochowska"),
         ("Przyczółek Grochowski", "przyczolek-grochowski"), ("Grochów", "grochow"), ("  Ąę  Źż--x ", "ae-zz-x")],
    )
    def test_slugify(self, label, slug):
        assert areas.slugify(label) == slug

    def test_build_features(self):
        district, feats, warnings = areas.build_features(_fake_overpass())
        assert district["slug"] == "_district"
        assert [f["slug"] for f in feats] == ["goclawek", "saska-kepa"]
        assert any("unexpected neighbourhood set" in w for w in warnings)
        assert not any("uncovered" in w or "overlap" in w for w in warnings)
        assert geo.area_m2(district["geometry"]) == pytest.approx(
            sum(geo.area_m2(f["geometry"]) for f in feats), rel=1e-6
        )

    def test_coverage_gap_detected(self):
        district = square(21.0, 52.0, 0.02)
        assert areas.coverage_warnings(district, [square(21.0, 52.0, 0.01)])

    def test_site_geojson_and_index(self):
        doc = areas.to_cache_document(_fake_overpass(), "https://example.invalid", "2026-10-23T00:00:00Z")
        fc = areas.to_site_geojson(doc)
        assert fc["type"] == "FeatureCollection" and "OpenStreetMap" in fc["attribution"]
        props = [f["properties"] for f in fc["features"]]
        assert props[0]["slug"] == "_district"
        assert all({"slug", "label", "source"} <= set(p) for p in props)
        assert all("ODbL" in p["source"] for p in props)
        idx = areas.AreaIndex.from_geojson(fc)
        assert idx.locate([21.005, 52.005]) == "saska-kepa"
        assert idx.locate([21.015, 52.005]) == "goclawek"
        assert idx.locate([21.0204, 52.005]) == "goclawek"  # ~27 m outside: nearest within 50 m
        assert idx.locate([21.03, 52.005]) is None
        assert idx.in_district([21.0204, 52.005]) is True
        assert idx.in_district([21.03, 52.005]) is False
        assert areas.AreaIndex(None).in_district([0, 0]) is None
        idx2 = areas.AreaIndex.from_cache_document(doc)
        assert idx2.labels == {"goclawek": "Gocławek", "saska-kepa": "Saska Kępa"}

    def test_missing_district_raises(self):
        data = _fake_overpass()
        data["elements"] = data["elements"][1:]
        with pytest.raises(ValueError):
            areas.build_features(data)

    @pytest.mark.skipif(not os.path.exists(os.path.join(ROOT, "site/data/areas.geojson")), reason="areas not built")
    def test_real_areas_file(self):
        with open(os.path.join(ROOT, "site/data/areas.geojson"), encoding="utf-8") as fh:
            fc = json.load(fh)
        idx = areas.AreaIndex.from_geojson(fc)
        assert set(idx.labels) == {"goclaw", "goclawek", "grochow", "kamionek", "olszynka-grochowska", "saska-kepa"}
        # Known addresses (UUG points) → MSI area.
        assert idx.locate([21.06429797542, 52.2494393793207]) == "kamionek"  # Mińska 46
        assert idx.locate([21.0889642545542, 52.22109783052]) == "goclaw"  # Wał Miedzeszyński 646
        assert idx.locate([21.1029653765054, 52.2577107805586]) == "olszynka-grochowska"  # Dudziarska 3
        assert idx.in_district([21.037823323174, 52.2736155108931]) is False  # Pińska 46 (Targówek)
        for f in fc["features"]:
            for c in geo.all_coords(f["geometry"]):
                assert c == [round(c[0], 6), round(c[1], 6)]
