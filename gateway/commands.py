"""
Gateway command processing for /new, /sessions, /status, etc.
"""
from fastapi import WebSocket
from typing import Optional
import logging

from .protocol import EventType, create_event
from .connections import ConnectionManager

logger = logging.getLogger(__name__)


async def handle_command(
    command: str,
    session_id: str,
    websocket: WebSocket,
    connection_manager: ConnectionManager
):
    """
    Process gateway commands.
    
    Commands are messages that start with / and are processed by the gateway
    instead of being sent to the agent.
    """
    command = command.strip()
    parts = command.split()
    cmd = parts[0].lower()
    args = parts[1:] if len(parts) > 1 else []
    
    if cmd == "/help":
        await handle_help_command(session_id, connection_manager)
    
    elif cmd == "/new":
        await handle_new_command(session_id, websocket, connection_manager)
    
    elif cmd == "/sessions":
        await handle_sessions_command(session_id, connection_manager)
    
    elif cmd == "/switch" or cmd == "/session":
        await handle_session_switch_command(session_id, args, websocket, connection_manager)
    
    elif cmd == "/history":
        count = int(args[0]) if args and args[0].isdigit() else 20
        await handle_history_command(session_id, count, connection_manager)
    
    elif cmd == "/status":
        await handle_status_command(session_id, connection_manager)
    
    else:
        # Unknown command
        message = f"Unknown command: {cmd}\n\nType /help for available commands."
        await send_command_response(session_id, message, connection_manager)


async def handle_help_command(session_id: str, connection_manager: ConnectionManager):
    """Show available commands."""
    help_text = """**Available Commands:**

**Session Management:**
• `/new` - Create new conversation
• `/sessions` - List recent sessions
• `/switch <number>` - Switch to a session from the list
• `/status` - Show current session info
• `/help` - Show this help message

**Natural Language:**
You can also ask the agent naturally:
• "Show me conversations about Python"
• "What did we discuss in our last conversation?"
• "Search for sessions about databases"
"""
    await send_command_response(session_id, help_text, connection_manager)


async def handle_new_command(
    session_id: str,
    websocket: WebSocket,
    connection_manager: ConnectionManager
):
    """Create a new session and switch to it."""
    from runtime.db.sessions import SessionsDB
    import uuid
    
    # Create new session in database
    new_session = SessionsDB.create_session(title="New conversation")
    new_session_id = new_session["id"]
    
    # Switch this client to the new session
    connection_manager.switch_client_session(websocket, new_session_id)
    
    # Send session_changed event
    await send_session_changed_event(
        new_session_id,
        websocket,
        connection_manager,
        message=f"✓ Created new conversation"
    )


async def handle_sessions_command(session_id: str, connection_manager: ConnectionManager):
    """List recent sessions."""
    from runtime.db.sessions import SessionsDB
    from runtime.db.messages import MessagesDB
    from datetime import datetime
    import sqlite3
    
    # Get recent sessions from database (limit to 9 for display)
    sessions = SessionsDB.list_sessions(limit=9, offset=0)
    
    if not sessions:
        message = """📋 **Recent Sessions:**

No sessions found. This is your first conversation!"""
    else:
        lines = ["📋 **Recent Sessions:**\n"]
        
        # Get message counts for all sessions in one query (more efficient)
        from runtime.db import get_db
        conn = get_db().get_connection()
        cursor = conn.cursor()
        
        for idx, sess in enumerate(sessions, 1):
            sess_id = sess["id"]
            
            # Get actual message count
            cursor.execute("SELECT COUNT(*) FROM messages WHERE session_id = ?", (sess_id,))
            msg_count = cursor.fetchone()[0]
            
            # Format time
            try:
                updated = datetime.fromisoformat(sess["updated_at"].replace("Z", "+00:00"))
                now = datetime.utcnow()
                delta = now - updated.replace(tzinfo=None)
                
                if delta.total_seconds() < 60:
                    time_str = "just now"
                elif delta.total_seconds() < 3600:
                    time_str = f"{int(delta.total_seconds() // 60)}m ago"
                elif delta.days == 0:
                    time_str = f"{int(delta.total_seconds() // 3600)}h ago"
                elif delta.days == 1:
                    time_str = "yesterday"
                else:
                    time_str = f"{delta.days}d ago"
            except:
                time_str = "unknown"
            
            title = sess["title"] or "Untitled"
            current_marker = " ← current" if sess_id == session_id else ""
            lines.append(f"{idx}. **{title}** • {msg_count} messages • {time_str}{current_marker}")
        
        conn.close()
        
        lines.append("\nType `/switch <number>` to switch sessions (e.g., `/switch 2`)")
        message = "\n".join(lines)
    
    await send_command_response(session_id, message, connection_manager)


async def handle_session_switch_command(
    session_id: str,
    args: list,
    websocket: WebSocket,
    connection_manager: ConnectionManager
):
    """Switch to a different session."""
    from runtime.db.sessions import SessionsDB
    
    if not args:
        message = "Usage: `/switch <number>` or `/switch <uuid>`"
        await send_command_response(session_id, message, connection_manager)
        return
    
    target = args[0]
    
    # Determine if it's a number (index) or UUID
    if target.isdigit():
        # Switch by index
        idx = int(target) - 1  # Convert to 0-based
        sessions = SessionsDB.list_sessions(limit=10, offset=0)
        
        if idx < 0 or idx >= len(sessions):
            message = f"❌ Invalid session number: {target}\n\nUse `/sessions` to see available sessions."
            await send_command_response(session_id, message, connection_manager)
            return
        
        target_session = sessions[idx]
        target_session_id = target_session["id"]
    else:
        # Switch by UUID
        target_session = SessionsDB.get_session(target)
        if not target_session:
            message = f"❌ Session not found: {target}"
            await send_command_response(session_id, message, connection_manager)
            return
        target_session_id = target_session["id"]
    
    # Switch this client to the target session
    connection_manager.switch_client_session(websocket, target_session_id)
    
    # Send session_changed event
    await send_session_changed_event(
        target_session_id,
        websocket,
        connection_manager,
        message=f"✓ Switched to: {target_session.get('title', 'Untitled')}"
    )


async def handle_history_command(
    session_id: str,
    count: int,
    connection_manager: ConnectionManager
):
    """Show session history."""
    # TODO: Load messages from database
    
    message = f"""📜 **Last {count} messages:**

[Messages would be displayed here]

Use `/history 50` for more messages."""
    
    await send_command_response(session_id, message, connection_manager)


async def handle_status_command(session_id: str, connection_manager: ConnectionManager):
    """Show session status."""
    # TODO: Get actual session stats from database
    
    message = f"""📊 **Session Status:**

**Session ID:** `{session_id[:8]}...`
**Messages:** 42
**Model:** gpt-4o
**Queue:** Empty
**Active processes:** None

Use `/sessions` to see all conversations."""
    
    await send_command_response(session_id, message, connection_manager)


async def send_command_response(
    session_id: str,
    message: str,
    connection_manager: ConnectionManager
):
    """Send command response as a system message event."""
    import uuid
    from datetime import datetime
    
    event = create_event(
        event_type=EventType.MESSAGE,
        payload={
            "role": "system",
            "content": message,
            "messageId": f"msg_{uuid.uuid4().hex[:16]}",
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }
    )
    
    await connection_manager.broadcast_to_session(
        session_id=session_id,
        event=event
    )


async def send_session_changed_event(
    new_session_id: str,
    websocket: WebSocket,
    connection_manager: ConnectionManager,
    message: Optional[str] = None
):
    """
    Send session_changed event to a specific websocket.
    
    This tells the client that their view has switched to a different session.
    Includes the new session info and recent message history.
    """
    from runtime.db.sessions import SessionsDB
    from runtime.db.messages import MessagesDB
    
    # Get session info
    session = SessionsDB.get_session(new_session_id)
    if not session:
        logger.error(f"Cannot send session_changed: session {new_session_id} not found")
        return
    
    # Get recent messages
    messages = MessagesDB.list_messages(new_session_id, limit=50, offset=0)
    
    # Estimate token usage for context window (rough: 1 token ~= 4 chars)
    total_chars = sum(len(msg.get("content", "")) for msg in messages)
    estimated_tokens = total_chars // 4
    
    # Get model and context limit from runtime (single source of truth)
    from runtime.runtime import get_runtime
    runtime = get_runtime()
    model_info = runtime.get_model_info()
    model_name = model_info["model_name"]
    token_limit = model_info["context_limit"]
    
    # Build event
    event = create_event(
        event_type=EventType.SESSION_CHANGED,
        payload={
            "sessionId": new_session_id,
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
            ],
            "stats": {
                "messageCount": len(messages),
                "modelName": model_name,
                "tokensUsed": estimated_tokens,
                "tokensLimit": token_limit
            },
            "message": message  # Optional status message
        }
    )
    
    # Send only to this specific websocket
    try:
        await websocket.send_json(event)
        logger.info(f"Sent session_changed to client: {new_session_id[:8]}...")
    except Exception as e:
        logger.error(f"Failed to send session_changed: {e}")
