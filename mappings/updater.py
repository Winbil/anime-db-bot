from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

from core.http_config import USER_AGENT
from mappings.config import (
    SOURCE_SPECS,
    MappingSourceSpec,
    mappings_auto_update,
    mappings_db_path,
    mappings_keep_downloads,
    mappings_keep_previous,
    mappings_request_timeout_seconds,
    mappings_update_max_age_hours,
    mappings_wikidata_check_interval_hours,
)
from mappings.database import MappingBuildStats, MappingDatabase, MappingDatabaseBuilder
from mappings.importers import IMPORTERS
from mappings.resolver import copy_mapping_overrides


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _download(spec: MappingSourceSpec, target: Path) -> str:
    timeout = httpx.Timeout(
        connect=30.0,
        read=mappings_request_timeout_seconds(),
        write=30.0,
        pool=30.0,
    )
    digest = hashlib.sha256()
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/sparql-results+json"
        if spec.importer == "wikidata_bahamut"
        else "*/*",
    }
    with httpx.Client(
        timeout=timeout, follow_redirects=True, headers=headers
    ) as client:
        with client.stream("GET", spec.url) as response:
            response.raise_for_status()
            with target.open("wb") as handle:
                for chunk in response.iter_bytes(chunk_size=1024 * 1024):
                    if not chunk:
                        continue
                    digest.update(chunk)
                    handle.write(chunk)

        actual = digest.hexdigest()
        if spec.checksum_url:
            checksum_response = client.get(spec.checksum_url)
            checksum_response.raise_for_status()
            expected = checksum_response.text.strip().split()[0].casefold()
            if expected and actual.casefold() != expected:
                raise RuntimeError(
                    f"Checksum mismatch for {spec.name}: expected {expected}, got {actual}"
                )
    return actual


def _dataset_state(path: Path) -> dict[str, tuple[str, str]]:
    if not path.is_file():
        return {}
    uri = f"file:{path.resolve().as_posix()}?mode=ro"
    try:
        with sqlite3.connect(uri, uri=True, timeout=5.0) as conn:
            return {
                str(name): (str(sha256), str(downloaded_at))
                for name, sha256, downloaded_at in conn.execute(
                    "SELECT name, sha256, downloaded_at FROM datasets"
                )
            }
    except sqlite3.DatabaseError:
        return {}


def _checked_at_timestamp(value: str) -> float | None:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.timestamp()


def _source_interval_hours(spec: MappingSourceSpec) -> float:
    if spec.check_interval == "wikidata":
        return mappings_wikidata_check_interval_hours()
    return mappings_update_max_age_hours()


def _source_due(
    spec: MappingSourceSpec,
    state: dict[str, tuple[str, str]],
    *,
    now: float | None = None,
) -> bool:
    current = state.get(spec.name)
    if current is None:
        return True
    checked_at = _checked_at_timestamp(current[1])
    if checked_at is None:
        return True
    current_time = time.time() if now is None else float(now)
    age_seconds = max(0.0, current_time - checked_at)
    return age_seconds >= _source_interval_hours(spec) * 3600.0


def _is_stale(path: Path) -> bool:
    state = _dataset_state(path)
    return not state or any(_source_due(spec, state) for spec in SOURCE_SPECS)


def _acquire_lock(lock_path: Path) -> int | None:
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        return os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        try:
            if time.time() - lock_path.stat().st_mtime > 6 * 3600:
                lock_path.unlink(missing_ok=True)
                return os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except OSError:
            pass
        return None


def _touch_checked_sources(path: Path, names: set[str], checked_at: str) -> None:
    if not names or not path.is_file():
        return
    with sqlite3.connect(path, timeout=5.0) as conn:
        conn.executemany(
            "UPDATE datasets SET downloaded_at=? WHERE name=?",
            [(checked_at, name) for name in sorted(names)],
        )
        conn.execute(
            "INSERT OR REPLACE INTO metadata(key, value) VALUES('last_source_check_at', ?)",
            (checked_at,),
        )
        conn.commit()


def _download_path(work_dir: Path, index: int, spec: MappingSourceSpec) -> Path:
    suffix = Path(spec.url.split("?", 1)[0]).suffix or ".data"
    return work_dir / f"{index:02d}-{spec.importer}{suffix}"


def update_mapping_database(*, force: bool = False) -> MappingBuildStats | None:
    db_path = mappings_db_path()
    state = _dataset_state(db_path)
    due_specs = (
        list(SOURCE_SPECS)
        if force or not state
        else [spec for spec in SOURCE_SPECS if _source_due(spec, state)]
    )
    if not due_specs:
        return None

    db_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = db_path.with_suffix(db_path.suffix + ".lock")
    lock_fd = _acquire_lock(lock_path)
    if lock_fd is None:
        logging.info("Mapping update skipped: another updater holds %s", lock_path)
        return None
    os.close(lock_fd)

    new_path = db_path.with_suffix(db_path.suffix + ".new")
    previous_path = db_path.with_suffix(db_path.suffix + ".previous")
    downloads_dir = db_path.parent / "downloads"
    work_dir = db_path.parent / ".update"
    work_dir.mkdir(parents=True, exist_ok=True)
    checked_at = _utc_now()
    staged: dict[str, tuple[Path, str]] = {}
    failed_optional: dict[str, str] = {}
    changed_sources: set[str] = set()

    try:
        for spec in due_specs:
            index = SOURCE_SPECS.index(spec)
            download_path = _download_path(work_dir, index, spec)
            download_path.unlink(missing_ok=True)
            logging.info("Mapping source check: %s", spec.name)
            try:
                sha256 = _download(spec, download_path)
                staged[spec.name] = (download_path, sha256)
                previous = state.get(spec.name)
                if previous is None or previous[0].casefold() != sha256.casefold():
                    changed_sources.add(spec.name)
            except Exception as exc:
                download_path.unlink(missing_ok=True)
                if spec.required:
                    raise RuntimeError(
                        f"Required mapping source failed: {spec.name}: {exc}"
                    ) from exc
                failed_optional[spec.name] = f"{type(exc).__name__}: {exc}"
                logging.warning(
                    "Optional mapping source unavailable during check: %s: %s",
                    spec.name,
                    exc,
                )

        successful_checks = set(staged)
        if db_path.is_file() and not force and not changed_sources:
            _touch_checked_sources(db_path, successful_checks, checked_at)
            logging.info(
                "Mapping sources unchanged; mappings.db kept in place (%d checked)",
                len(successful_checks),
            )
            return None

        new_path.unlink(missing_ok=True)
        required_loaded: set[str] = set()
        with MappingDatabaseBuilder(new_path) as builder:
            for index, spec in enumerate(SOURCE_SPECS):
                record_count = 0
                staged_item = staged.get(spec.name)
                if staged_item is not None:
                    download_path, sha256 = staged_item
                    logging.info("Mapping source ingest: %s", spec.name)
                    importer = IMPORTERS[spec.importer]
                    record_count = builder.ingest_dataset(
                        spec,
                        importer(download_path),
                        sha256=sha256,
                        downloaded_at=checked_at,
                    )
                    if record_count <= 0:
                        if spec.required:
                            raise RuntimeError(
                                f"Required mapping source produced zero usable records: {spec.name}"
                            )
                        failed_optional[spec.name] = (
                            "source produced zero usable mapping records"
                        )
                    elif mappings_keep_downloads():
                        downloads_dir.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(download_path, downloads_dir / download_path.name)
                elif db_path.is_file() and spec.name in state:
                    record_count = builder.copy_dataset_from(db_path, spec.name)
                    if record_count:
                        logging.info(
                            "Mapping source carried forward without network check: %s — %d records",
                            spec.name,
                            record_count,
                        )
                elif spec.name in failed_optional:
                    record_count = 0
                else:
                    download_path = _download_path(work_dir, index, spec)
                    download_path.unlink(missing_ok=True)
                    try:
                        sha256 = _download(spec, download_path)
                        importer = IMPORTERS[spec.importer]
                        record_count = builder.ingest_dataset(
                            spec,
                            importer(download_path),
                            sha256=sha256,
                            downloaded_at=checked_at,
                        )
                    finally:
                        download_path.unlink(missing_ok=True)

                if record_count > 0:
                    logging.info(
                        "Mapping source indexed: %s — %d records",
                        spec.name,
                        record_count,
                    )
                    if spec.required:
                        required_loaded.add(spec.name)

            expected_required = {spec.name for spec in SOURCE_SPECS if spec.required}
            missing_required = expected_required - required_loaded
            if missing_required:
                raise RuntimeError(
                    "Required mapping sources missing: "
                    + ", ".join(sorted(missing_required))
                )

            override_count = copy_mapping_overrides(db_path, builder.conn)
            if override_count:
                logging.info(
                    "Mapping overrides preserved in rebuild: %d", override_count
                )

            stats = builder.finalize(built_at=checked_at)
            builder.conn.execute(
                "INSERT OR REPLACE INTO metadata(key, value) VALUES('optional_failures', ?)",
                (json.dumps(failed_optional, ensure_ascii=False, sort_keys=True),),
            )
            builder.conn.execute(
                "INSERT OR REPLACE INTO metadata(key, value) VALUES('overrides', ?)",
                (str(override_count),),
            )
            builder.conn.execute(
                "INSERT OR REPLACE INTO metadata(key, value) VALUES('last_source_check_at', ?)",
                (checked_at,),
            )
            builder.conn.commit()

        if stats.datasets < len(required_loaded):
            raise RuntimeError(
                "mappings.db validation failed: dataset count is too small"
            )
        if stats.edges <= 0 or stats.accepted_edges <= 0:
            raise RuntimeError(
                "mappings.db validation failed: no accepted mapping edges"
            )

        if db_path.exists() and mappings_keep_previous():
            shutil.copy2(db_path, previous_path)
        os.replace(new_path, db_path)
        logging.info(
            "Mapping database updated: changed=%s datasets=%d records=%d evidence=%d edges=%d accepted=%d conflicts=%d overrides=%d",
            ",".join(sorted(changed_sources)) or "forced",
            stats.datasets,
            stats.records,
            stats.evidence,
            stats.edges,
            stats.accepted_edges,
            stats.conflicts,
            override_count,
        )
        return stats
    finally:
        new_path.unlink(missing_ok=True)
        for path, _sha in staged.values():
            path.unlink(missing_ok=True)
        try:
            if work_dir.exists() and not any(work_dir.iterdir()):
                work_dir.rmdir()
        except OSError:
            pass
        lock_path.unlink(missing_ok=True)


def update_if_stale() -> MappingBuildStats | None:
    if not mappings_auto_update():
        return None
    return update_mapping_database(force=False)


def mapping_status() -> dict[str, object]:
    database = MappingDatabase()
    metadata = database.metadata()
    return {
        "path": str(database.path),
        "available": database.available,
        "stale": _is_stale(database.path) if database.available else True,
        "metadata": metadata,
    }
