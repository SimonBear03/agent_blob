"""
Session state cache management.
Caches computed state to avoid replaying entire JSONL on every request.
"""

import json
import aiofiles
from pathlib import Path
from typing import Optional
from datetime import datetime

from .models import SessionState, RollingSummary


class StateCache:
    """
    Manages session state cache files.
    State cache is a JSON file with pre-computed session state.
    """
    
    def __init__(self, data_dir: str = "./data/sessions"):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
    
    def _get_state_path(self, session_id: str) -> Path:
        """Get path to state cache file"""
        safe_id = session_id.replace("/", "-").replace("\\", "-")
        return self.data_dir / f"{safe_id}.state.json"
    
    async def load_state(self, session_id: str) -> Optional[SessionState]:
        """
        Load cached state for a session.
        Returns None if cache doesn't exist.
        """
        state_path = self._get_state_path(session_id)
        
        if not state_path.exists():
            return None
        
        try:
            async with aiofiles.open(state_path, "r", encoding="utf-8") as f:
                content = await f.read()
                data = json.loads(content)
                return SessionState.from_dict(data)
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            print(f"Error loading state cache for {session_id}: {e}")
            return None
    
    async def save_state(self, state: SessionState) -> None:
        """Save session state to cache"""
        state_path = self._get_state_path(state.session_id)
        
        # Update timestamp
        state.updated_at = datetime.utcnow().isoformat() + "Z"
        
        async with aiofiles.open(state_path, "w", encoding="utf-8") as f:
            data = state.to_dict()
            content = json.dumps(data, indent=2, ensure_ascii=False)
            await f.write(content)
    
    async def create_initial_state(self, session_id: str) -> SessionState:
        """
        Create initial state for a new session.
        """
        now = datetime.utcnow().isoformat() + "Z"
        state = SessionState(
            session_id=session_id,
            rolling_summary=RollingSummary(),
            recent_turns=[],
            token_count=0,
            message_count=0,
            last_compaction=None,
            created_at=now,
            updated_at=now
        )
        await self.save_state(state)
        return state
    
    async def get_or_create_state(self, session_id: str) -> SessionState:
        """
        Load state from cache, or create initial state if doesn't exist.
        """
        state = await self.load_state(session_id)
        if state is None:
            state = await self.create_initial_state(session_id)
        return state
    
    def state_exists(self, session_id: str) -> bool:
        """Check if state cache exists"""
        return self._get_state_path(session_id).exists()
    
    async def delete_state(self, session_id: str) -> None:
        """Delete state cache file"""
        state_path = self._get_state_path(session_id)
        if state_path.exists():
            state_path.unlink()
    
    async def rebuild_state_from_events(
        self, 
        session_id: str,
        events: list
    ) -> SessionState:
        """
        Rebuild state by replaying events.
        This is used when cache is corrupted or after compaction.
        
        Note: This is a simplified version. Full implementation would
        parse all events and reconstruct state accurately.
        """
        # For now, create initial state
        # TODO: Implement full event replay logic
        return await self.create_initial_state(session_id)
