from __future__ import annotations

import base64
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import httpx

from core.http_client import HttpClientPool
from core.http_config import USER_AGENT
from core.user_agent_config import (
    USER_AGENT_CONFIG_PROFILES,
    UserAgentConfigError,
    UserAgentEntry,
    UserAgentProfile,
    UserAgentSettings,
    load_user_agent_settings,
)


class UserAgentConfigTests(unittest.TestCase):
    def test_priority_and_profile_enablement(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            directory = root / ".user-agents.d"
            directory.mkdir()
            (directory / "kitsu.toml").write_text(
                """enabled = true
[[user_agent]]
name = "low"
priority = 1
value = "UA-low"
[[user_agent]]
name = "high-a"
priority = 100
value = "UA-high-a"
[[user_agent]]
name = "high-b"
priority = 100
value = "UA-high-b"
"""
            )
            settings = load_user_agent_settings(root)
        self.assertEqual(
            [e.name for e in settings.preferred("kitsu")], ["high-a", "high-b"]
        )
        self.assertEqual(settings.effective_values("mal"), (USER_AGENT,))

    def test_examples_cover_fixed_profiles_and_default_to_builtin(self) -> None:
        example_dir = Path(__file__).resolve().parents[1] / ".user-agents.example.d"
        self.assertEqual(
            {p.name for p in example_dir.glob("*.toml")},
            {f"{profile}.toml" for profile in USER_AGENT_CONFIG_PROFILES},
        )
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            directory = root / ".user-agents.d"
            directory.mkdir()
            for path in example_dir.glob("*.toml"):
                (directory / path.name).write_bytes(path.read_bytes())
            settings = load_user_agent_settings(root)
        self.assertTrue(
            all(
                settings.effective_values(name) == (USER_AGENT,)
                for name in USER_AGENT_CONFIG_PROFILES
            )
        )

    def test_invalid_priority_and_header_value_fail_fast(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            directory = root / ".user-agents.d"
            directory.mkdir()
            path = directory / "mal.toml"
            path.write_text('[[user_agent]]\nname="bad"\npriority=true\nvalue="UA"\n')
            with self.assertRaisesRegex(UserAgentConfigError, "priority"):
                load_user_agent_settings(root)
            path.write_text('[[user_agent]]\nname="bad"\nvalue="bad\\nheader"\n')
            with self.assertRaises(UserAgentConfigError):
                load_user_agent_settings(root)


class _CaptureClient:
    def __init__(self, headers_seen: list[dict[str, str]]) -> None:
        self.headers_seen = headers_seen

    async def request(self, method, url, **kwargs):
        self.headers_seen.append(dict(kwargs.get("headers") or {}))
        return httpx.Response(200, request=httpx.Request(method, url))

    async def aclose(self) -> None:
        return None


class UserAgentHttpTests(unittest.IsolatedAsyncioTestCase):
    async def test_top_priority_user_agents_rotate_and_override_caller_header(
        self,
    ) -> None:
        profile = UserAgentProfile(
            name="anilist",
            user_agents=(
                UserAgentEntry("low", "UA-low", priority=1),
                UserAgentEntry("high-a", "UA-high-a", priority=10),
                UserAgentEntry("high-b", "UA-high-b", priority=10),
            ),
        )
        pool = HttpClientPool(
            user_agent_settings=UserAgentSettings({"anilist": profile})
        )
        seen: list[dict[str, str]] = []
        with patch.object(pool, "_client", return_value=_CaptureClient(seen)):
            await pool.request(
                "anilist",
                "POST",
                "https://example.invalid",
                headers={"User-Agent": "hardcoded"},
            )
            await pool.request(
                "anilist",
                "POST",
                "https://example.invalid",
                headers={"User-Agent": "hardcoded"},
            )
        self.assertEqual([h["User-Agent"] for h in seen], ["UA-high-a", "UA-high-b"])
        await pool.aclose()

    async def test_jikan_forwards_selected_user_agent_to_outbound_service(self) -> None:
        profile = UserAgentProfile(
            name="jikan",
            user_agents=(UserAgentEntry("custom", "UA-Jikan", priority=20),),
        )
        pool = HttpClientPool(user_agent_settings=UserAgentSettings({"jikan": profile}))
        seen: list[dict[str, str]] = []
        with patch.object(pool, "_client", return_value=_CaptureClient(seen)):
            await pool.request("jikan", "GET", "http://127.0.0.1:8091/anime/1/people")
        encoded = seen[0]["X-Anime-DB-Bot-User-Agent"]
        encoded += "=" * (-len(encoded) % 4)
        self.assertEqual(
            base64.urlsafe_b64decode(encoded).decode("latin-1"), "UA-Jikan"
        )
        await pool.aclose()


if __name__ == "__main__":
    unittest.main()
