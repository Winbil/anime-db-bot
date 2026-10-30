from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from core.http_client import http_request
from core.image_search import (
    ImageSearchAvailability,
    ImageSearchInput,
    ImageSearchMatch,
    ImageSearchQuotaExhausted,
)
from core.settings import SourceSettings, get_settings
from core.source_errors import SourceInvalidResponse, error_for_response
from services.runtime.rate_limits import wait_for_upstream
from services.search.image_quota import SQLiteImageSearchQuotaStore


def _clean(value: object) -> str:
    return " ".join(str(value or "").split()).strip()


def _number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _episode(value: object) -> str | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    text = _clean(value)
    return text or None


def _match_from_payload(
    provider_key: str, provider_name: str, raw: object
) -> ImageSearchMatch | None:
    if not isinstance(raw, dict):
        return None
    anilist_raw = raw.get("anilist")
    titles: dict[str, str] = {}
    aliases: tuple[str, ...] = ()
    mal_id: str | None = None
    if isinstance(anilist_raw, dict):
        anilist_id = _clean(anilist_raw.get("id"))
        raw_titles = anilist_raw.get("title")
        if isinstance(raw_titles, dict):
            for key in ("romaji", "english", "native"):
                value = _clean(raw_titles.get(key))
                if value:
                    titles[key] = value
        aliases = tuple(
            value
            for item in (anilist_raw.get("synonyms") or [])
            if (value := _clean(item))
        )
        mal_id = _clean(anilist_raw.get("idMal")) or None
    else:
        anilist_id = _clean(anilist_raw)
    if not anilist_id.isdigit():
        return None
    similarity = _number(raw.get("similarity"))
    if similarity is None:
        return None
    return ImageSearchMatch(
        provider_key=provider_key,
        provider_name=provider_name,
        anilist_id=anilist_id,
        similarity=max(0.0, min(1.0, similarity)),
        episode=_episode(raw.get("episode")),
        from_seconds=_number(raw.get("from")),
        to_seconds=_number(raw.get("to")),
        preview_image=_clean(raw.get("image")) or None,
        preview_video=_clean(raw.get("video")) or None,
        titles=titles,
        aliases=aliases,
        mal_id=mal_id,
    )


def _parse_results(
    provider_key: str, provider_name: str, payload: object
) -> list[ImageSearchMatch]:
    if not isinstance(payload, dict):
        raise SourceInvalidResponse(
            f"{provider_name} returned a non-object image-search response",
            source=provider_key,
            operation="image_search",
        )
    error = _clean(payload.get("error"))
    if error:
        raise SourceInvalidResponse(
            f"{provider_name} image search failed: {error}",
            source=provider_key,
            operation="image_search",
        )
    raw_results = payload.get("result")
    if not isinstance(raw_results, list):
        raise SourceInvalidResponse(
            f"{provider_name} response has no result list",
            source=provider_key,
            operation="image_search",
        )
    matches = [
        match
        for item in raw_results
        if (match := _match_from_payload(provider_key, provider_name, item)) is not None
    ]
    matches.sort(key=lambda item: item.similarity, reverse=True)
    return matches


class TraceMoeImageSearchProvider:
    key = "trace_moe"
    name = "trace.moe"

    def __init__(self, settings: SourceSettings | None = None) -> None:
        self.settings = settings or get_settings().sources
        self._lock = asyncio.Lock()
        self._availability: ImageSearchAvailability | None = None
        self._availability_at = 0.0

    def _headers(self) -> dict[str, str]:
        return (
            {"x-trace-key": self.settings.trace_moe_api_key}
            if self.settings.trace_moe_api_key
            else {}
        )

    async def availability(self, *, force: bool = False) -> ImageSearchAvailability:
        now = time.monotonic()
        if (
            not force
            and self._availability is not None
            and now - self._availability_at
            < self.settings.trace_moe_quota_cache_ttl_seconds
        ):
            return self._availability
        try:
            await wait_for_upstream(self.key, "quota")
            response = await http_request(
                self.key,
                "GET",
                f"{self.settings.trace_moe_api_url}/me",
                operation="quota",
                timeout=self.settings.trace_moe_request_timeout_seconds,
                headers=self._headers(),
                allowed_statuses={402, 429},
            )
            if response.status_code in {402, 429}:
                availability = ImageSearchAvailability(
                    self.key, self.name, False, 0, None
                )
            else:
                payload = response.json()
                quota = (
                    int(payload.get("quota") or 0) if isinstance(payload, dict) else 0
                )
                used = (
                    int(payload.get("quotaUsed") or 0)
                    if isinstance(payload, dict)
                    else 0
                )
                remaining = max(0, quota - used) if quota > 0 else None
                availability = ImageSearchAvailability(
                    self.key,
                    self.name,
                    remaining is None or remaining > 0,
                    remaining,
                    quota or None,
                )
            self._availability = availability
            self._availability_at = now
            return availability
        except Exception:
            logging.warning(
                "Could not refresh trace.moe quota; keeping source selectable",
                exc_info=True,
            )
            return self._availability or ImageSearchAvailability(
                self.key, self.name, True
            )

    async def search(self, image: ImageSearchInput) -> list[ImageSearchMatch]:
        async with self._lock:
            # The Telegram chooser refreshes /me immediately before the user can
            # start a search. Reuse that short-lived quota snapshot here instead
            # of spending a second control-plane request for every screenshot.
            availability = await self.availability()
            if not availability.available:
                raise ImageSearchQuotaExhausted("trace.moe search quota is exhausted")
            await wait_for_upstream(self.key, "image_search")
            params: dict[str, str] = {"anilistInfo": ""}
            if self.settings.trace_moe_cut_borders:
                params["cutBorders"] = ""
            headers = self._headers()
            if image.url:
                params["url"] = image.url
                response = await http_request(
                    self.key,
                    "GET",
                    f"{self.settings.trace_moe_api_url}/search",
                    operation="image_search",
                    timeout=self.settings.trace_moe_request_timeout_seconds,
                    params=params,
                    headers=headers,
                    allowed_statuses={402, 429},
                )
            else:
                headers = {
                    **headers,
                    "Content-Type": image.content_type or "application/octet-stream",
                }
                response = await http_request(
                    self.key,
                    "POST",
                    f"{self.settings.trace_moe_api_url}/search",
                    operation="image_search",
                    timeout=self.settings.trace_moe_request_timeout_seconds,
                    params=params,
                    headers=headers,
                    content=image.content or b"",
                    allowed_statuses={402, 429},
                )
            if response.status_code in {402, 429}:
                self._availability = ImageSearchAvailability(
                    self.key, self.name, False, 0, availability.limit
                )
                self._availability_at = time.monotonic()
                raise ImageSearchQuotaExhausted("trace.moe search quota is exhausted")
            matches = _parse_results(self.key, self.name, response.json())
            if self._availability and self._availability.remaining is not None:
                remaining = max(0, self._availability.remaining - 1)
                self._availability = ImageSearchAvailability(
                    self.key,
                    self.name,
                    remaining > 0,
                    remaining,
                    self._availability.limit,
                )
                self._availability_at = time.monotonic()
            return matches


class WhatAnimeIsThisImageSearchProvider:
    key = "whatanimeisthis"
    name = "What Anime Is This"

    def __init__(
        self,
        quota_store: SQLiteImageSearchQuotaStore,
        settings: SourceSettings | None = None,
    ) -> None:
        self.settings = settings or get_settings().sources
        self.quota_store = quota_store
        self._lock = asyncio.Lock()

    @property
    def daily_limit(self) -> int:
        return (
            self.settings.whatanimeisthis_api_daily_limit
            if self.settings.whatanimeisthis_api_key
            else self.settings.whatanimeisthis_guest_daily_limit
        )

    async def availability(self, *, force: bool = False) -> ImageSearchAvailability:
        del force
        state = self.quota_store.state(self.key)
        limit = self.daily_limit
        if limit <= 0:
            return ImageSearchAvailability(
                self.key,
                self.name,
                not state.exhausted,
                None,
                None,
            )
        remaining = max(0, limit - state.used)
        return ImageSearchAvailability(
            self.key,
            self.name,
            not state.exhausted and remaining > 0,
            remaining,
            limit,
        )

    def _headers(self) -> dict[str, str]:
        return (
            {"Authorization": f"Bearer {self.settings.whatanimeisthis_api_key}"}
            if self.settings.whatanimeisthis_api_key
            else {}
        )

    async def search(self, image: ImageSearchInput) -> list[ImageSearchMatch]:
        async with self._lock:
            availability = await self.availability()
            if not availability.available:
                raise ImageSearchQuotaExhausted(
                    "What Anime Is This daily quota is exhausted"
                )
            await wait_for_upstream(self.key, "image_search")
            kwargs: dict[str, Any] = {"headers": self._headers()}
            if image.url:
                kwargs["data"] = {"url": image.url}
            else:
                kwargs["files"] = {
                    "image": (
                        image.filename or "image",
                        image.content or b"",
                        image.content_type or "application/octet-stream",
                    )
                }
            response = await http_request(
                self.key,
                "POST",
                f"{self.settings.whatanimeisthis_api_url}/api/anime/search",
                operation="image_search",
                timeout=self.settings.whatanimeisthis_request_timeout_seconds,
                allowed_statuses={400, 402, 403, 429},
                **kwargs,
            )
            try:
                payload = response.json()
            except ValueError:
                payload = {}
            error = _clean(payload.get("error")) if isinstance(payload, dict) else ""
            error_folded = error.casefold()
            quota_exhausted = response.status_code == 402 or any(
                marker in error_folded
                for marker in ("daily", "quota", "credit", "free searches")
            )
            if quota_exhausted:
                self.quota_store.mark_exhausted(self.key)
                raise ImageSearchQuotaExhausted(
                    error or "What Anime Is This daily quota is exhausted"
                )
            if response.is_error:
                raise error_for_response(
                    response, source=self.key, operation="image_search"
                )
            if error:
                raise SourceInvalidResponse(
                    f"What Anime Is This image search failed: {error}",
                    source=self.key,
                    operation="image_search",
                )
            matches = _parse_results(self.key, self.name, payload)
            self.quota_store.consume(self.key)
            return matches
