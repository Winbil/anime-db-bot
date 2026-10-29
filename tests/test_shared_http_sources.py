from __future__ import annotations

import unittest
from dataclasses import replace
from unittest.mock import AsyncMock, patch

import httpx

from core.settings import get_settings
from core.source_errors import SourceInvalidResponse
from sources.providers import anidb, anilist, shikimori_people


def _response(
    status: int,
    *,
    text: str = "",
    json_data=None,
    headers: dict[str, str] | None = None,
) -> httpx.Response:
    request = httpx.Request("GET", "https://example.invalid/test")
    if json_data is not None:
        return httpx.Response(
            status,
            json=json_data,
            headers=headers,
            request=request,
        )
    return httpx.Response(status, text=text, headers=headers, request=request)


class SharedHttpSourceTests(unittest.IsolatedAsyncioTestCase):
    async def test_anilist_invalid_json_is_typed_and_operation_scoped(self) -> None:
        response = _response(200, text="not-json")
        with patch(
            "sources.providers.anilist.http_request",
            new=AsyncMock(return_value=response),
        ) as request:
            with self.assertRaises(SourceInvalidResponse) as raised:
                await anilist.graphql_request(
                    "query Test { x }", {}, operation="people"
                )

        self.assertEqual(raised.exception.info.source, "anilist")
        self.assertEqual(raised.exception.info.operation, "people")
        self.assertEqual(request.await_args.kwargs["operation"], "people")

    async def test_shikimori_people_keeps_retry_after_policy_on_shared_transport(
        self,
    ) -> None:
        limited = _response(429, json_data={}, headers={"Retry-After": "0"})
        success = _response(200, json_data={"id": 1})
        with (
            patch(
                "sources.providers.shikimori_people._rate_limited_get",
                new=AsyncMock(side_effect=[limited, success]),
            ) as getter,
            patch(
                "sources.providers.shikimori_people.asyncio.sleep",
                new=AsyncMock(),
            ) as sleeper,
        ):
            body = await shikimori_people._rest_get_json("/api/test")

        self.assertEqual(body, {"id": 1})
        self.assertEqual(getter.await_count, 2)
        sleeper.assert_awaited_once()

    async def test_anidb_serialized_fetch_uses_shared_http_boundary(self) -> None:
        settings = replace(get_settings().sources, anidb_client="testclient")
        response = _response(200, text='<anime id="1"><titles /></anime>')
        with (
            patch(
                "sources.providers.anidb.http_request",
                new=AsyncMock(return_value=response),
            ) as request,
            patch.object(anidb, "_MIN_REQUEST_INTERVAL_SECONDS", 0.0),
        ):
            anidb._LAST_NETWORK_REQUEST_AT = 0.0
            data = await anidb._network_xml("1", settings)

        self.assertIn(b"<anime", data)
        self.assertEqual(
            request.await_args.args[:3], ("anidb", "GET", settings.anidb_http_api_url)
        )
        self.assertEqual(request.await_args.kwargs["operation"], "metadata")


if __name__ == "__main__":
    unittest.main()
