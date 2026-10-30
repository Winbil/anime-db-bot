from __future__ import annotations

import unittest
from pathlib import Path

from core.settings import ROOT_DIR, AppSettings


class AppSettingsTests(unittest.TestCase):
    def test_typed_environment_parsing(self) -> None:
        settings = AppSettings.from_env(
            {
                "BOT_TOKEN": "token",
                "LOG_LEVEL": "debug",
                "LOG_STRUCTURED": "0",
                "LOG_REDACT_SECRETS": "0",
                "LOG_DIR": "logs-test",
                "LOG_MAX_BYTES": "12345",
                "LOG_BACKUPS": "2",
                "TELEGRAM_BOT_API_LOCAL": "true",
                "TELEGRAM_SESSION_TTL_SECONDS": "90",
                "ADMIN_TELEGRAM_USER_IDS": "1, 2;3\n2",
                "MAPPINGS_AUTO_UPDATE": "0",
                "MAPPINGS_CHECK_INTERVAL_SECONDS": "600",
                "MAL_CLIENT_ID": "mal-client",
                "UPSTREAM_RATE_LIMIT_ANILIST_PER_MINUTE": "77",
                "UPSTREAM_RATE_LIMIT_ANILIST_PEOPLE_PER_MINUTE": "13",
                "ANISEARCH_API_URL": "https://anisearch.example/api/",
                "ANISEARCH_APP_ID": "anisearch-app-id",
                "ANISEARCH_APP_SECRET": "anisearch-app-secret",
                "ANISEARCH_REQUEST_TIMEOUT_SECONDS": "17.5",
                "ANISEARCH_CACHE_TTL_SECONDS": "4321",
                "UPSTREAM_RATE_LIMIT_ANISEARCH_PER_MINUTE": "5",
                "SKIPDB_API_URL": "https://skipdb.example/api/",
                "SKIPDB_SITE_URL": "https://skipdb.example/",
                "SKIPDB_REQUEST_TIMEOUT_SECONDS": "12.5",
                "SKIPDB_CACHE_TTL_SECONDS": "1234",
                "UPSTREAM_RATE_LIMIT_SKIPDB_PER_MINUTE": "29",
                "ANIME_SKIP_API_URL": "https://anime-skip.example/api/",
                "ANIME_SKIP_CLIENT_ID": "anime-skip-client",
                "ANIME_SKIP_REQUEST_TIMEOUT_SECONDS": "11.5",
                "ANIME_SKIP_CACHE_TTL_SECONDS": "2345",
                "UPSTREAM_RATE_LIMIT_ANIME_SKIP_PER_MINUTE": "41",
                "SOURCE_HEALTH_FAILURE_THRESHOLD": "5",
                "SOURCE_HEALTH_COOLDOWN_SECONDS": "42.5",
            }
        )
        self.assertEqual(settings.logging.level, "DEBUG")
        self.assertFalse(settings.logging.structured)
        self.assertFalse(settings.logging.redact_secrets)
        self.assertEqual(settings.logging.directory, ROOT_DIR / Path("logs-test"))
        self.assertEqual(settings.logging.max_bytes, 12345)
        self.assertEqual(settings.logging.backups, 2)
        self.assertEqual(settings.telegram.bot_token, "token")
        self.assertTrue(settings.telegram.bot_api_local)
        self.assertEqual(settings.telegram.session_ttl_seconds, 90)
        self.assertEqual(settings.telegram.admin_user_ids, (1, 2, 3))
        self.assertFalse(settings.mappings.auto_update)
        self.assertEqual(settings.mappings.check_interval_seconds, 600.0)
        self.assertEqual(settings.sources.mal_client_id, "mal-client")
        self.assertEqual(settings.rate_limits.source_limit("anilist"), 77)
        self.assertEqual(settings.rate_limits.operation_limit("anilist", "people"), 13)
        self.assertEqual(
            settings.sources.anisearch_api_url, "https://anisearch.example/api"
        )
        self.assertEqual(settings.sources.anisearch_app_id, "anisearch-app-id")
        self.assertEqual(settings.sources.anisearch_app_secret, "anisearch-app-secret")
        self.assertEqual(settings.sources.anisearch_request_timeout_seconds, 17.5)
        self.assertEqual(settings.sources.anisearch_cache_ttl_seconds, 4321.0)
        self.assertEqual(settings.rate_limits.source_limit("anisearch"), 5)
        self.assertEqual(settings.sources.skipdb_api_url, "https://skipdb.example/api")
        self.assertEqual(settings.sources.skipdb_site_url, "https://skipdb.example")
        self.assertEqual(settings.sources.skipdb_request_timeout_seconds, 12.5)
        self.assertEqual(settings.sources.skipdb_cache_ttl_seconds, 1234.0)
        self.assertEqual(settings.rate_limits.source_limit("skipdb"), 29)
        self.assertEqual(
            settings.sources.anime_skip_api_url, "https://anime-skip.example/api"
        )
        self.assertEqual(settings.sources.anime_skip_client_id, "anime-skip-client")
        self.assertEqual(settings.sources.anime_skip_request_timeout_seconds, 11.5)
        self.assertEqual(settings.sources.anime_skip_cache_ttl_seconds, 2345.0)
        self.assertEqual(settings.rate_limits.source_limit("anime_skip"), 41)
        self.assertEqual(settings.source_health.failure_threshold, 5)
        self.assertEqual(settings.source_health.cooldown_seconds, 42.5)

    def test_relative_paths_are_rooted_at_project(self) -> None:
        settings = AppSettings.from_env(
            {
                "USER_SETTINGS_DB_PATH": "data/test-users.sqlite3",
                "BANS_DB_PATH": "data/test-bans.sqlite3",
                "MAPPINGS_DB_PATH": "data/test-mappings.sqlite3",
            }
        )
        self.assertEqual(
            settings.storage.user_settings_db_path,
            ROOT_DIR / Path("data/test-users.sqlite3"),
        )
        self.assertEqual(
            settings.storage.bans_db_path,
            ROOT_DIR / Path("data/test-bans.sqlite3"),
        )
        self.assertEqual(
            settings.mappings.db_path,
            ROOT_DIR / Path("data/test-mappings.sqlite3"),
        )

    def test_log_secret_redaction_defaults_to_enabled(self) -> None:
        settings = AppSettings.from_env({"BOT_TOKEN": "token"})
        self.assertTrue(settings.logging.redact_secrets)

    def test_anime_skip_rate_limit_cannot_exceed_server_ceiling(self) -> None:
        settings = AppSettings.from_env(
            {"UPSTREAM_RATE_LIMIT_ANIME_SKIP_PER_MINUTE": "999"}
        )
        self.assertEqual(settings.rate_limits.source_limit("anime_skip"), 60)

    def test_invalid_admin_id_fails_fast(self) -> None:
        with self.assertRaises(ValueError):
            AppSettings.from_env({"ADMIN_TELEGRAM_USER_IDS": "1,nope"})

    def test_required_bot_token_validation(self) -> None:
        with self.assertRaises(RuntimeError):
            AppSettings.from_env({}).require_bot_token()
        self.assertEqual(
            AppSettings.from_env({"BOT_TOKEN": "x"}).require_bot_token(), "x"
        )

    def test_only_settings_module_reads_environment_in_production(self) -> None:
        forbidden = (
            "AppSettings.from_env(",
            "os.getenv(",
            "os.environ",
            "load_dotenv(",
        )
        violations: list[str] = []
        settings_module = ROOT_DIR / "core" / "settings.py"
        for root_name in ("bots", "core", "mappings", "search", "services", "sources"):
            for path in (ROOT_DIR / root_name).rglob("*.py"):
                if path == settings_module:
                    continue
                source = path.read_text(encoding="utf-8")
                for token in forbidden:
                    if token in source:
                        violations.append(f"{path.relative_to(ROOT_DIR)}: {token}")

        self.assertEqual(violations, [])


if __name__ == "__main__":
    unittest.main()
