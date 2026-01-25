"""
Database models and operations for audit log.
"""
import uuid
from datetime import datetime
from typing import Optional, List
from db import get_db


class AuditDB:
    """Audit log operations."""
    
    @staticmethod
    def log_tool_execution(
        tool_name: str,
        parameters: str,
        result: Optional[str] = None,
        error: Optional[str] = None,
        thread_id: Optional[str] = None
    ) -> dict:
        """Log a tool execution."""
        log_id = str(uuid.uuid4())
        now = datetime.utcnow().isoformat()
        
        db = get_db()
        db.execute(
            """
            INSERT INTO audit_log (id, thread_id, tool_name, parameters, result, error, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (log_id, thread_id, tool_name, parameters, result, error, now)
        )
        
        return {
            "id": log_id,
            "thread_id": thread_id,
            "tool_name": tool_name,
            "parameters": parameters,
            "result": result,
            "error": error,
            "timestamp": now
        }
    
    @staticmethod
    def get_log_entry(log_id: str) -> Optional[dict]:
        """Get an audit log entry by ID."""
        db = get_db()
        return db.fetchone(
            "SELECT * FROM audit_log WHERE id = ?",
            (log_id,)
        )
    
    @staticmethod
    def list_logs(
        thread_id: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[dict]:
        """List audit log entries."""
        db = get_db()
        
        if thread_id:
            return db.fetchall(
                """
                SELECT * FROM audit_log 
                WHERE thread_id = ?
                ORDER BY timestamp DESC 
                LIMIT ? OFFSET ?
                """,
                (thread_id, limit, offset)
            )
        else:
            return db.fetchall(
                """
                SELECT * FROM audit_log 
                ORDER BY timestamp DESC 
                LIMIT ? OFFSET ?
                """,
                (limit, offset)
            )
