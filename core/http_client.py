from __future__ import annotations

from contextlib import contextmanager
import base64
import logging
import time
from contextvars import ContextVar
from typing import Any, Iterator

import httpx
from httpx_socks import AsyncProxyTransport

from core.http_config import USER_AGENT
from core.proxy_config import ProxyEntry, ProxySettings
from core.source_errors import error_for_response, normalize_source_error

_PROXY_FAILOVER_STATUSES = frozenset({407, 502, 503, 504})


class HttpClientPool:
    """Reusable async HTTP clients owned by AppContext.

    Clients are keyed by logical source plus proxy slot. A source with one or more
    enabled proxies never silently falls back to the direct connection. Requests
    start on a round-robin slot and fail over across the remaining enabled slots
    for transport/proxy failures.
    """

    def __init__(self, proxy_settings: ProxySettings | None = None) -> None:
        self._proxy_settings = proxy_settings or ProxySettings.empty()
        self._clients: dict[tuple[str, str], httpx.AsyncClient] = {}
        self._proxy_cursor: dict[str, int] = {}
        self._closed = False

    def _client(
        self,
        profile: str,
        *,
        proxy: ProxyEntry | None = None,
        proxy_slot: int = -1,
    ) -> httpx.AsyncClient:
        if self._closed:
            raise RuntimeError("HTTP client pool is closed")
        source = (profile or "default").strip().casefold() or "default"
        slot_key = "direct" if proxy is None else f"{proxy_slot}:{proxy.name}"
        key = (source, slot_key)
        client = self._clients.get(key)
        if client is not None:
            return client

        kwargs: dict[str, Any] = {
            "follow_redirects": True,
            "headers": {"User-Agent": USER_AGENT},
        }
        if proxy is not None:
            kwargs["transport"] = AsyncProxyTransport.from_url(proxy.url)
        client = httpx.AsyncClient(**kwargs)
        self._clients[key] = client
        return client

    def _proxy_order(self, profile: str) -> tuple[tuple[int, ProxyEntry], ...]:
        source = (profile or "default").strip().casefold() or "default"
        proxies = self._proxy_settings.active(source)
        if not proxies:
            return ()
        start = self._proxy_cursor.get(source, 0) % len(proxies)
        self._proxy_cursor[source] = (start + 1) % len(proxies)
        return tuple(
            ((start + offset) % len(proxies), proxies[(start + offset) % len(proxies)])
            for offset in range(len(proxies))
        )

    @staticmethod
    def _proxy_log_fields(
        proxy: ProxyEntry | None, attempt: int = 1
    ) -> dict[str, object]:
        if proxy is None:
            return {"proxy": "direct", "proxy_attempt": attempt}
        return {
            "proxy": proxy.name,
            "proxy_scheme": proxy.scheme,
            "proxy_attempt": attempt,
        }

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
        source = (profile or "default").strip().casefold() or "default"
        proxy_order = self._proxy_order(source)
        attempts: tuple[tuple[int, ProxyEntry | None], ...] = (
            proxy_order if proxy_order else ((-1, None),)
        )
        started = time.monotonic()
        last_error: BaseException | None = None

        for attempt_number, (proxy_slot, proxy) in enumerate(attempts, 1):
            attempt_started = time.monotonic()
            request_kwargs = dict(kwargs)
            client_proxy = proxy
            client_proxy_slot = proxy_slot
            if source == "jikan" and proxy is not None:
                # Jikan itself is a loopback service. Keep the Python -> Jikan hop
                # direct and let the local PHP service proxy its outbound MAL scrape.
                headers = dict(request_kwargs.get("headers") or {})
                headers["X-Anime-DB-Bot-Proxy"] = (
                    base64.urlsafe_b64encode(proxy.url.encode("utf-8"))
                    .decode("ascii")
                    .rstrip("=")
                )
                request_kwargs["headers"] = headers
                client_proxy = None
                client_proxy_slot = -1
            try:
                response = await self._client(
                    source,
                    proxy=client_proxy,
                    proxy_slot=client_proxy_slot,
                ).request(
                    method,
                    url,
                    timeout=timeout,
                    **request_kwargs,
                )
            except Exception as exc:
                last_error = exc
                if attempt_number < len(attempts):
                    logging.warning(
                        "Source proxy attempt failed; trying next proxy",
                        extra={
                            "event": "source_proxy_failover",
                            "source": source,
                            "operation": operation,
                            "outcome": "retry",
                            "error_type": type(exc).__name__,
                            "duration_ms": round(
                                (time.monotonic() - attempt_started) * 1000, 3
                            ),
                            **self._proxy_log_fields(proxy, attempt_number),
                        },
                    )
                    continue
                error = normalize_source_error(
                    exc,
                    source=source,
                    operation=operation,
                )
                logging.warning(
                    "Source HTTP request failed",
                    extra={
                        "event": "source_http_request",
                        "source": source,
                        "operation": operation,
                        "outcome": "error",
                        "error_type": type(error).__name__,
                        "duration_ms": round((time.monotonic() - started) * 1000, 3),
                        **self._proxy_log_fields(proxy, attempt_number),
                    },
                )
                raise error from exc

            if (
                response.status_code in _PROXY_FAILOVER_STATUSES
                and response.status_code not in allowed_statuses
                and attempt_number < len(attempts)
            ):
                logging.warning(
                    "Source proxy returned a failover status; trying next proxy",
                    extra={
                        "event": "source_proxy_failover",
                        "source": source,
                        "operation": operation,
                        "outcome": "retry",
                        "status_code": response.status_code,
                        "duration_ms": round(
                            (time.monotonic() - attempt_started) * 1000, 3
                        ),
                        **self._proxy_log_fields(proxy, attempt_number),
                    },
                )
                continue

            duration_ms = round((time.monotonic() - started) * 1000, 3)
            if response.is_error and response.status_code not in allowed_statuses:
                error = error_for_response(
                    response,
                    source=source,
                    operation=operation,
                )
                logging.warning(
                    "Source HTTP request returned an error",
                    extra={
                        "event": "source_http_request",
                        "source": source,
                        "operation": operation,
                        "outcome": "error",
                        "error_type": type(error).__name__,
                        "status_code": response.status_code,
                        "duration_ms": duration_ms,
                        **self._proxy_log_fields(proxy, attempt_number),
                    },
                )
                raise error
            logging.info(
                "Source HTTP request completed",
                extra={
                    "event": "source_http_request",
                    "source": source,
                    "operation": operation,
                    "outcome": "success",
                    "status_code": response.status_code,
                    "duration_ms": duration_ms,
                    **self._proxy_log_fields(proxy, attempt_number),
                },
            )
            return response

        # The loop always returns or raises. Keep a defensive typed failure for
        # static analysis and future refactors.
        if last_error is not None:  # pragma: no cover
            raise normalize_source_error(last_error, source=source, operation=operation)
        raise RuntimeError(
            "HTTP request had no direct or proxy route"
        )  # pragma: no cover

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
