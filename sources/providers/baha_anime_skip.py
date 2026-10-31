from __future__ import annotations

import logging
from pathlib import Path
import sqlite3
from typing import Any

from core.episode_segments import EpisodeSegment
from core.identity import AnimeIdentity
from core.settings import SourceSettings, get_settings
from core.sqlite import managed_sqlite_connection
from mappings.resolver import MappingResolver

BAHA_ANIME_SKIP_DISPLAY_NAME = "Baha Anime Skip"
BAHA_ANIME_SKIP_BACKEND_KEY = "baha_anime_skip"


def _settings(settings: SourceSettings | None) -> SourceSettings:
    return settings or get_settings().sources


def _positive_integer(value: Any) -> int | None:
    text = str(value or "").strip()
    if not text.isdigit():
        return None
    parsed = int(text)
    return parsed if parsed > 0 else None


class BahaAnimeSkipSegmentSource:
    """Read the archived Baha Anime Skip dataset exclusively from local SQLite.

    Anime identity is resolved locally through a confirmed ``bahamut`` ID. The
    ID may already be present on ``AnimeIdentity`` or be enriched one hop from
    ``mappings.db``. Runtime lookups never contact Bahamut or the original Baha
    Anime Skip repository.
    """

    name = BAHA_ANIME_SKIP_DISPLAY_NAME
    display_name = BAHA_ANIME_SKIP_DISPLAY_NAME
    backend_key = BAHA_ANIME_SKIP_BACKEND_KEY

    def __init__(
        self,
        settings: SourceSettings | None = None,
        *,
        db_path: Path | str | None = None,
        mapping_resolver: MappingResolver | None = None,
    ) -> None:
        configured = _settings(settings)
        self._db_path = Path(db_path or configured.baha_anime_skip_db_path)
        self._mapping_resolver = mapping_resolver or MappingResolver()
        self._warned_missing_db = False
        self._warned_invalid_db = False

    @property
    def db_path(self) -> Path:
        return self._db_path

    def supports_identity(self, identity: AnimeIdentity) -> bool:
        if not self._db_path.is_file() or identity.is_empty():
            return False
        if _positive_integer(identity.get("bahamut")) is not None:
            return True
        return self._mapping_resolver.available

    def _resolve_anime_sn(self, identity: AnimeIdentity) -> str | None:
        direct = _positive_integer(identity.get("bahamut"))
        if direct is not None:
            return str(direct)
        mapped = self._mapping_resolver.resolve(identity)
        resolved = _positive_integer(mapped.get("bahamut"))
        return str(resolved) if resolved is not None else None

    def _segment_rows(
        self,
        anime_sn: str,
        episode_number: int,
    ) -> list[tuple[str, str, float, float, str]]:
        if not self._db_path.is_file():
            if not self._warned_missing_db:
                logging.warning(
                    "Baha Anime Skip local database is missing; source disabled",
                    extra={"path": str(self._db_path)},
                )
                self._warned_missing_db = True
            return []

        uri = f"file:{self._db_path.resolve().as_posix()}?mode=ro"
        try:
            with managed_sqlite_connection(
                sqlite3.connect(uri, uri=True, timeout=2.0)
            ) as conn:
                conn.execute("PRAGMA query_only=ON")
                rows = conn.execute(
                    """
                    SELECT video_sn, kind, start_seconds, end_seconds, raw_kind
                    FROM segments
                    WHERE anime_sn=? AND episode_number=?
                    ORDER BY start_seconds, kind, video_sn
                    """,
                    (anime_sn, episode_number),
                ).fetchall()
        except (sqlite3.DatabaseError, OSError):
            if not self._warned_invalid_db:
                logging.exception(
                    "Could not read Baha Anime Skip local database",
                    extra={"path": str(self._db_path)},
                )
                self._warned_invalid_db = True
            return []

        result: list[tuple[str, str, float, float, str]] = []
        for video_sn, kind, start_seconds, end_seconds, raw_kind in rows:
            try:
                start = float(start_seconds)
                end = float(end_seconds)
            except (TypeError, ValueError):
                continue
            if start < 0 or end <= start:
                continue
            result.append((str(video_sn), str(kind), start, end, str(raw_kind)))
        return result

    async def load_segments(
        self,
        identity: AnimeIdentity,
        episode_number: int,
        *,
        episode_length_seconds: int | None = None,
    ) -> list[EpisodeSegment]:
        wanted = int(episode_number)
        if wanted <= 0 or not self.supports_identity(identity):
            return []

        anime_sn = self._resolve_anime_sn(identity)
        if anime_sn is None:
            return []

        episode_length = (
            float(episode_length_seconds)
            if episode_length_seconds and episode_length_seconds > 0
            else None
        )
        return [
            EpisodeSegment(
                kind=kind,
                source=self.backend_key,
                start_seconds=start,
                end_seconds=end,
                source_segment_id=f"{video_sn}:{raw_kind}",
                raw_kind=raw_kind,
                episode_length_seconds=episode_length,
            )
            for video_sn, kind, start, end, raw_kind in self._segment_rows(
                anime_sn, wanted
            )
        ]
