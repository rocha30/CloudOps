# CloudOps MCP Server — Specification

Custom local MCP server (assignment functionality 5) — see `PlanProyecto.md`
§2 for the design rationale. This document is the required deliverable per
the assignment spec: "Se debe proporcionar la especificación del servidor,
cómo utilizarlo y ejemplos de uso" (§3.1, point 5).

## 1. Use case

Simulated cloud infrastructure operations: monitoring and managing a small
fleet of servers and the services running on them — the kind of thing an
on-call engineer would ask a chat assistant while triaging an incident
("what's the status of X", "show me recent errors on Y", "restart Z").

Chosen because it combines, within a small scope that needs no real cloud
provider integration:

- **simple reads** (`list_servers`)
- **filtered reads** (`get_server_status`, `check_logs`)
- **state-mutating actions with validation** (`restart_service`,
  `scale_instance`)

— covering the different tool shapes MCP is meant to expose, without
over-engineering the domain itself.

## 2. Data model

SQLite, `data/cloudops.db` (gitignored, generated). Schema in
`servers/cloudops/db.py`; sample data in `servers/cloudops/seed.py`.

```
servers (
  id             TEXT PRIMARY KEY,
  name           TEXT NOT NULL,
  region         TEXT NOT NULL,
  status         TEXT NOT NULL CHECK (status IN ('running','stopped','degraded')),
  cpu_pct        REAL NOT NULL,
  mem_pct        REAL NOT NULL,
  uptime_s       INTEGER NOT NULL,
  instance_count INTEGER NOT NULL
)

services (
  id           TEXT PRIMARY KEY,
  server_id    TEXT NOT NULL REFERENCES servers(id),
  name         TEXT NOT NULL,
  status       TEXT NOT NULL CHECK (status IN ('running','stopped')),
  last_restart TIMESTAMP
)

log_entries (
  id        INTEGER PRIMARY KEY AUTOINCREMENT,
  server_id TEXT NOT NULL REFERENCES servers(id),
  timestamp TIMESTAMP NOT NULL,
  level     TEXT NOT NULL CHECK (level IN ('error','warn','info')),
  message   TEXT NOT NULL
)
```

Foreign keys are enforced (`PRAGMA foreign_keys = ON`), and `status`/`level`
are constrained at the database level, not just validated in application
code.

## 3. Transport & protocol

Manual JSON-RPC 2.0, no MCP SDK, over two interchangeable transports — same
handlers, same tools, same `tools/call` behavior either way:

- **stdio (local)** — `servers/mcp_stdio_server.py`: read one
  newline-delimited JSON message per line from stdin, dispatch to a
  registered handler, write the response to stdout.
- **HTTP (remote, Parte 2)** — `servers/cloudops/http_server.py`: one POST
  per JSON-RPC message to `/mcp`; the response comes back as the HTTP body
  instead of a stdout line. Both transports call the exact same
  `MCPServer.handle_message` (dispatch, no I/O) defined once in
  `servers/mcp_stdio_server.py` — `servers/cloudops/server.py`'s handlers
  don't know or care which transport is in front of them.

```
initialize()             — protocolVersion, capabilities, serverInfo
notifications/initialized — client confirms the handshake (no response)
tools/list                — returns the 5 tools below, with full inputSchema
tools/call                — invokes one tool by name + arguments
```

### 3.1 Remote deployment (Render)

The same server, deployed as a web service on [Render](https://render.com):

- **Endpoint:** `POST https://<service>.onrender.com/mcp` — one JSON-RPC
  message per request, JSON-RPC response as the body (or an empty `202` for
  a notification). `GET /` answers `200` for health checks.
- **Auth:** a shared secret header, `X-CloudOps-Token`, checked against the
  `CLOUDOPS_TOKEN` env var set on Render — deliberately minimal, this is
  simulated data behind a class demo, not a production secret.
- **Client side:** `mcp_client/http_transport.py`'s `HttpTransport` (same
  `send`/`send_request`/`close` interface as `StdioTransport`, built on
  `httpx`). The chatbot picks it automatically when `CLOUDOPS_REMOTE_URL`
  is set in `.env` — see `chatbot/main.py`'s `connect_cloudops_server`. No
  other code changes between local and remote.
- **State:** Render's filesystem is ephemeral per deploy, so
  `servers/cloudops/http_server.py` re-seeds `data/cloudops.db` on every
  boot (same idempotent `seed()` used locally).
- **Wireshark analysis:** see `docs/wireshark-analysis.md` for the capture
  of this exact HTTPS traffic, decrypted via `SSLKEYLOGFILE`.

## 4. Tools

Every tool's `tools/call` result follows the standard MCP shape:
`{"content": [{"type": "text", "text": "<JSON or message>"}], "isError": bool}`.
On success, `text` is a JSON-encoded value (an object or array); on error,
`text` is a plain human-readable message and `isError` is `true`. A tool
error is a *normal* response, not a JSON-RPC-level failure — the protocol
call itself succeeded, the requested operation just couldn't be completed
(bad id, invalid argument, business-rule violation).

### 4.1 `list_servers`

List all servers, optionally filtered by region.

**inputSchema**
```json
{
  "type": "object",
  "properties": {
    "region": { "type": "string", "description": "Only return servers in this region." }
  }
}
```

**Example — no filter**
```
list_servers({})
→ [
    {"id": "srv-1", "name": "api-gateway-01",  "region": "us-east-1",    "status": "running",  "cpu_pct": 42.5, "mem_pct": 61.2, "uptime_s": 864000, "instance_count": 3},
    {"id": "srv-2", "name": "worker-batch-02", "region": "us-west-2",    "status": "degraded", "cpu_pct": 88.9, "mem_pct": 76.4, "uptime_s": 172800, "instance_count": 2},
    {"id": "srv-3", "name": "db-replica-03",   "region": "eu-central-1", "status": "stopped",  "cpu_pct": 0.0,  "mem_pct": 0.0,  "uptime_s": 0,      "instance_count": 0}
  ]
```

**Example — filtered by region**
```
list_servers({"region": "us-west-2"})
→ [{"id": "srv-2", "name": "worker-batch-02", "region": "us-west-2", "status": "degraded", ...}]
```

### 4.2 `get_server_status`

CPU, memory, uptime, and status for one server.

**inputSchema**
```json
{
  "type": "object",
  "properties": {
    "server_id": { "type": "string", "description": "The server's id, e.g. 'srv-1'." }
  },
  "required": ["server_id"]
}
```

**Example — success**
```
get_server_status({"server_id": "srv-2"})
→ {"id": "srv-2", "name": "worker-batch-02", "region": "us-west-2", "status": "degraded",
   "cpu_pct": 88.9, "mem_pct": 76.4, "uptime_s": 172800, "instance_count": 2}
```

**Example — unknown id (isError: true)**
```
get_server_status({"server_id": "nope"})
→ "No such server: nope"
```

### 4.3 `check_logs`

Most recent log lines for a server (newest first), optionally filtered by
level, capped at `limit` (default 20).

**inputSchema**
```json
{
  "type": "object",
  "properties": {
    "server_id": { "type": "string", "description": "The server's id, e.g. 'srv-1'." },
    "level":     { "type": "string", "enum": ["error", "warn", "info"], "description": "Only return log lines at this level." },
    "limit":     { "type": "integer", "default": 20, "description": "Maximum number of log lines to return (most recent first)." }
  },
  "required": ["server_id"]
}
```

**Example**
```
check_logs({"server_id": "srv-2", "level": "error", "limit": 5})
→ [{"timestamp": "2026-08-19T09:55:00", "level": "error", "message": "batch-worker restarted after OOM"}]
```

**Validation:** rejects an unknown `server_id`, a `level` outside the enum,
and a `limit` that isn't a positive integer (a JSON `true`/`false` is
explicitly rejected too, since Python's `bool` is a subclass of `int`).

### 4.4 `restart_service`

Restarts a service within a server: sets its status to `running` and
stamps `last_restart` with the current UTC time.

**inputSchema**
```json
{
  "type": "object",
  "properties": {
    "server_id": { "type": "string" },
    "service_name": { "type": "string", "description": "The service's name, e.g. 'nginx'." }
  },
  "required": ["server_id", "service_name"]
}
```

**Example**
```
restart_service({"server_id": "srv-1", "service_name": "nginx"})
→ {"server_id": "srv-1", "service_name": "nginx", "status": "running",
   "last_restart": "2026-08-20T23:27:15.070758+00:00"}
```

**Validation:** both the server and the named service (within that server)
must exist, or the call returns a tool-level error.

### 4.5 `scale_instance`

Adjusts a server's `instance_count` by `delta` (positive to scale up,
negative to scale down).

**inputSchema**
```json
{
  "type": "object",
  "properties": {
    "server_id": { "type": "string" },
    "delta": { "type": "integer", "description": "Positive to scale up, negative to scale down." }
  },
  "required": ["server_id", "delta"]
}
```

**Example — success**
```
scale_instance({"server_id": "srv-1", "delta": 1})
→ {"server_id": "srv-1", "instance_count": 4}
```

**Example — rejected (limit enforcement)**
```
scale_instance({"server_id": "srv-1", "delta": 999})
→ "Cannot scale server srv-1: instance_count would exceed the maximum of 10 (current 4, delta +999)"
```

**Validation:** the resulting `instance_count` must stay within
`0 ≤ instance_count ≤ MAX_INSTANCE_COUNT` (10, a module constant in
`server.py`) — the request is rejected outright, never clamped to the
boundary. Both boundary values themselves (exactly 0, exactly 10) are
valid and accepted.

## 5. Running it

**Standalone** (for testing/inspection, talking to it directly):
```bash
python -m servers.cloudops.seed    # populate data/cloudops.db with sample data
python -m servers.cloudops.server  # blocks, reading JSON-RPC from stdin
```

**Through the chatbot** (normal usage): `chatbot/main.py` connects to it
automatically on startup (`connect_cloudops_server`), auto-seeding the
database on first run if it doesn't exist yet. No manual setup needed —
just `python -m chatbot.main`.

**Remote (Render), standalone:**
```bash
PORT=8000 CLOUDOPS_TOKEN=<secret> python -m servers.cloudops.http_server
```
On Render itself, `PORT` is injected automatically — set the start command
to `python -m servers.cloudops.http_server` and `CLOUDOPS_TOKEN` as an
env var. To point the chatbot at it instead of the local subprocess, set in
`.env`: `CLOUDOPS_REMOTE_URL=https://<service>.onrender.com/mcp` and the
matching `CLOUDOPS_TOKEN`.

## 6. Usage examples (via the chatbot)

Natural-language prompts that route to each tool — Claude picks the tool
and arguments on its own from the `inputSchema` descriptions:

- *"List all my cloud servers."* → `list_servers`
- *"Which servers are in us-west-2?"* → `list_servers({"region": "us-west-2"})`
- *"What's the status of worker-batch-02?"* → `get_server_status`
- *"Show me the last 5 error logs for worker-batch-02."* → `check_logs`
- *"Restart nginx on api-gateway-01."* → `restart_service`
- *"Scale up db-replica-03 by 2 instances."* → `scale_instance({"delta": 2})`
- *"Scale worker-batch-02 down to zero — actually, all the way to -5."* →
  `scale_instance` called, rejected with the boundary error above (a good
  way to demo the validation live).

See `docs/demo-filesystem-git.md` for the equivalent walkthrough style
applied to the Filesystem+Git servers; a CloudOps demo transcript in the
same format is added in commit #18.
