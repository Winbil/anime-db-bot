from __future__ import annotations

import asyncio
import logging
import re
import time
from typing import Any, Awaitable, Callable, TypeVar

import httpx

from core.identity import AnimeIdentity
from core.models import (
    AnimeRecord,
    CharacterRecord,
    DescriptionDetails,
    EpisodePage,
    EpisodeRecord,
    PersonCredit,
    PopularityStats,
    SearchPage,
    TrailerRecord,
)
from core.people_loading import PeopleBatch, PeopleManifest, without_portraits
from core.source_errors import SourceError, SourceUnavailable, normalize_source_error
from services.runtime.source_health import SourceHealthRegistry

T = TypeVar("T")

_RETRY_ATTEMPTS = 3
_RETRY_BASE_DELAY = 0.8
_TRANSIENT_STATUS_RE = re.compile(r"(?:HTTP\s+)?(429|5\d\d)\b", re.IGNORECASE)
_RETRY_AFTER_RE = re.compile(r"retry after\s+([0-9]+(?:\.[0-9]+)?)s?", re.IGNORECASE)


def _is_transient(exc: BaseException) -> bool:
    if isinstance(exc, SourceError):
        return exc.transient
    if isinstance(exc, (httpx.TimeoutException, httpx.TransportError)):
        return True
    return bool(_TRANSIENT_STATUS_RE.search(str(exc)))


def _retry_delay(exc: BaseException, attempt: int) -> float:
    if isinstance(exc, SourceError) and exc.retry_after is not None:
        return max(exc.retry_after, _RETRY_BASE_DELAY)
    match = _RETRY_AFTER_RE.search(str(exc))
    if match:
        try:
            return max(float(match.group(1)), _RETRY_BASE_DELAY)
        except ValueError:
            pass
    return _RETRY_BASE_DELAY * attempt


def _typed_error(exc: Exception, source_name: str, operation: str) -> SourceError:
    error = normalize_source_error(exc, source=source_name, operation=operation)
    if not error.transient and _is_transient(exc):
        return SourceUnavailable(
            str(error),
            source=source_name,
            operation=operation,
            transient=True,
            retry_after=_retry_delay(exc, 1),
        )
    return error


async def _retry_call(
    source_name: str,
    operation: str,
    call: Callable[[], Awaitable[T]],
    *,
    health: SourceHealthRegistry | None = None,
    health_key: str | None = None,
) -> T:
    key = health_key or source_name
    is_probe = health.before_call(key, operation) if health is not None else False
    attempts = 1 if is_probe else _RETRY_ATTEMPTS

    last_error: BaseException | None = None
    started = time.monotonic()
    for attempt in range(1, attempts + 1):
        try:
            result = await call()
            if health is not None:
                health.record_success(key)
            logging.debug(
                "Source call completed",
                extra={
                    "event": "source_call",
                    "source": key,
                    "operation": operation,
                    "outcome": "success",
                    "attempt": attempt,
                    "max_attempts": attempts,
                    "duration_ms": round((time.monotonic() - started) * 1000, 3),
                },
            )
            return result
        except asyncio.CancelledError:
            if health is not None and is_probe:
                health.release_probe(key)
            raise
        except Exception as exc:
            last_error = exc
            transient = _is_transient(exc)
            if not transient or attempt >= attempts:
                error = _typed_error(exc, source_name, operation)
                if health is not None:
                    health.record_failure(key, error)
                logging.warning(
                    "Source call failed after retries",
                    extra={
                        "event": "source_call",
                        "source": key,
                        "operation": operation,
                        "outcome": "error",
                        "attempt": attempt,
                        "max_attempts": attempts,
                        "error_type": type(error).__name__,
                        "duration_ms": round((time.monotonic() - started) * 1000, 3),
                    },
                )
                if error is exc:
                    raise
                raise error from exc

            delay = _retry_delay(exc, attempt)
            logging.warning(
                "Transient source failure; retry scheduled",
                extra={
                    "event": "source_retry",
                    "source": key,
                    "operation": operation,
                    "outcome": "retry",
                    "attempt": attempt + 1,
                    "max_attempts": attempts,
                    "retry_after": round(delay, 3),
                    "error_type": type(exc).__name__,
                },
            )
            await asyncio.sleep(delay)

    assert last_error is not None
    raise last_error


class RetryingSourceProxy:
    """Retry transient failures and maintain source-level health state."""

    def __init__(self, source: Any, health: SourceHealthRegistry | None = None) -> None:
        self._source = source
        self._health = health
        self.name = source.name
        self.source_key = getattr(source, "source_key", "")

    @property
    def _health_key(self) -> str:
        return str(self.source_key or self.name).strip().casefold()

    async def get_details(self, identity: AnimeIdentity) -> AnimeRecord | None:
        return await _retry_call(
            self.name,
            "metadata",
            lambda: self._source.get_details(identity),
            health=self._health,
            health_key=self._health_key,
        )

    def __getattr__(self, name: str) -> Any:
        return getattr(self._source, name)


class PeopleRetryingSourceProxy(RetryingSourceProxy):
    """Retry optional lazy people operations exposed by the wrapped source."""

    async def _people_call(self, operation: str, call: Callable[[], Awaitable[T]]) -> T:
        return await _retry_call(
            self.name,
            operation,
            call,
            health=self._health,
            health_key=self._health_key,
        )

    async def load_characters(self, identity: AnimeIdentity) -> list[CharacterRecord]:
        loader = getattr(self._source, "load_characters", None)
        if not callable(loader):
            return []
        return await self._people_call("characters", lambda: loader(identity))

    async def load_screenshots(self, identity: AnimeIdentity) -> list[str]:
        loader = getattr(self._source, "load_screenshots", None)
        if not callable(loader):
            return []
        return await self._people_call("screenshots", lambda: loader(identity))

    async def load_popularity(self, identity: AnimeIdentity) -> PopularityStats:
        loader = getattr(self._source, "load_popularity", None)
        if not callable(loader):
            return PopularityStats()
        return await self._people_call("popularity", lambda: loader(identity))

    async def load_description(self, identity: AnimeIdentity) -> DescriptionDetails:
        loader = getattr(self._source, "load_description", None)
        if not callable(loader):
            return DescriptionDetails()
        return await self._people_call("description", lambda: loader(identity))

    async def load_staff(self, identity: AnimeIdentity) -> list[PersonCredit]:
        loader = getattr(self._source, "load_staff", None)
        if not callable(loader):
            return []
        return await self._people_call("staff", lambda: loader(identity))

    async def load_voices(self, identity: AnimeIdentity) -> list[PersonCredit]:
        loader = getattr(self._source, "load_voices", None)
        if not callable(loader):
            return []
        return await self._people_call("voices", lambda: loader(identity))

    async def load_staff_manifest(self, identity: AnimeIdentity) -> PeopleManifest:
        loader = getattr(self._source, "load_staff_manifest", None)
        if not callable(loader):
            people = await self.load_staff(identity)
            return PeopleManifest(
                people=without_portraits(people), portrait_pool=people
            )
        return await self._people_call("staff manifest", lambda: loader(identity))

    async def load_voices_manifest(self, identity: AnimeIdentity) -> PeopleManifest:
        loader = getattr(self._source, "load_voices_manifest", None)
        if not callable(loader):
            people = await self.load_voices(identity)
            return PeopleManifest(
                people=without_portraits(people), portrait_pool=people
            )
        return await self._people_call("voices manifest", lambda: loader(identity))

    async def load_staff_portraits(
        self, identity: AnimeIdentity, people: list[PersonCredit]
    ) -> list[PersonCredit]:
        loader = getattr(self._source, "load_staff_portraits", None)
        if not callable(loader):
            return []
        return await self._people_call(
            "staff portraits", lambda: loader(identity, people)
        )

    async def load_voices_portraits(
        self, identity: AnimeIdentity, people: list[PersonCredit]
    ) -> list[PersonCredit]:
        loader = getattr(self._source, "load_voices_portraits", None)
        if not callable(loader):
            return []
        return await self._people_call(
            "voices portraits", lambda: loader(identity, people)
        )

    async def load_staff_batch(
        self,
        identity: AnimeIdentity,
        *,
        cursor: str | None = None,
        portrait_limit: int = 50,
    ) -> PeopleBatch:
        loader = getattr(self._source, "load_staff_batch", None)
        if not callable(loader):
            people = await self.load_staff(identity)
            return PeopleBatch(people=people, complete=True, total_count=len(people))
        return await self._people_call(
            "staff batch",
            lambda: loader(identity, cursor=cursor, portrait_limit=portrait_limit),
        )

    async def load_voices_batch(
        self,
        identity: AnimeIdentity,
        *,
        cursor: str | None = None,
        portrait_limit: int = 50,
    ) -> PeopleBatch:
        loader = getattr(self._source, "load_voices_batch", None)
        if not callable(loader):
            people = await self.load_voices(identity)
            return PeopleBatch(people=people, complete=True, total_count=len(people))
        return await self._people_call(
            "voices batch",
            lambda: loader(identity, cursor=cursor, portrait_limit=portrait_limit),
        )


class RetryingSearchProviderProxy:
    """Apply the shared retry/circuit policy to text-search providers."""

    def __init__(
        self,
        provider: Any,
        health: SourceHealthRegistry | None = None,
        *,
        health_key: str | None = None,
    ) -> None:
        self._provider = provider
        self._health = health
        self.name = provider.name
        self.source_key = health_key or getattr(provider, "source_key", "")

    @property
    def _health_key(self) -> str:
        return str(self.source_key or self.name).strip().casefold()

    async def search(
        self,
        query: str,
        *,
        page: int,
        limit: int,
    ) -> SearchPage:
        return await _retry_call(
            self.name,
            "search",
            lambda: self._provider.search(query, page=page, limit=limit),
            health=self._health,
            health_key=self._health_key,
        )

    def __getattr__(self, name: str) -> Any:
        return getattr(self._provider, name)


class RetryingTrailerSourceProxy:
    """Apply the shared retry/circuit policy to lazy trailer backends."""

    def __init__(self, source: Any, health: SourceHealthRegistry | None = None) -> None:
        self._source = source
        self._health = health
        self.name = source.name
        self.display_name = source.display_name
        self.source_key = source.source_key
        self.backend_key = source.backend_key

    @property
    def _health_key(self) -> str:
        return str(self.backend_key or self.source_key or self.name).strip().casefold()

    async def load_trailers(self, identity: AnimeIdentity) -> list[TrailerRecord]:
        return await _retry_call(
            self.name,
            "trailers",
            lambda: self._source.load_trailers(identity),
            health=self._health,
            health_key=self._health_key,
        )

    def __getattr__(self, name: str) -> Any:
        return getattr(self._source, name)


class RetryingEpisodeSourceProxy:
    """Apply the shared retry/circuit policy to lazy episode backends."""

    def __init__(self, source: Any, health: SourceHealthRegistry | None = None) -> None:
        self._source = source
        self._health = health
        self.name = source.name
        self.display_name = source.display_name
        self.source_key = source.source_key
        self.backend_key = source.backend_key

    @property
    def _health_key(self) -> str:
        return str(self.backend_key or self.source_key or self.name).strip().casefold()

    async def load_episode_page(
        self,
        identity: AnimeIdentity,
        *,
        page: int = 1,
    ) -> EpisodePage:
        return await _retry_call(
            self.name,
            "episodes",
            lambda: self._source.load_episode_page(identity, page=page),
            health=self._health,
            health_key=self._health_key,
        )

    async def load_episode(
        self,
        identity: AnimeIdentity,
        episode_number: int,
    ) -> EpisodeRecord | None:
        return await _retry_call(
            self.name,
            "episode",
            lambda: self._source.load_episode(identity, episode_number),
            health=self._health,
            health_key=self._health_key,
        )

    def __getattr__(self, name: str) -> Any:
        return getattr(self._source, name)


def resilient_source(
    source: Any,
    health: SourceHealthRegistry | None = None,
) -> RetryingSourceProxy:
    if (
        callable(getattr(source, "load_characters", None))
        or callable(getattr(source, "load_staff", None))
        or callable(getattr(source, "load_voices", None))
        or callable(getattr(source, "load_screenshots", None))
        or callable(getattr(source, "load_popularity", None))
        or callable(getattr(source, "load_description", None))
    ):
        return PeopleRetryingSourceProxy(source, health)
    return RetryingSourceProxy(source, health)


def resilient_search_provider(
    provider: Any,
    health: SourceHealthRegistry | None = None,
    *,
    health_key: str | None = None,
) -> RetryingSearchProviderProxy:
    return RetryingSearchProviderProxy(provider, health, health_key=health_key)


def resilient_trailer_source(
    source: Any,
    health: SourceHealthRegistry | None = None,
) -> RetryingTrailerSourceProxy:
    return RetryingTrailerSourceProxy(source, health)


def resilient_episode_source(
    source: Any,
    health: SourceHealthRegistry | None = None,
) -> RetryingEpisodeSourceProxy:
    return RetryingEpisodeSourceProxy(source, health)
