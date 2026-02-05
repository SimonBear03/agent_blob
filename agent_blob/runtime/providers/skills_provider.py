from __future__ import annotations

from typing import Any, Dict, List, Optional

from agent_blob.runtime.capabilities.provider import CapabilityProvider
from agent_blob.runtime.skills.loader import SkillsLoader
from agent_blob.runtime.tools.registry import ToolDefinition
from agent_blob.runtime.tools.skills import build_skills_tools


class SkillsProvider:
    name = "skills"

    def __init__(self):
        self.loader = SkillsLoader()
        self._skills_list, self._skills_get = build_skills_tools(self.loader)

    def tools(self) -> List[ToolDefinition]:
        return [
            ToolDefinition(
                name="skills_list",
                capability="skills.list",
                description="List available local skills (SKILL.md).",
                parameters={"type": "object", "properties": {}},
                executor=self._skills_list,
            ),
            ToolDefinition(
                name="skills_get",
                capability="skills.get",
                description="Get a local skill by name and return its instructions.",
                parameters={
                    "type": "object",
                    "properties": {"name": {"type": "string", "description": "Skill name"}},
                    "required": ["name"],
                },
                executor=self._skills_get,
            ),
        ]

    def system_instructions(self) -> Optional[str]:
        blocks = self.loader.enabled_blocks()
        if not blocks:
            return None
        return "Enabled skills:\n\n" + "\n\n".join(blocks)

