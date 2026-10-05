import sqlite3
import os
from pathlib import Path

DB_PATH = Path(__file__).parent / "data" / "verification.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS artifacts (
    id TEXT PRIMARY KEY,
    sha256 TEXT NOT NULL,
    phash TEXT,
    wm_id TEXT,
    merkle_proof TEXT,
    merkle_root TEXT,
    ledger_tx TEXT,
    anchored_at INTEGER,
    filename TEXT,
    content_type TEXT,
    size_bytes INTEGER,
    registered_at INTEGER NOT NULL,
    registered_by TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS api_keys (
    key TEXT PRIMARY KEY,
    owner TEXT NOT NULL,
    created_at  INTEGER NOT NULL,
    active INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS verify_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    content_url TEXT NOT NULL,
    content_type TEXT,
    verdict TEXT NOT NULL,
    artifact_id TEXT,
    method TEXT,
    hamming INTEGER,
    verified_at INTEGER NOT NULL,
    ip TEXT
);

CREATE INDEX IF NOT EXISTS idx_artifacts_sha256   ON artifacts(sha256);
CREATE INDEX IF NOT EXISTS idx_artifacts_phash    ON artifacts(phash);
CREATE INDEX IF NOT EXISTS idx_artifacts_wm_id    ON artifacts(wm_id);
CREATE INDEX IF NOT EXISTS idx_verify_log_url     ON verify_log(content_url);
"""

DEFAULT_API_KEY = os.environ.get("DEFAULT_API_KEY", "fade-dev-key-changeme")

def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn

def init_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = get_db()
    conn.executescript(SCHEMA)

 
    existing_cols = {row[1] for row in conn.execute("PRAGMA table_info(artifacts)").fetchall()}
    if "anchored_at" not in existing_cols:
        conn.execute("ALTER TABLE artifacts ADD COLUMN anchored_at INTEGER")
        print("[DB] Migration: added anchored_at column")

    import time
    conn.execute(
        "INSERT OR IGNORE INTO api_keys (key, owner, created_at, active) VALUES (?,?,?,1)",
        (DEFAULT_API_KEY, "default", int(time.time()))
    )
    conn.commit()
    conn.close()
    print(f"[DB] Initialised at {DB_PATH}")
