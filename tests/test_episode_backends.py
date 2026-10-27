from __future__ import annotations

import unittest
from unittest.mock import patch

from bots.telegram.card.episodes import _episode_keyboard
from core.identity import AnimeIdentity
from core.models import EpisodePage, EpisodeRecord
from services.episodes import EpisodeService


class _EpisodeSource:
    def __init__(self, backend: str, source_key: str, display_name: str) -> None:
        self.backend_key = backend
        self.source_key = source_key
        self.display_name = display_name
        self.name = display_name

    async def load_episode_page(self, identity: AnimeIdentity, *, page: int = 1) -> EpisodePage:
        return EpisodePage(items=[], page=page, has_next=False)

    async def load_episode(self, identity: AnimeIdentity, episode_number: int) -> EpisodeRecord | None:
        return None


class EpisodeBackendTests(unittest.TestCase):
    def test_available_backends_follow_confirmed_identity_keys(self) -> None:
        service = EpisodeService([
            _EpisodeSource("jikan", "mal", "MAL / Jikan"),
            _EpisodeSource("anidb", "anidb", "AniDB"),
        ])
        self.assertEqual(
            service.available_backends(AnimeIdentity({"mal": "1", "anidb": "2"})),
            ["jikan", "anidb"],
        )
        self.assertEqual(
            service.available_backends(AnimeIdentity({"anidb": "2"})),
            ["anidb"],
        )

    def test_episode_keyboard_scopes_page_and_detail_callbacks_to_backend(self) -> None:
        item = EpisodeRecord(number=1, source="anidb", backend="anidb")
        labels = {"jikan": "MAL / Jikan", "anidb": "AniDB"}
        with patch(
            "bots.telegram.card.episodes.EPISODE_SERVICE.display_name",
            side_effect=lambda backend: labels[backend],
        ):
            keyboard = _episode_keyboard(
                "token",
                [item],
                backends=["jikan", "anidb"],
                backend_index=1,
                view_page=3,
                has_prev=True,
                has_next=True,
                locale="ru",
            )
        flattened = [button for row in keyboard.inline_keyboard for button in row]
        callbacks = {button.callback_data for button in flattened if button.callback_data}
        self.assertIn("ae:token:1:1:3", callbacks)
        self.assertIn("ap:token:1:2", callbacks)
        self.assertIn("ap:token:1:4", callbacks)
        self.assertIn("ap:token:0:0", callbacks)
        self.assertIn("ap:token:1:0", callbacks)
        self.assertTrue(any(button.text == "✓ AniDB" for button in flattened))


if __name__ == "__main__":
    unittest.main()
