"""The city-wide planning index, ``site/data/warszawa/`` ("Cała Warszawa", docs/plans/all-districts.md §1.3, §2.2).

    uv run python -m pipeline.city_index        (``make city`` runs it after the district builds)

Assembled from the district shards on disk, so a build of a few districts re-assembles it with the others as they
are. Nothing is fetched and nothing is timestamped anew: ``generated_at`` is the newest of the shards'.

* ``records.json`` – the planning records (WZ, CP, wszczęcia) of every district in a lighter shape for the list,
  the map, the facets and the search (:func:`lite_record`; ≤ 2 MB gzip for ~18k records): no ``sources``,
  ``related``, ``warnings`` or ``date_raw``; ``geo`` without ``parcels_found``/``bbox``; ``address`` without ``raw``;
  ``parcels_raw`` only where no parcel was recognised; no null fields; ``area`` = the record's district (in the city, the neighbourhood facet is a district facet). A record's detail
  opens in its district, where the full record, its sources and its related records are.
* ``sources.json`` – no pages or files (those stay per district); ``districts`` says where each district's data
  came from and when it was built.
* ``areas.geojson`` – the districts' outlines (OSM) as the city's areas.

GUNB permits (43k cases) stay per district (plan §1.3).
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from . import districts
from .build import PROJECT_ROOT, DistrictPaths, dumps_json, write_atomic

log = logging.getLogger("wzsearch.city_index")

CITY_SLUG = "warszawa"
CITY_DIR = Path("site") / "data" / CITY_SLUG
PLANNING_KINDS = ("wz", "cp", "ws")
#: The city as the page names it (district.js reads these like a district's).
CITY_NAMES = {"name": "Cała Warszawa", "genitive": "Warszawy", "locative": "w Warszawie", "instrumental": "Warszawą"}

_DROP = frozenset({"date_raw", "sources", "related", "warnings"})


def _lite_address(address: dict[str, Any]) -> dict[str, Any]:
    """Without ``raw``, empty values, and ``parts`` when it only repeats the one street and number."""
    out = {k: v for k, v in address.items() if k != "raw" and v not in (None, False, "", [])}
    parts = out.get("parts") or []
    if len(parts) == 1 and parts[0].get("street") == out.get("street") and parts[0].get("number") == out.get("number") \
            and len(parts[0].get("numbers") or []) <= 1:
        del out["parts"]
    return out


def lite_record(record: dict[str, Any], slug: str) -> dict[str, Any]:
    """The city-index shape of a planning record of district ``slug`` (see the module docstring): also without
    null fields, ``partial`` only on partial parcels, coordinates to 5 decimals (~1 m)."""
    out: dict[str, Any] = {}
    for key, value in record.items():
        if key == "area":   # also where the record has no neighbourhood: the city's areas are its districts
            out[key] = slug
            continue
        if key in _DROP or value is None or (key == "parcels_raw" and record.get("parcels")):
            continue
        if key == "geo" and isinstance(value, dict):
            value = {k: (round(v, 5) if k in ("lat", "lon") else v) for k, v in value.items()
                     if k not in ("parcels_found", "bbox") and v is not None}
        elif key == "address" and isinstance(value, dict):
            value = _lite_address(value)
        elif key == "parcels" and isinstance(value, list):
            value = [{k: v for k, v in p.items() if k != "partial" or v} for p in value]
        out[key] = value
    out.setdefault("area", slug)
    out["district"] = slug
    return out


def _outline(slug: str, root: Path) -> dict | None:
    """The district's OSM outline from its shard's areas.geojson, as an area feature of the city."""
    try:
        doc = json.loads(DistrictPaths(root, slug=slug).areas_geojson.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    for f in doc.get("features") or []:
        props = f.get("properties") or {}
        if props.get("slug") == "_district" and f.get("geometry"):
            return {"type": "Feature", "geometry": f["geometry"],
                    "properties": {**props, "slug": slug, "label": districts.get(slug).name}}
    return None


def build_city_index(root: Path = PROJECT_ROOT) -> dict[Path, bytes] | None:
    """``{path: bytes}`` of the city index, or None when no district shard exists yet."""
    records: list[dict] = []
    shards: list[dict] = []
    meta: dict[str, Any] = {}
    outlines: list[dict] = []
    stamps: list[str] = []
    for d in districts.DISTRICTS.values():
        path = DistrictPaths(root, slug=d.slug).records_json
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        meta = meta or doc
        planning = [r for r in doc.get("records") or [] if r.get("kind") in PLANNING_KINDS]
        records += [lite_record(r, d.slug) for r in planning]
        shards.append({"slug": d.slug, "name": d.name, "generated_at": doc.get("generated_at"),
                       "count": len(planning), "entry_url": d.entry_url})
        if doc.get("generated_at"):
            stamps.append(doc["generated_at"])
        if outline := _outline(d.slug, root):
            outlines.append(outline)
    if not shards:
        return None
    generated_at = max(stamps) if stamps else None
    records.sort(key=lambda r: (r.get("date") or r.get("period") or "", r["id"]), reverse=True)
    by_kind = Counter(r["kind"] for r in records)
    datasets = meta.get("datasets") or {}
    issuers = meta.get("issuers") or {}
    records_doc = {
        "generated_at": generated_at,
        "city": True,
        "count": len(records),
        "kinds": {k: v for k, v in (meta.get("kinds") or {}).items() if k in PLANNING_KINDS},
        "tags": meta.get("tags") or {},
        "areas": {s["slug"]: {"label": s["name"]} for s in sorted(shards, key=lambda s: s["name"])},
        "datasets": {
            "district": {"label": "Urzędy dzielnic", "short": "Dzielnica",
                         "description": "Zestawienia urzędów dzielnic: wszczęte postępowania oraz wydane decyzje WZ "
                                        "i CP (zarządzenie nr 1129/2020 Prezydenta m.st. Warszawy)."},
            **({"baipp": datasets["baipp"]} if "baipp" in datasets else {}),
        },
        "issuers": {**issuers, "district": {"label": "Urząd dzielnicy (Wydział Architektury i Budownictwa)"}},
        "outcomes": meta.get("outcomes") or {},
        "permit_scopes": {},
        "permit_categories": {},
        "counts_by_kind": {k: by_kind.get(k, 0) for k in PLANNING_KINDS},
        "records": records,
    }
    if "baipp" in records_doc["datasets"]:
        records_doc["datasets"]["baipp"] = {**records_doc["datasets"]["baipp"], "description": (
            "Zestawienia ogólnomiejskie (roczne, aktualizowane co miesiąc) spraw WZ i CP prowadzonych centralnie "
            "przez Biuro Architektury i Planowania Przestrzennego; każdy wiersz pokazujemy w dzielnicy, którą "
            "wskazuje jego adres.")}
    sources_doc = {"generated_at": generated_at, "city": True, "districts": shards, "pages": [], "files": []}
    areas_doc = {"type": "FeatureCollection",
                 "attribution": "© OpenStreetMap contributors (ODbL 1.0)", "licence": "ODbL 1.0",
                 "licence_url": "https://opendatacommons.org/licenses/odbl/1-0/",
                 "copyright_url": "https://www.openstreetmap.org/copyright",
                 "source": "OpenStreetMap via Overpass API: the outlines of Warsaw's 18 districts (admin_level=9)",
                 "features": sorted(outlines, key=lambda f: f["properties"]["label"])}
    out = root / CITY_DIR
    return {
        out / "records.json": dumps_json(records_doc, ("records",)),
        out / "sources.json": dumps_json(sources_doc, ("districts",)),
        out / "areas.geojson": dumps_json(areas_doc, ("features",)),
    }


def city_entry(root: Path = PROJECT_ROOT) -> dict | None:
    """The city's entry of ``districts.json`` (like a district's), or None without a city index."""
    try:
        doc = json.loads((root / CITY_DIR / "records.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    coords = [(g["lon"], g["lat"]) for r in doc.get("records") or []
              if isinstance(g := r.get("geo"), dict) and g.get("lat") is not None]
    bbox = ([round(min(c[0] for c in coords), 5), round(min(c[1] for c in coords), 5),
             round(max(c[0] for c in coords), 5), round(max(c[1] for c in coords), 5)] if coords else None)
    return {"slug": CITY_SLUG, **CITY_NAMES, "city": True, "code": "", "status": "enabled", "note": None,
            "available": True, "generated_at": doc.get("generated_at"),
            "counts_by_kind": doc.get("counts_by_kind") or {}, "bbox": bbox, "center": [52.2297, 21.0122]}


def write_city_index(root: Path = PROJECT_ROOT) -> list[Path]:
    """Write the city index; returns the files that changed."""
    outputs = build_city_index(root)
    if outputs is None:
        log.info("no district shards – no city index")
        return []
    written = [p for p, data in outputs.items() if write_atomic(p, data)]
    for p in written:
        log.info("wrote %s", p.relative_to(root))
    return written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--root", type=Path, default=PROJECT_ROOT, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname).1s %(name)s: %(message)s")
    write_city_index(args.root)
    from .district_index import DISTRICTS_INDEX, districts_index   # noqa: PLC0415
    if write_atomic(args.root / DISTRICTS_INDEX, dumps_json(districts_index(args.root), ("districts",))):
        log.info("wrote %s", DISTRICTS_INDEX)
    return 0


__all__ = ["CITY_DIR", "CITY_SLUG", "build_city_index", "city_entry", "lite_record", "write_city_index"]

if __name__ == "__main__":
    sys.exit(main())
