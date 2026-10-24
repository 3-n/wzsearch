"""Geolocation stage: put every record on the map, as precisely as the data allows.

Strategy per record (see ``docs/DATA_MODEL.md``, ``Record.geo``):

1. **parcel** – look up every cadastral parcel id in GUGiK ULDK
   (``GetParcelById``); the point is the area-weighted centroid of the found
   parcels (i.e. of their union). Parcels spread more than ~1 km apart are
   clustered and the largest cluster wins (with a note).
2. **address** – GUGiK UUG geocoder (``GetAddress``) for "street + house
   number", validated: street name must match (diacritics/prefix/title
   insensitive), number must match, point must lie in Praga-Południe.
3. **street** – UUG street-only query: UUG's street point, or the street axis
   clipped to the district and the point halfway along it (note
   "lokalizacja przybliżona – ulica"); narrowed to the record's stated
   precinct when the street crosses it (ULDK ``GetRegionById``); for "A / B"
   addresses the crossing of the two streets.
4. otherwise ``lat/lon = null`` with an explanatory note.

An exact address far from the stated parcels (or with none of them in ULDK)
is checked against the parcel under it (``GetParcelByXY``): the same number
in another precinct reveals a precinct typo in the source, which is
corrected (see :func:`locate_records`).

Every point must lie inside the district polygon (+50 m) or it is discarded.
``record["area"]`` is the slug of the containing MSI neighbourhood.

All service responses (hits *and* misses) are cached in ``data/cache`` with a
``fetched_at`` timestamp, so rebuilds are offline-capable; misses are retried
after 30 days (or with ``refresh_misses=True``); hits are kept. Network
errors are never cached.

CLI::

    uv run python -m pipeline.geocode --probe 146507_8.0124.46/4 [...]
    uv run python -m pipeline.geocode --address "Mińska 46" [...]
    uv run python -m pipeline.geocode --areas [--refresh]
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
import tempfile
import threading
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from itertools import pairwise
from typing import Callable, Iterable
from urllib.parse import urlsplit

import requests

from . import areas as areas_mod
from . import geo

ULDK_URL = "https://uldk.gugik.gov.pl/"
UUG_URL = "https://services.gugik.gov.pl/uug/"
USER_AGENT = (
    "wzSearch/0.1 (open-data browser of Praga-Poludnie planning decisions; "
    "polite batch geocoding, cached)"
)
CITY = "Warszawa"
DISTRICT_TERYT = "146507_8"

MISS_TTL_DAYS = 30
DISTRICT_BUFFER_M = 50.0
CLUSTER_GAP_M = 1000.0
INTERSECTION_MAX_M = 60.0
ADDRESS_CONFLICT_M = 300.0
SITE_DECIMALS = 6

NOTE_STREET = "lokalizacja przybliżona – ulica"
NOTE_CROSSING = "lokalizacja przybliżona – skrzyżowanie ulic"
NOTE_PARCELS_NOT_FOUND = "działek nie znaleziono w ewidencji gruntów (ULDK) – mogły zostać podzielone lub scalone"

__all__ = [
    "PoliteSession",
    "load_cache",
    "save_cache",
    "parse_uldk_response",
    "parse_uug_response",
    "lookup_parcels",
    "geocode_address",
    "street_matches",
    "street_match_kind",
    "number_matches",
    "geocode_record_address",
    "known_subparcels",
    "locate_records",
    "lookup_regions",
    "parcel_at_point",
]


# =============================================================== HTTP session


class PoliteSession:
    """Small ``requests`` wrapper: per-host rate limit, retries with backoff.

    * at most ``max_rps`` requests per second per host (thread-safe),
    * retries on connection errors, timeouts, HTTP 429 and 5xx with exponential
      backoff (honouring ``Retry-After``), then raises,
    * identifies itself with a descriptive User-Agent.
    """

    RETRY_STATUS = {429, 500, 502, 503, 504}

    def __init__(
        self,
        max_rps: float = 4.0,
        retries: int = 4,
        backoff_s: float = 1.0,
        timeout_s: float = 30.0,
        user_agent: str = USER_AGENT,
        session: requests.Session | None = None,
    ):
        self.min_interval = 1.0 / max_rps
        self.retries = retries
        self.backoff_s = backoff_s
        self.timeout_s = timeout_s
        self._session = session or requests.Session()
        self._session.headers["User-Agent"] = user_agent
        self._lock = threading.Lock()
        self._next_slot: dict[str, float] = {}
        self.requests_made = 0

    def _wait_turn(self, url: str) -> None:
        host = urlsplit(url).netloc
        with self._lock:
            now = time.monotonic()
            slot = max(now, self._next_slot.get(host, 0.0))
            self._next_slot[host] = slot + self.min_interval
            self.requests_made += 1
        if slot > now:
            time.sleep(slot - now)

    def request(self, method: str, url: str, **kwargs) -> requests.Response:
        kwargs.setdefault("timeout", self.timeout_s)
        last_exc: Exception | None = None
        for attempt in range(self.retries + 1):
            self._wait_turn(url)
            delay = self.backoff_s * (2**attempt)
            try:
                resp = self._session.request(method, url, **kwargs)
                if resp.status_code not in self.RETRY_STATUS:
                    return resp
                last_exc = requests.HTTPError(f"HTTP {resp.status_code} from {url}", response=resp)
                retry_after = resp.headers.get("Retry-After", "")
                if retry_after.isdigit():
                    delay = max(delay, min(float(retry_after), 120.0))
            except (requests.ConnectionError, requests.Timeout) as exc:
                last_exc = exc
            if attempt < self.retries:
                time.sleep(delay)
        assert last_exc is not None
        raise last_exc

    def get(self, url: str, params=None, timeout: float | None = None) -> requests.Response:
        return self.request("GET", url, params=params, timeout=timeout or self.timeout_s)

    def post(self, url: str, data=None, timeout: float | None = None) -> requests.Response:
        return self.request("POST", url, data=data, timeout=timeout or self.timeout_s)


# ===================================================================== caches


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def _iso(dt: datetime) -> str:
    return dt.isoformat().replace("+00:00", "Z")


def _parse_iso(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


def load_cache(path: str) -> dict:
    """Load a JSON cache file (``{}`` if missing or unreadable)."""
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except FileNotFoundError:
        return {}
    except (OSError, json.JSONDecodeError) as exc:
        print(f"warning: ignoring unreadable cache {path}: {exc}", file=sys.stderr)
        return {}


def save_cache(path: str, cache: dict) -> None:
    """Atomically write a cache: sorted keys, one entry per line (diff-friendly)."""
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    lines = [
        json.dumps(k, ensure_ascii=False) + ":" + json.dumps(cache[k], ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        for k in sorted(cache)
    ]
    body = "{\n" + ",\n".join(lines) + "\n}\n" if lines else "{}\n"
    fd, tmp = tempfile.mkstemp(prefix=".tmp-", suffix=".json", dir=os.path.dirname(os.path.abspath(path)))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(body)
        os.chmod(tmp, 0o644)  # mkstemp creates 0600 files
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _is_fresh(entry: dict | None, now: datetime, refresh_misses: bool, max_age_days: float) -> bool:
    """Whether a cached entry can be used without asking the service again."""
    if not entry or entry.get("status") not in ("ok", "missing"):
        return False
    if entry["status"] == "ok":
        return True
    if refresh_misses:
        return False
    fetched = _parse_iso(entry.get("fetched_at"))
    return fetched is not None and now - fetched < timedelta(days=max_age_days)


# ======================================================================= ULDK

_PARCEL_ID_RE = re.compile(r"^\d{6}_\d\.\d{4}\.[0-9A-Za-z./-]+$")


def normalize_parcel_id(pid: str | None) -> str | None:
    """Strip whitespace; return ``None`` for ids that cannot be ULDK ids."""
    if not pid or not isinstance(pid, str):
        return None
    pid = re.sub(r"\s+", "", pid)
    return pid if _PARCEL_ID_RE.match(pid) else None


def parse_uldk_response(text: str) -> tuple[str, list[tuple[str, dict]]]:
    """Parse a ULDK ``result=id,geom_wkt`` text response.

    Returns ``("ok", [(id, geometry), ...])`` or ``("missing", [])``.
    Raises ``ValueError`` on anything unexpected (treated as an error, not
    cached). Format: first line is a status (``0`` = found, ``-1 brak
    wyników`` = not found), then one ``id|SRID=4326;POLYGON(...)`` line per
    object (``id||SRID=…`` when an empty attribute is in between).
    """
    if text is None:
        raise ValueError("empty ULDK response")
    lines = [ln.strip() for ln in text.strip().splitlines() if ln.strip()]
    if not lines:
        raise ValueError("empty ULDK response")
    head = lines[0]
    m = re.match(r"^(-?\d+)\b\s*(.*)$", head)
    if not m:
        raise ValueError(f"unexpected ULDK status line {head[:80]!r}")
    status = int(m.group(1))
    if status < 0:
        if "brak wynik" in text.lower():
            return "missing", []
        raise ValueError(f"ULDK error: {text.strip()[:160]!r}")
    results = []
    for ln in lines[1:]:
        parts = ln.split("|")
        wkt = next((p for p in reversed(parts) if "(" in p), None)
        if wkt is None:
            continue
        geom = geo.parse_wkt(wkt)
        if geom["type"] not in ("Polygon", "MultiPolygon"):
            raise ValueError(f"unexpected ULDK geometry {geom['type']}")
        results.append((parts[0].strip(), geom))
    if not results:
        # A "0" status with no rows has not been observed; don't cache it.
        raise ValueError(f"ULDK status {status} without geometry: {text.strip()[:160]!r}")
    return "ok", results


def _merge_polygons(geoms: list[dict]) -> dict:
    polys = [p for g in geoms for p in geo.polygons_of(g)]
    if len(polys) == 1:
        return {"type": "Polygon", "coordinates": polys[0]}
    return {"type": "MultiPolygon", "coordinates": polys}


def _uldk_entry(text: str, now: datetime) -> dict:
    """Cache entry from a ULDK response text (raises ValueError if unusable)."""
    status, results = parse_uldk_response(text)
    if status == "missing":
        return {"status": "missing", "fetched_at": _iso(now)}
    return _geometry_entry(_merge_polygons([g for _, g in results]), now)


def _geometry_entry(geometry: dict, now: datetime) -> dict:
    """``ok`` cache entry of a parcel geometry (rounded, with centroid, bbox and area)."""
    geometry = geo.round_geometry(geometry, SITE_DECIMALS)
    return {
        "status": "ok",
        "geometry": geometry,
        "centroid": [round(v, 7) for v in geo.centroid(geometry)],
        "bbox": [round(v, 6) for v in geo.bbox(geometry)],
        "area_m2": round(geo.area_m2(geometry), 1),
        "fetched_at": _iso(now),
    }


def fetch_parcel(pid: str, session, now: datetime | None = None) -> dict:
    """Ask ULDK for one parcel; returns a cache entry or an ``error`` entry."""
    now = now or _now()
    params = {"request": "GetParcelById", "id": pid, "result": "id,geom_wkt", "srid": "4326"}
    try:
        resp = session.get(ULDK_URL, params=params, timeout=30)
        if resp.status_code != 200:
            raise ValueError(f"HTTP {resp.status_code}")
        return _uldk_entry(resp.text, now)
    except Exception as exc:  # noqa: BLE001 - any failure is a (non-cached) error
        return {"status": "error", "error": f"{type(exc).__name__}: {exc}"[:300], "fetched_at": _iso(now)}


def lookup_parcels(
    ids: Iterable[str],
    cache: dict,
    session,
    online: bool = True,
    *,
    refresh_misses: bool = False,
    max_age_days: float = MISS_TTL_DAYS,
    workers: int = 3,
    log: Callable | None = None,
    checkpoint: Callable[[], None] | None = None,
    checkpoint_every: int = 100,
    now: datetime | None = None,
) -> dict[str, dict]:
    """Resolve parcel ids to geometries via the cache and (if online) ULDK.

    Returns ``{id: {"status": "ok"|"missing"|"error", "geometry", "centroid",
    "fetched_at", ...}}`` for every requested id. ``cache`` (a dict keyed by
    parcel id) is updated in place with new hits and misses; errors are not
    cached. ``checkpoint`` (e.g. a cache save) is called every
    ``checkpoint_every`` fetches.
    """
    now = now or _now()
    out: dict[str, dict] = {}
    todo: list[str] = []
    for raw in ids:
        pid = normalize_parcel_id(raw)
        if pid is None:
            out[raw] = {"status": "error", "error": "invalid parcel id", "geometry": None, "centroid": None, "fetched_at": None}
            continue
        if pid in out or pid in todo:
            continue
        entry = cache.get(pid)
        if _is_fresh(entry, now, refresh_misses, max_age_days):
            out[pid] = entry
        elif not online or session is None:
            out[pid] = entry if entry and entry.get("status") in ("ok", "missing") else {
                "status": "error", "error": "not cached (offline)", "fetched_at": None
            }
        else:
            todo.append(pid)
    if todo:
        if log:
            log(f"ULDK: fetching {len(todo)} parcels ({len(out)} from cache)…")
        done = ok = 0
        with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
            futures = {pool.submit(fetch_parcel, pid, session, now): pid for pid in todo}
            for fut in as_completed(futures):
                pid = futures[fut]
                entry = fut.result()
                out[pid] = entry
                if entry["status"] in ("ok", "missing"):
                    cache[pid] = entry
                done += 1
                ok += entry["status"] == "ok"
                if checkpoint and done % checkpoint_every == 0:
                    checkpoint()
                if log and (done % 100 == 0 or done == len(todo)):
                    log(f"  ULDK {done}/{len(todo)} fetched, {ok} found")
    # Copies, so callers never mutate cache entries by accident.
    return {k: {"geometry": None, "centroid": None, **v} for k, v in out.items()}


def _cached_or_fetch(key: str, cache: dict, session, online: bool, params: dict, parse: Callable[[str, datetime], dict],
                     *, refresh_misses: bool, max_age_days: float, now: datetime | None) -> dict:
    """One cached ULDK request (``ok``/``missing`` cached under ``key``; errors and offline misses not)."""
    now = now or _now()
    entry = cache.get(key)
    if _is_fresh(entry, now, refresh_misses, max_age_days):
        return dict(entry)
    if not online or session is None:
        if entry and entry.get("status") in ("ok", "missing"):
            return dict(entry)
        return {"status": "error", "error": "not cached (offline)", "fetched_at": None}
    try:
        resp = session.get(ULDK_URL, params=params, timeout=30)
        if resp.status_code != 200:
            raise ValueError(f"HTTP {resp.status_code}")
        entry = parse(resp.text, now)
    except Exception as exc:  # noqa: BLE001 - any failure is a (non-cached) error
        return {"status": "error", "error": f"{type(exc).__name__}: {exc}"[:300], "fetched_at": _iso(now)}
    cache[key] = entry
    return dict(entry)


def parcel_at_point(lon: float, lat: float, cache: dict, session, online: bool = True, *,
                    refresh_misses: bool = False, max_age_days: float = MISS_TTL_DAYS,
                    now: datetime | None = None) -> dict:
    """The parcel under a point (ULDK ``GetParcelByXY``) → ``{"status": "ok", "id": "146507_8.0526.35", …}``,
    ``missing`` or ``error``.

    Cached in the parcel cache under ``xy:<lon>,<lat>`` (6 decimals, as asked); a hit also stores the
    parcel's geometry under its own id (the ``GetParcelById`` entry), so it is then known like any
    looked-up parcel.
    """
    lon, lat = round(lon, 6), round(lat, 6)

    def parse(text: str, when: datetime) -> dict:
        status, results = parse_uldk_response(text)
        if status == "missing":
            return {"status": "missing", "fetched_at": _iso(when)}
        pid, geometry = results[0]
        if pid not in cache:   # never overwrite an answer other records were located with (deterministic builds)
            cache[pid] = _geometry_entry(geometry, when)
        return {"status": "ok", "id": pid, "fetched_at": _iso(when)}

    params = {"request": "GetParcelByXY", "xy": f"{lon:.6f},{lat:.6f},4326", "result": "id,geom_wkt", "srid": "4326"}
    return _cached_or_fetch(f"xy:{lon:.6f},{lat:.6f}", cache, session, online, params, parse,
                            refresh_misses=refresh_misses, max_age_days=max_age_days, now=now)


def lookup_regions(ids: Iterable[str], cache: dict, session, online: bool = True, *, refresh_misses: bool = False,
                   max_age_days: float = MISS_TTL_DAYS, now: datetime | None = None) -> dict[str, dict]:
    """Whether cadastral precincts exist (ULDK ``GetRegionById``, ``146508_8.1406``) →
    ``{id: {"status": "ok"|"missing"|"error"}}``; cached in the parcel cache under ``region:<id>``."""
    def parse(text: str, when: datetime) -> dict:
        head = (text or "").strip().split("\n", 1)[0]
        if head.startswith("-1") and "brak wynik" in (text or "").lower():
            return {"status": "missing", "fetched_at": _iso(when)}
        if head.strip() == "0":
            return {"status": "ok", "fetched_at": _iso(when)}
        raise ValueError(f"unexpected ULDK answer {text.strip()[:80]!r}")

    out: dict[str, dict] = {}
    for rid in dict.fromkeys(ids):
        params = {"request": "GetRegionById", "id": rid, "result": "id"}
        out[rid] = _cached_or_fetch(f"region:{rid}", cache, session, online, params, parse,
                                    refresh_misses=refresh_misses, max_age_days=max_age_days, now=now)
    return out


REGION_SIMPLIFY_M = 2.0


def region_geometry(rid: str, cache: dict, session, online: bool = True, *, refresh_misses: bool = False,
                    max_age_days: float = MISS_TTL_DAYS, now: datetime | None = None) -> dict | None:
    """Polygon of a cadastral precinct (ULDK ``GetRegionById``, ``146507_8.0524``), simplified to ~2 m; None if
    it does not exist or is unknown (offline without cache, network error). Cached under ``region:<id>``
    together with the existence answer of :func:`lookup_regions`."""
    now = now or _now()
    key = f"region:{rid}"
    entry = cache.get(key) or {}
    if entry.get("status") == "ok" and entry.get("geometry"):
        return entry["geometry"]
    if entry.get("status") == "missing" and _is_fresh(entry, now, refresh_misses, max_age_days):
        return None
    if not online or session is None:
        return None
    params = {"request": "GetRegionById", "id": rid, "result": "id,geom_wkt", "srid": "4326"}
    try:
        resp = session.get(ULDK_URL, params=params, timeout=30)
        if resp.status_code != 200:
            raise ValueError(f"HTTP {resp.status_code}")
        status, results = parse_uldk_response(resp.text)
    except Exception:  # noqa: BLE001 - not cached, retried next run
        return None
    if status == "missing":
        cache[key] = {"status": "missing", "fetched_at": _iso(now)}
        return None
    geometry = geo.round_geometry(geo.simplify_geometry(_merge_polygons([g for _, g in results]), REGION_SIMPLIFY_M),
                                  SITE_DECIMALS)
    cache[key] = {"status": "ok", "geometry": geometry, "bbox": [round(v, 6) for v in geo.bbox(geometry)],
                  "fetched_at": _iso(now)}
    return geometry


# ======================================================================== UUG

_TRANSLIT = str.maketrans({"ł": "l", "Ł": "L"})

# Generic street-type prefixes and honorifics/titles that the source and the
# national register write inconsistently ("Gen. Fieldorfa Nila" vs "ulica gen.
# Augusta Emila Fieldorfa „Nila”").
_STREET_TYPES = {
    "ul", "ulica", "ulicy", "ulic", "al", "aleja", "aleje", "alei", "pl", "plac", "rondo", "skwer", "os",
    "osiedle", "bulwar", "park", "pasaz", "trakt", "rejon", "rejonie", "okolice", "okolicy",
}
_TITLES = {
    "gen", "generala", "ks", "ksiedza", "kard", "kardynala", "bp", "biskupa", "abp", "arcybiskupa",
    "marsz", "marszalka", "prof", "profesora", "dr", "doktora", "kpt", "kapitana", "plk", "pulkownika",
    "ppłk", "pplk", "podpulkownika", "mjr", "majora", "por", "porucznika", "ppor", "podporucznika",
    "rtm", "rotmistrza", "hm", "harcmistrza", "inz", "inzyniera", "hr", "hrabiego", "kmdr", "komandora",
    "adm", "admirala", "sw", "swietego", "swietej", "bl", "blogoslawionego", "o", "ojca", "im", "imienia",
}
# Place names that leak into address cells ("Kamionkowska 29 Praga-Południe").
_PLACE_TOKENS = {"warszawa", "praga", "poludnie", "pld", "dzielnica", "m", "st"}


def _fold(s: str) -> str:
    s = unicodedata.normalize("NFKD", (s or "").translate(_TRANSLIT))
    return "".join(ch for ch in s if not unicodedata.combining(ch)).lower()


def street_tokens(name: str) -> list[str]:
    """Significant, accent-folded tokens of a street name (order kept)."""
    toks = re.findall(r"[0-9a-z]+", _fold(name))
    return [t for t in toks if t not in _STREET_TYPES and t not in _TITLES and t not in _PLACE_TOKENS]


def _osa_distance(a: str, b: str) -> int:
    """Optimal-string-alignment edit distance (adjacent transpositions count 1)."""
    if a == b:
        return 0
    prev2: list[int] = []
    prev = list(range(len(b) + 1))
    for i in range(1, len(a) + 1):
        cur = [i] + [0] * len(b)
        for j in range(1, len(b) + 1):
            cost = 0 if a[i - 1] == b[j - 1] else 1
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + cost)
            if i > 1 and j > 1 and a[i - 1] == b[j - 2] and a[i - 2] == b[j - 1]:
                cur[j] = min(cur[j], prev2[j - 2] + 1)
        prev2, prev = prev, cur
    return prev[-1]


def _fuzzy_token(t: str, c: str) -> bool:
    """Typo-tolerant token equality: same first letter and a small edit distance.

    ≤ 1 edit for tokens of 6+ letters ("Chdakowska" → Chodakowska, "Feildorfa"
    → Fieldorfa); 2 edits only for equal-length tokens of 10+ letters
    ("Borlemowska" → Boremlowska, but not "Grochowska" → Grochowa).
    "Mińska"/"Pińska" differ in the first letter and never match.
    """
    if t.isdigit() or c.isdigit() or t[0] != c[0] or len(t) < 6:
        return False
    d = _osa_distance(t, c)
    return d <= 1 or (d == 2 and len(t) >= 10 and len(t) == len(c))


def street_match_kind(query: str, candidate: str) -> str | None:
    """``"exact"`` / ``"fuzzy"`` / ``None`` – how well ``candidate`` names ``query``.

    Every significant token of ``query`` must appear in ``candidate``
    (case-, diacritic-, prefix- and title-insensitive). Short query tokens
    (≤ 3 chars, e.g. initials "J") may match by prefix. ``fuzzy`` means at
    least one token only matched within a small edit distance (typos in the
    source).
    """
    q, c = street_tokens(query), street_tokens(candidate)
    if not q or not c:
        return None
    kind = "exact"
    for t in q:
        if t in c:
            continue
        if len(t) <= 3 and not t.isdigit() and any(x.startswith(t) for x in c):
            continue
        if any(_fuzzy_token(t, x) for x in c):
            kind = "fuzzy"
            continue
        return None
    return kind


def street_matches(query: str, candidate: str, fuzzy: bool = False) -> bool:
    """True if ``candidate`` names the street ``query`` (see :func:`street_match_kind`).

    Rejects look-alikes such as "Mińska" vs "Pińska"; typo-tolerant matching
    only with ``fuzzy=True``.
    """
    kind = street_match_kind(query, candidate)
    return kind == "exact" or (fuzzy and kind == "fuzzy")


def _norm_number(n: str | None) -> str:
    return re.sub(r"\s+", "", _fold(str(n or "")))


def number_matches(query: str | None, candidate: str | None) -> bool:
    """House numbers equal ignoring case/spaces ("53a" == "53A")."""
    return bool(_norm_number(query)) and _norm_number(query) == _norm_number(candidate)


def _base_number(n: str | None) -> str | None:
    """Leading numeric part of a house number ("3A" → "3", "46/48" → "46")."""
    m = re.match(r"\s*(\d+)", str(n or ""))
    return m.group(1) if m else None


def clean_street(street: str) -> str:
    """Street text suitable for a UUG query.

    Drops quotes, a leading "ul."/"ulica", place names and parenthesised
    remarks; puts a space after abbreviations ("gen.Fieldorfa" → "gen.
    Fieldorfa") and closes up spaced hyphens ("Nowaka -Jeziorańskiego").
    UUG answers "Blad zapytania." to some punctuation, so keep it plain.
    """
    s = re.sub(r"[„”\"“‟'`’]", " ", street or "")
    s = re.sub(r"\([^)]*\)", " ", s)
    s = re.sub(r"\.(?=[^\s\d.,;/-])", ". ", s)
    s = re.sub(r"\s*-\s*", "-", s)
    vicinity = re.match(r"^\s*(w\s+)?(rejon(ie)?|okolic[ay]?)\s+((ul\.?|ulicy|ulic|al\.?|alei)\s+)?", s, re.IGNORECASE)
    if vicinity:
        # "w rejonie ulicy Chodakowskiej" → "Chodakowska" (genitive → nominative)
        s = s[vicinity.end():]
        s = re.sub(r"(?<=[scz]k)iej\b", "a", s)
    s = re.sub(r"^\s*(ul\.?|ulica)\s+", "", s, flags=re.IGNORECASE)
    s = re.sub(r"\b(Warszawa|Praga-Po[łl]udnie|Praga Po[łl]udnie)\b", " ", s, flags=re.IGNORECASE)
    s = re.sub(r"\s+", " ", s).strip(" ,;-")
    return s


def street_query_variants(street: str) -> list[str]:
    """Query spellings to try, best first.

    UUG is picky: "Gen. Fieldorfa Nila" and "Jana Nowaka Jeziorańskiego" find
    nothing, while "Fieldorfa" and "Jana Nowaka-Jeziorańskiego" do.
    """
    base = clean_street(street)
    if not base:
        return []
    variants = [base]
    words = base.split()
    no_titles = [w for w in words if _fold(w).strip(".") not in _TITLES]
    if no_titles and len(no_titles) != len(words):
        variants.append(" ".join(no_titles))
    if len(no_titles) >= 2 and all(w.isalpha() and len(w) >= 3 for w in no_titles[-2:]):
        # double surnames: "Jana Nowaka Jeziorańskiego" → "Jana Nowaka-Jeziorańskiego"
        variants.append(" ".join(no_titles[:-2] + [no_titles[-2] + "-" + no_titles[-1]]))
    longest = max(no_titles, key=len) if no_titles else ""
    if len(no_titles) >= 2 and len(longest) >= 5:
        variants.append(longest)
    seen, out = set(), []
    for v in variants:
        if v and v.lower() not in seen:
            seen.add(v.lower())
            out.append(v)
    return out


def parse_uug_response(data: dict) -> tuple[str, list[dict]]:
    """Normalise a UUG ``GetAddress`` JSON response.

    Returns ``(type, candidates)``; each candidate has ``street``, ``number``,
    ``lon``, ``lat``, ``accuracy`` and, for street results, the street
    ``geometry`` (GeoJSON, simplified to ~1 m and rounded to 6 decimals).
    Raises ``ValueError`` for malformed responses.
    """
    if not isinstance(data, dict):
        raise ValueError("UUG response is not an object")
    rtype = data.get("type") or "unknown"
    results = data.get("results") or {}
    if isinstance(results, list):
        items = results
    elif isinstance(results, dict):
        items = [results[k] for k in sorted(results, key=lambda k: int(k) if str(k).isdigit() else 0)]
    else:
        raise ValueError("unexpected UUG results")
    cands = []
    for it in items:
        try:
            lon, lat = float(it["x"]), float(it["y"])
        except (KeyError, TypeError, ValueError):
            continue
        cand = {
            "street": (it.get("street") or "").strip() or None,
            "number": (str(it["number"]).strip() if it.get("number") not in (None, "") else None),
            "city": it.get("city"),
            "code": it.get("code"),
            "simc": it.get("simc"),
            "ulic": it.get("ulic"),
            "lon": lon,
            "lat": lat,
            "accuracy": float(it["accuracy"]) if it.get("accuracy") not in (None, "") else None,
        }
        wkt = it.get("geometry_wkt")
        if wkt and not wkt.lstrip().upper().startswith("POINT"):
            try:
                g = geo.parse_wkt(wkt)
                cand["geometry"] = geo.round_geometry(geo.simplify_geometry(g, 1.0), SITE_DECIMALS)
            except ValueError:
                pass
        cands.append(cand)
    return rtype, cands


def uug_query(query: str, cache: dict, session, online: bool = True, *, refresh_misses: bool = False,
              max_age_days: float = MISS_TTL_DAYS, now: datetime | None = None, stats: dict | None = None) -> dict:
    """Cached UUG ``GetAddress`` call for a full query string ("Warszawa, Mińska 46")."""
    now = now or _now()
    entry = cache.get(query)
    if _is_fresh(entry, now, refresh_misses, max_age_days):
        return entry
    if not online or session is None:
        return entry or {"status": "error", "error": "not cached (offline)", "candidates": []}
    if stats is not None:
        stats["uug_requests"] = stats.get("uug_requests", 0) + 1
    try:
        resp = session.get(UUG_URL, params={"request": "GetAddress", "address": query, "srid": "4326"}, timeout=30)
        if resp.status_code != 200:
            raise ValueError(f"HTTP {resp.status_code}")
        text = (resp.text or "").strip()
        if text.lower().startswith("blad zapytania") or text.lower().startswith("błąd zapytania"):
            # Deterministic rejection of the query text itself: cache as a miss.
            entry = {"status": "missing", "type": "invalid-query", "candidates": [], "fetched_at": _iso(now)}
            cache[query] = entry
            return entry
        rtype, cands = parse_uug_response(resp.json())
    except Exception as exc:  # noqa: BLE001 - not cached, retried next run
        if stats is not None:
            stats["uug_errors"] = stats.get("uug_errors", 0) + 1
            stats.setdefault("uug_error_examples", [])
            if len(stats["uug_error_examples"]) < 10:
                stats["uug_error_examples"].append(f"{query}: {type(exc).__name__}: {exc}"[:200])
        return {"status": "error", "error": f"{type(exc).__name__}: {exc}"[:300], "candidates": []}
    entry = {"status": "ok" if cands else "missing", "type": rtype, "candidates": cands, "fetched_at": _iso(now)}
    cache[query] = entry
    return entry


def _near_district(pt, district: dict | None, buffer_m: float = DISTRICT_BUFFER_M) -> bool:
    if district is None:
        return True
    return geo.distance_to_polygon_m(pt, district) <= buffer_m


_STREET_POINT_MEMO: dict = {}


def _street_point(cand: dict, district: dict | None) -> list[float] | None:
    """Representative in-district point of a UUG street candidate.

    UUG's own point is used when it lies in the district; otherwise the street
    geometry is clipped to the district (+buffer) and the midpoint along its
    longest inside part is used. ``None`` if the street never enters it.
    """
    pt = [cand["lon"], cand["lat"]]
    if _near_district(pt, district):
        return pt
    g = cand.get("geometry")
    if not g or district is None:
        return None
    key = (
        cand.get("simc"), cand.get("ulic"), cand.get("street"), cand["lon"], cand["lat"],
        tuple(geo.bbox(district)), len(geo.polygons_of(district)),
    )
    if key in _STREET_POINT_MEMO:
        return _STREET_POINT_MEMO[key]
    result = None
    if g["type"] in ("Polygon", "MultiPolygon"):
        c = geo.centroid(g)
        result = c if _near_district(c, district) else None
    else:
        parts = geo.lines_inside(g, district, DISTRICT_BUFFER_M)
        if parts:
            longest = max(parts, key=lambda p: (len(p) > 1, sum(geo.haversine_m(a, b) for a, b in zip(p, p[1:]))))
            result = geo.midpoint_along([longest])
    _STREET_POINT_MEMO[key] = result
    return result


def _pick(cands: Iterable[tuple[dict, list[float], str]]) -> tuple[dict, list[float], str] | None:
    """Best validated ``(candidate, point, match_kind)``.

    Exact name matches beat fuzzy ones, streets beat roundabouts/squares,
    then UUG's accuracy decides.
    """
    best = None
    for cand, pt, kind in cands:
        name = _fold(cand.get("street") or "")
        rank = (
            kind == "exact",
            0 if re.match(r"(rondo|plac|skwer|most)\b", name) else 1,
            cand.get("accuracy") or 0.0,
        )
        if best is None or rank > best[0]:
            best = (rank, cand, pt, kind)
    return (best[1], best[2], best[3]) if best else None


def _fuzzy_note(kind: str, cand: dict) -> str | None:
    if kind != "fuzzy":
        return None
    return f"nazwa ulicy dopasowana w przybliżeniu ({cand.get('street')})"


def _address_hit(query: str, street: str, number: str, cache, session, district, online, opts, stats):
    entry = uug_query(query, cache, session, online, stats=stats, **opts)
    valid = []
    for cand in entry.get("candidates", []):
        if cand.get("number") is None or not number_matches(number, cand["number"]):
            continue
        kind = street_match_kind(street, cand.get("street") or "")
        if kind is None:
            continue
        pt = [cand["lon"], cand["lat"]]
        if not _near_district(pt, district):
            if stats is not None:
                stats["uug_rejected_outside"] = stats.get("uug_rejected_outside", 0) + 1
            continue
        valid.append((cand, pt, kind))
    return _pick(valid)


def _street_hit(street: str, cache, session, district, online, opts, stats):
    """Find the street in UUG trying spelling variants: ``(cand, point, variant, kind)``."""
    fuzzy_hit = None
    for variant in street_query_variants(street):
        entry = uug_query(f"{CITY}, {variant}", cache, session, online, stats=stats, **opts)
        valid = []
        for cand in entry.get("candidates", []):
            if cand.get("number") is not None:
                continue  # address point, not a street
            kind = street_match_kind(street, cand.get("street") or "")
            if kind is None:
                continue
            pt = _street_point(cand, district)
            if pt is None:
                if stats is not None:
                    stats["uug_rejected_outside"] = stats.get("uug_rejected_outside", 0) + 1
                continue
            valid.append((cand, pt, kind))
        hit = _pick(valid)
        if hit and hit[2] == "exact":
            return hit[0], hit[1], variant, "exact"
        if hit and fuzzy_hit is None:
            fuzzy_hit = (hit[0], hit[1], variant, "fuzzy")
    return fuzzy_hit


def _result(pt, method, cand, query, note=None) -> dict:
    matched = cand.get("street") or ""
    if cand.get("number"):
        matched += f" {cand['number']}"
    return {
        "lat": round(pt[1], 7),
        "lon": round(pt[0], 7),
        "method": method,
        "matched": matched.strip(),
        "accuracy": cand.get("accuracy"),
        "query": query,
        "note": note,
    }


def geocode_address(
    street: str | None,
    number: str | None,
    cache: dict,
    session,
    district_polygon: dict | None,
    online: bool = True,
    *,
    refresh_misses: bool = False,
    max_age_days: float = MISS_TTL_DAYS,
    stats: dict | None = None,
) -> dict | None:
    """Geocode "street [number]" in Warsaw with GUGiK UUG, validated.

    Returns ``{"lat", "lon", "method": "address"|"street", "matched",
    "accuracy", "query", "note"}`` or ``None``. ``method`` is ``address`` for
    an exact house number (or its numeric base, e.g. 3 for "3A", with a note)
    and ``street`` for a street-level fallback. Candidates whose street name or
    number differ, or which lie outside ``district_polygon`` (+50 m), are
    rejected – UUG happily returns "Pińska 46" for "Mińska 46".
    """
    street = clean_street(street or "")
    if not street:
        return None
    opts = {"refresh_misses": refresh_misses, "max_age_days": max_age_days}
    variants = street_query_variants(street)
    number = (number or "").strip() or None

    if number:
        q = f"{CITY}, {variants[0]} {number}"
        hit = _address_hit(q, street, number, cache, session, district_polygon, online, opts, stats)
        if hit:
            return _result(hit[1], "address", hit[0], q, _fuzzy_note(hit[2], hit[0]))

    found = _street_hit(street, cache, session, district_polygon, online, opts, stats)
    if number:
        spelling = found[2] if found else variants[0]
        if spelling != variants[0]:
            q = f"{CITY}, {spelling} {number}"
            hit = _address_hit(q, street, number, cache, session, district_polygon, online, opts, stats)
            if hit:
                return _result(hit[1], "address", hit[0], q, _fuzzy_note(hit[2], hit[0]))
        base = _base_number(number)
        if base and _norm_number(base) != _norm_number(number):
            q = f"{CITY}, {spelling} {base}"
            hit = _address_hit(q, street, base, cache, session, district_polygon, online, opts, stats)
            if hit:
                note = _join_notes([f"lokalizacja przybliżona – budynek nr {base}", _fuzzy_note(hit[2], hit[0])])
                return _result(hit[1], "address", hit[0], q, note)
    if found:
        cand, pt, variant, kind = found
        res = _result(pt, "street", cand, f"{CITY}, {variant}", _join_notes([NOTE_STREET, _fuzzy_note(kind, cand)]))
        if cand.get("geometry"):
            res["street_geometry"] = cand["geometry"]   # the street axis, for clipping to a precinct (not stored)
        return res
    nominative = _nominative(street)
    if nominative != street:
        # "w rejonie ulic Rybnej" → "Rybna": only as a fallback, since some
        # official names are genitive ("Bitwy Warszawskiej 1920 r.").
        return geocode_address(nominative, number, cache, session, district_polygon, online,
                               refresh_misses=refresh_misses, max_age_days=max_age_days, stats=stats)
    return None


def _nominative(street: str) -> str:
    """Crude genitive → nominative for feminine street adjectives (-skiej → -ska, -nej → -na, -wej → -wa)."""
    s = re.sub(r"(?<=[scz]k)iej\b", "a", street)
    s = re.sub(r"(?<=[nw])ej\b", "a", s)
    return s


_ADDR_RE = re.compile(r"^(?P<street>.*?\S)[\s,]+(?P<number>\d+\s*[A-Za-z]?(?:\s*[/-]\s*\d+\s*[A-Za-z]?)?)\s*$")


def split_address(text: str) -> tuple[str, str | None]:
    """``"Mińska 46"`` → ``("Mińska", "46")``; ``"11 Listopada"`` → ``("11 Listopada", None)``."""
    m = _ADDR_RE.match(text.strip())
    if m and re.search(r"[A-Za-zÀ-ž]", m.group("street")):
        return m.group("street"), m.group("number").replace(" ", "")
    return text.strip(), None


_STREET_SPLIT_RE = re.compile(
    r"\s*(?:/|;|,|\+|\bróg\b|\brog\b|\bnaroż\w*|\s+i\s+|\s+oraz\s+|\s+przy\s+)\s*", re.IGNORECASE
)


def _split_streets(street: str, number: str | None) -> list[tuple[str, str | None]]:
    """Split "A / B", "A i B", "A 20, B" into ``[(street, number), ...]``.

    A part's own trailing house number wins; the record's number applies to
    the first part only. Parts without letters ("23" in "Serocka 21,23") are
    dropped.
    """
    out = []
    for k, part in enumerate(_STREET_SPLIT_RE.split(street or "")):
        part = part.strip(" ,.")
        if not part or not re.search(r"[^\W\d_]{3,}", part):
            continue
        st, num = split_address(part)
        if num is None and not out:
            num = number
        if clean_street(st):
            out.append((st, num))
    return out


def geocode_record_address(address: dict | None, cache, session, district, online=True, *, opts=None, stats=None):
    """Geocode a record's ``address`` dict (``street`` + ``number``).

    Tries the street as given first. If that yields no exact address and the
    text names several streets ("Mińska / Głucha", "Drwęcka i Siennicka",
    "Mińska 20, Głucha"), each part is tried: the first exact address wins,
    else the crossing of the first two streets found (≤ 60 m apart), else the
    first street found.

    The streets come from ``address["parts"]`` when the normaliser provides
    two or more (it keeps only the first street in ``address["street"]``);
    otherwise ``street`` itself is split on the separators.
    """
    if not address:
        return None
    street, number = address.get("street"), address.get("number")
    if not street or not isinstance(street, str):
        return None
    opts = opts or {}
    whole = geocode_address(street, number, cache, session, district, online, stats=stats, **opts)
    if whole and whole["method"] == "address":
        return whole
    explicit = [(p["street"], p.get("number")) for p in address.get("parts") or []
                if isinstance(p, dict) and isinstance(p.get("street"), str) and p["street"].strip()]
    if len(explicit) >= 2:
        parts = explicit
    else:
        parts = _split_streets(street, number)
        if len(parts) < 2:
            return whole
        if whole:
            return whole  # the full text matched a real street name containing a separator
    street_hits = []
    for st, num in parts:
        r = geocode_address(st, num, cache, session, district, online, stats=stats, **opts)
        if r and r["method"] == "address":
            return r
        if r:
            street_hits.append((st, r))
    if len(street_hits) >= 2:
        found = []
        for st, _ in street_hits[:2]:
            hit = _street_hit(st, cache, session, district, online, opts, stats)
            if hit and hit[0].get("geometry"):
                found.append(hit)
        if len(found) == 2:
            ca = geo.closest_approach(found[0][0]["geometry"], found[1][0]["geometry"])
            if ca and ca[1] <= INTERSECTION_MAX_M and _near_district(ca[0], district):
                cand = dict(found[0][0])
                cand["street"] = f"{found[0][0].get('street')} / {found[1][0].get('street')}"
                return _result(ca[0], "street", cand, " | ".join(f"{CITY}, {h[2]}" for h in found), NOTE_CROSSING)
    return street_hits[0][1] if street_hits else None


# ============================================================ record locating


def _obreb_from_id(pid: str) -> tuple[str | None, str | None]:
    """``146507_8.0124.46/4`` → ``("3-01-24", "46/4")``."""
    parts = pid.split(".", 2)
    if len(parts) != 3 or len(parts[1]) != 4:
        return None, None
    o = parts[1]
    return f"3-{o[:2]}-{o[2:]}", parts[2]


def _bbox_gap_m(a: list[float], b: list[float]) -> float:
    """Approximate gap in metres between two lon/lat bboxes (0 if overlapping)."""
    lat = (a[1] + a[3] + b[1] + b[3]) / 4
    dx = max(0.0, b[0] - a[2], a[0] - b[2]) * 111_320 * math.cos(math.radians(lat))
    dy = max(0.0, b[1] - a[3], a[1] - b[3]) * 110_574
    return math.hypot(dx, dy)


def cluster_parcels(items: list[dict], gap_m: float = CLUSTER_GAP_M) -> list[list[dict]]:
    """Single-linkage clusters of parcel entries whose bboxes are ≤ ``gap_m`` apart.

    Returned largest first (by parcel count, then total area).
    """
    n = len(items)
    parent = list(range(n))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i in range(n):
        for j in range(i + 1, n):
            if _bbox_gap_m(items[i]["bbox"], items[j]["bbox"]) <= gap_m:
                parent[find(i)] = find(j)
    groups: dict[int, list[dict]] = {}
    for i in range(n):
        groups.setdefault(find(i), []).append(items[i])
    return sorted(groups.values(), key=lambda g: (len(g), sum(x.get("area_m2") or 0 for x in g)), reverse=True)


def _empty_geo(note=None) -> dict:
    return {"lat": None, "lon": None, "method": None, "parcels_found": [], "bbox": None, "note": note}


def _join_notes(notes: list[str | None]) -> str | None:
    notes = [n for n in notes if n]
    return "; ".join(dict.fromkeys(notes)) or None


def known_subparcels(pids: Iterable[str], results: dict, cache: dict,
                     named: set[str] | None = None) -> dict[str, list[str]]:
    """Cached sub-parcels of whole-number parcels that ULDK no longer knows.

    Subdividing parcel ``3`` creates ``3/1``, ``3/2``, … in the same precinct, and ULDK only
    knows current parcels. When a whole-number parcel is ``missing`` and some of its
    sub-parcels are in the cache (because other records name them), they stand in for it:
    ``{"146507_8.0203.3": ["146507_8.0203.3/1", "146507_8.0203.3/2", …]}`` (natural order).
    Parcels whose number already has a "/" never qualify (their split gets new numbers).
    ``named`` limits the sub-parcels to these ids (the parcels the records name), so parcels the
    cache learnt otherwise (under an address point) never change another record's location.
    """
    out: dict[str, list[str]] = {}
    for pid in pids:
        if (results.get(pid) or {}).get("status") != "missing" or "/" in pid.split(".", 2)[-1]:
            continue
        prefix = pid + "/"
        kids = [k for k, v in cache.items()
                if k.startswith(prefix) and k[len(prefix):].isdigit() and (v or {}).get("status") == "ok"
                and (named is None or k in named)]
        if kids:
            out[pid] = sorted(kids, key=lambda k: int(k[len(prefix):]))
    return out


def _interior_point(geometry: dict, hint: list[float]) -> list[float]:
    """A point inside ``geometry`` near ``hint``: the middle of the widest inside stretch of the
    horizontal line through ``hint`` (or, if that line misses the shape, through the middle of its
    bbox). Used when the centroid of a concave parcel (a bent road, an L-shaped plot) lies outside it.
    """
    rings = [ring for poly in geo.polygons_of(geometry) for ring in poly]
    box = geo.bbox(geometry)
    for y in (hint[1], (box[1] + box[3]) / 2):
        xs = sorted(
            a[0] + (y - a[1]) * (b[0] - a[0]) / (b[1] - a[1])
            for ring in rings for a, b in pairwise(ring)
            if (a[1] > y) != (b[1] > y)
        )
        spans = [(xs[i], xs[i + 1]) for i in range(0, len(xs) - 1, 2)]   # even-odd: inside between pairs
        if spans:
            x0, x1 = max(spans, key=lambda s: s[1] - s[0])
            return [(x0 + x1) / 2, y]
    return list(hint)


def _point_on_largest_parcel(items: list[dict], area_index) -> list[float]:
    """Centroid of the largest of ``items`` (preferring parcels inside the district), moved onto the
    parcel itself if it is concave and its centroid falls outside it."""
    inside = [it for it in items
              if not area_index or area_index.in_district(it["centroid"], DISTRICT_BUFFER_M) is not False]
    largest = max(inside or items, key=lambda it: (it.get("area_m2") or 0.0, it["id"]))
    pt = list(largest["centroid"])
    if largest.get("geometry") and not geo.point_in_polygon(pt, largest["geometry"]):
        pt = _interior_point(largest["geometry"], pt)
    return pt


def _cluster_point(items: list[dict], area_index) -> tuple[list[float], list[dict], int, bool]:
    """``(point, main cluster, number of clusters, moved to the largest parcel)`` for parcel entries."""
    clusters = cluster_parcels(items)
    main = clusters[0]
    pt = geo.weighted_centroid((it["centroid"], it.get("area_m2") or 0.0) for it in main)
    if any(it.get("geometry") and geo.point_in_polygon(pt, it["geometry"]) for it in items):
        return pt, main, len(clusters), False
    return _point_on_largest_parcel(main, area_index), main, len(clusters), True


NOTE_PARCELS_IN_DISTRICT = "część działek leży poza dzielnicą – punkt wyznaczono z działek na Pradze-Południe"
#: stats counters :func:`_parcel_geo` increments (restored when a record is located a second time)
_PARCEL_GEO_COUNTERS = ("records_parcels_in_district_only", "outside_district_discarded",
                        "records_point_on_largest_parcel", "records_spread_parcels", "records_via_subparcels")


def _parcel_geo(rid, pids, found, results, area_index, notes, stats, stand_ins=None, incomplete=()) -> dict | None:
    """``geo`` from the found parcels, or ``None`` if their centroid is outside the district.

    The point is the area-weighted centroid of the found parcels (of the largest cluster when they
    are far apart). When that centroid lies on none of them – two separate plots, a bent road – the
    point goes to the largest parcel instead (its centroid, or a point on it if it is concave), so a
    marker never sits on a neighbour's plot. When the point falls outside the district but some of
    the parcels lie in it (a sewer from Rembertów, a bridge from Śródmieście), the point is taken from
    those parcels alone (with a note).

    ``stand_ins`` maps a missing (subdivided) parcel to its known sub-parcels, which are used
    in its place (see :func:`known_subparcels`); for a number the source cut short (``incomplete``,
    "12/") the note says so instead of calling the parcel subdivided.
    """
    stand_ins = stand_ins or {}
    used = list(found) + [k for kids in stand_ins.values() for k in kids if k not in found]
    items = [dict(results[p], id=p) for p in used]
    pt, main, n_clusters, moved = _cluster_point(items, area_index)
    if area_index and area_index.in_district(pt, DISTRICT_BUFFER_M) is False:
        inside = [it for it in items if area_index.in_district(it["centroid"], DISTRICT_BUFFER_M)]
        if inside and len(inside) < len(items):
            pt, main, n_clusters, moved = _cluster_point(inside, area_index)
            notes.append(NOTE_PARCELS_IN_DISTRICT)
            stats["records_parcels_in_district_only"] = stats.get("records_parcels_in_district_only", 0) + 1
    if area_index and area_index.in_district(pt, DISTRICT_BUFFER_M) is False:
        stats["outside_district_discarded"] += 1
        stats["warnings"].append(f"{rid}: parcel centroid {pt} outside Praga-Południe – discarded")
        notes.append("działki poza granicami dzielnicy – pominięto")
        return None
    if moved:
        stats["records_point_on_largest_parcel"] = stats.get("records_point_on_largest_parcel", 0) + 1
    if n_clusters > 1:
        stats["records_spread_parcels"] += 1
        notes.append(
            f"działki odległe od siebie o ponad 1 km – punkt dla największej grupy ({len(main)} z {len(used)})")
    for parent, kids in stand_ins.items():
        obreb, number = _obreb_from_id(parent)
        parts = ", ".join(_obreb_from_id(k)[1] for k in kids)
        if parent in incomplete:
            notes.append(f"numer działki w źródle niepełny („{number}/”, obręb {obreb}) – przyjęto działki "
                         f"{number}/… znane z innych wpisów: {parts}")
        else:
            notes.append(f"działki {number} (obręb {obreb}) nie ma już w ewidencji (została podzielona) – "
                         f"przyjęto jej części znane z innych wpisów: {parts}")
    if stand_ins:
        stats["records_via_subparcels"] = stats.get("records_via_subparcels", 0) + 1
    if len(found) + len(stand_ins) < len(pids):
        notes.append(f"w ewidencji gruntów (ULDK) znaleziono {len(found)} z {len(pids)} działek")
    return {
        "lat": round(pt[1], 7),
        "lon": round(pt[0], 7),
        "method": "parcel",
        "parcels_found": used,
        "bbox": [round(v, 6) for v in geo.bbox_union(it["bbox"] for it in items)],
        "note": None,
    }


def _address_label(address: dict) -> str:
    return address.get("display") or f"{address.get('street')} {address.get('number') or ''}".strip()


def _cross_check(address, found, results, cache, session, district, online, opts, stats) -> dict | None:
    """The record's exact address when it lies > 300 m from all of its found parcels:
    ``{"point", "gap", "label", "note"}`` (else None)."""
    address = address or {}
    if not (address.get("street") and address.get("number")):
        return None
    hit = geocode_record_address(address, cache, session, district, online, opts=opts, stats=stats)
    if not hit or hit["method"] != "address" or hit.get("note"):
        return None  # only trust exact, unambiguous address points
    gap = min(geo.distance_to_polygon_m([hit["lon"], hit["lat"]], results[p]["geometry"]) for p in found)
    if gap <= ADDRESS_CONFLICT_M:
        return None
    label = _address_label(address)
    return {"point": [hit["lon"], hit["lat"]], "gap": gap, "label": label,
            "note": f"adres {label} leży ok. {round(gap, -1):.0f} m od wskazanych działek"}


def _parcel_base(number: str) -> str:
    return number.split("/", 1)[0]


def _address_parcel_match(pids: list[str], point: list[float], cache: dict, session, online: bool, opts: dict) -> dict | None:
    """The parcel under a validated address point (ULDK ``GetParcelByXY``) compared with the stated parcels.

    None when ULDK has no parcel there (or offline without a cached answer), else ``{"kind", "at", "source",
    "rewrites"}`` with ``kind``:

    * ``same`` – the point lies in a precinct the record names (a large site: the stated parcels stand);
    * ``typo`` – the parcel at the point has a stated number (``35``) – or is a part of a stated whole-number
      parcel that ULDK no longer has there (``137/2`` for ``137``) – in another precinct: the source's
      precinct is wrong. ``rewrites`` = {stated id: id in the precinct at the address} for that parcel and
      the other stated parcels of its precinct that exist in the new one (``source`` = the matched one);
    * ``base`` – only the number before "/" matches (``43/7`` for ``43/1``): a hint, nothing rewritten;
    * ``other`` – no match: address and parcels contradict each other.
    """
    at = parcel_at_point(point[0], point[1], cache, session, online, **opts)
    if at.get("status") != "ok":
        return None
    u_unit, u_code, u_num = at["id"].split(".", 2)
    stated = [(p, *p.split(".", 2)) for p in pids if p.count(".") >= 2]
    if any((unit, code) == (u_unit, u_code) for _, unit, code, _ in stated):
        return {"kind": "same", "at": at["id"], "source": None, "rewrites": {}}
    source = next((s for s in stated if s[1] == u_unit and s[3] == u_num), None)
    if source is None:
        whole = next((s for s in stated if s[1] == u_unit and "/" not in s[3] and u_num.startswith(s[3] + "/")), None)
        if whole is not None:
            pid = f"{u_unit}.{u_code}.{whole[3]}"
            if lookup_parcels([pid], cache, session, online, **opts)[pid]["status"] == "missing":
                source = whole   # "137" was subdivided there; "137/2" is one of its parts
    if source is None:
        base = next((s for s in stated if s[1] == u_unit and _parcel_base(s[3]) == _parcel_base(u_num)), None)
        return {"kind": "base" if base else "other", "at": at["id"], "source": base[0] if base else None,
                "rewrites": {}}
    moved = {s[0]: f"{u_unit}.{u_code}.{s[3]}" for s in stated if (s[1], s[2]) == (source[1], source[2])}
    others = [new for old, new in moved.items() if old != source[0]]
    look = lookup_parcels(others, cache, session, online, **opts) if others else {}
    rewrites = {old: new for old, new in moved.items() if old == source[0] or look[new]["status"] == "ok"}
    return {"kind": "typo", "at": at["id"], "source": source[0], "rewrites": rewrites}


def _densify(line: list, step_m: float = 20.0) -> list[list[float]]:
    """Vertices every ≤ ``step_m`` along a line (clipping by vertices needs them on a long straight street)."""
    out = [list(line[0])]
    for a, b in pairwise(line):
        n = max(1, math.ceil(geo.haversine_m(a, b) / step_m))
        out.extend([a[0] + k / n * (b[0] - a[0]), a[1] + k / n * (b[1] - a[1])] for k in range(1, n + 1))
    return out


def _length_m(line: list) -> float:
    return sum(geo.haversine_m(a, b) for a, b in pairwise(line))


def _street_in_precincts(street: dict, precincts: list[dict]) -> tuple[list[float], float] | None:
    """``(point, uncertainty_m)``: the middle of the longest stretch of the street axis inside the precincts and
    the largest distance from it to that stretch; None if the street does not cross them."""
    union = _merge_polygons(precincts)
    dense = {"type": "MultiLineString", "coordinates": [_densify(ln) for ln in geo.lines_of(street) if len(ln) > 1]}
    parts = [part for part in geo.lines_inside(dense, union, 0.0) if len(part) > 1]
    if not parts:
        return None
    longest = max(parts, key=_length_m)
    pt = geo.midpoint_along([longest])
    return pt, max(geo.haversine_m(pt, v) for v in longest)


AREA_BORDER_M = 25.0


def _precinct_area(pt: list[float], precincts: list[dict], area_index) -> str | None:
    """Neighbourhood for a street point on (or next to) a neighbourhood border: the one ≥ 90 % of the stated
    precincts lie in (12 × 12 grid sample), when the point is within 25 m of it; else None (normal lookup)."""
    union = _merge_polygons(precincts)
    b = geo.bbox(union)
    counts: dict[str | None, int] = {}
    for i in range(12):
        for j in range(12):
            q = [b[0] + (i + 0.5) * (b[2] - b[0]) / 12, b[1] + (j + 0.5) * (b[3] - b[1]) / 12]
            if geo.point_in_polygon(q, union):
                slug = area_index.locate(q, 0.0)
                counts[slug] = counts.get(slug, 0) + 1
    total = sum(counts.values())
    if not total:
        return None
    slug, n = max(counts.items(), key=lambda kv: (kv[1], kv[0] or ""))
    if not slug or n < 0.9 * total or area_index.locate(pt) == slug:
        return None
    shape = next((g for s, _, g in area_index.areas if s == slug), None)
    return slug if shape is not None and geo.distance_to_polygon_m(pt, shape) <= AREA_BORDER_M else None


def _street_uncertainty(pt: list[float], street: dict, district: dict | None) -> float | None:
    """Largest distance from a street point to the street's axis in the district (how far off it may be)."""
    parts = geo.lines_inside(street, district, DISTRICT_BUFFER_M) if district else geo.lines_of(street)
    vertices = [v for part in parts for v in part]
    return max(geo.haversine_m(pt, v) for v in vertices) if vertices else None


def _address_geo(address, pids, found, results, cache, session, district, online, opts, stats, notes) -> tuple[dict, dict | None]:
    """``(geo, address hit)`` from the address (exact / street / crossing), or an empty ``geo``."""
    hit = geocode_record_address(address, cache, session, district, online, opts=opts, stats=stats)
    if pids and not found:
        errors = [p for p in pids if results.get(p, {}).get("status") == "error"]
        notes.append(
            "nie udało się pobrać działek z ewidencji gruntów (ULDK)" if len(errors) == len(pids)
            else NOTE_PARCELS_NOT_FOUND
        )
    if hit:
        notes.append(hit.get("note"))
        return {"lat": hit["lat"], "lon": hit["lon"], "method": hit["method"], "parcels_found": [],
                "bbox": None, "note": None}, hit
    if not pids and not (address or {}).get("street"):
        notes.append("brak działek i adresu w źródle")
    else:
        notes.append("nie udało się ustalić lokalizacji")
    return _empty_geo(), None


def locate_records(
    records: list[dict],
    cache_dir: str = "data/cache",
    online: bool = True,
    log: Callable = print,
    *,
    session=None,
    area_index: "areas_mod.AreaIndex | None" = None,
    areas_out: str = "site/data/areas.geojson",
    refresh_misses: bool = False,
    cross_check: bool = True,
) -> dict:
    """Fill ``record["geo"]`` and ``record["area"]`` in place for every record.

    Returns ``{"parcels_geojson": FeatureCollection, "stats": {...}}`` where the
    FeatureCollection holds every found parcel referenced by a record
    (properties ``id``, ``obreb``, ``number``, ``records``).

    With ``cross_check`` (default) records located by parcels that also give
    a street + house number are geocoded too; if that exact address point lies
    more than 300 m from every found parcel, ULDK is asked which parcel lies
    under the address (``GetParcelByXY``, cached as ``xy:<lon>,<lat>``):

    * it has a stated number in another precinct (``35`` in 3-05-26 for "35
      3-06-03") → the source's precinct is wrong: the record's parcel ids are
      rewritten (also the other stated parcels of that precinct that exist in
      the new one), it is located by them and gets a warning;
    * it lies in a stated precinct (a large site) → the parcel point and the
      distance note stay;
    * otherwise → the parcel point stays with the note and ``geo.conflict = true``.

    The same check runs for records none of whose parcels ULDK knows but whose
    exact address is found: a same-number match rewrites the ids and locates the
    record by the parcels; a match of the number before "/" only adds a hint.
    So besides ``geo``/``area`` this may change ``parcels[].id/obreb`` and append
    to ``warnings``.
    """
    t0 = time.monotonic()
    uldk_path = os.path.join(cache_dir, "uldk.json")
    uug_path = os.path.join(cache_dir, "uug.json")
    uldk_cache = load_cache(uldk_path)
    uug_cache = load_cache(uug_path)
    if online and session is None:
        session = PoliteSession()

    warnings: list[str] = []
    if area_index is None:
        area_index = areas_mod.load_areas(cache_dir, areas_out)
        if area_index is None and online:
            try:
                area_index = areas_mod.AreaIndex.from_cache_document(
                    areas_mod.build_areas(cache_dir, areas_out, session=session, online=True, log=log)
                )
            except Exception as exc:  # noqa: BLE001 - keep going without areas
                warnings.append(f"neighbourhood boundaries unavailable: {exc}")
    district = area_index.district if area_index else None
    if district is None:
        warnings.append("district polygon unavailable: points are not validated against Praga-Południe")

    # ---- parcels
    record_pids: list[list[str]] = []
    all_pids: list[str] = []
    seen: set[str] = set()
    for rec in records:
        pids = []
        for p in rec.get("parcels") or []:
            pid = normalize_parcel_id((p or {}).get("id"))
            if pid and pid not in pids:
                pids.append(pid)
                if pid not in seen:
                    seen.add(pid)
                    all_pids.append(pid)
        record_pids.append(pids)

    parcel_meta: dict[str, tuple[str | None, str | None]] = {}
    for rec in records:
        for p in rec.get("parcels") or []:
            pid = normalize_parcel_id((p or {}).get("id"))
            if pid and pid not in parcel_meta:
                parcel_meta[pid] = (p.get("obreb"), p.get("number"))

    results = lookup_parcels(
        all_pids, uldk_cache, session, online, refresh_misses=refresh_misses, log=log,
        checkpoint=lambda: save_cache(uldk_path, uldk_cache),
    )
    if online:
        save_cache(uldk_path, uldk_cache)
    # Subdivided parcels: known sub-parcels (named by records) stand in for a parent ULDK no longer has.
    named = set(all_pids)
    subparcels = known_subparcels(all_pids, results, uldk_cache, named)
    for kids in subparcels.values():
        for k in kids:
            results.setdefault(k, {"geometry": None, "centroid": None, **uldk_cache[k]})

    stats: dict = {
        "records": len(records),
        "methods": {"parcel": 0, "address": 0, "street": 0, "none": 0},
        "parcels_unique": len(all_pids),
        "parcels_ok": sum(1 for p in all_pids if results[p]["status"] == "ok"),
        "parcels_missing": sum(1 for p in all_pids if results[p]["status"] == "missing"),
        "parcels_error": sum(1 for p in all_pids if results[p]["status"] == "error"),
        "records_with_parcels": sum(1 for p in record_pids if p),
        "records_all_parcels_found": 0,
        "records_some_parcels_found": 0,
        "records_no_parcel_found": 0,
        "records_spread_parcels": 0,
        "outside_district_discarded": 0,
        "uug_requests": 0,
        "uug_errors": 0,
        "uug_rejected_outside": 0,
        "address_parcel_conflicts": 0,
        "address_parcel_conflicts_flagged": 0,
        "obreb_corrected_by_address": 0,
        "street_clipped_to_precinct": 0,
        "records_via_subparcels": 0,
        "records_point_on_largest_parcel": 0,
        "records_parcels_in_district_only": 0,
        "with_area": 0,
        "missing_parcel_examples": [p for p in all_pids if results[p]["status"] == "missing"][:20],
        "warnings": warnings,
    }
    opts = {"refresh_misses": refresh_misses}
    parcel_records: dict[str, list[str]] = {}

    def relocate(rec: dict, rid: str, pids: list[str], match: dict, label: str, incomplete: set[str]):
        """``(geo, notes)`` of a record whose source precinct is wrong (the parcel under its exact address has a
        stated number, see :func:`_address_parcel_match`): its parcel ids are rewritten in place and a warning
        added. None (nothing changed) when the corrected parcels cannot be placed."""
        new_pids = list(dict.fromkeys(match["rewrites"].get(p, p) for p in pids))
        fresh = [p for p in new_pids if p not in results]
        if fresh:
            results.update(lookup_parcels(fresh, uldk_cache, session, online, refresh_misses=refresh_misses))
        subs = known_subparcels(new_pids, results, uldk_cache, named | {match["at"]})
        for kids in subs.values():
            for k in kids:
                results.setdefault(k, {"geometry": None, "centroid": None, **uldk_cache[k]})
        found2 = [p for p in new_pids if results[p]["status"] == "ok"]
        if not (found2 or subs):
            return None
        counters, n_warnings = {k: stats[k] for k in _PARCEL_GEO_COUNTERS}, len(stats["warnings"])
        notes2: list[str | None] = []
        g2 = _parcel_geo(rid, new_pids, found2, results, area_index, notes2, stats, subs, incomplete)
        if g2 is None:
            stats.update(counters)
            del stats["warnings"][n_warnings:]
            return None
        for parent, kids in subs.items():   # a part found under the address, not named by another record
            if match["at"] in kids:
                known = ", ".join(_obreb_from_id(k)[1] for k in kids)
                here = (f"przyjęto jej część leżącą pod adresem: {_obreb_from_id(match['at'])[1]}" if len(kids) == 1
                        else f"przyjęto jej części znane z innych wpisów i spod adresu: {known}")
                notes2 = [n.replace(f"przyjęto jej części znane z innych wpisów: {known}", here) if n else n
                          for n in notes2]
        src_obreb, src_number = _obreb_from_id(match["source"])
        for p in rec.get("parcels") or []:
            pid = normalize_parcel_id((p or {}).get("id")) or ""
            if pid == match["source"] and p.get("obreb"):
                src_obreb = p["obreb"]          # as the source writes it ("3-06-03"; a register's "1280")
            new = match["rewrites"].get(pid)
            if new:
                p["id"] = new
                p["obreb"] = _obreb_from_id(new)[0]
                parcel_meta.setdefault(new, (p["obreb"], p.get("number")))
        new_obreb, at_number = _obreb_from_id(match["at"])
        what = src_number if at_number == src_number else f"{at_number} (część działki {src_number})"
        rec.setdefault("warnings", []).append(f"obręb w źródle ({src_obreb}) prawdopodobnie błędny – działka {what} "
                                              f"pod adresem {label} leży w obrębie {new_obreb}")
        stats["obreb_corrected_by_address"] += 1
        return g2, notes2

    for idx, (rec, pids) in enumerate(zip(records, record_pids)):
        rid = rec.get("id") or f"#{idx}"
        found = [p for p in pids if results.get(p, {}).get("status") == "ok"]
        if pids:
            key = "all" if len(found) == len(pids) else "some" if found else "no"
            stats[{"all": "records_all_parcels_found", "some": "records_some_parcels_found",
                   "no": "records_no_parcel_found"}[key]] += 1
        notes: list[str | None] = []
        area: str | None = None   # set when the stated precinct decides a border street point's neighbourhood
        incomplete = {normalize_parcel_id(p.get("id")) for p in rec.get("parcels") or [] if (p or {}).get("incomplete")}
        stand_ins = {p: subparcels[p] for p in pids if p in subparcels}
        if stand_ins and not found:
            # An exact, validated address point beats an approximation of a subdivided parcel.
            hit = geocode_record_address(rec.get("address"), uug_cache, session, district, online,
                                         opts=opts, stats=stats)
            if hit and hit["method"] == "address" and not hit.get("note"):
                stand_ins = {}
        before = {k: stats[k] for k in _PARCEL_GEO_COUNTERS}
        g = (_parcel_geo(rid, pids, found, results, area_index, notes, stats, stand_ins, incomplete)
             if found or stand_ins else None)
        if g is not None:
            conflict = (_cross_check(rec.get("address"), g["parcels_found"], results, uug_cache, session,
                                     district, online, opts, stats) if cross_check else None)
            if conflict:
                # Is the source's precinct wrong? The parcel under the exact address decides (ULDK GetParcelByXY).
                match = _address_parcel_match(pids, conflict["point"], uldk_cache, session, online, opts)
                after = {k: stats[k] for k in _PARCEL_GEO_COUNTERS}
                stats.update(before)
                fixed = relocate(rec, rid, pids, match, conflict["label"], incomplete) if (
                    match and match["kind"] == "typo") else None
                if fixed:
                    g, notes = fixed
                else:
                    stats.update(after)
                    notes.append(conflict["note"])
                    stats["address_parcel_conflicts"] += 1
                    if match and match["kind"] in ("other", "base"):
                        g["conflict"] = True    # the address points to a parcel of another precinct
                        stats["address_parcel_conflicts_flagged"] += 1
        else:
            g, hit = _address_geo(rec.get("address"), pids, found, results, uug_cache, session, district,
                                  online, opts, stats, notes)
            if pids and not found and hit and hit["method"] == "address" and not hit.get("note"):
                # None of the stated parcels exists: the parcel under the exact address may reveal a wrong precinct.
                match = _address_parcel_match(pids, [hit["lon"], hit["lat"]], uldk_cache, session, online, opts)
                fixed = (relocate(rec, rid, pids, match, _address_label(rec.get("address") or {}), incomplete)
                         if match and match["kind"] == "typo" else None)
                if fixed:
                    g, notes = fixed
                elif match and match["kind"] == "base":
                    obreb, number = _obreb_from_id(match["at"])
                    hint = (f"działek nie znaleziono w ewidencji gruntów (ULDK); pod adresem leży działka {number} "
                            f"obr. {obreb} – obręb w źródle prawdopodobnie błędny")
                    notes = [hint if n == NOTE_PARCELS_NOT_FOUND else n for n in notes]
            elif g["method"] == "street" and hit and hit.get("street_geometry"):
                # A whole street is vague: the stated precinct narrows it down (the street's stretch in it).
                ids = sorted({".".join(p.split(".")[:2]) for p in pids if p.startswith(DISTRICT_TERYT + ".")})
                polygons = {r: geom for r in ids if (geom := region_geometry(r, uldk_cache, session, online, **opts))}
                names = ", ".join(_obreb_from_id(f"{r}.x")[0] for r in polygons)
                clipped = _street_in_precincts(hit["street_geometry"], list(polygons.values())) if polygons else None
                if clipped and (not area_index or area_index.in_district(clipped[0], DISTRICT_BUFFER_M) is not False):
                    (lon, lat), uncertainty = clipped
                    g["lat"], g["lon"] = round(lat, 7), round(lon, 7)
                    notes = [n.replace(NOTE_STREET, f"{NOTE_STREET} w obrębie {names}", 1) if n else n for n in notes]
                    stats["street_clipped_to_precinct"] += 1
                else:
                    uncertainty = _street_uncertainty([g["lon"], g["lat"]], hit["street_geometry"], district)
                    if polygons:
                        notes.append(f"ulica nie przechodzi przez obręb z rejestru ({names})")
                if uncertainty is not None:
                    g["uncertainty_m"] = int(round(uncertainty, -1))
                if polygons and area_index:
                    area = _precinct_area([g["lon"], g["lat"]], list(polygons.values()), area_index)
        if g["method"] == "parcel":
            for p in g["parcels_found"]:
                parcel_records.setdefault(p, []).append(rid)
        g["note"] = _join_notes(notes)
        rec["geo"] = g
        stats["methods"][g["method"] or "none"] += 1
        if area is None:
            area = area_index.locate([g["lon"], g["lat"]]) if g["lat"] is not None and area_index else None
        rec["area"] = area
        stats["with_area"] += rec["area"] is not None
        if online and (idx + 1) % 200 == 0:
            save_cache(uug_path, uug_cache)  # checkpoint
            log(f"  located {idx + 1}/{len(records)} records")

    if online:
        save_cache(uug_path, uug_cache)
        save_cache(uldk_path, uldk_cache)   # parcels under address points, corrected precincts

    features = []
    for pid in sorted(parcel_records):
        obreb, number = parcel_meta.get(pid, (None, None))
        o2, n2 = _obreb_from_id(pid)
        features.append(
            {
                "type": "Feature",
                "id": pid,
                "properties": {
                    "id": pid,
                    "obreb": obreb or o2,
                    "number": number or n2,
                    "records": sorted(set(parcel_records[pid])),
                },
                "geometry": geo.round_geometry(results[pid]["geometry"], SITE_DECIMALS),
            }
        )
    stats["parcel_hit_rate"] = round(stats["parcels_ok"] / stats["parcels_unique"], 4) if all_pids else None
    located = stats["records"] - stats["methods"]["none"]
    stats["located_rate"] = round(located / stats["records"], 4) if records else None
    stats["seconds"] = round(time.monotonic() - t0, 1)
    for w in warnings:
        log(f"  geocode warning: {w}")
    m = stats["methods"]
    log(
        f"geocode: {len(records)} records – parcel {m['parcel']}, address {m['address']}, street {m['street']}, "
        f"none {m['none']}; parcels {stats['parcels_ok']}/{stats['parcels_unique']} found in ULDK"
    )
    return {"parcels_geojson": {"type": "FeatureCollection", "features": features}, "stats": stats}


# ======================================================================== CLI

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m pipeline.geocode", description=__doc__.split("\n\n")[0])
    ap.add_argument("--probe", nargs="+", metavar="PARCEL_ID", help="look up parcel ids in ULDK (cached)")
    ap.add_argument("--address", action="append", metavar="ADDR", help='geocode "Street 12" with UUG (repeatable)')
    ap.add_argument("--areas", action="store_true", help="(re)build site/data/areas.geojson")
    ap.add_argument("--refresh", action="store_true", help="with --areas: re-download from Overpass")
    ap.add_argument("--refresh-misses", action="store_true", help="retry cached misses regardless of age")
    ap.add_argument("--offline", action="store_true", help="use caches only")
    ap.add_argument("--cache-dir", default="data/cache")
    ap.add_argument("--areas-out", default="site/data/areas.geojson")
    args = ap.parse_args(argv)
    if not (args.probe or args.address or args.areas):
        ap.print_help()
        return 2
    online = not args.offline
    session = PoliteSession() if online else None

    if args.areas:
        areas_mod.build_areas(args.cache_dir, args.areas_out, session=session, online=online, refresh=args.refresh)
    index = areas_mod.load_areas(args.cache_dir, args.areas_out)
    district = index.district if index else None

    if args.probe:
        path = os.path.join(args.cache_dir, "uldk.json")
        cache = load_cache(path)
        res = lookup_parcels(args.probe, cache, session, online, refresh_misses=args.refresh_misses, log=print)
        if online:
            save_cache(path, cache)
        for pid in args.probe:
            r = res.get(normalize_parcel_id(pid) or pid, {})
            out = {"id": pid, "status": r.get("status"), "centroid": r.get("centroid"),
                   "area_m2": r.get("area_m2"), "fetched_at": r.get("fetched_at")}
            if r.get("error"):
                out["error"] = r["error"]
            if r.get("centroid") and index:
                out["in_district"] = index.in_district(r["centroid"])
                out["area"] = index.locate(r["centroid"])
            print(json.dumps(out, ensure_ascii=False))

    if args.address:
        path = os.path.join(args.cache_dir, "uug.json")
        cache = load_cache(path)
        for text in args.address:
            street, number = split_address(text)
            hit = geocode_record_address({"street": street, "number": number}, cache, session, district, online,
                                         opts={"refresh_misses": args.refresh_misses})
            out = {"input": text, "street": street, "number": number,
                   "result": {k: v for k, v in (hit or {}).items() if k != "street_geometry"} if hit else None}
            if hit and index:
                out["area"] = index.locate([hit["lon"], hit["lat"]])
            print(json.dumps(out, ensure_ascii=False))
        if online:
            save_cache(path, cache)
    return 0


if __name__ == "__main__":
    sys.exit(main())
