"""
Data models for session storage.
"""

from dataclasses import dataclass, field, asdict
from typing import Optional, List, Dict, Any
from datetime import datetime
import json


@dataclass
class MessageTurn:
    """A single user-assistant message pair"""
    user_message: str
    assistant_message: str
    timestamp: str
    user_message_id: str
    assistant_message_id: str
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)
    tool_results: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class RollingSummary:
    """Structured summary of older conversation turns"""
    user_profile: str = ""
    active_topics: List[str] = field(default_factory=list)
    decisions: List[str] = field(default_factory=list)
    open_questions: List[str] = field(default_factory=list)
    tool_context: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RollingSummary":
        return cls(**data)
    
    def to_text(self) -> str:
        """Format as readable text for prompt injection"""
        lines = []
        if self.user_profile:
            lines.append(f"User profile: {self.user_profile}")
        if self.active_topics:
            lines.append(f"Active topics: {', '.join(self.active_topics)}")
        if self.decisions:
            lines.append("Key decisions:")
            for decision in self.decisions:
                lines.append(f"  * {decision}")
        if self.open_questions:
            lines.append(f"Open questions: {', '.join(self.open_questions)}")
        if self.tool_context:
            lines.append(f"Tool context: {self.tool_context}")
        return "\n".join(lines)


@dataclass
class SessionState:
    """Cached state for a session (avoids replaying entire JSONL)"""
    session_id: str
    rolling_summary: RollingSummary
    recent_turns: List[MessageTurn]
    token_count: int
    message_count: int
    last_compaction: Optional[str]
    created_at: str
    updated_at: str
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "rolling_summary": self.rolling_summary.to_dict(),
            "recent_turns": [asdict(turn) for turn in self.recent_turns],
            "token_count": self.token_count,
            "message_count": self.message_count,
            "last_compaction": self.last_compaction,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SessionState":
        return cls(
            session_id=data["session_id"],
            rolling_summary=RollingSummary.from_dict(data["rolling_summary"]),
            recent_turns=[MessageTurn(**turn) for turn in data["recent_turns"]],
            token_count=data["token_count"],
            message_count=data["message_count"],
            last_compaction=data.get("last_compaction"),
            created_at=data["created_at"],
            updated_at=data["updated_at"],
        )


@dataclass
class Event:
    """Base event for JSONL logging"""
    type: str
    timestamp: str
    data: Dict[str, Any] = field(default_factory=dict)
    
    def to_json_line(self) -> str:
        """Convert to JSONL format"""
        event_dict = {
            "type": self.type,
            "timestamp": self.timestamp,
            **self.data
        }
        return json.dumps(event_dict, ensure_ascii=False)
    
    @classmethod
    def from_json_line(cls, line: str) -> "Event":
        """Parse from JSONL format"""
        data = json.loads(line)
        event_type = data.pop("type")
        timestamp = data.pop("timestamp")
        return cls(type=event_type, timestamp=timestamp, data=data)


def create_session_event(session_id: str, version: int = 1) -> Event:
    """Create session initialization event"""
    return Event(
        type="session",
        timestamp=datetime.utcnow().isoformat() + "Z",
        data={"id": session_id, "version": version}
    )


def create_message_event(
    message_id: str,
    role: str,
    content: str,
    tool_calls: Optional[List[Dict]] = None,
    tool_call_id: Optional[str] = None,
    name: Optional[str] = None
) -> Event:
    """Create message event"""
    data = {
        "id": message_id,
        "role": role,
        "content": content
    }
    if tool_calls:
        data["tool_calls"] = tool_calls
    if tool_call_id:
        data["tool_call_id"] = tool_call_id
    if name:
        data["name"] = name
    
    return Event(
        type="message",
        timestamp=datetime.utcnow().isoformat() + "Z",
        data=data
    )


def create_tool_call_event(tool_call_id: str, name: str, arguments: Dict) -> Event:
    """Create tool call event"""
    return Event(
        type="tool_call",
        timestamp=datetime.utcnow().isoformat() + "Z",
        data={
            "id": tool_call_id,
            "name": name,
            "arguments": arguments
        }
    )


def create_tool_result_event(result_id: str, tool_call_id: str, result: Any) -> Event:
    """Create tool result event"""
    return Event(
        type="tool_result",
        timestamp=datetime.utcnow().isoformat() + "Z",
        data={
            "id": result_id,
            "tool_call_id": tool_call_id,
            "result": result
        }
    )


def create_compaction_event(summary: RollingSummary, facts_extracted: int) -> Event:
    """Create compaction event"""
    return Event(
        type="compaction",
        timestamp=datetime.utcnow().isoformat() + "Z",
        data={
            "summary": summary.to_dict(),
            "facts_extracted": facts_extracted
        }
    )
