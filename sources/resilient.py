from __future__ import annotations

import asyncio
import copy
import logging
import os
import re
import time
from typing import Any, Awaitable, Callable, TypeVar

import httpx

from core.models import AnimeRecord, PersonCredit
from sources.shikimori import _credits, _graphql

T = TypeVar("T")

_RETRY_ATTEMPTS = 3
_RETRY_BASE_DELAY = 0.8
_TRANSIENT_STATUS_RE = re.compile(r"(?:HTTP\s+)?(429|5\d\d)\b", re.IGNORECASE)
_RETRY_AFTER_RE = re.compile(r"retry after\s+([0-9]+(?:\.[0-9]+)?)s?", re.IGNORECASE)

SHIKIMORI_STAFF_QUERY = """
query AnimeStaff($ids: String!) {
  animes(ids: $ids, limit: 1) {
    id
    malId
    personRoles {
      rolesRu
      rolesEn
      person {
        id
        name
        russian
        japanese
        isSeyu
        poster {
          originalUrl
          main2xUrl
          mainUrl
          preview2xUrl
          previewUrl
        }
      }
    }
  }
}
"""

_SHIKIMORI_STAFF_CACHE: dict[str, tuple[float, list[PersonCredit]]] = {}


def _people_cache_ttl_seconds() -> int:
    raw = os.getenv("SHIKIMORI_PEOPLE_CACHE_TTL_SECONDS", "21600").strip()
    try:
        return max(0, int(raw))
    except ValueError:
        return 21600


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
    """Retry transient metadata failures while preserving the source contract."""

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
        return await _retry_call(
            self.name,
            "staff",
            lambda: self._source.load_staff(mal_id, known_ids),
        )

    async def load_voices(
        self,
        mal_id: str,
        known_ids: dict[str, str],
    ) -> list[PersonCredit]:
        media_id = await self._ensure_media_id(mal_id, known_ids)
        if not media_id:
            return []
        return await _retry_call(
            self.name,
            "voices",
            lambda: self._source.load_voices(mal_id, known_ids),
        )


async def _load_shikimori_staff(
    mal_id: str,
    known_ids: dict[str, str],
) -> list[PersonCredit]:
    mal_id = str(mal_id).strip()
    anime_id = str(known_ids.get("shikimori") or "").strip()
    if not mal_id.isdigit() or not anime_id.isdigit():
        return []

    now = time.monotonic()
    cached = _SHIKIMORI_STAFF_CACHE.get(anime_id)
    if cached is not None and cached[0] > now:
        return copy.deepcopy(cached[1])
    if cached is not None:
        _SHIKIMORI_STAFF_CACHE.pop(anime_id, None)

    data = await _graphql(SHIKIMORI_STAFF_QUERY, {"ids": anime_id})
    animes = data.get("animes") or []
    raw = animes[0] if animes else None
    if not isinstance(raw, dict):
        return []
    if str(raw.get("malId") or "") != mal_id:
        return []

    staff = _credits(raw, voices=False)
    ttl = _people_cache_ttl_seconds()
    if ttl > 0:
        _SHIKIMORI_STAFF_CACHE[anime_id] = (
            time.monotonic() + ttl,
            copy.deepcopy(staff),
        )
    return staff


class ShikimoriSourceProxy(RetryingSourceProxy):
    async def load_staff(
        self,
        mal_id: str,
        known_ids: dict[str, str],
    ) -> list[PersonCredit]:
        return await _retry_call(
            self.name,
            "staff",
            lambda: _load_shikimori_staff(mal_id, known_ids),
        )

    async def load_voices(
        self,
        mal_id: str,
        known_ids: dict[str, str],
    ) -> list[PersonCredit]:
        return await _retry_call(
            self.name,
            "voices",
            lambda: self._source.load_voices(mal_id, known_ids),
        )


def resilient_source(source: Any) -> RetryingSourceProxy:
    if source.name == "AniList":
        return AniListSourceProxy(source)
    if source.name == "Shikimori":
        return ShikimoriSourceProxy(source)
    return RetryingSourceProxy(source)
