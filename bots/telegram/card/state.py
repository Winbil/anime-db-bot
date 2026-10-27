from __future__ import annotations

import secrets
from dataclasses import dataclass, field

from bots.session_store import ExpiringSessionStore
from bots.telegram.card.constants import MAX_ANIME_SESSIONS
from core.models import AggregatedAnime, EpisodePage, EpisodeRecord, TrailerRecord


@dataclass(slots=True)
class AnimeCardSession:
    anime: AggregatedAnime
    owner_user_id: int
    episode_pages: dict[tuple[str, int], EpisodePage] = field(default_factory=dict)
    episode_details: dict[tuple[str, int], EpisodeRecord] = field(default_factory=dict)
    trailers_loaded: bool = False
    trailers_by_source: dict[str, list[TrailerRecord]] = field(default_factory=dict)
    trailer_errors: dict[str, str] = field(default_factory=dict)
    characters_loaded: bool = False
    character_errors: dict[str, str] = field(default_factory=dict)


ANIME_SESSIONS: ExpiringSessionStore[AnimeCardSession] = ExpiringSessionStore(
    max_entries=MAX_ANIME_SESSIONS,
)


def remember_anime(anime: AggregatedAnime, owner_user_id: int) -> str:
    token = secrets.token_urlsafe(6)
    ANIME_SESSIONS[token] = AnimeCardSession(
        anime=anime,
        owner_user_id=int(owner_user_id),
    )
    return token
