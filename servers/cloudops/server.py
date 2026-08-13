"""CloudOps MCP server: scaffold + initialize/tools/list (#12), first two
read tools (#13).

Simulated cloud infrastructure ops server — see `PlanProyecto.md` §2 for the
use case and §2.2 for the tool specs this file implements the schemas for.
`list_servers` and `get_server_status` are implemented in this commit;
`check_logs` (#14) and `restart_service`/`scale_instance` (#15) still return
a clear "not yet implemented" tool error if called.

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


# Tools implemented so far. A tool present in TOOLS (tools/list) but absent
# here is a real planned tool that just isn't built yet (commit #14/#15) —
# distinguished below from a tool name that doesn't exist at all.
TOOL_HANDLERS: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {
    "list_servers": tool_list_servers,
    "get_server_status": tool_get_server_status,
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
