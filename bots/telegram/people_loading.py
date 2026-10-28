from __future__ import annotations

import logging

from aiogram.types import Message

from bots.session_store import ExpiringSessionStore
from core.models import AggregatedAnime
from core.people import all_people
from localization import text
from services.app_context import get_app_context
from services.people_progress import PeopleLoadProgress, SourceLoadProgress


PEOPLE_LOADS: ExpiringSessionStore[PeopleLoadProgress] = ExpiringSessionStore(
    max_entries=400
)


def progress_key(token: str, section: str) -> str:
    return f"{token}:{section}"


def _service():
    return get_app_context().people_progress_service


def build_progress(anime: AggregatedAnime, section: str) -> PeopleLoadProgress:
    return _service().build_progress(anime, section)


def source_names(
    anime: AggregatedAnime,
    section: str,
    progress: PeopleLoadProgress | None,
) -> list[str]:
    return _service().source_names(anime, section, progress)


def scope_has_more(progress: PeopleLoadProgress, source: str | None) -> bool:
    return _service().scope_has_more(progress, source)


def scope_total_hint(
    anime: AggregatedAnime,
    section: str,
    progress: PeopleLoadProgress,
    source: str | None,
) -> int | None:
    return _service().scope_total_hint(anime, section, progress, source)


async def ensure_lazy_people(
    token: str,
    anime: AggregatedAnime,
    message: Message,
    section: str,
    *,
    locale: str,
    source: str | None = None,
    requested_page: int = 0,
) -> PeopleLoadProgress:
    key = progress_key(token, section)
    progress = PEOPLE_LOADS.get(key)
    created = progress is None
    service = _service()
    if progress is None:
        progress = service.build_progress(anime, section)
        PEOPLE_LOADS[key] = progress
    if not progress.sources:
        return progress

    if created:
        if not all_people(anime, section):
            loading_key = "loading_staff" if section == "staff" else "loading_voices"
            try:
                await message.edit_text(
                    text=text("people", loading_key, locale=locale),
                    reply_markup=None,
                )
            except Exception:
                logging.debug(
                    "Could not show progressive people loading state",
                    exc_info=True,
                )
        service.start_initial_batches(anime, section, progress)

    return await service.ensure(
        anime,
        section,
        progress,
        source=source,
        requested_page=requested_page,
    )


__all__ = [
    "PEOPLE_LOADS",
    "PeopleLoadProgress",
    "SourceLoadProgress",
    "build_progress",
    "ensure_lazy_people",
    "progress_key",
    "scope_has_more",
    "scope_total_hint",
    "source_names",
]
