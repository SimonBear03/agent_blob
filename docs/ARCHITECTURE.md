# Agent Blob Architecture

## Core Principle: "Dumb Client" Design

All clients (CLI, TUI, Web UI, Telegram) are **just chatboxes** that:
1. Send text messages to the gateway
2. Receive and display text responses
3. Handle minimal local UI commands only (`/clear`, `/quit`)

The gateway handles **everything else**.

## Gateway Features

The gateway (`gateway/`) provides:
- **Multi-client connection management** - Track multiple clients per session
- **Request queueing** - Per-session FIFO queue with cancellation
- **Session management** - Create, list, search, and switch sessions
- **Command processing** - Built-in commands like `/sessions`, `/switch`, `/help`
- **History limiting** - Configurable message history per client type
- **Broadcasting** - Smart event routing to all session clients
- **Stats tracking** - Model info, token usage, message counts

## Initial Connection Flow

```
┌─────────┐
│  Client │ (CLI/TUI/Telegram/Web)
└────┬────┘
     │ 1. Connect with preference ("auto", "new", or "continue")
     │    + optional historyLimit (default: 20 for most, 4 for Telegram)
     ▼
┌─────────────┐
│   Gateway   │
│             │
│   main.py   │◄─ Assigns session based on preference:
│             │   • "new": create new session
│             │   • "continue"/"auto": most recent (or create if none)
│             │◄─ Loads messages based on historyLimit
│             │◄─ Sends SESSION_CHANGED event with:
│             │   • Session info (id, title, timestamps)
│             │   • Message history (limited by historyLimit)
│             │   • Stats (model, tokens, message count)
│             │◄─ Sends contextual welcome MESSAGE:
│             │   • New user: "👋 Welcome to Agent Blob! This is your first..."
│             │   • New session: "✨ New conversation started!"
│             │   • Existing: "👋 Welcome back! You're in Python Help (42 msgs from 2h ago)."
└──────┬──────┘
       │ 3. Client displays messages + welcome
       ▼
┌─────────┐
│  Client │ Ready to chat!
└─────────┘
```

### Connection Parameters

- **clientType**: String identifying client ("tui", "cli", "web", "telegram")
- **sessionPreference**: "auto" (default), "new", or "continue"
- **historyLimit**: Max messages to load (default: 20 for TUI/CLI/Web, 4 for Telegram)
  - Set to 0 or negative to disable history loading

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
| `/help` | Returns formatted help text with all available commands |
| `/new` | Creates new session, switches client to it, sends SESSION_CHANGED event |
| `/sessions` | Lists recent sessions (page 1, 9 per page) with title, message count, time |
| `/sessions <n>` | Shows page N of sessions |
| `/sessions next` / `/sessions prev` | Paginate through sessions (tracks state per client) |
| `/sessions search <keyword>` | Search sessions by title/content |
| `/switch <n>` | Switches to session number N (from list), sends SESSION_CHANGED event |
| `/switch <uuid>` | Switches to session by UUID |
| `/status` | Returns current session stats (ID, message count, model, queue status) |
| `/history [count]` | Show message history (default: 20) |

### Session Command Features

The `/sessions` command family includes:
- **Pagination**: 9 sessions per page with `/sessions next` and `/sessions prev`
- **Search**: `/sessions search python` finds all sessions mentioning "python"
- **State tracking**: Gateway remembers last page/query per client
- **Current marker**: Shows which session is currently active
- **Rich formatting**: Message counts, relative timestamps (5m ago, 2h ago, 3d ago)

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
│  TUI      │  CLI  │  Web UI  │  Telegram  │... │
│  (Rich)   │(REPL) │ (React)  │  (Bot)     │    │
└─────┬───────────┬──────┬───────────┬───────────┘
      │           │      │           │
      └───────────┴──────┴───────────┘
                      │
              WebSocket (Protocol v1)
                      │
      ┌───────────────▼──────────────────┐
      │         Gateway                  │
      │  • Connection manager            │
      │  • Command processing            │
      │  • Session management            │
      │  • Request queue (per-session)   │
      │  • Multi-client broadcasting     │
      │  • History limiting              │
      └───────────────┬──────────────────┘
                      │
              Async Event Stream
                      │
      ┌───────────────▼──────────────────┐
      │      Agent Runtime               │
      │  • Event generator (async)       │
      │  • Tool execution                │
      │  • Process tracking              │
      │  • LLM streaming (OpenAI)        │
      └───────────────┬──────────────────┘
                      │
      ┌───────────────┴──────────────────┐
      │                                  │
┌─────▼──────┐              ┌───────────▼────────┐
│  Database  │              │   OpenAI API       │
│  (SQLite)  │              │   (GPT-4o)         │
│            │              │                    │
│ • sessions │              │ • Chat completion  │
│ • messages │              │ • Tool calling     │
│ • memory   │              │ • Streaming        │
│ • audit    │              │                    │
└────────────┘              └────────────────────┘
```

## Connection Manager

The `gateway/connections.py` module manages all client connections:

### Features
- **Multi-client tracking**: Maps WebSocket → ClientInfo with session, type, limits
- **Session switching**: Clients can switch between sessions dynamically
- **History limits**: Per-client message history limits (configurable)
- **Pagination state**: Tracks `/sessions` page/query per client
- **Smart broadcasting**: Routes events to all session clients with proper formatting

### Client Info Tracking
```python
@dataclass
class ClientInfo:
    websocket: WebSocket
    client_type: str           # "tui", "cli", "web", "telegram"
    session_id: str            # Current session
    history_limit: Optional[int]  # Message history limit
    sessions_page: int         # Last /sessions page viewed
    sessions_query: Optional[str]  # Last /sessions search query
```

### Default History Limits
- TUI: 20 messages
- CLI: 20 messages
- Web: 20 messages
- Telegram: 4 messages (to avoid overwhelming mobile users)

### Broadcasting Logic
When broadcasting events to a session:
1. Find all clients connected to that session
2. Format event based on client type:
   - **Telegram**: Prefix user messages from other clients with "🖥️ [From Web]"
   - **Web/CLI/TUI**: Add `fromSelf` flag to user messages
3. Send formatted event to each client
4. Handle disconnected clients gracefully

## Key Files

### Gateway Core
- `gateway/main.py` - FastAPI app, WebSocket endpoint, connection lifecycle
- `gateway/protocol.py` - Pydantic models for requests, responses, events
- `gateway/connections.py` - Multi-client connection manager
- `gateway/handlers.py` - Routes requests to appropriate handlers
- `gateway/commands.py` - Command processing and formatting
- `gateway/queue.py` - Per-session request queue with cancellation

### Clients
- `clients/cli/cli_tui.py` - Modern TUI with split-screen layout
- `clients/cli/tui.py` - Rich-based UI components (deprecated/experimental)
- `clients/cli/ui.py` - Shared UI utilities
- `clients/cli/connection.py` - WebSocket connection wrapper

### Runtime & Tools
- `runtime/runtime.py` - Agent event generator
- `runtime/processes.py` - Process manager
- `runtime/db/` - Database layer (sessions, messages, memory)
- `runtime/tools/` - Tool implementations

## Testing the Architecture

1. **Start gateway**: `python scripts/run_gateway.py`
2. **Start TUI**: `python run_cli.py` (launches TUI by default)
3. **Test commands**:
   - Type `/help` - See all gateway commands
   - Type `/sessions` - See formatted session list
   - Type `/sessions search python` - Search sessions
   - Type `/switch 2` - Switch to session #2
   - Type `/new` - Create new session
   - Type `/status` - See current session stats
4. **Test multi-client**: Open another terminal and run `python run_cli.py` again
   - Messages from one client appear in the other in real-time
   - Each client can be in a different session

All responses come from the gateway, not the client!

## TUI Client Features

The default TUI client (`clients/cli/cli_tui.py`) provides:

### Display Features
- **Split-screen layout**: Persistent chat history at top, input at bottom
- **Real-time streaming**: Tokens appear as they arrive with cursor indicator (▊)
- **Status bar**: Connection state, message count, model, context usage
- **Context tracking**: Visual indicator when approaching token limit
  - Green: < 60% used
  - Yellow: 60-85% used
  - Red: > 85% used (approaching limit)

### Session Statistics
The TUI displays real-time stats from gateway:
- **Model name**: e.g., "gpt-4o"
- **Token usage**: "12.3K/128K (10%)"
- **Message count**: Total messages in session
- **Status**: Connected, Thinking, Streaming, Using tools, etc.

### Multi-client Support
- Messages from other clients show with indicator: "📱 [From another client]"
- System messages (gateway commands) appear in red
- User messages in cyan, assistant in green

### Keyboard Shortcuts
- **Enter**: Send message
- **Ctrl+J**: New line (multi-line input)
- **Ctrl+C**: Cancel current request (or exit if idle)
- **Up/Down**: Navigate command history
