from __future__ import annotations

import unittest

from core.capabilities import SourceCapability, descriptor_for, source_keys_with
from core.source_keys import SourceKey, normalize_source_key
from search.registry import DEFAULT_SEARCH_PROVIDER_KEYS


class SourceCatalogTests(unittest.TestCase):
    def test_source_key_is_string_compatible_and_normalized(self) -> None:
        self.assertEqual(SourceKey.MAL, "mal")
        self.assertEqual(normalize_source_key(" AniList "), SourceKey.ANILIST)
        with self.assertRaises(ValueError):
            normalize_source_key("jikan")

    def test_jikan_is_not_an_identity_source(self) -> None:
        self.assertNotIn("jikan", {key.value for key in SourceKey})

    def test_fast_search_comes_from_declared_search_capabilities(self) -> None:
        self.assertEqual(
            DEFAULT_SEARCH_PROVIDER_KEYS,
            (SourceKey.SHIKIMORI, SourceKey.MAL, SourceKey.ANILIST),
        )
        self.assertEqual(
            source_keys_with(SourceCapability.SEARCH),
            DEFAULT_SEARCH_PROVIDER_KEYS,
        )

    def test_anidb_is_optional_metadata_and_episode_source(self) -> None:
        descriptor = descriptor_for(SourceKey.ANIDB)
        self.assertTrue(descriptor.optional)
        self.assertTrue(descriptor.supports(SourceCapability.METADATA))
        self.assertTrue(descriptor.supports(SourceCapability.EPISODES))
        self.assertFalse(descriptor.supports(SourceCapability.SEARCH))


if __name__ == "__main__":
    unittest.main()
