"""JSON-RPC 2.0 transport over HTTP(S) — Parte 2, remote CloudOps server.

Counterpart to `StdioTransport` (Parte 1): same `send`/`send_request`/`close`
interface, so `MCPClient` talks to a remote server exactly as it talks to a
local subprocess (see `mcp_client/client.py`). One POST per JSON-RPC
message: a request gets its response body back synchronously, a
notification's response body is discarded. This is a deliberate
simplification of the MCP "Streamable HTTP" transport — no SSE stream,
since this server never needs to push messages to the client outside of a
direct request/response.
"""

from __future__ import annotations

import os
import ssl
from typing import Any

import httpx

from mcp_client.errors import TransportError


class HttpTransportError(TransportError):
    """Raised on connection failures or a non-2xx HTTP response."""


def _build_ssl_context() -> ssl.SSLContext | None:
    """When SSLKEYLOGFILE is set, log the TLS session keys there so a tool
    like Wireshark can decrypt a capture of this traffic (see the Parte 2
    Wireshark analysis docs). Returns None — httpx's default verification —
    when the variable isn't set, which is the normal case outside of a
    capture session.
    """
    keylog_file = os.environ.get("SSLKEYLOGFILE")
    if not keylog_file:
        return None
    context = ssl.create_default_context()
    context.keylog_filename = keylog_file
    return context


class HttpTransport:
    """Talks JSON-RPC to a remote MCP server over HTTP POST."""

    def __init__(self, url: str, token: str | None = None, timeout: float = 30.0):
        self.url = url
        headers = {"Content-Type": "application/json"}
        if token:
            headers["X-CloudOps-Token"] = token
        self._client = httpx.Client(
            headers=headers, timeout=timeout, verify=_build_ssl_context() or True
        )

    def send(self, message: dict[str, Any]) -> None:
        """Send a JSON-RPC notification — no response expected."""
        try:
            self._client.post(self.url, json=message)
        except httpx.HTTPError as exc:
            raise HttpTransportError(f"failed to reach {self.url}: {exc}") from exc

    def send_request(self, message: dict[str, Any]) -> dict[str, Any]:
        """Send a request and return its parsed JSON-RPC response.

        Signature matches `StdioTransport.send_request`, so it can be passed
        straight into `mcp_client.interaction_logger.with_logging` the same
        way.
        """
        try:
            response = self._client.post(self.url, json=message)
        except httpx.HTTPError as exc:
            raise HttpTransportError(f"failed to reach {self.url}: {exc}") from exc

        if response.status_code >= 400:
            raise HttpTransportError(
                f"{self.url} responded {response.status_code}: {response.text}"
            )
        try:
            return response.json()
        except ValueError as exc:
            raise HttpTransportError(f"malformed JSON-RPC response: {response.text!r}") from exc

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "HttpTransport":
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()
