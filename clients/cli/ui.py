"""
UI rendering and display logic using Rich.
"""
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.spinner import Spinner
from rich.live import Live
from rich.text import Text
from rich.table import Table
from datetime import datetime
from typing import List, Dict, Any, Optional

console = Console()


def print_header():
    """Print application header."""
    header = Text()
    header.append("Agent Blob CLI", style="bold cyan")
    header.append(" v0.1.1", style="dim")
    console.print(Panel(header, border_style="cyan"))


def print_connection_status(
    uri: str,
    session_id: str,
    session_title: str,
    stats: dict = None
):
    """Print connection status with optional stats."""
    status = Text()
    status.append("●", style="bold green")
    status.append(f" Connected to {uri}\n", style="green")
    status.append(f"Session: {session_title} ", style="cyan")
    status.append(f"({session_id[:8]}...)", style="dim")
    
    # Add stats if provided
    if stats:
        status.append("\n")
        msg_count = stats.get("messageCount", 0)
        model = stats.get("modelName", "gpt-4o")
        tokens_used = stats.get("tokensUsed", 0)
        tokens_limit = stats.get("tokensLimit", 128000)
        
        # Calculate context percentage
        context_pct = (tokens_used / tokens_limit * 100) if tokens_limit > 0 else 0
        context_color = "green" if context_pct < 60 else "yellow" if context_pct < 85 else "red"
        
        # Format display
        tokens_k = tokens_used / 1000
        limit_k = tokens_limit / 1000
        
        status.append(f"📝 {msg_count} msgs", style="dim")
        status.append(" │ ", style="dim")
        status.append(f"🤖 {model}", style="dim")
        status.append(" │ ", style="dim")
        status.append(f"📊 {tokens_k:.1f}K/{limit_k:.0f}K ({context_pct:.0f}%)", style=context_color)
    
    console.print(status)
    console.print()


def print_user_message(content: str):
    """Print user message."""
    console.print(f"\n[bold cyan]You:[/bold cyan]")
    console.print(content)


def print_assistant_message_start():
    """Print assistant message header."""
    console.print(f"\n[bold green]Assistant:[/bold green]")
    # Next line starts the content (streaming tokens)


def print_token(content: str):
    """Print a single token (inline, no newline)."""
    console.print(content, end="", markup=False)


def print_status(status: str):
    """Print status indicator."""
    status_styles = {
        "thinking": ("⏳", "yellow"),
        "executing_tool": ("🔧", "blue"),
        "streaming": ("✍️", "green"),
        "done": ("✅", "green")
    }
    
    icon, color = status_styles.get(status, ("●", "white"))
    console.print(f"[{color}]{icon} {status.replace('_', ' ').title()}...[/{color}]")


def print_error(message: str, retryable: bool = False):
    """Print error message."""
    style = "yellow" if retryable else "red"
    console.print(f"\n[{style}]❌ Error: {message}[/{style}]")
    if retryable:
        console.print("[dim]This error may be temporary. You can try again.[/dim]")


def print_cancelled():
    """Print cancellation message."""
    console.print("\n[yellow]⚠️  Request cancelled[/yellow]")


def print_help_hint():
    """Print simple help hint."""
    console.print("\n[dim]Local commands: /clear (clear screen), /quit (exit)[/dim]")
    console.print("[dim]Gateway commands: /help, /new, /sessions, /switch <n>, /status[/dim]")
    console.print("[dim]Type any gateway command to see details![/dim]\n")


def print_divider():
    """Print a subtle divider."""
    console.print("[dim]" + "─" * console.width + "[/dim]")


def clear_screen():
    """Clear the console screen."""
    console.clear()


def print_welcome_prompt():
    """Print the session picker prompt."""
    console.print("[bold]Select a session to continue or start a new one:[/bold]")
    console.print("[dim]Type a number (1-9) or 'N' for new conversation[/dim]\n")


def print_final_message(message_id: str):
    """Print completion indicator."""
    console.print(f"\n[dim]Message complete ({message_id[:8]}...)[/dim]\n")


class StreamingMessage:
    """Context manager for streaming message display."""
    
    def __init__(self):
        self.buffer = []
        self.in_progress = False
    
    def __enter__(self):
        print_assistant_message_start()
        self.in_progress = True
        return self
    
    def add_token(self, content: str):
        """Add a token to the stream."""
        self.buffer.append(content)
        print_token(content)
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        console.print()  # Newline after streaming
        self.in_progress = False
