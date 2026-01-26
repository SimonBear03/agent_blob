# Telegram Bot Quick Start

Get the Telegram bot running in 5 minutes.

## Prerequisites

- Agent Blob gateway running (`python scripts/run_gateway.py`)
- Telegram account

## Setup Steps

### 1. Create Bot on Telegram

Open Telegram and follow these steps:

1. **Message @BotFather**: Search for `@BotFather` and start chat
2. **Create bot**: Send `/newbot`
3. **Name your bot**: e.g., "My Agent Blob Bot"
4. **Choose username**: e.g., `my_agent_blob_bot` (must end in `bot`)
5. **Copy token**: You'll get something like `123456789:ABCdefGHIjklMNOpqrsTUVwxyz`

### 2. Get Your User ID

1. **Message @userinfobot**: Search for `@userinfobot` and start chat
2. **Send any message**: e.g., "hi"
3. **Copy your ID**: You'll get a number like `123456789`

### 3. Configure

Edit your `.env` file:

```bash
# Add these lines:
TELEGRAM_BOT_TOKEN=123456789:ABCdefGHIjklMNOpqrsTUVwxyz
TELEGRAM_USER_ID=123456789
```

### 4. Install Dependencies

```bash
pip install -r clients/telegram/requirements.txt
```

### 5. Start Bot

```bash
# Terminal 1: Gateway (if not already running)
python scripts/run_gateway.py

# Terminal 2: Telegram bot
python run_telegram.py
```

You should see:
```
INFO:telegram_bot:Connecting to gateway at ws://127.0.0.1:3336/ws
INFO:telegram_bot:Connected to gateway successfully
INFO:telegram_bot:Starting bot polling...
```

### 6. Test It!

1. Open Telegram
2. Search for your bot username
3. Start chat with `/start`
4. Send a message!

## Example Conversation

```
You: /start
Bot: 🦞 Agent Blob Bot
     I'm connected to your Agent Blob gateway!
     Just send me messages and I'll forward them to your AI.

You: Hello!
Bot: Hi! How can I help you today?

You: /sessions
Bot: 📋 Recent Sessions:
     1. New conversation (5 messages) • just now
     2. Python help (42 messages) • 2h ago
     Type /switch <number> to switch sessions

You: /help
Bot: [Shows all available commands]
```

## Multi-Client Magic ✨

**Start TUI while Telegram is running:**

```bash
# Terminal 3
python run_cli.py
```

Now:
- Type in TUI → Telegram shows "📱 [From Tui] your message"
- Type in Telegram → TUI shows "💬 [From Telegram] your message"
- Both see AI responses
- Both can use `/switch` independently

## Troubleshooting

**Bot doesn't respond:**
- Check gateway is running
- Check `TELEGRAM_BOT_TOKEN` and `TELEGRAM_USER_ID` in `.env`
- Restart bot: `Ctrl+C` then `python run_telegram.py`

**Messages from strangers:**
- Double-check `TELEGRAM_USER_ID` is YOUR user ID
- Restart bot after changing `.env`

**Connection errors:**
- Check gateway is at `ws://127.0.0.1:3336/ws`
- Check no firewall blocking connections

## Next Steps

- Read `clients/telegram/README.md` for full documentation
- Try `/sessions search <keyword>` to search conversations
- Use `/switch` to work on multiple topics
- Run bot 24/7 with screen/tmux/systemd

Enjoy chatting with your AI from Telegram! 🦞
