"""Tests for pipeline.classify – texts are verbatim from the source files."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from pipeline.classify import TAGS, classify, explain
from pipeline.parse import parse_workbook

ROOT = Path(__file__).resolve().parents[1]

RAW = ROOT / "data" / "raw"
FUNCTION = {s for s, t in TAGS.items() if t["group"] == "funkcja"}


def test_taxonomy_shape():
    assert len(TAGS) >= 15
    for slug, tag in TAGS.items():
        assert re.fullmatch(r"[a-z]+(?:-[a-z]+)*", slug), slug          # ASCII kebab-case
        assert tag["label"] and len(tag["label"]) <= 40
        assert tag["description"].endswith(".")
        assert tag["group"] in ("funkcja", "roboty")
    assert list(TAGS)[-1] == "rozbiorka"                                  # works tags come after function tags


@pytest.mark.parametrize("text, expected", [
    # residential
    ("budowa budynku mieszkalnego jednorodzinnego ", ["jednorodzinny", "nowa-budowa"]),
    ("budowa dwóch budynków mieszkalnych jednorodzinnych w zabudowie bliźniaczej", ["jednorodzinny", "nowa-budowa"]),
    ("Budowa budynku mieszkalnego wielorodzinnego z usługami w parterze i garażem podziemnym",
     ["wielorodzinny", "nowa-budowa"]),                                   # services/garage are secondary
    ("Budowa budynku mieszkalnego wielorodzinnego \"B\"z częścią usługową w parterze i garażem",
     ["wielorodzinny", "nowa-budowa"]),
    ("Budowa budynku wielorodzinnegoi garażem", ["wielorodzinny", "nowa-budowa"]),
    ("Budowa budynku mieszkalnego ISKRA BIS PÓŁNOC z garażami w podziemiu i parterze", ["wielorodzinny", "nowa-budowa"]),
    ("budynek mieszkalny wielorodzinny z garażem podziemnym ", ["wielorodzinny", "nowa-budowa"]),
    ("Budowa budynku mieszkalno-usługowego z garażem podziemnym", ["wielorodzinny", "nowa-budowa"]),
    ("Budowa budynku mieszkalnego wielorodzinnego z garażem podziemnym i przedszkolem",
     ["wielorodzinny", "oswiata", "nowa-budowa"]),                        # kindergarten counts even as secondary
    ("Nadbudowa o2 kondygnacje z antresolą istniejącego budynku mieszkalnego wielorodzinnego",
     ["wielorodzinny", "rozbudowa-przebudowa"]),
    # conversions: tagged by what the space becomes
    ("zmiana sposobu użytkowania lokalu usługowego na lokal mieszkalny", ["adaptacja-mieszkalna", "zmiana-sposobu-uzytkowania"]),
    ("Zmiana sposobu użytkowania lokalu usługowego na żłobek", ["oswiata", "zmiana-sposobu-uzytkowania"]),
    ("Zmiana sposobu użytkowania lokalu nieużytkowego(pralni) na lokal usługowy(biuro) w budynku mieszkalnym wielorodzinnym",
     ["wielorodzinny", "uslugi", "zmiana-sposobu-uzytkowania"]),
    ("Zmiana sposobu użytkowania lokalu uslugowego (pracowni twórczej) na lokal mieszkalny w budynku mieszkalnym "
     "wielorodzinnym z częscią usługową", ["wielorodzinny", "adaptacja-mieszkalna", "zmiana-sposobu-uzytkowania"]),
    ("Przebudowa wraz ze zmianą sposobu uzytkowania lokalu przedszkolnego położonego w budynku mieszkalnym "
     "wielorodzinnym na lokale mieszkalne",
     ["wielorodzinny", "adaptacja-mieszkalna", "rozbudowa-przebudowa", "zmiana-sposobu-uzytkowania"]),
    ("Zmiana sposobu użytkowania pomieszczeń na pierwszym piętrze i poddaszu w budynku usługowo-handlowym na część "
     "mieszkalną", ["adaptacja-mieszkalna", "zmiana-sposobu-uzytkowania"]),
    ("zmiana sposobu użytkowania budynku garażu z poddaszem nieużytkowym na budynek mieszkalny jednorodzinny",
     ["jednorodzinny", "adaptacja-mieszkalna", "zmiana-sposobu-uzytkowania"]),
    ("Zmiana sposobu użytkowania lokalu użytkowego na lokal mioeszkalny", ["adaptacja-mieszkalna", "zmiana-sposobu-uzytkowania"]),
    ("zmianas posobu użytkowania poddasza nieużytkowego w budynku garażu na poddasze użytkowe mieszkalne",
     ["adaptacja-mieszkalna", "zmiana-sposobu-uzytkowania"]),
    ("przebudowa oraz zmiana sposobu użytkowania budynku usługowego biurowego na budynek usługowy o funkcji zamieszkania "
     "zbiorowego w formie domu studenckiego (akademik)wraz z lokalem usługowym w części parteru",
     ["zamieszkanie-zbiorowe", "uslugi", "rozbudowa-przebudowa", "zmiana-sposobu-uzytkowania"]),
    ("zmiama spsosobu użytkowania z lokalu użytkowego (sklep) na Bibliotekę Publiczną im. Zygmunta Jana Rumla",
     ["kultura", "zmiana-sposobu-uzytkowania"]),
    # services, public, technical
    ("Budowa pawilonu handlowego", ["uslugi", "nowa-budowa"]),
    ("Rozbudowa z przebudową istniejącego sklepu LIDL o pomieszczenie skupu butelek", ["uslugi", "rozbudowa-przebudowa"]),
    ("budowa, rozbudowa i nadbudowa budynku usług kultu religijnego -dom parafialny",
     ["kult-religijny", "nowa-budowa", "rozbudowa-przebudowa"]),
    ("przebudowa, rozbudowa i nadbudowa pawilonu III wraz z innymi niezbędnymi pomieszczeniami na terenie Szpitala "
     "Grochowskiego", ["zdrowie-opieka", "rozbudowa-przebudowa"]),
    ("Budowa parku w ramach zadania Budżeu Obywatelskiego pt: Park dla aktywnych.", ["sport-rekreacja-zielen", "nowa-budowa"]),
    ("budowa tężni solankowej wraz z przyłączem energii elektrycznej", ["sport-rekreacja-zielen", "nowa-budowa"]),
    ("Budowa parkingu naziemnego", ["parkingi-garaze", "nowa-budowa"]),
    ("Budowa osiedlowej sieci ciepłowniczej wraz z przyłączem do budynku przy ulicy Mińskiej 20",
     ["infrastruktura", "nowa-budowa"]),
    ("Budowa kontenerowej stacji tranformatorowej SN/nN 15/0, 4kV", ["infrastruktura", "nowa-budowa"]),
    ("budowa kontenerowej stacji transformatorowej Sn/nn/15/0,4kV dla potrzeb zasilania budynku mieszkalnego "
     "wielorodzinnego i budynku zamieszkania zbiorowego", ["infrastruktura", "nowa-budowa"]),
    ("Budowa odcinków kanalizacji kablowej wraz ze studniami typu SKMP-4", ["telekomunikacja", "nowa-budowa"]),
    ("Montaż masztu antenowego", ["telekomunikacja", "nowa-budowa"]),
    ("Budowa stacji bazowej telefonii komórkowej PLAY nr WAR2380A, w skład której wejdą anteny ..., urządzenia będą "
     "zlokalizowane na dachu budynku o funkcji biurowo-usługowej", ["telekomunikacja", "nowa-budowa"]),
    ("Budowa drogi publicznej o funkcji obsługi komunikacyjnej dla zabudowy mieszkaniowej wielorodzinnej",
     ["drogi-transport", "nowa-budowa"]),
    ("budowa podziemnego zbiornika przeciwpożarowego dla potrzeb istniejącego budynku nastawni ruchu kolejowego",
     ["infrastruktura", "drogi-transport", "nowa-budowa"]),
    ("budowa ogólnodostępnej stacji ładownia ", ["drogi-transport", "nowa-budowa"]),
    ("Budowa wolnostojącego nośnika reklamowego w postaci dwóch tablic (legalizacja obiektu)",
     ["reklama", "nowa-budowa", "legalizacja"]),
    ("budowa budynku produkcyjnego z częścią biurową ", ["przemysl-magazyny", "nowa-budowa"]),
    ("Budowa altany śmietnikowej", ["obiekty-pomocnicze", "nowa-budowa"]),
    ("rozbudowa budynku mieszkalnego wielorodzinnego o szyb dźwigowy wraz z przedsionkiem na parterze ",
     ["wielorodzinny", "windy-dostepnosc", "rozbudowa-przebudowa"]),
    ("Budowa schodów zewnętrznych i odtworzenie tarasu przy istniejącym budynku mieszkalnym jednorodzinnym",
     ["jednorodzinny", "rozbudowa-przebudowa"]),
    ("Zmiana Decyzji o warunkach zabudowy Nr 2/WZ/PPd/2021 z dnia 08.01.2021r. Poprzez wykreślenie wymogu",
     ["zmiana-decyzji"]),
    ("Budowa sieci wodociągowej wraz z przyłączami oraz umorzenie w części działek",
     ["infrastruktura", "nowa-budowa", "zmiana-decyzji"]),
    ("Rozbiórka budynku gospodarczego", ["obiekty-pomocnicze", "rozbiorka"]),
    ("", []),
    (None, []),
])
def test_classify(text, expected):
    assert classify(text) == expected


def test_classify_returns_tags_in_taxonomy_order():
    tags = classify("Zmiana sposobu użytkowania lokalu usługowego na cele mieszkaniowe oraz budowa parkingu")
    assert tags == [t for t in TAGS if t in tags]
    assert set(tags) == {"adaptacja-mieszkalna", "parkingi-garaze", "nowa-budowa", "zmiana-sposobu-uzytkowania"}


def test_explain_lists_clauses():
    clauses = explain("Nadbudowa budynku i zmiana sposobu użytkowania strychu na funkcję mieszkalną")
    assert [c for c, _ in clauses] == ["nadbudowa budynku", "zmiana sposobu uzytkowania strychu na funkcje mieszkalna"]


@pytest.mark.skipif(not RAW.exists() or not any(RAW.glob("*.xlsx")), reason="data/raw not downloaded")
def test_real_texts_coverage():
    parsed = [parse_workbook(p) for p in sorted(RAW.glob("*.xlsx"))]
    # district lists only: the city-wide BAiPP lists (tests/test_baipp.py) are mostly other districts' rows
    texts = [row["cells"]["investment"] for pf in parsed if not pf["layout"].startswith("baipp-") for row in pf["rows"]]
    tagged = [classify(t) for t in texts]
    assert all(tagged), "every record gets at least one tag"
    with_function = sum(1 for t in tagged if set(t) & FUNCTION)
    assert with_function / len(texts) >= 0.95
