"""
Process management tools for the LLM.

These tools allow the agent to list, check status, cancel, and get wait time estimates for running processes.
"""
from typing import Optional
from . import ToolDefinition, ToolRegistry
from ..processes import get_process_manager


async def process_list(run_id: Optional[str] = None, status: Optional[str] = None) -> dict:
    """
    List active processes, optionally filtered by run_id or status.
    
    Args:
        run_id: Filter by specific run ID (optional)
        status: Filter by status: "running", "completed", "cancelled", "failed" (optional)
    
    Returns:
        dict with processes array and stats
    """
    manager = get_process_manager()
    processes = manager.list_processes(run_id=run_id, status=status)
    
    formatted_processes = []
    for process in processes:
        formatted_processes.append({
            "id": process.id,
            "run_id": process.run_id,
            "tool_name": process.tool_name,
            "status": process.status,
            "progress": process.progress,
            "created_at": process.created_at.isoformat(),
            "completed_at": process.completed_at.isoformat() if process.completed_at else None
        })
    
    return {
        "success": True,
        "processes": formatted_processes,
        "count": len(formatted_processes),
        "stats": manager.get_stats()
    }


async def process_status(process_id: str) -> dict:
    """
    Get detailed status of a specific process.
    
    Args:
        process_id: ID of the process to check
    
    Returns:
        dict with process details
    """
    manager = get_process_manager()
    process = manager.get_process(process_id)
    
    if not process:
        return {
            "success": False,
            "error": f"Process not found: {process_id}"
        }
    
    return {
        "success": True,
        "process": {
            "id": process.id,
            "run_id": process.run_id,
            "tool_name": process.tool_name,
            "status": process.status,
            "progress": process.progress,
            "created_at": process.created_at.isoformat(),
            "completed_at": process.completed_at.isoformat() if process.completed_at else None,
            "error": process.error
        }
    }


async def process_cancel(process_id: str) -> dict:
    """
    Cancel a running process.
    
    Args:
        process_id: ID of the process to cancel
    
    Returns:
        dict with success status
    """
    manager = get_process_manager()
    success = await manager.cancel_process(process_id)
    
    if success:
        return {
            "success": True,
            "message": f"Process {process_id} cancelled successfully"
        }
    else:
        return {
            "success": False,
            "error": f"Could not cancel process {process_id} (not found or not running)"
        }


async def process_wait_time(run_id: Optional[str] = None) -> dict:
    """
    Get estimated wait time based on current queue and running processes.
    
    Args:
        run_id: Check wait time for a specific run (optional)
    
    Returns:
        dict with wait time estimates
    """
    manager = get_process_manager()
    stats = manager.get_stats()
    
    # Simple estimation: count running processes
    running_count = stats["running"]
    
    # Rough estimate: assume each process takes ~30 seconds on average
    estimated_seconds = running_count * 30
    
    return {
        "success": True,
        "running_processes": running_count,
        "estimated_wait_seconds": estimated_seconds,
        "estimated_wait_human": f"{estimated_seconds // 60}m {estimated_seconds % 60}s" if estimated_seconds >= 60 else f"{estimated_seconds}s",
        "stats": stats
    }


def register_tools(registry: ToolRegistry):
    """Register process management tools."""
    
    # process.list
    registry.register(ToolDefinition(
        name="process_list",
        description="List active processes. Use this when the user asks what's currently running or wants to see ongoing operations.",
        parameters={
            "type": "object",
            "properties": {
                "run_id": {
                    "type": "string",
                    "description": "Filter by specific run ID (optional)"
                },
                "status": {
                    "type": "string",
                    "enum": ["running", "completed", "cancelled", "failed"],
                    "description": "Filter by status (optional)"
                }
            },
            "required": []
        },
        executor=process_list
    ))
    
    # process.status
    registry.register(ToolDefinition(
        name="process_status",
        description="Get detailed status of a specific process.",
        parameters={
            "type": "object",
            "properties": {
                "process_id": {
                    "type": "string",
                    "description": "ID of the process to check"
                }
            },
            "required": ["process_id"]
        },
        executor=process_status
    ))
    
    # process.cancel
    registry.register(ToolDefinition(
        name="process_cancel",
        description="Cancel a running process. Use this when the user wants to stop a long-running operation.",
        parameters={
            "type": "object",
            "properties": {
                "process_id": {
                    "type": "string",
                    "description": "ID of the process to cancel"
                }
            },
            "required": ["process_id"]
        },
        executor=process_cancel
    ))
    
    # process.wait_time
    registry.register(ToolDefinition(
        name="process_wait_time",
        description="Get estimated wait time based on current queue. Use this when the user asks how long something will take.",
        parameters={
            "type": "object",
            "properties": {
                "run_id": {
                    "type": "string",
                    "description": "Check wait time for a specific run (optional)"
                }
            },
            "required": []
        },
        executor=process_wait_time
    ))
