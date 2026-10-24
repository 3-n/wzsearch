"""Helpers for the city-wide lists of Biuro Architektury i Planowania Przestrzennego (BAiPP).

BAiPP (Urząd m.st. Warszawy) publishes the same three lists as the district office – initiated
WZ/ULICP proceedings (``ws``), WZ decisions (``wz``) and ULICP decisions (``cp``, in two series) –
for the cases it handles itself, for the whole city, as yearly / year-to-date Excel files
(``architektura.um.warszawa.pl/postepowania-i-decyzje`` and the ``/-/rejestry…`` archive pages; the
crawler lives in :mod:`pipeline.crawl`). This module holds what is specific to those lists:

* :func:`in_district` – the Praga-Południe filter (last line of the address cell, never the applicant);
* :func:`strip_district` – the address cell without its district line (``"Parga Południe"`` typo too);
* :func:`split_number` / :func:`parse_outcome` – the number cell packs the number and the outcome
  (``"95/AM/PPD/WZ/2026/O\\n\\nodmowa"``);
* :func:`applicant_text` – ``"dane osobowe"`` (the bureau's anonymisation) → ``"osoba fizyczna"``;
* :func:`namespace_id` – record ids that never collide with district ids (``wz-am-2026-95``);
* :func:`check_out_of_district` – BAiPP rows labelled "Praga Południe" whose parcels ULDK places in
  another Warsaw district (probed in the same obręb zone, cached in ``data/cache/uldk.json``);
  :func:`check_out_of_district_permits` – the same for GUNB RWDZ cases whose unit id says Praga-Południe
  but whose precinct exists only in another district.

Every heuristic that changes or infers a value leaves a short Polish warning (see normalize.py).
"""

from __future__ import annotations

import os
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from . import geocode
from .textutil import cell_to_str, collapse_ws, fold, tidy_cell

__all__ = [
    "DISTRICT_RE",
    "OUTCOME_SUFFIXES",
    "WARSAW_UNITS",
    "NumberParts",
    "applicant_text",
    "check_out_of_district",
    "check_out_of_district_permits",
    "district_line",
    "duplicate_sequence_warning",
    "in_district",
    "namespace_id",
    "number_series",
    "parse_outcome",
    "split_number",
    "strip_district",
    "unplaced_geo",
]

#: District filter on the LAST non-empty line of the address cell (DATA_MODEL.md, v2 extension).
#: "Parga Południe" is a typo seen in the 2021 list.
DISTRICT_RE = re.compile(r"praga[\s-]*(po[lł]udnie|p[lł]d)|parga po[lł]udnie", re.I)

#: Outcome letter at the end of a 2024+ decision number (``95/AM/PPD/WZ/2026/O``).
OUTCOME_SUFFIXES = {"O": "refusal", "U": "discontinued", "P": "transfer", "W": "expiry"}
_OUTCOME_LABELS = {"refusal": "odmowa", "discontinued": "umorzenie", "transfer": "przeniesienie",
                   "expiry": "wygaśnięcie", "granted": "ustalenie"}
# Outcome words of the second line ("odmowa", "umorzenie licp", "wygaśnięcie decyzji w części", …);
# the first one in the text wins ("odmowa przeniesienia decyzji" is a refusal).
_OUTCOME_WORDS = [
    ("refusal", re.compile(r"\bodmow")),
    ("discontinued", re.compile(r"\bumorz")),
    ("transfer", re.compile(r"\bprzeniesien")),
    ("expiry", re.compile(r"\bwyga(?:s|sz)")),
]
_GRANTED_RE = re.compile(r"^(?:(?:wz|licp|ulicp)\b\s*)+$")

#: Warsaw's cadastral units (TERYT) – Praga-Południe is ``146507_8``.
WARSAW_UNITS = {
    "146502_8": "Bemowo", "146503_8": "Białołęka", "146504_8": "Bielany", "146505_8": "Mokotów",
    "146506_8": "Ochota", "146507_8": "Praga-Południe", "146508_8": "Praga-Północ", "146509_8": "Rembertów",
    "146510_8": "Śródmieście", "146511_8": "Targówek", "146512_8": "Ursus", "146513_8": "Ursynów",
    "146514_8": "Wawer", "146515_8": "Wesoła", "146516_8": "Wilanów", "146517_8": "Włochy",
    "146518_8": "Wola", "146519_8": "Żoliborz",
}
PRAGA_POLUDNIE = "146507_8"
#: Warsaw obręb names are ``Z-SS-NN`` and ULDK drops the zone digit ``Z`` (``4-15-08`` → ``1508``), so the
#: 4-digit code repeats across zones (``146505_8.0203`` is Mokotów's 1-02-03, ``146507_8.0203`` is 3-02-03).
#: A zone groups the districts carved out of one pre-1994 district; verified against the district named
#: in 2,000+ BAiPP rows (2020–2026). Wesoła (in Warsaw since 2002) has a zone of its own: ULDK names its
#: precinct 146515_8.0602 "8-06-02" (checked 2026-10-23) – probing it for a "3-06-02" would be a false match.
OBREB_ZONES = {
    "1": ("146505_8", "146513_8", "146516_8"),  # Mokotów, Ursynów, Wilanów
    "2": ("146506_8", "146512_8", "146517_8"),  # Ochota, Ursus, Włochy
    "3": ("146507_8", "146509_8", "146514_8"),  # Praga-Południe, Rembertów, Wawer
    "4": ("146508_8", "146511_8", "146503_8"),  # Praga-Północ, Targówek, Białołęka
    "5": ("146510_8",),                         # Śródmieście
    "6": ("146518_8", "146502_8"),              # Wola, Bemowo
    "7": ("146519_8", "146504_8"),              # Żoliborz, Bielany
    "8": ("146515_8",),                         # Wesoła
}
#: ``geo.note`` of a record whose parcels ULDK places in another district (not put on the district map)
NOTE_OUTSIDE = "działki poza dzielnicą Praga-Południe według ewidencji gruntów (ULDK) – nie pokazano na mapie"
#: start of the record warning that names those parcels (the report looks for it)
OUTSIDE_WARNING = "działka poza dzielnicą Praga-Południe według ewidencji gruntów (ULDK)"
#: Default BAiPP planning unit of Praga-Południe case signs (``AM-ZP-P.6730.14.2020``); case-sign numbering
#: is per unit (ZP-P, ZP-E, ZP-N, …), so a sign of another unit gets the unit in its id.
DEFAULT_UNIT = "ZP-P"


# =========================================================================== district filter


def _lines(value: Any) -> list[str]:
    """Visual lines of a cell (``\\n`` and the office's 3+-space gaps), stripped, without empty ones."""
    return [line for line in tidy_cell(cell_to_str(value)).split("\n") if line.strip()]


def district_line(address: Any) -> str | None:
    """The last non-empty line of the address cell ("ulica, dzielnica"), where BAiPP names the district."""
    lines = _lines(address)
    return lines[-1] if lines else None


def in_district(address: Any) -> bool:
    """True when the address cell's last line names Praga-Południe (``"Ostrobramska 73 \\nPraga Południe"``).

    Only the address column is looked at – applicant names can contain the district
    ("Spółdzielnia Spożywców Praga Południe").
    """
    line = district_line(address)
    return bool(line and DISTRICT_RE.search(line))


def strip_district(address: Any) -> str:
    """The address cell (visual lines joined with ``\\n``) without the district on its last line.

    ``"Chodakowska\\nWawerska\\nPraga Południe"`` → ``"Chodakowska\\nWawerska"``;
    ``"Wał Miedzeszyński 646 Praga Południe"`` → ``"Wał Miedzeszyński 646"``.
    """
    lines = _lines(address)
    if lines and DISTRICT_RE.search(lines[-1]):
        rest = DISTRICT_RE.sub(" ", lines[-1]).strip(" ,;-–")
        lines = lines[:-1] + ([rest] if rest else [])
    return "\n".join(lines)


# =========================================================================== number + outcome


@dataclass
class NumberParts:
    """A BAiPP number cell split into the printed number and the rest of the cell."""

    number: str                      # as printed, whitespace removed ("95/AM/PPD/WZ/2026/O")
    rest: str = ""                   # the outcome words ("odmowa"), single-spaced
    others: list[str] = field(default_factory=list)   # further case signs in the cell (EZD numbers)


_CASE_SIGN_RE = re.compile(r"(?<![\w.])(?:[A-Z]{1,5}-)+[A-Z]{1,5}\.\d{3,4}\.\d{1,5}\.\d{4}(?![\d])")
_DECISION_RE = re.compile(r"^\s*\d+(?:\s*/+\s*[0-9A-Za-zĄĆĘŁŃÓŚŹŻąćęłńóśźż]+)+")


def split_number(value: Any, kind: str | None) -> NumberParts:
    """Separate the number (or case sign) from the outcome words written in the same cell.

    * decisions (``wz``/``cp``): the leading ``n/…/…`` run, spaces around slashes tolerated
      (``"119/AM/PPD/WZ /2025/P\\nprzeniesienie"`` → ``119/AM/PPD/WZ/2025/P`` + ``przeniesienie``);
    * initiated proceedings (``ws``): the first case sign (``AM-ZP-P.6730.14.2020``); a second sign
      (``EZD AM-ZP-N.6730.43.2026``, the electronic-records number) goes to ``others``.

    Falls back to the whole cell without whitespace when nothing matches.
    """
    text = collapse_ws(cell_to_str(value))
    if not text:
        return NumberParts("")
    if kind == "ws":
        joined = re.sub(r"\s*([-.])\s*", r"\1", text)   # signs wrapped across lines: "AM-ZP-\nP.6730…"
        signs = _CASE_SIGN_RE.findall(joined)
        if signs:
            rest = _CASE_SIGN_RE.sub(" ", joined)
            rest = collapse_ws(re.sub(r"(?i)\bEZD\b", " ", rest))
            return NumberParts(signs[0], rest, signs[1:])
        return NumberParts(re.sub(r"\s+", "", text))
    m = _DECISION_RE.match(text)
    if not m:
        return NumberParts(re.sub(r"\s+", "", text))
    return NumberParts(re.sub(r"\s+", "", m.group(0)), collapse_ws(text[m.end():]).strip(" ,;-–+"))


def parse_outcome(number: str, rest: str, kind: str | None) -> tuple[str | None, list[str]]:
    """Outcome of a BAiPP decision → ``(granted|refusal|discontinued|transfer|expiry|None, warnings)``.

    Precedence: the words of the cell ("odmowa", "umorzenie licp", "wygaśnięcie decyzji") – they are
    the most specific ("/P" + "odmowa przeniesienia decyzji" is a refused transfer); then the
    2024+ suffix letter (/O /U /P /W); "wz"/"licp" alone = granted; a 2024+ ``…/AM/…`` number with
    neither suffix nor words = granted. Initiated proceedings (``ws``) have no outcome.
    """
    if kind not in ("wz", "cp"):
        return None, []
    warnings: list[str] = []
    m = re.search(r"/\d{2,4}/([A-Za-z])$", number)
    letter = m.group(1).upper() if m else None
    by_letter = OUTCOME_SUFFIXES.get(letter or "")
    words = collapse_ws(fold(rest))
    hits = [(m.start(), outcome) for outcome, rx in _OUTCOME_WORDS if (m := rx.search(words))]
    by_words = min(hits)[1] if hits else None
    if by_words is None and words and _GRANTED_RE.match(words):
        by_words = "granted"

    if by_words:
        if by_letter and by_letter != by_words and by_words != "refusal":
            warnings.append(f"oznaczenie /{letter} ({_OUTCOME_LABELS[by_letter]}) i opis „{rest}” wskazują różne "
                            f"rozstrzygnięcia – przyjęto opis")
        return by_words, warnings
    if words:
        if by_letter:
            warnings.append(f"nierozpoznany opis rozstrzygnięcia („{rest}”) – przyjęto oznaczenie /{letter} "
                            f"({_OUTCOME_LABELS[by_letter]})")
            return by_letter, warnings
        warnings.append(f"nie ustalono rozstrzygnięcia decyzji („{rest}”)")
        return None, warnings
    if by_letter:
        return by_letter, warnings
    if letter:
        warnings.append(f"nieznane oznaczenie /{letter} w numerze decyzji – nie ustalono rozstrzygnięcia")
        return None, warnings
    if "/AM/" in number.upper():
        return "granted", warnings      # 2024+: no suffix = decision issued as applied for
    return None, warnings


def _sequence(number: Any) -> int | None:
    m = re.match(r"\s*(\d+)\s*/", cell_to_str(number))
    return int(m.group(1)) if m else None


def duplicate_sequence_warning(number: str, rows: list[dict], kind: str | None) -> str | None:
    """Warning when a decision's sequence number is printed for another decision of the same city-wide list.

    WZ and ULICP decisions are numbered consecutively per year (and series) for the whole city, so the same
    number twice in one file is a source error (2025: "33/AM/BIE/…" and "33/AM/PPD/…", 34 missing).
    ``rows`` are all (city-wide) parsed rows of the file.
    """
    seq = _sequence(number)
    if kind not in ("wz", "cp") or seq is None:
        return None
    seqs = [_sequence(r["cells"].get("number")) for r in rows]
    if seqs.count(seq) < 2:
        return None
    missing = [n for n in (seq - 1, seq + 1) if n > 0 and n not in seqs and n <= max(s for s in seqs if s)]
    hint = f"; brak numeru {missing[0]}" if len(missing) == 1 else ""
    return (f"ten sam numer porządkowy ({seq}) nosi w zestawieniu także inna decyzja{hint} – "
            f"możliwa pomyłka w numeracji źródła")


# =========================================================================== applicant


def applicant_text(value: Any) -> str:
    """The bureau writes natural persons as "dane osobowe": → "osoba fizyczna" (type person).

    A business named after a person keeps its name with the redaction marked:
    ``"Kancelaria Adwokacka \\ndane osobowe"`` → ``"Kancelaria Adwokacka (dane osobowe)"``.
    """
    text = collapse_ws(cell_to_str(value))
    if re.fullmatch(r"(?i)\(?\s*dane\s+osobowe\s*\)?\.?", text):
        return "osoba fizyczna"
    return re.sub(r"(?i)(?<!\()\bdane\s+osobowe\b(?!\))", "(dane osobowe)", text)


# =========================================================================== ids


def number_series(number: str) -> str | None:
    """ULICP series printed in the number: ``C1``/``CP1`` → ``c1``, ``C2``/``CP2`` → ``c2``."""
    m = re.search(r"/CP?([12])(?=/|$)", number.upper())
    return f"c{m.group(1)}" if m else None


def namespace_id(base_id: str, kind: str | None, number: str, file_series: str | None) -> tuple[str, list[str]]:
    """Turn a district-style id into the BAiPP namespace (DATA_MODEL.md → Record ids).

    ``wz-2026-95`` → ``wz-am-2026-95``; ``cp-2022-1`` + series → ``cp-am-2022-c2-1``;
    ``ws-6730-2020-14`` → ``ws-am-6730-2020-14`` (``ws-am-zp-e-6730-2025-5`` for a case sign of
    another planning unit than ZP-P); fallback ``wz-f<file>-r<row>`` → ``wz-am-f<file>-r<row>``.
    The ULICP series comes from the number (``C2``/``CP2``), else from the file (link text / title).
    """
    warnings: list[str] = []
    head, _, tail = base_id.partition("-")
    if tail.startswith("f") and re.fullmatch(r"f[0-9a-z]+-r\d+", tail):
        return f"{head}-am-{tail}", warnings
    if kind == "cp":
        series = number_series(number)
        if series and file_series and series != file_series:
            warnings.append(f"seria decyzji w numerze ({series.upper()}) różni się od serii pliku "
                            f"({file_series.upper()}) – przyjęto numer")
        series = series or file_series
        if series:
            return f"{head}-am-{tail.split('-', 1)[0]}-{series}-{tail.split('-', 1)[1]}", warnings
        warnings.append("nie ustalono serii decyzji ULICP (C1/C2)")
    if kind == "ws":
        m = re.match(r"AM-([A-Z]+(?:-[A-Z]+)*)\.", number)
        unit = m.group(1) if m else DEFAULT_UNIT
        if unit != DEFAULT_UNIT:
            return f"{head}-am-{unit.lower()}-{tail}", warnings
    return f"{head}-am-{tail}", warnings


# =========================================================================== out-of-district parcels


def _parcel_parts(pid: str) -> tuple[str, str, str] | None:
    """``146507_8.1508.18/5`` → ``("146507_8", "1508", "18/5")``."""
    parts = pid.split(".", 2)
    return tuple(parts) if len(parts) == 3 else None  # type: ignore[return-value]


def _zone(obreb: str | None) -> str | None:
    m = re.match(r"^(\d)-\d{2}-\d{2}$", obreb or "")
    return m.group(1) if m else None


def check_out_of_district(
    records: list[dict],
    *,
    cache_dir: str,
    online: bool,
    session=None,
    refresh_misses: bool = False,
    log: Callable[[str], None] | None = None,
) -> set[str]:
    """Flag BAiPP records whose parcels ULDK places outside Praga-Południe; returns their ids.

    For every BAiPP record none of whose parcels exists under ``146507_8``, the same obręb / number is
    looked up under the other Warsaw units of the obręb's zone (``4-15-08`` → Praga-Północ, Targówek,
    Białołęka). When one resolves, the record keeps its data (sources matter) but gets the warning
    "działka poza dzielnicą Praga-Południe wg ULDK (…)", its parcel ids are corrected to the unit
    found (``146508_8.1508.18/5``) and the caller must not place it on the district map.
    Lookups (hits and misses) go through :func:`pipeline.geocode.lookup_parcels` and its cache file
    ``<cache_dir>/uldk.json``; offline, only cached answers are used.
    """
    candidates = [r for r in records if r.get("dataset") == "baipp" and r.get("parcels")]
    if not candidates:
        return set()
    path = os.path.join(cache_dir, "uldk.json")
    cache = geocode.load_cache(path)
    own_ids = [p["id"] for r in candidates for p in r["parcels"] if p.get("id")]
    own = geocode.lookup_parcels(own_ids, cache, session, online, refresh_misses=refresh_misses, log=log)

    suspects: list[dict] = []
    probes: dict[str, list[str]] = {}            # own parcel id → ids to try in other units of its zone
    for r in candidates:
        statuses = [own.get(p["id"], {}).get("status") for p in r["parcels"]]
        if "ok" in statuses or "error" in statuses or not statuses:
            continue                              # placed in the district, or unknown (offline / error)
        suspects.append(r)
        for p in r["parcels"]:
            split = _parcel_parts(p["id"])
            zone = _zone(p.get("obreb"))
            if split is None or zone is None:
                continue
            probes[p["id"]] = [f"{unit}.{split[1]}.{split[2]}" for unit in OBREB_ZONES.get(zone, ())
                               if unit != PRAGA_POLUDNIE]
    if not suspects:
        return set()
    found = geocode.lookup_parcels([pid for ids in probes.values() for pid in ids], cache, session, online,
                                   refresh_misses=refresh_misses, log=log)
    if online:
        geocode.save_cache(path, cache)

    outside: set[str] = set()
    for r in suspects:
        moved = []
        for p in r["parcels"]:
            hit = next((pid for pid in probes.get(p["id"], ()) if found.get(pid, {}).get("status") == "ok"), None)
            if hit:
                moved.append((p, hit))
        if not moved:
            continue
        where = ", ".join(f"{p['number']} obr. {p['obreb']}: {WARSAW_UNITS[hit.split('.', 1)[0]]}, {hit}"
                          for p, hit in moved)
        r["warnings"].append(f"{OUTSIDE_WARNING}: {where} – w źródle opisana jako Praga-Południe; nie zaznaczono "
                             f"jej na mapie dzielnicy")
        for p, hit in moved:
            p["id"] = hit
        outside.add(r["id"])
    return outside


def _probe_units() -> list[str]:
    """Warsaw units other than Praga-Południe: the same zone (Rembertów, Wawer), zone 4, then the rest."""
    first = [*OBREB_ZONES["3"], *OBREB_ZONES["4"]]
    return [u for u in dict.fromkeys([*first, *sorted(WARSAW_UNITS)]) if u != PRAGA_POLUDNIE]


def _no_such_obreb_warning(w: str, code: str) -> bool:
    """The RWDZ warning 'obręb „1406” nie występuje na Pradze-Południe …' for this 4-digit code."""
    m = re.match(r"obręb „(\d+)” nie występuje na Pradze-Południe", w)
    return bool(m) and m.group(1).zfill(4) == code


def _zone_of_unit(unit: str) -> str | None:
    return next((zone for zone, units in OBREB_ZONES.items() if unit in units), None)


#: decision-number codes of Praga-Północ in the city's numbering ("272/PRN/2019"; Praga-Południe is PRD/PPD)
_PRAGA_PN_NUMBER_RE = re.compile(r"/P(?:RN|PN)/", re.I)


def _units_hinted(record: dict) -> set[str]:
    """Units the case itself points to (the 4-digit precinct code repeats across zones: 1406 is Praga-Północ's
    4-14-06 and Wawer's 3-14-06): the organ "… - Praga Pn." or a Praga-Północ number code → Praga-Północ; the
    Praga-Południe district office → the neighbouring units of its zone it also handles (Rembertów, Wawer)."""
    raw = dict((record.get("sources") or [{}])[0].get("raw") or [])
    organ = collapse_ws(fold(raw.get("nazwa_organu") or ""))
    if re.search(r"praga\W*(?:pn|polnoc)", organ) or _PRAGA_PN_NUMBER_RE.search(record.get("number") or ""):
        return {"146508_8"}
    if re.search(r"praga\W*(?:pld|poludnie)", organ):
        return {u for u in OBREB_ZONES["3"] if u != PRAGA_POLUDNIE}
    return set()


def check_out_of_district_permits(
    records: list[dict],
    *,
    is_pp_obreb: Callable[[str], bool],
    cache_dir: str,
    online: bool,
    session=None,
    refresh_misses: bool = False,
    log: Callable[[str], None] | None = None,
) -> set[str]:
    """GUNB RWDZ records with a Praga-Południe unit id (``146507_8``) but a precinct the district does not have
    (``1406``, ``1507``, ``1122`` – register errors), which the geocoder could not place in the district: the
    same parcel and precinct are looked up under every other Warsaw unit (the register's 4-digit code has no
    zone digit). Returns the ids of the records moved out.

    The 4-digit code repeats across zones (``146508_8.1507.3`` and ``146514_8.1507.3`` both exist), so the
    case must point to the unit (:func:`_units_hinted`: organ, decision number): the hinted unit that has the
    parcel – or, when the parcel itself is gone there, the precinct (``146508_8.1406``) – wins. Without a
    hint, only a precinct that exists under exactly one other unit counts. Like BAiPP's
    :func:`check_out_of_district`, a moved record keeps its data (sources matter) but gets the corrected
    parcel id and obręb (``4-15-07``), the warning "działka poza dzielnicą Praga-Południe …" in place of the
    "obręb nie występuje" one, and the caller does not put it on the district map. Run it after geocoding:
    a record whose address lies in the district is a district case with a mistyped precinct and is never
    moved. Lookups are cached in ``<cache_dir>/uldk.json`` (offline: cache only; an incomplete answer moves
    nothing).
    """
    def bad(p: dict) -> bool:
        unit, _, rest = (p.get("id") or "").partition(".")
        return unit == PRAGA_POLUDNIE and not is_pp_obreb(rest.split(".", 1)[0])

    candidates = [r for r in records if r.get("dataset") == "rwdz" and not (r.get("geo") or {}).get("method")
                  and any(bad(p) for p in r.get("parcels") or [])]
    if not candidates:
        return set()
    path = os.path.join(cache_dir, "uldk.json")
    cache = geocode.load_cache(path)
    units = _probe_units()
    rests = sorted({p["id"].split(".", 1)[1] for r in candidates for p in r["parcels"] if bad(p)})
    found = geocode.lookup_parcels([f"{u}.{rest}" for rest in rests for u in units], cache, session, online,
                                   refresh_misses=refresh_misses, log=log)
    codes = sorted({rest.split(".", 1)[0] for rest in rests})
    regions = geocode.lookup_regions([f"{u}.{code}" for code in codes for u in units], cache, session, online,
                                     refresh_misses=refresh_misses)
    if online:
        geocode.save_cache(path, cache)

    def answers(ids: list[str], got: dict) -> set[str] | None:
        """Units whose id exists; None if any answer is unknown (offline without cache, network error)."""
        status = {i: got.get(i, {}).get("status") for i in ids}
        if any(v not in ("ok", "missing") for v in status.values()):
            return None
        return {i.split(".", 1)[0] for i, v in status.items() if v == "ok"}

    outside: set[str] = set()
    for r in candidates:
        hint = _units_hinted(r)
        moved = []
        for p in r["parcels"]:
            if not bad(p):
                continue
            rest = p["id"].split(".", 1)[1]
            code, number = rest.split(".", 1)
            with_parcel = answers([f"{u}.{rest}" for u in units], found)
            with_region = answers([f"{u}.{code}" for u in units], regions)
            if with_parcel is None or with_region is None:
                continue
            if hint:
                by_parcel, by_region = with_parcel & hint, with_region & hint
            else:
                by_parcel = with_parcel if len(with_region) == 1 and with_parcel <= with_region else set()
                by_region = with_region if len(with_region) == 1 else set()
            if len(by_parcel) == 1:
                unit = next(iter(by_parcel))
                moved.append((p, f"{unit}.{rest}", f"{number} obr. {code}: {WARSAW_UNITS[unit]}, {unit}.{rest}"))
            elif len(by_region) == 1:
                unit = next(iter(by_region))
                moved.append((p, f"{unit}.{rest}", f"{number} obr. {code}: obręb {unit}.{code} "
                                                    f"({WARSAW_UNITS[unit]}), działki już w nim nie ma"))
        if not moved:
            continue
        for p, new_id, _ in moved:
            unit, code = new_id.split(".")[:2]
            zone = _zone_of_unit(unit)
            r["warnings"] = [w for w in r.get("warnings") or [] if not _no_such_obreb_warning(w, code)]
            p["id"] = new_id
            p["obreb"] = f"{zone}-{code[:2]}-{code[2:]}" if zone else p["obreb"]
        r["warnings"].append(f"{OUTSIDE_WARNING}: {'; '.join(what for *_, what in moved)} – w rejestrze z "
                             f"identyfikatorem jednostki 146507_8 (Praga-Południe); nie zaznaczono jej na mapie dzielnicy")
        outside.add(r["id"])
    return outside


def unplaced_geo(note: str = NOTE_OUTSIDE) -> dict:
    """``geo`` of a record deliberately not placed on the district map."""
    return {"lat": None, "lon": None, "method": None, "parcels_found": [], "bbox": None, "note": note}
