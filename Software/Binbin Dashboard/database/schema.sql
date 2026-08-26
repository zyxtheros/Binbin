-- Idempotent schema. Safe to run on every startup.

CREATE TABLE IF NOT EXISTS schema_version (
    version INT NOT NULL
);

CREATE TABLE IF NOT EXISTS spec_field_definitions (
    field_key    TEXT PRIMARY KEY,
    display_name TEXT NOT NULL,
    field_type   TEXT NOT NULL DEFAULT 'text',  -- 'text' | 'number' | 'boolean'
    unit         TEXT,
    unit_system  TEXT DEFAULT NULL,  -- 'metric' | 'imperial' | NULL
    sort_order   INT NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS items (
    id          SERIAL PRIMARY KEY,
    sku         TEXT NOT NULL UNIQUE,
    name        TEXT NOT NULL,
    description TEXT,
    specs       JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_items_specs ON items USING GIN (specs);

CREATE TABLE IF NOT EXISTS items_images (
    id         SERIAL PRIMARY KEY,
    item_id    INT NOT NULL REFERENCES items(id) ON DELETE CASCADE,
    filename   TEXT NOT NULL,
    mime_type  TEXT,
    data       BYTEA NOT NULL,
    is_primary BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS items_datasheets (
    id        SERIAL PRIMARY KEY,
    item_id   INT NOT NULL REFERENCES items(id) ON DELETE CASCADE,
    filename  TEXT NOT NULL,
    data      BYTEA NOT NULL
);

-- Seed schema_version only if the table is empty (first run)
INSERT INTO schema_version (version)
SELECT 1
WHERE NOT EXISTS (SELECT 1 FROM schema_version);