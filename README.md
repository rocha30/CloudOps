# CloudOps

A console chatbot that talks to Anthropic's Claude API and extends it with tools exposed through the **Model Context Protocol (MCP)** — implemented manually over JSON-RPC 2.0, without any MCP SDK, as required by the project spec.

Built for **CC3067 Redes** (Universidad del Valle de Guatemala) — Project 1: *Uso de un protocolo existente*.

## Status

🚧 Work in progress — this is the initial project scaffold (repo structure, dependencies, environment setup). No functionality has been implemented yet.

See [`PlanProyecto.md`](./PlanProyecto.md) for the full development plan (in Spanish) and [`Proyecto1mcp.md`](./Proyecto1mcp.md) for the original assignment spec.

## Planned features (Part 1)

1. Connection to an LLM through Anthropic's API.
2. Session context (multi-turn conversation memory).
3. Logging of all MCP request/response interactions.
4. Integration with the official **Filesystem** and **Git** MCP servers (local, via `npx`).
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
chatbot/          # Host: chat loop, conversation history, Anthropic API client
mcp_client/        # Generic MCP client: JSON-RPC transport/protocol logic + logging wrapper
servers/cloudops/  # Custom MCP server (CloudOps): tools, SQLite-backed data model, seed script
data/               # SQLite database (generated, gitignored)
logs/               # MCP interaction logs (generated, gitignored)
```

## Setup

Requires Python 3.10+ and Node.js (for the official Filesystem/Git MCP servers, run via `npx`).

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

Not yet implemented — instructions will be added here once the chat loop (commit #3 in the plan) is functional.

## Implementation constraints

Per the assignment spec, the MCP protocol (JSON-RPC 2.0 framing, `initialize`/`initialized`, `tools/list`, `tools/call`) is implemented **manually**, without using any MCP SDK (e.g. the `mcp` Python package, `FastMCP`). Only generic libraries are used: `httpx`, `sqlite3`, `subprocess`, `asyncio`.
