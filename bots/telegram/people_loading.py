from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any

from aiogram.types import Message

from bots.session_store import ExpiringSessionStore
from bots.telegram.card.service import AGGREGATOR, SOURCES
from bots.telegram.people_views import (
    _all_people,
    _people_for_scope,
    _people_state,
    _portrait_urls,
    _section_mapping,
    _sources_with_portraits,
)
from core.models import AggregatedAnime, PersonCredit
from core.people_loading import PeopleBatch
from core.settings import get_settings
from localization import text


@dataclass(slots=True)
class SourceLoadProgress:
    source: Any
    cursor: str | None = None
    complete: bool = False
    total_count: int | None = None
    task: asyncio.Task[bool] | None = None


@dataclass(slots=True)
class PeopleLoadProgress:
    sources: dict[str, SourceLoadProgress] = field(default_factory=dict)


PEOPLE_LOADS: ExpiringSessionStore[PeopleLoadProgress] = ExpiringSessionStore(max_entries=400)


def _portrait_batch_size() -> int:
    return max(1, min(get_settings().sources.people_portrait_batch_size, 200))


def progress_key(token: str, section: str) -> str:
    return f"{token}:{section}"


def build_progress(anime: AggregatedAnime, section: str) -> PeopleLoadProgress:
    identity = anime.identity
    mapping = _section_mapping(anime, section)
    progress = PeopleLoadProgress()
    for source in SOURCES:
        source_key = str(getattr(source, "source_key", "") or "").strip().casefold()
        if source_key and not identity.has(source_key):
            continue
        batch_loader = getattr(source, f"load_{section}_batch", None)
        full_loader = getattr(source, f"load_{section}", None)
        if not callable(batch_loader) and not callable(full_loader):
            continue
        already_loaded = source.name in mapping
        progress.sources[source.name] = SourceLoadProgress(
            source=source,
            complete=already_loaded,
            total_count=len(mapping.get(source.name, [])) if already_loaded else None,
        )
    return progress


def source_names(
    anime: AggregatedAnime,
    section: str,
    progress: PeopleLoadProgress | None,
) -> list[str]:
    if progress is not None and progress.sources:
        return list(progress.sources)
    return _sources_with_portraits(anime, section)


def _scope_progresses(progress: PeopleLoadProgress, source: str | None) -> list[SourceLoadProgress]:
    if source is None:
        return list(progress.sources.values())
    item = progress.sources.get(source)
    return [item] if item is not None else []


def scope_has_more(progress: PeopleLoadProgress, source: str | None) -> bool:
    return any(not item.complete or item.task is not None for item in _scope_progresses(progress, source))


def scope_total_hint(
    anime: AggregatedAnime,
    section: str,
    progress: PeopleLoadProgress,
    source: str | None,
) -> int | None:
    actual = len(_people_for_scope(anime, section, source))
    if source is not None:
        item = progress.sources.get(source)
        if item is None or item.total_count is None:
            return actual or None
        return max(actual, item.total_count)
    hints = [item.total_count for item in progress.sources.values() if item.total_count is not None]
    return max([actual, *hints]) if actual or hints else None


def _merge_people_batch(anime: AggregatedAnime, section: str, source_name: str, batch: PeopleBatch) -> None:
    mapping = _section_mapping(anime, section)
    existing = list(mapping.get(source_name, []))
    AGGREGATOR.merge_people_source(
        anime,
        source_name=source_name,
        people=[*existing, *batch.people],
        section=section,
    )


async def _run_source_batch(anime: AggregatedAnime, section: str, item: SourceLoadProgress) -> bool:
    source = item.source
    try:
        identity = anime.identity
        batch_loader = getattr(source, f"load_{section}_batch", None)
        if callable(batch_loader):
            batch = await batch_loader(
                identity.copy(),
                cursor=item.cursor,
                portrait_limit=_portrait_batch_size(),
            )
        else:
            full_loader = getattr(source, f"load_{section}", None)
            if not callable(full_loader):
                item.complete = True
                return False
            people = await full_loader(identity.copy())
            batch = PeopleBatch(people=people, complete=True, total_count=len(people))

        _merge_people_batch(anime, section, source.name, batch)
        if batch.total_count is not None:
            item.total_count = max(item.total_count or 0, int(batch.total_count))
        item.cursor = batch.next_cursor
        item.complete = bool(batch.complete or batch.next_cursor is None)
        source_people = _section_mapping(anime, section).get(source.name, [])
        source_portraits = sum(
            1 for person in source_people if _portrait_urls(person, source=source.name)
        )
        logging.info(
            "Progressive %s loaded from %s: batch_people=%d, total_people=%d, portraits=%d, complete=%s, cursor=%s",
            section,
            source.name,
            len(batch.people),
            len(source_people),
            source_portraits,
            item.complete,
            item.cursor,
        )
        return bool(batch.people)
    except asyncio.CancelledError:
        raise
    except Exception:
        item.complete = True
        logging.exception("Progressive %s load failed for %s", section, source.name)
        return False
    finally:
        item.task = None


def _start_source_batch(
    anime: AggregatedAnime,
    section: str,
    item: SourceLoadProgress,
) -> asyncio.Task[bool] | None:
    if item.complete or item.task is not None:
        return item.task
    task = asyncio.create_task(_run_source_batch(anime, section, item))
    item.task = task
    return task


def _start_scope_batches(
    anime: AggregatedAnime,
    section: str,
    progress: PeopleLoadProgress,
    source: str | None,
) -> list[asyncio.Task[bool]]:
    tasks: list[asyncio.Task[bool]] = []
    for item in _scope_progresses(progress, source):
        task = _start_source_batch(anime, section, item)
        if task is not None:
            tasks.append(task)
    return tasks


async def _await_one_scope_batch(
    anime: AggregatedAnime,
    section: str,
    progress: PeopleLoadProgress,
    source: str | None,
) -> None:
    tasks = [item.task for item in _scope_progresses(progress, source) if item.task is not None]
    if not tasks:
        tasks = _start_scope_batches(anime, section, progress, source)
    if not tasks:
        return
    done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    for task in done:
        try:
            await task
        except asyncio.CancelledError:
            raise
        except Exception:
            logging.exception("Unexpected progressive people task failure")


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
    if progress is None:
        progress = build_progress(anime, section)
        PEOPLE_LOADS[key] = progress
    if not progress.sources:
        return progress

    if created:
        if not _all_people(anime, section):
            loading_key = "loading_staff" if section == "staff" else "loading_voices"
            try:
                await message.edit_text(text=text("people", loading_key, locale=locale), reply_markup=None)
            except Exception:
                logging.debug("Could not show progressive people loading state", exc_info=True)
        _start_scope_batches(anime, section, progress, None)

    def current_people() -> list[PersonCredit]:
        return _people_for_scope(anime, section, source)

    def current_portraits() -> int:
        return len(_people_state(anime, section, source)[1])

    while not current_people() and scope_has_more(progress, source):
        await _await_one_scope_batch(anime, section, progress, source)

    requested_page = max(0, int(requested_page))
    while requested_page > current_portraits() and scope_has_more(progress, source):
        await _await_one_scope_batch(anime, section, progress, source)
    return progress
