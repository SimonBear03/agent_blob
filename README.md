# Agent Blob

WebSocket gateway and agent runtime. Clients connect over WebSocket; the gateway handles sessions, commands, and the agent loop.

## What’s in this repo

- **gateway/** – WebSocket server, connection handling, built-in commands
- **runtime/** – Agent loop, tools, process and session state
- **shared/** – Protocol, prompts, schemas
- **scripts/run_gateway.py** – Start the gateway

## Quick start

```bash
# Dependencies
pip install -r requirements.txt

# Config
cp .env.example .env
# Set OPENAI_API_KEY in .env

# Run gateway
python scripts/run_gateway.py
```

- WebSocket: `ws://127.0.0.1:3336/ws`
- Health: `http://127.0.0.1:3336/health`

## Layout

```
gateway/       # WS server, commands, queue, session keys
runtime/       # Agent (runtime_v2), tools, db, memory, storage, compaction
shared/        # protocol/, prompts/, schemas/, model_config, skills
scripts/       # run_gateway.py
```

Build clients against the WebSocket API; see `shared/protocol/protocol_v1.md` for the protocol.
