from __future__ import annotations

import secrets
from dataclasses import dataclass

from bots.session_store import ExpiringSessionStore
from bots.telegram.card.constants import MAX_ANIME_SESSIONS
from core.models import AggregatedAnime


@dataclass(slots=True)
class AnimeCardSession:
    anime: AggregatedAnime
    owner_user_id: int


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
