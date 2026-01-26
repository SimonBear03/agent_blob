# Quick Start Guide

## Run in Your Terminal

```bash
cd /Users/simon/Documents/GitHub/agent_blob

# 1. Install dependencies
pip install --trusted-host pypi.org --trusted-host pypi.python.org --trusted-host files.pythonhosted.org -r requirements.txt

# 2. Copy environment template
cp .env.example .env

# 3. Edit .env and add your OpenAI API key
# Open .env in your editor and set OPENAI_API_KEY=sk-your-key-here

# 4. Start the gateway
python run_gateway.py
```

## Test the Gateway

In a **new terminal**:

```bash
cd /Users/simon/Documents/GitHub/agent_blob

# Test with the Python client
python test_client.py
```

You should see:
```
🔌 Connecting to ws://127.0.0.1:18789/ws...
📤 Sending connect request...
📥 Received: {...}
✅ Connected! Session ID: abc12345...
```

## Alternative: Manual Testing

```bash
# Install websocat (if not installed)
brew install websocat

# Connect to gateway
websocat ws://127.0.0.1:18789/ws
```

Then paste:
```json
{"type":"req","id":"1","method":"connect","params":{"version":"1","clientType":"cli"}}
```

Expected response:
```json
{"type":"res","id":"1","ok":true,"payload":{"gatewayVersion":"0.1.1","supportedMethods":[...],"sessionId":"..."}}
```

## Troubleshooting

### "No module named 'fastapi'"
```bash
pip install -r requirements.txt
```

### "ModuleNotFoundError: No module named 'agent_runtime'"
Make sure you run from the project root:
```bash
cd /Users/simon/Documents/GitHub/agent_blob
python run_gateway.py
```

### SSL Certificate Error
Use the full pip command with `--trusted-host` flags:
```bash
pip install --trusted-host pypi.org --trusted-host pypi.python.org --trusted-host files.pythonhosted.org -r requirements.txt
```

### "Connection refused"
Make sure the gateway is running in another terminal.

## What's Next?

Once the gateway is working:

1. **Read the protocol**: `shared/protocol/protocol_v1.md`
2. **Build a real client**: See `TODO_v0.1.1.md` for Web UI and CLI client tasks
3. **Add tools**: Implement filesystem, web search, and other tools
4. **Test multi-client**: Connect multiple clients to the same session

## Architecture

```
Client (Web/CLI/Telegram)
    ↓ WebSocket
Gateway (apps/gateway/)
    ↓ Event Stream
Agent Runtime (apps/agent_runtime/)
    ↓ OpenAI API
LLM + Tools
```

Everything is working through WebSocket streaming - no HTTP endpoints needed!
