# Quick Start Guide

Get Agent Blob running in 5 minutes.

## Prerequisites

- Python 3.11+
- OpenAI API key (or compatible endpoint)

## 1. Install Dependencies

```bash
cd /Users/simon/Documents/GitHub/agent_blob

# Install Python dependencies
pip install -r requirements.txt

# Or with SSL certificate issues on macOS:
pip install --trusted-host pypi.org --trusted-host pypi.python.org --trusted-host files.pythonhosted.org -r requirements.txt
```

## 2. Configure API Key

```bash
# Copy environment template
cp .env.example .env

# Edit .env and add your OpenAI API key
# OPENAI_API_KEY=sk-your-key-here
```

## 3. Start the Gateway

In your first terminal:

```bash
# Start the WebSocket gateway
python scripts/run_gateway.py

# You should see:
# INFO:gateway.main:Agent Blob Gateway starting up...
# INFO:gateway.main:Gateway version: 0.1.1
# INFO:gateway.main:Database initialized at ./data/agent_blob.db
# INFO:uvicorn:Uvicorn running on http://127.0.0.1:3336
```

The gateway is now running at `ws://127.0.0.1:3336/ws`

## 4. Start the TUI Client

In a **new terminal**:

```bash
cd /Users/simon/Documents/GitHub/agent_blob

# Start the TUI (Text User Interface)
python run_cli.py

# You should see:
# - A split-screen chat interface
# - Welcome message from the gateway
# - Status bar with connection info
# - Input prompt at the bottom
```

## 5. Try It Out

Type some messages and try the commands:

```
> Hello!

> /help
  (Shows all available commands)

> /sessions
  (Lists your conversation sessions)

> /new
  (Creates a new conversation)

> /status
  (Shows current session stats)
```

## Test the Gateway (Optional)

If you want to test the raw WebSocket connection:

```bash
# In another terminal
python tests/test_client.py

# You should see:
# 🔌 Connecting to ws://127.0.0.1:3336/ws...
# ✅ Connected! Session ID: abc12345...
```

## TUI Features

The default TUI client provides:

### Display
- **Split-screen layout**: Chat history at top, input at bottom
- **Real-time streaming**: See tokens appear as AI types
- **Status bar**: Connection state, message count, model, token usage
- **Color-coded context**: Green → Yellow → Red as you approach token limit

### Commands
Try these gateway commands:
- `/help` - Show all commands
- `/sessions` - List your conversations
- `/sessions search python` - Search sessions
- `/sessions next` / `/sessions prev` - Paginate
- `/switch 2` - Switch to session #2
- `/new` - Create new conversation
- `/status` - Show current stats

### Keyboard Shortcuts
- **Enter** - Send message
- **Ctrl+J** - New line (multi-line input)
- **Ctrl+C** - Cancel current request (or exit)
- **Up/Down** - Navigate command history

## Command Line Options

```bash
# Continue in most recent session (default)
python run_cli.py --continue

# Start a new session
python run_cli.py --new

# Connect to custom gateway
python run_cli.py --uri ws://localhost:8000/ws

# Enable debug logging
python run_cli.py --debug
```

## Multi-Client Support

Open multiple terminals and run `python run_cli.py` in each:
- All clients can connect to the same session
- Messages from one client appear in all others
- Each client can be in a different session
- Use `/switch` to change sessions per client

Try it:
```bash
# Terminal 1
python run_cli.py

# Terminal 2
python run_cli.py

# Type in either terminal - message appears in both!
```

## Troubleshooting

### "No module named 'fastapi'" or similar
```bash
pip install -r requirements.txt
pip install -r gateway/requirements.txt
```

### "ModuleNotFoundError: No module named 'runtime'"
Make sure you run from the project root:
```bash
cd /Users/simon/Documents/GitHub/agent_blob
python scripts/run_gateway.py
```

### SSL Certificate Error
Use the full pip command with `--trusted-host` flags:
```bash
pip install --trusted-host pypi.org --trusted-host pypi.python.org --trusted-host files.pythonhosted.org -r requirements.txt
```

### "Connection refused"
Make sure the gateway is running in another terminal.

### TUI rendering issues
If the TUI doesn't render well in your terminal:
```bash
# Use simple CLI mode instead
python run_cli.py --simple
```

### OpenAI API errors
Check your `.env` file has a valid API key:
```bash
cat .env | grep OPENAI_API_KEY
```

## Next Steps

Now that you have Agent Blob running:

### Learn More
1. **Read the docs**: `docs/ARCHITECTURE.md` - Understand the "dumb client" design
2. **Protocol spec**: `shared/protocol/protocol_v1.md` - WebSocket protocol details
3. **TUI implementation**: `docs/TUI_IMPLEMENTATION.md` - How the TUI works
4. **Client guide**: `docs/CLIENT_DESIGN.md` - Build your own client

### Explore Features
1. **Try the commands**: `/sessions`, `/switch`, `/new`, `/status`
2. **Search sessions**: `/sessions search <keyword>`
3. **Multi-client**: Open multiple TUIs and watch messages sync
4. **Use tools**: Ask the agent to read files, save memories, search conversations

### Development
1. **Check progress**: `PROGRESS.md` - Current implementation status
2. **See the plan**: `TODO_v0.1.1.md` - Detailed implementation plan
3. **Build a client**: Follow `docs/CLIENT_DESIGN.md` to create Web/Telegram clients

## Architecture Overview

```
┌─────────────────┐
│  TUI Client     │ ← You are here!
│  (Python)       │
└────────┬────────┘
         │ WebSocket (Protocol v1)
         │
┌────────▼────────────┐
│  Gateway            │
│  - Multi-client mgr │
│  - Commands         │
│  - Request queue    │
└────────┬────────────┘
         │ Event Stream
┌────────▼────────────┐
│  Agent Runtime      │
│  - LLM calls        │
│  - Tool execution   │
│  - Process tracking │
└────────┬────────────┘
         │
    ┌────┴─────┬────────┬───────┐
    │          │        │       │
┌───▼───┐ ┌───▼────┐ ┌─▼──┐ ┌──▼────┐
│OpenAI │ │ SQLite │ │FS  │ │Process│
│GPT-4o │ │   DB   │ │Tools│ │Manager│
└───────┘ └────────┘ └────┘ └───────┘
```

**Key concepts:**
- **WebSocket only**: No HTTP endpoints needed
- **Dumb clients**: All logic in gateway, clients just display
- **Multi-client**: Multiple clients can share sessions
- **Event streaming**: Real-time token-by-token responses
- **Local-first**: All data in SQLite, no cloud dependencies

## Getting Help

- **Documentation**: See `docs/` directory
- **Client READMEs**: See `clients/cli/README.md` and `README_TUI.md`
- **Protocol**: See `shared/protocol/protocol_v1.md`
- **Issues**: Check existing code comments and TODOs

Happy chatting! 🤖
