"""
Filesystem tools for reading and writing files.
Enforces safety boundaries via ALLOWED_FS_ROOT.
"""
import os
from pathlib import Path
from typing import Optional
from tools import ToolDefinition, ToolRegistry


# Get allowed root from environment
ALLOWED_FS_ROOT = os.getenv("ALLOWED_FS_ROOT", os.getcwd())


def is_path_allowed(path: str) -> tuple[bool, str]:
    """
    Check if a path is within the allowed filesystem root.
    Returns (is_allowed, absolute_path).
    """
    try:
        # Resolve to absolute path
        abs_path = Path(path).resolve()
        allowed_root = Path(ALLOWED_FS_ROOT).resolve()
        
        # Check if path is within allowed root
        try:
            abs_path.relative_to(allowed_root)
            return True, str(abs_path)
        except ValueError:
            return False, str(abs_path)
    except Exception as e:
        return False, str(path)


async def read_file(path: str) -> dict:
    """
    Read a file from the filesystem.
    
    Args:
        path: Absolute or relative path to the file
    
    Returns:
        Dict with 'success', 'content'/'error', and 'path'
    """
    is_allowed, abs_path = is_path_allowed(path)
    
    if not is_allowed:
        return {
            "success": False,
            "error": f"Access denied: path '{path}' is outside allowed root '{ALLOWED_FS_ROOT}'",
            "path": abs_path
        }
    
    try:
        with open(abs_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        return {
            "success": True,
            "content": content,
            "path": abs_path
        }
    except FileNotFoundError:
        return {
            "success": False,
            "error": f"File not found: {abs_path}",
            "path": abs_path
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"Error reading file: {str(e)}",
            "path": abs_path
        }


async def write_file(path: str, content: str, create_dirs: bool = True) -> dict:
    """
    Write content to a file.
    
    Args:
        path: Absolute or relative path to the file
        content: Content to write
        create_dirs: Whether to create parent directories if they don't exist
    
    Returns:
        Dict with 'success', 'message'/'error', and 'path'
    """
    is_allowed, abs_path = is_path_allowed(path)
    
    if not is_allowed:
        return {
            "success": False,
            "error": f"Access denied: path '{path}' is outside allowed root '{ALLOWED_FS_ROOT}'",
            "path": abs_path
        }
    
    try:
        path_obj = Path(abs_path)
        
        # Create parent directories if needed
        if create_dirs:
            path_obj.parent.mkdir(parents=True, exist_ok=True)
        
        # Write file
        with open(abs_path, 'w', encoding='utf-8') as f:
            f.write(content)
        
        return {
            "success": True,
            "message": f"Successfully wrote {len(content)} bytes to {abs_path}",
            "path": abs_path
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"Error writing file: {str(e)}",
            "path": abs_path
        }


async def list_directory(path: str) -> dict:
    """
    List contents of a directory.
    
    Args:
        path: Absolute or relative path to the directory
    
    Returns:
        Dict with 'success', 'entries'/'error', and 'path'
    """
    is_allowed, abs_path = is_path_allowed(path)
    
    if not is_allowed:
        return {
            "success": False,
            "error": f"Access denied: path '{path}' is outside allowed root '{ALLOWED_FS_ROOT}'",
            "path": abs_path
        }
    
    try:
        path_obj = Path(abs_path)
        
        if not path_obj.exists():
            return {
                "success": False,
                "error": f"Directory not found: {abs_path}",
                "path": abs_path
            }
        
        if not path_obj.is_dir():
            return {
                "success": False,
                "error": f"Path is not a directory: {abs_path}",
                "path": abs_path
            }
        
        entries = []
        for item in path_obj.iterdir():
            entries.append({
                "name": item.name,
                "path": str(item),
                "is_file": item.is_file(),
                "is_dir": item.is_dir()
            })
        
        return {
            "success": True,
            "entries": entries,
            "path": abs_path
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"Error listing directory: {str(e)}",
            "path": abs_path
        }


def register_tools(registry: ToolRegistry):
    """Register filesystem tools with the registry."""
    
    # Read file tool
    read_tool = ToolDefinition(
        name="filesystem_read",
        description="Read the contents of a file from the filesystem. Only works within the allowed filesystem root.",
        parameters={
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Absolute or relative path to the file to read"
                }
            },
            "required": ["path"]
        },
        executor=read_file,
        metadata={
            "category": "filesystem",
            "audit_level": "full"
        }
    )
    
    # Write file tool
    write_tool = ToolDefinition(
        name="filesystem_write",
        description="Write content to a file. Creates parent directories if needed. Only works within the allowed filesystem root.",
        parameters={
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Absolute or relative path to the file to write"
                },
                "content": {
                    "type": "string",
                    "description": "Content to write to the file"
                },
                "create_dirs": {
                    "type": "boolean",
                    "description": "Whether to create parent directories if they don't exist (default: true)",
                    "default": True
                }
            },
            "required": ["path", "content"]
        },
        executor=write_file,
        metadata={
            "category": "filesystem",
            "audit_level": "full",
            "requires_confirmation": False
        }
    )
    
    # List directory tool
    list_tool = ToolDefinition(
        name="filesystem_list",
        description="List the contents of a directory. Only works within the allowed filesystem root.",
        parameters={
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Absolute or relative path to the directory to list"
                }
            },
            "required": ["path"]
        },
        executor=list_directory,
        metadata={
            "category": "filesystem",
            "audit_level": "summary"
        }
    )
    
    registry.register(read_tool)
    registry.register(write_tool)
    registry.register(list_tool)
