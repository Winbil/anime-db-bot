from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from core.settings import (
    ENV_CONFIG_FILES,
    ROOT_DIR,
    AppSettings,
    ConfigFileError,
    load_project_environment,
    project_env_files,
    project_env_values,
)


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
                "TELEGRAM_BOT_API_LOCAL_FILE_ROOT": "/srv/telegram-bot-api",
                "TELEGRAM_SESSION_TTL_SECONDS": "90",
                "ADMIN_TELEGRAM_USER_IDS": "1, 2;3\n2",
                "MAPPINGS_AUTO_UPDATE": "0",
                "MAPPINGS_CHECK_INTERVAL_SECONDS": "600",
                "MAPPINGS_WIKIDATA_CHECK_INTERVAL_HOURS": "72",
                "MAL_CLIENT_ID": "mal-client",
                "UPSTREAM_RATE_LIMIT_ANILIST_PER_MINUTE": "77",
                "UPSTREAM_RATE_LIMIT_ANILIST_PEOPLE_PER_MINUTE": "13",
                "KITSU_API_URL": "https://kitsu.example/api/edge/",
                "KITSU_REQUEST_TIMEOUT_SECONDS": "14.5",
                "KITSU_CACHE_TTL_SECONDS": "5432",
                "TRACE_MOE_API_KEY": "trace-key",
                "TRACE_MOE_REQUEST_TIMEOUT_SECONDS": "18.5",
                "WHATANIMEISTHIS_API_KEY": "what-key",
                "WHATANIMEISTHIS_API_DAILY_LIMIT": "0",
                "IMAGE_SEARCH_MAX_BYTES": "123456",
                "JIKAN_UPDATE_IDLE_WAIT_SECONDS": "123",
                "UPSTREAM_RATE_LIMIT_KITSU_PER_MINUTE": "44",
                "UPSTREAM_RATE_LIMIT_KITSU_EPISODES_PER_MINUTE": "33",
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
                "BAHAMUT_API_URL": "https://bahamut.example/api/",
                "BAHAMUT_REQUEST_TIMEOUT_SECONDS": "9.5",
                "BAHAMUT_FALLBACK_CACHE_TTL_SECONDS": "3456",
                "BAHA_ANIME_SKIP_DATA_URL": "https://baha.example/data.json",
                "BAHA_ANIME_SKIP_CACHE_TTL_SECONDS": "4567",
                "UPSTREAM_RATE_LIMIT_BAHAMUT_PER_MINUTE": "17",
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
        self.assertEqual(
            settings.telegram.bot_api_local_file_root,
            Path("/srv/telegram-bot-api"),
        )
        self.assertEqual(settings.telegram.session_ttl_seconds, 90)
        self.assertEqual(settings.telegram.admin_user_ids, (1, 2, 3))
        self.assertFalse(settings.mappings.auto_update)
        self.assertEqual(settings.mappings.check_interval_seconds, 600.0)
        self.assertEqual(settings.mappings.wikidata_check_interval_hours, 72.0)
        self.assertEqual(settings.sources.mal_client_id, "mal-client")
        self.assertEqual(settings.rate_limits.source_limit("anilist"), 77)
        self.assertEqual(settings.rate_limits.operation_limit("anilist", "people"), 13)
        self.assertEqual(
            settings.sources.kitsu_api_url, "https://kitsu.example/api/edge"
        )
        self.assertEqual(settings.sources.kitsu_request_timeout_seconds, 14.5)
        self.assertEqual(settings.sources.kitsu_cache_ttl_seconds, 5432.0)
        self.assertEqual(settings.sources.trace_moe_api_key, "trace-key")
        self.assertEqual(settings.sources.trace_moe_request_timeout_seconds, 18.5)
        self.assertEqual(settings.sources.whatanimeisthis_api_key, "what-key")
        self.assertEqual(settings.sources.whatanimeisthis_api_daily_limit, 0)
        self.assertEqual(settings.sources.image_search_max_bytes, 123456)
        self.assertEqual(settings.sources.jikan_update_idle_wait_seconds, 123)
        self.assertEqual(settings.rate_limits.source_limit("kitsu"), 44)
        self.assertEqual(settings.rate_limits.operation_limit("kitsu", "episodes"), 33)
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
        self.assertEqual(
            settings.sources.bahamut_api_url, "https://bahamut.example/api"
        )
        self.assertEqual(settings.sources.bahamut_request_timeout_seconds, 9.5)
        self.assertEqual(settings.sources.bahamut_fallback_cache_ttl_seconds, 3456.0)
        self.assertEqual(
            settings.sources.baha_anime_skip_data_url, "https://baha.example/data.json"
        )
        self.assertEqual(settings.sources.baha_anime_skip_cache_ttl_seconds, 4567.0)
        self.assertEqual(settings.rate_limits.source_limit("bahamut"), 17)
        self.assertEqual(settings.source_health.failure_threshold, 5)
        self.assertEqual(settings.source_health.cooldown_seconds, 42.5)

    def test_split_env_uses_fixed_files_and_process_environment_wins(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            split = root / ".env.d"
            split.mkdir()
            (split / "telegram.env").write_text(
                "BOT_TOKEN=file-token\nTELEGRAM_SESSION_TTL_SECONDS=91\n",
                encoding="utf-8",
            )
            (split / "runtime.env").write_text(
                "SEARCH_CACHE_MAX_ENTRIES=321\n",
                encoding="utf-8",
            )
            (split / "backup.env").write_text(
                "UNEXPECTED_BACKUP_KEY=must-not-load\n",
                encoding="utf-8",
            )
            environ = {"BOT_TOKEN": "process-token"}

            loaded = load_project_environment(root, environ)

            self.assertEqual(loaded["BOT_TOKEN"], "process-token")
            self.assertEqual(loaded["TELEGRAM_SESSION_TTL_SECONDS"], "91")
            self.assertEqual(loaded["SEARCH_CACHE_MAX_ENTRIES"], "321")
            self.assertNotIn("UNEXPECTED_BACKUP_KEY", loaded)
            self.assertEqual(
                [path.name for path in project_env_files(root)],
                ["telegram.env", "runtime.env"],
            )

    def test_duplicate_keys_across_project_env_files_fail_fast(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            split = root / ".env.d"
            split.mkdir()
            (split / "telegram.env").write_text("BOT_TOKEN=first\n", encoding="utf-8")
            (split / "sources.env").write_text("BOT_TOKEN=second\n", encoding="utf-8")

            with self.assertRaisesRegex(ConfigFileError, "Duplicate configuration key"):
                project_env_values(root)

    def test_duplicate_key_inside_one_project_env_file_fails_fast(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            split = root / ".env.d"
            split.mkdir()
            (split / "telegram.env").write_text(
                "BOT_TOKEN=first\nBOT_TOKEN=second\n", encoding="utf-8"
            )

            with self.assertRaisesRegex(ConfigFileError, "inside"):
                project_env_values(root)

    def test_legacy_env_remains_supported_during_migration(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / ".env").write_text(
                "BOT_TOKEN=legacy-token\nLOG_LEVEL=warning\n", encoding="utf-8"
            )

            self.assertEqual(
                project_env_values(root),
                {"BOT_TOKEN": "legacy-token", "LOG_LEVEL": "warning"},
            )

    def test_legacy_and_split_files_cannot_repeat_the_same_key(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / ".env").write_text("BOT_TOKEN=legacy\n", encoding="utf-8")
            split = root / ".env.d"
            split.mkdir()
            (split / "telegram.env").write_text("BOT_TOKEN=split\n", encoding="utf-8")

            with self.assertRaisesRegex(ConfigFileError, "Duplicate configuration key"):
                project_env_values(root)

    def test_split_example_directory_has_every_fixed_file_and_unique_keys(self) -> None:
        example_dir = ROOT_DIR / ".env.example.d"
        self.assertEqual(
            {path.name for path in example_dir.glob("*.env")},
            set(ENV_CONFIG_FILES),
        )
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            split = root / ".env.d"
            split.mkdir()
            for name in ENV_CONFIG_FILES:
                (split / name).write_text(
                    (example_dir / name).read_text(encoding="utf-8"),
                    encoding="utf-8",
                )
            values = project_env_values(root)
        self.assertEqual(len(values), 129)
        self.assertIn("BOT_TOKEN", values)
        self.assertIn("TELEGRAM_BOT_API_LOCAL_FILE_ROOT", values)
        self.assertIn("KITSU_API_URL", values)
        self.assertIn("TRACE_MOE_API_KEY", values)
        self.assertIn("WHATANIMEISTHIS_API_KEY", values)
        self.assertIn("IMAGE_SEARCH_DB_PATH", values)
        self.assertIn("ANIME_SKIP_CLIENT_ID", values)

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
