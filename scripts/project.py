from __future__ import annotations

import argparse
import csv
import os
from pathlib import Path
import platform
import shutil
import signal
import subprocess
import sys
import time
import venv

ROOT_DIR = Path(__file__).resolve().parents[1]
VENV_DIR = ROOT_DIR / ".venv"
PID_FILE = ROOT_DIR / "data" / "runtime" / "anime-db-bot.pid"
LAUNCHER_LOG = ROOT_DIR / "logs" / "launcher.log"
BOT_MODULE = "bots.telegram.bot"
SUPPORTED_PYTHON = {(3, 11), (3, 12), (3, 13), (3, 14)}
ENV_FILES = (
    "telegram.env",
    "sources.env",
    "timestamps.env",
    "rate-limits.env",
    "mappings.env",
    "storage.env",
    "logging.env",
    "runtime.env",
)
PROFILE_FILES = (
    "telegram.toml",
    "shikimori.toml",
    "mal.toml",
    "anilist.toml",
    "kitsu.toml",
    "anidb.toml",
    "anisearch.toml",
    "jikan.toml",
    "aniskip.toml",
    "anime_skip.toml",
    "bahamut.toml",
    "baha_anime_skip.toml",
    "skipdb.toml",
    "trace_moe.toml",
    "whatanimeisthis.toml",
)


def _info(message: str) -> None:
    print(f"[anime-db-bot] {message}", flush=True)


def _fail(message: str, code: int = 1) -> int:
    print(f"[anime-db-bot] ERROR: {message}", file=sys.stderr, flush=True)
    return code


def _is_windows() -> bool:
    return os.name == "nt"


def venv_python(root: Path = ROOT_DIR, *, windows: bool | None = None) -> Path:
    use_windows = _is_windows() if windows is None else windows
    if use_windows:
        return root / ".venv" / "Scripts" / "python.exe"
    return root / ".venv" / "bin" / "python"


def _python_supported() -> bool:
    return sys.version_info[:2] in SUPPORTED_PYTHON


def _require_supported_python() -> bool:
    if _python_supported():
        return True
    supported = ", ".join(
        f"{major}.{minor}" for major, minor in sorted(SUPPORTED_PYTHON)
    )
    _fail(
        f"Python {sys.version_info.major}.{sys.version_info.minor} is not supported; "
        f"use one of: {supported}."
    )
    return False


def _run(
    command: list[str],
    *,
    check: bool = True,
    capture: bool = False,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=ROOT_DIR,
        check=check,
        text=True,
        capture_output=capture,
        env=env,
    )


def _chmod_private(path: Path, mode: int) -> None:
    if _is_windows():
        return
    try:
        path.chmod(mode)
    except OSError:
        pass


def _copy_missing_directory(
    example_name: str,
    runtime_name: str,
    filenames: tuple[str, ...],
) -> bool:
    example_dir = ROOT_DIR / example_name
    runtime_dir = ROOT_DIR / runtime_name
    if not example_dir.is_dir():
        raise RuntimeError(f"Missing example directory: {example_dir}")
    runtime_dir.mkdir(parents=True, exist_ok=True)
    _chmod_private(runtime_dir, 0o700)
    created = False
    for filename in filenames:
        source = example_dir / filename
        target = runtime_dir / filename
        if not source.is_file():
            raise RuntimeError(f"Missing example file: {source}")
        if not target.exists():
            shutil.copyfile(source, target)
            created = True
        _chmod_private(target, 0o600)
    return created


def initialize_config() -> bool:
    """Create missing runtime config from committed examples without overwriting values."""
    created_env = False
    legacy_env = ROOT_DIR / ".env"
    split_dir = ROOT_DIR / ".env.d"
    has_split = any((split_dir / filename).is_file() for filename in ENV_FILES)
    if not legacy_env.is_file() and not has_split:
        created_env = _copy_missing_directory(".env.example.d", ".env.d", ENV_FILES)
    elif split_dir.is_dir():
        _chmod_private(split_dir, 0o700)
        for filename in ENV_FILES:
            path = split_dir / filename
            if path.is_file():
                _chmod_private(path, 0o600)

    _copy_missing_directory(".proxies.example.d", ".proxies.d", PROFILE_FILES)
    _copy_missing_directory(".user-agents.example.d", ".user-agents.d", PROFILE_FILES)
    return created_env


def _venv_ready() -> bool:
    python = venv_python()
    if not python.is_file():
        return False
    result = subprocess.run(
        [str(python), "-m", "pip", "--version"],
        cwd=ROOT_DIR,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return result.returncode == 0


def setup_environment(*, dev: bool = False) -> int:
    if not _require_supported_python():
        return 2
    requirements = ROOT_DIR / "requirements.lock"
    if not requirements.is_file():
        return _fail("requirements.lock not found.")

    if not _venv_ready():
        _info(f"Creating virtual environment: {VENV_DIR}")
        if VENV_DIR.exists():
            shutil.rmtree(VENV_DIR)
        try:
            venv.EnvBuilder(with_pip=True).create(VENV_DIR)
        except Exception as exc:
            return _fail(f"Could not create virtual environment: {exc}")

    python = venv_python()
    _info(f"Installing locked dependencies with {python}")
    try:
        _run(
            [
                str(python),
                "-m",
                "pip",
                "install",
                "--disable-pip-version-check",
                "-r",
                str(requirements),
            ]
        )
        if dev:
            _run(
                [
                    str(python),
                    "-m",
                    "pip",
                    "install",
                    "--disable-pip-version-check",
                    "-r",
                    str(ROOT_DIR / "requirements-dev.txt"),
                ]
            )
        _run([str(python), "-m", "pip", "check"])
    except subprocess.CalledProcessError as exc:
        return _fail(f"Dependency installation failed with exit code {exc.returncode}.")

    try:
        created_env = initialize_config()
    except Exception as exc:
        return _fail(f"Could not initialize configuration: {exc}")

    _info(f"Environment ready: {_python_version(python)}")
    if created_env:
        _info(
            "Created .env.d from .env.example.d; add BOT_TOKEN before running the bot."
        )
    return 0


def _python_version(python: Path) -> str:
    result = subprocess.run(
        [str(python), "--version"],
        cwd=ROOT_DIR,
        text=True,
        capture_output=True,
        check=False,
    )
    return (result.stdout or result.stderr).strip()


def _ensure_environment() -> int:
    if _venv_ready():
        try:
            initialize_config()
        except Exception as exc:
            return _fail(f"Could not initialize configuration: {exc}")
        return 0
    _info("Virtual environment is missing or incomplete; running setup.")
    return setup_environment()


def _validate_runtime_config() -> int:
    python = venv_python()
    code = (
        "from core.settings import get_settings; "
        "settings=get_settings(); "
        "raise SystemExit(0 if settings.telegram.bot_token else 2)"
    )
    result = subprocess.run([str(python), "-c", code], cwd=ROOT_DIR, check=False)
    if result.returncode == 0:
        return 0
    if result.returncode == 2:
        return _fail("BOT_TOKEN is empty in .env.d/telegram.env (or legacy .env).")
    return _fail("Configuration loading failed; check .env.d and profile TOML files.")


def docker_compose_available() -> bool:
    if shutil.which("docker") is None:
        return False
    result = subprocess.run(
        ["docker", "compose", "version"],
        cwd=ROOT_DIR,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return result.returncode == 0


def ensure_jikan(*, build: bool = True) -> bool:
    if not docker_compose_available():
        _info(
            "Docker Compose is unavailable; continuing without the optional local Jikan supplement."
        )
        return False
    command = ["docker", "compose", "-f", str(ROOT_DIR / "compose.yml"), "up", "-d"]
    if build:
        command.append("--build")
    command.append("jikan")
    try:
        _run(command)
    except subprocess.CalledProcessError:
        _info(
            "Could not start the optional Jikan supplement; continuing with official MAL data."
        )
        return False
    _info("Local Jikan supplement is running through Docker Compose.")
    return True


def check_project(*, coverage: bool = False) -> int:
    if _ensure_environment() != 0:
        return 1
    python = venv_python()
    _info("Compiling Python sources...")
    modules = [
        "bots",
        "core",
        "localization",
        "mappings",
        "search",
        "services",
        "sources",
        "tests",
        "scripts",
    ]
    if (
        _run([str(python), "-m", "compileall", "-q", *modules], check=False).returncode
        != 0
    ):
        return _fail("Python compilation failed.")
    _info("Running unit tests...")
    if coverage:
        command = [
            str(python),
            "-m",
            "coverage",
            "run",
            "-m",
            "unittest",
            "discover",
            "-s",
            "tests",
            "-v",
        ]
    else:
        command = [str(python), "-m", "unittest", "discover", "-s", "tests", "-v"]
    result = _run(command, check=False)
    if result.returncode != 0:
        return result.returncode
    if coverage:
        return _run(
            [str(python), "-m", "coverage", "report", "--fail-under=70"], check=False
        ).returncode
    return 0


def run_bot(*, no_jikan: bool = False) -> int:
    if _ensure_environment() != 0 or _validate_runtime_config() != 0:
        return 1
    if not no_jikan:
        ensure_jikan()
    python = venv_python()
    _info(f"Starting {BOT_MODULE} in the foreground on {platform.system()}.")
    process = subprocess.run([str(python), "-m", BOT_MODULE], cwd=ROOT_DIR, check=False)
    return int(process.returncode)


def _read_pid() -> int | None:
    try:
        raw = PID_FILE.read_text(encoding="utf-8").strip()
        pid = int(raw)
    except (FileNotFoundError, OSError, ValueError):
        return None
    return pid if pid > 0 else None


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if _is_windows():
        result = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
            text=True,
            capture_output=True,
            check=False,
        )
        if result.returncode != 0:
            return False
        for row in csv.reader(result.stdout.splitlines()):
            if len(row) > 1 and row[1].strip() == str(pid):
                return True
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def status_bot() -> int:
    pid = _read_pid()
    if pid is None:
        _info("No launcher-managed bot PID is recorded.")
        return 1
    if _pid_alive(pid):
        _info(f"Bot is running (PID {pid}).")
        return 0
    _info(f"Removing stale PID file for PID {pid}.")
    PID_FILE.unlink(missing_ok=True)
    return 1


def start_bot(*, no_jikan: bool = False) -> int:
    existing = _read_pid()
    if existing and _pid_alive(existing):
        _info(f"Bot is already running (PID {existing}).")
        return 0
    PID_FILE.unlink(missing_ok=True)
    if _ensure_environment() != 0 or _validate_runtime_config() != 0:
        return 1
    if not no_jikan:
        ensure_jikan()

    PID_FILE.parent.mkdir(parents=True, exist_ok=True)
    LAUNCHER_LOG.parent.mkdir(parents=True, exist_ok=True)
    python = venv_python()
    env = os.environ.copy()
    env.setdefault("PYTHONUNBUFFERED", "1")
    with LAUNCHER_LOG.open("ab", buffering=0) as log_file:
        if _is_windows():
            creationflags = int(
                getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
                | getattr(subprocess, "DETACHED_PROCESS", 0)
            )
            process = subprocess.Popen(
                [str(python), "-m", BOT_MODULE],
                cwd=ROOT_DIR,
                stdin=subprocess.DEVNULL,
                stdout=log_file,
                stderr=subprocess.STDOUT,
                env=env,
                close_fds=True,
                creationflags=creationflags,
            )
        else:
            process = subprocess.Popen(
                [str(python), "-m", BOT_MODULE],
                cwd=ROOT_DIR,
                stdin=subprocess.DEVNULL,
                stdout=log_file,
                stderr=subprocess.STDOUT,
                env=env,
                close_fds=True,
                start_new_session=True,
            )
    PID_FILE.write_text(f"{process.pid}\n", encoding="utf-8")
    time.sleep(0.6)
    if process.poll() is not None:
        PID_FILE.unlink(missing_ok=True)
        return _fail(
            f"Bot exited immediately with code {process.returncode}; see {LAUNCHER_LOG}."
        )
    _info(f"Bot started in the background (PID {process.pid}).")
    _info(f"Launcher output: {LAUNCHER_LOG}")
    return 0


def stop_bot() -> int:
    pid = _read_pid()
    if pid is None:
        _info("No launcher-managed bot process is running.")
        return 0
    if not _pid_alive(pid):
        PID_FILE.unlink(missing_ok=True)
        _info("Removed stale PID file.")
        return 0

    _info(f"Stopping bot PID {pid}...")
    if _is_windows():
        subprocess.run(
            ["taskkill", "/PID", str(pid), "/T"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    else:
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass

    deadline = time.monotonic() + 10.0
    while time.monotonic() < deadline and _pid_alive(pid):
        time.sleep(0.2)
    if _pid_alive(pid):
        if _is_windows():
            subprocess.run(
                ["taskkill", "/PID", str(pid), "/T", "/F"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
        else:
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
    PID_FILE.unlink(missing_ok=True)
    _info("Bot stopped.")
    return 0


def run_mappings(arguments: list[str]) -> int:
    if _ensure_environment() != 0:
        return 1
    return _run(
        [str(venv_python()), "-m", "mappings", *arguments], check=False
    ).returncode


def doctor() -> int:
    _info(
        f"Platform: {platform.system()} {platform.release()} ({platform.machine() or 'unknown-arch'})"
    )
    _info(
        f"Interpreter: {platform.python_implementation()} {platform.python_version()}"
    )
    if not _python_supported():
        return _fail(
            "Current Python version is outside the supported 3.11-3.14 range.", 2
        )

    python = venv_python() if _venv_ready() else Path(sys.executable)
    _info(f"Runtime Python: {python}")

    import_check = subprocess.run(
        [
            str(python),
            "-c",
            "import aiogram,aiohttp,httpx,PIL,pydantic,sqlite3; print('runtime-imports-ok')",
        ],
        cwd=ROOT_DIR,
        text=True,
        capture_output=True,
        check=False,
    )
    if import_check.returncode != 0:
        if import_check.stderr:
            print(import_check.stderr.strip(), file=sys.stderr)
        return _fail("Runtime dependency import check failed.")
    _info("Runtime dependency imports: OK")
    _info(
        f"Docker Compose: {'available' if docker_compose_available() else 'not available (optional)'}"
    )
    env_state = (
        "present"
        if (ROOT_DIR / ".env").is_file() or (ROOT_DIR / ".env.d").is_dir()
        else "not initialized"
    )
    _info(f"Runtime configuration: {env_state}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Cross-platform project launcher for anime-db-bot."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    setup_parser = sub.add_parser(
        "setup", help="Create .venv and install dependencies."
    )
    setup_parser.add_argument(
        "--dev", action="store_true", help="Install quality tools too."
    )

    check_parser = sub.add_parser("check", help="Compile and run the unit test suite.")
    check_parser.add_argument("--coverage", action="store_true")

    run_parser = sub.add_parser("run", help="Run the bot in the foreground.")
    run_parser.add_argument("--no-jikan", action="store_true")

    start_parser = sub.add_parser("start", help="Start the bot in the background.")
    start_parser.add_argument("--no-jikan", action="store_true")

    sub.add_parser("stop", help="Stop a launcher-managed background bot.")
    restart_parser = sub.add_parser("restart", help="Restart a launcher-managed bot.")
    restart_parser.add_argument("--no-jikan", action="store_true")
    sub.add_parser("status", help="Show launcher-managed process status.")

    mappings_parser = sub.add_parser("mappings", help="Run the mappings CLI.")
    mappings_parser.add_argument("args", nargs=argparse.REMAINDER)

    sub.add_parser("doctor", help="Check platform/runtime compatibility.")
    return parser


def main(argv: list[str] | None = None) -> int:
    raw_args = list(sys.argv[1:] if argv is None else argv)
    if raw_args and raw_args[0] == "mappings":
        return run_mappings(raw_args[1:])

    args = build_parser().parse_args(raw_args)
    if args.command == "setup":
        return setup_environment(dev=args.dev)
    if args.command == "check":
        return check_project(coverage=args.coverage)
    if args.command == "run":
        return run_bot(no_jikan=args.no_jikan)
    if args.command == "start":
        return start_bot(no_jikan=args.no_jikan)
    if args.command == "stop":
        return stop_bot()
    if args.command == "restart":
        stop_bot()
        return start_bot(no_jikan=args.no_jikan)
    if args.command == "status":
        return status_bot()
    if args.command == "mappings":
        return run_mappings(args.args)
    if args.command == "doctor":
        return doctor()
    return _fail(f"Unknown command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
