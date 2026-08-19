"""Logging layer for MCP interactions (functionality 3).

Per the project plan, logging is implemented as a **wrapper around the MCP
client**, not tied to any specific server — so every server (Filesystem,
Git, CloudOps) gets its request/response interactions logged automatically,
with no extra code at the call site.

This commit lands before the JSON-RPC transport (commit #5), so there is no
real client to wrap yet. `InteractionLogger` (persistence) and `with_logging`
(the wrapper itself) are written generically now: `with_logging` wraps any
`send(message: dict) -> dict` callable, which is exactly the shape the
transport's send function will have once it exists — wiring it in later is
a one-line change, not a redesign.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

Direction = Literal["request", "response"]

DEFAULT_LOG_DIR = Path("logs")
DEFAULT_LOG_FILENAME = "mcp_interactions.jsonl"


class InteractionLogger:
    """Persists MCP JSON-RPC request/response interactions to a JSONL file.

    Each line is one interaction: a timestamp, which server it belongs to,
    its direction (request sent / response received), the raw JSON-RPC
    message, and — for responses — how long the call took.
    """

    def __init__(
        self,
        log_dir: str | Path = DEFAULT_LOG_DIR,
        filename: str = DEFAULT_LOG_FILENAME,
    ):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.log_path = self.log_dir / filename

    def log(
        self,
        server: str,
        direction: Direction,
        message: dict[str, Any],
        elapsed_ms: float | None = None,
    ) -> None:
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "server": server,
            "direction": direction,
            "message": message,
            "elapsed_ms": elapsed_ms,
        }
        with self.log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def read_entries(
        self, limit: int | None = None, server: str | None = None
    ) -> list[dict[str, Any]]:
        """Read logged interactions in chronological order (oldest first).

        `server`, if given, filters to that server *before* applying
        `limit` — so `limit` means "last N entries for this server", not
        "last N entries overall, then see if any match".
        """
        if not self.log_path.exists():
            return []
        with self.log_path.open("r", encoding="utf-8") as f:
            entries = [json.loads(line) for line in f if line.strip()]
        if server:
            entries = [e for e in entries if e["server"] == server]
        return entries[-limit:] if limit else entries

    @staticmethod
    def format_entry(entry: dict[str, Any]) -> str:
        """Render one log entry as a single human-readable line.

        Requests are labeled with the method, and — for `tools/call` — the
        actual tool name, since "-> tools/call" alone doesn't say which
        tool. Responses show the JSON-RPC error message when present, or
        the tool-level `isError` flag for a `tools/call` result, instead of
        the uninformative generic "response" every reply used to render as.
        """
        arrow = "->" if entry["direction"] == "request" else "<-"
        message = entry["message"]
        timing = f" ({entry['elapsed_ms']:.1f} ms)" if entry.get("elapsed_ms") else ""

        if entry["direction"] == "request":
            method = message.get("method", "?")
            if method == "tools/call":
                tool_name = message.get("params", {}).get("name", "?")
                label = f"tools/call({tool_name})"
            else:
                label = method
        else:
            if "error" in message:
                label = f"error: {message['error'].get('message', '?')}"
            else:
                result = message.get("result")
                if isinstance(result, dict) and "isError" in result:
                    label = f"result (isError={result['isError']})"
                else:
                    label = "result"

        return f"[{entry['timestamp']}] {entry['server']} {arrow} {label}{timing}"

    def print_recent(self, limit: int = 20, server: str | None = None) -> None:
        """Print the last N logged interactions — the 'mostrar' half of functionality 3.

        Pass `server` (e.g. "cloudops") to see only that server's entries.
        """
        entries = self.read_entries(limit=limit, server=server)
        if not entries:
            scope = f" for server '{server}'" if server else ""
            print(f"(no MCP interactions logged yet{scope})")
            return
        for entry in entries:
            print(self.format_entry(entry))


def with_logging(
    server: str,
    logger: InteractionLogger,
    send: Callable[[dict[str, Any]], dict[str, Any]],
) -> Callable[[dict[str, Any]], dict[str, Any]]:
    """Wrap a raw JSON-RPC `send(message) -> response` call with logging.

    This is the "wrapper alrededor del cliente MCP" from the plan: given the
    low-level send function the transport exposes, returns an equivalent
    function that transparently logs the outgoing request and the resulting
    response (or the error, if the call raises) before returning/re-raising.
    """

    def wrapped(message: dict[str, Any]) -> dict[str, Any]:
        logger.log(server, "request", message)
        start = time.monotonic()
        try:
            response = send(message)
        except Exception as exc:
            elapsed_ms = (time.monotonic() - start) * 1000
            logger.log(server, "response", {"error": str(exc)}, elapsed_ms=elapsed_ms)
            raise
        elapsed_ms = (time.monotonic() - start) * 1000
        logger.log(server, "response", response, elapsed_ms=elapsed_ms)
        return response

    return wrapped
