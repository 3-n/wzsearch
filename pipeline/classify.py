"""Transparent keyword tagging of investment descriptions (stage 4b of the pipeline).

``classify(text)`` returns tag slugs (in :data:`TAGS` order) for a "streszczenie ustaleń
decyzji" / "nazwa inwestycji" text.  The rules are plain, diacritics-insensitive regexes over
the folded text so that anyone can audit why a record got a tag.

Two tag groups:

* ``funkcja`` – *what* is built or created (dom jednorodzinny, sieci, przedszkole, …);
* ``roboty`` – *kind of works* (nowa budowa, rozbudowa/przebudowa, zmiana sposobu użytkowania…).

The same rules tag the building-permit texts of the GUNB register (``pipeline/rwdz.py``); two tags
exist mainly for them: ``instalacje-wewnetrzne`` (gas/water/heating installations inside a building –
a fifth of all permits, kept apart from the ``infrastruktura`` networks) and ``remont`` (renovation,
insulation, replacement of windows or installations).

How a text is read (derived from every text in the 2020–2026 files):

1. It is split into clauses at "…, oraz/i/wraz z + <verb>" ("Nadbudowa … wraz ze zmianą
   sposobu użytkowania …", "… oraz budowa parkingu").
2. In a "zmiana sposobu użytkowania X na Y" clause the function tags come from the target **Y**
   (a shop turned into a flat is tagged as a flat, not as a shop); building type
   (jedno-/wielorodzinny) may come from the whole clause.
3. Elsewhere function tags come from the **main object** – the text before the first
   "z …"/"wraz z …" – so "budynek wielorodzinny z usługami w parterze i garażem podziemnym"
   is residential, not a shop or a car park.  A few tags (e.g. kindergartens in
   "… z przedszkolem") are also taken from that secondary part.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .textutil import collapse_ws, fold

__all__ = ["TAGS", "classify", "explain"]

#: slug → {label (short, Polish, user-facing), description, group}
TAGS: dict[str, dict[str, str]] = {
    "jednorodzinny": {
        "label": "Dom jednorodzinny",
        "description": "Budynki mieszkalne jednorodzinne – wolnostojące, bliźniacze i szeregowe.",
        "group": "funkcja",
    },
    "wielorodzinny": {
        "label": "Budynek wielorodzinny",
        "description": "Budynki mieszkalne wielorodzinne, także mieszkalno-usługowe.",
        "group": "funkcja",
    },
    "adaptacja-mieszkalna": {
        "label": "Adaptacja na mieszkanie",
        "description": "Zamiana lokalu usługowego, strychu, poddasza, garażu itp. na lokal lub funkcję mieszkalną.",
        "group": "funkcja",
    },
    "zamieszkanie-zbiorowe": {
        "label": "Akademik, hostel, hotel",
        "description": "Budynki zamieszkania zbiorowego: akademiki, hostele, hotele, pokoje gościnne.",
        "group": "funkcja",
    },
    "uslugi": {
        "label": "Handel, usługi, biura",
        "description": "Sklepy, pawilony, gastronomia, biura, warsztaty, salony i inne lokale użytkowe.",
        "group": "funkcja",
    },
    "oswiata": {
        "label": "Żłobek, przedszkole, szkoła",
        "description": "Placówki oświatowe i opiekuńcze dla dzieci.",
        "group": "funkcja",
    },
    "kultura": {
        "label": "Kultura",
        "description": "Biblioteki, domy kultury i inne obiekty kultury.",
        "group": "funkcja",
    },
    "zdrowie-opieka": {
        "label": "Zdrowie i opieka",
        "description": "Szpitale, kliniki, przychodnie, gabinety lekarskie, opieka społeczna.",
        "group": "funkcja",
    },
    "sport-rekreacja-zielen": {
        "label": "Sport, rekreacja, zieleń",
        "description": "Parki, boiska, stadiony, skateparki, tężnie, ścieżki zdrowia.",
        "group": "funkcja",
    },
    "kult-religijny": {
        "label": "Obiekt sakralny",
        "description": "Kościoły, domy parafialne i inne budynki kultu religijnego.",
        "group": "funkcja",
    },
    "infrastruktura": {
        "label": "Sieci: woda, ciepło, prąd, gaz",
        "description": "Sieci i przyłącza wodociągowe, kanalizacyjne, ciepłownicze, gazowe i elektroenergetyczne, "
                       "stacje transformatorowe, zbiorniki retencyjne.",
        "group": "funkcja",
    },
    "instalacje-wewnetrzne": {
        "label": "Instalacje w budynku (gaz, woda, c.o.)",
        "description": "Instalacje wewnątrz budynków i lokali: gazowe, wodno-kanalizacyjne, grzewcze, wentylacyjne, "
                       "elektryczne, fotowoltaiczne (sieci i przyłącza – zob. „Sieci”).",
        "group": "funkcja",
    },
    "telekomunikacja": {
        "label": "Telekomunikacja",
        "description": "Stacje bazowe telefonii komórkowej, maszty antenowe, kanalizacja kablowa.",
        "group": "funkcja",
    },
    "drogi-transport": {
        "label": "Drogi i transport",
        "description": "Drogi, ulice, chodniki, ścieżki rowerowe, kolej, komunikacja miejska, stacje ładowania.",
        "group": "funkcja",
    },
    "parkingi-garaze": {
        "label": "Parking, garaż",
        "description": "Parkingi, miejsca postojowe i budynki garażowe jako główny przedmiot inwestycji.",
        "group": "funkcja",
    },
    "reklama": {
        "label": "Reklama",
        "description": "Nośniki i tablice reklamowe, ekrany LED.",
        "group": "funkcja",
    },
    "przemysl-magazyny": {
        "label": "Przemysł, magazyny",
        "description": "Budynki produkcyjne, magazyny, obiekty techniczne (np. serwerownie, centra danych).",
        "group": "funkcja",
    },
    "obiekty-pomocnicze": {
        "label": "Wiata, altana, budynek gospodarczy",
        "description": "Altany śmietnikowe, wiaty, pergole, budynki gospodarcze i inne obiekty pomocnicze.",
        "group": "funkcja",
    },
    "windy-dostepnosc": {
        "label": "Winda, dostępność",
        "description": "Dobudowa wind i szybów dźwigowych, rampy dla osób z niepełnosprawnościami.",
        "group": "funkcja",
    },
    "nowa-budowa": {
        "label": "Nowa budowa",
        "description": "Budowa nowego obiektu, sieci lub urządzenia (także montaż).",
        "group": "roboty",
    },
    "rozbudowa-przebudowa": {
        "label": "Rozbudowa, nadbudowa, przebudowa",
        "description": "Zmiany istniejących obiektów: rozbudowa, nadbudowa, przebudowa, zabudowa tarasu.",
        "group": "roboty",
    },
    "remont": {
        "label": "Remont, docieplenie",
        "description": "Remonty, docieplenia i termomodernizacja budynków, remonty elewacji, dachów i balkonów, "
                       "wymiana okien lub instalacji.",
        "group": "roboty",
    },
    "zmiana-sposobu-uzytkowania": {
        "label": "Zmiana sposobu użytkowania",
        "description": "Zmiana funkcji budynku, lokalu lub jego części.",
        "group": "roboty",
    },
    "zmiana-decyzji": {
        "label": "Zmiana lub umorzenie",
        "description": "Zmiana wcześniej wydanej decyzji (także projekt zamienny do pozwolenia na budowę) "
                       "lub umorzenie postępowania w części.",
        "group": "roboty",
    },
    "legalizacja": {
        "label": "Legalizacja",
        "description": "Legalizacja obiektu wybudowanego wcześniej.",
        "group": "roboty",
    },
    "rozbiorka": {
        "label": "Rozbiórka",
        "description": "Rozbiórka budynku lub innego obiektu budowlanego (głównie pozwolenia na rozbiórkę "
                       "z rejestru GUNB).",
        "group": "roboty",
    },
}


@dataclass(frozen=True)
class _Rule:
    slug: str
    rx: re.Pattern[str]
    secondary: bool = False   # may also fire on the "z …" part / outside the main object


def _r(slug: str, pattern: str, secondary: bool = False) -> _Rule:
    return _Rule(slug, re.compile(pattern), secondary)


# Function rules – evaluated on the main object (or the conversion target).
_FUNCTION_RULES: list[_Rule] = [
    _r("zamieszkanie-zbiorowe", r"zamieszkani\w* zbiorow|zbiorowego zamieszkania|hotel|hostel|akademik|"
                                r"dom\w* studenck|pokoje goscinn"),
    _r("uslugi", r"handl|handel|sklep|bazar|(?<!mieszkalno-)(?<!mieszkaniowo-)uslug(?!ami\b)(?!\w*\s+kultu)|biur|"
                 r"gastronom|kawiarn|restaurac|salon\w* samochod|warsztat|myjni|pracowni|lokal\w* uzytkow|"
                 r"konferenc|naukow"),
    _r("oswiata", r"zlob|przedszkol|szkol|edukacyj|oswiatow|opiekuna dziennego", secondary=True),
    _r("kultura", r"bibliote|dom\w* kultury|teatr|muze|kino\b"),
    _r("zdrowie-opieka", r"szpital|klinik|lekarsk|medyczn|przychodn|opieki spolecznej|hospic|rehabilitac",
       secondary=True),
    _r("sport-rekreacja-zielen", r"boisk|stadion|skate|pumptrack|\bpark(?:u|ow|i|iem)?\b|tezni|sciezk\w* zdrowia|"
                                 r"street workout|plac\w* zabaw|silowni|basen|\bkort|\bzielen|skwer", secondary=True),
    _r("kult-religijny", r"kosciol|parafi|kult\w* religijn|sakraln|kaplic|klasztor"),
    _r("infrastruktura", r"wodociag|kanalizac\w*\b(?! kablow)|ogolnospl|ogolnospawn|cieplown|cieplnej|gazow|"
                         r"elektroenerget|energetyczn|kablow\w* sn|linii kablow|sieci kablow|trans?formator|trafo|"
                         r"retencyjn|odwodnien|deszczow|sciekow|zasilani|punkt\w* p\w*miarow|przylacz(?!eni)|"
                         r"zbiornik\w* przeciwpozar"),
    _r("telekomunikacja", r"telefoni|stacj\w* bazow|maszt|antenow|telekomunikac|kanalizacj\w* kablow|swiatlowod"),
    _r("drogi-transport", r"\bdrog[aiey]?\b|drogow|\bulicy\b|chodnik|sciezk\w* rowerow|kolej|trakcyj|tramwaj|"
                          r"autobus|\bpetli\b|przystank|transportu publiczn|ladowan|ladowni|wiadukt"),
    _r("drogi-transport", r"kolej|tramwaj|trakcyj", secondary=True),   # "… dla potrzeb ruchu kolejowego"
    _r("parkingi-garaze", r"parking|miejsc\w* postojow|garaz"),
    _r("reklama", r"reklam|nosnik|billboard|ekran\w* led"),
    _r("przemysl-magazyny", r"p-?rodukc|magazyn|przemysl|centrum obslugi danych|serwerowni|\bhal[aie]\b"),
    _r("obiekty-pomocnicze", r"altan|smietnik|gromadzenia odpadow|\bwiat[aey]\b|pergol|gospodarcz"),
    _r("windy-dostepnosc", r"wind[aey]?\b|window|dzwigow|rampy|niepelnosprawn", secondary=True),
]

# An installation inside a building ("budowa wewnętrznej instalacji gazowej w lokalu nr 6") is not a
# network: it gets its own tag and is blanked out before the other function rules run.
_MEDIUM = (r"(?:gaz|wod|kanaliz|c\.?\s?o\b|centraln\w* ogrzew|grzew|ogrzew|ciepl|elektr|wentyl|klimaty|fotowolt|"
           r"ppoz|przeciwpoz|tryskacz|hydrant|odgrom|sanitar)\w*(?:\s+(?:zimnej|cieplej|ziemn\w*))?")
_INSTALLATION_RE = re.compile(
    rf"(?:mikro)?instalac\w*(?:\s+(?:wewnetrzn|zewnetrzn|now)\w*)?\s+{_MEDIUM}(?:\s*(?:,|i|oraz)\s+{_MEDIUM})*"
    rf"|wewnetrzn\w*\s+instalac\w*(?:\s+{_MEDIUM})?"
)
_SINGLE_RE = re.compile(r"jednorodzin|segment\w* mieszkaln|domu? jednorodz")
_MULTI_RE = re.compile(r"wieloro\w*dzin|mieszkalno-uslugow|mieszkaniowo-uslugow|biurowo-mieszkaln|"
                       r"budynk\w* komunaln\w* mieszkaln")
_GENERIC_HOME_RE = re.compile(r"budyn\w* mieszk\w*|mieszkaln\w* budyn\w*")
_MULTI_HINT_RE = re.compile(r"podziem|przyziem|w parterze|garaz\w* w|kondygnac")

_CONVERSION_RE = re.compile(r"zmia\w*\s*(?:s\w*\s+)?(?:posob\w*\s+)?uz+y?tk\w*|adaptac\w*")
_TARGET_SPLIT_RE = re.compile(r"\b(?:na|celem|z przeznaczeniem na)\s+")
_RESIDENTIAL_RE = re.compile(r"(?<!za)mi\w{0,2}eszk")   # mieszkalny / mieszkanie (+ typos), not "zamieszkanie"
_TARGET_HEAD_RE = re.compile(r"\s(?:w|we|wraz|z|ze|oraz)\s")
_CLAUSE_SPLIT_RE = re.compile(
    r"(?:\s*[,;]\s*|\s+(?:oraz|i|a)\s+|\s+wraz\s+ze?\s+|\s+-\s*)"
    r"(?=(?:budow|przebudow|rozbudow|nadbudow|dobudow|zmia\w*\s+(?:s\w*\s+)?(?:posob\w*\s+)?uz|montaz|rozbior|"
    r"umorzeni|wykonani|zabudow)\w*)"
    r"|\s+ze?\s+(?=(?:przebudow|rozbudow|nadbudow|dobudow)\w*)"          # "rozbudowa z przebudową …"
)
# End of the main object: "… z garażem", "… wraz z …", "… dla potrzeb …", ", w skład której …"
_HEAD_SPLIT_RE = re.compile(
    r"\s(?:wraz\s+)?(?:z|ze)\s(?!przeznaczeniem)|"
    r"\sdla\s+(?:potrzeb|zabudowy|obslugi|budynk|pracownik|istniejac|projektowan)|[\s,]+[wa]\s+sklad\s"
)
_MODIFY_RE = re.compile(r"^(?:rozbu\w*ow|nadbudow|przebudow|dobudow|zabudow)")

_WORKS_RULES: list[tuple[str, re.Pattern[str]]] = [
    ("legalizacja", re.compile(r"legalizac|samowol")),
    ("rozbiorka", re.compile(r"rozbior|wyburz")),
    ("zmiana-decyzji", re.compile(r"zmian\w* (?:decyzji|pozwolen)|projekt\w* zamienn|umorzeni")),
    ("zmiana-sposobu-uzytkowania", _CONVERSION_RE),
    ("rozbudowa-przebudowa", re.compile(r"rozbu\w*ow|nadbudow|przebudow|dobudow|zabudow\w* (?:czesci )?taras|"
                                        r"(?<!termo)modernizac|przy istniejacym")),
    ("remont", re.compile(r"\bremon?t(?!ow)|\brement|\br3mont|termomoderniz|docieplen|ocieplen|termoizolac|"
                          r"izolac\w* termiczn|\bwymian|renowac")),
]
_NEW_BUILD_RE = re.compile(r"^(?:budow\w*|montaz\w*|budyn\w*)\b")


def _prepare(text: str | None) -> str:
    """Folded, single-spaced text with the typos that would break clause/head detection fixed."""
    f = collapse_ws(fold(text)).replace("[", "").replace("]", "")
    f = f.replace('"', ' " ')                                              # „C.2 ”z garażem → … " z garażem
    # "wielorodzinnegoz usługami", "wielorodzinnegoi garażem" (instrumental → the typo'd word is "z")
    f = re.sub(r"(wielorodzinnego|jednorodzinnego|mieszkalnego)[iz]\b", r"\1 z", f)
    return collapse_ws(f)


def _split_clauses(f: str) -> list[str]:
    return [c.strip(" ,;-") for c in _CLAUSE_SPLIT_RE.split(f) if c and c.strip(" ,;-")]


def _residential_conversion(f: str) -> bool:
    """"zmiana sposobu użytkowania … na lokal mieszkalny / celem powiększenia lokalu mieszkalnego"."""
    for conv in _CONVERSION_RE.finditer(f):
        rest = f[conv.end():]
        for m in _TARGET_SPLIT_RE.finditer(rest):
            target = rest[m.end():]
            head = target[: t.start()] if (t := _TARGET_HEAD_RE.search(target)) else target
            if _RESIDENTIAL_RE.search(" ".join(head.split()[:4])):
                return True
    return False


def _clause_tags(clause: str) -> set[str]:
    tags: set[str] = set()
    for slug, rx in _WORKS_RULES:
        if rx.search(clause):
            tags.add(slug)
    if _NEW_BUILD_RE.search(clause) and not re.search(r"przy istniejacym", clause):
        tags.add("nowa-budowa")

    conv = _CONVERSION_RE.search(clause)
    if conv:
        # function = what the space becomes: text after the last "na"/"celem" (up to "w budynku …")
        rest = clause[conv.end():]
        pieces = _TARGET_SPLIT_RE.split(rest)
        target = pieces[-1] if len(pieces) > 1 else ""
        t = _TARGET_HEAD_RE.search(target)
        primary, secondary = (target[: t.start()], target[t.end():]) if t else (target, "")
        context = clause
    else:
        m = _HEAD_SPLIT_RE.search(clause)
        primary = clause[: m.start()] if m else clause
        secondary = clause[m.end():] if m else ""
        # works on an existing building may name the building after "z …" ("nadbudowa o 2 kondygnacje
        # z antresolą istniejącego budynku wielorodzinnego")
        context = clause if _MODIFY_RE.search(clause) else primary

    if _INSTALLATION_RE.search(primary):
        tags.add("instalacje-wewnetrzne")
        primary = _INSTALLATION_RE.sub(" ", primary)
    for rule in _FUNCTION_RULES:
        if rule.rx.search(primary) or (rule.secondary and secondary and rule.rx.search(secondary)):
            tags.add(rule.slug)

    if _SINGLE_RE.search(context):
        tags.add("jednorodzinny")
    if _MULTI_RE.search(context):
        tags.add("wielorodzinny")
    elif (not _SINGLE_RE.search(context) and _GENERIC_HOME_RE.search(primary)
          and _MULTI_HINT_RE.search(clause)):
        # "budynek mieszkalny ISKRA z garażami w podziemiu" – residential, clearly not a house
        tags.add("wielorodzinny")
    return tags


def classify(text: str | None) -> list[str]:
    """Tag slugs for an investment description, in :data:`TAGS` order.

    >>> classify("Budowa budynku mieszkalnego wielorodzinnego z usługami w parterze i garażem podziemnym")
    ['wielorodzinny', 'nowa-budowa']
    >>> classify("Zmiana sposobu użytkowania lokalu usługowego na żłobek")
    ['oswiata', 'zmiana-sposobu-uzytkowania']
    """
    f = _prepare(text)
    if not f:
        return []
    tags: set[str] = set()
    for clause in _split_clauses(f):
        tags |= _clause_tags(clause)
    if _residential_conversion(f):
        tags.add("adaptacja-mieszkalna")
    return [slug for slug in TAGS if slug in tags]


def explain(text: str | None) -> list[tuple[str, list[str]]]:
    """Debug helper: the clauses a text was split into and the tags each produced."""
    f = _prepare(text)
    return [(c, [s for s in TAGS if s in _clause_tags(c)]) for c in _split_clauses(f)]
