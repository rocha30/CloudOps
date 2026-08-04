"""Console chat loop for the CloudOps chatbot.

Covers functionality 1 (connection to an LLM at the API level), functionality
2 (session context: history is kept and resent on every turn via
ChatSession), and the "mostrar" half of functionality 3 (an in-chat command
to display logged MCP interactions). MCP servers themselves — and therefore
anything to actually log — are wired in starting with commit #5+; the `/log`
command works today and will start showing real entries once they land.

Usage:
    python -m chatbot.main
"""

from dotenv import load_dotenv

from chatbot.anthropic_client import AnthropicAPIError, AnthropicClient
from chatbot.session import ChatSession
from mcp_client.interaction_logger import InteractionLogger

EXIT_COMMANDS = {"exit", "quit", ":q"}
LOG_COMMAND = "/log"


def main() -> None:
    load_dotenv()

    try:
        client = AnthropicClient()
    except ValueError as exc:
        print(f"Error: {exc}")
        return

    session = ChatSession(client)
    interaction_logger = InteractionLogger()
    print("CloudOps chatbot — type 'exit' to quit, '/log' to show MCP interaction log.\n")

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
            if user_text.lower() == LOG_COMMAND:
                interaction_logger.print_recent()
                continue

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
