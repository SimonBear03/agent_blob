#!/usr/bin/env python3
"""
Agent Blob Telegram Bot - Simple "dumb client" implementation

This bot forwards messages to the gateway and displays responses.
All logic (commands, session management, formatting) is handled by the gateway.
"""
import asyncio
import logging
import sys
from pathlib import Path
from typing import Optional

from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import Message

# Add parent directories to path to import connection
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from clients.cli.connection import GatewayConnection

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class TelegramBotClient:
    """Telegram bot that connects to Agent Blob gateway."""
    
    def __init__(
        self,
        bot_token: str,
        allowed_user_id: int,
        gateway_uri: str = "ws://127.0.0.1:3336/ws"
    ):
        """
        Initialize the Telegram bot.
        
        Args:
            bot_token: Telegram bot token from BotFather
            allowed_user_id: Your Telegram user ID (for security)
            gateway_uri: WebSocket URI of the gateway
        """
        self.bot = Bot(token=bot_token)
        self.dp = Dispatcher()
        self.allowed_user_id = allowed_user_id
        self.gateway_uri = gateway_uri
        
        # Single connection to gateway (shared for all messages)
        self.gateway: Optional[GatewayConnection] = None
        self.connected = False
        
        # Track current message for streaming
        self.current_message_id: Optional[int] = None
        self.current_chat_id: Optional[int] = None
        self.streaming_buffer = ""
        
        # Track current session
        self.current_session_title = "Unknown"
        self.current_session_id = ""
        
        # Track metadata for display
        self.current_message_count = 0
        self.current_model = "unknown"
        self.current_tokens = 0
        
        # Register handlers
        self._register_handlers()
    
    def _register_handlers(self):
        """Register message handlers."""
        # Handle /start command
        self.dp.message.register(self._handle_start, Command("start"))
        
        # Handle all other messages
        self.dp.message.register(self._handle_message)
    
    async def start(self):
        """Start the bot."""
        try:
            # Connect to gateway
            logger.info(f"Connecting to gateway at {self.gateway_uri}")
            self.gateway = GatewayConnection(self.gateway_uri)
            
            await self.gateway.connect(
                client_type="telegram",
                session_preference="auto",
                history_limit=4  # Mobile-friendly
            )
            
            # Setup event handlers
            self.gateway.on_message = self._handle_gateway_message
            self.gateway.on_token = self._handle_gateway_token
            self.gateway.on_status = self._handle_gateway_status
            self.gateway.on_final = self._handle_gateway_final
            self.gateway.on_error = self._handle_gateway_error
            self.gateway.on_session_changed = self._handle_session_changed
            
            self.connected = True
            logger.info("Connected to gateway successfully")
            
            # Start polling
            logger.info("Starting bot polling...")
            await self.dp.start_polling(self.bot)
            
        except KeyboardInterrupt:
            logger.info("Shutting down...")
        except Exception as e:
            logger.exception(f"Fatal error: {e}")
        finally:
            if self.gateway:
                await self.gateway.disconnect()
            await self.bot.session.close()
    
    async def _handle_start(self, message: Message):
        """Handle /start command."""
        if message.from_user.id != self.allowed_user_id:
            return  # Silently ignore unauthorized users
        
        await message.reply(
            "🦞 *Agent Blob Bot*\n\n"
            "I'm connected to your Agent Blob gateway!\n\n"
            "Just send me messages and I'll forward them to your AI.\n\n"
            "Commands like `/help`, `/sessions`, `/new` work too!",
            parse_mode="Markdown"
        )
    
    async def _handle_message(self, message: Message):
        """Handle incoming messages from Telegram."""
        # Security check: Only accept messages from allowed user
        if message.from_user.id != self.allowed_user_id:
            logger.warning(f"Rejected message from unauthorized user: {message.from_user.id}")
            return
        
        if not self.connected or not self.gateway:
            await message.reply("❌ Not connected to gateway. Please restart the bot.")
            return
        
        # Show typing indicator
        await self.bot.send_chat_action(message.chat.id, "typing")
        
        # Store for streaming responses
        self.current_chat_id = message.chat.id
        
        # Forward to gateway
        logger.info(f"Forwarding message to gateway: {message.text[:50]}...")
        await self.gateway.send_message(message.text)
    
    # Gateway event handlers
    
    async def _handle_gateway_message(self, payload: dict):
        """Handle message event from gateway."""
        role = payload.get("role")
        content = payload.get("content", "")
        from_self = payload.get("fromSelf", False)
        
        if not self.current_chat_id:
            return
        
        # Handle user messages
        if role == "user":
            # Check if message is from another client (has emoji prefix like "📱 [From TUI]")
            # User messages from other clients are prefixed by gateway
            is_from_other_client = any(content.startswith(icon) for icon in ["📱", "💻", "🌐", "📨", "🤖"])
            
            if is_from_other_client:
                # Show messages from other clients (already has prefix from gateway)
                formatted_content = f"👤 **You (from other client):**\n{content}"
            elif from_self:
                # Skip our own message echo (shouldn't happen for Telegram, but just in case)
                return
            else:
                # This is our own message from Telegram - skip it (we already see it in the UI)
                return
        elif role == "assistant":
            formatted_content = f"🤖 **Assistant:**\n{content}"
        elif role == "system":
            formatted_content = f"⚙️ **System:**\n{content}"
        else:
            formatted_content = content
        
        # Send message to Telegram (chunked if needed)
        await self._send_telegram_message(self.current_chat_id, formatted_content)
    
    async def _handle_gateway_token(self, payload: dict):
        """Handle streaming token from gateway."""
        token = payload.get("content", "")
        self.streaming_buffer += token
        
        # Update message every 50 characters to avoid rate limits
        if len(self.streaming_buffer) % 50 == 0 and self.current_message_id:
            try:
                await self.bot.edit_message_text(
                    self.streaming_buffer + "▊",
                    chat_id=self.current_chat_id,
                    message_id=self.current_message_id,
                    parse_mode="Markdown"
                )
            except Exception:
                pass  # Ignore rate limit errors during streaming
    
    async def _handle_gateway_status(self, payload: dict):
        """Handle status event from gateway."""
        status = payload.get("status")
        
        if status == "streaming" and self.current_chat_id:
            # Start new message for streaming with role prefix
            self.streaming_buffer = "🤖 **Assistant:**\n"
            try:
                msg = await self.bot.send_message(
                    self.current_chat_id,
                    self.streaming_buffer + "▊",
                    parse_mode="Markdown"
                )
                self.current_message_id = msg.message_id
            except Exception as e:
                # If markdown fails, try without
                logger.warning(f"Markdown failed for streaming start: {e}")
                msg = await self.bot.send_message(
                    self.current_chat_id,
                    "🤖 Assistant:\n▊"
                )
                self.current_message_id = msg.message_id
        elif status == "thinking" and self.current_chat_id:
            await self.bot.send_chat_action(self.current_chat_id, "typing")
    
    async def _handle_gateway_final(self, payload: dict):
        """Handle final event (request completed)."""
        # Extract metadata from final event
        usage = payload.get("usage", {})
        model = payload.get("model", self.current_model)
        total_tokens = usage.get("totalTokens", 0)
        prompt_tokens = usage.get("promptTokens", 0)
        completion_tokens = usage.get("completionTokens", 0)
        
        # Store for later reference
        self.current_model = model
        self.current_tokens = total_tokens
        
        # Finalize streaming message with metadata
        if self.current_message_id and self.streaming_buffer:
            # Add metadata footer
            metadata = f"\n\n---\n"
            metadata += f"📊 **Model:** `{model}` | **Tokens:** {total_tokens:,}\n"
            metadata += f"💬 **Session:** {self.current_session_title[:30]}"
            
            final_text = self.streaming_buffer + metadata
            
            try:
                await self.bot.edit_message_text(
                    final_text,
                    chat_id=self.current_chat_id,
                    message_id=self.current_message_id,
                    parse_mode="Markdown"
                )
            except Exception as e:
                # If edit fails (maybe message too old), send as new message
                logger.warning(f"Failed to edit final message: {e}")
                await self._send_telegram_message(self.current_chat_id, final_text)
        
        # Reset state
        self.current_message_id = None
        self.streaming_buffer = ""
    
    async def _handle_gateway_error(self, payload: dict):
        """Handle error event from gateway."""
        message = payload.get("message", "Unknown error")
        
        if self.current_chat_id:
            await self._send_telegram_message(
                self.current_chat_id,
                f"❌ **Error:** {message}"
            )
    
    async def _handle_session_changed(self, payload: dict):
        """Handle session changed event."""
        title = payload.get("title", "Unknown")
        session_id = payload.get("sessionId", "")
        message = payload.get("message")
        stats = payload.get("stats", {})
        updated_at = payload.get("updatedAt", "")
        messages = payload.get("messages", [])
        
        # Store session info for later reference
        self.current_session_title = title
        self.current_session_id = session_id
        self.current_message_count = stats.get("messageCount", 0)
        
        if self.current_chat_id:
            if message:
                # Custom message provided
                text = message
            else:
                # Format session info
                msg_count = stats.get("messageCount", "?")
                session_short_id = session_id[:8] if session_id else "unknown"
                
                # Parse timestamp if available
                time_info = ""
                if updated_at:
                    try:
                        from datetime import datetime
                        dt = datetime.fromisoformat(updated_at.replace('Z', '+00:00'))
                        time_info = f"\n🕐 Last active: {dt.strftime('%b %d, %I:%M %p')}"
                    except:
                        pass
                
                text = f"""📎 **Switched to: {title}**

**ID:** `{session_short_id}...` | **Messages:** {msg_count}{time_info}"""
                
                # Show last 4 messages for context
                if messages:
                    # Get the last 4 messages (or fewer if there aren't that many)
                    recent_messages = messages[-4:]
                    
                    text += "\n\n**Recent context:**\n"
                    text += "---\n"
                    
                    for msg in recent_messages:
                        role = msg.get("role", "unknown")
                        content = msg.get("content", "")
                        
                        # Truncate long messages
                        if len(content) > 150:
                            content = content[:147] + "..."
                        
                        # Format based on role
                        if role == "user":
                            text += f"👤 **You:** {content}\n\n"
                        elif role == "assistant":
                            text += f"🤖 **Assistant:** {content}\n\n"
                        elif role == "system":
                            text += f"⚙️ **System:** {content}\n\n"
                    
                    text += "---"
            
            await self._send_telegram_message(self.current_chat_id, text)
    
    # Utility methods
    
    async def _send_telegram_message(self, chat_id: int, text: str):
        """
        Send message to Telegram, chunking if needed.
        
        Telegram has a 4096 character limit per message.
        """
        if not text:
            return
        
        chunks = self._chunk_message(text)
        
        for chunk in chunks:
            try:
                await self.bot.send_message(
                    chat_id,
                    chunk,
                    parse_mode="Markdown"
                )
            except Exception as e:
                # If markdown parsing fails, send as plain text
                logger.warning(f"Markdown parse error, sending as plain text: {e}")
                try:
                    await self.bot.send_message(chat_id, chunk)
                except Exception as e2:
                    logger.error(f"Failed to send message: {e2}")
    
    def _chunk_message(self, text: str, max_length: int = 4000) -> list[str]:
        """
        Split long messages into chunks for Telegram.
        
        Tries to split at newlines when possible to preserve formatting.
        """
        if len(text) <= max_length:
            return [text]
        
        chunks = []
        current_chunk = ""
        
        # Split by paragraphs (double newlines)
        paragraphs = text.split("\n\n")
        
        for para in paragraphs:
            # If adding this paragraph would exceed limit
            if len(current_chunk) + len(para) + 2 > max_length:
                # If current chunk is not empty, save it
                if current_chunk:
                    chunks.append(current_chunk.strip())
                    current_chunk = ""
                
                # If single paragraph is too long, split by sentences
                if len(para) > max_length:
                    sentences = para.split(". ")
                    for sentence in sentences:
                        if len(current_chunk) + len(sentence) + 2 > max_length:
                            if current_chunk:
                                chunks.append(current_chunk.strip())
                                current_chunk = ""
                        current_chunk += sentence + ". "
                else:
                    current_chunk = para + "\n\n"
            else:
                current_chunk += para + "\n\n"
        
        # Add remaining chunk
        if current_chunk:
            chunks.append(current_chunk.strip())
        
        return chunks if chunks else [text]


async def main():
    """Entry point."""
    import os
    from dotenv import load_dotenv
    
    load_dotenv()
    
    # Get configuration from environment
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    allowed_user_id = os.getenv("TELEGRAM_USER_ID")
    gateway_uri = os.getenv("GATEWAY_URI", "ws://127.0.0.1:3336/ws")
    
    if not bot_token:
        print("❌ Error: TELEGRAM_BOT_TOKEN not set in .env")
        print("\nSteps to set up:")
        print("1. Message @BotFather on Telegram")
        print("2. Create a new bot and get the token")
        print("3. Add TELEGRAM_BOT_TOKEN to .env")
        return
    
    if not allowed_user_id:
        print("❌ Error: TELEGRAM_USER_ID not set in .env")
        print("\nSteps to get your user ID:")
        print("1. Message @userinfobot on Telegram")
        print("2. It will tell you your user ID")
        print("3. Add TELEGRAM_USER_ID to .env")
        return
    
    try:
        allowed_user_id = int(allowed_user_id)
    except ValueError:
        print(f"❌ Error: TELEGRAM_USER_ID must be a number, got: {allowed_user_id}")
        return
    
    # Create and start bot
    bot_client = TelegramBotClient(
        bot_token=bot_token,
        allowed_user_id=allowed_user_id,
        gateway_uri=gateway_uri
    )
    
    await bot_client.start()


if __name__ == "__main__":
    asyncio.run(main())
