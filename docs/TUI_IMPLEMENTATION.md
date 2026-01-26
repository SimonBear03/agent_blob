# TUI Implementation Guide

This guide explains how the TUI client is implemented, useful for building similar clients or understanding the architecture.

## Overview

The TUI (`clients/cli/cli_tui.py`) is a full-featured terminal client with:
- Split-screen layout (chat area, status bar, input)
- Real-time streaming display
- Session management
- Multi-client support

## ⚠️ Core Principle: "Dumb Client"

**The TUI is a pure "dumb client"** - it follows the golden rule:

> **Clients are just chatboxes. Send text, display text. That's it.**

### What the TUI Does NOT Do:
- ❌ Parse commands (no checking if message starts with `/`)
- ❌ Make API calls (no session list endpoints)
- ❌ Format command responses (no "building" session lists)
- ❌ Manage sessions (no session state beyond current ID)
- ❌ Implement command logic (no business logic)

### What the TUI DOES Do:
- ✅ Send user input to gateway (all text, including `/commands`)
- ✅ Display messages from gateway (system, user, assistant)
- ✅ Show streaming tokens in real-time
- ✅ Update UI state from gateway events
- ✅ Handle 2 local commands: `/quit` and Ctrl+C (UI-only)

### Why This Matters:
When you type `/sessions`, the TUI:
1. Sends `"agent"` request with `message: "/sessions"` to gateway
2. Waits for response
3. Gateway recognizes command, queries DB, formats text
4. Gateway sends `MESSAGE` event with formatted text
5. TUI displays it - **no idea it was a command!**

This means:
- Building a Telegram client? Same pattern, < 200 lines
- Adding `/sessions search`? Change gateway only, all clients get it
- Changing session list format? Update gateway, done

**If you're tempted to add command parsing to your client - STOP! That logic belongs in the gateway.**

## Architecture

```
┌─────────────────────────────────────┐
│   AgentBlobTUI (Main App)           │
│   - Connection management           │
│   - Event handlers                  │
│   - Chat loop                       │
└─────────────┬───────────────────────┘
              │
    ┌─────────┴──────────┐
    │                    │
┌───▼────────────┐  ┌───▼──────────────────┐
│ SimpleTUI      │  │ GatewayConnection    │
│ - UI state     │  │ - WebSocket client   │
│ - Rendering    │  │ - Event callbacks    │
│ - Display      │  │ - Request sending    │
└────────────────┘  └──────────────────────┘
```

## Key Components

### 1. SimpleTUI (UI Layer)

Manages the visual display and state:

```python
class SimpleTUI:
    def __init__(self):
        self.session_id = None
        self.session_title = "New conversation"
        self.messages = []  # List of message dicts
        self.status = "Connected"
        self.status_color = "green"
        
        # Stats from gateway
        self.model_name = "gpt-4o"
        self.tokens_used = 0
        self.tokens_limit = 128000
        self.message_count = 0
    
    def render_full(self):
        """Clears screen and redraws entire UI."""
        self.clear_screen()
        # Render header, messages, status bar
    
    def add_user_message(self, content: str):
        """Add user message and re-render."""
        self.messages.append({
            "role": "user",
            "content": content,
            "streaming": False
        })
        self.render_full()
    
    def start_assistant_message(self):
        """Start streaming assistant response."""
        self.messages.append({
            "role": "assistant",
            "content": "",
            "streaming": True
        })
        self.render_full()
    
    def add_token(self, token: str):
        """Append token to current message."""
        if self.messages and self.messages[-1]["role"] == "assistant":
            self.messages[-1]["content"] += token
            # Only re-render every 10 chars to reduce flicker
            if len(self.messages[-1]["content"]) % 10 == 0:
                self.render_full()
    
    def finish_assistant_message(self):
        """Mark streaming as complete."""
        if self.messages:
            self.messages[-1]["streaming"] = False
        self.status = "Connected"
        self.render_full()
```

**Design decisions:**
- Full screen clear/redraw on each update (simpler than delta updates)
- Only re-render every 10 characters during streaming (reduces flicker)
- Messages stored as simple dicts (role, content, streaming flag)
- Stats tracked from SESSION_CHANGED events

### 2. AgentBlobTUI (Application Layer)

Manages connection and event handling:

```python
class AgentBlobTUI:
    def __init__(self, uri: str, auto_mode: Optional[str] = None):
        self.uri = uri
        self.auto_mode = auto_mode  # "new", "continue", or None
        self.connection = GatewayConnection(uri)
        self.tui = SimpleTUI()
        self.current_run_id = None
        self.streaming = False
        
        # Prompt session with history
        history_file = Path.home() / ".agent_blob_history"
        self.prompt_session = PromptSession(
            history=FileHistory(str(history_file)),
            multiline=False,
            enable_history_search=True
        )
    
    async def run(self):
        """Main application loop."""
        # 1. Connect to gateway
        session_pref = self._get_session_preference()
        initial_session = await self.connection.connect(
            client_type="tui",
            session_preference=session_pref,
            history_limit=20
        )
        
        # 2. Setup event handlers
        self.connection.on_session_changed = self._handle_session_changed
        self.connection.on_message = self._handle_message
        self.connection.on_token = self._handle_token
        self.connection.on_status = self._handle_status
        self.connection.on_error = self._handle_error
        self.connection.on_final = self._handle_final
        
        # 3. Load initial session
        self._load_session(initial_session)
        
        # 4. Show UI and enter chat loop
        self.tui.render_full()
        await self._chat_loop()
```

### 3. Event Handlers

Each gateway event type has a handler:

```python
async def _handle_session_changed(self, payload: dict):
    """User switched sessions."""
    self._load_session(payload)

async def _handle_message(self, payload: dict):
    """Received a message (user, assistant, or system)."""
    role = payload.get("role")
    content = payload.get("content")
    from_self = payload.get("fromSelf", False)
    
    if role == "user" and not from_self:
        # Message from another client
        content = f"📱 [From another client] {content}"
    
    self.tui.messages.append({
        "role": role,
        "content": content,
        "streaming": False
    })
    self.tui.render_full()

async def _handle_token(self, payload: dict):
    """Received a token during streaming."""
    if not self.cancelling:
        self.tui.add_token(payload.get("content", ""))

async def _handle_status(self, payload: dict):
    """Agent status changed (thinking, executing_tool, streaming)."""
    status = payload.get("status")
    if status == "streaming":
        self.tui.start_assistant_message()
    elif status == "thinking":
        self.tui.set_status("Thinking...", "yellow")
    elif status == "executing_tool":
        self.tui.set_status("Using tools...", "blue")

async def _handle_final(self, payload: dict):
    """Request completed."""
    self.tui.finish_assistant_message()
    
    # Update token usage
    usage = payload.get("usage", {})
    if usage:
        new_tokens = usage.get("totalTokens", 0)
        self.tui.update_stats(
            tokens_used=self.tui.tokens_used + new_tokens
        )
    
    self.streaming = False
```

### 4. Chat Loop

The main input/send loop:

```python
async def _chat_loop(self):
    """Main chat loop."""
    while self.running:
        try:
            # Get input (runs in executor to not block async)
            user_input = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self.prompt_session.prompt("> ", key_bindings=self.kb)
            )
            
            if not user_input.strip():
                continue
            
            # Handle local quit command
            if user_input.strip().lower() in ["/quit", "/exit"]:
                self.running = False
                break
            
            # Add to UI and send to gateway
            self.tui.add_user_message(user_input)
            run_id = await self.connection.send_message(user_input)
            
            # Wait for completion
            if run_id:
                self.streaming = True
                self.current_run_id = run_id
                while self.streaming:
                    await asyncio.sleep(0.1)
        
        except KeyboardInterrupt:
            # Handle Ctrl+C
            if self.streaming:
                await self.connection.cancel_request(self.current_run_id)
                self.streaming = False
            else:
                break
```

## Key Design Patterns

### 1. Full Redraw Strategy

Instead of trying to update specific parts of the screen:
- Clear entire screen
- Redraw all content
- Simpler code, fewer bugs
- Fast enough for modern terminals

**Optimization**: Only redraw every 10 characters during streaming to reduce flicker.

### 2. Async Event Handlers

All event handlers are async and can:
- Update UI state
- Send requests back to gateway
- Handle errors gracefully

### 3. Separation of Concerns

- **SimpleTUI**: Pure UI rendering (doesn't know about WebSocket)
- **AgentBlobTUI**: Application logic (doesn't know about Rich formatting)
- **GatewayConnection**: Network layer (doesn't know about UI)

### 4. Message Storage

Messages stored as simple dicts, not objects:
```python
{
    "role": "user" | "assistant" | "system",
    "content": "message text",
    "streaming": True | False
}
```

Easy to serialize, debug, and extend.

## Status Bar Implementation

The status bar shows real-time information:

```python
def _print_status_block(self):
    """Print status block."""
    # Status icon based on color
    status_icon = "●" if self.status_color == "green" else "⏳"
    
    # Context usage with color coding
    context_pct = (self.tokens_used / self.tokens_limit * 100)
    context_color = "green" if context_pct < 60 else "yellow" if context_pct < 85 else "red"
    
    # Format tokens as K (thousands)
    tokens_k = self.tokens_used / 1000
    limit_k = self.tokens_limit / 1000
    context_str = f"{tokens_k:.1f}K/{limit_k:.0f}K ({context_pct:.0f}%)"
    
    # Build status line
    status_line = (
        f"{status_icon} {self.status} │ "
        f"📝 {self.message_count} msgs │ "
        f"🤖 {self.model_name} │ "
        f"[{context_color}]📊 {context_str}[/{context_color}]"
    )
    
    console.print(status_line)
```

**Features:**
- Visual separator (│)
- Emojis for clarity
- Color-coded context usage
- K suffix for token counts (12.3K vs 12345)

## Multi-line Input

Using prompt_toolkit for multi-line support:

```python
# Key bindings
self.kb = KeyBindings()

@self.kb.add('c-j')
def _(event):
    """Ctrl+J adds new line."""
    event.current_buffer.insert_text('\n')

# Create prompt session
self.prompt_session = PromptSession(
    history=FileHistory(str(history_file)),
    multiline=False,  # False, but Ctrl+J adds newlines
    enable_history_search=True
)
```

**Result:**
- Enter sends message
- Ctrl+J adds newline without sending
- Command history with Up/Down arrows

## Testing Your TUI

```bash
# Run with debug logging
python run_cli.py --debug

# Start in new session
python run_cli.py --new

# Connect to custom gateway
python run_cli.py --uri ws://localhost:8000/ws
```

## Adapting for Other Platforms

The same patterns work for other UIs:

### Telegram Bot
```python
class TelegramClient:
    async def handle_session_changed(self, chat_id, payload):
        # Clear message history in memory
        self.sessions[chat_id] = {
            "session_id": payload["sessionId"],
            "title": payload["title"],
            "messages": []
        }
        
        # Send title update
        await bot.send_message(
            chat_id,
            f"📎 {payload.get('message', 'Session changed')}"
        )
    
    async def handle_message(self, chat_id, payload):
        # Just send the message to Telegram
        await bot.send_message(chat_id, payload["content"])
    
    async def handle_token(self, chat_id, payload):
        # Show typing indicator
        await bot.send_chat_action(chat_id, "typing")
```

### Web UI
```typescript
const [messages, setMessages] = useState([]);
const [streaming, setStreaming] = useState(false);
const [currentMessage, setCurrentMessage] = useState("");

connection.on_session_changed = (payload) => {
  setMessages(payload.messages);
  setSessionId(payload.sessionId);
  setStats(payload.stats);
};

connection.on_token = (payload) => {
  setCurrentMessage(prev => prev + payload.content);
};

connection.on_final = (payload) => {
  setMessages(prev => [...prev, {
    role: "assistant",
    content: currentMessage
  }]);
  setCurrentMessage("");
  setStreaming(false);
};
```

## Best Practices

1. **Let gateway handle commands**: Don't parse `/sessions` or `/switch` in client
2. **Use full redraws**: Simpler than delta updates for most UIs
3. **Track streaming state**: Know when to buffer vs display complete messages
4. **Handle disconnects gracefully**: Show reconnection UI
5. **Store minimal state**: Messages and current status only
6. **Use async/await**: Non-blocking I/O for smooth UX
7. **Throttle redraws**: During streaming, only redraw every N characters
8. **Color code context usage**: Help users see when approaching limit

## Common Pitfalls

1. **Parsing commands client-side**: Let gateway handle all `/` commands
2. **Storing too much state**: Gateway is source of truth
3. **Blocking I/O**: Use async for all network operations
4. **Redrawing too often**: Causes flicker during streaming
5. **Not handling fromSelf**: Multi-client support needs this flag
6. **Forgetting to update stats**: Use SESSION_CHANGED and FINAL events
