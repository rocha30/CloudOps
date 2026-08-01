"""Conversation state for the console chat loop (commit #3 scope).

The Messages API is stateless — the full message history has to be resent
on every call for the model to have context. ChatSession owns that history
for one session and keeps it in sync with each request/response pair.
"""

from __future__ import annotations

from chatbot.anthropic_client import AnthropicClient

DEFAULT_SYSTEM_PROMPT = (
    "You are the CloudOps chatbot, a console assistant for a cloud "
    "infrastructure operations project. Answer clearly and concisely."
)


class ChatSession:
    """Keeps message history for one conversation and drives the API calls."""

    def __init__(
        self,
        client: AnthropicClient,
        system: str | None = DEFAULT_SYSTEM_PROMPT,
    ):
        self.client = client
        self.system = system
        self.history: list[dict] = []

    def send(self, user_text: str) -> str:
        """Send a user turn with full history attached, return the answer text.

        On API failure the user turn is rolled back out of history, so a
        failed call doesn't leave a dangling unanswered turn that would
        desync the conversation on the next request.
        """
        self.history.append({"role": "user", "content": user_text})

        try:
            response = self.client.complete(messages=self.history, system=self.system)
        except Exception:
            self.history.pop()
            raise

        answer = ""
        for block in response.get("content", []):
            if block.get("type") == "text":
                answer = block["text"]
                break

        self.history.append({"role": "assistant", "content": answer})
        return answer

    def reset(self) -> None:
        """Clear the conversation history, starting a fresh session."""
        self.history.clear()
