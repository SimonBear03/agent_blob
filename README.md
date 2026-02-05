# Agent Blob (V2)

Always-on gateway + runtime (“master AI”) with:
- Universal WebSocket protocol for any client (CLI now; Telegram later)
- Durable tasks + supervisor loop (planned)
- Long-term memory (pinned + searchable, upgradeable)
- Tools and MCP capabilities (MCP integration planned)
- Interactive confirmations (Claude Code–style allow/ask/deny policy)

## Quick start

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
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
scripts/
  run_gateway.py  # start server
  cli.py          # minimal client
data/             # JSONL event log + memory + tasks (created at runtime)
```
