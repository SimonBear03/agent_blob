"""
TUI (Text User Interface) for Agent Blob CLI.

Modern chat interface with persistent history, status bar, and fixed input.
"""
import asyncio
from datetime import datetime
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field

from rich.console import Console, Group
from rich.layout import Layout
from rich.panel import Panel
from rich.text import Text
from rich.live import Live
from rich.table import Table
from rich.markdown import Markdown

console = Console()


@dataclass
class Message:
    """A single chat message."""
    role: str  # "user" or "assistant"
    content: str
    timestamp: Optional[str] = None
    streaming: bool = False
    
    def to_renderable(self):
        """Convert message to Rich renderable."""
        if self.role == "user":
            prefix = Text("You: ", style="bold cyan")
        elif self.role == "system":
            prefix = Text("System: ", style="bold red")
        else:
            prefix = Text("Assistant: ", style="bold green")
        
        # For long messages, wrap them nicely
        content = Text(self.content)
        if self.streaming:
            content.append("▊", style="bold")
        
        return Group(prefix, content)


@dataclass
class ChatState:
    """Current state of the chat interface."""
    session_id: Optional[str] = None
    session_title: str = "New conversation"
    messages: List[Message] = field(default_factory=list)
    status: str = "Connected"
    status_style: str = "green"
    streaming: bool = False
    current_message_buffer: str = ""
    
    def add_message(self, role: str, content: str):
        """Add a complete message to history."""
        self.messages.append(Message(
            role=role,
            content=content,
            timestamp=datetime.now().isoformat()
        ))
    
    def start_streaming(self):
        """Start a new assistant message."""
        self.streaming = True
        self.current_message_buffer = ""
        self.messages.append(Message(
            role="assistant",
            content="",
            streaming=True
        ))
    
    def add_token(self, token: str):
        """Add a token to the current streaming message."""
        if self.streaming and self.messages:
            self.current_message_buffer += token
            self.messages[-1].content = self.current_message_buffer
            self.messages[-1].streaming = True
    
    def finish_streaming(self):
        """Finish the current streaming message."""
        if self.streaming and self.messages:
            self.messages[-1].streaming = False
            self.streaming = False
            self.current_message_buffer = ""
    
    def set_status(self, status: str, style: str = "green"):
        """Update status bar."""
        self.status = status
        self.status_style = style


class TUI:
    """Text User Interface manager."""
    
    def __init__(self):
        self.state = ChatState()
        self.layout = self._create_layout()
        self.live: Optional[Live] = None
    
    def _create_layout(self) -> Layout:
        """Create the split-screen layout."""
        layout = Layout()
        
        layout.split_column(
            Layout(name="header", size=3),
            Layout(name="chat", ratio=1),
            Layout(name="status", size=3),
            Layout(name="input_hint", size=2)
        )
        
        return layout
    
    def _render_header(self) -> Panel:
        """Render the header bar."""
        title = Text()
        title.append("Agent Blob", style="bold cyan")
        if self.state.session_title:
            title.append(f" - {self.state.session_title}", style="white")
        if self.state.session_id:
            title.append(f" ({self.state.session_id[:8]}...)", style="dim")
        
        return Panel(title, border_style="cyan")
    
    def _render_chat(self) -> Panel:
        """Render the chat message area."""
        if not self.state.messages:
            empty = Text("No messages yet. Start chatting below!", style="dim italic")
            return Panel(empty, border_style="blue", title="Chat")
        
        # Render last N messages (keep memory reasonable)
        max_messages = 50
        visible_messages = self.state.messages[-max_messages:]
        
        renderables = []
        for i, msg in enumerate(visible_messages):
            renderables.append(msg.to_renderable())
            # Add spacing between messages
            if i < len(visible_messages) - 1:
                renderables.append(Text(""))
        
        group = Group(*renderables)
        return Panel(group, border_style="blue", title="Chat")
    
    def _render_status(self) -> Panel:
        """Render the status bar."""
        status_text = Text()
        
        # Status indicator
        if self.state.status_style == "green":
            status_text.append("● ", style="bold green")
        elif self.state.status_style == "yellow":
            status_text.append("⏳ ", style="bold yellow")
        elif self.state.status_style == "blue":
            status_text.append("🔧 ", style="bold blue")
        else:
            status_text.append("● ", style="bold red")
        
        status_text.append(self.state.status, style=self.state.status_style)
        
        return Panel(status_text, border_style=self.state.status_style)
    
    def _render_input_hint(self) -> Panel:
        """Render input hint."""
        hint = Text()
        hint.append("Ctrl+J", style="cyan")
        hint.append(" = new line │ ", style="dim")
        hint.append("Ctrl+C", style="cyan")
        hint.append(" = quit │ ", style="dim")
        hint.append("/help", style="cyan")
        hint.append(" for commands", style="dim")
        
        return Panel(hint, border_style="dim")
    
    def render(self):
        """Render the entire UI."""
        self.layout["header"].update(self._render_header())
        self.layout["chat"].update(self._render_chat())
        self.layout["status"].update(self._render_status())
        self.layout["input_hint"].update(self._render_input_hint())
    
    def start(self):
        """Start the live display."""
        self.live = Live(
            self.layout,
            console=console,
            refresh_per_second=10,
            screen=True
        )
        self.live.start()
        self.render()
    
    def stop(self):
        """Stop the live display."""
        if self.live:
            self.live.stop()
    
    def update(self):
        """Update the display."""
        self.render()
        if self.live:
            self.live.refresh()
    
    # State update methods
    
    def set_session(self, session_id: str, title: str, messages: List[Dict[str, Any]] = None):
        """Set current session and load messages."""
        self.state.session_id = session_id
        self.state.session_title = title
        
        # Load previous messages
        if messages:
            self.state.messages = []
            # Only show last 4 messages for context
            recent = messages[-4:] if len(messages) > 4 else messages
            for msg in recent:
                self.state.add_message(
                    role=msg.get("role"),
                    content=msg.get("content", "")
                )
        
        self.update()
    
    def add_user_message(self, content: str):
        """Add a user message."""
        self.state.add_message("user", content)
        self.update()
    
    def start_assistant_message(self):
        """Start streaming assistant response."""
        self.state.start_streaming()
        self.state.set_status("Streaming...", "green")
        self.update()
    
    def add_token(self, token: str):
        """Add token to streaming message."""
        self.state.add_token(token)
        self.update()
    
    def finish_assistant_message(self):
        """Finish streaming message."""
        self.state.finish_streaming()
        self.state.set_status("Connected", "green")
        self.update()
    
    def set_status(self, status: str, style: str = "green"):
        """Update status."""
        self.state.set_status(status, style)
        self.update()
    
    def show_error(self, message: str):
        """Show error message."""
        self.state.add_message("assistant", f"❌ Error: {message}")
        self.state.set_status("Error", "red")
        self.update()
    
    def clear_messages(self):
        """Clear all messages."""
        self.state.messages = []
        self.update()


def create_session_picker_panel(sessions: List[Dict[str, Any]]) -> Panel:
    """Create a session picker display."""
    if not sessions:
        content = Text()
        content.append("No existing sessions.\n\n", style="dim")
        content.append("[N] ", style="bold cyan")
        content.append("New conversation\n")
        return Panel(content, title="Select Session", border_style="cyan")
    
    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column("Index", style="bold cyan", width=4)
    table.add_column("Title", style="white")
    table.add_column("Info", style="dim")
    
    for i, session in enumerate(sessions, 1):
        title = session.get("title", "Untitled")
        message_count = session.get("messageCount", 0)
        updated_at = session.get("updatedAt", "")
        
        # Calculate relative time
        time_ago = _format_time_ago(updated_at)
        info_text = f"({message_count} messages) • {time_ago}"
        
        table.add_row(f"{i}.", title, info_text)
    
    content = Group(
        Text("Select a session to continue or start a new one:", style="bold"),
        Text(""),
        table,
        Text(""),
        Text("[N] ", style="bold cyan") + Text("New conversation")
    )
    
    return Panel(content, title="Select Session", border_style="cyan")


def _format_time_ago(timestamp: str) -> str:
    """Format timestamp as relative time."""
    try:
        from datetime import datetime
        dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
        now = datetime.now(dt.tzinfo)
        diff = now - dt
        
        seconds = diff.total_seconds()
        if seconds < 60:
            return "just now"
        elif seconds < 3600:
            return f"{int(seconds // 60)}m ago"
        elif seconds < 86400:
            return f"{int(seconds // 3600)}h ago"
        else:
            return f"{int(seconds // 86400)}d ago"
    except:
        return "unknown"
