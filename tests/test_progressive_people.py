from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, patch

from bots.telegram.people_portraits import _keyboard
from core.models import AggregatedAnime
from sources.shikimori_people_batches import load_shikimori_voices_batch


class ProgressiveShikimoriPeopleTests(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def _character(character_id: str, *, portrait: bool) -> dict:
        person_id = f"p{character_id}"
        image = {"original": f"/system/people/original/{person_id}.jpg"} if portrait else {}
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

        async def load_characters(ids: list[str]) -> list[dict]:
            return [
                self._character(
                    character_id,
                    portrait=int(character_id) >= 4,
                )
                for character_id in ids
            ]

        with (
            patch(
                "sources.shikimori_people_batches._character_ids_for_anime",
                new=AsyncMock(return_value=character_ids),
            ),
            patch(
                "sources.shikimori_people_batches._rest_character_details",
                new=AsyncMock(side_effect=load_characters),
            ) as character_details,
            patch(
                "sources.shikimori_people_batches._refresh_people",
                new=AsyncMock(return_value=None),
            ),
            patch(
                "sources.shikimori_people_batches._character_chunk_size",
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

        async def load_characters(ids: list[str]) -> list[dict]:
            return [self._character(character_id, portrait=True) for character_id in ids]

        with (
            patch(
                "sources.shikimori_people_batches._character_ids_for_anime",
                new=AsyncMock(return_value=character_ids),
            ),
            patch(
                "sources.shikimori_people_batches._rest_character_details",
                new=AsyncMock(side_effect=load_characters),
            ),
            patch(
                "sources.shikimori_people_batches._refresh_people",
                new=AsyncMock(return_value=None),
            ),
            patch(
                "sources.shikimori_people_batches._character_chunk_size",
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
        self.assertEqual([person.external_ids["shikimori"] for person in first.people], ["p1", "p2"])
        self.assertEqual([person.external_ids["shikimori"] for person in second.people], ["p3", "p4"])
        self.assertFalse(second.complete)
        self.assertEqual(second.next_cursor, "4")


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
