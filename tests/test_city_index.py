"""The city-wide planning index (pipeline/city_index.py) and its entry in districts.json."""

import json

from pipeline import city_index
from pipeline.build import DistrictPaths
from pipeline.district_index import districts_index


def _record(rid, kind="wz", **extra):
    return {
        "id": rid, "kind": kind, "procedure": kind, "dataset": "district", "issuer": "district", "outcome": None,
        "number": f"N/{rid}", "date": "2026-09-01", "date_raw": "01.09.2026", "filed_date": None, "period": "2026-09",
        "applicant": "osoba fizyczna", "applicant_type": "person", "investment": "Budowa domu",
        "address": {"raw": "ul. Lipowa 5", "street": "Lipowa", "number": "5", "display": "Lipowa 5",
                    "parts": [{"street": "Lipowa", "number": "5", "numbers": ["5"]}], "approximate": False},
        "parcels": [{"number": "1/2", "obreb": "3-01-01", "partial": False, "id": "146507_8.0101.1/2"},
                    {"number": "3", "obreb": "3-01-01", "partial": True, "id": "146507_8.0101.3"}],
        "parcels_raw": "dz. 1/2, 3 obr. 3-01-01", "tags": ["jednorodzinny"], "permit": None, "area": "osiedle",
        "geo": {"lat": 52.123456789, "lon": 21.987654321, "method": "parcel", "parcels_found": ["146507_8.0101.1/2"],
                "bbox": [21.9, 52.1, 22.0, 52.2], "note": None},
        "sources": [{"file_id": "f", "page_id": "p", "sheet": "S", "row": 2}], "related": ["wz-2"], "warnings": ["x"],
        **extra,
    }


def test_lite_record_keeps_what_the_list_map_and_search_use():
    lite = city_index.lite_record(_record("wz-bem-2026-1"), "bemowo")
    assert set(lite) == {"id", "kind", "procedure", "dataset", "issuer", "number", "date", "period", "applicant",
                         "applicant_type", "investment", "address", "parcels", "tags", "area", "geo", "district"}
    assert lite["area"] == lite["district"] == "bemowo"
    assert lite["geo"] == {"lat": 52.12346, "lon": 21.98765, "method": "parcel"}
    assert lite["address"] == {"street": "Lipowa", "number": "5", "display": "Lipowa 5"}   # parts only repeated it
    assert lite["parcels"] == [{"number": "1/2", "obreb": "3-01-01", "id": "146507_8.0101.1/2"},
                               {"number": "3", "obreb": "3-01-01", "partial": True, "id": "146507_8.0101.3"}]
    # parcels_raw stays where no parcel was recognised (the search falls back to it); real address lists keep parts
    rec = _record("ws-bem-1", "ws", parcels=[])
    rec["address"]["parts"].append({"street": "Bukowa", "number": None, "numbers": []})
    lite = city_index.lite_record(rec, "bemowo")
    assert lite["parcels_raw"] == "dz. 1/2, 3 obr. 3-01-01" and len(lite["address"]["parts"]) == 2
    # a record without a neighbourhood still belongs to its district (the city's area facet)
    assert city_index.lite_record(_record("wz-bem-2", area=None), "bemowo")["area"] == "bemowo"


def _shard(root, slug, records, generated_at, outline=True):
    paths = DistrictPaths(root, slug=slug)
    paths.records_json.parent.mkdir(parents=True, exist_ok=True)
    doc = {"generated_at": generated_at, "kinds": {k: {"label": k} for k in ("wz", "cp", "ws", "pb", "zg")},
           "tags": {"jednorodzinny": {"label": "Dom jednorodzinny"}}, "areas": {"osiedle": {"label": "Osiedle"}},
           "datasets": {"district": {"label": f"Urząd Dzielnicy {slug}"}, "baipp": {"label": "BAiPP", "short": "BAiPP"},
                        "rwdz": {"label": "GUNB"}},
           "issuers": {"district": {"label": "Urząd"}, "city": {"label": "Miasto"}}, "outcomes": {"refused": {}},
           "records": records}
    paths.records_json.write_text(json.dumps(doc), encoding="utf-8")
    if outline:
        square = {"type": "Polygon", "coordinates": [[[21.0, 52.0], [21.1, 52.0], [21.1, 52.1], [21.0, 52.0]]]}
        areas = {"type": "FeatureCollection", "features": [
            {"type": "Feature", "geometry": square, "properties": {"slug": "_district", "label": slug, "osm_id": 1}},
            {"type": "Feature", "geometry": square, "properties": {"slug": "osiedle", "label": "Osiedle"}}]}
        paths.areas_geojson.write_text(json.dumps(areas), encoding="utf-8")


def test_city_index_is_assembled_from_the_shards_on_disk(tmp_path):
    assert city_index.build_city_index(tmp_path) is None
    _shard(tmp_path, "praga-poludnie", [_record("wz-2026-1"), _record("pb-st-1", "pb")], "2026-10-01T00:00:00Z")
    _shard(tmp_path, "bemowo", [_record("cp-bem-2026-1", "cp", date="2026-10-02")], "2026-10-27T10:00:00Z",
           outline=False)
    outputs = city_index.build_city_index(tmp_path)
    out = tmp_path / city_index.CITY_DIR
    assert set(outputs) == {out / "records.json", out / "sources.json", out / "areas.geojson"}
    records_doc = json.loads(outputs[out / "records.json"])
    assert records_doc["generated_at"] == "2026-10-27T10:00:00Z" and records_doc["city"] is True
    assert [r["id"] for r in records_doc["records"]] == ["cp-bem-2026-1", "wz-2026-1"]   # no permits, newest first
    assert [r["district"] for r in records_doc["records"]] == ["bemowo", "praga-poludnie"]
    assert list(records_doc["kinds"]) == ["wz", "cp", "ws"]
    assert records_doc["counts_by_kind"] == {"wz": 1, "cp": 1, "ws": 0}
    assert records_doc["areas"] == {"bemowo": {"label": "Bemowo"}, "praga-poludnie": {"label": "Praga-Południe"}}
    assert set(records_doc["datasets"]) == {"district", "baipp"}
    sources_doc = json.loads(outputs[out / "sources.json"])
    assert [(d["slug"], d["count"]) for d in sources_doc["districts"]] == [("bemowo", 1), ("praga-poludnie", 1)]
    assert sources_doc["pages"] == sources_doc["files"] == []
    areas = json.loads(outputs[out / "areas.geojson"])
    assert [f["properties"]["slug"] for f in areas["features"]] == ["praga-poludnie"]   # Bemowo has no outline yet
    assert areas["features"][0]["properties"]["label"] == "Praga-Południe"

    # written once; districts.json then describes the city like a district
    assert len(city_index.write_city_index(tmp_path)) == 3
    assert city_index.write_city_index(tmp_path) == []
    index = districts_index(tmp_path)
    assert index["city"]["slug"] == "warszawa" and index["city"]["city"] is True
    assert index["city"]["counts_by_kind"] == {"wz": 1, "cp": 1, "ws": 0}
    assert index["city"]["bbox"] == [21.98765, 52.12346, 21.98765, 52.12346]
    assert "city" not in districts_index(tmp_path, ["praga-poludnie"])   # a single-district build lists no city
