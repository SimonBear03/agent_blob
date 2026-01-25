# Agent Blob

A local-first AI agent system with structured memory, tool execution, and PKM integration.

## Architecture

Agent Blob is a monorepo containing:

- **apps/web**: Next.js frontend for chat interface, memory management, and settings
- **apps/server**: FastAPI backend with agent loop, tool registry, SQLite storage, and PKM export
- **shared/**: Shared resources (prompts, skills, schemas)

```
┌─────────┐
│  User   │
└────┬────┘
     │
┌────▼────────────────────────┐
│  Next.js Web UI             │
│  - Chat interface           │
│  - Pinned memory editor     │
│  - Settings                 │
└────┬────────────────────────┘
     │ HTTP
┌────▼────────────────────────┐
│  FastAPI Server             │
│  ┌─────────────────────┐    │
│  │  Agent Loop         │    │
│  │  (System Prompt +   │    │
│  │   Active Skills)    │◄───┼─── Skills (PKM, etc.)
│  └──────┬──────────────┘    │
│         │                   │
│  ┌──────▼──────────────┐    │
│  │  Tool Registry      │    │
│  │  - filesystem.read  │    │
│  │  - filesystem.write │    │
│  │  - filesystem.list  │    │
│  │  - memory.*         │    │
│  └──────┬──────────────┘    │
│         │                   │
│  ┌──────▼──────────────┐    │
│  │  SQLite Database    │    │
│  │  - threads          │    │
│  │  - messages         │    │
│  │  - pinned_memory    │    │
│  │  - audit_log        │    │
│  └─────────────────────┘    │
│         │                   │
│  ┌──────▼──────────────┐    │
│  │  OpenAI-compatible  │    │
│  │  API (gpt-4o, etc.) │    │
│  └─────────────────────┘    │
└─────────────────────────────┘
```

## Key Features

- **Local-first**: All data stored in local SQLite database
- **Structured memory**: Persistent pinned memory + full conversation history
- **Tool registry**: General-purpose tools (filesystem, memory, etc.) with safety boundaries
- **Skills system**: Modular prompt extensions for specialized workflows (e.g., PKM note creation)
- **Audit logging**: Complete audit trail of all tool executions
- **PKM integration**: Skills can use filesystem tools to create notes in your PKM vault

## Safety Boundaries

1. **Filesystem access**: All filesystem tools constrained to `ALLOWED_FS_ROOT`
2. **No delete operations**: Filesystem tools support read, write, and list only
3. **Audit logging**: All tool calls logged with timestamp, inputs, outputs
4. **Server-side API keys**: API keys never exposed to frontend
5. **Skills-based workflows**: Complex operations like PKM export are implemented as skills that use general tools

## Local Development Setup

### Prerequisites

- Python 3.10+ with pip
- Node.js 18+ with npm
- OpenAI API key (or compatible API)

### 1. Clone and configure

```bash
git clone <your-repo-url>
cd agent_blob

# Copy example env file and configure
cp .env.example .env
# Edit .env with your actual values:
# - OPENAI_API_KEY
# - PKM_ROOT (path to your PKM vault - agent can write notes here)
# - ALLOWED_FS_ROOT (safe workspace path for general filesystem access)
```

### 2. Set up FastAPI server

```bash
cd apps/server

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Initialize database (automatic on first run)
# Run server
uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

Server will be available at `http://127.0.0.1:8000`

API docs: `http://127.0.0.1:8000/docs`

### 3. Set up Next.js web app

```bash
cd apps/web

# Install dependencies
npm install

# Run development server
npm run dev
```

Web app will be available at `http://localhost:3000`

### 4. Usage

1. Open `http://localhost:3000` in your browser
2. Configure API key in Settings (if not set in server .env)
3. Create a new chat thread
4. Start conversing with the agent
5. Agent can use general tools (filesystem read/write/list, memory management)
6. Ask agent to create PKM notes - the PKM skill will use filesystem tools to write notes to your vault

## Project Structure

```
agent_blob/
├── apps/
│   ├── server/              # FastAPI backend
│   │   ├── main.py          # FastAPI app entry point
│   │   ├── agent/           # Agent loop logic
│   │   ├── db/              # SQLite layer
│   │   ├── tools/           # Tool registry and general-purpose tools
│   │   └── schemas/         # Pydantic models
│   └── web/                 # Next.js frontend
│       ├── app/             # App router pages
│       ├── components/      # React components
│       └── lib/             # API client utilities
├── shared/
│   ├── prompts/             # System prompts
│   ├── skills/              # Agent skills (PKM, workflows, etc.)
│   └── schemas/             # JSON schemas for tools
├── .env.example             # Environment variable template
├── .gitignore
└── README.md
```

## Technology Stack

### Backend (apps/server)
- **FastAPI**: Modern Python web framework
- **SQLite**: Local-first database
- **OpenAI SDK**: LLM API integration with function calling
- **Pydantic**: Data validation and schemas

### Frontend (apps/web)
- **Next.js 14**: React framework with App Router
- **TypeScript**: Type-safe development
- **Tailwind CSS**: Utility-first styling
- **shadcn/ui**: Component library (optional)

## Development Roadmap

- [x] Monorepo scaffold
- [x] SQLite schema and initialization
- [x] Tool registry pattern
- [x] Basic filesystem tools (read, write, list)
- [x] Memory management tools
- [x] OpenAI integration with function calling
- [x] PKM skill (uses filesystem tools to create notes)
- [x] FastAPI endpoints (threads, chat, memory, settings)
- [x] Next.js basic UI
- [ ] Streaming responses
- [ ] Additional skills (web search, code analysis, etc.)
- [ ] Multi-model support
- [ ] Additional general tools (search, diff, etc.)
- [ ] Skills marketplace/sharing
