from __future__ import annotations

import unittest

from bots.telegram.card.service import SEARCH_SERVICE, SOURCES
from core.settings import AppSettings
from services.app_context import AppContext, activate_app_context, get_app_context


class AppContextTests(unittest.IsolatedAsyncioTestCase):
    def _settings(self) -> AppSettings:
        return AppSettings.from_env(
            {
                "BOT_TOKEN": "test-token",
                "MAL_CLIENT_ID": "",
                "ANIDB_CLIENT": "",
                "MAPPINGS_AUTO_UPDATE": "0",
            }
        )

    async def test_context_owns_runtime_services(self) -> None:
        context = AppContext.create(self._settings())
        self.assertTrue(context.search_providers)
        self.assertTrue(context.sources)
        self.assertTrue(context.search_service.provider_name)
        self.assertIsNotNone(context.people_progress_service)
        self.assertEqual(
            context.direct_lookup.source_keys,
            tuple(str(source.source_key) for source in context.sources),
        )
        await context.aclose()

    async def test_legacy_ui_surfaces_are_lazy_context_views(self) -> None:
        context = AppContext.create(self._settings())
        with self.assertRaises(RuntimeError):
            bool(SOURCES)

        with activate_app_context(context):
            self.assertIs(get_app_context(), context)
            self.assertTrue(SOURCES)
            self.assertEqual(
                SEARCH_SERVICE.provider_name, context.search_service.provider_name
            )

        with self.assertRaises(RuntimeError):
            get_app_context()
        await context.aclose()


if __name__ == "__main__":
    unittest.main()
