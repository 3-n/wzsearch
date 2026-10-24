"""Turn parsed rows into clean ``Record`` dicts (stage 4 of the pipeline).

Public API (see docs/DATA_MODEL.md for the Record schema):

* :func:`normalize_row` – one ParsedFile row → Record (without ``geo``/``related``/``area``);
* :func:`record_id`, :func:`parse_decision_number`, :func:`parse_case_sign`;
* :func:`parse_date`, :func:`clean_number`;
* :func:`clean_applicant`, :func:`applicant_type`, :func:`redact_persons`;
* :func:`parse_address`, :func:`street_key`;
* :func:`parse_parcels`, :func:`parcel_id`;
* :func:`merge_duplicates` – optional helper for the build stage (same id → one record).

Guiding principle: *never guess silently*.  Every heuristic that changes or infers a value
adds a short, user-facing Polish note to ``warnings``; the untouched source text is always
kept next to the interpreted value (``date_raw``, ``address.raw``, ``parcels_raw``,
``sources[].raw``).
"""

from __future__ import annotations

import calendar
import datetime as _dt
import json
import re
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from . import baipp
from .classify import classify
from .textutil import cell_to_str, collapse_ws, fold, is_blank, tidy_cell

__all__ = [
    "TERYT_PRAGA_POLUDNIE",
    "applicant_type",
    "clean_applicant",
    "clean_number",
    "merge_duplicates",
    "normalize_row",
    "parcel_id",
    "parse_address",
    "parse_case_sign",
    "parse_date",
    "parse_decision_number",
    "parse_parcels",
    "record_id",
    "redact_persons",
    "fix_street_typos",
    "street_key",
]

TERYT_PRAGA_POLUDNIE = "146507_8"
PERSON_REDACTED = "osoba fizyczna (dane usunięte)"

_OBREBY_FILE = Path(__file__).with_name("data") / "praga_poludnie_obreby.json"
#: The cadastral precincts (obręby) that exist in Praga-Południe, as 4-digit ULDK codes (``"0524"`` = 3-05-24).
#: Not every code between 3-01-… and 3-07-… exists (3-05-16, 3-07-07 do not), so a code outside this set is a
#: typo of the source or the register. Generated from ULDK by ``scripts/pp_obreby.py``.
PP_OBREBY: frozenset[str] = frozenset(json.loads(_OBREBY_FILE.read_text(encoding="utf-8"))["obreby"])


def is_pp_obreb(code: str | None) -> bool:
    """True for the 4-digit ULDK code of a real Praga-Południe precinct (``"0524"``; not ``"0516"``)."""
    return code in PP_OBREBY

#: JRWA symbols used in case signs of initiated proceedings.
JRWA_PROCEDURE = {"6730": "wz", "6733": "cp"}
#: Obvious typos seen in case signs (leading "6" dropped) → corrected symbol (with a warning).
JRWA_TYPOS = {"730": "6730", "733": "6733"}

DATE_SANITY_DAYS = 62
_HOUSING_TAGS = {"jednorodzinny", "wielorodzinny", "adaptacja-mieszkalna"}


# =========================================================================== numbers / ids


def clean_number(value: Any) -> str:
    """Decision number / case sign as printed, with all whitespace removed.

    Signs never contain meaningful spaces; the files wrap them across lines
    (``"UD-VI-WAB-\\nU.6730.36.2026.AZM"``) or pad them (``"18/WZ/PPd/20      "``).
    """
    return re.sub(r"\s+", "", cell_to_str(value))


def parse_decision_number(number: str) -> dict[str, Any]:
    """Split a WZ/CP decision number like ``15/PPD/WZ/2026`` into its parts.

    Returns ``{"seq": int|None, "year": int|None, "year_raw": str|None, "type": "wz"|"cp"|None}``.
    ``year`` is None when absent (``19/WZ/PPD``) or implausible (``42/WZ/PPd/23021``).
    Two-digit years are expanded (``18/WZ/PPd/20`` → 2020).
    """
    n = clean_number(number)
    out: dict[str, Any] = {"seq": None, "year": None, "year_raw": None, "type": None}
    m = re.match(r"(\d+)", n)
    if not m:
        return out
    out["seq"] = int(m.group(1))
    rest = n[m.end():]
    t = re.search(r"(WZ|CP)", rest, re.I)
    if t:
        out["type"] = t.group(1).lower()
    y = re.search(r"(\d+)\D*$", rest)
    if y:
        out["year_raw"] = y.group(1)
        raw = y.group(1)
        if len(raw) == 4 and 1990 <= int(raw) <= 2100:
            out["year"] = int(raw)
        elif len(raw) == 2:
            out["year"] = 2000 + int(raw)
    return out


def parse_case_sign(sign: str) -> dict[str, Any]:
    """Split a case sign like ``UD-VI-WAB-U.6730.29.2026.AKU``.

    Returns ``{"jrwa": str|None, "seq": int|None, "year": int|None, "jrwa_raw": str|None}``;
    ``jrwa`` is the corrected symbol (``730`` → ``6730``), ``jrwa_raw`` what was printed.
    """
    n = clean_number(sign)
    out: dict[str, Any] = {"jrwa": None, "jrwa_raw": None, "seq": None, "year": None}
    m = re.search(r"(?<!\d)(\d{3,4})\.(\d{1,5})\.(\d{4})(?!\d)", n)
    if not m:
        return out
    out["jrwa_raw"] = m.group(1)
    out["jrwa"] = JRWA_TYPOS.get(m.group(1), m.group(1))
    out["seq"] = int(m.group(2))
    out["year"] = int(m.group(3))
    return out


def _infer_kind(number: str) -> str | None:
    if parse_case_sign(number)["jrwa"] or re.search(r"WAB|UD-", number, re.I):
        return "ws"
    return parse_decision_number(number)["type"]


def record_id(kind: str | None, number: str, date_iso: str | None, file_id: str,
              excel_row: int) -> tuple[str, list[str]]:
    """Stable, URL-safe record id plus warnings explaining any fallback.

    * ``wz``/``cp``: ``<kind>-<year>-<seq>`` (year from the number, else from the date);
    * ``ws``: ``ws-<jrwa>-<year>-<seq>``;
    * fallback ``<kind>-f<file_id>-r<excel_row>`` when the number cannot be parsed.
    """
    warnings: list[str] = []
    k = kind or "x"
    n = clean_number(number)
    fallback = f"{k}-f{file_id}-r{excel_row}"
    if not n:
        warnings.append("brak numeru decyzji/znaku sprawy – identyfikator nadany z pozycji w pliku")
        return fallback, warnings

    date_year = int(date_iso[:4]) if date_iso else None
    if kind == "ws":
        cs = parse_case_sign(n)
        if cs["seq"] is None:
            warnings.append("nie rozpoznano znaku sprawy – identyfikator nadany z pozycji w pliku")
            return fallback, warnings
        if cs["jrwa_raw"] != cs["jrwa"]:
            warnings.append(f"symbol JRWA „{cs['jrwa_raw']}” w znaku sprawy potraktowano jako "
                            f"{cs['jrwa']} (prawdopodobna literówka)")
        if date_year is not None and cs["year"] > date_year:
            warnings.append(f"rok w znaku sprawy ({cs['year']}) jest późniejszy niż data wszczęcia")
        return f"ws-{cs['jrwa']}-{cs['year']}-{cs['seq']}", warnings

    dn = parse_decision_number(n)
    if dn["seq"] is None:
        warnings.append("nie rozpoznano numeru decyzji – identyfikator nadany z pozycji w pliku")
        return fallback, warnings
    if dn["type"] and kind in ("wz", "cp") and dn["type"] != kind:
        warnings.append(f"numer decyzji wskazuje na {dn['type'].upper()}, a plik na {kind.upper()}")
    year = dn["year"]
    if year is None:
        if dn["year_raw"]:
            warnings.append(f"nieprawidłowy rok w numerze decyzji („{dn['year_raw']}”) – przyjęto rok z daty")
        else:
            warnings.append("brak roku w numerze decyzji – przyjęto rok z daty")
        if date_year is None:
            warnings.append("brak daty – identyfikator nadany z pozycji w pliku")
            return fallback, warnings
        year = date_year
    elif date_year is not None and year != date_year:
        warnings.append(f"rok w numerze decyzji ({year}) różni się od roku daty ({date_year})")
    return f"{kind or dn['type'] or k}-{year}-{dn['seq']}", warnings


# =========================================================================== dates


def _period_bounds(period: str | None) -> tuple[_dt.date, _dt.date] | None:
    m = re.fullmatch(r"(\d{4})-(\d{2})", period or "")
    if not m:
        return None
    y, mo = int(m.group(1)), int(m.group(2))
    if not 1 <= mo <= 12:
        return None
    return _dt.date(y, mo, 1), _dt.date(y, mo, calendar.monthrange(y, mo)[1])


def parse_date(value: Any, period: str | None = None) -> tuple[str | None, str, list[str]]:
    """Parse a decision/initiation date → ``(iso | None, date_raw, warnings)``.

    Accepts datetimes and strings such as ``09.07.2026r.``, ``2020.09.23``, ``24.07.2026 r.``,
    ``2021-01-08.``, ``22.06.2023R.``.  When ``period`` (``YYYY-MM``) is given, a date more than
    62 days outside that month is flagged.
    """
    warnings: list[str] = []
    date_raw = collapse_ws(cell_to_str(value))
    d: _dt.date | None = None
    if value is None or is_blank(value):
        return None, "", ["brak daty"]
    if isinstance(value, _dt.datetime):
        d = value.date()
    elif isinstance(value, _dt.date):
        d = value
    elif isinstance(value, (int, float)) and not isinstance(value, bool):
        if 20000 < value < 80000:  # Excel serial day number
            d = _dt.date(1899, 12, 30) + _dt.timedelta(days=int(value))
            warnings.append("data zapisana w pliku jako liczba – przeliczono")
    else:
        s = date_raw
        suffix = r"\s*(?:r\.?|R\.?)?\s*\.?\s*"
        m = re.fullmatch(r"(\d{1,2})\s*[.\-/]\s*(\d{1,2})\s*[.\-/]\s*(\d{4})" + suffix, s)
        order = "dmy"
        if not m:
            m = re.fullmatch(r"(\d{4})\s*[.\-/]\s*(\d{1,2})\s*[.\-/]\s*(\d{1,2})" + suffix, s)
            order = "ymd"
        if not m:  # tolerate surrounding text, but say so
            m = re.search(r"(?<!\d)(\d{1,2})[.\-/](\d{1,2})[.\-/](\d{4})(?!\d)", s)
            order = "dmy"
            if not m:
                m = re.search(r"(?<!\d)(\d{4})[.\-/](\d{1,2})[.\-/](\d{1,2})(?!\d)", s)
                order = "ymd"
            if m:
                warnings.append(f"data z dodatkowym tekstem („{s}”)")
        if m:
            a, b, c = (int(x) for x in m.groups())
            y, mo, da = (c, b, a) if order == "dmy" else (a, b, c)
            try:
                d = _dt.date(y, mo, da)
            except ValueError:
                d = None
    if d is None:
        return None, date_raw, [f"nie rozpoznano daty („{date_raw}”)"]

    bounds = _period_bounds(period)
    if bounds:
        lo, hi = bounds
        gap = (lo - d).days if d < lo else (d - hi).days if d > hi else 0
        if gap > DATE_SANITY_DAYS:
            warnings.append(f"data {d.isoformat()} odbiega o {gap} dni od okresu sprawozdawczego {period}")
    return d.isoformat(), date_raw, warnings


# =========================================================================== applicant / privacy

_CAP = r"[A-ZĄĆĘŁŃÓŚŹŻ][\w’'\-]+"
_PERSON_RE = re.compile(
    r"\b(?:Pan|Pani|Panią|Pana|Panu|Panem|Państwo|Państwa|Państwu)\s+"
    rf"{_CAP}(?:\s+(?:i\s+)?{_CAP})*"
)


def redact_persons(text: str) -> str:
    """Replace explicit natural-person names ("Pani Agata X") with a neutral marker.

    Company / institution names are left alone; only the Pan/Pani/Państwo + Capitalised-words
    pattern is redacted (see DATA_MODEL.md → Privacy).
    """
    if not text or "Pa" not in text:
        return text
    return _PERSON_RE.sub(PERSON_REDACTED, text)


def clean_applicant(value: Any) -> str:
    """Applicant name, single-spaced, privacy-redacted; wording otherwise as printed."""
    return redact_persons(collapse_ws(cell_to_str(value)))


def applicant_type(applicant: str) -> str:
    """``person`` for "osoba fizyczna"/"osoby fizyczne" (any case/spacing, also redacted names),
    ``organization`` for any other non-empty name, ``unknown`` when empty."""
    f = collapse_ws(fold(applicant))
    if not f:
        return "unknown"
    if re.match(r"^(?:osob[aey]|osobom)\s+fizyczn", f):
        return "person"
    return "organization"


# =========================================================================== address

_DISTRICT_RE = re.compile(
    r"(?:\bdzielnic\w*\s+)?\bprag\w*\s*-?\s*(?:p\s*o\s*l\s*u\s*d\s*n\w*|pld\.?|pd\.?)(?![a-z])"
)
_CITY_RE = re.compile(r"(?:\bw\s+)?\bwarszaw\w*|\bm\.\s*st\.\s*")
_QUOTES_RE = re.compile(r"[\"„”“«»]")
_APPROX_RE = re.compile(r"\b(?:w\s+)?rejon\w*|\bna\s+wysokosci\b|\bokolic\w*|\bna\s+terenie\b")
# "ul."/"al." prefixes – a dot or a space is required, so "Ulrychowska"/"Algierska" stay intact
_STREET_PREFIX_RE = re.compile(r"^(?:ul\.|ulica\b|ulicy\b|al\.|aleja\b|alei\b|ul\s|al\s)\s*", re.I)
_HOUSE_RE = re.compile(r"^(\d+[A-Za-z]?(?:\s*/\s*\d+[A-Za-z]?)?)")


def _strip_quotes(s: str) -> str:
    return _QUOTES_RE.sub(" ", s)


def _clean_address_line(line: str) -> str:
    """Remove district/city, fix abbreviation dots, glued numbers and hyphen spacing."""
    f = fold(line)
    spans = [m.span() for m in _DISTRICT_RE.finditer(f)] + [m.span() for m in _CITY_RE.finditer(f)]
    if spans:
        chars = list(line)
        for a, b in spans:
            for i in range(a, b):
                chars[i] = " "
        line = "".join(chars)
    line = _strip_quotes(line)
    line = re.sub(r"\b([^\W\d_]{1,3})\.(?=[^\W\d_])", r"\1. ", line)   # T.Zana → T. Zana
    line = re.sub(r"(?<=[^\W\d_]{3})(?=\d)", " ", line)                    # Lubartowska23 → Lubartowska 23
    line = re.sub(r"(?<=\d)\s+([A-HJ-NP-VX-Ya-hj-np-vx-y])(?![\w.])", r"\1", line)  # 16 A → 16A
    line = re.sub(r"(?<=[^\W\d_])\s*-\s*(?=[^\W\d_])", "-", line)           # Nowaka - Jeziorańskiego
    line = re.sub(r"\s*,\s*", ", ", line)
    line = re.sub(r"\s*/\s*", "/", line)
    line = collapse_ws(line).strip(" ,;/-")
    return line


def _nominative(word_group: str) -> str:
    """Very small genitive → nominative heuristic for "w rejonie ul. Chodakowskiej" style text."""
    words = word_group.split()
    if not words:
        return word_group
    if fold(words[0]) == "pasazu":          # "na wysokości Pasażu Złotej Wilgi"
        words[0] = words[0][:-1]
    last = words[-1]
    for gen, nom in (("skiej", "ska"), ("ckiej", "cka"), ("dzkiej", "dzka"), ("nej", "na"),
                     ("wej", "wa"), ("iej", "ia")):
        if last.lower().endswith(gen) and len(last) > len(gen) + 2:
            words[-1] = last[: -len(gen)] + nom
            break
    return " ".join(words)


def _split_streets(text: str) -> list[str]:
    """Split "A 1/B", "A 2 róg B", "A i B", "A, B", "A oraz B" into street chunks.

    Separators are only honoured when followed by a word (so "4 i 4A", "21, 23" and "46/48"
    stay attached to their street as house-number lists).
    """
    word = r"(?=\s*(?:ul\.?\s+|al\.?\s+|gen\.?\s+)?[^\W\d_]{2})"
    parts = re.split(rf"\s*\|\s*|\s*/{word}\s*|\s*,{word}\s*|\s+(?:i|oraz|róg|rog|I){word}\s+|\s*;\s*", text)
    parts = [re.sub(r"\s+(?:i|oraz|róg|rog)$", "", p.strip(" ,;/")) for p in parts if p]
    return [p for p in parts if p]


def _address_lines(text: str) -> list[str]:
    """Cleaned lines of a tidied address cell; wrapped text is joined back to its line."""
    lines: list[str] = []
    for line in text.split("\n"):
        cleaned = _clean_address_line(line)
        if not cleaned:
            continue
        continuation = lines and (
            line.lstrip()[:1] in "„\"“”"                                   # „Nila” on its own line
            or re.search(r"(?:\s(?:i|oraz|róg)|[/,]|\bna odcinku)$", lines[-1])   # "… oraz" ⏎ "Pasaż …"
            or (re.match(r"^[a-ząćęłńóśźż]", cleaned)
                and not re.match(r"^(?:ul|al|gen|ks|pl|os|rejon|w\s|na\s(?!odcinku))", cleaned)))
        if continuation:
            joiner = "" if lines[-1].endswith("/") else " "
            lines[-1] = f"{lines[-1]}{joiner}{cleaned}"   # wrapped text continues
        else:
            lines.append(cleaned)
    return lines


_STRETCH_RE = re.compile(r"\bna\s+odcinku\b", re.I)


def _stretch_streets(text: str) -> str:
    """Streets of a road stretch, one per line (BAiPP linear investments, e.g. tram lines).

    ``"al. Stanów Zjednoczonych na odcinku od ul. Bajońskiej do ul. Międzynarodowej"`` →
    ``"al. Stanów Zjednoczonych\nul. Bajońskiej\nul. Międzynarodowej"`` (the genitive is turned into the
    nominative later); ``"osiedle Saska Kępa na odcinku A – B"`` → ``"A\nB"`` (an estate is no street).
    """
    flat = collapse_ws(text.replace("\n", " "))
    m = _STRETCH_RE.search(flat)
    if not m:
        return text
    head = flat[:m.start()].strip(" ,;")
    tail = re.sub(r"(?i)^\s*od\s+", "", flat[m.end():])
    ends = [e.strip(" ,;") for e in re.split(r"\s+(?:[-–—]|do)\s+", tail, maxsplit=1)]
    keep_head = head and not re.match(r"(?i)^(?:osiedl\w*|os\.)\s", head)
    return "\n".join([head] * bool(keep_head) + [e for e in ends if e])


def parse_address(raw: Any, warnings: list[str] | None = None) -> dict[str, Any]:
    """Parse the "ulica, dzielnica" cell.

    Returns ``{"raw", "street", "number", "display", "parts", "approximate"}``:

    * ``street`` – first street, without "ul."/"al." (``None`` if none recognised);
    * ``number`` – its first house number ("25", "3A", "46/48"), unit suffixes like
      "nr 419" / "lok. U6" / "/U4" are dropped from it (kept in ``display``);
    * ``parts`` – every ``{"street", "number", "numbers"}`` found (intersections, lists);
    * ``display`` – the cleaned text for humans ("Lubartowska 23 i Serocka 21"); ``street``/``parts`` use the
      one spelling of :data:`STREET_CANONICAL` ("Jerzego Waszyngtona" → "Waszyngtona");
    * ``approximate`` – text describes an area ("w rejonie ul. …", "na wysokości …") or a stretch of
      road ("al. Waszyngtona na odcinku Międzynarodowa – Kinowa": parts = the road and both ends).

    Known street misspellings are corrected in ``street``/``parts`` (not in ``display``); a note
    is appended to ``warnings`` when a list is passed.
    """
    raw_s = cell_to_str(raw) if raw is not None else ""
    out: dict[str, Any] = {"raw": raw_s, "street": None, "number": None, "display": "",
                           "parts": [], "approximate": False}
    if is_blank(raw_s):
        return out
    tidy = tidy_cell(raw_s)
    stretch = _STRETCH_RE.search(tidy)
    if stretch:   # "X na odcinku A - B": keep the dash between the ends visible ("A – B")
        tidy = tidy[:stretch.end()] + re.sub(r"[^\S\n]+-[^\S\n]+", " – ", tidy[stretch.end():])
    lines = _address_lines(tidy)
    if not lines:
        return out
    text = " | ".join(lines)
    display = re.sub(r"\s*\|\s*(?=[\d])", ", ", text)   # line starting with a number continues
    display = re.sub(r"\s*\|\s*", " / ", display)
    display = re.sub(r"(?<=[^\W\d_])/(?=[^\W\d_])", " / ", display)
    display = re.sub(r"(?<=\d)/(?=[^\W\d_]{2})", " / ", display)
    display = re.sub(r"(?:(?<=^)|(?<=/ ))(?:ul\.?|ulica)\s+", "", display, flags=re.I)
    display = re.sub(r"^(?:Al\.|AL\.)\s*", "al. ", display)
    out["display"] = display.strip()

    f = fold(text)
    approximate = bool(_APPROX_RE.search(f)) or bool(stretch)
    out["approximate"] = approximate
    work = text
    if stretch:
        work = " | ".join(_address_lines(_stretch_streets(tidy)))
    elif approximate:
        # keep the part that names streets: from the first "ul."/"ulicy"/"al." marker on
        m = re.search(r"\b(?:ul\.|ulicy|ulica|al\.|alei|aleja)\s*", work, re.I)
        if m:
            work = work[m.start():]
        work = re.sub(r"(?i)\b(?:w\s+)?rejon\w*|\bna\s+wysokości\b|\bna\s+terenie\b.*$|\bokolic\w*", " ", work)
    work = re.sub(r"\([^)]*\)", " ", work)               # "(Kozia Górka)" → only in display

    parts: list[dict[str, Any]] = []
    chunks = _split_streets(work)
    # "dawna Siennicka 48 / Drwęcka": the former address goes last
    chunks = [c for c in chunks if not re.match(r"(?i)dawn", c)] + [c for c in chunks if re.match(r"(?i)dawn", c)]
    for chunk in chunks:
        chunk = re.sub(r"(?i)^dawn\w*\s+", "", chunk)
        chunk = _STREET_PREFIX_RE.sub("", chunk.strip())
        m = re.match(r"^(?P<street>.*?[^\W\d_][.\-’']?)\s*(?P<nums>\d.*)?$", chunk)
        if not m:
            nums = chunk
            if parts and re.match(r"^\d", nums):  # bare numbers continue the previous street
                parts[-1]["numbers"].extend(_house_numbers(nums))
            continue
        street = collapse_ws(m.group("street")).strip(" ,.-")
        if approximate:
            street = _nominative(street)
        if not street or not re.search(r"[^\W\d_]{2}", street):
            continue
        fixed = fix_street_typos(street)
        if fixed != street:
            if warnings is not None:
                warnings.append(f"poprawiono pisownię ulicy: „{street}” → „{fixed}”")
            street = fixed
        street = canonical_street(street)   # "Jana Nowaka Jeziorańskiego" → "Nowaka-Jeziorańskiego" (display kept)
        numbers = _house_numbers(m.group("nums") or "")
        key = street_key(street)
        dup = next((p for p in parts if street_key(p["street"]) == key), None)
        if dup:
            dup["numbers"].extend(n for n in numbers if n not in dup["numbers"])
            continue
        parts.append({"street": street, "numbers": numbers})
    for p in parts:
        p["number"] = p["numbers"][0] if p["numbers"] else None
    out["parts"] = [{"street": p["street"], "number": p["number"], "numbers": p["numbers"]} for p in parts]
    if parts:
        out["street"] = parts[0]["street"]
        out["number"] = parts[0]["number"]
    return out


def _house_numbers(text: str) -> list[str]:
    """House numbers in a list: ``21,23`` → 21, 23; ``4 i 4A`` → 4, 4A; ``4A nr 419`` → 4A; ``12/U4`` → 12."""
    out: list[str] = []
    for piece in re.split(r"\s*(?:,|\bi\b|\boraz\b)\s*", text):
        m = _HOUSE_RE.match(piece.strip())
        if m:
            num = re.sub(r"\s+", "", m.group(1))
            if num not in out:
                out.append(num)
    return out


_TITLES = {
    "ul", "ulica", "ulicy", "al", "aleja", "alei", "pl", "plac", "os", "osiedle", "gen", "generala",
    "general", "ks", "ksiedza", "sw", "sw.", "swietego", "swietej", "marsz", "marszalka", "prof",
    "profesora", "dr", "doktora", "kard", "kardynala", "abp", "bp", "plk", "pulkownika", "mjr",
    "majora", "kpt", "kapitana", "por", "porucznika", "hr", "im", "imienia",
}
#: Misspellings found in the 2020–2026 files (folded word → correct spelling).  Applied to the
#: normalised ``street`` (with a warning) and to :func:`street_key`; ``display`` keeps the source text.
STREET_TYPOS = {
    "chdakowska": "Chodakowska",
    "meisssnera": "Meissnera",
    "borlemowska": "Boremlowska",
    "feildorfa": "Fieldorfa",
    "fieldora": "Fieldorfa",
    "jugoslowanianska": "Jugosłowiańska",
    "jugoslawianska": "Jugosłowiańska",
    "sygietynska": "Sygietyńskiego",
}
_FIRST_NAMES = {
    "jana", "romana", "stanislawa", "tomasza", "floriana", "ignacego", "augusta", "emila",
    "wincentego", "wladyslawa", "jozefa", "adama", "stefana", "tadeusza", "kazimierza",
    "franciszka", "juliana", "ludwika", "jakuba", "antoniego", "witolda", "zygmunta", "henryka",
    "karola", "piotra", "pawla", "michala", "andrzeja", "jerzego", "marii", "anny", "stanislawy",
    "janusza",
}
# whole-key aliases: the street of gen. August Emil Fieldorf "Nil" is written with and without the pseudonym
_STREET_ALIASES = {
    "fieldorfa nila": "fieldorfa",
    "nila fieldorfa": "fieldorfa",
}
#: One spelling per street for ``address.street`` / ``parts[].street`` (the site's street filter groups by the
#: spelling): :func:`street_key` → the name as most records write it, without first names, titles or initials
#: (TERYT: "gen. Augusta Emila Fieldorfa „Nila”", "al. Jerzego Waszyngtona" …). Hand-kept like STREET_TYPOS –
#: the report lists streets still written several ways. ``display`` and ``raw`` keep the source text.
STREET_CANONICAL = {
    "abrahama": "Abrahama",                      # gen. Romana Abrahama, Generała Abrahama
    "augusta": "Stanisława Augusta",             # St. Augusta (the key drops the first name; the street keeps it)
    "bora komorowskiego": "Bora-Komorowskiego",  # gen. T. Bora-Komorowskiego, Bora Komorowskiego
    "domeyki": "Domeyki",                        # Ignacego Domeyki
    "fieldorfa": "Fieldorfa",                    # Fieldorfa Nila, gen. A. E. Fieldorfa Nila, Augusta Emila Fieldorfa
    "meissnera": "Meissnera",                    # Janusza Meissnera
    "mikolajczyka": "Mikołajczyka",              # St. Mikołajczyka
    "nowaka jezioranskiego": "Nowaka-Jeziorańskiego",   # Jana Nowaka Jeziorańskiego
    "rogalskiego": "Rogalskiego",                # Stanisława / St. Rogalskiego
    "rychtera": "Rychtera",                      # W. Rychtera
    "skalskiego": "Skalskiego",                  # gen. Stanisława Skalskiego
    "sztuki": "Sztuki",                          # Ks. Jana Sztuki
    "uminskiego": "Umińskiego",                  # Władysława Umińskiego
    "waszyngtona": "Waszyngtona",                # Jerzego Waszyngtona
    "zana": "Zana",                              # T. Zana
    "znanieckiego": "Znanieckiego",              # Floriana Znanieckiego
}


def fix_street_typos(street: str) -> str:
    """Correct the known misspellings in :data:`STREET_TYPOS` word by word."""
    def _fix(m: re.Match[str]) -> str:
        return STREET_TYPOS.get(fold(m.group(0)), m.group(0))
    return re.sub(r"[^\W\d_]+", _fix, street)


def street_key(street: str | None) -> str:
    """Folded matching key for a street name: no diacritics, titles, initials or first names.

    >>> street_key("ul. Gen. Bora-Komorowskiego")
    'bora komorowskiego'
    >>> street_key("Jana Nowaka - Jeziorańskiego") == street_key("Nowaka-Jeziorańskiego")
    True
    >>> street_key("St. Augusta") == street_key("Stanisława Augusta")
    True
    """
    if not street:
        return ""
    s = fold(_strip_quotes(fix_street_typos(street)))
    # initials ("T.", "St.", "A.E.") – short tokens followed by a dot
    s = re.sub(r"\b[a-z]{1,2}\.", " ", s)
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    words = [w for w in s.split() if w not in _TITLES]
    # drop leading first names when a surname follows ("jana nowaka jezioranskiego")
    while len(words) > 1 and words[0] in _FIRST_NAMES:
        words.pop(0)
    key = " ".join(words)
    return _STREET_ALIASES.get(key, key)


def canonical_street(street: str | None) -> str | None:
    """The one spelling of a street used in ``address.street`` (:data:`STREET_CANONICAL`), else ``street``.

    >>> canonical_street("gen. A. E. Fieldorfa Nila"), canonical_street("St. Augusta")
    ('Fieldorfa', 'Stanisława Augusta')
    """
    if not street:
        return street
    return STREET_CANONICAL.get(street_key(street), street)


# =========================================================================== parcels

_OBREB_RE = re.compile(r"(?<![\d/])(?P<a>30|3)\s*-\s*(?P<b>\d{1,2})\s*-\s*(?P<c>0?\d{2})(?![\d/])")
# BAiPP lists cover the whole city: obręby of every Warsaw zone (1-…8-, e.g. Praga-Północ "4-15-08").
_OBREB_ANY_RE = re.compile(r"(?<![\d/])(?P<a>30|[1-8])\s*-\s*(?P<b>\d{1,2})\s*-\s*(?P<c>0?\d{2})(?![\d/])")
# "3-05-2;" – an obręb with its last part cut short; its parcels cannot be placed.
_OBREB_CUT_RE = re.compile(r"(?<![\d/])(?:30|3)\s*-\s*\d{2}\s*-\s*\d(?![\d/])")
_OBREB_CUT_ANY_RE = re.compile(r"(?<![\d/])(?:30|[1-8])\s*-\s*\d{2}\s*-\s*\d(?![\d/])")
_TOKEN_RE = re.compile(r"\d+(?:\s*/\s*\d+)?|[a-z]+\.?|[^\sa-z\d]")
_PARTIAL_WORDS = {"cz", "cz.", "czesc", "czesc.", "czesci", "czesci."}
_NOISE_WORDS = {
    "dz", "dz.", "dzialka", "dzialki", "dzialek", "dzialkach", "ew", "ew.", "ewid", "ewid.", "nr",
    "nr.", "obr", "obr.", "obreb", "obrebu", "obrebie", "z", "i", "oraz", "na", "ul", "ul.", "w",
    "nieruchomosc", "nieruchomosci", "numer", "numery",
}
_RESET_WORDS = {"dz", "dz.", "dzialka", "dzialki", "dzialek"}


def parcel_id(obreb: str, number: str) -> str:
    """ULDK id: ``146507_8.<obreb without leading '3-' and dashes>.<number>``.

    >>> parcel_id("3-01-24", "46/4")
    '146507_8.0124.46/4'
    """
    return f"{TERYT_PRAGA_POLUDNIE}.{obreb[2:].replace('-', '')}.{number}"


def _blank_spans(text: str, spans: Iterable[tuple[int, int]]) -> str:
    chars = list(text)
    for a, b in spans:
        for i in range(a, b):
            chars[i] = " "
    return "".join(chars)


def parse_parcels(raw: Any, street_hint: str | None = None, *,
                  any_obreb: bool = False) -> tuple[list[dict[str, Any]], list[str]]:
    """Parse the "nr dz. ew., obręb" cell into parcels.

    Returns ``(parcels, warnings)`` where each parcel is
    ``{"number": "46/4", "obreb": "3-01-24", "partial": bool, "id": "146507_8.0124.46/4"}``
    plus ``"access": True`` for parcels listed after "z dojazdem poprzez" (access road).
    With ``any_obreb`` (city-wide BAiPP lists) obręby of every Warsaw zone are read (``4-15-08``);
    their id still assumes Praga-Południe – :func:`pipeline.baipp.check_out_of_district` corrects it.

    Rules (derived from every variant in the 2020–2026 files):

    * an obręb ``3-XX-XX`` closes the list of parcels written before it, so
      ``"3/27,…,3/93  3-03-06  2,1,5/2  3-03-07"`` yields two groups; parcels written after the
      last obręb inherit it (with a warning);
    * partial markers: suffix (``16-cz``, ``4/42-cz.``, ``2/1 cz.``, ``2/5cz.``, ``8/4-część``,
      ``32/26 (cz.)``) marks one parcel; a prefix (``cz.``, ``część dz.``, ``na części dz.``) marks every
      following parcel of the group until "dz." is repeated;
    * former numbers ("(dawnej 14)", "dawnej 3") and comments in parentheses are ignored; the current
      numbers of a subdivided parcel, ``3-cz. (obecnie 3/1, 3/3)``, replace it (they inherit its partial
      flag; warning); a number cut short (``12/;``) gets ``incomplete: true`` and a warning;
    * a ``3-…`` obręb that does not exist in Praga-Południe (:data:`PP_OBREBY`, e.g. ``3-05-16``) gets a warning;
    * obvious obręb typos ("30-05-11", "3-04-012") are corrected with a warning;
    * anything else that is not understood is reported, never silently guessed.
    """
    raw_s = cell_to_str(raw) if raw is not None else ""
    warnings: list[str] = []
    if is_blank(raw_s):
        return [], warnings
    text = collapse_ws(raw_s)
    work = fold(text)                      # same length as `text`

    # 1. parentheses: unwrap "(3-02-06)" and the partial marker "32/26 (cz.)", mark "(obecnie 3/1, 3/3)" (the
    #    current numbers of the parcel before it) with brackets, drop "(dawnej 14)" / comments
    def _paren(m: re.Match[str]) -> str:
        inner = m.group(1)
        if _OBREB_RE.search(inner) or inner.strip() in _PARTIAL_WORDS:
            return " " + inner + " "
        if re.match(r"\s*obecnie\b", inner):
            return "[" + inner + "]"
        return " " * len(m.group(0))  # former number / comment – kept in parcels_raw only
    work = re.sub(r"\(([^()]*)\)", _paren, work)
    # 2. unparenthesised former numbers: "3/11 dawnej 3 3-02-03"
    work = _blank_spans(work, (m.span() for m in re.finditer(r"\bdawn\w*\s*\d+(?:\s*/\s*\d+)?", work)))
    # 3. access-road marker
    access_at = None
    m = re.search(r"\bz?\s*dojazd\w*(?:\s+(?:poprzez|porzez|przez))?", work)
    if m:
        access_at = m.start()
        work = _blank_spans(work, [m.span()])

    # 4. "60/25.1", "23/1.23/2": a dot between two numbers can only be a list separator
    def _dot(m: re.Match[str]) -> str:
        warnings.append(f"kropkę w „{collapse_ws(m.group(0))}” potraktowano jako separator działek")
        return f"{m.group(1)},{m.group(2)}"
    work = re.sub(r"(\d+(?:\s*/\s*\d+)?)\.(\d+(?:\s*/\s*\d+)?)", _dot, work)

    # 5. obręby (an obręb cut short, "3-05-2", closes its list too – those parcels cannot be placed)
    obreby: list[tuple[int, int, str | None]] = []
    for m in (_OBREB_ANY_RE if any_obreb else _OBREB_RE).finditer(work):
        a, b, c = m.group("a"), m.group("b"), m.group("c")
        zone = "3" if a == "30" else a
        norm = f"{zone}-{int(b):02d}-{int(c):02d}"
        if a == "30" or len(c) != 2 or len(b) != 2:
            warnings.append(f"poprawiono zapis obrębu „{text[m.start():m.end()]}” na {norm}")
        obreby.append((m.start(), m.end(), norm))
    for m in (_OBREB_CUT_ANY_RE if any_obreb else _OBREB_CUT_RE).finditer(work):
        if not any(a <= m.start() < b for a, b, _ in obreby):
            obreby.append((m.start(), m.end(), None))
    obreby.sort()

    unknown: list[str] = []
    hint = street_key(street_hint) if street_hint else ""

    def _scan(seg_start: int, seg_end: int, obreb: str | None) -> list[dict[str, Any]]:
        """Parcels written in work[seg_start:seg_end] (all belonging to ``obreb``)."""
        found: list[dict[str, Any]] = []
        tokens = [(t.group(0), t.start() + seg_start, t.end() + seg_start)
                  for t in _TOKEN_RE.finditer(work[seg_start:seg_end])]
        prefix_mode = False          # a leading "cz."/"część dz." marks following parcels
        last: dict[str, Any] | None = None
        last_end = -1
        sep_since_last = True        # a separator occurred since the last parcel number
        replaced: dict[str, Any] | None = None   # "3-cz. (obecnie 3/1, 3/3)": the parcel the numbers replace
        current: list[dict[str, Any]] = []
        for idx, (tok, a, b) in enumerate(tokens):
            nxt = tokens[idx + 1][0] if idx + 1 < len(tokens) else ""
            if tok[0].isdigit():
                last = {"number": re.sub(r"\s+", "", tok), "obreb": obreb, "partial": prefix_mode,
                        "access": access_at is not None and a > access_at}
                if re.match(r"\s*/(?!\s*\d)", work[b:seg_end]):        # "12/;" – the number is cut short
                    last["incomplete"] = True
                    warnings.append(f"niepełny numer działki „{text[a:b]}/” w źródle")
                if replaced is not None:
                    last["partial"] = last["partial"] or replaced["partial"]
                    current.append(last)
                found.append(last)
                last_end, sep_since_last = b, False
            elif tok == "obecnie" and idx and tokens[idx - 1][0] == "[" and last is not None and replaced is None:
                replaced, current = last, []
            elif tok == "]" and replaced is not None:
                if current:
                    found.remove(replaced)
                    warnings.append(f"działka {replaced['number']} – w źródle podano jej obecne numery: "
                                    f"{', '.join(p['number'] for p in current)}")
                replaced = None
            elif tok in _PARTIAL_WORDS:
                gap = work[last_end:a] if last is not None else ""
                attached = last is not None and not sep_since_last and (gap == "" or "-" in gap)
                spaced_suffix = (last is not None and not sep_since_last and not gap.strip()
                                 and not nxt[:1].isdigit())
                if attached or spaced_suffix:      # "16-cz", "2/5cz.", "10/10 cz."
                    last["partial"] = True
                else:                              # "cz. 7,12", "część dz. 43/4"
                    prefix_mode = True
            elif tok in _NOISE_WORDS:
                if tok in _RESET_WORDS and found:  # "cz. dz.1, 13/5, dz. 13/2" → new group
                    prefix_mode = False
                if tok in ("i", "oraz", "z", "na"):
                    sep_since_last = True
            elif tok in (",", ";", "+", "&", "."):
                sep_since_last = True
            elif tok in ("-", "/", '"', "'", ":", "*", "[", "]"):
                continue
            elif tok[0].isalpha() and hint and street_key(text[a:b]) and (
                    hint.startswith(street_key(text[a:b])) or street_key(text[a:b]) in hint.split()):
                continue                           # street name repeated in the parcels cell
            else:
                unknown.append(text[a:b])
        return found

    parcels: list[dict[str, Any]] = []
    prev = 0
    for start, end, norm in obreby:
        got = _scan(prev, start, norm)
        if norm is None:
            cut = collapse_ws(text[start:end])
            warnings.append(f"niepełny numer obrębu „{cut}” – pominięto działki zapisane przed nim"
                            + (f" ({', '.join(p['number'] for p in got)})" if got else ""))
        elif not got:
            warnings.append(f"obręb {norm} bez numerów działek")
        else:
            parcels.extend(got)
        prev = end
    tail = _scan(prev, len(work), None)
    if tail:
        if obreby and obreby[-1][2] is not None:
            last_obreb = obreby[-1][2]
            for p in tail:
                p["obreb"] = last_obreb
            warnings.append(f"działki zapisane po ostatnim obrębie przypisano do obrębu {last_obreb}")
            parcels.extend(tail)
        else:
            warnings.append("brak numeru obrębu – nie można jednoznacznie wskazać działek")

    if unknown:
        frag = collapse_ws(" ".join(unknown))
        warnings.append(f"pominięto niezrozumiały fragment oznaczenia działek: „{frag}”")

    # dedupe by id; finalise
    out: list[dict[str, Any]] = []
    by_id: dict[str, dict[str, Any]] = {}
    for p in parcels:
        pid = parcel_id(p["obreb"], p["number"])
        if pid in by_id:
            q = by_id[pid]
            q["partial"] = q["partial"] and p["partial"]   # listed whole anywhere → whole
            if q.get("access") and not p["access"]:
                q.pop("access", None)
            continue
        item = {"number": p["number"], "obreb": p["obreb"], "partial": bool(p["partial"]), "id": pid}
        if p["access"]:
            item["access"] = True
        if p.get("incomplete"):
            item["incomplete"] = True
        by_id[pid] = item
        out.append(item)
    if not out and not any("obręb" in w or "obrębu" in w for w in warnings):
        warnings.append("nie rozpoznano numerów działek")
    for obreb in dict.fromkeys(p["obreb"] for p in out):
        if obreb.startswith("3-") and not is_pp_obreb(obreb[2:].replace("-", "")):
            warnings.append(f"obręb {obreb} nie istnieje w ewidencji gruntów Pragi-Południe – możliwy błąd w źródle")
    return out, warnings


# =========================================================================== record


def _source_raw(raw_pairs: list[list[Any]]) -> list[list[str]]:
    out = []
    for label, value in raw_pairs:
        out.append([collapse_ws(label), redact_persons(tidy_cell(value))])
    return out


def normalize_row(row: dict[str, Any], kind: str | None, file_meta: dict[str, Any]) -> dict[str, Any]:
    """Normalise one parsed row into a Record (see DATA_MODEL.md; no geo/related/area yet).

    ``kind`` is the file's detected kind (``wz``/``cp``/``ws``); when ``None`` it is inferred
    from the number/sign of the row.  ``file_meta`` needs ``file_id``, ``page_id``, ``period``;
    optional ``dataset`` (``district`` – default – or ``baipp``) and, for BAiPP ULICP files,
    ``series`` (``c1``/``c2``).

    BAiPP rows (``dataset="baipp"``, already filtered to Praga-Południe by the caller) differ in:
    the number cell also holds the outcome (→ ``outcome``), ids are namespaced (``wz-am-2026-95``),
    "dane osobowe" means a natural person, the district is the last line of the address, parcels
    may lie in any Warsaw obręb zone, and ``period`` is the month of the record's own date (the
    files are yearly).
    """
    cells = row.get("cells", {})
    warnings: list[str] = list(row.get("warnings", []))
    file_id = file_meta.get("file_id", "")
    period = file_meta.get("period")
    dataset = file_meta.get("dataset") or "district"
    city = dataset == "baipp"

    number_parts = baipp.split_number(cells.get("number"), kind) if city else None
    number = number_parts.number if number_parts else clean_number(cells.get("number"))
    if number_parts and number_parts.others:
        warnings.append(f"w komórce numeru podano także: {', '.join(number_parts.others)}")
    if kind is None:
        kind = _infer_kind(number) if number else None
        if kind:
            warnings.append(f"rodzaj pozycji ({kind.upper()}) ustalono na podstawie numeru")
        else:
            warnings.append("nie ustalono rodzaju pozycji (WZ/CP/wszczęte)")

    date_iso, date_raw, w = parse_date(cells.get("date"), None if city else period)
    warnings += w
    if city:
        file_year = (period or "")[:4]
        if date_iso and file_year.isdigit() and date_iso[:4] != file_year:
            warnings.append(f"data {date_iso} spoza roku zestawienia ({file_year})")
        period = date_iso[:7] if date_iso else None

    rid, w = record_id(kind, number, date_iso, file_id, row.get("row", 0))
    warnings += w
    if city:
        rid, w = baipp.namespace_id(rid, kind, number, file_meta.get("series"))
        warnings += w

    procedure: str | None = kind if kind in ("wz", "cp") else None
    if kind == "ws":
        jrwa = parse_case_sign(number)["jrwa"]
        procedure = JRWA_PROCEDURE.get(jrwa or "")
        if jrwa and procedure is None:
            warnings.append(f"nieznany symbol JRWA {jrwa} w znaku sprawy – nie ustalono rodzaju postępowania")
    outcome, w = baipp.parse_outcome(number, number_parts.rest, kind) if number_parts else (None, [])
    warnings += w

    applicant = clean_applicant(baipp.applicant_text(cells.get("applicant")) if city else cells.get("applicant"))
    investment = redact_persons(collapse_ws(cell_to_str(cells.get("investment"))))
    if not investment:
        warnings.append("brak opisu inwestycji")

    address_cell = cells.get("address")
    address = parse_address(baipp.strip_district(address_cell) if city else address_cell, warnings)
    if city:
        address["raw"] = cell_to_str(address_cell) if address_cell is not None else ""
    parcels_raw = cell_to_str(cells.get("parcels")) if cells.get("parcels") is not None else ""
    parcels, w = parse_parcels(parcels_raw, address.get("street"), any_obreb=city)
    warnings += w

    tags = classify(investment)
    if kind == "ws" and procedure == "cp" and set(tags) & _HOUSING_TAGS:
        warnings.append("znak sprawy ma symbol 6733 (cel publiczny), a opis wskazuje na zabudowę mieszkaniową – "
                        "możliwa pomyłka w źródle")

    record = {
        "id": rid,
        "kind": kind,
        "procedure": procedure,
        "dataset": dataset,
        "issuer": "city" if city else "district",
        "outcome": outcome,
        "number": number,
        "date": date_iso,
        "date_raw": date_raw,
        "filed_date": None,
        "period": period,
        "applicant": applicant,
        "applicant_type": applicant_type(applicant),
        "investment": investment,
        "address": address,
        "parcels": parcels,
        "parcels_raw": parcels_raw,
        "tags": tags,
        "permit": None,
        "sources": [{
            "file_id": file_id,
            "page_id": file_meta.get("page_id"),
            "sheet": row.get("sheet"),
            "row": row.get("row"),
            "raw": _source_raw(row.get("raw", [])),
        }],
        "warnings": list(dict.fromkeys(warnings)),
    }
    return record


# =========================================================================== duplicates


def _content_key(r: dict[str, Any]) -> tuple[Any, ...]:
    return (r.get("date"), fold(collapse_ws(r.get("investment")))[:80])


#: Fields compared between two snapshots of a BAiPP list (label used in the warning).
_SNAPSHOT_FIELDS = {
    "number": "numer", "date": "data", "outcome": "rozstrzygnięcie", "applicant": "wnioskodawca",
    "investment": "opis inwestycji", "address": "adres", "parcels_raw": "działki",
}


def _snapshot_value(r: dict[str, Any], key: str) -> Any:
    value = r.get(key)
    if key == "address":
        value = (value or {}).get("raw")
    return collapse_ws(value) if isinstance(value, str) else value


def _source_files(r: dict[str, Any]) -> set[str]:
    return {s["file_id"] for s in r.get("sources") or []}


def _adopt_newer_snapshot(target: dict[str, Any], newer: dict[str, Any]) -> list[str]:
    """Merge ``newer`` (the same BAiPP case in a later snapshot) into ``target`` in place.

    The yearly lists are republished monthly and the office corrects rows in between, so the
    newest snapshot's values (and its row warnings) win; ``sources`` keep every snapshot row,
    oldest first. Returns the labels of the fields whose content changed.
    """
    changed = [label for key, label in _SNAPSHOT_FIELDS.items()
               if _snapshot_value(target, key) != _snapshot_value(newer, key)]
    seen = {(s["file_id"], s.get("sheet"), s.get("row")) for s in target["sources"]}
    sources = target["sources"] + [s for s in newer["sources"]
                                   if (s["file_id"], s.get("sheet"), s.get("row")) not in seen]
    target.update({k: v for k, v in newer.items() if k not in ("id", "sources", "warnings")})
    target["sources"] = sources
    target["warnings"] = list(newer["warnings"])
    return changed


def merge_duplicates(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Merge records sharing an ``id`` (optional helper for ``pipeline/build.py``).

    * same id **and** same date + investment text → one record listing all sources (first
      occurrence wins for field values);
    * BAiPP (``dataset="baipp"``): the same id in another file is the same case in another snapshot
      of the yearly list → always one record; the values of the newest snapshot (the last one
      passed in – callers pass files oldest first) win, with a warning if the content changed;
    * same id but different content (within one file, or district) → ids get ``-2``, ``-3``…
      suffixes and both records get a warning (DATA_MODEL.md → "Collision with different content").

    Order is preserved; inputs are not mutated.
    """
    out: list[dict[str, Any]] = []
    groups: dict[str, list[dict[str, Any]]] = {}
    for r in records:
        groups.setdefault(r["id"], []).append(r)
    emitted: set[int] = set()
    for r in records:
        if id(r) in emitted:
            continue
        group = groups[r["id"]]
        variants: list[dict[str, Any]] = []
        changed: dict[int, list[str]] = {}   # BAiPP variant → fields edited between snapshots
        for g in group:
            emitted.add(id(g))
            if g.get("dataset") == "baipp":
                snapshot = next((v for v in variants if v.get("dataset") == "baipp"
                                 and not _source_files(v) & _source_files(g)), None)
                if snapshot is not None:
                    changed.setdefault(id(snapshot), []).extend(_adopt_newer_snapshot(snapshot, g))
                    continue
            same = next((v for v in variants if _content_key(v) == _content_key(g)), None)
            if same is None:
                variants.append({**g, "sources": list(g["sources"]), "warnings": list(g["warnings"])})
                continue
            seen = {(s["file_id"], s.get("sheet"), s.get("row")) for s in same["sources"]}
            for s in g["sources"]:
                if (s["file_id"], s.get("sheet"), s.get("row")) not in seen:
                    same["sources"].append(s)
            for w in g["warnings"]:
                if w not in same["warnings"]:
                    same["warnings"].append(w)
        for v in variants:
            if changed.get(id(v)):
                fields = ", ".join(dict.fromkeys(changed[id(v)]))
                v["warnings"].append(f"treść pozycji różni się między wersjami zestawienia BAiPP ({fields}) – "
                                     "pokazano wersję z najnowszego pliku")
        if len(variants) > 1:
            base = variants[0]["id"]
            for i, v in enumerate(variants, 1):
                if i > 1:
                    v["id"] = f"{base}-{i}"
                v["warnings"].append(
                    f"ten sam numer ({v['number']}) występuje w źródłach z inną treścią – "
                    f"rozdzielono na {len(variants)} pozycje")
        out.extend(variants)
    return out
