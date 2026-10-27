from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Iterable, Iterator

import ijson

from mappings.database import MappingRecord


def _values(value: Any, *, numeric: bool = False) -> tuple[str, ...]:
    if value is None:
        return ()
    raw_values: list[Any]
    if isinstance(value, (list, tuple, set)):
        raw_values = list(value)
    elif isinstance(value, str) and "," in value:
        raw_values = value.split(",")
    else:
        raw_values = [value]

    result: list[str] = []
    seen: set[str] = set()
    for raw in raw_values:
        text = str(raw or "").strip()
        if numeric and not text.isdigit():
            continue
        if text and text.casefold() not in {"none", "null", "unknown", "hentai", "-1", "0"}:
            key = text.casefold()
            if key not in seen:
                seen.add(key)
                result.append(text)
    return tuple(result)


def _record(
    key: str,
    ids: dict[str, tuple[str, ...]],
    *,
    group: str,
    weight: int,
) -> MappingRecord | None:
    cleaned = {provider: values for provider, values in ids.items() if values}
    if len(cleaned) < 2:
        return None
    return MappingRecord(
        record_key=key,
        ids=cleaned,
        evidence_group=group,
        weight=weight,
    )


def import_fribb(path: Path) -> Iterator[MappingRecord]:
    with path.open("rb") as handle:
        for index, item in enumerate(ijson.items(handle, "item")):
            if not isinstance(item, dict):
                continue
            anidb = _values(item.get("anidb_id"), numeric=True)
            if not anidb:
                continue

            manami = _record(
                f"{index}:manami",
                {
                    "anidb": anidb,
                    "anilist": _values(item.get("anilist_id"), numeric=True),
                    "mal": _values(item.get("mal_id"), numeric=True),
                    "kitsu": _values(item.get("kitsu_id")),
                    "animeplanet": _values(item.get("anime-planet_id")),
                    "anisearch": _values(item.get("anisearch_id")),
                    "ann": _values(item.get("animenewsnetwork_id")),
                    "livechart": _values(item.get("livechart_id")),
                    "simkl": _values(item.get("simkl_id")),
                    "animecountdown": _values(item.get("animecountdown_id")),
                },
                group="manami",
                weight=60,
            )
            if manami is not None:
                yield manami

            tmdb = item.get("themoviedb_id") or {}
            if not isinstance(tmdb, dict):
                tmdb = {}
            anime_lists = _record(
                f"{index}:anime-lists",
                {
                    "anidb": anidb,
                    "tvdb": _values(item.get("tvdb_id"), numeric=True),
                    "tmdb_tv": _values(tmdb.get("tv"), numeric=True),
                    "tmdb_movie": _values(tmdb.get("movie"), numeric=True),
                    "imdb": _values(item.get("imdb_id")),
                },
                group="anime-lists",
                weight=60,
            )
            if anime_lists is not None:
                yield anime_lists


def import_kometa(path: Path) -> Iterator[MappingRecord]:
    with path.open("rb") as handle:
        for anidb_key, item in ijson.kvitems(handle, ""):
            if not isinstance(item, dict):
                continue
            anidb = _values(anidb_key, numeric=True)
            if not anidb:
                continue

            groups = (
                (
                    "manami",
                    62,
                    {
                        "anidb": anidb,
                        "mal": _values(item.get("mal_id"), numeric=True),
                        "anilist": _values(item.get("anilist_id"), numeric=True),
                    },
                ),
                (
                    "anime-lists",
                    62,
                    {
                        "anidb": anidb,
                        "tvdb": _values(item.get("tvdb_id"), numeric=True),
                        "imdb": _values(item.get("imdb_id")),
                    },
                ),
                (
                    "animeaggregations",
                    68,
                    {
                        "anidb": anidb,
                        "tmdb_movie": _values(item.get("tmdb_movie_id"), numeric=True),
                        "tmdb_tv": _values(item.get("tmdb_show_id"), numeric=True),
                    },
                ),
            )
            for group, weight, ids in groups:
                record = _record(
                    f"{anidb_key}:{group}", ids, group=group, weight=weight
                )
                if record is not None:
                    yield record


def import_anime_lists(path: Path) -> Iterator[MappingRecord]:
    index = 0
    for _event, element in ET.iterparse(path, events=("end",)):
        if element.tag.rsplit("}", 1)[-1] != "anime":
            continue
        attrs = element.attrib
        anidb = _values(attrs.get("anidbid"), numeric=True)
        if anidb:
            record = _record(
                str(index),
                {
                    "anidb": anidb,
                    "tvdb": _values(attrs.get("tvdbid"), numeric=True),
                    "tmdb_tv": _values(attrs.get("tmdbtv"), numeric=True),
                    "tmdb_movie": _values(attrs.get("tmdbid"), numeric=True),
                    "imdb": _values(attrs.get("imdbid")),
                },
                group="anime-lists",
                weight=82,
            )
            if record is not None:
                yield record
        index += 1
        element.clear()


def import_animap(path: Path) -> Iterator[MappingRecord]:
    with path.open("rb") as handle:
        for index, entry in enumerate(ijson.items(handle, "entries.item")):
            if not isinstance(entry, dict):
                continue
            ids = entry.get("ids") or {}
            if not isinstance(ids, dict):
                ids = {}
            record = _record(
                f"entry:{index}",
                {
                    "anilist": _values(entry.get("anilist_id"), numeric=True),
                    "anidb": _values(ids.get("anidb"), numeric=True),
                    "mal": _values(ids.get("mal"), numeric=True),
                },
                group="animap",
                weight=95,
            )
            if record is not None:
                yield record

    with path.open("rb") as handle:
        for index, anime in enumerate(ijson.items(handle, "anime.item")):
            if not isinstance(anime, dict):
                continue
            tmdb_movies: list[Any] = []
            extra_tvdb: list[Any] = []
            for run in anime.get("episodes") or []:
                if not isinstance(run, dict):
                    continue
                tmdb_movies.extend(run.get("tmdb_movies") or [])
                for target in run.get("tvdb") or []:
                    if isinstance(target, dict) and target.get("series") is not None:
                        extra_tvdb.append(target.get("series"))
            record = _record(
                f"anime:{index}",
                {
                    "anidb": _values(anime.get("anidb_id"), numeric=True),
                    "mal": _values(anime.get("mal_ids"), numeric=True),
                    "tvdb": _values(
                        [anime.get("tvdb_id"), *extra_tvdb], numeric=True
                    ),
                    "tmdb_movie": _values(tmdb_movies, numeric=True),
                    "imdb": _values(anime.get("imdb_ids")),
                },
                group="animap",
                weight=95,
            )
            if record is not None:
                yield record


_URL_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("anidb", re.compile(r"anidb\.net/(?:anime/|perl-bin/animedb\.pl\?show=anime&aid=)(\d+)", re.I)),
    ("anilist", re.compile(r"anilist\.co/anime/(\d+)", re.I)),
    ("mal", re.compile(r"myanimelist\.net/anime/(\d+)", re.I)),
    ("kitsu", re.compile(r"kitsu\.(?:app|io)/anime/([^/?#]+)", re.I)),
    ("animeplanet", re.compile(r"anime-planet\.com/anime/([^/?#]+)", re.I)),
    ("anisearch", re.compile(r"anisearch\.com/anime/(\d+)", re.I)),
    ("ann", re.compile(r"animenewsnetwork\.com/encyclopedia/anime\.php\?id=(\d+)", re.I)),
    ("livechart", re.compile(r"livechart\.me/anime/(\d+)", re.I)),
    ("simkl", re.compile(r"simkl\.com/anime/(\d+)", re.I)),
    ("animecountdown", re.compile(r"animecountdown\.com/(\d+)", re.I)),
)


def _ids_from_source_urls(urls: Iterable[Any]) -> dict[str, tuple[str, ...]]:
    collected: dict[str, list[str]] = {}
    for raw_url in urls:
        url = str(raw_url or "").strip()
        if not url:
            continue
        for provider, pattern in _URL_PATTERNS:
            match = pattern.search(url)
            if match:
                collected.setdefault(provider, []).append(match.group(1))
                break
    return {provider: _values(values) for provider, values in collected.items()}


def import_manami(path: Path) -> Iterator[MappingRecord]:
    with path.open("r", encoding="utf-8") as handle:
        for index, line in enumerate(handle):
            line = line.strip()
            if not line:
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(item, dict) or not isinstance(item.get("sources"), list):
                continue
            record = _record(
                str(index),
                _ids_from_source_urls(item["sources"]),
                group="manami",
                weight=82,
            )
            if record is not None:
                yield record


def _descriptor(value: object) -> tuple[str, str] | None:
    text = str(value or "").strip()
    parts = text.split(":")
    if len(parts) < 2:
        return None
    raw_provider, external_id = parts[0].casefold(), parts[1].strip()
    aliases = {
        "anidb": "anidb",
        "anilist": "anilist",
        "mal": "mal",
        "tvdb_show": "tvdb",
        "tvdb_movie": "tvdb_movie",
        "tmdb_show": "tmdb_tv",
        "tmdb_movie": "tmdb_movie",
        "imdb_show": "imdb",
        "imdb_movie": "imdb",
    }
    provider = aliases.get(raw_provider)
    if not provider or not external_id:
        return None
    return provider, external_id


def import_anibridge(path: Path) -> Iterator[MappingRecord]:
    with path.open("rb") as handle:
        for source_descriptor, targets in ijson.kvitems(handle, ""):
            source = _descriptor(source_descriptor)
            if source is None or not isinstance(targets, dict):
                continue
            for target_descriptor in targets:
                target = _descriptor(target_descriptor)
                if target is None or target[0] == source[0]:
                    continue
                record = _record(
                    f"{source_descriptor}->{target_descriptor}",
                    {
                        source[0]: (source[1],),
                        target[0]: (target[1],),
                    },
                    group="anibridge",
                    weight=92,
                )
                if record is not None:
                    yield record


IMPORTERS = {
    "fribb": import_fribb,
    "kometa": import_kometa,
    "anime_lists": import_anime_lists,
    "animap": import_animap,
    "manami": import_manami,
    "anibridge": import_anibridge,
}
