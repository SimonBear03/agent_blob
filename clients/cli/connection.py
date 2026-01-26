"""
WebSocket connection manager for CLI client.
"""
import asyncio
import json
import logging
from typing import Optional, Dict, Any, Callable, List
import websockets
from websockets.client import WebSocketClientProtocol

logger = logging.getLogger(__name__)


class GatewayConnection:
    """Manages WebSocket connection to Agent Blob Gateway."""
    
    def __init__(self, uri: str = "ws://127.0.0.1:3336/ws"):
        self.uri = uri
        self.ws: Optional[WebSocketClientProtocol] = None
        self.connected = False
        self.current_session_id: Optional[str] = None
        self.gateway_version: Optional[str] = None
        self.supported_methods: List[str] = []
        
        # Event handlers
        self.on_session_changed: Optional[Callable] = None
        self.on_message: Optional[Callable] = None
        self.on_token: Optional[Callable] = None
        self.on_status: Optional[Callable] = None
        self.on_error: Optional[Callable] = None
        self.on_final: Optional[Callable] = None
        
        # Internal state
        self._request_id_counter = 0
        self._pending_responses: Dict[str, asyncio.Future] = {}
        self._receive_task: Optional[asyncio.Task] = None
    
    async def connect(self, client_type: str = "cli", session_preference: str = "auto") -> Dict[str, Any]:
        """
        Connect to gateway and perform handshake.
        
        Args:
            client_type: Type of client ("cli", "tui", "telegram", "web", etc.)
            session_preference: "auto" (most recent), "new" (create new), or "continue" (most recent)
        
        Returns the initial session info from SESSION_CHANGED event.
        """
        try:
            self.ws = await websockets.connect(self.uri)
            self.connected = True
            logger.info(f"Connected to {self.uri}")
            
            # Send connect request
            connect_request = {
                "type": "req",
                "id": self._next_request_id(),
                "method": "connect",
                "params": {
                    "version": "1",
                    "clientType": client_type,
                    "sessionPreference": session_preference
                }
            }
            
            await self.ws.send(json.dumps(connect_request))
            
            # Receive connect response
            response_data = await self.ws.recv()
            response = json.loads(response_data)
            
            if not response.get("ok"):
                raise ConnectionError(f"Connection failed: {response.get('error')}")
            
            # Store gateway info
            payload = response.get("payload", {})
            self.gateway_version = payload.get("gatewayVersion")
            self.supported_methods = payload.get("supportedMethods", [])
            
            # Wait for SESSION_CHANGED event
            session_event_data = await self.ws.recv()
            session_event = json.loads(session_event_data)
            
            if session_event.get("event") != "session_changed":
                raise ConnectionError(f"Expected session_changed event, got: {session_event}")
            
            # Store current session
            session_payload = session_event.get("payload", {})
            self.current_session_id = session_payload.get("sessionId")
            
            # Start receive loop
            self._receive_task = asyncio.create_task(self._receive_loop())
            
            return session_payload
            
        except Exception as e:
            self.connected = False
            logger.error(f"Connection error: {e}")
            raise
    
    async def disconnect(self):
        """Disconnect from gateway."""
        self.connected = False
        if self._receive_task:
            self._receive_task.cancel()
        if self.ws:
            await self.ws.close()
            logger.info("Disconnected from gateway")
    
    async def send_message(self, message: str) -> Optional[str]:
        """
        Send a message to the agent.
        
        Returns the run_id for tracking this request, or None if it was a command.
        """
        request = {
            "type": "req",
            "id": self._next_request_id(),
            "method": "agent",
            "params": {
                "message": message
            }
        }
        
        response = await self._send_request(request)
        
        if not response.get("ok"):
            raise RuntimeError(f"Failed to send message: {response.get('error')}")
        
        # Commands return status instead of runId
        payload = response.get("payload", {})
        return payload.get("runId")  # Returns None for commands
    
    async def cancel_request(self, run_id: str) -> bool:
        """Cancel a running request."""
        request = {
            "type": "req",
            "id": self._next_request_id(),
            "method": "agent.cancel",
            "params": {
                "runId": run_id
            }
        }
        
        response = await self._send_request(request)
        return response.get("ok", False)
    
    async def _send_request(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Send a request and wait for response."""
        if not self.connected or not self.ws:
            raise ConnectionError("Not connected to gateway")
        
        request_id = request["id"]
        
        # Create future for this request
        future = asyncio.Future()
        self._pending_responses[request_id] = future
        
        # Send request
        await self.ws.send(json.dumps(request))
        
        # Wait for response
        try:
            response = await asyncio.wait_for(future, timeout=30.0)
            return response
        finally:
            self._pending_responses.pop(request_id, None)
    
    async def _receive_loop(self):
        """Background task to receive messages from gateway."""
        try:
            while self.connected and self.ws:
                try:
                    data = await self.ws.recv()
                    message = json.loads(data)
                    await self._handle_message(message)
                except websockets.exceptions.ConnectionClosed:
                    logger.info("Connection closed by gateway")
                    self.connected = False
                    break
                except Exception as e:
                    logger.error(f"Error in receive loop: {e}")
        except asyncio.CancelledError:
            logger.debug("Receive loop cancelled")
    
    async def _handle_message(self, message: Dict[str, Any]):
        """Handle incoming message from gateway."""
        msg_type = message.get("type")
        
        if msg_type == "res":
            # Response to a request
            request_id = message.get("id")
            future = self._pending_responses.get(request_id)
            if future and not future.done():
                future.set_result(message)
        
        elif msg_type == "event":
            # Event from gateway
            event_type = message.get("event")
            payload = message.get("payload", {})
            
            if event_type == "session_changed":
                self.current_session_id = payload.get("sessionId")
                if self.on_session_changed:
                    await self.on_session_changed(payload)
            
            elif event_type == "message":
                if self.on_message:
                    await self.on_message(payload)
            
            elif event_type == "token":
                if self.on_token:
                    await self.on_token(payload)
            
            elif event_type == "status":
                if self.on_status:
                    await self.on_status(payload)
            
            elif event_type == "error":
                if self.on_error:
                    await self.on_error(payload)
            
            elif event_type == "final":
                if self.on_final:
                    await self.on_final(payload)
    
    def _next_request_id(self) -> str:
        """Generate next request ID."""
        self._request_id_counter += 1
        return f"req-{self._request_id_counter}"
