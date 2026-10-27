"""Regenerate ``pipeline/data/warsaw_obreby.json``: which cadastral unit owns which precinct, for all of Warsaw.

Warsaw writes precincts as ``Z-SS-OO`` (``6-11-10``) but ULDK ids drop the zone digit
(``146502_8.1110.5/40``), and a zone is shared by up to three districts (``baipp.OBREB_ZONES``), so the unit of
a parcel cannot be read from the precinct alone. GUNB's RWDZ register gives the answer for free: every row
names the parcel's unit and its 4-digit precinct, and the Mazowieckie file has ~78,000 Warsaw rows.

The script counts ``(unit, SSOO)`` pairs in the GUNB ZIPs the build already downloads
(``data/cache/rwdz/*.zip``; run ``make rwdz`` first in a fresh clone). Typos in the register show up as
rare pairs; :func:`pipeline.districts.unit_for_precinct` lets a precinct belong to the unit with a 3:1
majority of rows. Praga-Południe keeps its ULDK-verified list (``praga_poludnie_obreby.json``).

    uv run python scripts/warsaw_obreby.py
"""

from __future__ import annotations

import csv
import io
import json
import re
import sys
import zipfile
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ZIPS = ROOT / "data" / "cache" / "rwdz"
OUT = ROOT / "pipeline" / "data" / "warsaw_obreby.json"
UNIT_RE = re.compile(r"1465(0[2-9]|1\d)_8")
COLUMNS = (("jednosta_numer_ew", "obreb_numer"), ("jednostki_numer", "obreb_numer"))


def count_pairs(zip_path: Path) -> Counter:
    pairs: Counter = Counter()
    with zipfile.ZipFile(zip_path) as zf:
        member = next(n for n in zf.namelist() if n.lower().endswith(".csv"))
        with zf.open(member) as fh:
            reader = csv.reader(io.TextIOWrapper(fh, encoding="utf-8-sig", newline=""), delimiter=";")
            header = next(reader)
            unit_col, obreb_col = next((header.index(u), header.index(o)) for u, o in COLUMNS if u in header)
            for row in reader:
                if len(row) <= max(unit_col, obreb_col):
                    continue
                unit, code = row[unit_col].strip(), row[obreb_col].strip()
                if UNIT_RE.fullmatch(unit) and re.fullmatch(r"\d{4}", code):
                    pairs[(unit, code)] += 1
    return pairs


def main() -> int:
    zips = sorted(ZIPS.glob("*.zip"))
    if not zips:
        print(f"no GUNB ZIPs in {ZIPS.relative_to(ROOT)} – run `make rwdz` first", file=sys.stderr)
        return 1
    pairs: Counter = Counter()
    for z in zips:
        pairs += count_pairs(z)
        print(f"{z.name}: {len(pairs)} unit/precinct pairs so far")
    units: dict[str, dict[str, int]] = defaultdict(dict)
    for (unit, code), n in sorted(pairs.items()):
        units[unit][code] = n
    doc = {
        "source": "GUNB RWDZ (wynik_mazowieckie.zip, wynik_zgloszenia_*.zip): liczba wierszy rejestru na parę "
                  "jednostka ewidencyjna / obręb",
        "files": [z.name for z in zips],
        "generated_at": datetime.now(UTC).strftime("%Y-%m-%d"),
        "units": {u: units[u] for u in sorted(units)},
    }
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=1, sort_keys=False) + "\n", encoding="utf-8")
    print(f"{sum(len(v) for v in units.values())} precincts in {len(units)} units → {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
