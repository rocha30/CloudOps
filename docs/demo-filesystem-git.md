# Demo: Filesystem + Git MCP servers (Part 1, commit #10)

End-to-end scenario required by the assignment: ask the chatbot to create a
repository, create a README file, add it, and commit it — all through
natural language, with the chatbot orchestrating both official MCP servers.

## Setup note: no `git_init` tool

The official `mcp-server-git` (current PyPI release) has no `git_init` tool —
every one of its 12 tools (`git_status`, `git_add`, `git_commit`, ...)
requires an existing `repo_path`. So "creating the repository" happens once
as chatbot startup (`git init` in `workspace/`, see `chatbot/main.py` →
`connect_git_server`), not as an LLM-driven tool call. Everything after that
— creating the file, staging it, committing it — is entirely LLM-driven.

## Transcript

```
Connected: Filesystem MCP server (sandbox: /path/to/CloudOps/workspace)
Connected: Git MCP server (repo: /path/to/CloudOps/workspace)
CloudOps chatbot — type 'exit' to quit, '/log' to show MCP interaction log.

You: Create a README.md file with the title "# CloudOps Demo" and one line
describing it as a test of the MCP filesystem and git integration. Then add
it to git and commit it with an appropriate message. Confirm each step
briefly.

Claude: ✅ Step 3 Complete: Changes committed successfully with hash
a4bb862da5a6d6841b9fe666c0e7d6ccfef2ad8b.

Summary:
- ✅ Created README.md with title "# CloudOps Demo" and description
- ✅ Added file to git staging area
- ✅ Committed with message "Initial commit: Add CloudOps Demo README with
  MCP integration test"

All steps completed successfully! The file is now tracked in the git
repository.
```

## Independent verification (not just Claude's word for it)

```
$ cat workspace/README.md
# CloudOps Demo

This is a test of the MCP filesystem and git integration.

$ git -C workspace log --oneline
a4bb862 Initial commit: Add CloudOps Demo README with MCP integration test

$ git -C workspace show --stat HEAD
commit a4bb862da5a6d6841b9fe666c0e7d6ccfef2ad8b
    Initial commit: Add CloudOps Demo README with MCP integration test

 README.md | 3 +++
 1 file changed, 3 insertions(+)
```

## What actually happened at the protocol level

From `mcp_client.interaction_logger` (functionality 3 — every one of these
lines is a real JSON-RPC request/response pair, logged automatically by the
`with_logging` wrapper without any special-casing in the tool-use loop):

| Server | Method | Tool called | Key arguments |
|---|---|---|---|
| filesystem | `initialize` | — | — |
| git | `initialize` | — | — |
| filesystem | `tools/list` | — | — |
| git | `tools/list` | — | — |
| filesystem | `tools/call` | `list_allowed_directories` | *(Claude checking the sandbox root first)* |
| filesystem | `tools/call` | `write_file` | `path: .../workspace/README.md` |
| git | `tools/call` | `git_add` | `files: ["README.md"]` |
| git | `tools/call` | `git_commit` | `message: "Initial commit: ..."` |

Notice Claude called `list_allowed_directories` on its own before writing —
it wasn't told the sandbox path, it discovered it via the tool's own
capabilities. This is the "agent coordinates tool use based on context"
behavior described in the assignment's background section (§1).

## Reproducing this demo

```bash
rm -rf workspace && mkdir workspace && touch workspace/.gitkeep  # clean slate
python -m chatbot.main
# then paste the same prompt used above
```
