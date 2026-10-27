from __future__ import annotations

import os
from typing import Any

import httpx

from core.identity import AnimeIdentity
from core.models import EpisodePage, EpisodeRecord
from services.rate_limits import wait_for_upstream

DEFAULT_JIKAN_API_URL = "http://127.0.0.1:8091"
JIKAN_DISPLAY_NAME = "MAL (MyAnimeList) / Jikan"


def api_url() -> str:
    return (
        os.getenv("JIKAN_API_URL", DEFAULT_JIKAN_API_URL).strip().rstrip("/")
        or DEFAULT_JIKAN_API_URL
    )


def _timeout() -> float:
    raw = os.getenv("JIKAN_REQUEST_TIMEOUT_SECONDS", "45").strip()
    try:
        return max(5.0, float(raw))
    except ValueError:
        return 45.0


def _clean(value: Any) -> str:
    return " ".join(str(value or "").replace("\r", " ").split()).strip()


def _int(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _float(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _episode(raw: dict[str, Any]) -> EpisodeRecord:
    number = _int(raw.get("number"))
    if number is None or number <= 0:
        raise ValueError("Jikan episode payload does not contain a positive episode number")

    titles = {
        key: value
        for key, raw_value in {
            "english": raw.get("title"),
            "japanese": raw.get("title_japanese"),
            "romaji": raw.get("title_romaji"),
        }.items()
        if (value := _clean(raw_value))
    }
    urls = {
        key: value
        for key, raw_value in {
            "MyAnimeList": raw.get("url"),
            "MyAnimeList forum": raw.get("forum_url"),
        }.items()
        if (value := _clean(raw_value))
    }

    return EpisodeRecord(
        number=number,
        source="mal",
        backend="jikan",
        titles=titles,
        aired_at=_clean(raw.get("aired_at")) or None,
        duration_seconds=_int(raw.get("duration_seconds")),
        score=_float(raw.get("score")),
        filler=bool(raw.get("filler")),
        recap=bool(raw.get("recap")),
        synopsis=_clean(raw.get("synopsis")) or None,
        urls=urls,
    )


async def _get(path: str, *, params: dict[str, object] | None = None) -> dict[str, Any]:
    await wait_for_upstream("jikan", "episodes")
    async with httpx.AsyncClient(timeout=_timeout(), follow_redirects=True) as client:
        response = await client.get(f"{api_url()}{path}", params=params)

    if response.is_error:
        preview = response.text.replace("\n", " ")[:800]
        raise RuntimeError(
            f"Jikan supplement HTTP {response.status_code} from {response.url}: {preview}"
        )
    try:
        body = response.json()
    except ValueError as exc:
        preview = response.text.replace("\n", " ")[:800]
        raise RuntimeError(f"Jikan supplement returned non-JSON response: {preview}") from exc
    if not isinstance(body, dict):
        raise RuntimeError("Jikan supplement returned an unexpected JSON payload")
    return body


class JikanSource:
    """MAL web supplement backed by the local on-demand Jikan parser service.

    This is a separate backend/capability source, but it deliberately consumes the
    existing MAL identity edge instead of introducing a Jikan identity key.
    """

    name = "Jikan"
    display_name = JIKAN_DISPLAY_NAME
    source_key = "mal"
    backend_key = "jikan"

    async def load_episode_page(
        self,
        identity: AnimeIdentity,
        *,
        page: int = 1,
    ) -> EpisodePage:
        mal_id = str(identity.get("mal") or "").strip()
        if not mal_id.isdigit():
            return EpisodePage(items=[], page=max(1, int(page)), has_next=False)

        page = max(1, int(page))
        body = await _get(f"/anime/{mal_id}/episodes", params={"page": page})
        items = [
            _episode(item)
            for item in body.get("data") or []
            if isinstance(item, dict)
        ]
        return EpisodePage(
            items=items,
            page=page,
            last_visible_page=max(1, _int(body.get("last_visible_page")) or 1),
            has_next=bool(body.get("has_next_page")),
        )

    async def load_episode(
        self,
        identity: AnimeIdentity,
        episode_number: int,
    ) -> EpisodeRecord | None:
        mal_id = str(identity.get("mal") or "").strip()
        episode_number = int(episode_number)
        if not mal_id.isdigit() or episode_number <= 0:
            return None

        body = await _get(f"/anime/{mal_id}/episodes/{episode_number}")
        raw = body.get("data")
        if not isinstance(raw, dict):
            return None
        return _episode(raw)
