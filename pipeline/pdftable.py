"""Read the district lists published only as PDF (Białołęka, Bielany, Mokotów, Ochota, Targówek, Włochy).

Two families of PDF (docs/research/warsaw-districts.md):

* **report** – printed by the case-management system (``jsPDF``; Białołęka, Bielany, Mokotów). The header is
  repeated on every page, cells are top-aligned and a row may continue on the next page. Two cells are
  composite: "Nr decyzji i data jej wydania" holds the number, the date and the outcome ("Pozytywna",
  "Odmowna", "Umarzająca") on separate lines, and "Oznaczenie nieruchomości" / "Teren Inw." hold
  "precinct ¬ parcels ¬ street".
* **template** – the Excel template of Zarządzenie 1129/2020 printed to PDF (Ochota, Targówek, Włochy). The
  header and its "1 2 3 4 5 6 7" column-numbering row are printed on the first page only, cells are centred
  vertically and Excel never splits a row across pages.

Words and their boxes come from poppler's ``pdftotext -tsv`` (the PDF is parsed by poppler in a subprocess
with a timeout; nothing in it is executed). Columns: in a template the numbering row gives every column's
centre; in a report every header cell starts at its column's left edge. Rows: a template row is anchored at
its Lp number, which sits in the middle of the row, and every cell's lines are centred on it; a report row runs
from its first-column entry to the next one.

:func:`parse_pdf` returns the ``ParsedFile`` dict of :func:`pipeline.parse.parse_workbook`, so the rest of the
pipeline does not see the difference: ``sheet`` is "strona N" (the page a row starts on), ``row`` the row's
ordinal in the file, ``raw`` the cells as printed (composite ones too) and ``cells`` the canonical fields, with
the composite cells split (number + outcome, date; parcels as "55, 56 obr. 4-02-24", address as "Marmurowa").
"""

from __future__ import annotations

import functools
import re
import statistics
import subprocess
from bisect import bisect_right
from dataclasses import dataclass, field
from itertools import pairwise
from pathlib import Path
from typing import Any

from . import parse
from .textutil import collapse_ws, fold

__all__ = ["PdfUnavailable", "parse_pdf", "read_words"]

PDFTOTEXT = "pdftotext"
MAX_BYTES = 40 * 1024 * 1024
TIMEOUT_S = 120
PHRASE_GAP = 3.8            # pt: words closer than this on one line belong to one header phrase (a space is
                            # 2.5–2.8 pt; tightly packed headers leave 4.3 pt between two columns' labels)
LINE_TOLERANCE = 3.0        # pt: words whose tops differ less are on one line (cells of a row vary by ~2 pt)

# Folded line texts above the table that are titles, not column headers.
_TITLE_RE = re.compile(r"informacj|rejestr|zalacznik|zarzadzeni|prezydent|zarzad dzielnicy|urzad|wydzial|"
                       r"nazwa organu|dla dzielnicy|^decyzje\b|^wnioski\b|"
                       r"^razem\b|zestawienie obejmuje")      # Białołęka's yearly lists: "Razem: 334", a scope note
# The first header line of a report ("Lp  Wniosek  Data …", "Nr decyzji  Rodzaj inwestycji …").
_REPORT_HEADER_RE = re.compile(r"^(?:lp\b|nr i data|znak sprawy|nazwa organu|kategoria|rodzaj dec)|\bnr decyzji\b|"
                               r"\bnumer dec\b")
# The header phrase over the column that starts every row: the Lp, else the decision / application number.
_ANCHOR_LABEL_RE = re.compile(r"^(?:l\s*\.?\s*p\b|nr decyzji|nr i data|numer\b)")
_SEPARATOR_RE = re.compile(r"^(?:rok\s+)?(?:19|20)\d{2}(?:\s*r\.?|\s+rok)?$")   # "ROK 2020", "2021 rok"
_PAGE_NO_RE = re.compile(r"^(?:strona\s+)?\d+\s*(?:z|/)\s*\d+$")
_FOOTER_RE = re.compile(r"^stan na \d{1,2}\.\d{1,2}\.\d{4}")                # Ochota: "Stan na 14.09.2026 r."
# The annex heading Excel repeats at the top of every page ("Załącznik nr 1 / do zarządzenia nr 1129/2020 / …").
_FURNITURE_RE = re.compile(r"^(?:zalacznik nr \d+|do zarzadzenia nr|prezydenta miasta stolecznego|z dnia \d)")
# The header and footer a browser prints on every page ("19.10.2023, 09:09   Raport Erwin 2.0", "about:blank 1/41").
_BROWSER_PRODUCER_RE = re.compile(rb"/Producer\s*\(Skia/PDF")
_BROWSER_RE = re.compile(r"raport erwin|^about:?blank\b")
_CASE_NO_RE = re.compile(r"\b\d{1,5}/(?:[A-ZĄĆĘŁŃÓŚŹŻ]+/)*(?:19|20)\d{2}\b")   # "9/2020", "12/BIA/WZ/2026"
_LP_RE = re.compile(r"^\d{1,5}\.?$")
_DECISION_NO_RE = re.compile(r"^\d{1,5}/[A-ZĄĆĘŁŃÓŚŹŻ]")            # "12/BIA/WZ/2026/O", "107/B/2022"
_YEAR_TAIL_RE = re.compile(r"^(?:19|20)\d{2}/[A-Z]?$")             # "2026/O": the wrapped end of a number
CELL_GAP = 4.0              # pt: a wider gap between two words on a line separates cells (a space is ~2.5 pt)
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$|^\d{1,2}\.\d{1,2}\.\d{4}")
_OUTCOME_RE = re.compile(r"^(?:pozytywn|odmown|umarzaj|umorz|przenies|wygas|uchyl|inna$)\w*$")
_PRECINCT_RE = re.compile(r"^\d-\d{2}-\d{2,3}$")
_APPLICATIONS_RE = re.compile(r"\bwnios(?:ki|kow)\b")
ZWSP = "\u200b"                # zero-width space: Białołęka's browser-printed lists put it at break points in words
WORDS_FILE = Path(__file__).parent / "data" / "words.tsv"     # scripts/wordlist.py
MIN_JOINED = 3                 # a joined form must occur this often in the word list to count as a word

# Header labels of the PDF layouts that parse.classify_header does not know (folded text → field;
# None = a known column kept only in ``raw``, without the "unrecognised column" warning).
_PDF_RULES: list[tuple[re.Pattern[str], str | None]] = [
    (re.compile(r"wygasniecie|stwierdzenie niewaznosci|^uwagi$"), None),
    (re.compile(r"^(?:stan|zmiana|typ)$"), None),      # Białołęka's yearly lists: case state, change, category
    # Włochy's CP template: the wrapped parent label leaves "wydania" over the date column ("wydania data (rrrr-…")
    (re.compile(r"^wydania data\b|\(rrrr-mm-dd\)$"), "date"),
    (re.compile(r"^numer nr$"), "number"),            # Włochy 2020: "Numer [decyzji i data…]" split over two columns
    (re.compile(r"^decyzja$"), None),                  # Białołęka's applications: the decision issued since
    (re.compile(r"^wniosek$"), "number"),              # Białołęka's applications: the case number
    (re.compile(r"^l\s*\.?\s*p\s*\.?$"), "lp"),             # "Lp ."
    (re.compile(r"^nazwa organu|^kategoria$|^rodzaj dec"), None),   # Mokotów: the office; WZ/CP of a case
    (re.compile(r"^wynik$"), "outcome"),               # Mokotów's 2025 export: "Pozytywna" in a column of its own
    (re.compile(r"^numer dec"), "number"),
    (re.compile(r"^obreb$"), "precinct"),             # Mokotów's 2025 export: "_Działka_" and "_Obręb_" apart
    (re.compile(r"^tresc$"), "investment"),
    (re.compile(r"^opis$"), "investment"),
    (re.compile(r"teren inw"), "parcels"),
]
_COMPOSITE_NUMBER_RE = re.compile(r"nr decyzji i data")
# Białołęka's yearly lists (the case system's "Raport Erwin 2.0" printed from a browser): "Decyzja" holds the number,
# the date and the outcome, "Wniosek" the case number and the filing date – one per line. In an applications list
# "Decyzja" is the decision issued since (kept in ``raw``), so it is composite only where there is no "Wniosek".
_STACKED_DECISION_RE = re.compile(r"^decyzja$")
_STACKED_APPLICATION_RE = re.compile(r"^wniosek$")
_COMPOSITE_PLACE_RE = re.compile(r"oznaczenie nieruchomosci|teren inw")


class PdfUnavailable(RuntimeError):
    """``pdftotext`` (poppler) is not installed: PDF lists cannot be read on this machine."""


@dataclass
class Word:
    x0: float
    x1: float
    top: float
    height: float
    text: str

    @property
    def xc(self) -> float:
        return (self.x0 + self.x1) / 2


@dataclass
class Line:
    page: int
    top: float
    words: list[Word] = field(default_factory=list)

    @property
    def text(self) -> str:
        return " ".join(w.text for w in self.words)


_ZWSP_SEEN = [False]     # set by read_words when the file marks break points with zero-width spaces


def read_words(path: str | Path) -> list[list[Word]]:
    """Every page's words with their boxes (``pdftotext -tsv``)."""
    path = Path(path)
    if path.stat().st_size > MAX_BYTES:
        raise ValueError(f"PDF larger than {MAX_BYTES >> 20} MB")
    try:
        out = subprocess.run([PDFTOTEXT, "-q", "-tsv", str(path), "-"], capture_output=True, timeout=TIMEOUT_S,
                             check=True).stdout.decode("utf-8", "replace")
    except FileNotFoundError:
        raise PdfUnavailable("pdftotext (poppler-utils) is not installed – PDF lists cannot be read") from None
    pages: dict[int, list[Word]] = {}
    for row in out.splitlines()[1:]:
        parts = row.split("\t")
        if len(parts) < 12:
            continue
        page = int(parts[1])
        if parts[0] == "1":
            pages.setdefault(page, [])
        text = "\t".join(parts[11:]).replace(ZWSP, "").strip()
        if parts[0] != "5" or not text:
            continue
        if "\t".join(parts[11:]).count(ZWSP):
            _ZWSP_SEEN[0] = True
        left, top, width, height = map(float, parts[6:10])
        pages.setdefault(page, []).append(Word(left, left + width, top, height, text))
    return [pages[k] for k in sorted(pages)]


def _lines(words: list[Word], page: int) -> list[Line]:
    lines: list[Line] = []
    for w in sorted(words, key=lambda w: (w.top, w.x0)):
        if lines and abs(w.top - lines[-1].top) <= LINE_TOLERANCE:
            lines[-1].words.append(w)
        else:
            lines.append(Line(page, w.top, [w]))
    for line in lines:
        line.words.sort(key=lambda w: w.x0)
    return lines


def _phrases(line: Line) -> list[list[Word]]:
    out: list[list[Word]] = []
    for w in line.words:
        if out and w.x0 - out[-1][-1].x1 <= PHRASE_GAP:
            out[-1].append(w)
        else:
            out.append([w])
    return out


def _ftext(text: str) -> str:
    return collapse_ws(fold(text)).strip("_ ").replace("_ ", " ").replace(" _", " ")


def _unbreak(text: str) -> str:
    """A header label whose word the browser broke across lines ("Decyzj a", "Wnioskodaw ca") – joined."""
    return re.sub(r"(?<=\w) (?=\w{1,3}$)", "", text.strip())


def _field(specific: str, label: str) -> tuple[str | None, bool]:
    """Canonical field of a column label → ``(field, known)``; ``known`` is False for an unrecognised label."""
    for text in (specific, label, _unbreak(specific)):
        f = _ftext(text)
        for rx, fld in _PDF_RULES:
            if rx.search(f):
                return fld, True
        fld = parse.classify_header(text.replace("_", " "))
        if fld:
            return fld, True
    return None, False


@dataclass
class _Columns:
    labels: list[str]
    fields: dict[int, str]
    composite: dict[int, str]           # col → "number" | "place"
    extra: set[int]                     # known columns kept only in ``raw``
    col_of: Any                         # word → column index
    warnings: list[str]


def _map_columns(labels: list[str], specifics: list[str], col_of) -> _Columns:
    fields: dict[int, str] = {}
    composite: dict[int, str] = {}
    extra: set[int] = set()             # known columns without a canonical field (kept in ``raw`` only)
    warnings: list[str] = []
    taken: dict[str, int] = {}
    applications = any(_STACKED_APPLICATION_RE.match(_ftext(_unbreak(s))) for s in specifics)
    # stacked only where the date has no column of its own (the reports print "Wniosek" and "Data" apart)
    dated = any(_field(spec, lab)[0] in ("date", "filed") for lab, spec in zip(labels, specifics))
    for j, (label, specific) in enumerate(zip(labels, specifics)):
        flabel, fspec = _ftext(label), _ftext(specific)
        funbroken = _ftext(_unbreak(specific))
        stacked = not dated and (_STACKED_APPLICATION_RE.match(funbroken)
                                 or (_STACKED_DECISION_RE.match(funbroken) and not applications))
        if _COMPOSITE_NUMBER_RE.search(fspec) or stacked:   # a template's "Nr decyzji i data … › nr" is not composite
            composite[j] = "number"
        elif _COMPOSITE_PLACE_RE.search(fspec) and "ulica" not in fspec and "nr dz" not in fspec:
            composite[j] = "place"
        fld, known = _field(specific, label)
        if composite.get(j) == "number":
            fld = "number"
        if fld is None:
            if known:
                extra.add(j)
            else:
                warnings.append(f"kolumna {j + 1} („{label}”) nie została rozpoznana – zachowano ją tylko w danych "
                                f"źródłowych")
            continue
        if fld in taken:
            if fld == "investment" and "streszczeni" in flabel:   # reports print both description columns
                extra.add(j)
            else:
                warnings.append(f"kolumny {taken[fld] + 1} i {j + 1} wyglądają na to samo pole ({fld}); użyto pierwszej")
            continue
        taken[fld] = j
        fields[j] = fld
    if "filed" in taken and "date" not in taken and "number" not in composite.values():
        fields[taken["filed"]] = "date"      # an applications list ("Data złożenia"): the filing date is its date
        taken["date"] = taken.pop("filed")
    missing = [f for f in parse.FIELDS if f not in taken and f != "lp"
               and not (f == "address" and "place" in composite.values())
               and not (f == "date" and "number" in composite.values())]
    if missing and labels:
        warnings.append(f"brak kolumn: {', '.join(missing)}")
    return _Columns(labels, fields, composite, extra, col_of, warnings)


# ------------------------------------------------------------------------------ template


def _numbering(line: Line) -> list[float] | None:
    """Column centres from the "1 2 3 4 5 6 7" row (one cell may be garbled: Ochota prints "1900-01-03" for 3)."""
    ws = line.words
    if len(ws) < 5:
        return None
    hits = sum(1 for i, w in enumerate(ws, 1) if w.text.rstrip(".") == str(i))
    return [w.xc for w in ws] if hits >= len(ws) - 1 else None


def _template_bounds(words: list[Word], centres: list[float]) -> list[float]:
    """Column boundaries of a template: Excel keeps a cell's text inside the cell, so the x-ranges no word of the
    table ever covers are the cell borders. Each covered range belongs to the numbering-row column centred in it;
    a range holding two centres (text touching across a border) is split halfway between them, a column without
    any text gets the boundary halfway between the centres."""
    spans: list[list[float]] = []
    for w in sorted(words, key=lambda w: w.x0):
        if spans and w.x0 <= spans[-1][1] + 1.0:
            spans[-1][1] = max(spans[-1][1], w.x1)
        else:
            spans.append([w.x0, w.x1])
    n = len(centres)
    mids = [(a + b) / 2 for a, b in pairwise(centres)]
    extent: list[list[float] | None] = [None] * n       # [min x0, max x1] of each column's text
    for a, b in spans:
        inside = [j for j, c in enumerate(centres) if a <= c <= b]
        if not inside:
            inside = [min(range(n), key=lambda j: min(abs(centres[j] - a), abs(centres[j] - b)))]
        cuts = [a] + [mids[j] for j in inside[:-1]] + [b]
        for j, lo, hi in zip(inside, cuts, cuts[1:]):
            e = extent[j]
            extent[j] = [lo, hi] if e is None else [min(e[0], lo), max(e[1], hi)]
    bounds = []
    for j in range(n - 1):
        left, right = extent[j], extent[j + 1]
        if left is None or right is None or left[1] >= right[0]:
            bounds.append(mids[j])
        else:
            bounds.append((left[1] + right[0]) / 2)
    return bounds


def _label_columns(header: list[Line], n: int, col_of, *, header_rows: bool = False) -> tuple[list[str], list[str]]:
    """Column labels from the header lines → ``(labels, specifics)``. A phrase that runs over several columns and
    has labels under it in two or more of them ("Nr decyzji i data jej wydania" over "nr" and "data") is their
    parent – the label becomes "parent › child"; any other phrase belongs to the column of its centre, even when
    it runs a little into the next one. ``specifics`` (the child, else the parent) classify the column."""
    phrases = [(ln.top, ph) for ln in header for ph in _phrases(ln)]
    parents: list[list[tuple[float, float, str]]] = [[] for _ in range(n)]
    children: list[list[tuple[float, float, str]]] = [[] for _ in range(n)]
    for top, ph in phrases:
        x0, x1 = ph[0].x0, ph[-1].x1
        text = " ".join(w.text for w in ph)
        under = {col_of(w.xc) for t, other in phrases if t > top + LINE_TOLERANCE for w in other
                 if min(x1, w.x1) > max(x0, w.x0)}
        if len(under) > 1 and len({col_of(w.xc) for w in ph}) > 1:
            for j in under:
                parents[j].append((top, x0, text))
        else:
            children[col_of((x0 + x1) / 2)].append((top, x0, text))
    # in a report, a column's own labels on lines far apart are two header rows ("Nr i data decyzji" … "Nr"): the
    # upper one is a parent (a template's multi-line labels are spaced too loosely for this test)
    h = statistics.median(w.height for ln in header for w in ln.words) if header else 10.0
    for j in range(n if header_rows else 0):
        own = sorted(children[j])
        cut = max((k for k in range(1, len(own)) if own[k][0] - own[k - 1][0] > 1.3 * h), default=0)
        parents[j] += own[:cut]
        children[j] = own[cut:]
    labels, specifics = [], []
    for j in range(n):
        parent = " ".join(t for *_, t in sorted(parents[j]))
        child = " ".join(t for *_, t in sorted(children[j]))
        labels.append(f"{parent}{parse._LABEL_SEP}{child}" if parent and child else parent or child or f"(kolumna {j + 1})")
        specifics.append(child or parent)
    return labels, specifics


def _template_columns(header: list[Line], bounds: list[float]) -> _Columns:
    col_of = lambda x: bisect_right(bounds, x)  # noqa: E731
    labels, specifics = _label_columns(header, len(bounds) + 1, col_of)
    return _map_columns(labels, specifics, lambda w: col_of(w.xc))


SPREAD_WEIGHT = 0.1


def _split_block(tops: list[float], anchors: list[float], strict: bool = False) -> list[int]:
    """Assign a block's consecutive lines to the anchors whose rows it spans: the contiguous split whose groups are
    best centred on their anchors (cells are centred vertically). Returns the anchor index of every line."""
    n, m = len(tops), len(anchors)
    inf = float("inf")
    # best[j][i]: cost of the first i lines given to the first j anchors
    best = [[inf] * (n + 1) for _ in range(m + 1)]
    cut = [[0] * (n + 1) for _ in range(m + 1)]
    best[0][0] = 0.0
    for j in range(1, m + 1):
        for i in range(n + 1):
            for k in range(i + 1):          # lines k..i-1 go to anchor j-1
                if best[j - 1][k] == inf:
                    continue
                group = tops[k:i]
                # a cell never reaches past the neighbouring rows' anchors (else one tall group centred on an
                # anchor could swallow the cells of the rows either side and leave them empty)
                if strict and group and ((j >= 2 and group[0] <= anchors[j - 2])
                                         or (j < m and group[-1] >= anchors[j])):
                    continue
                # centred on the anchor; a little spread breaks ties between equally centred splits (touching
                # three-line number cells: "outcome / number / date / outcome / number" is centred too)
                cost = best[j - 1][k] + (len(group) * abs(sum(group) / len(group) - anchors[j - 1])
                                         + (SPREAD_WEIGHT * sum(abs(t - anchors[j - 1]) for t in group) if strict else 0.0)
                                         if group else 0.0)
                if cost < best[j][i]:
                    best[j][i], cut[j][i] = cost, k
    out = [0] * n
    i = n
    for j in range(m, 0, -1):
        k = cut[j][i]
        for t in range(k, i):
            out[t] = j - 1
        i = k
    return out


def _skip_line(ln: Line) -> bool:
    text = _ftext(ln.text)
    return bool(_FOOTER_RE.match(text)) or (len(_phrases(ln)) == 1 and bool(_SEPARATOR_RE.match(text)
                                                                            or _PAGE_NO_RE.match(text)))


@dataclass
class _Table:
    """One table of a template PDF: its numbering row, the titles and header above it, and its parsed rows."""
    page: int
    line: int
    centres: list[float]
    titles: list[str]
    header: list[Line]
    start: int = 0       # index (on ``page``) of its first title or header line
    rows: list[tuple[int, list[list[Line]]]] = field(default_factory=list)
    cols: _Columns | None = None
    split_rows: bool = False   # printed by a browser, which (unlike Excel) splits a row across two pages


_WEAK_TITLE_RE = re.compile(r"^(?:decyzje|wnioski)\b")


def _is_title(ln: Line) -> bool:
    """A title line above a table. "Decyzje …" / "Wnioski …" open a heading, but a header line may start with the
    same word ("decyzję  decyzji  numer działki, obręb  ulica" – Włochy 2020): that one has several cells."""
    text = _ftext(ln.text)
    if not _TITLE_RE.search(text):
        return False
    weak_only = _WEAK_TITLE_RE.match(text) and not _TITLE_RE.search(_WEAK_TITLE_RE.sub("", text, count=1))
    return not weak_only or len(_phrases(ln)) == 1


def _titles_and_header(above: list[Line]) -> tuple[list[str], list[Line]]:
    """Split the lines above a numbering row into title texts (a title wrapped onto the next line, at the same
    left edge, is one text) and header lines."""
    last = max((i for i, ln in enumerate(above) if _is_title(ln)), default=-1)
    while 0 <= last < len(above) - 1:
        ln, nxt = above[last], above[last + 1]
        if abs(nxt.words[0].x0 - ln.words[0].x0) > 3.0 or nxt.top - ln.top > 1.6 * ln.words[0].height:
            break
        last += 1
    titles: list[str] = []
    for i in range(last + 1):
        ln = above[i]
        wrapped = i and abs(ln.words[0].x0 - above[i - 1].words[0].x0) <= 3.0 \
            and ln.top - above[i - 1].top <= 1.6 * above[i - 1].words[0].height
        if wrapped and titles and _TITLE_RE.search(_ftext(titles[-1])):
            titles[-1] += " " + ln.text
        else:
            titles.append(ln.text)
    return titles, above[last + 1:]


def _template_tables(pages: list[list[Line]]) -> list[_Table]:
    """Every numbering row with a title above it starts a table (a workbook's sheets printed one after another:
    Mokotów lists WZ applications on page 1 and CP applications on page 2); one without a title is the header
    printed again over the same table."""
    tables: list[_Table] = []
    for p, lines in enumerate(pages):
        for i, ln in enumerate(lines):
            centres = _numbering(ln)
            if not centres:
                continue
            titles, header = _titles_and_header(lines[:i])
            if tables and not titles:
                continue
            start = next((k for k, l in enumerate(lines[:i]) if _TITLE_RE.search(_ftext(l.text))), i - len(header))
            if not tables:
                titles = [l.text for pl in pages[:p] for l in pl] + titles
            tables.append(_Table(p, i, centres, titles, header, start))
    return tables


def _parse_template(pages: list[list[Line]], table: _Table, until: tuple[int, int],
                    result: dict[str, Any]) -> None:
    """Rows of one template table (up to the next table's title, ``until`` = (page, line)) → ``table.rows``:
    ``[(page, cells)]`` with each cell's lines (fragments of one column)."""
    vocab = {_ftext(w.text) for ln in table.header for w in ln.words}

    def repeated_header(ln: Line) -> bool:
        """A line of the header printed again over the same table (Ochota starts every year with it)."""
        words = [_ftext(w.text) for w in ln.words]
        known = sum(w in vocab for w in words)
        return bool(_numbering(ln)) or (known >= 0.6 * len(words) and (len(words) > 1 or len(words[0]) >= 4)
                                        and not _LP_RE.match(words[0]))

    bodies: list[tuple[int, list[Line]]] = []
    for p in range(table.page, min(until[0] + 1, len(pages))):
        lines = pages[p]
        hi = until[1] if p == until[0] else len(lines)
        lo = table.line + 1 if p == table.page else 0
        kept = []
        for ln in lines[lo:hi]:
            if _FURNITURE_RE.match(_ftext(ln.text)) or _BROWSER_RE.search(_ftext(ln.text)):
                continue
            if _skip_line(ln):
                result["skipped"].append({"sheet": f"strona {p + 1}", "row": None, "reason": f"wiersz „{ln.text}”"})
            elif p != table.page and repeated_header(ln):
                continue
            else:
                kept.append(ln)
        bodies.append((p, kept))
    bounds = _template_bounds([w for _, body in bodies for ln in body for w in ln.words], table.centres)
    cols = table.cols = _template_columns(table.header, bounds)
    if table.split_rows:
        # a browser left-aligns cell text: where a word starts is inside its cell, while a word ending at the
        # cell's right edge may have its centre over the border ("…STOJĄCEGO Z" – Białołęka)
        cols.col_of = lambda w: bisect_right(bounds, w.x0 + 1.0)  # noqa: E731
    lp_col = next((j for j, f in cols.fields.items() if f == "lp"), 0)
    date_col = next((j for j, f in cols.fields.items() if f == "date"), None)

    pages_data = []        # per page: (page, frags, lps, dates, line height)
    for p, body in bodies:
        frags: list[tuple[int, Line]] = []      # (column, fragment)
        lps: list[float] = []                   # tops of the lines with an Lp number
        dates: list[float] = []                 # tops of the date cells
        for ln in body:
            by_col: dict[int, list[Word]] = {}
            for w in ln.words:
                by_col.setdefault(cols.col_of(w), []).append(w)
            for j, ws in by_col.items():
                frag = Line(p, ln.top, ws)
                frags.append((j, frag))
                if j == lp_col and _LP_RE.match(frag.text):
                    lps.append(ln.top)
                elif j == date_col and _DATE_RE.match(frag.text):
                    dates.append(ln.top)
        if frags:
            pages_data.append((p, frags, lps, dates, statistics.median(w.height for _, f in frags for w in f.words)))
    align = _alignment([(_blocks(frags, len(cols.labels), h), lps or dates) for _, frags, lps, dates, h in pages_data])

    prev_anchor: float | None = None      # the last anchor of the previous page
    for p, frags, lps, dates, h in pages_data:
        anchors = lps or dates
        if not anchors:
            # Excel does not split a row across pages: text on a page without rows is a note under the table
            text = " ".join(f.text for _, f in sorted(frags, key=lambda jf: (jf[1].top, jf[1].words[0].x0)))
            result["skipped"].append({"sheet": f"strona {p + 1}", "row": None, "reason": f"tekst poza tabelą: „{text[:200]}”"})
            continue
        blocks = _blocks(frags, len(cols.labels), h)
        if table.split_rows and table.rows:
            # the end of the previous page's last row: blocks above this page's first anchor that do not reach it
            # (a centred cell always spans its anchor line)
            last = table.rows[-1][1]
            carried = False
            for j, col in enumerate(blocks):
                while col and col[0][-1].top < anchors[0] - 0.6 * h:
                    last[j].extend(col.pop(0))
                    carried = True
            # that row was split, and a browser top-aligns the part left on the first page: whatever of it lies
            # above its anchor line belongs to the row before (the tail of a neighbour's centred cell)
            if carried and len(table.rows) > 1 and prev_anchor is not None and table.rows[-2][0] == table.rows[-1][0]:
                before = table.rows[-2][1]
                for j, cell in enumerate(last):
                    up = [f for f in cell if f.page == table.rows[-1][0] and f.top < prev_anchor - 0.6 * h]
                    if up:
                        before[j].extend(up)
                        last[j][:] = [f for f in cell if f not in up]
        page_rows = _assign(blocks, anchors, h, align, table.split_rows)
        if lps and date_col is not None:
            # rows printed without an Lp number (Włochy) show up as a second date in a row: each date starts one
            extra = []
            for k, cells in enumerate(page_rows):
                tops = [f.top for f in cells[date_col] if _DATE_RE.match(f.text)]
                if len(tops) > 1:
                    keep = min(tops, key=lambda t: abs(t - anchors[k]))
                    extra += [t for t in tops if t != keep]
            if extra:
                anchors = sorted(anchors + extra)
                page_rows = _assign(blocks, anchors, h, align, table.split_rows)
        table.rows.extend((p, cells) for cells in page_rows)
        prev_anchor = anchors[-1]


def _blocks(frags: list[tuple[int, Line]], n_cols: int, h: float) -> list[list[list[Line]]]:
    """Each column's fragments grouped into blocks of consecutive lines (a cell's text, or touching cells')."""
    out: list[list[list[Line]]] = []
    for j in range(n_cols):
        blocks: list[list[Line]] = []
        for f in sorted((f for c, f in frags if c == j), key=lambda f: f.top):
            if blocks and f.top - blocks[-1][-1].top <= 1.5 * h:
                blocks[-1].append(f)
            else:
                blocks.append([f])
        out.append(blocks)
    return out


def _alignment(pages: list[tuple[list[list[list[Line]]], list[float]]]) -> str:
    """How the table's cells are aligned vertically – "center", "top" or "bottom" (Excel's default) – from where the
    anchor line sits in the multi-line blocks around it."""
    rel = []
    for blocks, anchors in pages:
        for col in blocks:
            for block in col:
                lo, hi = block[0].top, block[-1].top
                inside = [a for a in anchors if lo - 2.0 <= a <= hi + 2.0]
                if len(block) >= 3 and len(inside) == 1 and hi > lo:
                    rel.append((inside[0] - lo) / (hi - lo))
    if not rel:
        return "center"
    m = statistics.median(rel)
    return "top" if m < 0.3 else "bottom" if m > 0.7 else "center"


def _assign(blocks: list[list[list[Line]]], anchors: list[float], h: float, align: str,
            strict: bool = False) -> list[list[list[Line]]]:
    """Cells of the rows anchored at ``anchors`` (tops of their Lp lines): a block containing one anchor belongs to
    it; one containing several (cells touching) is split between them by the alignment; a block containing none goes
    to the anchor it is aligned to (centred on, below or above it)."""
    rows: list[list[list[Line]]] = [[[] for _ in blocks] for _ in anchors]

    def nearest(y: float) -> int:
        if align == "top":
            above = [k for k, a in enumerate(anchors) if a <= y + 2.0]
            if above:
                return above[-1]
        elif align == "bottom":
            below = [k for k, a in enumerate(anchors) if a >= y - 2.0]
            if below:
                return below[0]
        return min(range(len(anchors)), key=lambda k: abs(anchors[k] - y))

    for j, col in enumerate(blocks):
        for block in col:
            lo, hi = block[0].top - 0.6 * h, block[-1].top + 0.6 * h
            inside = [k for k, t in enumerate(anchors) if lo <= t <= hi]
            if len(inside) > 1:
                if align == "center":
                    owners = [inside[k] for k in _split_block([f.top for f in block], [anchors[k] for k in inside],
                                                              strict)]
                else:
                    owners = [nearest(f.top) for f in block]
                for f, k in zip(block, owners):
                    rows[k][j].append(f)
            elif inside:
                rows[inside[0]][j].extend(block)
            else:
                y = {"top": block[0].top, "bottom": block[-1].top}.get(align, (block[0].top + block[-1].top) / 2)
                rows[nearest(y)][j].extend(block)
    return rows


# -------------------------------------------------------------------------------- report


def _header_cells(header: list[Line]) -> list[tuple[float, float, str]]:
    """Header phrases grouped into cells (phrases on different lines that overlap horizontally) → (x0, x1, text)."""
    cells: list[list[tuple[float, float, float, str]]] = []
    for ln in header:
        for ph in _phrases(ln):
            x0, x1 = ph[0].x0, ph[-1].x1
            item = (ln.top, x0, x1, " ".join(w.text for w in ph))
            cell = next((c for c in cells if any(min(x1, b) - max(x0, a) > 0 for _, a, b, _ in c)), None)
            if cell is None:
                cells.append([item])
            else:
                cell.append(item)
    out = [(min(a for _, a, _, _ in c), max(b for _, _, b, _ in c), " ".join(t for *_, t in sorted(c))) for c in cells]
    return sorted(out)


def _report_columns(header: list[Line], anchors: list[Line], body: list[Line]) -> _Columns:
    """Columns of a report: where cell text starts on the rows' first lines (a word after a gap wider than a
    space, at the same place in several rows, and no word of any line crossing that place); the header names
    them. A header cell over a column that is (nearly) always empty ("Uwagi") starts a column of its own."""
    starts: list[float] = []
    for ln in anchors:
        for prev, w in zip([None, *ln.words], ln.words):
            if prev is None or w.x0 - prev.x1 >= CELL_GAP:
                starts.append(w.x0)
    clusters: list[list[float]] = []
    for x in sorted(starts):
        if clusters and x - clusters[-1][-1] <= 2.0:
            clusters[-1].append(x)
        else:
            clusters.append([x])
    # a column with centred text starts at several nearby places ("1" / "10" / "100", case numbers of different
    # lengths): starts within a few points of each other are one column, which begins at the leftmost
    merged: list[list[float]] = []
    for c in clusters:
        if merged and c[0] - merged[-1][-1] <= 6.0:
            merged[-1].extend(c)
        else:
            merged.append(list(c))
    clusters = merged
    need = 1 if len(anchors) == 1 else max(2, 0.08 * len(anchors))
    # a column edge no text crosses – bar a stray overlong cell or two (Włochy: "…6730.257.2021.AGA/BKA", a number
    # and its date printed without a space)
    allowed = int(0.02 * len(anchors))
    crossed = lambda x: sum(w.x0 < x - 1.0 < x + 1.0 < w.x1 for ln in body for w in ln.words) > allowed  # noqa: E731
    lefts = [min(c) for c in clusters if len(c) >= need and not crossed(min(c))]
    cells = _header_cells(header)
    owner = [max(bisect_right(lefts, (a + b) / 2) - 1, 0) for a, b, _ in cells]
    for k in range(len(cells)):
        if k and owner[k] == owner[k - 1]:
            lefts.append(cells[k][0] - 1.0)
    lefts.sort()
    # every real column has a label: a run of text starts with no header over it is inside a cell (a gap in a
    # one-row file), so it joins the column to its left
    centres = [(ph[0].x0 + ph[-1].x1) / 2 for ln in header for ph in _phrases(ln)]
    lefts = [x for j, x in enumerate(lefts)
             if j == 0 or any(x <= c < (lefts[j + 1] if j + 1 < len(lefts) else float("inf")) for c in centres)]
    col_of = lambda x: max(bisect_right(lefts, x) - 1, 0)  # noqa: E731
    labels, specifics = _label_columns(header, len(lefts), col_of, header_rows=True)
    return _map_columns(labels, specifics, lambda w: max(bisect_right(lefts, w.x0 + 2.0) - 1, 0))


def _is_anchor(word: str, style: str) -> bool:
    if style == "lp":
        return bool(_LP_RE.match(word))
    return bool(_DECISION_NO_RE.match(word)) and not _YEAR_TAIL_RE.match(word)


def _parse_report(pages: list[list[Line]], result: dict[str, Any]) -> list[tuple[int, list[list[Line]]]]:
    first = next(((p, i) for p, lines in enumerate(pages) for i, ln in enumerate(lines)
                  if _REPORT_HEADER_RE.search(_ftext(ln.text))), None)
    if first is None:
        raise ValueError("nie znaleziono nagłówka tabeli")
    p0, h0 = first
    # labels centred vertically in a tall header cell start above the "Lp" line (Włochy's Excel registers:
    # "Data wszczęcia" / "postępowania" / "(rrrr-mm-dd)"): take in the lines just above that are not titles
    while h0 > 0:
        above, cur = pages[p0][h0 - 1], pages[p0][h0]
        hh = statistics.median(w.height for w in cur.words)
        if cur.top - above.top > 1.45 * hh or _TITLE_RE.search(_ftext(above.text)) or _skip_line(above):
            break
        h0 -= 1
    result["_title_texts"] = [ln.text for pl in pages[:p0] for ln in pl] + [ln.text for ln in pages[p0][:h0]]
    header_key = _ftext(pages[p0][h0].text)
    # the column that starts every row: under the header's Lp, else its number
    labels = [(ph[0].x0, _ftext(" ".join(w.text for w in ph))) for ln in pages[p0][h0:h0 + 6] for ph in _phrases(ln)]
    lp = [x for x, t in labels if re.match(r"^l\s*\.?\s*p\b", t)]
    numbered = [x for x, t in labels if _ANCHOR_LABEL_RE.match(t)]
    style = "lp" if lp else "number"
    ax = min(lp or numbered or [min(x for x, _ in labels)])

    def anchor_word(ln: Line) -> Word | None:
        """The word in the column that starts every row (under the Lp or number label), if any."""
        w = next((w for w in ln.words if w.x0 >= ax - 8.0), None)
        return w if w is not None and w.x0 <= ax + 8.0 else None

    def starts_row(ln: Line, gap: float) -> bool:
        """An Lp number starts a row. A number cell may hold more than the number ("Nr" above it, the date and the
        outcome below), so in a numbered report a row starts where that column has text after the space between
        rows (``gap`` = space above the line in line heights; the first line of a page always qualifies)."""
        w = anchor_word(ln)
        if w is None:
            return False
        if style == "lp":
            return _is_anchor(w.text, style)
        return gap >= 1.4 and not (_DATE_RE.match(w.text) or _OUTCOME_RE.match(_ftext(w.text)))

    # the header runs to the first row (its lines may be far apart: "Nr i data decyzji" … "Nr  data")
    h1 = next((i for i in range(h0 + 1, len(pages[p0]))
               if (w := anchor_word(pages[p0][i])) is not None and _is_anchor(w.text, style)), len(pages[p0]))
    # ...and ends at the first clear gap: a centred first row's cell may start above its Lp line
    gap_end = next((i for i in range(h0 + 1, h1) if pages[p0][i].top - pages[p0][i - 1].top
                    > 2.2 * statistics.median(w.height for w in pages[p0][i].words)), h1)
    if gap_end < h1 and _skip_header_gap(pages[p0][h0:gap_end], pages[p0][gap_end:h1]):
        h1 = gap_end
    header = pages[p0][h0:h1]
    bodies: list[tuple[int, list[Line]]] = []
    for p, lines in enumerate(pages):
        if p < p0:
            continue
        if p == p0:
            body = lines[h1:]
        else:
            start = next((i for i, ln in enumerate(lines) if _ftext(ln.text) == header_key), None)
            body = lines[start + len(header):] if start is not None else lines
        bodies.append((p, [ln for ln in body if not (len(_phrases(ln)) == 1 and _PAGE_NO_RE.match(_ftext(ln.text)))]))
    lines = [ln for _, body in bodies for ln in body]
    def starts_case(ln: Line) -> bool:
        """The row's next cell (its case number) starts right after the Lp – unlike a wrapped Lp tail's line."""
        w = anchor_word(ln)
        rest = [x for x in ln.words if x.x0 > w.x1]
        return bool(rest) and rest[0].x0 - w.x1 < 30.0

    anchors = []
    last_lp = 0
    for _, body in bodies:
        for k, ln in enumerate(body):
            h = statistics.median(w.height for w in ln.words)
            if not starts_row(ln, (ln.top - body[k - 1].top) / h if k else float("inf")):
                continue
            if style == "lp":
                # an Lp of three digits wraps in a narrow column ("10" / "0"): the next line's digits complete it,
                # and a line holding only that tail is not a new row – Lp numbers grow
                lp = anchor_word(ln).text.rstrip(".")
                nxt = body[k + 1] if k + 1 < len(body) else None
                tail = anchor_word(nxt) if nxt is not None and (nxt.top - ln.top) / h < 1.4 else None
                expected = str(last_lp + 1)
                if tail is not None and tail.text.isdigit() and (
                        int(lp + tail.text) == last_lp + 1
                        or (last_lp < int(lp + tail.text) <= last_lp + 50 and len(nxt.words) == 1)):
                    lp += tail.text
                elif (anchors and k == len(body) - 1 and int(lp) <= last_lp and expected.startswith(lp)
                      and len(lp) < len(expected) and starts_case(ln)):
                    lp = expected      # its tail went to the next page
                if anchors and not last_lp < int(lp) <= last_lp + 50:
                    continue
                last_lp = int(lp)
            anchors.append(ln)
    if not anchors:
        result["skipped"].append({"sheet": f"strona {p0 + 1}", "row": None, "reason": "tabela bez pozycji"})
        result["_columns"] = _map_columns([], [], lambda w: 0)
        return []
    cols = _report_columns(header, anchors, lines)
    result["_columns"] = cols
    is_anchor = {id(ln) for ln in anchors}

    # an Excel register printed without the column-numbering row has its cells centred on the row's first-column
    # entry, not hanging below it: then rows are cut like a template's
    pages_data = []
    for p, body in bodies:
        frags = [(j, Line(p, ln.top, ws)) for ln in body for j, ws in _by_column(ln, cols).items()]
        tops = [ln.top for ln in body if id(ln) in is_anchor]
        if frags:
            pages_data.append((p, frags, tops, statistics.median(w.height for _, f in frags for w in f.words)))
    align = _alignment([(_blocks(frags, len(cols.labels), h), tops) for _, frags, tops, h in pages_data])
    if align != "top":
        rows: list[tuple[int, list[list[Line]]]] = []
        for p, frags, tops, h in pages_data:
            if not tops:
                result["warnings"].append(f"strona {p + 1}: tekst bez pozycji pominięto")
                continue
            rows.extend((p, cells) for cells in _assign(_blocks(frags, len(cols.labels), h), tops, h, align,
                                                        strict=True))
        return rows

    rows: list[tuple[int, list[list[Line]]]] = []
    for p, body in bodies:
        for ln in body:
            if id(ln) in is_anchor:
                rows.append((p, [[] for _ in cols.labels]))
            elif not rows:
                result["warnings"].append(f"strona {p + 1}: tekst przed pierwszą pozycją pominięto („{ln.text[:60]}”)")
                continue
            for j, ws in _by_column(ln, cols).items():
                rows[-1][1][j].append(Line(p, ln.top, ws))
    return rows


def _skip_header_gap(header: list[Line], below: list[Line]) -> bool:
    """Whether the lines between a header and its first row, after a clear gap, are row text rather than more
    header: they fall in a single header column's span (a description cell's first line), not in several."""
    spans = [(ph[0].x0, ph[-1].x1) for ln in header for ph in _phrases(ln)]
    cols = {i for ln in below for w in ln.words for i, (a, b) in enumerate(spans) if a - 5 <= w.x0 <= b + 40}
    return len(cols) <= 1


def _by_column(ln: Line, cols: _Columns) -> dict[int, list[Word]]:
    by_col: dict[int, list[Word]] = {}
    for w in ln.words:
        by_col.setdefault(cols.col_of(w), []).append(w)
    return by_col


# ---------------------------------------------------------------------------------- rows


WORD_GAP = 0.5               # pt: a browser-printed list splits one word into touching pieces ("BUDYN" "KU", gap 0.0)


def _line_text(line: Line, mend: bool) -> str:
    if not mend:
        return line.text
    out = ""
    for prev, w in zip([None, *line.words], line.words):
        out += w.text if prev is None or w.x0 - prev.x1 < WORD_GAP else " " + w.text
    return out


def _cell_lines(frags: list[Line], mend: bool = False) -> list[str]:
    return [_line_text(f, mend) for f in sorted(frags, key=lambda f: (f.page, f.top))]


@functools.lru_cache(maxsize=1)
def _word_counts() -> dict[str, int]:
    counts: dict[str, int] = {}
    for line in WORDS_FILE.read_text(encoding="utf-8").splitlines():
        word, _, n = line.partition("\t")
        counts[word] = int(n)
    return counts


_TAIL_RE = re.compile(r"([^\W\d_]+)$")
_HEAD_RE = re.compile(r"^([^\W\d_]+)")


def _one_word(x: str, y: str) -> bool:
    """Whether two pieces either side of a line break are one word the browser broke: the joined form is a known
    word and more frequent than the rarer piece ("z" + "agospodarowaniem", "bud" + "owie"; not "budynków" +
    "mieszkalnych", not "do" + "budowy")."""
    counts = _word_counts()
    joined = counts.get((x + y).lower(), 0)
    return joined >= MIN_JOINED and joined > min(counts.get(x.lower(), 0), counts.get(y.lower(), 0))


def _join_lines(lines: list[str], mend: bool) -> str:
    """A cell's lines as one text. In a browser-printed list (``mend``) a break may fall inside a word: a line
    ending in a hyphen ("4-01-", "usługowo-") continues without a space, and pieces that form a known word are
    joined (:func:`_one_word`). Elsewhere lines are joined with a space."""
    out = ""
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if not out:
            out = line
            continue
        if mend:
            tail, head = _TAIL_RE.search(out), _HEAD_RE.match(line)
            if out.endswith("-") and len(out) > 1 and out[-2] not in " -":
                out += line
                continue
            if tail and head and _one_word(tail.group(1), head.group(1)):
                out += line
                continue
        out += " " + line
    return collapse_ws(out)


def _split_number_cell(lines: list[str]) -> tuple[str, str | None, str | None]:
    """A report's "Nr decyzji i data jej wydania" cell → (number [+ outcome on its own line], date, rest)."""
    number, date, outcome, rest = [], None, None, []
    for ln in lines:
        if re.fullmatch(r"(?i)nr\.?", ln.strip()):     # "Nr" printed above the number (Mokotów X 2025)
            continue
        if date is None and _DATE_RE.match(ln):
            date = ln
        elif outcome is None and _OUTCOME_RE.match(_ftext(ln)):
            outcome = ln
        elif date is None and outcome is None:
            number.append(ln)
        else:
            rest.append(ln)
    text = "".join(number)       # a long number wraps without a space
    if outcome:
        text += "\n" + outcome
    return text, date, " ".join(rest) or None


def _split_place(text: str) -> tuple[str, str]:
    """"4-02-24 ¬ 55, 56 ¬ Marmurowa" → ("55, 56 obr. 4-02-24", "Marmurowa"); several properties are joined.
    Without "¬" the whole text is the parcels."""
    if "¬" not in text:
        return collapse_ws(text), ""
    parts = [collapse_ws(p) for p in text.split("¬")]
    parcels, streets = [], []
    precinct: str | None = None
    numbers: list[str] = []

    def flush() -> None:
        if precinct and numbers:
            parcels.append(f"{', '.join(numbers)} obr. {precinct}")
        elif numbers:
            parcels.append(", ".join(numbers))

    for part in parts:
        if not part:
            continue
        if _PRECINCT_RE.match(part):
            flush()
            precinct, numbers = part, []
        elif precinct is not None and not numbers and re.match(r"^(?:cz\.?\s*)?\d", part):
            numbers = [part]
        else:
            streets.append(part)
    flush()
    return "; ".join(parcels), ", ".join(dict.fromkeys(streets))


def _is_stacked_number(text: str) -> bool:
    return not (_DATE_RE.match(text) or _OUTCOME_RE.match(_ftext(text)))


def _repair_stacked(rows: list[tuple[int, list[list[Line]]]], j: int) -> None:
    """A browser splits a row at a page end and top-aligns what is left of it, so the stacked "number / date /
    outcome" cells of neighbouring rows can be cut in the wrong place. Lines before a row's number that are its
    predecessor's date or outcome go back to it; a number after a row's outcome goes on to the next row."""
    def kinds(frags: list[Line]) -> list[str]:
        return ["number" if _is_stacked_number(f.text) else "date" if _DATE_RE.match(f.text) else "outcome"
                for f in sorted(frags, key=lambda f: (f.page, f.top))]

    for k in range(len(rows)):
        cell = sorted(rows[k][1][j], key=lambda f: (f.page, f.top))
        ks = kinds(cell)
        if k and ks and ks[0] != "number" and "number" in ks:
            prev = rows[k - 1][1][j]
            lead = ks.index("number")
            if not any(x in kinds(prev) for x in ks[:lead]):
                prev.extend(cell[:lead])
                cell = cell[lead:]
        ks = kinds(cell)
        if k + 1 < len(rows) and len(ks) > 1 and ks[-1] == "number" and "outcome" in ks[:-1]:
            nxt = rows[k + 1][1][j]
            if "number" not in kinds(nxt):
                nxt.extend(cell[-1:])
                cell = cell[:-1]
        rows[k][1][j][:] = cell


def _make_rows(rows: list[tuple[int, list[list[Line]]]], cols: _Columns, result: dict[str, Any],
               mend: bool = False) -> None:
    if mend:
        for j, kind in cols.composite.items():
            if kind == "number":
                _repair_stacked(rows, j)
    for ordinal, (page, cells_lines) in enumerate(rows, start=1):
        cells: dict[str, Any] = {f: None for f in parse.FIELDS}
        raw: list[list[Any]] = []
        warnings: list[str] = []
        for j, frags in enumerate(cells_lines):
            lines = _cell_lines(frags, mend)
            joiner = "\n" if cols.composite.get(j) else " "
            value = _join_lines(lines, mend) if joiner == " " else "\n".join(lines)
            raw.append([cols.labels[j], value or None])
            if not lines:
                continue
            kind = cols.composite.get(j)
            if kind == "number":
                number, date, rest = _split_number_cell(lines)
                cells["number"] = number or None
                cells["date"] = cells["date"] or date
                if rest:
                    warnings.append(f"w komórce numeru podano także: {rest}")
            elif kind == "place":
                parcels, street = _split_place(" ".join(lines))
                cells["parcels"] = parcels or None
                if street and cells["address"] is None:
                    cells["address"] = street
            elif cols.fields.get(j) == "parcels" and "¬" in value:
                parcels, street = _split_place(value)
                cells["parcels"] = parcels or None
                if street and cells["address"] is None:
                    cells["address"] = street
            elif j in cols.fields:
                if cols.fields[j] in ("date", "filed") and not _DATE_RE.match(value) \
                        and _DATE_RE.match(compact := "".join(value.split())):
                    value = compact            # "2025-01-0" / "7": a date wrapped in a narrow column
                elif cols.fields[j] == "lp" and re.fullmatch(r"\d+(?: \d+)+\.?", value):
                    value = value.replace(" ", "")   # "10 1": an Lp wrapped in a narrow column
                cells[cols.fields[j]] = value
            elif j not in cols.extra:
                warnings.append(f"wartość w kolumnie bez rozpoznanego pola: „{cols.labels[j]}”")
        outcome = cells.pop("outcome", None)
        if outcome and cells["number"]:
            cells["number"] = f"{cells['number']}\n{outcome}"
        precinct = cells.pop("precinct", None)
        if precinct:
            cells["parcels"] = f"{cells['parcels'] or ''} obr. {precinct}".strip()
        if not any(cells[f] for f in parse.FIELDS if f != "lp"):
            result["skipped"].append({"sheet": f"strona {page + 1}", "row": ordinal, "reason": "tylko numer Lp"})
            continue
        if len(_CASE_NO_RE.findall(cells["number"] or "")) >= 3:
            # the rows of a table read as one (a layout the parser does not know): no record rather than a wrong one
            result["skipped"].append({"sheet": f"strona {page + 1}", "row": ordinal,
                                      "reason": "kilka pozycji w jednej komórce numeru – układu tabeli nie odczytano"})
            continue
        result["rows"].append({"sheet": f"strona {page + 1}", "row": ordinal, "cells": cells, "raw": raw,
                               "warnings": warnings})


def _kind_of(titles: list[str], labels: list[str]) -> tuple[str | None, str | None, str | None]:
    """(kind, procedure of an applications list, CP series) from a table's titles."""
    folded = _ftext(" ".join(titles))
    kind = "ws" if _APPLICATIONS_RE.search(folded) and "decyzj" not in folded else None
    kind = kind or parse.detect_kind(*titles) or parse.detect_kind(*labels)
    wz, cp = bool(re.search(r"warunk\w* zabudow", folded)), bool(re.search(r"cel\w* publiczn|\bcp\b|ulicp", folded))
    procedure = ("wz" if wz else "cp") if kind == "ws" and wz != cp else None
    return kind, procedure, parse.cp_series(*titles) if kind == "cp" else None


def parse_pdf(path: str | Path) -> dict[str, Any]:
    """Parse one PDF list into a ``ParsedFile`` dict (see the module docstring)."""
    _ZWSP_SEEN[0] = False
    pages = [_lines(words, p) for p, words in enumerate(read_words(path))]
    result: dict[str, Any] = {"kind": None, "title": None, "period_label": None, "layout": None, "series": None,
                              "procedure": None, "sheets": [], "rows": [], "skipped": [], "warnings": []}
    # printed by a browser from the case system: long words may be broken anywhere in a narrow column
    # (the case system's "Raport Erwin" header, zero-width break hints, or Chrome's PDF engine as the producer)
    mend = bool(pages) and (_ZWSP_SEEN[0] or any("raport erwin" in _ftext(ln.text) for ln in pages[0][:3])
                            or _BROWSER_PRODUCER_RE.search(Path(path).read_bytes()) is not None)
    tables = _template_tables(pages)
    if tables:
        family = "template"
        for k, table in enumerate(tables):
            nxt = tables[k + 1] if k + 1 < len(tables) else None
            if nxt is None:
                until = (len(pages) - 1, len(pages[-1]))
            elif nxt.page > table.page:
                until = (nxt.page - 1, len(pages[nxt.page - 1]))
            else:                       # two tables on one page: this one ends where the next one's title begins
                until = (nxt.page, nxt.start)
            table.split_rows = mend
            _parse_template(pages, table, until, result)
        parts = [(t.titles, t.cols, t.rows, t.page) for t in tables]
    else:
        family = "report"
        rows = _parse_report(pages, result)
        parts = [(result.pop("_title_texts"), result.pop("_columns"), rows, 0)]

    kinds: list[tuple[int, str | None, str | None]] = []      # (first page, kind, procedure) per table
    for titles, cols, rows, first_page in parts:
        titles = [collapse_ws(t) for t in titles]
        kind, procedure, series = _kind_of(titles, cols.labels)
        result["warnings"] += cols.warnings
        _make_rows(rows, cols, result, mend)
        kinds.append((first_page, kind, procedure))
        if result["title"] is None:
            result.update(title=parse._title(titles), period_label=parse._period_label(titles), kind=kind,
                          layout=f"pdf-{family}-{kind or 'unknown'}", series=series, procedure=procedure)
    if result["kind"] is None:
        result["warnings"].append("nie rozpoznano rodzaju listy (WZ/CP/wszczęte)")
    if len({k for _, k, _ in kinds}) > 1:
        result["warnings"].append(f"tabele w pliku mają różne rodzaje list: {', '.join(sorted(str(k) for _, k, _ in kinds))}")

    def table_of(page: int) -> tuple[str | None, str | None]:
        _, kind, procedure = max((t for t in kinds if t[0] <= page), default=kinds[0], key=lambda t: t[0])
        return kind, procedure

    result["sheets"] = [{"name": f"strona {p + 1}", "max_row": None, "header_row": None, "kind": table_of(p)[0],
                         "procedure": table_of(p)[1], "layout": result["layout"],
                         "rows": sum(1 for r in result["rows"] if r["sheet"] == f"strona {p + 1}")}
                        for p in range(len(pages))]
    return result
