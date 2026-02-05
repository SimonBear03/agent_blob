"""
WebSocket protocol types and validation using Pydantic.
"""
from pydantic import BaseModel, Field
from typing import Literal, Optional, Any, Dict
from enum import Enum


# Enums for type safety
class Method(str, Enum):
    """Available WebSocket methods."""
    CONNECT = "connect"
    AGENT = "agent"
    AGENT_CANCEL = "agent.cancel"
    SESSIONS_LIST = "sessions.list"
    SESSIONS_NEW = "sessions.new"
    SESSIONS_SWITCH = "sessions.switch"
    SESSIONS_HISTORY = "sessions.history"
    STATUS = "status"


class EventType(str, Enum):
    """Available event types."""
    MESSAGE = "message"
    QUEUED = "queued"
    TOKEN = "token"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    STATUS = "status"
    FINAL = "final"
    CANCELLED = "cancelled"
    ERROR = "error"
    SESSION_CHANGED = "session_changed"  # Gateway switched your session


class AgentStatus(str, Enum):
    """Agent processing status."""
    THINKING = "thinking"
    EXECUTING_TOOL = "executing_tool"
    STREAMING = "streaming"
    DONE = "done"


# Request/Response/Event Models
class Request(BaseModel):
    """WebSocket request from client to gateway."""
    type: Literal["req"]
    id: str
    method: Method
    params: Dict[str, Any] = Field(default_factory=dict)


class Response(BaseModel):
    """WebSocket response from gateway to client."""
    type: Literal["res"]
    id: str
    ok: bool
    payload: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class Event(BaseModel):
    """WebSocket event pushed from gateway to client."""
    type: Literal["event"]
    event: EventType
    payload: Dict[str, Any]
    seq: Optional[int] = None


# Method-specific parameter models
class ConnectParams(BaseModel):
    """Parameters for connect method."""
    version: str
    clientType: str  # "web", "cli"
    sessionPreference: Optional[str] = None
    historyLimit: Optional[int] = None


class AgentParams(BaseModel):
    """Parameters for agent method.
    
    Note: sessionId is NOT needed in params - gateway tracks which session
    the client is currently viewing.
    """
    message: str


class AgentCancelParams(BaseModel):
    """Parameters for agent.cancel method."""
    runId: str


class SessionsListParams(BaseModel):
    """Parameters for sessions.list method."""
    limit: int = 10
    offset: int = 0


class SessionsNewParams(BaseModel):
    """Parameters for sessions.new method."""
    title: Optional[str] = "New conversation"


class SessionsSwitchParams(BaseModel):
    """Parameters for sessions.switch method."""
    sessionId: str


class SessionsHistoryParams(BaseModel):
    """Parameters for sessions.history method."""
    sessionId: Optional[str] = None
    limit: int = 20
    before: Optional[str] = None


class StatusParams(BaseModel):
    """Parameters for status method."""
    sessionId: Optional[str] = None


# Event payload models
class MessageEventPayload(BaseModel):
    """Payload for message event."""
    role: Literal["user", "assistant"]
    content: str
    messageId: str
    timestamp: str
    fromSelf: Optional[bool] = None  # For web/cli clients


class QueuedEventPayload(BaseModel):
    """Payload for queued event."""
    requestId: str
    position: int
    message: str


class TokenEventPayload(BaseModel):
    """Payload for token event."""
    runId: str
    content: str
    delta: bool = True


class ToolCallEventPayload(BaseModel):
    """Payload for tool_call event."""
    runId: str
    toolName: str
    arguments: Dict[str, Any]


class ToolResultEventPayload(BaseModel):
    """Payload for tool_result event."""
    runId: str
    toolName: str
    result: Dict[str, Any]


class StatusEventPayload(BaseModel):
    """Payload for status event."""
    runId: str
    status: AgentStatus


class FinalEventPayload(BaseModel):
    """Payload for final event."""
    runId: str
    messageId: str
    totalTokens: int


class CancelledEventPayload(BaseModel):
    """Payload for cancelled event."""
    runId: str
    message: str


class ErrorEventPayload(BaseModel):
    """Payload for error event."""
    runId: Optional[str] = None
    message: str
    retryable: bool
    errorCode: Optional[str] = None


# Helper functions
def create_response(request_id: str, ok: bool, payload: Optional[Dict[str, Any]] = None, error: Optional[str] = None) -> Dict[str, Any]:
    """Create a response dict."""
    return Response(
        type="res",
        id=request_id,
        ok=ok,
        payload=payload,
        error=error
    ).model_dump()


def create_event(event_type: EventType, payload: Dict[str, Any], seq: Optional[int] = None) -> Dict[str, Any]:
    """Create an event dict."""
    return Event(
        type="event",
        event=event_type,
        payload=payload,
        seq=seq
    ).model_dump()
