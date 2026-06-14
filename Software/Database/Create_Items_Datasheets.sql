CREATE TABLE items_datasheets (
    id          SERIAL PRIMARY KEY,
    item_id     INTEGER REFERENCES items(id) ON DELETE CASCADE,
    filename    VARCHAR(255),
    data        BYTEA NOT NULL,
    created_at  TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_items_datasheets_item_id ON items_datasheets(item_id);