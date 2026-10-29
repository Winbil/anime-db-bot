from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, patch

from core.identity import AnimeIdentity
from core.source_keys import SourceKey
from sources.providers.shikimori import ShikimoriSource


class ShikimoriIdentitySourceTests(unittest.IsolatedAsyncioTestCase):
    async def test_own_id_is_sufficient_without_mal_identity(self) -> None:
        payload = {
            "id": "48316",
            "malId": 48316,
            "name": "Example",
            "synonyms": [],
            "genres": [],
            "studios": [],
            "licensors": [],
            "poster": {},
            "statusesStats": [],
            "scoresStats": [],
        }
        source = ShikimoriSource()
        with patch(
            "sources.providers.shikimori._get_raw",
            new=AsyncMock(return_value=payload),
        ) as loader:
            record = await source.get_details(AnimeIdentity({"shikimori": "48316"}))

        self.assertEqual(source.source_key, SourceKey.SHIKIMORI)
        self.assertIsNotNone(record)
        assert record is not None
        self.assertEqual(record.source_id, "48316")
        self.assertEqual(record.external_ids["shikimori"], "48316")
        self.assertEqual(record.external_ids["mal"], "48316")
        loader.assert_awaited_once_with("48316", source.settings)

    async def test_missing_shikimori_id_does_not_guess_from_mal_number(self) -> None:
        source = ShikimoriSource()
        with patch("sources.providers.shikimori._get_raw", new=AsyncMock()) as loader:
            record = await source.get_details(AnimeIdentity({"mal": "48316"}))

        self.assertIsNone(record)
        loader.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
