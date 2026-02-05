"""
JSONL-based session event store.
"""

import os
import aiofiles
import json
from pathlib import Path
from typing import AsyncIterator, Optional
from datetime import datetime

from .models import Event, create_session_event


class SessionStore:
    """
    Append-only JSONL event log for sessions.
    Each session has its own .jsonl file.
    """
    
    def __init__(self, data_dir: str = "./data/sessions"):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
    
    def _get_session_path(self, session_id: str) -> Path:
        """Get path to session JSONL file"""
        # Sanitize session_id for filename
        safe_id = session_id.replace("/", "-").replace("\\", "-")
        return self.data_dir / f"{safe_id}.jsonl"
    
    async def append_event(self, session_id: str, event: Event) -> None:
        """
        Append an event to the session log.
        Creates the session file if it doesn't exist.
        """
        session_path = self._get_session_path(session_id)
        
        # If file doesn't exist, write session header first
        if not session_path.exists():
            async with aiofiles.open(session_path, "w", encoding="utf-8") as f:
                header = create_session_event(session_id)
                await f.write(header.to_json_line() + "\n")
        
        # Append the event
        async with aiofiles.open(session_path, "a", encoding="utf-8") as f:
            await f.write(event.to_json_line() + "\n")
    
    async def replay_events(
        self, 
        session_id: str,
        skip_header: bool = True
    ) -> AsyncIterator[Event]:
        """
        Replay all events from a session log.
        
        Args:
            session_id: Session to replay
            skip_header: If True, skip the initial session event
        """
        session_path = self._get_session_path(session_id)
        
        if not session_path.exists():
            return
        
        async with aiofiles.open(session_path, "r", encoding="utf-8") as f:
            first_line = True
            async for line in f:
                line = line.strip()
                if not line:
                    continue
                
                # Skip header if requested
                if first_line and skip_header:
                    first_line = False
                    continue
                
                try:
                    event = Event.from_json_line(line)
                    yield event
                except json.JSONDecodeError as e:
                    # Log error but continue processing
                    print(f"Error parsing event in {session_id}: {e}")
                    continue
    
    def session_exists(self, session_id: str) -> bool:
        """Check if a session file exists"""
        return self._get_session_path(session_id).exists()
    
    async def get_session_size(self, session_id: str) -> int:
        """Get size of session file in bytes"""
        session_path = self._get_session_path(session_id)
        if not session_path.exists():
            return 0
        return session_path.stat().st_size
    
    async def list_sessions(self) -> list[str]:
        """List all session IDs"""
        sessions = []
        for path in self.data_dir.glob("*.jsonl"):
            # Remove .jsonl extension to get session_id
            session_id = path.stem
            sessions.append(session_id)
        return sessions
    
    async def get_session_metadata(self, session_id: str) -> Optional[dict]:
        """Get basic metadata about a session"""
        session_path = self._get_session_path(session_id)
        
        if not session_path.exists():
            return None
        
        stat = session_path.stat()
        
        # Read first line to get creation time
        created_at = None
        async with aiofiles.open(session_path, "r", encoding="utf-8") as f:
            first_line = await f.readline()
            if first_line:
                try:
                    event = Event.from_json_line(first_line)
                    created_at = event.timestamp
                except:
                    pass
        
        return {
            "session_id": session_id,
            "size_bytes": stat.st_size,
            "modified": datetime.fromtimestamp(stat.st_mtime).isoformat() + "Z",
            "created_at": created_at
        }
