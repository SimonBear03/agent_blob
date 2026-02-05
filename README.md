# Agent Blob (V2)

Always-on gateway + runtime (“master AI”) with:
- Universal WebSocket protocol for any client (CLI now; Telegram later)
- Durable tasks + supervisor heartbeat
- Long-term memory (pinned + searchable, upgradeable)
- LLM tool-calling (filesystem/shell) with interactive confirmations
- MCP capabilities (Streamable HTTP)
- Interactive confirmations (Claude Code–style allow/ask/deny policy)

## Quick start

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
 # Set OPENAI_API_KEY in .env
 # Configure non-secrets in agent_blob.json (model_name, ports, retention, etc.)

python3 scripts/run_gateway.py
python3 scripts/cli.py
```

Notes:
- `run_gateway.py` is not a global command; run it as `python3 scripts/run_gateway.py` (or `scripts/run_gateway.py`).
- Same for the CLI: `python3 scripts/cli.py` (or `scripts/cli.py`).

Default endpoints:
- WebSocket: `ws://127.0.0.1:3336/ws`
- Health: `http://127.0.0.1:3336/health`
## Repo layout

```
agent_blob/
  gateway/        # networking, runs, permissions, event streaming
  runtime/        # agent loop, memory, tasks, capabilities
  policy/         # allow/ask/deny rules + matching
  clients/        # client implementations (CLI now; more later)
scripts/
  run_gateway.py  # start server
  cli.py          # CLI entrypoint (implementation lives in agent_blob/clients/cli/)
data/             # JSONL event log + memory + tasks (created at runtime)
agent_blob.json   # policy + data dir config
```

## Notes

- **Permissions** are controlled by `agent_blob.json` (`deny` > `ask` > `allow`). Shell commands default to `ask`.
- Interactive approvals are **not persisted by default** (`permissions.remember: false`).
- **Filesystem tool root** is controlled by `agent_blob.json` at `tools.allowed_fs_root` (defaults to current working directory).
- **Supervisor** emits only on change by default. Configure via `agent_blob.json` at `supervisor.interval_s`, `supervisor.debug`, and `supervisor.maintenance_interval_s`.
- **Memory** writes: `data/pinned.json` (always loaded), `data/memories.jsonl` (structured candidates/audit), `data/agent_blob.sqlite` (consolidated memory state + BM25 + embeddings).
- **events.jsonl** is the canonical log; recent turns + episodic recall are derived from it (not from a separate “session” store).
- **Skills**: local `SKILL.md` files in `skills/` (and any other dirs configured in `agent_blob.json`) are injected as enabled skills and can be listed/read via `skills_list`/`skills_get`.
- **MCP**: `agent_blob/runtime/mcp/` implements MCP Streamable HTTP. Configure servers in `agent_blob.json` under `mcp.servers`, then use `mcp_list_tools` + `mcp_call` (or `mcp_refresh`).
- **Web fetch**: `web_fetch` can fetch URLs for summarization/research (permission-gated).

## Data folder

Agent Blob keeps an append-only audit trail plus small “current state” snapshots in `data/`.

- `data/events.jsonl`: canonical event log (rotated/pruned by log rotation policy).
- `data/tasks.json`: current task snapshot (purged by retention policy).
- `data/tasks_events.jsonl`: task history/audit (rotated/pruned by log rotation policy).
- `data/schedules.json`: schedule definitions (not purged).
- `data/pinned.json`: pinned memory (not automatically purged).
- `data/memories.jsonl`: extracted structured memory candidates (rotated/pruned by log rotation policy).
- `data/agent_blob.sqlite`: consolidated/deduped structured memory (SQLite + FTS5 + embeddings).
- `data/archives/`: rotated JSONL logs + `index.json` (simple archive index).

### Retention policy

Only `data/tasks.json` is actively pruned today (via supervisor maintenance):
- Terminal tasks (`done/cancelled/failed`) are kept for `maintenance.tasks_keep_done_days` days (default 30) and capped at `maintenance.tasks_keep_done_max` (default 200).
- Active tasks are always kept.

Additionally, tasks that remain non-terminal but inactive are **auto-closed**:
- Any task not updated for `tasks.auto_close_after_s` seconds (default 21600 = 6 hours) is set to `done` automatically.

Supervisor maintenance runs while the gateway is running, every `supervisor.maintenance_interval_s` seconds.

### Log rotation

JSONL logs are rotated and archived under `data/archives/` when they exceed configured size thresholds:
- `logs.events` controls `data/events.jsonl`
- `logs.tasks_events` controls `data/tasks_events.jsonl`
- `logs.memories` controls `data/memories.jsonl`

Each log type supports:
- `max_bytes`: rotate when the active file exceeds this size (0 disables rotation)
- `keep_days`: prune archives older than this many days (0 disables age pruning)
- `keep_max_files`: cap number of archives kept for this kind (0 disables the cap)

### Memory retrieval

Structured long-term memory retrieval is backed by `data/agent_blob.sqlite`:
- **Lexical search**: SQLite FTS5 (BM25)
- **Vector search**: OpenAI embeddings stored as float32 blobs (no SQLite extension required). Candidate generation scans the most recent embedded items (bounded), then unions with BM25 candidates.

Embedding behavior is controlled by `agent_blob.json` under `memory`:
- `memory.embedding_model` (default `text-embedding-3-small`)
- `memory.embeddings.enabled` (default `true`)
- `memory.embeddings.batch_size` (default `16`) — refreshed during supervisor maintenance
- `memory.embeddings.vector_scan_limit` (default `2000`) — how many recent embedded items to scan for vector candidates
- `memory.embeddings.vector_top_k` (default `50`) — number of vector candidates to union with BM25 candidates

### Memory management tools

The agent can manage structured memories without using the shell:
- `memory_search` (capability `memory.search`) — find items + ids
- `memory_list_recent` (capability `memory.list`) — show recent items
- `memory_delete` (capability `memory.delete`) — delete by id (defaults to `ask`)

### Filesystem write tool

`filesystem_write` (capability `filesystem.write`) is permission-gated and shows a unified diff preview before writing.

### Shell command safety

`shell_run` (capability `shell.run`) is permission-gated. Commands that look like they **modify files** (redirections like `>`/`>>`, `tee`, `sed -i`, `rm`, etc.) are treated as `shell.write` and will prompt separately.

## Testing checklist

1) **Permission prompt**
   - Trigger a permission prompt (e.g. ask “run `echo hi` in the shell”).
   - Confirm you can answer `y` (allow) or `n` (deny).

2) **filesystem_write preview**
   - Ask: “Create `tmp/test.txt` with the content ‘hello’.”
   - Confirm the permission preview shows a diff and, if you allow, the file is written.
   - Ask: “Update `tmp/test.txt` to add a second line ‘world’.”
   - Confirm the diff shows the change.

3) **Find + edit workflow (Claude/Codex-style)**
   - Ask: “Find the file that contains `agent_blob.json` permissions and show me where `filesystem.write` is mentioned.”
   - Confirm the agent uses `fs_grep` (safe) and/or `filesystem_read`.
   - Ask: “In `tmp/test.txt`, change `hello` to `hello!`.”
   - Confirm the agent uses `edit_apply_patch` and you see a diff preview.

3) **MCP**
   - Run `mcp_list_tools` and `mcp_call` against your configured MCP server.

4) **Skills**
   - Ask “list skills” and “get skill summarize”.

## Skills

Skills live under `skills/` as folders containing `SKILL.md`. Configure:
- `skills.dirs` (search paths)
- `skills.enabled` (injected into the system prompt)
- `skills.max_chars` (cap total injected skill text)

Use tools:
- `skills_list`
- `skills_get`

Bundled starter skills: `summarize`, `skill-creator`, `obsidian`.
