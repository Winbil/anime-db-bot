from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, patch

from bots.telegram.card.features.characters import (
    _keyboard,
    _merge_characters,
    _page_text,
    _source_name_for_selector,
)
from bots.telegram.card.runtime.state import AnimeCardSession
from core.character_identity import CharacterIdentity
from core.identity import AnimeIdentity
from core.models import AggregatedAnime, CharacterRecord
from services.media.characters import CharacterService
from sources.providers.anilist import _characters_from_connection
from sources.providers.jikan import JikanSource
from sources.providers.shikimori_people import _characters_from_roles


class CharacterParsingTests(unittest.IsolatedAsyncioTestCase):
    def test_anilist_character_role_names_and_portrait_are_normalized(self) -> None:
        values = _characters_from_connection(
            {
                "edges": [
                    {
                        "role": "MAIN",
                        "node": {
                            "id": 1,
                            "name": {
                                "full": "Cid Kagenou",
                                "native": "影野 実",
                                "alternative": ["Shadow"],
                            },
                            "image": {
                                "large": "https://img.example/cid.jpg",
                                "medium": None,
                            },
                        },
                    }
                ]
            }
        )
        self.assertEqual(len(values), 1)
        self.assertEqual(values[0].role, "main")
        self.assertEqual(values[0].external_ids, {"anilist": "1"})
        self.assertIn("影野 実", values[0].aliases)
        self.assertEqual(
            values[0].portraits["AniList"], ["https://img.example/cid.jpg"]
        )

    def test_shikimori_character_uses_roles_payload_without_extra_lookup(self) -> None:
        values = _characters_from_roles(
            [
                {
                    "roles": ["Supporting"],
                    "character": {
                        "id": 194178,
                        "name": "Alpha",
                        "russian": "Альфа",
                        "image": {"original": "/system/characters/original/194178.jpg"},
                    },
                }
            ]
        )
        self.assertEqual(len(values), 1)
        self.assertEqual(values[0].role, "supporting")
        self.assertEqual(values[0].external_ids, {"shikimori": "194178"})
        self.assertIn("Альфа", values[0].aliases)
        self.assertTrue(values[0].portraits["Shikimori"][0].startswith("https://"))

    async def test_jikan_characters_reuse_existing_people_payload(self) -> None:
        source = JikanSource()
        payload = {
            "characters": [
                {
                    "character": {
                        "mal_id": 20123,
                        "name": "Cid Kagenou",
                        "image_url": "https://cdn.myanimelist.net/cid.jpg",
                    },
                    "role": "Main",
                    "favorites": 100,
                }
            ]
        }
        with patch.object(
            source, "_load_people_payload", new=AsyncMock(return_value=payload)
        ) as loader:
            values = await source.load_characters(AnimeIdentity({"mal": "48316"}))
        loader.assert_awaited_once()
        self.assertEqual(len(values), 1)
        self.assertEqual(values[0].role, "main")
        self.assertEqual(values[0].external_ids, {"mal": "20123"})
        self.assertIn("MAL (MyAnimeList) / Jikan", values[0].portraits)


class _FakeSource:
    def __init__(
        self, name: str, source_key: str, values: list[CharacterRecord]
    ) -> None:
        self.name = name
        self.source_key = source_key
        self.values = values
        self.calls = 0

    async def load_characters(self, identity: AnimeIdentity) -> list[CharacterRecord]:
        self.calls += 1
        return list(self.values)


class CharacterServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_only_sources_with_confirmed_identity_are_called(self) -> None:
        ani = _FakeSource("AniList", "anilist", [CharacterRecord(name="Cid")])
        shi = _FakeSource("Shikimori", "shikimori", [CharacterRecord(name="Cid")])
        result = await CharacterService((ani, shi)).load(
            AnimeIdentity({"anilist": "1"})
        )
        self.assertEqual(ani.calls, 1)
        self.assertEqual(shi.calls, 0)
        self.assertIn("AniList", result.by_source)
        self.assertEqual(result.key_by_source, {"AniList": "anilist"})


class CharacterIdentityTests(unittest.TestCase):
    def test_shared_provider_id_confirms_match(self) -> None:
        left = CharacterIdentity({"anilist": "1"})
        right = CharacterIdentity({"anilist": "1", "shikimori": "2"})
        self.assertTrue(left.matches(right))
        left.merge_missing(right)
        self.assertEqual(left.external_ids, {"anilist": "1", "shikimori": "2"})

    def test_same_provider_different_id_is_conflict(self) -> None:
        left = CharacterIdentity({"anilist": "1"})
        right = CharacterIdentity({"anilist": "9"})
        self.assertTrue(left.conflicts_with(right))
        self.assertFalse(left.matches(right))


class CharacterUiTests(unittest.TestCase):
    def test_cross_source_exact_name_variants_merge_with_portrait_provenance(
        self,
    ) -> None:
        merged = _merge_characters(
            [
                [
                    CharacterRecord(
                        name="Cid Kagenou",
                        role="main",
                        aliases=["影野 実"],
                        portraits={"AniList": ["https://img.example/ani.jpg"]},
                    )
                ],
                [
                    CharacterRecord(
                        name="Cid Kagenou",
                        role="main",
                        aliases=["Сид Кагэно"],
                        portraits={"Shikimori": ["https://img.example/shi.jpg"]},
                    )
                ],
            ]
        )
        self.assertEqual(len(merged), 1)
        self.assertIn("Сид Кагэно", merged[0].aliases)
        self.assertEqual(set(merged[0].portraits), {"AniList", "Shikimori"})

    def test_mal_comma_name_merges_with_anilist_given_family_order(self) -> None:
        merged = _merge_characters(
            [
                [CharacterRecord(name="Cid Kagenou", role="main")],
                [CharacterRecord(name="Kagenou, Cid", role="main")],
            ]
        )
        self.assertEqual(len(merged), 1)
        self.assertIn("Kagenou, Cid", merged[0].aliases)

    def test_same_name_with_conflicting_source_ids_does_not_merge(self) -> None:
        values = _merge_characters(
            [
                [
                    CharacterRecord(name="Cid Kagenou", external_ids={"anilist": "1"}),
                    CharacterRecord(name="Cid Kagenou", external_ids={"anilist": "2"}),
                ]
            ]
        )
        self.assertEqual(len(values), 2)

    def test_name_fallback_does_not_infer_cross_provider_ids(self) -> None:
        values = _merge_characters(
            [
                [CharacterRecord(name="Cid Kagenou", external_ids={"anilist": "1"})],
                [CharacterRecord(name="Cid Kagenou", external_ids={"shikimori": "2"})],
            ]
        )
        self.assertEqual(len(values), 1)
        self.assertEqual(values[0].external_ids, {"anilist": "1"})

    def test_shared_character_id_merges_even_when_names_differ(self) -> None:
        values = _merge_characters(
            [
                [CharacterRecord(name="Kagenou, Cid", external_ids={"anilist": "1"})],
                [CharacterRecord(name="Cid Kagenou", external_ids={"anilist": "1"})],
            ]
        )
        self.assertEqual(len(values), 1)
        self.assertEqual(values[0].external_ids["anilist"], "1")

    def test_character_source_selector_supports_stable_and_legacy_callbacks(
        self,
    ) -> None:
        anime = AggregatedAnime(
            title="Shadow",
            sources=["Shikimori", "AniList"],
            characters_by_source={
                "Shikimori": [CharacterRecord(name="Cid")],
                "AniList": [CharacterRecord(name="Cid")],
            },
        )
        session = AnimeCardSession(
            anime=anime,
            owner_user_id=1,
            characters_loaded=True,
            character_key_by_source={
                "Shikimori": "shikimori",
                "AniList": "anilist",
            },
        )
        self.assertEqual(
            _source_name_for_selector(session, "anilist"),
            ("anilist", "AniList"),
        )
        self.assertEqual(
            _source_name_for_selector(session, "0"),
            ("shikimori", "Shikimori"),
        )

    def test_character_view_has_same_source_and_portrait_navigation_shape(self) -> None:
        anime = AggregatedAnime(
            title="Shadow",
            sources=["Shikimori", "AniList"],
            characters_by_source={
                "Shikimori": [
                    CharacterRecord(
                        name="Cid Kagenou",
                        role="main",
                        portraits={"Shikimori": ["https://img.example/cid.jpg"]},
                    )
                ],
                "AniList": [CharacterRecord(name="Cid Kagenou", role="main")],
            },
        )
        session = AnimeCardSession(anime=anime, owner_user_id=1, characters_loaded=True)
        content, urls, shown, total, page = _page_text(session, None, 1, locale="ru")
        keyboard = _keyboard(
            "token",
            [("shikimori", "Shikimori"), ("anilist", "AniList")],
            None,
            page,
            shown,
            total,
            1,
            locale="ru",
        )
        self.assertIn("Персонажи", content)
        self.assertIn("Роль: Главный", content)
        self.assertEqual(urls, ["https://img.example/cid.jpg"])
        self.assertEqual(
            keyboard.inline_keyboard[1][0].callback_data, "av:token:characters:0"
        )
        self.assertEqual(
            keyboard.inline_keyboard[2][0].callback_data,
            "ac:token:shikimori:0",
        )


if __name__ == "__main__":
    unittest.main()
