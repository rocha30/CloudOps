"""CloudOps MCP server: scaffold, `initialize`, `tools/list` (commit #12).

Simulated cloud infrastructure ops server — see `PlanProyecto.md` §2 for the
use case and §2.2 for the tool specs this file implements the schemas for.
Tool *behavior* (`tools/call`) is added incrementally in commits #13-#15:
`list_servers`/`get_server_status` (#13), `check_logs` (#14),
`restart_service`/`scale_instance` (#15).

Runs as a subprocess over stdio, launched by the chatbot starting commit
#16 — same pattern as the official Filesystem/Git servers, just on the
other end of the pipe. Can also be run and talked to directly for testing:

    python -m servers.cloudops.server
"""

from __future__ import annotations

from typing import Any

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


def main() -> None:
    server.run()


if __name__ == "__main__":
    main()
