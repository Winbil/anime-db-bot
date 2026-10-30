from __future__ import annotations

import os
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Mapping, MutableMapping

from dotenv import dotenv_values

ROOT_DIR = Path(__file__).resolve().parents[1]
ENV_CONFIG_FILES = (
    "telegram.env",
    "sources.env",
    "timestamps.env",
    "rate-limits.env",
    "mappings.env",
    "storage.env",
    "logging.env",
    "runtime.env",
)
_ADMIN_SPLIT_RE = re.compile(r"[\s,;]+")
_ENV_KEY_RE = re.compile(r"^[ \t]*(?:export[ \t]+)?([A-Za-z_][A-Za-z0-9_]*)[ \t]*=")


class ConfigFileError(RuntimeError):
    """Raised when project environment files are ambiguous or malformed."""


def _declared_env_keys(path: Path) -> tuple[str, ...]:
    keys: list[str] = []
    seen: set[str] = set()
    for line_number, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), 1
    ):
        match = _ENV_KEY_RE.match(line)
        if match is None:
            continue
        key = match.group(1)
        if key in seen:
            raise ConfigFileError(
                f"Duplicate configuration key {key!r} inside {path} "
                f"at line {line_number}."
            )
        seen.add(key)
        keys.append(key)
    return tuple(keys)


def project_env_files(root_dir: Path = ROOT_DIR) -> tuple[Path, ...]:
    """Return only the explicitly supported project configuration files."""
    paths: list[Path] = []
    legacy = root_dir / ".env"
    if legacy.is_file():
        paths.append(legacy)
    split_dir = root_dir / ".env.d"
    paths.extend(
        path for name in ENV_CONFIG_FILES if (path := split_dir / name).is_file()
    )
    return tuple(paths)


def project_env_values(root_dir: Path = ROOT_DIR) -> dict[str, str]:
    """Load project config with duplicate-key rejection across all config files."""
    merged: dict[str, str] = {}
    origins: dict[str, Path] = {}
    for path in project_env_files(root_dir):
        keys = _declared_env_keys(path)
        parsed = dotenv_values(path)
        for key in keys:
            previous = origins.get(key)
            if previous is not None:
                raise ConfigFileError(
                    f"Duplicate configuration key {key!r} in {previous} and {path}. "
                    "Keep each project setting in exactly one config file."
                )
            value = parsed.get(key)
            merged[key] = "" if value is None else str(value)
            origins[key] = path
    return merged


def load_project_environment(
    root_dir: Path = ROOT_DIR,
    environ: MutableMapping[str, str] | None = None,
) -> MutableMapping[str, str]:
    """Load project files without overriding real process environment variables."""
    target = os.environ if environ is None else environ
    for key, value in project_env_values(root_dir).items():
        target.setdefault(key, value)
    return target


load_project_environment()


def _raw(env: Mapping[str, str], name: str, default: str = "") -> str:
    return str(env.get(name, default) or "").strip()


def _bool(env: Mapping[str, str], name: str, default: bool) -> bool:
    value = _raw(env, name, "1" if default else "0").casefold()
    return value not in {"", "0", "false", "no", "off"}


def _int(env: Mapping[str, str], name: str, default: int, minimum: int = 0) -> int:
    try:
        return max(minimum, int(_raw(env, name, str(default))))
    except ValueError:
        return max(minimum, int(default))


def _float(
    env: Mapping[str, str],
    name: str,
    default: float,
    minimum: float = 0.0,
) -> float:
    try:
        return max(minimum, float(_raw(env, name, str(default))))
    except ValueError:
        return max(minimum, float(default))


def _path(env: Mapping[str, str], name: str, default: str) -> Path:
    value = _raw(env, name, default) or default
    path = Path(value)
    return path if path.is_absolute() else ROOT_DIR / path


def _admin_ids(value: str) -> tuple[int, ...]:
    result: list[int] = []
    seen: set[int] = set()
    for token in _ADMIN_SPLIT_RE.split((value or "").strip()):
        if not token:
            continue
        if not token.isdecimal() or int(token) <= 0:
            raise ValueError(
                "ADMIN_TELEGRAM_USER_IDS must contain positive numeric account IDs; "
                f"got {token!r}"
            )
        user_id = int(token)
        if user_id not in seen:
            seen.add(user_id)
            result.append(user_id)
    return tuple(result)


@dataclass(frozen=True, slots=True)
class LoggingSettings:
    level: str
    structured: bool
    redact_secrets: bool
    directory: Path
    max_bytes: int
    backups: int


@dataclass(frozen=True, slots=True)
class TelegramSettings:
    bot_token: str
    bot_api_url: str
    bot_api_local: bool
    session_ttl_seconds: int
    anime_input_ttl_seconds: int
    admin_user_ids: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class StorageSettings:
    user_settings_db_path: Path
    bans_db_path: Path


@dataclass(frozen=True, slots=True)
class SearchSettings:
    cache_ttl_seconds: float
    cache_max_entries: int
    collection_page_size: int
    collection_max_pages: int
    collection_max_items: int
    relevance_threshold: int
    irrelevant_tail_pages: int
    expansion_max_seeds: int
    expansion_max_queries: int
    expansion_max_pages: int


@dataclass(frozen=True, slots=True)
class MappingSettings:
    db_path: Path
    auto_update: bool
    update_max_age_hours: float
    wikidata_check_interval_hours: float
    check_interval_seconds: float
    request_timeout_seconds: float
    keep_downloads: bool
    keep_previous: bool


@dataclass(frozen=True, slots=True)
class SourceSettings:
    mal_client_id: str
    mal_api_url: str
    jikan_api_url: str
    jikan_port: int
    jikan_request_timeout_seconds: float
    jikan_supplement_cache_ttl_seconds: float
    jikan_people_cache_ttl_seconds: float
    jikan_update_idle_wait_seconds: int
    anidb_client: str
    anidb_client_version: int
    anidb_http_api_url: str
    anidb_request_timeout_seconds: float
    anidb_cache_dir: Path
    anidb_cache_ttl_seconds: float
    anisearch_api_url: str
    anisearch_app_id: str
    anisearch_app_secret: str
    anisearch_request_timeout_seconds: float
    anisearch_cache_ttl_seconds: float
    skipdb_api_url: str
    skipdb_site_url: str
    skipdb_request_timeout_seconds: float
    skipdb_cache_ttl_seconds: float
    anime_skip_api_url: str
    anime_skip_client_id: str
    anime_skip_request_timeout_seconds: float
    anime_skip_cache_ttl_seconds: float
    bahamut_api_url: str
    bahamut_request_timeout_seconds: float
    bahamut_fallback_cache_ttl_seconds: float
    baha_anime_skip_data_url: str
    baha_anime_skip_cache_ttl_seconds: float
    shikimori_api_url: str
    shikimori_site_url: str
    shikimori_people_cache_ttl_seconds: float
    shikimori_people_character_batch_size: int
    shikimori_rest_min_interval_seconds: float
    people_portrait_batch_size: int
    anilist_api_url: str
    anilist_access_token: str
    anilist_people_max_pages: int
    anilist_people_cache_ttl_seconds: float
    kitsu_api_url: str
    kitsu_request_timeout_seconds: float
    kitsu_cache_ttl_seconds: float


@dataclass(frozen=True, slots=True)
class SourceHealthSettings:
    failure_threshold: int
    cooldown_seconds: float


@dataclass(frozen=True, slots=True)
class RateLimitSettings:
    user_per_minute: int
    user_per_hour: int
    upstream_default_per_minute: int
    upstream_per_source: dict[str, int]
    upstream_per_operation: dict[tuple[str, str], int]

    def source_limit(self, source: str) -> int:
        return self.upstream_per_source.get(
            (source or "").strip().casefold(),
            self.upstream_default_per_minute,
        )

    def operation_limit(self, source: str, operation: str) -> int | None:
        return self.upstream_per_operation.get(
            ((source or "").strip().casefold(), (operation or "").strip().casefold())
        )


@dataclass(frozen=True, slots=True)
class AppSettings:
    logging: LoggingSettings
    telegram: TelegramSettings
    storage: StorageSettings
    search: SearchSettings
    mappings: MappingSettings
    sources: SourceSettings
    source_health: SourceHealthSettings
    rate_limits: RateLimitSettings

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "AppSettings":
        values: Mapping[str, str] = os.environ if env is None else env

        upstream_default = _int(
            values,
            "UPSTREAM_RATE_LIMIT_DEFAULT_PER_MINUTE",
            120,
            1,
        )
        source_defaults = {
            "anilist": 80,
            "kitsu": 60,
            "shikimori": 240,
            "mal": 120,
            "jikan": 30,
            "anidb": 20,
            "anisearch": 12,
            "skipdb": 30,
            "anime_skip": 60,
            "bahamut": 30,
            "baha_anime_skip": 20,
        }
        upstream_per_source = {
            source: _int(
                values,
                f"UPSTREAM_RATE_LIMIT_{source.upper()}_PER_MINUTE",
                default,
                1,
            )
            for source, default in source_defaults.items()
        }
        # Anime Skip client IDs have a hard server-side ceiling of 60 RPM. Local
        # configuration may reserve headroom, but must never raise that ceiling.
        upstream_per_source["anime_skip"] = min(60, upstream_per_source["anime_skip"])
        operation_defaults = {
            ("anilist", "people"): 20,
            ("kitsu", "search"): 60,
            ("kitsu", "episodes"): 60,
            ("kitsu", "trailers"): 60,
            ("shikimori", "people"): 60,
            ("jikan", "metadata"): 20,
            ("jikan", "people"): 15,
            ("jikan", "trailers"): 15,
            ("jikan", "episodes"): 20,
            ("anidb", "episodes"): 20,
            ("anisearch", "people"): 12,
            ("anisearch", "episodes"): 12,
            ("skipdb", "identity"): 30,
            ("skipdb", "episodes"): 30,
            ("skipdb", "episode"): 120,
            ("anime_skip", "episode_segments"): 60,
            ("bahamut", "identity"): 20,
            ("bahamut", "episodes"): 30,
            ("baha_anime_skip", "episode_segments"): 20,
        }
        upstream_per_operation = {
            (source, operation): _int(
                values,
                f"UPSTREAM_RATE_LIMIT_{source.upper()}_{operation.upper()}_PER_MINUTE",
                default,
                1,
            )
            for (source, operation), default in operation_defaults.items()
        }

        return cls(
            logging=LoggingSettings(
                level=(_raw(values, "LOG_LEVEL", "INFO") or "INFO").upper(),
                structured=_bool(values, "LOG_STRUCTURED", True),
                redact_secrets=_bool(values, "LOG_REDACT_SECRETS", True),
                directory=_path(values, "LOG_DIR", "logs"),
                max_bytes=_int(values, "LOG_MAX_BYTES", 10485760, 1),
                backups=_int(values, "LOG_BACKUPS", 5, 0),
            ),
            telegram=TelegramSettings(
                bot_token=_raw(values, "BOT_TOKEN"),
                bot_api_url=_raw(values, "TELEGRAM_BOT_API_URL"),
                bot_api_local=_bool(values, "TELEGRAM_BOT_API_LOCAL", False),
                session_ttl_seconds=_int(
                    values, "TELEGRAM_SESSION_TTL_SECONDS", 3600, 30
                ),
                anime_input_ttl_seconds=_int(
                    values, "ANIME_INPUT_TTL_SECONDS", 300, 30
                ),
                admin_user_ids=_admin_ids(_raw(values, "ADMIN_TELEGRAM_USER_IDS")),
            ),
            storage=StorageSettings(
                user_settings_db_path=_path(
                    values,
                    "USER_SETTINGS_DB_PATH",
                    "data/user_settings.sqlite3",
                ),
                bans_db_path=_path(values, "BANS_DB_PATH", "data/bans.sqlite3"),
            ),
            search=SearchSettings(
                cache_ttl_seconds=_float(values, "SEARCH_CACHE_TTL_SECONDS", 21600.0),
                cache_max_entries=_int(values, "SEARCH_CACHE_MAX_ENTRIES", 500, 1),
                collection_page_size=_int(values, "SEARCH_COLLECTION_PAGE_SIZE", 20, 1),
                collection_max_pages=_int(values, "SEARCH_COLLECTION_MAX_PAGES", 4, 1),
                collection_max_items=_int(
                    values, "SEARCH_COLLECTION_MAX_ITEMS", 120, 1
                ),
                relevance_threshold=_int(values, "SEARCH_RELEVANCE_THRESHOLD", 55, 0),
                irrelevant_tail_pages=_int(
                    values, "SEARCH_IRRELEVANT_TAIL_PAGES", 1, 1
                ),
                expansion_max_seeds=_int(values, "SEARCH_EXPANSION_MAX_SEEDS", 1, 0),
                expansion_max_queries=_int(
                    values, "SEARCH_EXPANSION_MAX_QUERIES", 1, 0
                ),
                expansion_max_pages=_int(values, "SEARCH_EXPANSION_MAX_PAGES", 2, 1),
            ),
            mappings=MappingSettings(
                db_path=_path(values, "MAPPINGS_DB_PATH", "data/mappings/mappings.db"),
                auto_update=_bool(values, "MAPPINGS_AUTO_UPDATE", True),
                update_max_age_hours=_float(
                    values,
                    "MAPPINGS_UPDATE_MAX_AGE_HOURS",
                    24.0,
                    0.25,
                ),
                wikidata_check_interval_hours=_float(
                    values,
                    "MAPPINGS_WIKIDATA_CHECK_INTERVAL_HOURS",
                    168.0,
                    1.0,
                ),
                check_interval_seconds=_float(
                    values,
                    "MAPPINGS_CHECK_INTERVAL_SECONDS",
                    3600.0,
                    300.0,
                ),
                request_timeout_seconds=_float(
                    values,
                    "MAPPINGS_REQUEST_TIMEOUT_SECONDS",
                    300.0,
                    30.0,
                ),
                keep_downloads=_bool(values, "MAPPINGS_KEEP_DOWNLOADS", False),
                keep_previous=_bool(values, "MAPPINGS_KEEP_PREVIOUS", True),
            ),
            sources=SourceSettings(
                mal_client_id=_raw(values, "MAL_CLIENT_ID"),
                mal_api_url=_raw(
                    values,
                    "MAL_API_URL",
                    "https://api.myanimelist.net/v2",
                ).rstrip("/"),
                jikan_api_url=_raw(
                    values,
                    "JIKAN_API_URL",
                    "http://127.0.0.1:8091",
                ).rstrip("/"),
                jikan_port=_int(values, "JIKAN_PORT", 8091, 1),
                jikan_request_timeout_seconds=_float(
                    values,
                    "JIKAN_REQUEST_TIMEOUT_SECONDS",
                    45.0,
                    5.0,
                ),
                jikan_supplement_cache_ttl_seconds=_float(
                    values,
                    "JIKAN_SUPPLEMENT_CACHE_TTL_SECONDS",
                    21600.0,
                ),
                jikan_people_cache_ttl_seconds=_float(
                    values,
                    "JIKAN_PEOPLE_CACHE_TTL_SECONDS",
                    21600.0,
                ),
                jikan_update_idle_wait_seconds=_int(
                    values,
                    "JIKAN_UPDATE_IDLE_WAIT_SECONDS",
                    300,
                    30,
                ),
                anidb_client=_raw(values, "ANIDB_CLIENT"),
                anidb_client_version=_int(values, "ANIDB_CLIENT_VERSION", 1, 1),
                anidb_http_api_url=_raw(
                    values,
                    "ANIDB_HTTP_API_URL",
                    "http://api.anidb.net:9001/httpapi",
                ),
                anidb_request_timeout_seconds=_float(
                    values,
                    "ANIDB_REQUEST_TIMEOUT_SECONDS",
                    45.0,
                    10.0,
                ),
                anidb_cache_dir=_path(values, "ANIDB_CACHE_DIR", "data/anidb"),
                anidb_cache_ttl_seconds=_float(
                    values,
                    "ANIDB_CACHE_TTL_SECONDS",
                    86400.0,
                ),
                anisearch_api_url=_raw(
                    values,
                    "ANISEARCH_API_URL",
                    "https://api.anisearch.com",
                ).rstrip("/"),
                anisearch_app_id=_raw(values, "ANISEARCH_APP_ID"),
                anisearch_app_secret=_raw(values, "ANISEARCH_APP_SECRET"),
                anisearch_request_timeout_seconds=_float(
                    values,
                    "ANISEARCH_REQUEST_TIMEOUT_SECONDS",
                    30.0,
                    3.0,
                ),
                anisearch_cache_ttl_seconds=_float(
                    values,
                    "ANISEARCH_CACHE_TTL_SECONDS",
                    21600.0,
                ),
                skipdb_api_url=_raw(
                    values,
                    "SKIPDB_API_URL",
                    "https://skipdb.tv",
                ).rstrip("/"),
                skipdb_site_url=_raw(
                    values,
                    "SKIPDB_SITE_URL",
                    "https://skipdb.tv",
                ).rstrip("/"),
                skipdb_request_timeout_seconds=_float(
                    values,
                    "SKIPDB_REQUEST_TIMEOUT_SECONDS",
                    20.0,
                    3.0,
                ),
                skipdb_cache_ttl_seconds=_float(
                    values,
                    "SKIPDB_CACHE_TTL_SECONDS",
                    21600.0,
                ),
                anime_skip_api_url=_raw(
                    values,
                    "ANIME_SKIP_API_URL",
                    "https://anime-skip.com/api",
                ).rstrip("/"),
                anime_skip_client_id=_raw(values, "ANIME_SKIP_CLIENT_ID"),
                anime_skip_request_timeout_seconds=_float(
                    values,
                    "ANIME_SKIP_REQUEST_TIMEOUT_SECONDS",
                    20.0,
                    3.0,
                ),
                anime_skip_cache_ttl_seconds=_float(
                    values,
                    "ANIME_SKIP_CACHE_TTL_SECONDS",
                    21600.0,
                ),
                bahamut_api_url=_raw(
                    values,
                    "BAHAMUT_API_URL",
                    "https://api.gamer.com.tw/mobile_app/anime",
                ).rstrip("/"),
                bahamut_request_timeout_seconds=_float(
                    values,
                    "BAHAMUT_REQUEST_TIMEOUT_SECONDS",
                    20.0,
                    3.0,
                ),
                bahamut_fallback_cache_ttl_seconds=_float(
                    values,
                    "BAHAMUT_FALLBACK_CACHE_TTL_SECONDS",
                    86400.0,
                ),
                baha_anime_skip_data_url=_raw(
                    values,
                    "BAHA_ANIME_SKIP_DATA_URL",
                    "https://raw.githubusercontent.com/JacobLinCool/baha-anime-skip/main/packages/baha-anime-skip-db/data.json",
                ),
                baha_anime_skip_cache_ttl_seconds=_float(
                    values,
                    "BAHA_ANIME_SKIP_CACHE_TTL_SECONDS",
                    21600.0,
                ),
                shikimori_api_url=_raw(
                    values,
                    "SHIKIMORI_API_URL",
                    "https://shikimori.io/api/graphql",
                ),
                shikimori_site_url=_raw(
                    values,
                    "SHIKIMORI_SITE_URL",
                    "https://shikimori.io",
                ).rstrip("/"),
                shikimori_people_cache_ttl_seconds=_float(
                    values,
                    "SHIKIMORI_PEOPLE_CACHE_TTL_SECONDS",
                    21600.0,
                ),
                shikimori_people_character_batch_size=_int(
                    values,
                    "SHIKIMORI_PEOPLE_CHARACTER_BATCH_SIZE",
                    8,
                    1,
                ),
                shikimori_rest_min_interval_seconds=_float(
                    values,
                    "SHIKIMORI_REST_MIN_INTERVAL_SECONDS",
                    0.24,
                ),
                people_portrait_batch_size=_int(
                    values,
                    "PEOPLE_PORTRAIT_BATCH_SIZE",
                    50,
                    1,
                ),
                anilist_api_url=_raw(
                    values,
                    "ANILIST_API_URL",
                    "https://graphql.anilist.co",
                ),
                anilist_access_token=_raw(values, "ANILIST_ACCESS_TOKEN"),
                anilist_people_max_pages=_int(
                    values,
                    "ANILIST_PEOPLE_MAX_PAGES",
                    4,
                    1,
                ),
                anilist_people_cache_ttl_seconds=_float(
                    values,
                    "ANILIST_PEOPLE_CACHE_TTL_SECONDS",
                    21600.0,
                ),
                kitsu_api_url=_raw(
                    values,
                    "KITSU_API_URL",
                    "https://kitsu.io/api/edge",
                ).rstrip("/"),
                kitsu_request_timeout_seconds=_float(
                    values,
                    "KITSU_REQUEST_TIMEOUT_SECONDS",
                    20.0,
                    3.0,
                ),
                kitsu_cache_ttl_seconds=_float(
                    values,
                    "KITSU_CACHE_TTL_SECONDS",
                    21600.0,
                ),
            ),
            source_health=SourceHealthSettings(
                failure_threshold=_int(
                    values,
                    "SOURCE_HEALTH_FAILURE_THRESHOLD",
                    3,
                    1,
                ),
                cooldown_seconds=_float(
                    values,
                    "SOURCE_HEALTH_COOLDOWN_SECONDS",
                    30.0,
                    1.0,
                ),
            ),
            rate_limits=RateLimitSettings(
                user_per_minute=_int(values, "USER_RATE_LIMIT_PER_MINUTE", 50, 1),
                user_per_hour=_int(values, "USER_RATE_LIMIT_PER_HOUR", 1000, 1),
                upstream_default_per_minute=upstream_default,
                upstream_per_source=upstream_per_source,
                upstream_per_operation=upstream_per_operation,
            ),
        )

    def require_bot_token(self) -> str:
        if not self.telegram.bot_token:
            raise RuntimeError(
                "BOT_TOKEN is empty. Add it to .env.d/telegram.env (or legacy .env) before starting the bot."
            )
        return self.telegram.bot_token


@lru_cache(maxsize=1)
def get_settings() -> AppSettings:
    return AppSettings.from_env()


def reload_settings() -> AppSettings:
    get_settings.cache_clear()
    return get_settings()
