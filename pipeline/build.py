"""Build stage: crawl → parse → normalise → merge → RWDZ → geocode → relate → site data, exports, report.

Three datasets end up as one ``Record`` shape (docs/DATA_MODEL.md, "v2 extension"): the district's
monthly lists and the city architecture bureau's (BAiPP) lists – WZ / ULICP / initiated proceedings,
``records.json`` – and GUNB's register of building permits and notifications (RWDZ, kinds ``pb`` /
``zg``, ``permits.json``, loaded lazily by the site).

Usage (from the project root)::

    uv run python -m pipeline.build                 # full live build (polite crawl, RWDZ download, geocoding)
    uv run python -m pipeline.build --skip-crawl    # reuse data/manifest.json + the committed RWDZ extracts,
                                                    # geocode online
    uv run python -m pipeline.build --offline       # no network at all: manifest, extracts + caches only
    uv run python -m pipeline.build --refresh       # re-download every source file

Outputs (see ``docs/DATA_MODEL.md``):

* ``data/manifest.json``              – via :func:`pipeline.crawl.run_crawl` (unless skipped)
* ``data/raw/rwdz/<file_id>.csv``     – via :func:`pipeline.rwdz.run_rwdz` (byte-exact Praga-Południe extracts)
* ``site/data/records.json``          – district + BAiPP records, normalised, geolocated, with sources + relations
* ``site/data/permits.json``          – RWDZ building permits and notifications (same Record schema)
* ``site/data/sources.json``          – pages/files of all three datasets, enriched with parsed/declared counts
* ``site/data/parcels.geojson``       – polygons of the cadastral parcels referenced by ``records.json``
* ``site/data/parcels-permits.geojson`` – polygons of the parcels referenced only by permits
* ``site/data/records.csv`` / ``permits.csv`` – the same records as tables for Excel (``pipeline/export.py``)
* ``site/feed.xml``                   – Atom feed of the newest 100 planning records (no permits)
* ``site/sources/<file_id>.xlsx``     – mirrored copies of the original Excel files (+ ``history/``)
* ``site/sources/rwdz/<file_id>.csv`` – mirrored RWDZ extracts (+ ``.meta.json`` line maps)
* ``data/report.md``                  – data-quality dashboard (declared vs parsed, per-dataset counts,
  geocoding, warnings)

Every output is deterministic: stable ordering, and ``generated_at`` is the only timestamp. When
a rebuild produces exactly the same data (the JSON/GeoJSON documents), the previous ``generated_at``
is kept and no file is rewritten, so a scheduled build that finds nothing new produces no diff at
all; a different ``SITE_URL`` alone re-renders only the CSVs, the feed and the report.

Exit codes: 0 = built; 1 = nothing could be built (no manifest, or an edited RWDZ extract); 3 = built,
but the live crawl failed and the previous manifest was used (also: a monthly page came back without
its file list and its previous version was used), GUNB's file format changed and the committed RWDZ
extracts were used, or a source file that gave records in the previous build cannot be read now.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import re
import sys
import tempfile
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import requests

from . import areas as areas_mod
from . import baipp, export
from . import crawl as crawl_mod
from . import rwdz as rwdz_mod
from .classify import TAGS
from .geocode import PoliteSession as GeoSession
from .geocode import locate_records
from .normalize import STREET_CANONICAL, is_pp_obreb, merge_duplicates, normalize_row, street_key
from .parse import parse_workbook

log = logging.getLogger("wzsearch.build")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
#: planning kinds (district + BAiPP lists, ``records.json``)
KIND_ORDER = ("wz", "cp", "ws")
#: GUNB RWDZ kinds (``permits.json``; opt-in in the UI)
PERMIT_KINDS = ("pb", "zg")
ALL_KINDS = (*KIND_ORDER, *PERMIT_KINDS)

#: Dictionary of record kinds shipped in ``records.json`` (labels are user-facing, Polish).
KINDS: dict[str, dict[str, str]] = {
    "wz": {
        "label": "Decyzja o warunkach zabudowy",
        "short": "WZ",
        "description": "Decyzja o warunkach zabudowy (WZ): określa, co i jak można zbudować na terenie, "
                       "dla którego nie ma miejscowego planu zagospodarowania przestrzennego.",
    },
    "cp": {
        "label": "Decyzja o lokalizacji inwestycji celu publicznego",
        "short": "CP",
        "description": "Decyzja o ustaleniu lokalizacji inwestycji celu publicznego (ULICP): sieci, drogi, "
                       "szkoły, parki i inne inwestycje publiczne poza obszarem planu miejscowego.",
    },
    "ws": {
        "label": "Wszczęte postępowanie",
        "short": "Wszczęcie",
        "description": "Informacja o wszczęciu postępowania w sprawie WZ lub CP (lokalizacji inwestycji celu "
                       "publicznego) – złożony wniosek; decyzja zapada później i trafia na listę wydanych decyzji.",
    },
    **{kind: dict(meta) for kind, meta in rwdz_mod.KIND_META.items()},   # pb, zg
}

#: Datasets (sources of records) – DATA_MODEL.md, "v2 extension: three datasets". Labels are user-facing.
DATASETS: dict[str, dict[str, str]] = {
    "district": {
        "label": "Urząd Dzielnicy Praga-Południe",
        "short": "Dzielnica",
        "publisher": "Urząd Dzielnicy Praga-Południe m.st. Warszawy – Wydział Architektury i Budownictwa",
        "url": crawl_mod.INDEX_URL,
        "description": "Comiesięczne zestawienia dzielnicy: wszczęte postępowania oraz wydane decyzje WZ i CP "
                       "(lokalizacja inwestycji celu publicznego) w sprawach prowadzonych przez urząd dzielnicy.",
    },
    "baipp": {
        "label": "Biuro Architektury i Planowania Przestrzennego",
        "short": "BAiPP (miasto)",
        "publisher": "Urząd m.st. Warszawy – Biuro Architektury i Planowania Przestrzennego",
        "url": crawl_mod.BAIPP_URL,
        "description": "Zestawienia ogólnomiejskie (roczne, aktualizowane co miesiąc) spraw WZ i CP (celu "
                       "publicznego) prowadzonych centralnie przez Biuro Architektury i Planowania Przestrzennego; "
                       "pokazujemy tylko pozycje, których adres wskazuje Pragę-Południe.",
    },
    "rwdz": dict(rwdz_mod.DATASET_META),   # label, short, publisher, url, dataset_url, licence(_url), description
}

#: Who issued / handles the case (``Record.issuer``). In Warsaw the legal authority for both district and
#: city cases is the Prezydent m.st. Warszawy (GUNB writes "Prezydent Miasta Warszawa - Praga Płd."), so the
#: labels name the office that handles the case.
ISSUERS: dict[str, dict[str, str]] = {
    "district": {"label": "Urząd Dzielnicy Praga-Południe (Wydział Architektury i Budownictwa)"},
    "city": {"label": "Urząd m.st. Warszawy (Biuro Architektury i Planowania Przestrzennego)"},
    "voivode": {"label": "Wojewoda Mazowiecki"},
    "other": {"label": "Inny organ"},
}

#: How a decision ended (``Record.outcome``; null = not stated in the source).
OUTCOMES: dict[str, dict[str, str]] = {
    "granted": {"label": "Ustalenie (decyzja pozytywna)",
                "description": "Ustalono warunki zabudowy lub lokalizację inwestycji celu publicznego."},
    "refusal": {"label": "Odmowa", "description": "Odmówiono ustalenia warunków zabudowy, lokalizacji inwestycji "
                                                  "albo innego żądania (np. przeniesienia decyzji)."},
    "discontinued": {"label": "Umorzenie postępowania",
                     "description": "Postępowanie zakończono bez rozstrzygnięcia co do istoty sprawy (np. po "
                                    "wycofaniu wniosku)."},
    "transfer": {"label": "Przeniesienie decyzji",
                 "description": "Decyzję przeniesiono na inny podmiot (nowego inwestora)."},
    "expiry": {"label": "Wygaśnięcie decyzji",
               "description": "Stwierdzono wygaśnięcie wcześniejszej decyzji (w całości lub w części)."},
}

#: Works scope of a permit (``Record.permit.scope``) – the UI label (the register's own wording is in
#: every record's ``permit.scope_label``).
PERMIT_SCOPES: dict[str, dict[str, str]] = {slug: {"label": v["label"]} for slug, v in rwdz_mod.PERMIT_SCOPES.items()}
#: Object categories I–XXX of Prawo budowlane: short UI ``label`` + the official ``description``.
PERMIT_CATEGORIES: dict[str, dict[str, str]] = {k: dict(v) for k, v in rwdz_mod.PERMIT_CATEGORIES.items()}

#: Top-level field order of a Record in ``records.json`` (DATA_MODEL.md); unknown keys follow.
RECORD_FIELDS = (
    "id", "kind", "procedure", "dataset", "issuer", "outcome", "number", "date", "date_raw", "filed_date",
    "period", "applicant", "applicant_type", "investment", "address", "parcels", "parcels_raw", "tags", "permit",
    "area", "geo", "sources", "related", "warnings",
)

PARCELS_ATTRIBUTION = "Działki: Główny Urząd Geodezji i Kartografii – usługa ULDK (uldk.gugik.gov.pl)"
PARCELS_SOURCE = "https://uldk.gugik.gov.pl/ (GetParcelById, EPSG:4326)"

EXIT_OK, EXIT_FATAL, EXIT_STALE = 0, 1, 3


class BuildError(RuntimeError):
    """The build cannot produce anything (e.g. no manifest and no way to crawl)."""


# =============================================================================
# Paths
# =============================================================================


@dataclass(frozen=True)
class Paths:
    """Every location the build reads or writes, relative to one project ``root``."""

    root: Path = PROJECT_ROOT

    @property
    def manifest(self) -> Path:
        return self.root / "data" / "manifest.json"

    @property
    def raw(self) -> Path:
        return self.root / "data" / "raw"

    @property
    def cache(self) -> Path:
        return self.root / "data" / "cache"

    @property
    def report(self) -> Path:
        return self.root / "data" / "report.md"

    @property
    def site(self) -> Path:
        return self.root / "site"

    @property
    def site_data(self) -> Path:
        return self.site / "data"

    @property
    def records_json(self) -> Path:
        return self.site_data / "records.json"

    @property
    def sources_json(self) -> Path:
        return self.site_data / "sources.json"

    @property
    def parcels_geojson(self) -> Path:
        return self.site_data / "parcels.geojson"

    @property
    def areas_geojson(self) -> Path:
        return self.site_data / "areas.geojson"

    @property
    def records_csv(self) -> Path:
        return self.site_data / "records.csv"

    @property
    def permits_json(self) -> Path:
        return self.site_data / "permits.json"

    @property
    def parcels_permits_geojson(self) -> Path:
        return self.site_data / "parcels-permits.geojson"

    @property
    def permits_csv(self) -> Path:
        return self.site_data / "permits.csv"

    @property
    def feed(self) -> Path:
        return self.site / "feed.xml"

    @property
    def mirror(self) -> Path:
        return self.site / "sources"

    @property
    def rwdz_raw(self) -> Path:
        """Committed RWDZ extracts + sidecars (``rwdz.LOCAL_DIR``)."""
        return self.root / rwdz_mod.LOCAL_DIR

    @property
    def rwdz_mirror(self) -> Path:
        return self.site / rwdz_mod.ARCHIVE_DIR


# =============================================================================
# Small helpers
# =============================================================================


def natural_key(s: str) -> list[Any]:
    """Natural sort key (``wz-2026-9`` < ``wz-2026-15``)."""
    return [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", s or "")]


def sort_records(records: Iterable[dict]) -> list[dict]:
    """Newest first: record date, then reporting period, then id (natural order, higher number first)."""
    return sorted(records, key=lambda r: (r.get("date") or "", r.get("period") or "", natural_key(r["id"])),
                  reverse=True)


def _now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def write_atomic(path: Path, data: bytes) -> bool:
    """Write ``data`` atomically (temp file + ``os.replace``); skip if identical. Returns True if written."""
    if path.is_file() and path.read_bytes() == data:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
        os.chmod(tmp, 0o644)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
    return True


def dumps_json(doc: Mapping[str, Any], line_arrays: Sequence[str] = ()) -> bytes:
    """Serialise a top-level object as diff-friendly JSON.

    Each top-level key sits on its own line (compact value); the arrays named in
    ``line_arrays`` are written one compact element per line, so a changed record or page
    shows up as a one-line diff. The result is valid JSON (UTF-8, no ASCII escaping).
    """
    def compact(v: Any) -> str:
        return json.dumps(v, ensure_ascii=False, separators=(",", ":"), allow_nan=False)

    items = list(doc.items())
    lines = ["{"]
    for i, (key, value) in enumerate(items):
        comma = "," if i < len(items) - 1 else ""
        k = json.dumps(key, ensure_ascii=False)
        if key in line_arrays and isinstance(value, list) and value:
            lines.append(f"{k}:[")
            lines.extend(compact(el) + ("," if j < len(value) - 1 else "") for j, el in enumerate(value))
            lines.append(f"]{comma}")
        else:
            lines.append(f"{k}:{compact(value)}{comma}")
    lines.append("}")
    return ("\n".join(lines) + "\n").encode("utf-8")


# =============================================================================
# Stage 1: manifest
# =============================================================================


def _same_except_generated_at(a: Mapping | None, b: Mapping | None) -> bool:
    if a is None or b is None:
        return False
    strip = lambda d: {k: v for k, v in d.items() if k != "generated_at"}  # noqa: E731
    return strip(a) == strip(b)


def obtain_manifest(paths: Paths, *, crawl: bool, refresh: bool = False,
                    session: requests.Session | None = None) -> tuple[dict, str | None]:
    """Crawl (if asked) and return ``(manifest, crawl_error)``.

    A failed crawl falls back to the existing manifest (``crawl_error`` says why); so does a monthly page
    that came back without its file list (``stale_pages``, kept from the previous crawl by the crawler):
    both make the build exit with code 3. A crawl that finds nothing new keeps the previous manifest's
    ``generated_at`` so the file does not change.
    """
    previous = crawl_mod.load_manifest(paths.manifest)
    error = None
    manifest = previous
    if crawl:
        try:
            manifest = crawl_mod.run_crawl(paths.manifest, paths.raw, refresh=refresh, session=session)
        except (requests.RequestException, RuntimeError, OSError) as exc:
            error = f"{type(exc).__name__}: {exc}"
            log.error("crawl failed (%s); using the previous manifest", error)
            manifest = previous
        else:
            if _same_except_generated_at(manifest, previous):
                manifest["generated_at"] = previous["generated_at"]
                crawl_mod.write_manifest(manifest, paths.manifest)
            if manifest.get("stale_pages"):
                error = ("monthly pages without their file list (kept from the previous crawl): "
                         + ", ".join(manifest["stale_pages"]))
                log.error("crawl: %s", error)
    if manifest is None:
        raise BuildError(f"no manifest at {paths.manifest}" + (f" and the crawl failed ({error})" if error else
                                                               " – run without --skip-crawl/--offline first"))
    return manifest, error


# =============================================================================
# Stage 2: parse + normalise
# =============================================================================


def _kind_label(kind: str | None) -> str:
    return KINDS[kind]["short"] if kind in KINDS else "nieznany"


def decide_kind(detected: str | None, category: str | None) -> tuple[str | None, list[str]]:
    """Kind of a file's rows: the file's own title/headers win over the linking block's text.

    The workbook describes its own content ("Informacja o wydanych decyzjach o warunkach
    zabudowy"), whereas a link on the page could be misplaced, so detection wins; the page
    category is the fallback when the file does not say. Returns ``(kind, file warnings)``.
    """
    if detected and category and detected != category:
        return detected, [f"Plik jest podlinkowany na stronie jako lista {_kind_label(category)}, ale jego "
                          f"nagłówek wskazuje listę {_kind_label(detected)} – przyjęto treść pliku."]
    if detected:
        return detected, []
    if category:
        return category, [f"W pliku nie rozpoznano rodzaju listy – przyjęto rodzaj z opisu na stronie "
                          f"({_kind_label(category)})."]
    return None, ["Nie rozpoznano rodzaju listy ani w pliku, ani na stronie – rodzaj ustalono z numerów pozycji."]


def _file_chrono_key(f: Mapping[str, Any]) -> tuple:
    """Oldest publication first, so the original listing of a decision wins when merging.

    BAiPP snapshots of one year share the period (``2026``): they are ordered by their version time
    (``last_modified``), so the newest snapshot comes last and its values win (see merge_duplicates).
    """
    version = (f.get("last_modified") or "") if f.get("source") == "baipp" else ""
    return (f.get("period") or "9999-99", version, f.get("filename") or "", f.get("file_id") or "")


@dataclass
class FileResult:
    """What the build learned about one source file."""

    kind_detected: str | None = None
    kind_used: str | None = None
    layout: str | None = None
    parsed_count: int | None = None   # data rows kept as records (BAiPP: the Praga-Południe rows)
    rows_total: int | None = None     # data rows in the file (BAiPP: city-wide)
    skipped_rows: int | None = None
    warnings: list[str] = field(default_factory=list)


def parse_sources(manifest: Mapping[str, Any], root: Path) -> tuple[list[dict], dict[str, FileResult]]:
    """Parse and normalise every manifest file (oldest first). Never raises on a bad file.

    BAiPP files (``source: "baipp"``) list the whole city: only rows whose address names
    Praga-Południe (:func:`pipeline.baipp.in_district`) become records; ``rows_total`` counts every
    data row, ``parsed_count`` the kept ones.

    Returns the un-merged records (one per kept data row) and a :class:`FileResult` per file id.
    """
    records: list[dict] = []
    results: dict[str, FileResult] = {}
    for f in sorted(manifest.get("files", []), key=_file_chrono_key):
        fid = f["file_id"]
        if f.get("source") not in (None, "district", "baipp"):
            # RWDZ files never come from the crawler (see obtain_permits); anything else is not a workbook
            log.warning("%s: manifest file of source %r skipped (not a district/BAiPP workbook)", fid, f.get("source"))
            continue
        res = results[fid] = FileResult()
        path = root / f.get("local_path", f"data/raw/{fid}.{f.get('ext', 'xlsx')}")
        if not path.is_file():
            res.warnings.append("Brak lokalnej kopii pliku (nie udało się go pobrać) – pozycje nieodczytane.")
            log.warning("%s (%s): no local copy, skipped", fid, f.get("filename"))
            continue
        try:
            parsed = parse_workbook(path)
        except Exception as exc:  # noqa: BLE001 – one unreadable file must not stop the build
            res.warnings.append(f"Nie udało się odczytać pliku ({type(exc).__name__}) – pozycje nieodczytane.")
            log.error("%s (%s): cannot parse: %s", fid, f.get("filename"), exc)
            continue
        kind, kind_warnings = decide_kind(parsed["kind"], f.get("category"))
        sheet_kinds = {s["name"]: s.get("kind") for s in parsed.get("sheets", [])}
        page_ids = f.get("page_ids") or []
        meta = {"file_id": fid, "page_id": page_ids[0] if page_ids else None, "period": f.get("period")}
        rows = parsed["rows"]
        if f.get("source") == "baipp":
            meta.update(dataset="baipp", series=f.get("series") or parsed.get("series"))
            rows = [row for row in rows if baipp.in_district(row["cells"].get("address"))]
            if f.get("series") and parsed.get("series") and f["series"] != parsed["series"]:
                kind_warnings.append(f"Seria decyzji ULICP z opisu na stronie ({f['series'].upper()}) różni się od "
                                     f"tytułu pliku ({parsed['series'].upper()}) – przyjęto opis na stronie.")
        for row in rows:
            row_kind = sheet_kinds.get(row["sheet"]) or kind
            rec = normalize_row(row, row_kind, meta)
            if parsed["kind"] is None and row_kind and row_kind == f.get("category"):
                rec["warnings"].append("rodzaj pozycji przyjęto z opisu na stronie (plik go nie podaje)")
            if f.get("source") == "baipp":
                dup = baipp.duplicate_sequence_warning(rec["number"], parsed["rows"], row_kind)
                if dup:
                    rec["warnings"].append(dup)
            records.append(rec)
        res.kind_detected = parsed["kind"]
        res.kind_used = kind
        res.layout = parsed.get("layout")
        res.parsed_count = len(rows)
        res.rows_total = len(parsed["rows"])
        res.skipped_rows = len(parsed.get("skipped", []))
        res.warnings = list(dict.fromkeys([*parsed.get("warnings", []), *kind_warnings]))
    return records, results


def lost_files(paths: Paths, results: Mapping[str, FileResult]) -> list[str]:
    """District/BAiPP files that gave records in the last build (``sources.json``) but cannot be read now
    (no local copy, unreadable workbook): their records would silently disappear, so the build reports them
    and exits with code 3."""
    try:
        previous = json.loads(paths.sources_json.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    lost = []
    for f in previous.get("files") or []:
        res = results.get(f.get("file_id"))
        if res is not None and res.parsed_count is None and (f.get("parsed_count") or 0) > 0:
            lost.append(f["file_id"])
    return sorted(lost)


# =============================================================================
# Stage 2b: GUNB RWDZ (building permits and notifications)
# =============================================================================


@dataclass
class PermitStage:
    """Outcome of the RWDZ stage (:func:`pipeline.rwdz.run_rwdz`)."""

    enabled: bool                 # False: no RWDZ dataset in this build at all
    records: list[dict] = field(default_factory=list)   # pb + zg, newest first
    files: list[dict] = field(default_factory=list)     # sources.json files[] entries
    page: dict | None = None                            # the "rwdz" pseudo-page
    stats: dict = field(default_factory=dict)
    error: str | None = None      # GUNB's format changed: the committed extracts were used instead


def obtain_permits(paths: Paths, *, enabled: bool | None, online: bool, refresh: bool = False,
                   session: Any = None) -> PermitStage:
    """Run the RWDZ stage: conditional download (``online``) → extracts → Records.

    ``enabled=None`` (default) runs it whenever it can produce something: online, or offline when
    committed extracts exist (``data/raw/rwdz/``); a project that never fetched RWDZ builds offline
    without the dataset. Network failures never raise (the committed extract is used, see
    ``run_rwdz``). When GUNB's format drifts (:class:`pipeline.rwdz.RwdzFormatError`) the build
    falls back to the committed extracts and reports it (exit code 3); an edited committed extract
    is fatal (:class:`BuildError`).
    """
    if enabled is None and not (online or paths.rwdz_raw.is_dir()):
        log.warning("RWDZ: no committed extracts in %s and building offline – permits are left out",
                    paths.rwdz_raw.relative_to(paths.root) if paths.rwdz_raw.is_relative_to(paths.root)
                    else paths.rwdz_raw)
        return PermitStage(enabled=False)
    if enabled is False:
        log.info("RWDZ: left out of this build")
        return PermitStage(enabled=False)
    kw: dict[str, Any] = {"cache_dir": paths.cache, "raw_dir": paths.rwdz_raw, "log": log.info}
    error = None
    try:
        result = rwdz_mod.run_rwdz(online=online, refresh=refresh, session=session, **kw)
    except rwdz_mod.RwdzFormatError as exc:
        if not online:
            raise BuildError(f"RWDZ: {exc}") from exc
        error = f"RwdzFormatError: {exc}"
        log.error("RWDZ: %s – using the committed extracts", exc)
        try:
            result = rwdz_mod.run_rwdz(online=False, **kw)
        except rwdz_mod.RwdzFormatError as exc2:
            raise BuildError(f"RWDZ: {exc2}") from exc2
    return PermitStage(enabled=True, records=result["records"], files=result["files"], page=result["page"],
                       stats=result["stats"], error=error)


# =============================================================================
# Stage 3–5: merge, relations
# =============================================================================


def merge_records(records: list[dict]) -> list[dict]:
    """One record per decision: same id + same content → sources merged; different content → ``-2``…

    (see :func:`pipeline.normalize.merge_duplicates`). Returns records newest first.
    """
    return sort_records(merge_duplicates(records))


def _norm_house(number: str | None) -> str:
    return re.sub(r"\s+", "", number or "").lower()


def address_keys(record: Mapping[str, Any]) -> set[tuple[str, str]]:
    """``{(street_key, house number)}`` of every street + number named in the record's address."""
    address = record.get("address") or {}
    parts = address.get("parts") or [{"street": address.get("street"), "number": address.get("number")}]
    keys = set()
    for part in parts:
        sk = street_key(part.get("street"))
        if not sk:
            continue
        for number in part.get("numbers") or ([part["number"]] if part.get("number") else []):
            if _norm_house(number):
                keys.add((sk, _norm_house(number)))
    return keys


def compute_related(records: list[dict]) -> None:
    """Fill ``record["related"]`` in place: other records sharing a parcel id or street + house number.

    Ordered chronologically (date, then natural id); a record is never related to itself.
    """
    by_parcel: dict[str, set[str]] = defaultdict(set)
    by_address: dict[tuple[str, str], set[str]] = defaultdict(set)
    order: dict[str, tuple] = {}
    for r in records:
        order[r["id"]] = (r.get("date") or "9999-99-99", natural_key(r["id"]))
        for p in r.get("parcels") or []:
            if p.get("id"):
                by_parcel[p["id"]].add(r["id"])
        for key in address_keys(r):
            by_address[key].add(r["id"])
    for r in records:
        related: set[str] = set()
        for p in r.get("parcels") or []:
            related |= by_parcel.get(p.get("id"), set())
        for key in address_keys(r):
            related |= by_address[key]
        related.discard(r["id"])
        r["related"] = sorted(related, key=order.__getitem__)


def order_record(r: Mapping[str, Any]) -> dict:
    """Record with keys in the DATA_MODEL.md order (unknown keys appended, sorted)."""
    out = {k: r.get(k) for k in RECORD_FIELDS}
    for k in sorted(set(r) - set(RECORD_FIELDS)):
        out[k] = r[k]
    return out


# =============================================================================
# Stage 6: sources.json
# =============================================================================


def block_counts(page: Mapping[str, Any], block: Mapping[str, Any], files_by_id: Mapping[str, Mapping],
                 results: Mapping[str, FileResult], counted: set[tuple[str, str]]) -> tuple[int | None, bool]:
    """``(parsed_count, count_mismatch)`` for one block of a monthly page.

    The declared count ("3 pozycje") belongs to the files **first published** on this page: a
    leftover link to last month's file (Oct 2025 WZ, Oct 2022 CP) is not counted again. A file
    is counted once per page even if two blocks link it (``counted`` tracks ``(page, file)``).
    Blocks without files count 0 when they name a category, else ``None`` (not a data block).
    """
    fids = list(block.get("file_ids") or [])
    if not fids:
        parsed = 0 if block.get("category") else None
    else:
        own = [f for f in fids if (files_by_id.get(f, {}).get("page_ids") or [None])[0] == page["page_id"]]
        chosen = [f for f in (own or fids) if (page["page_id"], f) not in counted]
        counted.update((page["page_id"], f) for f in chosen)
        counts = [results[f].parsed_count if f in results else None for f in chosen]
        parsed = None if any(c is None for c in counts) else sum(counts)
    declared = block.get("declared_count")
    mismatch = declared is not None and parsed is not None and parsed != declared
    return parsed, mismatch


def build_sources_doc(manifest: Mapping[str, Any], results: Mapping[str, FileResult], records: Sequence[dict],
                      mirrored: Mapping[str, str], generated_at: str | None) -> dict:
    """Manifest pages + files enriched for the site (DATA_MODEL.md → ``site/data/sources.json``)."""
    files_by_id = {f["file_id"]: f for f in manifest.get("files", [])}
    record_ids: dict[str, set[str]] = defaultdict(set)
    for r in records:
        for s in r.get("sources") or []:
            record_ids[s["file_id"]].add(r["id"])

    counted: set[tuple[str, str]] = set()
    pages = []
    for page in manifest.get("pages", []):
        blocks = []
        for block in page.get("blocks", []):
            parsed, mismatch = block_counts(page, block, files_by_id, results, counted)
            blocks.append({**block, "parsed_count": parsed, "count_mismatch": mismatch})
        pages.append({**page, "blocks": blocks})

    files = []
    for f in manifest.get("files", []):
        res = results.get(f["file_id"], FileResult())
        history = []
        for h in f.get("history") or []:
            h = dict(h)
            name = Path(h["archived_path"]).name if h.get("archived_path") else None
            h["archive_path"] = f"sources/history/{name}" if name and f"history/{name}" in mirrored else None
            history.append(h)
        files.append({
            **f,
            "history": history,
            "archive_path": mirrored.get(f["file_id"]),
            "record_ids": sorted(record_ids.get(f["file_id"], ()), key=natural_key),
            "parsed_count": res.parsed_count,
            "rows_total": res.rows_total,
            "kind_detected": res.kind_detected,
            "layout": res.layout,
            "skipped_rows": res.skipped_rows,
            "warnings": res.warnings,
        })
    return {
        "generated_at": generated_at,
        "index_url": manifest.get("index_url"),
        "pages": pages,
        "files": files,
    }


# =============================================================================
# Stage 6b: mirror the original files into the site
# =============================================================================


_MIRROR_NAME_RE = re.compile(r"^[0-9a-f]{10}\.[a-z0-9]{1,8}$")
_HISTORY_NAME_RE = re.compile(r"^[0-9a-f]{10}-[0-9a-f]{12}\.[a-z0-9]{1,8}$")


def mirror_sources(manifest: Mapping[str, Any], paths: Paths) -> dict[str, str]:
    """Copy every available original to ``site/sources/<file_id>.<ext>`` (and old versions to
    ``site/sources/history/``), removing copies of files no longer in the manifest.

    Returns ``{file_id: "sources/<file_id>.<ext>", "history/<name>": "sources/history/<name>"}``
    for the copies that exist afterwards. Copies are only rewritten when their bytes differ.
    """
    out: dict[str, str] = {}
    wanted: set[str] = set()
    wanted_history: set[str] = set()
    for f in manifest.get("files", []):
        src = paths.root / f.get("local_path", "")
        if f.get("local_path") and src.is_file():
            name = f"{f['file_id']}.{f.get('ext') or 'bin'}"
            _copy_if_changed(src, paths.mirror / name, f.get("sha256"))
            out[f["file_id"]] = f"sources/{name}"
            wanted.add(name)
        for h in f.get("history") or []:
            if h.get("archived_path") and (paths.root / h["archived_path"]).is_file():
                name = Path(h["archived_path"]).name
                _copy_if_changed(paths.root / h["archived_path"], paths.mirror / "history" / name, h.get("sha256"))
                out[f"history/{name}"] = f"sources/history/{name}"
                wanted_history.add(name)
    for directory, keep, pattern in ((paths.mirror, wanted, _MIRROR_NAME_RE),
                                     (paths.mirror / "history", wanted_history, _HISTORY_NAME_RE)):
        if directory.is_dir():
            for p in directory.iterdir():
                if p.is_file() and pattern.match(p.name) and p.name not in keep:
                    log.info("removing stale mirrored copy %s", p.relative_to(paths.root))
                    p.unlink()
    return out


def _copy_if_changed(src: Path, dst: Path, sha256: str | None) -> None:
    if dst.is_file() and dst.stat().st_size == src.stat().st_size and _sha256(dst) == (sha256 or _sha256(src)):
        return
    write_atomic(dst, src.read_bytes())


_RWDZ_MIRROR_RE = re.compile(r"^rwdz-[a-z0-9-]+\.(?:csv|meta\.json)$")


def mirror_rwdz(files: Sequence[Mapping[str, Any]], paths: Paths) -> dict[str, dict[str, str]]:
    """Copy every committed RWDZ extract and its sidecar (the original line numbers) to
    ``site/sources/rwdz/``, removing copies of files no longer built.

    Returns ``{file_id: {"archive_path": "sources/rwdz/<id>.csv", "archive_meta_path": "….meta.json"}}``
    for the extracts that exist afterwards. Copies are only rewritten when their bytes differ.
    """
    out: dict[str, dict[str, str]] = {}
    keep: set[str] = set()
    for f in files:
        src = paths.root / f["local_path"] if f.get("local_path") else None
        if src is None or not src.is_file():
            continue
        meta = src.with_name(src.name.removesuffix(".csv") + ".meta.json")
        _copy_if_changed(src, paths.rwdz_mirror / src.name, f.get("sha256"))
        keep.add(src.name)
        entry = {"archive_path": f"{rwdz_mod.ARCHIVE_DIR}/{src.name}"}
        if meta.is_file():
            _copy_if_changed(meta, paths.rwdz_mirror / meta.name, None)
            keep.add(meta.name)
            entry["archive_meta_path"] = f"{rwdz_mod.ARCHIVE_DIR}/{meta.name}"
        out[f["file_id"]] = entry
    if paths.rwdz_mirror.is_dir():
        for p in paths.rwdz_mirror.iterdir():
            if p.is_file() and _RWDZ_MIRROR_RE.match(p.name) and p.name not in keep:
                log.info("removing stale mirrored copy %s", p.relative_to(paths.root))
                p.unlink()
    return out


def rwdz_sources(stage: PermitStage, mirrored: Mapping[str, Mapping[str, str]]) -> tuple[list[dict], list[dict]]:
    """``(pages, files)`` of the RWDZ dataset for ``sources.json``: the pseudo-page and one entry per
    archive, ``archive_path`` (+ *ext* ``archive_meta_path``) set only when the mirrored copy exists."""
    if not stage.enabled:
        return [], []
    files = []
    for f in stage.files:
        entry: dict[str, Any] = {}
        for k, v in f.items():
            entry[k] = v
            if k == "archive_path":
                m = mirrored.get(f["file_id"]) or {}
                entry["archive_path"] = m.get("archive_path")
                entry["archive_meta_path"] = m.get("archive_meta_path")
        files.append(entry)
    return ([stage.page] if stage.page else []), files


# =============================================================================
# Stage 8: data-quality report
# =============================================================================


def warning_category(w: str) -> str:
    """Collapse a concrete warning into its type (quoted text, numbers, addresses removed)."""
    w = re.sub(r"„[^”]*”", "„…”", w)
    w = re.sub(r"\((?!ULDK\))[^)]*\)", "(…)", w)       # "(ULDK)" explains, it is no detail
    w = re.sub(r"^adres .+? leży", "adres … leży", w)
    w = re.sub(r"\b\d[\d./\-]*\b", "N", w)
    return w


def numbering_gaps(records: Iterable[Mapping[str, Any]]) -> dict[tuple[str, str], tuple[list[int], list[int]]]:
    """``{(kind, year): (sequence numbers seen, numbers never seen)}`` for WZ/CP decisions.

    Numbering restarts at 1 every year, so missing numbers run from 1 to the highest number seen – except in
    the first year of a kind, where the publication started mid-year and only gaps after the lowest number
    seen count. Uses the record ids (``wz-2026-15`` → 2026, 15); ``-2`` suffixes and fallback ids are ignored.
    """
    seen: dict[tuple[str, str], set[int]] = defaultdict(set)
    for r in records:
        m = re.fullmatch(r"(wz|cp)-(\d{4})-(\d+)", r.get("id") or "")
        if m:
            seen[(m.group(1), m.group(2))].add(int(m.group(3)))
    first_year = {kind: min(y for k, y in seen if k == kind) for kind, _ in seen}
    out = {}
    for (kind, year), numbers in seen.items():
        start = min(numbers) if year == first_year[kind] else 1
        out[(kind, year)] = (sorted(numbers), [i for i in range(start, max(numbers) + 1) if i not in numbers])
    return out


def _pct(n: int, total: int) -> str:
    return f"{100 * n / total:.1f}%" if total else "–"


def _md(text: Any) -> str:
    """Escape text for a Markdown table cell."""
    return str("" if text is None else text).replace("\\", "\\\\").replace("|", "\\|").replace("\n", " ")


def _rec_ref(rid: str, site_url: str | None) -> str:
    if site_url and re.match(r"^https?://", site_url):
        return f"[`{rid}`]({export.permalink(site_url, rid)})"
    return f"`{rid}`"


def _site_file_link(path: str, site_url: str | None) -> str:
    """A site-relative file (``sources/rwdz/…``) linked from ``data/report.md``: on the public site when
    ``site_url`` is absolute, else relative to the report (``../site/…``)."""
    if site_url and re.match(r"^https?://", site_url):
        return export.site_link(site_url, path)
    return f"../site/{path}"


def _baipp_report(pages: Sequence[Mapping[str, Any]], files: Sequence[Mapping[str, Any]], records: Sequence[dict],
                  ref: Callable[[str], str]) -> list[str]:
    """Report section for the city-wide BAiPP lists: city-wide rows vs Praga-Południe rows per file."""
    bpages = [p for p in pages if p.get("source") == "baipp"]
    bfiles = [f for f in files if f.get("source") == "baipp"]
    if not bpages and not bfiles:
        return []
    L = ["## BAiPP (city architecture bureau) lists", "",
         "Biuro Architektury i Planowania Przestrzennego publishes the same three lists for the whole city, one "
         "file per year and list (the current year's files are replaced every month; every snapshot we downloaded "
         "is kept). Only rows whose address names Praga-Południe on its last line become records.", "",
         "| Page | Year | List | File | City-wide rows | Praga-Południe rows | Records |",
         "|---|---|---|---|---:|---:|---:|"]
    pages_by_id = {p["page_id"]: p for p in bpages}
    kind_label = {"ws": "wszczęte", "wz": "WZ", "cp": "ULICP"}
    for f in sorted(bfiles, key=lambda f: (f.get("period") or "", f.get("category") or "", f.get("series") or "",
                                           f.get("last_modified") or "", f["file_id"]), reverse=True):
        page = pages_by_id.get((f.get("page_ids") or [None])[0]) or {}
        label = kind_label.get(f.get("category"), "?") + (f" {f['series'].upper()}" if f.get("series") else "")
        gone = f" (no longer linked since {f['removed_from_source_at']})" if f.get("removed_from_source_at") else ""
        L.append(f"| [{_md(page.get('title') or f.get('page_ids'))}]({page.get('url', '')}) | {f.get('period') or '–'} "
                 f"| {label} | [{_md(f['filename'])}]({f['url']}){gone} | "
                 f"{f.get('rows_total') if f.get('rows_total') is not None else '–'} | "
                 f"{f.get('parsed_count') if f.get('parsed_count') is not None else '–'} | "
                 f"{len(f.get('record_ids') or [])} |")
    L.append("")
    city = [r for r in records if r.get("dataset") == "baipp"]
    outcomes = Counter(r.get("outcome") or "–" for r in city if r.get("kind") in ("wz", "cp"))
    by_kind = Counter(r["kind"] for r in city)
    L.append(f"* Records: {len(city)} (" + ", ".join(f"{KINDS[k]['short']} {by_kind.get(k, 0)}" for k in KIND_ORDER)
             + "); decision outcomes: " + ", ".join(f"{(OUTCOMES.get(k) or {}).get('label', 'nie podano')} {outcomes[k]}"
                                                   for k in [*OUTCOMES, "–"] if outcomes.get(k)) + ".")
    multi = [r for r in city if len({s["file_id"] for s in r.get("sources") or []}) > 1]
    L.append(f"* Listed in more than one snapshot / yearly file: {len(multi)}"
             + (f" ({', '.join(ref(r['id']) for r in multi[:20])})" if multi else "") + ".")
    outside = [r for r in city if any(w.startswith("działka poza dzielnicą") for w in r.get("warnings") or [])]
    if outside:
        L.append("* Labelled Praga-Południe, but ULDK places the parcels in another district (kept, not on the map): "
                 + ", ".join(ref(r["id"]) for r in outside) + ".")
    L.append("")
    return L


def _median(values: Sequence[float]) -> float | None:
    v = sorted(values)
    if not v:
        return None
    mid = len(v) // 2
    return v[mid] if len(v) % 2 else (v[mid - 1] + v[mid]) / 2


def _days(a: str | None, b: str | None) -> int | None:
    try:
        return (datetime.fromisoformat(b).date() - datetime.fromisoformat(a).date()).days  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _refs(ids: Sequence[str], ref: Callable[[str], str], limit: int = 20) -> str:
    """``a, b, c`` (at most ``limit``, then "… and N more")."""
    shown = ", ".join(ref(i) for i in ids[:limit])
    return shown + (f" … and {len(ids) - limit} more" if len(ids) > limit else "")


def _dataset_of(r: Mapping[str, Any]) -> str:
    return r.get("dataset") or "district"


def _rwdz_report(stage: PermitStage | None, files: Sequence[Mapping[str, Any]], permits: Sequence[dict],
                 ref: Callable[[str], str], site_url: str | None = None) -> list[str]:
    """Report section for GUNB RWDZ: snapshots, counts per kind/year/issuer/scope, register quirks."""
    if stage is None or not stage.enabled:
        return []
    rfiles = [f for f in files if f.get("source") == rwdz_mod.DATASET]
    L = ["## GUNB RWDZ (building permits and notifications)", "",
         "GUNB publishes its register of building-permit decisions and notifications (*Rejestr wniosków, decyzji "
         "i zgłoszeń*, CC0 1.0) as three ZIP files rebuilt every night. Every case with a parcel in Praga-Południe "
         "(cadastral unit `146507_8`) is copied byte for byte into a committed extract (`data/raw/rwdz/`, mirrored to "
         "`site/sources/rwdz/`) and becomes one record in `permits.json`; the snapshot cited is the one the extract "
         "was taken from (a new GUNB file that changes nothing in the district is not adopted).", "",
         "| File | Kind | Snapshot (Last-Modified) | Rows in the file | Praga-Południe rows | Records | Extract |",
         "|---|---|---|---:|---:|---:|---|"]
    for f in rfiles:
        extract = (f"[`{f['archive_path']}`]({_site_file_link(f['archive_path'], site_url)})" if f.get("archive_path")
                   else f"**missing** ({_md(f.get('error'))})")
        L.append(f"| [{_md(f['filename'])}]({f['url']}) | {KINDS.get(f.get('category'), {}).get('short', '?')} | "
                 f"{f.get('last_modified') or '–'} | {f.get('rows_total') if f.get('rows_total') is not None else '–'} | "
                 f"{f.get('parsed_count') if f.get('parsed_count') is not None else '–'} | "
                 f"{len(f.get('record_ids') or [])} | {extract} |")
    L.append("")
    warned = [f for f in rfiles if f.get("warnings")]
    for f in warned:
        L.append(f"* `{f['file_id']}`: " + "; ".join(_md(w) for w in f["warnings"]))
    if warned:
        L.append("")

    kinds = [k for k in PERMIT_KINDS if any(r["kind"] == k for r in permits)] or list(PERMIT_KINDS)
    years = sorted({(r.get("date") or "????")[:4] for r in permits})
    per_year = Counter(((r.get("date") or "????")[:4], r["kind"]) for r in permits)
    L += ["Records per year (decision date for permits, filing date for notifications):", "",
          "| Year | " + " | ".join(KINDS[k]["short"] for k in kinds) + " | Total |",
          "|---|" + "---:|" * (len(kinds) + 1)]
    for y in years:
        row = [per_year.get((y, k), 0) for k in kinds]
        L.append(f"| {y} | " + " | ".join(map(str, row)) + f" | {sum(row)} |")
    by_kind = Counter(r["kind"] for r in permits)
    L += ["| **all** | " + " | ".join(f"**{by_kind.get(k, 0)}**" for k in kinds) + f" | **{len(permits)}** |", ""]

    def per_kind(key: Callable[[Mapping[str, Any]], Any], label: Callable[[Any], str]) -> str:
        out = []
        for k in kinds:
            c = Counter(key(r) for r in permits if r["kind"] == k)
            out.append(f"{KINDS[k]['short']}: " + ", ".join(f"{label(v)} {n}" for v, n in
                                                            sorted(c.items(), key=lambda kv: (-kv[1], str(kv[0])))))
        return "; ".join(out)

    L.append("* Issuer: " + per_kind(lambda r: r.get("issuer"), lambda v: (ISSUERS.get(v) or {}).get("label", v)) + ".")
    L.append("* Scope of works: " + per_kind(lambda r: (r.get("permit") or {}).get("scope"),
                                            lambda v: (PERMIT_SCOPES.get(v) or {}).get("label", "nie podano")) + ".")
    L.append("* Object category: " + per_kind(lambda r: (r.get("permit") or {}).get("category") or "–", str) + ".")
    L.append("* Investor: " + per_kind(lambda r: r.get("applicant_type"),
                                      lambda v: {"person": "natural person (not named by GUNB)",
                                                 "organization": "organisation", "unknown": "not published"}.get(v, v))
             + ".")
    pb = [r for r in permits if r["kind"] == "pb"]
    waits = [d for r in pb if (d := _days(r.get("filed_date"), r.get("date"))) is not None and d >= 0]
    if waits:
        waits.sort()
        L.append(f"* Application → decision (permits): median {_median(waits):.0f} days, 90th percentile "
                 f"{waits[min(len(waits) - 1, int(0.9 * len(waits)))]} days.")
    cub = [r for r in permits if (r.get("permit") or {}).get("cubature") is not None]
    L.append(f"* Cubature given: {len(cub)} of {len(permits)} records (the placeholders 0 and 1 count as not given).")
    no_parcels = [r["id"] for r in permits if not r.get("parcels")]
    if no_parcels:
        L.append(f"* Without a parcel in the register: {len(no_parcels)} ({_refs(no_parcels, ref)}).")
    other_units = [r["id"] for r in permits
                   if any(w.startswith("sprawa obejmuje też działki spoza") for w in r.get("warnings") or [])]
    if other_units:
        L.append(f"* Cases that also cover parcels of other districts (kept whole, those parcels keep their unit): "
                 f"{len(other_units)} ({_refs(other_units, ref)}).")
    L.append("")

    L += ["Register rows of the district office (*Prezydent Miasta Warszawa - Praga Płd.*) with a broken cadastral "
          "unit are kept and corrected to `146507_8` (a warning on the record), and so are the rows of the cases in "
          "`rwdz.UNIT_FIXES` (`listed`: register errors checked one by one in ULDK, any organ); a valid other Warsaw "
          "unit two or more edits away is genuine and not kept:", ""]
    signals: list[tuple[str, list]] = []
    for f in rfiles:
        st = (stage.stats.get("files") or {}).get(f["file_id"]) or {}
        kept = st.get("rows_kept_by_office_rule") or {}
        dropped = st.get("office_rows_not_kept") or {}
        kept_txt = ", ".join(f"{k} {v}" for k, v in sorted(kept.items())) or "none"
        dropped_txt = ", ".join(f"`{u}` ({rwdz_mod.WARSAW_UNITS.get(u, 'poza Warszawą')}) {n}"
                                for u, n in sorted(dropped.items())) or "none"
        L.append(f"* `{f['file_id']}`: kept – {kept_txt}; not kept – {dropped_txt}.")
        signals += [(f["file_id"], c) for c in st.get("signal_cases_not_kept") or []]
    unit_fixed = [r["id"] for r in permits if any("potraktowano jako 146507_8" in w or "przyjęto 146507_8" in w
                                                  or "bez oznaczenia działki w rejestrze – przyjęto" in w
                                                  for w in r.get("warnings") or [])]
    if unit_fixed:
        L.append(f"* Records with a corrected unit: {len(unit_fixed)} ({_refs(unit_fixed, ref)}).")
    moved = [r["id"] for r in permits if any(w.startswith(baipp.OUTSIDE_WARNING) for w in r.get("warnings") or [])]
    if moved:
        L.append(f"* Unit `146507_8` in the register with a precinct Praga-Południe does not have; ULDK places the "
                 f"parcel (or its precinct) in the district the case names (kept, not on the map): {len(moved)} "
                 f"({_refs(moved, ref)}).")
    if signals:
        L.append(f"* Not kept, but the case sign (`UD-VI-…`) or the decision number (`…/PPD/…`, `…/PRD/…`) points to "
                 f"Praga-Południe – check the parcel in ULDK and add a register error to `rwdz.UNIT_FIXES` "
                 f"({len(signals)}): " + ", ".join(f"`{c[0]}` (`{fid}` line {c[1]}, unit `{c[2] or '–'}`)"
                                                    for fid, c in signals) + ".")
    L.append("")
    return L


def _related_report(records: Sequence[dict], permits: Sequence[dict], ref: Callable[[str], str]) -> list[str]:
    """How the planning records and the permits connect (shared parcel or street + house number)."""
    if not permits:
        return []
    kind_of = {r["id"]: r["kind"] for r in (*records, *permits)}
    L = ["## Related records across datasets", "",
         "`related` links records that share a cadastral parcel or a street + house number, across all three "
         "datasets. A shared parcel is not necessarily the same project (a large housing-estate parcel carries "
         "many unrelated renovations).", ""]
    for ds in DATASETS:
        group = [r for r in records if _dataset_of(r) == ds]
        if group:
            n = sum(1 for r in group if any(kind_of.get(o) in PERMIT_KINDS for o in r.get("related") or []))
            L.append(f"* {DATASETS[ds]['short']}: {n} of {len(group)} records relate to at least one permit or "
                     f"notification.")
    n = sum(1 for r in permits if any(kind_of.get(o) in KIND_ORDER for o in r.get("related") or []))
    L.append(f"* {DATASETS['rwdz']['short']}: {n} of {len(permits)} permits/notifications relate to a WZ/ULICP "
             f"record.")
    by_parcel: dict[str, list[dict]] = defaultdict(list)
    for p in permits:
        if p["kind"] == "pb":
            for parcel in p.get("parcels") or []:
                by_parcel[parcel["id"]].append(p)
    for kind in ("wz", "cp"):
        decisions = [r for r in records if r["kind"] == kind and r.get("outcome") in (None, "granted") and r.get("date")]
        gaps = []
        for r in decisions:
            later = [_days(r["date"], p["date"]) for parcel in r.get("parcels") or []
                     for p in by_parcel.get(parcel["id"], ()) if p.get("date") and p["date"] > r["date"]]
            if later:
                gaps.append(min(later))
        if decisions:
            median = _median(gaps)
            L.append(f"* {KINDS[kind]['short']} decisions (not refused/discontinued) followed by a building permit "
                     f"on the same parcel: {len(gaps)} of {len(decisions)}"
                     + (f" (median {median:.0f} days to the first such permit)" if median is not None else "") + ".")
    top = sorted((*records, *permits), key=lambda r: (-len(r.get("related") or []), natural_key(r["id"])))[:5]
    L.append("* Most related: " + ", ".join(f"{ref(r['id'])} ({len(r.get('related') or [])})" for r in top) + ".")
    L.append("")
    return L


def _per_dataset_table(L: list[str], title: str, items: Mapping[str, Counter], examples: Mapping[str, list[str]],
                       datasets: Sequence[str], ref: Callable[[str], str]) -> None:
    """``| <title> | District | BAiPP | RWDZ | Examples |`` sorted by total count."""
    L.append(f"| {title} | " + " | ".join(DATASETS[d]["short"] for d in datasets) + " | Examples |")
    L.append("|---|" + "---:|" * len(datasets) + "---|")
    for cat, by_ds in sorted(items.items(), key=lambda kv: (-sum(kv[1].values()), kv[0])):
        L.append(f"| {_md(cat)} | " + " | ".join(str(by_ds.get(d, 0)) for d in datasets) + " | "
                 + ", ".join(ref(i) for i in examples[cat][:5]) + " |")


def build_report(*, manifest: Mapping[str, Any], sources_doc: Mapping[str, Any], records: Sequence[dict],
                 raw_records: Sequence[dict], results: Mapping[str, FileResult], geo_stats: Mapping[str, Any],
                 generated_at: str, site_url: str | None, crawl_error: str | None,
                 permits: Sequence[dict] = (), permit_stage: PermitStage | None = None,
                 lost: Sequence[str] = ()) -> str:
    """Markdown data-quality dashboard (deterministic: no timings or request counts).

    ``records`` = records.json (district + BAiPP), ``permits`` = permits.json (RWDZ).
    """
    L: list[str] = []
    add = L.append
    all_pages = sources_doc["pages"]
    all_files = sources_doc["files"]
    files_by_id = {f["file_id"]: f for f in all_files}
    # the district's monthly lists (declared counts, numbering) – BAiPP and RWDZ have sections of their own
    pages = [p for p in all_pages if (p.get("source") or "district") == "district"]
    files = [f for f in all_files if (f.get("source") or "district") == "district"]
    ref = lambda rid: _rec_ref(rid, site_url)  # noqa: E731
    n = len(records)
    everything = [*records, *permits]
    present = [d for d in DATASETS if any(_dataset_of(r) == d for r in everything)] or ["district"]

    add("# wzSearch – data-quality report")
    add("")
    add(f"Generated `{generated_at}` by `pipeline/build.py` from the district's "
        f"[source index]({manifest.get('index_url')}), the [BAiPP lists]({DATASETS['baipp']['url']}) and GUNB's "
        f"[RWDZ register]({DATASETS['rwdz']['url']}). Regenerated on every build; do not edit.")
    add("")
    if crawl_error:
        add(f"> **Warning: the live crawl failed** (`{_md(crawl_error)}`); this build used the previous manifest "
            f"(or the previous version of the pages named).")
        add("")
    if lost:
        add(f"> **Warning: files that gave records in the previous build cannot be read now** "
            f"({', '.join(f'`{f}`' for f in lost)}); their rows are missing from this build (exit code 3).")
        add("")
    if permit_stage is not None and permit_stage.error:
        add(f"> **Warning: GUNB's RWDZ file format changed** (`{_md(permit_stage.error)}`); this build used the "
            "committed extracts. Update `pipeline/rwdz.py`.")
        add("")

    # ---------------------------------------------------------------- totals
    periods = sorted(p["period"] for p in pages if p.get("period"))
    by_kind = Counter(r["kind"] for r in records)
    add("## Totals")
    add("")
    datasets = Counter(_dataset_of(r) for r in everything)
    add("* Records per dataset: " + ", ".join(f"{(DATASETS.get(k) or {}).get('short', k)} {datasets[k]}"
                                              for k in [*DATASETS, *sorted(set(datasets) - set(DATASETS))]
                                              if datasets.get(k))
        + f" – `records.json` {n}, `permits.json` {len(permits)}.")
    add(f"* Monthly pages: **{len(pages)}** ({periods[0] if periods else '–'} → {periods[-1] if periods else '–'}); "
        f"source files: **{len(files)}** ({sum(1 for f in files if f.get('parsed_count'))} with rows, "
        f"{sum(1 for f in files if f.get('parsed_count') == 0)} empty templates, "
        f"{sum(1 for f in files if f.get('parsed_count') is None)} unreadable/missing).")
    kind_totals = ", ".join(f"{KINDS[k]['short']} {by_kind.get(k, 0)}" for k in KIND_ORDER)
    add(f"* Workbook data rows kept (district + BAiPP): **{len(raw_records)}** → records after merging duplicates: "
        f"**{n}** ({kind_totals}).")
    if permits:
        pk = Counter(r["kind"] for r in permits)
        add(f"* Building permits and notifications (RWDZ): **{len(permits)}** ("
            + ", ".join(f"{KINDS[k]['short']} {pk.get(k, 0)}" for k in PERMIT_KINDS) + ").")
    multi_src = [r for r in records if len(r.get("sources") or []) > 1]
    add(f"* Records listed in more than one source row: {len(multi_src)}"
        + (f" ({', '.join(ref(r['id']) for r in multi_src[:20])})" if multi_src else "") + ".")
    procedures = Counter(r.get("procedure") or "null" for r in records)
    add("* Procedure (WZ vs public purpose, incl. initiated proceedings): "
        + ", ".join(f"{k} {v}" for k, v in sorted(procedures.items())) + ".")
    applicants = Counter(r.get("applicant_type") for r in records)
    add(f"* Applicants (WZ/ULICP): natural persons {applicants.get('person', 0)}, organisations "
        f"{applicants.get('organization', 0)}, unknown {applicants.get('unknown', 0)}.")
    add("")
    years = sorted({(r.get("date") or r.get("period") or "????")[:4] for r in records})
    add("WZ/ULICP records per year (decision / initiation date):")
    add("")
    add("| Year | " + " | ".join(KINDS[k]["short"] for k in KIND_ORDER) + " | Total |")
    add("|---|" + "---:|" * (len(KIND_ORDER) + 1))
    per_year = Counter(((r.get("date") or r.get("period") or "????")[:4], r["kind"]) for r in records)
    for y in years:
        row = [per_year.get((y, k), 0) for k in KIND_ORDER]
        add(f"| {y} | " + " | ".join(str(c) for c in row) + f" | {sum(row)} |")
    add("| **all** | " + " | ".join(f"**{by_kind.get(k, 0)}**" for k in KIND_ORDER) + f" | **{n}** |")
    add("")

    # ---------------------------------------------------------------- declared vs parsed
    add("## Declared vs parsed counts")
    add("")
    add("Each monthly page states how many entries each list has (\"3 pozycje\"). `parsed` counts the data rows "
        "read from the files first published on that page (a leftover link to an earlier month's file is not "
        "counted twice).")
    add("")
    blocks = [(p, b) for p in pages for b in p["blocks"]]
    district_raw = [r for r in raw_records if _dataset_of(r) == "district"]
    district_records = [r for r in records if _dataset_of(r) == "district"]
    rows_by_kind: Counter[str] = Counter(r["kind"] for r in district_raw)
    district_by_kind: Counter[str] = Counter(r["kind"] for r in district_records)
    add("| Kind | Declared (blocks with a number) | Parsed in those blocks | Parsed in blocks without a number "
        "| Parsed rows | Duplicates merged | Records |")
    add("|---|---:|---:|---:|---:|---:|---:|")
    for k in KIND_ORDER:
        kb = [(p, b) for p, b in blocks if b.get("category") == k]
        declared = sum(b["declared_count"] for _, b in kb if b.get("declared_count") is not None)
        parsed_d = sum(b["parsed_count"] or 0 for _, b in kb if b.get("declared_count") is not None)
        parsed_u = sum(b["parsed_count"] or 0 for _, b in kb if b.get("declared_count") is None)
        merged = rows_by_kind.get(k, 0) - district_by_kind.get(k, 0)
        add(f"| {KINDS[k]['short']} | {declared} | {parsed_d} | {parsed_u} | {rows_by_kind.get(k, 0)} | "
            f"{merged} | {district_by_kind.get(k, 0)} |")
    add("")
    mismatches = [(p, b) for p, b in blocks if b.get("count_mismatch")]
    if mismatches:
        add(f"**{len(mismatches)} block(s) where the declared count differs from the file:**")
        add("")
        add("| Month | Block text | Declared | Parsed | Files |")
        add("|---|---|---:|---:|---|")
        for p, b in mismatches:
            links = ", ".join(f"[{_md(files_by_id[f]['filename'])}]({files_by_id[f]['url']})"
                              for f in b["file_ids"] if f in files_by_id) or "no file linked"
            add(f"| [{_md(p.get('title'))}]({p['url']}) | {_md(b['text'])} | {b['declared_count']} | "
                f"{b['parsed_count']} | {links} |")
    else:
        add("All blocks with a declared count match the parsed files.")
    add("")
    undeclared = [(p, b) for p, b in blocks if b.get("declared_count") is None and b.get("file_ids")]
    if undeclared:
        add(f"Blocks that link a file but state no count ({len(undeclared)}; parsed rows are not checked): "
            + "; ".join(f"[{_md(p.get('title'))}]({p['url']}) {KINDS.get(b.get('category'), {}).get('short', '?')} "
                        f"→ {b['parsed_count']}" for p, b in undeclared) + ".")
        add("")
    relinked = [(p, b) for p, b in blocks if len(b.get("file_ids") or []) > 1]
    if relinked:
        add("Blocks linking several files (the extra link points to an earlier month's file, counted on its own "
            "page): " + "; ".join(f"[{_md(p.get('title'))}]({p['url']}) "
                                  f"{KINDS.get(b.get('category'), {}).get('short', '?')}" for p, b in relinked) + ".")
        add("")

    # ---------------------------------------------------------------- numbering gaps
    gaps = numbering_gaps(records)
    add("## Completeness: gaps in decision numbering")
    add("")
    add("WZ and CP decisions are numbered consecutively per year, so a number that never appears in any file is a "
        "decision that was not published in these lists (or a refusal/discontinuation the office does not list). "
        "Numbering restarts every year at 1; in the first year only numbers after the lowest one seen count, because "
        "the publication started in August 2020. (District numbering only: BAiPP numbers its decisions city-wide.)")
    add("")
    add("| Kind | Year | Published | Range seen | Missing | Missing numbers |")
    add("|---|---|---:|---|---:|---|")
    for (kind, year), (seen, missing) in sorted(gaps.items()):
        add(f"| {KINDS[kind]['short']} | {year} | {len(seen)} | {min(seen)}–{max(seen)} | {len(missing)} | "
            f"{', '.join(map(str, missing)) or '—'} |")
    add("")
    ws_signs = Counter(m.group(1) for r in records if (m := re.match(r"^ws-\d{4}-(\d{4})-\d+$", r["id"])))
    if ws_signs:
        add("Initiated proceedings use case signs whose numbering is shared with other cases of the same JRWA symbol, "
            "so gaps there are expected and not listed.")
        add("")

    # ---------------------------------------------------------------- BAiPP, RWDZ, relations
    L.extend(_baipp_report(all_pages, all_files, records, ref))
    L.extend(_rwdz_report(permit_stage, all_files, permits, ref, site_url))
    L.extend(_related_report(records, permits, ref))

    # ---------------------------------------------------------------- geocoding
    add("## Geolocation")
    add("")
    groups = {d: [r for r in everything if _dataset_of(r) == d] for d in present}
    add("| Method | " + " | ".join(DATASETS[d]["short"] for d in present) + " |")
    add("|---|" + "---:|" * len(present))
    methods = {d: Counter((r.get("geo") or {}).get("method") or "none" for r in g) for d, g in groups.items()}
    for m, label in (("parcel", "parcel (ULDK centroid)"), ("address", "address point (UUG)"),
                     ("street", "street / crossing (approximate)"), ("none", "not located")):
        add(f"| {label} | " + " | ".join(f"{methods[d].get(m, 0)} ({_pct(methods[d].get(m, 0), len(groups[d]))})"
                                         for d in present) + " |")
    add("| **located** | " + " | ".join(
        f"**{len(groups[d]) - methods[d].get('none', 0)}** (**{_pct(len(groups[d]) - methods[d].get('none', 0), len(groups[d]))}**)"
        for d in present) + " |")
    add("")
    gs = geo_stats or {}
    if gs:
        add(f"* Unique parcel ids (all datasets): {gs.get('parcels_unique', 0)}; found in ULDK {gs.get('parcels_ok', 0)} "
            f"({_pct(gs.get('parcels_ok', 0), gs.get('parcels_unique', 0))}), missing {gs.get('parcels_missing', 0)}, "
            f"lookup errors {gs.get('parcels_error', 0)}.")
        add(f"* Records with parcels: {gs.get('records_with_parcels', 0)} – all found "
            f"{gs.get('records_all_parcels_found', 0)}, some {gs.get('records_some_parcels_found', 0)}, "
            f"none {gs.get('records_no_parcel_found', 0)}.")
        add(f"* Precinct of the source corrected by the parcel under the exact address (ULDK GetParcelByXY; a "
            f"warning on the record): {gs.get('obreb_corrected_by_address', 0)}.")
        add(f"* Address vs parcel conflicts (> 300 m; parcel point kept): {gs.get('address_parcel_conflicts', 0)}, "
            f"of which the address lies on a parcel of another precinct (`geo.conflict`): "
            f"{gs.get('address_parcel_conflicts_flagged', 0)}; "
            f"parcels > 1 km apart: {gs.get('records_spread_parcels', 0)}; "
            f"point moved onto the largest parcel (centroid on none of them): "
            f"{gs.get('records_point_on_largest_parcel', 0)}; "
            f"point from the parcels in the district only (others lie in a neighbouring district): "
            f"{gs.get('records_parcels_in_district_only', 0)}; "
            f"points discarded outside the district: {gs.get('outside_district_discarded', 0)}.")
        missing = gs.get("missing_parcel_examples") or []
        if missing:
            add(f"* Parcel ids ULDK does not know (first {len(missing)}): " + ", ".join(f"`{p}`" for p in missing) + ".")
    for d in present:
        areas = Counter(r.get("area") or "(none)" for r in groups[d])
        add(f"* Records per MSI area ({DATASETS[d]['short']}): "
            + ", ".join(f"{k} {v}" for k, v in sorted(areas.items())) + ".")
    add("")
    for d in present:
        unlocated = [r for r in groups[d] if not (r.get("geo") or {}).get("method")]
        if not unlocated:
            continue
        limit = 60
        add(f"{DATASETS[d]['short']} records without a location ({len(unlocated)}"
            + (f", first {limit} shown" if len(unlocated) > limit else "") + "):")
        add("")
        add("| Record | Address | Parcels (as in source) | Note |")
        add("|---|---|---|---|")
        for r in unlocated[:limit]:
            add(f"| {ref(r['id'])} | {_md((r.get('address') or {}).get('display'))} | {_md(r.get('parcels_raw'))} "
                f"| {_md((r.get('geo') or {}).get('note'))} |")
        add("")
    notes: dict[str, Counter] = defaultdict(Counter)
    note_examples: dict[str, list[str]] = defaultdict(list)
    for r in everything:
        for note in ((r.get("geo") or {}).get("note") or "").split("; "):
            if note:
                cat = warning_category(note)
                notes[cat][_dataset_of(r)] += 1
                note_examples[cat].append(r["id"])
    if notes:
        add("Location notes:")
        add("")
        _per_dataset_table(L, "Note", notes, note_examples, present, ref)
        add("")

    # ---------------------------------------------------------------- warnings
    wcount: dict[str, Counter] = defaultdict(Counter)
    wexamples: dict[str, list[str]] = defaultdict(list)
    for r in everything:
        for w in r.get("warnings") or []:
            cat = warning_category(w)
            wcount[cat][_dataset_of(r)] += 1
            wexamples[cat].append(r["id"])
    add("## Record warnings")
    add("")
    if wcount:
        add(f"{sum(1 for r in everything if r.get('warnings'))} records carry "
            f"{sum(sum(c.values()) for c in wcount.values())} warnings (shown in the UI next to the record).")
        add("")
        _per_dataset_table(L, "Warning type", wcount, wexamples, present, ref)
    else:
        add("No record warnings.")
    add("")

    # ---------------------------------------------------------------- tags
    func = {s for s, t in TAGS.items() if t.get("group") == "funkcja"}
    add("## Classification")
    add("")
    add("| Tag | Group | " + " | ".join(DATASETS[d]["short"] for d in present) + " |")
    add("|---|---|" + "---:|" * len(present))
    tag_counts = {d: Counter(t for r in groups[d] for t in r.get("tags") or []) for d in present}
    for slug, t in TAGS.items():
        add(f"| {_md(t['label'])} (`{slug}`) | {t.get('group', '')} | "
            + " | ".join(str(tag_counts[d].get(slug, 0)) for d in present) + " |")
    add("")
    for d in present:
        untagged = [r["id"] for r in groups[d] if not r.get("tags")]
        no_func = [r["id"] for r in groups[d] if not set(r.get("tags") or []) & func]
        limit = None if d != rwdz_mod.DATASET else 30
        add(f"* {DATASETS[d]['short']} – untagged records: {len(untagged)}"
            + (f" – {_refs(untagged, ref, limit or len(untagged))}" if untagged else "") + "; "
            f"without a \"what is built\" (funkcja) tag: {len(no_func)}"
            + (f" – {_refs(no_func, ref, limit or len(no_func))}" if no_func else "") + ".")
    add("")

    # ---------------------------------------------------------------- street spellings
    spellings: dict[str, Counter] = defaultdict(Counter)
    for r in everything:
        a = r.get("address") or {}
        for name in dict.fromkeys([a.get("street"), *[(p or {}).get("street") for p in a.get("parts") or []]]):
            if isinstance(name, str) and name.strip() and street_key(name):
                spellings[street_key(name)][name.strip()] += 1
    several = {k: c for k, c in spellings.items() if len(c) > 1}
    add("## Street names")
    add("")
    add(f"* Streets: {len(spellings)}. One spelling per street in `address.street` (the site's street filter lists "
        f"every spelling separately; `normalize.STREET_CANONICAL` maps {len(STREET_CANONICAL)} streets written in "
        f"several ways to one, `address.display` keeps the source text).")
    add("* Still written in several ways (add them to `STREET_CANONICAL`): "
        + ("; ".join(f"`{k}`: " + ", ".join(f"„{_md(n)}” {c}" for n, c in sorted(v.items(), key=lambda kv: (-kv[1], kv[0])))
                     for k, v in sorted(several.items())) or "none") + ".")
    add("")

    # ---------------------------------------------------------------- files & pages
    add("## Source files and pages")
    add("")
    pages, files = all_pages, all_files
    layouts = Counter(f.get("layout") or "(none)" for f in files)
    add("* Layouts: " + ", ".join(f"{k} {v}" for k, v in sorted(layouts.items())) + ".")
    add(f"* Template rows skipped (only a pre-printed Lp number): {sum(f.get('skipped_rows') or 0 for f in files)}.")
    add("* Files linked from more than one page: "
        + (", ".join(f"[{_md(f['filename'])}]({f['url']})" for f in files if len(f.get("page_ids") or []) > 1)
           or "none") + ".")
    errors = [f for f in files if f.get("error")]
    if errors:
        add("* Download errors: " + "; ".join(f"`{f['file_id']}` {_md(f['error'])}" for f in errors) + ".")
    removed = [p for p in pages if p.get("removed_from_source_at")]
    if removed:
        add("* Pages no longer listed by the source (kept): "
            + ", ".join(f"[{_md(p['title'])}]({p['url']}) since {p['removed_from_source_at']}" for p in removed) + ".")
    unlinked = [f for f in files if f.get("removed_from_source_at")]
    if unlinked:
        add("* Files no longer linked by the source (kept as snapshots): "
            + ", ".join(f"[{_md(f['filename'])}]({f['url']}) since {f['removed_from_source_at']}" for f in unlinked)
            + ".")
    add("")
    fw = [f for f in files if f.get("warnings")]
    if fw:
        add("File warnings:")
        add("")
        for f in fw:
            add(f"* [{_md(f['filename'])}]({f['url']}): " + "; ".join(_md(w) for w in f["warnings"]))
        add("")
    pw = [(p, w) for p in pages for w in p.get("warnings") or []]
    if pw:
        add(f"Page warnings from the crawler ({len(pw)}):")
        add("")
        for p, w in pw:
            add(f"* [{_md(p.get('title'))}]({p['url']}): {_md(w)}")
        add("")
    return "\n".join(L).rstrip("\n") + "\n"


# =============================================================================
# Orchestration
# =============================================================================


@dataclass
class BuildResult:
    records: list[dict]           # records.json (district + BAiPP)
    sources_doc: dict
    generated_at: str
    written: list[Path]
    crawl_error: str | None
    geo_stats: dict
    exit_code: int
    permits: list[dict] = field(default_factory=list)   # permits.json (RWDZ pb + zg)
    rwdz_error: str | None = None
    lost_files: list[str] = field(default_factory=list)  # files that gave records before but cannot be read now


def _read_generated_at(path: Path) -> str | None:
    try:
        with path.open(encoding="utf-8") as fh:
            value = json.load(fh).get("generated_at")
    except (OSError, ValueError, AttributeError):
        return None
    return value if isinstance(value, str) else None


_FEED_SELF_RE = re.compile(r'<link rel="self" type="application/atom\+xml" href="(https?://[^"<>]+/)feed\.xml"/>')


def committed_site_url(paths: Paths) -> str | None:
    """The absolute public base URL of the committed ``site/feed.xml`` (its ``rel="self"`` link minus
    ``feed.xml``), or None. The default when neither ``site_url`` nor ``$SITE_URL`` is given, so a local
    build after a CI data commit renders the same links as CI did (no CSV/feed/report ping-pong)."""
    try:
        with paths.feed.open(encoding="utf-8") as fh:
            head = fh.read(4096)
    except OSError:
        return None
    m = _FEED_SELF_RE.search(head)
    return m.group(1).replace("&amp;", "&") if m else None


def _check_unique_ids(*groups: Sequence[Mapping[str, Any]]) -> None:
    """Record ids are permalinks: they must be unique across all datasets (namespaced by design)."""
    seen: Counter[str] = Counter(r["id"] for group in groups for r in group)
    dupes = sorted(rid for rid, n in seen.items() if n > 1)
    if dupes:
        raise BuildError(f"duplicate record ids across datasets: {', '.join(dupes[:10])}")


def split_parcels(features: Sequence[Mapping[str, Any]], planning_ids: set[str]) -> tuple[list, list]:
    """``(parcels.geojson features, parcels-permits.geojson features)``: a parcel referenced by any
    ``records.json`` record goes to the first file (its ``records`` list keeps the permit ids too);
    a parcel referenced only by permits goes to the second, which the site loads with permits.json."""
    planning, permits_only = [], []
    for f in features:
        (planning if set(f["properties"]["records"]) & planning_ids else permits_only).append(f)
    return planning, permits_only


def run_build(
    paths: Paths | None = None,
    *,
    crawl: bool = True,
    online: bool = True,
    refresh: bool = False,
    refresh_misses: bool = False,
    site_url: str | None = None,
    session: requests.Session | None = None,
    geo_session: Any = None,
    rwdz: bool | None = None,
    now: Callable[[], str] = _now_iso,
) -> BuildResult:
    """Run the whole pipeline and write every output (see module docstring).

    ``crawl``/``online`` = False skip the source downloads (crawl + RWDZ) / all network access
    (geocoding from caches only). ``session`` is used by the crawler and the RWDZ download,
    ``geo_session`` by the geocoder (tests inject fakes). ``rwdz``: None = include GUNB RWDZ when
    possible (see :func:`obtain_permits`), False = leave it out.
    """
    paths = paths or Paths()
    if site_url is None:
        site_url = os.environ.get("SITE_URL") or committed_site_url(paths) or "./"

    # 1. manifest (district + BAiPP pages and files)
    manifest, crawl_error = obtain_manifest(paths, crawl=crawl and online, refresh=refresh, session=session)
    log.info("manifest: %d pages, %d files", len(manifest.get("pages", [])), len(manifest.get("files", [])))

    # 2. parse + normalise the workbooks
    raw_records, results = parse_sources(manifest, paths.root)
    log.info("parsed %d rows from %d files", len(raw_records), sum(1 for r in results.values() if r.parsed_count))
    lost = lost_files(paths, results)
    if lost:
        log.error("files that gave records in the previous build cannot be read now: %s", ", ".join(lost))

    # 3. one record per decision
    records = merge_records(raw_records)
    log.info("%d records after merging duplicates", len(records))

    # 3b. building permits and notifications (GUNB RWDZ): downloaded with the crawl, else the committed extracts
    stage = obtain_permits(paths, enabled=rwdz, online=crawl and online, refresh=refresh, session=session)
    permits = stage.records
    _check_unique_ids(records, permits)
    log.info("%d permit records (RWDZ)", len(permits))

    # 4. geolocation (fills geo + area in place) – one pass over every dataset, sharing the caches. BAiPP
    #    rows labelled "Praga Południe" whose parcels ULDK places in another district keep their data but
    #    are not put on the district map.
    if online and geo_session is None:
        geo_session = GeoSession()
    outside = baipp.check_out_of_district(records, cache_dir=str(paths.cache), online=online, session=geo_session,
                                          refresh_misses=refresh_misses, log=log.info)
    for r in records:
        if r["id"] in outside:
            r["geo"], r["area"] = baipp.unplaced_geo(), None
    area_index = areas_mod.load_areas(str(paths.cache), str(paths.areas_geojson))
    geo = locate_records([r for r in records if r["id"] not in outside] + permits, cache_dir=str(paths.cache),
                         online=online, log=log.info, session=geo_session, area_index=area_index,
                         areas_out=str(paths.areas_geojson), refresh_misses=refresh_misses)
    if area_index is None:
        area_index = areas_mod.load_areas(str(paths.cache), str(paths.areas_geojson))
    # 4b. GUNB cases with the Praga-Południe unit id but a precinct the district does not have, which could not
    #     be placed in the district: probed under the other Warsaw units like the BAiPP rows above
    moved_out = baipp.check_out_of_district_permits(permits, is_pp_obreb=is_pp_obreb, cache_dir=str(paths.cache),
                                                    online=online, session=geo_session,
                                                    refresh_misses=refresh_misses, log=log.info)
    for r in permits:
        if r["id"] in moved_out:
            r["geo"], r["area"] = baipp.unplaced_geo(), None

    # 5. relations – across all datasets (a WZ decision ↔ the building permit on the same parcel)
    compute_related([*records, *permits])
    records = [order_record(r) for r in records]
    permits = [order_record(r) for r in permits]

    # 6. mirror originals, then render every output
    mirrored = mirror_sources(manifest, paths)
    rwdz_pages, rwdz_files = rwdz_sources(stage, mirror_rwdz(stage.files if stage.enabled else [], paths))
    area_labels = {slug: {"label": label} for slug, label in sorted((area_index.labels if area_index else {}).items())}
    tags = {slug: dict(t) for slug, t in TAGS.items()}
    kinds = {k: KINDS[k] for k in (ALL_KINDS if stage.enabled else KIND_ORDER)}
    datasets = {k: v for k, v in DATASETS.items() if stage.enabled or k != "rwdz"}
    by_kind = Counter(r["kind"] for r in (*records, *permits) if r.get("kind"))
    counts_by_kind = {k: by_kind.get(k, 0) for k in (*kinds, *sorted(set(by_kind) - set(kinds)))}
    planning_parcels, permit_parcels = split_parcels(geo["parcels_geojson"]["features"], {r["id"] for r in records})
    parcels_doc = {"type": "FeatureCollection", "attribution": PARCELS_ATTRIBUTION, "source": PARCELS_SOURCE,
                   "features": planning_parcels}
    permit_parcels_doc = {"type": "FeatureCollection", "attribution": PARCELS_ATTRIBUTION, "source": PARCELS_SOURCE,
                          "features": permit_parcels}

    def render(generated_at: str) -> tuple[dict[Path, bytes], dict]:
        sources_doc = build_sources_doc(manifest, results, records, mirrored, generated_at)
        sources_doc["pages"] += rwdz_pages
        sources_doc["files"] += rwdz_files
        files_by_id = {f["file_id"]: f for f in sources_doc["files"]}
        pages_by_id = {p["page_id"]: p for p in sources_doc["pages"]}
        records_doc = {
            "generated_at": generated_at,
            "source_index_url": manifest.get("index_url"),
            "count": len(records),
            "kinds": kinds,
            "tags": tags,
            "areas": area_labels,
            "datasets": datasets,
            "issuers": ISSUERS,
            "outcomes": OUTCOMES,
            "permit_scopes": PERMIT_SCOPES if stage.enabled else {},
            "permit_categories": PERMIT_CATEGORIES if stage.enabled else {},
            "counts_by_kind": counts_by_kind,
            "records": records,
        }
        permits_doc = {"generated_at": generated_at, "count": len(permits), "records": permits}
        ctx = dict(kinds=kinds, tags=tags, areas=area_labels, files_by_id=files_by_id, pages_by_id=pages_by_id,
                   site_url=site_url)
        csv_dicts = {"datasets": datasets, "issuers": ISSUERS, "outcomes": OUTCOMES, "categories": PERMIT_CATEGORIES}
        outputs = {   # the data documents first (see data_paths below), then the ones that embed site_url
            paths.records_json: dumps_json(records_doc, ("records",)),
            paths.permits_json: dumps_json(permits_doc, ("records",)),
            paths.sources_json: dumps_json(sources_doc, ("pages", "files")),
            paths.parcels_geojson: dumps_json(parcels_doc, ("features",)),
            paths.parcels_permits_geojson: dumps_json(permit_parcels_doc, ("features",)),
            paths.records_csv: export.records_to_csv(records, **ctx, **csv_dicts).encode("utf-8"),
            paths.permits_csv: export.records_to_csv(permits, **ctx, **csv_dicts).encode("utf-8"),
            paths.feed: export.atom_feed(records, generated_at=generated_at, datasets=datasets, outcomes=OUTCOMES,
                                         **ctx).encode("utf-8"),
            paths.report: build_report(manifest=manifest, sources_doc=sources_doc, records=records,
                                       raw_records=raw_records, results=results, geo_stats=geo["stats"],
                                       generated_at=generated_at, site_url=site_url, crawl_error=crawl_error,
                                       permits=permits, permit_stage=stage, lost=lost).encode("utf-8"),
        }
        return outputs, sources_doc

    # Keep the previous generated_at when the data did not change (no diff on a no-op rebuild). Only the
    # data documents decide: the CSVs, the feed and the report embed site_url, so a build with another
    # SITE_URL (CI's Pages URL vs a local "./") re-renders those with the kept timestamp and leaves the
    # JSON alone (test.yml compares the committed JSON with an offline rebuild).
    data_paths = (paths.records_json, paths.permits_json, paths.sources_json, paths.parcels_geojson,
                  paths.parcels_permits_geojson)
    previous_at = _read_generated_at(paths.records_json)
    outputs = sources_doc = None
    generated_at = previous_at
    if previous_at:
        outputs, sources_doc = render(previous_at)
        if not all(p.is_file() and p.read_bytes() == outputs[p] for p in data_paths):
            outputs = None
    if outputs is None:
        generated_at = now()
        outputs, sources_doc = render(generated_at)
    written = [p for p, data in outputs.items() if write_atomic(p, data)]
    for p in written:
        log.info("wrote %s", p.relative_to(paths.root) if p.is_relative_to(paths.root) else p)
    if not written:
        log.info("no changes – outputs are up to date (generated_at %s)", generated_at)

    stats = geo["stats"]
    for label, group in (("records", records), ("permits", permits)):
        m = Counter((r.get("geo") or {}).get("method") or "none" for r in group)
        log.info("%s: %d (%s); located: parcel %d, address %d, street %d, none %d", label, len(group),
                 ", ".join(f"{k} {v}" for k, v in sorted(Counter(r["kind"] for r in group).items())),
                 m["parcel"], m["address"], m["street"], m["none"])
    log.info("geocoding: %s UUG requests, %s errors, %.1f s", stats.get("uug_requests"), stats.get("uug_errors"),
             stats.get("seconds") or 0)
    stale = crawl_error or stage.error or lost
    return BuildResult(records=records, sources_doc=sources_doc, generated_at=generated_at, written=written,
                       crawl_error=crawl_error, geo_stats=stats, exit_code=EXIT_STALE if stale else EXIT_OK,
                       permits=permits, rwdz_error=stage.error, lost_files=lost)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m pipeline.build", description=__doc__.split("\n\n")[0])
    parser.add_argument("--offline", action="store_true",
                        help="no network: use data/manifest.json, the committed RWDZ extracts and the geocoding "
                             "caches only (implies --skip-crawl)")
    parser.add_argument("--skip-crawl", action="store_true",
                        help="reuse data/manifest.json and the committed RWDZ extracts instead of downloading")
    parser.add_argument("--refresh", action="store_true", help="re-download every source file during the crawl")
    parser.add_argument("--refresh-misses", action="store_true",
                        help="retry cached geocoding misses regardless of their age")
    parser.add_argument("--site-url", default=None,
                        help="public base URL for permalinks in the CSV/feed/report (default: $SITE_URL, else the "
                             "absolute URL of the committed site/feed.xml, else ./)")
    parser.add_argument("--root", type=Path, default=PROJECT_ROOT, help=argparse.SUPPRESS)
    parser.add_argument("-q", "--quiet", action="store_true", help="only print warnings and errors")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.WARNING if args.quiet else logging.INFO,
                        format="%(levelname).1s %(name)s: %(message)s", stream=sys.stderr)
    try:
        result = run_build(Paths(args.root.resolve()), crawl=not (args.skip_crawl or args.offline),
                           online=not args.offline, refresh=args.refresh, refresh_misses=args.refresh_misses,
                           site_url=args.site_url)
    except BuildError as exc:
        log.error("%s", exc)
        return EXIT_FATAL
    if result.crawl_error:
        log.error("built from the previous manifest because the crawl failed: %s", result.crawl_error)
    if result.rwdz_error:
        log.error("built from the committed RWDZ extracts because GUNB's file changed: %s", result.rwdz_error)
    if result.lost_files:
        log.error("built without the rows of unreadable files: %s", ", ".join(result.lost_files))
    return result.exit_code


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
