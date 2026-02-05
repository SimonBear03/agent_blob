from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from agent_blob.runtime.capabilities.provider import CapabilityProvider
from agent_blob.runtime.tools.registry import ToolDefinition


@dataclass
class CapabilityRegistry:
    providers: List[CapabilityProvider]

    def tools(self) -> List[ToolDefinition]:
        out: List[ToolDefinition] = []
        for p in self.providers:
            out.extend(p.tools())
        return out

    def system_instructions(self) -> str:
        blocks: List[str] = []
        for p in self.providers:
            txt = p.system_instructions()
            if txt:
                blocks.append(txt.strip())
        return "\n\n".join([b for b in blocks if b])

