"""Generic JSON-RPC message dispatch + stdio server loop (server side).

The counterpart to `mcp_client.stdio_transport.StdioTransport`, from the
other direction: reads one newline-delimited JSON-RPC message per line from
stdin, dispatches it to a registered handler, writes the JSON-RPC response
(if any) to stdout. Same framing invariant as the client side — one message
per line, no embedded newlines (guaranteed by `json.dumps`, which always
escapes control characters within string values). No MCP SDK: this is a
plain read/dispatch/write loop over `sys.stdin`/`sys.stdout`.

A concrete server (e.g. CloudOps, in `servers/cloudops/server.py`)
instantiates `MCPServer` and registers its own request handlers for
`initialize`, `tools/list`, `tools/call`, etc. via `@server.handler(method)`.

`handle_message` (dispatch, no I/O) is split out from `run` (the stdio
read/write loop) so Parte 2's `servers/cloudops/http_server.py` can reuse
the exact same dispatch logic over HTTP instead of stdio.
"""

from __future__ import annotations

import json
import sys
from typing import Any, Callable

RequestHandler = Callable[[dict[str, Any]], dict[str, Any]]

# JSON-RPC 2.0 standard error codes used here.
PARSE_ERROR = -32700
METHOD_NOT_FOUND = -32601
INTERNAL_ERROR = -32000


class MCPServer:
    """Registers method handlers and runs the blocking stdin read loop."""

    def __init__(self, name: str, version: str):
        self.name = name
        self.version = version
        self._handlers: dict[str, RequestHandler] = {}

    def handler(self, method: str) -> Callable[[RequestHandler], RequestHandler]:
        """Decorator: register `fn(params) -> result` as the handler for `method`."""

        def register(fn: RequestHandler) -> RequestHandler:
            self._handlers[method] = fn
            return fn

        return register

    def _write(self, message: dict[str, Any]) -> None:
        sys.stdout.write(json.dumps(message, ensure_ascii=False) + "\n")
        sys.stdout.flush()

    def handle_message(self, message: dict[str, Any]) -> dict[str, Any] | None:
        """Dispatch one already-parsed JSON-RPC message and return the
        response to send back, or `None` for a notification (no response).
        Pure — no I/O — so both the stdio loop (`run`, below) and the HTTP
        server (`servers/cloudops/http_server.py`) can share it.
        """
        method = message.get("method")
        msg_id = message.get("id")  # absent/None => notification, no response

        # 'notifications/initialized' (and its unprefixed alias, some clients
        # send either) has no handler and needs no response — just accept it.
        if method in ("notifications/initialized", "initialized"):
            return None

        handler = self._handlers.get(method)
        if handler is None:
            if msg_id is not None:
                return {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "error": {"code": METHOD_NOT_FOUND, "message": f"Method not found: {method}"},
                }
            return None

        try:
            result = handler(message.get("params") or {})
        except Exception as exc:
            if msg_id is not None:
                return {"jsonrpc": "2.0", "id": msg_id, "error": {"code": INTERNAL_ERROR, "message": str(exc)}}
            return None

        if msg_id is not None:  # a notification handler must not get a reply
            return {"jsonrpc": "2.0", "id": msg_id, "result": result}
        return None

    def run(self) -> None:
        """Blocking read loop: one line = one JSON-RPC message, until EOF."""
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                # Per JSON-RPC 2.0, a parse error has no reliable id to
                # reply to — reply with id: null, as the spec prescribes.
                self._write(
                    {"jsonrpc": "2.0", "id": None, "error": {"code": PARSE_ERROR, "message": "Parse error"}}
                )
                continue
            response = self.handle_message(message)
            if response is not None:
                self._write(response)
