"""Regenerate pipeline/data/words.tsv – word frequencies used to mend words a browser broke across lines.

Białołęka's yearly lists are printed from the case system ("Raport Erwin 2.0") by a browser that breaks long
words anywhere in a narrow column ("BUDYN" / "KU", "Z" / "AGOSPODAROWANIEM"). Whether two pieces at a line
break are one word is decided by how often each form occurs in text that is never broken: the descriptions,
streets and investors of GUNB's building-permit register (the committed per-district extracts, all Warsaw).

    uv run python scripts/wordlist.py

The list is committed and changes only when this script is run, so a GUNB update never changes how a PDF reads.
Words occurring fewer than MIN_COUNT times are left out (typos in the register).
"""

from __future__ import annotations

import collections
import csv
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "pipeline" / "data" / "words.tsv"
MIN_COUNT = 3
COLUMNS = {"nazwa_zamierzenia_bud", "nazwa_zam_budowlanego", "ulica", "ulica_dalej", "nazwa_inwestor", "miasto"}
WORD = re.compile(r"[^\W\d_]+")


def main() -> None:
    counts: collections.Counter[str] = collections.Counter()
    files = sorted([*ROOT.glob("data/districts/*/rwdz/*.csv"), *ROOT.glob("data/raw/rwdz/*.csv")])
    for path in files:
        with path.open(encoding="utf-8-sig", newline="") as fh:
            reader = csv.reader(fh, delimiter=";")
            header = next(reader)
            cols = [i for i, name in enumerate(header) if name in COLUMNS]
            for row in reader:
                for i in cols:
                    if i < len(row):
                        counts.update(WORD.findall(row[i].lower()))
    words = sorted((w, n) for w, n in counts.items() if n >= MIN_COUNT)
    OUT.write_text("".join(f"{w}\t{n}\n" for w, n in words), encoding="utf-8")
    print(f"{OUT.relative_to(ROOT)}: {len(words)} words from {len(files)} extracts")


if __name__ == "__main__":
    main()
