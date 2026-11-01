from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
import zstandard as zstd

from core.http_config import USER_AGENT
from core.sqlite import managed_sqlite_connection
from mappings.config import (
    mappings_auto_update,
    mappings_db_path,
    mappings_keep_previous,
    mappings_manifest_path,
    mappings_release_repository,
    mappings_request_timeout_seconds,
)
from mappings.resolver import copy_mapping_overrides

SUPPORTED_SCHEMA_VERSION = 3


@dataclass(frozen=True, slots=True)
class MappingUpdateResult:
    release_tag: str
    source_fingerprint: str
    runtime_bytes: int
    overrides_preserved: int


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _release_asset_url(repository: str, release_tag: str, asset_name: str) -> str:
    return (
        f"https://github.com/{repository}/releases/download/{release_tag}/{asset_name}"
    )


def _latest_manifest_url(repository: str) -> str:
    return f"https://github.com/{repository}/releases/latest/download/manifest.json"


def _timeout() -> httpx.Timeout:
    read_timeout = mappings_request_timeout_seconds()
    return httpx.Timeout(connect=30.0, read=read_timeout, write=30.0, pool=30.0)


def _fetch_manifest(repository: str) -> dict[str, Any]:
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    with httpx.Client(
        timeout=_timeout(), follow_redirects=True, headers=headers
    ) as client:
        response = client.get(_latest_manifest_url(repository))
        response.raise_for_status()
        payload = response.json()
    if not isinstance(payload, dict):
        raise RuntimeError("Mapping release manifest is not a JSON object")
    return payload


def _download(url: str, target: Path) -> str:
    digest = hashlib.sha256()
    headers = {"User-Agent": USER_AGENT, "Accept": "application/octet-stream"}
    with httpx.Client(
        timeout=_timeout(), follow_redirects=True, headers=headers
    ) as client:
        with client.stream("GET", url) as response:
            response.raise_for_status()
            with target.open("wb") as handle:
                for chunk in response.iter_bytes(chunk_size=1024 * 1024):
                    if not chunk:
                        continue
                    digest.update(chunk)
                    handle.write(chunk)
    return digest.hexdigest()


def _clean_manifest(payload: dict[str, Any], repository: str) -> dict[str, Any]:
    manifest_repository = str(payload.get("repository") or "").strip()
    if manifest_repository != repository:
        raise RuntimeError(
            f"Mapping manifest repository mismatch: expected {repository}, got {manifest_repository or '<empty>'}"
        )

    schema_value = payload.get("schema_version")
    if schema_value is None:
        raise RuntimeError("Mapping manifest schema_version is missing")
    try:
        schema_version = int(schema_value)
    except (TypeError, ValueError) as exc:
        raise RuntimeError("Mapping manifest schema_version is invalid") from exc
    if schema_version != SUPPORTED_SCHEMA_VERSION:
        raise RuntimeError(
            f"Unsupported mapping schema {schema_version}; expected {SUPPORTED_SCHEMA_VERSION}"
        )

    release_tag = str(payload.get("release_tag") or "").strip()
    source_fingerprint = str(payload.get("source_fingerprint") or "").strip().casefold()
    assets = payload.get("assets")
    if not release_tag or not source_fingerprint or not isinstance(assets, dict):
        raise RuntimeError("Mapping manifest is missing release identity or assets")

    runtime = assets.get("runtime")
    runtime_zstd = assets.get("runtime_zstd")
    if not isinstance(runtime, dict) or not isinstance(runtime_zstd, dict):
        raise RuntimeError("Mapping manifest is missing runtime assets")

    for label, asset in (("runtime", runtime), ("runtime_zstd", runtime_zstd)):
        name = str(asset.get("name") or "").strip()
        sha256 = str(asset.get("sha256") or "").strip().casefold()
        if (
            not name
            or len(sha256) != 64
            or any(ch not in "0123456789abcdef" for ch in sha256)
        ):
            raise RuntimeError(f"Mapping manifest {label} asset is invalid")
        size_value = asset.get("size")
        if size_value is None:
            raise RuntimeError(f"Mapping manifest {label} size is missing")
        try:
            size = int(size_value)
        except (TypeError, ValueError) as exc:
            raise RuntimeError(f"Mapping manifest {label} size is invalid") from exc
        if size <= 0:
            raise RuntimeError(f"Mapping manifest {label} size must be positive")
        asset["name"] = name
        asset["sha256"] = sha256
        asset["size"] = size

    payload["repository"] = manifest_repository
    payload["schema_version"] = schema_version
    payload["release_tag"] = release_tag
    payload["source_fingerprint"] = source_fingerprint
    return payload


def _read_local_manifest(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _write_manifest_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".new")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _validate_runtime_database(path: Path, manifest: dict[str, Any]) -> None:
    if not path.is_file():
        raise RuntimeError("Downloaded mapping runtime database is missing")
    uri = f"file:{path.resolve().as_posix()}?mode=ro"
    with managed_sqlite_connection(sqlite3.connect(uri, uri=True, timeout=5.0)) as conn:
        integrity = conn.execute("PRAGMA integrity_check").fetchone()
        if not integrity or str(integrity[0]) != "ok":
            raise RuntimeError(
                f"Downloaded mappings.db failed integrity_check: {integrity}"
            )
        metadata = {
            str(key): str(value)
            for key, value in conn.execute("SELECT key, value FROM metadata")
        }
        if metadata.get("database_role") != "runtime":
            raise RuntimeError("Downloaded mapping database is not a runtime database")
        if int(metadata.get("schema_version", 0)) != SUPPORTED_SCHEMA_VERSION:
            raise RuntimeError(
                "Downloaded mapping database schema does not match the bot"
            )
        if int(metadata.get("accepted_edges", 0)) <= 0:
            raise RuntimeError("Downloaded mapping database has no accepted edges")
        counts = manifest.get("counts")
        if isinstance(counts, dict):
            for key in ("datasets", "records", "edges", "accepted_edges", "conflicts"):
                if key not in counts:
                    continue
                try:
                    expected = int(counts[key])
                    actual = int(metadata.get(key, 0))
                except (TypeError, ValueError) as exc:
                    raise RuntimeError(f"Invalid mapping count for {key}") from exc
                if actual != expected:
                    raise RuntimeError(
                        f"Downloaded mapping database {key} mismatch: expected {expected}, got {actual}"
                    )


def _decompress_zstd(source: Path, target: Path) -> None:
    decompressor = zstd.ZstdDecompressor()
    with source.open("rb") as src, target.open("wb") as dst:
        decompressor.copy_stream(src, dst)


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


def update_mapping_database(*, force: bool = False) -> MappingUpdateResult | None:
    repository = mappings_release_repository().strip().strip("/")
    if not repository or repository.count("/") != 1:
        raise RuntimeError(f"Invalid mapping release repository: {repository!r}")

    db_path = mappings_db_path()
    manifest_path = mappings_manifest_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)

    remote = _clean_manifest(_fetch_manifest(repository), repository)
    local = _read_local_manifest(manifest_path)
    local_assets = local.get("assets")
    local_runtime = (
        local_assets.get("runtime") if isinstance(local_assets, dict) else {}
    )
    remote_runtime = remote["assets"]["runtime"]
    same_release = str(local.get("release_tag") or "") == remote["release_tag"]
    same_runtime = (
        isinstance(local_runtime, dict)
        and str(local_runtime.get("sha256") or "").casefold()
        == remote_runtime["sha256"]
    )
    if (
        not force
        and db_path.is_file()
        and same_release
        and same_runtime
        and int(local.get("schema_version") or 0) == SUPPORTED_SCHEMA_VERSION
    ):
        return None

    lock_path = db_path.with_suffix(db_path.suffix + ".lock")
    lock_fd = _acquire_lock(lock_path)
    if lock_fd is None:
        logging.info(
            "Mapping release update skipped: another updater holds %s", lock_path
        )
        return None
    os.close(lock_fd)

    compressed_path = db_path.with_suffix(db_path.suffix + ".download.zst")
    new_path = db_path.with_suffix(db_path.suffix + ".new")
    previous_path = db_path.with_suffix(db_path.suffix + ".previous")
    try:
        compressed_path.unlink(missing_ok=True)
        new_path.unlink(missing_ok=True)
        assets = remote["assets"]
        runtime_asset = assets["runtime"]
        compressed_asset = assets["runtime_zstd"]
        url = _release_asset_url(
            repository, remote["release_tag"], compressed_asset["name"]
        )
        actual_compressed_sha = _download(url, compressed_path)
        if actual_compressed_sha.casefold() != compressed_asset["sha256"]:
            raise RuntimeError(
                "Mapping release compressed SHA-256 mismatch: "
                f"expected {compressed_asset['sha256']}, got {actual_compressed_sha}"
            )
        if compressed_path.stat().st_size != compressed_asset["size"]:
            raise RuntimeError(
                "Mapping release compressed size mismatch: "
                f"expected {compressed_asset['size']}, got {compressed_path.stat().st_size}"
            )

        _decompress_zstd(compressed_path, new_path)
        actual_runtime_sha = _sha256_file(new_path)
        if actual_runtime_sha.casefold() != runtime_asset["sha256"]:
            raise RuntimeError(
                "Mapping release runtime SHA-256 mismatch: "
                f"expected {runtime_asset['sha256']}, got {actual_runtime_sha}"
            )
        if new_path.stat().st_size != runtime_asset["size"]:
            raise RuntimeError(
                "Mapping release runtime size mismatch: "
                f"expected {runtime_asset['size']}, got {new_path.stat().st_size}"
            )
        _validate_runtime_database(new_path, remote)

        overrides_preserved = 0
        if db_path.is_file():
            with managed_sqlite_connection(
                sqlite3.connect(new_path, timeout=5.0)
            ) as destination:
                overrides_preserved = copy_mapping_overrides(db_path, destination)
                integrity = destination.execute("PRAGMA integrity_check").fetchone()
                if not integrity or str(integrity[0]) != "ok":
                    raise RuntimeError(
                        f"mappings.db failed integrity after copying overrides: {integrity}"
                    )

        if mappings_keep_previous() and db_path.is_file():
            shutil.copy2(db_path, previous_path)
        os.replace(new_path, db_path)
        _write_manifest_atomic(manifest_path, remote)
        logging.info(
            "Mapping runtime updated from %s: release=%s fingerprint=%s bytes=%d overrides=%d",
            repository,
            remote["release_tag"],
            remote["source_fingerprint"],
            db_path.stat().st_size,
            overrides_preserved,
        )
        return MappingUpdateResult(
            release_tag=remote["release_tag"],
            source_fingerprint=remote["source_fingerprint"],
            runtime_bytes=db_path.stat().st_size,
            overrides_preserved=overrides_preserved,
        )
    finally:
        compressed_path.unlink(missing_ok=True)
        new_path.unlink(missing_ok=True)
        lock_path.unlink(missing_ok=True)


def update_if_stale() -> MappingUpdateResult | None:
    if not mappings_auto_update():
        return None
    return update_mapping_database(force=False)


def mapping_status() -> dict[str, object]:
    db_path = mappings_db_path()
    manifest_path = mappings_manifest_path()
    local = _read_local_manifest(manifest_path)
    metadata: dict[str, str] = {}
    if db_path.is_file():
        uri = f"file:{db_path.resolve().as_posix()}?mode=ro"
        try:
            with managed_sqlite_connection(
                sqlite3.connect(uri, uri=True, timeout=5.0)
            ) as conn:
                metadata = {
                    str(key): str(value)
                    for key, value in conn.execute(
                        "SELECT key, value FROM metadata ORDER BY key"
                    )
                }
        except sqlite3.DatabaseError:
            logging.exception("Could not read mappings.db metadata")
    return {
        "path": str(db_path),
        "available": db_path.is_file(),
        "manifest_path": str(manifest_path),
        "manifest_available": manifest_path.is_file(),
        "release_repository": mappings_release_repository(),
        "installed_release": str(local.get("release_tag") or ""),
        "source_fingerprint": str(local.get("source_fingerprint") or ""),
        "metadata": metadata,
    }
