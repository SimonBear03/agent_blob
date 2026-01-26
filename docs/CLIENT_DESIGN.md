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
# 1. Connect to gateway with preference
connection = await GatewayConnection.connect(
    client_type="telegram",  # or "cli", "tui", "web", etc.
    session_preference="auto"  # "auto", "new", or "continue"
)

# 2. Gateway automatically:
#    - Assigns a session
#    - Sends SESSION_CHANGED event (with last 4 messages)
#    - Sends welcome MESSAGE

# 3. Display everything received
for event in connection.listen():
    if event.type == "message":
        display(event.payload["content"])
    elif event.type == "token":
        append_token(event.payload["content"])
    elif event.type == "session_changed":
        update_session_ui(event.payload)

# 4. User starts chatting
```

## Session Preferences

| Preference | Behavior |
|------------|----------|
| `"auto"` | Most recent session, or create new if none exist |
| `"continue"` | Most recent session, or create new if none exist (same as auto) |
| `"new"` | Always create a new session |

## Client Examples

### CLI/TUI (Short-lived)

**Behavior:**
- User runs `python run_cli.py`
- Connects with `session_preference="auto"` (or based on flags)
- Gateway shows welcome message: "Welcome back! You're in Python Help..."
- User chats
- User quits

**Flags:**
- `--continue`: Use `session_preference="continue"`
- `--new`: Use `session_preference="new"`
- Default: Use `session_preference="auto"`

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

### Local Commands

Clients MAY handle these locally (no gateway involvement):

| Command | Client Action |
|---------|---------------|
| `/clear` | Clear chat display |
| `/quit` | Exit client application |

## Events from Gateway

### MESSAGE Event
```json
{
  "type": "event",
  "event": "message",
  "payload": {
    "role": "system",
    "content": "👋 Welcome back! You're in **Python Help**...",
    "messageId": "msg_abc123",
    "timestamp": "2026-01-26T12:00:00Z"
  }
}
```

**Roles:**
- `"system"` - Gateway messages (welcome, command responses)
- `"assistant"` - LLM responses
- `"user"` - User messages (echoed or from other clients)

**Client action:** Display based on role (subject on first line, content on next)
```
System:
Welcome back! You're in **Python Help**...