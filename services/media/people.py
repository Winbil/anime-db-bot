from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any

from core.canonicalization import person_identity_keys
from core.models import AggregatedAnime, PersonCredit
from core.people import (
    people_for_scope,
    people_state,
    portrait_urls,
    section_mapping,
    sources_with_portraits,
)
from core.people_loading import PeopleManifest, without_portraits
from services.identity.aggregator import AnimeAggregator


@dataclass(slots=True)
class SourceLoadProgress:
    source: Any
    manifest_people: list[PersonCredit] = field(default_factory=list)
    portrait_pool: list[PersonCredit] = field(default_factory=list)
    manifest_complete: bool = False
    manifest_task: asyncio.Task[bool] | None = None
    portrait_only: bool = False


@dataclass(slots=True)
class PeopleLoadProgress:
    sources: dict[str, SourceLoadProgress] = field(default_factory=dict)
    manifest_people: list[PersonCredit] = field(default_factory=list)
    portrait_cursor: int = 0
    portraits_complete: bool = False
    portrait_task: asyncio.Task[bool] | None = None
    enrichment_tasks: set[asyncio.Task[None]] = field(default_factory=set)
    view_revision: int = 0


class PeopleProgressService:
    """Load complete lightweight people manifests and enrich portraits in batches."""

    def __init__(
        self,
        sources: tuple[Any, ...] | list[Any],
        aggregator: AnimeAggregator,
        *,
        portrait_batch_size: int = 50,
    ) -> None:
        self._sources = tuple(sources)
        self._aggregator = aggregator
        self._portrait_batch_size = max(1, min(int(portrait_batch_size), 200))

    def build_progress(
        self, anime: AggregatedAnime, section: str
    ) -> PeopleLoadProgress:
        identity = anime.identity
        mapping = section_mapping(anime, section)
        progress = PeopleLoadProgress()
        for source in self._sources:
            source_key = str(getattr(source, "source_key", "") or "").strip().casefold()
            if source_key and not identity.has(source_key):
                continue
            manifest_loader = getattr(source, f"load_{section}_manifest", None)
            full_loader = getattr(source, f"load_{section}", None)
            if not callable(manifest_loader) and not callable(full_loader):
                continue
            existing = list(mapping.get(source.name, []))
            progress.sources[source.name] = SourceLoadProgress(
                source=source,
                manifest_people=without_portraits(existing),
                portrait_pool=list(existing),
                manifest_complete=bool(existing),
            )
        self._rebuild_manifest(anime, section, progress)
        return progress

    @staticmethod
    def source_names(
        anime: AggregatedAnime,
        section: str,
        progress: PeopleLoadProgress | None,
    ) -> list[str]:
        if progress is None:
            return sources_with_portraits(anime, section)
        if PeopleProgressService._manifest_complete(progress, None):
            return [
                name for name, item in progress.sources.items() if item.manifest_people
            ]
        return list(progress.sources)

    @staticmethod
    def _scope_progresses(
        progress: PeopleLoadProgress,
        source: str | None,
    ) -> list[SourceLoadProgress]:
        if source is None:
            return list(progress.sources.values())
        item = progress.sources.get(source)
        return [item] if item is not None else []

    @staticmethod
    def _manifest_complete(progress: PeopleLoadProgress, source: str | None) -> bool:
        items = PeopleProgressService._scope_progresses(progress, source)
        return bool(items) and all(
            item.manifest_complete and item.manifest_task is None for item in items
        )

    def scope_manifest_complete(
        self, progress: PeopleLoadProgress, source: str | None
    ) -> bool:
        return self._manifest_complete(progress, source)

    def scope_has_running(
        self, progress: PeopleLoadProgress, source: str | None
    ) -> bool:
        return progress.portrait_task is not None or any(
            item.manifest_task is not None
            for item in self._scope_progresses(progress, source)
        )

    @staticmethod
    def _source_key(item: SourceLoadProgress) -> str:
        return str(getattr(item.source, "source_key", "") or "").strip().casefold()

    @staticmethod
    def _person_names(person: PersonCredit) -> list[str]:
        return [person.name, *person.aliases]

    @classmethod
    def _same_person(
        cls,
        left: PersonCredit,
        right: PersonCredit,
        source_key: str,
    ) -> bool:
        left_id = (
            str(left.external_ids.get(source_key) or "").strip() if source_key else ""
        )
        right_id = (
            str(right.external_ids.get(source_key) or "").strip() if source_key else ""
        )
        if left_id and right_id:
            return left_id == right_id
        return bool(
            person_identity_keys(cls._person_names(left))
            & person_identity_keys(cls._person_names(right))
        )

    @classmethod
    def _source_targets(
        cls,
        item: SourceLoadProgress,
        merged_targets: list[PersonCredit],
    ) -> list[PersonCredit]:
        source_key = cls._source_key(item)
        return [
            person
            for person in item.manifest_people
            if any(
                cls._same_person(person, target, source_key)
                for target in merged_targets
            )
        ]

    def scope_has_more(self, progress: PeopleLoadProgress, source: str | None) -> bool:
        if not self._manifest_complete(progress, source):
            return True
        if progress.portrait_task is not None:
            return True
        if progress.portraits_complete:
            return False
        remaining = progress.manifest_people[progress.portrait_cursor :]
        if source is None:
            return bool(remaining)
        item = progress.sources.get(source)
        if item is None:
            return False
        return any(self._source_targets(item, [target]) for target in remaining)

    def scope_total_hint(
        self,
        anime: AggregatedAnime,
        section: str,
        progress: PeopleLoadProgress,
        source: str | None,
    ) -> int | None:
        del anime, section
        if not self._manifest_complete(progress, source):
            return None
        if source is not None:
            item = progress.sources.get(source)
            return len(item.manifest_people) if item is not None else 0
        return len(progress.manifest_people)

    def _rebuild_manifest(
        self,
        anime: AggregatedAnime,
        section: str,
        progress: PeopleLoadProgress,
    ) -> None:
        temporary = AggregatedAnime(title=anime.title, sources=list(anime.sources))
        ordered_names = [name for name in anime.sources if name in progress.sources]
        ordered_names.extend(
            name for name in progress.sources if name not in ordered_names
        )
        for source_name in ordered_names:
            item = progress.sources[source_name]
            if item.portrait_only:
                continue
            people = item.manifest_people
            if people:
                self._aggregator.merge_people_source(
                    temporary,
                    source_name=source_name,
                    people=people,
                    section=section,
                )
        progress.manifest_people = (
            list(temporary.staff) if section == "staff" else list(temporary.voices)
        )
        # Portrait-only providers enrich the already verified roster without
        # contributing extra identities to the exact total.
        for item in progress.sources.values():
            if item.portrait_only:
                item.manifest_people = without_portraits(progress.manifest_people)
        if progress.portrait_cursor >= len(progress.manifest_people):
            progress.portraits_complete = self._manifest_complete(progress, None)

    async def _run_manifest(
        self,
        anime: AggregatedAnime,
        section: str,
        progress: PeopleLoadProgress,
        item: SourceLoadProgress,
    ) -> bool:
        source = item.source
        try:
            loader = getattr(source, f"load_{section}_manifest", None)
            if callable(loader):
                manifest = await loader(anime.identity.copy())
            else:
                full_loader = getattr(source, f"load_{section}", None)
                if not callable(full_loader):
                    manifest = PeopleManifest()
                else:
                    people = await full_loader(anime.identity.copy())
                    manifest = PeopleManifest(
                        people=without_portraits(people), portrait_pool=people
                    )
            if not isinstance(manifest, PeopleManifest):
                values = list(manifest or [])
                manifest = PeopleManifest(people=without_portraits(values))
            item.portrait_only = bool(manifest.portrait_only)
            item.manifest_people = without_portraits(list(manifest.people))
            item.portrait_pool = list(manifest.portrait_pool)
            item.manifest_complete = True
            self._rebuild_manifest(anime, section, progress)
            logging.info(
                "People manifest loaded",
                extra={
                    "event": "people_manifest",
                    "source": str(getattr(source, "source_key", source.name)),
                    "operation": section,
                    "outcome": "success",
                    "items": len(item.manifest_people),
                },
            )
            return bool(item.manifest_people)
        except asyncio.CancelledError:
            raise
        except Exception:
            item.manifest_complete = True
            item.manifest_people = []
            item.portrait_pool = []
            self._rebuild_manifest(anime, section, progress)
            logging.exception("People manifest load failed for %s", source.name)
            return False
        finally:
            item.manifest_task = None

    def _start_manifest(
        self,
        anime: AggregatedAnime,
        section: str,
        progress: PeopleLoadProgress,
        item: SourceLoadProgress,
    ) -> asyncio.Task[bool] | None:
        if item.manifest_complete or item.manifest_task is not None:
            return item.manifest_task
        task = asyncio.create_task(self._run_manifest(anime, section, progress, item))
        item.manifest_task = task
        return task

    def start_manifest_loads(
        self,
        anime: AggregatedAnime,
        section: str,
        progress: PeopleLoadProgress,
    ) -> None:
        for item in progress.sources.values():
            self._start_manifest(anime, section, progress, item)

    async def settle_manifests(
        self,
        anime: AggregatedAnime,
        section: str,
        progress: PeopleLoadProgress,
        source: str | None = None,
    ) -> None:
        items = self._scope_progresses(progress, source)
        for item in items:
            self._start_manifest(anime, section, progress, item)
        tasks = [item.manifest_task for item in items if item.manifest_task is not None]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._rebuild_manifest(anime, section, progress)

    @classmethod
    def _pool_targets(
        cls,
        item: SourceLoadProgress,
        local_targets: list[PersonCredit],
    ) -> list[PersonCredit]:
        source_key = cls._source_key(item)
        return [
            person
            for person in item.portrait_pool
            if any(
                cls._same_person(person, target, source_key) for target in local_targets
            )
        ]

    async def _run_remote_enrichment(
        self,
        anime: AggregatedAnime,
        section: str,
        progress: PeopleLoadProgress,
        item: SourceLoadProgress,
        local_targets: list[PersonCredit],
    ) -> None:
        source = item.source
        loader = getattr(source, f"load_{section}_portraits", None)
        if not callable(loader) or not local_targets:
            return
        try:
            enriched = await loader(anime.identity.copy(), local_targets)
            if enriched:
                self._merge_people(anime, section, source.name, enriched)
        except asyncio.CancelledError:
            raise
        except Exception:
            logging.exception("People portrait enrichment failed for %s", source.name)

    @staticmethod
    def _track_enrichment(
        progress: PeopleLoadProgress, task: asyncio.Task[None]
    ) -> None:
        progress.enrichment_tasks.add(task)
        task.add_done_callback(progress.enrichment_tasks.discard)

    def _merge_people(
        self,
        anime: AggregatedAnime,
        section: str,
        source_name: str,
        people: list[PersonCredit],
    ) -> None:
        mapping = section_mapping(anime, section)
        existing = list(mapping.get(source_name, []))
        self._aggregator.merge_people_source(
            anime,
            source_name=source_name,
            people=[*existing, *people],
            section=section,
        )

    async def _run_portrait_batch(
        self,
        anime: AggregatedAnime,
        section: str,
        progress: PeopleLoadProgress,
    ) -> bool:
        try:
            start = progress.portrait_cursor
            end = min(start + self._portrait_batch_size, len(progress.manifest_people))
            targets = progress.manifest_people[start:end]
            if not targets:
                progress.portraits_complete = True
                return False

            for item in progress.sources.values():
                local_targets = self._source_targets(item, targets)
                if not local_targets:
                    continue
                pooled = self._pool_targets(item, local_targets)
                # The lightweight manifest records become visible immediately.
                # Cached portrait pools are applied synchronously; remote-only
                # enrichment (notably Shikimori voices) must never block the UI.
                self._merge_people(
                    anime,
                    section,
                    item.source.name,
                    [*local_targets, *pooled],
                )
                if not pooled:
                    loader = getattr(item.source, f"load_{section}_portraits", None)
                    if callable(loader):
                        task = asyncio.create_task(
                            self._run_remote_enrichment(
                                anime, section, progress, item, local_targets
                            )
                        )
                        self._track_enrichment(progress, task)

            progress.portrait_cursor = end
            progress.portraits_complete = end >= len(progress.manifest_people)
            loaded_portraits = len(people_state(anime, section, None)[1])
            logging.info(
                "People portrait batch loaded",
                extra={
                    "event": "people_portraits",
                    "operation": section,
                    "outcome": "success",
                    "batch_start": start,
                    "batch_end": end,
                    "manifest_total": len(progress.manifest_people),
                    "portraits": loaded_portraits,
                },
            )
            return True
        finally:
            progress.portrait_task = None

    def start_portrait_batch(
        self,
        anime: AggregatedAnime,
        section: str,
        progress: PeopleLoadProgress,
    ) -> asyncio.Task[bool] | None:
        if progress.portraits_complete or progress.portrait_task is not None:
            return progress.portrait_task
        if not self._manifest_complete(progress, None):
            return None
        if progress.portrait_cursor >= len(progress.manifest_people):
            progress.portraits_complete = True
            return None
        task = asyncio.create_task(self._run_portrait_batch(anime, section, progress))
        progress.portrait_task = task
        return task

    async def _await_portrait_batch(
        self,
        anime: AggregatedAnime,
        section: str,
        progress: PeopleLoadProgress,
    ) -> None:
        task = progress.portrait_task or self.start_portrait_batch(
            anime, section, progress
        )
        if task is not None:
            await task

    async def prefetch(
        self,
        anime: AggregatedAnime,
        section: str,
        progress: PeopleLoadProgress,
    ) -> None:
        """Prepare the exact manifest and the first bounded portrait batch."""
        self.start_manifest_loads(anime, section, progress)
        await self.settle_manifests(anime, section, progress)
        await self._await_portrait_batch(anime, section, progress)

    async def settle_started_batches(
        self,
        progress: PeopleLoadProgress,
        source: str | None = None,
    ) -> None:
        """Compatibility no-op waiter for callers from the older people loader."""
        tasks = [
            item.manifest_task
            for item in self._scope_progresses(progress, source)
            if item.manifest_task is not None
        ]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def ensure(
        self,
        anime: AggregatedAnime,
        section: str,
        progress: PeopleLoadProgress,
        *,
        source: str | None = None,
        requested_page: int = 0,
    ) -> PeopleLoadProgress:
        self.start_manifest_loads(anime, section, progress)
        # Exact totals require the full manifest. Prefetch normally finishes this
        # before the user opens the section; on a cold cache the UI shows its
        # loading state instead of presenting a false denominator.
        await self.settle_manifests(anime, section, progress)

        def current_people() -> list[PersonCredit]:
            return people_for_scope(anime, section, source)

        def current_portraits() -> int:
            return len(people_state(anime, section, source)[1])

        if not current_people() and self.scope_has_more(progress, source):
            await self._await_portrait_batch(anime, section, progress)

        requested_page = max(0, int(requested_page))
        while requested_page > current_portraits() and self.scope_has_more(
            progress, source
        ):
            await self._await_portrait_batch(anime, section, progress)
        return progress
