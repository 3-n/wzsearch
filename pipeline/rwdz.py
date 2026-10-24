"""GUNB RWDZ ingest: building permits (``pb``) and notifications (``zg``) for Praga-Południe.

Source: *Rejestr Wniosków, Decyzji i Zgłoszeń w sprawach budowlanych* (RWDZ, art. 82b Prawo
budowlane), published by Główny Urząd Nadzoru Budowlanego as nightly refreshed bulk CSV files in
ZIP archives (CC0 1.0), https://wyszukiwarka.gunb.gov.pl/pobranie.html, mirrored on dane.gov.pl
(dataset 3467). Three archives matter for Warsaw:

* ``wynik_mazowieckie.zip``          – permit applications that ended with a decision (Mazowieckie);
* ``wynik_zgloszenia_2016_2021.zip`` – notifications, whole country, 2016–2021;
* ``wynik_zgloszenia_2022_up.zip``   – notifications, whole country, 2022 onwards.

Public API (consumed by ``pipeline/build.py``; contract in docs/DATA_MODEL.md, "v2 extension"):

* :func:`run_rwdz` – conditional download → byte-exact Praga-Południe extract → Records,
  ``files[]`` entries and the ``rwdz`` pseudo-page for ``sources.json``;
* dictionaries :data:`DATASET_META`, :data:`KIND_META`, :data:`PERMIT_SCOPES`,
  :data:`PERMIT_CATEGORIES` (+ the official :data:`CATEGORY_LABELS`).

How a run works (per archive):

1. **Download** (online): a conditional GET (``If-None-Match`` / ``If-Modified-Since``). The ZIP goes
   to ``data/cache/rwdz/`` (git-ignored, streamed to a temp file + ``os.replace``). ``304`` – or
   no network – means the committed extract is reused; the ZIP itself is not needed then (CI runners
   never have it).
2. **Extract**: the CSV inside the ZIP is streamed (never unzipped to disk) with ``csv`` over
   ``io.TextIOWrapper(encoding="utf-8-sig", newline="\\n")`` (lines split on ``\\n`` only, nothing
   translated); separator ``;`` (the GUNB page wrongly says ``#``).
   The header is validated on every run (duplicate ``cecha;cecha`` is read by position) and any
   drift raises :class:`RwdzFormatError` before anything is written. Every record of every case
   that has a parcel in Praga-Południe is copied **byte for byte** (original header line + original
   lines, same order, including quoted multi-line values) to ``data/raw/rwdz/<file_id>.csv``, next to
   ``<file_id>.meta.json`` (snapshot metadata and the original line number of every extract line).
3. **Records** are always built from the extract + sidecar – online and offline runs therefore
   produce identical output by construction.

Snapshot stability: the tracked files (extract, sidecar, ``data/cache/rwdz.json``) change only when
the Praga-Południe extract changes (its bytes or the original line numbers). GUNB rebuilds its files
every night; a night that changes nothing in the district leaves the repository untouched, and the
cited snapshot (ETag, Last-Modified, SHA-256 of the ZIP) stays the one the extract was taken from.
The HTTP validators of the local ZIP copy live in the untracked ``data/cache/rwdz/local.json``.

Privacy: designer columns (``projektant_*``, ``nazwisko_projektanta``, ``imie_projektanta``,
``projektant_pozostali``) never reach a Record – they remain only in the byte-exact extract.
GUNB itself blanks investors who are natural persons (→ ``"osoba fizyczna"``).

Run by hand: ``uv run python -m pipeline.rwdz [--offline] [--refresh]`` (prints a summary).
"""

from __future__ import annotations

import argparse
import codecs
import contextlib
import csv
import datetime as _dt
import functools
import hashlib
import io
import json
import math
import os
import re
import sys
import tempfile
import zipfile
from collections import Counter
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from email.utils import format_datetime, parsedate_to_datetime
from pathlib import Path
from typing import IO, Any

import requests

from .classify import TAGS, classify
from .http import make_session
from .normalize import (
    TERYT_PRAGA_POLUDNIE,
    applicant_type,
    canonical_street,
    clean_applicant,
    fix_street_typos,
    is_pp_obreb,
    redact_persons,
    street_key,
)
from .textutil import collapse_ws, fold, tidy_cell

__all__ = [
    "CATEGORY_LABELS",
    "CATEGORY_SOURCE",
    "DATASET_META",
    "EXPECTED_HEADERS",
    "FILES",
    "KIND_META",
    "PERMIT_CATEGORIES",
    "PERMIT_SCOPES",
    "RwdzFile",
    "RwdzFormatError",
    "build_records",
    "compose_address",
    "extract_csv",
    "issuer_of",
    "match_location",
    "read_extract",
    "record_id",
    "run_rwdz",
]

# =========================================================================== source description

BASE_URL = "https://wyszukiwarka.gunb.gov.pl/pliki_pobranie/"
DOWNLOAD_PAGE_URL = "https://wyszukiwarka.gunb.gov.pl/pobranie.html"
DATASET_URL = "https://dane.gov.pl/pl/dataset/3467"
LICENCE = "CC0 1.0"
LICENCE_URL = "https://creativecommons.org/publicdomain/zero/1.0/deed.pl"
PAGE_ID = "rwdz"
DATASET = "rwdz"
#: project-relative directory of the committed extracts (``files[].local_path``) and the site mirror
LOCAL_DIR = "data/raw/rwdz"
ARCHIVE_DIR = "sources/rwdz"
#: bump when the selection/extract rules change: a committed extract made by an older version is
#: then re-made from the ZIP (downloaded unconditionally if there is no local copy)
#: 2 (2026-10-23): cases of UNIT_FIXES are kept
EXTRACT_VERSION = 2
CSV_DELIMITER = ";"
CSV_ENCODING = "utf-8-sig"


@dataclass(frozen=True)
class RwdzFile:
    """One GUNB archive we read."""

    file_id: str     # stable id used in sources.json / Record.sources (``rwdz-…``)
    zip_name: str    # file name on the GUNB server
    kind: str        # pb | zg
    layout: str      # wnioski | zgloszenia (header layout)
    title: str       # Polish, user-facing (pseudo-page block text)

    @property
    def url(self) -> str:
        return BASE_URL + self.zip_name


FILES: tuple[RwdzFile, ...] = (
    RwdzFile("rwdz-wnioski", "wynik_mazowieckie.zip", "pb", "wnioski",
             "Wnioski i decyzje o pozwoleniu na budowę lub rozbiórkę – województwo mazowieckie"),
    RwdzFile("rwdz-zgloszenia-2016-2021", "wynik_zgloszenia_2016_2021.zip", "zg", "zgloszenia",
             "Zgłoszenia budowy i robót – cały kraj, 2016–2021"),
    RwdzFile("rwdz-zgloszenia-2022", "wynik_zgloszenia_2022_up.zip", "zg", "zgloszenia",
             "Zgłoszenia budowy i robót – cały kraj, od 2022 r."),
)

#: Exact header of each layout (validated on every run; ``cecha`` really appears twice).
EXPECTED_HEADERS: dict[str, tuple[str, ...]] = {
    "wnioski": (
        "numer_urzad", "numer_gunb", "nazwa_organu", "adres_organu", "data_wplywu_wniosku",
        "numer_decyzji_urzedu", "data_wydania_decyzji", "nazwa_inwestor", "wojewodztwo", "miasto", "terc",
        "cecha", "cecha", "ulica", "ulica_dalej", "nr_domu", "rodzaj_inwestycji", "kategoria",
        "nazwa_zamierzenia_bud", "nazwa_zam_budowlanego", "kubatura", "projektant_nazwisko", "projektant_imie",
        "projektant_numer_uprawnien", "jednosta_numer_ew", "obreb_numer", "numer_dzialki",
        "numer_arkusza_dzialki", "jednostka_stara_numeracja_z_wniosku", "stara_numeracja_obreb_z_wnioskiu",
        "stara_numeracja_dzialka_z_wniosku",
    ),
    "zgloszenia": (
        "numer_ewidencyjny_system", "numer_ewidencyjny_urzad", "data_wplywu_wniosku_do_urzedu", "nazwa_organu",
        "wojewodztwo_objekt", "obiekt_kod_pocztowy", "miasto", "terc", "cecha", "cecha", "ulica", "ulica_dalej",
        "nr_domu", "kategoria", "nazwa_zam_budowlanego", "rodzaj_zam_budowlanego", "kubatura", "stan",
        "jednostki_numer", "obreb_numer", "numer_dzialki", "numer_arkusza_dzialki", "nazwisko_projektanta",
        "imie_projektanta", "projektant_numer_uprawnien", "projektant_pozostali",
    ),
}


@dataclass(frozen=True)
class Layout:
    """Column roles of one header layout (positions are resolved from :data:`EXPECTED_HEADERS`)."""

    name: str
    case: str                    # case-identifying column (GUNB system number)
    case_sign: str               # office case sign / number
    number: str                  # record ``number``
    date: str                    # record ``date``
    filed: str                   # application/notification filing date
    unit: str                    # cadastral unit (jednostka ewidencyjna)
    investor: str | None
    scope: str
    single_family: str | None
    state: str | None
    parcel_cols: frozenset[str]  # vary between the rows of one case (one row per parcel)
    designer_cols: frozenset[str]

    @property
    def header(self) -> tuple[str, ...]:
        return EXPECTED_HEADERS[self.name]

    def index(self, column: str) -> int:
        """Position of the first column with this name."""
        return self.header.index(column)


LAYOUTS: dict[str, Layout] = {
    "wnioski": Layout(
        name="wnioski", case="numer_gunb", case_sign="numer_urzad", number="numer_decyzji_urzedu",
        date="data_wydania_decyzji", filed="data_wplywu_wniosku", unit="jednosta_numer_ew",
        investor="nazwa_inwestor", scope="nazwa_zamierzenia_bud", single_family="rodzaj_inwestycji", state=None,
        parcel_cols=frozenset({"jednosta_numer_ew", "obreb_numer", "numer_dzialki", "numer_arkusza_dzialki",
                               "jednostka_stara_numeracja_z_wniosku", "stara_numeracja_obreb_z_wnioskiu",
                               "stara_numeracja_dzialka_z_wniosku"}),
        designer_cols=frozenset({"projektant_nazwisko", "projektant_imie", "projektant_numer_uprawnien"}),
    ),
    "zgloszenia": Layout(
        name="zgloszenia", case="numer_ewidencyjny_system", case_sign="numer_ewidencyjny_urzad",
        number="numer_ewidencyjny_urzad", date="data_wplywu_wniosku_do_urzedu",
        filed="data_wplywu_wniosku_do_urzedu", unit="jednostki_numer", investor=None,
        scope="rodzaj_zam_budowlanego", single_family=None, state="stan",
        parcel_cols=frozenset({"jednostki_numer", "obreb_numer", "numer_dzialki", "numer_arkusza_dzialki"}),
        designer_cols=frozenset({"nazwisko_projektanta", "imie_projektanta", "projektant_numer_uprawnien",
                                 "projektant_pozostali"}),
    ),
}

# =========================================================================== dictionaries (Polish, UI)

DATASET_META: dict[str, str] = {
    "label": "Rejestr wniosków, decyzji i zgłoszeń (GUNB)",
    "short": "GUNB RWDZ",
    "publisher": "Główny Urząd Nadzoru Budowlanego",
    "url": DOWNLOAD_PAGE_URL,
    "dataset_url": DATASET_URL,
    "licence": LICENCE,
    "licence_url": LICENCE_URL,
    "description": (
        "Krajowy rejestr wniosków i decyzji o pozwoleniu na budowę lub rozbiórkę oraz części zgłoszeń "
        "(art. 82b Prawa budowlanego), prowadzony przez Główny Urząd Nadzoru Budowlanego i udostępniany "
        "co noc jako otwarte dane (CC0 1.0). Tu: sprawy z działkami na Pradze-Południe (jednostka ewidencyjna "
        "146507_8), wpisane do rejestru od 2016 r. Rejestr nie obejmuje spraw w toku, decyzji II instancji "
        "ani inwestycji na terenach zamkniętych (np. kolejowych i wojskowych)."
    ),
}

KIND_META: dict[str, dict[str, str]] = {
    "pb": {
        "label": "Pozwolenie na budowę lub rozbiórkę",
        "short": "Pozwolenie",
        "description": (
            "Sprawa o pozwolenie na budowę (także rozbudowę, nadbudowę, odbudowę lub inne roboty) albo na "
            "rozbiórkę, zakończona decyzją urzędu – z krajowego rejestru GUNB (dane od 2016 r.). Rejestr "
            "zawiera tylko sprawy już rozstrzygnięte w pierwszej instancji i nie podaje rodzaju rozstrzygnięcia: "
            "wpis zwykle oznacza wydane pozwolenie, ale może dotyczyć także odmowy lub umorzenia. "
            "Inwestorów będących osobami fizycznymi rejestr nie wymienia z nazwy."
        ),
    },
    "zg": {
        "label": "Zgłoszenie budowy lub robót",
        "short": "Zgłoszenie",
        "description": (
            "Zgłoszenie budowy lub robót budowlanych, do którego urząd nie wniósł sprzeciwu – z krajowego "
            "rejestru GUNB (dane od 2016 r.). Rejestr zgłoszeń jest z założenia niepełny: według opisu GUNB "
            "obejmuje m.in. wolno stojące domy jednorodzinne, których obszar oddziaływania mieści się na działce, "
            "wolno stojące parterowe budynki i kontenerowe stacje transformatorowe do 35 m² oraz sieci "
            "elektroenergetyczne do 1 kV, wodociągowe, kanalizacyjne, cieplne i telekomunikacyjne. Większości "
            "drobnych zgłoszeń (np. remontów) w nim nie ma. Rejestr nie podaje inwestora ani numeru decyzji."
        ),
    },
}

#: Works scope (``nazwa_zamierzenia_bud`` / ``rodzaj_zam_budowlanego``): slug → UI label + the
#: register's own wording. The register has no separate "przebudowa": it falls under "inne".
PERMIT_SCOPES: dict[str, dict[str, str]] = {
    "budowa": {"label": "Budowa nowego obiektu", "register": "budowa nowego/nowych obiektów budowlanych"},
    "rozbudowa": {"label": "Rozbudowa", "register": "rozbudowa istniejącego/istniejących obiektów budowlanych"},
    "nadbudowa": {"label": "Nadbudowa", "register": "nadbudowa istniejącego/istniejących obiektów budowlanych"},
    "odbudowa": {"label": "Odbudowa", "register": "odbudowa istniejącego/istniejących obiektów budowlanych"},
    "rozbiorka": {"label": "Rozbiórka", "register": "rozbiórka istniejącego obiektu budowlanego"},
    "inne": {"label": "Inne roboty budowlane (np. przebudowa, remont)",
             "register": "wykonanie robót budowlanych innych niż wymienione powyżej"},
}
_SCOPE_BY_REGISTER = {collapse_ws(fold(v["register"])): slug for slug, v in PERMIT_SCOPES.items()}

#: Where :data:`CATEGORY_LABELS` comes from (official consolidated text, checked 2026-10-23; the
#: amending acts published after it – Dz.U. 2025 poz. 1673, 2026 poz. 605, 646, 1161, 1347 – do not
#: touch the annex).
CATEGORY_SOURCE = {
    "title": "Ustawa z dnia 7 lipca 1994 r. – Prawo budowlane, załącznik „Kategorie obiektów budowlanych”, "
             "tekst jednolity Dz.U. 2026 poz. 524 (obwieszczenie Marszałka Sejmu z 27 marca 2026 r.)",
    "url": "https://isap.sejm.gov.pl/isap.nsf/DocDetails.xsp?id=WDU20260000524",
    "pdf": "https://isap.sejm.gov.pl/isap.nsf/download.xsp/WDU20260000524/T/D20260524L.pdf",
}

#: Categories of building works objects, **official wording** of the annex (see :data:`CATEGORY_SOURCE`;
#: only line-break hyphenation of the PDF is undone).
CATEGORY_LABELS: dict[str, str] = {
    "I": "budynki mieszkalne jednorodzinne",
    "II": "budynki służące gospodarce rolnej, jak: produkcyjne, gospodarcze, inwentarsko-składowe",
    "III": "inne niewielkie budynki, jak: domy letniskowe, budynki gospodarcze, garaże do dwóch stanowisk włącznie",
    "IV": "elementy dróg publicznych i kolejowych dróg szynowych, jak: skrzyżowania i węzły, wjazdy, zjazdy, "
          "przejazdy, perony, rampy",
    "V": "obiekty sportu i rekreacji, jak: stadiony, amfiteatry, skocznie i wyciągi narciarskie, kolejki linowe, "
         "odkryte baseny, zjeżdżalnie",
    "VI": "cmentarze",
    "VII": "obiekty służące nawigacji wodnej, jak: dalby, wysepki cumownicze",
    "VIII": "inne budowle",
    "IX": "budynki kultury, nauki i oświaty, jak: teatry, opery, kina, muzea, galerie sztuki, biblioteki, archiwa, "
          "domy kultury, budynki szkolne i przedszkolne, żłobki, kluby dziecięce, internaty, bursy i domy "
          "studenckie, laboratoria i placówki badawcze, stacje meteorologiczne i hydrologiczne, obserwatoria, "
          "budynki ogrodów zoologicznych i botanicznych",
    "X": "budynki kultu religijnego, jak: kościoły, kaplice, klasztory, cerkwie, zbory, synagogi, meczety oraz domy "
         "pogrzebowe, krematoria",
    "XI": "budynki służby zdrowia, opieki społecznej i socjalnej, jak: szpitale, sanatoria, hospicja, przychodnie, "
          "poradnie, stacje krwiodawstwa, lecznice weterynaryjne, domy pomocy i opieki społecznej, domy dziecka, "
          "domy rencisty, schroniska dla bezdomnych oraz hotele robotnicze",
    "XII": "budynki administracji publicznej, budynki Sejmu, Senatu, Kancelarii Prezydenta, ministerstw i urzędów "
           "centralnych, terenowej administracji rządowej i samorządowej, sądów i trybunałów, więzień i domów "
           "poprawczych, zakładów dla nieletnich, zakładów karnych, aresztów śledczych oraz obiekty budowlane "
           "Sił Zbrojnych",
    "XIII": "pozostałe budynki mieszkalne",
    "XIV": "budynki zakwaterowania turystycznego i rekreacyjnego, jak: hotele, motele, pensjonaty, domy "
           "wypoczynkowe, schroniska turystyczne",
    "XV": "budynki sportu i rekreacji, jak: hale sportowe i widowiskowe, kryte baseny",
    "XVI": "budynki biurowe i konferencyjne",
    "XVII": "budynki handlu, gastronomii i usług, jak: sklepy, centra handlowe, domy towarowe, hale targowe, "
            "restauracje, bary, kasyna, dyskoteki, warsztaty rzemieślnicze, stacje obsługi pojazdów, myjnie "
            "samochodowe, garaże powyżej dwóch stanowisk, budynki dworcowe",
    "XVIII": "budynki przemysłowe, jak: budynki produkcyjne, służące energetyce, montownie, wytwórnie, rzeźnie oraz "
             "obiekty magazynowe, jak: budynki składowe, chłodnie, hangary, wiaty, a także budynki kolejowe, jak: "
             "nastawnie, podstacje trakcyjne, lokomotywownie, wagonownie, strażnice przejazdowe, myjnie taboru "
             "kolejowego",
    "XIX": "zbiorniki przemysłowe, jak: silosy, elewatory, bunkry do magazynowania paliw i gazów oraz innych "
           "produktów chemicznych",
    "XX": "stacje paliw",
    "XXI": "obiekty związane z transportem wodnym, jak: porty, przystanie, sztuczne wyspy, baseny, doki, "
           "falochrony, nabrzeża, mola, pirsy, pomosty, pochylnie",
    "XXII": "place składowe, postojowe, składowiska odpadów, parkingi",
    "XXIII": "obiekty lotniskowe, jak: pasy startowe, drogi kołowania, płyty lotniskowe, place postojowe "
             "i manewrowe, lądowiska",
    "XXIV": "obiekty gospodarki wodnej, jak: zbiorniki wodne i nadpoziomowe, stawy rybne",
    "XXV": "drogi i kolejowe drogi szynowe",
    "XXVI": "sieci, jak: elektroenergetyczne, telekomunikacyjne, gazowe, wodorowe, ciepłownicze, wodociągowe, "
            "kanalizacyjne oraz rurociągi przesyłowe",
    "XXVII": "budowle hydrotechniczne piętrzące, upustowe i regulacyjne, jak: zapory, progi i stopnie wodne, jazy, "
             "bramy przeciwpowodziowe, śluzy wałowe, syfony, wały przeciwpowodziowe, kanały, śluzy żeglowne, "
             "opaski i ostrogi brzegowe, rowy melioracyjne",
    "XXVIII": "drogowe i kolejowe obiekty mostowe, jak: mosty, estakady, kładki, przejścia podziemne, wiadukty, "
              "przepusty, tunele",
    "XXIX": "wolno stojące kominy i maszty oraz części budowlane elektrowni wiatrowych",
    "XXX": "obiekty służące do korzystania z zasobów wodnych, jak: ujęcia wód morskich i śródlądowych, budowle "
           "zrzutów wód i ścieków, pompownie, stacje strefowe, stacje uzdatniania wody, oczyszczalnie ścieków",
}

#: Short UI labels (our abbreviation of the official wording above, for filter chips).
CATEGORY_SHORT: dict[str, str] = {
    "I": "budynki mieszkalne jednorodzinne",
    "II": "budynki gospodarki rolnej",
    "III": "niewielkie budynki (letniskowe, gospodarcze, małe garaże)",
    "IV": "elementy dróg publicznych i kolejowych",
    "V": "obiekty sportu i rekreacji (na otwartym terenie)",
    "VI": "cmentarze",
    "VII": "obiekty nawigacji wodnej",
    "VIII": "inne budowle",
    "IX": "budynki kultury, nauki i oświaty",
    "X": "budynki kultu religijnego",
    "XI": "budynki służby zdrowia i opieki społecznej",
    "XII": "budynki administracji publicznej, sądów i wojska",
    "XIII": "pozostałe budynki mieszkalne (m.in. wielorodzinne)",
    "XIV": "budynki zakwaterowania turystycznego",
    "XV": "budynki sportu i rekreacji (hale, kryte baseny)",
    "XVI": "budynki biurowe i konferencyjne",
    "XVII": "budynki handlu, gastronomii i usług",
    "XVIII": "budynki przemysłowe i magazynowe",
    "XIX": "zbiorniki przemysłowe",
    "XX": "stacje paliw",
    "XXI": "obiekty transportu wodnego",
    "XXII": "place składowe i postojowe, parkingi, składowiska",
    "XXIII": "obiekty lotniskowe",
    "XXIV": "obiekty gospodarki wodnej",
    "XXV": "drogi i tory kolejowe",
    "XXVI": "sieci (energetyczne, telekomunikacyjne, gazowe, ciepłownicze, wodno-kanalizacyjne)",
    "XXVII": "budowle hydrotechniczne",
    "XXVIII": "mosty, wiadukty, tunele",
    "XXIX": "wolno stojące kominy i maszty",
    "XXX": "ujęcia wody, pompownie, oczyszczalnie",
}

#: ``permit_categories`` dictionary for records.json (roman numeral → label + official wording).
PERMIT_CATEGORIES: dict[str, dict[str, str]] = {
    roman: {"label": CATEGORY_SHORT[roman], "description": f"Kategoria {roman} – {official}"}
    for roman, official in CATEGORY_LABELS.items()
}

#: Function tag implied by an object category – used only when the description itself names no
#: function (the free text is more specific: category XVII also covers large garages, XXVI telecom).
CATEGORY_TAGS: dict[str, str] = {
    "I": "jednorodzinny", "III": "obiekty-pomocnicze", "IV": "drogi-transport",
    "V": "sport-rekreacja-zielen", "X": "kult-religijny", "XI": "zdrowie-opieka", "XIII": "wielorodzinny",
    "XIV": "zamieszkanie-zbiorowe", "XV": "sport-rekreacja-zielen", "XVI": "uslugi", "XVII": "uslugi",
    "XVIII": "przemysl-magazyny", "XIX": "przemysl-magazyny", "XXII": "parkingi-garaze",
    "XXV": "drogi-transport", "XXVI": "infrastruktura", "XXVIII": "drogi-transport", "XXX": "infrastruktura",
}
#: Works tag implied by the scope (always added – the register field is authoritative).
SCOPE_TAGS: dict[str, str] = {
    "budowa": "nowa-budowa", "rozbudowa": "rozbudowa-przebudowa", "nadbudowa": "rozbudowa-przebudowa",
    "rozbiorka": "rozbiorka",
}

#: Warsaw district cadastral units (TERYT), for location notes.
WARSAW_UNITS: dict[str, str] = {
    "146502_8": "Bemowo", "146503_8": "Białołęka", "146504_8": "Bielany", "146505_8": "Mokotów",
    "146506_8": "Ochota", "146507_8": "Praga-Południe", "146508_8": "Praga-Północ", "146509_8": "Rembertów",
    "146510_8": "Śródmieście", "146511_8": "Targówek", "146512_8": "Ursus", "146513_8": "Ursynów",
    "146514_8": "Wawer", "146515_8": "Wesoła", "146516_8": "Wilanów", "146517_8": "Włochy", "146518_8": "Wola",
    "146519_8": "Żoliborz",
}

#: Zone digit of the Warsaw precinct names ``Z-SS-NN`` per unit (ULDK ids drop it: ``3-02-03`` → ``0203``);
#: the same table as ``baipp.OBREB_ZONES`` (verified there on 2,000+ BAiPP rows), inverted.
UNIT_ZONES: dict[str, str] = {
    "146505_8": "1", "146513_8": "1", "146516_8": "1", "146506_8": "2", "146512_8": "2", "146517_8": "2",
    "146507_8": "3", "146509_8": "3", "146514_8": "3", "146508_8": "4", "146511_8": "4", "146503_8": "4",
    "146510_8": "5", "146518_8": "6", "146502_8": "6", "146519_8": "7", "146504_8": "7", "146515_8": "8",
}

_PARCEL_ID_RE = re.compile(r"^\d{6}_\d\.\d{4}\.[0-9A-Za-z./-]+$")   # = geocode.normalize_parcel_id
_DISTRICT_OFFICE_RE = re.compile(r"praga\W*(?:pld|poludnie)")
_CITY_RE = re.compile(r"prezydent\s+(?:m\.\s*st\.\s*|miasta\s+(?:stolecznego\s+)?)?warszaw\w*")
_REGISTER_ID_RE = re.compile(r"^(?P<prefix>[A-Za-z0-9-]+)/(?P<type>[^/\d]+)/(?P<seq>\d+)/(?P<year>\d{4})$")
_DATE_RE = re.compile(r"(\d{4})-(\d{2})-(\d{2})(?:[ T]\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?)?")
_ROMAN_RE = re.compile(r"^[IVX]+$")
_BUILD_WORD_RE = re.compile(r"(?<![a-z])(?:wy)?budow|montaz")


class RwdzFormatError(ValueError):
    """The GUNB file (or a committed extract) does not look like what this module was written for."""


# =========================================================================== CSV reading


@dataclass
class CsvRecord:
    """One CSV record exactly as read: start line, the raw physical lines, the parsed fields."""

    line: int            # 1-based physical line where the record starts (line 1 = header)
    n_lines: int         # physical lines it spans (> 1 only for quoted values with line breaks)
    text: str            # the physical lines, byte-for-byte (incl. line terminators)
    fields: list[str]


def iter_records(text: IO[str]) -> Iterator[CsvRecord]:
    """Yield every CSV record of ``text`` together with the physical lines it was read from.

    ``text`` must split lines on ``\\n`` only and must not translate line endings
    (``newline="\\n"``), so that ``"".join(record.text …)`` re-encodes to the original bytes and
    line numbers match ``sed -n Np`` on the original file.
    """
    pending: list[str] = []

    def lines() -> Iterator[str]:
        for line in text:
            pending.append(line)
            yield line

    reader = csv.reader(lines(), delimiter=CSV_DELIMITER, quotechar='"')
    line_no = 1
    while True:
        try:
            fields = next(reader)
        except StopIteration:
            return
        except csv.Error as exc:
            raise RwdzFormatError(f"niepoprawny wiersz CSV w linii {line_no}: {exc}") from exc
        chunk, n = "".join(pending), len(pending)
        pending.clear()
        yield CsvRecord(line_no, n, chunk, fields)
        line_no += n


@contextlib.contextmanager
def _open_text(binary: IO[bytes]) -> Iterator[tuple[bool, IO[str]]]:
    """``(has_bom, text stream)`` over a binary stream – UTF-8 with optional BOM, ``\\n`` lines."""
    peek = getattr(binary, "peek", None)
    head = peek(3)[:3] if peek else b""
    text = io.TextIOWrapper(binary, encoding=CSV_ENCODING, newline="\n")
    try:
        yield head.startswith(codecs.BOM_UTF8), text
    finally:
        text.detach()


def _zip_member(zf: zipfile.ZipFile) -> str:
    names = [n for n in zf.namelist() if not n.endswith("/")]
    if len(names) != 1 or not names[0].lower().endswith(".csv"):
        raise RwdzFormatError(f"archiwum GUNB powinno zawierać jeden plik CSV, a zawiera: {names}")
    return names[0]


def _zip_opener(zip_path: Path) -> Callable[[], contextlib.AbstractContextManager[tuple[bool, IO[str]]]]:
    @contextlib.contextmanager
    def opener() -> Iterator[tuple[bool, IO[str]]]:
        with zipfile.ZipFile(zip_path) as zf, zf.open(_zip_member(zf)) as raw, _open_text(raw) as opened:
            yield opened
    return opener


def _file_opener(path: Path) -> Callable[[], contextlib.AbstractContextManager[tuple[bool, IO[str]]]]:
    @contextlib.contextmanager
    def opener() -> Iterator[tuple[bool, IO[str]]]:
        with path.open("rb") as raw, _open_text(raw) as opened:
            yield opened
    return opener


def validate_header(fields: Sequence[str], layout: Layout, where: str) -> None:
    """Raise :class:`RwdzFormatError` unless ``fields`` is exactly the expected header."""
    expected = list(layout.header)
    got = [f.strip() for f in fields]
    if got == expected:
        return
    missing = [c for c in expected if c not in got]
    extra = [c for c in got if c not in expected]
    first = next((i for i, (a, b) in enumerate(zip(expected, got)) if a != b), min(len(expected), len(got)))
    raise RwdzFormatError(
        f"{where}: nagłówek pliku GUNB się zmienił (układ „{layout.name}”) – oczekiwano {len(expected)} kolumn, "
        f"jest {len(got)}; brak: {missing or '–'}; nowe: {extra or '–'}; pierwsza różnica w kolumnie {first + 1}"
    )


# =========================================================================== location filter


def _osa_distance(a: str, b: str) -> int:
    """Edit distance with adjacent transpositions (optimal string alignment)."""
    d = [[0] * (len(b) + 1) for _ in range(len(a) + 1)]
    for i in range(len(a) + 1):
        d[i][0] = i
    for j in range(len(b) + 1):
        d[0][j] = j
    for i in range(1, len(a) + 1):
        for j in range(1, len(b) + 1):
            cost = 0 if a[i - 1] == b[j - 1] else 1
            d[i][j] = min(d[i - 1][j] + 1, d[i][j - 1] + 1, d[i - 1][j - 1] + cost)
            if i > 1 and j > 1 and a[i - 1] == b[j - 2] and a[i - 2] == b[j - 1]:
                d[i][j] = min(d[i][j], d[i - 2][j - 2] + 1)
    return d[len(a)][len(b)]


@functools.lru_cache(maxsize=8192)
def is_district_office(organ: str) -> bool:
    """``Prezydent Miasta Warszawa - Praga Płd.`` (the district's architecture department).

    Cached: called for every one of ~2.5 million register rows, with a few thousand distinct organs."""
    return bool(_DISTRICT_OFFICE_RE.search(fold(organ)))


#: Praga-Południe cases whose register rows carry another unit id – register errors verified one by one with
#: ULDK (2026-10-23): GUNB case number → the unit as printed. Rows of these cases with that unit are kept and
#: corrected to 146507_8 (reason "listed"). New candidates are listed in data/report.md ("signal" cases).
UNIT_FIXES = {
    # Szaserów 133, 110/PPD/PB/2024 (district office): 146510_8.0407.10/1 does not exist, 146507_8.0407.10/1 does
    "ST-MZ-PA/WNIOSEK/14200/2024": "146510_8",
    # Zwycięzców 34, 372/PRD/2018 (city): 146510_8.0113.6 does not exist, 146507_8.0113.6 and .7 do (3-01-13)
    "ST-MZ-WA/WNIOSEK/37134/2018": "146510_8",
    # Ostrobramska, 15/AM/PPD/PB/2024/Z (city; amends pb-st-mz-wa-2021-5533 on 146507_8.0524.45/46): there is no
    # precinct 146508_8.0524
    "ST-MZ-WA/WNIOSEK/19454/2023": "146508_8",
    # Koleje Mazowieckie depot, 329/SAAB/2026 (voivode): 146507_5 is no unit, 146507_8.0306.3/29 exists (3-06-03)
    "PL-MZ/WNIOSEK/15131/2026": "146507_5",
}


def match_location(unit: str, organ: str, case: str | None = None) -> str | None:
    """Why a register row belongs to Praga-Południe, or None.

    * ``"unit"`` – the parcel's cadastral unit is ``146507_8``;
    * ``"listed"`` – the case is in :data:`UNIT_FIXES` with exactly this (wrong) unit, any organ;
    * rows of the **district office** (``… - Praga Płd.``) with a broken unit id: ``"empty"`` (no
      unit), ``"typo"`` (one edit or one swap of adjacent characters away from ``146507_8``, e.g.
      ``148507_8``, ``146057_8``, ``146517_8``) or ``"invalid"`` (not a Warsaw district unit at all,
      e.g. ``146078_8``, ``086101_1``). A *valid* other Warsaw unit two or more edits away is a
      genuine neighbouring parcel (the office handled some Wawer cases ``146514_8`` in 2020) → None.
    """
    u = unit.strip()
    if u == TERYT_PRAGA_POLUDNIE:
        return "unit"
    if case is not None and u and UNIT_FIXES.get(case.strip()) == u:
        return "listed"
    if not is_district_office(organ):
        return None
    if not u:
        return "empty"
    if _osa_distance(u, TERYT_PRAGA_POLUDNIE) <= 1:
        return "typo"
    if u not in WARSAW_UNITS:
        return "invalid"
    return None


@dataclass
class Selection:
    """Result of scanning one CSV (a GUNB file or a committed extract)."""

    bom: bool
    header_text: str                     # the header's physical line (without BOM)
    rows_total: int                      # data records in the scanned file
    kept: list[CsvRecord]                # every record of every selected case, file order
    reasons: dict[int, str]              # start line → match reason of rows kept by the office rule
    cases: int = 0
    malformed: int = 0
    blank: int = 0
    not_kept_office_units: Counter = field(default_factory=Counter)   # office rows outside the district
    signal_cases: list[list] = field(default_factory=list)   # [case, first line, unit] of unkept "signal" cases


#: Signs of a Praga-Południe case in rows the unit rules do not keep (listed in the report for review, never
#: kept automatically: 94/AM/PPD/PB/2025 is a genuine Praga-Północ parcel): the district office's case signs
#: (``UD-VI-…``) and the district codes of the city's decision numbers (``…/PPD/…``, ``…/PRD/…``).
_SIGNAL_SIGN_RE = re.compile(r"^UD-VI-", re.I)
_SIGNAL_NUMBER_RE = re.compile(r"/P(?:PD|RD)/", re.I)


_MAX_MALFORMED_SHARE = 0.01


def select_cases(opener: Callable[[], contextlib.AbstractContextManager[tuple[bool, IO[str]]]],
                 layout: Layout, where: str) -> Selection:
    """Two streaming passes: (1) cases with a Praga-Południe row, (2) every record of those cases.

    A case is kept whole – also its rows on parcels of other units (e.g. a city permit spanning
    Śródmieście), so that a record lists every parcel the decision covers.
    """
    i_case, i_unit, i_organ = layout.index(layout.case), layout.index(layout.unit), layout.index("nazwa_organu")
    i_sign, i_number = layout.index(layout.case_sign), layout.index(layout.number)
    width = len(layout.header)
    kept_cases: set[str] = set()
    reasons: dict[int, str] = {}
    office_out: Counter = Counter()
    signals: dict[str, list] = {}
    rows_total = malformed = blank = 0

    with opener() as (bom, text):
        records = iter_records(text)
        head = next(records, None)
        if head is None:
            raise RwdzFormatError(f"{where}: pusty plik")
        validate_header(head.fields, layout, where)
        header_text = head.text
        for rec in records:
            if not rec.fields:
                blank += 1
                continue
            rows_total += 1
            if len(rec.fields) != width:
                if TERYT_PRAGA_POLUDNIE in rec.text or "Praga Płd" in rec.text:
                    raise RwdzFormatError(f"{where}: linia {rec.line} ma {len(rec.fields)} pól zamiast {width} "
                                          "i może dotyczyć Pragi-Południe")
                malformed += 1
                continue
            case = rec.fields[i_case].strip()
            reason = match_location(rec.fields[i_unit], rec.fields[i_organ], case)
            if reason:
                kept_cases.add(case)
                if reason != "unit":
                    reasons[rec.line] = reason
                continue
            if is_district_office(rec.fields[i_organ]):
                office_out[rec.fields[i_unit].strip()] += 1
            if case not in signals and (_SIGNAL_SIGN_RE.match(rec.fields[i_sign].strip())
                                        or _SIGNAL_NUMBER_RE.search(rec.fields[i_number])):
                signals[case] = [case, rec.line, rec.fields[i_unit].strip()]
    if rows_total and malformed > _MAX_MALFORMED_SHARE * rows_total:
        raise RwdzFormatError(f"{where}: {malformed} z {rows_total} wierszy ma złą liczbę pól – zmiana formatu?")

    kept: list[CsvRecord] = []
    with opener() as (_bom, text):
        records = iter_records(text)
        next(records)
        for rec in records:
            if len(rec.fields) == width and rec.fields[i_case].strip() in kept_cases:
                kept.append(rec)
    return Selection(bom=bom, header_text=header_text, rows_total=rows_total, kept=kept, reasons=reasons,
                     cases=len(kept_cases), malformed=malformed, blank=blank, not_kept_office_units=office_out,
                     signal_cases=[v for c, v in signals.items() if c not in kept_cases])


# =========================================================================== extract + sidecar


def extract_bytes(sel: Selection) -> tuple[bytes, list[int]]:
    """Byte-exact extract (BOM + original header line + kept lines) and the original line number of
    every extract line after the header (``lines[i]`` ↔ extract line ``i + 2``)."""
    parts = [sel.header_text]
    lines: list[int] = []
    for rec in sel.kept:
        parts.append(rec.text)
        lines.extend(range(rec.line, rec.line + rec.n_lines))
    data = "".join(parts).encode("utf-8")
    return (codecs.BOM_UTF8 if sel.bom else b"") + data, lines


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _write_atomic(path: Path, data: bytes) -> bool:
    """Write ``data`` atomically unless the file already holds exactly these bytes."""
    if path.is_file() and path.read_bytes() == data:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
        os.chmod(tmp, 0o644)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
    return True


def _dumps(doc: Mapping[str, Any]) -> bytes:
    """Diff-friendly JSON: one top-level key per line, compact values."""
    items = list(doc.items())
    out = ["{"]
    for i, (k, v) in enumerate(items):
        comma = "," if i < len(items) - 1 else ""
        out.append(f"{json.dumps(k, ensure_ascii=False)}:"
                   f"{json.dumps(v, ensure_ascii=False, separators=(',', ':'), sort_keys=isinstance(v, dict))}{comma}")
    out.append("}")
    return ("\n".join(out) + "\n").encode("utf-8")


def _load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as exc:
        raise RwdzFormatError(f"{path}: nieczytelny plik JSON ({exc})") from exc


def extract_csv(file: RwdzFile, zip_path: Path, raw_dir: Path, snapshot: Mapping[str, Any],
                log: Callable[[str], None] = print) -> tuple[bool, dict]:
    """Make the Praga-Południe extract of ``zip_path``; write it (+ sidecar) only if it changed.

    ``snapshot`` = HTTP metadata of the ZIP (url, etag, last_modified, sha256_zip, size, downloaded_at).
    Returns ``(written, sidecar)``; the sidecar on disk is kept as is when the extract is unchanged.
    """
    layout = LAYOUTS[file.layout]
    with zipfile.ZipFile(zip_path) as zf:
        member = _zip_member(zf)
    sel = select_cases(_zip_opener(zip_path), layout, f"{file.zip_name}")
    data, lines = extract_bytes(sel)
    csv_path, meta_path = raw_dir / f"{file.file_id}.csv", raw_dir / f"{file.file_id}.meta.json"
    old = _load_json(meta_path) if meta_path.is_file() else {}
    sha = _sha256_bytes(data)
    if (old.get("sha256") == sha and old.get("lines") == lines and old.get("extract_version") == EXTRACT_VERSION
            and csv_path.is_file() and _sha256_file(csv_path) == sha):
        log(f"rwdz: {file.file_id}: Praga-Południe extract unchanged ({len(sel.kept)} rows)")
        return False, old
    sidecar = {
        "file_id": file.file_id,
        "source": DATASET,
        "url": file.url,
        "dataset_url": DATASET_URL,
        "licence": LICENCE,
        "zip_name": file.zip_name,
        "zip_member": member,
        "etag": snapshot.get("etag"),
        "last_modified": snapshot.get("last_modified"),
        "sha256_zip": snapshot.get("sha256_zip"),
        "size_zip": snapshot.get("size"),
        "downloaded_at": snapshot.get("downloaded_at"),
        "encoding": CSV_ENCODING if sel.bom else "utf-8",
        "delimiter": CSV_DELIMITER,
        "layout": layout.name,
        "header": list(layout.header),
        "rows_total": sel.rows_total,
        "rows_malformed": sel.malformed,
        "filter": "sprawy z co najmniej jedną działką w jednostce ewidencyjnej 146507_8 (Praga-Południe) "
                  "– całe sprawy, ze wszystkimi wierszami; także wiersze urzędu dzielnicy Praga-Południe "
                  "z pustym lub błędnym identyfikatorem jednostki oraz sprawy z listy błędów rejestru "
                  "sprawdzonych w ULDK (UNIT_FIXES)",
        "extract_version": EXTRACT_VERSION,
        "parsed_count": len(sel.kept),
        "cases": sel.cases,
        "office_rows_not_kept": dict(sorted(sel.not_kept_office_units.items())),
        "signal_cases_not_kept": sel.signal_cases,
        "sha256": sha,
        "size": len(data),
        "lines": lines,
    }
    _write_atomic(csv_path, data)
    _write_atomic(meta_path, _dumps(sidecar))
    log(f"rwdz: {file.file_id}: wrote extract ({len(sel.kept)} of {sel.rows_total} rows, {sel.cases} cases)")
    return True, sidecar


@dataclass
class KeptRow:
    fields: list[str]
    line: int            # start line in the ORIGINAL file (1 = header)
    extract_line: int    # start line in the extract
    reason: str | None   # match reason when kept by the district-office rule


def read_extract(file: RwdzFile, raw_dir: Path) -> tuple[dict, list[KeptRow], Selection]:
    """Parse a committed extract + sidecar → ``(sidecar, rows, selection)``.

    Raises :class:`RwdzFormatError` when the extract was edited (SHA-256 mismatch), its header
    drifted, or the sidecar's line map does not fit the extract.
    """
    csv_path, meta_path = raw_dir / f"{file.file_id}.csv", raw_dir / f"{file.file_id}.meta.json"
    sidecar = _load_json(meta_path)
    if not sidecar:
        raise FileNotFoundError(meta_path)
    data = csv_path.read_bytes()
    if _sha256_bytes(data) != sidecar.get("sha256"):
        raise RwdzFormatError(f"{csv_path}: SHA-256 wyciągu nie zgadza się z {meta_path.name} – plik zmieniono ręcznie?")
    layout = LAYOUTS[file.layout]
    sel = select_cases(_file_opener(csv_path), layout, str(csv_path))
    lines = sidecar.get("lines") or []
    physical = sum(r.n_lines for r in sel.kept)
    if len(lines) != physical or len(sel.kept) != sidecar.get("parsed_count"):
        raise RwdzFormatError(f"{meta_path}: mapa linii ({len(lines)}) nie pasuje do wyciągu ({physical} linii)")
    rows = [KeptRow(rec.fields, lines[rec.line - 2], rec.line, sel.reasons.get(rec.line)) for rec in sel.kept]
    return sidecar, rows, sel


# =========================================================================== download


def _http_date_to_iso(value: str | None) -> str | None:
    if not value:
        return None
    try:
        when = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    if when is None:
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=_dt.UTC)
    return when.astimezone(_dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _iso_to_http_date(value: str | None) -> str | None:
    if not value:
        return None
    try:
        when = _dt.datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=_dt.UTC)
    except ValueError:
        return None
    return format_datetime(when, usegmt=True)


def _now_iso() -> str:
    return _dt.datetime.now(_dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _mtime_iso(path: Path) -> str:
    return _dt.datetime.fromtimestamp(path.stat().st_mtime, _dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class Fetch:
    status: str                     # downloaded | not-modified | error
    state: dict = field(default_factory=dict)   # HTTP metadata of the local ZIP after the request
    error: str | None = None


def fetch_zip(file: RwdzFile, zip_path: Path, session: requests.Session, *, validators: Mapping[str, Any] | None,
              adopt: bool = False, log: Callable[[str], None] = print) -> Fetch:
    """Conditional GET of one archive, streamed to ``zip_path`` (temp file + ``os.replace``).

    ``validators`` = previous ``{etag, last_modified}``; ``adopt`` = a ZIP is already on disk but we
    hold no validators for it (e.g. copied by hand): ``If-Modified-Since`` = its mtime, and on 304
    the copy is adopted (its ETag from the response, Last-Modified from a HEAD request).
    """
    headers: dict[str, str] = {}
    if adopt and zip_path.is_file():
        headers["If-Modified-Since"] = format_datetime(
            _dt.datetime.fromtimestamp(zip_path.stat().st_mtime, _dt.UTC), usegmt=True)
    elif validators:
        if validators.get("etag"):
            headers["If-None-Match"] = validators["etag"]
        if http_date := _iso_to_http_date(validators.get("last_modified")):
            headers["If-Modified-Since"] = http_date
    try:
        with session.get(file.url, headers=headers, stream=True, timeout=(15, 120)) as resp:
            if resp.status_code == 304:
                state = dict(validators or {})
                if adopt:
                    lm = _http_date_to_iso(resp.headers.get("Last-Modified"))
                    if lm is None:
                        with session.head(file.url, timeout=(15, 60)) as head:
                            lm = _http_date_to_iso(head.headers.get("Last-Modified"))
                    state = {"url": file.url, "etag": resp.headers.get("ETag"), "last_modified": lm,
                             "size": zip_path.stat().st_size, "sha256_zip": _sha256_file(zip_path),
                             "downloaded_at": _mtime_iso(zip_path)}
                    log(f"rwdz: {file.zip_name}: local copy is current (304) – adopted")
                elif resp.headers.get("ETag"):
                    state["etag"] = resp.headers["ETag"]
                return Fetch("not-modified", state)
            if resp.status_code != 200:
                return Fetch("error", error=f"HTTP {resp.status_code}")
            expected = resp.headers.get("Content-Length")
            zip_path.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp = tempfile.mkstemp(prefix=f".{zip_path.name}.", suffix=".part", dir=zip_path.parent)
            h, size = hashlib.sha256(), 0
            try:
                with os.fdopen(fd, "wb") as fh:
                    for chunk in resp.iter_content(chunk_size=1 << 20):
                        fh.write(chunk)
                        h.update(chunk)
                        size += len(chunk)
                if expected and expected.isdigit() and int(expected) != size:
                    raise OSError(f"niepełne pobranie ({size} z {expected} B)")
                if not zipfile.is_zipfile(tmp):
                    raise OSError("pobrany plik nie jest archiwum ZIP")
                with zipfile.ZipFile(tmp) as zf:
                    _zip_member(zf)
                os.chmod(tmp, 0o644)
                os.replace(tmp, zip_path)
            except BaseException:
                Path(tmp).unlink(missing_ok=True)
                raise
            state = {"url": file.url, "etag": resp.headers.get("ETag"),
                     "last_modified": _http_date_to_iso(resp.headers.get("Last-Modified")),
                     "size": size, "sha256_zip": h.hexdigest(), "downloaded_at": _now_iso()}
            log(f"rwdz: {file.zip_name}: downloaded {size / 1e6:.1f} MB")
            return Fetch("downloaded", state)
    except (requests.RequestException, OSError, RwdzFormatError, zipfile.BadZipFile) as exc:
        return Fetch("error", error=f"{type(exc).__name__}: {exc}")


# =========================================================================== record building


def issuer_of(organ: str) -> str:
    """``district`` | ``city`` | ``voivode`` | ``other`` from ``nazwa_organu``."""
    f = collapse_ws(fold(organ))
    if _DISTRICT_OFFICE_RE.search(f):
        return "district"
    if _CITY_RE.fullmatch(f):
        return "city"
    if f.startswith("wojewoda mazowiecki"):
        return "voivode"
    return "other"


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", fold(text)).strip("-")


def record_id(kind: str, register_id: str) -> str | None:
    """``pb-st-mz-pa-2026-29594`` from ``ST-MZ-PA/WNIOSEK/29594/2026`` (type word dropped, year first);
    a register number of another shape is slugged whole; None when it is empty."""
    m = _REGISTER_ID_RE.match(collapse_ws(register_id).replace(" ", ""))
    if m:
        return f"{kind}-{_slug(m['prefix'])}-{m['year']}-{m['seq']}"
    slug = _slug(register_id)
    return f"{kind}-{slug}" if slug else None


def parse_register_date(value: str) -> str | None:
    """``2026-10-14 00:00:00`` → ``2026-10-14`` (None if empty or invalid)."""
    m = _DATE_RE.fullmatch(value.strip())
    if not m:
        return None
    try:
        return _dt.date(int(m[1]), int(m[2]), int(m[3])).isoformat()
    except ValueError:
        return None


def parse_cubature(value: str) -> tuple[float | int | None, list[str]]:
    """``kubatura`` → m³ (int when integral); ``2.03804e+06`` is accepted but flagged as rounded;
    the placeholder values 0 and 1 mean "not given"."""
    s = value.strip().replace(",", ".").replace(" ", "")
    if not s:
        return None, []
    try:
        v = float(s)
    except ValueError:
        return None, [f"nie rozpoznano kubatury („{value.strip()}”)"]
    if not math.isfinite(v) or v <= 1:   # offices type "1" (or 0) when the cubature does not apply
        return None, []
    notes = [f"kubatura zapisana w rejestrze w zaokrągleniu („{value.strip()}”)"] if "e" in s.lower() else []
    return (int(v) if v.is_integer() else round(v, 2)), notes


_HOUSE_RE = re.compile(r"^(\d+[A-Za-z]?(?:\s*/\s*\d+[A-Za-z]?)?)")


def _house_numbers(text: str) -> list[str]:
    """``65,67,69,73C`` → 65, 67, 69, 73C; ``1 i 1a`` → 1, 1a; ``75 C`` → 75C; ``28/30`` stays."""
    out: list[str] = []
    for piece in re.split(r"\s*(?:,|;|\bi\b|\boraz\b)\s*", text):
        m = _HOUSE_RE.match(piece.strip())
        if m:
            num = re.sub(r"\s+", "", m.group(1))
            if num not in out:
                out.append(num)
    return out


def _glue_letters(nr: str) -> str:
    """``75 C`` → ``75C`` (as ``normalize`` does; "i"/"o"/"w"/"z" are words, not building letters)."""
    return re.sub(r"(?<=\d)\s+([A-HJ-NP-VX-Ya-hj-np-vx-y])(?![\w.])", r"\1", collapse_ws(nr))


def _matching_street(name: str) -> str:
    """Street as the other datasets write it: no quotes; for "Aleja X Y" names (GUNB writes the full
    name in ``ulica``) without "Aleja" and without leading first names ("Aleja Jerzego Waszyngtona"
    → "Waszyngtona", "Aleja Stanów Zjednoczonych" → "Stanów Zjednoczonych")."""
    s = collapse_ws(re.sub(r"[\"„”“«»]", " ", name))
    m = re.match(r"(?i)^(?:aleja|al\.)\s+(.+)$", s)
    if m:
        s = m.group(1)
        key = street_key(s)
        words = s.split()
        while len(words) > 1 and street_key(" ".join(words[1:])) == key:
            words.pop(0)
        s = " ".join(words)
    return s


#: Register spellings that would not match the other datasets (folded street → canonical street).
STREET_FIXES = {"jezioranskiego": "Nowaka-Jeziorańskiego"}
_UNIT_ID_RE = re.compile(r"\d{6}_\d")   # a TERYT cadastral unit id ("146507_8")


def compose_address(cecha: str, ulica_dalej: str, ulica: str, nr_domu: str,
                    warnings: list[str] | None = None) -> dict[str, Any]:
    """Address from the register's TERYT-style columns.

    ``display`` reads naturally – first names / title before the surname, house number last, no
    "ul." ("Andrzeja Czapskiego 3", "gen. Augusta Emila Fieldorfa "Nila" 10", "Aleja Jerzego
    Waszyngtona 12"); ``street`` is the matching form the other datasets use ("Czapskiego"), in the
    one spelling of ``normalize.STREET_CANONICAL`` ("Fieldorfa"). A cadastral unit id typed as the house
    number ("146507_8") is dropped with a warning.
    """
    cecha_c, dalej, name = collapse_ws(cecha), collapse_ws(ulica_dalej), collapse_ws(ulica)
    nr = _glue_letters(nr_domu)
    if _UNIT_ID_RE.fullmatch(nr):
        if warnings is not None:
            warnings.append(f"w rejestrze zamiast numeru budynku wpisano kod jednostki ewidencyjnej („{nr}”) – "
                            "pominięto")
        nr = ""
    raw = collapse_ws(f"{cecha_c} {dalej} {name} {collapse_ws(nr_domu)}")
    out: dict[str, Any] = {"raw": raw, "street": None, "number": None, "display": "", "parts": [],
                           "approximate": False}
    if not name:   # a house number without a street says nothing
        return out
    prefix = ""
    kind = fold(cecha_c).rstrip(". ")
    if kind and kind not in ("ul", "inne") and not fold(f"{dalej} {name}".strip()).startswith(kind):
        prefix = cecha_c
    out["display"] = collapse_ws(f"{prefix} {dalej} {name} {nr}")
    street = fix_street_typos(_matching_street(name))
    fixed = STREET_FIXES.get(fold(street))
    if fixed:
        if warnings is not None:
            warnings.append(f"nazwę ulicy z rejestru („{collapse_ws(f'{dalej} {name}')}”) dopasowano do „{fixed}”")
        street = fixed
    street = canonical_street(street)
    numbers = _house_numbers(nr)
    out["street"] = street
    out["number"] = numbers[0] if numbers else None
    out["parts"] = [{"street": street, "number": out["number"], "numbers": numbers}]
    return out


def _parcel(unit: str, obreb: str, number: str) -> dict[str, Any]:
    """Parcel in the Record format; ``obreb`` is written like in the district files: ``3-06-05`` (zone
    digit of the unit + the 4-digit code), ``5-06-11`` for a Śródmieście parcel; as printed when the
    code is not 4 digits, the unit is outside Warsaw, or a 146507_8 code is no Praga-Południe precinct
    (``normalize.PP_OBREBY``: register errors such as 0002, 1406 or 0516)."""
    obreb4 = obreb.zfill(4) if obreb.isdigit() and len(obreb) < 4 else obreb
    zone = UNIT_ZONES.get(unit) if re.fullmatch(r"\d{4}", obreb4) else None
    if unit == TERYT_PRAGA_POLUDNIE and not is_pp_obreb(obreb4):
        zone = None
    display = f"{zone}-{obreb4[:2]}-{obreb4[2:]}" if zone else obreb4
    return {"number": number, "obreb": display, "partial": False, "id": f"{unit}.{obreb4}.{number}"}


def _unit_note(reason: str, unit: str, has_parcel: bool) -> str:
    if reason == "listed":
        where = f" ({WARSAW_UNITS[unit]})" if unit in WARSAW_UNITS else ""
        return (f"identyfikator jednostki ewidencyjnej w rejestrze „{unit}”{where} potraktowano jako 146507_8 "
                "(Praga-Południe) – według ewidencji gruntów (ULDK) ta działka lub obręb istnieje tylko na "
                "Pradze-Południe; błąd w rejestrze")
    if reason == "empty":
        if not has_parcel:
            return ("sprawa urzędu dzielnicy Praga-Południe bez oznaczenia działki w rejestrze – przyjęto, "
                    "że dotyczy Pragi-Południe")
        return ("brak identyfikatora jednostki ewidencyjnej w rejestrze – przyjęto 146507_8 (Praga-Południe; "
                "sprawa urzędu dzielnicy)")
    where = f" ({WARSAW_UNITS[unit]})" if unit in WARSAW_UNITS else ""
    return (f"identyfikator jednostki ewidencyjnej w rejestrze „{unit}”{where} potraktowano jako 146507_8 "
            "(Praga-Południe) – sprawa urzędu dzielnicy, prawdopodobna literówka")


def _cell(value: str) -> str:
    return redact_persons(tidy_cell(value))


def _case_record(file: RwdzFile, rows: list[KeptRow]) -> dict[str, Any]:
    """One Record from all register rows of one case (rows in file order)."""
    layout = LAYOUTS[file.layout]
    header = layout.header
    first = rows[0].fields
    warnings: list[str] = []

    def col(name: str) -> str:
        return first[layout.index(name)]

    # --- case-level columns must agree between the rows of a case
    for i, name in enumerate(header):
        if name in layout.parcel_cols or name in layout.designer_cols:
            continue
        if len({r.fields[i] for r in rows}) > 1:
            warnings.append(f"wiersze tej sprawy w rejestrze różnią się w kolumnie „{name}” – przyjęto pierwszy")

    register_id = collapse_ws(col(layout.case))
    case_sign = collapse_ws(col(layout.case_sign)) or None
    number = collapse_ws(col(layout.number))
    if not number:
        warnings.append("brak numeru decyzji w rejestrze" if file.kind == "pb" else "brak numeru zgłoszenia w rejestrze")
    if file.kind == "pb" and re.search(r"/O$", number):
        warnings.append("numer decyzji kończy się na „/O” – w numeracji urzędów m.st. Warszawy oznacza to zwykle "
                        "odmowę; rejestr GUNB nie podaje rodzaju rozstrzygnięcia")

    date_raw = collapse_ws(col(layout.date))
    date = parse_register_date(date_raw)
    if date is None:
        warnings.append(f"nie rozpoznano daty („{date_raw}”)" if date_raw else "brak daty w rejestrze")
    filed_raw = collapse_ws(col(layout.filed))
    filed = parse_register_date(filed_raw)
    if filed and date and file.kind == "pb" and filed > date:
        warnings.append("data wpływu wniosku jest późniejsza niż data decyzji")

    if layout.investor:
        investor = clean_applicant(col(layout.investor))
        applicant: str | None = investor or "osoba fizyczna"
        a_type = applicant_type(investor) if investor else "person"
    else:
        applicant, a_type = None, "unknown"

    investment = redact_persons(collapse_ws(col("nazwa_zam_budowlanego")))
    if not investment:
        warnings.append("brak opisu inwestycji")

    address = compose_address(col("cecha"), col("ulica_dalej"), col("ulica"), col("nr_domu"), warnings)

    # --- parcels: one per row (unit corrected for district-office rows with a broken unit id)
    i_unit, i_obreb, i_nr = layout.index(layout.unit), layout.index("obreb_numer"), layout.index("numer_dzialki")
    parcels: list[dict[str, Any]] = []
    seen: set[str] = set()
    raw_parcels: list[str] = []
    outside: Counter = Counter()
    for r in rows:
        unit_raw, obreb, nr = r.fields[i_unit].strip(), r.fields[i_obreb].strip(), re.sub(r"\s+", "", r.fields[i_nr])
        raw_parcels.append(collapse_ws(f"{unit_raw} {obreb} {nr}"))
        unit = TERYT_PRAGA_POLUDNIE if r.reason else unit_raw
        if r.reason:
            warnings.append(_unit_note(r.reason, unit_raw, bool(obreb and nr)))
        if not (unit and obreb and nr):
            warnings.append(f"wiersz rejestru (linia {r.line}) bez pełnego oznaczenia działki"
                            if obreb or nr else f"wiersz rejestru (linia {r.line}) bez oznaczenia działki")
            continue
        p = _parcel(unit, obreb, nr)
        if not _PARCEL_ID_RE.match(p["id"]):
            warnings.append(f"nietypowe oznaczenie działki w rejestrze („{p['id']}”)")
        elif unit == TERYT_PRAGA_POLUDNIE and not is_pp_obreb(p["id"].split(".")[1]):
            warnings.append(f"obręb „{obreb}” nie występuje na Pradze-Południe (nie ma go w ewidencji gruntów "
                            "dzielnicy) – możliwy błąd w rejestrze")
        if p["id"] in seen:
            continue
        seen.add(p["id"])
        parcels.append(p)
        if unit != TERYT_PRAGA_POLUDNIE:
            outside[unit] += 1
    for unit, n in sorted(outside.items()):
        where = WARSAW_UNITS.get(unit, "inna jednostka")
        warnings.append(f"sprawa obejmuje też działki spoza Pragi-Południe – jednostka ewidencyjna {unit} "
                        f"({where}): {n}")

    # --- permit attributes
    scope_label = collapse_ws(col(layout.scope))
    scope = _SCOPE_BY_REGISTER.get(collapse_ws(fold(scope_label))) if scope_label else None
    if scope_label and scope is None:
        warnings.append(f"nieznany zakres robót w rejestrze („{scope_label}”)")
    category = collapse_ws(col("kategoria")).upper() or None
    if category and (not _ROMAN_RE.match(category) or category not in CATEGORY_LABELS):
        warnings.append(f"nieznana kategoria obiektu w rejestrze („{category}”)")
        category = None
    single_family: bool | None = None
    if layout.single_family:
        sf = fold(col(layout.single_family))
        single_family = None if not sf.strip() else sf.startswith("budynek mieszkalny jednorodzinny")
    cubature, notes = parse_cubature(col("kubatura"))
    warnings += notes
    state = (collapse_ws(col(layout.state)) or None) if layout.state else None

    # --- tags: free text first; category / single-family flag only when the text names no function
    text_tags = classify(investment)
    tags = set(text_tags)
    if not any(TAGS[t]["group"] == "funkcja" for t in text_tags):
        if category in CATEGORY_TAGS:
            tags.add(CATEGORY_TAGS[category])
        elif single_family:
            tags.add("jednorodzinny")
    if scope in SCOPE_TAGS:
        tags.add(SCOPE_TAGS[scope])
    # a description that merely starts with "budynek …" reads as a new build to classify(); the
    # register's scope says what really happens (e.g. "rozbiórka" of "budynki produkcyjne, …")
    if scope not in (None, "budowa") and not _BUILD_WORD_RE.search(fold(investment)):
        tags.discard("nowa-budowa")

    # --- source row as in the register (designer columns removed, parcels joined)
    raw: list[list[str]] = []
    for i, name in enumerate(header):
        if name in layout.designer_cols:
            continue
        if name in layout.parcel_cols:
            values = [_cell(r.fields[i]) for r in rows]
            raw.append([name, " | ".join(values) if any(values) else ""])
        else:
            values = list(dict.fromkeys(_cell(r.fields[i]) for r in rows))
            raw.append([name, " | ".join(values)])

    rid = record_id(file.kind, register_id)
    if rid is None:
        rid = f"{file.kind}-f{file.file_id}-r{rows[0].line}"
        warnings.append("brak numeru sprawy w rejestrze – identyfikator nadany z pozycji w pliku")

    return {   # key order of records.json (DATA_MODEL "Record key order")
        "id": rid,
        "kind": file.kind,
        "procedure": file.kind,
        "dataset": DATASET,
        "issuer": issuer_of(col("nazwa_organu")),
        "outcome": None,
        "number": number,
        "date": date,
        "date_raw": date_raw,
        "filed_date": filed,
        "period": date[:7] if date else None,
        "applicant": applicant,
        "applicant_type": a_type,
        "investment": investment,
        "address": address,
        "parcels": parcels,
        "parcels_raw": " | ".join(raw_parcels),
        "tags": [t for t in TAGS if t in tags],
        "permit": {
            "register_id": register_id,
            "case_sign": case_sign,
            "scope": scope,
            "scope_label": scope_label or None,
            "category": category,
            "category_label": CATEGORY_LABELS.get(category) if category else None,
            "single_family": single_family,
            "cubature": cubature,
            "state": state,
        },
        "area": None,
        "geo": None,
        "sources": [{
            "file_id": file.file_id,
            "page_id": PAGE_ID,
            "sheet": None,
            "row": rows[0].line,
            "rows": [r.line for r in rows],
            "extract_rows": [r.extract_line for r in rows],
            "raw": raw,
        }],
        "related": [],
        "warnings": list(dict.fromkeys(warnings)),
    }


def build_records(file: RwdzFile, rows: Sequence[KeptRow]) -> list[dict[str, Any]]:
    """Group register rows by case (GUNB system number) → one Record per case, file order."""
    layout = LAYOUTS[file.layout]
    i_case = layout.index(layout.case)
    groups: dict[str, list[KeptRow]] = {}
    for r in rows:
        groups.setdefault(r.fields[i_case].strip(), []).append(r)
    return [_case_record(file, g) for g in groups.values()]


def _natural_key(s: str) -> list[Any]:
    return [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", s or "")]


def sort_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Newest first (date, period, id in natural order) – the same order as ``build.sort_records``."""
    return sorted(records, key=lambda r: (r.get("date") or "", r.get("period") or "", _natural_key(r["id"])),
                  reverse=True)


def resolve_collisions(records: list[dict[str, Any]]) -> int:
    """Same id twice: the same case in two files is merged (sources, parcels); different cases whose
    register numbers slug to the same id get ``-2``, ``-3``… and a warning. Returns the number of
    renamed records (0 on the real data)."""
    by_id: dict[str, list[dict[str, Any]]] = {}
    for r in records:
        by_id.setdefault(r["id"], []).append(r)
    renamed = 0
    drop: set[int] = set()
    for rid, group in by_id.items():
        if len(group) < 2:
            continue
        variants: list[dict[str, Any]] = []
        for r in group:
            same = next((v for v in variants if v["permit"]["register_id"] == r["permit"]["register_id"]), None)
            if same is None:
                variants.append(r)
                continue
            same["sources"].extend(r["sources"])
            known = {p["id"] for p in same["parcels"]}
            same["parcels"].extend(p for p in r["parcels"] if p["id"] not in known)
            same["warnings"].append("sprawa występuje w kilku plikach rejestru")
            drop.add(id(r))
        for i, v in enumerate(variants[1:], 2):
            v["id"] = f"{rid}-{i}"
            renamed += 1
        if len(variants) > 1:
            for v in variants:
                v["warnings"].append(f"numery spraw w rejestrze dają ten sam identyfikator – rozdzielono na "
                                     f"{len(variants)} pozycje")
    records[:] = [r for r in records if id(r) not in drop]
    return renamed


# =========================================================================== orchestration


def _file_entry(file: RwdzFile, sidecar: Mapping[str, Any] | None, record_ids: list[str],
                warnings: list[str], error: str | None) -> dict[str, Any]:
    s = sidecar or {}
    entry = {
        "file_id": file.file_id,
        "source": DATASET,
        "url": file.url,
        "dataset_url": DATASET_URL,
        "licence": LICENCE,
        "filename": file.zip_name,
        "zip_member": s.get("zip_member"),
        "ext": "csv",
        "category": file.kind,
        "period": None,
        "page_ids": [PAGE_ID],
        "local_path": f"{LOCAL_DIR}/{file.file_id}.csv" if sidecar else None,
        "archive_path": f"{ARCHIVE_DIR}/{file.file_id}.csv" if sidecar else None,
        "sha256": s.get("sha256"),
        "size": s.get("size"),
        "etag": s.get("etag"),
        "last_modified": s.get("last_modified"),
        "sha256_zip": s.get("sha256_zip"),
        "size_zip": s.get("size_zip"),
        "downloaded_at": s.get("downloaded_at"),
        "rows_total": s.get("rows_total"),
        "parsed_count": s.get("parsed_count") if sidecar else None,
        "record_ids": record_ids,
        "kind_detected": file.kind,
        "layout": f"rwdz-{file.layout}",
        "history": [],
        "warnings": warnings,
    }
    if error:
        entry["error"] = error
    return entry


def page_entry(files: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """The ``rwdz`` pseudo-page of ``sources.json`` (one block per archive)."""
    return {
        "page_id": PAGE_ID,
        "source": DATASET,
        "url": DOWNLOAD_PAGE_URL,
        "title": "Rejestr wniosków, decyzji i zgłoszeń (GUNB)",
        "period": None,
        "published_at": None,
        "summary": "Pliki do pobrania GUNB, aktualizowane co noc (licencja CC0 1.0). Wyciąg: sprawy z działkami "
                   "na Pradze-Południe.",
        "index_page": None,
        "blocks": [{
            "text": f"{file.title} ({file.zip_name})",
            "category": file.kind,
            "declared_count": None,
            "file_ids": [file.file_id],
            "parsed_count": next((f.get("parsed_count") for f in files if f["file_id"] == file.file_id), None),
            "count_mismatch": False,
        } for file in FILES],
        "warnings": [],
    }


_SNAPSHOT_KEYS = ("url", "etag", "last_modified", "size", "sha256_zip", "downloaded_at")


def _snapshot_of(sidecar: Mapping[str, Any]) -> dict[str, Any]:
    """HTTP metadata of the ZIP a committed extract was taken from (the ``rwdz.json`` entry)."""
    return {"url": sidecar.get("url"), "etag": sidecar.get("etag"), "last_modified": sidecar.get("last_modified"),
            "size": sidecar.get("size_zip"), "sha256_zip": sidecar.get("sha256_zip"),
            "downloaded_at": sidecar.get("downloaded_at")}


def _ensure_extract(file: RwdzFile, zips: Path, raw_dir: Path, tracked: Mapping[str, Any], local: dict, *,
                    online: bool, refresh: bool, session: requests.Session | None,
                    log: Callable[[str], None]) -> tuple[str, list[str], str | None]:
    """Bring ``raw_dir/<file_id>.csv`` (+ sidecar) up to date; returns ``(status, file warnings, error)``.

    Request mode: ``refresh`` → unconditional; a known local ZIP → its validators (``local.json``);
    a ZIP on disk we hold no validators for → adopt (``If-Modified-Since`` = its mtime); otherwise the
    validators of the committed snapshot (``rwdz.json``) – a 304 then means the committed extract
    is current and no ZIP is needed (CI).
    """
    zip_path = zips / file.zip_name
    meta_path, csv_path = raw_dir / f"{file.file_id}.meta.json", raw_dir / f"{file.file_id}.csv"
    sidecar = _load_json(meta_path) if meta_path.is_file() else {}
    present = bool(sidecar) and csv_path.is_file()
    current = present and sidecar.get("extract_version") == EXTRACT_VERSION
    loc = local.get(file.file_id)
    if loc and not (zip_path.is_file() and zip_path.stat().st_size == loc.get("size")):
        loc = None
    warnings: list[str] = []
    outdated_note = "wyciąg wykonano starszą wersją reguł – zostanie odświeżony przy następnym pobraniu pliku"

    def from_zip(state: Mapping[str, Any]) -> None:
        extract_csv(file, zip_path, raw_dir, state, log)
        local[file.file_id] = {**{k: state.get(k) for k in _SNAPSHOT_KEYS},
                               "extract_sha256": _sha256_file(csv_path), "extract_version": EXTRACT_VERSION}

    def extracted_from(state: Mapping[str, Any]) -> bool:
        return (current and state.get("extract_version") == EXTRACT_VERSION
                and state.get("extract_sha256") == sidecar.get("sha256"))

    if not online:
        if current:
            return "offline", warnings, None
        if loc:   # a missing/outdated extract, but a known local ZIP: re-make it without the network
            from_zip(loc)
            return "offline", warnings, None
        if present:
            return "offline", [outdated_note], None
        return "missing", warnings, "brak wyciągu z rejestru GUNB (uruchom budowanie z dostępem do sieci)"

    assert session is not None
    if refresh:
        mode, validators = "plain", None
    elif loc:
        mode, validators = "local", loc
    elif zip_path.is_file():
        mode, validators = "adopt", None
    elif current:
        mode, validators = "snapshot", tracked.get(file.file_id) or _snapshot_of(sidecar)
    else:
        mode, validators = "plain", None
    fetched = fetch_zip(file, zip_path, session, validators=validators, adopt=mode == "adopt", log=log)

    if fetched.status == "downloaded":
        from_zip(fetched.state)
        return "downloaded", warnings, None
    if fetched.status == "not-modified":
        if mode in ("local", "adopt"):
            state = {**(loc or {}), **fetched.state}
            local[file.file_id] = state
            if not extracted_from(state):
                from_zip(state)
        return "not-modified", warnings, None   # mode "snapshot": the committed extract is current

    log(f"rwdz: {file.zip_name}: download failed ({fetched.error})")
    if loc and not current:
        from_zip(loc)
        return "stale", [f"nie udało się pobrać pliku z GUNB ({fetched.error}) – użyto lokalnej kopii archiwum"], None
    if present:
        warnings.append(f"nie udało się pobrać pliku z GUNB ({fetched.error}) – użyto zapisanego wyciągu")
        if not current:
            warnings.append(outdated_note)
        return "stale", warnings, None
    return "error", warnings, fetched.error


def run_rwdz(cache_dir: str | Path = "data/cache", raw_dir: str | Path = "data/raw/rwdz", online: bool = True,
             refresh: bool = False, session: requests.Session | None = None,
             log: Callable[[str], None] = print) -> dict[str, Any]:
    """Download (conditionally), extract and normalise the three RWDZ archives.

    Returns ``{"records": [Record…] (newest first), "files": [files[] entries], "page": {…},
    "stats": {…}}``. Raises :class:`RwdzFormatError` on format drift (header, malformed rows of the
    district, edited extracts) – before anything is written.

    * ``cache_dir`` – ``rwdz.json`` (tracked snapshot metadata) and ``rwdz/`` (ZIPs + ``local.json``);
    * ``raw_dir`` – committed extracts ``<file_id>.csv`` + ``<file_id>.meta.json``;
    * ``online=False`` – committed extracts only (no network);
    * ``refresh`` – unconditional downloads.
    """
    cache_dir, raw_dir = Path(cache_dir), Path(raw_dir)
    zips = cache_dir / "rwdz"
    tracked_path, local_path = cache_dir / "rwdz.json", zips / "local.json"
    tracked = dict(_load_json(tracked_path).get("files", {}))
    local = dict(_load_json(local_path).get("files", {})) if local_path.is_file() else {}
    if online and session is None:
        session = make_session(min_delay=1.0)

    records: list[dict[str, Any]] = []
    files: list[dict[str, Any]] = []
    stats: dict[str, Any] = {"files": {}}
    for file in FILES:
        status, warnings, error = _ensure_extract(file, zips, raw_dir, tracked, local, online=online,
                                                  refresh=refresh, session=session, log=log)
        sidecar: dict[str, Any] | None = None
        rows: list[KeptRow] = []
        if error is None:
            sidecar, rows, _sel = read_extract(file, raw_dir)
            tracked[file.file_id] = _snapshot_of(sidecar)
        recs = build_records(file, rows)
        records.extend(recs)
        files.append(_file_entry(file, sidecar, [], warnings, error))
        stats["files"][file.file_id] = {
            "status": status, "error": error, "last_modified": (sidecar or {}).get("last_modified"),
            "rows_total": (sidecar or {}).get("rows_total"), "rows_kept": len(rows), "cases": len(recs),
            "rows_kept_by_office_rule": dict(sorted(Counter(r.reason for r in rows if r.reason).items())),
            "office_rows_not_kept": (sidecar or {}).get("office_rows_not_kept", {}),
            "signal_cases_not_kept": (sidecar or {}).get("signal_cases_not_kept", []),
        }
    # rwdz.json mirrors the snapshots of the committed extracts: it changes only when they do
    _write_atomic(tracked_path, _dumps({"files": dict(sorted(tracked.items()))}))
    if local:
        _write_atomic(local_path, _dumps({"files": dict(sorted(local.items()))}))

    renamed = resolve_collisions(records)
    records = sort_records(records)
    stats.update(_summary(records))
    stats["id_collisions"] = renamed
    for f in files:   # natural order = order of the rows in the file
        rows_of = {r["id"]: min(s["row"] for s in r["sources"] if s["file_id"] == f["file_id"])
                   for r in records if any(s["file_id"] == f["file_id"] for s in r["sources"])}
        f["record_ids"] = sorted(rows_of, key=rows_of.__getitem__)
    return {"records": records, "files": files, "page": page_entry(files), "stats": stats}


def _summary(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    def count(key: Callable[[Mapping[str, Any]], Any]) -> dict[str, int]:
        c = Counter(key(r) for r in records)
        return {str(k): v for k, v in sorted(c.items(), key=lambda kv: str(kv[0]))}

    parcels = {p["id"] for r in records for p in r["parcels"]}
    return {
        "records": len(records),
        "by_kind": count(lambda r: r["kind"]),
        "by_kind_year": count(lambda r: f"{r['kind']} {(r['date'] or '????')[:4]}"),
        "issuers": count(lambda r: r["issuer"]),
        "scopes": count(lambda r: f"{r['kind']} {r['permit']['scope']}"),
        "categories": count(lambda r: r["permit"]["category"]),
        "applicant_types": count(lambda r: f"{r['kind']} {r['applicant_type']}"),
        "parcels_unique": len(parcels),
        "records_without_parcels": sum(1 for r in records if not r["parcels"]),
        "records_with_warnings": sum(1 for r in records if r["warnings"]),
    }


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="GUNB RWDZ → Praga-Południe permits (summary on stdout)")
    ap.add_argument("--offline", action="store_true", help="committed extracts only, no network")
    ap.add_argument("--refresh", action="store_true", help="unconditional downloads")
    ap.add_argument("--root", default=".", help="project root (default: current directory)")
    args = ap.parse_args(argv)
    root = Path(args.root)
    result = run_rwdz(root / "data" / "cache", root / LOCAL_DIR, online=not args.offline, refresh=args.refresh)
    json.dump(result["stats"], sys.stdout, ensure_ascii=False, indent=1)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
