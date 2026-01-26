"""
Process management for tracking and controlling tool executions.
"""
import asyncio
import uuid
from typing import Dict, Optional, Any
from dataclasses import dataclass
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


@dataclass
class ProcessInfo:
    """Information about a running process/tool execution."""
    id: str
    run_id: str
    tool_name: str
    status: str  # "running", "completed", "cancelled", "failed"
    progress: float  # 0.0 to 1.0
    created_at: datetime
    completed_at: Optional[datetime] = None
    task: Optional[asyncio.Task] = None
    result: Optional[Any] = None
    error: Optional[str] = None


class ProcessManager:
    """Manages active tool executions and provides cancellation support."""
    
    def __init__(self):
        # process_id -> ProcessInfo
        self.active_processes: Dict[str, ProcessInfo] = {}
        # run_id -> list of process_ids
        self.run_processes: Dict[str, list] = {}
    
    def create_process(self, run_id: str, tool_name: str, task: Optional[asyncio.Task] = None) -> str:
        """Create and track a new process."""
        process_id = f"proc_{uuid.uuid4().hex[:16]}"
        
        process_info = ProcessInfo(
            id=process_id,
            run_id=run_id,
            tool_name=tool_name,
            status="running",
            progress=0.0,
            created_at=datetime.utcnow(),
            task=task
        )
        
        self.active_processes[process_id] = process_info
        
        if run_id not in self.run_processes:
            self.run_processes[run_id] = []
        self.run_processes[run_id].append(process_id)
        
        logger.info(f"Created process {process_id} for run {run_id}: {tool_name}")
        
        return process_id
    
    def update_progress(self, process_id: str, progress: float):
        """Update process progress (0.0 to 1.0)."""
        if process_id in self.active_processes:
            self.active_processes[process_id].progress = min(1.0, max(0.0, progress))
    
    def complete_process(self, process_id: str, result: Any = None):
        """Mark a process as completed."""
        if process_id in self.active_processes:
            process = self.active_processes[process_id]
            process.status = "completed"
            process.progress = 1.0
            process.completed_at = datetime.utcnow()
            process.result = result
            
            logger.info(f"Completed process {process_id}")
    
    def fail_process(self, process_id: str, error: str):
        """Mark a process as failed."""
        if process_id in self.active_processes:
            process = self.active_processes[process_id]
            process.status = "failed"
            process.completed_at = datetime.utcnow()
            process.error = error
            
            logger.error(f"Failed process {process_id}: {error}")
    
    async def cancel_process(self, process_id: str) -> bool:
        """Cancel a running process."""
        if process_id not in self.active_processes:
            return False
        
        process = self.active_processes[process_id]
        
        if process.status != "running":
            return False
        
        # Cancel the task if it exists
        if process.task and not process.task.done():
            process.task.cancel()
            try:
                await process.task
            except asyncio.CancelledError:
                pass
        
        process.status = "cancelled"
        process.completed_at = datetime.utcnow()
        
        logger.info(f"Cancelled process {process_id}")
        return True
    
    async def cancel_run(self, run_id: str) -> int:
        """Cancel all processes for a run. Returns count of cancelled processes."""
        if run_id not in self.run_processes:
            return 0
        
        cancelled = 0
        for process_id in self.run_processes[run_id]:
            if await self.cancel_process(process_id):
                cancelled += 1
        
        return cancelled
    
    def get_process(self, process_id: str) -> Optional[ProcessInfo]:
        """Get process info by ID."""
        return self.active_processes.get(process_id)
    
    def list_processes(self, run_id: Optional[str] = None, status: Optional[str] = None) -> list[ProcessInfo]:
        """List processes, optionally filtered by run_id or status."""
        processes = list(self.active_processes.values())
        
        if run_id:
            processes = [p for p in processes if p.run_id == run_id]
        
        if status:
            processes = [p for p in processes if p.status == status]
        
        return processes
    
    def get_run_processes(self, run_id: str) -> list[ProcessInfo]:
        """Get all processes for a specific run."""
        if run_id not in self.run_processes:
            return []
        
        return [
            self.active_processes[pid]
            for pid in self.run_processes[run_id]
            if pid in self.active_processes
        ]
    
    def cleanup_completed(self, max_age_seconds: int = 3600):
        """Remove completed/failed/cancelled processes older than max_age."""
        now = datetime.utcnow()
        to_remove = []
        
        for process_id, process in self.active_processes.items():
            if process.status in ["completed", "failed", "cancelled"]:
                if process.completed_at:
                    age = (now - process.completed_at).total_seconds()
                    if age > max_age_seconds:
                        to_remove.append(process_id)
        
        for process_id in to_remove:
            process = self.active_processes[process_id]
            del self.active_processes[process_id]
            
            # Also clean up from run_processes
            if process.run_id in self.run_processes:
                self.run_processes[process.run_id].remove(process_id)
                if not self.run_processes[process.run_id]:
                    del self.run_processes[process.run_id]
        
        if to_remove:
            logger.info(f"Cleaned up {len(to_remove)} old processes")
    
    def get_stats(self) -> dict:
        """Get process statistics."""
        running = sum(1 for p in self.active_processes.values() if p.status == "running")
        completed = sum(1 for p in self.active_processes.values() if p.status == "completed")
        failed = sum(1 for p in self.active_processes.values() if p.status == "failed")
        cancelled = sum(1 for p in self.active_processes.values() if p.status == "cancelled")
        
        return {
            "total": len(self.active_processes),
            "running": running,
            "completed": completed,
            "failed": failed,
            "cancelled": cancelled,
            "active_runs": len(self.run_processes)
        }


# Global process manager
_process_manager: Optional[ProcessManager] = None


def get_process_manager() -> ProcessManager:
    """Get the global process manager instance."""
    global _process_manager
    if _process_manager is None:
        _process_manager = ProcessManager()
    return _process_manager
