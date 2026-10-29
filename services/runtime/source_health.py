from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable

from core.source_errors import SourceCircuitOpen, SourceError


@dataclass(frozen=True, slots=True)
class SourceHealthSnapshot:
    source: str
    consecutive_failures: int
    circuit_open_until: float
    last_error: str | None
    last_success_at: float | None
    probe_in_flight: bool = False
    observed_at: float = 0.0

    @property
    def circuit_open(self) -> bool:
        return self.circuit_open_until > self.observed_at

    @property
    def state(self) -> str:
        if self.circuit_open:
            return "open"
        if self.circuit_open_until > 0.0:
            return "half_open"
        return "closed"


@dataclass(slots=True)
class _MutableHealth:
    consecutive_failures: int = 0
    circuit_open_until: float = 0.0
    last_error: str | None = None
    last_success_at: float | None = None
    probe_in_flight: bool = False


class SourceHealthRegistry:
    """Process-local health and simple circuit breaker per logical source."""

    def __init__(
        self,
        *,
        failure_threshold: int = 3,
        cooldown_seconds: float = 30.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.failure_threshold = max(1, int(failure_threshold))
        self.cooldown_seconds = max(1.0, float(cooldown_seconds))
        self._clock = clock
        self._states: dict[str, _MutableHealth] = {}

    @staticmethod
    def _key(source: str) -> str:
        return (source or "unknown").strip().casefold() or "unknown"

    def before_call(self, source: str, operation: str) -> bool:
        """Authorize one source call and report whether it is a half-open probe."""
        key = self._key(source)
        state = self._states.get(key)
        now = self._clock()
        if state is None:
            return False
        if state.circuit_open_until > now:
            remaining = state.circuit_open_until - now
            raise SourceCircuitOpen(
                f"{source} circuit is open for another {remaining:.1f}s",
                source=source,
                operation=operation,
                transient=True,
                retry_after=remaining,
            )
        if state.circuit_open_until:
            if state.probe_in_flight:
                raise SourceCircuitOpen(
                    f"{source} circuit is half-open; recovery probe is already running",
                    source=source,
                    operation=operation,
                    transient=True,
                )
            state.probe_in_flight = True
            return True
        return False

    def record_success(self, source: str) -> None:
        key = self._key(source)
        state = self._states.setdefault(key, _MutableHealth())
        state.consecutive_failures = 0
        state.circuit_open_until = 0.0
        state.last_error = None
        state.last_success_at = self._clock()
        state.probe_in_flight = False

    def record_failure(self, source: str, error: SourceError) -> None:
        key = self._key(source)
        state = self._states.setdefault(key, _MutableHealth())
        was_probe = state.probe_in_flight
        state.probe_in_flight = False
        state.last_error = f"{type(error).__name__}: {error}"
        if not error.transient:
            state.consecutive_failures = 0
            state.circuit_open_until = 0.0
            return

        state.consecutive_failures += 1
        if was_probe:
            # A failed recovery probe is enough to reopen immediately; waiting
            # for the normal threshold would create a post-cooldown request burst.
            state.consecutive_failures = max(
                state.consecutive_failures,
                self.failure_threshold,
            )

        if state.consecutive_failures >= self.failure_threshold:
            cooldown = max(self.cooldown_seconds, float(error.retry_after or 0.0))
            state.circuit_open_until = self._clock() + cooldown

    def release_probe(self, source: str) -> None:
        """Release an abandoned half-open probe without pretending it succeeded."""
        key = self._key(source)
        state = self._states.get(key)
        if state is not None:
            state.probe_in_flight = False

    def snapshot(self, source: str) -> SourceHealthSnapshot:
        key = self._key(source)
        state = self._states.get(key) or _MutableHealth()
        return SourceHealthSnapshot(
            source=key,
            consecutive_failures=state.consecutive_failures,
            circuit_open_until=state.circuit_open_until,
            last_error=state.last_error,
            last_success_at=state.last_success_at,
            probe_in_flight=state.probe_in_flight,
            observed_at=self._clock(),
        )

    def reset(self) -> None:
        self._states.clear()
