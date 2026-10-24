"""Offline tests for pipeline/crawl.py and pipeline/http.py.

HTML fixtures in tests/fixtures/html/ are real pages from pragapld.um.warszawa.pl
(fetched 2026-10-23) with <script>/<svg>/<style> stripped; scout_pages.json is
the scout crawl of all 73 monthly pages with hand-reviewed expectations.
"""

from __future__ import annotations

import hashlib
import io
import json
import zipfile
from pathlib import Path

import pytest
import requests
from requests.adapters import BaseAdapter
from requests.structures import CaseInsensitiveDict

from pipeline import crawl
from pipeline import http as phttp
from pipeline.crawl import (
    INDEX_URL,
    build_manifest,
    crawl_index,
    detect_category,
    document_path_of,
    download_files,
    file_id_of,
    filename_of,
    find_period,
    index_page_url,
    parse_declared_count,
    parse_index_page,
    parse_monthly_page,
    parse_period,
    run_crawl,
    summarize,
)

ROOT = Path(__file__).resolve().parents[1]

FIXTURES = ROOT / "tests" / "fixtures" / "html"
SITE = "https://pragapld.um.warszawa.pl"
SCOUT = json.loads((FIXTURES / "scout_pages.json").read_text(encoding="utf-8"))["pages"]
def _tiny_zip(text: str = "<Types/>") -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("[Content_Types].xml", text)
    return buf.getvalue()


XLSX = _tiny_zip()  # minimal valid zip archive (downloads are checked whole)


def fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def page_url(slug: str) -> str:
    return f"{SITE}/-/{slug}"


def load_page(slug: str) -> dict:
    return parse_monthly_page(fixture(f"page_{slug}.html"), page_url(slug))


# =============================================================================
# Fakes
# =============================================================================


class FakeResponse:
    def __init__(self, url: str, status: int = 200, content: bytes | str = b"", headers=None):
        self.url = url
        self.status_code = status
        self.content = content.encode("utf-8") if isinstance(content, str) else content
        self.headers = CaseInsensitiveDict(headers or {})
        self.encoding = None

    @property
    def text(self) -> str:
        return self.content.decode(self.encoding or "utf-8")

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code} for {self.url}", response=self)


class FakeSession:
    """Serves canned responses by exact URL; unknown URLs return 404."""

    def __init__(self, routes: dict | None = None):
        self.routes = dict(routes or {})
        self.calls: list[str] = []

    def get(self, url, **kwargs):
        self.calls.append(url)
        route = self.routes.get(url)
        if callable(route):
            route = route(url)
        if isinstance(route, Exception):
            raise route
        if route is None:
            return FakeResponse(url, 404, b"not found")
        if isinstance(route, FakeResponse):
            return route
        if isinstance(route, tuple):
            content, headers = route
            return FakeResponse(url, 200, content, headers)
        return FakeResponse(url, 200, route, {"Content-Type": "text/html;charset=UTF-8"})


def cur(n: int) -> str:
    return index_page_url(INDEX_URL, n)


# =============================================================================
# Index pages & pagination
# =============================================================================


def test_index_page_url_sets_and_replaces_cur_param():
    assert cur(3) == INDEX_URL + "?_AssetPublisher_nS01Fh02AyOr_cur=3"
    assert index_page_url(cur(3), 4) == INDEX_URL + "?_AssetPublisher_nS01Fh02AyOr_cur=4"
    assert index_page_url(INDEX_URL + "?x=1", 2) == INDEX_URL + "?x=1&_AssetPublisher_nS01Fh02AyOr_cur=2"


def test_parse_index_first_page_items_and_next_link():
    stubs, next_url = parse_index_page(fixture("index_cur1.html"), cur(1))
    assert [s["page_id"] for s in stubs] == [
        "informacje-o-wszczetych-postepowaniach-09-2026",
        "informacje-o-wszczetych-postepowaniach-08-2026",
        "informacje-o-wszczetych-postepowaniach-07-2026",
        "informacje-o-wszczetych-postepowaniach-06-2026",
    ]
    assert [s["title"] for s in stubs] == ["Wrzesień 2026", "Sierpień 2026", "Lipiec 2026", "Czerwiec 2026"]
    assert stubs[0]["url"] == page_url("informacje-o-wszczetych-postepowaniach-09-2026")
    assert stubs[2]["summary"] == (
        "Wydane decyzje o warunkach zabudowy: 3 pozycje Wydane decyzje w sprawie lokalizacji CP: "
        "0 pozycji Informacje o wszczętych postępowaniach: 2 pozycje"
    )
    assert next_url == cur(2)


def test_parse_index_last_page_has_no_next_link():
    stubs, next_url = parse_index_page(fixture("index_cur19.html"), cur(19))
    assert [(s["page_id"], s["title"]) for s in stubs] == [
        ("informacje-o-wszczetych-postepowaniach-sierpien-2020", "Sierpień 2020 r.")
    ]
    assert next_url is None  # "Następna" is a disabled javascript:; link


def test_parse_index_page_past_the_end_is_empty():
    assert parse_index_page(fixture("index_cur20.html"), cur(20)) == ([], None)


def test_next_link_must_point_to_the_following_page():
    html = fixture("index_cur1.html")  # its "Następna" points to cur=2
    _, next_url = parse_index_page(html, cur(5))
    assert next_url is None


def test_index_links_must_be_http_links_on_the_office_host():
    """A javascript: link (also hidden with a TAB entity) or a foreign host never becomes a stored page URL."""
    html = synthetic_index(1, ["lipiec-2026"], has_next=False)
    for href in ("java&#9;script:alert(1)//-/lipiec-2026", "javascript:alert(1)//-/lipiec-2026",
                 "https://evil.example/x/-/lipiec-2026", "//evil.example/-/lipiec-2026"):
        bad = html.replace(f'href="{SITE}/-/lipiec-2026"', f'href="{href}"')
        assert bad != html
        assert parse_index_page(bad, cur(1)) == ([], None), href
    stubs, _ = parse_index_page(html, cur(1))
    assert [s["url"] for s in stubs] == [f"{SITE}/-/lipiec-2026"]


def test_crawl_index_follows_pagination_until_no_next_link():
    session = FakeSession({cur(1): fixture("index_cur1.html"), cur(2): fixture("index_cur19.html")})
    stubs = crawl_index(session, INDEX_URL)
    assert session.calls == [cur(1), cur(2)]
    assert [s["index_page"] for s in stubs] == [1, 1, 1, 1, 2]
    assert stubs[-1]["title"] == "Sierpień 2020 r."
    assert set(stubs[0]) == {"url", "page_id", "title", "summary", "index_page"}


def test_crawl_index_stops_on_empty_page():
    session = FakeSession({cur(1): fixture("index_cur1.html"), cur(2): fixture("index_cur20.html")})
    stubs = crawl_index(session, INDEX_URL)
    assert len(stubs) == 4
    assert session.calls == [cur(1), cur(2)]


def test_crawl_index_respects_max_pages():
    session = FakeSession({cur(1): fixture("index_cur1.html"), cur(2): fixture("index_cur19.html")})
    assert len(crawl_index(session, INDEX_URL, max_pages=1)) == 4
    assert session.calls == [cur(1)]


def synthetic_index(n: int, items: list[str], has_next: bool) -> str:
    """Index page with the real markup skeleton (event list + Liferay pager)."""
    lis = "".join(
        f'<li class="event item"><article class="event__inner"><div class="event__data">'
        f'<h3 class="event__title"><a href="{SITE}/-/{slug}" class="event__link cut-text" '
        f'title="{slug}">{slug}</a></h3><p class="event__excerpt cut-text">Wydane: 1 pozycja</p>'
        f"</div></article></li>"
        for slug in items
    )
    nxt = (
        f'<li class=""><a href="{cur(n + 1)}" target="_self"> Następna </a></li>'
        if has_next
        else '<li class="disabled"><a href="javascript:;"> Następna </a></li>'
    )
    return (
        '<div id="p_p_id_com_liferay_asset_publisher_web_portlet_AssetPublisherPortlet_INSTANCE_nS01Fh02AyOr_">'
        f'<ul class="events-component">{lis}</ul><div class="lfr-pagination"><ul class="pager">{nxt}</ul></div></div>'
    )


def test_crawl_index_hard_cap_of_200_pages():
    session = FakeSession()
    for n in range(1, 205):
        session.routes[cur(n)] = synthetic_index(n, [f"p-{n}"], has_next=True)
    stubs = crawl_index(session, INDEX_URL)
    assert len(stubs) == 200
    assert len(session.calls) == 200


def test_crawl_index_dedupes_items_shifted_between_pages():
    session = FakeSession(
        {
            cur(1): synthetic_index(1, ["a", "b"], has_next=True),
            cur(2): synthetic_index(2, ["b", "c"], has_next=False),  # "b" shifted down
        }
    )
    assert [s["page_id"] for s in crawl_index(session, INDEX_URL)] == ["a", "b", "c"]


# =============================================================================
# Monthly pages
# =============================================================================


def test_monthly_page_new_layout_2026():
    page = load_page("informacje-o-wszczetych-postepowaniach-07-2026")
    assert page["page_id"] == "informacje-o-wszczetych-postepowaniach-07-2026"
    assert page["title"] == "Lipiec 2026"
    assert page["period"] == "2026-07"
    # the article's own <time>, not the ones in the "Pozostałe" sidebar
    assert page["published_at"] == "2026-08-10T08:32:00Z"
    assert [(b["text"], b["category"], b["declared_count"]) for b in page["blocks"]] == [
        ("Wydane decyzje o warunkach zabudowy: 3 pozycje", "wz", 3),
        ("Wydane decyzje w sprawie lokalizacji CP: 0 pozycji", "cp", 0),
        ("Informacje o wszczętych postępowaniach: 2 pozycje", "ws", 2),
    ]
    # the WZ <li> links the same file twice (text link + empty link) -> one file id
    assert page["blocks"][0]["file_ids"] == [
        file_id_of(
            "/documents/50051/165304801/wydane+decyzje+wz+-++lipiec+2026.xlsx/a1c72448-169b-c0ca-59b6-70e2da95d18a"
        )
    ]
    assert page["blocks"][1]["file_ids"] == []
    assert page["warnings"] == []
    link = page["links"][0]
    assert link["url"] == (
        SITE + "/documents/50051/165304801/wydane+decyzje+wz+-++lipiec+2026.xlsx/"
        "a1c72448-169b-c0ca-59b6-70e2da95d18a?t=1786350734551"
    )
    assert link["filename"] == "wydane decyzje wz -  lipiec 2026.xlsx"
    assert link["ext"] == "xlsx"


def test_monthly_page_2020_has_no_time_and_no_counts():
    page = load_page("informacje-o-wszczetych-postepowaniach-sierpien-2020")
    assert page["title"] == "Sierpień 2020 r."
    assert page["period"] == "2020-08"
    assert page["published_at"] is None  # aside <time> elements must not leak in
    assert [(b["category"], b["declared_count"], len(b["file_ids"])) for b in page["blocks"]] == [
        ("ws", None, 1),
        ("wz", None, 1),
        ("cp", None, 1),
    ]
    assert page["blocks"][0]["text"].startswith("Rejestr decyzji o wszczętych postępowaniach")


def test_monthly_page_with_file_size_suffixes():
    page = load_page("maj-2025")
    assert page["period"] == "2025-05"
    assert [(b["category"], b["declared_count"]) for b in page["blocks"]] == [("wz", 3), ("cp", 1), ("ws", 1)]
    assert page["blocks"][0]["text"] == "Wydane decyzje o warunkach zabudowy: 3 pozycje (12,7 KB, xlsx)"
    assert len(page["blocks"]) == 3  # the trailing <p>&nbsp;</p> is not a block


def test_monthly_page_paragraph_with_br_lines_is_split_per_category():
    page = load_page("maj-2023-r-")
    assert [(b["text"], b["category"], b["declared_count"], len(b["file_ids"])) for b in page["blocks"]] == [
        ("Wydane decyzje o warunkach zabudowy – 5 pozycji", "wz", 5, 1),
        ("Wydane decyzje w sprawie lokalizacji celu publicznego – 3 pozycje", "cp", 3, 1),
        ("Informacje o wszczętych postępowaniach – 1 pozycja", "ws", 1, 1),
    ]
    assert [link["filename"] for link in page["links"]] == [
        "wydane decyzje o warunkach zabudowy MAJ 2023.xlsx",
        "wydane decyzje celu publicznego maj 2023.xlsx",
        "wszczęte-postępowania- maj 2023.xlsx",
    ]
    assert page["warnings"] == []


def test_monthly_page_linking_previous_months_file_is_flagged():
    page = load_page("artykul-93")
    assert page["title"] == "Październik 2025"
    wz = page["blocks"][0]
    assert wz["text"] == "Wydane decyzje o warunkach zabudowy: 1 pozycja"  # "1" and "pozycja" are two links
    assert wz["declared_count"] == 1
    assert [link["filename"] for link in page["links"] if link["block"] == 0] == [
        "wydane decyzje wz - wrzesień  2025.xlsx",
        "wydane decyzje wz - październik  2025.xlsx",
    ]
    assert any("linkuje 2 pliki" in w for w in page["warnings"])
    assert any("innego miesiąca (2025-09)" in w for w in page["warnings"])


def test_monthly_page_invisible_absolute_link_to_previous_months_file():
    """Oct 2022: an absolute-URL <a> around a lone &nbsp; still links the Sep 2022 CP file."""
    page = load_page("pazdziernik-2022")
    cp = page["blocks"][1]
    assert (cp["text"], cp["category"], cp["declared_count"]) == (
        "Wydane decyzje w sprawie lokalizacji celu publicznego – 1 pozycja", "cp", 1
    )
    assert [link["filename"] for link in page["links"] if link["block"] == 1] == [
        "wydane decyzje celu publicznego wrzesień -22.xlsx",
        "wydane decyzje celu publicznego październik-22.xlsx",
    ]
    assert page["links"][1]["url"].startswith(SITE + "/documents/50051/63077970/")
    assert any("innego miesiąca (2022-09) niż strona (2022-10)" in w for w in page["warnings"])


def test_monthly_page_brak_variants_count_as_zero():
    oct2020 = load_page("informacje-o-wszczetych-postepowaniach-pazdziernik-2020")
    assert [(b["category"], b["declared_count"]) for b in oct2020["blocks"]] == [
        ("ws", 0),  # "... brak wszczętych postępowań – pilk do pobrania" (ws, not wz/cp)
        ("cp", None),
        ("wz", None),
    ]
    nov2020 = load_page("informacje-o-wszczetych-postepowaniach-listopad-2020")
    assert [(b["category"], b["declared_count"]) for b in nov2020["blocks"]] == [("wz", 3), ("cp", 0), ("ws", 2)]
    assert any("deklaruje 0 pozycji, ale linkuje plik" in w for w in nov2020["warnings"])


def test_monthly_page_numbered_items_and_repeated_count():
    page = load_page("artykul-162wszczete-postepowania-maj-2021")
    assert [(b["category"], b["declared_count"]) for b in page["blocks"]] == [("ws", 11), ("wz", 2), ("cp", 1)]


def test_monthly_page_empty_month():
    page = load_page("listopad-2024")
    assert page["period"] == "2024-11"
    assert [(b["category"], b["declared_count"], b["file_ids"]) for b in page["blocks"]] == [
        ("wz", 0, []),
        ("cp", 0, []),
        ("ws", 0, []),
    ]
    assert page["links"] == []


def test_segmenter_keeps_single_category_paragraph_with_br_together():
    html = (
        '<div class="journal-content-article" data-analytics-asset-title="Maj 2024">'
        '<div class="article-description"><p>Wydane decyzje o warunkach zabudowy<br>'
        '<a href="/documents/1/2/wz.xlsx/0f0f0f0f-0000-0000-0000-000000000000?t=1">3 pozycje</a></p>'
        '<p><a href="https://example.com/x">obcy link</a></p></div></div>'
    )
    page = parse_monthly_page(html, page_url("maj-2024"))
    assert page["blocks"][0] == {
        "text": "Wydane decyzje o warunkach zabudowy 3 pozycje",
        "category": "wz",
        "declared_count": 3,
        "file_ids": [file_id_of("/documents/1/2/wz.xlsx/0f0f0f0f-0000-0000-0000-000000000000")],
    }
    assert page["blocks"][1]["file_ids"] == []
    assert any("spoza /documents/" in w for w in page["warnings"])


def test_scout_pages_hrefs_are_all_extracted_from_real_fixtures():
    """Links extracted from the fixtures equal the scout crawl's hrefs - plus the
    absolute-URL link on the Oct 2022 page that the scout crawler missed."""
    missed_by_scout = {
        "pazdziernik-2022": [
            ("/documents/50051/63077970/wydane+decyzje+celu+publicznego+wrzesie%C5%84+-22.xlsx/"
            "8b372269-abb0-42a4-9229-0adaff059c95?t=1665733161974")
        ]
    }
    by_url = {p["url"]: p for p in SCOUT}
    fixtures = sorted(FIXTURES.glob("page_*.html"))
    assert len(fixtures) == 10
    for path in fixtures:
        slug = path.stem[len("page_"):]
        page = load_page(slug)
        expected = [h for b in by_url[page_url(slug)]["blocks"] for h in b["hrefs"]]
        got = [link["url"].removeprefix(SITE) for link in page["links"]]
        assert sorted(got) == sorted(expected + missed_by_scout.get(slug, [])), slug


# =============================================================================
# Periods, categories, declared counts (table-driven)
# =============================================================================


@pytest.mark.parametrize("scout_page", SCOUT, ids=lambda p: p["title"])
def test_period_of_every_scout_title(scout_page):
    assert parse_period(scout_page["title"]) == scout_page["period"]


def test_scout_periods_are_unique_and_span_aug_2020_to_sep_2026():
    periods = [p["period"] for p in SCOUT]
    assert len(periods) == len(set(periods)) == 73
    assert min(periods) == "2020-08" and max(periods) == "2026-09"


@pytest.mark.parametrize(
    "title, expected",
    [
        ("Grudzień 2021 r.", "2021-12"),
        ("Październik 2021r.", "2021-10"),
        ("Lipiec 2025r.", "2025-07"),
        ("Styczeń 2025", "2025-01"),
        ("GRUDZIEŃ 2021 R.", "2021-12"),
        ("grudnia 2021", "2021-12"),  # genitive
        ("Za miesiąc października 2022 r.", "2022-10"),
        ("w listopadzie 2020", "2020-11"),  # locative
        ("Wrzesnień 2021 r.", "2021-09"),  # typo seen in block texts
        ("Pazdziernik 2023", "2023-10"),  # no diacritics
        ("Wrzes. 2023", "2023-09"),  # stem fallback
        ("05.2021", "2021-05"),
        ("2021-05", "2021-05"),
        ("Informacje o wszczętych postępowaniach", None),
        ("Maj", None),
        ("2021", None),
        ("", None),
        (None, None),
    ],
)
def test_parse_period_variants(title, expected):
    assert parse_period(title) == expected


def test_find_period_in_file_names():
    assert find_period("wydane decyzje wz - wrzesień  2025.xlsx") == (2025, 9)
    assert find_period("1129_1009zal1_sierpien-wszczecia_-cp-wz.xlsx") == (None, 8)
    assert find_period("wydane decyzje celu publicznego lipiec -22.xlsx") == (None, 7)
    assert find_period("wydane decyzje celu publicznego lipiec -22.xlsx", short_year=True) == (2022, 7)
    assert find_period("wrzesień - 20 pozycji", short_year=False) == (None, 9)
    assert find_period("rejestr.xlsx") == (None, None)


@pytest.mark.parametrize(
    "text, expected",
    [
        ("Wydane decyzje o warunkach zabudowy: 3 pozycje", 3),
        ("Wydane decyzje o warunkach zabudowy: 0 pozycji", 0),
        ("Informacje o wszczętych postępowaniach: 1 pozycja", 1),
        ("Wydane decyzje o warunkach zabudowy – 20 pozycje", 20),
        ("Wydane decyzje o warunkach zabudowy\xa0– 5 pozcji", 5),
        ("Wydane decyzje o warunkach zabudowy kwiecień 2021 r. –\xa03 pozycji –\xa0plik do pobrania", 3),
        ("Informacje o wszczętych postępowaniach –\xa0\xa01\xa0pozycja", 1),
        ("Wydane decyzje w sprawie lokalizacji Celu Publicznego: 1\xa0Pozycja", 1),
        ("Wydane decyzje w sprawie lokalizacji Celu Publicznego: 0 pozycja", 0),
        ("Wydane decyzje w sprawie lokalizacji Celu Publicznego: 1 pozycje", 1),
        ("Wydane decyzje o warunkach zabudowy\xa0–\xa010 pozycji", 10),
        ("Wydane decyzje o warunkach zabudowy: 4 pozycje\xa0(12,9 KB,xlsx)", 4),
        ("Informacje o wszczętych postępowaniach: 3 pozycje\xa0(18,8 KB, xlsx)", 3),
        ("1/\xa0Informacje o wszczętych postępowaniach maj 2021 r. - 11 pozycji - 11 pozycji\xa0-\xa0plik do pobrania", 11),
        ("3/Wydane decyzje w sprawie ustalenia lokalizacji celu publicznego maj 2021 r. - 1 pozycja", 1),
        ("Wydane decyzje w sprawie ustalenia lokalizacji celu publicznego czerwiec 2021r .\xa0–\xa03 pozycje", 3),
        ("Wydane decyzje w sprawie ustalenia lokalizacji inwestycji celu publicznego –\xa0BRAK w LISTOPADZIE 2020\xa0–\xa0plik do pobrania", 0),
        (("Informacja o wszczętych postępowaniach o warunkach zabudowy i ustaleniu lokalizacji inwestycji celu "
         "publicznego- w miesiącu październiku brak wszczętych postępowań –\xa0pilk do pobrania"), 0),
        ("BRAK", 0),
        ("Informacja o wydanych decyzjach w sprawie warunków zabudowy –\xa0 wrzesień 2020 r.\xa0(plik do pobrania)", None),
        ("Rejestr decyzji o warunkach zabudowy\xa0–\xa0sierpień 2020 r. (pik do pobrania).", None),
        ("Wydane decyzje o warunkach zabudowy – 5 pozycji Wydane decyzje w sprawie lokalizacji celu publicznego – 3 pozycje", None),
        ("", None),
        (None, None),
    ],
)
def test_parse_declared_count_variants(text, expected):
    assert parse_declared_count(text) == expected


def scout_blocks():
    return [(p["title"], b) for p in SCOUT for b in p["blocks"]]


@pytest.mark.parametrize("title, block", scout_blocks(), ids=lambda v: v if isinstance(v, str) else "")
def test_declared_count_of_every_scout_block(title, block):
    assert parse_declared_count(block["text"]) == block["declared_count"]


@pytest.mark.parametrize("title, block", scout_blocks(), ids=lambda v: v if isinstance(v, str) else "")
def test_category_of_every_scout_block(title, block):
    if "note" in block:
        pytest.skip(block["note"])
    assert detect_category(block["text"]) == block["category"]
    assert block["category"] is not None  # every real block is classified


@pytest.mark.parametrize(
    "text, expected",
    [
        ("Wydane decyzje o warunkach zabudowy: 3 pozycje", "wz"),
        ("Informacja o wydanych decyzjach w sprawie warunków zabudowy w październiku", "wz"),
        ("Rejestr decyzji o warunkach zabudowy – sierpień 2020 r.", "wz"),
        ("Wydane decyzje w sprawie lokalizacji CP: 0 pozycji", "cp"),
        ("Wydane decyzje w sprawie lokalizacji Celu Publicznego: 1 pozycja", "cp"),
        ("Wydane decyzja w sprawie ustalenia lokalizacji celu publicznego grudzień 2020r.", "cp"),
        ("Rejestr decyzji o ustaleniu lokalizacji inwestycji celu publicznego", "cp"),
        (("Informacja o wydanych decyzjach w sprawie ustalenia lokalizacji inwestycji celu publicznego "
         "o znaczeniu powiatowym i gminnym"), "cp"),
        ("Informacje o wszczętych postępowaniach: 2 pozycje", "ws"),
        ("Informacje o wszczętych postepowaniach – 2 pozycje", "ws"),
        ("Informacja o wszczętych postępowaniach o warunkach zabudowy i ustaleniu inwestycji celu publicznego", "ws"),
        (("Rejestr decyzji o wszczętych postępowaniach administracyjnych dotyczących w sprawie wydania decyzji "
         "o warunkach zabudowy oraz decyzji o ustaleniu lokalizacji inwestycji celu publicznego"), "ws"),
        # file names
        ("wydane decyzje wz -  lipiec 2026.xlsx", "wz"),
        ("warunki_-zabudowy-sierpien-rejestr-n-_2020.xlsx", "wz"),
        ("rejestr-n-cel-publiczny-sierpien_-2020.xlsx", "cp"),
        ("1129_1009zal1_sierpien-wszczecia_-cp-wz.xlsx", "ws"),
        ("plik do pobrania", None),
        ("", None),
    ],
)
def test_detect_category_variants(text, expected):
    assert detect_category(text) == expected


# =============================================================================
# Identifiers
# =============================================================================


def test_file_id_matches_data_model_example():
    path = "/documents/50051/165304801/wydane+decyzje+wz+-++lipiec+2026.xlsx/a1c72448-169b-c0ca-59b6-70e2da95d18a"
    assert file_id_of(path) == hashlib.sha1(path.encode()).hexdigest()[:10]
    assert document_path_of(path + "?t=1786350734551") == path
    assert document_path_of(SITE + path + "?t=1#x") == path
    assert document_path_of(path + "?t=1", page_url("x")) == path


@pytest.mark.parametrize(
    "href",
    ["/-/lipiec-2026", "https://example.com/documents/1/2/x.xlsx/u", "javascript:;", "mailto:a@b.pl", "", "#top"],
)
def test_document_path_rejects_other_links(href):
    assert document_path_of(href, page_url("x")) is None


def test_document_path_accepts_city_cdn():
    assert document_path_of("https://cdn.um.warszawa.pl/documents/1/2/a.xlsx/u?t=1") == "/documents/1/2/a.xlsx/u"


def test_filename_decoding():
    assert filename_of("/documents/50051/171050435/wydane+decyzje+cp+-+wrzesie%C5%84+2026.xlsx/"
                       "e61067dd-08a5-ddc4-d67a-439cad37e0a0") == "wydane decyzje cp - wrzesień 2026.xlsx"
    assert filename_of("/documents/1/2/plik%20test.xls") == "plik test.xls"


def test_every_scout_file_id_exists_in_data_raw():
    raw = ROOT / "data" / "raw"
    if not raw.is_dir():
        pytest.skip("data/raw not present")
    ids = set()
    for page in SCOUT:
        for block in page["blocks"]:
            for href in block["hrefs"]:
                doc_path = document_path_of(href, page["url"])
                assert doc_path is not None, href
                ids.add(file_id_of(doc_path))
    assert len(ids) == 176
    missing = sorted(i for i in ids if not (raw / f"{i}.xlsx").is_file())
    assert missing == []


# =============================================================================
# Manifest assembly
# =============================================================================


def sep_2025_page() -> dict:
    """A September 2025 page linking the same September file as artykul-93 (older version)."""
    href = ("/documents/50051/145189586/wydane+decyzje+wz+-+wrzesie%C5%84++2025.xlsx/"
            "198aa886-f4b9-8292-a213-95e491eefd12?t=1760000000000")
    html = (
        '<div class="journal-content-article" data-analytics-asset-title="Wrzesień 2025">'
        '<time datetime="2025-10-09T11:58:00Z">x</time><div class="article-description">'
        f'<p>Wydane decyzje o warunkach zabudowy: <a href="{href}">1 pozycja</a></p></div></div>'
    )
    return parse_monthly_page(html, page_url("artykul-86"))


def test_build_manifest_dedups_files_and_orders_everything(tmp_path):
    pages = [load_page("maj-2023-r-"), load_page("artykul-93"), sep_2025_page(), load_page("listopad-2024")]
    manifest = build_manifest(pages, raw_dir=tmp_path, generated_at="2026-10-23T00:00:00Z")
    assert manifest["generated_at"] == "2026-10-23T00:00:00Z"
    assert manifest["index_url"] == INDEX_URL
    assert [p["period"] for p in manifest["pages"]] == ["2025-10", "2025-09", "2024-11", "2023-05"]
    assert all("links" not in p for p in manifest["pages"])

    files = {f["filename"]: f for f in manifest["files"]}
    assert len(manifest["files"]) == 3 + 4  # Sep file shared by two pages
    sep = files["wydane decyzje wz - wrzesień  2025.xlsx"]
    assert sep["page_ids"] == ["artykul-86", "artykul-93"]  # oldest (original publication) first
    assert sep["period"] == "2025-09"
    assert sep["category"] == "wz"
    assert sep["url"].endswith("?t=1760011064914")  # newest version wins
    assert sep["local_path"] == (tmp_path / f"{sep['file_id']}.xlsx").as_posix()
    assert sep["sha256"] is None and sep["history"] == []
    # files sorted by period desc, then filename
    keys = [(f["period"], f["filename"]) for f in manifest["files"]]
    assert keys == sorted(sorted(keys, key=lambda k: k[1]), key=lambda k: k[0], reverse=True)
    assert [f["period"] for f in manifest["files"]][:3] == ["2025-10"] * 3


def test_build_manifest_is_deterministic(tmp_path):
    pages = [load_page(s) for s in ("maj-2023-r-", "artykul-93", "maj-2025")]
    a = build_manifest(pages, raw_dir=tmp_path, generated_at="x")
    b = build_manifest(list(reversed(pages)), raw_dir=tmp_path, generated_at="x")
    assert a == b


# =============================================================================
# Downloads
# =============================================================================


def one_file_manifest(tmp_path, url_t="1") -> dict:
    page = parse_monthly_page(
        '<div class="journal-content-article" data-analytics-asset-title="Maj 2025">'
        '<div class="article-description"><p>Wydane decyzje o warunkach zabudowy: '
        f'<a href="/documents/1/2/wz+maj.xlsx/0f0f0f0f-0000-0000-0000-000000000000?t={url_t}">1 pozycja</a>'
        "</p></div></div>",
        page_url("maj-2025"),
    )
    return build_manifest([page], raw_dir=tmp_path, generated_at="x")


def file_url(t="1") -> str:
    return f"{SITE}/documents/1/2/wz+maj.xlsx/0f0f0f0f-0000-0000-0000-000000000000?t={t}"


def test_download_missing_file(tmp_path):
    manifest = one_file_manifest(tmp_path)
    session = FakeSession({file_url(): (XLSX, {"Last-Modified": "Mon, 09 Jun 2025 12:00:00 GMT"})})
    stats = download_files(session, manifest, tmp_path)
    entry = manifest["files"][0]
    local = tmp_path / f"{entry['file_id']}.xlsx"
    assert stats == {"downloaded": 1}
    assert local.read_bytes() == XLSX
    assert entry["sha256"] == hashlib.sha256(XLSX).hexdigest()
    assert entry["size"] == len(XLSX)
    assert entry["last_modified"] == "2025-06-09T12:00:00Z"
    assert entry["downloaded_at"].endswith("Z")
    assert [p.name for p in tmp_path.iterdir()] == [local.name]  # no temp leftovers


def test_existing_file_without_previous_manifest_is_adopted(tmp_path):
    manifest = one_file_manifest(tmp_path)
    entry = manifest["files"][0]
    (tmp_path / f"{entry['file_id']}.xlsx").write_bytes(XLSX)
    session = FakeSession()
    assert download_files(session, manifest, tmp_path) == {"adopted": 1}
    assert session.calls == []
    assert entry["sha256"] == hashlib.sha256(XLSX).hexdigest()
    assert entry["downloaded_at"] is not None
    assert entry["last_modified"] == "1970-01-01T00:00:00Z"  # from ?t=1 (ms), no request made


def test_last_modified_falls_back_to_version_param(tmp_path):
    manifest = one_file_manifest(tmp_path, url_t="1791550167700")
    session = FakeSession({file_url("1791550167700"): (XLSX, {})})  # no Last-Modified header
    download_files(session, manifest, tmp_path)
    assert manifest["files"][0]["last_modified"] == "2026-10-09T12:49:27Z"


def test_unchanged_url_keeps_local_file_and_metadata(tmp_path):
    previous = one_file_manifest(tmp_path)
    download_files(FakeSession({file_url(): (XLSX, {})}), previous, tmp_path)
    manifest = one_file_manifest(tmp_path)
    session = FakeSession()
    assert download_files(session, manifest, tmp_path, previous=previous) == {"kept": 1}
    assert session.calls == []
    for key in ("sha256", "size", "downloaded_at", "last_modified"):
        assert manifest["files"][0][key] == previous["files"][0][key]


def test_new_version_param_redownloads_and_records_history(tmp_path):
    previous = one_file_manifest(tmp_path, url_t="1")
    download_files(FakeSession({file_url("1"): (XLSX, {})}), previous, tmp_path)
    old = dict(previous["files"][0])

    manifest = one_file_manifest(tmp_path, url_t="2")
    new_content = _tiny_zip("<Types v=\"2\"/>")
    session = FakeSession({file_url("2"): (new_content, {})})
    assert download_files(session, manifest, tmp_path, previous=previous) == {"downloaded": 1}
    entry = manifest["files"][0]
    assert entry["sha256"] == hashlib.sha256(new_content).hexdigest()
    assert len(entry["history"]) == 1
    record = entry["history"][0]
    assert {k: record[k] for k in ("url", "sha256", "downloaded_at")} == {
        "url": file_url("1"), "sha256": old["sha256"], "downloaded_at": old["downloaded_at"]
    }
    archived = Path(record["archived_path"])
    assert archived.read_bytes() == XLSX  # previous bytes preserved
    assert (tmp_path / f"{entry['file_id']}.xlsx").read_bytes() == new_content

    # a third run with the same URL keeps the file and the history
    again = one_file_manifest(tmp_path, url_t="2")
    assert download_files(FakeSession(), again, tmp_path, previous=manifest) == {"kept": 1}
    assert again["files"][0]["history"] == entry["history"]


def test_refresh_redownloads_without_history_when_unchanged(tmp_path):
    previous = one_file_manifest(tmp_path)
    download_files(FakeSession({file_url(): (XLSX, {})}), previous, tmp_path)
    manifest = one_file_manifest(tmp_path)
    session = FakeSession({file_url(): (XLSX, {})})
    assert download_files(session, manifest, tmp_path, refresh=True, previous=previous) == {"downloaded": 1}
    assert session.calls == [file_url()]
    assert manifest["files"][0]["history"] == []


def test_corrupted_local_copy_is_redownloaded(tmp_path):
    previous = one_file_manifest(tmp_path)
    download_files(FakeSession({file_url(): (XLSX, {})}), previous, tmp_path)
    local = tmp_path / f"{previous['files'][0]['file_id']}.xlsx"
    local.write_bytes(b"PK\x03\x04garbage")
    manifest = one_file_manifest(tmp_path)
    assert download_files(FakeSession({file_url(): (XLSX, {})}), manifest, tmp_path, previous=previous) == {
        "downloaded": 1
    }
    assert local.read_bytes() == XLSX


@pytest.mark.parametrize(
    "response",
    [
        FakeResponse(file_url(), 200, b"<!DOCTYPE html><html>error</html>", {"Content-Type": "text/html"}),
        FakeResponse(file_url(), 404, b"nope"),
        requests.ConnectionError("boom"),
    ],
    ids=["html-instead-of-xlsx", "http-404", "connection-error"],
)
def test_failed_download_keeps_existing_file(tmp_path, response):
    manifest = one_file_manifest(tmp_path)
    entry = manifest["files"][0]
    local = tmp_path / f"{entry['file_id']}.xlsx"
    session = FakeSession({file_url(): response})
    assert download_files(session, manifest, tmp_path, refresh=True) == {"failed": 1}
    assert "error" in entry and not local.exists() and entry["sha256"] is None

    local.write_bytes(XLSX)  # with an existing copy, the copy survives and is described
    assert download_files(session, manifest, tmp_path, refresh=True) == {"failed": 1}
    assert local.read_bytes() == XLSX
    assert entry["sha256"] == hashlib.sha256(XLSX).hexdigest()


def test_no_download_mode_never_touches_the_network(tmp_path):
    manifest = one_file_manifest(tmp_path)
    session = FakeSession({file_url(): (XLSX, {})})
    assert download_files(session, manifest, tmp_path, download=False) == {"skipped": 1}
    assert session.calls == []
    assert manifest["files"][0]["sha256"] is None


# =============================================================================
# End-to-end (fake network)
# =============================================================================


E2E_SLUGS = ["artykul-93", "maj-2023-r-", "maj-2025"]


def e2e_session(slugs=E2E_SLUGS) -> FakeSession:
    session = FakeSession({cur(1): synthetic_index(1, slugs, has_next=False)})
    for slug in slugs:
        html = fixture(f"page_{slug}.html")
        session.routes[page_url(slug)] = html
        for link in parse_monthly_page(html, page_url(slug))["links"]:
            session.routes[link["url"]] = (XLSX + link["file_id"].encode(), {})
    return session


def assert_manifest_contract(manifest: dict, site: str = SITE) -> None:
    assert set(manifest) == {"generated_at", "index_url", "pages", "files"}
    page_keys = {"page_id", "url", "title", "period", "published_at", "summary", "index_page", "source", "blocks",
                 "warnings"}
    for page in manifest["pages"]:
        assert page_keys <= set(page) <= page_keys | {"removed_from_source_at"}
        assert page["source"] in ("district", "baipp")
        block_keys = {"text", "category", "declared_count", "file_ids"} | ({"series"} if page["source"] == "baipp" else set())
        for block in page["blocks"]:
            assert set(block) == block_keys
            assert block["category"] in (None, "wz", "cp", "ws")
    file_keys = {"file_id", "source", "url", "document_path", "filename", "ext", "category", "period", "page_ids",
                 "local_path", "sha256", "size", "downloaded_at", "last_modified", "history"}
    for entry in manifest["files"]:
        extra = {"series"} if entry["source"] == "baipp" else set()
        assert file_keys | extra <= set(entry) <= file_keys | extra | {"error", "removed_from_source_at"}
        assert entry["url"].startswith(site + entry["document_path"] + "?t=")


def test_run_crawl_end_to_end_and_idempotent(tmp_path):
    out, raw = tmp_path / "manifest.json", tmp_path / "raw"
    session = e2e_session()
    manifest = run_crawl(out, raw, session=session)
    assert_manifest_contract(manifest)
    assert json.loads(out.read_text(encoding="utf-8")) == manifest
    assert "Październik" in out.read_text(encoding="utf-8")  # ensure_ascii=False
    assert [p["page_id"] for p in manifest["pages"]] == ["artykul-93", "maj-2025", "maj-2023-r-"]
    assert all(p["index_page"] == 1 and p["summary"] for p in manifest["pages"])
    summary = summarize(manifest)
    assert summary["files"] == 10 and summary["links"] == 10
    assert summary["files_missing_locally"] == []
    assert summary["declared_totals"] == {"wz": 1 + 5 + 3, "cp": 1 + 3 + 1, "ws": 4 + 1 + 1}
    assert len(list(raw.glob("*.xlsx"))) == 10
    assert {p["source"] for p in manifest["pages"]} == {"district"}  # BAiPP unreachable here: not fatal

    # second run: same pages, nothing downloaded again
    session2 = e2e_session()
    again = run_crawl(out, raw, session=session2)
    assert not [c for c in session2.calls if "/documents/" in c]
    assert [f["sha256"] for f in again["files"]] == [f["sha256"] for f in manifest["files"]]


def test_run_crawl_keeps_pages_that_disappear_or_fail(tmp_path):
    out, raw = tmp_path / "manifest.json", tmp_path / "raw"
    run_crawl(out, raw, session=e2e_session())

    # "maj-2025" vanished from the index, "maj-2023-r-" fails to load
    session = e2e_session(["artykul-93", "maj-2023-r-"])
    session.routes[page_url("maj-2023-r-")] = FakeResponse(page_url("maj-2023-r-"), 503)
    manifest = run_crawl(out, raw, session=session)
    pages = {p["page_id"]: p for p in manifest["pages"]}
    assert set(pages) == {"artykul-93", "maj-2023-r-", "maj-2025"}
    assert pages["maj-2025"]["removed_from_source_at"]
    assert any("poprzedniej wersji" in w for w in pages["maj-2023-r-"]["warnings"])
    assert len(pages["maj-2023-r-"]["blocks"]) == 3
    assert len(manifest["files"]) == 10  # files of kept pages are still listed
    assert_manifest_contract(manifest)


MAINTENANCE_PAGE = ("<html><head><title>Serwis chwilowo niedostępny</title></head><body><h1>Prace serwisowe</h1>"
                    "<p>Przepraszamy, spróbuj później.</p></body></html>")


def test_page_answered_without_its_file_list_is_taken_from_the_previous_crawl(tmp_path):
    # HTTP 200, page chrome, no article (maintenance / error page): its files must not drop out of the manifest
    out, raw = tmp_path / "manifest.json", tmp_path / "raw"
    first = run_crawl(out, raw, session=e2e_session())
    session = e2e_session()
    session.routes[page_url("maj-2025")] = MAINTENANCE_PAGE
    manifest = run_crawl(out, raw, session=session)
    pages = {p["page_id"]: p for p in manifest["pages"]}
    before = {p["page_id"]: p for p in first["pages"]}
    assert manifest["stale_pages"] == ["maj-2025"]
    assert pages["maj-2025"]["blocks"] == before["maj-2025"]["blocks"]
    assert crawl.STALE_PAGE_WARNING in pages["maj-2025"]["warnings"]
    assert [f["file_id"] for f in manifest["files"]] == [f["file_id"] for f in first["files"]]

    # a good crawl clears the mark; a page that really lists no files any more (right title) is not stale
    session = e2e_session()
    session.routes[page_url("maj-2025")] = (
        '<div class="journal-content-article" data-analytics-asset-title="maj-2025"><div class="article-description">'
        "<p>Wydane decyzje o warunkach zabudowy: brak</p></div></div>")
    manifest = run_crawl(out, raw, session=session)
    assert "stale_pages" not in manifest
    assert len(manifest["files"]) < len(first["files"])


def test_broken_new_version_keeps_the_previous_copy_and_is_retried(tmp_path):
    previous = one_file_manifest(tmp_path, url_t="1")
    download_files(FakeSession({file_url("1"): (XLSX, {})}), previous, tmp_path)
    old = dict(previous["files"][0])
    truncated = _tiny_zip("<Types v=\"2\"/>" * 50)[:-40]   # cut off mid-archive, still starts with "PK"
    manifest = one_file_manifest(tmp_path, url_t="2")
    assert download_files(FakeSession({file_url("2"): (truncated, {})}), manifest, tmp_path,
                          previous=previous) == {"failed": 1}
    entry = manifest["files"][0]
    assert "broken .xlsx archive" in entry["error"]
    assert (tmp_path / f"{entry['file_id']}.xlsx").read_bytes() == XLSX       # the readable copy stays
    assert entry["history"] == [] and not (tmp_path / "history").exists()
    for key in ("url", "sha256", "size", "downloaded_at", "last_modified"):   # described as the version we have
        assert entry[key] == old[key]
    # the next crawl still sees ?t=2 as new and downloads it once it is whole
    again = one_file_manifest(tmp_path, url_t="2")
    good = _tiny_zip("<Types v=\"2\"/>")
    assert download_files(FakeSession({file_url("2"): (good, {})}), again, tmp_path, previous=manifest) == {
        "downloaded": 1}
    assert again["files"][0]["sha256"] == hashlib.sha256(good).hexdigest()


def test_run_crawl_raises_when_index_is_unreachable(tmp_path):
    with pytest.raises(requests.HTTPError):
        run_crawl(tmp_path / "m.json", tmp_path / "raw", session=FakeSession())
    assert not (tmp_path / "m.json").exists()


def test_cli_no_download(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(crawl, "make_session", lambda **kw: e2e_session())
    code = crawl.main(["--out", str(tmp_path / "m.json"), "--raw", str(tmp_path / "raw"), "--no-download", "-q"])
    assert code == 1  # files are missing locally
    manifest = json.loads((tmp_path / "m.json").read_text(encoding="utf-8"))
    assert len(manifest["pages"]) == 3
    assert '"files_missing_locally"' in capsys.readouterr().err


# =============================================================================
# pipeline/http.py
# =============================================================================


class ScriptedAdapter(BaseAdapter):
    """Transport adapter replaying (status, headers, body) tuples or exceptions."""

    def __init__(self, script):
        super().__init__()
        self.script = list(script)
        self.sent: list[tuple[requests.PreparedRequest, dict]] = []

    def send(self, request, **kwargs):
        self.sent.append((request, kwargs))
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        status, headers, body = item
        response = requests.Response()
        response.status_code = status
        response.headers = CaseInsensitiveDict(headers)
        response._content = body
        response.url = request.url
        response.request = request
        response.encoding = requests.utils.get_encoding_from_headers(response.headers)
        return response

    def close(self):
        pass


class FakeClock:
    def __init__(self):
        self.now = 1000.0
        self.sleeps: list[float] = []

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(round(seconds, 3))
        self.now += seconds


def polite(script, **kwargs):
    clock = FakeClock()
    session = phttp.PoliteSession(sleep=clock.sleep, clock=clock, **kwargs)
    adapter = ScriptedAdapter(script)
    session.mount("https://", adapter)
    return session, adapter, clock


def test_session_defaults():
    session = phttp.make_session()
    assert session.headers["User-Agent"] == "wzSearch/0.1 (civic open-data project)"
    assert session.timeout == (10.0, 30.0)
    assert session.min_delay == 0.4 and session.attempts == 3


def test_retries_5xx_with_exponential_backoff():
    session, adapter, clock = polite([(503, {}, b""), (502, {}, b""), (200, {}, b"ok")], min_delay=0)
    assert phttp.get_bytes(session, "https://a.test/x") == b"ok"
    assert clock.sleeps == [1.0, 2.0]
    assert all(kwargs["timeout"] == (10.0, 30.0) for _, kwargs in adapter.sent)
    assert adapter.sent[0][0].headers["User-Agent"] == phttp.USER_AGENT


def test_retry_after_is_honoured_and_last_error_is_returned():
    session, _, clock = polite([(429, {"Retry-After": "7"}, b""), (500, {}, b""), (500, {}, b"x")], min_delay=0)
    with pytest.raises(requests.HTTPError):
        phttp.fetch(session, "https://a.test/x")
    assert clock.sleeps == [7.0, 2.0]


def test_connection_errors_are_retried_then_raised():
    errors = [requests.ConnectionError("down")] * 3
    session, adapter, clock = polite(errors, min_delay=0)
    with pytest.raises(requests.ConnectionError):
        session.get("https://a.test/x")
    assert len(adapter.sent) == 3 and clock.sleeps == [1.0, 2.0]


def test_404_is_not_retried():
    session, adapter, _ = polite([(404, {}, b"")], min_delay=0)
    with pytest.raises(requests.HTTPError):
        phttp.fetch(session, "https://a.test/x")
    assert len(adapter.sent) == 1


def test_minimum_delay_between_requests_to_the_same_host():
    session, _, clock = polite([(200, {}, b"")] * 4, min_delay=0.4)
    session.get("https://a.test/1")
    session.get("https://a.test/2")
    session.get("https://b.test/1")  # other host: no wait
    clock.now += 5
    session.get("https://a.test/3")  # enough time passed: no wait
    assert clock.sleeps == [0.4]


def test_get_text_assumes_utf8_without_charset():
    body = "Październik".encode()
    session, _, _ = polite([(200, {"Content-Type": "text/html"}, body)], min_delay=0)
    assert phttp.get_text(session, "https://a.test/x") == "Październik"
