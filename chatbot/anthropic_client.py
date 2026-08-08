"""Minimal HTTP client for the Anthropic Messages API.

Deliberately implemented on top of `httpx` instead of the official `anthropic`
SDK: this project's chatbot talks to the LLM API directly over HTTP, in the
same spirit as the manual JSON-RPC implementation required for MCP — no
provider SDK in the request path.

Scope for this commit: a basic, stateless request/response call (no
conversation history yet — that is added on top of this client in a later
commit).
"""

from __future__ import annotations

import os

import httpx

ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"
# Cheaper model by default for development/testing (keeps the $5 free-tier
# budget from burning fast); override with ANTHROPIC_MODEL in .env for a
# stronger model, without touching code.
DEFAULT_MODEL = "claude-haiku-4-5-20251001"
DEFAULT_MAX_TOKENS = 1024


class AnthropicAPIError(RuntimeError):
    """Raised when the Anthropic API returns a non-2xx response."""

    def __init__(self, status_code: int, message: str):
        self.status_code = status_code
        super().__init__(f"Anthropic API error ({status_code}): {message}")


class AnthropicClient:
    """Thin wrapper around a single Anthropic Messages API call."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        timeout: float = 30.0,
    ):
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not self.api_key:
            raise ValueError(
                "Missing Anthropic API key. Set ANTHROPIC_API_KEY in your "
                "environment (see .env.example) or pass api_key explicitly."
            )
        self.model = model or os.environ.get("ANTHROPIC_MODEL") or DEFAULT_MODEL
        self._http = httpx.Client(timeout=timeout)

    def _headers(self) -> dict:
        return {
            "x-api-key": self.api_key,
            "anthropic-version": ANTHROPIC_VERSION,
            "content-type": "application/json",
        }

    def complete(
        self,
        messages: list[dict],
        system: str | None = None,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        tools: list[dict] | None = None,
    ) -> dict:
        """Send a raw Messages API request and return the parsed JSON response."""
        body = {
            "model": self.model,
            "max_tokens": max_tokens,
            "messages": messages,
        }
        if system:
            body["system"] = system
        if tools:
            body["tools"] = tools

        try:
            response = self._http.post(
                ANTHROPIC_API_URL, headers=self._headers(), json=body
            )
        except httpx.RequestError as exc:
            raise AnthropicAPIError(0, f"network error: {exc}") from exc

        if response.status_code != 200:
            detail = response.text
            try:
                detail = response.json().get("error", {}).get("message", detail)
            except ValueError:
                pass
            raise AnthropicAPIError(response.status_code, detail)

        return response.json()

    def ask(self, user_text: str, system: str | None = None) -> str:
        """Convenience call: single user turn in, plain text answer out."""
        response = self.complete(
            messages=[{"role": "user", "content": user_text}], system=system
        )
        for block in response.get("content", []):
            if block.get("type") == "text":
                return block["text"]
        return ""

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> "AnthropicClient":
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()
