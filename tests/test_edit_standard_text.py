from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, patch

from bots.telegram.card.renderer import edit_standard_text


class EditStandardTextTests(unittest.IsolatedAsyncioTestCase):
    async def test_overflow_chunks_are_not_discarded(self) -> None:
        message = AsyncMock()
        keyboard = object()
        with patch(
            "bots.telegram.card.renderer.split_text",
            return_value=["first", "second", "third"],
        ):
            await edit_standard_text(
                message,
                "full",
                reply_markup=keyboard,
                locale="ru",
            )
        message.edit_text.assert_awaited_once_with(
            text="first",
            reply_markup=keyboard,
        )
        self.assertEqual(
            [call.args[0] for call in message.answer.await_args_list],
            ["second", "third"],
        )
