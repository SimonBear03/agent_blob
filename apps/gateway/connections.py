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
    
    def add_client(self, session_id: str, websocket: WebSocket, client_type: str):
        """Add a new client connection."""
        client_info = ClientInfo(
            websocket=websocket,
            client_type=client_type,
            session_id=session_id
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
    
    def get_session_clients(self, session_id: str) -> List[ClientInfo]:
        """Get all clients connected to a session."""
        return self.active_connections.get(session_id, [])
    
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
