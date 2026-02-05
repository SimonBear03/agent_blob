from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class Skill:
    name: str
    description: str
    path: Path
    base_dir: Path
    body: str
    meta: Dict[str, Any]

    @property
    def slug(self) -> str:
        return self.name.strip()

