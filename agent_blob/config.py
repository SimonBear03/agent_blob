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

def load_config_uncached(path: str = "agent_blob.json") -> Dict[str, Any]:
    """
    Uncached config read. Use this when changes must take effect without restarting.
    """
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


def memory_dir() -> str:
    cfg = load_config()
    return str(_get(cfg, "memory", "dir", default="./memory"))


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


def memory_embedding_model() -> str:
    cfg = load_config()
    v = _get(cfg, "memory", "embedding_model", default="text-embedding-3-small")
    return str(v or "text-embedding-3-small")


def memory_embeddings_enabled() -> bool:
    cfg = load_config()
    return bool(_get(cfg, "memory", "embeddings", "enabled", default=True))


def memory_embeddings_batch_size() -> int:
    cfg = load_config()
    try:
        return int(_get(cfg, "memory", "embeddings", "batch_size", default=16))
    except Exception:
        return 16


def memory_recent_turns_limit() -> int:
    cfg = load_config()
    try:
        return int(_get(cfg, "memory", "retrieval", "recent_turns_limit", default=8))
    except Exception:
        return 8


def memory_related_turns_limit() -> int:
    cfg = load_config()
    try:
        return int(_get(cfg, "memory", "retrieval", "related_turns_limit", default=5))
    except Exception:
        return 5


def memory_structured_limit() -> int:
    cfg = load_config()
    try:
        return int(_get(cfg, "memory", "retrieval", "structured_limit", default=5))
    except Exception:
        return 5


def memory_introspection_limit() -> int:
    cfg = load_config()
    try:
        return int(_get(cfg, "memory", "retrieval", "introspection_limit", default=10))
    except Exception:
        return 10


def memory_vector_scan_limit() -> int:
    cfg = load_config()
    try:
        return int(_get(cfg, "memory", "embeddings", "vector_scan_limit", default=2000))
    except Exception:
        return 2000


def memory_vector_top_k() -> int:
    cfg = load_config()
    try:
        return int(_get(cfg, "memory", "embeddings", "vector_top_k", default=50))
    except Exception:
        return 50


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
    value = _get(cfg, "frontends", "native", "cli", "device_id", default=None)
    if value is None:
        value = _get(cfg, "clients", "cli", "device_id", default="cli")
    return str(value or "cli")


def allowed_fs_root() -> Optional[str]:
    cfg = load_config()
    v = _get(cfg, "tools", "allowed_fs_root", default=None)
    if v is None:
        return None
    s = str(v).strip()
    return s or None


def tasks_attach_window_s() -> int:
    cfg = load_config()
    try:
        return int(_get(cfg, "tasks", "attach_window_s", default=1800))
    except Exception:
        return 1800


def tasks_auto_close_after_s() -> int:
    cfg = load_config()
    try:
        return int(_get(cfg, "tasks", "auto_close_after_s", default=21600))
    except Exception:
        return 21600


def scheduler_timezone() -> Optional[str]:
    cfg = load_config()
    v = _get(cfg, "scheduler", "timezone", default=None)
    if v is None:
        return None
    s = str(v).strip()
    return s or None


def _log_cfg(kind: str) -> Dict[str, Any]:
    cfg = load_config()
    logs = _get(cfg, "logs", default={})
    if not isinstance(logs, dict):
        return {}
    v = logs.get(kind)
    return v if isinstance(v, dict) else {}


def log_max_bytes(kind: str, default: int) -> int:
    try:
        return int(_log_cfg(kind).get("max_bytes", default) or default)
    except Exception:
        return int(default)


def log_keep_days(kind: str, default: int) -> int:
    try:
        return int(_log_cfg(kind).get("keep_days", default) or default)
    except Exception:
        return int(default)


def log_keep_max_files(kind: str, default: int) -> int:
    try:
        return int(_log_cfg(kind).get("keep_max_files", default) or default)
    except Exception:
        return int(default)


def skills_dirs() -> list[str]:
    cfg = load_config()
    v = _get(cfg, "skills", "dirs", default=["./skills", "./agent_blob/runtime/skills/examples"])
    if isinstance(v, list):
        return [str(x) for x in v]
    return ["./skills", "./agent_blob/runtime/skills/examples"]


def skills_enabled() -> list[str]:
    cfg = load_config()
    v = _get(cfg, "skills", "enabled", default=["general"])
    if isinstance(v, list):
        return [str(x) for x in v]
    return ["general"]


def skills_max_chars() -> int:
    cfg = load_config()
    try:
        return int(_get(cfg, "skills", "max_chars", default=12000))
    except Exception:
        return 12000


def mcp_servers() -> list[dict]:
    cfg = load_config()
    v = _get(cfg, "mcp", "servers", default=[])
    return list(v or []) if isinstance(v, list) else []


def telegram_enabled() -> bool:
    cfg = load_config()
    value = _get(cfg, "frontends", "adapters", "telegram", "enabled", default=None)
    if value is None:
        value = _get(cfg, "channels", "telegram", "enabled", default=False)
    return bool(value)


def telegram_mode() -> str:
    cfg = load_config()
    value = _get(cfg, "frontends", "adapters", "telegram", "mode", default=None)
    if value is None:
        value = _get(cfg, "channels", "telegram", "mode", default="polling")
    return str(value or "polling")


def telegram_poll_interval_s() -> float:
    cfg = load_config()
    try:
        value = _get(cfg, "frontends", "adapters", "telegram", "poll_interval_s", default=None)
        if value is None:
            value = _get(cfg, "channels", "telegram", "poll_interval_s", default=1.5)
        return float(value)
    except Exception:
        return 1.5


def telegram_stream_edit_interval_ms() -> int:
    cfg = load_config()
    try:
        value = _get(cfg, "frontends", "adapters", "telegram", "stream_edit_interval_ms", default=None)
        if value is None:
            value = _get(cfg, "channels", "telegram", "stream_edit_interval_ms", default=700)
        return int(value)
    except Exception:
        return 700


def telegram_status_verbosity() -> str:
    cfg = load_config()
    value = _get(cfg, "frontends", "adapters", "telegram", "status_verbosity", default=None)
    if value is None:
        value = _get(cfg, "channels", "telegram", "status_verbosity", default="minimal")
    return str(value or "minimal")


def telegram_max_message_chars() -> int:
    cfg = load_config()
    try:
        value = _get(cfg, "frontends", "adapters", "telegram", "max_message_chars", default=None)
        if value is None:
            value = _get(cfg, "channels", "telegram", "max_message_chars", default=3800)
        return int(value)
    except Exception:
        return 3800


def telegram_media_enabled() -> bool:
    cfg = load_config()
    value = _get(cfg, "frontends", "adapters", "telegram", "media", "enabled", default=None)
    if value is None:
        value = _get(cfg, "channels", "telegram", "media", "enabled", default=True)
    return bool(value)


def telegram_media_download() -> bool:
    cfg = load_config()
    value = _get(cfg, "frontends", "adapters", "telegram", "media", "download", default=None)
    if value is None:
        value = _get(cfg, "channels", "telegram", "media", "download", default=True)
    return bool(value)


def telegram_media_max_file_mb() -> int:
    cfg = load_config()
    try:
        value = _get(cfg, "frontends", "adapters", "telegram", "media", "max_file_mb", default=None)
        if value is None:
            value = _get(cfg, "channels", "telegram", "media", "max_file_mb", default=25)
        return int(value)
    except Exception:
        return 25


def telegram_media_download_dir() -> str:
    cfg = load_config()
    value = _get(cfg, "frontends", "adapters", "telegram", "media", "download_dir", default=None)
    if value is None:
        value = _get(cfg, "channels", "telegram", "media", "download_dir", default="./data/media/telegram")
    return str(value or "./data/media/telegram")
