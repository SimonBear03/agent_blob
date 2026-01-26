#!/usr/bin/env python3
"""
Simple WebSocket test client for Agent Blob Gateway.

Usage: python test_client.py
"""
import asyncio
import json
import websockets


async def test_gateway():
    uri = "ws://127.0.0.1:18789/ws"
    
    print(f"🔌 Connecting to {uri}...")
    
    async with websockets.connect(uri) as websocket:
        # 1. Send connect request
        connect_request = {
            "type": "req",
            "id": "conn-1",
            "method": "connect",
            "params": {
                "version": "1",
                "clientType": "cli"
            }
        }
        
        print("\n📤 Sending connect request...")
        await websocket.send(json.dumps(connect_request))
        
        response = await websocket.recv()
        print(f"📥 Received: {response}")
        
        connect_response = json.loads(response)
        if not connect_response.get("ok"):
            print(f"❌ Connection failed: {connect_response.get('error')}")
            return
        
        session_id = connect_response["payload"]["sessionId"]
        print(f"✅ Connected! Session ID: {session_id[:8]}...")
        
        # 2. Send a test message
        agent_request = {
            "type": "req",
            "id": "msg-1",
            "method": "agent",
            "params": {
                "sessionId": session_id,
                "message": "Hello! Can you tell me what tools you have access to?"
            }
        }
        
        print("\n📤 Sending message...")
        await websocket.send(json.dumps(agent_request))
        
        # 3. Receive response and events
        print("\n📥 Receiving events...")
        while True:
            try:
                message = await asyncio.wait_for(websocket.recv(), timeout=30.0)
                data = json.loads(message)
                
                if data.get("type") == "res":
                    print(f"   Response: {data}")
                elif data.get("type") == "event":
                    event_type = data.get("event")
                    if event_type == "token":
                        # Print tokens inline
                        print(data["payload"]["content"], end="", flush=True)
                    elif event_type == "final":
                        print(f"\n   ✅ Final: {data}")
                        break
                    else:
                        print(f"\n   Event ({event_type}): {data}")
            
            except asyncio.TimeoutError:
                print("\n⏱️  Timeout waiting for response")
                break
            except Exception as e:
                print(f"\n❌ Error: {e}")
                break
        
        print("\n✅ Test complete!")


if __name__ == "__main__":
    try:
        asyncio.run(test_gateway())
    except KeyboardInterrupt:
        print("\n\n👋 Goodbye!")
    except Exception as e:
        print(f"\n❌ Error: {e}")
