from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from agent_blob import config
from agent_blob.runtime.skills.model import Skill


def _expand(p: str) -> Path:
    return Path(os.path.expanduser(p)).resolve()


def _parse_frontmatter(text: str) -> tuple[Dict[str, Any], str]:
    """
    Minimal frontmatter parser for AgentSkills/OpenClaw-style SKILL.md:
    - Optional YAML-like block delimited by '---' at the top
    - Only supports simple 'key: value' lines
    - If a value looks like JSON (starts with '{' or '['), we parse it as JSON
    Returns (meta, body).
    """
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, text
    meta: Dict[str, Any] = {}
    i = 1
    while i < len(lines):
        line = lines[i].rstrip("\n")
        if line.strip() == "---":
            i += 1
            break
        if ":" in line:
            k, v = line.split(":", 1)
            key = k.strip()
            val = v.strip()
            if key:
                if val.startswith("{") or val.startswith("["):
                    try:
                        meta[key] = json.loads(val)
                    except Exception:
                        meta[key] = val
                else:
                    meta[key] = val
        i += 1
    body = "\n".join(lines[i:]).lstrip("\n")
    return meta, body


@dataclass
class SkillsConfig:
    dirs: List[str]
    enabled: List[str]
    max_chars: int


def load_skills_config() -> SkillsConfig:
    cfg = config.load_config_uncached()
    skills = (cfg.get("skills") or {}) if isinstance(cfg, dict) else {}
    dirs = skills.get("dirs") if isinstance(skills, dict) else None
    enabled = skills.get("enabled") if isinstance(skills, dict) else None
    max_chars = skills.get("max_chars") if isinstance(skills, dict) else None
    return SkillsConfig(
        dirs=list(dirs or config.skills_dirs()),
        enabled=list(enabled or []),
        max_chars=int(max_chars or config.skills_max_chars()),
    )


class SkillsLoader:
    def __init__(self):
        pass

    def _skill_paths(self) -> List[Path]:
        cfg = load_skills_config()
        out: List[Path] = []
        for raw in cfg.dirs:
            p = _expand(str(raw))
            if p.exists() and p.is_dir():
                out.append(p)
        return out

    def discover(self) -> Dict[str, Skill]:
        """
        Discover SKILL.md files.

        Precedence: earlier dirs win (first match by skill name).
        """
        skills: Dict[str, Skill] = {}
        for root in self._skill_paths():
            for path in root.rglob("SKILL.md"):
                try:
                    txt = path.read_text(encoding="utf-8")
                except Exception:
                    continue
                meta, body = _parse_frontmatter(txt)
                name = str(meta.get("name") or path.parent.name).strip()
                if not name or name in skills:
                    continue
                desc = str(meta.get("description") or "").strip()
                skills[name] = Skill(
                    name=name,
                    description=desc,
                    path=path,
                    base_dir=path.parent,
                    body=body.strip(),
                    meta=meta,
                )
        return skills

    def list(self) -> List[Dict[str, Any]]:
        skills = self.discover()
        out = []
        for s in sorted(skills.values(), key=lambda x: x.name.lower()):
            out.append({"name": s.name, "description": s.description, "path": str(s.path)})
        return out

    def get(self, name: str) -> Optional[Skill]:
        skills = self.discover()
        raw = str(name or "").strip()
        if not raw:
            return None
        if raw in skills:
            return skills.get(raw)
        low = raw.lower()
        matches = [k for k in skills.keys() if str(k).lower() == low]
        if len(matches) == 1:
            return skills.get(matches[0])
        return None

    def enabled_blocks(self) -> List[str]:
        cfg = load_skills_config()
        if not cfg.enabled:
            cfg.enabled = config.skills_enabled()
        skills = self.discover()
        blocks: List[str] = []
        for n in cfg.enabled:
            s = skills.get(str(n))
            if not s:
                continue
            blocks.append(f"# Skill: {s.name}\n\n{s.body}\n")
        # Apply a hard cap so enabled skills can't blow up the context.
        cap = max(0, int(cfg.max_chars))
        if cap and sum(len(b) for b in blocks) > cap:
            clipped: List[str] = []
            used = 0
            for b in blocks:
                if used >= cap:
                    break
                remain = cap - used
                clipped.append(b[:remain])
                used += len(clipped[-1])
            blocks = clipped
        return blocks
