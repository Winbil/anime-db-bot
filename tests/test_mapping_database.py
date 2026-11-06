from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from core.identity import AnimeIdentity
from mappings.resolver import (
    MappingResolver,
    delete_mapping_override,
    list_mapping_override_history,
    list_mapping_overrides,
    set_mapping_override,
)
from tests.mapping_fixtures import create_runtime_mapping_db


class MappingResolverTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.path = self.root / "mappings.db"

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_direct_mapping_is_resolved_from_runtime_database(self) -> None:
        create_runtime_mapping_db(
            self.path,
            [("mal", "100", "anidb", "200")],
        )
        resolver = MappingResolver(self.path)
        self.assertEqual(
            resolver.resolve(AnimeIdentity({"mal": "100"})),
            {"anidb": "200"},
        )

    def test_amdb_anchor_uses_only_agreeing_known_provider_ids(self) -> None:
        create_runtime_mapping_db(
            self.path,
            [
                ("mal", "100", "anilist", "200"),
                ("mal", "101", "anilist", "201"),
            ],
            anchors={
                ("mal", "100"): 18472,
                ("anilist", "200"): 18472,
                ("mal", "101"): 25000,
                ("anilist", "201"): 25000,
            },
        )
        resolver = MappingResolver(self.path)
        self.assertEqual(
            resolver.anchor_for(AnimeIdentity({"mal": "100"})),
            "amdb:18472",
        )
        self.assertEqual(
            resolver.anchor_for(
                AnimeIdentity({"mal": "100", "anilist": "200", "imdb": "unknown"})
            ),
            "amdb:18472",
        )
        self.assertIsNone(
            resolver.anchor_for(AnimeIdentity({"mal": "100", "anilist": "201"}))
        )
        self.assertIsNone(
            resolver.anchor_for(AnimeIdentity({"mal": "999"}))
        )

    def test_all_ids_use_entity_membership_not_transitive_mapping_edges(self) -> None:
        create_runtime_mapping_db(
            self.path,
            [
                ("mal", "100", "anilist", "200"),
                ("anilist", "200", "anidb", "300"),
                ("anidb", "300", "kitsu", "400"),
            ],
            anchors={
                ("mal", "100"): 18472,
                ("anilist", "200"): 18472,
                ("anidb", "300"): 25000,
                ("kitsu", "400"): 25000,
            },
            redirects={9000: 18472},
        )
        resolver = MappingResolver(self.path)
        self.assertEqual(
            resolver.ids_for_anchor("amdb:9000"),
            {"anilist": ("200",), "mal": ("100",)},
        )
        self.assertEqual(
            resolver.ids_for_anchor("amdb:18472"),
            {"anilist": ("200",), "mal": ("100",)},
        )
        self.assertEqual(
            resolver.ids_for_anchor("amdb:25000"),
            {"anidb": ("300",), "kitsu": ("400",)},
        )
        self.assertEqual(resolver.ids_for_anchor("mal:100"), {})
        self.assertEqual(resolver.ids_for_anchor("amdb:999999"), {})

    def test_amdb_anchor_is_optional_for_older_mapping_schemas(self) -> None:
        create_runtime_mapping_db(
            self.path,
            [("mal", "100", "anilist", "200")],
        )
        self.assertIsNone(
            MappingResolver(self.path).anchor_for(AnimeIdentity({"mal": "100"}))
        )

    def test_directional_conflict_suppresses_only_ambiguous_route(self) -> None:
        create_runtime_mapping_db(
            self.path,
            [
                ("anidb", "200", "mal", "100"),
                ("anidb", "200", "mal", "101"),
            ],
            conflicts=[("anidb", "200", "mal", ["100", "101"])],
        )
        resolver = MappingResolver(self.path)
        self.assertEqual(resolver.resolve(AnimeIdentity({"anidb": "200"})), {})
        self.assertEqual(
            resolver.resolve(AnimeIdentity({"mal": "100"})),
            {"anidb": "200"},
        )

    def test_resolver_never_walks_transitive_chain(self) -> None:
        create_runtime_mapping_db(
            self.path,
            [
                ("mal", "100", "anidb", "200"),
                ("anidb", "200", "kitsu", "300"),
            ],
        )
        resolver = MappingResolver(self.path)
        self.assertEqual(
            resolver.resolve(AnimeIdentity({"mal": "100"})),
            {"anidb": "200"},
        )

    def test_confirmed_identity_is_never_overwritten(self) -> None:
        create_runtime_mapping_db(
            self.path,
            [("mal", "100", "anilist", "300")],
        )
        resolver = MappingResolver(self.path)
        self.assertEqual(
            resolver.resolve(AnimeIdentity({"mal": "100", "anilist": "999"})),
            {},
        )

    def test_accept_and_reject_overrides_remain_local_to_bot_runtime(self) -> None:
        create_runtime_mapping_db(
            self.path,
            [("mal", "100", "anidb", "200")],
        )
        resolver = MappingResolver(self.path)
        set_mapping_override(
            "mal",
            "100",
            "anidb",
            "201",
            action="accept",
            reason="verified correction",
            author="tester",
            path=self.path,
        )
        self.assertEqual(
            resolver.resolve(AnimeIdentity({"mal": "100"})),
            {"anidb": "201"},
        )
        current = list_mapping_overrides(self.path)
        self.assertEqual(len(current), 1)
        self.assertEqual(current[0].author, "tester")

        self.assertTrue(
            delete_mapping_override(
                "mal",
                "100",
                "anidb",
                "201",
                reason="superseded",
                author="tester2",
                path=self.path,
            )
        )
        self.assertEqual(
            resolver.resolve(AnimeIdentity({"mal": "100"})),
            {"anidb": "200"},
        )
        history = list_mapping_override_history(self.path)
        self.assertEqual([item.event for item in history], ["set", "delete"])
        self.assertEqual([item.author for item in history], ["tester", "tester2"])


if __name__ == "__main__":
    unittest.main()
