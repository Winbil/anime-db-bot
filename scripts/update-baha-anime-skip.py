#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
from typing import Any

import httpx

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.http_config import USER_AGENT  # noqa: E402
from core.settings import get_settings  # noqa: E402

_KIND_MAP = {"OP": "opening", "ED": "ending"}


def _positive_integer(value: Any) -> int | None:
    text = str(value or "").strip()
    if not text.isdigit():
        return None
    parsed = int(text)
    return parsed if parsed > 0 else None


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return (
        parsed
        if parsed == parsed and parsed not in (float("inf"), float("-inf"))
        else None
    )


def _bahamut_ids(path: Path) -> list[str]:
    if not path.is_file():
        raise FileNotFoundError(f"mappings database does not exist: {path}")
    uri = f"file:{path.resolve().as_posix()}?mode=ro"
    with closing(sqlite3.connect(uri, uri=True, timeout=5.0)) as conn:
        rows = conn.execute(
            """
            SELECT DISTINCT anime_sn FROM (
                SELECT CASE
                    WHEN a_provider='bahamut' THEN a_id ELSE b_id
                END AS anime_sn
                FROM edges
                WHERE status='accepted'
                  AND (a_provider='bahamut' OR b_provider='bahamut')
                UNION
                SELECT CASE
                    WHEN source_provider='bahamut' THEN source_id ELSE target_id
                END AS anime_sn
                FROM mapping_overrides
                WHERE action='accept'
                  AND (source_provider='bahamut' OR target_provider='bahamut')
            )
            """
        ).fetchall()
    return sorted(
        {str(value) for (value,) in rows if _positive_integer(value) is not None},
        key=int,
    )


async def _download_json(client: httpx.AsyncClient, url: str, timeout: float) -> bytes:
    response = await client.get(url, timeout=timeout)
    response.raise_for_status()
    payload = response.content
    parsed = json.loads(payload)
    if not isinstance(parsed, dict):
        raise ValueError("Baha Anime Skip data root is not an object")
    return payload


async def _fetch_anime(
    client: httpx.AsyncClient,
    base_url: str,
    anime_sn: str,
    timeout: float,
    semaphore: asyncio.Semaphore,
) -> tuple[str, dict[str, Any] | None, str | None]:
    url = f"{base_url.rstrip('/')}/v4/video.php"
    async with semaphore:
        last_error: BaseException | None = None
        for attempt in range(4):
            try:
                response = await client.get(
                    url,
                    params={"animeSn": anime_sn},
                    timeout=timeout,
                )
                if response.status_code == 429:
                    await asyncio.sleep(1.0 * (attempt + 1))
                    continue
                response.raise_for_status()
                payload = response.json()
                data = payload.get("data") if isinstance(payload, dict) else None
                anime = data.get("anime") if isinstance(data, dict) else None
                if not isinstance(anime, dict):
                    return anime_sn, None, "missing anime object"
                returned = _positive_integer(anime.get("animeSn"))
                if returned != int(anime_sn):
                    return anime_sn, None, "animeSn mismatch"
                return anime_sn, anime, None
            except (httpx.HTTPError, ValueError) as exc:
                last_error = exc
                if attempt < 3:
                    await asyncio.sleep(0.25 * (2**attempt))
        return anime_sn, None, str(last_error or "unknown error")


def _episode_video_map(anime: dict[str, Any]) -> dict[int, str]:
    groups = anime.get("episodes")
    if not isinstance(groups, dict):
        return {}
    preferred = groups.get("0")
    candidates = (
        preferred
        if isinstance(preferred, list) and preferred
        else [
            item
            for values in groups.values()
            if isinstance(values, list)
            for item in values
        ]
    )
    by_episode: dict[int, set[str]] = {}
    for item in candidates:
        if not isinstance(item, dict):
            continue
        episode = _positive_integer(item.get("episode"))
        video_sn = _positive_integer(item.get("videoSn"))
        if episode is None or video_sn is None:
            continue
        by_episode.setdefault(episode, set()).add(str(video_sn))
    return {
        episode: next(iter(video_ids))
        for episode, video_ids in by_episode.items()
        if len(video_ids) == 1
    }


def _create_database(
    path: Path,
    *,
    timestamp_data: dict[str, Any],
    anime_payloads: list[tuple[str, dict[str, Any] | None, str | None]],
    data_url: str,
    data_sha256: str,
    mappings_path: Path,
) -> tuple[int, int, int]:
    path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(path)) as conn:
        conn.executescript(
            """
            PRAGMA journal_mode=DELETE;
            PRAGMA synchronous=FULL;
            CREATE TABLE metadata (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            ) WITHOUT ROWID;
            CREATE TABLE segments (
                anime_sn TEXT NOT NULL,
                episode_number INTEGER NOT NULL,
                video_sn TEXT NOT NULL,
                kind TEXT NOT NULL,
                start_seconds REAL NOT NULL,
                end_seconds REAL NOT NULL,
                raw_kind TEXT NOT NULL,
                PRIMARY KEY (anime_sn, episode_number, video_sn, raw_kind)
            ) WITHOUT ROWID;
            CREATE INDEX segments_lookup_idx
                ON segments(anime_sn, episode_number, start_seconds, kind);
            """
        )
        indexed_anime: set[str] = set()
        indexed_episodes: set[tuple[str, int]] = set()
        segment_count = 0
        for anime_sn, anime, _error in anime_payloads:
            if not isinstance(anime, dict):
                continue
            for episode_number, video_sn in _episode_video_map(anime).items():
                raw_segments = timestamp_data.get(video_sn)
                if not isinstance(raw_segments, dict):
                    continue
                inserted = False
                for raw_kind, kind in _KIND_MAP.items():
                    raw_range = raw_segments.get(raw_kind)
                    if not isinstance(raw_range, list) or len(raw_range) < 2:
                        continue
                    start = _number(raw_range[0])
                    duration = _number(raw_range[1])
                    if start is None or duration is None or start < 0 or duration <= 0:
                        continue
                    conn.execute(
                        """
                        INSERT OR REPLACE INTO segments(
                            anime_sn, episode_number, video_sn, kind,
                            start_seconds, end_seconds, raw_kind
                        ) VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            anime_sn,
                            episode_number,
                            video_sn,
                            kind,
                            start,
                            start + duration,
                            raw_kind,
                        ),
                    )
                    inserted = True
                    segment_count += 1
                if inserted:
                    indexed_anime.add(anime_sn)
                    indexed_episodes.add((anime_sn, episode_number))

        failures = sum(1 for _sn, anime, _error in anime_payloads if anime is None)
        metadata = {
            "schema_version": "1",
            "built_at": datetime.now(timezone.utc).isoformat(),
            "source": "JacobLinCool/baha-anime-skip",
            "source_url": data_url,
            "source_sha256": data_sha256,
            "mappings_db": str(mappings_path),
            "bahamut_ids_scanned": str(len(anime_payloads)),
            "bahamut_fetch_failures": str(failures),
            "indexed_anime": str(len(indexed_anime)),
            "indexed_episodes": str(len(indexed_episodes)),
            "segments": str(segment_count),
        }
        conn.executemany(
            "INSERT INTO metadata(key, value) VALUES (?, ?)", metadata.items()
        )
        conn.execute("PRAGMA optimize")
        conn.commit()
    return len(indexed_anime), len(indexed_episodes), segment_count


async def _run(args: argparse.Namespace) -> int:
    settings = get_settings()
    mappings_path = Path(args.mappings_db or settings.mappings.db_path)
    output_path = Path(args.output or settings.sources.baha_anime_skip_db_path)
    data_url = str(args.data_url or settings.sources.baha_anime_skip_data_url)
    api_url = str(args.bahamut_api_url or settings.sources.bahamut_api_url)
    timeout = float(args.timeout or settings.sources.bahamut_request_timeout_seconds)
    anime_ids = _bahamut_ids(mappings_path)
    if not anime_ids:
        raise RuntimeError("No accepted Bahamut IDs were found in mappings.db")

    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    async with httpx.AsyncClient(headers=headers, follow_redirects=True) as client:
        raw_data = await _download_json(client, data_url, timeout)
        timestamp_data = json.loads(raw_data)
        semaphore = asyncio.Semaphore(max(1, int(args.concurrency)))
        tasks = [
            _fetch_anime(client, api_url, anime_sn, timeout, semaphore)
            for anime_sn in anime_ids
        ]
        payloads: list[tuple[str, dict[str, Any] | None, str | None]] = []
        total = len(tasks)
        for index, task in enumerate(asyncio.as_completed(tasks), 1):
            payloads.append(await task)
            if index == total or index % 50 == 0:
                print(f"[baha-index] Bahamut metadata: {index}/{total}", flush=True)

    failed = [(sn, error) for sn, anime, error in payloads if anime is None]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        dir=output_path.parent,
        prefix=f".{output_path.name}.",
        suffix=".tmp",
        delete=False,
    ) as handle:
        temp_path = Path(handle.name)
    temp_path.unlink(missing_ok=True)
    try:
        indexed_anime, indexed_episodes, segment_count = _create_database(
            temp_path,
            timestamp_data=timestamp_data,
            anime_payloads=payloads,
            data_url=data_url,
            data_sha256=hashlib.sha256(raw_data).hexdigest(),
            mappings_path=mappings_path,
        )
        temp_path.replace(output_path)
    finally:
        temp_path.unlink(missing_ok=True)

    print(
        "[baha-index] Built "
        f"{output_path}: anime={indexed_anime}, episodes={indexed_episodes}, "
        f"segments={segment_count}, failures={len(failed)}",
        flush=True,
    )
    if failed:
        print("[baha-index] Failed animeSn: " + ", ".join(sn for sn, _ in failed[:25]))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build the local Baha Anime Skip SQLite index."
    )
    parser.add_argument("--mappings-db")
    parser.add_argument("--output")
    parser.add_argument("--data-url")
    parser.add_argument("--bahamut-api-url")
    parser.add_argument("--timeout", type=float)
    parser.add_argument("--concurrency", type=int, default=12)
    args = parser.parse_args()
    return asyncio.run(_run(args))


if __name__ == "__main__":
    raise SystemExit(main())
