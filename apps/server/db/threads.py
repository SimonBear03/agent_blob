"""
Database models and operations for threads.
"""
import uuid
from datetime import datetime
from typing import Optional, List
from db import get_db


class ThreadsDB:
    """Thread operations."""
    
    @staticmethod
    def create_thread(title: Optional[str] = None, metadata: Optional[str] = None) -> dict:
        """Create a new conversation thread."""
        thread_id = str(uuid.uuid4())
        now = datetime.utcnow().isoformat()
        
        db = get_db()
        db.execute(
            """
            INSERT INTO threads (id, title, created_at, updated_at, metadata)
            VALUES (?, ?, ?, ?, ?)
            """,
            (thread_id, title, now, now, metadata)
        )
        
        return {
            "id": thread_id,
            "title": title,
            "created_at": now,
            "updated_at": now,
            "metadata": metadata
        }
    
    @staticmethod
    def get_thread(thread_id: str) -> Optional[dict]:
        """Get a thread by ID."""
        db = get_db()
        return db.fetchone(
            "SELECT * FROM threads WHERE id = ?",
            (thread_id,)
        )
    
    @staticmethod
    def list_threads(limit: int = 50, offset: int = 0) -> List[dict]:
        """List all threads ordered by updated_at."""
        db = get_db()
        return db.fetchall(
            """
            SELECT * FROM threads 
            ORDER BY updated_at DESC 
            LIMIT ? OFFSET ?
            """,
            (limit, offset)
        )
    
    @staticmethod
    def update_thread(thread_id: str, title: Optional[str] = None, metadata: Optional[str] = None):
        """Update thread metadata."""
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
        params.append(thread_id)
        
        query = f"UPDATE threads SET {', '.join(updates)} WHERE id = ?"
        db.execute(query, tuple(params))
    
    @staticmethod
    def delete_thread(thread_id: str):
        """Delete a thread and its messages."""
        db = get_db()
        # Delete messages first (foreign key constraint)
        db.execute("DELETE FROM messages WHERE thread_id = ?", (thread_id,))
        db.execute("DELETE FROM threads WHERE id = ?", (thread_id,))
