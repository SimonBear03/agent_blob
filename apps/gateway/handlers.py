"""
Request handlers for different WebSocket methods.
"""
from fastapi import WebSocket
import uuid
import logging
from typing import Optional

from .protocol import (
    Request, Method, EventType,
    create_response, create_event,
    AgentParams, AgentCancelParams,
    SessionsListParams, SessionsNewParams,
    SessionsSwitchParams, SessionsHistoryParams,
    StatusParams
)
from .connections import ConnectionManager
from .queue import SessionQueue, QueuedRequest

logger = logging.getLogger(__name__)


async def handle_request(
    request: Request,
    websocket: WebSocket,
    session_id: str,
    connection_manager: ConnectionManager,
    session_queue: SessionQueue,
    runtime=None  # Will be passed once runtime is implemented
):
    """Route request to appropriate handler."""
    
    if request.method == Method.AGENT:
        await handle_agent(request, websocket, session_id, connection_manager, session_queue, runtime)
    
    elif request.method == Method.AGENT_CANCEL:
        await handle_agent_cancel(request, websocket, session_id, connection_manager, session_queue)
    
    elif request.method == Method.SESSIONS_LIST:
        await handle_sessions_list(request, websocket)
    
    elif request.method == Method.SESSIONS_NEW:
        await handle_sessions_new(request, websocket)
    
    elif request.method == Method.SESSIONS_SWITCH:
        await handle_sessions_switch(request, websocket, connection_manager)
    
    elif request.method == Method.SESSIONS_HISTORY:
        await handle_sessions_history(request, websocket)
    
    elif request.method == Method.STATUS:
        await handle_status(request, websocket, session_id, connection_manager, session_queue)
    
    else:
        # Unknown method
        response = create_response(
            request_id=request.id,
            ok=False,
            error=f"Unknown method: {request.method}"
        )
        await websocket.send_json(response)


async def handle_agent(
    request: Request,
    websocket: WebSocket,
    session_id: str,
    connection_manager: ConnectionManager,
    session_queue: SessionQueue,
    runtime=None
):
    """Handle agent message request."""
    try:
        params = AgentParams(**request.params)
    except Exception as e:
        response = create_response(request.id, False, error=f"Invalid parameters: {e}")
        await websocket.send_json(response)
        return
    
    message = params.message
    
    # Check if message is a command
    if message.startswith("/"):
        from .commands import handle_command
        await handle_command(message, session_id, websocket, connection_manager)
        response = create_response(request.id, True, payload={"status": "command_processed"})
        await websocket.send_json(response)
        return
    
    # Generate run_id
    run_id = f"run_{uuid.uuid4().hex[:16]}"
    
    # Create queued request
    queued_request = QueuedRequest(
        request_id=request.id,
        run_id=run_id,
        session_id=session_id,
        message=message,
        websocket=websocket
    )
    
    # Enqueue request
    position = session_queue.enqueue(queued_request)
    
    # Send immediate response
    status = "queued" if position > 1 else "accepted"
    response = create_response(
        request_id=request.id,
        ok=True,
        payload={"runId": run_id, "status": status}
    )
    await websocket.send_json(response)
    
    # If queued, send queued event
    if position > 1:
        queued_event = create_event(
            event_type=EventType.QUEUED,
            payload={
                "requestId": request.id,
                "position": position,
                "message": f"Message queued (position {position})"
            }
        )
        await connection_manager.broadcast_to_session(
            session_id=session_id,
            event=queued_event
        )
    
    # Echo user message to all clients
    from datetime import datetime
    message_event = create_event(
        event_type=EventType.MESSAGE,
        payload={
            "role": "user",
            "content": message,
            "messageId": f"msg_{uuid.uuid4().hex[:16]}",
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "fromSelf": True  # Will be formatted per client by connection_manager
        }
    )
    await connection_manager.broadcast_to_session(
        session_id=session_id,
        event=message_event,
        sender_ws=websocket
    )
    
    # Start processing queue if not already processing
    if not session_queue.is_processing(session_id):
        # Get runtime and start processing
        from agent_runtime import get_runtime
        runtime_instance = get_runtime()
        await session_queue.start_processing(session_id, connection_manager, runtime_instance)


async def handle_agent_cancel(
    request: Request,
    websocket: WebSocket,
    session_id: str,
    connection_manager: ConnectionManager,
    session_queue: SessionQueue
):
    """Handle cancellation request."""
    try:
        params = AgentCancelParams(**request.params)
    except Exception as e:
        response = create_response(request.id, False, error=f"Invalid parameters: {e}")
        await websocket.send_json(response)
        return
    
    # Attempt to cancel the request
    cancelled = session_queue.cancel_request(params.runId)
    
    if cancelled:
        # Send success response
        response = create_response(
            request_id=request.id,
            ok=True,
            payload={"message": "Cancellation requested"}
        )
        await websocket.send_json(response)
        
        # Broadcast cancelled event
        cancelled_event = create_event(
            event_type=EventType.CANCELLED,
            payload={
                "runId": params.runId,
                "message": "Request cancelled by user"
            }
        )
        await connection_manager.broadcast_to_session(
            session_id=session_id,
            event=cancelled_event
        )
    else:
        response = create_response(
            request_id=request.id,
            ok=False,
            error=f"Request {params.runId} not found"
        )
        await websocket.send_json(response)


async def handle_sessions_list(request: Request, websocket: WebSocket):
    """Handle sessions.list request."""
    try:
        params = SessionsListParams(**request.params)
    except Exception as e:
        response = create_response(request.id, False, error=f"Invalid parameters: {e}")
        await websocket.send_json(response)
        return
    
    # Query database for sessions
    from agent_runtime.db.sessions import SessionsDB
    sessions = SessionsDB.get_sessions_with_stats(limit=params.limit, offset=params.offset)
    
    # Format for response
    formatted_sessions = []
    for session in sessions:
        formatted_sessions.append({
            "id": session["id"],
            "title": session["title"] or "Untitled conversation",
            "lastMessage": session.get("last_message", "")[:100] if session.get("last_message") else "",
            "lastActivity": session.get("last_activity") or session["updated_at"],
            "messageCount": session.get("message_count", 0)
        })
    
    response = create_response(
        request_id=request.id,
        ok=True,
        payload={
            "sessions": formatted_sessions,
            "total": len(formatted_sessions)  # TODO: Get actual total count
        }
    )
    await websocket.send_json(response)


async def handle_sessions_new(request: Request, websocket: WebSocket):
    """Handle sessions.new request."""
    try:
        params = SessionsNewParams(**request.params)
    except Exception as e:
        response = create_response(request.id, False, error=f"Invalid parameters: {e}")
        await websocket.send_json(response)
        return
    
    # Generate new session ID
    from datetime import datetime
    new_session_id = str(uuid.uuid4())
    
    # TODO: Create session in database
    
    response = create_response(
        request_id=request.id,
        ok=True,
        payload={
            "sessionId": new_session_id,
            "title": params.title,
            "createdAt": datetime.utcnow().isoformat() + "Z"
        }
    )
    await websocket.send_json(response)


async def handle_sessions_switch(
    request: Request,
    websocket: WebSocket,
    connection_manager: ConnectionManager
):
    """Handle sessions.switch request."""
    try:
        params = SessionsSwitchParams(**request.params)
    except Exception as e:
        response = create_response(request.id, False, error=f"Invalid parameters: {e}")
        await websocket.send_json(response)
        return
    
    # Load session from database
    from agent_runtime.db.sessions import SessionsDB
    from agent_runtime.db.messages import MessagesDB
    
    session = SessionsDB.get_session(params.sessionId)
    if not session:
        response = create_response(
            request_id=request.id,
            ok=False,
            error=f"Session not found: {params.sessionId}"
        )
        await websocket.send_json(response)
        return
    
    # Load recent messages (last 20)
    messages = MessagesDB.list_messages(params.sessionId, limit=20)
    formatted_messages = [
        {
            "id": msg["id"],
            "role": msg["role"],
            "content": msg["content"],
            "timestamp": msg["created_at"]
        }
        for msg in messages
    ]
    
    response = create_response(
        request_id=request.id,
        ok=True,
        payload={
            "sessionId": params.sessionId,
            "title": session["title"] or "Untitled conversation",
            "recentMessages": formatted_messages
        }
    )
    await websocket.send_json(response)


async def handle_sessions_history(request: Request, websocket: WebSocket):
    """Handle sessions.history request."""
    try:
        params = SessionsHistoryParams(**request.params)
    except Exception as e:
        response = create_response(request.id, False, error=f"Invalid parameters: {e}")
        await websocket.send_json(response)
        return
    
    # Load messages from database
    from agent_runtime.db.messages import MessagesDB
    session_id = params.sessionId
    
    if not session_id:
        response = create_response(request.id, False, error="sessionId required")
        await websocket.send_json(response)
        return
    
    messages = MessagesDB.list_messages(session_id, limit=params.limit)
    
    # Format messages
    formatted_messages = []
    for msg in messages:
        formatted_messages.append({
            "id": msg["id"],
            "role": msg["role"],
            "content": msg["content"],
            "timestamp": msg["created_at"]
        })
    
    response = create_response(
        request_id=request.id,
        ok=True,
        payload={
            "messages": formatted_messages,
            "hasMore": len(messages) == params.limit
        }
    )
    await websocket.send_json(response)


async def handle_status(
    request: Request,
    websocket: WebSocket,
    session_id: str,
    connection_manager: ConnectionManager,
    session_queue: SessionQueue
):
    """Handle status request."""
    try:
        params = StatusParams(**request.params)
    except Exception as e:
        response = create_response(request.id, False, error=f"Invalid parameters: {e}")
        await websocket.send_json(response)
        return
    
    # Get gateway stats
    conn_stats = connection_manager.get_stats()
    queue_stats = session_queue.get_stats()
    
    # TODO: Get uptime
    uptime = 0  # seconds
    
    payload = {
        "gateway": {
            "version": "0.1.1",
            "uptime": uptime,
            "activeConnections": conn_stats["totalConnections"],
            "activeSessions": conn_stats["activeSessions"]
        }
    }
    
    # Add session-specific stats if requested
    target_session = params.sessionId or session_id
    if target_session in queue_stats.get("sessionQueues", {}):
        session_queue_stats = queue_stats["sessionQueues"][target_session]
        payload["session"] = {
            "id": target_session,
            "queuedRequests": session_queue_stats["queued"],
            "processing": session_queue_stats["processing"]
        }
    
    response = create_response(
        request_id=request.id,
        ok=True,
        payload=payload
    )
    await websocket.send_json(response)
