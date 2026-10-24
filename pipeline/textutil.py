"""Small, dependency-free text helpers shared by the parsing stages.

Everything here is deliberately boring and deterministic:

* :func:`collapse_ws` – one-line, single-spaced text (for searchable fields);
* :func:`tidy_cell` – multi-line text that mimics how a padded Excel cell *looks*
  (used for the "as in source" view);
* :func:`fold` – lower-case + Polish diacritics removed, **length preserving**, so
  regex matches on the folded string can be mapped back onto the original;
* Polish month names and :func:`month_from_text`;
* :func:`cell_to_json` / :func:`cell_to_str` – serialise openpyxl cell values.
"""

from __future__ import annotations

import datetime as _dt
import re

__all__ = [
    "MONTHS_PL",
    "MONTHS_PL_GENITIVE",
    "cell_to_json",
    "cell_to_str",
    "collapse_ws",
    "fold",
    "is_blank",
    "month_from_text",
    "month_name",
    "tidy_cell",
]

# --------------------------------------------------------------------------- whitespace

# \s in Python's re already covers NBSP (U+00A0) and other Unicode spaces for str patterns.
_WS_RE = re.compile(r"\s+")
_H_WS_RE = re.compile(r"[^\S\n]+")  # horizontal whitespace (everything but \n)
_WIDE_GAP_RE = re.compile(r"[^\S\n]{3,}")  # 3+ spaces = a visual line break in a padded cell


def collapse_ws(value: object) -> str:
    """Return ``value`` as a single line: every whitespace run (incl. ``\\n``, NBSP) → one space.

    ``None`` becomes ``""``.

    >>> collapse_ws("Osoba  Fizyczna \\n   -Pełnomocnik ")
    'Osoba Fizyczna -Pełnomocnik'
    """
    if value is None:
        return ""
    return _WS_RE.sub(" ", str(value)).strip()


def tidy_cell(value: object) -> str:
    """Stringify a cell for human display while keeping its visual line structure.

    The office pads cells with long runs of spaces so that text wraps onto a new visual
    line inside a narrow Excel column ("Kamionkowska 29            Praga-Południe").
    We turn such gaps (3+ spaces) and real line breaks into ``\\n``, squeeze the remaining
    whitespace, strip every line and drop empty lines.  Wording is never changed.

    >>> tidy_cell("Kamionkowska 29                     Praga-Południe ")
    'Kamionkowska 29\\nPraga-Południe'
    >>> tidy_cell("dz. 46/4\\n3-01-24\\n")
    'dz. 46/4\\n3-01-24'
    """
    text = cell_to_str(value)
    if not text:
        return ""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _WIDE_GAP_RE.sub("\n", text)
    lines = (_H_WS_RE.sub(" ", line).strip() for line in text.split("\n"))
    return "\n".join(line for line in lines if line)


def is_blank(value: object) -> bool:
    """True for ``None`` and for strings that contain only whitespace."""
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    return False


# --------------------------------------------------------------------------- folding

_FOLD_MAP = str.maketrans(
    {
        "ą": "a", "ć": "c", "ę": "e", "ł": "l", "ń": "n", "ó": "o", "ś": "s", "ź": "z", "ż": "z",
        "Ą": "a", "Ć": "c", "Ę": "e", "Ł": "l", "Ń": "n", "Ó": "o", "Ś": "s", "Ź": "z", "Ż": "z",
        # typographic look-alikes that appear in the source files
        " ": " ", "–": "-", "—": "-", "„": '"', "”": '"', "“": '"',
        "’": "'", "‘": "'",
        # a few non-Polish Latin letters, so names like "Bouygues Immobilier" fold sanely
        "á": "a", "à": "a", "ä": "a", "é": "e", "è": "e", "ë": "e", "í": "i", "ö": "o",
        "ü": "u", "ú": "u", "ç": "c", "č": "c", "š": "s", "ž": "z", "ř": "r",
    }
)


def fold(value: object) -> str:
    """Lower-case and strip Polish diacritics **without changing the string length**.

    Because the mapping is strictly 1:1 per character, offsets of regex matches found in
    ``fold(s)`` are valid offsets into ``s`` – the address/parcel parsers rely on that.

    >>> fold("Praga-Południe ŻÓŁW")
    'praga-poludnie zolw'
    """
    if value is None:
        return ""
    out = []
    for ch in str(value).translate(_FOLD_MAP):
        low = ch.lower()
        out.append(low if len(low) == 1 else ch)
    return "".join(out)


# --------------------------------------------------------------------------- months

MONTHS_PL: dict[int, str] = {
    1: "styczeń", 2: "luty", 3: "marzec", 4: "kwiecień", 5: "maj", 6: "czerwiec",
    7: "lipiec", 8: "sierpień", 9: "wrzesień", 10: "październik", 11: "listopad", 12: "grudzień",
}
MONTHS_PL_GENITIVE: dict[int, str] = {
    1: "stycznia", 2: "lutego", 3: "marca", 4: "kwietnia", 5: "maja", 6: "czerwca",
    7: "lipca", 8: "sierpnia", 9: "września", 10: "października", 11: "listopada", 12: "grudnia",
}
# folded inflected forms (nominative, genitive, locative; plus one typo seen on the site)
_MONTH_FORMS: dict[int, str] = {
    1: r"stycz(?:en|nia|niu)", 2: r"lut(?:y|ego|ym)", 3: r"mar(?:zec|ca|cu)",
    4: r"kwie(?:cien|tnia|tniu)", 5: r"maj(?:a|u)?", 6: r"czerw(?:iec|ca|cu)",
    7: r"lip(?:iec|ca|cu)", 8: r"sierp(?:ien|nia|niu)", 9: r"wrze(?:sien|snia|sniu|snien)",
    10: r"pazdziern(?:ik|ika|iku)", 11: r"listopad(?:a|zie)?", 12: r"grud(?:zien|nia|niu)",
}
_MONTH_RE = re.compile(
    r"(?<![a-z])(?:" + "|".join(f"(?P<m{n}>{rx})" for n, rx in _MONTH_FORMS.items()) + r")(?![a-z])"
)


def month_name(month: int, *, genitive: bool = False) -> str:
    """Polish month name for ``month`` (1–12)."""
    return (MONTHS_PL_GENITIVE if genitive else MONTHS_PL)[month]


def month_from_text(text: object) -> int | None:
    """Return the first Polish month mentioned in ``text`` (any case/inflection), else None.

    >>> month_from_text("Wydział … Praga-Południe LUTY-21")
    2
    >>> month_from_text("w październiku brak")
    10
    """
    m = _MONTH_RE.search(fold(text))
    if not m:
        return None
    return next(int(k[1:]) for k, v in m.groupdict().items() if v is not None)


# --------------------------------------------------------------------------- cells


def _datetime_iso(value: _dt.datetime | _dt.date | _dt.time) -> str:
    if isinstance(value, _dt.datetime):
        if value.time() == _dt.time(0, 0):
            return value.date().isoformat()
        return value.isoformat(timespec="seconds")
    return value.isoformat()


def cell_to_json(value: object) -> object:
    """JSON-friendly cell value: datetimes → ISO strings, integral floats → int, else as is."""
    if isinstance(value, (_dt.datetime, _dt.date, _dt.time)):
        return _datetime_iso(value)
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value


def cell_to_str(value: object) -> str:
    """Stringify a cell value ("" for None, ISO for datetimes, ``1`` not ``1.0``)."""
    if value is None:
        return ""
    value = cell_to_json(value)
    return value if isinstance(value, str) else str(value)
