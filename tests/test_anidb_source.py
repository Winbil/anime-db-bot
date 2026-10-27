from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core.identity import AnimeIdentity
from sources.anidb import AniDBSource


ANIDB_XML = '''<?xml version="1.0" encoding="UTF-8"?>
<anime id="10" restricted="false">
  <type>TV Series</type>
  <episodecount>2</episodecount>
  <startdate>2024-01-01</startdate>
  <enddate>2024-01-08</enddate>
  <titles>
    <title xml:lang="x-jat" type="main">Example Anime</title>
    <title xml:lang="en" type="official">Example</title>
    <title xml:lang="ja" type="official">例</title>
    <title xml:lang="ru" type="official">Пример</title>
    <title xml:lang="en" type="syn">Example Alias</title>
  </titles>
  <creators>
    <name id="90" type="Direction">Director Person</name>
  </creators>
  <description>Example description</description>
  <ratings><permanent count="100">8.5</permanent></ratings>
  <picture>poster.jpg</picture>
  <resources>
    <resource type="2"><externalentity><identifier>20</identifier></externalentity></resource>
    <resource type="1"><externalentity><identifier>30</identifier></externalentity></resource>
  </resources>
  <characters>
    <character id="100" type="main character in">
      <name>Hero</name>
      <picture>hero.jpg</picture>
      <seiyuu id="200" picture="voice.jpg">Voice Person</seiyuu>
    </character>
    <character id="101" type="secondary cast in">
      <name>Friend</name>
      <picture>friend.jpg</picture>
    </character>
  </characters>
  <episodes>
    <episode id="1000">
      <epno type="1">1</epno>
      <length>24</length>
      <airdate>2024-01-01</airdate>
      <rating votes="10">8.1</rating>
      <title xml:lang="en">Start</title>
      <title xml:lang="x-jat">Hajimari</title>
      <title xml:lang="ja">始まり</title>
    </episode>
    <episode id="1001">
      <epno type="1">2</epno>
      <length>24</length>
      <airdate>2024-01-08</airdate>
      <rating votes="10">8.2</rating>
      <title xml:lang="en">Next</title>
    </episode>
    <episode id="1099">
      <epno type="2">S1</epno>
      <length>5</length>
      <title xml:lang="en">Special</title>
    </episode>
  </episodes>
</anime>
'''.encode("utf-8")


class AniDBSourceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.cache = Path(self.temp.name)
        (self.cache / "10.xml").write_bytes(ANIDB_XML)
        self.env = patch.dict(os.environ, {
            "ANIDB_CLIENT": "animedbbottest",
            "ANIDB_CLIENT_VERSION": "1",
            "ANIDB_CACHE_DIR": str(self.cache),
            "ANIDB_CACHE_TTL_SECONDS": "86400",
        })
        self.env.start()
        self.source = AniDBSource()
        self.identity = AnimeIdentity({"anidb": "10", "mal": "20"})

    async def asyncTearDown(self) -> None:
        self.env.stop()
        self.temp.cleanup()

    async def test_metadata_maps_titles_direct_mal_edge_staff_and_poster(self) -> None:
        record = await self.source.get_details(self.identity)
        self.assertIsNotNone(record)
        assert record is not None
        self.assertEqual(record.source_id, "10")
        self.assertEqual(record.external_ids["anidb"], "10")
        self.assertEqual(record.external_ids["mal"], "20")
        self.assertEqual(record.external_ids["ann"], "30")
        self.assertEqual(record.titles["romaji"], "Example Anime")
        self.assertEqual(record.titles["russian"], "Пример")
        self.assertIn("Example Alias", record.synonyms)
        self.assertEqual(record.kind, "tv")
        self.assertEqual(record.episodes_total, 2)
        self.assertAlmostEqual(record.score or 0, 8.5)
        self.assertTrue(record.posters[0].startswith("https://cdn-eu.anidb.net/images/main/"))
        self.assertEqual(record.staff[0].external_ids, {"anidb": "90"})

    async def test_characters_and_japanese_voice_actor_are_lazy_from_cached_xml(self) -> None:
        characters = await self.source.load_characters(self.identity)
        voices = await self.source.load_voices(self.identity)
        self.assertEqual([item.name for item in characters], ["Hero", "Friend"])
        self.assertEqual(characters[0].role, "main")
        self.assertEqual(characters[1].role, "supporting")
        self.assertEqual(voices[0].name, "Voice Person")
        self.assertEqual(voices[0].external_ids, {"anidb": "200"})
        self.assertTrue(voices[0].portraits["AniDB"][0].endswith("voice.jpg"))

    async def test_regular_episode_page_and_detail_use_anidb_backend(self) -> None:
        page = await self.source.load_episode_page(self.identity, page=1)
        self.assertEqual([item.number for item in page.items], [1, 2])
        self.assertFalse(page.has_next)
        self.assertEqual(page.items[0].backend, "anidb")
        self.assertEqual(page.items[0].duration_seconds, 1440)
        self.assertEqual(page.items[0].titles["romaji"], "Hajimari")
        detail = await self.source.load_episode(self.identity, 2)
        self.assertIsNotNone(detail)
        assert detail is not None
        self.assertEqual(detail.urls["AniDB"], "https://anidb.net/episode/1001")

    async def test_missing_anidb_identity_is_noop(self) -> None:
        self.assertIsNone(await self.source.get_details(AnimeIdentity({"mal": "20"})))
        self.assertEqual(await self.source.load_characters(AnimeIdentity({"mal": "20"})), [])


if __name__ == "__main__":
    unittest.main()
