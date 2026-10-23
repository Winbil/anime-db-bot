from __future__ import annotations

import inspect
import unittest

from aiogram import Dispatcher

from bots.telegram import search_ui
from bots.telegram.card.service import SEARCH_PROVIDERS
from core.models import SearchCandidate
from services.direct_lookup import DirectIdLookupService
from services.search import SearchService


class DummyDirectSource:
    source_key = "dummy"
    name = "Dummy"

    async def get_details(self, identity):
        return None


async def _noop_aggregate(message, candidate, owner_user_id):
    return None


class UnifiedSearchUiTests(unittest.TestCase):
    def test_scope_parser_normalizes_provider_order(self) -> None:
        self.assertEqual(
            search_ui._parse_scope("mal,shikimori"),
            ("shikimori", "mal"),
        )
        self.assertEqual(search_ui._parse_scope("ani"), ("anilist",))
        self.assertEqual(search_ui._parse_scope("all"), search_ui.ALL_PROVIDER_KEYS)
        self.assertIsNone(search_ui._parse_scope("unknown-source"))

    def test_default_scope_reuses_shared_search_service(self) -> None:
        default_service = SearchService(SEARCH_PROVIDERS)

        service = search_ui._service_for(
            search_ui.DEFAULT_SEARCH_PROVIDER_KEYS,
            default_service,
        )

        self.assertIs(service, default_service)

    def test_direct_id_parser_supports_plain_and_explicit_ids(self) -> None:
        supported = ("mal", "anilist", "shikimori")
        self.assertEqual(
            search_ui._parse_direct_query("37430", supported),
            (None, "37430"),
        )
        self.assertEqual(
            search_ui._parse_direct_query("mal:37430", supported),
            ("mal", "37430"),
        )
        self.assertEqual(
            search_ui._parse_direct_query("ani:101280", supported),
            ("anilist", "101280"),
        )
        self.assertIsNone(
            search_ui._parse_direct_query("futuredb:42", supported)
        )
        self.assertIsNone(
            search_ui._parse_direct_query("Tensei Slime", supported)
        )

    def test_preview_contains_all_external_ids(self) -> None:
        session = search_ui.SearchSession(
            query="slime",
            owner_user_id=1,
            items=[],
        )
        candidate = SearchCandidate(
            title="Slime",
            year=2018,
            external_ids={
                "mal": "37430",
                "anilist": "101280",
                "shikimori": "37430",
                "futuredb": "77",
            },
        )

        value = search_ui._preview_text(session, candidate, locale="ru")

        self.assertIn("Slime", value)
        self.assertIn("Год: 2018", value)
        self.assertIn("MAL: 37430", value)
        self.assertIn("AniList: 101280", value)
        self.assertIn("Shikimori: 37430", value)
        self.assertIn("FUTUREDB: 77", value)

    def test_preview_pagination_marks_incomplete_count(self) -> None:
        keyboard = search_ui._preview_keyboard(
            "token",
            2,
            18,
            complete=False,
            locale="ru",
        )
        nav = keyboard.inline_keyboard[0]

        self.assertEqual(nav[0].text, "◀️")
        self.assertEqual(nav[1].text, "3/18+")
        self.assertEqual(nav[2].text, "▶️")
        self.assertEqual(keyboard.inline_keyboard[1][0].text, "Подробнее")

    def test_legacy_search_command_is_not_registered(self) -> None:
        source = inspect.getsource(search_ui.register_search_handlers)
        self.assertNotIn('Command("search")', source)
        self.assertIn('Command("anime")', source)

    def test_handlers_register_on_real_dispatcher(self) -> None:
        dispatcher = Dispatcher()
        initial_message_handlers = len(dispatcher.message.handlers)
        initial_callback_handlers = len(dispatcher.callback_query.handlers)

        search_ui.register_search_handlers(
            dispatcher,
            aggregate_callback=_noop_aggregate,
            default_service=SearchService(SEARCH_PROVIDERS),
            direct_lookup=DirectIdLookupService((DummyDirectSource(),)),
        )

        self.assertEqual(
            len(dispatcher.message.handlers) - initial_message_handlers,
            3,
        )
        self.assertEqual(
            len(dispatcher.callback_query.handlers) - initial_callback_handlers,
            4,
        )

    def test_search_ui_keeps_card_runtime_outside_search_module(self) -> None:
        self.assertFalse(hasattr(search_ui, "ANIME_SESSIONS"))
        self.assertFalse(hasattr(search_ui, "AGGREGATOR"))
        self.assertFalse(hasattr(search_ui, "build_dispatcher"))
        self.assertFalse(hasattr(search_ui, "run_bot"))


if __name__ == "__main__":
    unittest.main()
