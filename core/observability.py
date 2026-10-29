from __future__ import annotations

import secrets
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Iterator


@dataclass(frozen=True, slots=True)
class ObservabilityContext:
    correlation_id: str | None = None
    platform: str | None = None
    action: str | None = None


_CONTEXT: ContextVar[ObservabilityContext] = ContextVar(
    "anime_db_bot_observability_context",
    default=ObservabilityContext(),
)


def current_observability_context() -> ObservabilityContext:
    return _CONTEXT.get()


def new_correlation_id() -> str:
    """Return a short opaque ID that contains no user/update identifiers."""
    return secrets.token_hex(8)


@contextmanager
def bind_observability_context(
    *,
    correlation_id: str | None = None,
    platform: str | None = None,
    action: str | None = None,
) -> Iterator[ObservabilityContext]:
    current = _CONTEXT.get()
    updated = ObservabilityContext(
        correlation_id=correlation_id or current.correlation_id,
        platform=platform or current.platform,
        action=action or current.action,
    )
    token = _CONTEXT.set(updated)
    try:
        yield updated
    finally:
        _CONTEXT.reset(token)
