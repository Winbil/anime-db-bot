from __future__ import annotations

import secrets

from bots.session_store import ExpiringSessionStore
from bots.telegram.card.constants import MAX_ANIME_SESSIONS
from core.models import AggregatedAnime

ANIME_SESSIONS: ExpiringSessionStore[AggregatedAnime] = ExpiringSessionStore(
    max_entries=MAX_ANIME_SESSIONS,
)


def remember_anime(anime: AggregatedAnime) -> str:
    token = secrets.token_urlsafe(6)
    ANIME_SESSIONS[token] = anime
    return token
