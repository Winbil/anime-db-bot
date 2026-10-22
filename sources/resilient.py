from __future__ import annotations

import asyncio
import logging
import re
from typing import Any, Awaitable, Callable, TypeVar

import httpx

from core.identity import AnimeIdentity
from core.models import AnimeRecord, PersonCredit

T = TypeVar("T")

_RETRY_ATTEMPTS = 3
_RETRY_BASE_DELAY = 0.8
_TRANSIENT_STATUS_RE = re.compile(r"(?:HTTP\s+)?(429|5\d\d)\b", re.IGNORECASE)
_RETRY_AFTER_RE = re.compile(r"retry after\s+([0-9]+(?:\.[0-9]+)?)s?", re.IGNORECASE)


def _is_transient(exc: BaseException) -> bool:
    if isinstance(exc, (httpx.TimeoutException, httpx.TransportError)):
        return True
    return bool(_TRANSIENT_STATUS_RE.search(str(exc)))


def _retry_delay(exc: BaseException, attempt: int) -> float:
    match = _RETRY_AFTER_RE.search(str(exc))
    if match:
        try:
            return max(float(match.group(1)), _RETRY_BASE_DELAY)
        except ValueError:
            pass
    return _RETRY_BASE_DELAY * attempt


async def _retry_call(
    source_name: str,
    operation: str,
    call: Callable[[], Awaitable[T]],
) -> T:
    last_error: BaseException | None = None
    for attempt in range(1, _RETRY_ATTEMPTS + 1):
        try:
            return await call()
        except Exception as exc:
            last_error = exc
            transient = _is_transient(exc)
            if not transient or attempt >= _RETRY_ATTEMPTS:
                logging.warning(
                    "%s %s failed after %d attempt(s): %s: %s",
                    source_name,
                    operation,
                    attempt,
                    type(exc).__name__,
                    exc,
                )
                raise

            delay = _retry_delay(exc, attempt)
            logging.warning(
                "%s %s transient failure (%s: %s); retry %d/%d in %.1fs",
                source_name,
                operation,
                type(exc).__name__,
                exc,
                attempt + 1,
                _RETRY_ATTEMPTS,
                delay,
            )
            await asyncio.sleep(delay)

    assert last_error is not None
    raise last_error


class RetryingSourceProxy:
    """Retry transient metadata failures without changing source capabilities."""

    def __init__(self, source: Any) -> None:
        self._source = source
        self.name = source.name

    async def get_details(self, identity: AnimeIdentity) -> AnimeRecord | None:
        return await _retry_call(
            self.name,
            "metadata",
            lambda: self._source.get_details(identity),
        )

    def __getattr__(self, name: str) -> Any:
        return getattr(self._source, name)


class PeopleRetryingSourceProxy(RetryingSourceProxy):
    """Retry optional lazy people operations exposed by the wrapped source."""

    async def load_staff(self, identity: AnimeIdentity) -> list[PersonCredit]:
        loader = getattr(self._source, "load_staff", None)
        if not callable(loader):
            return []
        return await _retry_call(
            self.name,
            "staff",
            lambda: loader(identity),
        )

    async def load_voices(self, identity: AnimeIdentity) -> list[PersonCredit]:
        loader = getattr(self._source, "load_voices", None)
        if not callable(loader):
            return []
        return await _retry_call(
            self.name,
            "voices",
            lambda: loader(identity),
        )


def resilient_source(source: Any) -> RetryingSourceProxy:
    if callable(getattr(source, "load_staff", None)) or callable(
        getattr(source, "load_voices", None)
    ):
        return PeopleRetryingSourceProxy(source)
    return RetryingSourceProxy(source)
