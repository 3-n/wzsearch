"""Polite HTTP helper shared by the pipeline stages.

Everything that talks to a remote server (the district office's Liferay portal,
GUGiK ULDK, the city geocoder, ...) should go through :func:`make_session` so
that all stages behave the same way:

* an identifying ``User-Agent``;
* default timeouts (connect 10 s / read 30 s);
* up to 3 attempts with exponential backoff on HTTP 429/5xx and on
  connection errors / timeouts (``Retry-After`` is honoured, capped);
* a minimum gap between consecutive requests to the same host
  (default 0.4 s, measured from the end of the previous response, so the
  effective rate always stays below 1 / ``min_delay`` requests per second).

The module only depends on ``requests``.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from urllib.parse import urlsplit

import requests

__all__ = [
    "DEFAULT_TIMEOUT",
    "RETRY_STATUSES",
    "USER_AGENT",
    "PoliteSession",
    "fetch",
    "get_bytes",
    "get_text",
    "make_session",
]

log = logging.getLogger("wzsearch.http")

USER_AGENT = "wzSearch/0.1 (civic open-data project)"
DEFAULT_TIMEOUT: tuple[float, float] = (10.0, 30.0)  # (connect, read) seconds
RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})
MAX_RETRY_AFTER = 60.0  # never sleep longer than this because of a Retry-After header


class PoliteSession(requests.Session):
    """A :class:`requests.Session` with throttling, retries and default timeouts.

    Parameters
    ----------
    min_delay:
        Minimum number of seconds between the end of one request and the start
        of the next one to the same host.
    attempts:
        Total number of attempts per request (1 = no retries).
    backoff:
        Base backoff in seconds; attempt *n* (1-based) waits ``backoff * 2**(n-1)``
        before the next try, unless the server sent a ``Retry-After`` header.
    timeout:
        Default ``timeout`` passed to every request that does not set one.
    sleep, clock:
        Injected for tests (default :func:`time.sleep` / :func:`time.monotonic`).

    Retries are reported through the ``wzsearch.http`` logger (WARNING level).
    """

    def __init__(
        self,
        *,
        min_delay: float = 0.4,
        attempts: int = 3,
        backoff: float = 1.0,
        timeout: tuple[float, float] | float = DEFAULT_TIMEOUT,
        user_agent: str = USER_AGENT,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        super().__init__()
        if attempts < 1:
            raise ValueError("attempts must be >= 1")
        self.min_delay = float(min_delay)
        self.attempts = int(attempts)
        self.backoff = float(backoff)
        self.timeout = timeout
        self.headers["User-Agent"] = user_agent
        self._sleep = sleep
        self._clock = clock
        self._last_request_end: dict[str, float] = {}

    # -- throttling ---------------------------------------------------------

    def _throttle(self, host: str) -> None:
        last = self._last_request_end.get(host)
        if last is None or self.min_delay <= 0:
            return
        wait = self.min_delay - (self._clock() - last)
        if wait > 0:
            self._sleep(wait)

    def _mark_done(self, host: str) -> None:
        self._last_request_end[host] = self._clock()

    # -- retries ------------------------------------------------------------

    def _backoff_delay(self, attempt: int, response: requests.Response | None = None) -> float:
        if response is not None:
            retry_after = _parse_retry_after(response.headers.get("Retry-After"))
            if retry_after is not None:
                return min(retry_after, MAX_RETRY_AFTER)
        return self.backoff * (2 ** (attempt - 1))

    def request(self, method, url, *args, **kwargs):  # type: ignore[override]
        """Send a request with throttling, default timeout and retries."""
        kwargs.setdefault("timeout", self.timeout)
        host = urlsplit(url).netloc.lower()
        for attempt in range(1, self.attempts + 1):
            self._throttle(host)
            try:
                response = super().request(method, url, *args, **kwargs)
            except (requests.ConnectionError, requests.Timeout) as exc:
                self._mark_done(host)
                if attempt >= self.attempts:
                    raise
                delay = self._backoff_delay(attempt)
                log.warning(
                    "%s for %s (attempt %d/%d), retrying in %.1fs",
                    type(exc).__name__, url, attempt, self.attempts, delay,
                )
                self._sleep(delay)
                continue
            self._mark_done(host)
            if response.status_code in RETRY_STATUSES and attempt < self.attempts:
                delay = self._backoff_delay(attempt, response)
                log.warning(
                    "HTTP %d for %s (attempt %d/%d), retrying in %.1fs",
                    response.status_code, url, attempt, self.attempts, delay,
                )
                response.close()
                self._sleep(delay)
                continue
            return response
        raise AssertionError("unreachable")  # pragma: no cover


def make_session(
    *,
    min_delay: float = 0.4,
    attempts: int = 3,
    backoff: float = 1.0,
    timeout: tuple[float, float] | float = DEFAULT_TIMEOUT,
) -> PoliteSession:
    """Return a ready-to-use :class:`PoliteSession` (see its docstring)."""
    return PoliteSession(min_delay=min_delay, attempts=attempts, backoff=backoff, timeout=timeout)


def fetch(session: requests.Session, url: str, **kwargs) -> requests.Response:
    """GET ``url`` and raise :class:`requests.HTTPError` on a non-2xx status."""
    response = session.get(url, **kwargs)
    response.raise_for_status()
    return response


def get_text(session: requests.Session, url: str, **kwargs) -> str:
    """GET ``url`` and return the body as text.

    If the server does not declare a charset, UTF-8 is assumed (``requests``
    would otherwise fall back to ISO-8859-1 for ``text/*``, which mangles
    Polish diacritics).
    """
    response = fetch(session, url, **kwargs)
    content_type = response.headers.get("Content-Type", "")
    if "charset=" not in content_type.lower():
        response.encoding = "utf-8"
    return response.text


def get_bytes(session: requests.Session, url: str, **kwargs) -> bytes:
    """GET ``url`` and return the raw body."""
    return fetch(session, url, **kwargs).content


# -- helpers ------------------------------------------------------------------


def _parse_retry_after(value: str | None) -> float | None:
    """Parse a ``Retry-After`` header (delta-seconds or HTTP date)."""
    if not value:
        return None
    value = value.strip()
    try:
        return max(0.0, float(value))
    except ValueError:
        pass
    try:
        when = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    if when is None:
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=UTC)
    return max(0.0, (when - datetime.now(UTC)).total_seconds())
