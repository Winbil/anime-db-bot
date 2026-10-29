from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, MagicMock

from core.identity import AnimeIdentity
from core.models import SearchCandidate, SearchPage
from mappings.resolver import MappingResolver
from services.identity.resolver import IdentityResolver


class IdentityResolverTests(unittest.IsolatedAsyncioTestCase):
    async def test_direct_mapping_and_live_shikimori_fallback_are_combined(
        self,
    ) -> None:
        mapping = MagicMock(spec=MappingResolver)
        mapping.resolve.return_value = {"anidb": "10"}
        provider = AsyncMock()
        provider.search = AsyncMock(
            return_value=SearchPage(
                items=[
                    SearchCandidate(
                        title="Example",
                        external_ids={"mal": "20", "shikimori": "30"},
                    )
                ],
                page=1,
                page_size=20,
                has_next=False,
            )
        )
        resolver = IdentityResolver(
            mapping_resolver=mapping,
            shikimori_provider=provider,
        )

        result = await resolver.enrich(AnimeIdentity({"mal": "20"}), ["Example"])

        self.assertEqual(
            result.external_ids,
            {"mal": "20", "anidb": "10", "shikimori": "30"},
        )
        mapping.resolve.assert_called_once()
        provider.search.assert_awaited_once_with("Example", page=1, limit=20)

    async def test_live_shikimori_resolution_is_cached_per_mal_id(self) -> None:
        mapping = MagicMock(spec=MappingResolver)
        mapping.resolve.return_value = {}
        provider = AsyncMock()
        provider.search = AsyncMock(
            return_value=SearchPage(
                items=[
                    SearchCandidate(
                        title="Example",
                        external_ids={"mal": "20", "shikimori": "30"},
                    )
                ],
                page=1,
                page_size=20,
                has_next=False,
            )
        )
        resolver = IdentityResolver(
            mapping_resolver=mapping,
            shikimori_provider=provider,
        )

        first = await resolver.enrich(AnimeIdentity({"mal": "20"}), ["Example"])
        second = await resolver.enrich(AnimeIdentity({"mal": "20"}), ["Other title"])

        self.assertEqual(first.get("shikimori"), "30")
        self.assertEqual(second.get("shikimori"), "30")
        self.assertEqual(provider.search.await_count, 1)


if __name__ == "__main__":
    unittest.main()
