# Agent Blob

A local-first AI agent system with structured memory, tool execution, and universal multi-client support.

**Version:** 0.1.1 (WebSocket-based architecture)

## Architecture

Agent Blob v0.1.1 uses a **WebSocket-only** architecture inspired by Clawdbot, enabling real-time streaming and multi-client support.

### Components

- **apps/gateway**: WebSocket gateway for universal client access (Web, CLI, Telegram)
- **apps/agent_runtime**: Event-streaming agent with tool execution and process management  
- **apps/web**: Next.js frontend (⚠️ needs migration to WebSocket - see `apps/web/MIGRATION_NEEDED.md`)
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
- **Multi-Client Support**: Multiple clients can connect to the same session
- **Real-Time Streaming**: Token-by-token streaming from GPT-4o
- **Session Management**: Search, list, and switch between conversation sessions
- **Tool Execution**: Filesystem, memory, session search, and process management
- **Process Tracking**: Monitor and cancel long-running operations
- **Request Queueing**: Per-session FIFO queue with immediate feedback
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

### 4. Test It

```bash
# In a new terminal, test the connection
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

- `/help` - Show available commands
- `/new` - Create a new session
- `/sessions` - List recent sessions
- `/session <id>` - Switch to a session
- `/history [count]` - Show message history
- `/status` - Show gateway and session status

## Project Structure

```
agent_blob/
├── apps/
│   ├── gateway/              # WebSocket gateway
│   │   ├── main.py          # FastAPI app
│   │   ├── protocol.py      # Pydantic models
│   │   ├── connections.py   # Multi-client manager
│   │   ├── queue.py         # Request queue
│   │   ├── handlers.py      # Method routing
│   │   └── commands.py      # Command processing
│   │
│   ├── agent_runtime/        # Agent runtime
│   │   ├── runtime.py       # Event generator
│   │   ├── processes.py     # Process manager
│   │   ├── db/              # Database layer
│   │   └── tools/           # Tool registry
│   │
│   └── web/                  # Web UI (needs migration)
│
├── shared/
│   ├── protocol/             # Protocol specs
│   └── prompts/              # System prompts
│
├── run_gateway.py            # Start script
├── test_client.py            # Basic test client
├── test_tools.py             # Tool execution test
├── requirements.txt          # Python dependencies
├── QUICKSTART.md             # Quick start guide
└── TODO_v0.1.1.md           # Implementation plan
```

## Development Status

**Version 0.1.1**: Core infrastructure complete (10/15 tasks)

✅ Complete:
- WebSocket protocol and gateway
- Multi-client connection manager
- Request queueing and broadcast
- Agent runtime as event generator
- Process management and tracking
- Session and process tools
- Filesystem and memory tools

⏳ In Progress:
- Web UI migration to WebSocket
- CLI client improvements
- Tests and documentation

See `PROGRESS.md` for detailed status.

## Documentation

- `QUICKSTART.md` - Quick start guide
- `INSTALL.md` - Installation instructions
- `PROGRESS.md` - Development progress
- `TODO_v0.1.1.md` - Detailed implementation plan
- `shared/protocol/protocol_v1.md` - WebSocket protocol specification
- `apps/web/MIGRATION_NEEDED.md` - Web UI migration guide

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
