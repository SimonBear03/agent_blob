from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Optional


@lru_cache(maxsize=1)
def load_config(path: str = "agent_blob.json") -> Dict[str, Any]:
    p = Path(path)
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _get(cfg: Dict[str, Any], *path: str, default: Any = None) -> Any:
    cur: Any = cfg
    for k in path:
        if not isinstance(cur, dict) or k not in cur:
            return default
        cur = cur[k]
    return cur


def gateway_host() -> str:
    cfg = load_config()
    return str(_get(cfg, "gateway", "host", default="127.0.0.1"))


def gateway_port() -> int:
    cfg = load_config()
    try:
        return int(_get(cfg, "gateway", "port", default=3336))
    except Exception:
        return 3336


def data_dir() -> str:
    cfg = load_config()
    return str(_get(cfg, "data", "dir", default="./data"))


def llm_model_name() -> str:
    cfg = load_config()
    return str(_get(cfg, "llm", "model_name", default="gpt-4o-mini"))


def memory_extraction_model() -> Optional[str]:
    cfg = load_config()
    v = _get(cfg, "memory", "extraction_model", default=None)
    if v is None:
        return None
    s = str(v).strip()
    return s or None


def memory_importance_min() -> int:
    cfg = load_config()
    try:
        return int(_get(cfg, "memory", "importance_min", default=6))
    except Exception:
        return 6


def supervisor_interval_s() -> float:
    cfg = load_config()
    try:
        return float(_get(cfg, "supervisor", "interval_s", default=15))
    except Exception:
        return 15.0


def supervisor_debug() -> bool:
    cfg = load_config()
    return bool(_get(cfg, "supervisor", "debug", default=False))


def maintenance_interval_s() -> float:
    cfg = load_config()
    try:
        return float(_get(cfg, "supervisor", "maintenance_interval_s", default=60))
    except Exception:
        return 60.0


def cli_device_id() -> str:
    cfg = load_config()
    return str(_get(cfg, "clients", "cli", "device_id", default="cli"))


def allowed_fs_root() -> Optional[str]:
    cfg = load_config()
    v = _get(cfg, "tools", "allowed_fs_root", default=None)
    if v is None:
        return None
    s = str(v).strip()
    return s or None
