from __future__ import annotations

import secrets
from dataclasses import dataclass, field

from bots.session_store import ExpiringSessionStore
from bots.telegram.card.constants import MAX_ANIME_SESSIONS
from core.models import AggregatedAnime, EpisodePage, EpisodeRecord, TrailerRecord
from services.people_progress import PeopleLoadProgress

MAX_PEOPLE_LOADS = 400


@dataclass(slots=True)
class AnimeCardSession:
    anime: AggregatedAnime
    owner_user_id: int
    episode_pages: dict[tuple[str, int], EpisodePage] = field(default_factory=dict)
    episode_details: dict[tuple[str, int], EpisodeRecord] = field(default_factory=dict)
    trailers_loaded: bool = False
    trailers_by_source: dict[str, list[TrailerRecord]] = field(default_factory=dict)
    trailer_key_by_source: dict[str, str] = field(default_factory=dict)
    trailer_errors: dict[str, str] = field(default_factory=dict)
    characters_loaded: bool = False
    character_key_by_source: dict[str, str] = field(default_factory=dict)
    character_errors: dict[str, str] = field(default_factory=dict)


@dataclass(slots=True)
class TelegramCardState:
    """Per-bot-run Telegram card and progressive-people callback state."""

    anime_sessions: ExpiringSessionStore[AnimeCardSession]
    people_loads: ExpiringSessionStore[PeopleLoadProgress]

    @classmethod
    def create(cls, session_ttl_seconds: int) -> TelegramCardState:
        ttl = max(1, int(session_ttl_seconds))
        return cls(
            anime_sessions=ExpiringSessionStore(
                max_entries=MAX_ANIME_SESSIONS,
                ttl_seconds=ttl,
            ),
            people_loads=ExpiringSessionStore(
                max_entries=MAX_PEOPLE_LOADS,
                ttl_seconds=ttl,
            ),
        )

    def remember_anime(self, anime: AggregatedAnime, owner_user_id: int) -> str:
        token = secrets.token_urlsafe(6)
        self.anime_sessions[token] = AnimeCardSession(
            anime=anime,
            owner_user_id=int(owner_user_id),
        )
        return token
