"""Shared transport error hierarchy.

`MCPClient` and `chatbot/main.py` catch transport failures without caring
whether the underlying transport is stdio (local subprocess) or HTTP
(remote server) — this base class is what makes that possible.
"""

from __future__ import annotations


class TransportError(RuntimeError):
    """Raised on transport-level failures: a closed pipe, a malformed frame,
    a connection failure, or a non-2xx HTTP response — anything below the
    JSON-RPC protocol layer (see `mcp_client.client.MCPProtocolError` for
    protocol-level failures)."""
