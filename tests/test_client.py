#!/usr/bin/env python3
"""
Simple WebSocket test client for Agent Blob Gateway.

Usage: python test_client.py
"""
import asyncio
import json
import websockets


async def test_gateway():
    uri = "ws://127.0.0.1:3336/ws"
    
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
        
        # Receive connect response
        response = await websocket.recv()
        print(f"📥 Received connect response: {response}")
        
        connect_response = json.loads(response)
        if not connect_response.get("ok"):
            print(f"❌ Connection failed: {connect_response.get('error')}")
            return
        
        print(f"✅ Connected to gateway v{connect_response['payload']['gatewayVersion']}")
        
        # Wait for SESSION_CHANGED event (gateway assigns the session)
        print("\n📥 Waiting for session assignment...")
        session_event = await websocket.recv()
        print(f"📥 Received: {session_event}")
        
        session_data = json.loads(session_event)
        if session_data.get("type") != "event" or session_data.get("event") != "session_changed":
            print(f"❌ Expected session_changed event, got: {session_data}")
            return
        
        session_id = session_data["payload"]["sessionId"]
        session_title = session_data["payload"].get("title", "Unknown")
        print(f"✅ Session assigned: {session_id[:8]}... (title: '{session_title}')")
        
        # 2. Send a test message
        # Note: No need to send sessionId - gateway tracks which session this client is in
        agent_request = {
            "type": "req",
            "id": "msg-1",
            "method": "agent",
            "params": {
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
