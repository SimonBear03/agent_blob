#!/usr/bin/env python3
"""
Cleanup script to remove all sessions with 0 messages from the database.
"""
import sys
import sqlite3
from pathlib import Path

def cleanup_empty_sessions():
    """Remove all sessions that have no messages."""
    # Connect to database directly
    db_path = "./data/agent_blob.db"
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    print(f"Connected to database: {db_path}")
    
    # Get all sessions
    cursor.execute("SELECT id, title FROM sessions ORDER BY updated_at DESC")
    sessions = cursor.fetchall()
    print(f"\nFound {len(sessions)} total sessions")
    
    deleted_count = 0
    kept_count = 0
    
    for session in sessions:
        session_id = session["id"]
        title = session["title"]
        
        # Count messages for this session
        cursor.execute("SELECT COUNT(*) as count FROM messages WHERE session_id = ?", (session_id,))
        message_count = cursor.fetchone()["count"]
        
        if message_count == 0:
            print(f"  Deleting empty session: {session_id[:8]}... (title: '{title}')")
            cursor.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
            deleted_count += 1
        else:
            kept_count += 1
    
    # Commit changes
    conn.commit()
    conn.close()
    
    print(f"\n✅ Cleanup complete!")
    print(f"   - Deleted: {deleted_count} empty sessions")
    print(f"   - Kept: {kept_count} sessions with messages")

if __name__ == "__main__":
    cleanup_empty_sessions()
