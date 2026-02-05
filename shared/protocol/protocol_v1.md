# Agent Blob WebSocket Protocol v1

## Overview

Agent Blob uses a WebSocket-based protocol for all client-gateway communication. This protocol supports:
- Multiple clients connecting to the same session simultaneously
- Real-time event streaming (tokens, tool execution, status updates)
- Per-session request queuing
- Session management and navigation
- Process management and cancellation

## Connection Flow

### 1. Connect (Handshake)

The first frame MUST be a `connect` request:

```json
{
  "type": "req",
  "id": "connect-1",
  "method": "connect",
  "params": {
    "version": "1",
    "clientType": "web" | "cli"
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
    "supportedMethods": ["agent", "agent.cancel", "sessions.list", "sessions.new", "sessions.switch", "sessions.history", "status"]
  }
}
```

**Error cases:**
- Invalid JSON → Close connection
- First frame not `connect` → Send error and close
- Unsupported protocol version → Send error response

### 2. Request/Response Pattern

All subsequent messages follow the request/response pattern:

**Request:**
```json
{
  "type": "req",
  "id": "unique-client-id",
  "method": "method-name",
  "params": { ... }
}
```

**Response:**
```json
{
  "type": "res",
  "id": "matches-request-id",
  "ok": true | false,
  "payload": { ... } | null,
  "error": "error message" | null
}
```

### 3. Event Streaming

Events are pushed from gateway to clients:

```json
{
  "type": "event",
  "event": "event-type",
  "payload": { ... },
  "seq": 42  // optional sequence number
}
```

## Methods

### agent - Send message to agent

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

**Response:**
```json
{
  "type": "res",
  "id": "req-1",
  "ok": true,
  "payload": {
    "runId": "run_abc123",
    "status": "accepted" | "queued"
  }
}
```

**Events emitted:**
- `message` - User message echo (broadcast to all clients)
- `queued` - If request queued (immediate feedback)
- `token` - Streaming text tokens
- `tool_call` - Agent calling a tool
- `tool_result` - Tool execution result
- `status` - Agent status update
- `final` - Agent finished

### agent.cancel - Cancel running request

**Request:**
```json
{
  "type": "req",
  "id": "req-2",
  "method": "agent.cancel",
  "params": {
    "runId": "run_abc123"
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

**Events emitted:**
- `cancelled` - When cancellation completes

### sessions.list - List sessions

**Request:**
```json
{
  "type": "req",
  "id": "req-3",
  "method": "sessions.list",
  "params": {
    "limit": 10,
    "offset": 0
  }
}
```

**Response:**
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
      }
    ],
    "total": 25
  }
}
```

### sessions.new - Create new session

**Request:**
```json
{
  "type": "req",
  "id": "req-4",
  "method": "sessions.new",
  "params": {
    "title": "New conversation"
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

### sessions.switch - Switch to different session

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

**Response:**
```json
{
  "type": "res",
  "id": "req-5",
  "ok": true,
  "payload": {
    "sessionId": "550e8400-e29b-41d4-a906-446655440000",
    "title": "AI architecture discussion",
    "recentMessages": [...]
  }
}
```

### sessions.history - Get session history

**Request:**
```json
{
  "type": "req",
  "id": "req-6",
  "method": "sessions.history",
  "params": {
    "sessionId": "550e8400-e29b-41d4-a906-446655440000",
    "limit": 20,
    "before": "msg_xyz"
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
    "messages": [...],
    "hasMore": true
  }
}
```

### status - Get gateway status

**Request:**
```json
{
  "type": "req",
  "id": "req-7",
  "method": "status",
  "params": {
    "sessionId": "550e8400-e29b-41d4-a906-446655440000"
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
    "session": {
      "id": "550e8400-e29b-41d4-a906-446655440000",
      "messageCount": 42,
      "queuedRequests": 0,
      "activeRun": null
    }
  }
}
```

## Event Types

### message - User message echo

Broadcast to all clients when any client sends a message:

```json
{
  "type": "event",
  "event": "message",
  "payload": {
    "role": "user",
    "content": "Hello",
    "messageId": "msg_abc123",
    "timestamp": "2026-01-26T10:30:00Z",
    "fromSelf": true
  }
}
```

**Client-specific formatting:**
- Web/CLI: `fromSelf` flag (true if this client sent it)
- Clients receive `fromSelf` flag on user messages to indicate sender.

### queued - Request queued

```json
{
  "type": "event",
  "event": "queued",
  "payload": {
    "requestId": "req_xyz",
    "position": 2,
    "message": "Message queued (position 2)"
  }
}
```

### token - Streaming text token

```json
{
  "type": "event",
  "event": "token",
  "payload": {
    "runId": "run_abc123",
    "content": "Hello",
    "delta": true
  },
  "seq": 42
}
```

### tool_call - Agent calling a tool

```json
{
  "type": "event",
  "event": "tool_call",
  "payload": {
    "runId": "run_abc123",
    "toolName": "filesystem.read",
    "arguments": {"path": "config.json"}
  }
}
```

### tool_result - Tool execution result

```json
{
  "type": "event",
  "event": "tool_result",
  "payload": {
    "runId": "run_abc123",
    "toolName": "filesystem.read",
    "result": {"success": true, "content": "..."}
  }
}
```

### status - Agent status update

```json
{
  "type": "event",
  "event": "status",
  "payload": {
    "runId": "run_abc123",
    "status": "thinking" | "executing_tool" | "streaming" | "done"
  }
}
```

### final - Agent finished

```json
{
  "type": "event",
  "event": "final",
  "payload": {
    "runId": "run_abc123",
    "messageId": "msg_xyz",
    "totalTokens": 1234
  }
}
```

### cancelled - Request cancelled

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

### error - Error occurred

```json
{
  "type": "event",
  "event": "error",
  "payload": {
    "runId": "run_abc123",
    "message": "Tool execution failed",
    "retryable": false,
    "errorCode": "TOOL_EXECUTION_FAILED"
  }
}
```

## Multi-Client Behavior

### Broadcast Rules

1. **User messages** - Broadcast to all clients in session
   - Sender receives: `fromSelf: true`
   - Others receive: `fromSelf: false`

2. **Agent events** - Broadcast identically to all clients
   - Tokens, tool calls, status, final - no client-specific formatting

3. **Error events** - Broadcast to all clients
   - Connection stays open unless critical error

### Session Isolation

- Events only broadcast within the same session
- Clients in different sessions never see each other's events
- One client can be in multiple sessions (different WebSocket connections)

## Error Handling

### Connection Errors (Close Connection)

- Malformed JSON
- First frame not `connect`
- Protocol version mismatch

### Request Errors (Send Error Response)

- Unknown method
- Invalid parameters
- Session not found
- Permission denied

### Runtime Errors (Send Error Event)

- Tool execution failed
- LLM API error
- Unrecoverable agent error

Connection stays open for error events - client decides whether to retry or close.

## Versioning

Protocol version is specified in the `connect` request. Current version: `"1"`.

Future versions may:
- Add new methods (backward compatible)
- Add new event types (backward compatible)
- Add new optional parameters (backward compatible)
- Change required parameters (breaking change, requires new version)

Clients should check `gatewayVersion` in connect response and handle accordingly.
