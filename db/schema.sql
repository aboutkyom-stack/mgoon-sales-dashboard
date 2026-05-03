-- 엠군 파이프라인 로컬 저장소 (SQLite)
-- 동료 Supabase DB와는 독립. read-only로 읽어온 제품으로 실행한 01~02 결과 보관.

CREATE TABLE IF NOT EXISTS mgoon_runs (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    source_db         TEXT NOT NULL DEFAULT 'supabase_v2',
    source_product_id INTEGER,
    product_name      TEXT NOT NULL,
    product_snapshot  TEXT NOT NULL,
    created_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS mgoon_targets (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id            INTEGER NOT NULL REFERENCES mgoon_runs(id) ON DELETE CASCADE,
    rank              INTEGER,
    character         TEXT,
    deficit           TEXT,
    deficit_source    TEXT,
    purchase_benefit  TEXT,
    involvement       INTEGER,
    channel           TEXT,
    note              TEXT,
    desire_layer3     TEXT,
    raw_output        TEXT,
    model             TEXT NOT NULL,
    selected          INTEGER DEFAULT 0,
    created_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS mgoon_positioning (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    target_id           INTEGER NOT NULL REFERENCES mgoon_targets(id) ON DELETE CASCADE,
    cv_analysis         TEXT,
    positioning_map     TEXT,
    two_down_two_up     TEXT,
    opening_copy        TEXT,
    value_additions     TEXT,
    product_essence     TEXT,
    raw_output          TEXT,
    model               TEXT NOT NULL,
    created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_targets_run ON mgoon_targets(run_id);
CREATE INDEX IF NOT EXISTS idx_positioning_target ON mgoon_positioning(target_id);
