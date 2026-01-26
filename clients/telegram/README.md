# Agent Blob Telegram Bot

Simple "dumb client" Telegram bot that connects to the Agent Blob gateway.

## Setup

### 1. Create a Telegram Bot

1. Open Telegram and message [@BotFather](https://t.me/BotFather)
2. Send `/newbot` command
3. Follow the prompts to create your bot
4. Copy the bot token (looks like `123456:ABC-DEF...`)

### 2. Get Your Telegram User ID

1. Message [@userinfobot](https://t.me/userinfobot) on Telegram
2. It will reply with your user ID (a number like `123456789`)
3. Copy this number

### 3. Configure Environment

Add to your `.env` file:

```bash
# Telegram Bot Configuration
TELEGRAM_BOT_TOKEN=123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11
TELEGRAM_USER_ID=123456789
```

### 4. Install Dependencies

```bash
pip install -r clients/telegram/requirements.txt
```

## Usage

### Start the Bot

```bash
# Terminal 1: Start gateway (if not already running)
python scripts/run_gateway.py

# Terminal 2: Start Telegram bot
python run_telegram.py
```

You should see:
```
INFO:telegram_bot:Connecting to gateway at ws://127.0.0.1:3336/ws
INFO:telegram_bot:Connected to gateway successfully
INFO:telegram_bot:Starting bot polling...
```

### Use the Bot

1. **Find your bot** in Telegram (search for the name you gave it)
2. **Start a chat** - Send `/start`
3. **Send messages** - Just type normally!
4. **Try commands**:
   - `/help` - Show available commands
   - `/sessions` - List your sessions
   - `/new` - Create new session
   - `/switch 2` - Switch to session #2

## Features

### ✅ What It Does

- **Forwards messages** to gateway (all text you send)
- **Displays responses** from AI
- **Real-time streaming** - See tokens appear as AI types
- **All gateway commands work** - `/help`, `/sessions`, `/switch`, etc.
- **Message chunking** - Automatically splits long responses (4096 char limit)
- **Markdown support** - Formatted text displays nicely
- **Security** - Only your user ID can use the bot

### ❌ What It Doesn't Do

- No command parsing (gateway handles all `/commands`)
- No session management (gateway tracks sessions)
- No formatting logic (gateway formats responses)

This is the "dumb client" philosophy in action!

## Multi-Client Support

The Telegram bot works alongside other clients:

```
You on Telegram  ─┐
You on TUI       ─┤──► Gateway ──► Same or different sessions
You on Web       ─┘
```

**Same session:**
- Type "hello" in TUI → Telegram shows "📱 [From Tui] hello"
- Type "hi" in Telegram → TUI shows "💬 [From Telegram] hi"

**Different sessions:**
- Telegram can be in Session A
- TUI can be in Session B
- Each is independent
- Use `/switch` to change sessions in each client

## Troubleshooting

### Bot doesn't respond

Check:
1. Gateway is running (`python scripts/run_gateway.py`)
2. Bot token is correct in `.env`
3. Your user ID is correct in `.env`
4. No error messages in terminal

### "Not connected to gateway"

- Restart the bot: `python run_telegram.py`
- Check gateway is running and accessible at `ws://127.0.0.1:3336/ws`

### Bot accepts messages from strangers

- Check `TELEGRAM_USER_ID` in `.env` matches YOUR user ID
- Restart the bot after changing `.env`

### Messages are cut off

- Long messages are automatically chunked (4096 char limit)
- You should receive multiple messages for long responses

## Architecture

```
Telegram User (You)
    ↓
Telegram Bot API
    ↓
telegram_bot.py (clients/telegram/)
    ↓ WebSocket
Gateway (gateway/)
    ↓
Agent Runtime (runtime/)
    ↓
OpenAI GPT-4o
```

**Key points:**
- Bot runs as daemon (always on)
- Single connection to gateway
- Gateway handles all logic
- Bot just forwards and displays

## Security

The bot implements these security measures:

1. **User ID allowlist** - Only your Telegram user ID can use the bot
2. **Silent rejection** - Unauthorized users get no response
3. **Local gateway** - Gateway runs on your machine (not exposed to internet)
4. **No data storage** - Bot doesn't store messages, gateway database handles it

**Important:** Keep your `TELEGRAM_BOT_TOKEN` secret! Anyone with this token can control your bot.

## Advanced Usage

### Running 24/7

To keep the bot running permanently:

```bash
# Option 1: Using screen
screen -S telegram_bot
python run_telegram.py
# Press Ctrl+A, then D to detach

# Option 2: Using tmux
tmux new -s telegram_bot
python run_telegram.py
# Press Ctrl+B, then D to detach

# Option 3: System service (systemd on Linux)
# Create a service file in /etc/systemd/system/telegram-bot.service
```

### Multiple Sessions

You can have Telegram in one session while TUI is in another:

```bash
# In Telegram
You: /sessions
Bot: 📋 Recent Sessions:
     1. Python Help
     2. Shopping List
     3. Work Notes

You: /switch 2
Bot: ✓ Switched to: Shopping List

# Now Telegram is in Session 2
# TUI can be in Session 1 (independent!)
```

### Connecting to Remote Gateway

If your gateway is on another machine:

```bash
# .env
GATEWAY_URI=ws://192.168.1.100:3336/ws
```

## See Also

- `docs/ARCHITECTURE.md` - System architecture
- `docs/CLIENT_DESIGN.md` - Client implementation guide
- `docs/DUMB_CLIENT_PHILOSOPHY.md` - Why clients are "dumb"
- `clients/cli/README.md` - TUI client documentation
