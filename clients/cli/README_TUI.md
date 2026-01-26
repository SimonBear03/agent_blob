# Agent Blob TUI

Modern Text User Interface for Agent Blob - inspired by Codex and Claude Code.

## What's New in TUI Mode?

🎨 **Split-screen layout** - Persistent chat history, fixed input box, status bar
📜 **Scrollable history** - See your entire conversation
⚡ **Live streaming** - Tokens appear in real-time without scrolling
📊 **Status indicators** - See connection state, thinking, tool usage
🎯 **Better UX** - Clean, organized interface

## Interface Layout

```
┌─────────────────────────────────────────────────┐
│ Agent Blob - Session: New conversation          │ ← Header
├─────────────────────────────────────────────────┤
│                                                 │
│ You:                                            │
│ Hello!                                          │
│                                                 │
│ Assistant:                                      │
│ Hi! How can I help?                             │ ← Chat Area
│                                                 │   (scrollable)
│ You:                                            │
│ What tools do you have?                         │
│                                                 │
│ Assistant:                                      │
│ I have access to...▊                            │
│                                                 │
├─────────────────────────────────────────────────┤
│ ● Streaming... │ 📝 42 msgs │ 🤖 gpt-4o │      │ ← Status Bar
│ 📊 12.3K/128K (10%)                             │   (with stats)
├─────────────────────────────────────────────────┤
│ Type below │ Shift+Enter = new line │ Enter... │ ← Input Hint
└─────────────────────────────────────────────────┘
  > Your message here_                              ← Input Box
```

## Usage

### Run TUI (Default)

```bash
# Start TUI with session picker
python run_cli.py

# Continue in most recent session
python run_cli.py --continue

# Start new session
python run_cli.py --new
```

### Run Simple CLI (Legacy)

```bash
# Use the old REPL-style CLI
python run_cli.py --simple
```

## Commands

### Gateway Commands
These are sent to the gateway and work across all clients:

| Command | Description |
|---------|-------------|
| `/help` | Show available commands |
| `/new` | Create new conversation |
| `/sessions` | List recent sessions |
| `/switch <n>` | Switch to session N |
| `/status` | Show session info |

### Local Commands
These only affect the local UI:

| Command | Description |
|---------|-------------|
| `/quit` or `/exit` | Exit CLI |
| `Ctrl+C` | Exit CLI |

## Keyboard Shortcuts

- **Enter** - Send message
- **Shift+Enter** - Add new line (multiline input)
- **Ctrl+C** - Cancel current request (or exit if idle)
- **Ctrl+D** - Exit CLI

## Features

### Real-time Streaming
Assistant responses appear token-by-token in the chat area, with a streaming cursor (▊) indicator.

### Multi-client Support
Messages from other connected clients (Web UI, Telegram, etc.) show up with a 📱 prefix.

### Status Indicators
- **● Connected** (green) - Ready
- **⏳ Thinking...** (yellow) - Agent is processing
- **🔧 Using tools...** (blue) - Executing tools
- **● Error** (red) - Something went wrong

### Status Bar Info
The status bar shows real-time information:
- **📝 Message count** - Total messages in session
- **🤖 Model** - Current AI model (e.g., gpt-4o)
- **📊 Context window** - Token usage and limit
  - Green: < 60% used
  - Yellow: 60-85% used
  - Red: > 85% used (approaching limit)

### Clean Architecture
The TUI follows the same "dumb client" principle as other clients:
- All state managed by gateway
- TUI just displays what it receives
- Easy to port the same logic to Telegram, Web, etc.

## Technical Details

Built with:
- **Rich** - Layout, live display, styling
- **Prompt Toolkit** - Input handling, history
- **Async/await** - Non-blocking I/O
- **WebSocket** - Real-time communication

The TUI maintains a simple message history model that can be easily adapted to other platforms like Telegram where you have a persistent chat view.
