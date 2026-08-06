"""MCP protocol layer: handshake (commit #6) + tool discovery (commit #7).

Sits on top of `StdioTransport` (commit #5, pure framing) and implements MCP
protocol semantics: the client/server capability handshake every MCP session
must perform before any other request, and `tools/list` for discovering what
a server offers. `tools/call` (actually invoking a tool) lands in commit #8.

Per the MCP specification, the handshake is:
  1. Client sends an `initialize` **request** (has an `id`, expects a response)
     with its supported `protocolVersion`, `capabilities`, and `clientInfo`.
  2. Server responds with its own `protocolVersion`, `capabilities`, and
     `serverInfo`.
  3. Client sends an `initialized` **notification** (no `id`, no response
     expected) confirming the handshake is complete — only after this may
     the client send any other request, including `tools/list`.
"""

from __future__ import annotations

from itertools import count
from typing import Any

from mcp_client.stdio_transport import StdioTransport, StdioTransportError

MCP_PROTOCOL_VERSION = "2025-06-18"
CLIENT_NAME = "cloudops-chatbot"
CLIENT_VERSION = "0.1.0"


class MCPProtocolError(RuntimeError):
    """Raised when a server response violates the JSON-RPC/MCP contract
    (missing fields, mismatched id, or a JSON-RPC `error` object)."""


class MCPClient:
    """One MCP session over stdio with a single server: handshake, request id
    bookkeeping, and tool discovery. Tool invocation (`tools/call`) is added
    in commit #8.
    """

    def __init__(self, command: list[str], server_name: str):
        self.server_name = server_name
        self.transport = StdioTransport(command)
        self._id_counter = count(1)
        self.server_info: dict[str, Any] | None = None
        self.server_capabilities: dict[str, Any] | None = None
        self._initialized = False

    def _next_id(self) -> int:
        return next(self._id_counter)

    def _request(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Send a JSON-RPC request and return its `result`, raising on `error`
        or on a response whose `id` doesn't match the request just sent."""
        request_id = self._next_id()
        message = {"jsonrpc": "2.0", "id": request_id, "method": method}
        if params is not None:
            message["params"] = params

        response = self.transport.send_request(message)

        if response.get("id") != request_id:
            raise MCPProtocolError(
                f"response id {response.get('id')!r} does not match request id {request_id!r}"
            )
        if "error" in response:
            error = response["error"]
            raise MCPProtocolError(
                f"{method} failed: [{error.get('code')}] {error.get('message')}"
            )
        if "result" not in response:
            raise MCPProtocolError(f"{method} response has neither 'result' nor 'error'")

        return response["result"]

    def _notify(self, method: str, params: dict[str, Any] | None = None) -> None:
        """Send a JSON-RPC notification (no id, no response expected)."""
        message = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            message["params"] = params
        self.transport.send(message)

    def initialize(self) -> dict[str, Any]:
        """Perform the initialize handshake. Returns the server's `initialize` result."""
        result = self._request(
            "initialize",
            {
                "protocolVersion": MCP_PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": CLIENT_NAME, "version": CLIENT_VERSION},
            },
        )
        self.server_info = result.get("serverInfo")
        self.server_capabilities = result.get("capabilities")

        # Step 3: confirm the handshake with the 'initialized' notification —
        # only after this is the server expected to accept other requests.
        self._notify("notifications/initialized")
        self._initialized = True

        return result

    @property
    def is_initialized(self) -> bool:
        return self._initialized

    def list_tools(self) -> list[dict[str, Any]]:
        """Discover the tools a server offers via `tools/list`.

        Returns each tool's raw definition (`name`, `description`,
        `inputSchema`). `tools/list` is paginated per the MCP spec — a
        response may include a `nextCursor`, in which case the client must
        keep requesting with that cursor until the server omits it.
        """
        if not self._initialized:
            raise MCPProtocolError("cannot list tools before the initialize handshake completes")

        tools: list[dict[str, Any]] = []
        cursor: str | None = None
        while True:
            params = {"cursor": cursor} if cursor else None
            result = self._request("tools/list", params)
            tools.extend(result.get("tools", []))
            cursor = result.get("nextCursor")
            if not cursor:
                break

        return tools

    def close(self) -> None:
        self.transport.close()

    def __enter__(self) -> "MCPClient":
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()
