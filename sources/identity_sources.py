from __future__ import annotations

import logging

from core.identity import AnimeIdentity
from core.models import AnimeRecord, CharacterRecord, PersonCredit
from core.people_loading import PeopleBatch
from core.settings import AppSettings, SourceSettings
from sources.anilist import _all_characters as _anilist_all_characters
from sources.anilist import _cached_people as _anilist_cached_people
from sources.anilist import _graphql as _anilist_graphql
from sources.anilist import _record as _anilist_record
from sources.anilist import AniListSource as LegacyAniListSource
from sources.shikimori import _credits as _shikimori_credits
from sources.shikimori import _get_raw as _shikimori_get_raw
from sources.shikimori import _get_staff_raw as _shikimori_get_staff_raw
from sources.shikimori import _record as _shikimori_record
from sources.shikimori_people import _load_shikimori_characters, _load_shikimori_voices
from sources.shikimori_people_batches import load_shikimori_voices_batch


ANILIST_BY_ID_QUERY = """
query AnimeDetailsById($id: Int!) {
  Media(id: $id, type: ANIME) {
    id
    idMal
    title { romaji english native }
    synonyms
    format
    status
    description(asHtml: false)
    startDate { year month day }
    endDate { year month day }
    season
    seasonYear
    episodes
    duration
    averageScore
    popularity
    favourites
    rankings { rank type year season allTime }
    stats {
      statusDistribution { status amount }
      scoreDistribution { score amount }
    }
    genres
    isAdult
    coverImage { extraLarge large medium }
    siteUrl
    nextAiringEpisode { airingAt episode }
    studios { nodes { name } }
  }
}
"""


class AniListIdentitySource:
    """AniList adapter that can start from AniList ID or MAL ID."""

    name = "AniList"

    def __init__(self, settings: SourceSettings | None = None) -> None:
        self._settings = settings or AppSettings.from_env().sources
        self._legacy = LegacyAniListSource(self._settings)

    async def get_details(self, identity: AnimeIdentity) -> AnimeRecord | None:
        anilist_id = str(identity.get("anilist") or "").strip()
        if anilist_id.isdigit():
            data = await _anilist_graphql(
                ANILIST_BY_ID_QUERY,
                {"id": int(anilist_id)},
                self._settings,
            )
            raw = data.get("Media")
            if not raw or str(raw.get("id") or "") != anilist_id:
                return None
            return _anilist_record(raw)

        mal_id = str(identity.get("mal") or "").strip()
        if not mal_id.isdigit():
            return None
        return await self._legacy.get_details(mal_id, identity.external_ids)

    async def load_characters(self, identity: AnimeIdentity) -> list[CharacterRecord]:
        media_id = str(identity.get("anilist") or "").strip()
        if not media_id.isdigit():
            return []
        return await _anilist_all_characters(int(media_id), self._settings)

    async def load_staff(self, identity: AnimeIdentity) -> list[PersonCredit]:
        media_id = str(identity.get("anilist") or "").strip()
        if not media_id.isdigit():
            return []
        return await _anilist_cached_people(media_id, "staff", self._settings)

    async def load_voices(self, identity: AnimeIdentity) -> list[PersonCredit]:
        media_id = str(identity.get("anilist") or "").strip()
        if not media_id.isdigit():
            return []
        return await _anilist_cached_people(media_id, "voices", self._settings)

    async def load_staff_batch(
        self,
        identity: AnimeIdentity,
        *,
        cursor: str | None = None,
        portrait_limit: int = 50,
    ) -> PeopleBatch:
        if cursor is not None:
            return PeopleBatch(complete=True)
        people = await self.load_staff(identity)
        return PeopleBatch(
            people=people,
            complete=True,
            total_count=len(people),
        )

    async def load_voices_batch(
        self,
        identity: AnimeIdentity,
        *,
        cursor: str | None = None,
        portrait_limit: int = 50,
    ) -> PeopleBatch:
        if cursor is not None:
            return PeopleBatch(complete=True)
        people = await self.load_voices(identity)
        return PeopleBatch(
            people=people,
            complete=True,
            total_count=len(people),
        )


class ShikimoriIdentitySource:
    """Shikimori adapter keyed only by its own ID, with no MAL requirement."""

    name = "Shikimori"

    def __init__(self, settings: SourceSettings | None = None) -> None:
        self._settings = settings or AppSettings.from_env().sources

    async def get_details(self, identity: AnimeIdentity) -> AnimeRecord | None:
        anime_id = str(identity.get("shikimori") or "").strip()
        if not anime_id.isdigit():
            return None

        raw = await _shikimori_get_raw(anime_id, self._settings)
        if not raw or str(raw.get("id") or "") != anime_id:
            return None
        record = _shikimori_record(raw, self._settings)
        logging.info(
            "Shikimori people for anime %s: staff=deferred, voices=deferred",
            anime_id,
        )
        return record

    async def load_characters(self, identity: AnimeIdentity) -> list[CharacterRecord]:
        anime_id = str(identity.get("shikimori") or "").strip()
        if not anime_id.isdigit():
            return []
        return await _load_shikimori_characters(anime_id, self._settings)

    async def load_staff(self, identity: AnimeIdentity) -> list[PersonCredit]:
        anime_id = str(identity.get("shikimori") or "").strip()
        if not anime_id.isdigit():
            return []
        raw = await _shikimori_get_staff_raw(anime_id, self._settings)
        if not raw or str(raw.get("id") or "") != anime_id:
            return []
        return _shikimori_credits(raw, voices=False)

    async def load_voices(self, identity: AnimeIdentity) -> list[PersonCredit]:
        anime_id = str(identity.get("shikimori") or "").strip()
        if not anime_id.isdigit():
            return []
        return await _load_shikimori_voices(anime_id, self._settings)

    async def load_staff_batch(
        self,
        identity: AnimeIdentity,
        *,
        cursor: str | None = None,
        portrait_limit: int = 50,
    ) -> PeopleBatch:
        if cursor is not None:
            return PeopleBatch(complete=True)
        people = await self.load_staff(identity)
        return PeopleBatch(
            people=people,
            complete=True,
            total_count=len(people),
        )

    async def load_voices_batch(
        self,
        identity: AnimeIdentity,
        *,
        cursor: str | None = None,
        portrait_limit: int = 50,
    ) -> PeopleBatch:
        anime_id = str(identity.get("shikimori") or "").strip()
        if not anime_id.isdigit():
            return PeopleBatch(complete=True)
        return await load_shikimori_voices_batch(
            anime_id,
            cursor=cursor,
            portrait_limit=portrait_limit,
            settings=self._settings,
        )
