# Agent Blob (V2)

Always-on gateway + runtime (“master AI”) with:
- Universal WebSocket protocol for any client (CLI now; Telegram later)
- Durable tasks + supervisor heartbeat
- Long-term memory (pinned + searchable, upgradeable)
- LLM tool-calling (filesystem/shell) with interactive confirmations
- MCP capabilities (planned)
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
- **Filesystem tool root** is controlled by `ALLOWED_FS_ROOT` (defaults to current working directory).
- **Supervisor** emits only on change by default; set `SUPERVISOR_DEBUG=1` to log periodic ticks. Interval via `SUPERVISOR_INTERVAL_S` (default `15`).
- **Memory** writes: `data/pinned.json` (always loaded), `data/memories.jsonl` (structured candidates), `data/memory_state.json` (consolidated state).
- **events.jsonl** is the canonical log; recent turns + episodic recall are derived from it (not from a separate “session” store).
