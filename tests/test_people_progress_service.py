from __future__ import annotations

import asyncio
import copy
import unittest

from core.models import AggregatedAnime, PersonCredit
from core.people_loading import PeopleManifest, without_portraits
from services.media.people import PeopleProgressService


class _FakeAggregator:
    def merge_people_source(
        self,
        anime: AggregatedAnime,
        *,
        source_name: str,
        people: list[PersonCredit],
        section: str,
    ) -> None:
        mapping = getattr(anime, f"{section}_by_source")
        # Enough identity merging for these service-level tests.
        by_name: dict[str, PersonCredit] = {}
        for person in people:
            key = person.name.casefold()
            current = by_name.get(key)
            if current is None:
                by_name[key] = copy.deepcopy(person)
                continue
            current.roles = list(dict.fromkeys([*current.roles, *person.roles]))
            current.external_ids.update(person.external_ids)
            for source, urls in person.portraits.items():
                current.portraits[source] = list(
                    dict.fromkeys([*current.portraits.get(source, []), *urls])
                )
        mapping[source_name] = list(by_name.values())

        merged_by_name: dict[str, PersonCredit] = {}
        for values in mapping.values():
            for person in values:
                key = person.name.casefold()
                current = merged_by_name.get(key)
                if current is None:
                    merged_by_name[key] = copy.deepcopy(person)
                    continue
                current.roles = list(dict.fromkeys([*current.roles, *person.roles]))
                current.external_ids.update(person.external_ids)
                for source, urls in person.portraits.items():
                    current.portraits[source] = list(
                        dict.fromkeys([*current.portraits.get(source, []), *urls])
                    )
        setattr(anime, section, list(merged_by_name.values()))


class _ManifestSource:
    name = "AniList"
    source_key = "anilist"

    def __init__(self, count: int = 5, release: asyncio.Event | None = None) -> None:
        self.release = release
        self.manifest_calls = 0
        self.people = [
            PersonCredit(
                name=f"Person {index}",
                external_ids={"anilist": str(index)},
                portraits={"AniList": [f"https://img.example/{index}.jpg"]},
            )
            for index in range(1, count + 1)
        ]

    async def load_voices_manifest(self, identity) -> PeopleManifest:
        del identity
        self.manifest_calls += 1
        if self.release is not None:
            await self.release.wait()
        return PeopleManifest(
            people=without_portraits(self.people),
            portrait_pool=copy.deepcopy(self.people),
        )


class _NamedManifestSource(_ManifestSource):
    def __init__(
        self,
        name: str,
        source_key: str,
        person_name: str,
        release: asyncio.Event | None = None,
    ) -> None:
        self.name = name
        self.source_key = source_key
        self.release = release
        self.manifest_calls = 0
        self.people = [
            PersonCredit(
                name=person_name,
                external_ids={source_key: "1"},
                portraits={name: [f"https://img.example/{source_key}.jpg"]},
            )
        ]


class _PortraitOnlySource:
    name = "Shikimori"
    source_key = "shikimori"

    def __init__(self, release: asyncio.Event) -> None:
        self.release = release
        self.calls = 0

    async def load_voices_manifest(self, identity) -> PeopleManifest:
        del identity
        return PeopleManifest(portrait_only=True)

    async def load_voices_portraits(
        self, identity, people: list[PersonCredit]
    ) -> list[PersonCredit]:
        del identity
        self.calls += 1
        await self.release.wait()
        result = copy.deepcopy(people)
        for person in result:
            person.portraits["Shikimori"] = [f"https://shiki.example/{person.name}.jpg"]
        return result


class PeopleProgressServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_manifest_total_is_exact_before_portrait_batches(self) -> None:
        source = _ManifestSource(count=5)
        service = PeopleProgressService(
            [source],
            _FakeAggregator(),  # type: ignore[arg-type]
            portrait_batch_size=2,
        )
        anime = AggregatedAnime(
            title="Example",
            external_ids={"anilist": "1"},
            sources=["AniList"],
        )
        progress = service.build_progress(anime, "voices")
        self.assertEqual(service.source_names(anime, "voices", progress), ["AniList"])

        service.start_manifest_loads(anime, "voices", progress)
        await service.settle_manifests(anime, "voices", progress)

        self.assertEqual(service.scope_total_hint(anime, "voices", progress, None), 5)
        self.assertEqual(anime.voices, [])
        self.assertEqual(progress.portrait_cursor, 0)

    async def test_portraits_are_enriched_in_global_batches(self) -> None:
        source = _ManifestSource(count=5)
        service = PeopleProgressService(
            [source],
            _FakeAggregator(),  # type: ignore[arg-type]
            portrait_batch_size=2,
        )
        anime = AggregatedAnime(
            title="Example",
            external_ids={"anilist": "1"},
            sources=["AniList"],
        )
        progress = service.build_progress(anime, "voices")

        await service.ensure(anime, "voices", progress, requested_page=1)
        self.assertEqual(progress.portrait_cursor, 2)
        self.assertEqual(len(anime.voices), 2)
        self.assertEqual(service.scope_total_hint(anime, "voices", progress, None), 5)
        self.assertTrue(service.scope_has_more(progress, None))

        await service.ensure(anime, "voices", progress, requested_page=3)
        self.assertEqual(progress.portrait_cursor, 4)
        self.assertEqual(len(anime.voices), 4)
        self.assertEqual(service.scope_total_hint(anime, "voices", progress, None), 5)

        await service.ensure(anime, "voices", progress, requested_page=5)
        self.assertEqual(progress.portrait_cursor, 5)
        self.assertEqual(len(anime.voices), 5)
        self.assertFalse(service.scope_has_more(progress, None))

    async def test_manifest_settle_waits_for_every_source_for_exact_union(self) -> None:
        release = asyncio.Event()
        fast = _NamedManifestSource("Fast", "anilist", "Same Person")
        slow = _NamedManifestSource("Slow", "mal", "Second Person", release)
        service = PeopleProgressService(
            [fast, slow],
            _FakeAggregator(),  # type: ignore[arg-type]
            portrait_batch_size=50,
        )
        anime = AggregatedAnime(
            title="Example",
            external_ids={"anilist": "1", "mal": "1"},
            sources=["Fast", "Slow"],
        )
        progress = service.build_progress(anime, "voices")
        service.start_manifest_loads(anime, "voices", progress)
        settle_task = asyncio.create_task(
            service.settle_manifests(anime, "voices", progress)
        )
        await asyncio.sleep(0)
        await asyncio.sleep(0)

        self.assertEqual(fast.manifest_calls, 1)
        self.assertEqual(slow.manifest_calls, 1)
        self.assertFalse(settle_task.done())
        self.assertIsNone(service.scope_total_hint(anime, "voices", progress, None))

        release.set()
        await settle_task
        self.assertEqual(service.scope_total_hint(anime, "voices", progress, None), 2)

    async def test_duplicate_people_across_sources_count_once(self) -> None:
        first = _NamedManifestSource("AniList", "anilist", "Same Person")
        second = _NamedManifestSource("MAL", "mal", "Same Person")
        service = PeopleProgressService(
            [first, second],
            _FakeAggregator(),  # type: ignore[arg-type]
            portrait_batch_size=50,
        )
        anime = AggregatedAnime(
            title="Example",
            external_ids={"anilist": "1", "mal": "1"},
            sources=["AniList", "MAL"],
        )
        progress = service.build_progress(anime, "voices")
        await service.settle_manifests(anime, "voices", progress)
        self.assertEqual(service.scope_total_hint(anime, "voices", progress, None), 1)

    async def test_portrait_batch_size_is_global_across_sources(self) -> None:
        first = _ManifestSource(count=60)
        second = _ManifestSource(count=60)
        second.name = "MAL"
        second.source_key = "mal"
        second.people = [
            PersonCredit(
                name=f"Person {index}",
                external_ids={"mal": str(index)},
                portraits={"MAL": [f"https://mal.example/{index}.jpg"]},
            )
            for index in range(1, 61)
        ]
        service = PeopleProgressService(
            [first, second],
            _FakeAggregator(),  # type: ignore[arg-type]
            portrait_batch_size=50,
        )
        anime = AggregatedAnime(
            title="Example",
            external_ids={"anilist": "1", "mal": "1"},
            sources=["AniList", "MAL"],
        )
        progress = service.build_progress(anime, "voices")
        await service.ensure(anime, "voices", progress, requested_page=1)

        self.assertEqual(service.scope_total_hint(anime, "voices", progress, None), 60)
        self.assertEqual(progress.portrait_cursor, 50)
        self.assertEqual(len(anime.voices), 50)

    async def test_slow_portrait_only_enrichment_never_blocks_batch_cursor(
        self,
    ) -> None:
        release = asyncio.Event()
        authority = _ManifestSource(count=60)
        shikimori = _PortraitOnlySource(release)
        service = PeopleProgressService(
            [authority, shikimori],
            _FakeAggregator(),  # type: ignore[arg-type]
            portrait_batch_size=50,
        )
        anime = AggregatedAnime(
            title="Example",
            external_ids={"anilist": "1", "shikimori": "1"},
            sources=["AniList", "Shikimori"],
        )
        progress = service.build_progress(anime, "voices")

        await service.ensure(anime, "voices", progress, requested_page=1)
        await asyncio.sleep(0)

        self.assertEqual(progress.portrait_cursor, 50)
        self.assertEqual(len(anime.voices), 50)
        self.assertEqual(shikimori.calls, 1)
        self.assertTrue(progress.enrichment_tasks)

        release.set()
        await asyncio.gather(*list(progress.enrichment_tasks))
        self.assertFalse(progress.enrichment_tasks)

    async def test_progress_excludes_sources_without_confirmed_identity(self) -> None:
        source = _ManifestSource()
        service = PeopleProgressService(
            [source],
            _FakeAggregator(),  # type: ignore[arg-type]
            portrait_batch_size=2,
        )
        anime = AggregatedAnime(title="Example", external_ids={"mal": "1"})
        self.assertFalse(service.build_progress(anime, "voices").sources)


if __name__ == "__main__":
    unittest.main()
