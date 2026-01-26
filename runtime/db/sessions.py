"""
Database models and operations for sessions (formerly threads).
"""
import uuid
from datetime import datetime
from typing import Optional, List
from . import get_db


class SessionsDB:
    """Session operations."""
    
    @staticmethod
    def create_session(title: Optional[str] = None, metadata: Optional[str] = None) -> dict:
        """Create a new conversation session."""
        session_id = str(uuid.uuid4())
        now = datetime.utcnow().isoformat()
        
        db = get_db()
        db.execute(
            """
            INSERT INTO sessions (id, title, created_at, updated_at, metadata)
            VALUES (?, ?, ?, ?, ?)
            """,
            (session_id, title, now, now, metadata)
        )
        
        return {
            "id": session_id,
            "title": title,
            "created_at": now,
            "updated_at": now,
            "metadata": metadata
        }
    
    @staticmethod
    def get_session(session_id: str) -> Optional[dict]:
        """Get a session by ID."""
        db = get_db()
        return db.fetchone(
            "SELECT * FROM sessions WHERE id = ?",
            (session_id,)
        )
    
    @staticmethod
    def list_sessions(limit: int = 50, offset: int = 0) -> List[dict]:
        """
        List all sessions ordered by updated_at (most recent first).
        
        This is the key query for session navigation - sorted by last activity.
        """
        db = get_db()
        return db.fetchall(
            """
            SELECT * FROM sessions 
            ORDER BY updated_at DESC 
            LIMIT ? OFFSET ?
            """,
            (limit, offset)
        )
    
    @staticmethod
    def search_sessions(query: str, limit: int = 10) -> List[dict]:
        """
        Search sessions by title or metadata.
        
        Used by LLM tools to find sessions matching user queries.
        """
        db = get_db()
        search_pattern = f"%{query}%"
        return db.fetchall(
            """
            SELECT * FROM sessions 
            WHERE title LIKE ? OR metadata LIKE ?
            ORDER BY updated_at DESC 
            LIMIT ?
            """,
            (search_pattern, search_pattern, limit)
        )
    
    @staticmethod
    def update_session(session_id: str, title: Optional[str] = None, metadata: Optional[str] = None):
        """
        Update session metadata and timestamp.
        
        This should be called on every message to keep sessions sorted by activity.
        """
        now = datetime.utcnow().isoformat()
        db = get_db()
        
        updates = []
        params = []
        
        if title is not None:
            updates.append("title = ?")
            params.append(title)
        
        if metadata is not None:
            updates.append("metadata = ?")
            params.append(metadata)
        
        updates.append("updated_at = ?")
        params.append(now)
        params.append(session_id)
        
        query = f"UPDATE sessions SET {', '.join(updates)} WHERE id = ?"
        db.execute(query, tuple(params))
    
    @staticmethod
    def delete_session(session_id: str):
        """Delete a session and its messages."""
        db = get_db()
        # Delete messages first (foreign key constraint)
        db.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
        # Delete agent runs
        db.execute("DELETE FROM agent_runs WHERE session_id = ?", (session_id,))
        # Delete session
        db.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
    
    @staticmethod
    def get_session_with_message_count(session_id: str) -> Optional[dict]:
        """Get session with message count."""
        db = get_db()
        conn = db.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT 
                s.*,
                COUNT(m.id) as message_count,
                MAX(m.created_at) as last_message_at
            FROM sessions s
            LEFT JOIN messages m ON s.id = m.session_id
            WHERE s.id = ?
            GROUP BY s.id
        """, (session_id,))
        
        row = cursor.fetchone()
        conn.close()
        
        return dict(row) if row else None
    
    @staticmethod
    def get_sessions_with_stats(limit: int = 50, offset: int = 0) -> List[dict]:
        """
        Get sessions with statistics (message count, last message).
        
        Used for session lists in UI.
        """
        db = get_db()
        conn = db.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT 
                s.id,
                s.title,
                s.created_at,
                s.updated_at,
                s.metadata,
                COUNT(m.id) as message_count,
                MAX(m.content) as last_message,
                MAX(m.created_at) as last_activity
            FROM sessions s
            LEFT JOIN messages m ON s.id = m.session_id
            GROUP BY s.id
            ORDER BY s.updated_at DESC
            LIMIT ? OFFSET ?
        """, (limit, offset))
        
        rows = cursor.fetchall()
        conn.close()
        
        return [dict(row) for row in rows]
