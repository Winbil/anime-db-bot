from __future__ import annotations

import os
from typing import Any

import httpx

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
    }
  }
}
"""


class AniListSearchProvider:
    """Explicit AniList search provider.

    This provider is intentionally not part of the default /anime search so the
    AniList rate limit is only spent when the user explicitly selects AniList
    (or selects every search provider through /search).
    """

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
            "User-Agent": "anime-db-bot/0.8 (https://github.com/Winbil/anime-db-bot)",
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
            mal_id = str(raw.get("idMal") or "").strip()
            if not mal_id:
                # The rest of the bot intentionally uses MAL ID as its canonical
                # hand-off ID, so entries without a MAL mapping are not selectable.
                continue

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

            items.append(
                SearchCandidate(
                    title=title,
                    aliases=aliases,
                    year=raw.get("seasonYear"),
                    external_ids={
                        "mal": mal_id,
                        "anilist": str(raw.get("id") or ""),
                    },
                    scores=scores,
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
