from __future__ import annotations

import asyncio
import logging
import re
from typing import Any, Awaitable, Callable, TypeVar

import httpx

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
    """Retry transient source failures without reimplementing source logic."""

    def __init__(self, source: Any) -> None:
        self._source = source
        self.name = source.name

    async def get_details(
        self,
        mal_id: str,
        known_ids: dict[str, str],
    ) -> AnimeRecord | None:
        return await _retry_call(
            self.name,
            "metadata",
            lambda: self._source.get_details(mal_id, known_ids),
        )

    async def load_staff(
        self,
        mal_id: str,
        known_ids: dict[str, str],
    ) -> list[PersonCredit]:
        loader = getattr(self._source, "load_staff", None)
        if not callable(loader):
            return []
        return await _retry_call(
            self.name,
            "staff",
            lambda: loader(mal_id, known_ids),
        )

    async def load_voices(
        self,
        mal_id: str,
        known_ids: dict[str, str],
    ) -> list[PersonCredit]:
        loader = getattr(self._source, "load_voices", None)
        if not callable(loader):
            return []
        return await _retry_call(
            self.name,
            "voices",
            lambda: loader(mal_id, known_ids),
        )

    def __getattr__(self, name: str) -> Any:
        return getattr(self._source, name)


class AniListSourceProxy(RetryingSourceProxy):
    async def _ensure_media_id(
        self,
        mal_id: str,
        known_ids: dict[str, str],
    ) -> str:
        media_id = str(known_ids.get("anilist") or "").strip()
        if media_id.isdigit():
            return media_id

        record = await self.get_details(mal_id, known_ids)
        if record is None:
            return ""
        media_id = str(record.external_ids.get("anilist") or record.source_id).strip()
        if media_id.isdigit():
            known_ids["anilist"] = media_id
        return media_id

    async def load_staff(
        self,
        mal_id: str,
        known_ids: dict[str, str],
    ) -> list[PersonCredit]:
        media_id = await self._ensure_media_id(mal_id, known_ids)
        if not media_id:
            return []
        return await super().load_staff(mal_id, known_ids)

    async def load_voices(
        self,
        mal_id: str,
        known_ids: dict[str, str],
    ) -> list[PersonCredit]:
        media_id = await self._ensure_media_id(mal_id, known_ids)
        if not media_id:
            return []
        return await super().load_voices(mal_id, known_ids)


def resilient_source(source: Any) -> RetryingSourceProxy:
    if source.name == "AniList":
        return AniListSourceProxy(source)
    return RetryingSourceProxy(source)
