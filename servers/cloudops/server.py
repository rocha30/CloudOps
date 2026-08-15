"""CloudOps MCP server: all 5 planned tools implemented (#12-#15).

Simulated cloud infrastructure ops server — see `PlanProyecto.md` §2 for the
use case and §2.2 for the tool specs. Read tools: `list_servers`,
`get_server_status` (#13), `check_logs` (#14). Write tools (mutate state,
with validation): `restart_service`, `scale_instance` (#15).

Runs as a subprocess over stdio, launched by the chatbot starting commit
#16 — same pattern as the official Filesystem/Git servers, just on the
other end of the pipe. Can also be run and talked to directly for testing:

    python -m servers.cloudops.server

Reads from the SQLite database seeded by `servers/cloudops/seed.py` — run
that script first, or these tools will just see an empty database (no
crash, just empty/"not found" results).
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any, Callable

from servers.cloudops.db import get_connection, init_db
from servers.mcp_stdio_server import MCPServer

MCP_PROTOCOL_VERSION = "2025-06-18"
SERVER_NAME = "cloudops"
SERVER_VERSION = "0.1.0"

# Full inputSchema for every planned tool, per PlanProyecto.md §2.2 — defined
# up front so tools/list is complete and accurate even before tools/call
# implements the behavior behind each one.
TOOLS: list[dict[str, Any]] = [
    {
        "name": "list_servers",
        "description": "List all servers, with id, name, region, and status. Optionally filter by region.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "region": {"type": "string", "description": "Only return servers in this region."},
            },
        },
    },
    {
        "name": "get_server_status",
        "description": "Get CPU, memory, uptime, and status for one server.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "server_id": {"type": "string", "description": "The server's id, e.g. 'srv-1'."},
            },
            "required": ["server_id"],
        },
    },
    {
        "name": "check_logs",
        "description": "Get the most recent log lines for a server, optionally filtered by level.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "server_id": {"type": "string", "description": "The server's id, e.g. 'srv-1'."},
                "level": {
                    "type": "string",
                    "enum": ["error", "warn", "info"],
                    "description": "Only return log lines at this level.",
                },
                "limit": {
                    "type": "integer",
                    "default": 20,
                    "description": "Maximum number of log lines to return (most recent first).",
                },
            },
            "required": ["server_id"],
        },
    },
    {
        "name": "restart_service",
        "description": "Restart a service within a server, updating its last_restart timestamp.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "server_id": {"type": "string"},
                "service_name": {"type": "string", "description": "The service's name, e.g. 'nginx'."},
            },
            "required": ["server_id", "service_name"],
        },
    },
    {
        "name": "scale_instance",
        "description": (
            "Increase or decrease a server's instance_count by delta. "
            "Rejected if it would go below 0 or above the configured maximum."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "server_id": {"type": "string"},
                "delta": {
                    "type": "integer",
                    "description": "Positive to scale up, negative to scale down.",
                },
            },
            "required": ["server_id", "delta"],
        },
    },
]

server = MCPServer(SERVER_NAME, SERVER_VERSION)

# Single connection, reused for the server's whole lifetime — the stdin
# read loop is synchronous and single-threaded, so there's no concurrent
# access to guard against. Opened lazily on first tool call, not at import
# time, so simply importing this module (e.g. from a test) never touches
# the filesystem.
_conn: sqlite3.Connection | None = None


def _get_conn() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        _conn = get_connection()
        init_db(_conn)  # CREATE TABLE IF NOT EXISTS — safe if already seeded
    return _conn


def _text_result(data: Any) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": json.dumps(data, indent=2)}], "isError": False}


def _error_result(message: str) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": message}], "isError": True}


def _row_to_server_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "name": row["name"],
        "region": row["region"],
        "status": row["status"],
        "cpu_pct": row["cpu_pct"],
        "mem_pct": row["mem_pct"],
        "uptime_s": row["uptime_s"],
        "instance_count": row["instance_count"],
    }


@server.handler("initialize")
def handle_initialize(params: dict[str, Any]) -> dict[str, Any]:
    return {
        "protocolVersion": MCP_PROTOCOL_VERSION,
        "capabilities": {"tools": {"listChanged": False}},
        "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
    }


@server.handler("tools/list")
def handle_tools_list(params: dict[str, Any]) -> dict[str, Any]:
    return {"tools": TOOLS}


def tool_list_servers(arguments: dict[str, Any]) -> dict[str, Any]:
    conn = _get_conn()
    region = arguments.get("region")
    if region:
        rows = conn.execute("SELECT * FROM servers WHERE region = ? ORDER BY id", (region,)).fetchall()
    else:
        rows = conn.execute("SELECT * FROM servers ORDER BY id").fetchall()
    return _text_result([_row_to_server_dict(r) for r in rows])


def tool_get_server_status(arguments: dict[str, Any]) -> dict[str, Any]:
    server_id = arguments.get("server_id")
    if not server_id:
        return _error_result("Missing required argument: server_id")

    row = _get_conn().execute("SELECT * FROM servers WHERE id = ?", (server_id,)).fetchone()
    if row is None:
        return _error_result(f"No such server: {server_id}")

    return _text_result(_row_to_server_dict(row))


VALID_LOG_LEVELS = ("error", "warn", "info")


def tool_check_logs(arguments: dict[str, Any]) -> dict[str, Any]:
    server_id = arguments.get("server_id")
    if not server_id:
        return _error_result("Missing required argument: server_id")

    conn = _get_conn()
    if conn.execute("SELECT 1 FROM servers WHERE id = ?", (server_id,)).fetchone() is None:
        return _error_result(f"No such server: {server_id}")

    level = arguments.get("level")
    if level is not None and level not in VALID_LOG_LEVELS:
        return _error_result(f"Invalid level: {level!r} (must be one of {', '.join(VALID_LOG_LEVELS)})")

    limit = arguments.get("limit", 20)
    if not isinstance(limit, int) or isinstance(limit, bool) or limit <= 0:
        return _error_result("'limit' must be a positive integer")

    query = "SELECT timestamp, level, message FROM log_entries WHERE server_id = ?"
    query_args: list[Any] = [server_id]
    if level:
        query += " AND level = ?"
        query_args.append(level)
    query += " ORDER BY timestamp DESC LIMIT ?"
    query_args.append(limit)

    rows = conn.execute(query, query_args).fetchall()
    logs = [{"timestamp": r["timestamp"], "level": r["level"], "message": r["message"]} for r in rows]
    return _text_result(logs)


def tool_restart_service(arguments: dict[str, Any]) -> dict[str, Any]:
    server_id = arguments.get("server_id")
    service_name = arguments.get("service_name")
    if not server_id:
        return _error_result("Missing required argument: server_id")
    if not service_name:
        return _error_result("Missing required argument: service_name")

    conn = _get_conn()
    if conn.execute("SELECT 1 FROM servers WHERE id = ?", (server_id,)).fetchone() is None:
        return _error_result(f"No such server: {server_id}")

    service_row = conn.execute(
        "SELECT id FROM services WHERE server_id = ? AND name = ?", (server_id, service_name)
    ).fetchone()
    if service_row is None:
        return _error_result(f"No such service '{service_name}' on server {server_id}")

    last_restart = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "UPDATE services SET status = 'running', last_restart = ? WHERE id = ?",
        (last_restart, service_row["id"]),
    )
    conn.commit()

    return _text_result(
        {
            "server_id": server_id,
            "service_name": service_name,
            "status": "running",
            "last_restart": last_restart,
        }
    )


# Instance count ceiling for scale_instance — the "maximum configurado" the
# plan calls for. Simulated infra, so a plain module constant is enough;
# not exposed as a tool parameter since it's an operational limit, not a
# per-call choice.
MAX_INSTANCE_COUNT = 10


def tool_scale_instance(arguments: dict[str, Any]) -> dict[str, Any]:
    server_id = arguments.get("server_id")
    if not server_id:
        return _error_result("Missing required argument: server_id")

    delta = arguments.get("delta")
    if not isinstance(delta, int) or isinstance(delta, bool):
        return _error_result("'delta' must be an integer")

    conn = _get_conn()
    row = conn.execute("SELECT instance_count FROM servers WHERE id = ?", (server_id,)).fetchone()
    if row is None:
        return _error_result(f"No such server: {server_id}")

    current = row["instance_count"]
    new_count = current + delta
    if new_count < 0:
        return _error_result(
            f"Cannot scale server {server_id}: instance_count would go below 0 "
            f"(current {current}, delta {delta:+d})"
        )
    if new_count > MAX_INSTANCE_COUNT:
        return _error_result(
            f"Cannot scale server {server_id}: instance_count would exceed the maximum "
            f"of {MAX_INSTANCE_COUNT} (current {current}, delta {delta:+d})"
        )

    conn.execute("UPDATE servers SET instance_count = ? WHERE id = ?", (new_count, server_id))
    conn.commit()

    return _text_result({"server_id": server_id, "instance_count": new_count})


# Tools implemented so far — all 5 planned tools, as of this commit.
TOOL_HANDLERS: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {
    "list_servers": tool_list_servers,
    "get_server_status": tool_get_server_status,
    "check_logs": tool_check_logs,
    "restart_service": tool_restart_service,
    "scale_instance": tool_scale_instance,
}

_PLANNED_TOOL_NAMES = {tool["name"] for tool in TOOLS}


@server.handler("tools/call")
def handle_tools_call(params: dict[str, Any]) -> dict[str, Any]:
    name = params.get("name")
    arguments = params.get("arguments") or {}

    handler = TOOL_HANDLERS.get(name)
    if handler is not None:
        return handler(arguments)

    if name in _PLANNED_TOOL_NAMES:
        return _error_result(f"Tool '{name}' is planned but not implemented yet.")
    return _error_result(f"Unknown tool: {name}")


def main() -> None:
    server.run()


if __name__ == "__main__":
    main()
