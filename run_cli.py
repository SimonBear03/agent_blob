#!/usr/bin/env python3
"""
Convenient entry point for Agent Blob CLI.

Usage:
    python run_cli.py [--uri WS_URI] [--continue|--new] [--debug] [--simple]
"""
import sys
from pathlib import Path

# Add project root to Python path
root_dir = Path(__file__).parent
sys.path.insert(0, str(root_dir))

# Check if user wants simple CLI or TUI
if "--simple" in sys.argv:
    sys.argv.remove("--simple")
    # Run simple REPL-style CLI
    from clients.cli.cli import main
else:
    # Run modern TUI (default)
    from clients.cli.cli_tui import main

if __name__ == "__main__":
    main()
