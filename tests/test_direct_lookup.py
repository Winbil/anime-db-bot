from __future__ import annotations

import unittest

from core.models import AnimeRecord
from services.direct_lookup import DirectIdLookupService


class FakeSource:
    def __init__(self, source_key: str, name: str, records: dict[str, AnimeRecord]) -> None:
        self.source_key = source_key
        self.name = name
        self.records = records
        self.calls: list[str] = []

    async def get_details(self, identity):
        value = str(identity.get(self.source_key) or "")
        self.calls.append(value)
        return self.records.get(value)


def record(
    source: str,
    source_id: str,
    *,
    title: str,
    external_ids: dict[str, str],
    poster: str | None = None,
) -> AnimeRecord:
    return AnimeRecord(
        source=source,
        source_id=source_id,
        titles={"romaji": title},
        external_ids=external_ids,
        posters=[poster] if poster else [],
    )


class DirectIdLookupTests(unittest.IsolatedAsyncioTestCase):
    async def test_selected_source_only_queries_that_source(self) -> None:
        mal = FakeSource(
            "mal",
            "MyAnimeList",
            {"10": record("MyAnimeList", "10", title="One", external_ids={"mal": "10"})},
        )
        anilist = FakeSource(
            "anilist",
            "AniList",
            {"10": record("AniList", "10", title="Other", external_ids={"anilist": "10"})},
        )
        service = DirectIdLookupService((mal, anilist))

        result = await service.lookup("10", source_keys=("mal",))

        self.assertEqual(len(result.items), 1)
        self.assertEqual(result.items[0].external_ids, {"mal": "10"})
        self.assertEqual(mal.calls, ["10"])
        self.assertEqual(anilist.calls, [])

    async def test_confirmed_cross_ids_merge_direct_hits(self) -> None:
        mal = FakeSource(
            "mal",
            "MyAnimeList",
            {
                "20": record(
                    "MyAnimeList",
                    "20",
                    title="Shared",
                    external_ids={"mal": "20", "anilist": "30"},
                    poster="https://example.invalid/mal.jpg",
                )
            },
        )
        anilist = FakeSource(
            "anilist",
            "AniList",
            {
                "20": record(
                    "AniList",
                    "20",
                    title="Different direct hit",
                    external_ids={"anilist": "20"},
                )
            },
        )
        bridge = FakeSource(
            "future",
            "Future",
            {
                "20": record(
                    "Future",
                    "20",
                    title="Shared",
                    external_ids={"future": "20", "mal": "20", "anilist": "30"},
                )
            },
        )
        service = DirectIdLookupService((mal, anilist, bridge))

        result = await service.lookup("20")

        self.assertEqual(len(result.items), 2)
        linked = next(item for item in result.items if item.external_ids.get("mal") == "20")
        self.assertEqual(
            linked.external_ids,
            {"mal": "20", "anilist": "30", "future": "20"},
        )
        self.assertIn("https://example.invalid/mal.jpg", linked.posters)

    async def test_same_number_and_same_title_do_not_merge_without_identity_edge(self) -> None:
        mal = FakeSource(
            "mal",
            "MyAnimeList",
            {"42": record("MyAnimeList", "42", title="Same title", external_ids={"mal": "42"})},
        )
        anilist = FakeSource(
            "anilist",
            "AniList",
            {"42": record("AniList", "42", title="Same title", external_ids={"anilist": "42"})},
        )
        service = DirectIdLookupService((mal, anilist))

        result = await service.lookup("42")

        self.assertEqual(len(result.items), 2)
        self.assertEqual(
            {frozenset(item.external_ids) for item in result.items},
            {frozenset({"mal"}), frozenset({"anilist"})},
        )


if __name__ == "__main__":
    unittest.main()
