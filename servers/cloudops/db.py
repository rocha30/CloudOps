"""SQLite data model for the CloudOps MCP server (commit #11 scope).

Schema per `PlanProyecto.md` § 2.1: `Server` / `Service` / `LogEntry`.
This module only defines the schema and connection handling — the MCP
server itself (`tools/list`, `tools/call`) is built in commit #12+.

Only the standard library `sqlite3` is used, per the project's "no MCP SDK"
constraint (irrelevant here anyway — this is plain data access, not
protocol code).
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "cloudops.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS servers (
    id             TEXT PRIMARY KEY,
    name           TEXT NOT NULL,
    region         TEXT NOT NULL,
    status         TEXT NOT NULL CHECK (status IN ('running', 'stopped', 'degraded')),
    cpu_pct        REAL NOT NULL,
    mem_pct        REAL NOT NULL,
    uptime_s       INTEGER NOT NULL,
    instance_count INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS services (
    id           TEXT PRIMARY KEY,
    server_id    TEXT NOT NULL REFERENCES servers(id),
    name         TEXT NOT NULL,
    status       TEXT NOT NULL CHECK (status IN ('running', 'stopped')),
    last_restart TIMESTAMP
);

CREATE TABLE IF NOT EXISTS log_entries (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    server_id TEXT NOT NULL REFERENCES servers(id),
    timestamp TIMESTAMP NOT NULL,
    level     TEXT NOT NULL CHECK (level IN ('error', 'warn', 'info')),
    message   TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_services_server_id ON services(server_id);
CREATE INDEX IF NOT EXISTS idx_log_entries_server_id ON log_entries(server_id);
"""


def get_connection(db_path: Path | str = DB_PATH) -> sqlite3.Connection:
    """Open a connection with foreign keys enforced and dict-like row access.

    Creates the parent directory (`data/`) if it doesn't exist yet, but does
    NOT create the schema — call `init_db()` for that.
    """
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    """Create the servers/services/log_entries tables if they don't exist yet."""
    conn.executescript(SCHEMA)
    conn.commit()
