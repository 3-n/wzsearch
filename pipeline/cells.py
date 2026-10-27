"""Source cells ("Dane w źródle") kept outside the record files (docs/plans/all-districts.md §2.2).

Every ``sources[]`` entry of a record carries ``raw``: the row's cells as ``[column label, value]`` pairs, shown
only in the detail's "Dane w źródle" panel. They are 25–40 % of the record files' bytes, so the build moves them to
small bucket files next to the records and the page fetches one bucket when the panel is opened:

    <site_data>/cells/r-<bb>.json   planning records (records.json)
    <site_data>/cells/p-<bb>.json   GUNB records (permits.json)

``<bb>`` is the record's bucket, :func:`bucket_of` (FNV-1a over the id's UTF-8 bytes, modulo the bucket count),
in two lowercase hex digits; ``site/js/cells.js`` computes the same. A bucket maps record id → one ``raw`` per
source (``null`` where a source has none), in the order of the record's ``sources``. The record file states the
set: ``"cells": {"prefix": "cells/r-", "buckets": 16}``.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

#: Average JSON bytes per bucket the count aims at (~5–10 kB gzip): one panel opening is one small request.
BUCKET_BYTES = 48_000
MAX_BUCKETS = 256
PREFIXES = {"records": "cells/r-", "permits": "cells/p-"}


def fnv1a32(text: str) -> int:
    """32-bit FNV-1a of ``text``'s UTF-8 bytes."""
    h = 0x811C9DC5
    for byte in text.encode("utf-8"):
        h = ((h ^ byte) * 0x01000193) & 0xFFFFFFFF
    return h


def bucket_of(record_id: str, buckets: int) -> int:
    return fnv1a32(record_id) % buckets


def bucket_count(total_bytes: int) -> int:
    """Smallest power of two (1…:data:`MAX_BUCKETS`) that keeps the average bucket under :data:`BUCKET_BYTES`."""
    n = 1
    while n < MAX_BUCKETS and total_bytes / n > BUCKET_BYTES:
        n *= 2
    return n


def split_cells(records: Iterable[dict[str, Any]]) -> dict[str, list[Any]]:
    """Remove ``raw`` from every source of ``records`` (in place); return record id → raws (records with any)."""
    out: dict[str, list[Any]] = {}
    for r in records:
        raws = [s.pop("raw", None) for s in r.get("sources") or []]
        if any(raw is not None for raw in raws):
            out[r["id"]] = raws
    return out


def _compact(v: Any) -> str:
    return json.dumps(v, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def bucket_files(cells: Mapping[str, list[Any]], site_data: Path, kind: str) -> tuple[dict, dict[Path, bytes]]:
    """``(meta, {path: bytes})`` of one set: ``meta`` goes into the record file as ``cells``; every bucket is
    written, empty ones too, so a record id never points at a missing file. One record per line (one-line diffs)."""
    prefix = PREFIXES[kind]
    n = bucket_count(sum(len(k) + len(_compact(v)) for k, v in cells.items()))
    buckets: list[dict[str, list[Any]]] = [{} for _ in range(n)]
    for rid in sorted(cells):
        buckets[bucket_of(rid, n)][rid] = cells[rid]
    files = {}
    for i, bucket in enumerate(buckets):
        lines = [f"{_compact(rid)}:{_compact(raws)}" for rid, raws in bucket.items()]
        body = "{\n" + ",\n".join(lines) + "\n}\n" if lines else "{}\n"
        files[site_data / f"{prefix}{i:02x}.json"] = body.encode("utf-8")
    return {"prefix": prefix, "buckets": n}, files


def stale_buckets(site_data: Path, keep: Iterable[Path]) -> list[Path]:
    """Bucket files of an earlier build that this one does not write (the bucket count shrank)."""
    keep = set(keep)
    folder = site_data / "cells"
    return sorted(p for p in folder.glob("[rp]-*.json") if p not in keep) if folder.is_dir() else []


__all__ = ["BUCKET_BYTES", "PREFIXES", "bucket_count", "bucket_files", "bucket_of", "fnv1a32", "split_cells",
           "stale_buckets"]
