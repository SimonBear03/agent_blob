#!/usr/bin/env python3
import asyncio
import sys
from pathlib import Path

# Ensure repo root is on sys.path when running as a script.
root_dir = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root_dir))

from agent_blob.clients.cli import main


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
