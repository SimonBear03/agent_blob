# Agent Blob CLI

Beautiful, interactive command-line client for Agent Blob.

## Pure "Dumb Client" Architecture

Both CLI modes are **just chatboxes**:
- Send text to gateway
- Display text from gateway
- No session management logic
- No command parsing
- Gateway handles everything

### 1. TUI Mode (Default) ⭐ Recommended
Modern split-screen interface like Codex/Claude Code:
- Persistent chat history
- Fixed input box at bottom
- Live status bar
- Real-time streaming display

### 2. Simple CLI Mode
Traditional REPL-style interface:
- Linear output (messages scroll up)
- Good for scripting or simple usage

## Features

- 🎨 Rich terminal UI with clean layout
- ⚡ Real-time streaming responses
- 📝 Multi-line input support (Shift+Enter)
- 📜 Command history
- 🔄 Universal session picker
- ⌨️ Smart Ctrl+C handling
- 🎯 Multi-client broadcast support

## Installation

```bash
# Install CLI dependencies (if not already installed)
pip install -r requirements.txt
```

## Usage

### TUI Mode (Default)

```bash
# Auto-connect to most recent session (or create if none)
python run_cli.py

# Explicitly continue most recent session
python run_cli.py --continue

# Create new session
python run_cli.py --new
```

**Gateway shows a welcome message** with session info when you connect!

### Simple CLI Mode

```bash
# Use traditional REPL-style CLI
python run_cli.py --simple

# All other options work with --simple
python run_cli.py --simple --continue
```

### Command-line Options

```bash
# Connect to custom gateway
python run_cli.py --uri ws://localhost:3336/ws

# Skip session picker, continue in most recent session
python run_cli.py --continue

# Skip session picker, create new session
python run_cli.py --new

# Use simple REPL-style CLI instead of TUI
python run_cli.py --simple

# Enable debug logging
python run_cli.py --debug
```

## Available Commands

### Gateway Commands (work in all clients)

These commands are handled by the gateway and return text responses:

| Command | Description |
|---------|-------------|
| `/help` | Show available gateway commands |
| `/new` | Create new conversation |
| `/sessions` | List recent sessions |
| `/switch <n>` | Switch to session number N |
| `/status` | Show current session info |

### Local UI Commands

These are handled locally by the CLI:

| Command | Description |
|---------|-------------|
| `/quit` or `/exit` | Exit the CLI |
| `Ctrl+C` | Exit the CLI |

## Keyboard Shortcuts

- **Enter** - Send message
- **Shift+Enter** - New line (multi-line input)
- **Up/Down** - Navigate command history (when input is empty)
- **Ctrl+C** - Cancel current request (or exit if idle)
- **Ctrl+D** - Exit CLI

## Architecture

The CLI is a **pure "dumb" client**:
- No API calls (except WebSocket messages)
- No command parsing (gateway handles all commands)
- No session management (gateway decides sessions)
- Just sends text in, displays text out

**What happens on connect:**
1. Client connects with preference (`auto`, `new`, or `continue`)
2. Gateway assigns session
3. Gateway sends last 4 messages
4. Gateway sends welcome message: "👋 Welcome back! You're in Python Help..."
5. Client displays everything and is ready to chat

## Why Two Modes?

**TUI Mode** provides the best user experience for interactive chat - you can see your full conversation history and the interface stays clean as messages stream in.

**Simple CLI Mode** is useful for:
- Slower terminals
- Scripting/automation
- Environments where TUI doesn't render well
- Personal preference

Both modes use the same underlying WebSocket connection and follow the same "dumb client" principle.

## Session Picker

On startup, both modes show a universal session picker:

```
Select a session to continue or start a new one:

1. New conversation (2 messages) • 5m ago
2. Python project help (8 messages) • 1h ago
3. Database design (15 messages) • 3h ago
...
9. Old session (30 messages) • 2d ago

[N] New conversation

>
```

This same picker logic works for Web UI, Telegram, and any future clients!

## Learn More

- [TUI Mode Details](./README_TUI.md) - Full documentation for TUI mode
- [Connection Manager](./connection.py) - WebSocket connection logic
- [Protocol](../../shared/protocol/protocol_v1.md) - Gateway protocol spec
