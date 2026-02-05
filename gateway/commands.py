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
        await handle_sessions_command(session_id, args, websocket, connection_manager)
    
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
• `/sessions` - List sessions, then type a number to switch
• `/sessions 2` or `/sessions page 2` - Show page 2
• `/sessions next` / `/sessions prev` - Navigate pages
• `/sessions search <keyword>` - Search sessions
• `/status` - Show current session info
• `/help` - Show this help message

**Tip:** After `/sessions`, just type a number to switch!
Example: `/sessions` → `2` → switches to session #2

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
    from runtime import get_runtime
    r = get_runtime()
    new_session = await r.create_session()
    new_session_id = new_session["id"]
    connection_manager.switch_client_session(websocket, new_session_id)
    await send_session_changed_event(
        new_session_id,
        websocket,
        connection_manager,
        message=f"✓ Created new conversation"
    )


async def handle_sessions_command(
    session_id: str,
    args: list,
    websocket: WebSocket,
    connection_manager: ConnectionManager
):
    """List recent sessions with pagination and search."""
    from runtime import get_runtime
    from datetime import datetime
    from math import ceil

    r = get_runtime()
    per_page = 9
    page = 1
    query = None
    last_page, last_query = connection_manager.get_sessions_state(websocket)

    if args:
        head = args[0].lower()
        if head == "next":
            page = last_page + 1
            query = last_query
        elif head == "prev":
            page = max(1, last_page - 1)
            query = last_query
        elif head == "page" and len(args) > 1 and args[1].isdigit():
            page = max(1, int(args[1]))
        elif head == "search":
            if len(args) < 2:
                message = "Usage: `/sessions search <keyword>`"
                await send_command_response(session_id, message, connection_manager)
                return
            if args[-1].isdigit() and len(args) > 2:
                page = max(1, int(args[-1]))
                query = " ".join(args[1:-1])
            else:
                query = " ".join(args[1:])
        elif head.isdigit():
            page = max(1, int(head))
        else:
            message = "Usage: `/sessions` | `/sessions 2` (page 2) | `/sessions page 2` | `/sessions next` | `/sessions prev` | `/sessions search <keyword>`"
            await send_command_response(session_id, message, connection_manager)
            return

    offset = (page - 1) * per_page

    if query:
        all_sessions = await r.list_sessions(limit=500, offset=0)
        q = query.lower()
        sessions = [s for s in all_sessions if q in (s.get("id") or "").lower() or q in (s.get("title") or "").lower()]
        total = len(sessions)
        sessions = sessions[offset : offset + per_page]
        header = f"📋 **Sessions matching:** `{query}`"
    else:
        total = await r.count_sessions()
        sessions = await r.list_sessions(limit=per_page, offset=offset)
        header = "📋 **Recent Sessions:**"

    total_pages = max(1, ceil(total / per_page)) if total > 0 else 1
    if page > total_pages:
        page = total_pages
        offset = (page - 1) * per_page
        if query:
            all_sessions = await r.list_sessions(limit=500, offset=0)
            q = query.lower()
            sessions = [s for s in all_sessions if q in (s.get("id") or "").lower() or q in (s.get("title") or "").lower()]
            sessions = sessions[offset : offset + per_page]
        else:
            sessions = await r.list_sessions(limit=per_page, offset=offset)
    
    if not sessions:
        if query:
            message = f"{header}\n\nNo sessions found."
        else:
            message = f"{header}\n\nNo sessions found. This is your first conversation!"
        await send_command_response(session_id, message, connection_manager)
        return
    
    lines = [header, f"\nPage {page}/{total_pages} • {total} total\n"]

    for idx, sess in enumerate(sessions, 1 + offset):
        sess_id = sess["id"]
        try:
            updated = datetime.fromisoformat((sess.get("updated_at") or "").replace("Z", "+00:00"))
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
        except Exception:
            time_str = "unknown"
        title = sess.get("title") or sess_id or "Untitled"
        current_marker = " ← current" if sess_id == session_id else ""
        lines.append(f"{idx}. **{title}** • {time_str}{current_marker}")
    
    lines.append("\nType a number to switch (e.g., just `2` for session #2)")
    lines.append("Use `/sessions next` or `/sessions prev` to navigate pages.")
    message = "\n".join(lines)
    
    # Persist pagination state
    connection_manager.set_sessions_state(websocket, page, query)
    
    # Set last command for context-aware session switching
    connection_manager.set_last_command(websocket, "sessions")
    
    await send_command_response(session_id, message, connection_manager)


async def handle_session_switch_command(
    session_id: str,
    args: list,
    websocket: WebSocket,
    connection_manager: ConnectionManager
):
    """Switch to a different session."""
    from runtime import get_runtime
    r = get_runtime()

    if not args:
        message = "Usage: `/switch <number>` or type a number after `/sessions`"
        await send_command_response(session_id, message, connection_manager)
        return

    target = args[0]
    if target.isdigit():
        idx = int(target) - 1
        if idx < 0:
            message = f"❌ Invalid session number: {target}\n\nUse `/sessions` to see available sessions."
            await send_command_response(session_id, message, connection_manager)
            return
        sessions = await r.list_sessions(limit=1, offset=idx)
        if not sessions:
            message = f"❌ Invalid session number: {target}\n\nUse `/sessions` to see available sessions."
            await send_command_response(session_id, message, connection_manager)
            return
        target_session_id = sessions[0]["id"]
    else:
        target_session = await r.get_session(target)
        if not target_session:
            message = f"❌ Session not found: {target}"
            await send_command_response(session_id, message, connection_manager)
            return
        target_session_id = target_session["id"]

    connection_manager.switch_client_session(websocket, target_session_id)
    await send_session_changed_event(
        target_session_id,
        websocket,
        connection_manager
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
    from runtime import get_runtime
    r = get_runtime()
    model_info = r.get_model_info()
    session = await r.get_session(session_id)
    msg_count = session.get("message_count") if session else 0
    if session is None:
        session = await r.get_or_create_session(session_id)
    state = getattr(r, "state_cache", None)
    if state:
        s = await state.load_state(session_id)
        msg_count = s.message_count if s else 0
    message = f"""📊 **Session Status:**

**Session ID:** `{session_id[:20]}...` (truncated)
**Messages:** {msg_count}
**Model:** {model_info.get("model_name", "gpt-4o")}
**Context limit:** {model_info.get("context_limit", "?")}

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
    """Send session_changed event to a specific websocket."""
    from runtime import get_runtime
    r = get_runtime()
    session = await r.get_or_create_session(new_session_id)
    try:
        history_limit = connection_manager.get_history_limit(websocket)
    except AttributeError:
        history_limit = None
    if history_limit == 0:
        messages = []
    elif history_limit is None:
        messages = await r.load_messages(new_session_id, limit=10000, offset=0)
    else:
        messages = await r.load_messages(new_session_id, limit=history_limit, offset=0)
    total_chars = sum(len(str(m.get("content", ""))) for m in messages)
    estimated_tokens = total_chars // 4
    model_info = r.get_model_info()
    model_name = model_info["model_name"]
    token_limit = model_info["context_limit"]
    event = create_event(
        event_type=EventType.SESSION_CHANGED,
        payload={
            "sessionId": new_session_id,
            "title": session.get("title", "New conversation"),
            "createdAt": session.get("created_at"),
            "updatedAt": session.get("updated_at"),
            "messages": [
                {"id": m["id"], "role": m["role"], "content": m["content"], "timestamp": m.get("created_at", "")}
                for m in messages
            ],
            "stats": {
                "messageCount": len(messages),
                "modelName": model_name,
                "tokensUsed": estimated_tokens,
                "tokensLimit": token_limit
            },
            "message": message
        }
    )
    
    # Send only to this specific websocket
    try:
        await websocket.send_json(event)
        logger.info(f"Sent session_changed to client: {new_session_id[:8]}...")
    except Exception as e:
        logger.error(f"Failed to send session_changed: {e}")
