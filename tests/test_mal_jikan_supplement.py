from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, patch

from core.identity import AnimeIdentity
from search.providers.mal import MALSearchProvider
from sources.jikan import JIKAN_DISPLAY_NAME
from sources.mal import MALSource


class MALJikanSupplementTests(unittest.IsolatedAsyncioTestCase):
    def test_search_and_metadata_share_one_logical_mal_source_name(self) -> None:
        self.assertEqual(MALSearchProvider.name, MALSource.name)
        self.assertEqual(MALSource.name, JIKAN_DISPLAY_NAME)

    @staticmethod
    def _official_payload() -> dict:
        return {
            "id": 123,
            "title": "Example",
            "alternative_titles": {"en": "Example EN", "ja": "例"},
            "statistics": {"status": {"watching": 10, "completed": 20}},
        }

    async def test_jikan_fills_fields_missing_from_official_mal_api(self) -> None:
        source = MALSource()
        source._jikan.load_metadata_supplement = AsyncMock(
            return_value={
                "licensors": ["Sentai Filmworks"],
                "score_distribution": {10: 100, 9: 50},
            }
        )

        with patch("sources.mal._get_raw", new=AsyncMock(return_value=self._official_payload())):
            record = await source.get_details(AnimeIdentity({"mal": "123"}))

        self.assertIsNotNone(record)
        assert record is not None
        self.assertEqual(source.name, JIKAN_DISPLAY_NAME)
        self.assertEqual(record.source, JIKAN_DISPLAY_NAME)
        self.assertEqual(record.identity.external_ids, {"mal": "123"})
        self.assertEqual(record.licensors, ["Sentai Filmworks"])
        self.assertEqual(record.score_distribution, {10: 100, 9: 50})
        self.assertEqual(record.status_distribution, {"watching": 10, "completed": 20})

    async def test_jikan_failure_does_not_break_official_mal_metadata(self) -> None:
        source = MALSource()
        source._jikan.load_metadata_supplement = AsyncMock(
            side_effect=RuntimeError("local parser unavailable")
        )

        with patch("sources.mal._get_raw", new=AsyncMock(return_value=self._official_payload())):
            record = await source.get_details(AnimeIdentity({"mal": "123"}))

        self.assertIsNotNone(record)
        assert record is not None
        self.assertEqual(record.title if hasattr(record, "title") else record.titles["romaji"], "Example")
        self.assertEqual(record.licensors, [])
        self.assertEqual(record.score_distribution, {})

    async def test_lazy_people_are_delegated_to_jikan_backend(self) -> None:
        source = MALSource()
        expected_staff = [object()]
        expected_voices = [object()]
        source._jikan.load_staff = AsyncMock(return_value=expected_staff)
        source._jikan.load_voices = AsyncMock(return_value=expected_voices)
        identity = AnimeIdentity({"mal": "123"})

        self.assertIs(await source.load_staff(identity), expected_staff)
        self.assertIs(await source.load_voices(identity), expected_voices)
        source._jikan.load_staff.assert_awaited_once_with(identity)
        source._jikan.load_voices.assert_awaited_once_with(identity)


if __name__ == "__main__":
    unittest.main()
