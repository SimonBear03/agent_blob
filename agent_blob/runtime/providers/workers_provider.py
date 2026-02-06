from __future__ import annotations

from typing import Any, Dict, List, Optional

from agent_blob.runtime.capabilities.provider import CapabilityProvider
from agent_blob.runtime.tools.registry import ToolDefinition


class WorkersProvider:
    """
    Defines the "worker_run" tool used for master->sub-agent delegation.

    Execution is implemented inside Runtime (so it can reuse the same permission
    callback and tool gating). This provider exists purely to advertise the tool
    schema to the LLM.
    """

    name = "workers"

    def tools(self) -> List[ToolDefinition]:
        async def _noop(args: Dict[str, Any]) -> Any:
            # Runtime intercepts this tool by name.
            return {"ok": False, "error": "worker_run is handled internally by runtime"}

        return [
            ToolDefinition(
                name="worker_run",
                capability="workers.run",
                description=(
                    "Delegate a task to a specialized sub-agent (worker) and return its result. "
                    "Use this for multitasking and domain-specific work (briefing/quant/dev)."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "worker_type": {
                            "type": "string",
                            "description": "Worker type: briefing | quant | dev",
                        },
                        "prompt": {"type": "string", "description": "The worker job instruction"},
                        "max_rounds": {"type": "integer", "description": "Max tool-calling rounds", "default": 3},
                    },
                    "required": ["worker_type", "prompt"],
                },
                executor=_noop,
            )
        ]

    def system_instructions(self) -> Optional[str]:
        return None

