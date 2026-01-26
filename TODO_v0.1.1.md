# Agent Blob v0.1.1 — Universal Gateway Architecture (TODO)

This release transforms `agent_blob` into a **Clawdbot-style universal gateway** where the gateway IS the product and clients are truly dumb transport layers.

## Architecture Decision (Locked for v0.1.1)

**Gateway = Agent System** (not just routing)
- The gateway owns ALL: WebSocket protocol, agent loop, tools, sessions, memory
- Clients (Web UI, CLI, Telegram) are **thin adapters** that only connect to WebSocket and forward messages
- One process, one daemon, universal protocol

**Transport**: WebSocket (ws://localhost:3336)

## Core Philosophy (Learned from Clawdbot)

1. **Gateway is the product**
   - Gateway owns messaging, agent loop, tool execution, session management, and state
   - Not a "router" between services - it IS the agent system

2. **Clients are truly dumb**
   - Every client does the same thing: connect to WebSocket, send messages, receive events
   - No client-specific agent logic, no special handling
   - Web UI = CLI = Telegram = just different ways to send text over WebSocket

3. **Commands are gateway commands**
   - `/new`, `/sessions`, `/status` are handled BY THE GATEWAY, not by clients
   - Clients just send them as plain text
   - Gateway recognizes and processes them

4. **Universal session model**
   - All sessions use pure UUIDs: `550e8400-e29b-41d4-a906-446655440000`
   - No client encoding in ID - gateway tracks which clients connect to which sessions
   - Sessions sorted by **last activity** (most recent message), not created date
   - Navigate sessions via commands: `/sessions` to list, `/session <number>` to switch

5. **Multi-client support (Full Broadcast)**
   - Multiple clients can connect to the SAME session simultaneously
   - All clients see ALL messages, including what other clients sent
   - Example: Start chat on Telegram, continue on Web UI - both see full conversation
   - Gateway broadcasts every message/event to all connected clients in that session

6. **Simple protocol**
   - Requests: `{type: "req", id: "...", method: "agent", params: {...}}`
   - Responses: `{type: "res", id: "...", ok: true, payload: {...}}`
   - Events: `{type: "event", event: "token", payload: {...}}`

## Why This Architecture

Right now, the Web UI is tightly coupled to the agent. The server exposes HTTP endpoints that the Web UI calls. This breaks when:

- We add CLI: need to duplicate agent logic or create yet another HTTP client
- We add Telegram: need a bot that somehow talks to the server HTTP API
- We want streaming: HTTP request/response doesn't support real-time token streaming
- We want tool progress: no way to push updates to clients

**With the Clawdbot model:**
- Adding a new client = write 50 lines of WebSocket connection code
- Streaming works uniformly for all clients
- Gateway can push events (tool progress, status updates) anytime
- Protocol is versioned and stable

## Why Python is Better Here

Clawdbot uses Node.js (TypeScript). Agent Blob uses Python. Advantages:

1. **Rich AI ecosystem**: LangChain, llama-index, sentence-transformers, FAISS
2. **Memory/embeddings**: Easy to add vector DB (ChromaDB, Weaviate) later
3. **Large context handling**: Better libraries for context compression, summarization
4. **Scientific Python**: NumPy, pandas for data-heavy tools
5. **FastAPI**: Excellent WebSocket support + async/await native

We keep the **Clawdbot architecture** (gateway-centric, dumb clients) but leverage **Python's strengths** for the agent intelligence layer.

## Workflow (User → Gateway → Agent → Client)

```mermaid
flowchart TD
  U[User] --> C[Client\n(Web UI / CLI / Telegram)]
  C -->|WebSocket: req:agent| WS[Gateway WS Handler]
  
  WS -->|1. Parse & validate request| P[Protocol Handler]
  P -->|2. Extract session_id + message| R[Agent Runtime]
  
  R -->|3. Load history from DB| DB[(SQLite\nsessions + messages)]
  DB --> R
  
  R -->|4. Build prompt + call LLM| LLM[OpenAI / Anthropic]
  LLM -->|stream tokens| R
  LLM -->|tool call| R
  
  R -->|5. Execute tool| T[Tool Registry]
  T --> R
  
  R -->|6. Yield events| WS
  WS -->|7. Stream to client| C
  C -->|8. Render| U
  
  R -->|9. Persist to DB| DB
```

## New Folder Structure

```
agent_blob/
├── apps/
│   ├── gateway/                    # The universal gateway (replaces apps/server)
│   │   ├── main.py                 # FastAPI app + WebSocket endpoint
│   │   ├── protocol.py             # Request/Response/Event types (Pydantic models)
│   │   ├── handlers.py             # Route methods to runtime
│   │   ├── commands.py             # Handle /new, /sessions, /status, etc.
│   │   ├── connections.py          # Multi-client connection management
│   │   └── queue.py                # Per-session request queue
│   │
│   ├── agent_runtime/              # Agent logic (no transport knowledge)
│   │   ├── runtime.py              # AgentRuntime.process() - main loop
│   │   ├── sessions.py             # Session/conversation management
│   │   ├── processes.py            # Process manager (track running tools/tasks)
│   │   ├── tools/                  # Tool registry + implementations
│   │   │   ├── __init__.py         # Registry
│   │   │   ├── filesystem.py       # File operations
│   │   │   ├── memory_tools.py     # Memory CRUD
│   │   │   ├── session_tools.py    # Sessions search/list (for LLM)
│   │   │   └── process_tools.py    # Process list/cancel/status
│   │   └── db/                     # Database layer
│   │       ├── __init__.py
│   │       ├── sessions.py         # Was threads.py
│   │       ├── messages.py
│   │       ├── memory.py
│   │       ├── agent_runs.py       # NEW: track agent request runs
│   │       └── audit.py
│   │
│   ├── web/                        # Next.js frontend (becomes WebSocket client)
│   │   └── ... (existing structure, rewire to WebSocket)
│   │
│   └── cli/                        # Simple CLI client (NEW)
│       └── main.py                 # Connect to WS, send/receive
│
├── shared/
│   ├── protocol/                   # Protocol schemas (shared knowledge)
│   │   ├── protocol_v1.md          # Human-readable protocol spec
│   │   ├── request.schema.json     # JSON Schema for requests
│   │   ├── response.schema.json    # JSON Schema for responses
│   │   └── event.schema.json       # JSON Schema for events
│   ├── prompts/
│   └── skills/
│
└── README.md
```

## Protocol Definition (v1)

### Connection Handshake

First frame MUST be `connect`:

```json
{
  "type": "req",
  "id": "connect-1",
  "method": "connect",
  "params": {
    "version": "1",
    "clientType": "web" | "cli" | "telegram"
  }
}
```

Gateway responds:

```json
{
  "type": "res",
  "id": "connect-1",
  "ok": true,
  "payload": {
    "gatewayVersion": "0.1.1",
    "supportedMethods": ["agent", "sessions.list", "sessions.new", "status"]
  }
}
```

### Request Frame

```typescript
{
  "type": "req",
  "id": string,              // Client-generated, for matching response
  "method": string,          // "agent" | "sessions.list" | "sessions.new" | "status"
  "params": {
    "sessionId"?: string,    // Optional, gateway creates if missing
    "message"?: string,      // For "agent" method
    ...                      // Method-specific params
  }
}
```

### Response Frame

```typescript
{
  "type": "res",
  "id": string,              // Matches request.id
  "ok": boolean,
  "payload"?: any,           // Success payload
  "error"?: string           // Error message if ok=false
}
```

### Event Frame (Streaming)

```typescript
{
  "type": "event",
  "event": string,           // "token" | "tool_call" | "tool_result" | "status" | "final" | "error"
  "payload": {
    "runId"?: string,        // Ties events to a specific agent run
    "sessionId"?: string,
    ...                      // Event-specific data
  },
  "seq"?: number             // Optional sequence number
}
```

## Event Types

### `message` - User message echo (multi-client broadcast)

Sent when ANY client sends a message to the session (all connected clients receive this):

```json
{
  "type": "event",
  "event": "message",
  "payload": {
    "role": "user",
    "content": "Hello",
    "messageId": "msg_abc123",
    "timestamp": "2026-01-26T10:30:00Z",
    "fromSelf": true  // true if this client sent it, false if another client
  }
}
```

### `queued` - Request queued (immediate feedback)

Sent immediately when a message is queued (e.g., if previous request still processing):

```json
{
  "type": "event",
  "event": "queued",
  "payload": {
    "requestId": "req_xyz",
    "position": 2,
    "message": "✓ Message queued (position 2)"
  }
}
```

### `token` - Streaming text tokens

```json
{
  "type": "event",
  "event": "token",
  "payload": {
    "runId": "abc123",
    "content": "Hello",
    "delta": true
  },
  "seq": 42  // optional sequence number
}
```

### `tool_call` - Agent calling a tool

```json
{
  "type": "event",
  "event": "tool_call",
  "payload": {
    "runId": "abc123",
    "toolName": "filesystem.read",
    "arguments": {"path": "config.json"}
  }
}
```

### `tool_result` - Tool execution result

```json
{
  "type": "event",
  "event": "tool_result",
  "payload": {
    "runId": "abc123",
    "toolName": "filesystem.read",
    "result": {"success": true, "content": "..."}
  }
}
```

### `status` - Agent status update

```json
{
  "type": "event",
  "event": "status",
  "payload": {
    "runId": "abc123",
    "status": "thinking" | "executing_tool" | "streaming" | "done"
  }
}
```

### `final` - Agent finished

```json
{
  "type": "event",
  "event": "final",
  "payload": {
    "runId": "abc123",
    "messageId": "msg_xyz",
    "totalTokens": 1234
  }
}
```

### `cancelled` - Request cancelled

```json
{
  "type": "event",
  "event": "cancelled",
  "payload": {
    "runId": "run_xyz",
    "message": "Request cancelled by user"
  }
}
```

### `error` - Error occurred

```json
{
  "type": "event",
  "event": "error",
  "payload": {
    "runId": "abc123",
    "message": "Tool execution failed",
    "retryable": false,
    "errorCode": "TOOL_EXECUTION_FAILED"
  }
}
```

**Error Handling Philosophy:**
- Connection stays open unless client sends malformed JSON or invalid handshake
- Recoverable errors (tool failure, LLM timeout) → send `error` event, keep connection alive
- Unrecoverable errors (invalid API key) → send `error` event with `retryable: false`, keep connection alive
- Client decides whether to retry, switch sessions, or close

## Methods

### `agent` - Send message to agent

**Request:**
```json
{
  "type": "req",
  "id": "req-1",
  "method": "agent",
  "params": {
    "sessionId": "550e8400-e29b-41d4-a906-446655440000",
    "message": "Hello, agent!"
  }
}
```

**Response (immediate ack):**
```json
{
  "type": "res",
  "id": "req-1",
  "ok": true,
  "payload": {
    "runId": "run_xyz",
    "status": "accepted"  // or "queued" if request queued
  }
}
```

**If queued, also sends `queued` event immediately**

**Then streams events: `message` → `token` → `tool_call` → `tool_result` → `final`**

**Queueing behavior:**
- Per-session queue: only one agent request processed at a time per session
- If previous request still running, new request is queued
- Gateway sends immediate response: `{"status": "queued"}` + `queued` event
- When queue position reached, processing starts and events stream

### `agent.cancel` - Cancel running request

**Request:**
```json
{
  "type": "req",
  "id": "req-2",
  "method": "agent.cancel",
  "params": {
    "runId": "run_xyz"
  }
}
```

**Response:**
```json
{
  "type": "res",
  "id": "req-2",
  "ok": true,
  "payload": {
    "message": "Cancellation requested"
  }
}
```

**Then sends `cancelled` event when cancellation completes**

### `sessions.list` - List sessions (sorted by most recent activity)

**Request:**
```json
{
  "type": "req",
  "id": "req-3",
  "method": "sessions.list",
  "params": {
    "limit": 10,  // optional, default 10
    "offset": 0   // optional, for pagination
  }
}
```

**Response (sorted by last message time, descending):**
```json
{
  "type": "res",
  "id": "req-3",
  "ok": true,
  "payload": {
    "sessions": [
      {
        "id": "550e8400-e29b-41d4-a906-446655440000",
        "title": "AI architecture discussion",
        "lastMessage": "That makes sense!",
        "lastActivity": "2026-01-26T10:00:00Z",
        "messageCount": 42
      },
      {
        "id": "6ba7b810-9dad-11d1-80b4-00c04fd430c8",
        "title": "Python async patterns",
        "lastMessage": "Thanks for the explanation",
        "lastActivity": "2026-01-25T15:30:00Z",
        "messageCount": 15
      }
    ],
    "total": 25
  }
}
```

### `sessions.new` - Create new session

**Request:**
```json
{
  "type": "req",
  "id": "req-4",
  "method": "sessions.new",
  "params": {
    "title": "New conversation"  // optional
  }
}
```

**Response:**
```json
{
  "type": "res",
  "id": "req-4",
  "ok": true,
  "payload": {
    "sessionId": "7c9e6679-7425-40de-944b-e07fc1f90ae7",
    "title": "New conversation",
    "createdAt": "2026-01-26T11:00:00Z"
  }
}
```

### `sessions.switch` - Switch to different session

**Request:**
```json
{
  "type": "req",
  "id": "req-5",
  "method": "sessions.switch",
  "params": {
    "sessionId": "550e8400-e29b-41d4-a906-446655440000"
  }
}
```

**Response (includes recent message history):**
```json
{
  "type": "res",
  "id": "req-5",
  "ok": true,
  "payload": {
    "sessionId": "550e8400-e29b-41d4-a906-446655440000",
    "title": "AI architecture discussion",
    "recentMessages": [
      {
        "role": "user",
        "content": "How does the gateway work?",
        "timestamp": "2026-01-26T09:55:00Z"
      },
      {
        "role": "assistant",
        "content": "The gateway owns all messaging...",
        "timestamp": "2026-01-26T09:55:05Z"
      }
    ]
  }
}
```

### `sessions.history` - Get session message history

**Request:**
```json
{
  "type": "req",
  "id": "req-6",
  "method": "sessions.history",
  "params": {
    "sessionId": "550e8400-e29b-41d4-a906-446655440000",  // optional, defaults to current
    "limit": 20,  // optional, default 20
    "before": "msg_xyz"  // optional, for pagination (get messages before this message_id)
  }
}
```

**Response:**
```json
{
  "type": "res",
  "id": "req-6",
  "ok": true,
  "payload": {
    "messages": [
      {
        "id": "msg_abc",
        "role": "user",
        "content": "Hello",
        "timestamp": "2026-01-26T09:00:00Z"
      },
      {
        "id": "msg_def",
        "role": "assistant",
        "content": "Hi there!",
        "timestamp": "2026-01-26T09:00:05Z"
      }
    ],
    "hasMore": true
  }
}
```

### `status` - Get gateway status

**Request:**
```json
{
  "type": "req",
  "id": "req-7",
  "method": "status",
  "params": {
    "sessionId": "550e8400-e29b-41d4-a906-446655440000"  // optional
  }
}
```

**Response:**
```json
{
  "type": "res",
  "id": "req-7",
  "ok": true,
  "payload": {
    "gateway": {
      "version": "0.1.1",
      "uptime": 3600,
      "activeConnections": 5,
      "activeSessions": 3
    },
    "session": {  // if sessionId provided
      "id": "550e8400-e29b-41d4-a906-446655440000",
      "messageCount": 42,
      "queuedRequests": 0,
      "activeRun": null  // or runId if processing
    }
  }
}
```

## Gateway Commands (Processed by Gateway)

Users can send these as regular messages (clients just send as text, gateway intercepts):

### Session Management
- `/new` - Create new session and switch to it
- `/sessions` - List recent sessions (sorted by last activity)
  ```
  📋 Recent sessions:
    1. [2 min ago] AI architecture discussion
    2. [yesterday] Python async patterns
    3. [3 days ago] Project planning
  
  Reply with /session <number> to switch
  ```
- `/session <number>` - Switch to a session from the list (e.g., `/session 2`)
- `/session <uuid>` - Switch to a specific session by full ID
- `/history [count]` - Show last N messages in current session (default 20)

### Status & Info
- `/status` - Show current session status (model, tokens, queue, active processes)
- `/help` - Show available commands

### Agent Commands (for LLM tool access)
The LLM has access to a `sessions.search` tool so users can naturally ask:
- "Show me sessions about AI" → LLM calls tool, searches session titles/content
- "Switch to my conversation from yesterday" → LLM searches by date, presents options
- "What was I talking about last week?" → LLM searches historical sessions

Gateway intercepts commands, processes them, and sends appropriate response events back.

## Deliverables (v0.1.1 Checklist)

### Phase 1: Protocol & Gateway Core (3-4 days)

- [ ] **A1. Define protocol schemas**
  - [ ] Create `shared/protocol/protocol_v1.md` (human-readable spec)
  - [ ] Create `shared/protocol/request.schema.json`
  - [ ] Create `shared/protocol/response.schema.json`
  - [ ] Create `shared/protocol/event.schema.json`
  - [ ] Add Python types in `apps/gateway/protocol.py` (Pydantic models)
  - [ ] Document all event types: `message`, `queued`, `token`, `tool_call`, `tool_result`, `status`, `final`, `cancelled`, `error`

- [ ] **A2. Build gateway WebSocket handler**
  - [ ] Create `apps/gateway/main.py` with FastAPI + WebSocket endpoint
  - [ ] Implement connection handshake (first frame = connect)
  - [ ] Implement request/response matching (by request.id)
  - [ ] Add WebSocket ping/pong for connection health
  - [ ] Add basic error handling (invalid frames, connection drops)

- [ ] **A3. Multi-client connection management**
  - [ ] Create `apps/gateway/connections.py`
  - [ ] Track active connections: `session_id → [ws1, ws2, ...]`
  - [ ] Implement broadcast: send event to all clients in session
  - [ ] Handle client disconnect: remove from active connections
  - [ ] Echo user messages to all clients (with `fromSelf` flag)

- [ ] **A4. Request queue per session**
  - [ ] Create `apps/gateway/queue.py`
  - [ ] Maintain per-session request queue
  - [ ] Send immediate ack: `{"status": "queued"}` + `queued` event
  - [ ] Process queue sequentially per session
  - [ ] Support cancellation: `agent.cancel` method

- [ ] **A5. Implement method routing**
  - [ ] Create `apps/gateway/handlers.py`
  - [ ] Route `agent` → queue → runtime.process()
  - [ ] Route `agent.cancel` → cancel request
  - [ ] Route `sessions.list` → database query (sorted by last activity)
  - [ ] Route `sessions.new` → create session
  - [ ] Route `sessions.switch` → switch session + load history
  - [ ] Route `sessions.history` → load messages
  - [ ] Route `status` → gateway + session status

- [ ] **A6. Add command handling**
  - [ ] Create `apps/gateway/commands.py`
  - [ ] Parse `/new`, `/sessions`, `/session <n>`, `/history`, `/status`, `/help`
  - [ ] Generate formatted response events
  - [ ] Handle natural language session commands (route to LLM tool)

### Phase 2: Agent Runtime Refactor (3-4 days)

- [ ] **B1. Restructure folders**
  - [ ] Move `apps/server/agent/` → `apps/agent_runtime/runtime.py`
  - [ ] Move `apps/server/tools/` → `apps/agent_runtime/tools/`
  - [ ] Move `apps/server/db/` → `apps/agent_runtime/db/`
  - [ ] Rename `apps/server/db/threads.py` → `apps/agent_runtime/db/sessions.py`

- [ ] **B2. Database schema updates**
  - [ ] Rename table: `threads` → `sessions` (or map in code)
  - [ ] Add `agent_runs` table (id, session_id, status, request, timestamps, error)
  - [ ] Add `active_processes` table (id, run_id, tool_name, status, progress, timestamps)
  - [ ] Update queries to sort sessions by `updated_at` (last message time)
  - [ ] Add indexes for performance (sessions.updated_at, agent_runs.session_id)

- [ ] **B3. Refactor agent loop to generator**
  - [ ] Change `run_conversation()` to `async def process(request) -> AsyncIterator[Event]`
  - [ ] Yield `token` events during LLM streaming
  - [ ] Yield `tool_call` before tool execution
  - [ ] Yield `tool_result` after tool execution
  - [ ] Yield `status` events (thinking, executing_tool, streaming, done)
  - [ ] Yield `final` event with message ID and token count

- [ ] **B4. Process management**
  - [ ] Create `apps/agent_runtime/processes.py` - ProcessManager class
  - [ ] Register process when tool starts executing
  - [ ] Track process status, progress, start time
  - [ ] Support cancellation: set flag, tool checks periodically
  - [ ] Clean up completed/failed processes

- [ ] **B5. Add new tools**
  - [ ] **Session tools** (`apps/agent_runtime/tools/session_tools.py`):
    - [ ] `sessions.search` - LLM can search sessions by title/content/date
    - [ ] `sessions.list` - LLM can list recent sessions
    - [ ] `sessions.get` - LLM can retrieve specific session details
  - [ ] **Process tools** (`apps/agent_runtime/tools/process_tools.py`):
    - [ ] `process.list` - List running processes/tools
    - [ ] `process.status` - Get status of specific process
    - [ ] `process.cancel` - Cancel running process
    - [ ] `process.wait_time` - Estimate queue wait time
  - [ ] Keep existing tools working:
    - [ ] `filesystem.read`, `filesystem.write`, `filesystem.list`
    - [ ] `memory.get`, `memory.set`, `memory.list`, `memory.delete`

- [ ] **B6. Session persistence & activity tracking**
  - [ ] Update `sessions.updated_at` on every message
  - [ ] Persist messages immediately (user message, then assistant message)
  - [ ] Store tool calls and results in messages table
  - [ ] Audit logging captures all tool executions

### Phase 3: Web UI Migration (3-4 days)

- [ ] **C1. Add WebSocket client**
  - [ ] Create `apps/web/lib/websocket.ts`
  - [ ] Connect to `ws://localhost:3336/ws`
  - [ ] Send `connect` frame with version and clientType
  - [ ] Handle reconnection on drop (exponential backoff)
  - [ ] Implement ping/pong heartbeat

- [ ] **C2. Event handling & state management**
  - [ ] Handle `message` event (echo from this or other clients)
    - [ ] Display messages with indicator if from other client
  - [ ] Handle `queued` event (show queue position)
  - [ ] Handle `token` events (stream tokens into message)
  - [ ] Handle `tool_call` / `tool_result` (show tool execution)
  - [ ] Handle `status` events (show agent status)
  - [ ] Handle `final` event (mark message complete)
  - [ ] Handle `cancelled` event
  - [ ] Handle `error` event (display error to user)

- [ ] **C3. Rebuild chat interface**
  - [ ] Send messages via WebSocket (`method: "agent"`)
  - [ ] Show streaming tokens in real-time
  - [ ] Show tool execution with status indicator (🔧 Reading file...)
  - [ ] Support multi-client: show messages from other clients
  - [ ] Add cancel button for running requests

- [ ] **C4. Session/conversation management**
  - [ ] Load conversations via `sessions.list` (sorted by last activity)
  - [ ] Create new conversations via `sessions.new`
  - [ ] Switch conversations via `sessions.switch`
  - [ ] Display session list in sidebar
  - [ ] Highlight active session
  - [ ] Show "other client active" indicator if another client connected

- [ ] **C5. Commands support**
  - [ ] Send commands as regular messages (`/new`, `/sessions`, etc.)
  - [ ] Display formatted command responses
  - [ ] Special UI for `/sessions` response (clickable session list)

- [ ] **C6. Remove old HTTP API**
  - [ ] Remove axios calls to `/chat`
  - [ ] Remove HTTP `/threads/*` endpoints
  - [ ] Remove HTTP `/messages/*` endpoints
  - [ ] Keep settings endpoints temporarily (migrate in v0.1.2)
  - [ ] Keep memory endpoints temporarily (migrate in v0.1.2)

### Phase 4: CLI Client (2 days)

- [ ] **D1. Create CLI script**
  - [ ] Create `apps/cli/main.py`
  - [ ] Parse arguments: 
    - [ ] `agent-cli "message"` - send to current/new session
    - [ ] `agent-cli "message" --session <id>` - send to specific session
    - [ ] `agent-cli --new "message"` - create new session
    - [ ] `agent-cli --sessions` - list recent sessions
    - [ ] `agent-cli --history [count]` - show session history
  - [ ] Connect to WebSocket at `ws://localhost:3336/ws`
  - [ ] Send `connect` handshake

- [ ] **D2. Event handling & display**
  - [ ] Handle `message` event (echo, show if from other client)
  - [ ] Handle `queued` event (print queue position)
  - [ ] Print `token` events as they arrive (real-time streaming)
  - [ ] Show tool execution: "🔧 Executing filesystem.read..."
  - [ ] Print tool results (truncated if large)
  - [ ] Handle `error` events (print to stderr)
  - [ ] Handle Ctrl+C (send cancel request, then exit)

- [ ] **D3. Session persistence**
  - [ ] Save last session ID to `~/.agent_blob/cli_session`
  - [ ] Auto-resume if no --session provided
  - [ ] Support `--new` flag to create fresh session
  - [ ] Store session history in `~/.agent_blob/cli_history/`

- [ ] **D4. Interactive mode (optional)**
  - [ ] Support `agent-cli --interactive` for REPL mode
  - [ ] Read input, send message, display response, repeat
  - [ ] Support commands like `/sessions`, `/new`, `/history`

### Phase 5: Testing & Documentation (2-3 days)

- [ ] **E1. Protocol tests**
  - [ ] Test connection handshake (valid/invalid)
  - [ ] Test invalid JSON → error and close
  - [ ] Test missing `connect` → error and close
  - [ ] Test unknown method → error response
  - [ ] Test malformed request params → error response
  - [ ] Test sequence: connect → agent → events → final

- [ ] **E2. Multi-client tests**
  - [ ] Connect two clients to same session
  - [ ] Send message from client A
  - [ ] Verify client B receives `message` event (with `fromSelf: false`)
  - [ ] Verify both clients receive all token/tool/final events
  - [ ] Test client disconnect (other client continues)
  - [ ] Test session isolation (messages don't leak between sessions)

- [ ] **E3. Queue & cancellation tests**
  - [ ] Send two requests from same client quickly
  - [ ] Verify second request queued (receives `queued` event)
  - [ ] Verify requests process sequentially
  - [ ] Test cancellation of running request
  - [ ] Test cancellation of queued request
  - [ ] Verify `cancelled` event sent to all clients

- [ ] **E4. Session management tests**
  - [ ] Create new session
  - [ ] List sessions (verify sorted by last activity)
  - [ ] Switch sessions (verify history loaded)
  - [ ] Send message (verify session moves to top of list)
  - [ ] Test session search tool (LLM can find sessions)

- [ ] **E5. Process management tests**
  - [ ] Start long-running tool
  - [ ] Call `process.list` tool (verify tool listed)
  - [ ] Call `process.cancel` (verify tool stops)
  - [ ] Verify process removed from active list

- [ ] **E6. Error handling tests**
  - [ ] Test tool execution failure (verify `error` event, connection stays open)
  - [ ] Test LLM API error (verify `error` event with `retryable: false`)
  - [ ] Test invalid session ID (verify error response)
  - [ ] Test connection drop during streaming (client reconnects, history intact)

- [ ] **E7. Integration tests**
  - [ ] End-to-end: Web UI → Gateway → Agent → Response
  - [ ] End-to-end: CLI → Gateway → Agent → Response
  - [ ] Multi-client: Send from CLI, receive on Web UI
  - [ ] Commands: Test `/sessions`, `/new`, `/history` from all clients

- [ ] **E8. Documentation**
  - [ ] Write `docs/protocol_v1.md` (complete protocol specification)
  - [ ] Write `docs/multi_client.md` (how multi-client works)
  - [ ] Update `README.md` with new architecture diagram
  - [ ] Add CLI usage examples and commands
  - [ ] Document session management and navigation
  - [ ] Document process management tools

## Definition of Done (v0.1.1)

**Core Protocol:**
- [ ] Gateway accepts WebSocket connections and implements protocol v1
- [ ] All event types work: `message`, `queued`, `token`, `tool_call`, `tool_result`, `status`, `final`, `cancelled`, `error`
- [ ] All methods work: `agent`, `agent.cancel`, `sessions.list`, `sessions.new`, `sessions.switch`, `sessions.history`, `status`
- [ ] Connection handshake enforced (`connect` frame required)
- [ ] Error handling: connection stays open, errors sent as events

**Multi-Client Support:**
- [ ] Multiple clients can connect to same session simultaneously
- [ ] All clients receive all messages/events (full broadcast)
- [ ] User messages echoed to all clients with `fromSelf` flag
- [ ] Works across Web UI + CLI (can monitor session from either)

**Session Management:**
- [ ] Sessions use pure UUIDs (no client prefix)
- [ ] Sessions sorted by last activity (most recent first)
- [ ] Commands work: `/new`, `/sessions`, `/session <n>`, `/history`, `/status`
- [ ] LLM can search sessions via `sessions.search` tool
- [ ] Session switching loads recent message history

**Queue & Cancellation:**
- [ ] Per-session request queue (one request processed at a time)
- [ ] Immediate feedback: `queued` event with position
- [ ] Cancellation works: `agent.cancel` stops running/queued requests
- [ ] `cancelled` event sent to all connected clients

**Process Management:**
- [ ] Long-running tools tracked in `active_processes`
- [ ] LLM can call: `process.list`, `process.status`, `process.cancel`, `process.wait_time`
- [ ] Processes support cancellation (tools check cancellation flag)

**Clients:**
- [ ] Web UI connects via WebSocket and works end-to-end
- [ ] CLI connects via WebSocket and works end-to-end
- [ ] Both clients can send messages, receive streaming responses
- [ ] Both clients support all commands
- [ ] Old HTTP endpoints removed (except settings/memory, temporarily)

**Database:**
- [ ] Tables renamed: `threads` → `sessions`
- [ ] New tables: `agent_runs`, `active_processes`
- [ ] Sessions sorted by `updated_at` in queries
- [ ] Messages persisted immediately (user + assistant)
- [ ] Audit logging captures all tool executions

**Testing:**
- [ ] Protocol tests cover all methods and event types
- [ ] Multi-client tests verify broadcast behavior
- [ ] Queue and cancellation tests pass
- [ ] Session management tests pass
- [ ] Integration tests: Web UI + CLI working together

## Architecture Benefits

**Why This Design Wins:**

1. **Adding new clients is trivial**
   - Telegram bot? 50 lines: connect to WebSocket, forward messages, display events
   - WhatsApp? Same pattern
   - Discord bot? Same pattern
   - No need to understand agent logic, just protocol

2. **Multi-device support for free**
   - Start conversation on phone (Telegram)
   - Continue on laptop (Web UI)
   - Monitor from tablet (CLI)
   - All see same conversation in real-time

3. **LLM-driven session navigation**
   - No need to design complex UI for session switching
   - Just ask: "show me sessions about AI"
   - LLM searches, presents options, user picks
   - Works identically in Web UI, CLI, Telegram

4. **Process management built-in**
   - LLM can answer: "What's running?" "How long until my request?"
   - Can cancel: "Cancel that search"
   - User always has visibility into what agent is doing

5. **Python's AI ecosystem**
   - Easy to add: ChromaDB, FAISS, sentence-transformers
   - LangChain integration straightforward
   - Context compression, summarization tools available
   - Better than Node.js for AI/ML workloads

6. **Streaming everywhere**
   - Real-time token streaming to all clients
   - Tool execution progress visible
   - No more "loading..." spinners

7. **Testable & maintainable**
   - Protocol is well-defined (JSON schemas)
   - Runtime has no transport knowledge (pure functions)
   - Easy to test: mock WebSocket, send events, verify responses

## Non-Goals (Defer to Later)

- **Memory improvements**: Keep current pinned memory, no vector DB yet (v0.1.2+)
- **Tool progress events**: Tools are fast enough for now (v0.1.2+)
- **Telegram integration**: Design is ready, but implement in v0.1.2
- **WhatsApp integration**: After Telegram (v0.1.3+)
- **Authentication**: Local-only for now, no token auth (v0.2+)
- **Multi-agent**: Single agent for now (v0.2+)
- **Rate limiting**: Not needed for local-first (v0.2+ if remote access)
- **Persistence optimizations**: Current SQLite is fine (optimize later if needed)

## Migration Notes

1. **Breaking Change**: Web UI will need to reconnect to gateway (WebSocket instead of HTTP)
2. **Database**: Rename `threads` → `sessions`, add `agent_runs` and `active_processes` tables
3. **Backward Compatibility**: Old HTTP API will be removed (clean break, no migration path)
4. **Deployment**: Single process (`python -m apps.gateway.main`) replaces old server
5. **Data**: Existing messages/threads will be migrated (rename table, update references)
6. **Settings**: Keep old settings/memory HTTP endpoints temporarily (remove in v0.1.2)

## Summary

**v0.1.1 transforms Agent Blob from a Web-UI-first agent into a Clawdbot-style universal gateway.**

**Key changes:**
- ✅ Gateway IS the agent system (not just routing)
- ✅ Clients are dumb (just WebSocket connections)
- ✅ Multi-client support (full broadcast to all connected clients)
- ✅ Session navigation via LLM tools (no complex UI needed)
- ✅ Process management (LLM can monitor/cancel running tasks)
- ✅ Per-session queue (requests processed sequentially)
- ✅ Cancellation support (users can cancel requests)
- ✅ Universal protocol (same for Web/CLI/future Telegram/WhatsApp)

**What users get:**
- Start chat on Telegram, continue on laptop
- Ask "show me sessions about AI", LLM finds them
- Ask "what's taking so long?", LLM shows running processes
- Cancel long-running requests with `/cancel` or natural language
- Real-time streaming tokens in all clients
- Tool execution visible everywhere

**What developers get:**
- Adding new client = 50 lines of WebSocket code
- Protocol is well-defined and testable
- Runtime is transport-agnostic (easy to test)
- Python's AI ecosystem ready for memory/embeddings/RAG (v0.1.2+)

**Next steps after v0.1.1:**
- v0.1.2: Telegram integration, tool progress events, memory improvements
- v0.1.3: WhatsApp integration, vector DB for semantic search
- v0.2: Multi-agent routing, authentication, remote access

---

## Ready to Start?

**Phase 1** begins with defining the protocol schemas and building the WebSocket gateway core.

Run through the checklist in order, test as you go, and the architecture will emerge cleanly.

The key insight: **the gateway owns everything, clients are just thin adapters.**

Let's build it! 🚀

## Decisions Made

1. **Session ID format**: ✅ Pure UUIDs (no client prefix)
   - Gateway tracks which clients connected to which sessions
   - Navigate via commands: `/sessions`, `/session <n>`

2. **Multi-client behavior**: ✅ Full broadcast (Option 1)
   - All clients see all messages (including from other clients)
   - User messages echoed with `fromSelf` flag

3. **Concurrent requests**: ✅ Queue per session
   - Immediate ack with `queued` event showing position
   - Requests processed sequentially per session

4. **Cancellation**: ✅ `agent.cancel` method
   - Cancel running or queued requests
   - `cancelled` event broadcast to all clients

5. **Error handling**: ✅ Keep connection open
   - Send `error` events with `retryable` flag
   - Only close on: malformed JSON, invalid handshake, protocol mismatch

6. **Sequence numbers**: ✅ Add to events (optional, not enforced)
   - Reserve for future gap detection

7. **Tool progress**: ❌ Defer to v0.1.2+
   - Current tools fast enough

8. **Message persistence**: ✅ Save immediately
   - User message on receive
   - Assistant message after LLM response
   - Update with tool results

9. **Reconnection/resume**: ✅ No special handling in v0.1.1
   - Load history via `sessions.history` method
   - Sessions persist, clients just reconnect

10. **Database**: ✅ Rename threads → sessions
    - Add `agent_runs` and `active_processes` tables

11. **Backward compatibility**: ✅ Clean break
    - Remove old HTTP API (except settings/memory temporarily)

12. **Testing**: ✅ Write alongside implementation
    - Protocol tests in Phase 1
    - Integration tests in Phase 5

13. **Event buffering**: ✅ WebSocket handles buffering
    - Trust underlying WebSocket reliability
    - No application-level buffering needed

14. **CLI session storage**: ✅ `~/.agent_blob/`
    - Last session: `cli_session`
    - History: `cli_history/`

## Estimated Timeline

- **Phase 1** (Protocol & Gateway Core): 3-4 days
  - Protocol schemas, WebSocket handler, multi-client, queue, method routing
- **Phase 2** (Agent Runtime Refactor): 3-4 days
  - Database updates, generator refactor, process management, new tools
- **Phase 3** (Web UI Migration): 3-4 days
  - WebSocket client, event handling, multi-client UI, session management
- **Phase 4** (CLI Client): 2 days
  - CLI script, event display, session persistence, interactive mode
- **Phase 5** (Testing & Documentation): 2-3 days
  - Protocol tests, multi-client tests, integration tests, docs

**Total: 13-17 days**

**Daily breakdown (ideal):**
- Days 1-4: Phase 1 (gateway core + protocol)
- Days 5-8: Phase 2 (runtime + tools + DB)
- Days 9-12: Phase 3 (Web UI)
- Days 13-14: Phase 4 (CLI)
- Days 15-17: Phase 5 (testing + docs)

## New Tools for LLM (v0.1.1)

### Session Management Tools
Allow LLM to help users navigate sessions naturally:

```python
# sessions.search - Search sessions by content/title/date
{
  "name": "sessions.search",
  "description": "Search user's conversation sessions",
  "parameters": {
    "query": "string (optional) - search terms",
    "date_filter": "string (optional) - 'today', 'yesterday', 'this_week', 'last_week'",
    "limit": "number (optional) - max results (default 10)"
  }
}

# sessions.list - List recent sessions
{
  "name": "sessions.list",
  "description": "List user's recent conversation sessions",
  "parameters": {
    "limit": "number (optional) - max results (default 10)"
  }
}

# sessions.get - Get specific session details
{
  "name": "sessions.get",
  "description": "Get details and recent messages for a specific session",
  "parameters": {
    "session_id": "string - session UUID"
  }
}
```

**Use cases:**
- User: "Show me sessions about AI" → LLM calls `sessions.search(query="AI")`
- User: "What did we talk about yesterday?" → LLM calls `sessions.search(date_filter="yesterday")`
- User: "Switch to my conversation from last week about Python" → LLM searches, presents options

### Process Management Tools
Allow LLM to monitor and control running tasks:

```python
# process.list - List active processes
{
  "name": "process.list",
  "description": "List currently running agent processes and tools",
  "parameters": {}
}

# process.status - Get process status
{
  "name": "process.status",
  "description": "Get detailed status of a specific process",
  "parameters": {
    "process_id": "string - process UUID"
  }
}

# process.cancel - Cancel running process
{
  "name": "process.cancel",
  "description": "Cancel a running process or tool",
  "parameters": {
    "process_id": "string - process UUID"
  }
}

# process.wait_time - Estimate queue wait
{
  "name": "process.wait_time",
  "description": "Estimate wait time for queued requests",
  "parameters": {
    "session_id": "string (optional) - specific session or current"
  }
}
```

**Use cases:**
- User: "What's taking so long?" → LLM calls `process.list()`, sees long-running file read
- User: "How many processes are running?" → LLM calls `process.list()`, counts and reports
- User: "Cancel that search" → LLM calls `process.cancel(process_id)`
- User: "How long until my request is processed?" → LLM calls `process.wait_time()`

### Existing Tools (Unchanged)
- `filesystem.read`, `filesystem.write`, `filesystem.list`
- `memory.get`, `memory.set`, `memory.list`, `memory.delete`

## Success Criteria

✅ **Protocol works end-to-end:**
- Can send message from Web UI → Gateway → Agent → Stream back tokens
- Can send message from CLI → Gateway → Agent → Print tokens to terminal
- All event types work: message, queued, token, tool_call, tool_result, status, final, cancelled, error

✅ **Multi-client support:**
- Web UI and CLI can connect to SAME session simultaneously
- Both clients receive all messages/events (full broadcast)
- Sending message from one client → other client sees it immediately
- No duplicate agent logic across clients

✅ **Session management:**
- Commands work: `/new`, `/sessions`, `/session <n>`, `/history`, `/status`
- LLM can search sessions: "show me sessions about AI" works
- Sessions sorted by last activity (most recent first)
- Switching sessions loads history

✅ **Queue & cancellation:**
- Sending two messages quickly → second is queued (receives position)
- Cancellation works: can cancel running or queued requests
- Queue processing is sequential per session

✅ **Process management:**
- LLM can list running processes: "what's running?"
- LLM can cancel processes: "cancel that search"
- Long-running tools tracked in active_processes table

✅ **Tool execution:**
- Tool calls visible in both Web UI and CLI
- Tool results streamed back to all connected clients
- Existing tools (filesystem, memory) work unchanged

✅ **Database:**
- Tables renamed: threads → sessions
- Sessions sorted by updated_at
- agent_runs table tracks request status
- Messages persisted immediately
