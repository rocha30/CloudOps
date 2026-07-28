"""Manual smoke test for the Anthropic API connection (commit #2 scope).

Sends a single, stateless question to Claude and prints the answer. This is
not the final chat loop (session context is added in a later commit) — it
only proves that functionality 1 ("connection to an LLM at the API level")
works end to end.

Usage:
    python -m chatbot.main
"""

from dotenv import load_dotenv

from chatbot.anthropic_client import AnthropicAPIError, AnthropicClient


def main() -> None:
    load_dotenv()

    question = input("Ask Claude something: ").strip()
    if not question:
        print("No question entered, exiting.")
        return

    try:
        with AnthropicClient() as client:
            answer = client.ask(question)
    except (ValueError, AnthropicAPIError) as exc:
        print(f"Error: {exc}")
        return

    print(f"\nClaude: {answer}")


if __name__ == "__main__":
    main()
