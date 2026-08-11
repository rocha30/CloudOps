"""Seed script for the CloudOps database (commit #11 scope).

Populates servers/services/log_entries with example data so the demo is
reproducible — several servers across regions/states, a couple of services
per server, and a handful of log lines mixing levels.

Idempotent: wipes existing rows before inserting, so running this twice
lands on the same known state instead of duplicating log entries.

Usage:
    python -m servers.cloudops.seed
"""

from __future__ import annotations

from servers.cloudops.db import DB_PATH, get_connection, init_db

SERVERS = [
    {
        "id": "srv-1",
        "name": "api-gateway-01",
        "region": "us-east-1",
        "status": "running",
        "cpu_pct": 42.5,
        "mem_pct": 61.2,
        "uptime_s": 864000,
        "instance_count": 3,
    },
    {
        "id": "srv-2",
        "name": "worker-batch-02",
        "region": "us-west-2",
        "status": "degraded",
        "cpu_pct": 88.9,
        "mem_pct": 76.4,
        "uptime_s": 172800,
        "instance_count": 2,
    },
    {
        "id": "srv-3",
        "name": "db-replica-03",
        "region": "eu-central-1",
        "status": "stopped",
        "cpu_pct": 0.0,
        "mem_pct": 0.0,
        "uptime_s": 0,
        "instance_count": 0,
    },
]

SERVICES = [
    {
        "id": "svc-1",
        "server_id": "srv-1",
        "name": "nginx",
        "status": "running",
        "last_restart": "2026-08-15T09:00:00",
    },
    {
        "id": "svc-2",
        "server_id": "srv-1",
        "name": "auth-api",
        "status": "running",
        "last_restart": "2026-08-10T14:30:00",
    },
    {
        "id": "svc-3",
        "server_id": "srv-2",
        "name": "batch-worker",
        "status": "running",
        "last_restart": "2026-08-18T02:00:00",
    },
    {
        "id": "svc-4",
        "server_id": "srv-3",
        "name": "postgres-replica",
        "status": "stopped",
        "last_restart": "2026-08-01T00:00:00",
    },
]

# (server_id, timestamp, level, message)
LOG_ENTRIES = [
    ("srv-1", "2026-08-19T10:00:00", "info", "Health check passed"),
    ("srv-1", "2026-08-19T10:05:00", "info", "Request handled in 42ms"),
    ("srv-2", "2026-08-19T09:50:00", "warn", "CPU usage above 85% for 5 minutes"),
    ("srv-2", "2026-08-19T09:55:00", "error", "batch-worker restarted after OOM"),
    ("srv-2", "2026-08-19T09:56:00", "info", "batch-worker back online"),
    ("srv-3", "2026-08-18T23:59:00", "error", "Connection refused: server stopped"),
]


def seed(db_path=DB_PATH) -> None:
    conn = get_connection(db_path)
    try:
        init_db(conn)

        # Wipe first (children before parents, for the FK constraints) so
        # re-running this script is idempotent instead of piling up rows.
        conn.execute("DELETE FROM log_entries")
        conn.execute("DELETE FROM services")
        conn.execute("DELETE FROM servers")

        conn.executemany(
            "INSERT INTO servers (id, name, region, status, cpu_pct, mem_pct, uptime_s, instance_count) "
            "VALUES (:id, :name, :region, :status, :cpu_pct, :mem_pct, :uptime_s, :instance_count)",
            SERVERS,
        )
        conn.executemany(
            "INSERT INTO services (id, server_id, name, status, last_restart) "
            "VALUES (:id, :server_id, :name, :status, :last_restart)",
            SERVICES,
        )
        conn.executemany(
            "INSERT INTO log_entries (server_id, timestamp, level, message) VALUES (?, ?, ?, ?)",
            LOG_ENTRIES,
        )
        conn.commit()
    finally:
        conn.close()


if __name__ == "__main__":
    seed()
    print(
        f"Seeded {DB_PATH} with {len(SERVERS)} servers, "
        f"{len(SERVICES)} services, {len(LOG_ENTRIES)} log entries."
    )
