"""
Agent Blob Gateway - WebSocket-based universal gateway.

This is the main entry point for all clients (Web UI, CLI, Telegram).
"""
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
import os
import json
import logging
from dotenv import load_dotenv

from .protocol import Request, Response, create_response
from .connections import ConnectionManager
from .queue import SessionQueue

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="Agent Blob Gateway",
    description="Universal WebSocket gateway for multi-client agent system",
    version="0.1.1"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://100.117.142.1:3000",  # Tailscale
        "http://*.ts.net:3000",
        "https://*.ts.net:3000",
    ],
    allow_origin_regex=r"https?://(100\.\d{1,3}\.\d{1,3}\.\d{1,3}|.*\.ts\.net)(:\d+)?",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global managers
connection_manager = ConnectionManager()
session_queue = SessionQueue()

# Import runtime (will be created in next steps)
# from runtime import AgentRuntime
# runtime = AgentRuntime()


@app.on_event("startup")
async def startup_event():
    """Initialize on startup."""
    logger.info("Agent Blob Gateway starting up...")
    logger.info(f"Gateway version: 0.1.1")
    
    # Initialize database
    from runtime.db import init_db
    db_path = os.getenv("DB_PATH", "./data/agent_blob.db")
    init_db(db_path)
    logger.info(f"Database initialized at {db_path}")
    
    # Initialize runtime
    from runtime import init_runtime
    init_runtime()
    logger.info("Agent runtime initialized")


@app.get("/")
async def root():
    """Health check endpoint."""
    return {
        "service": "Agent Blob Gateway",
        "version": "0.1.1",
        "status": "ok"
    }


@app.get("/health")
async def health():
    """Detailed health check."""
    return {
        "status": "ok",
        "connections": connection_manager.get_stats(),
        "queue": session_queue.get_stats()
    }


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """
    Main WebSocket endpoint for all clients.
    
    Protocol:
    1. Client connects
    2. Client sends 'connect' request (MUST be first frame)
    3. Gateway validates and responds
    4. Client can send other requests
    5. Gateway streams events back
    """
    await websocket.accept()
    logger.info(f"WebSocket connection accepted from {websocket.client}")
    
    session_id = None
    client_type = "unknown"
    
    try:
        # FIRST FRAME MUST BE CONNECT
        data = await websocket.receive_json()
        
        try:
            request = Request(**data)
        except Exception as e:
            error_response = {
                "type": "res",
                "id": data.get("id", "unknown"),
                "ok": False,
                "error": f"Invalid request format: {str(e)}"
            }
            await websocket.send_json(error_response)
            await websocket.close()
            return
        
        if request.method != "connect":
            error_response = create_response(
                request_id=request.id,
                ok=False,
                error="First frame must be 'connect' request"
            )
            await websocket.send_json(error_response)
            await websocket.close()
            return
        
        # Handle connect request
        client_type = request.params.get("clientType", "unknown")
        protocol_version = request.params.get("version", "1")
        
        if protocol_version != "1":
            error_response = create_response(
                request_id=request.id,
                ok=False,
                error=f"Unsupported protocol version: {protocol_version}. Supported: 1"
            )
            await websocket.send_json(error_response)
            await websocket.close()
            return
        
        # Gateway decides which session to assign (always most recent, or create first)
        from runtime.db.sessions import SessionsDB
        from runtime.db.messages import MessagesDB
        
        sessions = SessionsDB.list_sessions(limit=1, offset=0)
        if sessions:
            session_id = sessions[0]["id"]
            logger.info(f"Connected to most recent session: {session_id[:8]}...")
        else:
            # No sessions exist, create the first one
            session = SessionsDB.create_session(title="New conversation")
            session_id = session["id"]
            logger.info(f"Created first session: {session_id[:8]}...")
        
        # Add client to connection manager
        connection_manager.add_client(session_id, websocket, client_type)
        
        # Send success response
        connect_response = create_response(
            request_id=request.id,
            ok=True,
            payload={
                "gatewayVersion": "0.1.1",
                "supportedMethods": [
                    "agent",
                    "agent.cancel",
                    "sessions.list",
                    "sessions.history",
                    "status"
                ]
            }
        )
        await websocket.send_json(connect_response)
        
        logger.info(f"Client connected: type={client_type}, session={session_id[:8]}...")
        
        # Send initial session_changed event with session info and message history
        session = SessionsDB.get_session(session_id)
        messages = MessagesDB.list_messages(session_id, limit=50, offset=0)
        
        from .protocol import EventType, create_event
        session_event = create_event(
            event_type=EventType.SESSION_CHANGED,
            payload={
                "sessionId": session_id,
                "title": session.get("title", "New conversation"),
                "createdAt": session.get("created_at"),
                "updatedAt": session.get("updated_at"),
                "messages": [
                    {
                        "id": msg["id"],
                        "role": msg["role"],
                        "content": msg["content"],
                        "timestamp": msg["created_at"]
                    }
                    for msg in messages
                ]
            }
        )
        await websocket.send_json(session_event)
        
        # Handle subsequent messages
        while True:
            data = await websocket.receive_json()
            
            try:
                request = Request(**data)
                
                # Get current session for this client (may have changed via /switch command)
                current_session = connection_manager.get_client_session(websocket)
                if not current_session:
                    # Fallback to initial session if not found
                    current_session = session_id
                
                # Route to appropriate handler
                from .handlers import handle_request
                await handle_request(
                    request=request,
                    websocket=websocket,
                    session_id=current_session,
                    connection_manager=connection_manager,
                    session_queue=session_queue
                )
                
            except Exception as e:
                logger.error(f"Error handling request: {e}")
                error_response = create_response(
                    request_id=data.get("id", "unknown"),
                    ok=False,
                    error=str(e)
                )
                await websocket.send_json(error_response)
    
    except WebSocketDisconnect:
        logger.info(f"Client disconnected: type={client_type}, session={session_id[:8] if session_id else 'unknown'}...")
    
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
    
    finally:
        # Clean up connection
        if websocket in connection_manager.ws_to_client:
            connection_manager.remove_client(websocket)


if __name__ == "__main__":
    import uvicorn
    host = os.getenv("GATEWAY_HOST", "127.0.0.1")
    port = int(os.getenv("GATEWAY_PORT", "3336"))
    
    logger.info(f"Starting gateway on {host}:{port}")
    uvicorn.run(app, host=host, port=port)
