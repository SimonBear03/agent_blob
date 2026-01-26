#!/usr/bin/env python3
"""
Start the Agent Blob Gateway.

This script ensures proper Python path setup and starts the gateway server.
"""
import sys
import os
from pathlib import Path

# Add apps directory to Python path
root_dir = Path(__file__).parent
apps_dir = root_dir / "apps"
sys.path.insert(0, str(apps_dir))

# Import and run gateway
if __name__ == "__main__":
    from gateway.main import app
    import uvicorn
    
    host = os.getenv("GATEWAY_HOST", "127.0.0.1")
    port = int(os.getenv("GATEWAY_PORT", "18789"))
    
    print(f"🚀 Starting Agent Blob Gateway on {host}:{port}")
    print(f"📡 WebSocket endpoint: ws://{host}:{port}/ws")
    print(f"🔍 Health check: http://{host}:{port}/health")
    print()
    
    uvicorn.run(app, host=host, port=port)
