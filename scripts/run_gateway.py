#!/usr/bin/env python3
"""
Start the Agent Blob Gateway.

Usage:
    python scripts/run_gateway.py
    OR (from venv):
    source venv/bin/activate && python scripts/run_gateway.py
"""
import sys
import os
from pathlib import Path

# Add project root to Python path so we can import gateway and runtime
root_dir = Path(__file__).parent.parent
sys.path.insert(0, str(root_dir))

if __name__ == "__main__":
    try:
        from gateway.main import app
        import uvicorn
    except ImportError as e:
        print(f"❌ Import error: {e}")
        print("\n💡 Make sure you've installed dependencies:")
        print("   pip install -r requirements.txt")
        print("\nOr activate the virtual environment:")
        print("   source venv/bin/activate")
        sys.exit(1)
    
    host = os.getenv("GATEWAY_HOST", "127.0.0.1")
    port = int(os.getenv("GATEWAY_PORT", "3336"))
    
    print(f"🚀 Starting Agent Blob Gateway on {host}:{port}")
    print(f"📡 WebSocket endpoint: ws://{host}:{port}/ws")
    print(f"🔍 Health check: http://{host}:{port}/health")
    print()
    
    uvicorn.run(app, host=host, port=port)
