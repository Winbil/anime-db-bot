from __future__ import annotations

import asyncio
import logging

from aiogram.types import Message

from bots.telegram.card.runtime.state import TelegramCardState
from core.models import AggregatedAnime
from localization import text
from services.media.people import PeopleLoadProgress, SourceLoadProgress
from services.runtime.app_context import get_app_context

_BACKGROUND_PEOPLE_PREFETCH_TASKS: set[asyncio.Task[None]] = set()


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


def scope_has_running(progress: PeopleLoadProgress, source: str | None) -> bool:
    return _service().scope_has_running(progress, source)


def scope_manifest_complete(progress: PeopleLoadProgress, source: str | None) -> bool:
    return _service().scope_manifest_complete(progress, source)


def scope_total_hint(
    anime: AggregatedAnime,
    section: str,
    progress: PeopleLoadProgress,
    source: str | None,
) -> int | None:
    return _service().scope_total_hint(anime, section, progress, source)


async def settle_started_batches(
    progress: PeopleLoadProgress, source: str | None = None
) -> None:
    await _service().settle_started_batches(progress, source)


def _track_prefetch(task: asyncio.Task[None]) -> None:
    _BACKGROUND_PEOPLE_PREFETCH_TASKS.add(task)
    task.add_done_callback(_BACKGROUND_PEOPLE_PREFETCH_TASKS.discard)


async def _prefetch_section(
    anime: AggregatedAnime,
    section: str,
    progress: PeopleLoadProgress,
) -> None:
    try:
        await _service().prefetch(anime, section, progress)
    except asyncio.CancelledError:
        raise
    except Exception:
        logging.exception("People manifest prefetch failed for %s", section)


def start_people_prefetch(
    state: TelegramCardState,
    token: str,
    anime: AggregatedAnime,
) -> None:
    """Start lightweight staff/voice manifests before the user opens the sections."""
    service = _service()
    for section in ("staff", "voices"):
        key = progress_key(token, section)
        progress = state.people_loads.get(key)
        if progress is None:
            progress = service.build_progress(anime, section)
            state.people_loads[key] = progress
        if not progress.sources:
            continue
        service.start_manifest_loads(anime, section, progress)
        _track_prefetch(
            asyncio.create_task(_prefetch_section(anime, section, progress))
        )


async def ensure_lazy_people(
    state: TelegramCardState,
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
    progress = state.people_loads.get(key)
    service = _service()
    if progress is None:
        progress = service.build_progress(anime, section)
        state.people_loads[key] = progress
    if not progress.sources:
        return progress

    if not service.scope_manifest_complete(progress, None):
        loading_key = "loading_staff" if section == "staff" else "loading_voices"
        try:
            await message.edit_text(
                text=text("people", loading_key, locale=locale),
                reply_markup=None,
            )
        except Exception:
            logging.debug(
                "Could not show people manifest loading state",
                exc_info=True,
            )

    return await service.ensure(
        anime,
        section,
        progress,
        source=source,
        requested_page=requested_page,
    )


__all__ = [
    "PeopleLoadProgress",
    "SourceLoadProgress",
    "build_progress",
    "ensure_lazy_people",
    "progress_key",
    "scope_has_more",
    "scope_has_running",
    "scope_manifest_complete",
    "scope_total_hint",
    "settle_started_batches",
    "source_names",
    "start_people_prefetch",
]
