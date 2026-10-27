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
                       r"nazwa organu|dla dzielnicy|^decyzje\b|^wnioski\b")
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
_LP_RE = re.compile(r"^\d{1,5}\.?$")
_DECISION_NO_RE = re.compile(r"^\d{1,5}/[A-ZĄĆĘŁŃÓŚŹŻ]")            # "12/BIA/WZ/2026/O", "107/B/2022"
_YEAR_TAIL_RE = re.compile(r"^(?:19|20)\d{2}/[A-Z]?$")             # "2026/O": the wrapped end of a number
CELL_GAP = 4.0              # pt: a wider gap between two words on a line separates cells (a space is ~2.5 pt)
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$|^\d{1,2}\.\d{1,2}\.\d{4}")
_OUTCOME_RE = re.compile(r"^(?:pozytywn|odmown|umarzaj|umorz|przenies|wygas|uchyl|inna$)\w*$")
_PRECINCT_RE = re.compile(r"^\d-\d{2}-\d{2,3}$")
_APPLICATIONS_RE = re.compile(r"\bwnios(?:ki|kow)\b")

# Header labels of the PDF layouts that parse.classify_header does not know (folded text → field;
# None = a known column kept only in ``raw``, without the "unrecognised column" warning).
_PDF_RULES: list[tuple[re.Pattern[str], str | None]] = [
    (re.compile(r"wygasniecie|stwierdzenie niewaznosci|^uwagi$"), None),
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
        text = "\t".join(parts[11:]).strip()
        if parts[0] != "5" or not text:
            continue
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


def _field(specific: str, label: str) -> tuple[str | None, bool]:
    """Canonical field of a column label → ``(field, known)``; ``known`` is False for an unrecognised label."""
    for text in (specific, label):
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
    for j, (label, specific) in enumerate(zip(labels, specifics)):
        flabel, fspec = _ftext(label), _ftext(specific)
        if _COMPOSITE_NUMBER_RE.search(fspec):          # a template's "Nr decyzji i data … › nr" is not composite
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


def _split_block(tops: list[float], anchors: list[float]) -> list[int]:
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
                cost = best[j - 1][k] + (len(group) * abs(sum(group) / len(group) - anchors[j - 1]) if group else 0.0)
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


def _titles_and_header(above: list[Line]) -> tuple[list[str], list[Line]]:
    """Split the lines above a numbering row into title texts (a title wrapped onto the next line, at the same
    left edge, is one text) and header lines."""
    last = max((i for i, ln in enumerate(above) if _TITLE_RE.search(_ftext(ln.text))), default=-1)
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
            if _FURNITURE_RE.match(_ftext(ln.text)):
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

    for p, frags, lps, dates, h in pages_data:
        anchors = lps or dates
        if not anchors:
            # Excel does not split a row across pages: text on a page without rows is a note under the table
            text = " ".join(f.text for _, f in sorted(frags, key=lambda jf: (jf[1].top, jf[1].words[0].x0)))
            result["skipped"].append({"sheet": f"strona {p + 1}", "row": None, "reason": f"tekst poza tabelą: „{text[:200]}”"})
            continue
        blocks = _blocks(frags, len(cols.labels), h)
        page_rows = _assign(blocks, anchors, h, align)
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
                page_rows = _assign(blocks, anchors, h, align)
        table.rows.extend((p, cells) for cells in page_rows)


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


def _assign(blocks: list[list[list[Line]]], anchors: list[float], h: float, align: str) -> list[list[list[Line]]]:
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
                    owners = [inside[k] for k in _split_block([f.top for f in block], [anchors[k] for k in inside])]
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
    need = 1 if len(anchors) == 1 else max(2, 0.08 * len(anchors))
    crossed = lambda x: any(w.x0 < x - 1.0 < x + 1.0 < w.x1 for ln in body for w in ln.words)  # noqa: E731
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
    anchors = []
    for _, body in bodies:
        for k, ln in enumerate(body):
            h = statistics.median(w.height for w in ln.words)
            if starts_row(ln, (ln.top - body[k - 1].top) / h if k else float("inf")):
                anchors.append(ln)
    if not anchors:
        result["skipped"].append({"sheet": f"strona {p0 + 1}", "row": None, "reason": "tabela bez pozycji"})
        result["_columns"] = _map_columns([], [], lambda w: 0)
        return []
    cols = _report_columns(header, anchors, lines)
    result["_columns"] = cols
    is_anchor = {id(ln) for ln in anchors}

    rows: list[tuple[int, list[list[Line]]]] = []
    for p, body in bodies:
        for ln in body:
            if id(ln) in is_anchor:
                rows.append((p, [[] for _ in cols.labels]))
            elif not rows:
                result["warnings"].append(f"strona {p + 1}: tekst przed pierwszą pozycją pominięto („{ln.text[:60]}”)")
                continue
            by_col: dict[int, list[Word]] = {}
            for w in ln.words:
                by_col.setdefault(cols.col_of(w), []).append(w)
            for j, ws in by_col.items():
                rows[-1][1][j].append(Line(p, ln.top, ws))
    return rows


# ---------------------------------------------------------------------------------- rows


def _cell_lines(frags: list[Line]) -> list[str]:
    return [f.text for f in sorted(frags, key=lambda f: (f.page, f.top))]


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


def _make_rows(rows: list[tuple[int, list[list[Line]]]], cols: _Columns, result: dict[str, Any]) -> None:
    for ordinal, (page, cells_lines) in enumerate(rows, start=1):
        cells: dict[str, Any] = {f: None for f in parse.FIELDS}
        raw: list[list[Any]] = []
        warnings: list[str] = []
        for j, frags in enumerate(cells_lines):
            lines = _cell_lines(frags)
            joiner = "\n" if cols.composite.get(j) else " "
            value = collapse_ws(" ".join(lines)) if joiner == " " else "\n".join(lines)
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
    pages = [_lines(words, p) for p, words in enumerate(read_words(path))]
    result: dict[str, Any] = {"kind": None, "title": None, "period_label": None, "layout": None, "series": None,
                              "procedure": None, "sheets": [], "rows": [], "skipped": [], "warnings": []}
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
        _make_rows(rows, cols, result)
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
