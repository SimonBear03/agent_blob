from __future__ import annotations

import json
import os
from pathlib import Path


def data_dir() -> Path:
    env = os.getenv("DATA_DIR")
    if env:
        p = Path(env)
        p.mkdir(parents=True, exist_ok=True)
        return p

    cfg = Path("agent_blob.json")
    if cfg.exists():
        data = json.loads(cfg.read_text(encoding="utf-8"))
        d = ((data.get("data") or {}).get("dir")) or "./data"
        p = Path(d)
        p.mkdir(parents=True, exist_ok=True)
        return p

    p = Path("./data")
    p.mkdir(parents=True, exist_ok=True)
    return p
