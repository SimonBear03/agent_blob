from __future__ import annotations

from typing import Any, Dict

from agent_blob.runtime.skills.loader import SkillsLoader


def build_skills_tools(loader: SkillsLoader):
    async def skills_list(args: Dict[str, Any]) -> Any:
        out = loader.list()
        # Include enabled names for UX.
        try:
            from agent_blob.runtime.skills.loader import load_skills_config

            enabled = load_skills_config().enabled
        except Exception:
            enabled = []
        return {"ok": True, "enabled": list(enabled or []), "skills": out}

    async def skills_get(args: Dict[str, Any]) -> Any:
        name = str(args.get("name", "") or "").strip()
        s = loader.get(name)
        if not s:
            available = [x.get("name") for x in (loader.list() or []) if isinstance(x, dict) and x.get("name")]
            low = name.lower()
            suggestions = []
            if low:
                suggestions = [a for a in available if low in str(a).lower()][:10]
            return {
                "ok": False,
                "error": "Skill not found",
                "name": name,
                "suggestions": suggestions,
                "available": available[:50],
            }
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
