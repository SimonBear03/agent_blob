#!/usr/bin/env python3
"""
Agent Blob CLI - Interactive command-line client

Usage:
    python -m clients.cli.cli [--uri WS_URI] [--continue|--new]
"""
import asyncio
import argparse
import sys
import logging
from pathlib import Path
from typing import Optional

from prompt_toolkit import PromptSession
from prompt_toolkit.history import FileHistory
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.keys import Keys

from .connection import GatewayConnection
from . import ui

# Setup logging
logging.basicConfig(
    level=logging.WARNING,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class AgentBlobCLI:
    """Main CLI application."""
    
    def __init__(self, uri: str, auto_mode: Optional[str] = None):
        self.uri = uri
        self.auto_mode = auto_mode  # "continue" or "new" or None
        self.connection = GatewayConnection(uri)
        self.current_run_id: Optional[str] = None
        self.streaming = False
        self.cancelling = False
        
        # Setup prompt session with history
        history_file = Path.home() / ".agent_blob_history"
        self.prompt_session = PromptSession(
            history=FileHistory(str(history_file)),
            multiline=False,
            enable_history_search=True
        )
    
    async def run(self):
        """Main application loop."""
        try:
            # Print header
            ui.print_header()
            
            # Determine session preference
            if self.auto_mode == "new":
                session_pref = "new"
            elif self.auto_mode == "continue":
                session_pref = "continue"
            else:
                session_pref = "auto"
            
            # Connect to gateway
            ui.console.print("[dim]Connecting to gateway...[/dim]")
            initial_session = await self.connection.connect(
                client_type="cli",
                session_preference=session_pref
            )
            
            # Setup event handlers
            self.connection.on_session_changed = self._handle_session_changed
            self.connection.on_message = self._handle_message
            self.connection.on_token = self._handle_token
            self.connection.on_status = self._handle_status
            self.connection.on_error = self._handle_error
            self.connection.on_final = self._handle_final
            
            # Load initial session (gateway decided)
            self._display_session_messages(initial_session)
            
            # Print connection status
            ui.print_connection_status(
                self.uri,
                self.connection.current_session_id,
                initial_session.get("title", "Unknown"),
                stats=initial_session.get("stats")
            )
            
            # Main chat loop
            await self._chat_loop()
            
        except KeyboardInterrupt:
            ui.console.print("\n\n[dim]Goodbye![/dim]")
        except Exception as e:
            ui.console.print(f"\n[red]Error: {e}[/red]")
            logger.exception("Fatal error")
        finally:
            await self.connection.disconnect()
    
    async def _chat_loop(self):
        """Main chat interaction loop."""
        ui.console.print("[dim]Ctrl+C or /quit to exit | Type /help for commands[/dim]\n")
        
        while True:
            try:
                # Get user input
                user_input = await self._prompt_async("\n> ")
                
                if not user_input.strip():
                    continue
                
                # Only handle local UI command (quit)
                if user_input.strip().lower() in ["/quit", "/exit"]:
                    break
                
                # Send message (all commands go to gateway)
                ui.print_user_message(user_input)
                
                # Send to gateway
                run_id = await self.connection.send_message(user_input)
                
                # If it's a command (no run_id), don't wait for streaming
                if run_id:
                    self.streaming = True
                    self.current_run_id = run_id
                    
                    # Wait for completion
                    while self.streaming:
                        await asyncio.sleep(0.1)
                
            except KeyboardInterrupt:
                # Handle Ctrl+C
                if self.streaming and self.current_run_id:
                    # Cancel current request
                    ui.console.print("\n[yellow]Cancelling...[/yellow]")
                    await self.connection.cancel_request(self.current_run_id)
                    self.streaming = False
                    self.cancelling = True
                else:
                    # Exit CLI
                    raise
            except EOFError:
                # Ctrl+D pressed
                break
    
    async def _prompt_async(self, message: str) -> str:
        """Async wrapper for prompt_toolkit."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            lambda: self.prompt_session.prompt(message)
        )
    
    def _display_session_messages(self, session_payload: dict):
        """Display last 4 messages from a session."""
        messages = session_payload.get("messages", [])
        
        if messages:
            recent_messages = messages[-4:] if len(messages) > 4 else messages
            
            ui.console.print("\n[dim]━━━ Previous messages ━━━[/dim]")
            for i, msg in enumerate(recent_messages):
                role = msg.get("role")
                content = msg.get("content", "")
                
                if role == "user":
                    ui.console.print(f"[bold cyan]You:[/bold cyan]")
                    ui.console.print(content)
                elif role == "system":
                    ui.console.print(f"[bold red]System:[/bold red]")
                    ui.console.print(content)
                elif role == "assistant":
                    ui.console.print(f"[bold green]Assistant:[/bold green]")
                    ui.console.print(content)
                
                # Add empty line between messages (but not after the last one)
                if i < len(recent_messages) - 1:
                    ui.console.print()
            
            ui.console.print("[dim]━━━━━━━━━━━━━━━━━━━━━━[/dim]\n")
    
    # Event handlers
    
    async def _handle_session_changed(self, payload: dict):
        """Handle session changed event."""
        session_id = payload.get("sessionId")
        title = payload.get("title", "Unknown")
        
        logger.info(f"Session changed: {title} ({session_id})")
        
        # Display previous messages
        self._display_session_messages(payload)
    
    async def _handle_message(self, payload: dict):
        """Handle message event."""
        role = payload.get("role")
        content = payload.get("content")
        from_self = payload.get("fromSelf", False)
        
        if role == "user" and not from_self:
            # Message from another client
            ui.console.print(f"\n[dim]📱 [From another client][/dim] {content}")
        elif role == "system":
            # System message (gateway welcome, command responses, etc.)
            ui.console.print(f"\n[bold red]System:[/bold red]")
            ui.console.print(content)
        elif role == "assistant":
            # Assistant message (LLM responses)
            ui.console.print(f"\n[bold green]Assistant:[/bold green]")
            ui.console.print(content)
    
    async def _handle_token(self, payload: dict):
        """Handle token event (streaming)."""
        if self.cancelling:
            return
        content = payload.get("content", "")
        ui.print_token(content)
    
    async def _handle_status(self, payload: dict):
        """Handle status event."""
        status = payload.get("status")
        run_id = payload.get("runId")
        
        if run_id == self.current_run_id:
            if status == "streaming":
                ui.print_assistant_message_start()
    
    async def _handle_error(self, payload: dict):
        """Handle error event."""
        message = payload.get("message")
        retryable = payload.get("retryable", False)
        ui.print_error(message, retryable)
        self.streaming = False
        self.cancelling = False
    
    async def _handle_final(self, payload: dict):
        """Handle final event (completion)."""
        if self.cancelling:
            ui.print_cancelled()
            self.cancelling = False
        else:
            ui.console.print()  # Newline after streaming
        
        self.streaming = False
        self.current_run_id = None


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="Agent Blob CLI")
    parser.add_argument(
        "--uri",
        default="ws://127.0.0.1:3336/ws",
        help="WebSocket URI of gateway (default: ws://127.0.0.1:3336/ws)"
    )
    parser.add_argument(
        "--continue",
        action="store_true",
        dest="continue_session",
        help="Continue in most recent session (skip picker)"
    )
    parser.add_argument(
        "--new",
        action="store_true",
        help="Start a new session (skip picker)"
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging"
    )
    
    args = parser.parse_args()
    
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Determine auto mode
    auto_mode = None
    if args.continue_session:
        auto_mode = "continue"
    elif args.new:
        auto_mode = "new"
    
    # Run CLI
    cli = AgentBlobCLI(args.uri, auto_mode)
    asyncio.run(cli.run())


if __name__ == "__main__":
    main()
