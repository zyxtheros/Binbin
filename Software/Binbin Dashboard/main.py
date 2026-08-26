"""
Desktop entry point.

Flow:
  1. Ensure embedded Postgres is running (starts it on first call, generating
     config on very first launch).
  2. Run schema.sql / seed.sql / migrations.
  3. Start Flask in a background thread.
  4. Open a native window pointed at it (pywebview) instead of a browser tab.
  5. On window close, stop Postgres cleanly.
"""

import atexit
import threading

import psycopg2
import psycopg2.extras
import webview          #pywebview

import pg_manager
import migrate
from app import app as flask_app  # your existing Flask app object

_DB_CONFIG = None


def get_db():
    """Drop-in replacement for the old get_db() in app.py — reads generated config."""
    return psycopg2.connect(
        host=_DB_CONFIG["host"],
        port=_DB_CONFIG["port"],
        dbname=_DB_CONFIG["dbname"],
        user=_DB_CONFIG["user"],
        password=_DB_CONFIG["password"],
        cursor_factory=psycopg2.extras.RealDictCursor,
    )


def run_flask():
    flask_app.run(host="127.0.0.1", port=5002, debug=False, use_reloader=False)


def main():
    global _DB_CONFIG

    print("Starting database...")
    _DB_CONFIG = pg_manager.ensure_running()
    atexit.register(pg_manager.stop_postgres)

    print("Applying schema/migrations...")
    conn = psycopg2.connect(
        host=_DB_CONFIG["host"], port=_DB_CONFIG["port"],
        dbname=_DB_CONFIG["dbname"], user=_DB_CONFIG["user"],
        password=_DB_CONFIG["password"],
    )
    migrate.run_all(conn)
    conn.close()

    # Make config importable from app.py without circular-import pain
    import app as app_module
    app_module.get_db = get_db

    threading.Thread(target=run_flask, daemon=True).start()

    webview.create_window("Inventory", "http://127.0.0.1:5002", width=1200, height=800)
    webview.start()

    # webview.start() blocks until window closes; atexit handles pg shutdown


if __name__ == "__main__":
    main()