"""Neighbourhood (MSI area) boundaries of Praga-Południe from OpenStreetMap.

Source: OpenStreetMap relations fetched through the Overpass API.

* District outline: relation 2544288 "Praga-Południe" (boundary=administrative,
  admin_level=9, teryt:terc=1465078).
* Neighbourhoods: every boundary=administrative + admin_level=10 relation inside
  the district. In Warsaw OSM uses admin_level=10 for the areas of the city's
  Miejski System Informacji (MSI); for Praga-Południe these are Gocław,
  Gocławek, Grochów, Kamionek, Olszynka Grochowska and Saska Kępa, which tile
  the district exactly. (Przyczółek Grochowski is part of the MSI area Gocław;
  OSM maps it separately only as an admin_level=11 "osiedle".)

Data © OpenStreetMap contributors, available under the Open Database Licence
(ODbL 1.0). The attribution is stored in every output file.

Outputs:

* ``data/cache/areas.json`` – full-resolution geometries (7 decimals) plus
  source metadata; the geocoder reads this for point-in-polygon tests.
* ``site/data/areas.geojson`` – FeatureCollection for the map: one feature per
  neighbourhood (``slug``, ``label``, ``source``) and one with
  ``slug: "_district"`` for the outline; coordinates rounded to 6 decimals and
  lightly simplified (shared borders stay identical because simplification is
  done per OSM way, before rings are assembled).

This module performs no I/O on its own except in :func:`build_areas` /
:func:`load_areas`; HTTP goes through a caller-provided session object with a
``post(url, data=..., timeout=...)`` method (see ``pipeline.geocode``).
"""

from __future__ import annotations

import json
import os
import tempfile
import time
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable

from . import geo

DISTRICT_RELATION_ID = 2544288
DISTRICT_TERC = "1465078"
AREA_ADMIN_LEVEL = "10"

# Names we expect to find (used only to flag surprises in the log).
EXPECTED_AREAS = {
    "Gocław",
    "Gocławek",
    "Grochów",
    "Kamionek",
    "Olszynka Grochowska",
    "Saska Kępa",
}

OVERPASS_ENDPOINTS = (
    "https://overpass-api.de/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
)

OVERPASS_QUERY = f"""[out:json][timeout:120];
rel({DISTRICT_RELATION_ID})->.d;
.d map_to_area->.a;
(
  .d;
  rel(area.a)["boundary"="administrative"]["admin_level"="{AREA_ADMIN_LEVEL}"];
);
out geom;"""

ATTRIBUTION = "© OpenStreetMap contributors"
LICENCE = "ODbL 1.0"
LICENCE_URL = "https://opendatacommons.org/licenses/odbl/1-0/"
COPYRIGHT_URL = "https://www.openstreetmap.org/copyright"

DISTRICT_SLUG = "_district"
SIMPLIFY_TOLERANCE_M = 1.5
SITE_DECIMALS = 6
CACHE_DECIMALS = 7

_TRANSLIT = str.maketrans({"ł": "l", "Ł": "L", "ø": "o", "Ø": "O", "đ": "d", "Đ": "D"})


def slugify(label: str) -> str:
    """ASCII kebab-case slug: ``"Saska Kępa"`` → ``"saska-kepa"``."""
    s = unicodedata.normalize("NFKD", label.translate(_TRANSLIT))
    s = "".join(ch for ch in s if not unicodedata.combining(ch)).lower()
    out, dash = [], False
    for ch in s:
        if ch.isascii() and ch.isalnum():
            out.append(ch)
            dash = False
        elif not dash and out:
            out.append("-")
            dash = True
    return "".join(out).strip("-")


# ------------------------------------------------------------------ building


def relation_geometry(element: dict, simplify_m: float = 0.0, way_cache: dict | None = None) -> dict:
    """Assemble an Overpass ``out geom`` relation into a (Multi)Polygon.

    Uses member ways with role ``outer`` (or empty) and ``inner``; other members
    (label nodes, subarea relations) are ignored. When ``simplify_m`` > 0 each
    way is simplified first (endpoints fixed), keyed by way id in ``way_cache``
    so a border shared by two relations is simplified identically.
    """
    outers, inners = [], []
    for m in element.get("members", []):
        if m.get("type") != "way" or not m.get("geometry"):
            continue
        role = m.get("role") or "outer"
        if role not in ("outer", "inner"):
            continue
        key = (m.get("ref"), simplify_m)
        if way_cache is not None and key in way_cache:
            coords = way_cache[key]
        else:
            coords = [[float(n["lon"]), float(n["lat"])] for n in m["geometry"] if n]
            if simplify_m > 0:
                coords = geo.simplify_line(coords, simplify_m)
            if way_cache is not None:
                way_cache[key] = coords
        (outers if role == "outer" else inners).append(coords)
    rings_out = geo.assemble_rings(outers)
    rings_in = geo.assemble_rings(inners) if inners else []
    return geo.rings_to_geometry(rings_out, rings_in)


def build_features(overpass: dict, simplify_m: float = 0.0) -> tuple[dict, list[dict], list[str]]:
    """Turn an Overpass response into ``(district_feature, area_features, warnings)``.

    Features are plain dicts ``{"slug", "label", "osm_id", "admin_level",
    "geometry"}`` (not yet GeoJSON Features). Pure function.
    """
    warnings: list[str] = []
    way_cache: dict = {}
    district = None
    areas = []
    for el in overpass.get("elements", []):
        if el.get("type") != "relation":
            continue
        tags = el.get("tags", {})
        name = tags.get("name", "").strip()
        try:
            geometry = relation_geometry(el, simplify_m, way_cache)
        except ValueError as exc:
            warnings.append(f"relation {el.get('id')} ({name}): {exc}")
            continue
        item = {
            "slug": slugify(name),
            "label": name,
            "osm_id": el["id"],
            "admin_level": tags.get("admin_level"),
            "geometry": geometry,
        }
        if el["id"] == DISTRICT_RELATION_ID:
            if tags.get("teryt:terc") not in (None, DISTRICT_TERC):
                warnings.append(f"district relation has unexpected teryt:terc={tags.get('teryt:terc')}")
            item["slug"] = DISTRICT_SLUG
            district = item
        elif tags.get("admin_level") == AREA_ADMIN_LEVEL:
            areas.append(item)
    if district is None:
        raise ValueError(f"district relation {DISTRICT_RELATION_ID} missing from Overpass response")

    # Overpass's area filter also returns relations that merely touch the
    # district: keep those whose centroid lies inside it.
    kept = []
    for a in areas:
        c = geo.centroid(a["geometry"])
        if geo.point_in_polygon(c, district["geometry"]):
            kept.append(a)
    areas = sorted(kept, key=lambda a: a["slug"])
    names = {a["label"] for a in areas}
    if names != EXPECTED_AREAS:
        warnings.append(
            "unexpected neighbourhood set: missing="
            f"{sorted(EXPECTED_AREAS - names)} extra={sorted(names - EXPECTED_AREAS)}"
        )
    slugs = [a["slug"] for a in areas]
    if len(set(slugs)) != len(slugs):
        warnings.append(f"duplicate neighbourhood slugs: {slugs}")
    warnings.extend(coverage_warnings(district["geometry"], [a["geometry"] for a in areas]))
    return district, areas, warnings


def coverage_warnings(district: dict, areas: list[dict], grid: int = 60) -> list[str]:
    """Check on a sample grid that the areas tile the district (no gaps/overlaps)."""
    b = geo.bbox(district)
    inside = gaps = overlaps = 0
    for i in range(grid):
        for j in range(grid):
            pt = [b[0] + (b[2] - b[0]) * (i + 0.5) / grid, b[1] + (b[3] - b[1]) * (j + 0.5) / grid]
            if not geo.point_in_polygon(pt, district):
                continue
            inside += 1
            hits = sum(1 for g in areas if geo.point_in_polygon(pt, g))
            gaps += hits == 0
            overlaps += hits > 1
    out = []
    if inside and gaps / inside > 0.01:
        out.append(f"neighbourhoods leave {gaps}/{inside} district sample points uncovered")
    if inside and overlaps / inside > 0.01:
        out.append(f"neighbourhoods overlap at {overlaps}/{inside} sample points")
    return out


def _source_meta(overpass: dict, endpoint: str | None) -> dict:
    return {
        "name": "OpenStreetMap",
        "attribution": ATTRIBUTION,
        "licence": LICENCE,
        "licence_url": LICENCE_URL,
        "copyright_url": COPYRIGHT_URL,
        "osm_base": (overpass.get("osm3s") or {}).get("timestamp_osm_base"),
        "endpoint": endpoint,
        "query": OVERPASS_QUERY,
    }


def _osm_url(osm_id: int) -> str:
    return f"https://www.openstreetmap.org/relation/{osm_id}"


def to_cache_document(overpass: dict, endpoint: str | None = None, fetched_at: str | None = None) -> dict:
    """Full-resolution cache document for ``data/cache/areas.json``."""
    district, areas, warnings = build_features(overpass, simplify_m=0.0)
    feats = []
    for item in [district] + areas:
        feats.append({**item, "geometry": geo.round_geometry(item["geometry"], CACHE_DECIMALS)})
    return {
        "fetched_at": fetched_at or _now(),
        "source": _source_meta(overpass, endpoint),
        "warnings": warnings,
        "features": feats,
        # Keep the raw response so the site file can be re-derived (e.g. with a
        # different simplification) without hitting Overpass again.
        "overpass": overpass,
    }


def to_site_geojson(cache_doc: dict, simplify_m: float = SIMPLIFY_TOLERANCE_M) -> dict:
    """Simplified, 6-decimal FeatureCollection for ``site/data/areas.geojson``."""
    district, areas, _ = build_features(cache_doc["overpass"], simplify_m=simplify_m)
    src = cache_doc["source"]
    features = []
    for item in [district] + areas:
        features.append(
            {
                "type": "Feature",
                "id": item["slug"],
                "properties": {
                    "slug": item["slug"],
                    "label": item["label"],
                    "source": f"{ATTRIBUTION}, {LICENCE} – OSM relation {item['osm_id']}",
                    "source_url": _osm_url(item["osm_id"]),
                    "osm_id": item["osm_id"],
                    "admin_level": item["admin_level"],
                },
                "geometry": geo.round_geometry(item["geometry"], SITE_DECIMALS),
            }
        )
    return {
        "type": "FeatureCollection",
        "attribution": f"{ATTRIBUTION} ({LICENCE})",
        "licence": LICENCE,
        "licence_url": LICENCE_URL,
        "copyright_url": COPYRIGHT_URL,
        "source": "OpenStreetMap via Overpass API: Praga-Południe (relation "
        f"{DISTRICT_RELATION_ID}) and its admin_level=10 MSI areas",
        "osm_base": src.get("osm_base"),
        "fetched_at": cache_doc.get("fetched_at"),
        "features": features,
    }


# ------------------------------------------------------------------ fetching


def fetch_overpass(session, endpoints=OVERPASS_ENDPOINTS, log: Callable = print) -> tuple[dict, str]:
    """POST the query to the first Overpass endpoint that answers with JSON."""
    last_exc: Exception | None = None
    for url in endpoints:
        try:
            resp = session.post(url, data={"data": OVERPASS_QUERY}, timeout=180)
            if resp.status_code != 200:
                raise RuntimeError(f"HTTP {resp.status_code}")
            data = resp.json()
            if not data.get("elements"):
                raise RuntimeError("empty Overpass result")
            return data, url
        except Exception as exc:  # noqa: BLE001 - try the next mirror
            log(f"  overpass {url}: {exc}")
            last_exc = exc
            time.sleep(1)
    raise RuntimeError(f"all Overpass endpoints failed: {last_exc}")


# --------------------------------------------------------------------- files


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def write_json_atomic(path: str, obj, *, compact: bool = False) -> None:
    """Write JSON via a temp file + ``os.replace`` (deterministic key order)."""
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".tmp-", suffix=".json", dir=os.path.dirname(os.path.abspath(path)))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            if compact:
                json.dump(obj, fh, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            else:
                json.dump(obj, fh, ensure_ascii=False, sort_keys=True, indent=1)
            fh.write("\n")
        os.chmod(tmp, 0o644)  # mkstemp creates 0600 files
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def build_areas(
    cache_dir: str = "data/cache",
    out_path: str = "site/data/areas.geojson",
    session=None,
    online: bool = True,
    refresh: bool = False,
    log: Callable = print,
) -> dict:
    """(Re)build ``areas.json`` (if needed) and ``areas.geojson``; return the cache doc."""
    cache_path = os.path.join(cache_dir, "areas.json")
    doc = None
    if not refresh and os.path.exists(cache_path):
        with open(cache_path, encoding="utf-8") as fh:
            doc = json.load(fh)
    if doc is None:
        if not online or session is None:
            raise RuntimeError(f"{cache_path} missing and offline: cannot build neighbourhood areas")
        log("fetching neighbourhood boundaries from OpenStreetMap (Overpass)…")
        overpass, endpoint = fetch_overpass(session, log=log)
        doc = to_cache_document(overpass, endpoint)
        write_json_atomic(cache_path, doc, compact=True)
    for w in doc.get("warnings", []):
        log(f"  areas warning: {w}")
    site = to_site_geojson(doc)
    write_json_atomic(out_path, site, compact=True)
    labels = ", ".join(f["properties"]["label"] for f in site["features"] if f["properties"]["slug"] != DISTRICT_SLUG)
    log(f"wrote {out_path}: district outline + {len(site['features']) - 1} areas ({labels})")
    return doc


# ------------------------------------------------------------------ lookups


@dataclass
class AreaIndex:
    """District outline + neighbourhood polygons for point lookups."""

    district: dict | None
    areas: list[tuple[str, str, dict]] = field(default_factory=list)  # (slug, label, geometry)
    _bboxes: list[list[float]] = field(default_factory=list, repr=False)

    def __post_init__(self):
        self._bboxes = [geo.bbox(g) for _, _, g in self.areas]

    @classmethod
    def from_cache_document(cls, doc: dict) -> "AreaIndex":
        district = None
        areas = []
        for f in doc.get("features", []):
            if f["slug"] == DISTRICT_SLUG:
                district = f["geometry"]
            else:
                areas.append((f["slug"], f["label"], f["geometry"]))
        return cls(district, areas)

    @classmethod
    def from_geojson(cls, fc: dict) -> "AreaIndex":
        district = None
        areas = []
        for f in fc.get("features", []):
            p = f.get("properties", {})
            if p.get("slug") == DISTRICT_SLUG:
                district = f["geometry"]
            else:
                areas.append((p["slug"], p.get("label", p["slug"]), f["geometry"]))
        return cls(district, areas)

    @property
    def labels(self) -> dict[str, str]:
        return {slug: label for slug, label, _ in self.areas}

    def in_district(self, pt, buffer_m: float = 50.0) -> bool | None:
        """True/False if inside the district (+buffer); ``None`` if unknown."""
        if self.district is None:
            return None
        return geo.distance_to_polygon_m(pt, self.district) <= buffer_m

    def locate(self, pt, tolerance_m: float = 50.0) -> str | None:
        """Slug of the neighbourhood containing ``pt``.

        Points just outside every polygon (e.g. on a border street, or in the
        50 m buffer outside the district) go to the nearest area within
        ``tolerance_m``.
        """
        x, y = pt[0], pt[1]
        for (slug, _, g), b in zip(self.areas, self._bboxes):
            if b[0] <= x <= b[2] and b[1] <= y <= b[3] and geo.point_in_polygon(pt, g):
                return slug
        best, best_d = None, tolerance_m
        for slug, _, g in self.areas:
            d = geo.distance_to_polygon_m(pt, g)
            if d <= best_d:
                best, best_d = slug, d
        return best


def load_areas(cache_dir: str = "data/cache", site_path: str = "site/data/areas.geojson") -> AreaIndex | None:
    """Load the area index from the cache (preferred) or the site GeoJSON."""
    cache_path = os.path.join(cache_dir, "areas.json")
    if os.path.exists(cache_path):
        with open(cache_path, encoding="utf-8") as fh:
            return AreaIndex.from_cache_document(json.load(fh))
    if os.path.exists(site_path):
        with open(site_path, encoding="utf-8") as fh:
            return AreaIndex.from_geojson(json.load(fh))
    return None
