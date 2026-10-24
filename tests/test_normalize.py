"""Table-driven tests for pipeline.normalize (every case below is a variant seen in the real files)."""

from __future__ import annotations

import datetime as dt
import re
from pathlib import Path

import pytest

from pipeline.normalize import (
    PERSON_REDACTED,
    PP_OBREBY,
    STREET_CANONICAL,
    applicant_type,
    canonical_street,
    clean_applicant,
    clean_number,
    merge_duplicates,
    normalize_row,
    parcel_id,
    parse_address,
    parse_case_sign,
    parse_date,
    parse_decision_number,
    is_pp_obreb,
    parse_parcels,
    record_id,
    redact_persons,
    street_key,
)
from pipeline.parse import parse_workbook
from pipeline.textutil import collapse_ws, fold, month_from_text, tidy_cell

ROOT = Path(__file__).resolve().parents[1]

FIX = ROOT / "tests" / "fixtures" / "xlsx"
RAW = ROOT / "data" / "raw"


# =========================================================================== textutil


@pytest.mark.parametrize("value, expected", [
    ("Osoba  Fizyczna    -Pełnomocnik", "Osoba Fizyczna -Pełnomocnik"),
    ("\nNazwa\xa0 wnioskodawcy\n", "Nazwa wnioskodawcy"),
    (None, ""),
])
def test_collapse_ws(value, expected):
    assert collapse_ws(value) == expected


@pytest.mark.parametrize("value, expected", [
    ("Kamionkowska 29                     Praga-Południe", "Kamionkowska 29\nPraga-Południe"),
    ("dz. 46/4\n3-01-24\n", "dz. 46/4\n3-01-24"),
    ("Osoba  Fizyczna", "Osoba Fizyczna"),
    (dt.datetime(2020, 9, 1), "2020-09-01"),
    (1.0, "1"),
    (None, ""),
])
def test_tidy_cell(value, expected):
    assert tidy_cell(value) == expected


def test_fold_is_length_preserving():
    s = "Żółkiewskiego „Nila” – Praga-Południe"
    assert fold(s) == 'zolkiewskiego "nila" - praga-poludnie'
    assert len(fold(s)) == len(s)


@pytest.mark.parametrize("text, month", [
    ("Lipiec 2026", 7), ("SIERPIEŃ", 8), ("LUTY-21", 2), ("maj 2023r.", 5), ("w październiku", 10),
    ("Grudzień 2021 r.", 12), ("wrzesnień 2021", 9), ("majątek", None), ("", None),
])
def test_month_from_text(text, month):
    assert month_from_text(text) == month


# =========================================================================== numbers and ids


@pytest.mark.parametrize("value, expected", [
    ("15/PPD/WZ/2026\n", "15/PPD/WZ/2026"),
    ("18/WZ/PPd/20                       ", "18/WZ/PPd/20"),
    ("UD-VI-WAB-\nU.6730.36.2026.AZM", "UD-VI-WAB-U.6730.36.2026.AZM"),
    ("UD-VI -WAB-U. 6733.11.2022.AZM", "UD-VI-WAB-U.6733.11.2022.AZM"),
    ("11/PPD/WZ/\n2024\n", "11/PPD/WZ/2024"),
    (None, ""),
])
def test_clean_number(value, expected):
    assert clean_number(value) == expected


@pytest.mark.parametrize("number, seq, year, typ", [
    ("15/PPD/WZ/2026", 15, 2026, "wz"),
    ("17/WZ/PPd/2020", 17, 2020, "wz"),
    ("18/WZ/PPd/20", 18, 2020, "wz"),
    ("19/WZ/PPD", 19, None, "wz"),
    ("5WZ/PPd/2023", 5, 2023, "wz"),
    ("8CP/PPd/2021", 8, 2021, "cp"),
    ("7/WZ/PPd2022", 7, 2022, "wz"),
    ("26/WZ/PPd//2022", 26, 2022, "wz"),
    ("42/WZ/PPd/23021", 42, None, "wz"),
    ("9/PPd/CP/2024", 9, 2024, "cp"),
    ("x", None, None, None),
])
def test_parse_decision_number(number, seq, year, typ):
    d = parse_decision_number(number)
    assert (d["seq"], d["year"], d["type"]) == (seq, year, typ)


@pytest.mark.parametrize("sign, jrwa, seq, year", [
    ("UD-VI-WAB-U.6730.57.2020.AZM", "6730", 57, 2020),
    ("UD-VI-WAB-U.6733.34.2020.MWR", "6733", 34, 2020),
    ("UD-VI-WAB-U-6730.1.2021.FBA", "6730", 1, 2021),
    ("UD-VI-WAB-U.730.16.2021.AZM", "6730", 16, 2021),       # typo → corrected
    ("UD-VI-WAB-⏎.U.6730.38.2025.AKU".replace("⏎", "\n"), "6730", 38, 2025),
    ("UD-VI-WAB-U.6730.51.2020.MWR/ AZM", "6730", 51, 2020),
    ("UD-VI-WAB.-U.6730.23.2025.AKU", "6730", 23, 2025),
    ("brak", None, None, None),
])
def test_parse_case_sign(sign, jrwa, seq, year):
    cs = parse_case_sign(sign)
    assert (cs["jrwa"], cs["seq"], cs["year"]) == (jrwa, seq, year)


@pytest.mark.parametrize("kind, number, date, expected_id, warning", [
    ("wz", "15/PPD/WZ/2026", "2026-07-09", "wz-2026-15", None),
    ("wz", "18/WZ/PPd/20", "2020-09-17", "wz-2020-18", None),
    ("wz", "19/WZ/PPD", "2020-09-29", "wz-2020-19", "brak roku"),
    ("wz", "42/WZ/PPd/23021", "2021-12-20", "wz-2021-42", "nieprawidłowy rok"),
    ("wz", "27/WZ/PPd/2023", "2024-12-30", "wz-2023-27", "różni się od roku daty"),
    ("cp", "29/CP/PPD/2020", "2020-09-23", "cp-2020-29", None),
    ("wz", "8CP/PPd/2021", "2021-09-20", "wz-2021-8", "wskazuje na CP"),
    ("ws", "UD-VI-WAB-U.6730.29.2026.AKU", "2026-07-14", "ws-6730-2026-29", None),
    ("ws", "UD-VI-WAB-U.730.16.2021.AZM", "2021-03-22", "ws-6730-2021-16", "literówka"),
    ("ws", "UD-VI-WAB-U.6730.90.2019.FBA", "2021-05-25", "ws-6730-2019-90", None),
    ("ws", "bez znaku", "2021-05-25", "ws-fabc1234567-r9", "nie rozpoznano znaku"),
    ("wz", "", "2021-05-25", "wz-fabc1234567-r9", "brak numeru"),
    ("wz", "19/WZ/PPD", None, "wz-fabc1234567-r9", "brak daty"),
])
def test_record_id(kind, number, date, expected_id, warning):
    rid, warnings = record_id(kind, number, date, "abc1234567", 9)
    assert rid == expected_id
    if warning:
        assert any(warning in w for w in warnings), warnings
    else:
        assert warnings == []
    assert re.fullmatch(r"[a-z0-9-]+", rid)


# =========================================================================== dates


@pytest.mark.parametrize("value, iso", [
    (dt.datetime(2020, 9, 1), "2020-09-01"),
    ("09.07.2026r.", "2026-07-09"),
    ("2020.09.23", "2020-09-23"),
    ("24.07.2026 r.", "2026-07-24"),
    ("2021-01-08.", "2021-01-08"),
    ("22.06.2023R.", "2023-06-22"),
    ("28.10.2024r. ", "2024-10-28"),
    ("2024-12-07", "2024-12-07"),
    (44000, "2020-06-18"),             # Excel serial number (= openpyxl from_excel)
])
def test_parse_date_variants(value, iso):
    got, raw, warnings = parse_date(value)
    assert got == iso
    assert raw


@pytest.mark.parametrize("value, period, warning", [
    ("31.02.2021", None, "nie rozpoznano daty"),
    ("wkrótce", None, "nie rozpoznano daty"),
    (None, None, "brak daty"),
    ("01.01.2020", "2020-09", "odbiega o"),
    ("data: 01.09.2020", "2020-09", "dodatkowym tekstem"),
])
def test_parse_date_warnings(value, period, warning):
    _, _, warnings = parse_date(value, period)
    assert any(warning in w for w in warnings), warnings


def test_parse_date_sanity_window():
    # within the month or up to 62 days outside it: fine (decisions are often listed a month late)
    assert parse_date("02.04.2025r.", "2025-03")[2] == []
    assert parse_date("11.03.2025r.", "2025-04")[2] == []
    assert parse_date(dt.datetime(2024, 12, 30), "2024-12")[2] == []


# =========================================================================== applicant / privacy


@pytest.mark.parametrize("value, typ", [
    ("osoba fizyczna ", "person"),
    ("Osoba Fizyczna -Pełnomocnik", "person"),
    ("Osoba  Fizyczna    -Pełnomocnik", "person"),
    ("Osoby fizyczne reprezentowane przez pełnomocnika", "person"),
    ("Osoba fizyczna pełnomocnik osoba fizyczna", "person"),
    ("Pani Agata Kowalska reprezentowana przez pełnomocnika", "person"),   # redacted first
    ("PIT-RADWAR S.A. działająca przez pełnomocnika", "organization"),
    ("Spółka Innogy Stoen Operator Sp. z o.o. -pełnomocnik osoba fizyczna", "organization"),
    ("Wspólnota Mieszkaniowa Osowska 32", "organization"),
    ("", "unknown"),
    (None, "unknown"),
])
def test_applicant_type(value, typ):
    assert applicant_type(clean_applicant(value)) == typ


@pytest.mark.parametrize("text, expected", [
    ("Pani Agata Zesch-Fronc       reprezentowana przez pełnomocnika",
     f"{PERSON_REDACTED} reprezentowana przez pełnomocnika"),
    ("Pan Jan Kowalski", PERSON_REDACTED),
    ("Państwo Anna i Jan Nowak", PERSON_REDACTED),
    ("Panorama Development Sp. z o.o.", "Panorama Development Sp. z o.o."),
    ("MJS Studio Michał Spisak", "MJS Studio Michał Spisak"),          # business name: kept
    ("osoba fizyczna", "osoba fizyczna"),
])
def test_redact_persons(text, expected):
    assert collapse_ws(redact_persons(text)) == expected


# =========================================================================== address


@pytest.mark.parametrize("raw, street, number, display, others", [
    ("Marokańska\nPraga-Południe\n", "Marokańska", None, "Marokańska", []),
    ("Osowska 37                            Praga-Południe", "Osowska", "37", "Osowska 37", []),
    ("Żupnicza 25\nPraga-Południe", "Żupnicza", "25", "Żupnicza 25", []),
    ("Abrahama   Praga-Poludnie", "Abrahama", None, "Abrahama", []),
    ("T.Zana 11 Praga Południe", "Zana", "11", "T. Zana 11", []),          # one spelling per street (canonical)
    ("Chodakowska   Praga- Południe", "Chodakowska", None, "Chodakowska", []),
    ("Lubartowska 23   Praga-Południw", "Lubartowska", "23", "Lubartowska 23", []),
    ("Fieldorfa \nPraga-Południa\n", "Fieldorfa", None, "Fieldorfa", []),
    ("Dwernickiego 20   Praga-Południ ", "Dwernickiego", "20", "Dwernickiego 20", []),
    ("Chodakowska 19/31  Praga-Południe ", "Chodakowska", "19/31", "Chodakowska 19/31", []),
    ("Podskarbińska 32/34", "Podskarbińska", "32/34", "Podskarbińska 32/34", []),
    ("Marokańska 1M   Praga-Południe", "Marokańska", "1M", "Marokańska 1M", []),
    ("Serocka 53a\nPraga-Południe", "Serocka", "53a", "Serocka 53a", []),
    ("Busolowa 16 A\n  Praga-Południe", "Busolowa", "16A", "Busolowa 16A", []),
    ("Przeworska 4A nr 419   Praga-Południe", "Przeworska", "4A", "Przeworska 4A nr 419", []),
    ("ul. Przeworska 7 lok. U6\nPraga-Południe", "Przeworska", "7", "Przeworska 7 lok. U6", []),
    ("Mikołajczyka 12/U4   Praga-Południe", "Mikołajczyka", "12", "Mikołajczyka 12/U4", []),
    ("ul. Makowska 155\nPraga-Południe\n", "Makowska", "155", "Makowska 155", []),
    ("al.Stanów Zjednoczonych 32 \nPraga-Południe", "Stanów Zjednoczonych", "32", "al. Stanów Zjednoczonych 32", []),
    ("ul. Awionetki RWD 1A\nPraga-Południe", "Awionetki RWD", "1A", "Awionetki RWD 1A", []),
    ("Gen. Fieldorfa Nila/Jana Nowaka Jeziorańskiego Praga-Południe", "Fieldorfa", None,
     "Gen. Fieldorfa Nila / Jana Nowaka Jeziorańskiego", [("Nowaka-Jeziorańskiego", [])]),
    ("Lubartowska23 i Serocka21   Praga-Południe", "Lubartowska", "23", "Lubartowska 23 i Serocka 21",
     [("Serocka", ["21"])]),
    ("Mińska 20/Głucha   Praga-Południe", "Mińska", "20", "Mińska 20 / Głucha", [("Głucha", [])]),
    ("Złotej Wilgi 2 róg Umińskiego   Praga-Południw", "Złotej Wilgi", "2", "Złotej Wilgi 2 róg Umińskiego",
     [("Umińskiego", [])]),
    ("Chodakowska   Żupnicza   Praga-Południe   ", "Chodakowska", None, "Chodakowska / Żupnicza", [("Żupnicza", [])]),
    ("Serocka 21,23   Dubieńska 22   Praga-Południe", "Serocka", "21", "Serocka 21, 23 / Dubieńska 22",
     [("Dubieńska", ["22"])]),
    ("Sygietyńskiego 4 i 4A   Praga-Południe", "Sygietyńskiego", "4", "Sygietyńskiego 4 i 4A", []),
    ("Drwęcka  i Siennicka   Praga-Południe", "Drwęcka", None, "Drwęcka i Siennicka", [("Siennicka", [])]),
    ("Jana Nowaka Jeziorańskiego oraz   Pasaż Złotej Wilgi   Praga-Południe", "Nowaka-Jeziorańskiego", None,
     "Jana Nowaka Jeziorańskiego oraz Pasaż Złotej Wilgi", [("Pasaż Złotej Wilgi", [])]),
    ("Wiatraczna (Kozia Górka)   Praga-Południe", "Wiatraczna", None, "Wiatraczna (Kozia Górka)", []),
    ("gen. Augusta Emila Fieldora \n„ Nila“41A\nPraga-Południe", "Fieldorfa", "41A",
     "gen. Augusta Emila Fieldora Nila 41A", []),
    ("dawna Siennicka48   Drwęcka   Praga-Południe", "Drwęcka", None, "dawna Siennicka 48 / Drwęcka",
     [("Siennicka", ["48"])]),
    ("Jana Nowaka - Jeziorańskiego   Praga -Południe ", "Nowaka-Jeziorańskiego", None,
     "Jana Nowaka-Jeziorańskiego", []),
])
def test_parse_address(raw, street, number, display, others):
    a = parse_address(raw)
    assert a["raw"] == raw
    assert (a["street"], a["number"], a["display"]) == (street, number, display)
    assert [(p["street"], p["numbers"]) for p in a["parts"][1:]] == others
    assert a["approximate"] is False


@pytest.mark.parametrize("raw, street, others", [
    ("rejon ul. Jugosłowaniańskiej   Praga-Południe", "Jugosłowiańska", []),
    ("w rejonie ulicy Chodakowskiej/   Rybnej/Kałuszyńskiej   Praga-Południe", "Chodakowska", ["Rybna", "Kałuszyńska"]),
    ("w rejonie Jeziorka Gocławskiego /\nul. Kwarciana   Praga-Południe", "Kwarciana", []),
    ("w rejonie Al. Stanów Zjednoczonych i ul. Wzorcowej", "Stanów Zjednoczonych", ["Wzorcowa"]),
    ("rejon ul. Skalskiego oraz \nul. Rogalskiego 8\nPraga-Południe", "Skalskiego", ["Rogalskiego"]),
])
def test_parse_address_approximate(raw, street, others):
    a = parse_address(raw)
    assert a["approximate"] is True
    assert a["street"] == street
    assert [p["street"] for p in a["parts"][1:]] == others
    assert a["display"].lower().startswith(("rejon", "w rejonie"))


def test_parse_address_typo_fix_is_reported():
    warnings: list[str] = []
    a = parse_address("ul.Borlemowska 49\nPraga-Południe", warnings)
    assert (a["street"], a["display"]) == ("Boremlowska", "Borlemowska 49")
    assert warnings == ["poprawiono pisownię ulicy: „Borlemowska” → „Boremlowska”"]


@pytest.mark.parametrize("raw, street", [
    ("Ulrychowska 5", "Ulrychowska"), ("Algierska 16", "Algierska"), ("ul Makowska 3", "Makowska"),
    ("Al. Stanów Zjednoczonych 59", "Stanów Zjednoczonych"),
])
def test_parse_address_prefix_needs_dot_or_space(raw, street):
    assert parse_address(raw)["street"] == street


def test_parse_address_empty():
    assert parse_address(None)["street"] is None
    assert parse_address("   ")["display"] == ""


@pytest.mark.parametrize("a, b", [
    ("ul. Gen. Bora-Komorowskiego", "Bora Komorowskiego"),
    ("Jana Nowaka - Jeziorańskiego", "Nowaka-Jeziorańskiego"),
    ("St. Augusta", "Stanisława Augusta"),
    ("T. Zana", "Zana"),
    ("W. Rychtera", "Rychtera"),
    ("Gen. Fieldorfa Nila", "Fieldorfa"),
    ("gen. A. E. Feildorfa „Nila”", "Fieldorfa"),
    ("Generała Abrahama", "gen. Romana Abrahama"),
    ("Ignacego Domeyki", "Domeyki"),
    ("Chdakowska", "Chodakowska"),
    ("al. Stanów Zjednoczonych", "Stanów Zjednoczonych"),
])
def test_street_key_matches_variants(a, b):
    assert street_key(a) == street_key(b) != ""


@pytest.mark.parametrize("variant, canonical", [
    ("Fieldorfa Nila", "Fieldorfa"), ("Fieldorfa", "Fieldorfa"), ("gen. A. E. Fieldorfa Nila", "Fieldorfa"),
    ("Augusta Emila Fieldorfa", "Fieldorfa"), ("gen. Augusta Emila Fieldorfa Nila", "Fieldorfa"),
    ("gen. Emila Fieldorfa Nila", "Fieldorfa"),
    ("Jerzego Waszyngtona", "Waszyngtona"), ("Jana Nowaka Jeziorańskiego", "Nowaka-Jeziorańskiego"),
    ("gen. Romana Abrahama", "Abrahama"), ("Generała Abrahama", "Abrahama"), ("Janusza Meissnera", "Meissnera"),
    # "Stanisława Augusta" is a street of its own: its first name stays (the key drops it, the name does not)
    ("St. Augusta", "Stanisława Augusta"), ("Stanisława Augusta", "Stanisława Augusta"),
    ("Grochowska", "Grochowska"), ("Pasaż Złotej Wilgi", "Pasaż Złotej Wilgi"),
])
def test_canonical_street(variant, canonical):
    assert canonical_street(variant) == canonical


def test_canonical_streets_keep_their_key():
    # address.street changes spelling only: related records (street_key + house number) must not change
    for key, name in STREET_CANONICAL.items():
        assert street_key(name) == key, name
    assert canonical_street(None) is None and canonical_street("") == ""


def test_street_key_keeps_distinct_streets_apart():
    assert street_key("Złotej Wilgi") != street_key("Pasaż Złotej Wilgi")
    assert street_key("Kozia Górka") == "kozia gorka"
    assert street_key(None) == ""


# =========================================================================== parcels


def _compact(parcels):
    return [(p["number"], p["obreb"], p["partial"], p.get("access", False)) for p in parcels]


@pytest.mark.parametrize("raw, expected", [
    ("dz. 46/4\n3-01-24", [("46/4", "3-01-24", False, False)]),
    ("dz.30/1-cz.\n3-03-02\n", [("30/1", "3-03-02", True, False)]),
    ("49                                                  3-02-06", [("49", "3-02-06", False, False)]),
    ("2 i 3-cz.                                      3-04-13", [("2", "3-04-13", False, False), ("3", "3-04-13", True, False)]),
    ("24/1,27/2,24/4-cz.,23-cz.    3-02-03",
     [("24/1", "3-02-03", False, False), ("27/2", "3-02-03", False, False),
      ("24/4", "3-02-03", True, False), ("23", "3-02-03", True, False)]),
    ("4/13-cz. i 4/24-cz.    3-05-21", [("4/13", "3-05-21", True, False), ("4/24", "3-05-21", True, False)]),
    ("16-cz   3-06-03", [("16", "3-06-03", True, False)]),
    ("2/1 cz.   3-02-11 ", [("2/1", "3-02-11", True, False)]),
    ("2/5cz.   3-02-11", [("2/5", "3-02-11", True, False)]),
    ("8/4-część   3-04-03", [("8/4", "3-04-03", True, False)]),
    ("3/65, 3/16- cz.   3-06-07", [("3/65", "3-06-07", False, False), ("3/16", "3-06-07", True, False)]),
    ("8/4-cz./   3-04-03", [("8/4", "3-04-03", True, False)]),
    ("4 ,5,12   3-02-11 ", [("4", "3-02-11", False, False), ("5", "3-02-11", False, False), ("12", "3-02-11", False, False)]),
    ("4/16 4/36   3-05-21", [("4/16", "3-05-21", False, False), ("4/36", "3-05-21", False, False)]),
    ("dz.4/1, 3-02-08", [("4/1", "3-02-08", False, False)]),
    ("dz. 139-cz.,\n3-04-10", [("139", "3-04-10", True, False)]),
    ("33-cz. I 21/3-cz.   3-05-25", [("33", "3-05-25", True, False), ("21/3", "3-05-25", True, False)]),
    ("CZ. 2/2  (DAWNIEJ 2/1)   3-02-11", [("2/2", "3-02-11", True, False)]),
    ("26cz.(dot.nadwieszenia balkonów),32,30cz.   3-04-13  ",
     [("26", "3-04-13", True, False), ("32", "3-04-13", False, False), ("30", "3-04-13", True, False)]),
    ("cz. dz.1, 13/5, dz. 13/2, 9/7\n3-05-24\n",       # repeated "dz." ends the partial group
     [("1", "3-05-24", True, False), ("13/5", "3-05-24", True, False),
      ("13/2", "3-05-24", False, False), ("9/7", "3-05-24", False, False)]),
    ("3/12 cz. 11 3-02-03", [("3/12", "3-02-03", False, False), ("11", "3-02-03", True, False)]),
])
def test_parse_parcels_single_group(raw, expected):
    parcels, warnings = parse_parcels(raw)
    assert _compact(parcels) == expected
    assert warnings == []
    for p in parcels:
        assert p["id"] == parcel_id(p["obreb"], p["number"])


def test_parse_parcels_multi_obreb_each_obreb_follows_its_list():
    raw = ("3/27,3/6,3/5,3/48,3/4,3/24,3/23,3/22,8,3/50,3/51,3/52,3/53,3/54,3/55,3/56,3/57,3/58,3/59,3/60,3/61,3/62,"
           "3/63,3/64,3/65,3/66,3/67,3/68,3/69,3/70,3/71,3/72,3/73,3/74,3/75,3/76,3/77,3/78,3/79,3/80,3/81,3/82,3/83,"
           "3/84,3/85,3/86,3/87,3/88,3/89,3/90,3/91,3/92,3/93                          3-03-06"
           "                2,1,5/2                          3-03-07")
    parcels, warnings = parse_parcels(raw)
    assert warnings == []
    first = [p for p in parcels if p["obreb"] == "3-03-06"]
    second = [p for p in parcels if p["obreb"] == "3-03-07"]
    assert len(first) == 53 and first[0]["number"] == "3/27" and first[-1]["number"] == "3/93"
    assert [p["number"] for p in second] == ["2", "1", "5/2"]
    assert second[2]["id"] == "146507_8.0307.5/2"


@pytest.mark.parametrize("raw, expected", [
    ("1/1-cz.   3-02-11   7-cz.   3-02-03", [("1/1", "3-02-11", True, False), ("7", "3-02-03", True, False)]),
    ("cz.66   3-04-05   cz.8,cz.3/4,3/6 cz.,cz.3/22   3-03-06",
     [("66", "3-04-05", True, False), ("8", "3-03-06", True, False), ("3/4", "3-03-06", True, False),
      ("3/6", "3-03-06", True, False), ("3/22", "3-03-06", True, False)]),
    ("2/8  3-02-11   1/8 i 7  3-02-03   cz.1/1,2/8   3-02-11",       # 2/8 listed whole and partial → whole
     [("2/8", "3-02-11", False, False), ("1/8", "3-02-03", False, False), ("7", "3-02-03", False, False),
      ("1/1", "3-02-11", True, False)]),
    ("Mińska\nna części dz. 1/2, 38/1 i 60 (3-02-06), część dz. 19   (3-02-03), dz.1  (3-02-07)",
     [("1/2", "3-02-06", True, False), ("38/1", "3-02-06", True, False), ("60", "3-02-06", True, False),
      ("19", "3-02-03", True, False), ("1", "3-02-07", False, False)]),
    ("cz.3/1(dawniej 3),3/2(dawniej3),3/12(dawniej 3)cz. 11   3-02-03",
     [("3/1", "3-02-03", True, False), ("3/2", "3-02-03", True, False), ("3/12", "3-02-03", True, False),
      ("11", "3-02-03", True, False)]),
    ("cz.3/1,3/2   dawnej 3   3-02-03 i cz.11   3-02-03",
     [("3/1", "3-02-03", True, False), ("3/2", "3-02-03", True, False), ("11", "3-02-03", True, False)]),
    ("44 oraz 45   3-07-18   z dojazdem poprzez 60/25, 10   3-07-18",
     [("44", "3-07-18", False, False), ("45", "3-07-18", False, False),
      ("60/25", "3-07-18", False, True), ("10", "3-07-18", False, True)]),
])
def test_parse_parcels_multi_group(raw, expected):
    parcels, warnings = parse_parcels(raw, street_hint="Mińska")
    assert _compact(parcels) == expected
    assert warnings == []


@pytest.mark.parametrize("raw, expected, warning", [
    ("67   30-05-11", [("67", "3-05-11", False, False)], "poprawiono zapis obrębu „30-05-11”"),
    ("51,52,53,54   3-04-012", [(n, "3-04-12", False, False) for n in ("51", "52", "53", "54")], "3-04-012"),
    ("6/8   3-07-18   6/7,60/25.1   3-07-18",
     [("6/8", "3-07-18", False, False), ("6/7", "3-07-18", False, False), ("60/25", "3-07-18", False, False),
      ("1", "3-07-18", False, False)], "kropkę w „60/25.1”"),
    ("część dz. 32/26   3-06-01   z dojazdem poprzez dz. 33/1, 33/2",
     [("32/26", "3-06-01", True, False), ("33/1", "3-06-01", False, True), ("33/2", "3-06-01", False, True)],
     "przypisano do obrębu 3-06-01"),
    ("część dz.6/8 z obrębu   3-07-18 \nz dojazdem poprzez  dz. 6/7-cz., 8   ",
     [("6/8", "3-07-18", True, False), ("6/7", "3-07-18", True, True), ("8", "3-07-18", False, True)],
     "przypisano do obrębu"),
    ("46/4 obok Biedronki   3-01-24", [("46/4", "3-01-24", False, False)], "niezrozumiały fragment"),
])
def test_parse_parcels_corrections_are_reported(raw, expected, warning):
    parcels, warnings = parse_parcels(raw)
    assert _compact(parcels) == expected
    assert any(warning in w for w in warnings), warnings


@pytest.mark.parametrize("raw, warning", [
    ("46/4", "brak numeru obrębu"),
    ("teren przy szkole", "nie rozpoznano numerów działek"),
    ("3-01-24", "bez numerów działek"),
])
def test_parse_parcels_unparseable_never_guesses(raw, warning):
    parcels, warnings = parse_parcels(raw)
    assert parcels == []
    assert any(warning in w for w in warnings), warnings


def test_parse_parcels_empty():
    assert parse_parcels(None) == ([], [])
    assert parse_parcels("   ") == ([], [])


def test_parcel_id_format():
    assert parcel_id("3-01-24", "46/4") == "146507_8.0124.46/4"
    assert parcel_id("3-05-21", "4") == "146507_8.0521.4"


# =========================================================================== whole rows

META = {"file_id": "03a2d4f046", "page_id": "informacje-o-wszczetych-postepowaniach-07-2026", "period": "2026-07"}


def test_normalize_row_new_wz_matches_contract_example():
    pf = parse_workbook(FIX / "new-wz-2026-07.xlsx")
    rec = normalize_row(pf["rows"][0], pf["kind"], META)
    assert rec["id"] == "wz-2026-15"
    assert (rec["kind"], rec["procedure"]) == ("wz", "wz")
    assert (rec["number"], rec["date"], rec["date_raw"], rec["period"]) == ("15/PPD/WZ/2026", "2026-07-09", "09.07.2026r.", "2026-07")
    assert (rec["applicant"], rec["applicant_type"]) == ("osoba fizyczna", "person")
    assert rec["investment"] == "budowa budynku mieszkalnego jednorodzinnego"
    assert rec["address"]["raw"] == "Marokańska\nPraga-Południe\n"
    assert (rec["address"]["street"], rec["address"]["number"], rec["address"]["display"]) == ("Marokańska", None, "Marokańska")
    assert rec["parcels"] == [{"number": "46/4", "obreb": "3-01-24", "partial": False, "id": "146507_8.0124.46/4"}]
    assert rec["parcels_raw"] == "dz. 46/4\n3-01-24"
    assert rec["tags"] == ["jednorodzinny", "nowa-budowa"]
    # v2 fields on every record (DATA_MODEL.md → "v2 extension")
    assert (rec["dataset"], rec["issuer"], rec["outcome"], rec["filed_date"], rec["permit"]) == (
        "district", "district", None, None, None)
    src = rec["sources"][0]
    assert (src["file_id"], src["page_id"], src["sheet"], src["row"]) == (
        "03a2d4f046", META["page_id"], "Decyzje o warunkach zabudowy", 6)
    assert src["raw"][:2] == [["Lp", "1"], ["Numer decyzji", "15/PPD/WZ/2026"]]
    assert all(isinstance(v, str) for _, v in src["raw"])
    assert rec["warnings"] == []
    assert "geo" not in rec and "related" not in rec and "area" not in rec


def test_normalize_row_old_ws_procedure_from_jrwa():
    pf = parse_workbook(FIX / "old-ws-2020-09-trailing-lp.xlsx")
    recs = [normalize_row(r, pf["kind"], {"file_id": "003e21f1e3", "page_id": "p", "period": "2020-09"}) for r in pf["rows"]]
    assert [r["id"] for r in recs] == ["ws-6730-2020-57", "ws-6733-2020-33", "ws-6730-2020-22", "ws-6730-2020-32",
                                       "ws-6730-2020-55"]
    assert [r["procedure"] for r in recs] == ["wz", "cp", "wz", "wz", "wz"]
    assert recs[0]["date"] == "2020-09-03"
    assert recs[0]["address"]["display"] == "Kamionkowska 29"
    assert recs[0]["parcels"][0]["id"] == "146507_8.0206.49"


def test_normalize_row_privacy_in_applicant_and_source_raw():
    pf = parse_workbook(FIX / "old-wz-2020-09-datetime-privacy.xlsx")
    rec = normalize_row(pf["rows"][2], pf["kind"], {"file_id": "55ccbc4e16", "page_id": "p", "period": "2020-09"})
    assert rec["id"] == "wz-2020-19"
    assert rec["applicant"] == f"{PERSON_REDACTED} reprezentowana przez pełnomocnika"
    assert rec["applicant_type"] == "person"
    raw_text = " ".join(v for _, v in rec["sources"][0]["raw"])
    assert "Zesch" not in raw_text and "Agata" not in raw_text
    assert PERSON_REDACTED in raw_text
    assert "brak roku w numerze decyzji – przyjęto rok z daty" in rec["warnings"]


def test_normalize_row_without_kind_infers_from_number():
    row = {"sheet": "S", "row": 7, "cells": {"lp": 1, "number": "UD-VI-WAB-U.6733.9.2022.AZM", "date": "08.03.2022",
                                              "applicant": "Veolia", "investment": "Budowa sieci ciepłowniczej",
                                              "address": "Kamionkowska 39", "parcels": "61 3-02-06"},
           "raw": [["Znak sprawy", "UD-VI-WAB-U.6733.9.2022.AZM"]], "warnings": []}
    rec = normalize_row(row, None, {"file_id": "x", "page_id": "p", "period": "2022-03"})
    assert (rec["kind"], rec["procedure"], rec["id"]) == ("ws", "cp", "ws-6733-2022-9")
    assert any("ustalono na podstawie numeru" in w for w in rec["warnings"])


def test_normalize_row_unknown_jrwa_symbol():
    row = {"sheet": "S", "row": 7, "cells": {"lp": 1, "number": "UD-VI-WAB-U.6731.9.2022.AZM", "date": "08.03.2022",
                                              "applicant": "x", "investment": "y", "address": "z", "parcels": "1 3-02-06"},
           "raw": [], "warnings": []}
    rec = normalize_row(row, "ws", {"file_id": "x", "page_id": "p", "period": "2022-03"})
    assert rec["procedure"] is None
    assert any("nieznany symbol JRWA 6731" in w for w in rec["warnings"])


def test_normalize_row_flags_public_purpose_symbol_on_housing():
    row = {"sheet": "S", "row": 7, "cells": {"lp": 1, "number": "UD-VI-WAB-U.6733.68.2021.MWR", "date": "18.10.2021",
                                              "applicant": "Osoba fizyczna",
                                              "investment": "Rozbudowa budynku mieszkalnego jednorodzinnego",
                                              "address": "Algierska 18B", "parcels": "10/45 3-01-24"},
           "raw": [], "warnings": []}
    rec = normalize_row(row, "ws", {"file_id": "x", "page_id": "p", "period": "2021-10"})
    assert rec["procedure"] == "cp"                       # contract: JRWA 6733 → cp, as printed
    assert any("możliwa pomyłka w źródle" in w for w in rec["warnings"])


def test_merge_duplicates():
    base = {"id": "wz-2025-29", "number": "29/PPD/WZ/2025", "date": "2025-09-22", "investment": "zmiana",
            "warnings": [], "sources": [{"file_id": "a", "sheet": "S", "row": 6}]}
    same = {**base, "sources": [{"file_id": "b", "sheet": "S", "row": 6}], "warnings": ["w"]}
    other = {**base, "date": "2025-10-01", "sources": [{"file_id": "c", "sheet": "S", "row": 9}]}
    out = merge_duplicates([base, same, other])
    assert [r["id"] for r in out] == ["wz-2025-29", "wz-2025-29-2"]
    assert [s["file_id"] for s in out[0]["sources"]] == ["a", "b"]
    assert "w" in out[0]["warnings"]
    assert all(any("inną treścią" in w for w in r["warnings"]) for r in out)
    assert base["sources"] == [{"file_id": "a", "sheet": "S", "row": 6}]   # inputs not mutated


# =========================================================================== whole corpus


@pytest.mark.skipif(not RAW.exists() or not any(RAW.glob("*.xlsx")), reason="data/raw not downloaded")
def test_all_raw_files_normalise():
    records = []
    for path in sorted(RAW.glob("*.xlsx")):
        pf = parse_workbook(path)
        if pf["layout"].startswith("baipp-"):
            continue  # city-wide BAiPP lists: filtered and namespaced, see tests/test_baipp.py
        for row in pf["rows"]:
            rec = normalize_row(row, pf["kind"], {"file_id": path.stem, "page_id": None, "period": None})
            records.append(rec)
            why = " ".join(rec["warnings"])
            assert rec["number"] or "numer" in why, rec["id"]
            assert rec["date"] or "dat" in why, rec["id"]
            assert rec["kind"] in ("wz", "cp", "ws") or "rodzaj" in why, rec["id"]
            assert re.fullmatch(r"[a-z0-9-]+", rec["id"]), rec["id"]
            assert rec["sources"][0]["raw"], rec["id"]
            if rec["parcels_raw"].strip() and not rec["parcels"]:
                assert why, rec["id"]   # an unparsed parcel cell must come with an explanation
    with_raw = [r for r in records if r["parcels_raw"].strip()]
    assert len(records) >= 450
    assert sum(1 for r in with_raw if r["parcels"]) / len(with_raw) >= 0.95
    # ids are unique across the whole corpus (no collisions to resolve today)
    assert len({r["id"] for r in records}) == len(records)


# =========================================================================== parcels: markers, current numbers


def _parts(parcels):
    return [(p["number"], p["obreb"], p["partial"]) for p in parcels]


def test_parenthesised_partial_markers():
    # BAiPP tram-line ULICP decisions write "32/26 (cz.)" – 45 parcels in three records
    parcels, warnings = parse_parcels("2/2, 31/2, 32/26 (cz.), 2/1, 29/8 (cz.), 1, 3/1 (cz.) 3-06-01", any_obreb=True)
    assert {p["number"]: p["partial"] for p in parcels} == {
        "2/2": False, "31/2": False, "32/26": True, "2/1": False, "29/8": True, "1": False, "3/1": True}
    assert warnings == []
    parcels, _ = parse_parcels("39 (cz.), 40, 21/2 (cz.) 3-06-05")
    assert _parts(parcels) == [("39", "3-06-05", True), ("40", "3-06-05", False), ("21/2", "3-06-05", True)]
    parcels, warnings = parse_parcels("3/11 (dawnej 14) 3-02-03")           # former numbers stay ignored
    assert _parts(parcels) == [("3/11", "3-02-03", False)] and warnings == []


def test_current_numbers_replace_the_subdivided_parcel():
    parcels, warnings = parse_parcels("3-cz. ( obecnie 3/1, 3/3, 3/4)  12-cz. 3-02-03", any_obreb=True)
    assert _parts(parcels) == [("3/1", "3-02-03", True), ("3/3", "3-02-03", True), ("3/4", "3-02-03", True),
                               ("12", "3-02-03", True)]
    assert warnings == ["działka 3 – w źródle podano jej obecne numery: 3/1, 3/3, 3/4"]


def test_number_cut_short_is_flagged():
    parcels, warnings = parse_parcels("12/;  3-06-06", any_obreb=True)
    assert parcels == [{"number": "12", "obreb": "3-06-06", "partial": False, "id": "146507_8.0606.12",
                        "incomplete": True}]
    assert any("niepełny numer działki „12/”" in w for w in warnings)
    parcels, warnings = parse_parcels("12/3, 13 3-06-06")
    assert not any(p.get("incomplete") for p in parcels) and warnings == []


def test_district_precinct_list():
    codes = sorted(PP_OBREBY)
    assert len(codes) > 90 and all(re.fullmatch(r"0[1-7]\d\d", c) for c in codes)
    doc_codes = __import__("json").loads((ROOT / "pipeline" / "data" / "praga_poludnie_obreby.json")
                                         .read_text(encoding="utf-8"))["obreby"]
    assert doc_codes == codes                                                   # committed sorted
    assert is_pp_obreb("0524") and not is_pp_obreb("0516") and not is_pp_obreb("0707") and not is_pp_obreb("1406")


def test_precinct_that_does_not_exist_in_the_district_is_flagged():
    parcels, warnings = parse_parcels("cz. 1/1, 2/5 3-05-16", any_obreb=True)
    assert [p["id"] for p in parcels] == ["146507_8.0516.1/1", "146507_8.0516.2/5"]
    assert warnings == ["obręb 3-05-16 nie istnieje w ewidencji gruntów Pragi-Południe – możliwy błąd w źródle"]
    _parcels, warnings = parse_parcels("18/5 4-15-08", any_obreb=True)       # other zones: the ULDK probe decides
    assert warnings == []
