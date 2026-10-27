"""City-wide build: every Warsaw district into a shard of its own (docs/plans/all-districts.md).

    uv run python -m pipeline.city [--districts all|enabled|bemowo,wola] [--offline | --skip-crawl]
                                   [--refresh] [--refresh-misses] [--site-url URL]

For each district (:mod:`pipeline.districts`) the ordinary single-district build (:func:`pipeline.build.run_build`)
runs with :class:`pipeline.build.DistrictPaths` and the district set as current:

* its own lists – crawled (``attachments`` strategy) into ``data/districts/<slug>/`` (Praga-Południe keeps its
  legacy ``data/manifest.json`` and ``data/raw``); districts whose lists are PDF-only or in their own layout are
  ``pending`` and get no own lists yet;
* the district's rows of the city-wide BAiPP lists (crawled once, with Praga-Południe's manifest);
* the district's cases of the GUNB register (the ZIPs in ``data/cache/rwdz`` are downloaded once and filtered
  per district into ``data/districts/<slug>/rwdz``);
* geocoding with the shared ULDK/UUG caches and the district's own OSM outline and MSI areas.

Outputs go to ``site/data/d/<slug>/`` (records.json, permits.json, sources.json, GeoJSON, CSV, feed.xml) and
``site/sources/d/<slug>/``; finally ``site/data/districts.json`` lists all 18 districts for the district switcher.
The legacy single-district outputs (``site/data/records.json`` …, ``make data``) are not touched.

Exit code: the worst of the district builds (0 ok, 3 a live source failed somewhere, 1 nothing could be built).
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

import requests

from . import crawl as crawl_mod
from . import districts
from .build import (
    EXIT_FATAL,
    EXIT_OK,
    PROJECT_ROOT,
    BuildError,
    DistrictPaths,
    Paths,
    committed_site_url,
    dumps_json,
    run_build,
    write_atomic,
)
from .district_index import DISTRICTS_INDEX, districts_index
from .geocode import PoliteSession as GeoSession
from .http import make_session

log = logging.getLogger("wzsearch.city")

def select(spec: str) -> list[str]:
    """``all`` | ``enabled`` | comma-separated slugs → slugs in registry order, Praga-Południe first (its crawl
    also refreshes the shared BAiPP lists)."""
    if spec == "all":
        slugs = list(districts.DISTRICTS)
    elif spec == "enabled":
        slugs = [s for s, d in districts.DISTRICTS.items() if d.enabled]
    else:
        slugs = [districts.get(s.strip()).slug for s in spec.split(",") if s.strip()]
    return sorted(dict.fromkeys(slugs), key=lambda s: (s != districts.LEGACY_SLUG, list(districts.DISTRICTS).index(s)))


def run_city_build(root: Path, slugs: list[str], *, crawl: bool = True, online: bool = True, refresh: bool = False,
                   refresh_misses: bool = False, site_url: str | None = None,
                   session: requests.Session | None = None, geocode: bool = True) -> int:
    """Build every district of ``slugs`` (see the module docstring); returns the worst exit code."""
    legacy = Paths(root)
    if site_url is None:
        site_url = os.environ.get("SITE_URL") or committed_site_url(legacy) or "./"
    crawl = crawl and online
    if crawl and session is None:
        session = make_session(min_delay=crawl_mod.DEFAULT_DELAY)
    # BAiPP's city-wide lists live in the legacy manifest and are refreshed by Praga-Południe's crawl (``make data``
    # or this command with praga-poludnie among the districts); other districts read them as they are.
    if crawl and districts.LEGACY_SLUG not in slugs:
        log.info("BAiPP lists as of the last Praga-Południe crawl (%s)",
                 (crawl_mod.load_manifest(legacy.manifest) or {}).get("generated_at"))
    geo_session = GeoSession() if online and geocode else None
    codes: dict[str, int] = {}
    gunb_checked = False   # GUNB's three ZIPs are checked once per run; the other districts filter the local copies
    for slug in slugs:
        d = districts.get(slug)
        log.info("=== %s (%s, %s) ===", d.name, d.unit, d.status)
        with districts.use(d):
            try:
                result = run_build(DistrictPaths(root, slug=slug), crawl=crawl, online=online, refresh=refresh,
                                   refresh_misses=refresh_misses, site_url=site_url, session=session,
                                   geo_session=geo_session, geocode=geocode, rwdz_online=crawl and not gunb_checked)
            except BuildError as exc:
                log.error("%s: %s", d.name, exc)
                codes[slug] = EXIT_FATAL
                continue
        codes[slug] = result.exit_code
        gunb_checked = gunb_checked or crawl
        log.info("%s: %d records, %d permits, exit %d", d.name, len(result.records), len(result.permits),
                 result.exit_code)
    index_path = root / DISTRICTS_INDEX
    if write_atomic(index_path, dumps_json(districts_index(root), ("districts",))):
        log.info("wrote %s", index_path.relative_to(root))
    for slug, code in codes.items():
        if code != EXIT_OK:
            log.error("%s: exit code %d", slug, code)
    return max(codes.values(), default=EXIT_OK) if EXIT_FATAL not in codes.values() else EXIT_FATAL


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m pipeline.city", description=__doc__.split("\n\n")[0])
    parser.add_argument("--districts", default="all",
                        help="all (default), enabled, or comma-separated slugs (e.g. bemowo,wola)")
    parser.add_argument("--offline", action="store_true", help="no network (manifests, extracts and caches only)")
    parser.add_argument("--skip-crawl", action="store_true", help="no crawling or GUNB download; geocode online")
    parser.add_argument("--refresh", action="store_true", help="re-download every source file")
    parser.add_argument("--refresh-misses", action="store_true", help="retry cached geocoding misses")
    parser.add_argument("--geocode-cache-only", action="store_true",
                        help="crawl and download online, but geocode from the caches only (the first city-wide run "
                             "needs ~60,000 ULDK lookups ≈ 8–10 h; run it district by district later)")
    parser.add_argument("--site-url", default=None, help="public base URL for permalinks in CSV/feeds")
    parser.add_argument("--root", type=Path, default=PROJECT_ROOT, help=argparse.SUPPRESS)
    parser.add_argument("-q", "--quiet", action="store_true", help="only print warnings and errors")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.WARNING if args.quiet else logging.INFO,
                        format="%(levelname).1s %(name)s: %(message)s", stream=sys.stderr)
    try:
        slugs = select(args.districts)
    except KeyError as exc:
        parser.error(str(exc))
    return run_city_build(args.root.resolve(), slugs, crawl=not (args.skip_crawl or args.offline),
                          online=not args.offline, refresh=args.refresh, refresh_misses=args.refresh_misses,
                          site_url=args.site_url, geocode=not args.geocode_cache_only)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
