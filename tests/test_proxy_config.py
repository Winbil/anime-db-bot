from __future__ import annotations

import base64
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import httpx
from python_socks import ProxyConnectionError, ProxyTimeoutError

from core.http_client import HttpClientPool
from core.proxy_config import (
    PROXY_CONFIG_PROFILES,
    ProxyConfigError,
    ProxyEntry,
    ProxyProfile,
    ProxySettings,
    load_proxy_settings,
)
from core.source_errors import SourceTimeout, SourceUnavailable, normalize_source_error


class ProxyConfigTests(unittest.TestCase):
    def test_fixed_profile_files_ignore_stray_configs_and_keep_duplicate_urls(
        self,
    ) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            directory = root / ".proxies.d"
            directory.mkdir()
            (directory / "mal.toml").write_text(
                """enabled = true

[[proxy]]
name = "primary"
enabled = true
url = "http://user:pass@127.0.0.1:8080"

[[proxy]]
name = "weighted-copy"
enabled = true
url = "http://user:pass@127.0.0.1:8080"

[[proxy]]
name = "disabled"
enabled = false
url = "socks5://127.0.0.1:1080"
""",
                encoding="utf-8",
            )
            (directory / "backup.toml").write_text(
                '[[proxy]]\nurl = "socks5://127.0.0.1:9999"\n',
                encoding="utf-8",
            )

            settings = load_proxy_settings(root)

        self.assertEqual(set(settings.profiles), set(PROXY_CONFIG_PROFILES))
        self.assertEqual(
            [entry.name for entry in settings.active("mal")],
            ["primary", "weighted-copy"],
        )
        self.assertEqual(
            settings.active("mal")[0].url,
            settings.active("mal")[1].url,
        )
        self.assertEqual(settings.active("backup"), ())
        self.assertEqual(set(settings.secret_values()), {"user", "pass"})

    def test_profile_switch_disables_all_entries_without_mutating_them(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            directory = root / ".proxies.d"
            directory.mkdir()
            (directory / "anilist.toml").write_text(
                """enabled = false
[[proxy]]
name = "configured"
enabled = true
url = "socks4://127.0.0.1:1080"
""",
                encoding="utf-8",
            )
            settings = load_proxy_settings(root)

        self.assertEqual(len(settings.profile("anilist").proxies), 1)
        self.assertEqual(settings.active("anilist"), ())

    def test_supported_proxy_schemes(self) -> None:
        schemes = ("http", "socks4", "socks5")
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            directory = root / ".proxies.d"
            directory.mkdir()
            body = ["enabled = true"]
            for index, scheme in enumerate(schemes, 1):
                body.extend(
                    [
                        "",
                        "[[proxy]]",
                        f'name = "p{index}"',
                        "enabled = true",
                        f'url = "{scheme}://127.0.0.1:{1000 + index}"',
                    ]
                )
            (directory / "kitsu.toml").write_text("\n".join(body) + "\n")
            settings = load_proxy_settings(root)

        self.assertEqual(
            [entry.scheme for entry in settings.active("kitsu")], list(schemes)
        )

    def test_example_directory_has_every_fixed_profile_and_no_active_entries(
        self,
    ) -> None:
        example_dir = Path(__file__).resolve().parents[1] / ".proxies.example.d"
        self.assertEqual(
            {path.name for path in example_dir.glob("*.toml")},
            {f"{profile}.toml" for profile in PROXY_CONFIG_PROFILES},
        )
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            directory = root / ".proxies.d"
            directory.mkdir()
            for path in example_dir.glob("*.toml"):
                (directory / path.name).write_bytes(path.read_bytes())
            settings = load_proxy_settings(root)

        self.assertTrue(
            all(not settings.active(name) for name in PROXY_CONFIG_PROFILES)
        )

    def test_jikan_router_applies_forwarded_proxy_to_outbound_mal_client(self) -> None:
        router = (
            Path(__file__).resolve().parents[1]
            / "jikan_service"
            / "public"
            / "router.php"
        ).read_text(encoding="utf-8")

        self.assertIn("HTTP_X_ANIME_DB_BOT_PROXY", router)
        self.assertIn("new CurlHttpClient(['proxy' => $proxy])", router)
        self.assertEqual(router.count("$client = malClient();"), 7)

    def test_invalid_scheme_and_duplicate_names_fail_fast(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            directory = root / ".proxies.d"
            directory.mkdir()
            (directory / "mal.toml").write_text(
                '[[proxy]]\nname = "bad"\nurl = "ftp://127.0.0.1:21"\n',
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ProxyConfigError, "unsupported scheme"):
                load_proxy_settings(root)

            (directory / "mal.toml").write_text(
                """[[proxy]]
name = "same"
url = "http://127.0.0.1:8001"
[[proxy]]
name = "same"
url = "http://127.0.0.1:8002"
""",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ProxyConfigError, "Duplicate proxy name"):
                load_proxy_settings(root)


class ProxyErrorNormalizationTests(unittest.TestCase):
    def test_python_socks_transport_errors_are_transient(self) -> None:
        unavailable = normalize_source_error(
            ProxyConnectionError("proxy down"),
            source="kitsu",
            operation="search",
        )
        timeout = normalize_source_error(
            ProxyTimeoutError("proxy timeout"),
            source="kitsu",
            operation="search",
        )

        self.assertIsInstance(unavailable, SourceUnavailable)
        self.assertTrue(unavailable.transient)
        self.assertIsInstance(timeout, SourceTimeout)
        self.assertTrue(timeout.transient)


class _FakeClient:
    def __init__(self, result: httpx.Response | BaseException) -> None:
        self.result = result

    async def request(self, *args, **kwargs) -> httpx.Response:
        if isinstance(self.result, BaseException):
            raise self.result
        return self.result

    async def aclose(self) -> None:
        return None


def _ok_response() -> httpx.Response:
    return httpx.Response(
        200,
        json={"ok": True},
        request=httpx.Request("GET", "https://example.invalid/test"),
    )


class HttpProxyPoolTests(unittest.IsolatedAsyncioTestCase):
    async def test_source_proxy_pool_round_robins_and_fails_over_without_direct_fallback(
        self,
    ) -> None:
        entries = (
            ProxyEntry("one", "http://127.0.0.1:8001"),
            ProxyEntry("two", "socks5://127.0.0.1:8002"),
        )
        settings = ProxySettings({"mal": ProxyProfile(name="mal", proxies=entries)})
        pool = HttpClientPool(settings)
        seen: list[str] = []
        first_failure = httpx.ConnectError(
            "proxy one unavailable",
            request=httpx.Request("GET", "https://example.invalid/test"),
        )

        def client_factory(profile, *, proxy=None, proxy_slot=-1):
            self.assertEqual(profile, "mal")
            self.assertIsNotNone(proxy)
            seen.append(proxy.name)
            if proxy.name == "one" and seen.count("one") == 1:
                return _FakeClient(first_failure)
            return _FakeClient(_ok_response())

        with patch.object(pool, "_client", side_effect=client_factory):
            first = await pool.request("mal", "GET", "https://example.invalid/test")
            second = await pool.request("mal", "GET", "https://example.invalid/test")

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(seen, ["one", "two", "two"])
        await pool.aclose()

    async def test_proxy_gateway_status_fails_over_to_next_entry(self) -> None:
        entries = (
            ProxyEntry("one", "http://127.0.0.1:8001"),
            ProxyEntry("two", "http://127.0.0.1:8002"),
        )
        pool = HttpClientPool(
            ProxySettings({"mal": ProxyProfile(name="mal", proxies=entries)})
        )
        seen: list[str] = []
        bad_gateway = httpx.Response(
            502,
            request=httpx.Request("GET", "https://example.invalid/test"),
        )

        def client_factory(profile, *, proxy=None, proxy_slot=-1):
            self.assertIsNotNone(proxy)
            seen.append(proxy.name)
            return _FakeClient(bad_gateway if proxy.name == "one" else _ok_response())

        with patch.object(pool, "_client", side_effect=client_factory):
            response = await pool.request("mal", "GET", "https://example.invalid/test")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(seen, ["one", "two"])
        await pool.aclose()

    async def test_jikan_proxy_is_forwarded_to_local_backend_not_used_for_loopback_hop(
        self,
    ) -> None:
        entry = ProxyEntry("jikan-socks", "socks5://user:pass@127.0.0.1:1080")
        pool = HttpClientPool(
            ProxySettings({"jikan": ProxyProfile(name="jikan", proxies=(entry,))})
        )
        seen_proxy: list[object] = []
        seen_headers: list[dict[str, str]] = []

        class _JikanClient(_FakeClient):
            async def request(self, *args, **kwargs):
                seen_headers.append(dict(kwargs.get("headers") or {}))
                return await super().request(*args, **kwargs)

        def client_factory(profile, *, proxy=None, proxy_slot=-1):
            self.assertEqual(profile, "jikan")
            seen_proxy.append(proxy)
            return _JikanClient(_ok_response())

        with patch.object(pool, "_client", side_effect=client_factory):
            response = await pool.request(
                "jikan", "GET", "http://127.0.0.1:8091/anime/1/people"
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(seen_proxy, [None])
        encoded = seen_headers[0]["X-Anime-DB-Bot-Proxy"]
        padded = encoded + "=" * (-len(encoded) % 4)
        self.assertEqual(
            base64.urlsafe_b64decode(padded).decode(),
            entry.url,
        )
        await pool.aclose()

    async def test_all_failed_proxies_raise_instead_of_leaking_to_direct(self) -> None:
        entries = (
            ProxyEntry("one", "http://127.0.0.1:8001"),
            ProxyEntry("two", "socks4://127.0.0.1:8002"),
        )
        pool = HttpClientPool(
            ProxySettings({"kitsu": ProxyProfile(name="kitsu", proxies=entries)})
        )
        seen: list[str] = []

        def client_factory(profile, *, proxy=None, proxy_slot=-1):
            self.assertIsNotNone(proxy)
            seen.append(proxy.name)
            return _FakeClient(
                httpx.ConnectError(
                    f"{proxy.name} down",
                    request=httpx.Request("GET", "https://example.invalid/test"),
                )
            )

        with patch.object(pool, "_client", side_effect=client_factory):
            with self.assertRaises(SourceUnavailable):
                await pool.request("kitsu", "GET", "https://example.invalid/test")

        self.assertEqual(seen, ["one", "two"])
        await pool.aclose()

    async def test_disabled_proxy_profile_uses_direct_client(self) -> None:
        entry = ProxyEntry("configured", "socks5://127.0.0.1:8002")
        pool = HttpClientPool(
            ProxySettings(
                {
                    "anilist": ProxyProfile(
                        name="anilist",
                        enabled=False,
                        proxies=(entry,),
                    )
                }
            )
        )
        seen: list[object] = []

        def client_factory(profile, *, proxy=None, proxy_slot=-1):
            seen.append(proxy)
            return _FakeClient(_ok_response())

        with patch.object(pool, "_client", side_effect=client_factory):
            response = await pool.request(
                "anilist", "POST", "https://example.invalid/graphql"
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(seen, [None])
        await pool.aclose()


if __name__ == "__main__":
    unittest.main()
