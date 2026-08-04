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

    def read_entries(self, limit: int | None = None) -> list[dict[str, Any]]:
        """Read logged interactions in chronological order (oldest first)."""
        if not self.log_path.exists():
            return []
        with self.log_path.open("r", encoding="utf-8") as f:
            entries = [json.loads(line) for line in f if line.strip()]
        return entries[-limit:] if limit else entries

    @staticmethod
    def format_entry(entry: dict[str, Any]) -> str:
        """Render one log entry as a single human-readable line."""
        arrow = "->" if entry["direction"] == "request" else "<-"
        message = entry["message"]
        label = message.get("method") or message.get("error", {}).get("message") or "response"
        timing = f" ({entry['elapsed_ms']:.1f} ms)" if entry.get("elapsed_ms") else ""
        return f"[{entry['timestamp']}] {entry['server']} {arrow} {label}{timing}"

    def print_recent(self, limit: int = 20) -> None:
        """Print the last N logged interactions — the 'mostrar' half of functionality 3."""
        entries = self.read_entries(limit=limit)
        if not entries:
            print("(no MCP interactions logged yet)")
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
