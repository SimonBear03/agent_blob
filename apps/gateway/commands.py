"""
Gateway command processing for /new, /sessions, /status, etc.
"""
from fastapi import WebSocket
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
        await handle_new_command(session_id, connection_manager)
    
    elif cmd == "/sessions":
        await handle_sessions_command(session_id, connection_manager)
    
    elif cmd == "/session":
        await handle_session_switch_command(session_id, args, connection_manager)
    
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
• `/new` - Create new session and switch to it
• `/sessions` - List recent sessions (sorted by activity)
• `/session <number>` - Switch to a session from the list
• `/session <uuid>` - Switch to a specific session by ID
• `/history [count]` - Show last N messages (default: 20)

**Status & Info:**
• `/status` - Show current session status
• `/help` - Show this help message

**Natural Language:**
You can also ask the agent naturally:
• "Show me sessions about AI"
• "Switch to my conversation from yesterday"
• "What processes are running?"
"""
    await send_command_response(session_id, help_text, connection_manager)


async def handle_new_command(session_id: str, connection_manager: ConnectionManager):
    """Create a new session."""
    import uuid
    from datetime import datetime
    
    new_session_id = str(uuid.uuid4())
    
    # TODO: Create session in database
    
    message = f"""✓ Created new session: `{new_session_id[:8]}...`

You can switch back to this conversation anytime with:
`/session {new_session_id}`

Or use `/sessions` to see all your conversations."""
    
    await send_command_response(session_id, message, connection_manager)


async def handle_sessions_command(session_id: str, connection_manager: ConnectionManager):
    """List recent sessions."""
    # TODO: Query database for recent sessions
    
    # Placeholder response
    message = """📋 **Recent Sessions:**

1. [2 min ago] AI architecture discussion `550e8400...`
2. [yesterday] Python async patterns `6ba7b810...`
3. [3 days ago] Project planning `7c9e6679...`

Reply with `/session <number>` to switch (e.g., `/session 2`)

Or ask naturally: "Show me sessions about AI" """
    
    await send_command_response(session_id, message, connection_manager)


async def handle_session_switch_command(
    session_id: str,
    args: list,
    connection_manager: ConnectionManager
):
    """Switch to a different session."""
    if not args:
        message = "Usage: `/session <number>` or `/session <uuid>`"
        await send_command_response(session_id, message, connection_manager)
        return
    
    target = args[0]
    
    # TODO: Implement actual session switching
    # This requires database query and connection manager updates
    
    message = f"""✓ Switched to session: `{target}`

[Last few messages would be loaded here]

Continue your conversation from where you left off!"""
    
    await send_command_response(session_id, message, connection_manager)


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
    """Send command response as an assistant message event."""
    import uuid
    from datetime import datetime
    
    event = create_event(
        event_type=EventType.MESSAGE,
        payload={
            "role": "assistant",
            "content": message,
            "messageId": f"msg_{uuid.uuid4().hex[:16]}",
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }
    )
    
    await connection_manager.broadcast_to_session(
        session_id=session_id,
        event=event
    )
