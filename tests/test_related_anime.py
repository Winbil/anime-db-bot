from __future__ import annotations

import unittest
import xml.etree.ElementTree as ET
from unittest.mock import AsyncMock, patch

from bots.telegram.card.features.related import related_keyboard
from bots.telegram.card.ui.keyboards import fallback_main_keyboard, navigation_keyboard
from bots.telegram.card.views.main import main_rich
from core.identity import AnimeIdentity
from core.models import AggregatedAnime
from core.related_anime import AnimeReference, canonical_relation_kind
from services.media.related import RelatedAnimeService
from sources.providers.anidb import AniDBSource
from sources.providers.anilist import AniListSource
from sources.providers.anisearch import AniSearchSource
from sources.providers.kitsu import KitsuSource
from sources.providers.mal import MALSource
from sources.providers.shikimori import ShikimoriSource


class _MappingResolver:
    def enrich(self, identity: AnimeIdentity) -> AnimeIdentity:
        result = identity.copy()
        if result.get("mal") == "20":
            result.merge_missing({"anilist": "200"})
        if result.get("anilist") == "200":
            result.merge_missing({"mal": "20"})
        if result.get("shikimori") == "2000":
            result.merge_missing({"mal": "20", "anilist": "200"})
        return result


class _Source:
    def __init__(
        self,
        name: str,
        source_key: str,
        *,
        relations: list[AnimeReference] | None = None,
        recommendations: list[AnimeReference] | None = None,
    ) -> None:
        self.name = name
        self.source_key = source_key
        self._relations = relations or []
        self._recommendations = recommendations or []

    async def load_relations(self, identity: AnimeIdentity) -> list[AnimeReference]:
        del identity
        return list(self._relations)

    async def load_recommendations(
        self, identity: AnimeIdentity
    ) -> list[AnimeReference]:
        del identity
        return list(self._recommendations)


class RelatedAnimeCoreTests(unittest.TestCase):
    def test_relation_aliases_are_canonical(self) -> None:
        self.assertEqual(canonical_relation_kind("Spin-off"), "spin_off")
        self.assertEqual(
            canonical_relation_kind("Alternative version"), "alternative_version"
        )
        self.assertEqual(canonical_relation_kind("PARENT_STORY"), "parent")


class RelatedAnimeServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_confirmed_mapping_edges_merge_three_sources(self) -> None:
        service = RelatedAnimeService(
            (
                _Source(
                    "MAL (MyAnimeList) / Jikan",
                    "mal",
                    recommendations=[
                        AnimeReference(
                            source="MAL (MyAnimeList)",
                            titles={"romaji": "Target"},
                            external_ids={"mal": "20"},
                            rank=1,
                        )
                    ],
                ),
                _Source(
                    "AniList",
                    "anilist",
                    recommendations=[
                        AnimeReference(
                            source="AniList",
                            titles={"english": "Target English"},
                            external_ids={"anilist": "200"},
                            rank=2,
                        )
                    ],
                ),
                _Source(
                    "Shikimori",
                    "shikimori",
                    recommendations=[
                        AnimeReference(
                            source="Shikimori",
                            titles={"russian": "Цель"},
                            external_ids={"shikimori": "2000"},
                            rank=3,
                        )
                    ],
                ),
            ),
            _MappingResolver(),
        )
        result = await service.load_recommendations(
            AnimeIdentity({"mal": "1", "anilist": "1", "shikimori": "1"})
        )
        self.assertEqual(len(result.items), 1)
        item = result.items[0]
        self.assertEqual(item.external_ids["mal"], "20")
        self.assertEqual(item.external_ids["anilist"], "200")
        self.assertEqual(item.external_ids["shikimori"], "2000")
        self.assertEqual(item.sources, ["MAL (MyAnimeList)", "AniList", "Shikimori"])
        self.assertEqual(set(result.by_source), {"mal", "anilist", "shikimori"})
        self.assertEqual(result.source_names["mal"], "MAL (MyAnimeList)")
        self.assertEqual(len(result.by_source["mal"]), 1)
        self.assertEqual(result.by_source["mal"][0].sources, ["MAL (MyAnimeList)"])

    async def test_same_title_without_identity_evidence_does_not_merge(self) -> None:
        service = RelatedAnimeService(
            (
                _Source(
                    "MAL (MyAnimeList) / Jikan",
                    "mal",
                    recommendations=[
                        AnimeReference(
                            source="MAL (MyAnimeList)",
                            titles={"romaji": "Same title"},
                            external_ids={"mal": "20"},
                        )
                    ],
                ),
                _Source(
                    "AniList",
                    "anilist",
                    recommendations=[
                        AnimeReference(
                            source="AniList",
                            titles={"romaji": "Same title"},
                            external_ids={"anilist": "999"},
                        )
                    ],
                ),
            ),
            _MappingResolver(),
        )
        result = await service.load_recommendations(
            AnimeIdentity({"mal": "1", "anilist": "1"})
        )
        self.assertEqual(len(result.items), 2)

    async def test_current_anime_is_filtered_from_results(self) -> None:
        service = RelatedAnimeService(
            (
                _Source(
                    "AniList",
                    "anilist",
                    relations=[
                        AnimeReference(
                            source="AniList",
                            titles={"romaji": "Self"},
                            external_ids={"anilist": "1"},
                            relation="sequel",
                        )
                    ],
                ),
            ),
            _MappingResolver(),
        )
        result = await service.load_relations(AnimeIdentity({"anilist": "1"}))
        self.assertEqual(result.items, [])


class RelatedAnimeSourceTests(unittest.IsolatedAsyncioTestCase):
    async def test_mal_relations_and_recommendations_are_lazy(self) -> None:
        source = MALSource.__new__(MALSource)
        source._settings = object()
        related_payload = {
            "related_anime": [
                {
                    "relation_type": "sequel",
                    "node": {
                        "id": 20,
                        "title": "Target",
                        "main_picture": {"large": "https://img/20.jpg"},
                    },
                }
            ]
        }
        rec_payload = {
            "recommendations": [
                {
                    "num_recommendations": 8,
                    "node": {"id": 30, "title": "Recommended"},
                }
            ]
        }
        with patch(
            "sources.providers.mal._get_raw",
            AsyncMock(side_effect=[related_payload, rec_payload]),
        ) as request:
            relations = await source.load_relations(AnimeIdentity({"mal": "1"}))
            recommendations = await source.load_recommendations(
                AnimeIdentity({"mal": "1"})
            )
        self.assertEqual(relations[0].relation, "sequel")
        self.assertEqual(relations[0].external_ids, {"mal": "20"})
        self.assertEqual(recommendations[0].external_ids, {"mal": "30"})
        self.assertEqual(request.await_count, 2)

    async def test_anilist_relations_keep_peer_mal_id(self) -> None:
        source = AniListSource()
        payload = {
            "Media": {
                "id": 1,
                "relations": {
                    "edges": [
                        {
                            "relationType": "PREQUEL",
                            "node": {
                                "id": 200,
                                "idMal": 20,
                                "type": "ANIME",
                                "title": {"romaji": "Target"},
                                "coverImage": {},
                            },
                        }
                    ]
                },
            }
        }
        with patch(
            "sources.providers.anilist.graphql_request",
            AsyncMock(return_value=payload),
        ):
            result = await source.load_relations(AnimeIdentity({"anilist": "1"}))
        self.assertEqual(result[0].relation, "prequel")
        self.assertEqual(result[0].external_ids, {"anilist": "200", "mal": "20"})

    async def test_shikimori_related_skips_manga_and_similar_is_capped(self) -> None:
        source = ShikimoriSource.__new__(ShikimoriSource)
        source._settings = object()
        related = [
            {"relation": "Adaptation", "manga": {"id": 1}, "anime": None},
            {
                "relation": "Sequel",
                "anime": {
                    "id": 20,
                    "name": "Target",
                    "russian": "Цель",
                    "image": {},
                },
            },
        ]
        similar = [
            {"id": index, "name": f"Anime {index}", "image": {}}
            for index in range(1, 50)
        ]
        with (
            patch(
                "sources.providers.shikimori._load_related_rest",
                AsyncMock(side_effect=[related, similar]),
            ),
            patch(
                "sources.providers.shikimori._load_peer_mal_ids",
                AsyncMock(side_effect=[{"20": "200"}, {}]),
            ),
        ):
            relations = await source.load_relations(AnimeIdentity({"shikimori": "1"}))
            recommendations = await source.load_recommendations(
                AnimeIdentity({"shikimori": "1"})
            )
        self.assertEqual(len(relations), 1)
        self.assertEqual(relations[0].relation, "sequel")
        self.assertEqual(relations[0].external_ids, {"shikimori": "20", "mal": "200"})
        self.assertEqual(len(recommendations), 30)

    async def test_kitsu_relations_keep_only_anime_destinations(self) -> None:
        source = KitsuSource.__new__(KitsuSource)
        source._settings = object()
        payload = {
            "data": {
                "type": "anime",
                "id": "1",
                "relationships": {
                    "mediaRelationships": {
                        "data": [
                            {"type": "mediaRelationships", "id": "10"},
                            {"type": "mediaRelationships", "id": "11"},
                        ]
                    }
                },
            },
            "included": [
                {
                    "type": "mediaRelationships",
                    "id": "10",
                    "attributes": {"role": "sequel"},
                    "relationships": {
                        "destination": {"data": {"type": "anime", "id": "2"}}
                    },
                },
                {
                    "type": "mediaRelationships",
                    "id": "11",
                    "attributes": {"role": "adaptation"},
                    "relationships": {
                        "destination": {"data": {"type": "manga", "id": "3"}}
                    },
                },
                {
                    "type": "anime",
                    "id": "2",
                    "attributes": {
                        "titles": {"en_jp": "Target"},
                        "canonicalTitle": "Target",
                        "posterImage": {"large": "https://img/2.jpg"},
                    },
                },
                {"type": "manga", "id": "3", "attributes": {"canonicalTitle": "Manga"}},
            ],
        }
        with patch(
            "sources.providers.kitsu._request_json",
            AsyncMock(return_value=payload),
        ):
            result = await source.load_relations(AnimeIdentity({"kitsu": "1"}))
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].external_ids, {"kitsu": "2"})
        self.assertEqual(result[0].relation, "sequel")
        self.assertEqual(result[0].titles["romaji"], "Target")

    async def test_anidb_uses_related_and_similar_anime_blocks(self) -> None:
        source = AniDBSource.__new__(AniDBSource)
        source._settings = object()
        root = ET.fromstring(
            """
            <anime id="1">
              <relatedanime>
                <anime id="2" type="Sequel">Target sequel</anime>
              </relatedanime>
              <similaranime>
                <anime id="3" approval="5" total="9">Lower</anime>
                <anime id="4" approval="12" total="20">Higher</anime>
              </similaranime>
            </anime>
            """
        )
        source._load_root = AsyncMock(return_value=root)
        relations = await source.load_relations(AnimeIdentity({"anidb": "1"}))
        recommendations = await source.load_recommendations(
            AnimeIdentity({"anidb": "1"})
        )
        self.assertEqual(relations[0].external_ids, {"anidb": "2"})
        self.assertEqual(relations[0].relation, "Sequel")
        self.assertEqual(
            [item.external_ids["anidb"] for item in recommendations], ["4", "3"]
        )

    async def test_anisearch_relations_use_related_anime_map(self) -> None:
        source = AniSearchSource.__new__(AniSearchSource)
        source._settings = object()
        source._payload = AsyncMock(
            return_value={"related": {"anime": {"20": "Side Story", "30": "Summary"}}}
        )
        result = await source.load_relations(AnimeIdentity({"anisearch": "1"}))
        self.assertEqual(
            [item.external_ids["anisearch"] for item in result], ["20", "30"]
        )
        self.assertEqual(result[0].relation, "Side Story")


class RelatedAnimeUiTests(unittest.TestCase):
    def test_main_card_keeps_discovery_actions_out_of_rich_html(self) -> None:
        anime = AggregatedAnime(title="Test", external_ids={"mal": "1"})
        rich = main_rich("token", anime, "Test", locale="ru")
        self.assertNotIn('data="av:token:related:0"', rich.html)
        self.assertNotIn('data="av:token:recommendations:0"', rich.html)

    def test_main_navigation_uses_inline_discovery_buttons(self) -> None:
        anime = AggregatedAnime(title="Test", external_ids={"mal": "1"})
        keyboard = navigation_keyboard("token", anime, "main", 0, 1, locale="ru")
        self.assertIsNotNone(keyboard)
        assert keyboard is not None
        callbacks = [
            button.callback_data
            for row in keyboard.inline_keyboard
            for button in row
            if button.callback_data
        ]
        self.assertEqual(
            callbacks,
            ["av:token:related:0", "av:token:recommendations:0"],
        )

    def test_fallback_main_keyboard_has_both_discovery_buttons(self) -> None:
        keyboard = fallback_main_keyboard("token", locale="ru")
        callbacks = [
            button.callback_data
            for row in keyboard.inline_keyboard
            for button in row
            if button.callback_data
        ]
        self.assertIn("av:token:related:0", callbacks)
        self.assertIn("av:token:recommendations:0", callbacks)

    def test_related_keyboard_uses_item_callbacks_and_pagination(self) -> None:
        items = [
            __import__(
                "core.related_anime", fromlist=["AggregatedAnimeReference"]
            ).AggregatedAnimeReference(
                titles={"romaji": f"Title {index}"},
                external_ids={"mal": str(index)},
                relations=["sequel"],
            )
            for index in range(1, 8)
        ]
        keyboard = related_keyboard(
            "token",
            "related",
            items,
            0,
            source_key="all",
            source_names={"mal": "MAL", "anilist": "AniList"},
            locale="ru",
        )
        callbacks = [
            button.callback_data
            for row in keyboard.inline_keyboard
            for button in row
            if button.callback_data
        ]
        self.assertIn("ari:token:related~all:0", callbacks)
        self.assertIn("ar:token:related~mal:0", callbacks)
        self.assertIn("ar:token:related~anilist:0", callbacks)
        self.assertIn("av:token:main:0", callbacks)
        self.assertTrue(
            any(value.startswith("cp:token:ar~related~all:") for value in callbacks)
        )


if __name__ == "__main__":
    unittest.main()
