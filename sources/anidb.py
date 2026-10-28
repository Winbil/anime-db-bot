from __future__ import annotations

import asyncio
import math
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

import httpx

from core.canonicalization import canonical_role_token, voice_role_token
from core.http_config import USER_AGENT
from core.identity import AnimeIdentity
from core.models import AnimeRecord, CharacterRecord, EpisodePage, EpisodeRecord, PersonCredit
from core.people_loading import PeopleBatch
from core.settings import AppSettings, SourceSettings
from core.source_keys import SourceKey
from services.rate_limits import wait_for_upstream

ANIDB_SOURCE_NAME = "AniDB"
DEFAULT_API_URL = "http://api.anidb.net:9001/httpapi"
IMAGE_BASE_URL = "https://cdn-eu.anidb.net/images/main/"
_XML_LANG = "{http://www.w3.org/XML/1998/namespace}lang"
_NETWORK_LOCK = asyncio.Lock()
_LAST_NETWORK_REQUEST_AT = 0.0
_MIN_REQUEST_INTERVAL_SECONDS = 2.2


def _settings(settings: SourceSettings | None = None) -> SourceSettings:
    return settings or AppSettings.from_env().sources


def enabled(settings: SourceSettings | None = None) -> bool:
    return bool(_settings(settings).anidb_client)


def _client(settings: SourceSettings | None = None) -> str:
    return _settings(settings).anidb_client


def _client_version(settings: SourceSettings | None = None) -> int:
    return max(1, _settings(settings).anidb_client_version)


def _api_url(settings: SourceSettings | None = None) -> str:
    return _settings(settings).anidb_http_api_url or DEFAULT_API_URL


def _timeout(settings: SourceSettings | None = None) -> float:
    return max(10.0, _settings(settings).anidb_request_timeout_seconds)


def _cache_ttl(settings: SourceSettings | None = None) -> float:
    return max(0.0, _settings(settings).anidb_cache_ttl_seconds)


def _cache_dir(settings: SourceSettings | None = None) -> Path:
    return _settings(settings).anidb_cache_dir


def _clean(value: Any) -> str:
    return " ".join(str(value or "").replace("\r", " ").split()).strip()


def _text(element: ET.Element | None) -> str:
    return _clean(element.text if element is not None else "")


def _int(value: Any) -> int | None:
    try:
        return int(str(value).strip()) if value is not None and str(value).strip() else None
    except (TypeError, ValueError):
        return None


def _float(value: Any) -> float | None:
    try:
        return float(str(value).strip()) if value is not None and str(value).strip() else None
    except (TypeError, ValueError):
        return None


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for raw in values:
        value = _clean(raw)
        key = value.casefold()
        if value and key not in seen:
            seen.add(key)
            result.append(value)
    return result


def _image_url(value: Any) -> str | None:
    filename = _clean(value)
    if not filename:
        return None
    if filename.startswith(("http://", "https://")):
        return "https://" + filename.split("://", 1)[1]
    return IMAGE_BASE_URL + filename.lstrip("/")


def _kind(value: Any) -> str | None:
    raw = _clean(value).casefold()
    mapping = {
        "tv series": "tv",
        "tv special": "tv_special",
        "movie": "movie",
        "ova": "ova",
        "web": "ona",
        "ona": "ona",
        "special": "special",
        "music video": "music_video",
    }
    return mapping.get(raw, raw.replace(" ", "_") or None)


def _character_role(value: Any) -> str | None:
    raw = _clean(value).casefold()
    if "main character" in raw:
        return "main"
    if "secondary cast" in raw:
        return "supporting"
    if "appears in" in raw:
        return "background"
    return None


def _title_data(root: ET.Element) -> tuple[dict[str, str], list[str]]:
    titles: dict[str, str] = {}
    aliases: list[str] = []
    for element in root.findall("./titles/title"):
        value = _text(element)
        if not value:
            continue
        lang = _clean(element.attrib.get(_XML_LANG) or element.attrib.get("lang")).casefold()
        kind = _clean(element.attrib.get("type")).casefold()
        key: str | None = None
        if kind == "main" and lang == "x-jat":
            key = "romaji"
        elif kind == "official" and lang == "en":
            key = "english"
        elif kind == "official" and lang == "ja":
            key = "japanese"
        elif kind == "official" and lang == "ru":
            key = "russian"
        if key and key not in titles:
            titles[key] = value
        else:
            aliases.append(value)
    chosen = {value.casefold() for value in titles.values()}
    return titles, [value for value in _dedupe(aliases) if value.casefold() not in chosen]


def _resource_ids(root: ET.Element) -> dict[str, str]:
    collected: dict[str, set[str]] = {}
    type_map = {"1": "ann", "2": "mal"}
    for resource in root.findall("./resources/resource"):
        provider = type_map.get(_clean(resource.attrib.get("type")))
        if provider is None:
            continue
        for identifier in resource.findall("./externalentity/identifier"):
            value = _text(identifier)
            if value:
                collected.setdefault(provider, set()).add(value)
    return {
        provider: next(iter(values))
        for provider, values in collected.items()
        if len(values) == 1
    }


def _staff(root: ET.Element) -> list[PersonCredit]:
    result: list[PersonCredit] = []
    seen: set[tuple[str, str]] = set()
    for creator in root.findall("./creators/name"):
        name = _text(creator)
        person_id = _clean(creator.attrib.get("id"))
        role_raw = _clean(creator.attrib.get("type"))
        if not name:
            continue
        key = (person_id, name.casefold())
        if key in seen:
            continue
        seen.add(key)
        role = canonical_role_token(role_raw) if role_raw else ""
        result.append(PersonCredit(
            name=name,
            roles=[role] if role else [],
            external_ids={"anidb": person_id} if person_id else {},
        ))
    return result


def _characters(root: ET.Element) -> list[CharacterRecord]:
    result: list[CharacterRecord] = []
    seen: set[str] = set()
    for character in root.findall("./characters/character"):
        character_id = _clean(character.attrib.get("id"))
        name = _text(character.find("name"))
        if not name:
            continue
        key = character_id or name.casefold()
        if key in seen:
            continue
        seen.add(key)
        portrait = _image_url(_text(character.find("picture")))
        result.append(CharacterRecord(
            name=name,
            role=_character_role(character.attrib.get("type")),
            external_ids={"anidb": character_id} if character_id else {},
            portraits={ANIDB_SOURCE_NAME: [portrait]} if portrait else {},
        ))
    return result


def _voices(root: ET.Element) -> list[PersonCredit]:
    result: dict[str, PersonCredit] = {}
    for character in root.findall("./characters/character"):
        character_name = _text(character.find("name"))
        for seiyuu in character.findall("seiyuu"):
            name = _text(seiyuu)
            person_id = _clean(seiyuu.attrib.get("id"))
            if not name:
                continue
            key = person_id or name.casefold()
            portrait = _image_url(seiyuu.attrib.get("picture"))
            role = voice_role_token(character_name or None)
            existing = result.get(key)
            if existing is None:
                result[key] = PersonCredit(
                    name=name,
                    roles=[role],
                    external_ids={"anidb": person_id} if person_id else {},
                    portraits={ANIDB_SOURCE_NAME: [portrait]} if portrait else {},
                )
            elif role not in existing.roles:
                existing.roles.append(role)
    return list(result.values())


def _episodes(root: ET.Element) -> list[EpisodeRecord]:
    result: list[EpisodeRecord] = []
    for episode in root.findall("./episodes/episode"):
        epno = episode.find("epno")
        if epno is None or _clean(epno.attrib.get("type")) != "1":
            continue
        number_text = _text(epno)
        if not number_text.isdigit():
            continue
        number = int(number_text)
        titles: dict[str, str] = {}
        for title in episode.findall("title"):
            value = _text(title)
            lang = _clean(title.attrib.get(_XML_LANG) or title.attrib.get("lang")).casefold()
            key = {"en": "english", "ja": "japanese", "x-jat": "romaji"}.get(lang)
            if key and value and key not in titles:
                titles[key] = value
        episode_id = _clean(episode.attrib.get("id"))
        rating = episode.find("rating")
        score = _float(_text(rating)) if rating is not None else None
        length = _int(_text(episode.find("length")))
        urls = {
            "AniDB": f"https://anidb.net/episode/{episode_id}"
        } if episode_id else {}
        result.append(EpisodeRecord(
            number=number,
            source="anidb",
            backend="anidb",
            titles=titles,
            aired_at=_text(episode.find("airdate")) or None,
            duration_seconds=length * 60 if length and length > 0 else None,
            score=score,
            urls=urls,
        ))
    result.sort(key=lambda item: item.number)
    return result


async def _read_bytes(path: Path) -> bytes:
    return await asyncio.to_thread(path.read_bytes)


async def _write_atomic(path: Path, data: bytes) -> None:
    def write() -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_bytes(data)
        temporary.replace(path)
    await asyncio.to_thread(write)


async def _network_xml(aid: str, settings: SourceSettings | None = None) -> bytes:
    global _LAST_NETWORK_REQUEST_AT
    settings = _settings(settings)
    if not enabled(settings):
        raise RuntimeError("AniDB HTTP API is disabled: ANIDB_CLIENT is empty")

    async with _NETWORK_LOCK:
        elapsed = time.monotonic() - _LAST_NETWORK_REQUEST_AT
        if elapsed < _MIN_REQUEST_INTERVAL_SECONDS:
            await asyncio.sleep(_MIN_REQUEST_INTERVAL_SECONDS - elapsed)
        params = {
            "request": "anime",
            "aid": aid,
            "client": _client(settings),
            "clientver": _client_version(settings),
            "protover": 1,
        }
        try:
            async with httpx.AsyncClient(
                timeout=_timeout(settings),
                follow_redirects=True,
                headers={"User-Agent": USER_AGENT},
            ) as client:
                response = await client.get(_api_url(settings), params=params)
        finally:
            _LAST_NETWORK_REQUEST_AT = time.monotonic()
        response.raise_for_status()
        data = response.content
        if not data.strip():
            raise RuntimeError("AniDB returned an empty response")
        try:
            root = ET.fromstring(data)
        except ET.ParseError as exc:
            raise RuntimeError("AniDB returned invalid XML") from exc
        if root.tag.rsplit("}", 1)[-1] == "error":
            raise RuntimeError(f"AniDB API error: {_text(root)}")
        return data


class AniDBSource:
    name = ANIDB_SOURCE_NAME
    display_name = ANIDB_SOURCE_NAME
    source_key = SourceKey.ANIDB
    backend_key = "anidb"

    def __init__(self, settings: SourceSettings | None = None) -> None:
        self._settings = _settings(settings)

    @staticmethod
    def is_enabled(settings: SourceSettings | None = None) -> bool:
        return enabled(settings)

    @staticmethod
    def _aid(identity: AnimeIdentity) -> str:
        value = _clean(identity.get("anidb"))
        return value if value.isdigit() and int(value) > 0 else ""

    async def _load_root(self, identity: AnimeIdentity) -> ET.Element | None:
        aid = self._aid(identity)
        if not aid:
            return None
        cache_path = _cache_dir(self._settings) / f"{aid}.xml"
        ttl = _cache_ttl(self._settings)
        if cache_path.is_file() and (
            ttl <= 0 or time.time() - cache_path.stat().st_mtime < ttl
        ):
            data = await _read_bytes(cache_path)
        else:
            data = await _network_xml(aid, self._settings)
            await _write_atomic(cache_path, data)
        root = ET.fromstring(data)
        if root.tag.rsplit("}", 1)[-1] != "anime":
            raise RuntimeError(f"Unexpected AniDB XML root: {root.tag}")
        return root

    async def get_details(self, identity: AnimeIdentity) -> AnimeRecord | None:
        root = await self._load_root(identity)
        if root is None:
            return None
        aid = self._aid(identity)
        titles, synonyms = _title_data(root)
        external_ids = {"anidb": aid, **_resource_ids(root)}
        permanent = root.find("./ratings/permanent")
        score = _float(_text(permanent)) if permanent is not None else None
        picture = _image_url(_text(root.find("picture")))
        description = _text(root.find("description"))
        restricted = _clean(root.attrib.get("restricted")) in {"1", "true", "yes"}
        return AnimeRecord(
            source=ANIDB_SOURCE_NAME,
            source_id=aid,
            titles=titles,
            synonyms=synonyms,
            external_ids=external_ids,
            kind=_kind(_text(root.find("type"))),
            rating="adult" if restricted else None,
            episodes_total=_int(_text(root.find("episodecount"))),
            aired_on=_text(root.find("startdate")) or None,
            released_on=_text(root.find("enddate")) or None,
            score=score,
            descriptions={ANIDB_SOURCE_NAME: description} if description else {},
            posters=[picture] if picture else [],
            urls={"AniDB": f"https://anidb.net/anime/{aid}"},
            staff=_staff(root),
            voices=_voices(root),
        )

    async def load_characters(self, identity: AnimeIdentity) -> list[CharacterRecord]:
        root = await self._load_root(identity)
        return _characters(root) if root is not None else []

    async def load_staff(self, identity: AnimeIdentity) -> list[PersonCredit]:
        root = await self._load_root(identity)
        return _staff(root) if root is not None else []

    async def load_voices(self, identity: AnimeIdentity) -> list[PersonCredit]:
        root = await self._load_root(identity)
        return _voices(root) if root is not None else []

    async def load_staff_batch(
        self,
        identity: AnimeIdentity,
        *,
        cursor: str | None = None,
        portrait_limit: int = 50,
    ) -> PeopleBatch:
        if cursor is not None:
            return PeopleBatch(complete=True)
        values = await self.load_staff(identity)
        return PeopleBatch(people=values, complete=True, total_count=len(values))

    async def load_voices_batch(
        self,
        identity: AnimeIdentity,
        *,
        cursor: str | None = None,
        portrait_limit: int = 50,
    ) -> PeopleBatch:
        if cursor is not None:
            return PeopleBatch(complete=True)
        values = await self.load_voices(identity)
        return PeopleBatch(people=values, complete=True, total_count=len(values))

    async def load_episode_page(
        self,
        identity: AnimeIdentity,
        *,
        page: int = 1,
    ) -> EpisodePage:
        await wait_for_upstream("anidb", "episodes")
        root = await self._load_root(identity)
        page = max(1, int(page))
        if root is None:
            return EpisodePage(items=[], page=page, has_next=False)
        values = _episodes(root)
        page_size = 100
        start = (page - 1) * page_size
        items = values[start:start + page_size]
        last_page = max(1, math.ceil(len(values) / page_size))
        return EpisodePage(
            items=items,
            page=page,
            last_visible_page=last_page,
            has_next=page < last_page,
        )

    async def load_episode(
        self,
        identity: AnimeIdentity,
        episode_number: int,
    ) -> EpisodeRecord | None:
        await wait_for_upstream("anidb", "episodes")
        root = await self._load_root(identity)
        if root is None:
            return None
        wanted = int(episode_number)
        return next((item for item in _episodes(root) if item.number == wanted), None)
