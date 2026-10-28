from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlsplit

import httpx

from core.http_config import USER_AGENT
from core.identity import AnimeIdentity
from core.models import TrailerRecord
from core.settings import SourceSettings, get_settings
from core.source_keys import SourceKey
from services.rate_limits import wait_for_upstream
from sources.anilist import _graphql as _anilist_graphql
from sources.jikan import JikanSource
from sources.shikimori import site_url as shikimori_site_url

ANILIST_TRAILER_QUERY = """
query AnimeTrailer($id: Int!) {
  Media(id: $id, type: ANIME) {
    id
    trailer { id site thumbnail }
  }
}
"""

_SHIKIMORI_PROMO_KINDS = {
    "pv": "trailer",
    "character_trailer": "character_trailer",
    "cm": "commercial",
}


def _clean(value: Any) -> str:
    return " ".join(str(value or "").replace("\r", " ").split()).strip()


def _https(value: Any) -> str:
    raw = _clean(value)
    if not raw:
        return ""

    # Some Shikimori records contain malformed duplicated schemes such as
    # ``https:// https://youtu.be/...``. Telegram rejects the whole inline
    # keyboard when even one button contains such a URL, so extract the last
    # structurally valid HTTP(S) URL instead of forwarding upstream garbage.
    candidates = re.findall(r"https?://[^\s]+", raw, flags=re.IGNORECASE)
    for candidate in reversed(candidates):
        candidate = candidate.rstrip(".,;)")
        parsed = urlsplit(candidate)
        if parsed.scheme.casefold() not in {"http", "https"} or not parsed.netloc:
            continue
        if parsed.scheme.casefold() == "http":
            candidate = "https://" + candidate.split("://", 1)[1]
        return candidate
    return ""


def _dedupe(values: list[TrailerRecord]) -> list[TrailerRecord]:
    result: list[TrailerRecord] = []
    seen: set[str] = set()
    for item in values:
        key = item.url.strip().casefold()
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def _anilist_url(site: str, external_id: str) -> tuple[str, str | None]:
    site_key = site.casefold()
    if site_key == "youtube":
        return (
            f"https://www.youtube.com/watch?v={external_id}",
            f"https://www.youtube.com/embed/{external_id}",
        )
    if site_key == "dailymotion":
        return (
            f"https://www.dailymotion.com/video/{external_id}",
            f"https://www.dailymotion.com/embed/video/{external_id}",
        )
    return "", None


def _anilist_trailers(raw: dict[str, Any] | None) -> list[TrailerRecord]:
    raw = raw or {}
    external_id = _clean(raw.get("id"))
    site = _clean(raw.get("site"))
    if not external_id or not site:
        return []
    url, embed_url = _anilist_url(site, external_id)
    if not url:
        return []
    return [TrailerRecord(
        source="anilist",
        backend="anilist",
        title=None,
        kind="trailer",
        hosting=site,
        url=url,
        embed_url=embed_url,
        thumbnail=_https(raw.get("thumbnail")) or None,
    )]


def _shikimori_trailers(body: list[Any]) -> list[TrailerRecord]:
    result: list[TrailerRecord] = []
    for raw in body:
        if not isinstance(raw, dict):
            continue
        raw_kind = _clean(raw.get("kind")).casefold()
        kind = _SHIKIMORI_PROMO_KINDS.get(raw_kind)
        if kind is None:
            continue
        url = _https(raw.get("url"))
        if not url:
            continue
        result.append(TrailerRecord(
            source="shikimori",
            backend="shikimori",
            title=_clean(raw.get("name")) or None,
            kind=kind,
            hosting=_clean(raw.get("hosting")) or None,
            url=url,
            embed_url=_https(raw.get("player_url")) or None,
            thumbnail=_https(raw.get("image_url")) or None,
        ))
    return _dedupe(result)


class AniListTrailerSource:
    name = "AniListTrailer"
    display_name = "AniList"
    source_key = SourceKey.ANILIST
    backend_key = "anilist"

    def __init__(self, settings: SourceSettings | None = None) -> None:
        self._settings = settings or get_settings().sources

    async def load_trailers(self, identity: AnimeIdentity) -> list[TrailerRecord]:
        media_id = str(identity.get("anilist") or "").strip()
        if not media_id.isdigit():
            return []

        await wait_for_upstream("anilist", "trailers")
        data = await _anilist_graphql(
            ANILIST_TRAILER_QUERY,
            {"id": int(media_id)},
            self._settings,
        )
        raw = (data.get("Media") or {}).get("trailer") or {}
        return _anilist_trailers(raw if isinstance(raw, dict) else None)


class ShikimoriTrailerSource:
    name = "ShikimoriTrailer"
    display_name = "Shikimori"
    source_key = SourceKey.SHIKIMORI
    backend_key = "shikimori"

    def __init__(self, settings: SourceSettings | None = None) -> None:
        self._settings = settings or get_settings().sources

    async def load_trailers(self, identity: AnimeIdentity) -> list[TrailerRecord]:
        anime_id = str(identity.get("shikimori") or "").strip()
        if not anime_id.isdigit():
            return []

        await wait_for_upstream("shikimori", "trailers")
        headers = {"Accept": "application/json", "User-Agent": USER_AGENT}
        async with httpx.AsyncClient(timeout=20.0, headers=headers, follow_redirects=True) as client:
            response = await client.get(f"{shikimori_site_url(self._settings)}/api/animes/{anime_id}/videos")
        if response.is_error:
            preview = response.text.replace("\n", " ")[:800]
            raise RuntimeError(
                f"Shikimori trailers HTTP {response.status_code} from {response.url}: {preview}"
            )
        try:
            body = response.json()
        except ValueError as exc:
            raise RuntimeError("Shikimori trailers returned non-JSON response") from exc
        if not isinstance(body, list):
            return []
        return _shikimori_trailers(body)


def get_builtin_trailer_sources(
    settings: SourceSettings | None = None,
):
    """Return trailer backends in the same logical order used by metadata cards."""
    settings = settings or get_settings().sources
    return (
        ShikimoriTrailerSource(settings),
        AniListTrailerSource(settings),
        JikanSource(settings),
    )
