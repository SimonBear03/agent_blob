from __future__ import annotations

from pathlib import Path
from agent_blob.config import data_dir as configured_data_dir
from agent_blob.config import memory_dir as configured_memory_dir


def data_dir() -> Path:
    p = Path(configured_data_dir())
    p.mkdir(parents=True, exist_ok=True)
    return p


def memory_dir() -> Path:
    p = Path(configured_memory_dir())
    p.mkdir(parents=True, exist_ok=True)
    return p
