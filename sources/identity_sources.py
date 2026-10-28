from __future__ import annotations

import logging

from core.identity import AnimeIdentity
from core.models import AnimeRecord, CharacterRecord, PersonCredit
from core.people_loading import PeopleBatch
from core.settings import AppSettings, SourceSettings
from sources.shikimori import _credits as _shikimori_credits
from sources.shikimori import _get_raw as _shikimori_get_raw
from sources.shikimori import _get_staff_raw as _shikimori_get_staff_raw
from sources.shikimori import _record as _shikimori_record
from sources.shikimori_people import _load_shikimori_characters, _load_shikimori_voices
from sources.shikimori_people_batches import load_shikimori_voices_batch


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
