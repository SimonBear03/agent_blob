"""
Agent loop implementation with OpenAI integration.
"""
import os
import json
from pathlib import Path
from typing import List, Dict, Any, Optional
from openai import AsyncOpenAI
from db.messages import MessagesDB
from db.threads import ThreadsDB
from db.audit import AuditDB
from tools import get_registry


class Agent:
    """Agent with tool execution and OpenAI integration."""
    
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
        
        # Get tool registry
        self.registry = get_registry()
    
    def _load_system_prompt(self, path: str) -> str:
        """Load system prompt from file."""
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return f.read()
        except Exception as e:
            print(f"Warning: Could not load system prompt from {path}: {e}")
            return "You are a helpful AI assistant with access to tools and persistent memory."
    
    async def run_conversation(
        self,
        thread_id: str,
        user_message: str,
        max_iterations: int = 10
    ) -> Dict[str, Any]:
        """
        Run a conversation turn with the agent.
        
        Args:
            thread_id: ID of the conversation thread
            user_message: User's message
            max_iterations: Maximum number of agent iterations (prevents infinite loops)
        
        Returns:
            Dict with assistant's final response
        """
        if not self.client:
            raise ValueError("OpenAI API key not configured")
        
        # Save user message
        MessagesDB.create_message(thread_id, "user", user_message)
        
        # Get conversation history
        messages = self._build_messages(thread_id)
        
        # Get available tools
        tools = self.registry.to_openai_functions()
        
        iteration = 0
        while iteration < max_iterations:
            iteration += 1
            
            # Call OpenAI
            response = await self.client.chat.completions.create(
                model=self.model_name,
                messages=messages,
                tools=tools,
                tool_choice="auto"
            )
            
            assistant_message = response.choices[0].message
            
            # Check if done (no tool calls)
            if not assistant_message.tool_calls:
                # Save assistant response
                saved_msg = MessagesDB.create_message(
                    thread_id,
                    "assistant",
                    assistant_message.content or ""
                )
                
                # Update thread timestamp
                ThreadsDB.update_thread(thread_id)
                
                return {
                    "success": True,
                    "message": saved_msg,
                    "iterations": iteration
                }
            
            # Save assistant message with tool calls
            tool_calls_json = json.dumps([
                {
                    "id": tc.id,
                    "type": tc.type,
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments
                    }
                }
                for tc in assistant_message.tool_calls
            ])
            
            MessagesDB.create_message(
                thread_id,
                "assistant",
                assistant_message.content or "",
                tool_calls=tool_calls_json
            )
            
            # Add assistant message to conversation
            messages.append({
                "role": "assistant",
                "content": assistant_message.content,
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": tc.type,
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments
                        }
                    }
                    for tc in assistant_message.tool_calls
                ]
            })
            
            # Execute tool calls
            for tool_call in assistant_message.tool_calls:
                tool_name = tool_call.function.name
                tool_args = json.loads(tool_call.function.arguments)
                
                # Execute tool
                try:
                    result = await self.registry.execute_tool(tool_name, tool_args)
                    result_str = json.dumps(result)
                    error_str = None
                except Exception as e:
                    result = {"success": False, "error": str(e)}
                    result_str = json.dumps(result)
                    error_str = str(e)
                
                # Log to audit
                AuditDB.log_tool_execution(
                    tool_name=tool_name,
                    parameters=json.dumps(tool_args),
                    result=result_str,
                    error=error_str,
                    thread_id=thread_id
                )
                
                # Save tool response message
                MessagesDB.create_message(
                    thread_id,
                    "tool",
                    result_str,
                    tool_call_id=tool_call.id,
                    name=tool_name
                )
                
                # Add tool response to conversation
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "name": tool_name,
                    "content": result_str
                })
        
        # Max iterations reached
        error_msg = f"Maximum iterations ({max_iterations}) reached without completion"
        saved_msg = MessagesDB.create_message(
            thread_id,
            "assistant",
            error_msg
        )
        
        return {
            "success": False,
            "error": error_msg,
            "message": saved_msg,
            "iterations": iteration
        }
    
    def _build_messages(self, thread_id: str) -> List[Dict[str, Any]]:
        """Build message history for OpenAI API."""
        messages = [
            {"role": "system", "content": self.system_prompt}
        ]
        
        # Get thread messages
        db_messages = MessagesDB.list_messages(thread_id)
        
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


# Global agent instance
_agent: Optional[Agent] = None


def get_agent() -> Agent:
    """Get the global agent instance."""
    global _agent
    if _agent is None:
        _agent = Agent()
    return _agent


def init_agent(api_key: Optional[str] = None, model_name: Optional[str] = None) -> Agent:
    """Initialize the agent with specific configuration."""
    global _agent
    _agent = Agent(api_key=api_key, model_name=model_name)
    return _agent
