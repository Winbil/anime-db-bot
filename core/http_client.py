from __future__ import annotations

from contextlib import contextmanager
import logging
import time
from contextvars import ContextVar
from typing import Any, Iterator

import httpx

from core.http_config import USER_AGENT
from core.source_errors import error_for_response, normalize_source_error


class HttpClientPool:
    """Reusable async HTTP clients owned by AppContext.

    Clients are keyed by logical profile/source and share connection pools for the
    lifetime of the application. Request-specific auth headers and timeouts remain
    explicit at call sites.
    """

    def __init__(self) -> None:
        self._clients: dict[str, httpx.AsyncClient] = {}
        self._closed = False

    def _client(self, profile: str) -> httpx.AsyncClient:
        if self._closed:
            raise RuntimeError("HTTP client pool is closed")
        key = (profile or "default").strip().casefold() or "default"
        client = self._clients.get(key)
        if client is None:
            client = httpx.AsyncClient(
                follow_redirects=True,
                headers={"User-Agent": USER_AGENT},
            )
            self._clients[key] = client
        return client

    async def request(
        self,
        profile: str,
        method: str,
        url: str,
        *,
        operation: str = "request",
        timeout: float | httpx.Timeout | None = None,
        allowed_statuses: set[int] | frozenset[int] = frozenset(),
        **kwargs: Any,
    ) -> httpx.Response:
        started = time.monotonic()
        try:
            response = await self._client(profile).request(
                method,
                url,
                timeout=timeout,
                **kwargs,
            )
        except Exception as exc:
            error = normalize_source_error(
                exc,
                source=profile,
                operation=operation,
            )
            logging.warning(
                "Source HTTP request failed",
                extra={
                    "event": "source_http_request",
                    "source": profile,
                    "operation": operation,
                    "outcome": "error",
                    "error_type": type(error).__name__,
                    "duration_ms": round((time.monotonic() - started) * 1000, 3),
                },
            )
            raise error from exc
        duration_ms = round((time.monotonic() - started) * 1000, 3)
        if response.is_error and response.status_code not in allowed_statuses:
            error = error_for_response(
                response,
                source=profile,
                operation=operation,
            )
            logging.warning(
                "Source HTTP request returned an error",
                extra={
                    "event": "source_http_request",
                    "source": profile,
                    "operation": operation,
                    "outcome": "error",
                    "error_type": type(error).__name__,
                    "status_code": response.status_code,
                    "duration_ms": duration_ms,
                },
            )
            raise error
        logging.info(
            "Source HTTP request completed",
            extra={
                "event": "source_http_request",
                "source": profile,
                "operation": operation,
                "outcome": "success",
                "status_code": response.status_code,
                "duration_ms": duration_ms,
            },
        )
        return response

    async def aclose(self) -> None:
        if self._closed:
            return
        self._closed = True
        clients = tuple(self._clients.values())
        self._clients.clear()
        for client in clients:
            await client.aclose()


_CURRENT_HTTP_POOL: ContextVar[HttpClientPool | None] = ContextVar(
    "anime_db_bot_http_pool",
    default=None,
)


@contextmanager
def activate_http_pool(pool: HttpClientPool) -> Iterator[HttpClientPool]:
    token = _CURRENT_HTTP_POOL.set(pool)
    try:
        yield pool
    finally:
        _CURRENT_HTTP_POOL.reset(token)


async def http_request(
    profile: str,
    method: str,
    url: str,
    *,
    operation: str = "request",
    timeout: float | httpx.Timeout | None = None,
    allowed_statuses: set[int] | frozenset[int] = frozenset(),
    **kwargs: Any,
) -> httpx.Response:
    """Use the AppContext pool, or an isolated client for standalone tests/tools."""
    pool = _CURRENT_HTTP_POOL.get()
    if pool is not None:
        return await pool.request(
            profile,
            method,
            url,
            operation=operation,
            timeout=timeout,
            allowed_statuses=allowed_statuses,
            **kwargs,
        )

    temporary = HttpClientPool()
    try:
        return await temporary.request(
            profile,
            method,
            url,
            operation=operation,
            timeout=timeout,
            allowed_statuses=allowed_statuses,
            **kwargs,
        )
    finally:
        await temporary.aclose()
