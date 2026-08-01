"""Console chat loop for the CloudOps chatbot.

Covers functionality 1 (connection to an LLM at the API level) and
functionality 2 (session context: history is kept and resent on every turn
via ChatSession). MCP tool integration and logging are added in later
commits.

Usage:
    python -m chatbot.main
"""

from dotenv import load_dotenv

from chatbot.anthropic_client import AnthropicAPIError, AnthropicClient
from chatbot.session import ChatSession

EXIT_COMMANDS = {"exit", "quit", ":q"}


def main() -> None:
    load_dotenv()

    try:
        client = AnthropicClient()
    except ValueError as exc:
        print(f"Error: {exc}")
        return

    session = ChatSession(client)
    print("CloudOps chatbot — type 'exit' to quit.\n")

    try:
        while True:
            try:
                user_text = input("You: ").strip()
            except EOFError:
                break

            if not user_text:
                continue
            if user_text.lower() in EXIT_COMMANDS:
                break

            try:
                answer = session.send(user_text)
            except AnthropicAPIError as exc:
                print(f"Error: {exc}")
                continue

            print(f"Claude: {answer}\n")
    except KeyboardInterrupt:
        pass
    finally:
        client.close()
        print("\nGoodbye.")


if __name__ == "__main__":
    main()
