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

🚧 **Part 2 in progress** — the CloudOps server now also runs remotely (Render), reached over HTTP instead of stdio, with no change to the chatbot's tool-use logic. See [`docs/cloudops-server-spec.md`](./docs/cloudops-server-spec.md) §3.1 for the remote transport details. The Wireshark capture/analysis deliverable is tracked in `docs/wireshark-analysis.md`.

## Planned features (Part 1)

1. Connection to an LLM through Anthropic's API.
2. Session context (multi-turn conversation memory).
3. Logging of all MCP request/response interactions.
4. Integration with the official **Filesystem** (via `npx`) and **Git** (via the `mcp-server-git` pip package) MCP servers, local for now.
5. A custom local MCP server — **CloudOps**: a simulated cloud infrastructure ops tool (list servers, check status, read logs, restart services, scale instances).

6. A remote deployment of the CloudOps server (Render), reached over HTTP by the same chatbot.
7. Wireshark-based analysis of the client↔remote-server communication.

## Architecture

```
Chatbot (host)
   -> Generic MCP client (JSON-RPC framing, initialize / tools/list / tools/call, logging wrapper)
        -> Filesystem MCP server (official, local, via npx)
        -> Git MCP server (official, local, via npx)
        -> CloudOps MCP server (custom, local stdio OR remote HTTP on Render — same tools either way)
```

The MCP client is built once and is server-agnostic — the same client code talks to the official servers and to the custom CloudOps server, whether it's a local subprocess or the remote Render deployment.

## Project structure

```
chatbot/            # Host: chat loop, conversation history, Anthropic API client
mcp_client/          # Generic MCP client: JSON-RPC transport/protocol logic + logging wrapper
  stdio_transport.py   #   Local transport (subprocess over stdio)
  http_transport.py    #   Remote transport (HTTP POST, for the Render-hosted CloudOps server)
servers/             # MCP server(s) we built ourselves
  mcp_stdio_server.py  #   Generic message dispatch + stdio server loop
  cloudops/            #   CloudOps server: tools, SQLite-backed data model, seed script
    server.py            #     Tools + handlers (transport-agnostic)
    http_server.py        #     HTTP entrypoint for the remote (Render) deployment
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

To use the **remote** CloudOps server (Render) instead of the local subprocess, also set in `.env`:

```
CLOUDOPS_REMOTE_URL=https://<your-service>.onrender.com/mcp
CLOUDOPS_TOKEN=<the same shared secret configured on Render>
```

Leave both unset to keep using the local stdio server (default).

## Usage

```bash
python -m chatbot.main
```

Starts a console chat session with Claude. The full conversation history is kept and resent on every turn, so follow-up questions ("when was he born?" after "who was Alan Turing?") work as expected.

In-chat commands:

- `exit`, `quit`, or `:q` — end the session.
- `/log` — show the most recent logged MCP interactions across all connected servers (Filesystem, Git, CloudOps). `/log <server>` (e.g. `/log cloudops`) filters to just one.

## Remote deployment (Part 2)

The CloudOps server can run as a web service on [Render](https://render.com) instead of a local subprocess — see [`docs/cloudops-server-spec.md`](./docs/cloudops-server-spec.md) §3.1 for the full transport/auth details.

**Deploying:**
1. Connect your GitHub account to Render and grant it access to this repo.
2. New → Web Service → build command `pip install -r requirements.txt`, start command `python -m servers.cloudops.http_server`.
3. Set the `CLOUDOPS_TOKEN` env var on Render to a secret of your choice.
4. Point the chatbot at it via `CLOUDOPS_REMOTE_URL`/`CLOUDOPS_TOKEN` in `.env` (see Setup above).

Render's free tier spins the service down after 15 minutes idle (~1 minute to wake back up) — send it one request ahead of a live demo.

## Implementation constraints

Per the assignment spec, the MCP protocol (JSON-RPC 2.0 framing, `initialize`/`initialized`, `tools/list`, `tools/call`) is implemented **manually, on both ends** — a generic client (`mcp_client/`, with both a local and a remote transport) and our own server's message dispatch (`servers/mcp_stdio_server.py`, reused by both the stdio and the HTTP entrypoint) — without using any MCP SDK (e.g. the `mcp` Python package, `FastMCP`). Only generic libraries are used: `httpx`, `sqlite3`, `subprocess`, `http.server`. `asyncio` was considered for the transport but deliberately not used — see the design note in `mcp_client/stdio_transport.py`.
