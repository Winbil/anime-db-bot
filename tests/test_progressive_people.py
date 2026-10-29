from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from bots.telegram.card.runtime.state import TelegramCardState
from bots.telegram.people.loading import ensure_lazy_people
from bots.telegram.people.portraits import _keyboard
from core.models import AggregatedAnime
from services.media.people import PeopleLoadProgress, SourceLoadProgress
from sources.providers.shikimori_people_batches import (
    _character_ids_for_anime,
    load_shikimori_voices_batch,
)
from sources.providers.shikimori_people_runtime import ShikimoriPeopleRuntime


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
    async def test_first_render_settles_all_started_initial_batches(self) -> None:
        state = TelegramCardState.create(60)
        anime = AggregatedAnime(title="Example")
        message = AsyncMock()
        progress = PeopleLoadProgress(
            sources={"Slow": SourceLoadProgress(source=object())}
        )
        service = MagicMock()
        service.build_progress.return_value = progress
        service.settle_started_batches = AsyncMock(return_value=None)
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
        service.start_initial_batches.assert_called_once_with(anime, "staff", progress)
        service.settle_started_batches.assert_awaited_once_with(progress, None)
        service.ensure.assert_awaited_once_with(
            anime,
            "staff",
            progress,
            source=None,
            requested_page=0,
        )


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
        self.assertTrue(
            any(button.text == "Показано 80 • загружено 130+" for button in navigation)
        )

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
