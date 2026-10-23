from __future__ import annotations

import os
from typing import Any

import httpx

from core.http_config import USER_AGENT
from core.models import SearchCandidate, SearchPage

DEFAULT_ANILIST_GRAPHQL_URL = "https://graphql.anilist.co"
ANILIST_MAX_PAGE_SIZE = 50

SEARCH_QUERY = """
query SearchAnime($search: String!, $page: Int!, $perPage: Int!) {
  Page(page: $page, perPage: $perPage) {
    pageInfo { hasNextPage }
    media(search: $search, type: ANIME) {
      id
      idMal
      title { romaji english native }
      synonyms
      seasonYear
      averageScore
      coverImage { extraLarge large medium }
    }
  }
}
"""


class AniListSearchProvider:
    """AniList text-search provider used by the unified /anime flow."""

    name = "AniList"

    def api_url(self) -> str:
        return (
            os.getenv("ANILIST_API_URL", DEFAULT_ANILIST_GRAPHQL_URL).strip()
            or DEFAULT_ANILIST_GRAPHQL_URL
        )

    async def search(
        self,
        query: str,
        *,
        page: int,
        limit: int,
    ) -> SearchPage:
        page = max(1, int(page))
        limit = max(1, min(int(limit), ANILIST_MAX_PAGE_SIZE))

        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": USER_AGENT,
        }
        token = os.getenv("ANILIST_ACCESS_TOKEN", "").strip()
        if token:
            headers["Authorization"] = f"Bearer {token}"

        payload = {
            "query": SEARCH_QUERY,
            "variables": {
                "search": query,
                "page": page,
                "perPage": limit,
            },
        }

        async with httpx.AsyncClient(
            timeout=20.0,
            headers=headers,
            follow_redirects=True,
        ) as client:
            response = await client.post(self.api_url(), json=payload)

        if response.is_error:
            preview = response.text.replace("\n", " ")[:800]
            retry_after = response.headers.get("Retry-After")
            retry_text = f"; retry after {retry_after}s" if retry_after else ""
            raise RuntimeError(
                f"AniList HTTP {response.status_code}{retry_text}: {preview}"
            )

        try:
            body: dict[str, Any] = response.json()
        except ValueError as exc:
            preview = response.text.replace("\n", " ")[:800]
            raise RuntimeError(f"AniList returned non-JSON response: {preview}") from exc

        if body.get("errors"):
            messages = [error.get("message", str(error)) for error in body["errors"]]
            raise RuntimeError("AniList GraphQL error: " + "; ".join(messages))

        page_data = (body.get("data") or {}).get("Page") or {}
        items: list[SearchCandidate] = []

        for raw in page_data.get("media") or []:
            anilist_id = str(raw.get("id") or "").strip()
            if not anilist_id:
                continue

            mal_id = str(raw.get("idMal") or "").strip()
            titles = raw.get("title") or {}
            romaji = _clean(titles.get("romaji"))
            english = _clean(titles.get("english"))
            native = _clean(titles.get("native"))
            title = english or romaji or native or "Без названия"

            aliases = _dedupe(
                [
                    romaji,
                    english,
                    native,
                    *[_clean(value) for value in raw.get("synonyms") or []],
                ]
            )
            aliases = [value for value in aliases if value.casefold() != title.casefold()]

            scores: dict[str, float] = {}
            try:
                if raw.get("averageScore") is not None:
                    scores[self.name] = round(float(raw["averageScore"]) / 10.0, 2)
            except (TypeError, ValueError):
                pass

            external_ids = {"anilist": anilist_id}
            if mal_id:
                external_ids["mal"] = mal_id

            cover = raw.get("coverImage") or {}
            poster_url = _clean(
                cover.get("extraLarge")
                or cover.get("large")
                or cover.get("medium")
            )

            items.append(
                SearchCandidate(
                    title=title,
                    romaji_title=romaji or None,
                    aliases=aliases,
                    year=raw.get("seasonYear"),
                    external_ids=external_ids,
                    scores=scores,
                    posters=[poster_url] if poster_url else [],
                )
            )

        return SearchPage(
            items=items,
            page=page,
            page_size=limit,
            has_next=bool((page_data.get("pageInfo") or {}).get("hasNextPage")),
        )


def _clean(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).replace("\r", " ").split())


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        value = _clean(value)
        key = value.casefold()
        if value and key not in seen:
            seen.add(key)
            result.append(value)
    return result