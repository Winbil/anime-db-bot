from __future__ import annotations

import os
from typing import Any

import httpx

from core.models import SearchCandidate, SearchPage

DEFAULT_SHIKIMORI_GRAPHQL_URL = "https://shikimori.io/api/graphql"
SHIKIMORI_MAX_PAGE_SIZE = 50

SEARCH_QUERY = """
query SearchAnime($search: String!, $page: PositiveInt!, $limit: PositiveInt!) {
  animes(search: $search, page: $page, limit: $limit, order: popularity) {
    id
    malId
    name
    russian
    english
    japanese
    synonyms
    score
    airedOn { year }
  }
}
"""


class ShikimoriSearchProvider:
    name = "Shikimori"

    def api_url(self) -> str:
        return (
            os.getenv("SHIKIMORI_API_URL", DEFAULT_SHIKIMORI_GRAPHQL_URL).strip()
            or DEFAULT_SHIKIMORI_GRAPHQL_URL
        )

    async def search(
        self,
        query: str,
        *,
        page: int,
        limit: int,
    ) -> SearchPage:
        page = max(1, int(page))
        limit = max(1, min(int(limit), SHIKIMORI_MAX_PAGE_SIZE))

        headers = {
            "Accept": "application/json",
            "User-Agent": "anime-db-bot/0.7 (https://github.com/Winbil/anime-db-bot)",
        }
        payload = {
            "query": SEARCH_QUERY,
            "variables": {
                "search": query,
                "page": page,
                "limit": limit,
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
            raise RuntimeError(
                f"Shikimori HTTP {response.status_code} from {response.url}: {preview}"
            )

        try:
            body: dict[str, Any] = response.json()
        except ValueError as exc:
            preview = response.text.replace("\n", " ")[:800]
            raise RuntimeError(f"Shikimori returned non-JSON response: {preview}") from exc

        if body.get("errors"):
            messages = [error.get("message", str(error)) for error in body["errors"]]
            raise RuntimeError("Shikimori GraphQL error: " + "; ".join(messages))

        raw_items = ((body.get("data") or {}).get("animes") or [])
        items: list[SearchCandidate] = []

        for raw in raw_items:
            mal_id = str(raw.get("malId") or "").strip()
            if not mal_id:
                continue

            russian = _clean(raw.get("russian"))
            romaji = _clean(raw.get("name"))
            english = _clean(raw.get("english"))
            japanese = _clean(raw.get("japanese"))
            title = russian or romaji or english or japanese or "Без названия"
            aliases = _dedupe(
                [
                    romaji,
                    english,
                    japanese,
                    *[_clean(value) for value in raw.get("synonyms") or []],
                ]
            )
            aliases = [value for value in aliases if value.casefold() != title.casefold()]

            scores: dict[str, float] = {}
            try:
                if raw.get("score") not in (None, ""):
                    scores[self.name] = float(raw["score"])
            except (TypeError, ValueError):
                pass

            items.append(
                SearchCandidate(
                    title=title,
                    aliases=aliases,
                    year=(raw.get("airedOn") or {}).get("year"),
                    external_ids={
                        "mal": mal_id,
                        "shikimori": str(raw.get("id") or ""),
                    },
                    scores=scores,
                )
            )

        return SearchPage(
            items=items,
            page=page,
            page_size=limit,
            has_next=len(raw_items) >= limit,
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
