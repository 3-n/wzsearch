"""``site/data/districts.json`` – the district list the frontend's district picker reads (docs/plans/all-districts.md).

Written by the city-wide build (:mod:`pipeline.city`, every district) and – when missing – by the single-district
build (Praga-Południe alone, so that a single-district site answers the page's request for the list instead of
logging a 404). The frontend treats a list with one district as a single-district site. ``city`` – when the city
index exists – describes "Cała Warszawa" like a district.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from . import districts
from .build import DistrictPaths
from .city_index import city_entry
from .crawl import FIRST_YEAR, load_manifest

DISTRICTS_INDEX = Path("site") / "data" / "districts.json"


def _bbox(root: Path, slug: str, records: list[dict]) -> list[float] | None:
    """[west, south, east, north] of the district: its OSM outline, else its located records."""
    areas = DistrictPaths(root, slug=slug).areas_geojson
    coords: list[tuple[float, float]] = []
    try:
        doc = json.loads(areas.read_text(encoding="utf-8"))
        outline = next((f for f in doc.get("features", []) if (f.get("properties") or {}).get("slug") == "_district"),
                       None)
        if outline:
            stack: list[Any] = [outline["geometry"]["coordinates"]]
            while stack:
                item = stack.pop()
                if item and isinstance(item[0], (int, float)):
                    coords.append((item[0], item[1]))
                else:
                    stack.extend(item)
    except (OSError, ValueError, KeyError, TypeError):
        coords = []
    if not coords:
        coords = [(g["lon"], g["lat"]) for r in records if (g := r.get("geo") or {}).get("lat") is not None]
    if not coords:
        return None
    xs, ys = [c[0] for c in coords], [c[1] for c in coords]
    return [round(min(xs), 5), round(min(ys), 5), round(max(xs), 5), round(max(ys), 5)]


STALE_MONTHS = 12


def _months(period: str) -> int:
    return int(period[:4]) * 12 + int(period[5:7]) - 1 if len(period) >= 7 else int(period[:4]) * 12 + 11


def list_gaps(root: Path, slug: str, generated_at: str | None) -> dict | None:
    """What is missing from a district's own lists (plan §7, the "niepełne dane" label), from its committed manifest:
    files in scope (from :data:`pipeline.crawl.FIRST_YEAR`) that could not be downloaded, and a newest list more than
    :data:`STALE_MONTHS` older than the build. None when nothing is missing."""
    manifest = load_manifest(DistrictPaths(root, slug=slug).manifest) or {}
    own = [f for f in manifest.get("files") or [] if f.get("source", "district") != "baipp"
           and int((f.get("period") or "9999")[:4]) >= FIRST_YEAR]
    # a refused re-download leaves an earlier local copy in place (and readable): only files without one are missing
    have = [f for f in own if f.get("sha256") or (f.get("local_path") and (root / f["local_path"]).is_file())]
    missing = [f for f in own if f.get("error") and f not in have]
    periods = sorted(p for f in have if (p := f.get("period")))
    newest = periods[-1] if periods else None
    stale = bool(newest and generated_at and _months(generated_at[:7]) - _months(newest) > STALE_MONTHS)
    if not missing and not stale:
        return None
    return {
        "missing_files": len(missing), "files": len(own),
        "missing_years": sorted({f["period"][:4] for f in missing if f.get("period")}),
        "newest_list": newest if stale else None,
    }


def districts_index(root: Path, slugs: Iterable[str] | None = None) -> dict:
    """``site/data/districts.json``: every district (or those of ``slugs``) with what its shard holds."""
    items = []
    stamps = []
    for d in districts.DISTRICTS.values():
        if slugs is not None and d.slug not in slugs:
            continue
        shard = DistrictPaths(root, slug=d.slug).records_json
        try:
            doc = json.loads(shard.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            doc = None
        item: dict[str, Any] = {
            "slug": d.slug, "name": d.name, "genitive": d.genitive, "locative": d.locative,
            "instrumental": d.instrumental, "code": d.code, "unit": d.unit, "status": d.status, "note": d.note,
            "strategy": d.strategy, "entry_url": d.entry_url, "office": d.office,
            "inbox": d.inbox, "inbox_source": d.inbox_source,
            "available": doc is not None,
            "generated_at": (doc or {}).get("generated_at"),
            "counts_by_kind": (doc or {}).get("counts_by_kind") or {},
            "bbox": _bbox(root, d.slug, (doc or {}).get("records") or []) if doc else None,
            "center": list(d.center),
            "gaps": list_gaps(root, d.slug, (doc or {}).get("generated_at")) if doc else None,
        }
        if item["generated_at"]:
            stamps.append(item["generated_at"])
        items.append(item)
    out = {"generated_at": max(stamps) if stamps else None, "default": districts.LEGACY_SLUG, "districts": items}
    if slugs is None and (city := city_entry(root)):   # "Cała Warszawa" (pipeline/city_index.py)
        out["city"] = city
    return out




__all__ = ["DISTRICTS_INDEX", "districts_index"]
