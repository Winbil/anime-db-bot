from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, patch

import httpx

from core.models import AnimeRecord, PersonCredit
from sources.resilient import AniListSourceProxy, RetryingSourceProxy


class _FlakySource:
    name = "TestSource"

    def __init__(self) -> None:
        self.calls = 0
        self.staff_calls = 0

    async def get_details(self, mal_id: str, known_ids: dict[str, str]):
        self.calls += 1
        if self.calls < 3:
            raise httpx.ConnectError("temporary network failure")
        return AnimeRecord(
            source=self.name,
            source_id="1",
            external_ids={"mal": mal_id},
        )

    async def load_staff(self, mal_id: str, known_ids: dict[str, str]):
        self.staff_calls += 1
        if self.staff_calls < 2:
            raise httpx.ReadTimeout("temporary staff timeout")
        return [PersonCredit(name="Staff Person")]


class _AniListFake:
    name = "AniList"

    def __init__(self) -> None:
        self.details_calls = 0
        self.staff_calls = 0

    async def get_details(self, mal_id: str, known_ids: dict[str, str]):
        self.details_calls += 1
        return AnimeRecord(
            source="AniList",
            source_id="999",
            external_ids={"mal": mal_id, "anilist": "999"},
        )

    async def load_staff(self, mal_id: str, known_ids: dict[str, str]):
        self.staff_calls += 1
        return [PersonCredit(name="Staff Person", external_ids={"anilist": "1"})]

    async def load_voices(self, mal_id: str, known_ids: dict[str, str]):
        return []


class ResilientSourceTests(unittest.IsolatedAsyncioTestCase):
    async def test_transient_metadata_failure_is_retried(self) -> None:
        source = _FlakySource()
        proxy = RetryingSourceProxy(source)

        with patch("sources.resilient.asyncio.sleep", new=AsyncMock()):
            record = await proxy.get_details("48316", {"mal": "48316"})

        self.assertIsNotNone(record)
        self.assertEqual(source.calls, 3)

    async def test_lazy_staff_delegates_to_source_and_is_retried(self) -> None:
        source = _FlakySource()
        proxy = RetryingSourceProxy(source)

        with patch("sources.resilient.asyncio.sleep", new=AsyncMock()):
            people = await proxy.load_staff("48316", {"mal": "48316"})

        self.assertEqual(source.staff_calls, 2)
        self.assertEqual([person.name for person in people], ["Staff Person"])

    async def test_missing_optional_people_loader_returns_empty_list(self) -> None:
        class _MetadataOnlySource:
            name = "MetadataOnly"

            async def get_details(self, mal_id: str, known_ids: dict[str, str]):
                return None

        proxy = RetryingSourceProxy(_MetadataOnlySource())

        self.assertEqual(await proxy.load_staff("1", {"mal": "1"}), [])
        self.assertEqual(await proxy.load_voices("1", {"mal": "1"}), [])

    async def test_anilist_lazy_people_recovers_missing_media_id(self) -> None:
        source = _AniListFake()
        proxy = AniListSourceProxy(source)
        known_ids = {"mal": "48316"}

        people = await proxy.load_staff("48316", known_ids)

        self.assertEqual(source.details_calls, 1)
        self.assertEqual(source.staff_calls, 1)
        self.assertEqual(known_ids["anilist"], "999")
        self.assertEqual([person.name for person in people], ["Staff Person"])


if __name__ == "__main__":
    unittest.main()
