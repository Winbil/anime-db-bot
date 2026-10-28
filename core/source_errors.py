from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx


@dataclass(frozen=True, slots=True)
class SourceErrorInfo:
    source: str
    operation: str
    message: str
    transient: bool
    status_code: int | None = None
    retry_after: float | None = None


class SourceError(RuntimeError):
    """Base typed failure emitted by external source boundaries."""

    def __init__(
        self,
        message: str,
        *,
        source: str = "unknown",
        operation: str = "unknown",
        transient: bool = False,
        status_code: int | None = None,
        retry_after: float | None = None,
    ) -> None:
        super().__init__(message)
        self.info = SourceErrorInfo(
            source=source,
            operation=operation,
            message=message,
            transient=transient,
            status_code=status_code,
            retry_after=retry_after,
        )

    @property
    def transient(self) -> bool:
        return self.info.transient

    @property
    def retry_after(self) -> float | None:
        return self.info.retry_after


class SourceTimeout(SourceError):
    pass


class SourceUnavailable(SourceError):
    pass


class SourceRateLimited(SourceError):
    pass


class SourceAuthenticationError(SourceError):
    pass


class SourceNotFound(SourceError):
    pass


class SourceInvalidResponse(SourceError):
    pass


class SourceCircuitOpen(SourceUnavailable):
    pass


def retry_after_seconds(headers: Any) -> float | None:
    raw = str((headers or {}).get("Retry-After") or "").strip()
    if not raw:
        return None
    try:
        return max(0.0, float(raw))
    except ValueError:
        return None


def error_for_response(
    response: httpx.Response,
    *,
    source: str,
    operation: str,
) -> SourceError:
    status = int(response.status_code)
    preview = response.text.replace("\n", " ")[:800]
    message = f"{source} HTTP {status} from {response.url}: {preview}"
    retry_after = retry_after_seconds(response.headers)
    if status == 404:
        return SourceNotFound(
            message,
            source=source,
            operation=operation,
            status_code=status,
        )
    if status == 429:
        return SourceRateLimited(
            message,
            source=source,
            operation=operation,
            transient=True,
            status_code=status,
            retry_after=retry_after,
        )
    if status in {401, 403}:
        return SourceAuthenticationError(
            message,
            source=source,
            operation=operation,
            status_code=status,
        )
    return SourceUnavailable(
        message,
        source=source,
        operation=operation,
        transient=status >= 500,
        status_code=status,
    )


def normalize_source_error(
    exc: BaseException,
    *,
    source: str,
    operation: str,
) -> SourceError:
    if isinstance(exc, SourceError):
        return exc
    if isinstance(exc, httpx.TimeoutException):
        return SourceTimeout(
            f"{source} {operation} timed out: {exc}",
            source=source,
            operation=operation,
            transient=True,
        )
    if isinstance(exc, httpx.TransportError):
        return SourceUnavailable(
            f"{source} {operation} transport failure: {exc}",
            source=source,
            operation=operation,
            transient=True,
        )
    return SourceError(
        f"{source} {operation} failed: {type(exc).__name__}: {exc}",
        source=source,
        operation=operation,
        transient=False,
    )
