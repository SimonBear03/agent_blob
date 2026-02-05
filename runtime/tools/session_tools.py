"""
Session management tools for the LLM.
Use the runtime's session/store APIs (SessionStore + StateCache).
"""
from . import ToolDefinition, ToolRegistry


async def sessions_search(query: str, limit: int = 10) -> dict:
    """Search sessions by keyword in id/title (simple filter)."""
    from .. import get_runtime
    r = get_runtime()
    sessions = await r.list_sessions(limit=100, offset=0)
    q = (query or "").lower()
    if q:
        sessions = [s for s in sessions if q in (s.get("id") or "").lower() or q in (s.get("title") or "").lower()]
    sessions = sessions[:limit]
    return {
        "success": True,
        "sessions": [{"id": s["id"], "title": s.get("title") or s["id"], "updated_at": s.get("updated_at"), "relevance": "high"} for s in sessions],
        "total": len(sessions),
        "query": query,
    }


async def sessions_list(limit: int = 10, offset: int = 0) -> dict:
    """List recent sessions sorted by activity."""
    from .. import get_runtime
    r = get_runtime()
    sessions = await r.list_sessions(limit=limit, offset=offset)
    return {
        "success": True,
        "sessions": [
            {
                "id": s["id"],
                "title": s.get("title") or s["id"],
                "message_count": 0,
                "last_activity": s.get("updated_at"),
                "last_message": "",
            }
            for s in sessions
        ],
        "total": len(sessions),
        "offset": offset,
    }


async def sessions_get(session_id: str, include_messages: bool = False, message_limit: int = 20) -> dict:
    """Get session details and optionally recent messages."""
    from .. import get_runtime
    r = get_runtime()
    session = await r.get_session(session_id)
    if not session:
        return {"success": False, "error": f"Session not found: {session_id}"}
    result = {
        "success": True,
        "session": {
            "id": session["id"],
            "title": session.get("title") or session["id"],
            "created_at": session.get("created_at"),
            "updated_at": session.get("updated_at"),
            "message_count": 0,
            "last_message_at": session.get("updated_at"),
        },
    }
    if include_messages:
        messages = await r.load_messages(session_id, limit=message_limit, offset=0)
        result["session"]["recent_messages"] = [
            {"role": m["role"], "content": (m["content"] or "")[:200], "created_at": m.get("created_at", "")}
            for m in messages
        ]
    return result


def register_tools(registry: ToolRegistry):
    registry.register(ToolDefinition(
        name="sessions_search",
        description="Search for sessions by keywords in title or content. Use this when the user asks to find conversations about a specific topic.",
        parameters={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query (keywords to search for in session titles and content)"},
                "limit": {"type": "integer", "description": "Maximum number of results to return (default: 10)", "default": 10},
            },
            "required": ["query"],
        },
        executor=sessions_search,
    ))
    registry.register(ToolDefinition(
        name="sessions_list",
        description="List recent sessions sorted by last activity. Use this when the user asks to see their recent conversations or sessions.",
        parameters={
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "description": "Maximum number of sessions to return (default: 10)", "default": 10},
                "offset": {"type": "integer", "description": "Offset for pagination (default: 0)", "default": 0},
            },
            "required": [],
        },
        executor=sessions_list,
    ))
    registry.register(ToolDefinition(
        name="sessions_get",
        description="Get detailed information about a specific session, including optionally its recent messages.",
        parameters={
            "type": "object",
            "properties": {
                "session_id": {"type": "string", "description": "Session id to retrieve"},
                "include_messages": {"type": "boolean", "description": "Whether to include recent messages (default: false)", "default": False},
                "message_limit": {"type": "integer", "description": "Number of recent messages to include if include_messages is true (default: 20)", "default": 20},
            },
            "required": ["session_id"],
        },
        executor=sessions_get,
    ))
