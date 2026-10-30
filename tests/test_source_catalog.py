from __future__ import annotations

import unittest

from core.capabilities import SourceCapability
from core.source_keys import SourceKey, normalize_source_key
from search.registry import DEFAULT_SEARCH_PROVIDER_KEYS
from sources.runtime.catalog import (
    SOURCE_CATALOG,
    descriptor_for,
    get_episode_sources,
    get_trailer_sources,
    source_keys_with,
)


class SourceCatalogTests(unittest.TestCase):
    def test_source_key_is_string_compatible_and_normalized(self) -> None:
        self.assertEqual(SourceKey.MAL, "mal")
        self.assertEqual(normalize_source_key(" AniList "), SourceKey.ANILIST)
        self.assertEqual(normalize_source_key(" AniSearch "), SourceKey.ANISEARCH)
        with self.assertRaises(ValueError):
            normalize_source_key("jikan")

    def test_jikan_is_not_an_identity_source(self) -> None:
        self.assertNotIn("jikan", {key.value for key in SourceKey})

    def test_fast_search_comes_from_declared_search_capabilities(self) -> None:
        self.assertEqual(
            DEFAULT_SEARCH_PROVIDER_KEYS,
            (SourceKey.SHIKIMORI, SourceKey.MAL, SourceKey.ANILIST, SourceKey.KITSU),
        )
        self.assertEqual(
            source_keys_with(SourceCapability.SEARCH),
            DEFAULT_SEARCH_PROVIDER_KEYS,
        )

    def test_skipdb_provider_is_dormant_and_not_runtime_registered(self) -> None:
        episode_keys = [source.backend_key for source in get_episode_sources()]
        self.assertNotIn("skipdb", episode_keys)
        with self.assertRaises(KeyError):
            descriptor_for(SourceKey.IMDB)

    def test_anidb_is_optional_metadata_and_episode_source(self) -> None:
        descriptor = descriptor_for(SourceKey.ANIDB)
        self.assertTrue(descriptor.optional)
        self.assertTrue(descriptor.supports(SourceCapability.METADATA))
        self.assertTrue(descriptor.supports(SourceCapability.EPISODES))
        self.assertFalse(descriptor.supports(SourceCapability.SEARCH))

    def test_anisearch_is_identity_native_but_not_a_search_provider(self) -> None:
        descriptor = descriptor_for(SourceKey.ANISEARCH)
        self.assertTrue(descriptor.supports(SourceCapability.METADATA))
        self.assertTrue(descriptor.supports(SourceCapability.PEOPLE))
        self.assertTrue(descriptor.supports(SourceCapability.CHARACTERS))
        self.assertTrue(descriptor.supports(SourceCapability.EPISODES))
        self.assertTrue(descriptor.supports(SourceCapability.POPULARITY))
        self.assertTrue(descriptor.supports(SourceCapability.DESCRIPTION))
        self.assertFalse(descriptor.supports(SourceCapability.SEARCH))
        self.assertFalse(descriptor.supports(SourceCapability.TRAILERS))
        self.assertFalse(descriptor.supports(SourceCapability.SCREENSHOTS))

    def test_lazy_section_capabilities_are_declared(self) -> None:
        shikimori = descriptor_for(SourceKey.SHIKIMORI)
        mal = descriptor_for(SourceKey.MAL)
        anilist = descriptor_for(SourceKey.ANILIST)
        anidb = descriptor_for(SourceKey.ANIDB)
        kitsu = descriptor_for(SourceKey.KITSU)

        self.assertTrue(shikimori.supports(SourceCapability.SCREENSHOTS))
        self.assertTrue(shikimori.supports(SourceCapability.POPULARITY))
        self.assertTrue(shikimori.supports(SourceCapability.DESCRIPTION))
        self.assertTrue(mal.supports(SourceCapability.POPULARITY))
        self.assertTrue(mal.supports(SourceCapability.DESCRIPTION))
        self.assertTrue(anilist.supports(SourceCapability.POPULARITY))
        self.assertTrue(anilist.supports(SourceCapability.DESCRIPTION))
        self.assertTrue(anidb.supports(SourceCapability.DESCRIPTION))
        self.assertTrue(kitsu.supports(SourceCapability.SEARCH))
        self.assertTrue(kitsu.supports(SourceCapability.METADATA))
        self.assertTrue(kitsu.supports(SourceCapability.EPISODES))
        self.assertTrue(kitsu.supports(SourceCapability.TRAILERS))
        self.assertTrue(kitsu.supports(SourceCapability.POPULARITY))
        self.assertTrue(kitsu.supports(SourceCapability.DESCRIPTION))
        self.assertFalse(kitsu.supports(SourceCapability.PEOPLE))
        self.assertFalse(kitsu.supports(SourceCapability.CHARACTERS))

    def test_declared_runtime_capabilities_have_factories(self) -> None:
        for registration in SOURCE_CATALOG:
            with self.subTest(source=registration.key):
                if registration.supports(SourceCapability.SEARCH):
                    self.assertIsNotNone(registration.search_factory)
                if registration.supports(SourceCapability.METADATA):
                    self.assertIsNotNone(registration.metadata_factory)
                if registration.supports(SourceCapability.TRAILERS):
                    self.assertTrue(registration.trailer_backends)
                if registration.supports(SourceCapability.EPISODES):
                    self.assertTrue(registration.episode_backends)

    def test_backend_order_preserves_existing_ui_contract(self) -> None:
        trailer_keys = [source.backend_key for source in get_trailer_sources()]
        self.assertEqual(trailer_keys, ["shikimori", "anilist", "jikan", "kitsu"])
        episode_keys = [source.backend_key for source in get_episode_sources()]
        self.assertEqual(episode_keys[0], "jikan")
        self.assertIn("anisearch", episode_keys)
        self.assertLess(episode_keys.index("jikan"), episode_keys.index("anisearch"))


if __name__ == "__main__":
    unittest.main()
