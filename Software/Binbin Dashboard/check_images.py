"""
Quick diagnostic: list rows in items_images, optionally filtered by item_id.

Run from the same folder as app.py (or wherever your .env lives):
    python3 check_images.py
    python3 check_images.py 5      # only rows for item_id = 5
"""
import os
import sys
import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

load_dotenv()

print(f"[DB DEBUG] connecting host={os.getenv('DB_HOST', 'localhost')} "
      f"port={os.getenv('DB_PORT', 5432)} db={os.getenv('DB_NAME', 'Inventory')} "
      f"user={os.getenv('DB_USER', 'postgres')}")

conn = psycopg2.connect(
    host=os.getenv("DB_HOST", "localhost"),
    port=os.getenv("DB_PORT", 5432),
    dbname=os.getenv("DB_NAME", "Inventory"),
    user=os.getenv("DB_USER", "postgres"),
    password=os.getenv("DB_PASSWORD", "super"),
    cursor_factory=psycopg2.extras.RealDictCursor
)
cur = conn.cursor()

item_id = sys.argv[1] if len(sys.argv) > 1 else None

if item_id:
    cur.execute(
        "SELECT id, item_id, filename, mime_type, is_primary, length(data) AS bytes "
        "FROM items_images WHERE item_id = %s ORDER BY id",
        (item_id,)
    )
else:
    cur.execute(
        "SELECT id, item_id, filename, mime_type, is_primary, length(data) AS bytes "
        "FROM items_images ORDER BY item_id, id"
    )

rows = cur.fetchall()
conn.close()

if not rows:
    print("No rows found in items_images" + (f" for item_id={item_id}" if item_id else "") + ".")
else:
    for r in rows:
        print(dict(r))

print(f"\nTotal rows: {len(rows)}")