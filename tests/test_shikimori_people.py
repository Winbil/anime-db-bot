from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, patch

from core.canonicalization import localize_role_token
from sources.shikimori import DETAIL_FIELDS, STAFF_QUERY
from sources.shikimori_people import _load_shikimori_voices, _rest_voice_credits, _voices_from_character_details
from sources.shikimori_people_runtime import ShikimoriPeopleRuntime


class ShikimoriPeopleTests(unittest.TestCase):
    def test_main_metadata_query_does_not_request_person_roles(self) -> None:
        self.assertNotIn("personRoles", DETAIL_FIELDS)
        self.assertIn("personRoles", STAFF_QUERY)

    def test_character_seyu_is_original_voice_link(self) -> None:
        voices = _voices_from_character_details([
            {
                "id": 10,
                "name": "Rimuru Tempest",
                "russian": "Римуру Темпест",
                "seyu": [
                    {
                        "id": 20,
                        "name": "Miho Okasaki",
                        "russian": "Михо Окасаки",
                        "image": {"original": "/system/people/original/20.jpg"},
                    }
                ],
            }
        ])

        self.assertEqual(len(voices), 1)
        self.assertEqual(voices[0].external_ids["shikimori"], "20")
        self.assertEqual(voices[0].roles, ["voice_of::Rimuru Tempest"])
        self.assertEqual(
            localize_role_token(voices[0].roles[0], locale="ru"),
            "Озвучка: Rimuru Tempest",
        )
        self.assertEqual(
            localize_role_token(voices[0].roles[0], locale="en"),
            "Voice: Rimuru Tempest",
        )
        self.assertTrue(voices[0].portraits["Shikimori"][0].startswith("https://"))

    def test_same_seiyuu_across_characters_is_coalesced(self) -> None:
        voices = _voices_from_character_details([
            {
                "name": "Character A",
                "seyu": [{"id": 20, "name": "Voice Person", "image": {}}],
            },
            {
                "name": "Character B",
                "seyu": [{"id": 20, "name": "Voice Person", "image": {}}],
            },
        ])

        self.assertEqual(len(voices), 1)
        self.assertEqual(
            voices[0].roles,
            ["voice_of::Character A", "voice_of::Character B"],
        )

    def test_smoke_compatibility_helper_uses_same_parser(self) -> None:
        voices = _rest_voice_credits([
            {
                "person": {"id": 1, "name": "Test Seiyuu", "image": {}},
                "character": {"id": 2, "name": "Test Character"},
            }
        ])

        self.assertEqual(len(voices), 1)
        self.assertEqual(voices[0].roles, ["voice_of::Test Character"])


class ShikimoriPeopleRuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def test_voice_cache_is_scoped_to_people_runtime(self) -> None:
        first = ShikimoriPeopleRuntime()
        second = ShikimoriPeopleRuntime()

        with (
            patch("sources.shikimori_people._rest_anime_roles", new=AsyncMock(return_value=[])) as load_roles,
            patch("sources.shikimori_people._refresh_people", new=AsyncMock(return_value=None)),
        ):
            await _load_shikimori_voices("37430", runtime=first)
            await _load_shikimori_voices("37430", runtime=first)
            await _load_shikimori_voices("37430", runtime=second)

        self.assertEqual(load_roles.await_count, 2)


if __name__ == "__main__":
    unittest.main()
