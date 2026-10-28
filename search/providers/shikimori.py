from __future__ import annotations

from typing import Any

from core.http_client import http_request
from core.models import SearchCandidate, SearchPage
from core.settings import AppSettings, SourceSettings
from core.source_errors import SourceInvalidResponse
from services.rate_limits import wait_for_upstream

SHIKIMORI_MAX_PAGE_SIZE = 50

SEARCH_FIELDS = """
    id
    malId
    name
    russian
    english
    japanese
    synonyms
    score
    airedOn { year }
    poster {
      originalUrl
      main2xUrl
      mainUrl
      preview2xUrl
      previewUrl
    }
"""


class ShikimoriSearchProvider:
    name = "Shikimori"

    def __init__(self, settings: SourceSettings | None = None) -> None:
        self._settings = settings

    @property
    def settings(self) -> SourceSettings:
        return self._settings or AppSettings.from_env().sources

    def api_url(self) -> str:
        return self.settings.shikimori_api_url

    async def search(
        self,
        query: str,
        *,
        page: int,
        limit: int,
    ) -> SearchPage:
        page = max(1, int(page))
        limit = max(1, min(int(limit), SHIKIMORI_MAX_PAGE_SIZE))
        payload = {
            "query": _search_query(page, limit),
            "variables": {"search": query},
        }

        await wait_for_upstream("shikimori", "search")
        response = await http_request(
            "shikimori",
            "POST",
            self.api_url(),
            operation="search",
            timeout=20.0,
            headers={"Accept": "application/json"},
            json=payload,
        )

        try:
            body: dict[str, Any] = response.json()
        except ValueError as exc:
            preview = response.text.replace("\n", " ")[:800]
            raise SourceInvalidResponse(
                f"Shikimori returned non-JSON response: {preview}",
                source="shikimori",
                operation="search",
            ) from exc

        if body.get("errors"):
            messages = [error.get("message", str(error)) for error in body["errors"]]
            raise SourceInvalidResponse(
                "Shikimori GraphQL error: " + "; ".join(messages),
                source="shikimori",
                operation="search",
            )

        raw_items = ((body.get("data") or {}).get("animes") or [])
        items: list[SearchCandidate] = []

        for raw in raw_items:
            shikimori_id = str(raw.get("id") or "").strip()
            if not shikimori_id:
                continue

            mal_id = str(raw.get("malId") or "").strip()
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

            external_ids = {"shikimori": shikimori_id}
            if mal_id:
                external_ids["mal"] = mal_id

            poster = raw.get("poster") or {}
            poster_url = _clean(
                poster.get("originalUrl")
                or poster.get("main2xUrl")
                or poster.get("mainUrl")
                or poster.get("preview2xUrl")
                or poster.get("previewUrl")
            )

            items.append(
                SearchCandidate(
                    title=title,
                    romaji_title=romaji or None,
                    aliases=aliases,
                    year=(raw.get("airedOn") or {}).get("year"),
                    external_ids=external_ids,
                    scores=scores,
                    posters=[poster_url] if poster_url else [],
                )
            )

        return SearchPage(
            items=items,
            page=page,
            page_size=limit,
            has_next=len(raw_items) >= limit,
        )


def _search_query(page: int, limit: int) -> str:
    return f"""
query SearchAnime($search: String!) {{
  animes(search: $search, page: {page}, limit: {limit}, order: popularity) {{
{SEARCH_FIELDS}
  }}
}}
"""


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
