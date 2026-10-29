from __future__ import annotations

import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from bots.telegram.card.runtime.state import TelegramCardState
from bots.telegram.people.loading import ensure_lazy_people, start_people_prefetch
from bots.telegram.people.portraits import _keyboard
from core.models import AggregatedAnime, PersonCredit
from services.media.people import PeopleLoadProgress, SourceLoadProgress
from sources.providers.shikimori_people_batches import (
    _character_ids_for_anime,
    load_shikimori_voices_batch,
)
from sources.providers.shikimori_people_runtime import ShikimoriPeopleRuntime
from sources.providers.shikimori_people import (
    load_shikimori_voice_manifest,
    load_shikimori_voice_portraits,
)


class ProgressiveShikimoriPeopleTests(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def _character(character_id: str, *, portrait: bool) -> dict:
        person_id = f"p{character_id}"
        image = (
            {"original": f"/system/people/original/{person_id}.jpg"} if portrait else {}
        )
        return {
            "id": character_id,
            "name": f"Character {character_id}",
            "seyu": [
                {
                    "id": person_id,
                    "name": f"Voice Person {character_id}",
                    "image": image,
                }
            ],
        }

    async def test_portraitless_people_do_not_consume_batch_budget(self) -> None:
        character_ids = [str(index) for index in range(1, 8)]

        async def load_characters(ids: list[str], *_args) -> list[dict]:
            return [
                self._character(
                    character_id,
                    portrait=int(character_id) >= 4,
                )
                for character_id in ids
            ]

        with (
            patch(
                "sources.providers.shikimori_people_batches._character_ids_for_anime",
                new=AsyncMock(return_value=character_ids),
            ),
            patch(
                "sources.providers.shikimori_people_batches._rest_character_details",
                new=AsyncMock(side_effect=load_characters),
            ) as character_details,
            patch(
                "sources.providers.shikimori_people_batches._refresh_people",
                new=AsyncMock(return_value=None),
            ),
            patch(
                "sources.providers.shikimori_people_batches._character_chunk_size",
                return_value=1,
            ),
        ):
            batch = await load_shikimori_voices_batch(
                "37430",
                portrait_limit=2,
            )

        # Three portrait-less people are kept but do not use the portrait budget;
        # scanning continues until two actual portrait-bearing seiyuu are found.
        self.assertEqual(len(batch.people), 5)
        self.assertEqual(
            sum(bool(person.portraits.get("Shikimori")) for person in batch.people),
            2,
        )
        self.assertFalse(batch.complete)
        self.assertEqual(batch.next_cursor, "5")
        self.assertEqual(character_details.await_count, 5)

    async def test_cursor_continues_after_portrait_budget_boundary(self) -> None:
        character_ids = [str(index) for index in range(1, 8)]

        async def load_characters(ids: list[str], *_args) -> list[dict]:
            return [
                self._character(character_id, portrait=True) for character_id in ids
            ]

        with (
            patch(
                "sources.providers.shikimori_people_batches._character_ids_for_anime",
                new=AsyncMock(return_value=character_ids),
            ),
            patch(
                "sources.providers.shikimori_people_batches._rest_character_details",
                new=AsyncMock(side_effect=load_characters),
            ),
            patch(
                "sources.providers.shikimori_people_batches._refresh_people",
                new=AsyncMock(return_value=None),
            ),
            patch(
                "sources.providers.shikimori_people_batches._character_chunk_size",
                return_value=1,
            ),
        ):
            first = await load_shikimori_voices_batch("37430", portrait_limit=2)
            second = await load_shikimori_voices_batch(
                "37430",
                cursor=first.next_cursor,
                portrait_limit=2,
            )

        self.assertEqual(first.next_cursor, "2")
        self.assertFalse(first.complete)
        self.assertEqual(
            [person.external_ids["shikimori"] for person in first.people], ["p1", "p2"]
        )
        self.assertEqual(
            [person.external_ids["shikimori"] for person in second.people], ["p3", "p4"]
        )
        self.assertFalse(second.complete)
        self.assertEqual(second.next_cursor, "4")


class ShikimoriManifestTests(unittest.IsolatedAsyncioTestCase):
    async def test_voice_manifest_is_portrait_only_without_character_crawl(
        self,
    ) -> None:
        with patch(
            "sources.providers.shikimori_people._rest_anime_roles",
            new=AsyncMock(),
        ) as roles:
            manifest = await load_shikimori_voice_manifest("37430")

        self.assertTrue(manifest.portrait_only)
        self.assertEqual(manifest.people, [])
        roles.assert_not_awaited()

    async def test_portrait_enrichment_matches_only_verified_batch_people(self) -> None:
        target = PersonCredit(
            name="Voice Person 1",
            roles=["voice_of::Character 1"],
            external_ids={"mal": "100"},
        )
        unrelated = PersonCredit(
            name="Other Person",
            roles=["voice_of::Character 2"],
            external_ids={"mal": "200"},
        )
        roles = [
            {
                "character": {
                    "id": "1",
                    "name": "Character 1",
                    "russian": "",
                }
            },
            {
                "character": {
                    "id": "2",
                    "name": "Character 2",
                    "russian": "",
                }
            },
        ]
        character = ProgressiveShikimoriPeopleTests._character("1", portrait=True)
        with (
            patch(
                "sources.providers.shikimori_people._rest_anime_roles",
                new=AsyncMock(return_value=roles),
            ),
            patch(
                "sources.providers.shikimori_people._rest_character_details",
                new=AsyncMock(return_value=[character]),
            ) as details,
        ):
            enriched = await load_shikimori_voice_portraits(
                "37430", [target, unrelated]
            )

        details.assert_awaited_once()
        self.assertEqual(details.await_args.args[0], ["1", "2"])
        self.assertEqual(len(enriched), 1)
        self.assertEqual(enriched[0].external_ids["shikimori"], "p1")
        self.assertTrue(enriched[0].portraits["Shikimori"])


class ShikimoriRoleIndexCacheTests(unittest.IsolatedAsyncioTestCase):
    async def test_role_index_cache_is_scoped_to_people_runtime(self) -> None:
        roles = [{"character": {"id": "1"}}]
        first = ShikimoriPeopleRuntime()
        second = ShikimoriPeopleRuntime()

        with patch(
            "sources.providers.shikimori_people_batches._rest_anime_roles",
            new=AsyncMock(return_value=roles),
        ) as load_roles:
            self.assertEqual(
                await _character_ids_for_anime("37430", runtime=first), ["1"]
            )
            self.assertEqual(
                await _character_ids_for_anime("37430", runtime=first), ["1"]
            )
            self.assertEqual(
                await _character_ids_for_anime("37430", runtime=second), ["1"]
            )

        self.assertEqual(load_roles.await_count, 2)


class ProgressivePeopleLoadingWiringTests(unittest.IsolatedAsyncioTestCase):
    async def test_cold_open_shows_loading_until_exact_manifest_is_ready(self) -> None:
        state = TelegramCardState.create(60)
        anime = AggregatedAnime(title="Example")
        message = AsyncMock()
        progress = PeopleLoadProgress(
            sources={"Slow": SourceLoadProgress(source=object())}
        )
        service = MagicMock()
        service.build_progress.return_value = progress
        service.scope_manifest_complete.return_value = False
        service.ensure = AsyncMock(return_value=progress)

        with patch("bots.telegram.people.loading._service", return_value=service):
            result = await ensure_lazy_people(
                state,
                "token",
                anime,
                message,
                "staff",
                locale="ru",
            )

        self.assertIs(result, progress)
        message.edit_text.assert_awaited_once()
        service.ensure.assert_awaited_once_with(
            anime,
            "staff",
            progress,
            source=None,
            requested_page=0,
        )

    async def test_main_card_prefetch_starts_manifest_and_first_portrait_batch(
        self,
    ) -> None:
        state = TelegramCardState.create(60)
        anime = AggregatedAnime(title="Example")
        staff = PeopleLoadProgress(
            sources={"Staff": SourceLoadProgress(source=object())}
        )
        voices = PeopleLoadProgress(
            sources={"Voices": SourceLoadProgress(source=object())}
        )
        service = MagicMock()
        service.build_progress.side_effect = [staff, voices]
        service.prefetch = AsyncMock(return_value=None)

        with patch("bots.telegram.people.loading._service", return_value=service):
            start_people_prefetch(state, "token", anime)
            await asyncio.sleep(0)
            await asyncio.sleep(0)

        self.assertEqual(service.build_progress.call_count, 2)
        self.assertEqual(service.start_manifest_loads.call_count, 2)
        self.assertEqual(service.prefetch.await_count, 2)


class ProgressivePeopleKeyboardTests(unittest.TestCase):
    def test_next_button_stays_available_at_loaded_boundary(self) -> None:
        anime = AggregatedAnime(title="Example")
        keyboard = _keyboard(
            "token",
            anime,
            "voices",
            None,
            page=50,
            shown=80,
            total=130,
            max_page=50,
            locale="ru",
            source_names=["Shikimori", "AniList"],
            has_more=True,
        )

        navigation = keyboard.inline_keyboard[0]
        callbacks = [button.callback_data for button in navigation]
        self.assertIn("av:token:voices:51", callbacks)
        self.assertTrue(any(button.text == "Показано 80/130" for button in navigation))

    def test_next_button_disappears_when_loaded_data_is_complete(self) -> None:
        anime = AggregatedAnime(title="Example")
        keyboard = _keyboard(
            "token",
            anime,
            "staff",
            None,
            page=50,
            shown=80,
            total=80,
            max_page=50,
            locale="ru",
            source_names=["Shikimori", "AniList"],
            has_more=False,
        )

        callbacks = [button.callback_data for button in keyboard.inline_keyboard[0]]
        self.assertNotIn("av:token:staff:51", callbacks)


if __name__ == "__main__":
    unittest.main()
