"""Warsaw's 18 districts – the registry behind the city-wide build (docs/plans/all-districts.md).

The pipeline builds **one district at a time**. :func:`use` makes a district the current one for the code
that runs inside it (a context variable); the modules ask :func:`current` for the cadastral unit, the
names and the patterns they used to hard-code for Praga-Południe. Without :func:`use` the current district
is Praga-Południe, so every existing entry point (``make data``, the tests) behaves exactly as before.

Praga-Południe is the *legacy* district: its record ids carry no district code (``wz-2026-15``,
``wz-am-2026-95``) because they are permalinks published before the other districts existed. Every other
district namespaces its ids with a fixed three-letter code (``wz-bem-2026-1``, ``wz-am-bie-2025-33``).

Precincts (obręby) → cadastral unit: Warsaw writes precincts as ``Z-SS-OO`` (zone, section, number) while
ULDK ids drop the zone (``146502_8.1110.5/40`` is Bemowo's ``6-11-10``), and a zone is shared by up to
three districts. ``data/warsaw_obreby.json`` (generated from the GUNB register by
``scripts/warsaw_obreby.py``) tells which unit owns ``(zone, SSOO)``.
"""

from __future__ import annotations

import contextlib
import contextvars
import json
import re
from collections.abc import Iterator
from dataclasses import dataclass, field
from functools import cache
from pathlib import Path

__all__ = [
    "DISTRICTS",
    "District",
    "LEGACY_SLUG",
    "by_code",
    "by_unit",
    "current",
    "get",
    "precinct_units",
    "unit_for_precinct",
    "use",
]

LEGACY_SLUG = "praga-poludnie"


@dataclass(frozen=True)
class District:
    """One Warsaw district: identity, names in the cases the UI needs, patterns and how its lists are crawled."""

    slug: str
    name: str                 # "Praga-Południe" (nominative, as in "Urząd Dzielnicy Praga-Południe")
    genitive: str             # "Pragi-Południe" ("z Pragi-Południe", "dla Pragi-Południe")
    locative: str             # "na Pradze-Południe" (with its preposition)
    instrumental: str         # "Pragą-Południe" ("poza Pragą-Południe")
    unit: str                 # TERYT cadastral unit, "146507_8"
    code: str                 # record-id namespace; "" for the legacy district
    zones: tuple[str, ...]    # precinct zone digit(s) of the district
    name_re: str              # regex over *folded* text: the district's name in an address cell
    organ_re: str             # regex over folded GUNB "nazwa_organu": the district office
    entry_url: str            # the list page linked from BAiPP's "w serwisach dzielnicowych" box
    strategy: str             # monthly-pages | attachments | own-layout
    pages: tuple[str, ...] = ()        # list pages crawled by the "attachments" strategy
    extensions: tuple[str, ...] = ("xlsx", "zip")   # attachments taken from those pages
    exclude_re: str | None = None      # folded link text + file name of attachments to leave out
    short_precinct_zone: str | None = None   # precincts written without the zone ("07-07" in Wesoła)
    status: str = "enabled"   # enabled | pending (lists not ingested yet; GUNB + BAiPP still are)
    note: str | None = None   # why a district is pending (shown in the UI)
    osm_relation: int | None = None

    @property
    def center(self) -> tuple[float, float]:
        """Approximate centre (lat, lon) – the first map view before the district's outline is known."""
        return CENTERS[self.slug]

    @property
    def legacy(self) -> bool:
        return self.code == ""

    @property
    def terc(self) -> str:
        """``teryt:terc`` of the district in OSM (``146507_8`` → ``1465078``)."""
        return self.unit.replace("_", "")

    @property
    def office(self) -> str:
        return f"Urząd Dzielnicy {self.name} m.st. Warszawy – Wydział Architektury i Budownictwa"

    @property
    def enabled(self) -> bool:
        return self.status == "enabled"

    def id_prefix(self, kind: str) -> str:
        """``wz`` → ``wz-bem`` (``wz`` for the legacy district)."""
        return kind if self.legacy else f"{kind}-{self.code}"

    @property
    def pattern(self) -> re.Pattern[str]:
        return _compiled(self.name_re)

    @property
    def organ_pattern(self) -> re.Pattern[str]:
        return _compiled(self.organ_re)


@cache
def _compiled(rx: str) -> re.Pattern[str]:
    return re.compile(rx)


#: Approximate district centres (lat, lon), read off the map; only the initial map view uses them.
CENTERS: dict[str, tuple[float, float]] = {
    "bemowo": (52.254, 20.91),
    "bialoleka": (52.32, 20.985),
    "bielany": (52.29, 20.94),
    "mokotow": (52.19, 21.03),
    "ochota": (52.212, 20.975),
    "praga-poludnie": (52.2385, 21.095),
    "praga-polnoc": (52.258, 21.035),
    "rembertow": (52.258, 21.16),
    "srodmiescie": (52.232, 21.012),
    "targowek": (52.284, 21.05),
    "ursus": (52.195, 20.885),
    "ursynow": (52.145, 21.045),
    "wawer": (52.2, 21.17),
    "wesola": (52.235, 21.23),
    "wilanow": (52.15, 21.1),
    "wlochy": (52.19, 20.93),
    "wola": (52.236, 20.965),
    "zoliborz": (52.268, 20.985),
}

#: Attachments of the districts that publish their lists as PDF (read by :mod:`pipeline.pdftable`; a few
#: years are xlsx).
_PDF_LISTS = ("pdf", "xlsx")

#: The 18 districts in alphabetical order of their Polish names. Patterns work on folded text
#: (lower case, no diacritics – :func:`pipeline.textutil.fold`); they must not match street names
#: ("Wawerska", "al. Wilanowska", "Targowa", "Wolska" are streets).
DISTRICTS: dict[str, District] = {d.slug: d for d in (
    District("bemowo", "Bemowo", "Bemowa", "na Bemowie", "Bemowem", "146502_8", "bem", ("6",),
             r"\bbemow(?:o|a|ie|em)?\b", r"warszaw\w*\W+bemowo\b",
             "https://bemowo.um.warszawa.pl/jawnosc-procesu-inwestycyjnego", "attachments",
             pages=("https://bemowo.um.warszawa.pl/jawnosc-procesu-inwestycyjnego",)),
    District("bialoleka", "Białołęka", "Białołęki", "na Białołęce", "Białołęką", "146503_8", "bia", ("4",),
             r"\bbialol(?:eka|eki|ece|eke)\b", r"warszaw\w*\W+bialoleka\b",
             "https://bialoleka.um.warszawa.pl/decyzje-architektoniczne", "attachments",
             pages=("https://bialoleka.um.warszawa.pl/warunki-zabudowy-wnioski",
                    "https://bialoleka.um.warszawa.pl/warunki-zabudowy-decyzje",
                    "https://bialoleka.um.warszawa.pl/inwestycje-celu-publicznego-decyzje"),
             extensions=_PDF_LISTS),
    District("bielany", "Bielany", "Bielan", "na Bielanach", "Bielanami", "146504_8", "bie", ("7",),
             r"\bbielan(?:y|ach|ami|om)?\b", r"warszaw\w*\W+bielany\b",
             "https://bielany.um.warszawa.pl/architektura", "attachments",
             pages=("https://bielany.um.warszawa.pl/-/wszczete_postepowania",
                    "https://bielany.um.warszawa.pl/-/warunki_zabudowy",
                    "https://bielany.um.warszawa.pl/-/lokalizacja_inwestycji_celu_publicznego"),
             extensions=_PDF_LISTS),
    District("mokotow", "Mokotów", "Mokotowa", "na Mokotowie", "Mokotowem", "146505_8", "mok", ("1",),
             r"\bmokotow(?:a|ie|em)?\b", r"warszaw\w*\W+mokotow\b",
             "https://mokotow.um.warszawa.pl/wykazy-i-informacje-o-decyzjach", "attachments",
             pages=("https://mokotow.um.warszawa.pl/wykazy-i-informacje-o-decyzjach",
                    "https://mokotow.um.warszawa.pl/-/archiwum-informacje-o-wnioskach-o-wydanie-decyzji-o-warunkach-"
                    "zabudowy-i-zagospodarowania-terenu",
                    "https://mokotow.um.warszawa.pl/-/archiwum-informacje-o-wydanych-decyzjach-o-warunkach-zabudowy-i-"
                    "zagospodarowania-terenu"),
             extensions=_PDF_LISTS),   # 2018–19 registers are old .xls: not read
    District("ochota", "Ochota", "Ochoty", "na Ochocie", "Ochotą", "146506_8", "och", ("2",),
             r"\boch(?:ota|oty|ocie|ote)\b", r"warszaw\w*\W+ochota\b",
             "https://ochota.um.warszawa.pl/warunki-zabudowy", "attachments",
             pages=("https://ochota.um.warszawa.pl/warunki-zabudowy",), extensions=_PDF_LISTS),
    District("praga-poludnie", "Praga-Południe", "Pragi-Południe", "na Pradze-Południe", "Pragą-Południe",
             "146507_8", "", ("3",),
             r"(?:\bdzielnic\w*\s+)?\bprag\w*\s*-?\s*(?:p\s*o\s*l\s*u\s*d\s*n\w*|pld\.?|pd\.?)(?![a-z])",
             r"praga\W*(?:pld|poludnie)",
             "https://pragapld.um.warszawa.pl/informacja-o-wszczetych-postepowaniach-oraz-wydanych-decyzjach-"
             "administracyjnych", "monthly-pages", osm_relation=2544288),
    District("praga-polnoc", "Praga-Północ", "Pragi-Północ", "na Pradze-Północ", "Pragą-Północ", "146508_8", "ppn",
             ("4",), r"(?:\bdzielnic\w*\s+)?\bprag\w*\s*-?\s*(?:p\s*o\s*l\s*n\w*|pn\.?|pln\.?)(?![a-z])",
             r"praga\W*(?:pn|polnoc)\b", "https://pragapn.um.warszawa.pl/-/ogloszenia-2", "attachments",
             pages=("https://pragapn.um.warszawa.pl/-/ogloszenia-2",)),
    District("rembertow", "Rembertów", "Rembertowa", "w Rembertowie", "Rembertowem", "146509_8", "rem", ("3",),
             r"\brembertow(?:a|ie|em)?\b", r"warszaw\w*\W+rembertow\b",
             "https://rembertow.um.warszawa.pl/-/informacja-o-wszczetych-postepowaniach-i-wydanych-decyzjach-"
             "administracyjnych", "attachments",
             pages=("https://rembertow.um.warszawa.pl/-/informacja-o-wszczetych-postepowaniach-i-wydanych-decyzjach-"
                    "administracyjnych",)),
    District("srodmiescie", "Śródmieście", "Śródmieścia", "w Śródmieściu", "Śródmieściem", "146510_8", "srd", ("5",),
             r"\bsrodmiesc(?:ie|ia|iu)\b", r"warszaw\w*\W+srodmiescie\b",
             "https://srodmiescie.um.warszawa.pl/wszczete-postepowania-i-wydane-decyzje", "attachments",
             pages=("https://srodmiescie.um.warszawa.pl/-/wszczete-postepowania",
                    "https://srodmiescie.um.warszawa.pl/-/decyzje-warunki-zabudowy",
                    "https://srodmiescie.um.warszawa.pl/-/decyzje-cel-publiczny-powiat",
                    "https://srodmiescie.um.warszawa.pl/-/decyzje-cel-publiczny-kraj")),
    District("targowek", "Targówek", "Targówka", "na Targówku", "Targówkiem", "146511_8", "tar", ("4",),
             r"\btargow(?:ek|ka|ku|kiem)\b", r"warszaw\w*\W+targowek\b",
             "https://targowek.um.warszawa.pl/-/warunki-zabudowy-postepowania-decyzje", "attachments",
             pages=("https://targowek.um.warszawa.pl/-/warunki-zabudowy-postepowania-decyzje",), extensions=_PDF_LISTS),
    District("ursus", "Ursus", "Ursusa", "w Ursusie", "Ursusem", "146512_8", "urs", ("2",),
             r"\bursus(?:a|ie|em)?\b", r"warszaw\w*\W+ursus\b",
             "https://ursus.um.warszawa.pl/decyzje-architektoniczne", "own-layout", status="pending",
             note="dzielnica publikuje własne rejestry (inny układ kolumn niż wzór z zarządzenia 1129/2020) – "
                  "ich odczyt jest w przygotowaniu; pozwolenia na budowę (GUNB) i sprawy Biura Architektury "
                  "są już dostępne"),
    District("ursynow", "Ursynów", "Ursynowa", "na Ursynowie", "Ursynowem", "146513_8", "urn", ("1",),
             r"\bursynow(?:a|ie|em)?\b", r"warszaw\w*\W+ursynow\b",
             "https://ursynow.um.warszawa.pl/-/rejestr-wnioskow-decyzji", "attachments",
             pages=("https://ursynow.um.warszawa.pl/-/rejestr-wnioskow-decyzji",)),
    District("wawer", "Wawer", "Wawra", "w Wawrze", "Wawrem", "146514_8", "waw", ("3",),
             r"\bwawer\b|\bwawr(?:a|ze|owi|em)\b", r"warszaw\w*\W+wawer\b",
             "https://wawer.um.warszawa.pl/dokumenty-budowlane", "attachments",
             pages=("https://wawer.um.warszawa.pl/dokumenty-budowlane",),
             exclude_re=r"pozwoleni\w* na budow|decyzje_pb|\bpb_"),   # building permits: GUNB has them
    District("wesola", "Wesoła", "Wesołej", "w Wesołej", "Wesołą", "146515_8", "wes", ("8",),
             r"\bwesol(?:a|ej)\b", r"warszaw\w*\W+wesola\b",
             "https://wesola.um.warszawa.pl/architektura", "attachments",
             pages=("https://wesola.um.warszawa.pl/-/informacje-o-wszczetych-postepowaniach-o-warunkach-zabudowy",
                    "https://wesola.um.warszawa.pl/-/informacje-o-wydanych-decyzjach-w-sprawie-warunkow-zabudowy",
                    "https://wesola.um.warszawa.pl/-/informacje-o-wydanych-decyzjach"),
             short_precinct_zone="8"),
    District("wilanow", "Wilanów", "Wilanowa", "w Wilanowie", "Wilanowem", "146516_8", "wil", ("1",),
             r"\bwilanow(?:a|ie|em)?\b", r"warszaw\w*\W+wilanow\b",
             "https://wilanow.um.warszawa.pl/-/nowe-procedury-zwiazane-z-jawnoscia-procesu-inwestycyjnego",
             "attachments",
             pages=("https://wilanow.um.warszawa.pl/-/informacje-o-wszczetych-postepowaniach-oraz-wydanych-decyzjach",)),
    District("wlochy", "Włochy", "Włoch", "we Włochach", "Włochami", "146517_8", "wlo", ("2",),
             r"\bwloch(?:y|ach|ow|ami)\b", r"warszaw\w*\W+wlochy\b",
             "https://wlochy.um.warszawa.pl/architektura", "attachments",
             pages=("https://wlochy.um.warszawa.pl/warunki-zabudowy-wnioski",
                    "https://wlochy.um.warszawa.pl/warunki-zabudowy-decyzje",
                    "https://wlochy.um.warszawa.pl/inwestycje-celu-publicznego-decyzje"),
             extensions=_PDF_LISTS),
    District("wola", "Wola", "Woli", "na Woli", "Wolą", "146518_8", "wol", ("6",),
             r"\bwol(?:a|i|e)\b", r"warszaw\w*\W+wola\b",
             "https://wola.um.warszawa.pl/wykazy-i-informacje-o-decyzjach", "attachments",
             pages=("https://wola.um.warszawa.pl/waw/wola/-/wnioski-o-wydanie-decyzji-urbanistycznych",
                    "https://wola.um.warszawa.pl/waw/wola/-/decyzje-o-warunkach-zabudowy",
                    "https://wola.um.warszawa.pl/waw/wola/-/decyzje-o-ustaleniu-lokalizacji-inwestycji-celu-"
                    "publicznego"),
             extensions=("xlsx",)),   # the pages also link every decision's text, and a 135 MB ZIP of them
    District("zoliborz", "Żoliborz", "Żoliborza", "na Żoliborzu", "Żoliborzem", "146519_8", "zol", ("7",),
             r"\bzoliborz(?:a|u|em)?\b", r"warszaw\w*\W+zoliborz\b",
             "https://zoliborz.um.warszawa.pl/-/informacja-o-wszczetych-postepowaniach-oraz-wydanych-decyzjach-"
             "administracyjnych-1", "attachments",
             pages=("https://zoliborz.um.warszawa.pl/-/informacja-o-wszczetych-postepowaniach-oraz-wydanych-"
                    "decyzjach-administracyjnych-1",)),
)}

_BY_UNIT = {d.unit: d for d in DISTRICTS.values()}
_BY_CODE = {d.code: d for d in DISTRICTS.values() if d.code}

_CURRENT: contextvars.ContextVar[District] = contextvars.ContextVar("wzsearch_district",
                                                                     default=DISTRICTS[LEGACY_SLUG])


def get(slug: str) -> District:
    try:
        return DISTRICTS[slug]
    except KeyError:
        raise KeyError(f"unknown district {slug!r} (known: {', '.join(DISTRICTS)})") from None


def by_unit(unit: str | None) -> District | None:
    return _BY_UNIT.get(unit or "")


def by_code(code: str | None) -> District | None:
    return _BY_CODE.get(code or "")


def current() -> District:
    """The district being built (Praga-Południe unless :func:`use` says otherwise)."""
    return _CURRENT.get()


@contextlib.contextmanager
def use(district: District | str) -> Iterator[District]:
    """Build ``district`` inside the ``with`` block."""
    d = get(district) if isinstance(district, str) else district
    token = _CURRENT.set(d)
    try:
        yield d
    finally:
        _CURRENT.reset(token)


# =========================================================================== precincts


_PRECINCTS_FILE = Path(__file__).with_name("data") / "warsaw_obreby.json"


@dataclass(frozen=True)
class _PrecinctTable:
    units: dict[str, frozenset[str]] = field(default_factory=dict)        # unit → {SSOO}
    owner: dict[tuple[str, str], str] = field(default_factory=dict)        # (zone, SSOO) → unit


@cache
def _table() -> _PrecinctTable:
    """Load ``warsaw_obreby.json``: ``{"units": {unit: {SSOO: rows}}}`` → per-unit sets and the owner of each
    ``(zone, SSOO)`` (the unit with the most register rows; a 3:1 majority is required, else nobody owns it)."""
    try:
        doc = json.loads(_PRECINCTS_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return _PrecinctTable()
    counts: dict[str, dict[str, int]] = {u: dict(v) for u, v in (doc.get("units") or {}).items()}
    units = {u: frozenset(v) for u, v in counts.items()}
    by_key: dict[tuple[str, str], list[tuple[int, str]]] = {}
    for unit, codes in counts.items():
        d = _BY_UNIT.get(unit)
        if d is None:
            continue
        for zone in d.zones:
            for code, n in codes.items():
                by_key.setdefault((zone, code), []).append((n, unit))
    owner = {}
    for key, cands in by_key.items():
        cands.sort(reverse=True)
        if len(cands) == 1 or cands[0][0] >= 3 * cands[1][0]:
            owner[key] = cands[0][1]
    return _PrecinctTable(units=units, owner=owner)


def precinct_units(unit: str) -> frozenset[str]:
    """Every 4-digit precinct code (``SSOO``) known in ``unit`` (from the GUNB register)."""
    return _table().units.get(unit, frozenset())


def unit_for_precinct(precinct: str, prefer: str | None = None) -> str | None:
    """Cadastral unit of a precinct ``Z-SS-OO`` (``"6-11-10"`` → ``"146502_8"``).

    ``prefer`` (the record's own district unit) wins when it has the precinct or when nobody owns it
    but the zone is the district's. None when the precinct cannot be placed in any unit.
    """
    m = re.fullmatch(r"(\d)-(\d{2})-(\d{2})", precinct or "")
    if not m:
        return None
    zone, code = m.group(1), m.group(2) + m.group(3)
    table = _table()
    if prefer and code in table.units.get(prefer, ()):
        d = _BY_UNIT.get(prefer)
        if d is None or zone in d.zones:
            return prefer
    found = table.owner.get((zone, code))
    if found:
        return found
    d = _BY_UNIT.get(prefer or "")
    if d is not None and zone in d.zones:
        return prefer
    return None
