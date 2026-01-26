# The "Dumb Client" Philosophy

## Core Principle

**Clients are just chatboxes. They send text and display text. That's it.**

This is the most important architectural decision in Agent Blob, and it makes everything else possible.

## What It Means

### Clients Do This:
```
User types: "/sessions"
Client: websocket.send({ method: "agent", params: { message: "/sessions" } })
Gateway sends back: { event: "message", payload: { role: "system", content: "📋 Recent Sessions:\n1. Python help\n2. Database design\n..." } }
Client: display(content)
```

**That's it.** No parsing. No API calls. No formatting. Just pass it through.

### Gateway Does Everything Else:
```python
# gateway/commands.py
if message.startswith("/sessions"):
    sessions = SessionsDB.list_sessions()
    formatted = format_session_list(sessions)
    send_message_event(formatted)
```

## Why This Is Brilliant

### 1. Universal Commands

Type `/sessions` in:
- TUI client → Works
- Web UI → Works
- Telegram bot → Works
- Future iOS app → Will work

Same command, same response, same behavior everywhere. **No client-side code needed.**

### 2. Easy to Build Clients

**Full Telegram bot implementation:**
```python
@bot.message_handler(func=lambda m: True)
async def handle(message):
    # Connect to gateway (if not connected)
    gateway = await get_connection(message.chat.id)
    
    # Send user message
    await gateway.send_message(message.text)
    
    # Display responses
    async for event in gateway.listen():
        if event.type == "message":
            await bot.send_message(message.chat.id, event.payload["content"])
        elif event.type == "token":
            # Show typing indicator
            await bot.send_chat_action(message.chat.id, "typing")
```

**That's a complete client in ~15 lines.** No command parsing. No session management. No formatting. Just forward messages.

### 3. Change Once, All Clients Benefit

Want to add `/sessions search <keyword>`?

**Before (traditional smart clients):**
- Update CLI command parser
- Update Web UI command parser
- Update Telegram command parser
- Update each client's API calls
- Update each client's response formatter
- Test all clients
- Fix bugs in each client
- **Total: ~500 lines changed across 3 clients**

**With dumb clients:**
- Update `gateway/commands.py` (one function)
- **Total: ~20 lines changed**
- All clients get it immediately
- One place to test
- One place to fix bugs

### 4. Consistent UX

Because all formatting happens in the gateway:
- Session lists look the same everywhere
- Error messages are consistent
- Help text is identical
- Time formatting is uniform

No more "CLI shows time as '2h ago' but Web shows '2 hours ago'" inconsistencies.

## Real Example: Session Switching

### Traditional Approach (Smart Clients)

**CLI Client:**
```python
if message.startswith("/switch"):
    session_num = int(message.split()[1])
    response = await api.get_sessions()
    session_id = response["sessions"][session_num - 1]["id"]
    await api.switch_session(session_id)
    history = await api.get_history(session_id)
    display_history(history)
    print(f"Switched to session {session_num}")
```

**Web Client:**
```typescript
if (message.startsWith("/switch")) {
  const sessionNum = parseInt(message.split(" ")[1]);
  const sessions = await fetch("/api/sessions").then(r => r.json());
  const sessionId = sessions[sessionNum - 1].id;
  await fetch("/api/sessions/switch", { body: { sessionId } });
  const history = await fetch(`/api/history/${sessionId}`).then(r => r.json());
  setMessages(history);
  showNotification(`Switched to session ${sessionNum}`);
}
```

**Problems:**
- Different error handling
- Different formatting
- Duplicated logic
- Two places to maintain
- Two places for bugs

### Dumb Client Approach

**CLI Client:**
```python
# Send everything to gateway
await gateway.send_message(message)

# Display whatever comes back
async for event in gateway.listen():
    if event.type == "message":
        print(event.payload["content"])
    elif event.type == "session_changed":
        load_session(event.payload)
```

**Web Client:**
```typescript
// Send everything to gateway
gateway.sendMessage(message);

// Display whatever comes back
gateway.on("message", (payload) => {
  displayMessage(payload.content);
});

gateway.on("session_changed", (payload) => {
  loadSession(payload);
});
```

**Gateway (single source of truth):**
```python
@handle_command("/switch")
async def switch_session(args, session_id, websocket):
    session_num = int(args[0])
    sessions = SessionsDB.list_sessions()
    target_session = sessions[session_num - 1]
    
    # Switch client's session
    connection_manager.switch_client_session(websocket, target_session["id"])
    
    # Send session_changed event with full context
    await send_session_changed_event(target_session["id"], websocket)
```

**Result:**
- One implementation
- Consistent behavior
- Easy to test
- Easy to fix bugs
- Both clients are ~10 lines instead of ~30

## Common Pitfalls (What NOT To Do)

### ❌ Bad: Client-side command parsing
```python
# DON'T DO THIS IN CLIENT:
if message.startswith("/sessions"):
    response = await api.get_sessions()
    formatted = format_sessions(response)
    display(formatted)
```

**Why it's bad:** Now you have command logic in two places. When you add `/sessions search`, you have to update the client too.

### ✅ Good: Send everything to gateway
```python
# DO THIS IN CLIENT:
await gateway.send_message(message)
```

**Why it's good:** Client doesn't know or care what's a command. Gateway handles it.

---

### ❌ Bad: Client-side formatting
```python
# DON'T DO THIS IN CLIENT:
sessions = event.payload["sessions"]
for i, session in enumerate(sessions):
    print(f"{i+1}. {session['title']} ({session['message_count']} msgs)")
```

**Why it's bad:** Different clients format differently. Change the format? Update all clients.

### ✅ Good: Display gateway's text
```python
# DO THIS IN CLIENT:
print(event.payload["content"])
```

**Why it's good:** Gateway already formatted it. Just show it. Change format? Update gateway only.

---

### ❌ Bad: Client-side API calls
```python
# DON'T DO THIS IN CLIENT:
if message.startswith("/sessions"):
    async with httpx.AsyncClient() as client:
        response = await client.get("http://gateway/api/sessions")
        data = response.json()
```

**Why it's bad:** Now you have REST API + WebSocket. More endpoints to maintain. More ways to get out of sync.

### ✅ Good: Everything via WebSocket messages
```python
# DO THIS IN CLIENT:
await gateway.send_message(message)
# Gateway sends response as MESSAGE event
```

**Why it's good:** One protocol. One connection. One way to do things.

## Exceptions: Local UI Commands

There are TWO commands clients can handle locally:

1. **`/quit`** - Exit the client application
2. **`/clear`** - Clear the local display

These are UI-only operations that don't involve the gateway or other clients.

**Everything else goes to the gateway.**

## The Mental Model

Think of clients as **terminals** connecting to a **mainframe**:

```
Terminal 1 (TUI)    ──┐
Terminal 2 (Web)    ──┤──► Mainframe (Gateway) ──► Does all the work
Terminal 3 (Mobile) ──┘

Terminals just:
- Send keypresses (messages)
- Display responses (text/events)
```

The terminals don't understand commands. They don't know about sessions. They don't format responses. **They're dumb terminals.**

The mainframe (gateway) does all the intelligent work:
- Parses commands
- Manages sessions
- Formats responses
- Coordinates between terminals

## Benefits Summarized

1. **🚀 Fast client development** - Basic client in < 200 lines
2. **🔄 Universal behavior** - Commands work identically everywhere
3. **🛠 Single point of maintenance** - Change gateway once
4. **🎨 Consistent UX** - Same formatting everywhere
5. **🐛 Easy debugging** - One place to look
6. **📱 Future-proof** - New platforms trivial to add
7. **🌐 Platform agnostic** - Same code patterns for Web, CLI, Telegram, iOS, etc.

## For Client Developers

When building a client, ask yourself:

> "Am I doing something the gateway should handle?"

If the answer is yes (usually it is), move that logic to the gateway.

**Your client should be so simple that you're almost embarrassed to show the code.**

That's when you know you're doing it right. ✨

## See Also

- `docs/ARCHITECTURE.md` - Full architecture explanation
- `docs/CLIENT_DESIGN.md` - Client implementation patterns
- `docs/TUI_IMPLEMENTATION.md` - TUI client example
- `gateway/commands.py` - Gateway command implementations
