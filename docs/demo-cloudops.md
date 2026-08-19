# Demo: CloudOps MCP server (commit #18)

End-to-end scenario from the assignment's background section (§1): "pregúntale
al chatbot el estado de un servidor y pídele que reinicie un servicio" —
check a server's status and ask the chatbot to restart a service, all
through natural language, with the chatbot's own custom MCP server.

## Transcript

```
Connected: Filesystem MCP server (sandbox: .../workspace)
Connected: Git MCP server (repo: .../workspace)
Connected: CloudOps MCP server (db: .../data/cloudops.db)
CloudOps chatbot — type 'exit' to quit, '/log' (or '/log <server>') to show MCP interaction log.

You: What is the status of worker-batch-02? If it looks unhealthy, restart
its batch-worker service and confirm.

Claude: Status Summary:
- Server: worker-batch-02 (srv-2) - DEGRADED
- CPU: 88.9% (High)
- Memory: 76.4% (High)
- Uptime: 2 days

Action Taken:
✅ Batch-worker service restarted successfully
- Service status: running
- Last restart: 2026-08-21 at 01:06:28 UTC

The service has been restarted. You may want to monitor the server's CPU
and memory usage over the next few minutes to confirm the restart
alleviates the degraded state.
```

## Independent verification

```
$ python3 -c "
from servers.cloudops.db import get_connection
conn = get_connection()
row = conn.execute(\"SELECT status, last_restart FROM services \
  WHERE server_id='srv-2' AND name='batch-worker'\").fetchone()
print(dict(row))
"
{'status': 'running', 'last_restart': '2026-08-21T01:06:28.078624+00:00'}
```

## What actually happened, tool call by tool call

This run is a better demo than a clean one would have been — Claude didn't
know server *names* aren't valid `server_id`s, got two tool-level errors,
and recovered on its own without any hint from the user:

| # | Tool call | Arguments | Result |
|---|---|---|---|
| 1 | `get_server_status` | `server_id: "worker-batch-02"` | ❌ `isError: true` — "No such server: worker-batch-02" |
| 2 | `check_logs` | `server_id: "worker-batch-02"` | ❌ `isError: true` — same reason |
| 3 | `list_servers` | *(none)* | ✅ discovers the real id: `srv-2` |
| 4 | `restart_service` | `server_id: "srv-2", service_name: "batch-worker"` | ✅ `isError: false` |

Steps 1-2 used the server's display **name** as if it were its `id` — a
reasonable guess from the tool's description alone. After two tool-level
errors (not protocol errors — the JSON-RPC calls succeeded; the *tool*
correctly rejected an unknown id), Claude fell back to `list_servers` to
resolve the real id, then completed the original request. This is the
"agent coordinates tool use based on context" behavior the assignment's
background section describes (§1) — visible here specifically as
*recovering from a tool-level error*, not just chaining happy-path calls.

## Reading this from `/log`

The commit #18 logging improvements make this readable without decoding
raw JSON-RPC by hand — `/log cloudops` from inside the chatbot (or
`InteractionLogger().print_recent(server="cloudops")`) prints:

```
[...] cloudops -> initialize
[...] cloudops <- result (20.8 ms)
[...] cloudops -> tools/list
[...] cloudops <- result (0.1 ms)
[...] cloudops -> tools/call(get_server_status)
[...] cloudops <- result (isError=True) (2.4 ms)
[...] cloudops -> tools/call(check_logs)
[...] cloudops <- result (isError=True) (0.3 ms)
[...] cloudops -> tools/call(list_servers)
[...] cloudops <- result (isError=False) (0.2 ms)
[...] cloudops -> tools/call(restart_service)
[...] cloudops <- result (isError=False) (4.0 ms)
```

Before this commit, every response line rendered as the same generic
`<- response (N ms)` regardless of what happened — the tool name and
success/failure were invisible without opening the raw JSONL log. Now the
tool name is on the request line and the outcome is on the response line,
which is what actually made the recovery sequence above easy to read back.

## Reproducing this demo

```bash
rm -f data/cloudops.db logs/mcp_interactions.jsonl  # clean slate
python -m chatbot.main
# then paste the same prompt used above
```
