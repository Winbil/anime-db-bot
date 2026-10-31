from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, patch

from bots.telegram.card.features.related import related_keyboard
from bots.telegram.card.ui.keyboards import fallback_main_keyboard
from bots.telegram.card.views.main import main_rich
from core.identity import AnimeIdentity
from core.models import AggregatedAnime
from core.related_anime import AnimeReference, canonical_relation_kind
from services.media.related import RelatedAnimeService
from sources.providers.anilist import AniListSource
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


class RelatedAnimeUiTests(unittest.TestCase):
    def test_main_card_places_discovery_buttons_at_bottom(self) -> None:
        anime = AggregatedAnime(title="Test", external_ids={"mal": "1"})
        rich = main_rich("token", anime, "Test", locale="ru")
        self.assertIn('data="av:token:related:0"', rich.html)
        self.assertIn('data="av:token:recommendations:0"', rich.html)
        self.assertLess(
            rich.html.index('data="av:token:related:0"'),
            rich.html.index('data="av:token:recommendations:0"'),
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
        keyboard = related_keyboard("token", "related", items, 0, locale="ru")
        callbacks = [
            button.callback_data
            for row in keyboard.inline_keyboard
            for button in row
            if button.callback_data
        ]
        self.assertIn("ari:token:related:0", callbacks)
        self.assertIn("av:token:related:1", callbacks)
        self.assertIn("av:token:main:0", callbacks)


if __name__ == "__main__":
    unittest.main()
