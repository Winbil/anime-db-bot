from __future__ import annotations

import os
from typing import Any

import httpx

from core.models import SearchCandidate, SearchPage

DEFAULT_MAL_API_URL = "https://api.myanimelist.net/v2"
MAL_MAX_PAGE_SIZE = 100


class MALSearchProvider:
    name = "MyAnimeList"

    def api_url(self) -> str:
        return (
            os.getenv("MAL_API_URL", DEFAULT_MAL_API_URL).strip().rstrip("/")
            or DEFAULT_MAL_API_URL
        )

    def client_id(self) -> str:
        client_id = os.getenv("MAL_CLIENT_ID", "").strip()
        if not client_id:
            raise RuntimeError(
                "MAL_CLIENT_ID is empty. Create a MyAnimeList API application and add its Client ID to .env."
            )
        return client_id

    async def search(
        self,
        query: str,
        *,
        page: int,
        limit: int,
    ) -> SearchPage:
        page = max(1, int(page))
        limit = max(1, min(int(limit), MAL_MAX_PAGE_SIZE))
        offset = (page - 1) * limit

        headers = {
            "Accept": "application/json",
            "User-Agent": "anime-db-bot/0.7 (https://github.com/Winbil/anime-db-bot)",
            "X-MAL-CLIENT-ID": self.client_id(),
        }
        params = {
            "q": query,
            "limit": limit,
            "offset": offset,
            "fields": "alternative_titles,start_date,mean",
        }

        async with httpx.AsyncClient(
            timeout=20.0,
            headers=headers,
            follow_redirects=True,
        ) as client:
            response = await client.get(f"{self.api_url()}/anime", params=params)

        if response.is_error:
            preview = response.text.replace("\n", " ")[:800]
            if response.status_code in {401, 403}:
                raise RuntimeError(
                    f"MyAnimeList rejected MAL_CLIENT_ID (HTTP {response.status_code}): {preview}"
                )
            raise RuntimeError(
                f"MyAnimeList HTTP {response.status_code} from {response.url}: {preview}"
            )

        try:
            body: dict[str, Any] = response.json()
        except ValueError as exc:
            preview = response.text.replace("\n", " ")[:800]
            raise RuntimeError(f"MyAnimeList returned non-JSON response: {preview}") from exc

        items: list[SearchCandidate] = []
        for entry in body.get("data") or []:
            node = entry.get("node") or {}
            mal_id = str(node.get("id") or "").strip()
            if not mal_id:
                continue

            title = str(node.get("title") or "Без названия").strip()
            alternative = node.get("alternative_titles") or {}
            aliases: list[str] = []
            for value in (
                alternative.get("en"),
                alternative.get("ja"),
                *(alternative.get("synonyms") or []),
            ):
                value = str(value or "").strip()
                if value and value.casefold() != title.casefold():
                    aliases.append(value)

            aliases = _dedupe(aliases)

            start_date = str(node.get("start_date") or "").strip()
            year: int | None = None
            if len(start_date) >= 4 and start_date[:4].isdigit():
                year = int(start_date[:4])

            scores: dict[str, float] = {}
            try:
                if node.get("mean") is not None:
                    scores[self.name] = float(node["mean"])
            except (TypeError, ValueError):
                pass

            items.append(
                SearchCandidate(
                    title=title,
                    aliases=aliases,
                    year=year,
                    external_ids={"mal": mal_id},
                    scores=scores,
                )
            )

        paging = body.get("paging") or {}
        return SearchPage(
            items=items,
            page=page,
            page_size=limit,
            has_next=bool(paging.get("next")),
        )


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        key = value.casefold()
        if value and key not in seen:
            seen.add(key)
            result.append(value)
    return result
