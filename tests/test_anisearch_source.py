from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, patch

from core.identity import AnimeIdentity
from core.settings import AppSettings
from core.source_errors import SourceUnavailable
from core.source_keys import SourceKey
from sources.providers import anisearch
from sources.providers.anisearch import AniSearchSource


def _payload() -> dict:
    return {
        "id": 5048,
        "url": "https://www.anisearch.com/anime/5048,hagane-no-renkinjutsushi-2009",
        "external_ids": {"myanimelist": 5114, "anidb": 6107},
        "origin": "Japan",
        "title": "Hagane no Renkinjutsushi (2009)",
        "title_native": "鋼の錬金術師 FULLMETAL ALCHEMIST （2009）",
        "status": "Completed",
        "year": 2009,
        "season": "Spring 2009",
        "type": "TV-Series",
        "episodes": 64,
        "duration": 25,
        "aired_from": "2009-04-05",
        "aired_to": "2010-07-04",
        "studios": [{"id": 377, "name": "BONES Inc."}],
        "genres": {
            "main": ["Adventure"],
            "subsidiary": ["Fantasy", "Comedy"],
            "tags": ["Historical"],
            "explicit": None,
        },
        "adapted_from": ["Manga"],
        "cover": {
            "available": True,
            "large": "https://cdn.anisearch.com/fma.webp",
            "medium": "https://cdn.anisearch.com/fma-medium.webp",
            "nsfw": None,
        },
        "rank": 2,
        "score": 90,
        "member_count": 8400,
        "rating_count": 7385,
        "synonyms": ["FMA 2"],
        "releases": {
            "en": {
                "title": "Fullmetal Alchemist: Brotherhood",
                "publishers": [{"id": 632, "name": "FUNimation"}],
                "synonyms": ["FMA Brotherhood"],
                "synopsis": {
                    "text": "The <b>Elric</b> brothers ...",
                    "source": "anisearch",
                },
                "dubbed": "Yes",
            },
            "ja": {
                "title": "鋼の錬金術師",
                "synonyms": ["ハガレン"],
                "synopsis": {"text": "兄弟の物語。", "source": "blurb"},
            },
            "de": {
                "title": "Fullmetal Alchemist: Brotherhood DE",
                "synonyms": ["Deutscher Alias"],
                "synopsis": {"text": "Deutsche Beschreibung", "source": "anisearch"},
            },
        },
        "details": {
            "episodes": {
                "ja": [
                    {
                        "number": "1",
                        "title": "鋼の錬金術師",
                        "minutes": 25,
                        "publication": "2009-04-05",
                        "filler": False,
                        "recap": False,
                    },
                    {
                        "number": "2",
                        "title": "はじまりの日",
                        "minutes": 25,
                        "publication": "2009-04-12",
                        "filler": True,
                        "recap": False,
                    },
                ],
                "en": [
                    {
                        "number": "1",
                        "title": "Fullmetal Alchemist",
                        "minutes": 25,
                        "publication": "2010-02-13",
                        "filler": False,
                        "recap": True,
                    }
                ],
                "de": [
                    {
                        "number": "1",
                        "title": "Der Stahlalchemist",
                        "minutes": 25,
                        "publication": "2014-01-01",
                        "filler": False,
                        "recap": False,
                    }
                ],
            },
            "characters": [
                {
                    "id": 563,
                    "name": "Edward ELRIC",
                    "role": "main",
                    "voices": {
                        "ja": [
                            {
                                "name": "Edward Elric",
                                "person": {"id": 1067, "name": "Romi PARK"},
                            }
                        ],
                        "en": [
                            {
                                "name": "Edward Elric",
                                "person": {"id": 8632, "name": "Vic MIGNOGNA"},
                            }
                        ],
                        "de": [
                            {
                                "name": "Edward Elric",
                                "person": {"id": 4010, "name": "David TURBA"},
                            }
                        ],
                    },
                },
                {
                    "id": 531,
                    "name": "Alphonse ELRIC",
                    "role": "supporting",
                    "voices": {},
                },
            ],
            "staff": [
                {
                    "name": "Direction",
                    "creators": [
                        {
                            "id": 19695,
                            "name": "Yasuhiro IRIE",
                            "tasks": [
                                {
                                    "name": "Direction",
                                    "name_native": "監督",
                                    "episodes": None,
                                },
                                {
                                    "name": "Episode Direction",
                                    "name_native": "演出",
                                    "episodes": "1–3",
                                },
                            ],
                        }
                    ],
                }
            ],
        },
    }


class AniSearchParserTests(unittest.TestCase):
    def test_metadata_uses_only_enabled_english_and_japanese_localizations(
        self,
    ) -> None:
        record = anisearch._record(_payload(), "5048")
        self.assertEqual(record.source, "AniSearch")
        self.assertEqual(record.source_id, "5048")
        self.assertEqual(record.external_ids["anisearch"], "5048")
        self.assertEqual(record.external_ids["mal"], "5114")
        self.assertEqual(record.external_ids["anidb"], "6107")
        self.assertEqual(record.titles["english"], "Fullmetal Alchemist: Brotherhood")
        self.assertEqual(
            record.titles["japanese"], "鋼の錬金術師 FULLMETAL ALCHEMIST （2009）"
        )
        self.assertIn("ハガレン", record.synonyms)
        self.assertNotIn("Deutscher Alias", record.synonyms)
        self.assertNotIn("Fullmetal Alchemist: Brotherhood DE", record.synonyms)
        self.assertEqual(record.kind, "tv")
        self.assertEqual(record.status, "finished")
        self.assertEqual(record.season, "spring")
        self.assertEqual(record.season_year, 2009)
        self.assertEqual(record.episodes_total, 64)
        self.assertEqual(record.duration_minutes, 25)
        self.assertEqual(record.score, 9.0)
        self.assertEqual(record.source_materials, ["manga"])
        self.assertEqual(record.licensors, ["FUNimation"])
        self.assertEqual(record.posters, ["https://cdn.anisearch.com/fma.webp"])

    def test_description_filters_locales_and_preserves_required_attribution(
        self,
    ) -> None:
        details = anisearch._description(_payload())
        self.assertIsNotNone(details.description)
        value = details.description or ""
        self.assertIn("English:\nThe Elric brothers ...", value)
        self.assertIn("日本語:\n兄弟の物語。", value)
        self.assertNotIn("Deutsche Beschreibung", value)
        self.assertIn("aniSearch: https://www.anisearch.com/anime/5048", value)

    def test_episode_parser_merges_only_japanese_and_english_rows(self) -> None:
        episodes = anisearch._episodes(_payload())
        self.assertEqual([item.number for item in episodes], [1, 2])
        first = episodes[0]
        self.assertEqual(first.titles["japanese"], "鋼の錬金術師")
        self.assertEqual(first.titles["english"], "Fullmetal Alchemist")
        self.assertNotIn("german", first.titles)
        self.assertEqual(first.aired_at.isoformat(), "2009-04-05")
        self.assertEqual(first.duration_seconds, 1500)
        self.assertFalse(first.filler)
        self.assertTrue(first.recap)
        self.assertTrue(episodes[1].filler)

    def test_characters_staff_and_voices_keep_anisearch_ids(self) -> None:
        characters = anisearch._characters(_payload())
        self.assertEqual(len(characters), 2)
        self.assertEqual(characters[0].external_ids, {"anisearch": "563"})
        self.assertEqual(characters[0].role, "main")

        staff = anisearch._staff(_payload())
        self.assertEqual(len(staff), 1)
        self.assertEqual(staff[0].external_ids, {"anisearch": "19695"})
        self.assertEqual(staff[0].roles, ["Direction"])
        self.assertNotIn("Episode Direction", " ".join(staff[0].roles))

        voices = anisearch._voices(_payload())
        self.assertEqual(
            {person.name for person in voices}, {"Romi PARK", "Vic MIGNOGNA"}
        )
        self.assertNotIn("David TURBA", {person.name for person in voices})
        romi = next(person for person in voices if person.name == "Romi PARK")
        vic = next(person for person in voices if person.name == "Vic MIGNOGNA")
        self.assertEqual(romi.external_ids, {"anisearch": "1067"})
        self.assertTrue(any("Edward ELRIC" in role for role in romi.roles))
        self.assertTrue(any("[EN]" in role for role in vic.roles))

    def test_popularity_uses_cached_title_rating_fields(self) -> None:
        stats = anisearch._popularity(_payload())
        self.assertEqual(stats.rank, 2)
        self.assertEqual(stats.list_users, 8400)
        self.assertEqual(stats.scoring_users, 7385)


class AniSearchSourceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.settings = AppSettings.from_env(
            {
                "ANISEARCH_API_URL": "https://api.anisearch.test",
                "ANISEARCH_API_TOKEN": "",
                "ANISEARCH_CACHE_TTL_SECONDS": "0",
            }
        ).sources
        self.source = AniSearchSource(self.settings)
        self.identity = AnimeIdentity.from_mapping({"anisearch": "5048"})

    async def test_initial_metadata_uses_shared_full_payload_but_keeps_heavy_fields_lazy(
        self,
    ) -> None:
        loader = AsyncMock(return_value=_payload())
        with patch("sources.providers.anisearch._load_item", loader):
            record = await self.source.get_details(self.identity)
        self.assertIsNotNone(record)
        loader.assert_awaited_once_with("5048", settings=self.settings)
        self.assertEqual(record.staff, [])
        self.assertEqual(record.voices, [])

    async def test_lazy_sections_share_full_payload_parser_contract(self) -> None:
        loader = AsyncMock(return_value=_payload())
        with patch("sources.providers.anisearch._load_item", loader):
            characters = await self.source.load_characters(self.identity)
            staff = await self.source.load_staff(self.identity)
            voices = await self.source.load_voices(self.identity)
        self.assertEqual(len(characters), 2)
        self.assertEqual(len(staff), 1)
        self.assertEqual(len(voices), 2)
        self.assertTrue(
            all(
                call.kwargs["settings"] is self.settings
                for call in loader.await_args_list
            )
        )

    async def test_episode_backend_paginates_full_payload(self) -> None:
        loader = AsyncMock(return_value=_payload())
        with (
            patch("sources.providers.anisearch._load_item", loader),
            patch("sources.providers.anisearch.wait_for_upstream", AsyncMock()),
        ):
            page = await self.source.load_episode_page(self.identity, page=1)
            episode = await self.source.load_episode(self.identity, 1)
        self.assertEqual([item.number for item in page.items], [1, 2])
        self.assertFalse(page.has_next)
        self.assertIsNotNone(episode)
        self.assertEqual(episode.titles["english"], "Fullmetal Alchemist")

    async def test_one_cached_full_request_serves_metadata_and_lazy_sections(
        self,
    ) -> None:
        settings = AppSettings.from_env(
            {
                "ANISEARCH_API_URL": "https://cache-test.anisearch.invalid",
                "ANISEARCH_CACHE_TTL_SECONDS": "60",
            }
        ).sources
        source = AniSearchSource(settings)
        identity = AnimeIdentity.from_mapping({"anisearch": "5048"})
        anisearch._FULL_CACHE.clear()
        upstream = AsyncMock(return_value={"results": [_payload()]})
        with patch("sources.providers.anisearch._paced_request", upstream):
            record = await source.get_details(identity)
            characters = await source.load_characters(identity)
            staff = await source.load_staff(identity)
            voices = await source.load_voices(identity)
        self.assertIsNotNone(record)
        self.assertEqual(len(characters), 2)
        self.assertEqual(len(staff), 1)
        self.assertEqual(len(voices), 2)
        upstream.assert_awaited_once_with(
            "/v1/anime/5048/full", operation="full", settings=settings
        )
        anisearch._FULL_CACHE.clear()

    async def test_local_pacing_skips_instead_of_blocking_card(self) -> None:
        request = AsyncMock()
        with (
            patch.object(anisearch, "_LAST_NETWORK_REQUEST_AT", 100.0),
            patch("sources.providers.anisearch.time.monotonic", return_value=100.1),
            patch("sources.providers.anisearch.http_request", request),
            self.assertRaises(SourceUnavailable),
        ):
            await anisearch._paced_request(
                "/v1/anime/5048/full",
                operation="full",
                settings=self.settings,
            )

        request.assert_not_awaited()

    async def test_missing_anisearch_identity_never_calls_network(self) -> None:
        loader = AsyncMock(return_value=_payload())
        with patch("sources.providers.anisearch._load_item", loader):
            record = await self.source.get_details(
                AnimeIdentity.from_mapping({"mal": "5114"})
            )
        self.assertIsNone(record)
        loader.assert_not_awaited()

    def test_source_identity_is_native_anisearch(self) -> None:
        self.assertEqual(self.source.source_key, SourceKey.ANISEARCH)
        self.assertEqual(self.source.backend_key, "anisearch")


if __name__ == "__main__":
    unittest.main()
