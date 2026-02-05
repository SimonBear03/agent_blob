#!/usr/bin/env python3
import sys
import os
from pathlib import Path

import uvicorn
from dotenv import load_dotenv

load_dotenv()

if __name__ == "__main__":
    # Ensure repo root is on sys.path when running as a script.
    root_dir = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root_dir))

    from agent_blob.gateway.app import create_app
    from agent_blob import config

    host = config.gateway_host()
    port = config.gateway_port()

    app = create_app()
    uvicorn.run(app, host=host, port=port)
