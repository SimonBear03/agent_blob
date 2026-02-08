from __future__ import annotations

import asyncio
from typing import Any, List

from agent_blob import config
from agent_blob.frontends.adapters.telegram import TelegramPoller


async def start_enabled_adapters(*, gateway: Any) -> List[asyncio.Task]:
    """
    Start configured adapter frontends and return their background tasks.
    """
    tasks: List[asyncio.Task] = []
    if config.telegram_enabled() and config.telegram_mode().strip().lower() == "polling":
        poller = TelegramPoller(gateway=gateway)
        tasks.append(asyncio.create_task(poller.run()))
    return tasks

