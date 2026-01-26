"""
Multi-client connection management with broadcast support.
"""
from fastapi import WebSocket
from typing import Dict, List, Optional
from collections import defaultdict
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


@dataclass
class ClientInfo:
    """Information about a connected client."""
    websocket: WebSocket
    client_type: str  # "web", "cli", "telegram"
    session_id: str
    history_limit: Optional[int] = None
    sessions_page: int = 1
    sessions_query: Optional[str] = None


class ConnectionManager:
    """Manages WebSocket connections and broadcasts events to clients."""
    
    def __init__(self):
        # session_id -> list of ClientInfo
        self.active_connections: Dict[str, List[ClientInfo]] = defaultdict(list)
        # websocket -> ClientInfo mapping for quick lookup
        self.ws_to_client: Dict[WebSocket, ClientInfo] = {}
        # Track client type icons for formatting
        self.client_icons = {
            "web": "🖥️",
            "cli": "📱",
            "telegram": "💬"
        }
        self.default_history_limits = {
            "tui": 20,
            "cli": 20,
            "web": 20,
            "telegram": 4
        }
    
    def add_client(
        self,
        session_id: str,
        websocket: WebSocket,
        client_type: str,
        history_limit: Optional[int] = None
    ):
        """Add a new client connection."""
        resolved_history_limit = (
            history_limit
            if history_limit is not None
            else self.default_history_limits.get(client_type, 20)
        )
        client_info = ClientInfo(
            websocket=websocket,
            client_type=client_type,
            session_id=session_id,
            history_limit=resolved_history_limit
        )
        self.active_connections[session_id].append(client_info)
        self.ws_to_client[websocket] = client_info
        
        logger.info(f"Client connected: type={client_type}, session={session_id[:8]}...")
    
    def remove_client(self, websocket: WebSocket):
        """Remove a client connection."""
        if websocket in self.ws_to_client:
            client_info = self.ws_to_client[websocket]
            session_id = client_info.session_id
            
            self.active_connections[session_id].remove(client_info)
            del self.ws_to_client[websocket]
            
            # Clean up empty session lists
            if not self.active_connections[session_id]:
                del self.active_connections[session_id]
            
            logger.info(f"Client disconnected: type={client_info.client_type}, session={session_id[:8]}...")
    
    def get_client_info(self, websocket: WebSocket) -> Optional[ClientInfo]:
        """Get client info for a websocket."""
        return self.ws_to_client.get(websocket)

    def get_history_limit(self, websocket: WebSocket) -> int:
        """Get history limit for a websocket."""
        client_info = self.ws_to_client.get(websocket)
        if client_info and client_info.history_limit is not None:
            return client_info.history_limit
        return 20

    def get_sessions_state(self, websocket: WebSocket) -> tuple[int, Optional[str]]:
        """Get last sessions page and query for a websocket."""
        client_info = self.ws_to_client.get(websocket)
        if not client_info:
            return (1, None)
        return (client_info.sessions_page, client_info.sessions_query)

    def set_sessions_state(self, websocket: WebSocket, page: int, query: Optional[str]):
        """Set last sessions page and query for a websocket."""
        client_info = self.ws_to_client.get(websocket)
        if not client_info:
            return
        client_info.sessions_page = page
        client_info.sessions_query = query
    
    def get_session_clients(self, session_id: str) -> List[ClientInfo]:
        """Get all clients connected to a session."""
        return self.active_connections.get(session_id, [])
    
    def get_client_session(self, websocket: WebSocket) -> Optional[str]:
        """Get the current session ID for a websocket."""
        if websocket in self.ws_to_client:
            return self.ws_to_client[websocket].session_id
        return None
    
    def switch_client_session(self, websocket: WebSocket, new_session_id: str) -> bool:
        """
        Switch a client to a different session.
        
        This updates the connection manager's tracking so future broadcasts
        go to the correct session.
        
        Returns:
            True if successful, False if websocket not found
        """
        if websocket not in self.ws_to_client:
            logger.error(f"Cannot switch session: websocket not found")
            return False
        
        client_info = self.ws_to_client[websocket]
        old_session_id = client_info.session_id
        
        # Remove from old session
        if old_session_id in self.active_connections:
            try:
                self.active_connections[old_session_id].remove(client_info)
                if not self.active_connections[old_session_id]:
                    del self.active_connections[old_session_id]
            except ValueError:
                pass
        
        # Update session_id and add to new session
        client_info.session_id = new_session_id
        self.active_connections[new_session_id].append(client_info)
        
        logger.info(f"Switched client from session {old_session_id[:8]}... to {new_session_id[:8]}...")
        return True
    
    async def broadcast_to_session(
        self,
        session_id: str,
        event: dict,
        sender_ws: Optional[WebSocket] = None
    ):
        """
        Broadcast event to all clients in a session.
        
        Formats messages appropriately based on client type:
        - Telegram: Prefixes user messages from other clients
        - Web/CLI: Uses fromSelf flag
        
        Args:
            session_id: Session to broadcast to
            event: Event dict to send
            sender_ws: WebSocket of the sender (if applicable)
        """
        if session_id not in self.active_connections:
            logger.warning(f"Attempted to broadcast to non-existent session: {session_id[:8]}...")
            return
        
        # Get sender client info
        sender_client = self.ws_to_client.get(sender_ws) if sender_ws else None
        sender_type = sender_client.client_type if sender_client else None
        
        # Broadcast to all clients in the session
        disconnected_clients = []
        
        for client_info in self.active_connections[session_id]:
            # Clone event for this client
            client_event = self._format_event_for_client(
                event=event,
                client_info=client_info,
                sender_ws=sender_ws,
                sender_type=sender_type
            )
            
            # Send to client
            try:
                await client_info.websocket.send_json(client_event)
            except Exception as e:
                logger.error(f"Failed to send to client: {e}")
                disconnected_clients.append(client_info)
        
        # Clean up disconnected clients
        for client_info in disconnected_clients:
            self.remove_client(client_info.websocket)
    
    def _format_event_for_client(
        self,
        event: dict,
        client_info: ClientInfo,
        sender_ws: Optional[WebSocket],
        sender_type: Optional[str]
    ) -> dict:
        """
        Format event based on client type.
        
        For user messages:
        - Telegram: Prefix with source if from another client
        - Web/CLI: Add fromSelf flag
        
        For other events: No formatting needed
        """
        # Clone the event
        client_event = event.copy()
        
        # Only format user message events
        if (event.get("event") == "message" and 
            event.get("payload", {}).get("role") == "user"):
            
            is_sender = (client_info.websocket == sender_ws)
            
            if client_info.client_type == "telegram":
                # Telegram gets prefixed message if not sender
                if not is_sender and sender_type:
                    icon = self.client_icons.get(sender_type, "📨")
                    source_name = sender_type.title()
                    
                    original_content = event["payload"]["content"]
                    client_event["payload"] = event["payload"].copy()
                    client_event["payload"]["content"] = f"{icon} [From {source_name}] {original_content}"
            else:
                # Web/CLI get fromSelf flag
                client_event["payload"] = event["payload"].copy()
                client_event["payload"]["fromSelf"] = is_sender
        
        return client_event
    
    def get_stats(self) -> dict:
        """Get connection statistics."""
        return {
            "totalConnections": len(self.ws_to_client),
            "activeSessions": len(self.active_connections),
            "sessionDetails": {
                session_id: len(clients)
                for session_id, clients in self.active_connections.items()
            }
        }
