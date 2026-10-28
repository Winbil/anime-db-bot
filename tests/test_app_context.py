from __future__ import annotations

import unittest

from bots.telegram.card import service as card_service
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
                "SOURCE_HEALTH_FAILURE_THRESHOLD": "7",
                "SOURCE_HEALTH_COOLDOWN_SECONDS": "45",
            }
        )

    async def test_context_owns_runtime_services(self) -> None:
        context = AppContext.create(self._settings())
        self.assertTrue(context.search_providers)
        self.assertEqual(
            tuple(context.search_provider_map.values()), context.search_providers
        )
        self.assertTrue(context.sources)
        self.assertTrue(context.search_service.provider_name)
        self.assertIsNotNone(context.people_progress_service)
        self.assertEqual(
            context.source_health.failure_threshold,
            context.settings.source_health.failure_threshold,
        )
        self.assertEqual(
            context.source_health.cooldown_seconds,
            context.settings.source_health.cooldown_seconds,
        )
        self.assertEqual(context.source_health.failure_threshold, 7)
        self.assertEqual(context.source_health.cooldown_seconds, 45.0)
        self.assertEqual(
            context.direct_lookup.source_keys,
            tuple(str(source.source_key) for source in context.sources),
        )
        await context.aclose()

    async def test_context_activation_exposes_owned_context(self) -> None:
        context = AppContext.create(self._settings())
        with self.assertRaises(RuntimeError):
            get_app_context()

        with activate_app_context(context):
            self.assertIs(get_app_context(), context)
            self.assertTrue(context.sources)
            self.assertTrue(context.search_service.provider_name)

        with self.assertRaises(RuntimeError):
            get_app_context()
        await context.aclose()

    def test_card_service_exports_no_runtime_service_proxies(self) -> None:
        for name in (
            "SEARCH_PROVIDERS",
            "SEARCH_SERVICE",
            "SOURCES",
            "AGGREGATOR",
            "CHARACTER_SERVICE",
            "EPISODE_SERVICE",
            "TRAILER_SERVICE",
            "_ContextAttributeProxy",
        ):
            with self.subTest(name=name):
                self.assertFalse(hasattr(card_service, name))


if __name__ == "__main__":
    unittest.main()
