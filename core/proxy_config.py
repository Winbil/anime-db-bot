from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import tomllib
from urllib.parse import unquote, urlsplit

from core.settings import ROOT_DIR

PROXY_CONFIG_PROFILES = (
    "telegram",
    "shikimori",
    "mal",
    "anilist",
    "kitsu",
    "anidb",
    "anisearch",
    "jikan",
    "aniskip",
    "anime_skip",
    "skipdb",
    "trace_moe",
    "whatanimeisthis",
)
_ALLOWED_PROXY_SCHEMES = {"http", "socks4", "socks5"}


class ProxyConfigError(RuntimeError):
    """Raised when a proxy profile is malformed or ambiguous."""


@dataclass(frozen=True, slots=True)
class ProxyEntry:
    name: str
    url: str
    enabled: bool = True
    priority: int = 0

    @property
    def scheme(self) -> str:
        return urlsplit(self.url).scheme.casefold()


@dataclass(frozen=True, slots=True)
class ProxyProfile:
    name: str
    enabled: bool = True
    proxies: tuple[ProxyEntry, ...] = ()

    @property
    def active(self) -> tuple[ProxyEntry, ...]:
        if not self.enabled:
            return ()
        return tuple(proxy for proxy in self.proxies if proxy.enabled)


@dataclass(frozen=True, slots=True)
class ProxySettings:
    profiles: dict[str, ProxyProfile]

    @classmethod
    def empty(cls) -> "ProxySettings":
        return cls({name: ProxyProfile(name=name) for name in PROXY_CONFIG_PROFILES})

    def profile(self, name: str) -> ProxyProfile:
        key = (name or "").strip().casefold()
        return self.profiles.get(key, ProxyProfile(name=key or "default"))

    def active(self, name: str) -> tuple[ProxyEntry, ...]:
        return self.profile(name).active

    def secret_values(self) -> tuple[str, ...]:
        """Return configured proxy credentials for the log redactor."""
        secrets: set[str] = set()
        for profile in self.profiles.values():
            for proxy in profile.proxies:
                parsed = urlsplit(proxy.url)
                if parsed.username:
                    secrets.add(unquote(parsed.username))
                if parsed.password:
                    secrets.add(unquote(parsed.password))
        return tuple(sorted(secrets, key=len, reverse=True))


def _validated_proxy_url(*, profile: str, entry_name: str, value: object) -> str:
    url = str(value or "").strip()
    if not url:
        raise ProxyConfigError(
            f"Proxy {entry_name!r} in profile {profile!r} has an empty url."
        )
    try:
        parsed = urlsplit(url)
        port = parsed.port
    except ValueError as exc:
        raise ProxyConfigError(
            f"Proxy {entry_name!r} in profile {profile!r} has an invalid port."
        ) from exc
    scheme = parsed.scheme.casefold()
    if scheme not in _ALLOWED_PROXY_SCHEMES:
        supported = ", ".join(sorted(_ALLOWED_PROXY_SCHEMES))
        raise ProxyConfigError(
            f"Proxy {entry_name!r} in profile {profile!r} uses unsupported scheme "
            f"{scheme!r}; supported schemes: {supported}."
        )
    if not parsed.hostname or port is None or port <= 0:
        raise ProxyConfigError(
            f"Proxy {entry_name!r} in profile {profile!r} must include host and port."
        )
    return url


def _load_profile(path: Path, profile: str) -> ProxyProfile:
    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ProxyConfigError(f"Could not parse proxy config {path}: {exc}") from exc

    unknown_top = set(raw) - {"enabled", "proxy"}
    if unknown_top:
        raise ProxyConfigError(
            f"Unknown keys in proxy profile {profile!r}: {sorted(unknown_top)}"
        )
    enabled = raw.get("enabled", True)
    if not isinstance(enabled, bool):
        raise ProxyConfigError(
            f"Proxy profile {profile!r} field 'enabled' must be true or false."
        )

    raw_entries = raw.get("proxy", [])
    if not isinstance(raw_entries, list):
        raise ProxyConfigError(
            f"Proxy profile {profile!r} field 'proxy' must be an array of tables."
        )

    entries: list[ProxyEntry] = []
    seen_names: set[str] = set()
    for index, item in enumerate(raw_entries, 1):
        if not isinstance(item, dict):
            raise ProxyConfigError(
                f"Proxy profile {profile!r} entry #{index} must be a table."
            )
        unknown = set(item) - {"name", "enabled", "priority", "url"}
        if unknown:
            raise ProxyConfigError(
                f"Unknown keys in proxy profile {profile!r} entry #{index}: "
                f"{sorted(unknown)}"
            )
        name = str(item.get("name") or f"proxy-{index}").strip()
        if not name:
            raise ProxyConfigError(
                f"Proxy profile {profile!r} entry #{index} has an empty name."
            )
        if name in seen_names:
            raise ProxyConfigError(
                f"Duplicate proxy name {name!r} in profile {profile!r}. "
                "Duplicate URLs are allowed, but entry names must be unique."
            )
        seen_names.add(name)
        item_enabled = item.get("enabled", True)
        if not isinstance(item_enabled, bool):
            raise ProxyConfigError(
                f"Proxy {name!r} in profile {profile!r} field 'enabled' must be true or false."
            )
        priority = item.get("priority", 0)
        if isinstance(priority, bool) or not isinstance(priority, int):
            raise ProxyConfigError(
                f"Proxy {name!r} in profile {profile!r} field 'priority' must be an integer."
            )
        url = _validated_proxy_url(
            profile=profile,
            entry_name=name,
            value=item.get("url"),
        )
        entries.append(
            ProxyEntry(name=name, url=url, enabled=item_enabled, priority=priority)
        )

    return ProxyProfile(name=profile, enabled=enabled, proxies=tuple(entries))


def load_proxy_settings(root_dir: Path = ROOT_DIR) -> ProxySettings:
    """Load only fixed per-profile TOML files from .proxies.d/."""
    directory = root_dir / ".proxies.d"
    profiles: dict[str, ProxyProfile] = {}
    for profile in PROXY_CONFIG_PROFILES:
        path = directory / f"{profile}.toml"
        profiles[profile] = (
            _load_profile(path, profile)
            if path.is_file()
            else ProxyProfile(name=profile)
        )
    return ProxySettings(profiles)
