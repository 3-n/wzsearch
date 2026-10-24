"""Offline tests for pipeline/rwdz.py (GUNB RWDZ building permits and notifications).

Fixtures in tests/fixtures/rwdz/ are real register records (CC0 1.0) copied byte for byte from the
2026-10-22 GUNB files (line numbers in provenance.json): one CSV per archive, each with the
original header. The tests zip them into fake GUNB archives served by a fake HTTP session.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import re
import zipfile
from email.utils import parsedate_to_datetime
from pathlib import Path

import pytest
import requests
from requests.structures import CaseInsensitiveDict

from pipeline import rwdz
from pipeline.classify import TAGS, classify
from pipeline.normalize import street_key
from pipeline.rwdz import (
    CATEGORY_LABELS,
    CATEGORY_SHORT,
    CATEGORY_TAGS,
    DATASET_META,
    EXPECTED_HEADERS,
    FILES,
    KIND_META,
    LAYOUTS,
    PERMIT_CATEGORIES,
    PERMIT_SCOPES,
    SCOPE_TAGS,
    RwdzFormatError,
    compose_address,
    issuer_of,
    iter_records,
    match_location,
    parse_cubature,
    parse_register_date,
    record_id,
    resolve_collisions,
    run_rwdz,
)

ROOT = Path(__file__).resolve().parents[1]

FIX = ROOT / "tests" / "fixtures" / "rwdz"
FIXTURE_OF = {"rwdz-wnioski": "wnioski.csv", "rwdz-zgloszenia-2016-2021": "zgloszenia_2016_2021.csv",
              "rwdz-zgloszenia-2022": "zgloszenia_2022.csv"}
FILE = {f.file_id: f for f in FILES}
ETAG = '"2c55480-65e74a33e9129"'
LAST_MODIFIED = "Thu, 22 Oct 2026 21:35:08 GMT"
URL_SAFE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def fixture_bytes(file_id: str) -> bytes:
    return (FIX / FIXTURE_OF[file_id]).read_bytes()


def zip_bytes(member: str, data: bytes) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(member, data)
    return buf.getvalue()


def archive(file_id: str, data: bytes | None = None) -> bytes:
    f = FILE[file_id]
    return zip_bytes(f.zip_name.replace(".zip", ".csv"), fixture_bytes(file_id) if data is None else data)


# =============================================================================
# Fake HTTP
# =============================================================================


class FakeResponse:
    def __init__(self, status: int, content: bytes = b"", headers: dict | None = None):
        self.status_code = status
        self.content = content
        self.headers = CaseInsensitiveDict(headers or {})

    def iter_content(self, chunk_size: int = 1):
        for i in range(0, len(self.content), 7919):   # several chunks
            yield self.content[i:i + 7919]

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class FakeGunb:
    """Serves one archive per URL with ETag / Last-Modified and honours conditional requests."""

    def __init__(self, archives: dict[str, bytes] | None = None, *, fail: bool = False, lm_on_304: bool = False):
        self.archives = {FILE[fid].url: data for fid, data in (archives or default_archives()).items()}
        self.fail = fail
        self.lm_on_304 = lm_on_304
        self.calls: list[tuple[str, str, dict]] = []

    def etag(self, url: str) -> str:
        return '"' + hashlib.md5(self.archives[url]).hexdigest()[:12] + '"'

    def get(self, url, headers=None, stream=False, timeout=None):
        headers = dict(headers or {})
        self.calls.append(("GET", url, headers))
        if self.fail:
            raise requests.ConnectionError("network down")
        etag = self.etag(url)
        if "If-None-Match" in headers:                      # RFC 9110: If-None-Match wins over If-Modified-Since
            not_modified = headers["If-None-Match"] == etag
        elif "If-Modified-Since" in headers:
            not_modified = parsedate_to_datetime(headers["If-Modified-Since"]) >= parsedate_to_datetime(LAST_MODIFIED)
        else:
            not_modified = False
        if not_modified:
            return FakeResponse(304, headers={"ETag": etag, **({"Last-Modified": LAST_MODIFIED} if self.lm_on_304 else {})})
        data = self.archives[url]
        return FakeResponse(200, data, {"ETag": etag, "Last-Modified": LAST_MODIFIED,
                                        "Content-Length": str(len(data)), "Content-Type": "application/zip"})

    def head(self, url, timeout=None):
        self.calls.append(("HEAD", url, {}))
        return FakeResponse(200, headers={"ETag": self.etag(url), "Last-Modified": LAST_MODIFIED})

    def requests_for(self, file_id: str) -> list[tuple[str, dict]]:
        return [(m, h) for m, u, h in self.calls if u == FILE[file_id].url]


def default_archives() -> dict[str, bytes]:
    return {fid: archive(fid) for fid in FIXTURE_OF}


def run(tmp_path: Path, session=None, **kw) -> dict:
    return run_rwdz(tmp_path / "cache", tmp_path / "raw", session=session, log=lambda m: None, **kw)


def snapshot_files(tmp_path: Path) -> dict[str, bytes]:
    """Every tracked output (extracts, sidecars, rwdz.json) – for "nothing was rewritten" checks."""
    paths = sorted((tmp_path / "raw").glob("*")) + [tmp_path / "cache" / "rwdz.json"]
    return {p.name: p.read_bytes() for p in paths if p.is_file()}


@pytest.fixture()
def built(tmp_path):
    """A first online run against the fake GUNB server (no ZIP, no extract yet)."""
    gunb = FakeGunb()
    result = run(tmp_path, gunb)
    return tmp_path, gunb, result


def rec(result: dict, rid: str) -> dict:
    return next(r for r in result["records"] if r["id"] == rid)


# =============================================================================
# Dictionaries
# =============================================================================


ROMAN = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII", "XIII", "XIV", "XV", "XVI",
         "XVII", "XVIII", "XIX", "XX", "XXI", "XXII", "XXIII", "XXIV", "XXV", "XXVI", "XXVII", "XXVIII", "XXIX",
         "XXX"]


def test_category_labels_are_the_thirty_annex_categories():
    assert list(CATEGORY_LABELS) == ROMAN
    assert list(CATEGORY_SHORT) == ROMAN and list(PERMIT_CATEGORIES) == ROMAN
    # spot checks of the official wording (Dz.U. 2026 poz. 524, annex)
    assert CATEGORY_LABELS["I"] == "budynki mieszkalne jednorodzinne"
    assert CATEGORY_LABELS["XIII"] == "pozostałe budynki mieszkalne"
    assert CATEGORY_LABELS["XXVI"].startswith("sieci, jak: elektroenergetyczne, telekomunikacyjne, gazowe, wodorowe")
    assert "stacje krwiodawstwa" in CATEGORY_LABELS["XI"]           # PDF hyphenation undone
    assert "inwentarsko-składowe" in CATEGORY_LABELS["II"]          # a real hyphen is kept
    assert all("  " not in v and v == v.strip() for v in CATEGORY_LABELS.values())
    assert rwdz.CATEGORY_SOURCE["url"].startswith("https://isap.sejm.gov.pl/") and "WDU20260000524" in rwdz.CATEGORY_SOURCE["url"]
    for roman, entry in PERMIT_CATEGORIES.items():
        assert entry["label"] == CATEGORY_SHORT[roman] and len(entry["label"]) <= 90
        assert entry["description"] == f"Kategoria {roman} – {CATEGORY_LABELS[roman]}"


def test_scopes_cover_the_register_vocabulary():
    # every value of nazwa_zamierzenia_bud / rodzaj_zam_budowlanego seen nationwide on 2026-10-22
    vocabulary = [
        "budowa nowego/nowych obiektów budowlanych", "wykonanie robót budowlanych innych niż wymienione powyżej",
        "rozbiórka istniejącego obiektu budowlanego", "rozbudowa istniejącego/istniejących obiektów budowlanych",
        "nadbudowa istniejącego/istniejących obiektów budowlanych",
        "odbudowa istniejącego/istniejących obiektów budowlanych",
    ]
    assert sorted(v["register"] for v in PERMIT_SCOPES.values()) == sorted(vocabulary)
    assert list(PERMIT_SCOPES) == ["budowa", "rozbudowa", "nadbudowa", "odbudowa", "rozbiorka", "inne"]
    assert all(v["label"] for v in PERMIT_SCOPES.values())


def test_kind_and_dataset_meta_follow_the_contract():
    assert KIND_META["pb"]["label"] == "Pozwolenie na budowę lub rozbiórkę" and KIND_META["pb"]["short"] == "Pozwolenie"
    assert KIND_META["zg"]["label"] == "Zgłoszenie budowy lub robót" and KIND_META["zg"]["short"] == "Zgłoszenie"
    assert "rozstrzygnięcia" in KIND_META["pb"]["description"]       # no outcome column
    assert "pierwszej instancji" in KIND_META["pb"]["description"]    # only decided, first-instance cases
    assert "niepełny" in KIND_META["zg"]["description"]               # coverage caveat
    assert set(DATASET_META) >= {"label", "short", "publisher", "url", "licence", "description"}
    assert DATASET_META["licence"] == "CC0 1.0" and DATASET_META["publisher"] == "Główny Urząd Nadzoru Budowlanego"


def test_tag_mappings_point_to_existing_tags():
    assert set(CATEGORY_TAGS) <= set(CATEGORY_LABELS)
    assert set(CATEGORY_TAGS.values()) | set(SCOPE_TAGS.values()) <= set(TAGS)
    assert all(TAGS[t]["group"] == "funkcja" for t in CATEGORY_TAGS.values())
    assert all(TAGS[t]["group"] == "roboty" for t in SCOPE_TAGS.values())


# =============================================================================
# CSV reading and header validation
# =============================================================================


def test_fixture_headers_match_the_expected_layouts():
    for file_id, name in FIXTURE_OF.items():
        data = fixture_bytes(file_id)
        assert data.startswith(b"\xef\xbb\xbf")                       # UTF-8 with BOM, like GUNB
        header = data[3:data.index(b"\n")].decode("utf-8").split(";")
        assert tuple(header) == EXPECTED_HEADERS[FILE[file_id].layout], name
    assert EXPECTED_HEADERS["wnioski"].count("cecha") == 2 and EXPECTED_HEADERS["zgloszenia"].count("cecha") == 2


def test_iter_records_keeps_exact_lines_of_quoted_multiline_values():
    text = fixture_bytes("rwdz-zgloszenia-2016-2021")[3:].decode("utf-8")
    records = list(iter_records(io.StringIO(text, newline="\n")))
    assert [(r.line, r.n_lines) for r in records] == [(1, 1), (2, 1), (3, 2), (5, 1), (6, 1)]
    assert "".join(r.text for r in records) == text                    # nothing lost or altered
    multi = records[2]
    assert "\r\n" in multi.text and len(multi.fields) == 26
    assert multi.fields[-1].startswith("Szustecka Hanna") and "\r\n" in multi.fields[-1]


@pytest.mark.parametrize("mutate, message", [
    (lambda h: h.replace(b"numer_gunb", b"numer_gunb_nowy"), "nagłówek"),       # renamed column
    (lambda h: h.replace(b"kubatura;", b"kubatura;nowa_kolumna;"), "nagłówek"),  # extra column
    (lambda h: h.replace(b";", b"#"), "nagłówek"),                              # separator changed
])
def test_header_drift_fails_loudly_before_anything_is_written(tmp_path, mutate, message):
    data = fixture_bytes("rwdz-wnioski")
    end = data.index(b"\n")
    broken = mutate(data[:end]) + data[end:]
    gunb = FakeGunb({**default_archives(), "rwdz-wnioski": archive("rwdz-wnioski", broken)})
    with pytest.raises(RwdzFormatError, match=message):
        run(tmp_path, gunb)
    assert not (tmp_path / "raw" / "rwdz-wnioski.csv").exists()


def test_a_malformed_district_row_fails_loudly(tmp_path):
    lines = fixture_bytes("rwdz-wnioski").split(b"\n")
    lines[3] = lines[3].replace(b";", b"", 1)                             # Salamandry 3 loses a field
    gunb = FakeGunb({**default_archives(), "rwdz-wnioski": archive("rwdz-wnioski", b"\n".join(lines))})
    with pytest.raises(RwdzFormatError, match="pól"):
        run(tmp_path, gunb)


def test_a_malformed_row_elsewhere_is_counted_not_fatal(tmp_path):
    lines = fixture_bytes("rwdz-wnioski").split(b"\n")
    lines[1] = lines[1].replace(b";", b"", 1)                             # a Gostynin row (not Warsaw)
    # 1 bad row out of 25 is above the 1 % threshold – pad the file with good non-Warsaw rows
    padded = b"\n".join(lines[:2] + [lines[2]] * 120 + lines[2:])
    gunb = FakeGunb({**default_archives(), "rwdz-wnioski": archive("rwdz-wnioski", padded)})
    run(tmp_path, gunb)
    sidecar = json.loads((tmp_path / "raw" / "rwdz-wnioski.meta.json").read_text())
    assert sidecar["rows_malformed"] == 1 and sidecar["parsed_count"] == 21


# =============================================================================
# Location filter
# =============================================================================


OFFICE = "Prezydent Miasta Warszawa - Praga Płd."


@pytest.mark.parametrize("unit, organ, expected", [
    ("146507_8", "Wojewoda Mazowiecki", "unit"),
    (" 146507_8 ", "Prezydent Miasta Warszawa", "unit"),
    ("", OFFICE, "empty"),
    ("148507_8", OFFICE, "typo"),         # one substitution
    ("146057_8", OFFICE, "typo"),         # adjacent swap
    ("146517_8", OFFICE, "typo"),         # one edit away, although a valid unit (Włochy) – Ateńska 10 is in PP
    ("146078_8", OFFICE, "invalid"),      # not a Warsaw district unit at all
    ("086101_1", OFFICE, "invalid"),
    ("146514_8", OFFICE, None),           # Wawer: the office handled genuine Wawer cases in 2020
    ("146510_8", OFFICE, None),           # Śródmieście, two edits away
    ("148507_8", "Prezydent Miasta Warszawa", None),   # the typo rule is for the district office only
    ("", "Wojewoda Mazowiecki", None),
    ("146508_8", "Prezydent Miasta Warszawa - Praga Pn.", None),
])
def test_match_location(unit, organ, expected):
    assert match_location(unit, organ) == expected


SZASEROW = "ST-MZ-PA/WNIOSEK/14200/2024"   # rwdz.UNIT_FIXES: Śródmieście unit on a Praga-Południe parcel


@pytest.mark.parametrize("unit, organ, case, expected", [
    ("146510_8", OFFICE, SZASEROW, "listed"),
    ("146510_8", "Prezydent Miasta Warszawa", "ST-MZ-WA/WNIOSEK/37134/2018", "listed"),   # any organ
    ("146507_5", "Wojewoda Mazowiecki", "PL-MZ/WNIOSEK/15131/2026", "listed"),
    ("146514_8", OFFICE, SZASEROW, None),                 # only the unit the table names
    ("146510_8", OFFICE, "ST-MZ-PA/WNIOSEK/14201/2024", None),   # the same wrong unit, another case: out
    ("146507_8", OFFICE, SZASEROW, "unit"),
])
def test_match_location_listed_register_errors(unit, organ, case, expected):
    assert match_location(unit, organ, case) == expected


def test_listed_register_error_is_kept_with_a_corrected_unit(built):
    _tmp, _gunb, result = built
    szaserow = rec(result, "pb-st-mz-pa-2024-14200")
    assert [p["id"] for p in szaserow["parcels"]] == ["146507_8.0407.10/1"]
    assert szaserow["parcels"][0]["obreb"] == "3-04-07" and szaserow["parcels_raw"] == "146510_8 0407 10/1"
    assert any("„146510_8” (Śródmieście) potraktowano jako 146507_8" in w and "błąd w rejestrze" in w
               for w in szaserow["warnings"])
    assert not any("sprawa urzędu dzielnicy" in w for w in szaserow["warnings"])


def test_unkept_cases_with_district_signs_are_listed_for_review(tmp_path):
    # the same Szaserów row under a case number that is not listed: not kept, but its office case sign
    # (UD-VI-…) and decision number (…/PPD/…) put it on the review list of the sidecar / report
    data = fixture_bytes("rwdz-wnioski").replace(SZASEROW.encode(), b"ST-MZ-PA/WNIOSEK/14201/2024")
    gunb = FakeGunb({**default_archives(), "rwdz-wnioski": archive("rwdz-wnioski", data)})
    run(tmp_path, gunb)
    sidecar = json.loads((tmp_path / "raw" / "rwdz-wnioski.meta.json").read_text())
    assert sidecar["parsed_count"] == 20 and sidecar["office_rows_not_kept"] == {"146510_8": 1, "146514_8": 1}
    assert sidecar["signal_cases_not_kept"] == [["ST-MZ-PA/WNIOSEK/14201/2024", 20, "146510_8"]]


def test_selection_keeps_whole_cases_and_drops_everything_else(built):
    tmp_path, _gunb, result = built
    sidecar = json.loads((tmp_path / "raw" / "rwdz-wnioski.meta.json").read_text())
    assert sidecar["rows_total"] == 25 and sidecar["parsed_count"] == 21 and sidecar["cases"] == 12
    # fixture lines 2-3 (Gostynin), 11 (another case between TPPI rows), 19 (Wawer) are out; 20 (Szaserów 133 with
    # the Śródmieście unit) is a listed register error (UNIT_FIXES)
    assert sidecar["lines"] == [4, 5, 6, 7, 8, 9, 10, 12, 13, 14, 15, 16, 17, 18, 20, 21, 22, 23, 24, 25, 26]
    assert sidecar["office_rows_not_kept"] == {"146514_8": 1}
    assert sidecar["signal_cases_not_kept"] == [] and sidecar["extract_version"] == 2
    mpwik = rec(result, "pb-st-mz-wa-2016-41260")                         # city case, 2 Rembertów parcels
    assert [p["id"] for p in mpwik["parcels"]] == ["146509_8.0702.201/1", "146509_8.0702.259/1", "146507_8.0303.35"]
    assert [p["obreb"] for p in mpwik["parcels"]] == ["3-07-02", "3-07-02", "3-03-03"]   # Rembertów is zone 3 too
    assert "jednostka ewidencyjna 146509_8 (Rembertów): 2" in mpwik["warnings"][0]
    stats = result["stats"]["files"]["rwdz-wnioski"]
    assert stats["rows_kept_by_office_rule"] == {"empty": 1, "invalid": 1, "listed": 1, "typo": 1}


def test_broken_unit_ids_of_the_district_office_are_corrected_with_a_warning(built):
    _tmp, _gunb, result = built
    francuska = rec(result, "pb-st-mz-pa-2020-25855")
    assert [p["id"] for p in francuska["parcels"]] == ["146507_8.0107.105"]
    assert francuska["parcels_raw"] == "148507_8 0107 105"                # as printed
    assert "„148507_8”" in francuska["warnings"][0] and "literówka" in francuska["warnings"][0]
    orlik = rec(result, "pb-st-mz-pa-2024-8401")
    assert [p["id"] for p in orlik["parcels"]] == ["146507_8.0002.39/6"]
    assert orlik["parcels"][0]["obreb"] == "0002"                        # not a Praga-Południe precinct: as printed
    assert any("obręb „0002” nie występuje na Pradze-Południe" in w for w in orlik["warnings"])
    brazylijska = rec(result, "pb-st-mz-pa-2016-6365")                    # empty unit, obręb and parcel
    assert brazylijska["parcels"] == []
    assert any("bez oznaczenia działki w rejestrze" in w for w in brazylijska["warnings"])
    ostrobramska = rec(result, "zg-st-mz-pa-2023-8611")                   # 3 good rows + one 146057_8 row
    assert [p["id"] for p in ostrobramska["parcels"]] == [
        "146507_8.0519.7/19", "146507_8.0519.7/3", "146507_8.0519.7/18", "146507_8.0519.19"]


# =============================================================================
# Byte-exact extract + sidecar
# =============================================================================


def test_extract_is_byte_exact(built):
    tmp_path, _gunb, _result = built
    for file_id in FIXTURE_OF:
        original = fixture_bytes(file_id)
        extract = (tmp_path / "raw" / f"{file_id}.csv").read_bytes()
        sidecar = json.loads((tmp_path / "raw" / f"{file_id}.meta.json").read_text())
        olines = original.split(b"\n")
        elines = extract.split(b"\n")
        assert extract.startswith(b"\xef\xbb\xbf") and elines[0] == olines[0]      # BOM + original header
        assert len(sidecar["lines"]) == len(elines) - 2                              # trailing "" after last \n
        for i, n in enumerate(sidecar["lines"], start=1):
            assert elines[i] == olines[n - 1]
        kept = b"\n".join([olines[0]] + [olines[n - 1] for n in sidecar["lines"]]) + b"\n"
        assert hashlib.sha256(kept).hexdigest() == hashlib.sha256(extract).hexdigest() == sidecar["sha256"]
        assert sidecar["size"] == len(extract)
        assert sidecar["header"] == list(EXPECTED_HEADERS[FILE[file_id].layout])


def test_extract_keeps_multiline_records_whole(built):
    tmp_path, _gunb, result = built
    sidecar = json.loads((tmp_path / "raw" / "rwdz-zgloszenia-2022.meta.json").read_text())
    assert sidecar["parsed_count"] == 9 and len(sidecar["lines"]) == 10    # one record spans 2 lines
    jubilerska = rec(result, "zg-st-mz-pa-2024-9647")
    assert jubilerska["sources"][0]["rows"] == [6] and jubilerska["sources"][0]["extract_rows"] == [6]
    lubelska = rec(result, "zg-st-mz-pa-2026-6161")
    assert lubelska["sources"][0]["rows"] == [8, 9, 10, 11]                 # line 7 is the continuation


def test_sidecar_records_the_snapshot(built):
    tmp_path, gunb, _result = built
    sidecar = json.loads((tmp_path / "raw" / "rwdz-wnioski.meta.json").read_text())
    url = FILE["rwdz-wnioski"].url
    assert sidecar["url"] == url and sidecar["licence"] == "CC0 1.0"
    assert sidecar["dataset_url"] == "https://dane.gov.pl/pl/dataset/3467"
    assert sidecar["etag"] == gunb.etag(url) and sidecar["last_modified"] == "2026-10-22T21:35:08Z"
    assert sidecar["sha256_zip"] == hashlib.sha256(gunb.archives[url]).hexdigest()
    assert sidecar["zip_member"] == "wynik_mazowieckie.csv" and sidecar["delimiter"] == ";"
    tracked = json.loads((tmp_path / "cache" / "rwdz.json").read_text())["files"]["rwdz-wnioski"]
    assert tracked == {"url": url, "etag": sidecar["etag"], "last_modified": sidecar["last_modified"],
                       "size": len(gunb.archives[url]), "sha256_zip": sidecar["sha256_zip"],
                       "downloaded_at": sidecar["downloaded_at"]}


def test_an_edited_extract_is_rejected(built):
    tmp_path, _gunb, _result = built
    path = tmp_path / "raw" / "rwdz-wnioski.csv"
    path.write_bytes(path.read_bytes().replace(b"Salamandry", b"Salamandra"))
    with pytest.raises(RwdzFormatError, match="SHA-256"):
        run(tmp_path, online=False)


# =============================================================================
# Download: conditional GET, 304, offline, stability
# =============================================================================


def test_first_run_downloads_unconditionally_and_writes_caches(built):
    tmp_path, gunb, result = built
    for file_id in FIXTURE_OF:
        (method, headers), = gunb.requests_for(file_id)
        assert method == "GET" and "If-None-Match" not in headers and "If-Modified-Since" not in headers
        assert (tmp_path / "cache" / "rwdz" / FILE[file_id].zip_name).is_file()
        assert result["stats"]["files"][file_id]["status"] == "downloaded"
    assert not list((tmp_path / "cache" / "rwdz").glob("*.part"))          # temp files cleaned up
    local = json.loads((tmp_path / "cache" / "rwdz" / "local.json").read_text())["files"]
    assert set(local) == set(FIXTURE_OF) and all(v["extract_version"] == rwdz.EXTRACT_VERSION for v in local.values())


def test_second_run_is_a_304_and_rewrites_nothing(built):
    tmp_path, gunb, first = built
    before = snapshot_files(tmp_path)
    mtimes = {p: p.stat().st_mtime_ns for p in (tmp_path / "raw").glob("*")}
    again = run(tmp_path, gunb)
    for file_id in FIXTURE_OF:
        _method, headers = gunb.requests_for(file_id)[-1]
        assert headers["If-None-Match"] == gunb.etag(FILE[file_id].url)
        assert again["stats"]["files"][file_id]["status"] == "not-modified"
    assert snapshot_files(tmp_path) == before
    assert {p: p.stat().st_mtime_ns for p in (tmp_path / "raw").glob("*")} == mtimes
    assert again["records"] == first["records"] and again["files"] == first["files"]


def test_ci_without_the_zip_uses_tracked_validators_and_the_committed_extract(built):
    tmp_path, gunb, first = built
    for p in (tmp_path / "cache" / "rwdz").iterdir():                       # a fresh CI checkout
        p.unlink()
    again = run(tmp_path, gunb)
    _method, headers = gunb.requests_for("rwdz-wnioski")[-1]
    assert headers["If-None-Match"] == gunb.etag(FILE["rwdz-wnioski"].url)
    assert headers["If-Modified-Since"] == LAST_MODIFIED
    assert again["stats"]["files"]["rwdz-wnioski"]["status"] == "not-modified"
    assert not (tmp_path / "cache" / "rwdz" / "wynik_mazowieckie.zip").exists()   # ZIP not needed
    assert again["records"] == first["records"]


def test_offline_reproduces_the_online_records_exactly(built):
    tmp_path, _gunb, first = built
    for p in (tmp_path / "cache" / "rwdz").iterdir():
        p.unlink()
    offline = run(tmp_path, online=False)
    assert offline["records"] == first["records"]
    assert offline["files"] == first["files"] and offline["page"] == first["page"]
    assert all(f["status"] == "offline" for f in offline["stats"]["files"].values())
    assert json.dumps(offline["records"], ensure_ascii=False) == json.dumps(first["records"], ensure_ascii=False)


def test_network_failure_falls_back_to_the_committed_extract(built):
    tmp_path, _gunb, first = built
    for p in (tmp_path / "cache" / "rwdz").iterdir():
        p.unlink()
    again = run(tmp_path, FakeGunb(fail=True))
    assert again["records"] == first["records"]
    entry = next(f for f in again["files"] if f["file_id"] == "rwdz-wnioski")
    assert entry["warnings"] and "nie udało się pobrać" in entry["warnings"][0] and "error" not in entry
    assert again["stats"]["files"]["rwdz-wnioski"]["status"] == "stale"


def test_nothing_available_yields_an_error_entry_not_a_crash(tmp_path):
    result = run(tmp_path, FakeGunb(fail=True))
    assert result["records"] == []
    assert all(f["error"] and f["parsed_count"] is None and f["archive_path"] is None for f in result["files"])
    offline = run(tmp_path, online=False)
    assert all("brak wyciągu" in f["error"] for f in offline["files"])


def test_a_new_snapshot_with_the_same_district_rows_changes_nothing(built):
    tmp_path, _gunb, first = built
    before = snapshot_files(tmp_path)
    grown = fixture_bytes("rwdz-wnioski") + fixture_bytes("rwdz-wnioski").split(b"\n")[1] + b"\n"   # +1 Gostynin row
    gunb = FakeGunb({**default_archives(), "rwdz-wnioski": archive("rwdz-wnioski", grown)})
    again = run(tmp_path, gunb)
    assert again["stats"]["files"]["rwdz-wnioski"]["status"] == "downloaded"
    assert snapshot_files(tmp_path) == before                              # extract, sidecar, rwdz.json untouched
    assert again["records"] == first["records"]


def test_a_new_snapshot_with_changed_district_rows_is_adopted(built):
    tmp_path, _gunb, first = built
    changed = fixture_bytes("rwdz-wnioski").replace(b"Projekt przebudowy lokalu mieszkalnego nr 46",
                                                     b"Projekt przebudowy lokalu mieszkalnego nr 47")
    gunb = FakeGunb({**default_archives(), "rwdz-wnioski": archive("rwdz-wnioski", changed)})
    again = run(tmp_path, gunb)
    assert rec(again, "pb-st-mz-pa-2026-29594")["investment"].endswith("nr 47 w budynku mieszkalnym wielorodzinnym")
    sidecar = json.loads((tmp_path / "raw" / "rwdz-wnioski.meta.json").read_text())
    tracked = json.loads((tmp_path / "cache" / "rwdz.json").read_text())["files"]["rwdz-wnioski"]
    url = FILE["rwdz-wnioski"].url
    assert sidecar["etag"] == tracked["etag"] == gunb.etag(url) != first["files"][0]["etag"]


def test_a_zip_copied_by_hand_is_adopted_with_one_conditional_get(tmp_path):
    zips = tmp_path / "cache" / "rwdz"
    zips.mkdir(parents=True)
    gunb = FakeGunb()
    for file_id in FIXTURE_OF:
        (zips / FILE[file_id].zip_name).write_bytes(gunb.archives[FILE[file_id].url])
    result = run(tmp_path, gunb)
    (m1, h1), (m2, _h2) = gunb.requests_for("rwdz-wnioski")
    assert m1 == "GET" and "If-Modified-Since" in h1 and "If-None-Match" not in h1
    assert m2 == "HEAD"                                                     # 304 carried no Last-Modified
    sidecar = json.loads((tmp_path / "raw" / "rwdz-wnioski.meta.json").read_text())
    assert sidecar["etag"] == gunb.etag(FILE["rwdz-wnioski"].url) and sidecar["last_modified"] == "2026-10-22T21:35:08Z"
    assert result["stats"]["files"]["rwdz-wnioski"]["status"] == "not-modified"
    assert len(result["records"]) == 16


def test_refresh_downloads_unconditionally(built):
    tmp_path, gunb, _first = built
    run(tmp_path, gunb, refresh=True)
    method, headers = gunb.requests_for("rwdz-wnioski")[-1]
    assert method == "GET" and not headers


def test_an_outdated_extract_is_remade_from_the_zip(built, monkeypatch):
    tmp_path, gunb, _first = built
    monkeypatch.setattr(rwdz, "EXTRACT_VERSION", rwdz.EXTRACT_VERSION + 1)
    run(tmp_path, gunb)
    sidecar = json.loads((tmp_path / "raw" / "rwdz-wnioski.meta.json").read_text())
    assert sidecar["extract_version"] == rwdz.EXTRACT_VERSION


# =============================================================================
# Records
# =============================================================================


def test_record_fields_of_a_permit(built):
    _tmp, _gunb, result = built
    r = rec(result, "pb-st-mz-pa-2026-29594")
    assert list(r) == ["id", "kind", "procedure", "dataset", "issuer", "outcome", "number", "date", "date_raw",
                       "filed_date", "period", "applicant", "applicant_type", "investment", "address", "parcels",
                       "parcels_raw", "tags", "permit", "area", "geo", "sources", "related", "warnings"]
    assert (r["kind"], r["procedure"], r["dataset"], r["issuer"]) == ("pb", "pb", "rwdz", "district")
    assert (r["number"], r["date"], r["date_raw"], r["period"], r["filed_date"]) == (
        "163/PPD/PB/2026", "2026-10-14", "2026-10-14 00:00:00", "2026-10", "2026-09-24")
    assert (r["applicant"], r["applicant_type"]) == ("osoba fizyczna", "person")      # blank investor
    assert r["investment"] == "Projekt przebudowy lokalu mieszkalnego nr 46 w budynku mieszkalnym wielorodzinnym"
    assert r["parcels"] == [{"number": "25/12", "obreb": "3-06-05", "partial": False, "id": "146507_8.0605.25/12"}]
    assert (r["geo"], r["area"], r["related"], r["outcome"]) == (None, None, [], None)
    assert r["permit"] == {
        "register_id": "ST-MZ-PA/WNIOSEK/29594/2026", "case_sign": "RPW/142815/2026-1B/FSO", "scope": "inne",
        "scope_label": "wykonanie robót budowlanych innych niż wymienione powyżej", "category": "XIII",
        "category_label": "pozostałe budynki mieszkalne", "single_family": False, "cubature": None, "state": None}
    src = r["sources"][0]
    assert (src["file_id"], src["page_id"], src["sheet"], src["row"], src["rows"], src["extract_rows"]) == (
        "rwdz-wnioski", "rwdz", None, 4, [4], [2])
    assert dict(src["raw"])["numer_gunb"] == "ST-MZ-PA/WNIOSEK/29594/2026"


def test_record_fields_of_a_notification(built):
    _tmp, _gunb, result = built
    r = rec(result, "zg-st-mz-pa-2026-6161")
    assert (r["kind"], r["applicant"], r["applicant_type"]) == ("zg", None, "unknown")
    assert r["number"] == r["permit"]["case_sign"] == "UD-VI-WOM-ROB/21555/26/PHO"
    assert r["date"] == r["filed_date"] == "2026-08-28"
    assert r["permit"]["state"] == "Brak sprzeciwu" and r["permit"]["single_family"] is None
    assert r["permit"]["scope"] == "budowa" and r["permit"]["category"] == "XXVI"
    assert dict(r["sources"][0]["raw"])["numer_dzialki"] == "4 | 2 | 8 | 15/1"   # parcels joined


def test_grouping_by_case_across_interrupted_rows(built):
    _tmp, _gunb, result = built
    tppi = rec(result, "pb-st-mz-pa-2024-10384")
    assert tppi["sources"][0]["rows"] == [9, 10, 12]                        # line 11 is another case
    assert [p["number"] for p in tppi["parcels"]] == ["51", "52", "54"]
    assert len(result["records"]) == 16
    assert len({r["permit"]["register_id"] for r in result["records"]}) == 16


def test_designer_columns_never_reach_records(built):
    _tmp, _gunb, result = built
    designer_values = set()
    for file_id in FIXTURE_OF:
        layout = LAYOUTS[FILE[file_id].layout]
        positions = [i for i, name in enumerate(layout.header) if name in layout.designer_cols]
        text = fixture_bytes(file_id)[3:].decode("utf-8")
        for record in list(iter_records(io.StringIO(text, newline="\n")))[1:]:
            designer_values |= {record.fields[i].strip() for i in positions if len(record.fields[i].strip()) > 3}
    assert len(designer_values) > 10
    dumped = json.dumps(result, ensure_ascii=False)
    leaked = [v for v in designer_values if v in dumped]
    assert leaked == []
    for r in result["records"]:
        assert not any(label.startswith(("projektant", "nazwisko_proj", "imie_proj")) for label, _ in r["sources"][0]["raw"])


def test_ids_are_url_safe_stable_and_unique(built):
    _tmp, _gunb, result = built
    ids = [r["id"] for r in result["records"]]
    assert len(ids) == len(set(ids)) and all(URL_SAFE.match(i) for i in ids)
    assert result["stats"]["id_collisions"] == 0


@pytest.mark.parametrize("kind, register_id, expected", [
    ("pb", "ST-MZ-PA/WNIOSEK/29594/2026", "pb-st-mz-pa-2026-29594"),
    ("zg", "PL-MZ/ZGŁOSZENIE/12/2025", "zg-pl-mz-2025-12"),
    ("zg", "ST-MZ-PA/ZGŁOSZENIE/6161/2026", "zg-st-mz-pa-2026-6161"),
    ("pb", " ST-MZ-WA/WNIOSEK/0041/2016 ", "pb-st-mz-wa-2016-0041"),      # digits kept as printed
    ("pb", "XYZ 12/2016", "pb-xyz-12-2016"),                                # other shapes are slugged whole
    ("pb", "", None),
])
def test_record_id(kind, register_id, expected):
    assert record_id(kind, register_id) == expected


def test_collisions_merge_the_same_case_and_split_different_ones():
    def fake(rid, register_id, file_id):
        return {"id": rid, "permit": {"register_id": register_id}, "parcels": [{"id": f"{file_id}.p"}],
                "sources": [{"file_id": file_id, "row": 2}], "warnings": []}
    records = [fake("zg-a-2021-1", "A/ZGŁOSZENIE/1/2021", "f1"), fake("zg-a-2021-1", "A/ZGŁOSZENIE/1/2021", "f2"),
               fake("pb-x", "X 1", "f1"), fake("pb-x", "X-1", "f1")]
    assert resolve_collisions(records) == 1
    assert [r["id"] for r in records] == ["zg-a-2021-1", "pb-x", "pb-x-2"]
    merged = records[0]
    assert [s["file_id"] for s in merged["sources"]] == ["f1", "f2"] and len(merged["parcels"]) == 2
    assert "kilku plikach" in merged["warnings"][0]
    assert all("ten sam identyfikator" in r["warnings"][0] for r in records[1:])


@pytest.mark.parametrize("cecha, dalej, ulica, nr, display, street, number, numbers", [
    ("ul.  ", "Andrzeja ", "Czapskiego", "3", "Andrzeja Czapskiego 3", "Czapskiego", "3", ["3"]),
    ("al.  ", "", "Aleja Jerzego Waszyngtona", "96", "Aleja Jerzego Waszyngtona 96", "Waszyngtona", "96", ["96"]),
    ("al.  ", "", "Aleja Stanów Zjednoczonych", "53", "Aleja Stanów Zjednoczonych 53", "Stanów Zjednoczonych", "53",
     ["53"]),
    ("ul.  ", "gen. Augusta Emila ", 'Fieldorfa "Nila"', "12", 'gen. Augusta Emila Fieldorfa "Nila" 12',
     "Fieldorfa", "12", ["12"]),                                           # one spelling (normalize.STREET_CANONICAL)
    ("pl.  ", "", "Plac Przymierza", "5", "Plac Przymierza 5", "Plac Przymierza", "5", ["5"]),
    ("rondo", "", "Rondo Wiatraczna", "", "Rondo Wiatraczna", "Rondo Wiatraczna", None, []),
    ("os.  ", "", "Przyjaźni", "3", "os. Przyjaźni 3", "Przyjaźni", "3", ["3"]),
    ("inne ", "", "Pasaż Złotej Wilgi", "", "Pasaż Złotej Wilgi", "Pasaż Złotej Wilgi", None, []),
    ("ul.  ", "1 ", "Praskiego Pułku WP", "2", "1 Praskiego Pułku WP 2", "Praskiego Pułku WP", "2", ["2"]),
    ("ul.  ", "", "Grochowska", "75 C", "Grochowska 75C", "Grochowska", "75C", ["75C"]),
    ("ul.  ", "", "Grochowska", "65,67,69,73C", "Grochowska 65,67,69,73C", "Grochowska", "65",
     ["65", "67", "69", "73C"]),
    ("ul.  ", "", "Serocka", "9 i 11", "Serocka 9 i 11", "Serocka", "9", ["9", "11"]),
    ("ul.  ", "", "Szaserów", "28/30", "Szaserów 28/30", "Szaserów", "28/30", ["28/30"]),
])
def test_compose_address(cecha, dalej, ulica, nr, display, street, number, numbers):
    a = compose_address(cecha, dalej, ulica, nr)
    assert (a["display"], a["street"], a["number"]) == (display, street, number)
    assert a["parts"] == [{"street": street, "number": number, "numbers": numbers}]
    assert a["approximate"] is False


def test_compose_address_drops_a_unit_id_typed_as_house_number():
    warnings: list[str] = []
    a = compose_address("ul.  ", "", "Grochowska", "146507_8", warnings)
    assert (a["street"], a["number"], a["display"]) == ("Grochowska", None, "Grochowska")
    assert a["raw"] == "ul. Grochowska 146507_8"                            # as printed
    assert warnings == ["w rejestrze zamiast numeru budynku wpisano kod jednostki ewidencyjnej („146507_8”) – "
                        "pominięto"]


def test_precinct_codes_outside_the_district_list_are_printed_as_is():
    assert rwdz._parcel("146507_8", "0605", "25/12")["obreb"] == "3-06-05"
    assert rwdz._parcel("146507_8", "0707", "3/51")["obreb"] == "0707"     # no such precinct in Praga-Południe
    assert rwdz._parcel("146509_8", "0707", "3/51")["obreb"] == "3-07-07"  # Rembertów has it


def test_compose_address_matches_the_other_datasets():
    warnings: list[str] = []
    a = compose_address("ul.  ", "Jana ", "Jeziorańskiego", "28", warnings)
    assert a["street"] == "Nowaka-Jeziorańskiego" and a["display"] == "Jana Jeziorańskiego 28"   # display as printed
    assert warnings and "Nowaka-Jeziorańskiego" in warnings[0]
    # the matching keys are those of the district files
    assert street_key(a["street"]) == street_key("Jana Nowaka Jeziorańskiego")
    assert street_key(compose_address("ul.  ", "gen. Augusta Emila ", 'Fieldorfa "Nila"', "")["street"]) == \
        street_key("Gen. Fieldorfa Nila")
    assert compose_address("al.  ", "", "Aleja Jerzego Waszyngtona", "1")["street"] == "Waszyngtona"
    assert compose_address("ul.  ", "", "", "12")["display"] == ""           # a number without a street
    assert compose_address("", "", "", "")["raw"] == ""
    assert compose_address("ul.  ", "Andrzeja ", "Czapskiego", "3")["raw"] == "ul. Andrzeja Czapskiego 3"


@pytest.mark.parametrize("organ, expected", [
    ("Prezydent Miasta Warszawa - Praga Płd.", "district"),
    ("Prezydent Miasta Warszawa", "city"),
    ("Prezydent m.st. Warszawy", "city"),
    ("Wojewoda Mazowiecki", "voivode"),
    ("Wojewoda Mazowiecki - Delegatura w Radomiu", "voivode"),
    ("Prezydent Miasta Warszawa - Praga Pn.", "other"),
    ("Starosta Powiatu Gostynin", "other"),
])
def test_issuer_of(organ, expected):
    assert issuer_of(organ) == expected


@pytest.mark.parametrize("value, expected, noted", [
    ("12919", 12919, False), ("80.39", 80.39, False), ("1525,83", 1525.83, False),
    ("2.03804e+06", 2038040, True), ("1", None, False), ("0", None, False), ("", None, False),
    ("ok. 100", None, True),
])
def test_parse_cubature(value, expected, noted):
    got, notes = parse_cubature(value)
    assert got == expected and bool(notes) == noted


def test_parse_register_date():
    assert parse_register_date("2026-10-14 00:00:00") == "2026-10-14"
    assert parse_register_date("2026-02-30 00:00:00") is None
    assert parse_register_date("") is None and parse_register_date("14.10.2026") is None


def test_permit_specific_values(built):
    _tmp, _gunb, result = built
    bouygues = rec(result, "pb-st-mz-pa-2020-12384")
    assert bouygues["permit"]["cubature"] == 2038040 and "zaokrągleniu" in bouygues["warnings"][0]
    assert bouygues["applicant_type"] == "organization"
    refusal = rec(result, "pb-st-mz-pa-2024-10219")                         # 66/PPD/PB/2025/O
    assert refusal["outcome"] is None and "„/O”" in refusal["warnings"][0]
    waszyngtona = rec(result, "pb-st-mz-pa-2024-13400")
    assert waszyngtona["permit"]["cubature"] is None                        # "1" is a placeholder
    assert waszyngtona["address"]["display"] == "Aleja Jerzego Waszyngtona 96"


@pytest.mark.parametrize("rid, tags", [
    # text: gas installation in a flat; unit typo record
    ("pb-st-mz-pa-2020-25855", ["instalacje-wewnetrzne", "remont"]),
    # category XIII names the building when the text does not ("remont ... balkonów")
    ("pb-st-mz-pa-2024-10219", ["wielorodzinny", "remont"]),
    # scope "rozbiórka" adds the works tag
    ("pb-st-mz-pa-2016-6365", ["parkingi-garaze", "rozbiorka"]),
    # scope "budowa" + networks (category XXVI)
    ("zg-st-mz-pa-2026-6161", ["infrastruktura", "nowa-budowa"]),
])
def test_tags_combine_text_scope_and_category(built, rid, tags):
    _tmp, _gunb, result = built
    assert rec(result, rid)["tags"] == tags


def test_files_and_page_entries(built):
    _tmp, _gunb, result = built
    files = {f["file_id"]: f for f in result["files"]}
    assert list(files) == [f.file_id for f in FILES]
    w = files["rwdz-wnioski"]
    assert (w["source"], w["category"], w["kind_detected"], w["page_ids"], w["period"]) == (
        "rwdz", "pb", "pb", ["rwdz"], None)
    assert w["archive_path"] == "sources/rwdz/rwdz-wnioski.csv" and w["local_path"] == "data/raw/rwdz/rwdz-wnioski.csv"
    assert (w["rows_total"], w["parsed_count"]) == (25, 21) and w["licence"] == "CC0 1.0"
    assert w["record_ids"][:2] == ["pb-st-mz-pa-2026-29594", "pb-st-mz-pa-2020-12384"]   # file order
    assert set(w["record_ids"]) == {r["id"] for r in result["records"] if r["kind"] == "pb"}
    page = result["page"]
    assert (page["page_id"], page["source"], page["url"], page["period"]) == (
        "rwdz", "rwdz", "https://wyszukiwarka.gunb.gov.pl/pobranie.html", None)
    assert page["title"] == "Rejestr wniosków, decyzji i zgłoszeń (GUNB)"
    assert [b["file_ids"] for b in page["blocks"]] == [[f.file_id] for f in FILES]
    assert all(b["declared_count"] is None and b["count_mismatch"] is False for b in page["blocks"])
    assert [b["parsed_count"] for b in page["blocks"]] == [21, 2, 9]


def test_records_are_sorted_newest_first(built):
    _tmp, _gunb, result = built
    keys = [(r["date"] or "", r["period"] or "") for r in result["records"]]
    assert keys == sorted(keys, reverse=True)


# =============================================================================
# Classification of permit texts (pipeline/classify.py extensions)
# =============================================================================


@pytest.mark.parametrize("text, expected", [
    ("budowa wewnętrznej instalacji gazowej w lokalu mieszkalnym 47", ["instalacje-wewnetrzne", "nowa-budowa"]),
    ("BUDOWA INSTALACJI GAZU DLA PROJEKTOWANEGO BUDYNKU MIESZKALNEGO WIELORODZINNEGO",
     ["instalacje-wewnetrzne", "nowa-budowa"]),
    ("wymiana wewnetrznej instalacji gazowej w lok nr 6", ["instalacje-wewnetrzne", "remont"]),
    ("REMONT INSTALACJI WODY ZIMNEJ I KANALIZACJI.", ["instalacje-wewnetrzne", "remont"]),
    ("BUDOWA INSTALACJI FOTOWOLTAICZNEJ O MOCY 78 kW", ["instalacje-wewnetrzne", "nowa-budowa"]),
    ("budowa przyłącza gazu i instalacji gazowej", ["infrastruktura", "instalacje-wewnetrzne", "nowa-budowa"]),
    ("BUDOWA PRZYŁĄCZA CIEPLNEGO", ["infrastruktura", "nowa-budowa"]),
    ("Przyłączenie pomieszczenia do lokalu mieszkalnego", []),                  # "przyłączenie" is not a network
    ("KOMPLEKSOWA TERMOMODERNIZACJA - REMONT ELEWACJI ORAZ BALKONÓW WRAZ Z DOCIEPLENIEM ŚCIAN ZEWNĘTRZNYCH", ["remont"]),
    ("REMONT DACHU BUDYNKU MIESZKALNEGO WIELORODZINNEGO", ["wielorodzinny", "remont"]),
    ("roboty budowlane polegające na wydzieleniu komórek lokatorskich", []),    # "wydzieleniu" ≠ zieleń
    ("budynek wielorodzinny z garażem podziemnym-projekt zamienny", ["wielorodzinny", "nowa-budowa", "zmiana-decyzji"]),
    ("wniosek o zmianę pozwolenia na budowe hotelu", ["zamieszkanie-zbiorowe", "zmiana-decyzji"]),
    ("budowa budynku mieszkalnego jednorodzinnego wraz z instalacją gazową", ["jednorodzinny", "nowa-budowa"]),
    ("budowa budynków biurowych wraz z zapleczem remontowo-magazynowym", ["uslugi", "nowa-budowa"]),
    ("TERMOMODERNIZACJA BUDYNKU MIESZKALNEGO WIELOKONDYGNACYJNEGO", ["wielorodzinny", "remont"]),  # no "przebudowa"
])
def test_classify_permit_texts(text, expected):
    assert classify(text) == expected


def test_new_tags_keep_the_taxonomy_contract():
    assert TAGS["instalacje-wewnetrzne"]["group"] == "funkcja" and TAGS["remont"]["group"] == "roboty"
    order = list(TAGS)
    assert order.index("instalacje-wewnetrzne") < order.index("nowa-budowa") < order.index("remont")
    assert order[-1] == "rozbiorka"


# =============================================================================
# The committed real data (data/raw/rwdz/) – skipped before the first download
# =============================================================================


REAL = ROOT / "data" / "raw" / "rwdz"


@pytest.mark.skipif(not (REAL / "rwdz-wnioski.meta.json").is_file(), reason="data/raw/rwdz not built yet")
def test_committed_extracts_build_valid_records(tmp_path):
    result = run_rwdz(tmp_path / "cache", REAL, online=False, log=lambda m: None)   # reads REAL only
    records = result["records"]
    ids = [r["id"] for r in records]
    assert len(ids) == len(set(ids)) and all(URL_SAFE.match(i) for i in ids)
    by_kind = result["stats"]["by_kind"]
    assert by_kind["pb"] > 2000 and by_kind["zg"] > 150
    assert all(re.fullmatch(r"\d{6}_\d\.\d{4}\.[0-9A-Za-z./-]+", p["id"]) for r in records for p in r["parcels"])
    assert all(r["sources"][0]["rows"] == sorted(r["sources"][0]["rows"]) for r in records)
    designer = {c for layout in LAYOUTS.values() for c in layout.designer_cols}
    assert not any(label in designer for r in records for label, _ in r["sources"][0]["raw"])
    assert all(r["permit"]["scope"] in PERMIT_SCOPES or r["permit"]["scope"] is None for r in records)
    assert sum(1 for r in records if r["permit"]["scope"] is None) <= 5
    keys = [(r["date"] or "", r["period"] or "") for r in records]
    assert keys == sorted(keys, reverse=True)


@pytest.mark.skipif(os.environ.get("RWDZ_VERIFY_ZIPS") != "1" or
                    not (ROOT / "data" / "cache" / "rwdz" / "wynik_mazowieckie.zip").is_file(),
                    reason="set RWDZ_VERIFY_ZIPS=1 with the GUNB ZIPs in data/cache/rwdz/ (≈ 10 s)")
def test_committed_extracts_are_byte_exact_copies_of_the_gunb_files():
    for f in FILES:
        sidecar = json.loads((REAL / f"{f.file_id}.meta.json").read_text())
        zip_path = ROOT / "data" / "cache" / "rwdz" / f.zip_name
        if hashlib.sha256(zip_path.read_bytes()).hexdigest() != sidecar["sha256_zip"]:
            pytest.skip(f"{f.zip_name} is a newer snapshot than the committed extract")
        with zipfile.ZipFile(zip_path) as zf:
            original = zf.read(sidecar["zip_member"]).split(b"\n")
        extract = (REAL / f"{f.file_id}.csv").read_bytes().split(b"\n")
        assert extract[0] == original[0]
        assert all(extract[i] == original[n - 1] for i, n in enumerate(sidecar["lines"], start=1))
