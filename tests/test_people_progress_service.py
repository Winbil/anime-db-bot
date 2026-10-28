from __future__ import annotations

import unittest

from core.models import AggregatedAnime, PersonCredit
from core.people_loading import PeopleBatch
from services.people_progress import PeopleProgressService


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
        mapping[source_name] = list(people)
        setattr(anime, section, list(people))


class _BatchSource:
    name = "AniList"
    source_key = "anilist"

    def __init__(self) -> None:
        self.calls: list[tuple[str | None, int]] = []

    async def load_voices_batch(
        self,
        identity,
        *,
        cursor: str | None,
        portrait_limit: int,
    ) -> PeopleBatch:
        self.calls.append((cursor, portrait_limit))
        if cursor is None:
            return PeopleBatch(
                people=[
                    PersonCredit(
                        name="First",
                        portraits={"AniList": ["https://img.example/first.jpg"]},
                    )
                ],
                next_cursor="1",
                complete=False,
                total_count=2,
            )
        return PeopleBatch(
            people=[
                PersonCredit(
                    name="Second",
                    portraits={"AniList": ["https://img.example/second.jpg"]},
                )
            ],
            complete=True,
            total_count=2,
        )


class PeopleProgressServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_progressive_loading_is_transport_independent(self) -> None:
        source = _BatchSource()
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
        self.assertTrue(service.scope_has_more(progress, None))

        service.start_initial_batches(anime, "voices", progress)
        await service.ensure(
            anime,
            "voices",
            progress,
            requested_page=2,
        )

        self.assertEqual(source.calls, [(None, 2), ("1", 2)])
        self.assertEqual([person.name for person in anime.voices], ["First", "Second"])
        self.assertEqual(service.scope_total_hint(anime, "voices", progress, None), 2)
        self.assertFalse(service.scope_has_more(progress, None))

    async def test_progress_excludes_sources_without_confirmed_identity(self) -> None:
        source = _BatchSource()
        service = PeopleProgressService(
            [source],
            _FakeAggregator(),  # type: ignore[arg-type]
            portrait_batch_size=2,
        )
        anime = AggregatedAnime(title="Example", external_ids={"mal": "1"})
        self.assertFalse(service.build_progress(anime, "voices").sources)


if __name__ == "__main__":
    unittest.main()
