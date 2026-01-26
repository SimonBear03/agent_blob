#!/usr/bin/env python3
"""
Agent Blob TUI - Interactive Text User Interface

Modern chat interface with persistent history, similar to Codex/Claude Code.
"""
import asyncio
import argparse
import sys
import logging
from pathlib import Path
from typing import Optional
import os

from prompt_toolkit import PromptSession
from prompt_toolkit.history import FileHistory
from prompt_toolkit.key_binding import KeyBindings

from .connection import GatewayConnection
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

# Setup logging (to file, not stdout)
logging.basicConfig(
    level=logging.WARNING,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    filename='/tmp/agent_blob_cli.log'
)
logger = logging.getLogger(__name__)

console = Console()


class SimpleTUI:
    """Simplified TUI that works better with prompt_toolkit."""
    
    def __init__(self):
        self.session_id = None
        self.session_title = "New conversation"
        self.messages = []
        self.status = "Connected"
        self.status_color = "green"
        self.model_name = "gpt-4o"
        self.tokens_used = 0
        self.tokens_limit = 128000  # Default for gpt-4o
        self.message_count = 0
    
    def clear_screen(self):
        """Clear the screen."""
        os.system('clear' if os.name != 'nt' else 'cls')

    def _print_status_block(self):
        """Print a stationary-looking status/input block."""
        status_icon = "●" if self.status_color == "green" else "⏳" if self.status_color == "yellow" else "🔧"
        context_pct = (self.tokens_used / self.tokens_limit * 100) if self.tokens_limit > 0 else 0
        context_color = "green" if context_pct < 60 else "yellow" if context_pct < 85 else "red"
        tokens_k = self.tokens_used / 1000
        limit_k = self.tokens_limit / 1000
        context_str = f"{tokens_k:.1f}K/{limit_k:.0f}K ({context_pct:.0f}%)"
        status_line = (
            f"{status_icon} {self.status} │ 📝 {self.message_count} msgs │ 🤖 {self.model_name} "
            f"│ [{context_color}]📊 {context_str}[/{context_color}]"
        )
        hint_line = "Ctrl+J = new line │ Ctrl+C = quit │ /help"
        console.print(f"[dim]{'─' * console.width}[/dim]")
        console.print(status_line)
        console.print(f"[dim]{hint_line}[/dim]")
    
    def render_full(self):
        """Render the full UI."""
        self.clear_screen()
        if self.session_title:
            session_id = f"{self.session_id[:8]}..." if self.session_id else "unknown"
            console.print(f"[dim]Session: {self.session_title} ({session_id})[/dim]")
            console.print(f"[dim]{'─' * console.width}[/dim]\n")
        
        # Messages
        if not self.messages:
            console.print("[dim italic]No messages yet. Start chatting below![/dim italic]\n")
        else:
            for i, msg in enumerate(self.messages):
                role = msg.get("role")
                content = msg.get("content", "")
                streaming = msg.get("streaming", False)
                
                if role == "user":
                    console.print(f"[bold cyan]You:[/bold cyan]")
                    console.print(content)
                elif role == "system":
                    # System messages (gateway, commands)
                    console.print(f"[bold red]System:[/bold red]")
                    console.print(content)
                elif role == "assistant":
                    display_content = content
                    if streaming:
                        display_content += "▊"
                    console.print(f"[bold green]Assistant:[/bold green]")
                    console.print(display_content)
                
                # Add spacing between messages
                if i < len(self.messages) - 1:
                    console.print()
        
        console.print()

        # Status + input block
        self._print_status_block()
    
    def add_user_message(self, content: str):
        """Add user message."""
        self.messages.append({
            "role": "user",
            "content": content,
            "streaming": False
        })
        self.message_count += 1
        self.render_full()
    
    def start_assistant_message(self):
        """Start assistant message."""
        self.messages.append({
            "role": "assistant",
            "content": "",
            "streaming": True
        })
        self.status = "Streaming..."
        self.status_color = "green"
        self.render_full()
    
    def add_token(self, token: str):
        """Add token to current message."""
        if self.messages and self.messages[-1]["role"] == "assistant":
            self.messages[-1]["content"] += token
            # Only re-render every few tokens to avoid flickering
            if len(self.messages[-1]["content"]) % 10 == 0:
                self.render_full()
    
    def finish_assistant_message(self):
        """Finish assistant message."""
        if self.messages and self.messages[-1]["role"] == "assistant":
            self.messages[-1]["streaming"] = False
            self.message_count += 1
        self.status = "Connected"
        self.status_color = "green"
        self.render_full()
    
    def set_status(self, status: str, color: str = "green"):
        """Set status."""
        self.status = status
        self.status_color = color
        self.render_full()
    
    def set_session(self, session_id: str, title: str, messages: list = None):
        """Set session."""
        self.session_id = session_id
        self.session_title = title
        self.messages = []
        if messages:
            self.message_count = len(messages)
            for msg in messages:
                self.messages.append({
                    "role": msg.get("role"),
                    "content": msg.get("content", ""),
                    "streaming": False
                })
        else:
            self.message_count = 0
        
        self.render_full()
    
    def update_stats(self, **kwargs):
        """Update session statistics."""
        if "model_name" in kwargs:
            self.model_name = kwargs["model_name"]
        if "tokens_used" in kwargs:
            self.tokens_used = kwargs["tokens_used"]
        if "tokens_limit" in kwargs:
            self.tokens_limit = kwargs["tokens_limit"]
        if "message_count" in kwargs:
            self.message_count = kwargs["message_count"]
    
    def show_error(self, message: str):
        """Show error."""
        self.messages.append({
            "role": "assistant",
            "content": f"❌ Error: {message}",
            "streaming": False
        })
        self.status = "Error"
        self.status_color = "red"
        self.render_full()
    
    def clear_messages(self):
        """Clear messages."""
        self.messages = []
        self.render_full()


class AgentBlobTUI:
    """Main TUI application."""
    
    def __init__(self, uri: str, auto_mode: Optional[str] = None):
        self.uri = uri
        self.auto_mode = auto_mode
        self.connection = GatewayConnection(uri)
        self.tui = SimpleTUI()
        self.current_run_id: Optional[str] = None
        self.streaming = False
        self.cancelling = False
        self.running = True
        
        # Setup prompt session
        history_file = Path.home() / ".agent_blob_history"
        self.prompt_session = PromptSession(
            history=FileHistory(str(history_file)),
            multiline=False,
            enable_history_search=True
        )
        
        # Key bindings
        self.kb = KeyBindings()
        
        @self.kb.add('escape', 'enter')
        def _(event):
            """Alt+Enter adds new line."""
            event.current_buffer.insert_text('\n')
        
        @self.kb.add('c-j')
        def _(event):
            """Ctrl+J adds new line."""
            event.current_buffer.insert_text('\n')
    
    async def run(self):
        """Main application loop."""
        try:
            # Determine session preference from auto_mode
            if self.auto_mode == "new":
                session_pref = "new"
            elif self.auto_mode == "continue":
                session_pref = "continue"
            else:
                session_pref = "auto"
            
            # Connect to gateway
            console.print("[dim]Connecting to gateway...[/dim]")
            initial_session = await self.connection.connect(
                client_type="tui",
                session_preference=session_pref,
                history_limit=None  # Load ALL messages for scrollable TUI
            )
            
            # Setup event handlers
            self.connection.on_session_changed = self._handle_session_changed
            self.connection.on_message = self._handle_message
            self.connection.on_token = self._handle_token
            self.connection.on_status = self._handle_status
            self.connection.on_error = self._handle_error
            self.connection.on_final = self._handle_final
            
            # Load initial session (gateway already decided which one)
            self._load_session(initial_session)
            
            # Show initial UI
            self.tui.render_full()
            
            # Main chat loop
            await self._chat_loop()
            
        except KeyboardInterrupt:
            pass
        except Exception as e:
            logger.exception("Fatal error")
            console.print(f"\n[red]Error: {e}[/red]")
            await asyncio.sleep(2)
        finally:
            await self.connection.disconnect()
    
    def _load_session(self, session_payload: dict):
        """Load session."""
        session_id = session_payload.get("sessionId")
        title = session_payload.get("title", "New conversation")
        messages = session_payload.get("messages", [])
        stats = session_payload.get("stats", {})
        
        self.tui.set_session(session_id, title, messages)
        
        # Update stats if provided
        if stats:
            self.tui.update_stats(
                model_name=stats.get("modelName", "gpt-4o"),
                tokens_used=stats.get("tokensUsed", 0),
                tokens_limit=stats.get("tokensLimit", 128000),
                message_count=stats.get("messageCount", len(messages))
            )
    
    async def _chat_loop(self):
        """Main chat loop."""
        while self.running:
            try:
                # Get input
                user_input = await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: self.prompt_session.prompt("> ", key_bindings=self.kb)
                )
                
                if not user_input.strip():
                    continue
                
                # Only handle local UI command (quit)
                if user_input.strip().lower() in ["/quit", "/exit"]:
                    self.running = False
                    break
                
                # Add user message to UI
                self.tui.add_user_message(user_input)
                
                # Send to gateway
                run_id = await self.connection.send_message(user_input)
                
                if run_id:
                    self.streaming = True
                    self.current_run_id = run_id
                    
                    # Wait for completion
                    while self.streaming:
                        await asyncio.sleep(0.1)
            
            except KeyboardInterrupt:
                if self.streaming and self.current_run_id:
                    self.tui.set_status("Cancelling...", "yellow")
                    await self.connection.cancel_request(self.current_run_id)
                    self.streaming = False
                    self.cancelling = True
                else:
                    self.running = False
                    break
            
            except EOFError:
                self.running = False
                break
    
    
    # Event handlers
    
    async def _handle_session_changed(self, payload: dict):
        """Handle session changed."""
        self._load_session(payload)
    
    async def _handle_message(self, payload: dict):
        """Handle message."""
        role = payload.get("role")
        content = payload.get("content")
        from_self = payload.get("fromSelf", False)
        
        if role == "user" and not from_self:
            # Message from another client
            self.tui.messages.append({
                "role": "user",
                "content": f"📱 [From another client] {content}",
                "streaming": False
            })
            self.tui.render_full()
        elif role == "system":
            # System message (gateway welcome, command responses, etc.)
            self.tui.messages.append({
                "role": "system",
                "content": content,
                "streaming": False
            })
            self.tui.render_full()
        elif role == "assistant":
            # Assistant messages are handled via streaming (STATUS → TOKEN → FINAL)
            # Only show them here if we're NOT currently streaming
            # (e.g., when loading history or for non-streamed responses)
            if not self.streaming:
                self.tui.messages.append({
                    "role": "assistant",
                    "content": content,
                    "streaming": False
                })
                self.tui.render_full()
    
    async def _handle_token(self, payload: dict):
        """Handle token."""
        if self.cancelling:
            return
        content = payload.get("content", "")
        self.tui.add_token(content)
    
    async def _handle_status(self, payload: dict):
        """Handle status."""
        status = payload.get("status")
        run_id = payload.get("runId")
        
        # Respond to status events from any client in this session
        # (not just our own requests)
        if status == "streaming":
            self.streaming = True
            self.tui.start_assistant_message()
        elif status == "thinking":
            self.tui.set_status("Thinking...", "yellow")
        elif status == "executing_tool":
            self.tui.set_status("Using tools...", "blue")
    
    async def _handle_error(self, payload: dict):
        """Handle error."""
        message = payload.get("message")
        self.tui.show_error(message)
        self.streaming = False
        self.cancelling = False
    
    async def _handle_final(self, payload: dict):
        """Handle final event from any client in this session."""
        run_id = payload.get("runId")
        
        if self.cancelling:
            self.tui.messages.append({
                "role": "assistant",
                "content": "⚠️ Request cancelled",
                "streaming": False
            })
            self.tui.set_status("Connected", "green")
            self.cancelling = False
        else:
            self.tui.finish_assistant_message()
            
            # Update token usage and model if provided
            usage = payload.get("usage", {})
            model = payload.get("model")
            
            if usage:
                # Add new tokens to running total
                new_tokens = usage.get("totalTokens", 0)
                stats_update = {"tokens_used": self.tui.tokens_used + new_tokens}
                
                # Update model if provided (ensures we show the actual model being used)
                if model:
                    stats_update["model_name"] = model
                
                self.tui.update_stats(**stats_update)
        
        # Always stop streaming when any request completes
        # (gateway processes requests sequentially per session)
        self.streaming = False
        
        # Only clear current_run_id if this was OUR request
        if run_id == self.current_run_id:
            self.current_run_id = None


def main():
    """TUI entry point."""
    parser = argparse.ArgumentParser(description="Agent Blob TUI")
    parser.add_argument("--uri", default="ws://127.0.0.1:3336/ws")
    parser.add_argument("--continue", action="store_true", dest="continue_session")
    parser.add_argument("--new", action="store_true")
    parser.add_argument("--debug", action="store_true")
    
    args = parser.parse_args()
    
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
    
    auto_mode = None
    if args.continue_session:
        auto_mode = "continue"
    elif args.new:
        auto_mode = "new"
    
    tui = AgentBlobTUI(args.uri, auto_mode)
    asyncio.run(tui.run())


if __name__ == "__main__":
    main()
