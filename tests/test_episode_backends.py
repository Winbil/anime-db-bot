from __future__ import annotations

import unittest

from bots.telegram.card.features.episodes import (
    _episode_detail_text,
    _episode_keyboard,
    _episode_summary_lines,
    resolve_backend_selector,
)
from core.identity import AnimeIdentity
from core.models import EpisodePage, EpisodeRecord, EpisodeSkipSegment
from services.media.episodes import EpisodeService


class _EpisodeSource:
    def __init__(self, backend: str, source_key: str, display_name: str) -> None:
        self.backend_key = backend
        self.source_key = source_key
        self.display_name = display_name
        self.name = display_name

    async def load_episode_page(
        self, identity: AnimeIdentity, *, page: int = 1
    ) -> EpisodePage:
        return EpisodePage(items=[], page=page, has_next=False)

    async def load_episode(
        self, identity: AnimeIdentity, episode_number: int
    ) -> EpisodeRecord | None:
        return None


class _DynamicEpisodeSource(_EpisodeSource):
    def supports_identity(self, identity: AnimeIdentity) -> bool:
        return identity.has("tmdb_tv")


class EpisodeBackendTests(unittest.TestCase):
    def test_available_backends_follow_confirmed_identity_keys(self) -> None:
        service = EpisodeService(
            [
                _EpisodeSource("jikan", "mal", "MAL / Jikan"),
                _EpisodeSource("anidb", "anidb", "AniDB"),
            ]
        )
        self.assertEqual(
            service.available_backends(AnimeIdentity({"mal": "1", "anidb": "2"})),
            ["jikan", "anidb"],
        )
        self.assertEqual(
            service.available_backends(AnimeIdentity({"anidb": "2"})),
            ["anidb"],
        )

    def test_backend_can_declare_dynamic_identity_support(self) -> None:
        service = EpisodeService(
            [
                _EpisodeSource("jikan", "mal", "MAL / Jikan"),
                _DynamicEpisodeSource("skipdb", "imdb", "SkipDB"),
            ]
        )
        identity = AnimeIdentity({"tmdb_tv": "119495"})
        self.assertEqual(service.available_backends(identity), ["skipdb"])

    def test_backend_selector_supports_old_numeric_callbacks(self) -> None:
        backends = ["jikan", "anidb"]
        self.assertEqual(resolve_backend_selector("anidb", backends), "anidb")
        self.assertEqual(resolve_backend_selector("0", backends), "jikan")
        self.assertEqual(resolve_backend_selector("1", backends), "anidb")
        with self.assertRaises(ValueError):
            resolve_backend_selector("9", backends)
        with self.assertRaises(ValueError):
            resolve_backend_selector("missing", backends)

    def test_skipdb_ui_uses_season_episode_reference_not_internal_selector(
        self,
    ) -> None:
        item = EpisodeRecord(
            number=10001,
            source="imdb",
            backend="skipdb",
            titles={"english": "Pilot"},
            season_number=1,
            episode_number=1,
            skip_segments={
                "intro": EpisodeSkipSegment(
                    kind="intro",
                    start_ms=61_000,
                    end_ms=91_000,
                    confidence=0.93,
                )
            },
        )
        summary = _episode_summary_lines(item, locale="ru")
        self.assertTrue(summary[0].startswith("S1E1. "))
        self.assertNotIn("10001", "\n".join(summary))
        detail = _episode_detail_text(item, locale="ru", source_name="SkipDB")
        self.assertIn("S1E1", detail)
        self.assertIn("Опенинг: 1:01.0–1:31.0", detail)
        self.assertNotIn("10001", detail)

    def test_episode_keyboard_scopes_page_and_detail_callbacks_to_backend(self) -> None:
        item = EpisodeRecord(number=1, source="anidb", backend="anidb")
        service = EpisodeService(
            [
                _EpisodeSource("jikan", "mal", "MAL / Jikan"),
                _EpisodeSource("anidb", "anidb", "AniDB"),
            ]
        )
        keyboard = _episode_keyboard(
            "token",
            [item],
            backends=["jikan", "anidb"],
            backend="anidb",
            view_page=3,
            has_prev=True,
            has_next=True,
            locale="ru",
            service=service,
        )
        flattened = [button for row in keyboard.inline_keyboard for button in row]
        callbacks = {
            button.callback_data for button in flattened if button.callback_data
        }
        self.assertIn("ae:token:anidb:1:3", callbacks)
        self.assertIn("ap:token:anidb:2", callbacks)
        self.assertIn("ap:token:anidb:4", callbacks)
        self.assertIn("ap:token:jikan:0", callbacks)
        self.assertIn("ap:token:anidb:0", callbacks)
        self.assertTrue(any(button.text == "✓ AniDB" for button in flattened))


if __name__ == "__main__":
    unittest.main()
