"""Source cells outside the record files (pipeline/cells.py; the page's half is tests/js/cells.test.mjs)."""

import json

import pytest

from pipeline import cells

# The same vectors as tests/js/cells.test.mjs (the first three are FNV's published ones).
VECTORS = [("", 0x811C9DC5), ("a", 0xE40C292C), ("foobar", 0xBF9CF968), ("ws-waw-6730-2026-624", 0x8DC9A2B2),
           ("pb-zażółć", 0xB763106E)]


@pytest.mark.parametrize(("text", "expected"), VECTORS)
def test_fnv1a_matches_the_page(text, expected):
    assert cells.fnv1a32(text) == expected


def test_bucket_count_is_a_power_of_two_sized_by_bytes():
    assert cells.bucket_count(0) == 1
    assert cells.bucket_count(cells.BUCKET_BYTES) == 1
    assert cells.bucket_count(cells.BUCKET_BYTES + 1) == 2
    assert cells.bucket_count(cells.BUCKET_BYTES * 20) == 32
    assert cells.bucket_count(10**12) == cells.MAX_BUCKETS


def test_split_and_bucket_files_round_trip(tmp_path):
    records = [
        {"id": "wz-1", "sources": [{"file_id": "f", "raw": [["Lp.", "1"]]}, {"file_id": "g"}]},
        {"id": "wz-2", "sources": [{"file_id": "f"}]},                       # no cells: not listed
        {"id": "pb-ż", "sources": [{"file_id": "h", "raw": [["Nr", "ż"]]}]},
    ]
    found = cells.split_cells(records)
    assert all("raw" not in s for r in records for s in r["sources"])
    assert found == {"wz-1": [[["Lp.", "1"]], None], "pb-ż": [[["Nr", "ż"]]]}
    meta, files = cells.bucket_files(found, tmp_path, "records")
    assert meta == {"prefix": "cells/r-", "buckets": 1}
    assert list(files) == [tmp_path / "cells" / "r-00.json"]
    body = files[tmp_path / "cells" / "r-00.json"].decode()
    assert json.loads(body) == found
    assert body.count("\n") == 4                                            # "{", one line per record, "}"


def test_every_bucket_is_written_and_stale_ones_found(tmp_path, monkeypatch):
    monkeypatch.setattr(cells, "BUCKET_BYTES", 10)
    found = {f"wz-{i}": [[["Lp.", str(i)]]] for i in range(40)}
    meta, files = cells.bucket_files(found, tmp_path, "permits")
    n = meta["buckets"]
    assert n > 1 and len(files) == n
    for rid in found:
        path = tmp_path / f"cells/p-{cells.bucket_of(rid, n):02x}.json"
        assert rid in json.loads(files[path])
    (tmp_path / "cells").mkdir()
    for p in [*files, tmp_path / "cells" / f"p-{n:02x}.json", tmp_path / "cells" / "notes.txt"]:
        p.write_bytes(b"{}\n")
    assert cells.stale_buckets(tmp_path, files) == [tmp_path / "cells" / f"p-{n:02x}.json"]
