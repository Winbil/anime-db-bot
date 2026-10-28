from __future__ import annotations

import json
import logging
import re
from collections.abc import Iterable
from datetime import datetime, timezone
from typing import TextIO

_REDACTED = "<redacted>"
_TELEGRAM_TOKEN_RE = re.compile(r"\b\d{6,12}:[A-Za-z0-9_-]{20,}\b")
_BEARER_RE = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+\-/=]+")
_SENSITIVE_ASSIGNMENT_RE = re.compile(
    r"(?i)([\"']?(?:authorization|access[_-]?token|api[_-]?key|token|"
    r"client[_-]?secret|secret|password|cookie)[\"']?\s*[:=]\s*[\"']?)"
    r"([^\"'\s,;}&]+)"
)
_SENSITIVE_QUERY_RE = re.compile(
    r"(?i)([?&](?:access[_-]?token|api[_-]?key|token|secret|password)=)([^&\s]+)"
)
_URL_CREDENTIAL_RE = re.compile(r"(?i)(https?://[^:/@\s]+:)([^@/\s]+)(@)")
_STRUCTURED_FIELDS = (
    "event",
    "platform",
    "source",
    "operation",
    "backend",
    "provider",
    "attempt",
    "max_attempts",
    "retry_after",
    "duration_ms",
)


class SecretRedactor:
    """Best-effort log sanitizer for configured secrets and common token shapes."""

    def __init__(self, secrets: Iterable[str] = ()) -> None:
        self._secrets = tuple(
            sorted(
                {str(secret) for secret in secrets if secret and len(str(secret)) >= 6},
                key=len,
                reverse=True,
            )
        )

    def redact(self, value: object) -> str:
        text = str(value)
        for secret in self._secrets:
            text = text.replace(secret, _REDACTED)
        text = _TELEGRAM_TOKEN_RE.sub(_REDACTED, text)
        text = _BEARER_RE.sub(f"Bearer {_REDACTED}", text)
        text = _SENSITIVE_ASSIGNMENT_RE.sub(rf"\1{_REDACTED}", text)
        text = _SENSITIVE_QUERY_RE.sub(rf"\1{_REDACTED}", text)
        return _URL_CREDENTIAL_RE.sub(rf"\1{_REDACTED}\3", text)


class StructuredLogFormatter(logging.Formatter):
    """Emit one sanitized JSON object per log record."""

    def __init__(self, redactor: SecretRedactor | None = None) -> None:
        super().__init__()
        self.redactor = redactor or SecretRedactor()

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "timestamp": datetime.fromtimestamp(record.created, timezone.utc)
            .isoformat(timespec="milliseconds")
            .replace("+00:00", "Z"),
            "level": record.levelname,
            "logger": record.name,
            "message": self.redactor.redact(record.getMessage()),
        }
        for field in _STRUCTURED_FIELDS:
            value = getattr(record, field, None)
            if value is None:
                continue
            payload[field] = (
                self.redactor.redact(value) if isinstance(value, str) else value
            )
        if record.exc_info:
            payload["exception"] = self.redactor.redact(
                self.formatException(record.exc_info)
            )
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


class RedactingTextFormatter(logging.Formatter):
    """Keep CLI logs readable while applying the same secret sanitizer."""

    def __init__(self, redactor: SecretRedactor | None = None) -> None:
        super().__init__("%(asctime)s | %(levelname)s | %(name)s | %(message)s")
        self.redactor = redactor or SecretRedactor()

    def format(self, record: logging.LogRecord) -> str:
        return self.redactor.redact(super().format(record))


def configure_logging(
    *,
    level: str = "INFO",
    structured: bool = True,
    secrets: Iterable[str] = (),
    stream: TextIO | None = None,
    logger: logging.Logger | None = None,
) -> logging.Handler:
    """Install one deterministic sanitized handler on ``logger`` (root by default)."""
    target = logger or logging.getLogger()
    level_name = str(level or "INFO").strip().upper()
    level_value = getattr(logging, level_name, logging.INFO)
    redactor = SecretRedactor(secrets)
    handler = logging.StreamHandler(stream)
    handler.setFormatter(
        StructuredLogFormatter(redactor)
        if structured
        else RedactingTextFormatter(redactor)
    )
    for existing in tuple(target.handlers):
        target.removeHandler(existing)
        existing.close()
    target.setLevel(level_value)
    target.addHandler(handler)
    return handler
