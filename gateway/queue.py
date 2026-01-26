"""
Per-session request queue for sequential processing.
"""
from collections import deque
from typing import Dict, Deque, Optional
from dataclasses import dataclass
from fastapi import WebSocket
import asyncio
import logging

logger = logging.getLogger(__name__)


@dataclass
class QueuedRequest:
    """A queued agent request."""
    request_id: str
    run_id: str
    session_id: str
    message: str
    websocket: WebSocket


class SessionQueue:
    """Manages per-session request queues."""
    
    def __init__(self):
        # session_id -> queue of requests
        self.queues: Dict[str, Deque[QueuedRequest]] = {}
        # session_id -> currently processing run_id
        self.processing: Dict[str, str] = {}
        # session_id -> processing task
        self.tasks: Dict[str, asyncio.Task] = {}
    
    def enqueue(self, request: QueuedRequest) -> int:
        """
        Add a request to the session queue.
        
        Returns:
            Position in queue (1-indexed)
        """
        session_id = request.session_id
        
        if session_id not in self.queues:
            self.queues[session_id] = deque()
        
        self.queues[session_id].append(request)
        position = len(self.queues[session_id])
        
        logger.info(f"Enqueued request {request.request_id} for session {session_id[:8]}... (position {position})")
        
        return position
    
    def is_processing(self, session_id: str) -> bool:
        """Check if a session is currently processing a request."""
        return session_id in self.processing
    
    def get_queue_size(self, session_id: str) -> int:
        """Get the number of queued requests for a session."""
        return len(self.queues.get(session_id, []))
    
    def cancel_request(self, run_id: str) -> bool:
        """
        Cancel a request by run_id.
        
        Returns:
            True if found and cancelled, False otherwise
        """
        # Check if it's currently processing
        for session_id, processing_run_id in self.processing.items():
            if processing_run_id == run_id:
                # TODO: Implement actual cancellation of running request
                logger.info(f"Cancelling running request: {run_id}")
                return True
        
        # Check queues
        for session_id, queue in self.queues.items():
            for request in queue:
                if request.run_id == run_id:
                    queue.remove(request)
                    logger.info(f"Removed queued request: {run_id}")
                    return True
        
        return False
    
    async def start_processing(self, session_id: str, connection_manager, runtime):
        """
        Start processing queued requests for a session.
        
        This creates a background task that processes requests sequentially.
        """
        if session_id in self.tasks and not self.tasks[session_id].done():
            # Already processing this session
            return
        
        task = asyncio.create_task(
            self._process_queue(session_id, connection_manager, runtime)
        )
        self.tasks[session_id] = task
    
    async def _process_queue(self, session_id: str, connection_manager, runtime):
        """
        Process queued requests sequentially for a session.
        
        This runs in a background task and processes one request at a time.
        """
        logger.info(f"Started queue processor for session {session_id[:8]}...")
        
        try:
            while self.queues.get(session_id):
                request = self.queues[session_id].popleft()
                self.processing[session_id] = request.run_id
                
                logger.info(f"Processing request {request.request_id} (run_id: {request.run_id})")
                
                try:
                    # Process via runtime, broadcast events to all clients
                    async for event in runtime.process(request):
                        await connection_manager.broadcast_to_session(
                            session_id=session_id,
                            event=event,
                            sender_ws=request.websocket
                        )
                
                except Exception as e:
                    logger.error(f"Error processing request {request.request_id}: {e}")
                    
                    # Send error event to all clients
                    error_event = {
                        "type": "event",
                        "event": "error",
                        "payload": {
                            "runId": request.run_id,
                            "message": f"Request processing failed: {str(e)}",
                            "retryable": False,
                            "errorCode": "PROCESSING_ERROR"
                        }
                    }
                    await connection_manager.broadcast_to_session(
                        session_id=session_id,
                        event=error_event
                    )
                
                finally:
                    # Clear processing status
                    if session_id in self.processing:
                        del self.processing[session_id]
        
        except Exception as e:
            logger.error(f"Queue processor error for session {session_id[:8]}...: {e}")
        
        finally:
            # Clean up
            if session_id in self.tasks:
                del self.tasks[session_id]
            
            logger.info(f"Stopped queue processor for session {session_id[:8]}...")
    
    def get_stats(self) -> dict:
        """Get queue statistics."""
        return {
            "activeSessions": len(self.processing),
            "queuedRequests": sum(len(q) for q in self.queues.values()),
            "sessionQueues": {
                session_id: {
                    "queued": len(queue),
                    "processing": session_id in self.processing
                }
                for session_id, queue in self.queues.items()
                if queue or session_id in self.processing
            }
        }
