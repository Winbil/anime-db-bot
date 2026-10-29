from __future__ import annotations

import logging
import os
from datetime import datetime
from pathlib import Path

_LOG_STREAMS = frozenset({"bot", "users", "api"})


def classify_log_stream(record: logging.LogRecord) -> str:
    """Route a record to one stable low-cardinality file stream."""
    explicit = str(getattr(record, "log_stream", "") or "").strip().casefold()
    if explicit in _LOG_STREAMS:
        return explicit

    event = str(getattr(record, "event", "") or "").strip().casefold()
    if event == "telegram_update" or event.startswith("user_"):
        return "users"
    if event.startswith("source_"):
        return "api"
    return "bot"


class DailySplitFileHandler(logging.Handler):
    """Write records to date-scoped bot/users/api files with bounded size rotation."""

    def __init__(
        self,
        directory: Path | str,
        *,
        max_bytes: int = 10 * 1024 * 1024,
        backups: int = 5,
    ) -> None:
        super().__init__()
        self.directory = Path(directory)
        self.max_bytes = max(1, int(max_bytes))
        self.backups = max(0, int(backups))

    def emit(self, record: logging.LogRecord) -> None:
        try:
            rendered = self.format(record)
            day = (
                datetime.fromtimestamp(record.created).astimezone().strftime("%Y.%m.%d")
            )
            day_dir = self.directory / day
            day_dir.mkdir(parents=True, exist_ok=True)

            stream = classify_log_stream(record)
            self._write(day_dir / f"{stream}.log", rendered)
            if record.levelno >= logging.ERROR:
                self._write(day_dir / "errors.log", rendered)
        except Exception:
            self.handleError(record)

    def _write(self, path: Path, rendered: str) -> None:
        line = f"{rendered}\n"
        encoded_size = len(line.encode("utf-8"))
        self._rotate_if_needed(path, encoded_size)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(line)

    def _rotate_if_needed(self, path: Path, incoming_bytes: int) -> None:
        try:
            current_size = path.stat().st_size
        except FileNotFoundError:
            return
        if current_size + incoming_bytes <= self.max_bytes:
            return

        if self.backups == 0:
            path.write_text("", encoding="utf-8")
            return

        oldest = path.with_name(f"{path.name}.{self.backups}")
        if oldest.exists():
            oldest.unlink()
        for index in range(self.backups - 1, 0, -1):
            source = path.with_name(f"{path.name}.{index}")
            if source.exists():
                os.replace(source, path.with_name(f"{path.name}.{index + 1}"))
        if path.exists():
            os.replace(path, path.with_name(f"{path.name}.1"))
