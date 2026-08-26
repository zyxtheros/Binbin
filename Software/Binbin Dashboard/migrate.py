"""
Minimal migration runner.

- schema.sql / seed.sql always run (idempotent) -> gets a fresh install to the
  latest baseline in one shot.
- migrations/NNN_description.sql are numbered, one-shot changes applied AFTER
  the baseline, tracked via schema_version, for users upgrading from an
  older installed version.

Usage: call run_all(conn) once at startup, after ensure_running().
"""

import re
from pathlib import Path

MIGRATIONS_DIR = Path(__file__).parent / "migrations"


def run_all(conn):
    cur = conn.cursor()
    cur.execute(Path(__file__).parent.joinpath("database/schema.sql").read_text())
    cur.execute(Path(__file__).parent.joinpath("database/seed.sql").read_text())
    conn.commit()

    if not MIGRATIONS_DIR.exists():
        return

    cur.execute("SELECT version FROM schema_version LIMIT 1")
    current = cur.fetchone()[0]

    files = sorted(MIGRATIONS_DIR.glob("*.sql"), key=lambda p: int(re.match(r"\d+", p.name).group()))
    for f in files:
        version = int(re.match(r"\d+", f.name).group())
        if version <= current:
            continue
        cur.execute(f.read_text())
        cur.execute("UPDATE schema_version SET version = %s", (version,))
        conn.commit()
        print(f"Applied migration {f.name} -> version {version}")