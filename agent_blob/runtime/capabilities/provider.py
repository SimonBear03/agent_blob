from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Protocol

from agent_blob.runtime.tools.registry import ToolDefinition


class CapabilityProvider(Protocol):
    """
    Pluggable provider of capabilities to the runtime.

    This is intentionally small so we can add new ecosystems (MCP, skills, future specs)
    without rewriting the agent loop.
    """

    name: str

    def tools(self) -> List[ToolDefinition]:
        ...

    def system_instructions(self) -> Optional[str]:
        """
        Optional system-level instruction block to inject into the model context.
        """
        ...

