from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from agent_blob import config

def _allowed_root() -> Path:
    root = config.allowed_fs_root() or os.getcwd()
    return Path(root).resolve()


def _resolve(path: str) -> Path:
    p = Path(path)
    if not p.is_absolute():
        p = (Path.cwd() / p)
    return p.resolve()

def _within_root(p: Path, root: Path) -> bool:
    try:
        p.relative_to(root)
        return True
    except ValueError:
        return False

async def filesystem_write(path: str, content: str, *, append: bool = False, create_parents: bool = True) -> dict:
    root = _allowed_root()
    p = _resolve(path)
    if not _within_root(p, root):
        return {"ok": False, "error": f"Access denied (outside tools.allowed_fs_root): {p}", "path": str(p)}
    try:
        if create_parents:
            p.parent.mkdir(parents=True, exist_ok=True)
        if append:
            # UX nicety: if appending to a non-empty text file, ensure we start on a new line
            # unless the caller already provided a leading newline.
            try:
                existing = p.read_text(encoding="utf-8") if p.exists() else ""
            except Exception:
                existing = ""
            to_write = str(content)
            if existing and (not existing.endswith("\n")) and to_write and (not to_write.startswith("\n")):
                to_write = "\n" + to_write
            with p.open("a", encoding="utf-8") as f:
                f.write(to_write)
        else:
            p.write_text(str(content), encoding="utf-8")
        written_text = str(content)
        if append and "to_write" in locals():
            written_text = to_write
        return {"ok": True, "path": str(p), "bytes": len(written_text.encode("utf-8")), "append": bool(append)}
    except Exception as e:
        return {"ok": False, "error": str(e), "path": str(p)}

async def filesystem_read_optional(path: str) -> dict:
    """
    Like filesystem_read, but returns ok=True with empty content when file doesn't exist.
    Useful for diffs/previews.
    """
    root = _allowed_root()
    p = _resolve(path)
    if not _within_root(p, root):
        return {"ok": False, "error": f"Access denied (outside tools.allowed_fs_root): {p}", "path": str(p)}
    try:
        if not p.exists():
            return {"ok": True, "path": str(p), "content": "", "exists": False}
        return {"ok": True, "path": str(p), "content": p.read_text(encoding="utf-8"), "exists": True}
    except Exception as e:
        return {"ok": False, "error": str(e), "path": str(p)}


async def filesystem_read(path: str) -> dict:
    root = _allowed_root()
    p = _resolve(path)
    try:
        p.relative_to(root)
    except ValueError:
        return {"ok": False, "error": f"Access denied (outside tools.allowed_fs_root): {p}", "path": str(p)}
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
        return {"ok": False, "error": f"Access denied (outside tools.allowed_fs_root): {p}", "path": str(p)}
    try:
        if not p.exists():
            return {"ok": False, "error": "Not found", "path": str(p)}
        if not p.is_dir():
            return {"ok": False, "error": "Not a directory", "path": str(p)}
        entries = [{"name": c.name, "is_dir": c.is_dir()} for c in p.iterdir()]
        return {"ok": True, "path": str(p), "entries": entries}
    except Exception as e:
        return {"ok": False, "error": str(e), "path": str(p)}
