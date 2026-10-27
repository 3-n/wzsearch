"""Tests for pipeline.pdftable: the district lists published only as PDF.

Fixtures are real lists (27 X 2026): Mokotów's applications of IX 2026 and three of its decision lists in the
case-system's other layouts (VIII 2026: a two-row header; IV 2025: an export with "Wynik", "Działka" and "Obręb"
columns; X 2025: a number cell that starts with "Nr"), Targówek's CP decisions I–VI 2026 and Włochy's WZ
decisions of VII 2026 (the Excel template printed to PDF; Włochy left the Lp number out of its last four rows).
Reading them needs poppler's ``pdftotext``.
"""

import shutil
from pathlib import Path

import pytest

from pipeline import districts, parse, pdftable as pt
from pipeline.normalize import normalize_row

FIX = Path(__file__).parent / "fixtures" / "districts"
needs_poppler = pytest.mark.skipif(shutil.which("pdftotext") is None, reason="pdftotext (poppler) not installed")


def W(x0, x1, top, text, height=9.0):
    return pt.Word(x0, x1, top, height, text)


# ------------------------------------------------------------------------------- pieces


def test_numbering_row_tolerates_one_garbled_cell():
    line = pt.Line(0, 290, [W(110, 113, 290, "1"), W(181, 184, 290, "2"), W(251, 290, 290, "1900-01-03"),
                            W(359, 362, 290, "4"), W(471, 474, 290, "5"), W(583, 586, 290, "6"),
                            W(690, 693, 290, "7")])
    assert pt._numbering(line) == pytest.approx([111.5, 182.5, 270.5, 360.5, 472.5, 584.5, 691.5])
    assert pt._numbering(pt.Line(0, 0, [W(0, 5, 0, "1"), W(10, 15, 0, "osoba"), W(20, 25, 0, "fizyczna"),
                                        W(30, 35, 0, "Budowa"), W(40, 45, 0, "domu")])) is None


def test_template_columns_come_from_the_gaps_no_text_covers():
    # numbering centres are not always the middle of their columns (Targówek: "5" at the left edge)
    centres = [110, 170, 390, 540]
    words = [W(100, 120, 0, "1"), W(140, 200, 0, "UD-X"), W(380, 520, 0, "we wniosku nie określono nazwy"),
             W(531, 600, 0, "ul. Promienna"), W(380, 470, 10, "inwestycji")]
    bounds = pt._template_bounds(words, centres)
    assert bounds[2] == pytest.approx((520 + 531) / 2)
    assert [__import__("bisect").bisect_right(bounds, w.xc) for w in words] == [0, 1, 2, 3, 2]


def test_split_block_centres_each_group_on_its_anchor():
    # two touching multi-line cells: 3 lines around 100, 5 lines around 140
    tops = [90, 100, 110, 120, 130, 140, 150, 160]
    assert pt._split_block(tops, [100, 140]) == [0, 0, 0, 1, 1, 1, 1, 1]


@pytest.mark.parametrize("text,expected", [
    ("4-02-24 ¬ 55, 56 ¬ Marmurowa", ("55, 56 obr. 4-02-24", "Marmurowa")),
    ("1-05-60 ¬ 35", ("35 obr. 1-05-60", "")),
    ("7-11-11 ¬ cz. 69/18 ¬ Arkuszowa", ("cz. 69/18 obr. 7-11-11", "Arkuszowa")),
    ("4-02-07 ¬ 42 ¬ Żółta ¬ 4-02-08 ¬ 7 ¬ Żółta", ("42 obr. 4-02-07; 7 obr. 4-02-08", "Żółta")),
    ("dz. 31 obr. 2-07-02", ("dz. 31 obr. 2-07-02", "")),
])
def test_split_place(text, expected):
    assert pt._split_place(text) == expected


def test_split_number_cell():
    assert pt._split_number_cell(["5/BIA/WZ/2026/O", "2026-01-08", "Odmowna"]) == ("5/BIA/WZ/2026/O\nOdmowna",
                                                                                   "2026-01-08", None)
    assert pt._split_number_cell(["123/BIA/WZ/", "2026/U", "2026-03-01", "Umarzająca"])[0] == "123/BIA/WZ/2026/U\nUmarzająca"


# ------------------------------------------------------------------------------- whole files


@needs_poppler
def test_report_layout_mokotow_applications():
    r = parse.parse_source(FIX / "mokotow-ws-2026-09.pdf")
    assert (r["kind"], r["layout"], r["procedure"]) == ("ws", "pdf-report-ws", "wz")
    assert r["warnings"] == []
    assert [row["cells"]["lp"] for row in r["rows"]] == ["1", "2", "3", "4", "5", "6"]
    first = r["rows"][0]
    assert first["sheet"] == "strona 1"
    assert first["cells"] == {"lp": "1", "number": "UD-IV-WAB-D.6730.13.2026", "date": "2026-09-02",
                              "applicant": "osoba fizyczna", "investment": "budynek mieszkalny+ gospodarczy+garaż",
                              "address": "Spiralna", "parcels": "35 obr. 1-05-60"}
    assert first["raw"][-1] == ["Oznaczenie nieruchomości", "1-05-60 ¬ 35"]   # composite cell as printed
    assert r["rows"][1]["cells"]["number"] is None                            # no case sign in the source
    assert r["rows"][5]["cells"]["address"] == "Goraszewska 24 A"


@needs_poppler
def test_template_layout_targowek_cp():
    r = parse.parse_source(FIX / "targowek-cp-2026.pdf")
    assert (r["kind"], r["layout"], r["series"]) == ("cp", "pdf-template-cp", "c2")
    assert r["warnings"] == []
    cells = [row["cells"] for row in r["rows"]]
    assert [c["number"] for c in cells] == ["1/TRG/CP/2026", "2/TRG/CP/2026/U", "3/TRG/CP/2026/U"]
    assert cells[0]["applicant"] == "K2 Residental Sp. z o.o. Sp. k."
    assert cells[0]["investment"] == "Budowa sieci wodociągowej DN100"
    assert cells[0]["address"] == "ul. Pożarowa; dzielnica Targówek"
    assert cells[0]["parcels"] == "dz. ewid. nr 76/2 obręb 4-08-21"
    assert cells[1]["applicant"] == "ORLEN S.A."
    assert r["rows"][0]["raw"][1][0] == "Nr decyzji"


@needs_poppler
def test_template_layout_wlochy_rows_without_lp():
    r = parse.parse_source(FIX / "wlochy-wz-2026-07.pdf")
    assert (r["kind"], r["layout"]) == ("wz", "pdf-template-wz")
    assert r["warnings"] == []
    rows = r["rows"]
    assert len(rows) == 14
    assert [row["cells"]["number"] for row in rows[9:]] == [
        "59/WLO/WZ/2026/U", "60/WLO/WZ/2026/U", "61/WLO/WZ/2026/U", "62/WLO/WZ/2026", "63/WLO/WZ/2026"]
    assert [row["cells"]["lp"] for row in rows[9:]] == ["10", None, None, None, None]
    assert rows[12]["cells"]["parcels"] == "dz. 51 obr. 2-07-20"
    assert rows[0]["cells"]["investment"].startswith("umorzenie postępowania administracyjnego w sprawie")
    assert rows[0]["raw"][5][0] == ("Oznaczenie nieruchomości (ulica, Dzielnica Włochy, nr działki ew. obręb) › "
                                    "nr działki, obręb")


@needs_poppler
def test_pdf_rows_normalise_like_workbook_rows():
    r = parse.parse_source(FIX / "mokotow-ws-2026-09.pdf")
    with districts.use(districts.get("mokotow")):
        rec = normalize_row(r["rows"][0], r["kind"], {"file_id": "f1", "page_id": "p1", "period": None,
                                                      "procedure": r["procedure"]})
    assert rec["id"].startswith("ws-mok-")
    assert rec["procedure"] == "wz"
    assert [p["id"] for p in rec["parcels"]] == ["146505_8.0560.35"]
    assert rec["sources"][0]["sheet"] == "strona 1"


@needs_poppler
def test_report_with_a_two_row_header():
    r = parse.parse_source(FIX / "mokotow-wz-2026-08.pdf")
    assert r["warnings"] == []
    assert [label for label, _ in r["rows"][0]["raw"]] == [
        "Nr i data decyzji › Nr", "data", "Nazwa i adres wnioskodawcy", "Oznaczenie nieruchomości › ulica",
        "Oznaczenie nieruchomości › obręb nr. dz.", "Streszczenie ustaleń decyzji"]
    first = r["rows"][0]["cells"]
    assert (first["number"], first["date"], first["address"], first["parcels"]) == (
        "35/MOK/WZ/2026 Pozytywna", "2026-08-06", "Okrężna 79", "43 obr. 1-05-32")


@needs_poppler
def test_report_export_with_outcome_and_split_parcel_columns():
    r = parse.parse_source(FIX / "mokotow-wz-2025-04.pdf")
    assert (r["kind"], r["warnings"], len(r["rows"])) == ("wz", [], 8)
    first = r["rows"][0]["cells"]
    assert first["number"] == "19/MOK/WZ/2025\nPozytywna"          # "Wynik" joins the number, like a report's cell
    assert (first["address"], first["parcels"]) == ("Wróbla 6A", "24 obr. 1-04-09")


@needs_poppler
def test_report_rows_start_after_the_gap_between_rows():
    r = parse.parse_source(FIX / "mokotow-wz-2025-10.pdf")
    assert r["warnings"] == []
    numbers = [row["cells"]["number"].split("\n")[0] for row in r["rows"]]
    assert numbers == [f"{n}/MOK/WZ/2025{s}" for n, s in
                       [(63, "/U"), (64, "/P"), (65, "/O"), (66, ""), (67, ""), (68, "/U"), (69, "/U"), (70, "/U")]]
    transfer = r["rows"][1]["cells"]                    # its number cell reads "Nr / 64/MOK/WZ/2025/P / …"
    assert transfer["investment"].startswith("przeniesienie decyzji nr 79/WZ/MOK/2020")
    assert transfer["parcels"] == "43 obr. 1-02-03"


def lines_at(rows):
    """Synthetic page: ``rows`` = [(top, [(x0, x1, text), …]), …]; a text's words share its x-range, a space apart."""
    out = []
    for top, phrases in rows:
        words = []
        for a, b, text in phrases:
            parts = text.split()
            step = (b - a + 2.5) / len(parts)
            words += [W(a + k * step, a + (k + 1) * step - 2.5, top, part) for k, part in enumerate(parts)]
        out.append(pt.Line(0, top, words))
    return out


def test_label_columns_parent_only_over_several_sub_labels():
    header = lines_at([
        (10, [(100, 220, "Nr decyzji i data jej wydania"), (300, 420, "Oznaczenie nieruchomości (ulica,")]),
        (20, [(100, 110, "nr"), (180, 210, "data"), (300, 350, "dzielnica)")]),
    ])
    bounds = [150, 250, 430]            # columns: nr | data | address (the label runs 10 pt into its neighbour) | …
    labels, specifics = pt._label_columns(header, 4, lambda x: __import__("bisect").bisect_right(bounds, x))
    assert labels[:3] == ["Nr decyzji i data jej wydania › nr", "Nr decyzji i data jej wydania › data",
                          "Oznaczenie nieruchomości (ulica, dzielnica)"]
    assert specifics[:3] == ["nr", "data", "Oznaczenie nieruchomości (ulica, dzielnica)"]


def test_bottom_aligned_cells_go_to_the_anchor_below():
    # Excel's default alignment: a cell's last line sits on the row's Lp line
    frags = [(1, pt.Line(0, t, [W(0, 10, t, f"l{t}")])) for t in (60, 70, 80, 100, 110, 120)]
    blocks = pt._blocks(frags, 2, 9.0)
    assert pt._alignment([(blocks, [80, 120])]) == "bottom"
    rows = pt._assign(blocks, [80, 120], 9.0, "bottom")
    assert [[f.top for f in row[1]] for row in rows] == [[60, 70, 80], [100, 110, 120]]


def test_two_titled_tables_in_one_pdf_are_parsed_apart():
    def page(title):
        return lines_at([(10, [(10, 300, title)]),
                         (30, [(10, 20, "Lp."), (60, 120, "Znak sprawy"), (160, 200, "Data")]),
                         (50, [(14, 16, "1"), (88, 90, "2"), (178, 180, "3"), (240, 242, "4"), (300, 302, "5")])])
    pages = [page("Informacja o wszczętych postępowaniach o warunkach zabudowy"),
             page("Informacja o wszczętych postępowaniach o ustaleniu lokalizacji inwestycji celu publicznego")]
    tables = pt._template_tables(pages)
    assert [t.page for t in tables] == [0, 1]
    assert tables[1].titles[-1].endswith("lokalizacji inwestycji celu publicznego")
    assert [pt._kind_of(t.titles, [])[:2] for t in tables] == [("ws", "wz"), ("ws", "cp")]


def test_four_digit_precinct_code_takes_the_district_zone():
    from pipeline.normalize import parse_parcels
    with districts.use(districts.get("mokotow")):
        assert [p["id"] for p in parse_parcels("dz.ew. nr 40/2, ob. 0514")[0]] == ["146505_8.0514.40/2"]
        assert [p["id"] for p in parse_parcels("dz.ew. nr 150 ob.. 0407")[0]] == ["146505_8.0407.150"]
    # Praga-Południe's lists never write it so; a bare 4-digit number stays a parcel number
    assert parse_parcels("dz. 1234 obr. 3-04-12")[0][0]["number"] == "1234"


def test_missing_pdftotext_is_reported(monkeypatch, tmp_path):
    pdf = tmp_path / "x.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")
    monkeypatch.setattr(pt, "PDFTOTEXT", "pdftotext-that-does-not-exist")
    with pytest.raises(pt.PdfUnavailable):
        pt.read_words(pdf)
