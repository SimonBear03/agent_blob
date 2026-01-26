#!/usr/bin/env python3
"""
Cleanup script to remove sessions with low message counts from the database.
"""
import sys
import sqlite3
from pathlib import Path

def cleanup_empty_sessions(min_messages: int = 3):
    """Remove all sessions that have fewer than min_messages."""
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
    print(f"Deleting sessions with fewer than {min_messages} messages\n")
    
    deleted_count = 0
    kept_count = 0
    
    for session in sessions:
        session_id = session["id"]
        title = session["title"]
        
        # Count messages for this session
        cursor.execute("SELECT COUNT(*) as count FROM messages WHERE session_id = ?", (session_id,))
        message_count = cursor.fetchone()["count"]
        
        if message_count < min_messages:
            print(f"  Deleting session: {session_id[:8]}... (messages: {message_count}, title: '{title}')")
            cursor.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
            deleted_count += 1
        else:
            kept_count += 1
    
    # Commit changes
    conn.commit()
    conn.close()
    
    print(f"\n✅ Cleanup complete!")
    print(f"   - Deleted: {deleted_count} sessions")
    print(f"   - Kept: {kept_count} sessions")

if __name__ == "__main__":
    min_messages = 3
    if len(sys.argv) > 1 and sys.argv[1].isdigit():
        min_messages = int(sys.argv[1])
    cleanup_empty_sessions(min_messages=min_messages)
