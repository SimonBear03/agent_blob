"""
Session management tools for the LLM.

These tools allow the agent to search, list, and navigate sessions.
"""
from typing import Optional
from . import ToolDefinition, ToolRegistry
from ..db.sessions import SessionsDB
from ..db.messages import MessagesDB


async def sessions_search(query: str, limit: int = 10) -> dict:
    """
    Search sessions by title or content.
    
    Args:
        query: Search query string
        limit: Maximum number of results (default: 10)
    
    Returns:
        dict with sessions array and total count
    """
    sessions = SessionsDB.search_sessions(query, limit=limit)
    
    formatted_sessions = []
    for session in sessions:
        formatted_sessions.append({
            "id": session["id"],
            "title": session["title"] or "Untitled conversation",
            "updated_at": session["updated_at"],
            "relevance": "high"  # TODO: Implement relevance scoring
        })
    
    return {
        "success": True,
        "sessions": formatted_sessions,
        "total": len(formatted_sessions),
        "query": query
    }


async def sessions_list(limit: int = 10, offset: int = 0) -> dict:
    """
    List recent sessions sorted by activity.
    
    Args:
        limit: Maximum number of sessions to return (default: 10)
        offset: Offset for pagination (default: 0)
    
    Returns:
        dict with sessions array and total count
    """
    sessions = SessionsDB.get_sessions_with_stats(limit=limit, offset=offset)
    
    formatted_sessions = []
    for session in sessions:
        formatted_sessions.append({
            "id": session["id"],
            "title": session["title"] or "Untitled conversation",
            "message_count": session.get("message_count", 0),
            "last_activity": session.get("last_activity") or session["updated_at"],
            "last_message": session.get("last_message", "")[:100] if session.get("last_message") else ""
        })
    
    return {
        "success": True,
        "sessions": formatted_sessions,
        "total": len(formatted_sessions),
        "offset": offset
    }


async def sessions_get(session_id: str, include_messages: bool = False, message_limit: int = 20) -> dict:
    """
    Get detailed information about a specific session.
    
    Args:
        session_id: UUID of the session
        include_messages: Whether to include recent messages (default: False)
        message_limit: Number of recent messages to include (default: 20)
    
    Returns:
        dict with session details and optionally messages
    """
    session = SessionsDB.get_session_with_message_count(session_id)
    
    if not session:
        return {
            "success": False,
            "error": f"Session not found: {session_id}"
        }
    
    result = {
        "success": True,
        "session": {
            "id": session["id"],
            "title": session["title"] or "Untitled conversation",
            "created_at": session["created_at"],
            "updated_at": session["updated_at"],
            "message_count": session.get("message_count", 0),
            "last_message_at": session.get("last_message_at")
        }
    }
    
    if include_messages:
        messages = MessagesDB.list_messages(session_id, limit=message_limit)
        result["session"]["recent_messages"] = [
            {
                "role": msg["role"],
                "content": msg["content"][:200] if len(msg["content"]) > 200 else msg["content"],
                "created_at": msg["created_at"]
            }
            for msg in messages
        ]
    
    return result


def register_tools(registry: ToolRegistry):
    """Register session management tools."""
    
    # sessions.search
    registry.register(ToolDefinition(
        name="sessions_search",
        description="Search for sessions by keywords in title or content. Use this when the user asks to find conversations about a specific topic.",
        parameters={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query (keywords to search for in session titles and content)"
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of results to return (default: 10)",
                    "default": 10
                }
            },
            "required": ["query"]
        },
        executor=sessions_search
    ))
    
    # sessions.list
    registry.register(ToolDefinition(
        name="sessions_list",
        description="List recent sessions sorted by last activity. Use this when the user asks to see their recent conversations or sessions.",
        parameters={
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of sessions to return (default: 10)",
                    "default": 10
                },
                "offset": {
                    "type": "integer",
                    "description": "Offset for pagination (default: 0)",
                    "default": 0
                }
            },
            "required": []
        },
        executor=sessions_list
    ))
    
    # sessions.get
    registry.register(ToolDefinition(
        name="sessions_get",
        description="Get detailed information about a specific session, including optionally its recent messages.",
        parameters={
            "type": "object",
            "properties": {
                "session_id": {
                    "type": "string",
                    "description": "UUID of the session to retrieve"
                },
                "include_messages": {
                    "type": "boolean",
                    "description": "Whether to include recent messages (default: false)",
                    "default": False
                },
                "message_limit": {
                    "type": "integer",
                    "description": "Number of recent messages to include if include_messages is true (default: 20)",
                    "default": 20
                }
            },
            "required": ["session_id"]
        },
        executor=sessions_get
    ))
