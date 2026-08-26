"""
Manages a private, embedded PostgreSQL instance for a desktop app.

Responsibilities:
  - Locate bundled postgres binaries (works both in dev and PyInstaller-frozen builds)
  - Generate a one-time random port + credentials on first launch
  - initdb a private data directory under the OS app-data folder
  - Start / stop postgres as a subprocess, and wait until it accepts connections
  - Never rely on default ports/passwords — everything is generated per-install
"""

import json
import os
import secrets
import socket
import subprocess
import sys
import time
from pathlib import Path

APP_NAME = "BinBin"  # <-- rename to your product name


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

def get_app_data_dir() -> Path:
    """OS-appropriate per-user data directory."""
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData/Roaming"))
    elif sys.platform == "darwin":
        base = Path.home() / "Library/Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share"))
    d = base / APP_NAME
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_pgdata_dir() -> Path:
    return get_app_data_dir() / "pgdata"


def get_config_path() -> Path:
    return get_app_data_dir() / "db_config.json"


def get_bundled_pg_bin_dir() -> Path:
    """
    Where the postgres binaries live relative to the running app.
    In a PyInstaller onefile/onedir build, bundled data sits next to the executable
    (or under sys._MEIPASS for onefile). In dev, it's a local ./pgbin folder.
    """
    if getattr(sys, "frozen", False):
        base = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    else:
        base = Path(__file__).parent

    # plat = {"win32": "windows", "darwin": "macos"}.get(sys.platform, "linux")
    #TODO: check if we need to use subdirs for different platforms, or if universal binaries are enough
    bin_dir = base / "postgres" / "bin" # using universal binaries for all platforms, so no subdir needed
    if not bin_dir.exists():
        raise FileNotFoundError(
            f"Bundled postgres binaries not found at {bin_dir}. "
            "Did you run the binary-fetch step before packaging?"
        )
    return bin_dir


def _exe(name: str) -> str:
    bin_dir = get_bundled_pg_bin_dir()
    suffix = ".exe" if sys.platform == "win32" else ""
    return str(bin_dir / f"{name}{suffix}")


# ---------------------------------------------------------------------------
# Config / first-run setup
# ---------------------------------------------------------------------------

def _free_port() -> int:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def get_config() -> dict:
    """Return existing config, or run first-time setup and create it."""
    config_path = get_config_path()
    if config_path.exists():
        return json.loads(config_path.read_text())
    return _first_run_setup()


def _first_run_setup() -> dict:
    pgdata = get_pgdata_dir()
    password = secrets.token_urlsafe(24)
    port = _free_port()
    user = "appuser"
    dbname = "inventory"

    pwfile = get_app_data_dir() / "_initpw.tmp"
    pwfile.write_text(password)
    try:
        subprocess.run(
            [
                _exe("initdb"),
                "-D", str(pgdata),
                "-U", user,
                "--pwfile", str(pwfile),
                "-A", "scram-sha-256",
                "--encoding=UTF8",
                #"-L", str(get_bundled_pg_bin_dir() / "share"),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as e:
        print("initdb failed:")
        print("stdout:", e.stdout)
        print("stderr:", e.stderr)
        raise
    finally:
        pwfile.unlink(missing_ok=True)

    # Lock down access to localhost-only, password auth
    (pgdata / "pg_hba.conf").write_text(
        "local all all scram-sha-256\n"
        "host all all 127.0.0.1/32 scram-sha-256\n"
        "host all all ::1/128 scram-sha-256\n"
    )

    config = {"host": "127.0.0.1", "port": port, "user": user,
              "password": password, "dbname": dbname}
    get_config_path().write_text(json.dumps(config, indent=2))

    # Create the actual database (initdb only creates 'postgres')
    #TODO: remove?
    _create_database(config)
    return config


def _create_database(config: dict):
    import psycopg2
    conn = psycopg2.connect(
        host=config["host"], port=config["port"],
        user=config["user"], password=config["password"], dbname="postgres",
    )
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (config["dbname"],))
    if not cur.fetchone():
        cur.execute(f'CREATE DATABASE "{config["dbname"]}"')
    conn.close()


# ---------------------------------------------------------------------------
# Process control
# ---------------------------------------------------------------------------

def start_postgres(config: dict):
    """Start postgres via pg_ctl (detached, logs to pgdata/server.log)."""
    pgdata = get_pgdata_dir()
    log_path = pgdata / "server.log"
    subprocess.run(
        [
            _exe("pg_ctl"), "start",
            "-D", str(pgdata),
            "-l", str(log_path),
            "-o", f'-p {config["port"]} -h {config["host"]}',
            "-w", "-t", "30",
        ],
        check=True,
    )


def stop_postgres():
    """Stop postgres cleanly. Call this on app exit."""
    pgdata = get_pgdata_dir()
    if not pgdata.exists():
        return
    subprocess.run(
        [_exe("pg_ctl"), "stop", "-D", str(pgdata), "-m", "fast", "-w", "-t", "15"],
        check=False,
    )


def wait_for_postgres_ready(config: dict, timeout: float = 15.0):
    """Poll until a real connection succeeds (pg_ctl -w usually covers this, but be defensive)."""
    import psycopg2
    deadline = time.time() + timeout
    last_err = None
    while time.time() < deadline:
        try:
            conn = psycopg2.connect(
                host=config["host"], port=config["port"],
                user=config["user"], password=config["password"],
                dbname="postgres", connect_timeout=2,
            )
            conn.close()
            return
        except Exception as e:  # noqa: BLE001
            last_err = e
            time.sleep(0.3)
    raise TimeoutError(f"Postgres did not become ready in time: {last_err}")


def is_already_running(config: dict) -> bool:
    """Detect if postgres is already up (e.g. app relaunched without clean shutdown)."""
    import psycopg2
    try:
        conn = psycopg2.connect(
            host=config["host"], port=config["port"],
            user=config["user"], password=config["password"],
            dbname="postgres", connect_timeout=1,
        )
        conn.close()
        return True
    except Exception:  # noqa: BLE001
        return False


def ensure_running() -> dict:
    """One-call entry point: get config, start if needed, wait until ready."""
    config = get_config()
    if not is_already_running(config):
        start_postgres(config)
        wait_for_postgres_ready(config)
        _create_database(config)
    return config