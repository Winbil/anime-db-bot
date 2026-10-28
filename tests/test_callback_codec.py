from __future__ import annotations

import unittest

from bots.telegram.callbacks import (
    EpisodeDetailCallback,
    IndexedCallback,
    SectionSourceCallback,
    ViewCallback,
)


class CallbackCodecTests(unittest.TestCase):
    def test_view_round_trip_preserves_wire_format(self) -> None:
        value = ViewCallback("abc", "voices", 12)
        self.assertEqual(value.encode(), "av:abc:voices:12")
        self.assertEqual(ViewCallback.parse(value.encode()), value)

    def test_section_source_round_trip_preserves_wire_format(self) -> None:
        value = SectionSourceCallback("abc", "staff", 2, 9)
        self.assertEqual(value.encode(), "as:abc:staff:2:9")
        self.assertEqual(SectionSourceCallback.parse(value.encode()), value)

    def test_indexed_codec_supports_existing_namespaces(self) -> None:
        value = IndexedCallback("ac", "abc", 3, 4)
        self.assertEqual(value.encode(), "ac:abc:3:4")
        self.assertEqual(IndexedCallback.parse(value.encode(), prefix="ac"), value)
        self.assertIsNone(IndexedCallback.parse(value.encode(), prefix="at"))

    def test_episode_detail_parser_accepts_legacy_and_current_payloads(self) -> None:
        self.assertEqual(
            EpisodeDetailCallback.parse("ae:abc:7:2"),
            EpisodeDetailCallback("abc", 0, 7, 2),
        )
        current = EpisodeDetailCallback("abc", 1, 7, 2)
        self.assertEqual(current.encode(), "ae:abc:1:7:2")
        self.assertEqual(EpisodeDetailCallback.parse(current.encode()), current)

    def test_invalid_or_oversized_callbacks_are_rejected(self) -> None:
        self.assertIsNone(ViewCallback.parse("av:abc:voices:nope"))
        with self.assertRaises(ValueError):
            ViewCallback("x" * 60, "voices", 0).encode()
        with self.assertRaises(ValueError):
            ViewCallback("bad:token", "voices", 0).encode()


if __name__ == "__main__":
    unittest.main()
