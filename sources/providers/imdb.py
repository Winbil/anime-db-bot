from __future__ import annotations

import hashlib
import hmac
import json
import re
import sqlite3
from datetime import datetime, timezone
from urllib.parse import urlsplit

from core.http_client import http_request
from core.identity import AnimeIdentity
from core.imdb import IMDbRating
from core.settings import SourceSettings
from core.source_keys import SourceKey
from core.sqlite import managed_sqlite_connection
from services.runtime.rate_limits import wait_for_upstream

_IMDB_ID_RE = re.compile(r"^tt\d+$", re.IGNORECASE)
_IMDB_SITE_URL = "https://www.imdb.com/title/{imdb_id}/"
_API_QUERY = """query Rating($id: ID!) {
  title(id: $id) {
    ratingsSummary {
      aggregateRating
      voteCount
    }
  }
}"""


def _clean_imdb_id(value: object) -> str:
    raw = str(value or "").strip()
    return raw.casefold() if _IMDB_ID_RE.fullmatch(raw) else ""


def _sign(key: bytes, message: str) -> bytes:
    return hmac.new(key, message.encode("utf-8"), hashlib.sha256).digest()


def _sigv4_headers(
    *,
    endpoint: str,
    body: bytes,
    api_key: str,
    data_set_id: str,
    revision_id: str,
    asset_id: str,
    access_key_id: str,
    secret_access_key: str,
    session_token: str = "",
    region: str = "us-east-1",
    now: datetime | None = None,
) -> dict[str, str]:
    """Build AWS Signature V4 headers for IMDb's AWS Data Exchange API asset."""
    moment = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    amz_date = moment.strftime("%Y%m%dT%H%M%SZ")
    date_stamp = moment.strftime("%Y%m%d")
    parsed = urlsplit(endpoint)
    host = parsed.netloc
    canonical_uri = parsed.path or "/"
    payload_hash = hashlib.sha256(body).hexdigest()

    headers: dict[str, str] = {
        "content-type": "application/json",
        "host": host,
        "x-amz-content-sha256": payload_hash,
        "x-amz-date": amz_date,
        "x-amzn-dataexchange-asset-id": asset_id,
        "x-amzn-dataexchange-data-set-id": data_set_id,
        "x-amzn-dataexchange-revision-id": revision_id,
        "x-api-key": api_key,
    }
    if session_token:
        headers["x-amz-security-token"] = session_token

    signed_names = sorted(headers)
    canonical_headers = "".join(
        f"{name}:{' '.join(headers[name].split())}\n" for name in signed_names
    )
    signed_headers = ";".join(signed_names)
    canonical_request = "\n".join(
        (
            "POST",
            canonical_uri,
            parsed.query,
            canonical_headers,
            signed_headers,
            payload_hash,
        )
    )
    algorithm = "AWS4-HMAC-SHA256"
    credential_scope = f"{date_stamp}/{region}/dataexchange/aws4_request"
    string_to_sign = "\n".join(
        (
            algorithm,
            amz_date,
            credential_scope,
            hashlib.sha256(canonical_request.encode("utf-8")).hexdigest(),
        )
    )
    date_key = _sign(("AWS4" + secret_access_key).encode("utf-8"), date_stamp)
    region_key = _sign(date_key, region)
    service_key = _sign(region_key, "dataexchange")
    signing_key = _sign(service_key, "aws4_request")
    signature = hmac.new(
        signing_key, string_to_sign.encode("utf-8"), hashlib.sha256
    ).hexdigest()
    headers["authorization"] = (
        f"{algorithm} Credential={access_key_id}/{credential_scope}, "
        f"SignedHeaders={signed_headers}, Signature={signature}"
    )
    return headers


class IMDbRatingsSource:
    """IMDb rating supplement with local-dataset and licensed API backends."""

    name = "IMDb Ratings"
    display_name = "IMDb Ratings"
    source_key = SourceKey.IMDB
    backend_key = "imdb"

    def __init__(self, settings: SourceSettings) -> None:
        self._settings = settings
        self.db_path = settings.imdb_ratings_db_path
        backend = (settings.imdb_ratings_backend or "auto").strip().casefold()
        self.backend = backend if backend in {"auto", "local", "api", "off"} else "auto"

    @property
    def api_configured(self) -> bool:
        settings = self._settings
        return all(
            (
                settings.imdb_api_key,
                settings.imdb_api_data_set_id,
                settings.imdb_api_revision_id,
                settings.imdb_api_asset_id,
                settings.imdb_aws_access_key_id,
                settings.imdb_aws_secret_access_key,
            )
        )

    @property
    def status_mode(self) -> str:
        if self.backend == "off":
            return "unavailable"
        if self.backend == "api" or (self.backend == "auto" and self.api_configured):
            return "remote"
        return "local"

    @property
    def status_note(self) -> str:
        if self.backend == "api":
            return "IMDb GraphQL API"
        if self.backend == "auto" and self.api_configured:
            return "API → local fallback"
        if self.backend == "off":
            return "disabled"
        return "SQLite ratings"

    async def load_rating(self, identity: AnimeIdentity) -> IMDbRating | None:
        imdb_id = _clean_imdb_id(identity.get(SourceKey.IMDB.value))
        if not imdb_id or self.backend == "off":
            return None

        if self.backend == "api":
            if not self.api_configured:
                return None
            return await self._load_api(imdb_id)

        if self.backend == "auto" and self.api_configured:
            try:
                rating = await self._load_api(imdb_id)
            except Exception:
                rating = None
            if rating is not None:
                return rating

        return self._load_local(imdb_id)

    def _load_local(self, imdb_id: str) -> IMDbRating | None:
        if not self.db_path.is_file():
            return None
        uri = f"{self.db_path.resolve().as_uri()}?mode=ro"
        with managed_sqlite_connection(sqlite3.connect(uri, uri=True)) as connection:
            row = connection.execute(
                "SELECT rating, votes FROM ratings WHERE imdb_id = ?",
                (imdb_id,),
            ).fetchone()
        if row is None:
            return None
        rating = float(row[0])
        votes = int(row[1])
        return IMDbRating(
            imdb_id=imdb_id,
            rating=rating,
            votes=votes,
            url=_IMDB_SITE_URL.format(imdb_id=imdb_id),
            backend="local",
        )

    async def _load_api(self, imdb_id: str) -> IMDbRating | None:
        settings = self._settings
        await wait_for_upstream("imdb", "ratings")
        payload = json.dumps(
            {"query": _API_QUERY, "variables": {"id": imdb_id}},
            separators=(",", ":"),
        ).encode("utf-8")
        headers = _sigv4_headers(
            endpoint=settings.imdb_api_endpoint,
            body=payload,
            api_key=settings.imdb_api_key,
            data_set_id=settings.imdb_api_data_set_id,
            revision_id=settings.imdb_api_revision_id,
            asset_id=settings.imdb_api_asset_id,
            access_key_id=settings.imdb_aws_access_key_id,
            secret_access_key=settings.imdb_aws_secret_access_key,
            session_token=settings.imdb_aws_session_token,
            region=settings.imdb_aws_region,
        )
        response = await http_request(
            "imdb",
            "POST",
            settings.imdb_api_endpoint,
            operation="ratings",
            timeout=settings.imdb_request_timeout_seconds,
            headers=headers,
            content=payload,
        )
        data = response.json()
        if data.get("errors"):
            raise RuntimeError(f"IMDb GraphQL returned errors: {data['errors']!r}")
        summary = ((data.get("data") or {}).get("title") or {}).get(
            "ratingsSummary"
        ) or {}
        raw_rating = summary.get("aggregateRating")
        raw_votes = summary.get("voteCount")
        if raw_rating is None or raw_votes is None:
            return None
        rating = float(raw_rating)
        votes = int(raw_votes)
        if not 0 <= rating <= 10 or votes < 0:
            return None
        return IMDbRating(
            imdb_id=imdb_id,
            rating=rating,
            votes=votes,
            url=_IMDB_SITE_URL.format(imdb_id=imdb_id),
            backend="api",
        )
