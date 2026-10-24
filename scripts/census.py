#!/usr/bin/env python3
"""Data census: parse + normalise every downloaded workbook and report what came out.

Usage (from the project root)::

    uv run python scripts/census.py                       # uses data/manifest.json if present
    uv run python scripts/census.py --pages path/to/scout/pages.json
    uv run python scripts/census.py --json /tmp/census.json --verbose

Reports per-file row counts, detected kinds/layouts and warnings, global statistics (rows per
kind, unparseable dates / numbers / parcels, untagged records, duplicate ids) and compares the
number of parsed rows with the count declared on the monthly web page ("3 pozycje").

Declared counts and periods come from ``data/manifest.json`` (pipeline/crawl.py) or, before the
crawler has run, from a scouting ``pages.json`` (``[{page, title, blocks: [{text, hrefs}]}]``).
Without either, files are still parsed but nothing can be compared.
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import html
import json
import re
import sys
import urllib.parse
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.classify import TAGS  # noqa: E402
from pipeline.normalize import merge_duplicates, normalize_row  # noqa: E402
from pipeline.parse import parse_workbook  # noqa: E402
from pipeline.textutil import collapse_ws, fold, month_from_text  # noqa: E402

CATEGORY_PATTERNS = [
    ("ws", r"wszcz"),
    ("cp", r"celu\s+publiczn|\bcp\b|lokalizacji\s+inwestycji"),
    ("wz", r"warunk\w*\s+zabudow"),
]


# --------------------------------------------------------------------------- page metadata


def block_counts(text: str) -> dict[str, int | None]:
    """Declared counts per category in a block text.

    Handles one-category blocks ("Wydane decyzje o warunkach zabudowy: 3 pozycje") as well as the
    May 2023 block that lists all three categories in one paragraph, and "BRAK" (= 0).
    """
    f = collapse_ws(fold(text))
    hits: list[tuple[int, str]] = []
    for cat, rx in CATEGORY_PATTERNS:
        for m in re.finditer(rx, f):
            hits.append((m.start(), cat))
    hits.sort()
    # a ws block also mentions "warunkach zabudowy" / "celu publicznego": keep the first category
    # of each run until a count appears
    out: dict[str, int | None] = {}
    i = 0
    while i < len(hits):
        start, cat = hits[i]
        j = i + 1
        while j < len(hits) and not re.search(r"\d+\s*poz|brak", f[start:hits[j][0]]):
            j += 1
        end = hits[j][0] if j < len(hits) else len(f)
        seg = f[start:end]
        m = re.search(r"(\d+)\s*poz", seg)
        if m:
            out.setdefault(cat, int(m.group(1)))
        elif re.search(r"\bbrak\b", seg):
            out.setdefault(cat, 0)
        else:
            out.setdefault(cat, None)
        i = j
    return out


def period_from_title(title: str) -> str | None:
    month = month_from_text(title)
    year = re.search(r"(20\d\d)", title or "")
    if month and year:
        return f"{year.group(1)}-{month:02d}"
    return None


def file_id_for(href: str) -> str:
    """DATA_MODEL.md: sha1 of the HTML-unescaped href without the query string, first 10 hex chars."""
    path = html.unescape(href).split("?", 1)[0]
    if path.startswith("http"):
        path = urllib.parse.urlsplit(path).path
    return hashlib.sha1(path.encode()).hexdigest()[:10]


def load_pages(manifest: Path | None, scout_pages: Path | None) -> dict[str, list[dict[str, Any]]]:
    """file_id → list of {page_id, period, block_text, declared (by category), n_files}."""
    links: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
    if manifest and manifest.exists():
        data = json.loads(manifest.read_text())
        for page in data.get("pages", []):
            for block in page.get("blocks", []):
                for fid in block.get("file_ids", []):
                    links[fid].append({"page_id": page.get("page_id"), "period": page.get("period"),
                                       "block": block.get("text", ""), "declared": block_counts(block.get("text", "")),
                                       "n_files": len(block.get("file_ids", [])),
                                       "category": block.get("category")})
        return links
    if scout_pages and scout_pages.exists():
        for page in json.loads(scout_pages.read_text()):
            page_id = page["page"].rsplit("/-/", 1)[-1]
            period = period_from_title(page.get("title", ""))
            for block in page.get("blocks", []):
                hrefs = block.get("hrefs", [])
                for href in hrefs:
                    links[file_id_for(href)].append({"page_id": page_id, "period": period,
                                                     "block": block.get("text", ""),
                                                     "declared": block_counts(block.get("text", "")),
                                                     "n_files": len(hrefs), "category": None})
    return links


# --------------------------------------------------------------------------- census


def warning_category(w: str) -> str:
    """Collapse a concrete warning into its category (quotes, numbers and ids removed)."""
    w = re.sub(r"„[^”]*”", "„…”", w)
    w = re.sub(r"arkusz „…”: ", "", w)
    w = re.sub(r"\b[0-9][0-9./\-]*\b", "N", w)
    w = re.sub(r"kolumn[ay] [A-Z]+( i [A-Z]+)?", "kolumna X", w)
    return w


def run(raw_dir: Path, links: dict[str, list[dict[str, Any]]], verbose: bool = False) -> dict[str, Any]:
    files = sorted(raw_dir.glob("*.xlsx"))
    per_file: list[dict[str, Any]] = []
    records: list[dict[str, Any]] = []
    file_warn = collections.Counter()
    rec_warn = collections.Counter()
    rec_warn_examples: dict[str, str] = {}
    for path in files:
        fid = path.stem
        meta = links.get(fid, [])
        periods = sorted(p["period"] for p in meta if p.get("period"))
        period = periods[0] if periods else None
        page_id = next((p["page_id"] for p in meta if p.get("period") == period), meta[0]["page_id"] if meta else None)
        try:
            pf = parse_workbook(path)
        except Exception as exc:  # noqa: BLE001 – census must report, not crash
            per_file.append({"file_id": fid, "error": repr(exc)})
            continue
        recs = [normalize_row(r, pf["kind"], {"file_id": fid, "page_id": page_id, "period": period})
                for r in pf["rows"]]
        records.extend(recs)
        for w in pf["warnings"]:
            file_warn[warning_category(w)] += 1
        for r in recs:
            for w in r["warnings"]:
                cat = warning_category(w)
                rec_warn[cat] += 1
                rec_warn_examples.setdefault(cat, f"{r['id']}: {w}")

        declared: list[dict[str, Any]] = []
        for link in meta:
            counts = link["declared"]
            value = counts.get(pf["kind"]) if pf["kind"] in counts else (
                next(iter(counts.values())) if len(counts) == 1 else None)
            declared.append({"page_id": link["page_id"], "declared": value, "n_files": link["n_files"],
                             "block_categories": sorted(counts)})
        n = len(recs)
        mismatch = [d for d in declared if d["declared"] is not None and d["declared"] != n and d["n_files"] == 1]
        multi = [d for d in declared if d["n_files"] > 1]
        block_cats = {c for d in declared for c in d["block_categories"]}
        per_file.append({
            "file_id": fid, "period": period, "page_ids": [d["page_id"] for d in declared],
            "kind": pf["kind"], "layout": pf["layout"], "period_label": pf["period_label"],
            "rows": n, "skipped_template_rows": len(pf["skipped"]),
            "declared": [d["declared"] for d in declared], "count_mismatch": bool(mismatch),
            "multi_file_block": bool(multi),
            "kind_vs_block": (sorted(block_cats) if pf["kind"] and block_cats and pf["kind"] not in block_cats
                              else None),
            "file_warnings": pf["warnings"],
            "record_warnings": sum(len(r["warnings"]) for r in recs),
        })

    merged = merge_duplicates(records)
    ids = collections.Counter(r["id"] for r in records)
    dup_ids = {k: v for k, v in ids.items() if v > 1}
    by_kind = collections.Counter(r["kind"] for r in merged)
    func_tags = {s for s, t in TAGS.items() if t.get("group") == "funkcja"}
    with_parcels_raw = [r for r in records if r["parcels_raw"].strip()]
    stats = {
        "files": len(files),
        "files_with_rows": sum(1 for f in per_file if f.get("rows")),
        "rows_parsed": len(records),
        "records_after_merge": len(merged),
        "records_per_kind": dict(by_kind),
        "rows_per_kind": dict(collections.Counter(r["kind"] for r in records)),
        "procedure": dict(collections.Counter(str(r["procedure"]) for r in merged)),
        "applicant_type": dict(collections.Counter(r["applicant_type"] for r in merged)),
        "skipped_template_rows": sum(f.get("skipped_template_rows", 0) for f in per_file),
        "no_date": sum(1 for r in records if not r["date"]),
        "no_number": sum(1 for r in records if not r["number"]),
        "fallback_ids": sum(1 for r in records if re.search(r"-f[0-9a-f]{10}-r\d+$", r["id"])),
        "rows_with_parcels_raw": len(with_parcels_raw),
        "rows_with_parcels": sum(1 for r in with_parcels_raw if r["parcels"]),
        "parcel_refs": sum(len(r["parcels"]) for r in records),
        "unique_parcels": len({p["id"] for r in records for p in r["parcels"]}),
        "address_without_street": sum(1 for r in records if r["address"]["raw"].strip() and not r["address"]["street"]),
        "untagged": [r["id"] for r in merged if not r["tags"]],
        "no_function_tag": [r["id"] for r in merged if not set(r["tags"]) & func_tags],
        "tag_counts": dict(collections.Counter(t for r in merged for t in r["tags"]).most_common()),
        "duplicate_ids": dup_ids,
        "count_mismatches": [f for f in per_file if f.get("count_mismatch")],
        "kind_vs_block": [f for f in per_file if f.get("kind_vs_block")],
        "file_warning_categories": dict(file_warn.most_common()),
        "record_warning_categories": dict(rec_warn.most_common()),
        "record_warning_examples": rec_warn_examples,
    }
    return {"stats": stats, "files": per_file, "records": merged if verbose else None}


def print_report(report: dict[str, Any], verbose: bool) -> None:
    s = report["stats"]
    p = print
    p(f"Files: {s['files']} (with data rows: {s['files_with_rows']})")
    p(f"Rows parsed: {s['rows_parsed']}  → records after merging duplicates: {s['records_after_merge']}")
    p(f"Rows per kind: {s['rows_per_kind']}   records per kind: {s['records_per_kind']}")
    p(f"Procedure: {s['procedure']}   applicant type: {s['applicant_type']}")
    p(f"Template rows skipped (only an Lp number): {s['skipped_template_rows']}")
    p(f"No date: {s['no_date']}   no number: {s['no_number']}   fallback ids: {s['fallback_ids']}")
    share = s["rows_with_parcels"] / s["rows_with_parcels_raw"] if s["rows_with_parcels_raw"] else 0
    p(f"Parcels: {s['rows_with_parcels']}/{s['rows_with_parcels_raw']} rows with parcel text parsed "
      f"({share:.1%}); {s['parcel_refs']} references, {s['unique_parcels']} unique parcels")
    p(f"Addresses without a recognised street: {s['address_without_street']}")
    p(f"Untagged records: {len(s['untagged'])} {s['untagged']}")
    p(f"Records without a function tag: {len(s['no_function_tag'])} {s['no_function_tag']}")
    p(f"Tags: {s['tag_counts']}")
    p(f"Duplicate ids before merge: {s['duplicate_ids']}")
    p("\nDeclared vs parsed counts (single-file blocks):")
    if not s["count_mismatches"]:
        p("  all match")
    for f in s["count_mismatches"]:
        p(f"  {f['file_id']} {f['period']} {f['kind']}: parsed {f['rows']}, declared {f['declared']} on {f['page_ids']}")
    multi = [f for f in report["files"] if f.get("multi_file_block")]
    for f in multi:
        p(f"  (multi-file block) {f['file_id']} {f['period']} {f['kind']}: parsed {f['rows']}, block declares {f['declared']}")
    p("\nFile kind differs from the category of the linking block:")
    for f in s["kind_vs_block"] or []:
        p(f"  {f['file_id']} {f['period']}: file is {f['kind']}, block says {f['kind_vs_block']}")
    p("\nFile-level warning categories:")
    for k, v in s["file_warning_categories"].items():
        p(f"  {v:4d}  {k}")
    p("\nRecord warning categories (count, example):")
    for k, v in s["record_warning_categories"].items():
        p(f"  {v:4d}  {k}\n        e.g. {s['record_warning_examples'][k]}")
    if verbose:
        p("\nPer file:")
        for f in report["files"]:
            if "error" in f:
                p(f"  {f['file_id']} ERROR {f['error']}")
                continue
            p(f"  {f['file_id']} {f['period'] or '???????'} {str(f['kind']):4s} {str(f['layout']):8s} rows={f['rows']:3d} "
              f"skipped={f['skipped_template_rows']:3d} declared={f['declared']} label={f['period_label']!r}"
              + (f" warnings={f['file_warnings']}" if f["file_warnings"] else ""))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--raw", type=Path, default=ROOT / "data" / "raw", help="directory with <file_id>.xlsx")
    ap.add_argument("--manifest", type=Path, default=ROOT / "data" / "manifest.json")
    ap.add_argument("--pages", type=Path, default=None, help="scouting pages.json (used when no manifest)")
    ap.add_argument("--json", type=Path, default=None, help="also write the full report as JSON here")
    ap.add_argument("--verbose", "-v", action="store_true", help="per-file table (and records in --json)")
    args = ap.parse_args(argv)

    manifest = args.manifest if args.manifest.exists() and args.pages is None else None
    links = load_pages(manifest, args.pages)
    if not links:
        print("note: no manifest/pages metadata – declared counts and periods unavailable", file=sys.stderr)
    report = run(args.raw, links, verbose=args.verbose)
    print_report(report, args.verbose)
    if args.json:
        args.json.write_text(json.dumps(report, ensure_ascii=False, indent=1, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
