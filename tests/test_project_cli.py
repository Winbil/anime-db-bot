from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from scripts import project


class CrossPlatformProjectCliTests(unittest.TestCase):
    def test_venv_python_uses_native_platform_layout(self) -> None:
        root = Path("project-root")
        self.assertEqual(
            project.venv_python(root, windows=False),
            root / ".venv" / "bin" / "python",
        )
        self.assertEqual(
            project.venv_python(root, windows=True),
            root / ".venv" / "Scripts" / "python.exe",
        )

    def test_initialize_config_copies_missing_files_without_overwrite(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            env_examples = root / ".env.example.d"
            proxy_examples = root / ".proxies.example.d"
            ua_examples = root / ".user-agents.example.d"
            env_examples.mkdir()
            proxy_examples.mkdir()
            ua_examples.mkdir()
            for filename in project.ENV_FILES:
                (env_examples / filename).write_text(
                    f"# {filename}\nVALUE_{filename.replace('.', '_')}=1\n",
                    encoding="utf-8",
                )
            for filename in project.PROFILE_FILES:
                (proxy_examples / filename).write_text(
                    "enabled = false\n", encoding="utf-8"
                )
                (ua_examples / filename).write_text(
                    "enabled = false\n", encoding="utf-8"
                )

            with patch.object(project, "ROOT_DIR", root):
                self.assertTrue(project.initialize_config())
                telegram = root / ".env.d" / "telegram.env"
                telegram.write_text("BOT_TOKEN=keep-me\n", encoding="utf-8")
                self.assertFalse(project.initialize_config())

            self.assertEqual(
                (root / ".env.d" / "telegram.env").read_text(encoding="utf-8"),
                "BOT_TOKEN=keep-me\n",
            )
            self.assertTrue((root / ".proxies.d" / "kitsu.toml").is_file())
            self.assertTrue((root / ".user-agents.d" / "telegram.toml").is_file())

    def test_cli_exposes_cross_platform_runtime_commands(self) -> None:
        parser = project.build_parser()
        for command in (
            "setup",
            "check",
            "run",
            "start",
            "stop",
            "restart",
            "status",
            "mappings",
            "baha-index",
            "doctor",
        ):
            with self.subTest(command=command):
                args = parser.parse_args([command])
                self.assertEqual(args.command, command)

    def test_start_sh_profile_contract_matches_project_profiles(self) -> None:
        start_sh = (project.ROOT_DIR / "start.sh").read_text(encoding="utf-8")
        self.assertNotIn("bahamut.toml", start_sh)
        self.assertNotIn("baha_anime_skip.toml", start_sh)
        for filename in project.PROFILE_FILES:
            with self.subTest(filename=filename):
                self.assertIn(filename, start_sh)

    def test_mappings_command_forwards_unknown_mapping_flags(self) -> None:
        with patch.object(project, "run_mappings", return_value=0) as run_mappings:
            self.assertEqual(project.main(["mappings", "--status"]), 0)
        run_mappings.assert_called_once_with(["--status"])

    def test_compose_uses_published_loopback_port_not_host_network(self) -> None:
        compose = (project.ROOT_DIR / "compose.yml").read_text(encoding="utf-8")
        dockerfile = (project.ROOT_DIR / "jikan_service" / "Dockerfile").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("network_mode: host", compose)
        self.assertIn("127.0.0.1:${JIKAN_PORT:-8091}:${JIKAN_PORT:-8091}", compose)
        self.assertIn("php -S 0.0.0.0:${JIKAN_PORT:-8091}", dockerfile)

    def test_jikan_start_uses_explicit_compose_file(self) -> None:
        with (
            patch.object(project, "docker_compose_available", return_value=True),
            patch.object(project, "_run") as run,
        ):
            self.assertTrue(project.ensure_jikan(build=True))
        command = run.call_args.args[0]
        self.assertEqual(
            command[:4],
            ["docker", "compose", "-f", str(project.ROOT_DIR / "compose.yml")],
        )
        self.assertIn("--build", command)
        self.assertEqual(command[-1], "jikan")


if __name__ == "__main__":
    unittest.main()
