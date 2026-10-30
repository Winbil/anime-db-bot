from __future__ import annotations

import unittest

from bots.telegram.card.runtime import service as card_service
from services.users import bans as bans_service
from services.runtime import rate_limits as rate_limits_service
from services.users import settings as user_settings_service
from core.identity import AnimeIdentity
from core.settings import AppSettings
from mappings import database as mapping_database_module
from mappings import resolver as mapping_resolver_module
from services.runtime.app_context import AppContext, activate_app_context, get_app_context
from services.users.bans import get_ban_store
from services.runtime.rate_limits import get_personal_rate_limiter, get_upstream_rate_limiter
from services.users.settings import get_user_settings_store


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
            context.episode_segment_service.available_backends(
                AnimeIdentity({"mal": "1"})
            ),
            ["aniskip"],
        )
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
        self.assertIs(context.aggregator.identity_resolver, context.identity_resolver)
        self.assertIs(
            context.direct_lookup.identity_resolver, context.identity_resolver
        )
        self.assertEqual(
            context.identity_resolver.mapping_resolver.path,
            context.settings.mappings.db_path,
        )
        await context.aclose()

    async def test_context_activation_exposes_owned_context(self) -> None:
        context = AppContext.create(self._settings())
        with self.assertRaises(RuntimeError):
            get_app_context()

        with activate_app_context(context):
            self.assertIs(get_app_context(), context)
            self.assertIs(get_user_settings_store(), context.user_settings_store)
            self.assertIs(get_ban_store(), context.ban_store)
            self.assertIs(get_personal_rate_limiter(), context.personal_rate_limiter)
            self.assertIs(get_upstream_rate_limiter(), context.upstream_rate_limiter)
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

    def test_runtime_state_modules_export_no_import_time_instances(self) -> None:
        for module, names in (
            (bans_service, ("BANS",)),
            (user_settings_service, ("USER_SETTINGS",)),
            (rate_limits_service, ("PERSONAL_RATE_LIMITER", "UPSTREAM_RATE_LIMITER")),
        ):
            for name in names:
                with self.subTest(module=module.__name__, name=name):
                    self.assertFalse(hasattr(module, name))

    def test_mapping_modules_export_no_runtime_singletons(self) -> None:
        self.assertFalse(hasattr(mapping_resolver_module, "MAPPING_RESOLVER"))
        self.assertFalse(hasattr(mapping_database_module, "MAPPING_DATABASE"))


if __name__ == "__main__":
    unittest.main()
