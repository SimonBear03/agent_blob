# Installation Guide

## Quick Start

### 1. Install Dependencies

```bash
# If you have SSL certificate issues on macOS:
pip install --trusted-host pypi.org --trusted-host pypi.python.org --trusted-host files.pythonhosted.org -r requirements.txt

# Or if SSL works fine:
pip install -r requirements.txt
```

### 2. Set Up Environment Variables

Create a `.env` file in the project root:

```bash
# Required
OPENAI_API_KEY=your_openai_api_key_here

# Optional
MODEL_NAME=gpt-4o
GATEWAY_HOST=127.0.0.1
GATEWAY_PORT=18789
DB_PATH=./data/agent_blob.db
```

### 3. Start the Gateway

```bash
python run_gateway.py
```

You should see:
```
🚀 Starting Agent Blob Gateway on 127.0.0.1:18789
📡 WebSocket endpoint: ws://127.0.0.1:18789/ws
🔍 Health check: http://127.0.0.1:18789/health
```

### 4. Test the Gateway

**Health Check:**
```bash
curl http://127.0.0.1:18789/health
```

**WebSocket Test (using websocat):**
```bash
# Install websocat first: brew install websocat

# Connect and send messages
websocat ws://127.0.0.1:18789/ws
```

Then send:
```json
{"type":"req","id":"1","method":"connect","params":{"version":"1","clientType":"cli"}}
```

## Troubleshooting

### ModuleNotFoundError: No module named 'fastapi'
Install dependencies: `pip install -r requirements.txt`

### SSL Certificate Error
Use the `--trusted-host` flags shown above

### Import Errors
Make sure you're running from the project root: `python run_gateway.py`

### Database Errors
The database will be created automatically at `./data/agent_blob.db`

## Next Steps

Once the gateway is running:
1. Read the protocol docs: `shared/protocol/protocol_v1.md`
2. Build a client (Web UI, CLI, or Telegram bot)
3. Start sending messages!
