from __future__ import annotations

import argparse
import gzip
import io
import os
import re
import sqlite3
import tempfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, TextIO
from urllib.request import Request, urlopen

ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_URL = "https://datasets.imdbws.com/title.ratings.tsv.gz"
DEFAULT_MAPPINGS = ROOT_DIR / "data" / "mappings" / "mappings.db"
DEFAULT_OUTPUT = ROOT_DIR / "data" / "imdb_ratings.sqlite3"
IMDB_ID_RE = re.compile(r"^tt\d+$", re.IGNORECASE)
USER_AGENT = "anime-db-bot IMDb ratings indexer"
SAFE_IDENTITY_PROVIDERS = (
    "mal",
    "anilist",
    "shikimori",
    "kitsu",
    "anidb",
    "anisearch",
)


def _imdb_ids(mapping_db: Path) -> set[str]:
    if not mapping_db.is_file():
        raise FileNotFoundError(f"Mappings database not found: {mapping_db}")
    connection = sqlite3.connect(mapping_db)
    try:
        safe = ", ".join("?" for _ in SAFE_IDENTITY_PROVIDERS)
        rows = connection.execute(
            f"""
            SELECT a_id FROM edges
              WHERE status = 'accepted' AND a_provider = 'imdb'
                AND b_provider IN ({safe})
            UNION
            SELECT b_id FROM edges
              WHERE status = 'accepted' AND b_provider = 'imdb'
                AND a_provider IN ({safe})
            UNION
            SELECT source_id FROM mapping_overrides
              WHERE action = 'accept' AND source_provider = 'imdb'
                AND target_provider IN ({safe})
            UNION
            SELECT target_id FROM mapping_overrides
              WHERE action = 'accept' AND target_provider = 'imdb'
                AND source_provider IN ({safe})
            """,
            (*SAFE_IDENTITY_PROVIDERS,) * 4,
        )
        return {
            value.casefold()
            for (raw_value,) in rows
            if (value := str(raw_value or "").strip()) and IMDB_ID_RE.fullmatch(value)
        }
    finally:
        connection.close()


@contextmanager
def _ratings_stream(url: str, source_file: Path | None) -> Iterator[TextIO]:
    if source_file is not None:
        with gzip.open(source_file, "rt", encoding="utf-8", newline="") as stream:
            yield stream
        return

    request = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=120) as response:  # noqa: S310 - fixed/explicit maintenance URL
        with gzip.GzipFile(fileobj=response) as compressed:
            with io.TextIOWrapper(compressed, encoding="utf-8", newline="") as stream:
                yield stream


def _build_database(
    *,
    target_ids: set[str],
    output: Path,
    url: str,
    source_file: Path | None,
) -> tuple[int, int]:
    output.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(
        prefix=f".{output.name}.", suffix=".tmp", dir=output.parent
    )
    os.close(fd)
    temp_path = Path(temp_name)
    matched = 0
    scanned = 0
    try:
        connection = sqlite3.connect(temp_path)
        try:
            connection.executescript(
                """
                PRAGMA journal_mode=OFF;
                PRAGMA synchronous=OFF;
                CREATE TABLE metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                CREATE TABLE ratings (
                    imdb_id TEXT PRIMARY KEY,
                    rating REAL NOT NULL,
                    votes INTEGER NOT NULL
                ) WITHOUT ROWID;
                """
            )
            with _ratings_stream(url, source_file) as stream:
                header = stream.readline().rstrip("\r\n").split("\t")
                if header[:3] != ["tconst", "averageRating", "numVotes"]:
                    raise RuntimeError(f"Unexpected IMDb ratings header: {header!r}")
                pending: list[tuple[str, float, int]] = []
                for line in stream:
                    scanned += 1
                    raw = line.rstrip("\r\n").split("\t")
                    if len(raw) < 3:
                        continue
                    imdb_id = raw[0].casefold()
                    if imdb_id not in target_ids:
                        continue
                    try:
                        rating = float(raw[1])
                        votes = int(raw[2])
                    except ValueError:
                        continue
                    if not 0 <= rating <= 10 or votes < 0:
                        continue
                    pending.append((imdb_id, rating, votes))
                    if len(pending) >= 500:
                        connection.executemany(
                            "INSERT OR REPLACE INTO ratings(imdb_id, rating, votes) VALUES (?, ?, ?)",
                            pending,
                        )
                        matched += len(pending)
                        pending.clear()
                if pending:
                    connection.executemany(
                        "INSERT OR REPLACE INTO ratings(imdb_id, rating, votes) VALUES (?, ?, ?)",
                        pending,
                    )
                    matched += len(pending)
            metadata = {
                "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "source_url": url,
                "mapping_imdb_ids": str(len(target_ids)),
                "matched_ratings": str(matched),
                "schema_version": "1",
            }
            connection.executemany(
                "INSERT INTO metadata(key, value) VALUES (?, ?)", metadata.items()
            )
            connection.commit()
        finally:
            connection.close()
        os.replace(temp_path, output)
        return scanned, matched
    finally:
        temp_path.unlink(missing_ok=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build an anime-only local IMDb ratings SQLite index."
    )
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--mappings-db", type=Path, default=DEFAULT_MAPPINGS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--source-file",
        type=Path,
        help="Read a local title.ratings.tsv.gz instead of downloading it.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    target_ids = _imdb_ids(args.mappings_db)
    if not target_ids:
        raise RuntimeError("No accepted IMDb IDs were found in mappings.db")
    scanned, matched = _build_database(
        target_ids=target_ids,
        output=args.output,
        url=args.url,
        source_file=args.source_file,
    )
    print(
        f"IMDb ratings index: {matched}/{len(target_ids)} mapped IDs matched "
        f"after scanning {scanned} IMDb rows -> {args.output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
