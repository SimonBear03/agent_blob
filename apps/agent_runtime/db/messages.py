"""
Database models and operations for messages.
"""
import uuid
from datetime import datetime
from typing import Optional, List
from . import get_db


class MessagesDB:
    """Message operations."""
    
    @staticmethod
    def create_message(
        session_id: str,
        role: str,
        content: str,
        tool_calls: Optional[str] = None,
        tool_call_id: Optional[str] = None,
        name: Optional[str] = None
    ) -> dict:
        """Create a new message in a session."""
        message_id = str(uuid.uuid4())
        now = datetime.utcnow().isoformat()
        
        db = get_db()
        db.execute(
            """
            INSERT INTO messages (id, session_id, role, content, created_at, tool_calls, tool_call_id, name)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (message_id, session_id, role, content, now, tool_calls, tool_call_id, name)
        )
        
        return {
            "id": message_id,
            "session_id": session_id,
            "role": role,
            "content": content,
            "created_at": now,
            "tool_calls": tool_calls,
            "tool_call_id": tool_call_id,
            "name": name
        }
    
    @staticmethod
    def get_message(message_id: str) -> Optional[dict]:
        """Get a message by ID."""
        db = get_db()
        return db.fetchone(
            "SELECT * FROM messages WHERE id = ?",
            (message_id,)
        )
    
    @staticmethod
    def list_messages(session_id: str, limit: int = 100, offset: int = 0) -> List[dict]:
        """List all messages in a session ordered by created_at."""
        db = get_db()
        return db.fetchall(
            """
            SELECT * FROM messages 
            WHERE session_id = ?
            ORDER BY created_at ASC 
            LIMIT ? OFFSET ?
            """,
            (session_id, limit, offset)
        )
    
    @staticmethod
    def delete_message(message_id: str):
        """Delete a message."""
        db = get_db()
        db.execute("DELETE FROM messages WHERE id = ?", (message_id,))
