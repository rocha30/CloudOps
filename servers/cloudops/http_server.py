"""HTTP entrypoint for the CloudOps MCP server — Parte 2 (remote deployment).

Same `server` (tools, handlers, SQLite-backed logic) as
`servers/cloudops/server.py`, just reached over HTTP POST instead of stdio:
`MCPServer.handle_message` already returns a plain response dict with no I/O
of its own, so this module only has to get a JSON-RPC message in from an
HTTP request and the response dict back out.

One POST endpoint (`/mcp`) — a request gets its JSON-RPC response back as
the HTTP body, a notification gets an empty 202. A GET on `/` answers 200
for basic health checks (Render, or a browser sanity check).

`http.server.HTTPServer` (single-threaded, not `ThreadingHTTPServer`) is
enough: `servers/cloudops/server.py` keeps one shared SQLite connection that
isn't thread-safe, and this server only ever serves one chatbot client at a
time — same "no concurrency to justify the complexity" reasoning as
`mcp_client/stdio_transport.py`'s choice of sync I/O over asyncio.

Auth is a single shared secret: if `CLOUDOPS_TOKEN` is set, every POST to
`/mcp` must carry a matching `X-CloudOps-Token` header. Deliberately minimal
— this is simulated infrastructure data behind a class demo, not a
production secret.

Run locally:
    PORT=8000 python -m servers.cloudops.http_server

On Render: set the start command to `python -m servers.cloudops.http_server`
— `PORT` is injected automatically.
"""

from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, HTTPServer

from servers.cloudops.seed import seed as seed_cloudops_db
from servers.cloudops.server import server

CLOUDOPS_TOKEN = os.environ.get("CLOUDOPS_TOKEN")


class MCPHTTPHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802 (BaseHTTPRequestHandler's naming convention)
        body = b"CloudOps MCP server is running.\n"
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:  # noqa: N802
        # Always drain the request body before responding, even on an early
        # rejection below — otherwise the client's still-unread bytes can
        # trigger a TCP reset instead of a clean HTTP response.
        length = int(self.headers.get("Content-Length", 0))
        raw_body = self.rfile.read(length)

        if self.path != "/mcp":
            self.send_response(404)
            self.end_headers()
            return

        if CLOUDOPS_TOKEN and self.headers.get("X-CloudOps-Token") != CLOUDOPS_TOKEN:
            self.send_response(401)
            self.end_headers()
            return

        try:
            message = json.loads(raw_body)
        except json.JSONDecodeError:
            self._write_json(400, {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}})
            return

        response = server.handle_message(message)
        if response is None:
            self.send_response(202)
            self.end_headers()
            return
        self._write_json(200, response)

    def _write_json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args) -> None:  # noqa: A002
        # Render captures stdout/stderr as logs on its own — the default
        # BaseHTTPRequestHandler behavior (write to stderr) is fine, this
        # override just keeps the format on one line per request.
        print(f"{self.address_string()} - {format % args}")


def main() -> None:
    seed_cloudops_db()  # Render's filesystem is ephemeral per deploy — always re-seed on boot.
    port = int(os.environ.get("PORT", 10000))
    httpd = HTTPServer(("0.0.0.0", port), MCPHTTPHandler)
    print(f"CloudOps MCP HTTP server listening on 0.0.0.0:{port}")
    httpd.serve_forever()


if __name__ == "__main__":
    main()
