"""Tests for pipeline.parse – fixtures are real workbooks copied from data/raw (one per layout + edge cases)."""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import openpyxl
import pytest

from pipeline.parse import FIELDS, classify_header, detect_kind, parse_workbook
from pipeline.textutil import is_blank

ROOT = Path(__file__).resolve().parents[1]

FIX = ROOT / "tests" / "fixtures" / "xlsx"
RAW = ROOT / "data" / "raw"


def fx(name: str) -> Path:
    return FIX / f"{name}.xlsx"


# --------------------------------------------------------------------------- header mapping


@pytest.mark.parametrize("label, field", [
    ("Lp", "lp"), ("Lp.\n", "lp"), ("L.p.", "lp"),
    ("Numer decyzji", "number"), ("nr ", "number"), ("Znak sprawy", "number"),
    ("Data wydania decyzji", "date"), ("data\n (rrrr-mm-dd)", "date"),
    ("Data wszczęcia postępowania\n (rrrr-mm-dd)\n", "date"),
    ("\nNazwa  wnioskodawcy", "applicant"),
    ("Streszczenie ustaleń decyzji", "investment"),
    ("Streszczenie ustaleń decyzji\nulica, dzielnica", "investment"),   # 2025+ CP: mislabelled summary column
    ("Nazwa inwestycji \nz wniosku ", "investment"),
    ("Adres inwestycji\nulica, dzielnica", "address"), ("ulica, dzielnica", "address"),
    ("Adres inwestycji \n(ulica, dzielnica)", "address"),
    ("nr dz. ew., obręb ", "parcels"), ("Oznaczenie nieruchomości\nnr dz. ew., obręb", "parcels"),
    ("Oznaczenie nieruchomości  (nr działki ew., obręb)", "parcels"),
    ("Uwagi", None), ("", None),
])
def test_classify_header(label, field):
    assert classify_header(label) == field


@pytest.mark.parametrize("texts, kind", [
    (["INFORMACJA O WSZCZĘTYCH POSTĘPOWANIACH O WARUNKACH ZABUDOWY I USTALENIU LOKALIZACJI INWESTYCJI CELU PUBLICZNEGO"], "ws"),
    (["INFORMACJA O WYDANYCH  DECYZJACH  W SPRAWIE  USTALENIA LOKALIZACJI INWESTYCJI  CELU PUBLICZNEGO"], "cp"),
    (["Informacja o wydanych decyzjach w sprawie warunków zabudowy"], "wz"),
    (["Decyzje celu publicznego"], "cp"),
    (["Wszczęte postępowania"], "ws"),
    (["Zarząd Dzielnicy Praga-Południe m. st. Warszawy", "Lipiec 2026"], None),
])
def test_detect_kind(texts, kind):
    assert detect_kind(*texts) == kind


# --------------------------------------------------------------------------- real fixtures

FIXTURES = [
    # name, kind, layout, period_label, rows, skipped template rows
    ("new-wz-2026-07", "wz", "new-wz", "Lipiec 2026", 3, 0),
    ("new-cp-2026-09-mislabelled-summary", "cp", "new-cp", "Wrzesień 2026", 2, 0),
    ("new-ws-2025-11-numbering-gap", "ws", "new-ws", "Listopad 2025", 3, 0),
    ("old-wz-2020-09-datetime-privacy", "wz", "old-wz", "WRZESIEŃ", 3, 0),
    ("old-wz-2021-12-twenty-rows", "wz", "old-wz", "GRUDZIEŃ-21", 20, 0),
    ("old-wz-2023-05-empty-first-sheet", "wz", "old-wz", "maj 2023r.", 5, 0),
    ("old-cp-2020-08-multi-obreb-intersection", "cp", "old-cp", "SIERPIEŃ", 5, 0),
    ("old-cp-2020-09-string-dates", "cp", "old-cp", "WRZESIEŃ", 3, 0),
    ("old-cp-2022-04-former-numbers", "cp", "old-cp", "KWIECIEŃ-22", 6, 0),
    ("old-cp-2023-06-obreb-in-parens", "cp", "old-cp", "czerwiec 2023", 2, 0),
    ("old-ws-2020-09-trailing-lp", "ws", "old-ws", "WRZESIEŃ", 5, 1),
    ("old-ws-2020-10-empty-template", "ws", "old-ws", "Październik", 0, 6),
    ("old-ws-2022-07-dot-separator", "ws", "old-ws", "LIPIEC-22", 6, 0),
    ("old-ws-2023-02-access-road", "ws", "old-ws", "LUTY 2023", 2, 6),   # incl. a whitespace-only row
]


@pytest.mark.parametrize("name, kind, layout, label, n_rows, n_skipped", FIXTURES)
def test_fixture_overview(name, kind, layout, label, n_rows, n_skipped):
    pf = parse_workbook(fx(name))
    assert pf["kind"] == kind
    assert pf["layout"] == layout
    assert pf["period_label"] == label
    assert len(pf["rows"]) == n_rows
    assert len(pf["skipped"]) == n_skipped
    assert pf["warnings"] == []
    assert pf["title"] and "informacja" in pf["title"].lower()
    for row in pf["rows"]:
        assert set(row["cells"]) == set(FIELDS)
        assert row["warnings"] == []
        # every mapped, non-empty field also appears in raw, in column order
        labels = [label for label, _ in row["raw"]]
        assert len(labels) == len(set(labels))
        assert row["row"] > 4


def test_new_wz_cells_and_raw():
    pf = parse_workbook(fx("new-wz-2026-07"))
    row = pf["rows"][0]
    assert row["sheet"] == "Decyzje o warunkach zabudowy"
    assert row["row"] == 6
    assert row["cells"] == {
        "lp": 1, "number": "15/PPD/WZ/2026\n", "date": "09.07.2026r.", "applicant": "osoba fizyczna ",
        "investment": "budowa budynku mieszkalnego jednorodzinnego ", "address": "Marokańska\nPraga-Południe\n",
        "parcels": "dz. 46/4\n3-01-24",
    }
    assert row["raw"][0] == ["Lp", 1]
    assert row["raw"][1] == ["Numer decyzji", "15/PPD/WZ/2026\n"]
    assert [label for label, _ in row["raw"]][-1] == "Streszczenie ustaleń decyzji"


def test_new_cp_mislabelled_summary_column_is_investment():
    pf = parse_workbook(fx("new-cp-2026-09-mislabelled-summary"))
    cells = pf["rows"][0]["cells"]
    assert cells["investment"].startswith("budowa ogólnodostępnej stacji")
    assert cells["address"] == "Ostrobramska 97\nPraga-Południe"
    assert cells["parcels"] == "dz. 14\n3-05-21"
    assert pf["rows"][0]["raw"][4][0] == "Streszczenie ustaleń decyzji ulica, dzielnica"


def test_old_wz_two_row_header_and_datetime():
    pf = parse_workbook(fx("old-wz-2020-09-datetime-privacy"))
    row = pf["rows"][0]
    assert row["row"] == 7
    assert row["cells"]["number"] == "17/WZ/PPd/2020"
    assert row["cells"]["date"] == dt.datetime(2020, 9, 1)
    assert row["cells"]["parcels"].startswith("2 i 3-cz.")
    # 2-row header → "parent › child"; datetimes in raw are ISO strings
    assert row["raw"][1] == ["Nr decyzji i data jej wydania › nr", "17/WZ/PPd/2020"]
    assert row["raw"][2] == ["Nr decyzji i data jej wydania › data (rrrr-mm-dd)", "2020-09-01"]
    # WZ column order: address/parcels BEFORE the summary
    assert [lbl for lbl, _ in row["raw"]][-1] == "Streszczenie ustaleń decyzji"


def test_old_cp_column_order_differs_from_wz():
    pf = parse_workbook(fx("old-cp-2020-08-multi-obreb-intersection"))
    row = pf["rows"][0]
    labels = [lbl for lbl, _ in row["raw"]]
    assert labels.index("Streszczenie ustaleń decyzji") < labels.index(
        "Oznaczenie nieruchomości (ulica, dzielnica, nr działki ew., obręb) › ulica, dzielnica")
    assert row["cells"]["investment"].startswith("Budowa drogi publicznej")
    assert row["cells"]["address"].startswith("Podskarbińska")


def test_string_dates_kept_raw():
    pf = parse_workbook(fx("old-cp-2020-09-string-dates"))
    assert [r["cells"]["date"] for r in pf["rows"]] == ["2020.09.23", "2020.09.25", "2020.09.28"]


def test_numbering_row_with_gap_is_skipped():
    pf = parse_workbook(fx("new-ws-2025-11-numbering-gap"))   # numbering row is "1 2 _ 4 5 6 7"
    assert [r["row"] for r in pf["rows"]] == [6, 7, 8]
    assert pf["rows"][0]["cells"]["number"] == "UD-VI-WAB-\n.U.6730.40.2025.ASU"


def test_trailing_lp_rows_and_extra_sheet():
    pf = parse_workbook(fx("old-ws-2020-09-trailing-lp"))
    assert pf["skipped"] == [{"sheet": "Arkusz1", "row": 11, "reason": "tylko numer Lp"}]
    assert [s["name"] for s in pf["sheets"]] == ["Arkusz1", "Arkusz2"]
    assert pf["sheets"][1]["header_row"] is None


def test_empty_first_sheet_is_ignored():
    pf = parse_workbook(fx("old-wz-2023-05-empty-first-sheet"))
    assert {r["sheet"] for r in pf["rows"]} == {"ROK"}
    assert pf["rows"][0]["cells"]["number"] == "5WZ/PPd/2023"


# --------------------------------------------------------------------------- synthetic edge cases


def _save(tmp_path: Path, rows: list[list], *, extra_sheets: dict[str, list[list]] | None = None) -> Path:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Arkusz1"
    for r in rows:
        ws.append(r)
    for name, srows in (extra_sheets or {}).items():
        s = wb.create_sheet(name)
        for r in srows:
            s.append(r)
    path = tmp_path / "t.xlsx"
    wb.save(path)
    return path


NEW_WZ_HEADER = ["Lp", "Numer decyzji", "Data wydania decyzji", "Nazwa wnioskodawcy",
                 "Adres inwestycji\nulica, dzielnica", "Oznaczenie nieruchomości\nnr dz. ew., obręb",
                 "Streszczenie ustaleń decyzji"]
TITLE = [["Informacja o wydanych decyzjach w sprawie warunków zabudowy"], ["Zarząd Dzielnicy"], ["Lipiec 2026"]]


def test_unmapped_column_value_is_kept_with_warning(tmp_path):
    path = _save(tmp_path, TITLE + [NEW_WZ_HEADER + ["Uwagi"], [1, 2, 3, 4, 5, 6, 7, 8],
                                    [1, "1/PPD/WZ/2026", "01.07.2026", "osoba fizyczna", "Marokańska", "dz. 1\n3-01-24",
                                     "budowa", "ważna uwaga"],
                                    [2, None, None, None, None, None, None, None, "sierota"]])
    pf = parse_workbook(path)
    assert any("Uwagi" in w for w in pf["warnings"])
    assert len(pf["rows"]) == 2
    assert pf["rows"][0]["raw"][-1] == ["Uwagi", "ważna uwaga"]
    assert pf["rows"][0]["warnings"] == ["wartość w kolumnie bez rozpoznanego pola: „Uwagi”"]
    orphan = pf["rows"][1]
    assert orphan["cells"]["number"] is None
    assert ["(kolumna I)", "sierota"] in orphan["raw"]


def test_gap_rows_and_late_data_are_scanned(tmp_path):
    rows = TITLE + [NEW_WZ_HEADER, [1, 2, 3, 4, 5, 6, 7],
                    [1, "1/PPD/WZ/2026", "01.07.2026", "a", "b", "dz. 1 3-01-24", "c"],
                    [2], [None], [], [],
                    [3, "3/PPD/WZ/2026", "03.07.2026", "a", "b", "dz. 1 3-01-24", "c"]]
    pf = parse_workbook(_save(tmp_path, rows))
    assert [r["cells"]["number"] for r in pf["rows"]] == ["1/PPD/WZ/2026", "3/PPD/WZ/2026"]
    assert [s["row"] for s in pf["skipped"]] == [7]


def test_sheet_without_header_is_emitted_with_warning(tmp_path):
    rows = TITLE + [NEW_WZ_HEADER, [1, "1/PPD/WZ/2026", "01.07.2026", "a", "b", "dz. 1 3-01-24", "c"]]
    pf = parse_workbook(_save(tmp_path, rows, extra_sheets={"Notatki": [["coś ważnego", None, 42]]}))
    assert any("Notatki" in w and "nagłówka" in w for w in pf["warnings"])
    loose = [r for r in pf["rows"] if r["sheet"] == "Notatki"]
    assert loose and loose[0]["raw"] == [["(kolumna A)", "coś ważnego"], ["(kolumna C)", 42]]


def test_repeated_header_remaps_columns(tmp_path):
    cp_header = ["Lp", "Numer decyzji", "Data wydania decyzji", "Nazwa wnioskodawcy",
                 "Streszczenie ustaleń decyzji", "Adres inwestycji", "Oznaczenie nieruchomości nr dz. ew., obręb"]
    rows = TITLE + [NEW_WZ_HEADER, [1, "1/PPD/WZ/2026", "01.07.2026", "a", "ADR", "dz. 1 3-01-24", "SUM"],
                    cp_header, [1, "2/PPD/WZ/2026", "02.07.2026", "a", "SUM2", "ADR2", "dz. 2 3-01-24"]]
    pf = parse_workbook(_save(tmp_path, rows))
    assert [(r["cells"]["address"], r["cells"]["investment"]) for r in pf["rows"]] == [("ADR", "SUM"), ("ADR2", "SUM2")]


def test_kind_unknown_is_reported(tmp_path):
    pf = parse_workbook(_save(tmp_path, [["Lista"], NEW_WZ_HEADER, [1, "x", "y", "z", "a", "b", "c"]]))
    # the header contains no ws/cp/wz cue, the title neither
    assert pf["kind"] is None
    assert any("rodzaju listy" in w for w in pf["warnings"])


# --------------------------------------------------------------------------- whole corpus


def _independent_row_count(path: Path) -> int:
    """Oracle: rows below the header block that hold anything besides the Lp number."""
    wb = openpyxl.load_workbook(path, data_only=True)
    total = 0
    for ws in wb.worksheets:
        rows = list(ws.iter_rows(values_only=True))
        hdr = next((i for i, r in enumerate(rows)
                    if any(isinstance(v, str) and v.strip().rstrip(".").lower() == "lp" for v in r)), None)
        if hdr is None:
            continue
        lp_col = next(j for j, v in enumerate(rows[hdr]) if isinstance(v, str) and v.strip().rstrip(".").lower() == "lp")
        for r in rows[hdr + 1:]:
            others = [v for j, v in enumerate(r) if j != lp_col and not is_blank(v)]
            if not others:
                continue
            if all(isinstance(v, int) for v in others):           # "1 2 3 4 5 6 7" numbering row
                continue
            if is_blank(r[lp_col]) and all(isinstance(v, str) and len(v) < 40 for v in others) \
                    and any(v.strip().lower().startswith(("nr", "data", "ulica")) for v in others):
                continue                                           # 2nd header row (nr / data / ulica …)
            total += 1
    return total


@pytest.mark.skipif(not RAW.exists() or not any(RAW.glob("*.xlsx")), reason="data/raw not downloaded")
def test_every_raw_workbook_parses_and_keeps_every_row():
    files = sorted(RAW.glob("*.xlsx"))
    assert len(files) >= 100
    total = 0
    for path in files:
        pf = parse_workbook(path)
        if pf["layout"].startswith("baipp-"):
            continue  # the city-wide BAiPP lists are covered by tests/test_baipp.py
        assert pf["kind"] in ("wz", "cp", "ws"), path.name
        assert pf["layout"] in ("old-wz", "old-cp", "old-ws", "new-wz", "new-cp", "new-ws"), path.name
        assert len(pf["rows"]) == _independent_row_count(path), path.name
        total += len(pf["rows"])
        for row in pf["rows"]:
            assert row["raw"], (path.name, row["row"])
    assert total >= 450
