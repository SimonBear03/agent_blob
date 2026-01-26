#!/usr/bin/env python3
"""
Agent Blob Telegram Bot Launcher

Start the Telegram bot that connects to the gateway.
"""
import asyncio
from clients.telegram.telegram_bot import main

if __name__ == "__main__":
    asyncio.run(main())
