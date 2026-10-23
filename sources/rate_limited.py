from __future__ import annotations

from typing import Any

from core.identity import AnimeIdentity
from core.models import AnimeRecord, PersonCredit
from services.rate_limits import wait_for_upstream


class RateLimitedSourceProxy:
    """Apply source-global upstream quotas before metadata operations."""

    def __init__(self, source: Any, source_key: str) -> None:
        self._source = source
        self.source_key = source_key
        self.name = source.name

    async def get_details(self, identity: AnimeIdentity) -> AnimeRecord | None:
        await wait_for_upstream(self.source_key, "metadata")
        return await self._source.get_details(identity)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._source, name)


class PeopleRateLimitedSourceProxy(RateLimitedSourceProxy):
    """Rate-limit expensive lazy people operations independently."""

    async def load_staff(self, identity: AnimeIdentity) -> list[PersonCredit]:
        loader = getattr(self._source, "load_staff", None)
        if not callable(loader):
            return []
        await wait_for_upstream(self.source_key, "people")
        return await loader(identity)

    async def load_voices(self, identity: AnimeIdentity) -> list[PersonCredit]:
        loader = getattr(self._source, "load_voices", None)
        if not callable(loader):
            return []
        await wait_for_upstream(self.source_key, "people")
        return await loader(identity)

    async def load_staff_batch(
        self,
        identity: AnimeIdentity,
        *,
        cursor: str | None = None,
        portrait_budget: int = 50,
    ) -> Any:
        loader = getattr(self._source, "load_staff_batch", None)
        if not callable(loader):
            return None
        await wait_for_upstream(self.source_key, "people")
        return await loader(
            identity,
            cursor=cursor,
            portrait_budget=portrait_budget,
        )

    async def load_voices_batch(
        self,
        identity: AnimeIdentity,
        *,
        cursor: str | None = None,
        portrait_budget: int = 50,
    ) -> Any:
        loader = getattr(self._source, "load_voices_batch", None)
        if not callable(loader):
            return None
        await wait_for_upstream(self.source_key, "people")
        return await loader(
            identity,
            cursor=cursor,
            portrait_budget=portrait_budget,
        )


def rate_limited_source(source: Any, source_key: str) -> RateLimitedSourceProxy:
    has_people = any(
        callable(getattr(source, name, None))
        for name in (
            "load_staff",
            "load_voices",
            "load_staff_batch",
            "load_voices_batch",
        )
    )
    proxy_type = PeopleRateLimitedSourceProxy if has_people else RateLimitedSourceProxy
    return proxy_type(source, source_key)
