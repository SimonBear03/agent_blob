"""
Database models and operations for pinned memory.
"""
import uuid
from datetime import datetime
from typing import Optional, List
from db import get_db


class MemoryDB:
    """Pinned memory operations."""
    
    @staticmethod
    def create_or_update_memory(key: str, value: str, description: Optional[str] = None) -> dict:
        """Create or update a pinned memory entry."""
        db = get_db()
        existing = db.fetchone("SELECT * FROM pinned_memory WHERE key = ?", (key,))
        
        now = datetime.utcnow().isoformat()
        
        if existing:
            # Update existing
            db.execute(
                """
                UPDATE pinned_memory 
                SET value = ?, description = ?, updated_at = ?
                WHERE key = ?
                """,
                (value, description, now, key)
            )
            return {
                "id": existing["id"],
                "key": key,
                "value": value,
                "description": description,
                "created_at": existing["created_at"],
                "updated_at": now
            }
        else:
            # Create new
            memory_id = str(uuid.uuid4())
            db.execute(
                """
                INSERT INTO pinned_memory (id, key, value, description, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (memory_id, key, value, description, now, now)
            )
            return {
                "id": memory_id,
                "key": key,
                "value": value,
                "description": description,
                "created_at": now,
                "updated_at": now
            }
    
    @staticmethod
    def get_memory(key: str) -> Optional[dict]:
        """Get a pinned memory entry by key."""
        db = get_db()
        return db.fetchone(
            "SELECT * FROM pinned_memory WHERE key = ?",
            (key,)
        )
    
    @staticmethod
    def list_memories() -> List[dict]:
        """List all pinned memory entries."""
        db = get_db()
        return db.fetchall(
            "SELECT * FROM pinned_memory ORDER BY updated_at DESC"
        )
    
    @staticmethod
    def delete_memory(key: str):
        """Delete a pinned memory entry."""
        db = get_db()
        db.execute("DELETE FROM pinned_memory WHERE key = ?", (key,))
