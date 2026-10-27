#!/usr/bin/env python3
"""Per-district summary of the built shards – the table in docs/plans/all-districts.md §5a.

Usage (from the project root, after ``make city`` or ``make city-offline``)::

    uv run python scripts/city_summary.py

Per district: planning records (all / from the district's own lists), the share on the map, permits and
notifications (share on the map), and the gzip sizes of records.json / permits.json; then the city index.
"""

from __future__ import annotations

import gzip
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline import districts  # noqa: E402
from pipeline.build import DistrictPaths  # noqa: E402
from pipeline.city_index import CITY_DIR  # noqa: E402


def gz_kb(path: Path) -> int:
    return len(gzip.compress(path.read_bytes(), 6)) // 1024


def located(records: list[dict]) -> int:
    return sum(1 for r in records if (r.get("geo") or {}).get("method"))


def main() -> int:
    print("| District | lists | planning | of which district lists | located | permits + notif. (located) "
          "| gz records / permits |")
    print("|---|---|---:|---:|---:|---:|---:|")
    tot = [0, 0, 0, 0, 0]
    for d in districts.DISTRICTS.values():
        p = DistrictPaths(ROOT, slug=d.slug)
        try:
            recs = json.loads(p.records_json.read_text(encoding="utf-8"))["records"]
            perms = json.loads(p.permits_json.read_text(encoding="utf-8"))["records"]
        except OSError:
            print(f"| {d.name} | – | – | – | – | – | – |")
            continue
        own = sum(1 for r in recs if r["dataset"] == "district")
        fmt = "own xlsx" if d.strategy == "own-layout" or d.slug == "ursus" else ("PDF" if "pdf" in d.extensions else "xlsx")
        print(f"| {d.name} | {fmt} | {len(recs):,} | {own:,} | {located(recs) / max(len(recs), 1):.0%} "
              f"| {len(perms):,} ({located(perms) / max(len(perms), 1):.0%}) "
              f"| {gz_kb(p.records_json)} / {gz_kb(p.permits_json)} kB |")
        for i, v in enumerate((len(recs), own, located(recs), len(perms), located(perms))):
            tot[i] += v
    print(f"| **All 18** | | **{tot[0]:,}** | {tot[1]:,} | {tot[2] / max(tot[0], 1):.0%} "
          f"| **{tot[3]:,}** ({tot[4] / max(tot[3], 1):.0%}) | |")
    city = ROOT / CITY_DIR / "records.json"
    if city.is_file():
        n = len(json.loads(city.read_text(encoding="utf-8"))["records"])
        print(f"\nCała Warszawa ({CITY_DIR}/records.json): {n:,} planning records, {gz_kb(city)} kB gzip")
    return 0


if __name__ == "__main__":
    sys.exit(main())
