"""
Auto-session key generation based on conversation identity.

Following Clawdbot's approach: sessions are automatically created based on
the conversation identity (client + user + context), not manually by users.
"""

def get_session_key(
    client_type: str,
    user_id: str = "default",
    context: str = "default"
) -> str:
    """
    Generate session key from conversation identity.
    
    Args:
        client_type: Type of client (cli, web)
        user_id: User identifier (for future multi-user support)
        context: Optional context/workspace (default: "default")
    
    Returns:
        Session key like "cli-simon-default" or "web-default-work"
    
    Examples:
        - CLI on default workspace: "cli-default-default"
        - Web UI work context: "web-default-work"
    """
    # Sanitize components
    client_type = client_type.lower().strip()
    user_id = user_id.lower().strip() if user_id else "default"
    context = context.lower().strip() if context else "default"
    
    # Build key
    return f"{client_type}-{user_id}-{context}"


def parse_session_key(session_key: str) -> dict:
    """
    Parse session key back into components.
    
    Args:
        session_key: Session key like "cli-simon-default"
    
    Returns:
        Dict with client_type, user_id, context
    """
    parts = session_key.split("-")
    if len(parts) >= 3:
        return {
            "client_type": parts[0],
            "user_id": parts[1],
            "context": "-".join(parts[2:])  # Context may have dashes
        }
    else:
        # Fallback for malformed keys
        return {
            "client_type": "unknown",
            "user_id": "default",
            "context": "default"
        }
