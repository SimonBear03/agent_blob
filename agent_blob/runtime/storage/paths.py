from __future__ import annotations

from pathlib import Path
from agent_blob.config import data_dir as configured_data_dir


def data_dir() -> Path:
    p = Path(configured_data_dir())
    p.mkdir(parents=True, exist_ok=True)
    return p
