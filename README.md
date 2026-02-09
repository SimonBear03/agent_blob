# Agent Blob (V2)

Always-on gateway + runtime (“master AI”) with:
- Universal WebSocket protocol for any client (CLI now; Telegram later)
- Durable tasks + supervisor heartbeat
- Long-term memory (pinned + searchable, upgradeable)
- LLM tool-calling (filesystem/shell) with interactive confirmations
- MCP capabilities (Streamable HTTP)
- Interactive confirmations (Claude Code–style allow/ask/deny policy)
- Telegram DM client (polling mode, optional)

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
- Telegram client runs inside the gateway process when enabled.

Default endpoints:
- WebSocket: `ws://127.0.0.1:3336/ws`
- Health: `http://127.0.0.1:3336/health`
## Repo layout

```
agent_blob/
  gateway/        # networking, runs, permissions, event streaming
  runtime/        # agent loop, memory, tasks, capabilities
  policy/         # allow/ask/deny rules + matching
  frontends/
    native/       # first-party clients using Agent Blob protocol (CLI now)
    adapters/     # external platform adapters (Telegram now)
scripts/
  run_gateway.py  # start server
  cli.py          # CLI entrypoint (implementation lives in agent_blob/frontends/native/cli/)
  mcp_example_server.py  # local MCP test server (optional)
data/             # tasks/schedules/adapter state (created at runtime)
memory/           # canonical memory + event history (created at runtime)
agent_blob.json   # policy + data dir config
```

## Notes

- **Permissions** are controlled by `agent_blob.json` (`deny` > `ask` > `allow`). Shell commands default to `ask`.
- Interactive approvals are **not persisted by default** (`permissions.remember: false`).
- **Filesystem tool root** is controlled by `agent_blob.json` at `tools.allowed_fs_root` (defaults to current working directory).
- **Supervisor** emits only on change by default. Configure via `agent_blob.json` at `supervisor.interval_s`, `supervisor.debug`, and `supervisor.maintenance_interval_s`.
- **Memory** writes: `memory/pinned.json` (always loaded) and `memory/agent_blob.sqlite` (canonical long-term memory + BM25 + embeddings).
- **events.jsonl** is canonical run history at `memory/events.jsonl`; recent turns + episodic recall are derived from it.
- **Skills**: local `SKILL.md` files in `skills/` (and any other dirs configured in `agent_blob.json`) are injected as enabled skills and can be listed/read via `skills_list`/`skills_get`.
- **MCP**: `agent_blob/runtime/mcp/` implements MCP Streamable HTTP. Configure servers in `agent_blob.json` under `mcp.servers`, then use `mcp_list_tools` + `mcp_call` (or `mcp_refresh`).
- **System prompt**: built from modular prompt blocks in `agent_blob/runtime/prompts/system_prompt.py` (`master`, `scheduled`, `worker` modes) plus provider instructions.
- Prompt behavior can be tuned in `agent_blob.json` under `prompts`:
  - `include_memory_policy`, `include_editing_policy`, `include_tool_policy`
  - `include_examples`, `include_scheduling_policy`
  - `allow_worker_delegation`, `worker_include_change_summary`
  - `scheduled_force_execute`, `extra_instructions`
- **Web fetch**: `web_fetch` can fetch URLs for summarization/research (permission-gated).
- **Channel routing policy**: no broadcast by default. Replies go back to the origin client/channel only (CLI input -> CLI output, Telegram input -> Telegram output).

## Telegram (DM only)

Set secrets in `.env`:

```bash
TELEGRAM_BOT_TOKEN=...
```

Enable adapter in `agent_blob.json`:

```json
{
  "frontends": {
    "adapters": {
      "telegram": {
        "enabled": true,
        "mode": "polling",
        "poll_interval_s": 1.5,
        "stream_edit_interval_ms": 700,
        "status_verbosity": "minimal",
        "max_message_chars": 3800,
        "media": {
          "enabled": true,
          "download": true,
          "max_file_mb": 25,
          "download_dir": "./data/media/telegram"
        }
      }
    }
  }
}
```

Run gateway:

```bash
python3 scripts/run_gateway.py
```

Then DM your bot directly in Telegram.

Telegram behavior:
- DM text creates a runtime run through the same gateway/runtime path as CLI.
- Replies stream back to Telegram only (no cross-channel mirror).
- Permission requests show Allow/Deny inline buttons.
- Media (photo/document/voice) is accepted and attached as metadata in the run input.

## MCP (how to test)

1) Start the example MCP server (optional, for local testing):

```bash
python3 scripts/mcp_example_server.py --port 9000
```

2) Add it to `agent_blob.json`:

```json
{
  "mcp": {
    "servers": [
      { "name": "example", "url": "http://127.0.0.1:9000/mcp", "transport": "streamable-http" }
    ]
  }
}
```

3) Restart the gateway, then in the CLI ask:
- “List MCP servers”
- “List MCP tools”
- “Call `example.echo` with text hello”

MCP tools available in the example server:
- `example.echo` (`{ "text": "..." }`)
- `example.add` (`{ "a": 2, "b": 3 }`)
- `example.time` (`{}`)

## Skills

Skills are local folders containing `SKILL.md` files (OpenClaw-style). Configure:
- `skills.dirs` (where to search)
- `skills.enabled` (which ones to inject into the system prompt)
- `skills.max_chars` (cap total injected skill text)

Runtime tools:
- `skills_list` (shows available + enabled)
- `skills_get` (returns a skill body)

## Scheduler (background runs)

Schedules are stored in `data/schedules.json` and are triggered by the gateway supervisor loop.

Runtime tools:
- `schedule_list`
- `schedule_create_interval` (capability `schedules.write`, prompts by default)
- `schedule_create_daily` (capability `schedules.write`, prompts by default)
- `schedule_create_cron` (capability `schedules.write`, prompts by default)
- `schedule_update` (capability `schedules.write`, prompts by default)
- `schedule_delete` (capability `schedules.write`, prompts by default)

Example prompt to the agent:
- “Every 60 seconds, check my tasks and tell me what’s still running.”
- “Every day at 7:30 AM, give me a morning briefing about my tasks.” (set `scheduler.timezone` in `agent_blob.json` if needed)

## Data folder

Agent Blob keeps operational state in `data/` and memory/history in `memory/`.

- `data/tasks.json`: current task snapshot (purged by retention policy).
- `data/tasks_events.jsonl`: task history/audit (rotated/pruned by log rotation policy).
- `data/schedules.json`: schedule definitions (not purged).
- `data/telegram_offset.json`: Telegram adapter cursor state.
- `memory/events.jsonl`: canonical event log (rotated/pruned by log rotation policy).
- `memory/memory_events.jsonl`: memory audit log (`added` / `modified` / `removed`).
- `memory/pinned.json`: pinned memory (not automatically purged).
- `memory/agent_blob.sqlite`: consolidated/deduped structured memory (SQLite + FTS5 + embeddings).
- `memory/archives/`: rotated memory event logs.

### Retention policy

Only `data/tasks.json` is actively pruned today (via supervisor maintenance):
- Terminal tasks (`done/stopped/failed`) are kept for `maintenance.tasks_keep_done_days` days (default 30) and capped at `maintenance.tasks_keep_done_max` (default 200).
- Active tasks are always kept.

Additionally, tasks that remain non-terminal but inactive are **auto-closed**:
- Any task not updated for `tasks.auto_close_after_s` seconds (default 21600 = 6 hours) is set to `done` automatically.

Supervisor maintenance runs while the gateway is running, every `supervisor.maintenance_interval_s` seconds.

### Log rotation

JSONL logs are rotated and archived when they exceed configured size thresholds:
- `logs.events` controls `memory/events.jsonl`
- `logs.memory_events` controls `memory/memory_events.jsonl`
- `logs.tasks_events` controls `data/tasks_events.jsonl`

Each log type supports:
- `max_bytes`: rotate when the active file exceeds this size (0 disables rotation)
- `keep_days`: prune archives older than this many days (0 disables age pruning)
- `keep_max_files`: cap number of archives kept for this kind (0 disables the cap)

### Memory retrieval

Memory uses bounded retrieval, not full-history replay:
- `memory/events.jsonl` is canonical run history.
- `memory/agent_blob.sqlite` stores canonical long-term memory items.
- `memory/pinned.json` stores small always-load memory.

Each run injects:
- pinned memory,
- recent turns (bounded),
- related turns (bounded),
- top-K long-term memory hits (hybrid BM25 + vectors).

Memory behavior is controlled by `agent_blob.json` under `memory`:
- `memory.dir` (default `./memory`)
- `memory.importance_min`
- `memory.retrieval.recent_turns_limit`
- `memory.retrieval.related_turns_limit`
- `memory.retrieval.structured_limit`
- `memory.retrieval.introspection_limit`
- `memory.embedding_model`
- `memory.embeddings.enabled`
- `memory.embeddings.batch_size`
- `memory.embeddings.vector_scan_limit`
- `memory.embeddings.vector_top_k`

### Memory management tools

The agent can manage structured memories without using the shell:
- `memory_search` (capability `memory.search`) — find items + ids
- `memory_list_recent` (capability `memory.list`) — show recent items
- `memory_delete` (capability `memory.delete`) — delete by id (defaults to `ask`)

### Filesystem write tool

`filesystem_write` (capability `filesystem.write`) is permission-gated and shows a unified diff preview before writing.

### Shell command safety

`shell_run` (capability `shell.run`) is permission-gated. Commands that look like they **modify files** (redirections like `>`/`>>`, `tee`, `sed -i`, `rm`, etc.) are treated as `shell.write` and will prompt separately.

### Run stop

- Protocol supports `run.stop` with optional `{ "runId": "..." }`.
- If `runId` is omitted, gateway stops the latest active run for that same client.
- CLI supports `/stop <run_id>` and natural-language stop phrases (for example: `stop that run`, `please stop`).
- On stop, gateway emits `run.status=stopped` then `run.final`, and matching tasks are marked `stopped`.

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

4) **Memory V3 ingest + recall**
   - Ask: “We decided that Telegram should be an adapter frontend. Please remember this.”
   - Ask: “What do you remember about Telegram frontend design?”
   - Confirm the answer is grounded in stored memory and not full-history replay.

5) **Memory delete guardrail**
   - Ask: “Add a memory that X is true.”
   - Confirm the agent does not call `memory_delete`.
   - Ask explicitly: “Forget the memory about X.”
   - Confirm `memory_delete` is requested and permission-gated.

6) **Run stop**
   - Start a long request (for example a web-fetch-heavy prompt).
   - Stop it with either `/stop <run_id>` or a plain message like `stop that run`.
   - Confirm you receive `status: stopped` and a final event.

4) **MCP**
   - Start `python3 scripts/mcp_example_server.py --port 9000`.
   - Add the server to `agent_blob.json` and restart gateway.
   - Ask: “List MCP servers”, then “List MCP tools”, then “Call `example.add` with a=2 b=3”.

5) **Skills**
   - Ask “list skills” and “get skill general”.

Bundled example skills live under `agent_blob/runtime/skills/examples/`. Your own skills can live in `./skills/`.

6) **Scheduler**
   - Ask: “Create a schedule to say ‘hello from schedule’ every 10 seconds.”
   - Approve the schedule write prompt.
   - Wait ~15 seconds and confirm you see a background run (run ids like `run_sched_*`) producing output.
   - Ask: “List schedules” (should show the new schedule).
   - Ask: “Every day at 7:30 AM, remind me to check positions.”
   - Approve the schedule write prompt, then “List schedules” and confirm a `type: cron` schedule exists.
   - Ask: “Disable the schedule you just created.”
   - Approve the schedule write prompt, then “List schedules” and confirm it shows `enabled: false`.
   - Ask: “Every 10 seconds, run `echo hi` in the shell.”
   - Confirm scheduled runs consistently call `shell_run` (they should not respond “I can’t run shell commands”).
   - (Offline-safe) Stop the CLI, keep gateway running, create a schedule that tries a permissioned action (e.g. “Every 10 seconds, run `echo hi` in the shell”). Wait for it to trigger.
   - Reconnect with the CLI and confirm you receive the queued permission prompt.

7) **Workers (delegation)**
   - Ask: “Use a briefing worker to summarize the home page of https://example.com”
   - Approve `workers.run` then approve `web.fetch` when prompted.
   - Confirm the final answer includes the worker result and you saw tool calls under a `run_worker_*` run id.
   - Ask: “Any workers active right now?”
   - Confirm it reports active workers (or none).

8) **Telegram DM**
   - Enable telegram in `agent_blob.json` and set `TELEGRAM_BOT_TOKEN`.
   - Run `python3 scripts/run_gateway.py`.
   - Send a DM text to the bot; confirm you receive streamed response in Telegram.
   - Trigger a permissioned action; confirm inline Allow/Deny appears and works.
   - Send a photo/document/voice; confirm run is accepted (attachment metadata included).
