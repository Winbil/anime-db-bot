from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
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
)
from mappings.database import MappingBuildStats, MappingDatabase, MappingDatabaseBuilder
from mappings.importers import IMPORTERS


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
    headers = {"User-Agent": USER_AGENT}
    with httpx.Client(timeout=timeout, follow_redirects=True, headers=headers) as client:
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


def _is_stale(path: Path) -> bool:
    if not path.is_file():
        return True
    age_seconds = max(0.0, time.time() - path.stat().st_mtime)
    return age_seconds >= mappings_update_max_age_hours() * 3600.0


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


def update_mapping_database(*, force: bool = False) -> MappingBuildStats | None:
    db_path = mappings_db_path()
    if not force and not _is_stale(db_path):
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
    required_loaded: set[str] = set()
    failed_optional: dict[str, str] = {}

    try:
        new_path.unlink(missing_ok=True)
        with MappingDatabaseBuilder(new_path) as builder:
            for index, spec in enumerate(SOURCE_SPECS):
                suffix = Path(spec.url.split("?", 1)[0]).suffix or ".data"
                download_path = work_dir / f"{index:02d}-{spec.importer}{suffix}"
                download_path.unlink(missing_ok=True)
                logging.info("Mapping source download: %s", spec.name)
                try:
                    sha256 = _download(spec, download_path)
                    importer = IMPORTERS[spec.importer]
                    record_count = builder.ingest_dataset(
                        spec,
                        importer(download_path),
                        sha256=sha256,
                        downloaded_at=_utc_now(),
                    )
                    if record_count <= 0:
                        raise RuntimeError("source produced zero usable mapping records")
                    logging.info(
                        "Mapping source indexed: %s — %d records",
                        spec.name,
                        record_count,
                    )
                    if spec.required:
                        required_loaded.add(spec.name)
                    if mappings_keep_downloads():
                        downloads_dir.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(download_path, downloads_dir / download_path.name)
                except Exception as exc:
                    if spec.required:
                        raise RuntimeError(
                            f"Required mapping source failed: {spec.name}: {exc}"
                        ) from exc
                    failed_optional[spec.name] = f"{type(exc).__name__}: {exc}"
                    logging.warning(
                        "Optional mapping source unavailable: %s: %s",
                        spec.name,
                        exc,
                    )
                finally:
                    download_path.unlink(missing_ok=True)

            expected_required = {spec.name for spec in SOURCE_SPECS if spec.required}
            missing_required = expected_required - required_loaded
            if missing_required:
                raise RuntimeError(
                    "Required mapping sources missing: " + ", ".join(sorted(missing_required))
                )

            stats = builder.finalize(built_at=_utc_now())
            builder.conn.execute(
                "INSERT OR REPLACE INTO metadata(key, value) VALUES('optional_failures', ?)",
                (json.dumps(failed_optional, ensure_ascii=False, sort_keys=True),),
            )
            builder.conn.commit()

        if stats.datasets < len(required_loaded):
            raise RuntimeError("mappings.db validation failed: dataset count is too small")
        if stats.edges <= 0 or stats.accepted_edges <= 0:
            raise RuntimeError("mappings.db validation failed: no accepted mapping edges")

        if db_path.exists() and mappings_keep_previous():
            shutil.copy2(db_path, previous_path)
        os.replace(new_path, db_path)
        logging.info(
            "Mapping database updated: datasets=%d records=%d evidence=%d edges=%d accepted=%d conflicts=%d",
            stats.datasets,
            stats.records,
            stats.evidence,
            stats.edges,
            stats.accepted_edges,
            stats.conflicts,
        )
        return stats
    finally:
        new_path.unlink(missing_ok=True)
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
