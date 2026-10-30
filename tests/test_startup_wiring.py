from __future__ import annotations

import inspect
import unittest

from aiogram.types import InputRichMessage

from bots.telegram.bot import _CallbackRoutingMiddleware, select_transport
from bots.telegram.card.runtime import handlers as card_handlers
from bots.telegram.card.runtime import state as card_state_module
from bots.telegram.card.ui.constants import SOURCE_SELECTABLE_SECTIONS
from bots.telegram.card.runtime.state import TelegramCardState
from bots.telegram.card.ui.selectors import source_section_sources
from bots.telegram.people import loading as people_loading_module
from bots.telegram.people.portraits import (
    _sources_with_portraits,
    handle_people_callback,
)
from bots.telegram.search.handlers import register_search_handlers
from bots.telegram.transports.official import OfficialTelegramTransport
from bots.telegram.transports.tgapi import LocalTelegramTransport
from core.canonicalization import (
    canonical_genre,
    canonical_role,
    is_primary_voice_role,
    localize_role_token,
    person_identity_keys,
)
from core.contracts import AnimeSearchProvider, AnimeSource
from core.http_config import USER_AGENT
from core.proxy_config import ProxyEntry, ProxyProfile
from core.settings import TelegramSettings
from core.models import (
    AggregatedAnime,
    AnimeRecord,
    PersonCredit,
    PopularityStats,
    SearchCandidate,
    SearchPage,
)
from search.providers.anilist import AniListSearchProvider
from search.providers.mal import MALSearchProvider
from search.providers.shikimori import ShikimoriSearchProvider
from search.registry import get_search_provider_map, get_search_providers
from services.aggregation.service import AnimeAggregator, _merge_people
from services.media.people import PeopleLoadProgress
from services.search.service import SearchService
from sources.providers.anilist import AniListSource
from sources.providers.mal import MALSource
from sources.runtime.registry import get_sources
from sources.providers.shikimori import ShikimoriSource
from sources.providers.shikimori_people import _rest_voice_credits


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
        card_state = TelegramCardState.create(300)
        self.assertIsNotNone(_CallbackRoutingMiddleware(card_state))

        search_service = SearchService(providers)
        aggregator = AnimeAggregator(sources)
        self.assertTrue(search_service.provider_name)
        self.assertIsNotNone(aggregator)

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

    def test_card_runtime_state_is_per_bot_run(self) -> None:
        first = TelegramCardState.create(300)
        second = TelegramCardState.create(300)
        anime = AggregatedAnime(title="Runtime state")

        token = first.remember_anime(anime, owner_user_id=42)
        first.people_loads["token:staff"] = PeopleLoadProgress()
        dispatcher = card_handlers.build_dispatcher("test", first)

        self.assertIsNotNone(dispatcher)
        self.assertIsNotNone(first.anime_sessions.get(token))
        self.assertIsNone(second.anime_sessions.get(token))
        self.assertIsNotNone(first.people_loads.get("token:staff"))
        self.assertIsNone(second.people_loads.get("token:staff"))
        self.assertFalse(hasattr(card_state_module, "ANIME_SESSIONS"))
        self.assertFalse(hasattr(people_loading_module, "PEOPLE_LOADS"))

    def test_callback_handlers_use_real_message_attribute(self) -> None:
        self.assertNotIn(".messae", inspect.getsource(card_handlers))

    def test_telegram_transport_selection(self) -> None:
        base = dict(
            bot_token="123456:TEST_TOKEN",
            bot_api_local=False,
            session_ttl_seconds=3600,
            anime_input_ttl_seconds=300,
            admin_user_ids=(),
        )
        official = select_transport(TelegramSettings(bot_api_url="", **base))
        local_settings = TelegramSettings(bot_api_url="http://127.0.0.1:8081", **base)
        local = select_transport(local_settings)
        proxied = select_transport(
            local_settings,
            ProxyProfile(
                name="telegram",
                proxies=(ProxyEntry("proxy", "socks5://127.0.0.1:1080"),),
            ),
        )

        self.assertIsInstance(official, OfficialTelegramTransport)
        self.assertIsInstance(local, LocalTelegramTransport)
        self.assertIsInstance(proxied, OfficialTelegramTransport)
        self.assertEqual(len(proxied.proxy_profile.active), 1)

    def test_canonicalization_contracts(self) -> None:
        self.assertEqual(canonical_genre("Fantasy"), canonical_genre("Фэнтези"))
        self.assertEqual(canonical_role("Director"), canonical_role("Режиссёр"))
        self.assertTrue(
            person_identity_keys(["Fuse"]) & person_identity_keys(["Фусэ", "Fuse"])
        )
        self.assertTrue(is_primary_voice_role("Сэйю"))
        self.assertFalse(is_primary_voice_role("Сэйю (EN)"))

    def test_source_selectable_sections_and_portraits(self) -> None:
        self.assertEqual(
            SOURCE_SELECTABLE_SECTIONS,
            {"titles", "staff", "voices", "popularity", "screenshots"},
        )

        sample = AggregatedAnime(
            title="Smoke test",
            sources=["AniList"],
            titles_by_source={"AniList": {"english": "Smoke test"}},
            popularity_by_source={
                "AniList": PopularityStats(list_users=100, scoring_users=80)
            },
            staff=[
                PersonCredit(
                    name="Test Person",
                    portraits={"AniList": ["https://example.invalid/staff.jpg"]},
                )
            ],
            voices=[
                PersonCredit(
                    name="Test Voice",
                    portraits={"AniList": ["https://example.invalid/voice.jpg"]},
                )
            ],
            staff_by_source={
                "AniList": [
                    PersonCredit(
                        name="Test Person",
                        portraits={"AniList": ["https://example.invalid/staff.jpg"]},
                    )
                ]
            },
            voices_by_source={
                "AniList": [
                    PersonCredit(
                        name="Test Voice",
                        portraits={"AniList": ["https://example.invalid/voice.jpg"]},
                    )
                ]
            },
        )

        self.assertEqual(source_section_sources(sample, "titles"), ["AniList"])
        self.assertEqual(source_section_sources(sample, "popularity"), ["AniList"])
        self.assertEqual(_sources_with_portraits(sample, "staff"), ["AniList"])
        self.assertEqual(_sources_with_portraits(sample, "voices"), ["AniList"])

    def test_shikimori_structural_voice_links(self) -> None:
        voices = _rest_voice_credits(
            [
                {
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
                }
            ]
        )

        self.assertEqual(len(voices), 1)
        self.assertEqual(voices[0].roles, ["voice_of::Test Character"])
        self.assertEqual(
            localize_role_token(voices[0].roles[0], locale="ru"),
            "Озвучка: Test Character",
        )
        self.assertEqual(
            localize_role_token(voices[0].roles[0], locale="en"),
            "Voice: Test Character",
        )

    def test_cross_source_portrait_merge(self) -> None:
        people = _merge_people(
            [
                [
                    PersonCredit(
                        name="Test Person",
                        portraits={"AniList": ["https://example.invalid/anilist.jpg"]},
                    )
                ],
                [
                    PersonCredit(
                        name="Test Person",
                        portraits={
                            "Shikimori": ["https://example.invalid/shikimori.jpg"]
                        },
                    )
                ],
            ]
        )

        self.assertEqual(len(people), 1)
        self.assertEqual(set(people[0].portraits), {"AniList", "Shikimori"})


if __name__ == "__main__":
    unittest.main()
