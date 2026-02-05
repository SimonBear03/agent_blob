from __future__ import annotations

from typing import Any, Dict

from agent_blob.runtime.skills.loader import SkillsLoader


def build_skills_tools(loader: SkillsLoader):
    async def skills_list(args: Dict[str, Any]) -> Any:
        return loader.list()

    async def skills_get(args: Dict[str, Any]) -> Any:
        name = str(args.get("name", "") or "").strip()
        s = loader.get(name)
        if not s:
            return {"ok": False, "error": "Skill not found", "name": name}
        return {
            "ok": True,
            "name": s.name,
            "description": s.description,
            "path": str(s.path),
            "base_dir": str(s.base_dir),
            "body": s.body,
            "meta": s.meta,
        }

    return skills_list, skills_get

