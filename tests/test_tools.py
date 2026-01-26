#!/usr/bin/env python3
"""
Test WebSocket connection with tool execution.

This will ask the agent to use the filesystem tool to list files.
"""
import asyncio
import json
import websockets


async def test_tools():
    uri = "ws://127.0.0.1:3336/ws"
    
    print(f"🔌 Connecting to {uri}...")
    
    async with websockets.connect(uri) as websocket:
        # 1. Connect
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
        connect_response = json.loads(response)
        
        if not connect_response.get("ok"):
            print(f"❌ Connection failed: {connect_response.get('error')}")
            return
        
        session_id = connect_response["payload"]["sessionId"]
        print(f"✅ Connected! Session ID: {session_id[:8]}...")
        
        # 2. Ask agent to use a tool
        agent_request = {
            "type": "req",
            "id": "msg-1",
            "method": "agent",
            "params": {
                "sessionId": session_id,
                "message": "Can you read the README.md file and tell me what this project is about?"
            }
        }
        
        print("\n📤 Asking agent to use filesystem tool...")
        await websocket.send(json.dumps(agent_request))
        
        # 3. Receive events
        print("\n📥 Receiving events...")
        while True:
            try:
                message = await asyncio.wait_for(websocket.recv(), timeout=60.0)
                data = json.loads(message)
                
                if data.get("type") == "res":
                    print(f"   Response: {data['payload']}")
                elif data.get("type") == "event":
                    event_type = data.get("event")
                    
                    if event_type == "token":
                        print(data["payload"]["content"], end="", flush=True)
                    elif event_type == "tool_call":
                        print(f"\n\n   🔧 Tool Call: {data['payload']['toolName']}")
                        print(f"      Args: {data['payload']['arguments']}")
                    elif event_type == "tool_result":
                        print(f"\n   ✅ Tool Result: {data['payload']['toolName']}")
                        result = data['payload']['result']
                        if isinstance(result, dict):
                            print(f"      Success: {result.get('success')}")
                            if 'content' in result:
                                print(f"      Content length: {len(result.get('content', ''))} chars")
                    elif event_type == "final":
                        print(f"\n\n   ✅ Final: Run {data['payload']['runId']}")
                        break
                    elif event_type == "status":
                        status = data['payload']['status']
                        if status == "executing_tool":
                            print(f"\n   ⚙️  Executing tool...")
                    elif event_type not in ["message"]:
                        print(f"\n   Event ({event_type}): {data['payload']}")
            
            except asyncio.TimeoutError:
                print("\n⏱️  Timeout waiting for response")
                break
            except Exception as e:
                print(f"\n❌ Error: {e}")
                break
        
        print("\n✅ Test complete!")


if __name__ == "__main__":
    try:
        asyncio.run(test_tools())
    except KeyboardInterrupt:
        print("\n\n👋 Goodbye!")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
