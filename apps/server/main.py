"""
Agent Blob FastAPI Server

Main application entry point with API endpoints.
"""
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Initialize FastAPI app
app = FastAPI(
    title="Agent Blob API",
    description="Local-first AI agent with structured memory and tool execution",
    version="0.1.0"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Import modules after app creation
from db import get_db, init_db
from db.threads import ThreadsDB
from db.messages import MessagesDB
from db.memory import MemoryDB
from db.audit import AuditDB
from agent import get_agent, init_agent
from schemas import (
    ThreadCreate, Thread, MessageCreate, Message,
    MemoryCreate, Memory, ChatRequest, ChatResponse,
    SettingsUpdate, Settings
)

# Initialize database on startup
@app.on_event("startup")
async def startup_event():
    """Initialize database and agent on startup."""
    db_path = os.getenv("DB_PATH", "./data/agent_blob.db")
    init_db(db_path)
    init_agent()


# Health check
@app.get("/")
async def root():
    """Health check endpoint."""
    return {
        "status": "ok",
        "service": "Agent Blob API",
        "version": "0.1.0"
    }


# ==================== Thread Endpoints ====================

@app.post("/threads", response_model=Thread)
async def create_thread(thread_data: ThreadCreate):
    """Create a new conversation thread."""
    thread = ThreadsDB.create_thread(
        title=thread_data.title,
        metadata=thread_data.metadata
    )
    return thread


@app.get("/threads", response_model=List[Thread])
async def list_threads(limit: int = 50, offset: int = 0):
    """List all conversation threads."""
    threads = ThreadsDB.list_threads(limit=limit, offset=offset)
    return threads


@app.get("/threads/{thread_id}", response_model=Thread)
async def get_thread(thread_id: str):
    """Get a specific thread by ID."""
    thread = ThreadsDB.get_thread(thread_id)
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")
    return thread


@app.delete("/threads/{thread_id}")
async def delete_thread(thread_id: str):
    """Delete a thread and its messages."""
    thread = ThreadsDB.get_thread(thread_id)
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")
    
    ThreadsDB.delete_thread(thread_id)
    return {"success": True, "message": "Thread deleted"}


# ==================== Message Endpoints ====================

@app.get("/threads/{thread_id}/messages", response_model=List[Message])
async def list_messages(thread_id: str, limit: int = 100, offset: int = 0):
    """List all messages in a thread."""
    # Verify thread exists
    thread = ThreadsDB.get_thread(thread_id)
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")
    
    messages = MessagesDB.list_messages(thread_id, limit=limit, offset=offset)
    return messages


# ==================== Chat Endpoint ====================

@app.post("/chat")
async def chat(request: ChatRequest):
    """
    Send a message and get agent response.
    Creates a new thread if thread_id is not provided.
    """
    agent = get_agent()
    
    # Create or get thread
    if request.thread_id:
        thread = ThreadsDB.get_thread(request.thread_id)
        if not thread:
            raise HTTPException(status_code=404, detail="Thread not found")
        thread_id = request.thread_id
    else:
        thread = ThreadsDB.create_thread(title="New conversation")
        thread_id = thread["id"]
    
    # Run agent conversation
    try:
        result = await agent.run_conversation(thread_id, request.message)
        
        if not result["success"]:
            raise HTTPException(status_code=500, detail=result.get("error", "Agent execution failed"))
        
        # Get user message (last message before assistant response)
        messages = MessagesDB.list_messages(thread_id)
        user_msg = None
        for msg in reversed(messages):
            if msg["role"] == "user":
                user_msg = msg
                break
        
        return {
            "thread_id": thread_id,
            "message": user_msg,
            "assistant_message": result["message"]
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ==================== Pinned Memory Endpoints ====================

@app.get("/pinned-memory", response_model=List[Memory])
async def list_memories():
    """List all pinned memory entries."""
    memories = MemoryDB.list_memories()
    return memories


@app.get("/pinned-memory/{key}", response_model=Memory)
async def get_memory(key: str):
    """Get a specific pinned memory entry."""
    memory = MemoryDB.get_memory(key)
    if not memory:
        raise HTTPException(status_code=404, detail="Memory not found")
    return memory


@app.post("/pinned-memory", response_model=Memory)
async def create_or_update_memory(memory_data: MemoryCreate):
    """Create or update a pinned memory entry."""
    memory = MemoryDB.create_or_update_memory(
        key=memory_data.key,
        value=memory_data.value,
        description=memory_data.description
    )
    return memory


@app.delete("/pinned-memory/{key}")
async def delete_memory(key: str):
    """Delete a pinned memory entry."""
    memory = MemoryDB.get_memory(key)
    if not memory:
        raise HTTPException(status_code=404, detail="Memory not found")
    
    MemoryDB.delete_memory(key)
    return {"success": True, "message": "Memory deleted"}


# ==================== Audit Log Endpoints ====================

@app.get("/audit-log")
async def list_audit_logs(thread_id: Optional[str] = None, limit: int = 100, offset: int = 0):
    """List audit log entries, optionally filtered by thread."""
    logs = AuditDB.list_logs(thread_id=thread_id, limit=limit, offset=offset)
    return logs


# ==================== Settings Endpoints ====================

@app.get("/settings", response_model=Settings)
async def get_settings():
    """Get current settings."""
    api_key = os.getenv("OPENAI_API_KEY", "")
    model_name = os.getenv("MODEL_NAME", "gpt-4o")
    
    return {
        "model_name": model_name,
        "has_api_key": bool(api_key)
    }


@app.post("/settings")
async def update_settings(settings: SettingsUpdate):
    """
    Update settings (server-side only, not persisted to .env).
    Note: This only updates runtime settings, not the .env file.
    """
    if settings.openai_api_key:
        os.environ["OPENAI_API_KEY"] = settings.openai_api_key
        # Reinitialize agent with new API key
        init_agent(api_key=settings.openai_api_key)
    
    if settings.model_name:
        os.environ["MODEL_NAME"] = settings.model_name
        # Reinitialize agent with new model
        init_agent(model_name=settings.model_name)
    
    return {"success": True, "message": "Settings updated"}


# ==================== Tools Endpoint ====================

@app.get("/tools")
async def list_tools():
    """List all available tools."""
    from tools import get_registry
    registry = get_registry()
    tools = registry.list_tools()
    
    return [
        {
            "name": tool.name,
            "description": tool.description,
            "parameters": tool.parameters,
            "metadata": tool.metadata
        }
        for tool in tools
    ]


if __name__ == "__main__":
    import uvicorn
    host = os.getenv("SERVER_HOST", "127.0.0.1")
    port = int(os.getenv("SERVER_PORT", "8000"))
    uvicorn.run(app, host=host, port=port)
