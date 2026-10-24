"""Exports for people who do not want JSON: a CSV table for Excel and an Atom feed.

* :func:`records_to_csv` - every record as one row, tuned for Polish Excel: UTF-8 with BOM,
  semicolon delimiter, decimal comma in coordinates, CRLF line endings, RFC 4180 quoting and a
  formula-injection guard. The columns are **the same** as the in-browser "CSV" button
  (``site/js/csv.js`` → ``CSV_COLUMNS``), so a filtered download and the full table line up.
* :func:`atom_feed` - the newest records as an Atom 1.0 feed (``site/feed.xml``); every entry
  links to its permalink ``<SITE_URL>#/wpis/<id>`` and to the source Excel file.

The build writes ``records.csv`` (district + BAiPP lists) and ``permits.csv`` (GUNB RWDZ building
permits and notifications) with the same columns; the feed carries the planning decisions only
(permits would flood it).

Both functions are pure (no I/O) and deterministic: the same input gives byte-identical output.
``site_url`` is the public base URL of the site (``SITE_URL`` env in CI, e.g.
``https://user.github.io/wzSearch/``); the default ``"./"`` yields links relative to the site root,
which is right for ``feed.xml`` (readers resolve them against the feed URL) and harmless in CSV.
"""

from __future__ import annotations

import datetime as _dt
import re
import uuid
from collections.abc import Iterable, Mapping, Sequence
from typing import Any
from urllib.parse import quote
from xml.sax.saxutils import escape as _xml_escape

from .textutil import MONTHS_PL_GENITIVE

__all__ = [
    "BOM",
    "CSV_COLUMNS",
    "DELIMITER",
    "EOL",
    "FEED_LIMIT",
    "atom_feed",
    "category_text",
    "decimal_comma",
    "escape_cell",
    "permalink",
    "records_to_csv",
    "site_link",
    "to_csv",
]

BOM = "﻿"
DELIMITER = ";"
EOL = "\r\n"
FEED_LIMIT = 100

#: Same columns, same order as ``site/js/csv.js`` (keep them in sync; a pytest compares them): the v1
#: columns unchanged, then the v2 columns (DATA_MODEL.md, "CSV columns v2").
CSV_COLUMNS = [
    "id", "rodzaj", "rodzaj_opis", "postepowanie", "numer", "data", "data_w_zrodle", "okres_sprawozdawczy",
    "wnioskodawca", "typ_wnioskodawcy", "inwestycja", "adres", "ulica", "numer_budynku", "dzialki",
    "dzialki_w_zrodle", "typy_inwestycji", "obszar", "szerokosc_geogr", "dlugosc_geogr", "dokladnosc_lokalizacji",
    "uwagi", "powiazane_wpisy", "link", "plik_zrodlowy", "plik_url", "kopia_archiwalna_url", "strona_zrodlowa",
    "strona_zrodlowa_url", "arkusz_wiersz",
    "zrodlo_danych", "organ", "rozstrzygniecie", "data_wniosku", "nr_w_rejestrze", "znak_sprawy_urzedu",
    "zakres_robot", "kategoria_obiektu", "kubatura_m3",
]

_PRECISION = {"parcel": "działka", "address": "adres", "street": "ulica (przybliżona)"}
_APPLICANT = {"person": "osoba fizyczna", "organization": "firma lub instytucja", "unknown": "nieustalony"}
#: Formula guard, the same rule as site/js/csv.js: a cell starting with = + - @ TAB CR gets a leading apostrophe,
#: unless the whole cell is a plain number ("-5", "-12,5"); "-1+1" would otherwise run as a formula in Excel.
_FORMULA_RE = re.compile(r"^[=+\-@\t\r]")
_PLAIN_NUMBER_RE = re.compile(r"-?\d+(?:[.,]\d+)?")
_XML_INVALID_RE = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f￾￿]")

#: Namespace for the stable Atom ids (uuid5 of the record id) – never change it.
_FEED_NS = uuid.UUID("5b0c7a52-3c1e-4d8e-9f50-7a2e1b6d9c11")
_XLSX_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


# =============================================================================
# Links
# =============================================================================


def site_link(site_url: str | None, path: str = "") -> str:
    """Join the site base URL and a site-relative path (``"./"`` + ``"sources/x.xlsx"``)."""
    base = site_url or "./"
    if not base.endswith("/"):
        base += "/"
    return base + path.lstrip("/")


def permalink(site_url: str | None, record_id: str) -> str:
    """``<SITE_URL>#/wpis/<id>`` – the record's page in the browser app."""
    return f"{site_link(site_url)}#/wpis/{quote(record_id, safe='')}"


# =============================================================================
# CSV
# =============================================================================


def escape_cell(value: Any, delimiter: str = DELIMITER) -> str:
    """One CSV cell: ``None`` → empty, formula guard (leading ``'``), RFC 4180 quoting."""
    if value is None:
        return ""
    s = value if isinstance(value, str) else str(value)
    if _FORMULA_RE.match(s) and not _PLAIN_NUMBER_RE.fullmatch(s):
        s = "'" + s
    if delimiter in s or '"' in s or "\n" in s or "\r" in s:
        s = '"' + s.replace('"', '""') + '"'
    return s


def to_csv(header: Sequence[str], rows: Iterable[Sequence[Any]], *, bom: bool = True,
           delimiter: str = DELIMITER) -> str:
    """Serialise a header and rows (CRLF line endings, trailing newline)."""
    lines = [delimiter.join(escape_cell(c, delimiter) for c in row) for row in [header, *rows]]
    return (BOM if bom else "") + EOL.join(lines) + EOL


def decimal_comma(n: Any) -> str:
    """``52.223054`` → ``"52,223054"`` (Polish Excel); non-numbers → ``""``."""
    if isinstance(n, bool) or not isinstance(n, (int, float)):
        return ""
    return repr(n).replace(".", ",") if isinstance(n, float) else str(n)


def _join(values: Iterable[Any], sep: str = " | ") -> str:
    return sep.join(str(v) for v in values if v is not None and v != "")


def _parcel_text(p: Mapping[str, Any]) -> str:
    return f"{p.get('number')}{' (część)' if p.get('partial') else ''} obr. {p.get('obreb')}"


def _sheet_name(source: Mapping[str, Any]) -> str:
    """Sheet name for ``arkusz_wiersz``: as printed (trimmed); ``(arkusz bez nazwy)`` for a blank one (some BAiPP
    workbooks name a sheet " "); ``""`` without a sheet (RWDZ) – as ``csv.js`` renders it."""
    sheet = source.get("sheet")
    return str(sheet if sheet is not None else "").strip() or ("(arkusz bez nazwy)" if sheet is not None else "")


def _label(dictionary: Mapping[str, Mapping[str, Any]], key: Any) -> str:
    """``dictionary[key]["label"]``, else the key itself; ``""`` for no key (as ``csv.js`` does)."""
    if not key:
        return ""
    return (dictionary.get(key) or {}).get("label") or str(key)


def category_text(permit: Mapping[str, Any] | None, categories: Mapping[str, Mapping[str, Any]] | None = None) -> str:
    """``"XIII – pozostałe budynki mieszkalne"`` (the record's label, else the dictionary's); ``"XIII"``
    alone without a label; ``""`` without a category – ``categoryText`` in ``site/js/csv.js``."""
    category = (permit or {}).get("category")
    if not category:
        return ""
    label = (permit or {}).get("category_label") or ((categories or {}).get(category) or {}).get("label") or ""
    return f"{category} – {label}" if label else str(category)


def records_to_csv(
    records: Sequence[Mapping[str, Any]],
    *,
    kinds: Mapping[str, Mapping[str, Any]],
    tags: Mapping[str, Mapping[str, Any]],
    areas: Mapping[str, Mapping[str, Any]],
    files_by_id: Mapping[str, Mapping[str, Any]],
    pages_by_id: Mapping[str, Mapping[str, Any]],
    site_url: str | None = None,
    datasets: Mapping[str, Mapping[str, Any]] | None = None,
    issuers: Mapping[str, Mapping[str, Any]] | None = None,
    outcomes: Mapping[str, Mapping[str, Any]] | None = None,
    categories: Mapping[str, Mapping[str, Any]] | None = None,
) -> str:
    """Every record as one CSV row (columns: :data:`CSV_COLUMNS`).

    Multi-valued cells (several sources, warnings) are joined with ``" | "``; the source file
    URL is the official one (um.warszawa.pl, GUNB), the archive URL our mirrored copy. The
    dictionaries are those of ``records.json`` (``datasets``, ``issuers``, ``outcomes``,
    ``permit_categories``); a missing entry falls back to the code, like the browser export.
    """
    datasets, issuers, outcomes = datasets or {}, issuers or {}, outcomes or {}
    rows = []
    for r in records:
        sources = list(r.get("sources") or [])
        files = [files_by_id.get(s.get("file_id")) or {} for s in sources]
        pages = [pages_by_id.get(s.get("page_id")) or {} for s in sources]
        geo = r.get("geo") or {}
        address = r.get("address") or {}
        kind = kinds.get(r.get("kind")) or {}
        procedure = r.get("procedure")
        permit = r.get("permit") if isinstance(r.get("permit"), Mapping) else {}
        rows.append([
            r.get("id"),
            kind.get("short") or r.get("kind"),
            kind.get("label") or "",
            ((kinds.get(procedure) or {}).get("short") or procedure) if procedure else "",
            r.get("number"),
            r.get("date"),
            r.get("date_raw"),
            r.get("period"),
            r.get("applicant"),
            _APPLICANT.get(r.get("applicant_type"), _APPLICANT["unknown"]),
            r.get("investment"),
            address.get("display"),
            address.get("street"),
            address.get("number"),
            _join((_parcel_text(p) for p in r.get("parcels") or []), ", "),
            r.get("parcels_raw"),
            _join(((tags.get(t) or {}).get("label") or t for t in r.get("tags") or []), ", "),
            ((areas.get(r["area"]) or {}).get("label") or r["area"]) if r.get("area") else "",
            decimal_comma(geo.get("lat")),
            decimal_comma(geo.get("lon")),
            _PRECISION.get(geo.get("method"), geo.get("method") or ""),
            _join(r.get("warnings") or []),
            _join(r.get("related") or [], ", "),
            permalink(site_url, r["id"]),
            _join(f.get("filename") or s.get("file_id") for f, s in zip(files, sources)),
            _join(f.get("url") for f in files),
            _join(site_link(site_url, f["archive_path"]) if f.get("archive_path") else "" for f in files),
            _join(p.get("title") for p in pages),
            _join(p.get("url") for p in pages),
            _join(f"{_sheet_name(s)}!{s.get('row') if s.get('row') is not None else ''}" for s in sources),
            _label(datasets, r.get("dataset")),
            _label(issuers, r.get("issuer")),
            _label(outcomes, r.get("outcome")),
            r.get("filed_date"),
            permit.get("register_id"),
            permit.get("case_sign"),
            permit.get("scope_label"),
            category_text(permit, categories),
            decimal_comma(permit.get("cubature")),
        ])
    return to_csv(CSV_COLUMNS, rows)


# =============================================================================
# Atom feed
# =============================================================================


def _x(text: Any) -> str:
    """XML-escape text (also quotes) and drop characters XML 1.0 forbids."""
    return _xml_escape(_XML_INVALID_RE.sub("", "" if text is None else str(text)), {'"': "&quot;"})


def _polish_date(iso: str | None) -> str | None:
    """``2026-07-09`` → ``9 lipca 2026``."""
    try:
        d = _dt.date.fromisoformat(iso or "")
    except ValueError:
        return None
    return f"{d.day} {MONTHS_PL_GENITIVE[d.month]} {d.year}"


def _shorten(text: str, limit: int) -> str:
    text = " ".join((text or "").split())
    if len(text) <= limit:
        return text
    cut = text[: limit - 1].rsplit(" ", 1)[0].rstrip(" ,;:-–")
    return cut + "…"


def _entry_time(record: Mapping[str, Any], pages_by_id: Mapping[str, Mapping[str, Any]]) -> str:
    """When the entry became public: publication time of its first source page, else its own date."""
    for s in record.get("sources") or []:
        published = (pages_by_id.get(s.get("page_id")) or {}).get("published_at")
        if published:
            return published
    if record.get("date"):
        return f"{record['date']}T00:00:00Z"
    if record.get("period"):
        return f"{record['period']}-01T00:00:00Z"
    return "1970-01-01T00:00:00Z"


def _outcome_label(record: Mapping[str, Any], outcomes: Mapping[str, Mapping[str, Any]]) -> str | None:
    """Label of a stated outcome other than "granted" (a refusal must never read like a decision that
    allows building), else None."""
    outcome = record.get("outcome")
    if not outcome or outcome == "granted":
        return None
    return (outcomes.get(outcome) or {}).get("label") or outcome


def _entry_title(record: Mapping[str, Any], kinds: Mapping[str, Mapping[str, Any]],
                 outcomes: Mapping[str, Mapping[str, Any]] | None = None) -> str:
    kind = (kinds.get(record.get("kind")) or {}).get("short") or (record.get("kind") or "").upper()
    outcome = _outcome_label(record, outcomes or {})
    if outcome:
        kind = f"{kind} ({outcome.lower()})"
    place = (record.get("address") or {}).get("display")
    head = " · ".join(x for x in (kind, record.get("number"), place) if x)
    investment = _shorten(record.get("investment") or "", 110)
    return f"{head} — {investment}" if investment else head


def _entry_content(record, *, kinds, tags, areas, files_by_id, pages_by_id, site_url, datasets=None,
                   outcomes=None) -> str:
    """HTML body of an entry (returned unescaped; the caller escapes it into the XML)."""
    def e(s: Any) -> str:
        return _x(s)

    kind = kinds.get(record.get("kind")) or {}
    when = _polish_date(record.get("date")) or record.get("date_raw") or "—"
    verb = "z dnia" if record.get("kind") in ("wz", "cp") else "wszczęte"
    parts = [f"<p><strong>{e(kind.get('label') or record.get('kind'))}</strong> "
             f"nr {e(record.get('number') or '—')}, {verb} {e(when)}.</p>"]
    if record.get("investment"):
        parts.append(f"<p>{e(record['investment'])}</p>")
    facts = []
    outcome = _outcome_label(record, outcomes or {})
    if outcome:
        facts.append(f"<li>Rozstrzygnięcie: {e(outcome)}</li>")
    address = (record.get("address") or {}).get("display")
    if address:
        facts.append(f"<li>Adres: {e(address)}</li>")
    if record.get("parcels"):
        facts.append(f"<li>Działki: {e(', '.join(_parcel_text(p) for p in record['parcels']))}</li>")
    elif record.get("parcels_raw"):
        facts.append(f"<li>Działki (w źródle): {e(record['parcels_raw'])}</li>")
    if record.get("area"):
        facts.append(f"<li>Obszar: {e((areas.get(record['area']) or {}).get('label') or record['area'])}</li>")
    if record.get("applicant"):
        facts.append(f"<li>Wnioskodawca: {e(record['applicant'])}</li>")
    labels = [(tags.get(t) or {}).get("label") or t for t in record.get("tags") or []]
    if labels:
        facts.append(f"<li>Rodzaj inwestycji: {e(', '.join(labels))}</li>")
    if record.get("dataset") and (datasets or {}).get(record["dataset"]):
        facts.append(f"<li>Źródło danych: {e(datasets[record['dataset']].get('label') or record['dataset'])}</li>")
    if facts:
        parts.append("<ul>" + "".join(facts) + "</ul>")
    for s in record.get("sources") or []:
        f = files_by_id.get(s.get("file_id")) or {}
        p = pages_by_id.get(s.get("page_id")) or {}
        file_link = (f'<a href="{e(f["url"])}">{e(f.get("filename") or s.get("file_id"))}</a>'
                     if f.get("url") else e(f.get("filename") or s.get("file_id")))
        sheet = str(s.get("sheet") or "").strip()
        if sheet:
            where = f" (arkusz „{e(sheet)}”, wiersz {e(s.get('row'))})"
        elif s.get("sheet") is not None:   # a sheet named " " (some BAiPP workbooks)
            where = f" (arkusz bez nazwy, wiersz {e(s.get('row'))})"
        else:
            where = ""
        page = f' na stronie <a href="{e(p["url"])}">{e(p.get("title") or s.get("page_id"))}</a>' if p.get("url") else ""
        archive = (f' · <a href="{e(site_link(site_url, f["archive_path"]))}">kopia archiwalna</a>'
                   if f.get("archive_path") else "")
        parts.append(f"<p>Źródło: plik {file_link}{where}{page}{archive}.</p>")
    if record.get("warnings"):
        parts.append("<p>Uwagi do danych: " + e("; ".join(record["warnings"])) + "</p>")
    parts.append(f'<p><a href="{e(permalink(site_url, record["id"]))}">Zobacz w wzSearch</a></p>')
    return "".join(parts)


def atom_feed(
    records: Sequence[Mapping[str, Any]],
    *,
    kinds: Mapping[str, Mapping[str, Any]],
    tags: Mapping[str, Mapping[str, Any]],
    areas: Mapping[str, Mapping[str, Any]],
    files_by_id: Mapping[str, Mapping[str, Any]],
    pages_by_id: Mapping[str, Mapping[str, Any]],
    generated_at: str,
    site_url: str | None = None,
    limit: int = FEED_LIMIT,
    datasets: Mapping[str, Mapping[str, Any]] | None = None,
    outcomes: Mapping[str, Mapping[str, Any]] | None = None,
) -> str:
    """Atom 1.0 feed of the ``limit`` newest records (by record date, then id).

    Entry ids are ``urn:uuid:`` UUIDv5 of the record id, so they never change, whatever the
    site URL; ``published``/``updated`` is when the record appeared on the publisher's site
    (publication time of its first source page), falling back to the record date. A stated
    outcome other than "granted" (refusal, discontinuation …) is named in the title.
    """
    newest = sorted(records, key=lambda r: (r.get("date") or "", _natural(r.get("id") or "")), reverse=True)[:limit]
    home = site_link(site_url)
    out = [
        '<?xml version="1.0" encoding="utf-8"?>',
        '<feed xmlns="http://www.w3.org/2005/Atom" xml:lang="pl">',
        f"  <id>urn:uuid:{uuid.uuid5(_FEED_NS, 'wzsearch:praga-poludnie:feed')}</id>",
        "  <title>wzSearch – Praga-Południe: decyzje WZ, decyzje celu publicznego (CP) i wszczęte postępowania</title>",
        "  <subtitle>Najnowsze pozycje z list publikowanych co miesiąc przez Urząd Dzielnicy Praga-Południe "
        "m.st. Warszawy i Biuro Architektury i Planowania Przestrzennego Urzędu m.st. Warszawy "
        "(nieoficjalny serwis).</subtitle>",
        f'  <link rel="alternate" type="text/html" href="{_x(home)}"/>',
        f'  <link rel="self" type="application/atom+xml" href="{_x(site_link(site_url, "feed.xml"))}"/>',
        f"  <updated>{_x(generated_at)}</updated>",
        "  <author><name>wzSearch</name></author>",
        "  <generator>wzSearch pipeline</generator>",
        "  <rights>Dane: Urząd Dzielnicy Praga-Południe m.st. Warszawy i Urząd m.st. Warszawy – Biuro "
        "Architektury i Planowania Przestrzennego (informacja publiczna); działki: GUGiK ULDK; "
        "obszary: © OpenStreetMap contributors (ODbL).</rights>",
    ]
    for r in newest:
        when = _entry_time(r, pages_by_id)
        kind = kinds.get(r.get("kind")) or {}
        out += [
            "  <entry>",
            f"    <id>urn:uuid:{uuid.uuid5(_FEED_NS, r['id'])}</id>",
            f"    <title>{_x(_entry_title(r, kinds, outcomes))}</title>",
            f'    <link rel="alternate" type="text/html" href="{_x(permalink(site_url, r["id"]))}"/>',
        ]
        for s in r.get("sources") or []:
            f = files_by_id.get(s.get("file_id")) or {}
            if f.get("url"):
                out.append(f'    <link rel="related" type="{_XLSX_TYPE}" href="{_x(f["url"])}" '
                           f'title="{_x(f.get("filename") or "plik źródłowy")}"/>')
        out += [
            f"    <published>{_x(when)}</published>",
            f"    <updated>{_x(when)}</updated>",
            f'    <category term="{_x(r.get("kind"))}" label="{_x(kind.get("label") or r.get("kind"))}"/>',
        ]
        for t in r.get("tags") or []:
            out.append(f'    <category term="{_x(t)}" label="{_x((tags.get(t) or {}).get("label") or t)}"/>')
        if r.get("investment"):
            out.append(f"    <summary>{_x(_shorten(r['investment'], 300))}</summary>")
        content = _entry_content(r, kinds=kinds, tags=tags, areas=areas, files_by_id=files_by_id,
                                 pages_by_id=pages_by_id, site_url=site_url, datasets=datasets, outcomes=outcomes)
        out += [f'    <content type="html">{_x(content)}</content>', "  </entry>"]
    out.append("</feed>")
    return "\n".join(out) + "\n"


def _natural(s: str) -> list[Any]:
    """Natural sort key: ``wz-2026-9`` < ``wz-2026-15``."""
    return [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", s)]
