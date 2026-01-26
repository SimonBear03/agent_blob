# Client Design Guide

## Pure Dumb Client Philosophy

All Agent Blob clients follow one simple rule: **clients are just chatboxes**.

- Send text messages to gateway
- Display text messages from gateway
- Handle minimal local UI commands only

**NO:**
- ❌ API calls to list sessions
- ❌ Command parsing logic
- ❌ Session management
- ❌ Message formatting
- ❌ Business logic

**YES:**
- ✅ Display what gateway sends
- ✅ Send what user types
- ✅ Handle local UI commands (`/clear`, `/quit`)

## Connection Flow

### For All Clients

```python
# 1. Connect to gateway with preference and history limit
connection = await GatewayConnection.connect(
    client_type="tui",           # "tui", "cli", "web", "telegram"
    session_preference="auto",   # "auto", "new", or "continue"
    history_limit=20             # Optional: defaults per client type
)

# 2. Gateway automatically:
#    - Assigns a session based on preference
#    - Loads message history (limited by historyLimit)
#    - Sends SESSION_CHANGED event with:
#      • Session info (id, title, timestamps)
#      • Message history array
#      • Stats (model, tokens used/limit, message count)
#    - Sends contextual welcome MESSAGE

# 3. Display everything received
async for event in connection.listen():
    if event.type == "message":
        role = event.payload["role"]
        content = event.payload["content"]
        from_self = event.payload.get("fromSelf", False)
        display_message(role, content, from_self)
    
    elif event.type == "token":
        append_token(event.payload["content"])
    
    elif event.type == "session_changed":
        # User switched sessions (via /switch or /new)
        session_id = event.payload["sessionId"]
        title = event.payload["title"]
        messages = event.payload["messages"]
        stats = event.payload["stats"]
        update_session_ui(session_id, title, messages, stats)
    
    elif event.type == "status":
        # Agent status updates (thinking, executing_tool, streaming)
        status = event.payload["status"]
        update_status_bar(status)
    
    elif event.type == "final":
        # Request completed
        finish_streaming()

# 4. User starts chatting
```

## Connection Parameters

### Session Preferences

| Preference | Behavior |
|------------|----------|
| `"auto"` | Most recent session, or create new if none exist (default) |
| `"continue"` | Most recent session, or create new if none exist (same as auto) |
| `"new"` | Always create a new session |

### History Limit

Control how many messages are loaded on connection:

| Client Type | Default Limit | Rationale |
|-------------|---------------|-----------|
| TUI | 20 | Good balance for terminal display |
| CLI | 20 | Good balance for terminal display |
| Web | 20 | Typical chat interface |
| Telegram | 4 | Mobile-friendly, limited screen space |

**Override**: Pass `historyLimit` parameter in connect request
**Disable**: Set `historyLimit` to 0 or negative to disable history loading

## Client Examples

### TUI (Default, Recommended)

Modern split-screen interface with persistent history, inspired by Codex/Claude Code.

**Behavior:**
- User runs `python run_cli.py` (TUI is default)
- Connects with `session_preference="auto"` (or based on flags)
- Gateway sends SESSION_CHANGED with message history (20 messages)
- Gateway sends contextual welcome message
- User sees full chat interface with status bar
- User chats with real-time streaming
- User quits with `/quit` or Ctrl+C

**Features:**
- Split-screen layout (chat area + status bar + input)
- Real-time token streaming with cursor indicator (▊)
- Status indicators (Connected, Thinking, Using tools, Streaming)
- Context usage tracking with color coding (green/yellow/red)
- Multi-line input (Ctrl+J for newline)
- Command history (Up/Down arrows)
- Multi-client message indicators

**Flags:**
- `--continue`: Use `session_preference="continue"`
- `--new`: Use `session_preference="new"`
- `--uri ws://...`: Custom gateway URL
- `--debug`: Enable debug logging

### CLI (Simple, Legacy)

Traditional REPL-style interface for simple usage or scripting.

**Behavior:**
- User runs `python run_cli.py --simple`
- Linear output (messages scroll up)
- Same gateway connection as TUI
- Simpler display without live updates

**When to use:**
- Slower terminals
- Scripting/automation
- Environments where TUI doesn't render well
- Personal preference

### Telegram (Persistent)

**Behavior:**
- Bot is always running
- First message from user → Connect with `session_preference="auto"`
- Gateway assigns/creates session for this user
- Store connection per `telegram_user_id`
- Subsequent messages → Use existing connection
- User can type `/sessions`, `/switch`, etc. - gateway handles it

**Session Persistence:**
Each Telegram user gets their own persistent connection. When they come back, the connection is already tied to their last session.

### Web UI (Session-based)

**Behavior:**
- User opens web app
- Check localStorage for `preferred_session_id`
- If found: Connect with `session_preference="continue"` and send session ID in future enhancement
- If not: Connect with `session_preference="auto"`
- Gateway assigns session
- Store `session_id` in localStorage
- User refreshes → Use stored session

## Command Handling

### Gateway Commands

These are sent as regular messages and gateway responds with text:

| Command | Gateway Response |
|---------|------------------|
| `/help` | Formatted help text |
| `/sessions` | Formatted session list |
| `/switch 2` | Switches session, sends SESSION_CHANGED event |
| `/new` | Creates session, sends SESSION_CHANGED event |
| `/status` | Current session stats |

**Client just displays the response** - no special handling!

**Command Response Format:**
All command responses come as MESSAGE events with `role: "system"`:
- Markdown formatting supported
- Multi-line responses common
- Pagination state tracked by gateway (not client)

### Local Commands

Clients MAY handle these locally (no gateway involvement):

| Command | Client Action |
|---------|---------------|
| `/clear` | Clear chat display |
| `/quit` | Exit client application |

## Events from Gateway

### SESSION_CHANGED Event
```json
{
  "type": "event",
  "event": "session_changed",
  "payload": {
    "sessionId": "abc123...",
    "title": "Python Help",
    "createdAt": "2026-01-26T10:00:00Z",
    "updatedAt": "2026-01-26T12:00:00Z",
    "messages": [
      {
        "id": "msg_1",
        "role": "user",
        "content": "Hello",
        "timestamp": "2026-01-26T10:05:00Z"
      },
      {
        "id": "msg_2",
        "role": "assistant",
        "content": "Hi! How can I help?",
        "timestamp": "2026-01-26T10:05:02Z"
      }
    ],
    "stats": {
      "messageCount": 42,
      "modelName": "gpt-4o",
      "tokensUsed": 12345,
      "tokensLimit": 128000
    },
    "message": "✓ Switched to: Python Help"  // Optional status message
  }
}
```

**When sent:**
- On initial connection (after connect request)
- When user switches sessions (`/switch` command)
- When user creates new session (`/new` command)

**Client action:**
1. Update session UI (title, ID)
2. Clear current messages
3. Load message history from payload
4. Update stats display (model, tokens, count)
5. Show status message if provided

### MESSAGE Event
```json
{
  "type": "event",
  "event": "message",
  "payload": {
    "role": "system",
    "content": "👋 Welcome back! You're in **Python Help** (42 messages from 2h ago).\n\nType `/sessions` to see other conversations or `/new` to start fresh.",
    "messageId": "msg_abc123",
    "timestamp": "2026-01-26T12:00:00Z",
    "fromSelf": true  // For user messages only
  }
}
```

**Roles:**
- `"system"` - Gateway messages (welcome, command responses)
- `"assistant"` - LLM responses
- `"user"` - User messages (echoed or from other clients)

**fromSelf flag** (user messages only):
- `true` - Message sent by this client
- `false` - Message from another client in the same session
- Telegram clients receive prefixed content instead: "🖥️ [From Web] Message here"

**Client action:** Display based on role
```
System:
👋 Welcome back! You're in Python Help...