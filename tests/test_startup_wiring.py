from __future__ import annotations

import unittest
from unittest.mock import patch

from aiogram.types import InputRichMessage

from bots.telegram import common as common_bot
from bots.telegram.bot import _CallbackRoutingMiddleware, select_transport
from bots.telegram.people_portraits import _sources_with_portraits, handle_people_callback
from bots.telegram.search_ui import register_search_handlers
from bots.telegram.transports.official import TRANSPORT as OFFICIAL_TRANSPORT
from bots.telegram.transports.tgapi import TRANSPORT as TGAPI_TRANSPORT
from core.canonicalization import (
    canonical_genre,
    canonical_role,
    is_primary_voice_role,
    person_identity_keys,
)
from core.contracts import AnimeSearchProvider, AnimeSource
from core.http_config import USER_AGENT
from core.models import AggregatedAnime, AnimeRecord, PersonCredit, SearchCandidate, SearchPage
from search.providers.anilist import AniListSearchProvider
from search.providers.mal import MALSearchProvider
from search.providers.shikimori import ShikimoriSearchProvider
from search.registry import get_search_provider_map, get_search_providers
from services.aggregator import AnimeAggregator, _merge_people
from services.search import SearchService
from sources.anilist import AniListSource
from sources.mal import MALSource
from sources.registry import get_sources
from sources.shikimori import ShikimoriSource
from sources.shikimori_people import _rest_voice_credits


class StartupWiringTests(unittest.TestCase):
    def test_services_and_public_wiring_import(self) -> None:
        providers = get_search_providers()
        provider_map = get_search_provider_map()
        sources = get_sources()

        self.assertTrue(providers)
        self.assertTrue(provider_map)
        self.assertTrue(sources)
        self.assertTrue(USER_AGENT.startswith("anime-db-bot/"))
        self.assertTrue(callable(handle_people_callback))
        self.assertTrue(callable(register_search_handlers))
        self.assertIsNotNone(_CallbackRoutingMiddleware())

        SearchService(providers)
        AnimeAggregator(sources)

        # Keep imports exercised so accidental module/file removals fail CI.
        for imported in (
            InputRichMessage,
            AnimeSearchProvider,
            AnimeSource,
            AggregatedAnime,
            AnimeRecord,
            PersonCredit,
            SearchCandidate,
            SearchPage,
            AniListSearchProvider,
            MALSearchProvider,
            ShikimoriSearchProvider,
            AniListSource,
            MALSource,
            ShikimoriSource,
        ):
            self.assertIsNotNone(imported)

    def test_telegram_transport_selection(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            self.assertIs(select_transport(), OFFICIAL_TRANSPORT)

        with patch.dict(
            "os.environ",
            {"TELEGRAM_BOT_API_URL": "http://127.0.0.1:8081"},
            clear=True,
        ):
            self.assertIs(select_transport(), TGAPI_TRANSPORT)

        self.assertFalse(OFFICIAL_TRANSPORT.use_custom_api)
        self.assertTrue(TGAPI_TRANSPORT.use_custom_api)

    def test_canonicalization_contracts(self) -> None:
        self.assertEqual(canonical_genre("Fantasy"), canonical_genre("Фэнтези"))
        self.assertEqual(canonical_role("Director"), canonical_role("Режиссёр"))
        self.assertTrue(person_identity_keys(["Fuse"]) & person_identity_keys(["Фусэ", "Fuse"]))
        self.assertTrue(is_primary_voice_role("Сэйю"))
        self.assertFalse(is_primary_voice_role("Сэйю (EN)"))

    def test_source_selectable_sections_and_portraits(self) -> None:
        self.assertEqual(
            common_bot.SOURCE_SELECTABLE_SECTIONS,
            {"titles", "staff", "voices"},
        )

        sample = AggregatedAnime(
            title="Smoke test",
            sources=["AniList"],
            titles_by_source={"AniList": {"english": "Smoke test"}},
            staff=[PersonCredit(
                name="Test Person",
                portraits={"AniList": ["https://example.invalid/staff.jpg"]},
            )],
            voices=[PersonCredit(
                name="Test Voice",
                portraits={"AniList": ["https://example.invalid/voice.jpg"]},
            )],
            staff_by_source={"AniList": [PersonCredit(
                name="Test Person",
                portraits={"AniList": ["https://example.invalid/staff.jpg"]},
            )]},
            voices_by_source={"AniList": [PersonCredit(
                name="Test Voice",
                portraits={"AniList": ["https://example.invalid/voice.jpg"]},
            )]},
        )

        self.assertEqual(common_bot._source_section_sources(sample, "titles"), ["AniList"])
        self.assertEqual(_sources_with_portraits(sample, "staff"), ["AniList"])
        self.assertEqual(_sources_with_portraits(sample, "voices"), ["AniList"])

    def test_shikimori_structural_voice_links(self) -> None:
        voices = _rest_voice_credits([{
            "roles": ["Main"],
            "roles_russian": ["Главная роль"],
            "person": {
                "id": 1,
                "name": "Test Seiyuu",
                "russian": "",
                "image": {},
            },
            "character": {
                "id": 2,
                "name": "Test Character",
                "russian": "Тестовый персонаж",
                "image": {},
            },
        }])

        self.assertEqual(len(voices), 1)
        self.assertEqual(voices[0].roles, ["Озвучка: Тестовый персонаж"])

    def test_cross_source_portrait_merge(self) -> None:
        people = _merge_people([
            [PersonCredit(
                name="Test Person",
                portraits={"AniList": ["https://example.invalid/anilist.jpg"]},
            )],
            [PersonCredit(
                name="Test Person",
                portraits={"Shikimori": ["https://example.invalid/shikimori.jpg"]},
            )],
        ])

        self.assertEqual(len(people), 1)
        self.assertEqual(set(people[0].portraits), {"AniList", "Shikimori"})


if __name__ == "__main__":
    unittest.main()
