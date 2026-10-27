"""GUGiK's county parcel package: every cadastral parcel of Warsaw in one file, looked up locally.

GUGiK harvests the county EGiB services daily and publishes the parcels of each county as a GeoPackage
(geoportal.gov.pl → Pobierz dane → "Dane powiatowe"; announced 19 IX 2025). Warsaw (county ``1465``) is one
107 MB ZIP, 474 MB unpacked, ~288,000 parcels in EPSG:2180::

    https://opendata.geoportal.gov.pl/InneDane/latest_exports/eziudp_wfs/GPKG/1465.gpkg.zip

It holds the same parcels as ULDK (checked on the draft's 6,693 found and 1,012 missing parcel ids: all found
ones are in the package, centroids within 3 cm (median), none of the missing ones is). ULDK's own terms
(uldk.gugik.gov.pl/opis.html) cap a client at 10,000 requests a day and point bulk users to these packages, so a
city-wide first geocoding (~60,000 parcels) reads the package instead of asking ULDK one parcel at a time.

:class:`ParcelPackage` answers the three ULDK questions the geocoder asks – a parcel's geometry by id
(``GetParcelById``), the parcel under a point (``GetParcelByXY``) and whether a precinct exists
(``GetRegionById``) – with Python's own ``sqlite3`` (a GeoPackage is an SQLite database). Precinct outlines
still come from ULDK (a handful per district). :func:`open_package` downloads the package when it is missing or
older than :data:`MAX_AGE_DAYS`; the geocoder uses it only when many parcels are unknown (see
``geocode.locate_records``), so a monthly run asks ULDK for its few new parcels as before.
"""

from __future__ import annotations

import json
import os
import sqlite3
import struct
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

from . import geo

COUNTY = "1465"   # m.st. Warszawa
PACKAGE_URL = "https://opendata.geoportal.gov.pl/InneDane/latest_exports/eziudp_wfs/GPKG/{county}.gpkg.zip"
SOURCE_LABEL = "GUGiK – działki EGiB, pakiet powiatowy (opendata.geoportal.gov.pl)"
MAX_AGE_DAYS = 7          # GUGiK rebuilds the packages daily; a week-old copy misses few new subdivisions
MIN_PARCELS = 300         # fewer unknown parcels than this: ask ULDK (a 107 MB download is not worth it)
DOWNLOAD_TIMEOUT = (30, 120)

__all__ = ["ParcelPackage", "open_package", "package_path"]


def package_path(cache_dir: str | Path, county: str = COUNTY) -> Path:
    return Path(cache_dir) / f"{county}.gpkg"


def _meta_path(path: Path) -> Path:
    return path.with_suffix(".json")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


# ------------------------------------------------------------------ geometry blobs


def _wkb_polygons(b: bytes, o: int) -> tuple[list, int]:
    """Polygons (lists of rings of ``(x, y)``) of a WKB Polygon/MultiPolygon at offset ``o``; Z/M values dropped."""
    e = "<" if b[o] == 1 else ">"
    code = struct.unpack_from(e + "I", b, o + 1)[0]
    o += 5
    base, dims = code % 1000, {0: 2, 1: 3, 2: 3, 3: 4}[code // 1000]
    if base == 3:
        (n_rings,) = struct.unpack_from(e + "I", b, o)
        o += 4
        rings = []
        for _ in range(n_rings):
            (n,) = struct.unpack_from(e + "I", b, o)
            o += 4
            flat = struct.unpack_from(f"{e}{n * dims}d", b, o)
            o += 8 * n * dims
            rings.append([(flat[i], flat[i + 1]) for i in range(0, n * dims, dims)])
        return [rings], o
    if base == 6:
        (n,) = struct.unpack_from(e + "I", b, o)
        o += 4
        polys = []
        for _ in range(n):
            part, o = _wkb_polygons(b, o)
            polys += part
        return polys, o
    raise ValueError(f"unexpected WKB geometry type {code}")


def gpkg_polygons(blob: bytes) -> list:
    """Polygons of a GeoPackage geometry blob (``GP`` header + envelope + WKB), in the package's grid."""
    if blob[:2] != b"GP":
        raise ValueError("not a GeoPackage geometry")
    envelope = (blob[3] >> 1) & 7
    return _wkb_polygons(blob, 8 + {0: 0, 1: 32, 2: 48, 3: 48, 4: 64}[envelope])[0]


def to_geojson(polys: list) -> dict:
    """EPSG:2180 polygons → GeoJSON geometry in ``[lon, lat]``."""
    coords = [[[geo.puwg1992_to_wgs84(x, y) for x, y in ring] for ring in poly] for poly in polys]
    if len(coords) == 1:
        return {"type": "Polygon", "coordinates": coords[0]}
    return {"type": "MultiPolygon", "coordinates": coords}


def _contains(polys: list, x: float, y: float) -> bool:
    return geo.point_in_polygon((x, y), {"type": "MultiPolygon", "coordinates": polys})


# ------------------------------------------------------------------------- package


class ParcelPackage:
    """Read-only lookups in a county package (``dzialki`` table, EPSG:2180, R-tree index)."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.db = sqlite3.connect(f"file:{self.path}?mode=ro", uri=True, check_same_thread=False)
        self._fids: dict[str, int] | None = None
        self._regions: set[str] | None = None
        (self.as_of,) = self.db.execute("SELECT max(data) FROM dzialki").fetchone()

    def __len__(self) -> int:
        return len(self._index())

    def _index(self) -> dict[str, int]:
        if self._fids is None:
            # GUGiK counts "duplicates" (one id, differing attributes); the newest row wins.
            rows = self.db.execute("SELECT id_dzialki, fid FROM dzialki ORDER BY data, fid")
            self._fids = {pid: fid for pid, fid in rows if pid}
        return self._fids

    def _polygons(self, fid: int) -> list:
        (blob,) = self.db.execute("SELECT geometry FROM dzialki WHERE fid = ?", (fid,)).fetchone()
        return gpkg_polygons(blob)

    def geometry(self, pid: str) -> dict | None:
        """A parcel's outline (GeoJSON, EPSG:4326) by its full id (``146507_8.0101.12/1``); None if unknown."""
        fid = self._index().get(pid)
        return to_geojson(self._polygons(fid)) if fid is not None else None

    def at_point(self, lon: float, lat: float) -> tuple[str, dict] | None:
        """The parcel under a point → ``(id, geometry)``; None outside every parcel."""
        x, y = geo.wgs84_to_puwg1992(lon, lat)
        rows = self.db.execute(
            "SELECT d.fid, d.id_dzialki FROM rtree_dzialki_geometry r JOIN dzialki d ON d.fid = r.id "
            "WHERE r.minx <= ? AND r.maxx >= ? AND r.miny <= ? AND r.maxy >= ? ORDER BY d.fid", (x, x, y, y))
        for fid, pid in rows:
            polys = self._polygons(fid)
            if pid and _contains(polys, x, y):
                return pid, to_geojson(polys)
        return None

    def has_region(self, rid: str) -> bool:
        """Whether a precinct (``146508_8.1406``) has any parcel."""
        if self._regions is None:
            self._regions = {".".join(pid.split(".", 2)[:2]) for pid in self._index()}
        return rid in self._regions

    def close(self) -> None:
        self.db.close()


def _download(url: str, path: Path, session, log: Callable[[str], None]) -> dict:
    """Stream the ZIP next to ``path``, unpack the GeoPackage into ``path``; returns the response metadata."""
    part = path.with_name(path.name + ".zip.part")
    path.parent.mkdir(parents=True, exist_ok=True)
    resp = session.request("GET", url, stream=True, timeout=DOWNLOAD_TIMEOUT)
    try:
        if resp.status_code != 200:
            raise OSError(f"HTTP {resp.status_code} from {url}")
        total = int(resp.headers.get("Content-Length") or 0)
        done = next_log = 0
        with open(part, "wb") as fh:
            for chunk in resp.iter_content(1 << 20):
                fh.write(chunk)
                done += len(chunk)
                if done >= next_log:
                    log(f"  parcel package: {done >> 20} / {total >> 20} MB")
                    next_log += 20 << 20
        if total and done != total:
            raise OSError(f"incomplete download ({done} of {total} bytes)")
    finally:
        resp.close()
    try:
        with zipfile.ZipFile(part) as zf:
            member = next(n for n in zf.namelist() if n.endswith(".gpkg"))
            tmp = path.with_name(path.name + ".tmp")
            with zf.open(member) as src, open(tmp, "wb") as dst:
                while chunk := src.read(1 << 20):
                    dst.write(chunk)
        os.replace(tmp, path)
    finally:
        part.unlink(missing_ok=True)
    return {"url": url, "bytes": done, "last_modified": resp.headers.get("Last-Modified"),
            "etag": resp.headers.get("ETag")}


def open_package(cache_dir: str | Path, session=None, online: bool = True, *, county: str = COUNTY,
                 max_age_days: float = MAX_AGE_DAYS, log: Callable[[str], None] = print,
                 now: datetime | None = None) -> ParcelPackage | None:
    """The county package from ``cache_dir`` – downloaded first when missing or older than ``max_age_days``
    (and ``online``). None when there is none and it cannot be downloaded (the caller asks ULDK instead)."""
    now = now or _utcnow()
    path = package_path(cache_dir, county)
    meta_path = _meta_path(path)
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        meta = {}
    downloaded = meta.get("downloaded_at")
    fresh = path.exists() and downloaded and now - datetime.fromisoformat(downloaded) < timedelta(days=max_age_days)
    if not fresh and online and session is not None:
        url = PACKAGE_URL.format(county=county)
        log(f"parcel package: downloading {url} (~107 MB) …")
        try:
            meta = {**_download(url, path, session, log), "downloaded_at": now.isoformat()}
            meta_path.write_text(json.dumps(meta, indent=1) + "\n", encoding="utf-8")
        except Exception as exc:  # noqa: BLE001 - keep a stale copy, else fall back to ULDK
            log(f"parcel package: download failed ({type(exc).__name__}: {exc})")
    if not path.exists():
        return None
    try:
        pkg = ParcelPackage(path)
    except sqlite3.Error as exc:
        log(f"parcel package: unreadable {path} ({exc})")
        return None
    log(f"parcel package: {path.name}, parcels as of {pkg.as_of}")
    return pkg
