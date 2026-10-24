"""Regenerate ``pipeline/data/praga_poludnie_obreby.json``: the cadastral precincts (obręby) of Praga-Południe.

The district's precincts are ``3-01-01`` … ``3-07-NN`` (ULDK ids ``146507_8.0101`` …), but not every code in that
range exists (``3-05-16``, ``3-07-07`` …), so a regex cannot tell a register/source typo from a real precinct.
This script asks GUGiK ULDK (``GetRegionById``, ≤ 2 requests/s) for every code 0101–0799; a code proven by a
parcel found earlier (``data/cache/uldk.json``) needs no request. Run it again if the district's precincts change
(practically never)::

    uv run python scripts/pp_obreby.py
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline import geocode  # noqa: E402

UNIT = "146507_8"
OUT = ROOT / "pipeline" / "data" / "praga_poludnie_obreby.json"


def main() -> int:
    cache = geocode.load_cache(str(ROOT / "data" / "cache" / "uldk.json"))
    proven = {k.split(".")[1] for k, v in cache.items()
              if k.startswith(UNIT + ".") and (v or {}).get("status") == "ok"}
    session = geocode.PoliteSession(max_rps=2)
    found: list[str] = []
    for section in range(1, 8):
        for number in range(1, 100):
            code = f"{section:02d}{number:02d}"
            if code in proven:
                found.append(code)
                continue
            resp = session.get(geocode.ULDK_URL, params={"request": "GetRegionById", "id": f"{UNIT}.{code}",
                                                         "result": "id"})
            text = resp.text.strip()
            if resp.status_code != 200 or not text or not text[0] in "0-":
                raise SystemExit(f"unexpected ULDK answer for {code}: {resp.status_code} {text[:80]!r}")
            if text.startswith("0"):
                found.append(code)
    doc = {
        "unit": UNIT,
        "source": "GUGiK ULDK GetRegionById (kody 0101–0799) i działki znalezione w ULDK",
        "checked_at": datetime.now(UTC).strftime("%Y-%m-%d"),
        "obreby": sorted(found),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"{len(found)} precincts → {OUT.relative_to(ROOT)} ({session.requests_made} ULDK requests)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
