from __future__ import annotations

from typing import Any

from core.identity import AnimeIdentity
from core.people_loading import PeopleManifest, without_portraits
from core.models import (
    AnimeRecord,
    CharacterRecord,
    DescriptionDetails,
    PersonCredit,
    PopularityStats,
)
from services.runtime.rate_limits import wait_for_upstream


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

    async def load_characters(self, identity: AnimeIdentity) -> list[CharacterRecord]:
        loader = getattr(self._source, "load_characters", None)
        if not callable(loader):
            return []
        await wait_for_upstream(self.source_key, "people")
        return await loader(identity)

    async def load_screenshots(self, identity: AnimeIdentity) -> list[str]:
        loader = getattr(self._source, "load_screenshots", None)
        if not callable(loader):
            return []
        await wait_for_upstream(self.source_key, "metadata")
        return await loader(identity)

    async def load_popularity(self, identity: AnimeIdentity) -> PopularityStats:
        loader = getattr(self._source, "load_popularity", None)
        if not callable(loader):
            return PopularityStats()
        await wait_for_upstream(self.source_key, "metadata")
        return await loader(identity)

    async def load_description(self, identity: AnimeIdentity) -> DescriptionDetails:
        loader = getattr(self._source, "load_description", None)
        if not callable(loader):
            return DescriptionDetails()
        await wait_for_upstream(self.source_key, "metadata")
        return await loader(identity)

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

    async def load_staff_manifest(self, identity: AnimeIdentity) -> PeopleManifest:
        loader = getattr(self._source, "load_staff_manifest", None)
        if callable(loader):
            await wait_for_upstream(self.source_key, "people")
            return await loader(identity)
        people = await self.load_staff(identity)
        return PeopleManifest(
            people=without_portraits(people),
            portrait_pool=people,
        )

    async def load_voices_manifest(self, identity: AnimeIdentity) -> PeopleManifest:
        loader = getattr(self._source, "load_voices_manifest", None)
        if callable(loader):
            await wait_for_upstream(self.source_key, "people")
            return await loader(identity)
        people = await self.load_voices(identity)
        return PeopleManifest(
            people=without_portraits(people),
            portrait_pool=people,
        )

    async def load_staff_portraits(
        self, identity: AnimeIdentity, people: list[PersonCredit]
    ) -> list[PersonCredit]:
        loader = getattr(self._source, "load_staff_portraits", None)
        if not callable(loader):
            return []
        await wait_for_upstream(self.source_key, "people")
        return await loader(identity, people)

    async def load_voices_portraits(
        self, identity: AnimeIdentity, people: list[PersonCredit]
    ) -> list[PersonCredit]:
        loader = getattr(self._source, "load_voices_portraits", None)
        if not callable(loader):
            return []
        await wait_for_upstream(self.source_key, "people")
        return await loader(identity, people)

    async def load_staff_batch(
        self,
        identity: AnimeIdentity,
        *,
        cursor: str | None = None,
        portrait_limit: int = 50,
    ) -> Any:
        loader = getattr(self._source, "load_staff_batch", None)
        if not callable(loader):
            return None
        await wait_for_upstream(self.source_key, "people")
        return await loader(
            identity,
            cursor=cursor,
            portrait_limit=portrait_limit,
        )

    async def load_voices_batch(
        self,
        identity: AnimeIdentity,
        *,
        cursor: str | None = None,
        portrait_limit: int = 50,
    ) -> Any:
        loader = getattr(self._source, "load_voices_batch", None)
        if not callable(loader):
            return None
        await wait_for_upstream(self.source_key, "people")
        return await loader(
            identity,
            cursor=cursor,
            portrait_limit=portrait_limit,
        )


def rate_limited_source(source: Any, source_key: str) -> RateLimitedSourceProxy:
    has_people = any(
        callable(getattr(source, name, None))
        for name in (
            "load_characters",
            "load_staff",
            "load_voices",
            "load_staff_batch",
            "load_voices_batch",
            "load_screenshots",
            "load_popularity",
            "load_description",
        )
    )
    proxy_type = PeopleRateLimitedSourceProxy if has_people else RateLimitedSourceProxy
    return proxy_type(source, source_key)
