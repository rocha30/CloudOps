"""JSON-RPC 2.0 transport over stdio (commit #5 scope).

Implements only the framing and send/receive mechanics for talking to an MCP
server subprocess — no protocol semantics yet (no `initialize` handshake, no
`tools/list`; those land in the following commits). Per the MCP
specification, stdio messages are **newline-delimited JSON**: one message
per line, and a message must not contain an embedded newline. This is
simpler than (and different from) LSP's `Content-Length`-prefixed framing.

Design choice: synchronous, blocking I/O via `subprocess.Popen` — not
`asyncio`. The chatbot itself is a blocking console REPL that talks to one
server at a time, so there is no concurrent I/O to justify an event loop;
sync keeps the manual framing code straightforward to read and debug.
"""

from __future__ import annotations

import json
import subprocess
import threading
from typing import Any


class StdioTransportError(RuntimeError):
    """Raised on subprocess failures, malformed frames, or a closed pipe."""


class StdioTransport:
    """Launches an MCP server as a subprocess and exchanges JSON-RPC
    messages with it over its stdin/stdout, one newline-delimited JSON
    message per line.
    """

    def __init__(self, command: list[str]):
        try:
            self._process = subprocess.Popen(
                command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,  # line-buffered
            )
        except OSError as exc:
            raise StdioTransportError(f"failed to launch server {command!r}: {exc}") from exc

        # Guards send+receive pairs: this project talks to one server one
        # request at a time, so a lock is enough to prevent an interleaved
        # write/read if send_request is ever called from more than one place.
        self._lock = threading.Lock()

    def send(self, message: dict[str, Any]) -> None:
        """Write one JSON-RPC message as a single line to the server's stdin."""
        if self._process.poll() is not None:
            raise StdioTransportError(
                f"server process exited (code {self._process.returncode})"
            )
        # json.dumps always escapes control characters within string values
        # (a raw "\n" becomes the two-character "\\n"), so the serialized
        # line can never itself contain an embedded newline — the MCP
        # stdio framing invariant holds by construction, not by a runtime check.
        line = json.dumps(message, ensure_ascii=False)

        assert self._process.stdin is not None
        try:
            self._process.stdin.write(line + "\n")
            self._process.stdin.flush()
        except (BrokenPipeError, OSError) as exc:
            raise StdioTransportError(f"failed to write to server stdin: {exc}") from exc

    def receive(self) -> dict[str, Any]:
        """Read and parse one JSON-RPC message (one line) from the server's stdout."""
        assert self._process.stdout is not None
        line = self._process.stdout.readline()
        if line == "":
            detail = self._drain_stderr()
            raise StdioTransportError(
                "server closed stdout unexpectedly"
                + (f" — stderr: {detail}" if detail else "")
            )
        try:
            return json.loads(line)
        except json.JSONDecodeError as exc:
            raise StdioTransportError(f"malformed JSON-RPC frame: {line!r}") from exc

    def send_request(self, message: dict[str, Any]) -> dict[str, Any]:
        """Send a request and block for its matching response.

        Signature matches the `send(message) -> response` shape expected by
        `mcp_client.interaction_logger.with_logging`, so a transport's
        `send_request` can be passed straight into that wrapper.
        """
        with self._lock:
            self.send(message)
            return self.receive()

    def _drain_stderr(self) -> str:
        if self._process.stderr is None:
            return ""
        try:
            return self._process.stderr.read()
        except Exception:
            return ""

    def close(self) -> None:
        if self._process.poll() is None:
            self._process.terminate()
            try:
                self._process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._process.kill()
                self._process.wait()

    def __enter__(self) -> "StdioTransport":
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()
