from __future__ import annotations

import unittest

from bots.telegram.card.trailers import _source_keyboard, _trailer_text
from core.identity import AnimeIdentity
from core.models import TrailerRecord
from services.trailers import TrailerService
from sources.trailers import _anilist_trailers, _shikimori_trailers


class TrailerParsingTests(unittest.TestCase):
    def test_anilist_youtube_trailer_is_normalized(self) -> None:
        items = _anilist_trailers({
            "id": "abc123",
            "site": "youtube",
            "thumbnail": "http://img.example/trailer.jpg",
        })

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].source, "anilist")
        self.assertEqual(items[0].backend, "anilist")
        self.assertEqual(items[0].url, "https://www.youtube.com/watch?v=abc123")
        self.assertEqual(items[0].embed_url, "https://www.youtube.com/embed/abc123")
        self.assertEqual(items[0].thumbnail, "https://img.example/trailer.jpg")

    def test_shikimori_keeps_only_promotional_video_kinds(self) -> None:
        items = _shikimori_trailers([
            {
                "url": "https://youtu.be/pv",
                "image_url": "http://img.youtube.com/vi/pv/hqdefault.jpg",
                "player_url": "http://youtube.com/embed/pv",
                "name": "PV1",
                "kind": "pv",
                "hosting": "youtube",
            },
            {
                "url": "https://youtu.be/cm",
                "name": "CM1",
                "kind": "cm",
                "hosting": "youtube",
            },
            {
                "url": "https://youtu.be/op",
                "name": "Opening",
                "kind": "op",
                "hosting": "youtube",
            },
            {
                "url": "https://youtu.be/preview",
                "name": "Episode 1 preview",
                "kind": "episode_preview",
                "hosting": "youtube",
            },
        ])

        self.assertEqual([item.title for item in items], ["PV1", "CM1"])
        self.assertEqual([item.kind for item in items], ["trailer", "commercial"])
        self.assertEqual(items[0].embed_url, "https://youtube.com/embed/pv")
        self.assertTrue(items[0].thumbnail.startswith("https://"))

    def test_shikimori_repairs_duplicated_scheme_in_real_world_video_url(self) -> None:
        items = _shikimori_trailers([{
            "url": "https:// https://youtu.be/aJHwReyz-os",
            "image_url": "http://img.youtube.com/vi/aJHwReyz-os/hqdefault.jpg",
            "player_url": "http://youtube.com/embed/aJHwReyz-os",
            "name": "Дельта, Эпсилон, Дзета, Эта",
            "kind": "character_trailer",
            "hosting": "youtube",
        }])

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].url, "https://youtu.be/aJHwReyz-os")
        self.assertEqual(items[0].embed_url, "https://youtube.com/embed/aJHwReyz-os")
        self.assertEqual(
            items[0].thumbnail,
            "https://img.youtube.com/vi/aJHwReyz-os/hqdefault.jpg",
        )


class TrailerUiTests(unittest.TestCase):
    def test_source_view_renders_type_platform_and_open_buttons(self) -> None:
        items = [
            TrailerRecord(
                source="mal",
                backend="jikan",
                title="PV 1",
                kind="trailer",
                hosting="YouTube",
                url="https://www.youtube.com/watch?v=abc",
            ),
            TrailerRecord(
                source="mal",
                backend="jikan",
                title="CM 1",
                kind="commercial",
                hosting="YouTube",
                url="https://www.youtube.com/watch?v=def",
            ),
        ]
        content = _trailer_text(
            "MAL (MyAnimeList) / Jikan",
            items,
            offset=0,
            locale="ru",
        )
        keyboard = _source_keyboard(
            "token",
            ["MAL (MyAnimeList) / Jikan"],
            0,
            items,
            offset=0,
            page=0,
            page_count=1,
            locale="ru",
        )

        self.assertIn("Трейлеры — MAL (MyAnimeList) / Jikan", content)
        self.assertIn("Тип: Трейлер / PV", content)
        self.assertIn("Тип: Рекламный ролик", content)
        self.assertIn("Площадка: YouTube", content)
        self.assertEqual(keyboard.inline_keyboard[0][0].url, items[0].url)
        self.assertEqual(keyboard.inline_keyboard[1][0].url, items[1].url)

    def test_second_page_navigation_preserves_source_and_page(self) -> None:
        items = [
            TrailerRecord(
                source="shikimori",
                backend="shikimori",
                title=f"PV {index}",
                url=f"https://youtu.be/video{index}",
            )
            for index in range(6, 11)
        ]
        keyboard = _source_keyboard(
            "token",
            ["Shikimori", "AniList", "MAL (MyAnimeList) / Jikan"],
            0,
            items,
            offset=5,
            page=1,
            page_count=2,
            locale="ru",
        )

        nav = keyboard.inline_keyboard[len(items)]
        self.assertEqual(nav[0].callback_data, "at:token:0:0")
        self.assertEqual(nav[1].callback_data, "noop")
        self.assertEqual(nav[1].text, "2/2")
        for row in keyboard.inline_keyboard[:len(items)]:
            self.assertTrue((row[0].url or "").startswith("https://"))


class _FakeTrailerSource:
    def __init__(
        self,
        source_key: str,
        display_name: str,
        *,
        items: list[TrailerRecord] | None = None,
        error: Exception | None = None,
    ) -> None:
        self.name = display_name + "Backend"
        self.display_name = display_name
        self.source_key = source_key
        self.backend_key = source_key
        self.items = list(items or [])
        self.error = error
        self.calls = 0

    async def load_trailers(self, identity: AnimeIdentity) -> list[TrailerRecord]:
        self.calls += 1
        if self.error is not None:
            raise self.error
        return list(self.items)


class TrailerServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_only_sources_with_confirmed_identity_are_called(self) -> None:
        anilist = _FakeTrailerSource(
            "anilist",
            "AniList",
            items=[TrailerRecord(
                source="anilist",
                backend="anilist",
                url="https://example.invalid/trailer",
            )],
        )
        shikimori = _FakeTrailerSource("shikimori", "Shikimori")
        service = TrailerService((anilist, shikimori))

        result = await service.load(AnimeIdentity({"anilist": "10"}))

        self.assertEqual(anilist.calls, 1)
        self.assertEqual(shikimori.calls, 0)
        self.assertIn("AniList", result.by_source)

    async def test_one_failed_source_does_not_hide_other_trailers(self) -> None:
        good = _FakeTrailerSource(
            "anilist",
            "AniList",
            items=[TrailerRecord(
                source="anilist",
                backend="anilist",
                url="https://example.invalid/trailer",
            )],
        )
        bad = _FakeTrailerSource(
            "mal",
            "MAL (MyAnimeList) / Jikan",
            error=RuntimeError("parser unavailable"),
        )
        service = TrailerService((good, bad))

        result = await service.load(AnimeIdentity({"anilist": "10", "mal": "20"}))

        self.assertIn("AniList", result.by_source)
        self.assertIn("MAL (MyAnimeList) / Jikan", result.errors)


if __name__ == "__main__":
    unittest.main()
