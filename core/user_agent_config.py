from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import tomllib

from core.http_config import USER_AGENT
from core.proxy_config import PROXY_CONFIG_PROFILES
from core.settings import ROOT_DIR

USER_AGENT_CONFIG_PROFILES = PROXY_CONFIG_PROFILES


class UserAgentConfigError(RuntimeError):
    """Raised when a User-Agent profile is malformed or ambiguous."""


@dataclass(frozen=True, slots=True)
class UserAgentEntry:
    name: str
    value: str
    enabled: bool = True
    priority: int = 0


@dataclass(frozen=True, slots=True)
class UserAgentProfile:
    name: str
    enabled: bool = True
    user_agents: tuple[UserAgentEntry, ...] = ()

    @property
    def active(self) -> tuple[UserAgentEntry, ...]:
        if not self.enabled:
            return ()
        return tuple(entry for entry in self.user_agents if entry.enabled)

    @property
    def preferred(self) -> tuple[UserAgentEntry, ...]:
        active = self.active
        if not active:
            return ()
        top = max(entry.priority for entry in active)
        return tuple(entry for entry in active if entry.priority == top)


@dataclass(frozen=True, slots=True)
class UserAgentSettings:
    profiles: dict[str, UserAgentProfile]

    @classmethod
    def empty(cls) -> "UserAgentSettings":
        return cls(
            {name: UserAgentProfile(name=name) for name in USER_AGENT_CONFIG_PROFILES}
        )

    def profile(self, name: str) -> UserAgentProfile:
        key = (name or "").strip().casefold()
        return self.profiles.get(key, UserAgentProfile(name=key or "default"))

    def preferred(self, name: str) -> tuple[UserAgentEntry, ...]:
        return self.profile(name).preferred

    def effective_values(self, name: str) -> tuple[str, ...]:
        preferred = self.preferred(name)
        return tuple(entry.value for entry in preferred) if preferred else (USER_AGENT,)


def _validate_value(*, profile: str, entry_name: str, value: object) -> str:
    text = str(value or "").strip()
    if not text:
        raise UserAgentConfigError(
            f"User-Agent {entry_name!r} in profile {profile!r} has an empty value."
        )
    if "\r" in text or "\n" in text:
        raise UserAgentConfigError(
            f"User-Agent {entry_name!r} in profile {profile!r} contains a newline."
        )
    try:
        text.encode("latin-1")
    except UnicodeEncodeError as exc:
        raise UserAgentConfigError(
            f"User-Agent {entry_name!r} in profile {profile!r} must be HTTP header compatible."
        ) from exc
    return text


def _load_profile(path: Path, profile: str) -> UserAgentProfile:
    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise UserAgentConfigError(
            f"Could not parse User-Agent config {path}: {exc}"
        ) from exc

    unknown_top = set(raw) - {"enabled", "user_agent"}
    if unknown_top:
        raise UserAgentConfigError(
            f"Unknown keys in User-Agent profile {profile!r}: {sorted(unknown_top)}"
        )
    enabled = raw.get("enabled", True)
    if not isinstance(enabled, bool):
        raise UserAgentConfigError(
            f"User-Agent profile {profile!r} field 'enabled' must be true or false."
        )
    raw_entries = raw.get("user_agent", [])
    if not isinstance(raw_entries, list):
        raise UserAgentConfigError(
            f"User-Agent profile {profile!r} field 'user_agent' must be an array of tables."
        )

    entries: list[UserAgentEntry] = []
    seen_names: set[str] = set()
    for index, item in enumerate(raw_entries, 1):
        if not isinstance(item, dict):
            raise UserAgentConfigError(
                f"User-Agent profile {profile!r} entry #{index} must be a table."
            )
        unknown = set(item) - {"name", "enabled", "priority", "value"}
        if unknown:
            raise UserAgentConfigError(
                f"Unknown keys in User-Agent profile {profile!r} entry #{index}: {sorted(unknown)}"
            )
        name = str(item.get("name") or f"user-agent-{index}").strip()
        if not name:
            raise UserAgentConfigError(
                f"User-Agent profile {profile!r} entry #{index} has an empty name."
            )
        if name in seen_names:
            raise UserAgentConfigError(
                f"Duplicate User-Agent name {name!r} in profile {profile!r}."
            )
        seen_names.add(name)
        item_enabled = item.get("enabled", True)
        if not isinstance(item_enabled, bool):
            raise UserAgentConfigError(
                f"User-Agent {name!r} in profile {profile!r} field 'enabled' must be true or false."
            )
        priority = item.get("priority", 0)
        if isinstance(priority, bool) or not isinstance(priority, int):
            raise UserAgentConfigError(
                f"User-Agent {name!r} in profile {profile!r} field 'priority' must be an integer."
            )
        value = _validate_value(
            profile=profile, entry_name=name, value=item.get("value")
        )
        entries.append(
            UserAgentEntry(
                name=name, value=value, enabled=item_enabled, priority=priority
            )
        )
    return UserAgentProfile(name=profile, enabled=enabled, user_agents=tuple(entries))


def load_user_agent_settings(root_dir: Path = ROOT_DIR) -> UserAgentSettings:
    """Load only fixed per-profile TOML files from .user-agents.d/."""
    directory = root_dir / ".user-agents.d"
    profiles: dict[str, UserAgentProfile] = {}
    for profile in USER_AGENT_CONFIG_PROFILES:
        path = directory / f"{profile}.toml"
        profiles[profile] = (
            _load_profile(path, profile)
            if path.is_file()
            else UserAgentProfile(name=profile)
        )
    return UserAgentSettings(profiles)
