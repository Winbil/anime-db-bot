from __future__ import annotations

from typing import Any

from core.http_client import http_request
from core.models import SearchCandidate, SearchPage
from core.settings import SourceSettings, get_settings
from core.source_errors import SourceInvalidResponse
from core.source_names import MAL_SOURCE_NAME
from services.rate_limits import wait_for_upstream

MAL_MAX_PAGE_SIZE = 100


class MALSearchProvider:
    name = MAL_SOURCE_NAME

    def __init__(self, settings: SourceSettings | None = None) -> None:
        self._settings = settings

    @property
    def settings(self) -> SourceSettings:
        return self._settings or get_settings().sources

    def api_url(self) -> str:
        return self.settings.mal_api_url

    def client_id(self) -> str:
        client_id = self.settings.mal_client_id
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
            "X-MAL-CLIENT-ID": self.client_id(),
        }
        params = {
            "q": query,
            "limit": limit,
            "offset": offset,
            "fields": "alternative_titles,start_date,mean,main_picture",
        }

        await wait_for_upstream("mal", "search")
        response = await http_request(
            "mal",
            "GET",
            f"{self.api_url()}/anime",
            operation="search",
            timeout=20.0,
            headers=headers,
            params=params,
        )

        try:
            body: dict[str, Any] = response.json()
        except ValueError as exc:
            preview = response.text.replace("\n", " ")[:800]
            raise SourceInvalidResponse(
                f"MyAnimeList returned non-JSON response: {preview}",
                source="mal",
                operation="search",
            ) from exc

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

            picture = node.get("main_picture") or {}
            poster = str(picture.get("large") or picture.get("medium") or "").strip()

            items.append(
                SearchCandidate(
                    title=title,
                    romaji_title=title,
                    aliases=aliases,
                    year=year,
                    external_ids={"mal": mal_id},
                    scores=scores,
                    posters=[poster] if poster else [],
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
