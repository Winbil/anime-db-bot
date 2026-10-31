from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

from bots.telegram.card.features.episodes import (
    _episode_release_projection_text,
    edit_episodes_view,
    _episode_detail_text,
    _episode_keyboard,
    _episode_summary_lines,
    _view_slice,
    resolve_backend_selector,
)
from core.identity import AnimeIdentity
from core.models import (
    AggregatedAnime,
    EpisodePage,
    EpisodeRecord,
    EpisodeReleaseProjection,
    EpisodeSkipSegment,
)
from bots.telegram.card.runtime.state import AnimeCardSession
from services.media.episode_segments import EpisodeSegmentService
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


class _SegmentSource:
    name = "AniSkip"
    display_name = "AniSkip"
    backend_key = "aniskip"

    def supports_identity(self, identity: AnimeIdentity) -> bool:
        return identity.has("mal")

    async def load_segments(
        self,
        identity: AnimeIdentity,
        episode_number: int,
        *,
        episode_length_seconds: int | None = None,
    ) -> list:
        return []


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

    def test_one_episode_view_keeps_upstream_requests_batched_by_100(self) -> None:
        self.assertEqual(_view_slice(0), (1, 0))
        self.assertEqual(_view_slice(99), (1, 99))
        self.assertEqual(_view_slice(100), (2, 0))

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

    def test_episode_keyboard_separates_episode_and_timestamp_sources(self) -> None:
        item = EpisodeRecord(number=4, source="anidb", backend="anidb")
        service = EpisodeService(
            [
                _EpisodeSource("jikan", "mal", "MAL / Jikan"),
                _EpisodeSource("anidb", "anidb", "AniDB"),
            ]
        )
        segment_service = EpisodeSegmentService([_SegmentSource()])
        keyboard = _episode_keyboard(
            "token",
            backends=["jikan", "anidb"],
            backend="anidb",
            segment_backends=["aniskip"],
            segment_backend="all",
            view_page=3,
            total_episodes=12,
            has_prev=True,
            has_next=True,
            locale="ru",
            service=service,
            segment_service=segment_service,
        )
        flattened = [button for row in keyboard.inline_keyboard for button in row]
        callbacks = {
            button.callback_data for button in flattened if button.callback_data
        }
        self.assertIn("ap:token:anidb:2", callbacks)
        self.assertTrue(any(button.text == "4/12" for button in flattened))
        self.assertIn("cp:token:ap~anidb:3:12:0", callbacks)
        self.assertIn("ap:token:anidb:4", callbacks)
        self.assertIn("ap:token:jikan:3", callbacks)
        self.assertIn("ap:token:anidb:3", callbacks)
        self.assertIn("ap:token:segments-all:3", callbacks)
        self.assertIn("ap:token:segments-aniskip:3", callbacks)
        self.assertFalse(any(value.startswith("ae:") for value in callbacks))
        self.assertTrue(any(button.text == "✓ AniDB" for button in flattened))
        self.assertTrue(any(button.text == "✓ ⏱ Все" for button in flattened))

        rows = keyboard.inline_keyboard
        episode_source_row = next(
            index
            for index, row in enumerate(rows)
            if any(button.text == "✓ AniDB" for button in row)
        )
        timestamp_row = next(
            index
            for index, row in enumerate(rows)
            if any("⏱" in button.text for button in row)
        )
        self.assertGreater(timestamp_row, episode_source_row)


class _CaptureMessage:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def edit_text(self, **kwargs) -> None:
        self.calls.append(kwargs)

    async def answer(self, *args, **kwargs) -> None:
        self.calls.append({"answer_args": args, **kwargs})


class EpisodeProjectionUiTests(unittest.IsolatedAsyncioTestCase):
    async def test_future_projection_keeps_one_episode_per_page_and_pagination(
        self,
    ) -> None:
        source = _EpisodeSource("jikan", "mal", "MAL / Jikan")

        async def load_page(identity, *, page=1):
            return EpisodePage(
                items=[
                    EpisodeRecord(
                        number=number,
                        source="mal",
                        backend="jikan",
                        titles={"english": f"Episode {number}"},
                    )
                    for number in range(1, 6)
                ],
                page=page,
                last_visible_page=1,
                has_next=False,
            )

        async def load_episode(identity, episode_number):
            if 1 <= episode_number <= 5:
                return EpisodeRecord(
                    number=episode_number,
                    source="mal",
                    backend="jikan",
                    titles={"english": f"Episode {episode_number}"},
                )
            return None

        source.load_episode_page = load_page
        source.load_episode = load_episode
        episode_service = EpisodeService([source])
        segment_service = EpisodeSegmentService([])
        first = datetime(2026, 11, 6, 14, 0, tzinfo=timezone.utc)
        anime = AggregatedAnime(
            title="Ongoing",
            external_ids={"mal": "1"},
            episodes_total=12,
            episodes_aired=5,
            episode_release_schedule=[
                EpisodeReleaseProjection(
                    episode_number=number,
                    airs_at=first + timedelta(days=7 * (number - 6)),
                    estimated=number != 6,
                )
                for number in range(6, 13)
            ],
        )
        session = AnimeCardSession(anime=anime, owner_user_id=1)
        message = _CaptureMessage()
        context = SimpleNamespace(
            episode_service=episode_service,
            episode_segment_service=segment_service,
        )

        first_page_message = _CaptureMessage()
        with patch(
            "bots.telegram.card.features.episodes.get_app_context",
            return_value=context,
        ):
            await edit_episodes_view(
                first_page_message,
                "token",
                session,
                view_page=0,
                locale="ru",
                backend="jikan",
            )
            await edit_episodes_view(
                message,
                "token",
                session,
                view_page=5,
                locale="ru",
                backend="jikan",
            )

        first_keyboard = first_page_message.calls[0]["reply_markup"]
        first_buttons = [
            button for row in first_keyboard.inline_keyboard for button in row
        ]
        self.assertTrue(any(button.text == "1/12" for button in first_buttons))
        first_html = first_page_message.calls[0]["rich_message"].html or ""
        self.assertIn("Серия 1", first_html)
        self.assertNotIn("Серия 6:", first_html)

        self.assertEqual(session.episode_view_page, 5)
        self.assertEqual(len(message.calls), 1)
        call = message.calls[0]
        html = call["rich_message"].html or ""
        self.assertIn("Серия 6", html)
        self.assertIn("дата источника", html)
        self.assertNotIn("Серия 7:", html)
        self.assertNotIn("Серия 8:", html)

        keyboard = call["reply_markup"]
        flattened = [button for row in keyboard.inline_keyboard for button in row]
        self.assertTrue(any(button.text == "6/12" for button in flattened))
        callbacks = {
            button.callback_data for button in flattened if button.callback_data
        }
        self.assertIn("ap:token:jikan:4", callbacks)
        self.assertIn("ap:token:jikan:6", callbacks)

    def test_projection_text_is_scoped_to_requested_episode(self) -> None:
        first = datetime(2026, 11, 6, 14, 0, tzinfo=timezone.utc)
        anime = AggregatedAnime(
            title="Ongoing",
            episode_release_schedule=[
                EpisodeReleaseProjection(6, first, False),
                EpisodeReleaseProjection(7, first + timedelta(days=7), True),
            ],
        )
        rendered = _episode_release_projection_text(anime, 6, locale="ru")
        self.assertIn("Серия 6:", rendered)
        self.assertNotIn("Серия 7:", rendered)


if __name__ == "__main__":
    unittest.main()
