# CloudOps

A console chatbot that talks to Anthropic's Claude API and extends it with tools exposed through the **Model Context Protocol (MCP)** — implemented manually over JSON-RPC 2.0, without any MCP SDK, as required by the project spec.

Built for **CC3067 Redes** (Universidad del Valle de Guatemala) — Project 1: *Uso de un protocolo existente*.

## Status

✅ **Part 1 complete** — all 5 required functionalities implemented and demoed end-to-end:

- Connection to Claude's API (manual HTTP client, no SDK).
- Session context: the console chat loop keeps and resends full conversation history.
- MCP interaction logging layer (`InteractionLogger` + `with_logging` wrapper) and an in-chat `/log` (or `/log <server>`) command to display it, with per-tool/per-outcome detail — populated automatically as soon as any MCP server is connected.
- The official **Filesystem** and **Git** MCP servers, connected on startup (sandboxed to `workspace/`). See [`docs/demo-filesystem-git.md`](./docs/demo-filesystem-git.md) for the end-to-end demo (create README → git add → git commit, driven entirely through chat).
- The custom **CloudOps** MCP server (simulated cloud infra ops), connected the same way, through the same client. See [`docs/cloudops-server-spec.md`](./docs/cloudops-server-spec.md) for the full tool specification and [`docs/demo-cloudops.md`](./docs/demo-cloudops.md) for an end-to-end demo — including Claude recovering on its own from two tool-level errors mid-conversation.

Part 2 (remote deployment, Wireshark analysis) isn't covered by this repo yet.

See [`PlanProyecto.md`](./PlanProyecto.md) for the full development plan (in Spanish) and [`Proyecto1mcp.md`](./Proyecto1mcp.md) for the original assignment spec.

## Planned features (Part 1)

1. Connection to an LLM through Anthropic's API.
2. Session context (multi-turn conversation memory).
3. Logging of all MCP request/response interactions.
4. Integration with the official **Filesystem** (via `npx`) and **Git** (via the `mcp-server-git` pip package) MCP servers, local for now.
5. A custom local MCP server — **CloudOps**: a simulated cloud infrastructure ops tool (list servers, check status, read logs, restart services, scale instances).

A remote deployment of the CloudOps server and a Wireshark-based protocol analysis are planned for Part 2 of the project (not covered by this repo yet).

## Architecture

```
Chatbot (host)
   -> Generic MCP client (JSON-RPC framing, initialize / tools/list / tools/call, logging wrapper)
        -> Filesystem MCP server (official, local, via npx)
        -> Git MCP server (official, local, via npx)
        -> CloudOps MCP server (custom, local for now)
```

The MCP client is built once and is server-agnostic — the same client code talks to the official servers and to the custom CloudOps server.

## Project structure

```
chatbot/            # Host: chat loop, conversation history, Anthropic API client
mcp_client/          # Generic MCP client: JSON-RPC transport/protocol logic + logging wrapper
servers/             # MCP server(s) we built ourselves
  mcp_stdio_server.py  #   Generic server-side JSON-RPC-over-stdio loop
  cloudops/            #   CloudOps server: tools, SQLite-backed data model, seed script
docs/                # Specs and demo walkthroughs (see docs/*.md)
data/                # SQLite database (generated, gitignored)
logs/                # MCP interaction logs (generated, gitignored)
workspace/           # Sandbox root for the Filesystem/Git MCP servers (generated, gitignored)
```

## Setup

Requires Python 3.10+ and Node.js (for the official Filesystem MCP server, run via `npx`). The Git MCP server (`mcp-server-git`) installs from `requirements.txt` — no extra setup needed.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# then edit .env and set your ANTHROPIC_API_KEY
# optionally set ANTHROPIC_MODEL to override the default (claude-haiku-4-5-20251001,
# chosen to conserve the $5 free-tier API budget during development)
```

## Usage

```bash
python -m chatbot.main
```

Starts a console chat session with Claude. The full conversation history is kept and resent on every turn, so follow-up questions ("when was he born?" after "who was Alan Turing?") work as expected.

In-chat commands:

- `exit`, `quit`, or `:q` — end the session.
- `/log` — show the most recent logged MCP interactions across all connected servers (Filesystem, Git, CloudOps). `/log <server>` (e.g. `/log cloudops`) filters to just one.

## Implementation constraints

Per the assignment spec, the MCP protocol (JSON-RPC 2.0 framing, `initialize`/`initialized`, `tools/list`, `tools/call`) is implemented **manually, on both ends** — a generic client (`mcp_client/`) and our own server's stdio loop (`servers/mcp_stdio_server.py`) — without using any MCP SDK (e.g. the `mcp` Python package, `FastMCP`). Only generic libraries are used: `httpx`, `sqlite3`, `subprocess`. `asyncio` was considered for the transport but deliberately not used — see the design note in `mcp_client/stdio_transport.py`.
