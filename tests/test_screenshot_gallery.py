from __future__ import annotations

import unittest
from unittest.mock import AsyncMock

from bots.telegram.card.features.screenshots import (
    SCREENSHOTS_PER_PAGE,
    edit_screenshots_view,
    screenshot_pages,
    screenshot_rich_message,
)
from core.models import AggregatedAnime


class ScreenshotGalleryTests(unittest.IsolatedAsyncioTestCase):
    def _sample(self, count: int = 30) -> AggregatedAnime:
        return AggregatedAnime(
            title="Screenshot Test",
            sources=["Shikimori"],
            screenshots_by_source={
                "Shikimori": [
                    f"https://example.invalid/screenshot-{index}.jpg"
                    for index in range(1, count + 1)
                ]
            },
        )

    def test_large_gallery_is_bounded_to_eight_images_per_rich_page(self) -> None:
        anime = self._sample(30)
        pages = screenshot_pages(anime)
        self.assertEqual([len(page) for page in pages], [8, 8, 8, 6])
        self.assertEqual(len(pages[0]), SCREENSHOTS_PER_PAGE)

        first = screenshot_rich_message(anime, page=0, locale="ru").html or ""
        second = screenshot_rich_message(anime, page=1, locale="ru").html or ""
        self.assertIn("screenshot-1.jpg", first)
        self.assertIn("screenshot-8.jpg", first)
        self.assertNotIn("screenshot-9.jpg", first)
        self.assertIn("screenshot-9.jpg", second)
        self.assertNotIn("screenshot-1.jpg", second)

    async def test_all_and_source_views_both_render_slideshow_immediately(self) -> None:
        anime = self._sample(17)
        message = AsyncMock()

        await edit_screenshots_view(
            message,
            "card-token",
            anime,
            source_key=None,
            page=0,
            locale="ru",
        )
        all_html = message.edit_text.await_args.kwargs["rich_message"].html or ""
        self.assertIn("<tg-slideshow>", all_html)
        self.assertIn("screenshot-1.jpg", all_html)

        message.reset_mock()
        await edit_screenshots_view(
            message,
            "card-token",
            anime,
            source_key="shikimori",
            page=0,
            locale="ru",
        )
        source_html = message.edit_text.await_args.kwargs["rich_message"].html or ""
        self.assertIn("<tg-slideshow>", source_html)
        self.assertIn("Скриншоты — Shikimori", source_html)
        self.assertIn("screenshot-1.jpg", source_html)

    async def test_source_page_navigation_keeps_the_gallery(self) -> None:
        anime = self._sample(17)
        message = AsyncMock()
        await edit_screenshots_view(
            message,
            "card-token",
            anime,
            source_key="shikimori",
            page=1,
            locale="ru",
        )
        html = message.edit_text.await_args.kwargs["rich_message"].html or ""
        self.assertIn("screenshot-9.jpg", html)
        self.assertNotIn("screenshot-1.jpg", html)


if __name__ == "__main__":
    unittest.main()
