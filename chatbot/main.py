"""Console chat loop for the CloudOps chatbot.

Covers functionality 1 (connection to an LLM at the API level), functionality
2 (session context via ChatSession), functionality 3 (MCP interactions are
logged — the `/log` command shows them), and functionality 4: the official
**Filesystem** (commit #8) and **Git** (commit #9) MCP servers are connected
on startup and their tools are made available to Claude through the
ChatSession tool-use loop. The custom CloudOps server lands in commit #12+.

Note on the Git server: the current official `mcp-server-git` has no
`git_init` tool — every one of its tools requires an existing repo
(`repo_path`). So "creating the repository" can't be a step the LLM performs
through a tool call; `git init` runs once here as setup, before the server
is even connected, not as part of the chat demo.

Usage:
    python -m chatbot.main
"""

import subprocess
from pathlib import Path

from dotenv import load_dotenv

from chatbot.anthropic_client import AnthropicAPIError, AnthropicClient
from chatbot.session import ChatSession
from mcp_client.client import MCPClient, MCPProtocolError
from mcp_client.interaction_logger import InteractionLogger
from mcp_client.stdio_transport import StdioTransportError

EXIT_COMMANDS = {"exit", "quit", ":q"}
LOG_COMMAND = "/log"

# Sandbox root for the Filesystem and Git MCP servers — every file the LLM
# reads/writes/commits during a demo lands here, never in the project's own
# tree. See .gitignore: workspace/* is ignored.
WORKSPACE_DIR = Path(__file__).resolve().parent.parent / "workspace"


def connect_filesystem_server(logger: InteractionLogger) -> MCPClient | None:
    """Launch and handshake with the official Filesystem MCP server via npx,
    sandboxed to WORKSPACE_DIR. Best-effort: MCP servers are optional extras
    on top of a working chatbot — if npx/node/network aren't available, the
    session still works for plain conversation, just without those tools.
    """
    WORKSPACE_DIR.mkdir(exist_ok=True)
    try:
        mcp_client = MCPClient(
            ["npx", "-y", "@modelcontextprotocol/server-filesystem", str(WORKSPACE_DIR)],
            server_name="filesystem",
            logger=logger,
        )
        mcp_client.initialize()
        return mcp_client
    except (StdioTransportError, MCPProtocolError) as exc:
        print(f"Warning: could not connect to the Filesystem MCP server: {exc}")
        return None


def connect_git_server(logger: InteractionLogger) -> MCPClient | None:
    """Ensure WORKSPACE_DIR is a git repo (one-time setup — see module
    docstring), then launch and handshake with the official Git MCP server.
    Best-effort, same reasoning as connect_filesystem_server.
    """
    WORKSPACE_DIR.mkdir(exist_ok=True)
    if not (WORKSPACE_DIR / ".git").exists():
        try:
            subprocess.run(
                ["git", "init"], cwd=WORKSPACE_DIR, check=True, capture_output=True, text=True
            )
        except (subprocess.CalledProcessError, OSError) as exc:
            print(f"Warning: could not initialize the workspace git repo: {exc}")
            return None

    try:
        mcp_client = MCPClient(
            ["mcp-server-git", "--repository", str(WORKSPACE_DIR)],
            server_name="git",
            logger=logger,
        )
        mcp_client.initialize()
        return mcp_client
    except (StdioTransportError, MCPProtocolError) as exc:
        print(f"Warning: could not connect to the Git MCP server: {exc}")
        return None


def main() -> None:
    load_dotenv()

    try:
        client = AnthropicClient()
    except ValueError as exc:
        print(f"Error: {exc}")
        return

    interaction_logger = InteractionLogger()

    mcp_clients: dict[str, MCPClient] = {}
    filesystem_client = connect_filesystem_server(interaction_logger)
    if filesystem_client is not None:
        mcp_clients["filesystem"] = filesystem_client
        print(f"Connected: Filesystem MCP server (sandbox: {WORKSPACE_DIR})")

    git_client = connect_git_server(interaction_logger)
    if git_client is not None:
        mcp_clients["git"] = git_client
        print(f"Connected: Git MCP server (repo: {WORKSPACE_DIR})")

    session = ChatSession(client, mcp_clients=mcp_clients)
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
        for mcp_client in mcp_clients.values():
            mcp_client.close()
        client.close()
        print("\nGoodbye.")


if __name__ == "__main__":
    main()
