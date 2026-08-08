"""Conversation state + MCP tool-use loop (commit #8 scope).

The Messages API is stateless — the full message history has to be resent
on every call for the model to have context (commit #3). On top of that,
ChatSession now also wires in MCP tools: it advertises every connected
server's tools to Claude, and when Claude asks to use one (`stop_reason ==
"tool_use"`), it dispatches the call to the right `MCPClient`, feeds the
result back, and keeps looping until Claude produces a final text answer.
"""

from __future__ import annotations

import json
from typing import Any

from chatbot.anthropic_client import AnthropicClient
from mcp_client.client import MCPClient, MCPProtocolError

DEFAULT_SYSTEM_PROMPT = (
    "You are the CloudOps chatbot, a console assistant for a cloud "
    "infrastructure operations project. You have access to MCP tools when "
    "connected servers offer them. Answer clearly and concisely."
)

# Safety cap: stop looping if the model somehow never converges on a final
# answer after this many rounds of tool use, instead of hanging forever.
MAX_TOOL_ITERATIONS = 8


def mcp_tool_to_anthropic_tool(tool: dict[str, Any]) -> dict[str, Any]:
    """Convert one MCP tool definition (`tools/list` shape) to the shape the
    Anthropic Messages API expects. Both are JSON-Schema based — only the
    field name differs (`inputSchema` -> `input_schema`)."""
    return {
        "name": tool["name"],
        "description": tool.get("description", ""),
        "input_schema": tool["inputSchema"],
    }


class ChatSession:
    """Keeps message history for one conversation, drives the API calls, and
    executes any MCP tool calls Claude asks for along the way."""

    def __init__(
        self,
        client: AnthropicClient,
        mcp_clients: dict[str, MCPClient] | None = None,
        system: str | None = DEFAULT_SYSTEM_PROMPT,
    ):
        self.client = client
        self.system = system
        self.history: list[dict] = []
        self.mcp_clients = mcp_clients or {}
        self._tool_to_server: dict[str, str] = {}
        self.tools: list[dict[str, Any]] = []
        self.refresh_tools()

    def refresh_tools(self) -> None:
        """Re-discover tools from every connected MCP server. Names are
        assumed unique across servers (true for Filesystem-only today);
        a later duplicate is skipped rather than silently shadowing the
        first server that offers it.
        """
        self.tools = []
        self._tool_to_server = {}
        for server_name, mcp_client in self.mcp_clients.items():
            for tool in mcp_client.list_tools():
                if tool["name"] in self._tool_to_server:
                    continue
                self._tool_to_server[tool["name"]] = server_name
                self.tools.append(mcp_tool_to_anthropic_tool(tool))

    def send(self, user_text: str) -> str:
        """Send a user turn, run the tool-use loop to completion, return the
        final text answer.

        On failure the user turn (and any partial assistant/tool turns
        appended this call) is rolled back out of history, so a failed call
        doesn't leave history desynced for the next request.
        """
        checkpoint = len(self.history)
        self.history.append({"role": "user", "content": user_text})

        try:
            return self._run_until_done()
        except Exception:
            del self.history[checkpoint:]
            raise

    def _run_until_done(self) -> str:
        for _ in range(MAX_TOOL_ITERATIONS):
            response = self.client.complete(
                messages=self.history, system=self.system, tools=self.tools or None
            )
            content = response.get("content", [])
            self.history.append({"role": "assistant", "content": content})

            if response.get("stop_reason") != "tool_use":
                return self._extract_text(content)

            tool_uses = [block for block in content if block.get("type") == "tool_use"]
            tool_results = [self._execute_tool_use(block) for block in tool_uses]
            self.history.append({"role": "user", "content": tool_results})

        raise RuntimeError(
            f"exceeded {MAX_TOOL_ITERATIONS} tool-use iterations without a final answer"
        )

    def _execute_tool_use(self, block: dict[str, Any]) -> dict[str, Any]:
        tool_name = block["name"]
        server_name = self._tool_to_server.get(tool_name)

        if server_name is None:
            return {
                "type": "tool_result",
                "tool_use_id": block["id"],
                "content": f"Unknown tool: {tool_name}",
                "is_error": True,
            }

        mcp_client = self.mcp_clients[server_name]
        try:
            result = mcp_client.call_tool(tool_name, block.get("input") or {})
        except MCPProtocolError as exc:
            return {
                "type": "tool_result",
                "tool_use_id": block["id"],
                "content": str(exc),
                "is_error": True,
            }

        text_parts = [
            c.get("text", "") for c in result.get("content", []) if c.get("type") == "text"
        ]
        content = "\n".join(text_parts) if text_parts else json.dumps(result.get("content", []))

        return {
            "type": "tool_result",
            "tool_use_id": block["id"],
            "content": content,
            "is_error": result.get("isError", False),
        }

    @staticmethod
    def _extract_text(content: list[dict[str, Any]]) -> str:
        for block in content:
            if block.get("type") == "text":
                return block["text"]
        return ""

    def reset(self) -> None:
        """Clear the conversation history, starting a fresh session."""
        self.history.clear()
