from __future__ import annotations

from typing import Any

from core.http_client import http_request
from core.models import SearchCandidate, SearchPage
from core.settings import SourceSettings, get_settings
from core.source_errors import SourceInvalidResponse
from services.rate_limits import wait_for_upstream

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

    def __init__(self, settings: SourceSettings | None = None) -> None:
        self._settings = settings

    @property
    def settings(self) -> SourceSettings:
        return self._settings or get_settings().sources

    def api_url(self) -> str:
        return self.settings.anilist_api_url

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
        }
        if self.settings.anilist_access_token:
            headers["Authorization"] = f"Bearer {self.settings.anilist_access_token}"

        payload = {
            "query": SEARCH_QUERY,
            "variables": {
                "search": query,
                "page": page,
                "perPage": limit,
            },
        }

        await wait_for_upstream("anilist", "search")
        response = await http_request(
            "anilist",
            "POST",
            self.api_url(),
            operation="search",
            timeout=20.0,
            headers=headers,
            json=payload,
        )

        try:
            body: dict[str, Any] = response.json()
        except ValueError as exc:
            preview = response.text.replace("\n", " ")[:800]
            raise SourceInvalidResponse(
                f"AniList returned non-JSON response: {preview}",
                source="anilist",
                operation="search",
            ) from exc

        if body.get("errors"):
            messages = [error.get("message", str(error)) for error in body["errors"]]
            raise SourceInvalidResponse(
                "AniList GraphQL error: " + "; ".join(messages),
                source="anilist",
                operation="search",
            )

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
