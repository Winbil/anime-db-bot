from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, patch

import httpx

from core.identity import AnimeIdentity
from core.models import AnimeRecord, PersonCredit
from sources.resilient import (
    PeopleRetryingSourceProxy,
    RetryingSourceProxy,
    resilient_source,
)


class _FlakySource:
    name = "TestSource"

    def __init__(self) -> None:
        self.calls = 0
        self.staff_calls = 0
        self.identities: list[AnimeIdentity] = []

    async def get_details(self, identity: AnimeIdentity):
        self.calls += 1
        self.identities.append(identity.copy())
        if self.calls < 3:
            raise httpx.ConnectError("temporary network failure")
        return AnimeRecord(
            source=self.name,
            source_id="1",
            external_ids=dict(identity.external_ids),
        )

    async def load_staff(self, identity: AnimeIdentity):
        self.staff_calls += 1
        self.identities.append(identity.copy())
        if self.staff_calls < 2:
            raise httpx.ReadTimeout("temporary staff timeout")
        return [PersonCredit(name="Staff Person")]


class ResilientSourceTests(unittest.IsolatedAsyncioTestCase):
    async def test_transient_metadata_failure_is_retried_with_same_identity(self) -> None:
        source = _FlakySource()
        proxy = RetryingSourceProxy(source)
        identity = AnimeIdentity({"anilist": "999"})

        with patch("sources.resilient.asyncio.sleep", new=AsyncMock()):
            record = await proxy.get_details(identity)

        self.assertIsNotNone(record)
        self.assertEqual(source.calls, 3)
        self.assertTrue(all(item.get("anilist") == "999" for item in source.identities))

    async def test_lazy_staff_delegates_identity_and_is_retried(self) -> None:
        source = _FlakySource()
        proxy = PeopleRetryingSourceProxy(source)
        identity = AnimeIdentity({"shikimori": "48316"})

        with patch("sources.resilient.asyncio.sleep", new=AsyncMock()):
            people = await proxy.load_staff(identity)

        self.assertEqual(source.staff_calls, 2)
        self.assertEqual([person.name for person in people], ["Staff Person"])
        self.assertEqual(source.identities[-1].get("shikimori"), "48316")

    def test_metadata_only_source_does_not_gain_people_capabilities(self) -> None:
        class _MetadataOnlySource:
            name = "MetadataOnly"

            async def get_details(self, identity: AnimeIdentity):
                return None

        proxy = resilient_source(_MetadataOnlySource())

        self.assertIsInstance(proxy, RetryingSourceProxy)
        self.assertNotIsInstance(proxy, PeopleRetryingSourceProxy)
        self.assertFalse(hasattr(proxy, "load_staff"))
        self.assertFalse(hasattr(proxy, "load_voices"))

    def test_people_source_gets_generic_people_retry_proxy(self) -> None:
        source = _FlakySource()
        proxy = resilient_source(source)

        self.assertIsInstance(proxy, PeopleRetryingSourceProxy)
        self.assertNotEqual(type(proxy).__name__, "AniListSourceProxy")


if __name__ == "__main__":
    unittest.main()
