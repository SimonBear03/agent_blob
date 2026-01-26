"""
Agent runtime - processes agent requests and yields event stream.

This is the core agent loop that's decoupled from transport (WebSocket/HTTP).
"""
import os
import json
from pathlib import Path
from typing import AsyncIterator, Dict, Any, Optional
from openai import AsyncOpenAI
import logging

from .db.messages import MessagesDB
from .db.sessions import SessionsDB
from .db.audit import AuditDB

logger = logging.getLogger(__name__)


class AgentRuntime:
    """Agent runtime with tool execution and LLM integration."""
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        model_name: Optional[str] = None,
        system_prompt_path: Optional[str] = None
    ):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.model_name = model_name or os.getenv("MODEL_NAME", "gpt-4o")
        self.client = AsyncOpenAI(api_key=self.api_key) if self.api_key else None
        
        # Load system prompt
        if system_prompt_path:
            self.system_prompt = self._load_system_prompt(system_prompt_path)
        else:
            default_path = Path(__file__).parent.parent.parent / "shared" / "prompts" / "system.md"
            self.system_prompt = self._load_system_prompt(str(default_path))
        
        # Get tool registry (will be imported when tools are implemented)
        self.registry = None  # TODO: from .tools import get_registry
    
    def _load_system_prompt(self, path: str) -> str:
        """Load system prompt from file."""
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return f.read()
        except Exception as e:
            logger.warning(f"Could not load system prompt from {path}: {e}")
            return "You are a helpful AI assistant with access to tools and persistent memory."
    
    async def process(self, request) -> AsyncIterator[Dict[str, Any]]:
        """
        Process an agent request and yield event stream.
        
        Args:
            request: QueuedRequest with session_id, message, run_id
        
        Yields:
            Event dicts: {type: "event", event: "...", payload: {...}}
        """
        session_id = request.session_id
        message = request.message
        run_id = request.run_id
        
        if not self.client:
            yield {
                "type": "event",
                "event": "error",
                "payload": {
                    "runId": run_id,
                    "message": "OpenAI API key not configured",
                    "retryable": False,
                    "errorCode": "NO_API_KEY"
                }
            }
            return
        
        try:
            # Save user message
            MessagesDB.create_message(session_id, "user", message)
            
            # Update session timestamp (for activity sorting)
            SessionsDB.update_session(session_id)
            
            # Yield status: thinking
            yield {
                "type": "event",
                "event": "status",
                "payload": {
                    "runId": run_id,
                    "status": "thinking"
                }
            }
            
            # Build conversation history
            messages = self._build_messages(session_id)
            
            # Get available tools (will be implemented later)
            tools = []  # TODO: self.registry.to_openai_functions() if self.registry else []
            
            # Agent loop
            iteration = 0
            max_iterations = 10
            collected_content = ""
            
            while iteration < max_iterations:
                iteration += 1
                
                # Call OpenAI with streaming
                response_stream = await self.client.chat.completions.create(
                    model=self.model_name,
                    messages=messages,
                    tools=tools if tools else None,
                    stream=True
                )
                
                # Yield status: streaming
                yield {
                    "type": "event",
                    "event": "status",
                    "payload": {
                        "runId": run_id,
                        "status": "streaming"
                    }
                }
                
                # Stream tokens
                tool_calls_accumulator = {}
                async for chunk in response_stream:
                    delta = chunk.choices[0].delta
                    
                    # Stream content tokens
                    if delta.content:
                        collected_content += delta.content
                        yield {
                            "type": "event",
                            "event": "token",
                            "payload": {
                                "runId": run_id,
                                "content": delta.content,
                                "delta": True
                            }
                        }
                    
                    # Accumulate tool calls
                    if delta.tool_calls:
                        for tc_delta in delta.tool_calls:
                            idx = tc_delta.index
                            if idx not in tool_calls_accumulator:
                                tool_calls_accumulator[idx] = {
                                    "id": tc_delta.id or "",
                                    "type": "function",
                                    "function": {
                                        "name": tc_delta.function.name or "",
                                        "arguments": tc_delta.function.arguments or ""
                                    }
                                }
                            else:
                                if tc_delta.function.name:
                                    tool_calls_accumulator[idx]["function"]["name"] += tc_delta.function.name
                                if tc_delta.function.arguments:
                                    tool_calls_accumulator[idx]["function"]["arguments"] += tc_delta.function.arguments
                
                # Check if there are tool calls
                if not tool_calls_accumulator:
                    # No tool calls - we're done
                    break
                
                # Process tool calls
                tool_calls = list(tool_calls_accumulator.values())
                
                # Save assistant message with tool calls
                tool_calls_json = json.dumps(tool_calls)
                MessagesDB.create_message(
                    session_id,
                    "assistant",
                    collected_content or "",
                    tool_calls=tool_calls_json
                )
                
                # Add to messages history
                messages.append({
                    "role": "assistant",
                    "content": collected_content or "",
                    "tool_calls": tool_calls
                })
                
                # Execute tool calls
                for tool_call in tool_calls:
                    tool_name = tool_call["function"]["name"]
                    tool_args_str = tool_call["function"]["arguments"]
                    
                    # Yield tool_call event
                    yield {
                        "type": "event",
                        "event": "tool_call",
                        "payload": {
                            "runId": run_id,
                            "toolName": tool_name,
                            "arguments": json.loads(tool_args_str) if tool_args_str else {}
                        }
                    }
                    
                    # Yield status: executing_tool
                    yield {
                        "type": "event",
                        "event": "status",
                        "payload": {
                            "runId": run_id,
                            "status": "executing_tool"
                        }
                    }
                    
                    # Execute tool (placeholder for now)
                    try:
                        # TODO: Execute actual tool
                        result = {
                            "success": True,
                            "message": f"Tool {tool_name} would be executed here"
                        }
                        result_str = json.dumps(result)
                        error_str = None
                    except Exception as e:
                        result = {"success": False, "error": str(e)}
                        result_str = json.dumps(result)
                        error_str = str(e)
                    
                    # Log to audit
                    AuditDB.log_tool_execution(
                        tool_name=tool_name,
                        parameters=tool_args_str,
                        result=result_str,
                        error=error_str,
                        session_id=session_id
                    )
                    
                    # Save tool response message
                    MessagesDB.create_message(
                        session_id,
                        "tool",
                        result_str,
                        tool_call_id=tool_call["id"],
                        name=tool_name
                    )
                    
                    # Yield tool_result event
                    yield {
                        "type": "event",
                        "event": "tool_result",
                        "payload": {
                            "runId": run_id,
                            "toolName": tool_name,
                            "result": result
                        }
                    }
                    
                    # Add tool response to messages
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call["id"],
                        "name": tool_name,
                        "content": result_str
                    })
                
                # Reset for next iteration
                collected_content = ""
            
            # Save final assistant message if we have content
            if collected_content:
                saved_msg = MessagesDB.create_message(
                    session_id,
                    "assistant",
                    collected_content
                )
            else:
                saved_msg = {"id": "unknown"}
            
            # Update session timestamp
            SessionsDB.update_session(session_id)
            
            # Yield final event
            yield {
                "type": "event",
                "event": "final",
                "payload": {
                    "runId": run_id,
                    "messageId": saved_msg["id"],
                    "totalTokens": 0  # TODO: Get from response
                }
            }
        
        except Exception as e:
            logger.error(f"Error processing request {run_id}: {e}")
            yield {
                "type": "event",
                "event": "error",
                "payload": {
                    "runId": run_id,
                    "message": f"Agent processing failed: {str(e)}",
                    "retryable": False,
                    "errorCode": "AGENT_ERROR"
                }
            }
    
    def _build_messages(self, session_id: str) -> list:
        """Build message history for OpenAI API."""
        messages = [
            {"role": "system", "content": self.system_prompt}
        ]
        
        # Get session messages
        db_messages = MessagesDB.list_messages(session_id)
        
        for msg in db_messages:
            if msg["role"] == "user":
                messages.append({
                    "role": "user",
                    "content": msg["content"]
                })
            elif msg["role"] == "assistant":
                msg_dict = {
                    "role": "assistant",
                    "content": msg["content"]
                }
                if msg["tool_calls"]:
                    msg_dict["tool_calls"] = json.loads(msg["tool_calls"])
                messages.append(msg_dict)
            elif msg["role"] == "tool":
                messages.append({
                    "role": "tool",
                    "tool_call_id": msg["tool_call_id"],
                    "name": msg["name"],
                    "content": msg["content"]
                })
        
        return messages


# Global runtime instance
_runtime: Optional[AgentRuntime] = None


def get_runtime() -> AgentRuntime:
    """Get the global runtime instance."""
    global _runtime
    if _runtime is None:
        _runtime = AgentRuntime()
    return _runtime


def init_runtime(api_key: Optional[str] = None, model_name: Optional[str] = None) -> AgentRuntime:
    """Initialize the runtime with specific configuration."""
    global _runtime
    _runtime = AgentRuntime(api_key=api_key, model_name=model_name)
    return _runtime
