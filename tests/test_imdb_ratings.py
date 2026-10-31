from __future__ import annotations

import gzip
import runpy
import sqlite3
import tempfile
import unittest
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch

from core.identity import AnimeIdentity
from core.models import AggregatedAnime
from core.settings import AppSettings
from mappings.resolver import MappingResolver
from services.media.imdb import IMDbRatingService
from sources.providers.imdb import IMDbRatingsSource, _sigv4_headers


class _Response:
    def __init__(self, body: dict[str, object]) -> None:
        self._body = body

    def json(self) -> dict[str, object]:
        return self._body


class IMDbRatingsTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.db_path = self.root / "imdb.sqlite3"

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _settings(self, **values: str):
        env = {
            "BOT_TOKEN": "x",
            "IMDB_RATINGS_DB_PATH": str(self.db_path),
            **values,
        }
        return AppSettings.from_env(env).sources

    def _write_db(self) -> None:
        with closing(sqlite3.connect(self.db_path)) as connection:
            connection.execute(
                "CREATE TABLE ratings(imdb_id TEXT PRIMARY KEY, rating REAL NOT NULL, votes INTEGER NOT NULL) WITHOUT ROWID"
            )
            connection.execute(
                "INSERT INTO ratings(imdb_id, rating, votes) VALUES ('tt1234567', 8.7, 123456)"
            )
            connection.commit()

    def _mapping_resolver(
        self,
        *,
        source_provider: str = "mal",
        source_id: str = "1",
        imdb_id: str = "tt1234567",
    ) -> MappingResolver:
        path = self.root / f"mapping-{source_provider}.db"
        with closing(sqlite3.connect(path)) as connection:
            connection.executescript(
                """
                CREATE TABLE edges(
                    a_provider TEXT NOT NULL,
                    a_id TEXT NOT NULL,
                    b_provider TEXT NOT NULL,
                    b_id TEXT NOT NULL,
                    status TEXT NOT NULL
                );
                CREATE TABLE conflicts(
                    source_provider TEXT NOT NULL,
                    source_id TEXT NOT NULL,
                    target_provider TEXT NOT NULL
                );
                CREATE TABLE mapping_overrides(
                    source_provider TEXT NOT NULL,
                    source_id TEXT NOT NULL,
                    target_provider TEXT NOT NULL,
                    target_id TEXT NOT NULL,
                    action TEXT NOT NULL,
                    reason TEXT NOT NULL DEFAULT ''
                );
                """
            )
            connection.execute(
                "INSERT INTO edges VALUES (?, ?, 'imdb', ?, 'accepted')",
                (source_provider, source_id, imdb_id),
            )
            connection.commit()
        return MappingResolver(path)

    async def test_local_backend_reads_only_confirmed_imdb_identity(self) -> None:
        self._write_db()
        source = IMDbRatingsSource(self._settings(IMDB_RATINGS_BACKEND="local"))
        rating = await source.load_rating(AnimeIdentity({"imdb": "tt1234567"}))
        self.assertIsNotNone(rating)
        assert rating is not None
        self.assertEqual(
            (rating.rating, rating.votes, rating.backend), (8.7, 123456, "local")
        )
        self.assertEqual(rating.url, "https://www.imdb.com/title/tt1234567/")
        self.assertIsNone(await source.load_rating(AnimeIdentity({"mal": "1"})))
        self.assertIsNone(await source.load_rating(AnimeIdentity({"imdb": "not-imdb"})))

    async def test_service_enriches_score_votes_consensus_and_link(self) -> None:
        self._write_db()
        service = IMDbRatingService(
            IMDbRatingsSource(self._settings(IMDB_RATINGS_BACKEND="local")),
            self._mapping_resolver(),
        )
        anime = AggregatedAnime(
            title="Example",
            external_ids={"mal": "1", "imdb": "tt9999999"},
            sources=["AniList"],
            scores={"AniList": 9.1},
            score_average=9.1,
            score_sources_count=1,
        )
        result = await service.enrich(anime)
        self.assertIsNotNone(result)
        self.assertEqual(anime.scores, {"AniList": 9.1, "IMDb": 8.7})
        self.assertEqual(anime.score_votes, {"IMDb": 123456})
        self.assertEqual(anime.score_average, 8.9)
        self.assertEqual(anime.score_sources_count, 2)
        self.assertEqual(anime.urls["IMDb"], "https://www.imdb.com/title/tt1234567/")
        self.assertNotIn("IMDb", anime.sources)

    async def test_service_rejects_imdb_id_available_only_through_non_anime_bridge(
        self,
    ) -> None:
        self._write_db()
        service = IMDbRatingService(
            IMDbRatingsSource(self._settings(IMDB_RATINGS_BACKEND="local")),
            self._mapping_resolver(
                source_provider="tmdb_tv",
                source_id="30991",
                imdb_id="tt1234567",
            ),
        )
        anime = AggregatedAnime(
            title="Cowboy Bebop",
            external_ids={
                "mal": "1",
                "tmdb_tv": "30991",
                "imdb": "tt1234567",
            },
        )
        self.assertIsNone(await service.enrich(anime))
        self.assertNotIn("IMDb", anime.scores)

    async def test_api_backend_parses_official_ratings_summary(self) -> None:
        source = IMDbRatingsSource(
            self._settings(
                IMDB_RATINGS_BACKEND="api",
                IMDB_API_KEY="api-key",
                IMDB_API_DATA_SET_ID="dataset",
                IMDB_API_REVISION_ID="revision",
                IMDB_API_ASSET_ID="asset",
                IMDB_AWS_ACCESS_KEY_ID="AKID",
                IMDB_AWS_SECRET_ACCESS_KEY="secret",
            )
        )
        response = _Response(
            {
                "data": {
                    "title": {
                        "ratingsSummary": {
                            "aggregateRating": 8.4,
                            "voteCount": 765432,
                        }
                    }
                }
            }
        )
        with (
            patch("sources.providers.imdb.wait_for_upstream", new=AsyncMock()) as wait,
            patch(
                "sources.providers.imdb.http_request",
                new=AsyncMock(return_value=response),
            ) as request,
        ):
            rating = await source.load_rating(AnimeIdentity({"imdb": "tt7654321"}))
        self.assertIsNotNone(rating)
        assert rating is not None
        self.assertEqual(
            (rating.rating, rating.votes, rating.backend), (8.4, 765432, "api")
        )
        wait.assert_awaited_once_with("imdb", "ratings")
        self.assertEqual(
            request.await_args.args[:3],
            ("imdb", "POST", source._settings.imdb_api_endpoint),
        )
        headers = request.await_args.kwargs["headers"]
        self.assertEqual(headers["x-api-key"], "api-key")
        self.assertIn("x-amzn-dataexchange-data-set-id", headers)
        self.assertTrue(headers["authorization"].startswith("AWS4-HMAC-SHA256 "))

    async def test_auto_backend_falls_back_to_local_when_api_fails(self) -> None:
        self._write_db()
        source = IMDbRatingsSource(
            self._settings(
                IMDB_RATINGS_BACKEND="auto",
                IMDB_API_KEY="api-key",
                IMDB_API_DATA_SET_ID="dataset",
                IMDB_API_REVISION_ID="revision",
                IMDB_API_ASSET_ID="asset",
                IMDB_AWS_ACCESS_KEY_ID="AKID",
                IMDB_AWS_SECRET_ACCESS_KEY="secret",
            )
        )
        with patch(
            "sources.providers.imdb.http_request",
            new=AsyncMock(side_effect=RuntimeError("offline")),
        ):
            rating = await source.load_rating(AnimeIdentity({"imdb": "tt1234567"}))
        self.assertIsNotNone(rating)
        assert rating is not None
        self.assertEqual(rating.backend, "local")

    def test_sigv4_headers_are_deterministic_and_complete(self) -> None:
        headers = _sigv4_headers(
            endpoint="https://api-fulfill.dataexchange.us-east-1.amazonaws.com/v1",
            body=b'{"query":"query"}',
            api_key="api-key",
            data_set_id="dataset",
            revision_id="revision",
            asset_id="asset",
            access_key_id="AKID",
            secret_access_key="secret",
            region="us-east-1",
            now=datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc),
        )
        self.assertEqual(headers["x-amz-date"], "20260102T030405Z")
        self.assertEqual(headers["x-api-key"], "api-key")
        self.assertEqual(headers["x-amzn-dataexchange-asset-id"], "asset")
        self.assertIn(
            "AKID/20260102/us-east-1/dataexchange/aws4_request",
            headers["authorization"],
        )
        self.assertIn("SignedHeaders=", headers["authorization"])

    def test_builder_filters_dataset_to_mapping_imdb_ids(self) -> None:
        mapping = self.root / "mappings.db"
        with closing(sqlite3.connect(mapping)) as connection:
            connection.executescript(
                """
                CREATE TABLE edges(
                    a_provider TEXT, a_id TEXT, b_provider TEXT, b_id TEXT, status TEXT
                );
                CREATE TABLE mapping_overrides(
                    source_provider TEXT, source_id TEXT, target_provider TEXT,
                    target_id TEXT, action TEXT
                );
                """
            )
            connection.execute(
                "INSERT INTO edges VALUES ('mal','1','imdb','tt1111111','accepted')"
            )
            connection.execute(
                "INSERT INTO edges VALUES ('mal','2','imdb','tt2222222','rejected')"
            )
            connection.execute(
                "INSERT INTO mapping_overrides VALUES ('anilist','3','imdb','tt3333333','accept')"
            )
            connection.commit()
        dataset = self.root / "title.ratings.tsv.gz"
        with gzip.open(dataset, "wt", encoding="utf-8", newline="") as stream:
            stream.write("tconst\taverageRating\tnumVotes\n")
            stream.write("tt1111111\t8.1\t100\n")
            stream.write("tt2222222\t9.9\t200\n")
            stream.write("tt3333333\t7.5\t300\n")
            stream.write("tt9999999\t6.0\t400\n")

        module = runpy.run_path(
            str(
                Path(__file__).resolve().parents[1]
                / "scripts"
                / "update-imdb-ratings.py"
            )
        )
        ids = module["_imdb_ids"](mapping)
        self.assertEqual(ids, {"tt1111111", "tt3333333"})
        output = self.root / "filtered.sqlite3"
        scanned, matched = module["_build_database"](
            target_ids=ids,
            output=output,
            url="https://datasets.imdbws.com/title.ratings.tsv.gz",
            source_file=dataset,
        )
        self.assertEqual((scanned, matched), (4, 2))
        with closing(sqlite3.connect(output)) as connection:
            rows = connection.execute(
                "SELECT imdb_id, rating, votes FROM ratings ORDER BY imdb_id"
            ).fetchall()
        self.assertEqual(rows, [("tt1111111", 8.1, 100), ("tt3333333", 7.5, 300)])


if __name__ == "__main__":
    unittest.main()
