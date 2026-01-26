# Agent Blob

A local-first AI agent system with structured memory, tool execution, and universal multi-client support.

**Version:** 0.1.1 (WebSocket-based architecture)

## Architecture

Agent Blob v0.1.1 uses a **WebSocket-only** architecture inspired by Clawdbot, enabling real-time streaming and multi-client support.

### Components

- **gateway/**: WebSocket gateway for universal client access (Web, CLI, Telegram)
- **runtime/**: Event-streaming agent with tool execution and process management
- **clients/**: Client implementations
  - **cli/**: TUI (Text User Interface) - modern terminal client with split-screen layout
- **shared/**: Protocol specs, prompts, and schemas

### Architecture Diagram

```
┌──────────────┐  ┌──────────────┐  ┌──────────────┐
│   Web UI     │  │   CLI Client │  │ Telegram Bot │
│  (Browser)   │  │   (Python)   │  │   (Python)   │
└──────┬───────┘  └──────┬───────┘  └──────┬───────┘
       │                 │                  │
       └─────────────────┴──────────────────┘
                         │ WebSocket
                         │ (Protocol v1)
              ┌──────────▼──────────┐
              │  Gateway            │
              │  - Connection mgr   │
              │  - Multi-client     │
              │  - Request queue    │
              │  - Commands         │
              └──────────┬──────────┘
                         │ Event Stream
              ┌──────────▼──────────┐
              │  Agent Runtime      │
              │  - Event generator  │
              │  - Tool registry    │
              │  - Process manager  │
              └──────────┬──────────┘
                         │
       ┌─────────────────┼─────────────────┐
       │                 │                 │
┌──────▼─────┐  ┌────────▼────────┐  ┌────▼──────┐
│  OpenAI    │  │  SQLite DB      │  │ Processes │
│  GPT-4o    │  │  - sessions     │  │  Tracking │
│            │  │  - messages     │  │           │
│            │  │  - memory       │  │           │
└────────────┘  └─────────────────┘  └───────────┘
```

## Key Features

- **WebSocket Protocol**: Universal transport for all clients (Web, CLI, Telegram)
- **Multi-Client Support**: Multiple clients can connect to the same session simultaneously
- **Real-Time Streaming**: Token-by-token streaming from GPT-4o with status updates
- **Session Management**: Search, list, paginate, and switch between conversation sessions
- **Gateway Commands**: Built-in commands (`/sessions`, `/switch`, `/new`, `/help`, etc.)
- **Modern TUI Client**: Split-screen terminal interface with persistent history and status bar
- **Tool Execution**: Filesystem, memory, session search, and process management
- **Process Tracking**: Monitor and cancel long-running operations
- **Request Queueing**: Per-session FIFO queue with cancellation support
- **Configurable History**: Per-client message history limits (4-20 messages)
- **Local-First**: All data stored in SQLite, no cloud dependencies

## Quick Start

### Prerequisites

- Python 3.11+
- OpenAI API key (or compatible endpoint)
- Node.js 18+ (for Web UI, optional)

### 1. Install Dependencies

```bash
# Install Python dependencies
pip install -r requirements.txt

# Or with SSL certificate issues on macOS:
pip install --trusted-host pypi.org --trusted-host pypi.python.org --trusted-host files.pythonhosted.org -r requirements.txt
```

### 2. Configure API Key

```bash
# Copy environment template
cp .env.example .env

# Edit .env and add your OpenAI API key
# OPENAI_API_KEY=sk-your-key-here
```

### 3. Start the Gateway

```bash
# Start the WebSocket gateway
python run_gateway.py

# Gateway will be available at:
# WebSocket: ws://127.0.0.1:3336/ws
# Health: http://127.0.0.1:3336/health
```

### 4. Start the TUI Client

```bash
# In a new terminal, start the TUI
python run_cli.py

# The TUI will connect and show:
# - Contextual welcome message
# - Your conversation history (last 20 messages)
# - Status bar with model, tokens, message count
# - Input prompt at the bottom

# Try these commands:
# /help - Show all available commands
# /sessions - List your sessions
# /new - Create a new session
# /status - Show current session stats
```

### 5. Test Basic Connection (Optional)

```bash
# Test raw WebSocket connection
python test_client.py

# Or test tool execution
python test_tools.py
```

## Available Tools

The agent has access to:

1. **Filesystem**
   - `filesystem.read` - Read files with workspace constraints
   - `filesystem.write` - Write files safely
   - `filesystem.list` - List directory contents

2. **Memory**
   - `memory.set` - Store persistent memory
   - `memory.get` - Retrieve memory
   - `memory.list` - List all memory

3. **Sessions**
   - `sessions.search` - Search conversations by keywords
   - `sessions.list` - List recent sessions
   - `sessions.get` - Get session details

4. **Processes**
   - `process.list` - List running processes
   - `process.status` - Check process status
   - `process.cancel` - Cancel a process
   - `process.wait_time` - Get wait time estimate

## WebSocket Protocol

Agent Blob uses a custom WebSocket protocol (v1) for all communication. See `shared/protocol/protocol_v1.md` for the complete specification.

### Connection Flow

1. **Connect**: Client sends `connect` request with version and client type
2. **Session**: Gateway creates or resumes a session
3. **Messages**: Client sends messages via `agent` method
4. **Events**: Gateway streams events (tokens, tool calls, status, etc.)
5. **Commands**: Client can use gateway commands (`/help`, `/sessions`, etc.)

### Example

```javascript
// Connect
ws.send(JSON.stringify({
  type: "req",
  id: "conn-1",
  method: "connect",
  params: { version: "1", clientType: "web" }
}));

// Send message
ws.send(JSON.stringify({
  type: "req",
  id: "msg-1",
  method: "agent",
  params: { sessionId: "session-id", message: "Hello!" }
}));

// Receive events
ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  if (data.event === "token") {
    console.log(data.payload.content); // Stream tokens
  }
};
```

## Multi-Client Support

Multiple clients can connect to the same session simultaneously. All events are broadcast to all connected clients:

- **User messages**: Broadcast with sender indication (Web/CLI/Telegram)
- **Agent responses**: Broadcast identically to all clients
- **Tool execution**: All clients see tool calls and results

Telegram clients receive messages prefixed with source:
```
🖥️ [From Web UI] Hello from the web interface!
```

## Gateway Commands

Commands are messages starting with `/` that are processed by the gateway:

### Session Management
- `/sessions` - List recent sessions (page 1, 9 per page)
- `/sessions <n>` - Show page N of sessions
- `/sessions next` / `/sessions prev` - Navigate through pages
- `/sessions search <keyword>` - Search sessions by title or content
- `/switch <n>` - Switch to session number N from the list
- `/new` - Create a new session

### Information
- `/help` - Show all available commands
- `/status` - Show current session stats (ID, messages, model, queue)
- `/history [count]` - Show message history (default: 20)

**Note**: Commands are handled by the gateway and work identically across all clients (TUI, Web, Telegram, etc.)

## Project Structure

```
agent_blob/
├── gateway/                  # WebSocket gateway
│   ├── main.py              # FastAPI app with /ws endpoint
│   ├── protocol.py          # Pydantic models for requests/responses/events
│   ├── connections.py       # Multi-client connection manager
│   ├── queue.py             # Per-session request queue
│   ├── handlers.py          # Method routing (agent, sessions, status)
│   ├── commands.py          # Command processing (/sessions, /switch, etc.)
│   └── requirements.txt
│
├── runtime/                  # Agent runtime
│   ├── runtime.py           # Event-streaming agent loop
│   ├── processes.py         # Process manager
│   ├── db/                  # Database layer
│   │   ├── sessions.py      # Session CRUD + search
│   │   ├── messages.py      # Message CRUD
│   │   ├── memory.py        # Memory CRUD
│   │   └── audit.py         # Audit logging
│   └── tools/               # Tool implementations
│       ├── filesystem.py    # File read/write/list
│       ├── memory_tools.py  # Memory set/get/list
│       ├── session_tools.py # Session search/list/get
│       └── process_tools.py # Process list/status/cancel/wait_time
│
├── clients/                  # Client implementations
│   └── cli/                 # CLI/TUI client
│       ├── cli_tui.py       # Modern TUI with split-screen layout
│       ├── tui.py           # UI components (experimental)
│       ├── ui.py            # Shared UI utilities
│       ├── connection.py    # WebSocket connection wrapper
│       ├── README.md        # CLI client documentation
│       └── README_TUI.md    # TUI mode details
│
├── shared/
│   ├── protocol/            # Protocol specs
│   │   ├── protocol_v1.md   # Full WebSocket protocol spec
│   │   ├── request.schema.json
│   │   ├── response.schema.json
│   │   └── event.schema.json
│   ├── prompts/
│   │   └── system.md        # System prompt
│   └── schemas/
│       └── tool_schema.json # Tool definitions
│
├── docs/                     # Documentation
│   ├── ARCHITECTURE.md      # "Dumb client" architecture
│   ├── CLIENT_DESIGN.md     # Client implementation guide
│   └── TUI_IMPLEMENTATION.md # TUI implementation details
│
├── scripts/
│   ├── run_gateway.py       # Gateway startup script
│   └── cleanup_sessions.py  # Database maintenance
│
├── tests/
│   ├── test_client.py       # Basic WebSocket test
│   └── test_tools.py        # Tool execution test
│
├── data/                     # SQLite database (created on first run)
│   └── agent_blob.db
│
├── run_cli.py               # TUI client launcher
├── requirements.txt         # Python dependencies
├── QUICKSTART.md            # Quick start guide
├── PROGRESS.md              # Development progress
└── TODO_v0.1.1.md          # Implementation plan
```

## Development Status

**Version 0.1.1**: Core infrastructure complete

✅ Complete:
- WebSocket protocol and gateway
- Multi-client connection manager with broadcasting
- Request queueing, cancellation, and per-session queue
- Agent runtime as event generator
- Process management and tracking
- Session tools (search, list, get with pagination)
- Gateway commands (/sessions, /switch, /new, /help, /status)
- Filesystem and memory tools
- Modern TUI client with split-screen layout
- History limiting per client type
- Session statistics and token tracking

📝 Documentation:
- Protocol specification (protocol_v1.md)
- Architecture guide (ARCHITECTURE.md)
- Client design guide (CLIENT_DESIGN.md)
- TUI implementation guide (TUI_IMPLEMENTATION.md)
- Client README files

⏳ Future Enhancements:
- Web UI client (React-based)
- Telegram bot client
- Additional tools (web search, code execution)
- Enhanced testing suite

See `PROGRESS.md` for detailed status.

## Documentation

### Getting Started
- `QUICKSTART.md` - Quick start guide
- `INSTALL.md` - Installation instructions
- `README.md` - This file (overview and features)

### Architecture & Design
- `docs/ARCHITECTURE.md` - "Dumb client" architecture and gateway design
- `docs/CLIENT_DESIGN.md` - Client implementation guide
- `docs/TUI_IMPLEMENTATION.md` - TUI client implementation details
- `shared/protocol/protocol_v1.md` - WebSocket protocol specification

### Client Documentation
- `clients/cli/README.md` - CLI/TUI client usage
- `clients/cli/README_TUI.md` - TUI mode detailed documentation

### Development
- `PROGRESS.md` - Development progress and status
- `TODO_v0.1.1.md` - Detailed implementation plan

## License

MIT

## Changelog

### v0.1.1 (Current)
- Complete architectural rewrite to WebSocket-only
- Multi-client support with broadcasting
- Session-based conversations (replacing threads)
- Process management and tracking
- Real-time event streaming
- Gateway commands
- Session and process tools for LLM

### v0.1.0
- Initial HTTP-based implementation
- Basic chat with tool execution
- Thread-based conversations
- Filesystem and memory tools
