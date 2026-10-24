"""Crawler / downloader stage: index pages -> monthly pages -> Excel files.

Produces ``data/manifest.json`` (see ``docs/DATA_MODEL.md``) and keeps
``data/raw/<file_id>.<ext>`` in sync with the files linked from two sources:

* ``district`` – the Praga-Południe "informacja o wszczętych postępowaniach oraz wydanych
  decyzjach administracyjnych" pages (paginated index → monthly pages);
* ``baipp`` – the city architecture bureau's (BAiPP) page ``architektura.um.warszawa.pl/
  postepowania-i-decyzje`` (current year, replaced monthly) and the yearly archive pages it
  links in its "Dane z ubiegłych lat" box (discovered, never guessed). Every snapshot ever
  downloaded stays in the manifest (``removed_from_source_at`` once it is no longer linked).

Usage::

    uv run python -m pipeline.crawl [--out data/manifest.json] [--raw data/raw]
                                    [--refresh] [--max-index-pages N] [--no-download]
                                    [--skip-district | --skip-baipp]

The integrator should call :func:`run_crawl`.

Downloaded HTML is untrusted: it is only ever parsed with the stdlib
:class:`html.parser.HTMLParser`, never executed or rendered.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import logging
import os
import re
import shutil
import sys
import unicodedata
import zipfile
from collections import Counter
from collections.abc import Iterable, Iterator
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import parse_qsl, unquote_plus, urlencode, urljoin, urlsplit, urlunsplit

import requests

from pipeline.http import fetch, get_text, make_session

log = logging.getLogger("wzsearch.crawl")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
INDEX_URL = (
    "https://pragapld.um.warszawa.pl/"
    "informacja-o-wszczetych-postepowaniach-oraz-wydanych-decyzjach-administracyjnych"
)
PAGINATION_PARAM = "_AssetPublisher_nS01Fh02AyOr_cur"
ASSET_PUBLISHER_INSTANCE = "nS01Fh02AyOr"
HARD_PAGE_CAP = 200
DEFAULT_OUT = PROJECT_ROOT / "data" / "manifest.json"
DEFAULT_RAW = PROJECT_ROOT / "data" / "raw"
CATEGORIES = ("wz", "cp", "ws")
#: The city architecture bureau's (BAiPP) page with the current year's lists.
BAIPP_URL = "https://architektura.um.warszawa.pl/postepowania-i-decyzje"
#: Crawled sources, in manifest order (pages and files are grouped by source).
SOURCES = ("district", "baipp")
#: Minimum gap between two requests to the same host: at most 2 requests per second.
DEFAULT_DELAY = 0.5

__all__ = [
    "BAIPP_URL",
    "INDEX_URL",
    "PAGINATION_PARAM",
    "SOURCES",
    "build_manifest",
    "crawl_baipp",
    "crawl_index",
    "detect_baipp_category",
    "detect_category",
    "document_path_of",
    "download_files",
    "file_id_of",
    "find_period",
    "index_page_url",
    "load_manifest",
    "main",
    "parse_baipp_page",
    "parse_declared_count",
    "parse_index_page",
    "parse_monthly_page",
    "parse_period",
    "run_crawl",
    "summarize",
    "write_manifest",
]


# =============================================================================
# Minimal HTML tree (stdlib only)
# =============================================================================

_VOID_TAGS = frozenset(
    "area base br col embed hr img input link meta param source track wbr".split()
)
_SKIP_TAGS = frozenset({"script", "style", "noscript", "template", "svg"})


class Node:
    """A lightweight element node. ``children`` holds :class:`Node` and ``str``."""

    __slots__ = ("attrs", "children", "parent", "tag")

    def __init__(self, tag: str, attrs: dict[str, str], parent: Node | None) -> None:
        self.tag = tag
        self.attrs = attrs
        self.children: list[Node | str] = []
        self.parent = parent

    @property
    def classes(self) -> set[str]:
        return set(self.attrs.get("class", "").split())

    def iter(self) -> Iterator[Node]:
        """Depth-first, document-order iteration over this node and its descendants."""
        stack: list[Node] = [self]
        while stack:
            node = stack.pop()
            yield node
            stack.extend(c for c in reversed(node.children) if isinstance(c, Node))

    def find_all(self, tag: str | None = None, cls: str | None = None) -> Iterator[Node]:
        for node in self.iter():
            if tag is not None and node.tag != tag:
                continue
            if cls is not None and cls not in node.classes:
                continue
            yield node

    def find(self, tag: str | None = None, cls: str | None = None) -> Node | None:
        return next(self.find_all(tag, cls), None)

    def text(self) -> str:
        """Concatenated text content, skipping ``<script>``/``<style>``."""
        parts: list[str] = []
        stack: list[Node | str] = [self]
        while stack:
            item = stack.pop()
            if isinstance(item, str):
                parts.append(item)
            elif item.tag not in _SKIP_TAGS:
                stack.extend(reversed(item.children))
        return "".join(parts)


class _TreeBuilder(HTMLParser):
    """Builds a forgiving :class:`Node` tree; mismatched end tags are ignored."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = Node("#document", {}, None)
        self._current = self.root

    def handle_starttag(self, tag, attrs):
        node = Node(tag, {k: (v or "") for k, v in attrs}, self._current)
        self._current.children.append(node)
        if tag not in _VOID_TAGS:
            self._current = node

    def handle_startendtag(self, tag, attrs):
        self._current.children.append(Node(tag, {k: (v or "") for k, v in attrs}, self._current))

    def handle_endtag(self, tag):
        if tag in _VOID_TAGS:
            return
        node: Node | None = self._current
        while node is not None and node.tag != tag:
            node = node.parent
        if node is not None and node.parent is not None:
            self._current = node.parent

    def handle_data(self, data):
        self._current.children.append(data)


def parse_html(html: str) -> Node:
    builder = _TreeBuilder()
    builder.feed(html)
    builder.close()
    return builder.root


# =============================================================================
# Text helpers
# =============================================================================

_INVISIBLE = dict.fromkeys(map(ord, "\u200b\u200c\u200d\ufeff\u00ad"), None)  # ZW(N)J/ZWSP, BOM, soft hyphen


def clean_text(text: str | None) -> str:
    """Collapse all whitespace (incl. NBSP) to single spaces and strip."""
    if not text:
        return ""
    return " ".join(text.translate(_INVISIBLE).split())


def fold(text: str) -> str:
    """Lowercase and strip Polish diacritics (``Październik`` -> ``pazdziernik``)."""
    text = text.replace("ł", "l").replace("Ł", "L")
    text = unicodedata.normalize("NFKD", text)
    return "".join(c for c in text if not unicodedata.combining(c)).lower()


def _words(text: str) -> str:
    """Folded text reduced to space-separated alphanumeric tokens, padded with spaces."""
    return " " + " ".join(re.findall(r"[a-z]+|\d+", fold(text))) + " "


# =============================================================================
# Periods, categories, declared counts
# =============================================================================

_MONTH_FORMS: dict[str, int] = {}
for _month, _forms in enumerate(
    [
        "styczen stycznia styczniu",
        "luty lutego lutym",
        "marzec marca marcu",
        "kwiecien kwietnia kwietniu",
        "maj maja maju",
        "czerwiec czerwca czerwcu",
        "lipiec lipca lipcu",
        "sierpien sierpnia sierpniu",
        "wrzesien wrzesnia wrzesniu wrzesnien",
        "pazdziernik pazdziernika pazdzierniku",
        "listopad listopada listopadzie",
        "grudzien grudnia grudniu",
    ],
    start=1,
):
    for _form in _forms.split():
        _MONTH_FORMS[_form] = _month

# Prefix stems used only as a fallback for titles with unforeseen typos.
_MONTH_STEMS = [
    ("stycz", 1), ("lut", 2), ("marz", 3), ("marc", 3), ("kwie", 4), ("maj", 5),
    ("czerw", 6), ("lip", 7), ("sierp", 8), ("wrze", 9), ("pazdz", 10), ("listop", 11),
    ("grud", 12),
]


def find_period(
    text: str | None, *, fuzzy: bool = False, short_year: bool = False
) -> tuple[int | None, int | None]:
    """Find a Polish month name and a 4-digit year anywhere in ``text``.

    Returns ``(year, month)``, either of which may be ``None``. Month names are
    matched in nominative, genitive and locative forms, case- and
    diacritics-insensitively. With ``fuzzy=True`` unknown tokens are also
    matched by their stem (for typos such as ``wrzesnień``). With
    ``short_year=True`` a 2-digit number right after the month counts as the
    year when there is no 4-digit one (file names like ``wrzesień -22.xlsx``).
    """
    if not text:
        return None, None
    tokens = re.findall(r"[a-z]+|\d+", fold(text))
    month_at = next((i for i, t in enumerate(tokens) if t in _MONTH_FORMS), None)
    month = _MONTH_FORMS[tokens[month_at]] if month_at is not None else None
    if month is None and fuzzy:
        for i, token in enumerate(tokens):
            stem_month = next((m for stem, m in _MONTH_STEMS if token.startswith(stem)), None)
            if len(token) >= 3 and stem_month is not None:
                month_at, month = i, stem_month
                break
    year = next(
        (int(t) for t in tokens if len(t) == 4 and t.isdigit() and 2000 <= int(t) <= 2099), None
    )
    if year is None and short_year and month_at is not None and month_at + 1 < len(tokens):
        following = tokens[month_at + 1]
        if len(following) == 2 and following.isdigit() and 15 <= int(following) <= 49:
            year = 2000 + int(following)
    return year, month


def parse_period(title: str | None) -> str | None:
    """Reporting period ``YYYY-MM`` from a monthly page title.

    >>> parse_period("Grudzień 2021 r.")
    '2021-12'
    >>> parse_period("Październik 2021r.")
    '2021-10'

    Numeric titles (``05.2021``, ``2021-05``) are accepted as a fallback.
    Returns ``None`` when no month+year can be found.
    """
    if not title:
        return None
    year, month = find_period(title, fuzzy=True)
    if year is None or month is None:
        folded = fold(title)
        m = re.search(r"(?<!\d)(0?[1-9]|1[0-2])\s*[./-]\s*(20\d\d)(?!\d)", folded)
        if m:
            month, year = int(m.group(1)), int(m.group(2))
        else:
            m = re.search(r"(?<!\d)(20\d\d)\s*[./-]\s*(0?[1-9]|1[0-2])(?!\d)", folded)
            if m:
                year, month = int(m.group(1)), int(m.group(2))
    if year is None or month is None:
        return None
    return f"{year:04d}-{month:02d}"


def detect_category(text: str | None) -> str | None:
    """Classify a block text (or a file name) as ``wz``, ``cp``, ``ws`` or ``None``.

    Initiated proceedings win over decision types, because their headings
    mention both procedures ("wszczęte postępowania o warunkach zabudowy i …
    celu publicznego").
    """
    if not text:
        return None
    t = _words(text)
    if "wszcz" in t or (" postepowan" in t and " wydan" not in t):
        return "ws"
    if re.search(r" (cp|ulicp) ", t) or re.search(r" cel[a-z]* publiczn", t):
        return "cp"
    if re.search(r" wz ", t) or (" warunk" in t and " zabudow" in t):
        return "wz"
    return None


def parse_declared_count(text: str | None) -> int | None:
    """Number of entries a block says its file has.

    ``"3 pozycje"`` -> 3, ``"5 pozcji"`` -> 5, ``"BRAK w LISTOPADZIE"`` -> 0,
    ``"brak wszczętych postępowań"`` -> 0, no number -> ``None``. When a block
    states two different numbers the count is ambiguous and ``None`` is returned.
    """
    if not text:
        return None
    t = fold(clean_text(text))
    numbers = [int(n) for n in re.findall(r"(?<!\d)(\d+)\s*poz", t)]
    if numbers:
        return numbers[0] if len(set(numbers)) == 1 else None
    if re.search(r"\bbrak\b", t):
        return 0
    return None


# =============================================================================
# Links and identifiers
# =============================================================================

_UUID_RE = re.compile(r"^[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}$", re.IGNORECASE)


def document_path_of(href: str, base_url: str | None = None) -> str | None:
    """``/documents/...`` path of a link (query/fragment dropped, still URL-encoded).

    Returns ``None`` for anything that is not an http(s) link to ``/documents/``
    on a ``*.um.warszawa.pl`` host.
    """
    href = (href or "").strip()
    if not href:
        return None
    absolute = urljoin(base_url, href) if base_url else href
    parts = urlsplit(absolute)
    if parts.scheme not in ("http", "https", ""):
        return None
    host = (parts.hostname or "").lower()
    if host and not (host == "um.warszawa.pl" or host.endswith(".um.warszawa.pl")):
        return None
    if not parts.path.startswith("/documents/"):
        return None
    return parts.path


def file_id_of(document_path: str) -> str:
    """First 10 hex chars of ``sha1(document_path)`` (see DATA_MODEL.md)."""
    return hashlib.sha1(document_path.encode("utf-8")).hexdigest()[:10]


def filename_of(document_path: str) -> str:
    """Human file name from a Liferay document path (``+`` -> space, %-decoded)."""
    segments = [s for s in document_path.split("/") if s]
    if len(segments) >= 2 and _UUID_RE.match(segments[-1]):
        raw = segments[-2]
    else:
        raw = segments[-1] if segments else ""
    return unquote_plus(raw)


def extension_of(filename: str) -> str:
    """Lower-case extension (``xlsx``); ``bin`` when missing or odd."""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    return ext if re.fullmatch(r"[a-z0-9]{1,8}", ext) else "bin"


def _version_of(url: str) -> int:
    """Liferay ``?t=`` version timestamp of a document URL (0 if absent)."""
    for key, value in parse_qsl(urlsplit(url).query):
        if key == "t" and value.isdigit():
            return int(value)
    return 0


def page_id_of(url: str) -> str | None:
    """Slug after ``/-/`` in a monthly page URL."""
    path = urlsplit(url).path
    if "/-/" not in path:
        return None
    slug = path.split("/-/", 1)[1].strip("/")
    return slug or None


# =============================================================================
# Index pages
# =============================================================================


def index_page_url(index_url: str, n: int) -> str:
    """URL of index page ``n`` (1-based), replacing any existing ``cur`` param."""
    parts = urlsplit(index_url)
    query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if k != PAGINATION_PARAM]
    query.append((PAGINATION_PARAM, str(n)))
    return urlunsplit(parts._replace(query=urlencode(query)))


def _cur_of(url: str) -> int | None:
    for key, value in parse_qsl(urlsplit(url).query):
        if key == PAGINATION_PARAM and value.isdigit():
            return int(value)
    return None


def _publisher_root(root: Node) -> Node:
    """The asset-publisher portlet holding the monthly list (falls back to the document)."""
    marker = f"INSTANCE_{ASSET_PUBLISHER_INSTANCE}_"
    for node in root.iter():
        if node.attrs.get("id", "").endswith(marker) and node.attrs["id"].startswith("p_p_id"):
            return node
    return root


def _office_url(url: str) -> str | None:
    """``url`` normalised (``urlsplit`` drops TAB/CR/LF) if it is an http(s) link on ``um.warszawa.pl`` or a
    subdomain, else ``None`` – an index link with another scheme ("java\tscript:…") or host is never stored."""
    parts = urlsplit((url or "").strip())
    host = (parts.hostname or "").lower()
    if parts.scheme not in ("http", "https") or not (host == "um.warszawa.pl" or host.endswith(".um.warszawa.pl")):
        return None
    return urlunsplit(parts)


def parse_index_page(html: str, page_url: str) -> tuple[list[dict], str | None]:
    """Parse one index page.

    Returns ``(stubs, next_url)`` where each stub is
    ``{"url", "page_id", "title", "summary"}`` and ``next_url`` is the absolute
    URL of the "Następna" link if it points to page ``cur + 1`` (else ``None``).
    """
    root = _publisher_root(parse_html(html))
    stubs: list[dict] = []
    seen: set[str] = set()
    for item in root.find_all("li", cls="event"):
        link = item.find("a", cls="event__link")
        if link is None or not link.attrs.get("href"):
            continue
        url = _office_url(urljoin(page_url, link.attrs["href"].strip()))
        if url is None:
            log.warning("index: skipping a link that is not an http(s) link on um.warszawa.pl: %r", link.attrs["href"])
            continue
        page_id = page_id_of(url)
        if page_id is None or page_id in seen:
            continue
        seen.add(page_id)
        excerpt = item.find("p", cls="event__excerpt")
        stubs.append(
            {
                "url": url,
                "page_id": page_id,
                "title": clean_text(link.attrs.get("title") or link.text()),
                "summary": clean_text(excerpt.text()) if excerpt is not None else None,
            }
        )

    current = _cur_of(page_url) or 1
    next_url = None
    for anchor in root.find_all("a"):
        if fold(clean_text(anchor.text())) != "nastepna":
            continue
        href = anchor.attrs.get("href", "").strip()
        if not href or href.lower().startswith("javascript"):
            continue
        candidate = _office_url(urljoin(page_url, href))
        if candidate is None:
            continue
        if _cur_of(candidate) == current + 1:
            next_url = candidate
            break
        log.warning("index: 'Następna' link %s does not point to page %d", candidate, current + 1)
    return stubs, next_url


def crawl_index(
    session: requests.Session,
    index_url: str = INDEX_URL,
    max_pages: int | None = None,
) -> list[dict]:
    """Walk the paginated index and return page stubs (newest first).

    Each stub: ``{"url", "page_id", "title", "summary", "index_page"}``.
    Stops when there is no "Następna" link to ``cur=N+1``, when a page lists no
    items, after ``max_pages`` pages, or at the hard cap of 200 pages.
    """
    limit = HARD_PAGE_CAP if max_pages is None else max(1, min(max_pages, HARD_PAGE_CAP))
    stubs: list[dict] = []
    seen: set[str] = set()
    url: str | None = index_page_url(index_url, 1)
    n = 1
    while url is not None:
        html = get_text(session, url)
        items, next_url = parse_index_page(html, url)
        log.info("index page %d: %d item(s)", n, len(items))
        if not items:
            break
        for item in items:
            if item["page_id"] in seen:  # list shifted while crawling
                continue
            seen.add(item["page_id"])
            stubs.append({**item, "index_page": n})
        if n >= limit:
            if max_pages is None and next_url:
                log.warning("index: hard cap of %d pages reached, stopping", HARD_PAGE_CAP)
            break
        url = next_url
        n += 1
    return stubs


# =============================================================================
# Monthly pages
# =============================================================================

_BLOCK_TAGS = frozenset(
    """address article aside blockquote caption dd details dialog div dl dt fieldset
    figcaption figure footer form h1 h2 h3 h4 h5 h6 header hr li main nav ol p pre
    section table tbody td tfoot th thead tr ul""".split()
)


class _Line:
    __slots__ = ("hrefs", "parts")

    def __init__(self) -> None:
        self.parts: list[str] = []
        self.hrefs: list[str] = []

    @property
    def text(self) -> str:
        return clean_text("".join(self.parts))

    def __bool__(self) -> bool:
        return bool(self.text or self.hrefs)


class _Segmenter:
    """Splits an article body into segments (one per block element), each a list of
    ``<br>``-separated lines carrying their text and the hrefs of their ``<a>`` tags."""

    def __init__(self) -> None:
        self.segments: list[list[_Line]] = []
        self._current: list[_Line] = [_Line()]

    def run(self, body: Node) -> list[list[_Line]]:
        self._walk(body)
        self._flush()
        return self.segments

    def _flush(self) -> None:
        lines = [line for line in self._current if line]
        if lines:
            self.segments.append(lines)
        self._current = [_Line()]

    def _walk(self, node: Node) -> None:
        for child in node.children:
            if isinstance(child, str):
                self._current[-1].parts.append(child)
                continue
            if child.tag in _SKIP_TAGS:
                continue
            if child.tag == "br":
                self._current.append(_Line())
                continue
            if child.tag == "a" and child.attrs.get("href"):
                self._current[-1].hrefs.append(child.attrs["href"])
            if child.tag in _BLOCK_TAGS:
                self._flush()
                self._walk(child)
                self._flush()
            else:
                self._walk(child)


def _segment_to_blocks(lines: list[_Line]) -> list[tuple[str, list[str]]]:
    """Turn a segment into one or more ``(text, hrefs)`` blocks.

    A ``<p>`` that packs several categories into ``<br>``-separated lines
    (May 2023) is split into one block per categorised line; lines without a
    category of their own stay with the preceding categorised line. Otherwise
    the lines are joined into a single block.
    """
    categorised = [i for i, line in enumerate(lines) if detect_category(line.text)]
    if len(lines) > 1 and len(categorised) >= 2:
        groups: list[list[_Line]] = []
        for i, line in enumerate(lines):
            if i in categorised or not groups:
                groups.append([line])
            else:
                groups[-1].append(line)
        # leading uncategorised lines belong to the first categorised group
        if groups and not detect_category(groups[0][0].text) and len(groups) > 1:
            groups[1] = groups[0] + groups[1]
            groups.pop(0)
    else:
        groups = [lines]
    blocks = []
    for group in groups:
        text = clean_text(" ".join(line.text for line in group))
        hrefs = [h for line in group for h in line.hrefs]
        blocks.append((text, hrefs))
    return blocks


def _article_container(root: Node) -> Node:
    node = root.find(cls="journal-content-article")
    if node is not None:
        return node
    return root.find("article") or root


def _page_title(root: Node, container: Node) -> str:
    title = container.attrs.get("data-analytics-asset-title")
    if title and clean_text(title):
        return clean_text(title)
    h1 = root.find("h1", cls="article-title") or root.find("h1")
    if h1 is not None and clean_text(h1.text()):
        return clean_text(h1.text())
    for meta in root.find_all("meta"):
        if meta.attrs.get("property") == "og:title" and clean_text(meta.attrs.get("content")):
            return clean_text(meta.attrs["content"])
    title_node = root.find("title")
    if title_node is not None:
        return clean_text(re.sub(r"\s+-\s+Praga Południe\s*$", "", title_node.text()))
    return ""


def _fmt_period(year: int | None, month: int | None) -> str:
    if year and month:
        return f"{year:04d}-{month:02d}"
    if month:
        return f"????-{month:02d}"
    return "?"


def _plural_pozycja(n: int) -> str:
    if n == 1:
        return "pozycję"
    if n % 10 in (2, 3, 4) and n % 100 not in (12, 13, 14):
        return "pozycje"
    return "pozycji"


def parse_monthly_page(html: str, url: str) -> dict:
    """Parse a monthly page into a manifest page dict (DATA_MODEL.md).

    Besides the contract fields the result carries:

    * ``links`` - one entry per (block, file) pair:
      ``{"block", "file_id", "url", "document_path", "filename", "ext"}``
      (consumed by :func:`build_manifest`, not written to the manifest);
    * ``warnings`` - human-readable (Polish) notes about source anomalies.

    ``summary`` and ``index_page`` are ``None``; they come from the index stub.
    """
    root = parse_html(html)
    container = _article_container(root)
    title = _page_title(root, container)
    time_node = next((n for n in container.find_all("time") if n.attrs.get("datetime")), None)
    published_at = clean_text(time_node.attrs["datetime"]) if time_node is not None else None
    body = container.find(cls="article-description") or container
    period = parse_period(title)

    page: dict = {
        "page_id": page_id_of(url) or url,
        "url": url,
        "title": title,
        "period": period,
        "published_at": published_at or None,
        "summary": None,
        "index_page": None,
        "source": "district",
        "blocks": [],
        "links": [],
        "warnings": [],
    }
    warnings: list[str] = page["warnings"]
    if period is None:
        warnings.append(f"Nie udało się odczytać miesiąca z tytułu strony „{title}”.")

    for lines in _Segmenter().run(body):
        for text, hrefs in _segment_to_blocks(lines):
            block_index = len(page["blocks"])
            file_ids: list[str] = []
            for href in hrefs:
                doc_path = document_path_of(href, url)
                if doc_path is None:
                    if not href.startswith(("#", "mailto:", "tel:")):
                        warnings.append(f"Blok „{text}” zawiera link spoza /documents/: {href}")
                    continue
                file_id = file_id_of(doc_path)
                if file_id in file_ids:
                    continue
                file_ids.append(file_id)
                filename = filename_of(doc_path)
                page["links"].append(
                    {
                        "block": block_index,
                        "file_id": file_id,
                        "url": urljoin(url, href.strip()),
                        "document_path": doc_path,
                        "filename": filename,
                        "ext": extension_of(filename),
                    }
                )
            category = detect_category(text)
            declared = parse_declared_count(text)
            page["blocks"].append(
                {"text": text, "category": category, "declared_count": declared, "file_ids": file_ids}
            )
            warnings.extend(_block_warnings(page, block_index))
    return page


def _block_warnings(page: dict, index: int) -> list[str]:
    """Source anomalies of one block (category, counts, files from other months)."""
    block = page["blocks"][index]
    text, category, declared = block["text"], block["category"], block["declared_count"]
    links = [link for link in page["links"] if link["block"] == index]
    out: list[str] = []
    if links and category is None:
        out.append(f"Nie rozpoznano kategorii bloku „{text}” (linkuje plik).")
    if declared and not links:
        out.append(f"Blok „{text}” deklaruje {declared} {_plural_pozycja(declared)}, ale nie linkuje pliku.")
    if declared == 0 and links:
        out.append(f"Blok „{text}” deklaruje 0 pozycji, ale linkuje plik (zwykle pusty wzór tabeli).")
    if len(links) > 1:
        names = ", ".join(f"„{link['filename']}”" for link in links)
        out.append(f"Blok „{text}” linkuje {len(links)} pliki: {names}.")
    page_year, page_month = (int(x) for x in page["period"].split("-")) if page["period"] else (None, None)
    for link in links:
        name = link["filename"]
        if link["ext"] not in ("xlsx", "xls"):
            out.append(f"Plik „{name}” ma nietypowe rozszerzenie .{link['ext']}.")
        file_category = detect_category(name)
        if category and file_category and file_category != category:
            out.append(
                f"Nazwa pliku „{name}” sugeruje kategorię {file_category}, a blok „{text}” – {category}."
            )
        year, month = find_period(name, short_year=True)
        if page_month and month and (
            month != page_month or (year is not None and year != page_year)
        ):
            out.append(
                f"Plik „{name}” dotyczy innego miesiąca ({_fmt_period(year, month)}) "
                f"niż strona ({page['period']})."
            )
    return out


# =============================================================================
# BAiPP pages (city architecture bureau, architektura.um.warszawa.pl)
# =============================================================================


def detect_baipp_category(text: str | None) -> str | None:
    """Category of a BAiPP attachment from its link text or file name.

    Like :func:`detect_category`, plus the bureau's abbreviations: "w spr. ust. lokalizacji
    inwestycji celu publ.", "licp" (``informacja_dec._licp_pow_gmi_…``) → ``cp``.
    """
    category = detect_category(text)
    if category or not text:
        return category
    t = _words(text)
    if re.search(r" (?:licp|ulicp) | lokalizacj[a-z]* inwestycj| cel[a-z]* publ", t):
        return "cp"
    return None


def baipp_series(text: str | None) -> str | None:
    """ULICP series named in a link text / file name: ``c2`` = "o znaczeniu powiatowym i gminnym"
    (``pow-gm``, ``pow_gmi``), ``c1`` = "o znaczeniu krajowym i wojewódzkim" (``kraj-woj``)."""
    t = _words(text or "")
    local = bool(re.search(r" (?:powiat|gmin|pow gm)", t))
    national = bool(re.search(r" (?:krajow|wojewodzk|kraj woj)", t))
    if local == national:
        return None
    return "c2" if local else "c1"


def _years_in(text: str) -> list[int]:
    """4-digit years in a text ("IX.2026", "I-XII 2025", "sierpień - grudzień 2020 r.")."""
    return [int(y) for y in re.findall(r"(?<!\d)(20\d\d)(?!\d)", text or "")]


def _slug_of(url: str) -> str:
    """``page_id`` of a BAiPP page: the slug after ``/-/``, else the last path segment."""
    return page_id_of(url) or urlsplit(url).path.strip("/").rsplit("/", 1)[-1] or url


def _archive_stubs(articles: list[Node], container: Node, url: str) -> list[dict] | None:
    """Pages linked from the "Dane z ubiegłych lat" box: ``[{"url", "page_id", "title"}]``.

    ``None`` when the page has no such box. Only same-host ``/-/<slug>`` links count; the slugs
    are irregular (``rejestry2022`` vs ``rejestry23``), so they are never guessed.
    """
    host = (urlsplit(url).hostname or "").lower()
    for article in articles:
        if article is container:
            continue
        text = fold(clean_text(article.text()))
        if "ubieglych lat" not in text and "lat ubieglych" not in text:
            continue
        stubs: list[dict] = []
        for anchor in article.find_all("a"):
            target = urljoin(url, anchor.attrs.get("href", "").strip())
            parts = urlsplit(target)
            if (parts.hostname or "").lower() != host or "/-/" not in parts.path:
                continue
            clean_url = urlunsplit(parts._replace(query="", fragment=""))
            stubs.append({"url": clean_url, "page_id": _slug_of(clean_url), "title": clean_text(anchor.text())})
        return stubs
    return None


def parse_baipp_page(html: str, url: str, *, today: str | None = None) -> tuple[dict, list[dict] | None]:
    """Parse a BAiPP page (the current-year page or a yearly archive page).

    Returns ``(page, archive)``: ``page`` is a manifest page dict with ``source: "baipp"``, one block
    per attachment link (``category`` from the link text, ``declared_count`` null, ``series``
    ``c1``/``c2`` for ULICP lists) and the internal ``links`` (as :func:`parse_monthly_page`);
    ``archive`` lists the yearly pages of the "Dane z ubiegłych lat" box (``None`` without a box).

    The attachments are in the first ``journal-content-article`` that links ``/documents/``.
    ``period`` is the year (``YYYY``) from the title ("… (2025 r.)"), else from the link texts
    ("… IX.2026"), else the running year of ``today`` (ISO date; default: now).
    """
    root = parse_html(html)
    articles = list(root.find_all(cls="journal-content-article"))

    def documents(node: Node) -> list[Node]:
        return [a for a in node.find_all("a") if document_path_of(a.attrs.get("href", ""), url)]

    container = next((a for a in articles if documents(a)), articles[0] if articles else root)
    title = _page_title(root, container)
    title = re.sub(r"\s+-\s+Architektura, planowanie, zabytki\s*$", "", title)
    time_node = next((n for n in container.find_all("time") if n.attrs.get("datetime")), None)
    page: dict = {
        "page_id": _slug_of(url),
        "url": url,
        "title": title,
        "period": None,
        "published_at": (clean_text(time_node.attrs["datetime"]) or None) if time_node is not None else None,
        "summary": None,
        "index_page": None,
        "source": "baipp",
        "blocks": [],
        "links": [],
        "warnings": [],
    }
    warnings: list[str] = page["warnings"]
    link_years: Counter[int] = Counter()
    for anchor in documents(container):
        href = anchor.attrs["href"]
        doc_path = document_path_of(href, url)
        file_id = file_id_of(doc_path)
        if any(file_id in b["file_ids"] for b in page["blocks"]):
            continue
        text = clean_text(anchor.text())
        filename = filename_of(doc_path)
        category = detect_baipp_category(text) or detect_baipp_category(filename)
        series = (baipp_series(text) or baipp_series(filename)) if category == "cp" else None
        page["blocks"].append({"text": text, "category": category, "declared_count": None,
                               "file_ids": [file_id], "series": series})
        page["links"].append({"block": len(page["blocks"]) - 1, "file_id": file_id, "url": urljoin(url, href.strip()),
                              "document_path": doc_path, "filename": filename, "ext": extension_of(filename)})
        link_years.update(set(_years_in(text)))
        if category is None:
            warnings.append(f"Nie rozpoznano kategorii załącznika „{text or filename}”.")
        elif category == "cp" and series is None:
            warnings.append(f"Nie rozpoznano serii decyzji ULICP (krajowe/wojewódzkie czy powiatowe/gminne) "
                            f"załącznika „{text or filename}”.")
        if extension_of(filename) not in ("xlsx", "xls"):
            warnings.append(f"Plik „{filename}” ma nietypowe rozszerzenie .{extension_of(filename)}.")
    if not page["blocks"]:
        warnings.append("Na stronie nie znaleziono załączników z listami (możliwa zmiana układu strony).")

    title_years = _years_in(title)
    if title_years:
        year = title_years[-1]
    elif link_years:
        year = link_years.most_common(1)[0][0]
    else:
        year = int((today or _now_iso())[:4])
        warnings.append(f"Nie ustalono roku zestawień ani z tytułu, ani z opisów plików – przyjęto bieżący rok "
                        f"({year}).")
    page["period"] = f"{year:04d}"
    for block in page["blocks"]:
        other = sorted(set(_years_in(block["text"])) - {year})
        if other:
            warnings.append(f"Załącznik „{block['text']}” dotyczy innego roku ({', '.join(map(str, other))}) "
                            f"niż strona ({year}).")
    return page, _archive_stubs(articles, container, url)


def crawl_baipp(
    session: requests.Session,
    url: str = BAIPP_URL,
    *,
    previous: dict | None = None,
) -> tuple[list[dict], bool]:
    """Fetch the BAiPP current-year page and every archive page linked from its "Dane z ubiegłych lat" box.

    Returns ``(pages, complete)`` – parsed pages (with ``links``), current page first – and whether the
    list of archive pages could be read; only then may BAiPP pages missing from this crawl be marked
    ``removed_from_source_at``. Pages that fail to load are taken from ``previous`` (a manifest) with
    a warning; if the current page itself fails, every previous BAiPP page is returned unchanged.
    """
    prev_pages = {p["page_id"]: p for p in (previous or {}).get("pages", []) if p.get("source") == "baipp"}
    prev_files = {f["file_id"]: f for f in (previous or {}).get("files", [])}
    main_id = _slug_of(url)
    try:
        html = get_text(session, url)
    except requests.RequestException as exc:
        log.error("BAiPP: %s: fetch failed: %s", url, exc)
        pages = [_page_from_previous(p, prev_files) for p in prev_pages.values()]
        for page in pages:
            if page["page_id"] == main_id:
                page["warnings"].append("Nie udało się pobrać strony; użyto poprzedniej wersji.")
        return pages, False

    main, archive = parse_baipp_page(html, url)
    pages = [main]
    log.info("BAiPP %s -> %s: %d attachment(s)", main["title"], main["period"], len(main["blocks"]))
    if archive is None:
        main["warnings"].append("Nie znaleziono ramki „Dane z ubiegłych lat” – strony archiwalne przyjęto "
                                "z poprzedniego manifestu.")
        return pages, False

    seen = {main["page_id"]}
    for number, stub in enumerate(archive, start=1):
        if stub["page_id"] in seen:
            continue
        seen.add(stub["page_id"])
        try:
            page_html = get_text(session, stub["url"])
        except requests.RequestException as exc:
            log.error("BAiPP [%d/%d] %s: fetch failed: %s", number, len(archive), stub["url"], exc)
            if stub["page_id"] in prev_pages:
                page = _page_from_previous(prev_pages[stub["page_id"]], prev_files)
                page["warnings"].append("Nie udało się pobrać strony; użyto poprzedniej wersji.")
            else:
                years = _years_in(stub["title"])
                page = {
                    "page_id": stub["page_id"], "url": stub["url"], "title": stub["title"],
                    "period": f"{years[-1]:04d}" if years else None, "published_at": None, "summary": None,
                    "index_page": None, "source": "baipp", "blocks": [], "links": [],
                    "warnings": [f"Nie udało się pobrać strony ({type(exc).__name__})."],
                }
        else:
            page, _ = parse_baipp_page(page_html, stub["url"])
            stub_years = _years_in(stub["title"])
            if stub_years and page["period"] != f"{stub_years[-1]:04d}":
                page["warnings"].append(f"Link „{stub['title']}” wskazuje rok {stub_years[-1]}, a tytuł strony "
                                        f"– {page['period']}.")
        pages.append(page)
        log.info("BAiPP [%d/%d] %s -> %s: %d attachment(s)%s", number, len(archive), page["title"], page["period"],
                 len(page["blocks"]), f", {len(page['warnings'])} warning(s)" if page["warnings"] else "")
    return pages, True


# =============================================================================
# Manifest assembly
# =============================================================================


def _source_rank(entry: dict) -> int:
    source = entry.get("source") or "district"
    return SOURCES.index(source) if source in SOURCES else len(SOURCES)


def _sort_pages(pages: Iterable[dict]) -> list[dict]:
    """Grouped by source (district, then BAiPP); within a source newest period first (then newest
    ``published_at``, then ``page_id``); pages without a period go last. Relies on :func:`sorted`
    being stable."""
    out = sorted(pages, key=lambda p: p["page_id"])
    out.sort(key=lambda p: p.get("published_at") or "", reverse=True)
    out.sort(key=lambda p: p.get("period") or "", reverse=True)
    out.sort(key=lambda p: p.get("period") is None)
    out.sort(key=_source_rank)
    return out


def _sort_files(files: Iterable[dict]) -> list[dict]:
    """Grouped by source; by first-page period (newest first), then file name, then ``file_id``."""
    out = sorted(files, key=lambda f: (f["filename"], f["file_id"]))
    out.sort(key=lambda f: f.get("period") or "", reverse=True)
    out.sort(key=lambda f: f.get("period") is None)
    out.sort(key=_source_rank)
    return out


def _chrono_key(page: dict) -> tuple:
    """Oldest-first key: (period, published_at, page_id); unknown periods last."""
    return (page.get("period") is None, page.get("period") or "", page.get("published_at") or "", page["page_id"])


def build_manifest(
    pages: list[dict],
    *,
    index_url: str = INDEX_URL,
    raw_dir: Path | str = DEFAULT_RAW,
    generated_at: str | None = None,
) -> dict:
    """Assemble the manifest from parsed pages (as returned by :func:`parse_monthly_page`).

    * pages are grouped by source and sorted newest period first; their internal ``links`` are dropped;
    * files are de-duplicated by ``file_id``; ``page_ids`` lists every linking
      page **oldest first** (the first one is the original publication), and
      ``category``/``period`` come from that first page's linking block;
    * the file ``url`` is the most recent version (highest ``?t=``) seen; ``source`` is the linking page's
      source (``district`` / ``baipp``), BAiPP files also carry the ULICP ``series`` of their block;
    * download fields (``sha256``…) are ``None`` until :func:`download_files` runs.
    """
    raw_dir = Path(raw_dir)
    files: dict[str, dict] = {}
    for page in sorted(pages, key=_chrono_key):
        for link in page.get("links", []):
            block = page["blocks"][link["block"]]
            entry = files.get(link["file_id"])
            if entry is None:
                entry = files[link["file_id"]] = {
                    "file_id": link["file_id"],
                    "source": page.get("source") or "district",
                    "url": link["url"],
                    "document_path": link["document_path"],
                    "filename": link["filename"],
                    "ext": link["ext"],
                    "category": block["category"],
                    "period": page.get("period"),
                    "page_ids": [],
                    "local_path": _display_path(raw_dir / f"{link['file_id']}.{link['ext']}"),
                    "sha256": None,
                    "size": None,
                    "downloaded_at": None,
                    "last_modified": None,
                    "history": [],
                }
                if entry["source"] == "baipp":
                    entry["series"] = block.get("series")
            elif entry["category"] is None and block["category"] is not None:
                entry["category"] = block["category"]
            if _version_of(link["url"]) > _version_of(entry["url"]):
                entry["url"] = link["url"]
            if page["page_id"] not in entry["page_ids"]:
                entry["page_ids"].append(page["page_id"])

    return {
        "generated_at": generated_at or _now_iso(),
        "index_url": index_url,
        "pages": [{k: v for k, v in page.items() if k != "links"} for page in _sort_pages(pages)],
        "files": _sort_files(files.values()),
    }


def _page_from_previous(prev_page: dict, prev_files: dict[str, dict]) -> dict:
    """Rebuild a parsed-page dict (with ``links``) from a previous manifest entry."""
    page = json.loads(json.dumps(prev_page))  # deep copy
    page.setdefault("warnings", [])
    page.setdefault("source", "district")   # manifests written before the BAiPP source existed
    page["links"] = []
    for index, block in enumerate(page.get("blocks", [])):
        for file_id in block.get("file_ids", []):
            prev = prev_files.get(file_id)
            if prev is None:
                continue
            page["links"].append(
                {
                    "block": index,
                    "file_id": file_id,
                    "url": prev["url"],
                    "document_path": prev["document_path"],
                    "filename": prev["filename"],
                    "ext": prev.get("ext") or extension_of(prev["filename"]),
                }
            )
    return page


# =============================================================================
# Downloads
# =============================================================================

_MAGIC = {
    "xlsx": b"PK\x03\x04",
    "xlsm": b"PK\x03\x04",
    "docx": b"PK\x03\x04",
    "ods": b"PK\x03\x04",
    "zip": b"PK\x03\x04",
    "xls": b"\xd0\xcf\x11\xe0",
    "doc": b"\xd0\xcf\x11\xe0",
    "pdf": b"%PDF",
}


def _validate_content(content: bytes, ext: str, content_type: str = "") -> None:
    """Raise ``ValueError`` if ``content`` is obviously not a file of type ``ext``.

    Zip-based formats (.xlsx …) are checked whole – every member's CRC – so a truncated or broken new
    version never replaces a readable copy."""
    if not content:
        raise ValueError("empty response body")
    magic = _MAGIC.get(ext)
    if magic is not None and not content.startswith(magic):
        raise ValueError(f"response is not a valid .{ext} file (got {content[:16]!r}…)")
    if magic == b"PK\x03\x04":
        try:
            with zipfile.ZipFile(io.BytesIO(content)) as zf:
                bad = zf.testzip()
        except (zipfile.BadZipFile, EOFError, OSError, ValueError, NotImplementedError) as exc:
            raise ValueError(f"response is a broken .{ext} archive ({type(exc).__name__}: {exc})") from exc
        if bad is not None:
            raise ValueError(f"response is a broken .{ext} archive (bad member {bad!r})")
    if magic is None:
        head = content[:512].lstrip().lower()
        if head.startswith((b"<!doctype html", b"<html")) or "text/html" in content_type.lower():
            raise ValueError("server returned an HTML page instead of a file")


def _sha256_file(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 16), b""):
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


def _atomic_write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.part")
    try:
        with tmp.open("wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink()


def _http_date_to_iso(value: str | None) -> str | None:
    if not value:
        return None
    try:
        when = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return value
    if when is None:
        return value
    if when.tzinfo is None:
        when = when.replace(tzinfo=UTC)
    return when.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _mtime_iso(path: Path) -> str:
    return datetime.fromtimestamp(path.stat().st_mtime, UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _display_path(path: Path) -> str:
    """Project-relative POSIX path when inside the project, else absolute."""
    resolved = Path(os.path.abspath(path))
    try:
        return resolved.relative_to(PROJECT_ROOT).as_posix()
    except ValueError:
        return resolved.as_posix()


def download_files(
    session: requests.Session | None,
    manifest: dict,
    raw_dir: Path | str,
    refresh: bool = False,
    previous: dict | None = None,
    *,
    download: bool = True,
) -> dict[str, int]:
    """Bring ``raw_dir`` in sync with ``manifest["files"]`` (mutates the entries).

    Per file (local copy ``raw_dir/<file_id>.<ext>``):

    * ``keep`` - local copy exists and the previous manifest has the same URL
      (incl. ``?t=``) and the same sha256: metadata is carried over;
    * ``adopt`` - local copy exists but there is no previous entry: hash it,
      ``downloaded_at`` = file mtime, ``last_modified`` from ``?t=``, nothing
      is downloaded;
    * ``download`` - missing locally, ``refresh=True``, the ``?t=`` version
      changed (the old ``{url, sha256, downloaded_at}`` is appended to
      ``history``) or the local copy no longer matches the recorded hash.
      Content is validated (zip magic for .xlsx), written to a temp file and
      moved into place with :func:`os.replace`. If the content changed, the
      previous bytes are kept as ``raw_dir/history/<file_id>-<sha12>.<ext>``.

    With ``download=False`` (or ``session=None``) nothing is fetched; files that
    would need a download keep whatever is on disk (or stay ``None``).
    A failed download is logged and recorded as ``entry["error"]``; it never
    aborts the run. Returns counters per action.
    """
    raw_dir = Path(raw_dir)
    raw_dir.mkdir(parents=True, exist_ok=True)
    prev_files = {f["file_id"]: f for f in (previous or {}).get("files", []) if "file_id" in f}
    can_download = download and session is not None
    stats: Counter[str] = Counter()
    total = len(manifest["files"])

    for number, entry in enumerate(manifest["files"], start=1):
        local = raw_dir / f"{entry['file_id']}.{entry['ext']}"
        entry["local_path"] = _display_path(local)
        entry.pop("error", None)
        prev = prev_files.get(entry["file_id"])
        history = [dict(h) for h in (prev or {}).get("history", [])]
        entry["history"] = history
        exists = local.is_file()

        reason = None
        if refresh:
            reason = "refresh"
        elif not exists:
            reason = "missing"
        elif prev is not None and prev.get("url") != entry["url"]:
            reason = "new version (?t= changed)"
        elif prev is not None and prev.get("sha256"):
            sha, size = _sha256_file(local)
            if sha != prev["sha256"]:
                reason = "local copy differs from manifest"
            else:
                entry.update(
                    sha256=sha,
                    size=size,
                    downloaded_at=prev.get("downloaded_at"),
                    last_modified=prev.get("last_modified") or _version_iso(entry["url"]),
                )
                stats["kept"] += 1
                continue

        if reason is None:  # exists, no usable previous entry -> adopt (it matches the current URL)
            _describe_local(entry, local, (prev or {}).get("last_modified") or _version_iso(entry["url"]))
            stats["adopted"] += 1
            continue

        if not can_download:
            if exists:  # possibly stale copy: only trust what the previous manifest knew
                _describe_local(entry, local, (prev or {}).get("last_modified"))
            log.warning("[%d/%d] %s: needs download (%s) but downloads are disabled",
                        number, total, entry["filename"], reason)
            stats["skipped"] += 1
            continue

        log.info("[%d/%d] downloading %s (%s)", number, total, entry["filename"], reason)
        try:
            response = fetch(session, entry["url"])
            content = response.content
            _validate_content(content, entry["ext"], response.headers.get("Content-Type", ""))
        except (requests.RequestException, ValueError) as exc:
            log.error("[%d/%d] %s: download failed: %s", number, total, entry["filename"], exc)
            entry["error"] = f"{type(exc).__name__}: {exc}"
            if exists and prev is not None and prev.get("sha256") and _sha256_file(local)[0] == prev["sha256"]:
                # the copy we have is the previous version: describe it as such (its URL included), so the new
                # ?t= version is tried again by the next crawl
                entry.update({k: prev.get(k) for k in ("url", "sha256", "size", "downloaded_at", "last_modified")})
            elif exists:
                _describe_local(entry, local, (prev or {}).get("last_modified"))
            stats["failed"] += 1
            continue

        new_sha = hashlib.sha256(content).hexdigest()
        record = _history_record(entry, prev, local if exists else None, new_sha, raw_dir)
        if record is not None:
            history.append(record)
        _atomic_write_bytes(local, content)
        entry.update(
            sha256=new_sha,
            size=len(content),
            downloaded_at=_now_iso(),
            last_modified=_http_date_to_iso(response.headers.get("Last-Modified"))
            or _version_iso(entry["url"]),
        )
        stats["downloaded"] += 1

    return dict(stats)


def _describe_local(entry: dict, local: Path, last_modified: str | None) -> None:
    """Fill hash/size/dates of ``entry`` from the copy on disk (no download)."""
    sha, size = _sha256_file(local)
    entry.update(sha256=sha, size=size, downloaded_at=_mtime_iso(local), last_modified=last_modified)


def _version_iso(url: str) -> str | None:
    """Liferay's ``?t=`` (ms since epoch) as ISO UTC.

    Verified on 2026-10-23 to equal the HTTP ``Last-Modified`` of the file to
    the second, so it stands in for it when a file was not downloaded.
    """
    version = _version_of(url)
    if not version:
        return None
    return datetime.fromtimestamp(version // 1000, UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _history_record(
    entry: dict, prev: dict | None, local: Path | None, new_sha: str, raw_dir: Path
) -> dict | None:
    """Describe the version being replaced (and archive its bytes if they differ).

    A record is produced when the previous manifest knew this file and either
    its URL (``?t=``) or its content changed, or - without a previous entry -
    when an existing local copy is about to be overwritten with different bytes.
    The bytes being overwritten are copied to ``raw_dir/history/`` first.
    """
    old_sha = _sha256_file(local)[0] if local is not None else None
    archived: Path | None = None
    if old_sha is not None and old_sha != new_sha:
        archived = raw_dir / "history" / f"{entry['file_id']}-{old_sha[:12]}.{entry['ext']}"
        if not archived.exists():
            archived.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(local, archived)

    if prev is not None and prev.get("sha256"):
        if prev.get("url") == entry["url"] and prev["sha256"] == new_sha:
            return None
        record = {"url": prev.get("url"), "sha256": prev["sha256"], "downloaded_at": prev.get("downloaded_at")}
        if archived is not None and prev["sha256"] == old_sha:
            record["archived_path"] = _display_path(archived)
        return record
    if archived is not None:
        return {
            "url": None,
            "sha256": old_sha,
            "downloaded_at": _mtime_iso(local),
            "archived_path": _display_path(archived),
        }
    return None


# =============================================================================
# Manifest I/O, summary, orchestration
# =============================================================================


def load_manifest(path: Path | str) -> dict | None:
    """Read a manifest, or ``None`` if it is missing or unreadable."""
    path = Path(path)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        log.warning("ignoring unreadable previous manifest %s: %s", path, exc)
        return None
    return data if isinstance(data, dict) else None


def write_manifest(manifest: dict, path: Path | str) -> None:
    """Atomically write pretty, UTF-8 JSON (``ensure_ascii=False``)."""
    text = json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
    _atomic_write_bytes(Path(path), text.encode("utf-8"))


def summarize(manifest: dict) -> dict:
    """Totals used for the CLI report and sanity checks."""
    blocks = [(p, b) for p in manifest["pages"] for b in p["blocks"]]
    declared: Counter[str] = Counter()
    for _, block in blocks:
        if block["declared_count"] is not None:
            declared[block["category"] or "unknown"] += block["declared_count"]
    files = manifest["files"]
    return {
        "pages": len(manifest["pages"]),
        "pages_by_source": dict(Counter(p.get("source") or "district" for p in manifest["pages"])),
        "periods": len({p["period"] for p in manifest["pages"] if p.get("period")}),
        "pages_without_period": [p["page_id"] for p in manifest["pages"] if not p.get("period")],
        "pages_without_published_at": sum(1 for p in manifest["pages"] if not p.get("published_at")),
        "blocks": len(blocks),
        "blocks_with_links": sum(1 for _, b in blocks if b["file_ids"]),
        "blocks_with_links_without_category": [
            (p["page_id"], b["text"]) for p, b in blocks if b["file_ids"] and b["category"] is None
        ],
        "blocks_without_declared_count": sum(1 for _, b in blocks if b["declared_count"] is None),
        "links": sum(len(b["file_ids"]) for _, b in blocks),
        "files": len(files),
        "files_by_source": dict(Counter(f.get("source") or "district" for f in files)),
        "files_removed_from_source": [f["file_id"] for f in files if f.get("removed_from_source_at")],
        "files_by_category": dict(Counter(f["category"] or "unknown" for f in files)),
        "files_by_ext": dict(Counter(f["ext"] for f in files)),
        "files_linked_from_several_pages": [f["file_id"] for f in files if len(f["page_ids"]) > 1],
        "files_missing_locally": [f["file_id"] for f in files if not f.get("sha256")],
        "files_with_errors": [f["file_id"] for f in files if f.get("error")],
        "declared_totals": dict(declared),
        "warnings": sum(len(p.get("warnings", [])) for p in manifest["pages"]),
    }


#: page warning when a monthly page came back without its list of files (and is taken from the last crawl)
STALE_PAGE_WARNING = ("Strona nie zawierała listy plików (np. strona serwisowa lub błąd serwisu) – użyto "
                      "poprzedniej wersji.")


def _looks_broken(page: dict, stub: dict, prev: dict | None) -> bool:
    """A monthly page answered with HTTP 200 but without its article (maintenance / error / WAF page): it
    links no file although the previous crawl found some, and its title is not the month the index names."""
    if prev is None or page["links"] or not any(b.get("file_ids") for b in prev.get("blocks", [])):
        return False
    return page.get("period") is None or clean_text(stub.get("title") or "") != page.get("title")


def _crawl_district(
    session: requests.Session,
    index_url: str,
    max_index_pages: int | None,
    prev_pages: dict[str, dict],
    prev_files: dict[str, dict],
    stale: list[str] | None = None,
) -> list[dict]:
    """Crawl the district index and parse every monthly page (raises if the index is unreachable).

    A page that loads but has lost its file list (:func:`_looks_broken`) is taken from the previous
    manifest with a warning and its id is appended to ``stale`` (the build then exits with code 3)."""
    stubs = crawl_index(session, index_url, max_pages=max_index_pages)
    if not stubs:
        raise RuntimeError(f"no monthly pages found at {index_url}")
    log.info("index: %d monthly page(s)", len(stubs))

    pages: list[dict] = []
    for number, stub in enumerate(stubs, start=1):
        try:
            html = get_text(session, stub["url"])
        except requests.RequestException as exc:
            log.error("[%d/%d] %s: fetch failed: %s", number, len(stubs), stub["url"], exc)
            if stub["page_id"] in prev_pages:
                page = _page_from_previous(prev_pages[stub["page_id"]], prev_files)
                page["warnings"].append("Nie udało się pobrać strony; użyto poprzedniej wersji.")
            else:
                page = {
                    "page_id": stub["page_id"], "url": stub["url"], "title": stub["title"],
                    "period": parse_period(stub["title"]), "published_at": None,
                    "summary": None, "index_page": None, "source": "district", "blocks": [], "links": [],
                    "warnings": [f"Nie udało się pobrać strony ({type(exc).__name__})."],
                }
        else:
            page = parse_monthly_page(html, stub["url"])
            prev = prev_pages.get(stub["page_id"])
            if _looks_broken(page, stub, prev):
                log.error("[%d/%d] %s: the page lists no files any more (title %r) – using the previous version",
                          number, len(stubs), stub["url"], page.get("title"))
                page = _page_from_previous(prev, prev_files)
                if STALE_PAGE_WARNING not in page["warnings"]:
                    page["warnings"].append(STALE_PAGE_WARNING)
                if stale is not None:
                    stale.append(stub["page_id"])
        _merge_stub(page, stub)
        pages.append(page)
        log.info(
            "[%d/%d] %s -> %s: %d block(s), %d link(s)%s",
            number, len(stubs), page["title"], page["period"], len(page["blocks"]),
            len(page["links"]), f", {len(page['warnings'])} warning(s)" if page["warnings"] else "",
        )
    return pages


def _retain_snapshots(manifest: dict, previous: dict | None, today: str, *, mark: bool) -> int:
    """Keep BAiPP files the pages no longer link (earlier monthly snapshots of the current year).

    The current-year page links a new file every month and drops the previous one; every snapshot
    we ever downloaded stays a source of its records, so its manifest entry (and ``data/raw`` copy)
    is carried over, with ``removed_from_source_at`` = the first crawl that missed it (``mark``:
    only when the BAiPP crawl was complete). Returns the number of retained entries.
    """
    linked = {f["file_id"] for f in manifest["files"]}
    kept = []
    for prev in (previous or {}).get("files", []):
        if prev.get("source") != "baipp" or prev.get("file_id") in linked:
            continue
        entry = json.loads(json.dumps(prev))  # deep copy
        if mark:
            entry.setdefault("removed_from_source_at", today)
        kept.append(entry)
    if kept:
        manifest["files"] = _sort_files(manifest["files"] + kept)
        log.info("BAiPP: %d snapshot file(s) no longer linked – kept in the manifest", len(kept))
    return len(kept)


def run_crawl(
    out_path: Path | str = DEFAULT_OUT,
    raw_dir: Path | str = DEFAULT_RAW,
    refresh: bool = False,
    download: bool = True,
    max_index_pages: int | None = None,
    *,
    session: requests.Session | None = None,
    index_url: str = INDEX_URL,
    sources: Iterable[str] = SOURCES,
    baipp_url: str = BAIPP_URL,
) -> dict:
    """Crawl every source, sync the files and write the manifest.

    * ``sources`` – which of ``district`` / ``baipp`` to crawl (both by default); the pages and files
      of a source that is not crawled are carried over from the previous manifest unchanged.
    * District: a failing monthly page – or one that loads without its file list (a maintenance page) – is
      taken from the previous manifest (with a warning; the latter are listed in ``stale_pages``); the
      crawl raises if the index itself cannot be crawled (nothing is written then).
    * BAiPP: failures never abort the run – previous pages are kept, with a warning.
    * Pages present in the previous manifest but no longer listed are kept: after a complete crawl
      of their source they get ``removed_from_source_at`` (first date they were missed); with
      ``max_index_pages`` (or a partial BAiPP crawl) they are carried over unchanged.
    * BAiPP snapshot files no longer linked stay in the manifest (see :func:`_retain_snapshots`).

    Returns the manifest that was written to ``out_path``.
    """
    out_path, raw_dir = Path(out_path), Path(raw_dir)
    sources = tuple(sources)
    unknown = sorted(set(sources) - set(SOURCES))
    if unknown:
        raise ValueError(f"unknown source(s): {', '.join(unknown)} (known: {', '.join(SOURCES)})")
    previous = load_manifest(out_path)
    prev_pages = {p["page_id"]: p for p in (previous or {}).get("pages", [])}
    prev_files = {f["file_id"]: f for f in (previous or {}).get("files", [])}
    session = session or make_session(min_delay=DEFAULT_DELAY)

    pages: list[dict] = []
    complete: dict[str, bool] = {}
    stale: list[str] = []
    if "district" in sources:
        pages += _crawl_district(session, index_url, max_index_pages, prev_pages, prev_files, stale)
        complete["district"] = max_index_pages is None
    if "baipp" in sources:
        baipp_pages, complete["baipp"] = crawl_baipp(session, baipp_url, previous=previous)
        pages += baipp_pages

    seen = {p["page_id"] for p in pages}
    today = datetime.now(UTC).strftime("%Y-%m-%d")
    for page_id, prev_page in prev_pages.items():
        if page_id in seen:
            continue
        page = _page_from_previous(prev_page, prev_files)
        if complete.get(page["source"]):
            page.setdefault("removed_from_source_at", today)
            log.warning("page %s is no longer listed by its source; kept from previous manifest", page_id)
        pages.append(page)

    manifest = build_manifest(pages, index_url=index_url, raw_dir=raw_dir)
    _retain_snapshots(manifest, previous, today, mark=complete.get("baipp", False))
    stats = download_files(session, manifest, raw_dir, refresh=refresh, previous=previous, download=download)
    log.info("files: %s", ", ".join(f"{k}={v}" for k, v in sorted(stats.items())) or "none")
    if stale:
        manifest["stale_pages"] = sorted(stale)   # build: exit code 3 (nothing is committed or deployed)
    write_manifest(manifest, out_path)
    log.info("wrote %s", _display_path(out_path))
    return manifest


def _merge_stub(page: dict, stub: dict) -> None:
    """Fill index-only fields and cross-check the title with the index entry."""
    page["summary"] = stub.get("summary")
    page["index_page"] = stub.get("index_page")
    page.pop("removed_from_source_at", None)
    if not page.get("title"):
        page["title"] = stub.get("title") or ""
    elif stub.get("title") and clean_text(stub["title"]) != page["title"]:
        page["warnings"].append(
            f"Tytuł w indeksie („{stub['title']}”) różni się od tytułu strony („{page['title']}”)."
        )
    if page.get("period") is None:
        page["period"] = parse_period(page["title"]) or parse_period(stub.get("title"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m pipeline.crawl",
        description="Crawl the Praga-Południe WZ/ULICP pages (district + city BAiPP) and download the Excel files.",
    )
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="manifest path (default: data/manifest.json)")
    parser.add_argument("--raw", type=Path, default=DEFAULT_RAW, help="directory for downloaded files (default: data/raw)")
    parser.add_argument("--refresh", action="store_true", help="re-download every file")
    parser.add_argument("--max-index-pages", type=int, default=None, metavar="N", help="crawl only the first N index pages")
    parser.add_argument("--no-download", action="store_true", help="do not download files (hash what is on disk)")
    parser.add_argument("--delay", type=float, default=DEFAULT_DELAY,
                        help=f"minimum seconds between requests to one host (default: {DEFAULT_DELAY})")
    skip = parser.add_mutually_exclusive_group()
    skip.add_argument("--skip-district", action="store_true", help="do not crawl the district pages (keep them)")
    skip.add_argument("--skip-baipp", action="store_true", help="do not crawl the BAiPP pages (keep them)")
    parser.add_argument("--index-url", default=INDEX_URL, help=argparse.SUPPRESS)
    parser.add_argument("--baipp-url", default=BAIPP_URL, help=argparse.SUPPRESS)
    parser.add_argument("-q", "--quiet", action="store_true", help="only print warnings and the summary")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.WARNING if args.quiet else logging.INFO,
        format="%(levelname).1s %(message)s",
        stream=sys.stderr,
    )
    try:
        manifest = run_crawl(
            args.out,
            args.raw,
            refresh=args.refresh,
            download=not args.no_download,
            max_index_pages=args.max_index_pages,
            session=make_session(min_delay=args.delay),
            index_url=args.index_url,
            sources=[s for s in SOURCES if not getattr(args, f"skip_{s}")],
            baipp_url=args.baipp_url,
        )
    except (requests.RequestException, RuntimeError) as exc:
        log.error("crawl failed: %s", exc)
        return 1

    summary = summarize(manifest)
    print(json.dumps(summary, ensure_ascii=False, indent=2), file=sys.stderr)
    for page in manifest["pages"]:
        for warning in page.get("warnings", []):
            print(f"  ! {page['title']} ({page['page_id']}): {warning}", file=sys.stderr)
    return 1 if summary["files_missing_locally"] or summary["files_with_errors"] else 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
