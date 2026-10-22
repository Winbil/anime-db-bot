from __future__ import annotations

import unittest

from core.identity import AnimeIdentity


class AnimeIdentityTests(unittest.TestCase):
    def test_source_keys_are_normalized_without_selecting_primary_id(self) -> None:
        identity = AnimeIdentity({" MAL ": "123", "AniList": "456"})

        self.assertEqual(identity.get("mal"), "123")
        self.assertEqual(identity.get("ANILIST"), "456")
        self.assertEqual(
            identity.fingerprint(),
            (("anilist", "456"), ("mal", "123")),
        )

    def test_any_shared_non_conflicting_external_id_confirms_match(self) -> None:
        left = AnimeIdentity({"anilist": "10", "mal": "20"})
        right = AnimeIdentity({"anilist": "10", "shikimori": "30"})

        self.assertTrue(left.matches(right))
        self.assertEqual(left.shared_ids(right), {"anilist": "10"})

    def test_conflicting_same_source_id_prevents_match(self) -> None:
        left = AnimeIdentity({"anilist": "10", "mal": "20"})
        right = AnimeIdentity({"anilist": "11", "mal": "20"})

        self.assertFalse(left.matches(right))
        self.assertEqual(left.conflicting_ids(right), {"anilist": ("10", "11")})

    def test_merge_missing_never_overwrites_conflicting_evidence(self) -> None:
        identity = AnimeIdentity({"mal": "20"})

        conflicts = identity.merge_missing({"mal": "21", "shikimori": "30"})

        self.assertEqual(identity.external_ids, {"mal": "20", "shikimori": "30"})
        self.assertEqual(conflicts, {"mal": ("20", "21")})

    def test_empty_identity_is_valid_but_not_matchable(self) -> None:
        empty = AnimeIdentity()
        other = AnimeIdentity({"anilist": "10"})

        self.assertTrue(empty.is_empty())
        self.assertFalse(empty.matches(other))


if __name__ == "__main__":
    unittest.main()
