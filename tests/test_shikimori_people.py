from __future__ import annotations

import unittest

from sources.shikimori_people import _rest_voice_credits, _voices_from_character_details


class ShikimoriPeopleTests(unittest.TestCase):
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
        self.assertEqual(voices[0].roles, ["Озвучка: Римуру Темпест"])
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
            ["Озвучка: Character A", "Озвучка: Character B"],
        )

    def test_smoke_compatibility_helper_uses_same_parser(self) -> None:
        voices = _rest_voice_credits([
            {
                "person": {"id": 1, "name": "Test Seiyuu", "image": {}},
                "character": {"id": 2, "name": "Test Character"},
            }
        ])

        self.assertEqual(len(voices), 1)
        self.assertEqual(voices[0].roles, ["Озвучка: Test Character"])


if __name__ == "__main__":
    unittest.main()
