# Telegram Client Plan (DM Only, Origin-Channel Replies)

## Goal
Add a Telegram client that behaves like CLI:
- Accept user messages from Telegram DM.
- Send all responses back to the same Telegram DM.
- Keep client logic thin ("dumb client").
- Keep orchestration, memory, tools, permissions, and scheduling in gateway/runtime.

## Routing Policy (Locked)
1. No cross-channel broadcast.
2. Reply goes to origin channel only (Telegram input -> Telegram output, CLI input -> CLI output).
3. Permission prompts are shown only on the origin channel for that run.
4. Shared backend state remains global (memory/tasks/schedules) across clients.

## Scope
### In scope
- Telegram 1:1 DM text flow.
- Gateway-to-Telegram event rendering.
- Permission approvals through Telegram inline buttons.
- Media ingestion metadata (photo/document/voice) routed to runtime as attachments.

### Out of scope (initial)
- Group chats.
- Multi-user auth model.
- Cross-channel mirroring.

## Architecture
### Components
1. `agent_blob/frontends/adapters/telegram/poller.py`
   - Long-poll `getUpdates`.
   - Convert updates into gateway run requests.
   - Track `update_id` checkpoint.

2. `agent_blob/frontends/adapters/telegram/client.py`
   - Send/edit Telegram messages.
   - Build inline keyboard for permission prompts.
   - Handle callback queries for allow/deny.

3. Gateway run sink routing
   - Introduce per-run output sink (WS sink for CLI, Telegram sink for Telegram).
   - Ensure scheduled runs keep current behavior (broadcast to connected sinks or future policy selection).

4. Attachment envelope
   - Normalize Telegram media into a stable payload:
     - `kind`, `file_id`, `mime_type`, `size`, `local_path` (if downloaded), `caption`.
   - Pass envelope in run input metadata.

## Execution Flow
1. Telegram DM update arrives.
2. Poller maps it to `run.create` (internal gateway method), with channel context:
   - `channel=telegram`, `chat_id`, `user_id`, `message_id`.
3. Gateway starts runtime run and binds output to Telegram sink for that run.
4. Runtime emits events.
5. Telegram sink renders events:
   - status/log: minimal
   - token stream: incremental message edit
   - final/error: finalize message
   - permission.request: inline buttons
6. User taps allow/deny -> callback -> gateway `permission.respond`.

## Event Rendering Rules (CLI parity, Telegram-safe)
1. Keep one active assistant message per run for streaming.
2. Edit that message every N ms (rate-limited) during token streaming.
3. On completion, send final if needed and stop edits.
4. Tool/status logs are concise (avoid flooding).
5. Permission prompts are separate messages with inline buttons.

## Configuration
Add to `agent_blob.json`:

```json
{
  "frontends": {
    "adapters": {
      "telegram": {
        "enabled": false,
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

Secrets remain in `.env`:
- `TELEGRAM_BOT_TOKEN`

## Reliability Requirements
1. Polling reconnect loop with backoff.
2. Exactly-once update consumption via persisted last `update_id`.
3. Safe handling of stale callback queries.
4. No gateway crash if Telegram API temporarily fails.

## Acceptance Tests
1. DM text -> run executes -> response in same DM.
2. Permissioned action -> inline allow/deny works.
3. Runtime error -> Telegram displays clean error.
4. Restart gateway -> polling resumes without duplicate handling.
5. Telegram input does not appear in CLI by default.
6. CLI input does not appear in Telegram by default.

## Implementation Order
1. Gateway sink abstraction (origin-channel routing).
2. Telegram poller + text send.
3. Telegram permission callbacks.
4. Media attachment envelope.
5. Docs/tests.
