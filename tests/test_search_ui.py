from __future__ import annotations

import unittest

from bots.telegram import common as common_bot
from bots.telegram import search_ui
from core.models import SearchPage
from services.search import SearchService


class UnifiedSearchUiTests(unittest.TestCase):
    def test_default_search_keeps_anime_style_result_text(self) -> None:
        session = search_ui.SearchSession(
            query="slime",
            provider_keys=search_ui.DEFAULT_SEARCH_PROVIDER_KEYS,
            show_scope_label=False,
        )
        page = SearchPage(items=[], page=1, page_size=10, has_next=False)

        text = search_ui._result_text(session, page)

        self.assertIn("Результаты поиска по запросу «slime»", text)
        self.assertNotIn("Поиск только через:", text)

    def test_explicit_search_shows_selected_scope(self) -> None:
        session = search_ui.SearchSession(
            query="slime",
            provider_keys=("shikimori",),
            show_scope_label=True,
        )
        page = SearchPage(items=[], page=1, page_size=10, has_next=False)

        text = search_ui._result_text(session, page)

        self.assertIn("Поиск только через: Shikimori", text)
        self.assertIn("Запрос: «slime»", text)

    def test_scope_parser_normalizes_provider_order(self) -> None:
        self.assertEqual(
            search_ui._parse_scope("mal,shikimori"),
            ("shikimori", "mal"),
        )
        self.assertEqual(search_ui._parse_scope("ani"), ("anilist",))
        self.assertIsNone(search_ui._parse_scope("unknown-source"))

    def test_default_scope_reuses_shared_search_service(self) -> None:
        default_service = SearchService(common_bot.SEARCH_PROVIDERS)

        service = search_ui._service_for(
            search_ui.DEFAULT_SEARCH_PROVIDER_KEYS,
            default_service,
        )

        self.assertIs(service, default_service)

    def test_common_no_longer_contains_legacy_search_runtime(self) -> None:
        self.assertFalse(hasattr(common_bot, "SearchSession"))
        self.assertFalse(hasattr(common_bot, "SEARCH_SESSIONS"))
        self.assertFalse(hasattr(common_bot, "_get_search_page"))
        self.assertFalse(hasattr(common_bot, "build_dispatcher"))
        self.assertFalse(hasattr(common_bot, "run_bot"))


if __name__ == "__main__":
    unittest.main()
