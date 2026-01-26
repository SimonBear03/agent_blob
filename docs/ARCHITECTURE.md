# Agent Blob Architecture

## Core Principle: "Dumb Client" Design

All clients (CLI, TUI, Web UI, Telegram) are **just chatboxes** that:
1. Send text messages to the gateway
2. Receive and display text responses
3. Handle minimal local UI commands only (`/clear`, `/quit`)

The gateway handles **everything else**.

## Initial Connection Flow

```
┌─────────┐
│  Client │ (CLI/TUI/Telegram/Web)
└────┬────┘
     │ 1. Connect with preference ("auto", "new", or "continue")
     ▼
┌─────────────┐
│   Gateway   │
│             │
│   main.py   │◄─ Assigns session based on preference:
│             │   • "new": create new session
│             │   • "continue"/"auto": most recent (or create if none)
│             │◄─ Sends SESSION_CHANGED event (with last 4 messages)
│             │◄─ Sends welcome MESSAGE:
│             │   "👋 Welcome back! You're in Python Help (3 msgs from 2h ago).
│             │    Type /sessions to see other conversations."
└──────┬──────┘
       │ 3. Client displays messages + welcome
       ▼
┌─────────┐
│  Client │ Ready to chat!
└─────────┘
```

## Command Flow

### User types `/sessions`

```
┌─────────┐
│  Client │ (CLI/TUI/Telegram/Web)
└────┬────┘
     │ 1. User types "/sessions"
     │ 2. Client sends it as regular message
     ▼
┌─────────────┐
│   Gateway   │
│             │
│ commands.py │◄─ Recognizes /sessions command
│             │◄─ Queries database
│             │◄─ Formats text response:
│             │   "📋 Recent Sessions:
│             │    1. Chat A • 5 msgs • 2h ago
│             │    2. Chat B • 3 msgs • 1d ago
│             │    Type /switch <n> to switch"
└──────┬──────┘
       │ 3. Gateway sends as assistant message
       ▼
┌─────────┐
│  Client │ Displays the text
└─────────┘
```

### User types `/switch 2`

```
Client → Gateway → Gateway switches session → Sends SESSION_CHANGED event → Client updates UI
```

## Gateway Commands

All these commands are handled by `gateway/commands.py`:

| Command | What Gateway Does |
|---------|-------------------|
| `/help` | Returns formatted help text |
| `/new` | Creates session, switches client, returns confirmation |
| `/sessions` | Lists sessions from DB, formats as text |
| `/switch <n>` | Switches session, sends SESSION_CHANGED event |
| `/status` | Returns current session stats |

## Client Commands

Clients handle **only** these local UI commands:

| Command | What Client Does |
|---------|------------------|
| `/clear` | Clears local display (no gateway involved) |
| `/quit` | Exits the client app |

Everything else gets sent to the gateway.

## Benefits

✅ **Telegram client** = Just forward messages, display text responses
✅ **Web UI client** = Simple chatbox with no command logic
✅ **CLI/TUI client** = Simple chatbox with no command logic
✅ **Change /sessions format?** = Change gateway once, all clients benefit
✅ **Add new command?** = Add to gateway, all clients get it for free

## Example: Building a Telegram Client

```python
# Telegram bot - entire implementation!
class TelegramClient:
    def __init__(self):
        # Map telegram chat_id to gateway WebSocket connection
        self.connections = {}
    
    async def get_connection(self, chat_id):
        """Get or create connection for this Telegram user."""
        if chat_id not in self.connections:
            # First message from this user - connect to gateway
            conn = GatewayConnection("ws://gateway:3336/ws")
            await conn.connect(
                client_type="telegram",
                session_preference="auto"  # Gateway assigns session
            )
            self.connections[chat_id] = conn
        return self.connections[chat_id]

@bot.message_handler(func=lambda m: True)
async def handle_message(message):
    chat_id = message.chat.id
    gateway = await get_connection(chat_id)
    
    # Send user message to gateway
    await gateway.send_message(message.text)
    
    # Listen for events and display
    async for event in gateway.listen():
        if event.type == "token":
            # Stream tokens (show typing indicator)
            await bot.send_chat_action(chat_id, "typing")
        
        elif event.type == "message":
            # Display message (works for both regular messages AND command responses!)
            await bot.send_message(chat_id, event.payload["content"])
        
        elif event.type == "session_changed":
            # Session switched
            title = event.payload["title"]
            await bot.send_message(chat_id, f"📎 Switched to: {title}")
```

**Key points for Telegram:**
- Each Telegram user gets their own gateway connection
- Gateway remembers which session each connection is in
- User can type `/sessions`, `/switch 2`, etc. - gateway handles it
- Client just displays text responses - no special handling needed!

That's it! No command parsing, no session management, no UI logic.

## Architecture Diagram

```
┌─────────────────────────────────────────────────┐
│                    Clients                      │
│  (Just chatboxes - send text, display text)    │
├─────────────────────────────────────────────────┤
│  CLI/TUI  │  Web UI  │  Telegram  │  Future... │
└─────┬───────────┬───────────┬──────────────┬───┘
      │           │           │              │
      └───────────┴───────────┴──────────────┘
                      │
                 WebSocket
                      │
      ┌───────────────▼──────────────────┐
      │         Gateway                  │
      │  • Handles all commands          │
      │  • Manages all sessions          │
      │  • Routes to agent runtime       │
      │  • Formats all responses         │
      └───────────────┬──────────────────┘
                      │
      ┌───────────────▼──────────────────┐
      │      Agent Runtime               │
      │  • Calls LLM                     │
      │  • Executes tools                │
      │  • Manages processes             │
      └───────────────┬──────────────────┘
                      │
      ┌───────────────▼──────────────────┐
      │         Database                 │
      │  • Sessions                      │
      │  • Messages                      │
      │  • Agent runs                    │
      └──────────────────────────────────┘
```

## Key Files

- `gateway/commands.py` - All command handling and formatting
- `gateway/handlers.py` - Routes commands vs. agent messages
- `clients/cli/cli_tui.py` - Minimal TUI chatbox
- `clients/cli/cli.py` - Minimal simple CLI chatbox

## Testing the Architecture

1. **Start gateway**: `python scripts/run_gateway.py`
2. **Start CLI**: `python run_cli.py`
3. **Type `/sessions`** - Should see formatted list
4. **Type `/switch 2`** - Should switch and show context
5. **Type `/help`** - Should see all gateway commands

All responses come from the gateway, not the client!
