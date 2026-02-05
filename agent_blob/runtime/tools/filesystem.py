from __future__ import annotations

import os
from pathlib import Path


def _allowed_root() -> Path:
    root = os.getenv("ALLOWED_FS_ROOT") or os.getcwd()
    return Path(root).resolve()


def _resolve(path: str) -> Path:
    p = Path(path)
    if not p.is_absolute():
        p = (Path.cwd() / p)
    return p.resolve()


async def filesystem_read(path: str) -> dict:
    root = _allowed_root()
    p = _resolve(path)
    try:
        p.relative_to(root)
    except ValueError:
        return {"ok": False, "error": f"Access denied (outside ALLOWED_FS_ROOT): {p}", "path": str(p)}
    try:
        return {"ok": True, "path": str(p), "content": p.read_text(encoding="utf-8")}
    except Exception as e:
        return {"ok": False, "error": str(e), "path": str(p)}


async def filesystem_list(path: str) -> dict:
    root = _allowed_root()
    p = _resolve(path)
    try:
        p.relative_to(root)
    except ValueError:
        return {"ok": False, "error": f"Access denied (outside ALLOWED_FS_ROOT): {p}", "path": str(p)}
    try:
        if not p.exists():
            return {"ok": False, "error": "Not found", "path": str(p)}
        if not p.is_dir():
            return {"ok": False, "error": "Not a directory", "path": str(p)}
        entries = [{"name": c.name, "is_dir": c.is_dir()} for c in p.iterdir()]
        return {"ok": True, "path": str(p), "entries": entries}
    except Exception as e:
        return {"ok": False, "error": str(e), "path": str(p)}
