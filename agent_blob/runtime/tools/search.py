from __future__ import annotations

import fnmatch
import os
import re
from pathlib import Path
from typing import Any, Dict, List

from agent_blob.runtime.tools.filesystem import _allowed_root


def _resolve_under_root(path: str) -> Path:
    root = _allowed_root()
    p = Path(path) if path else root
    if not p.is_absolute():
        p = (Path.cwd() / p)
    p = p.resolve()
    try:
        p.relative_to(root)
    except ValueError:
        # Force to root for safety
        p = root
    return p


async def fs_glob(*, pattern: str, base_dir: str = ".", limit: int = 200) -> dict:
    """
    Safe file discovery: glob-like pattern matching under tools.allowed_fs_root.
    Pattern uses fnmatch semantics (e.g. **/*.py).
    """
    root = _allowed_root()
    base = _resolve_under_root(base_dir)
    pat = str(pattern or "").strip()
    if not pat:
        return {"ok": False, "error": "pattern is required"}

    limit = max(1, int(limit or 200))
    matches: List[str] = []
    # Walk bounded under base; match relative paths.
    for dirpath, dirnames, filenames in os.walk(base):
        # skip hidden dirs quickly
        dirnames[:] = [d for d in dirnames if not d.startswith(".")]
        rel_dir = str(Path(dirpath).resolve().relative_to(root))
        for name in filenames:
            rel = str(Path(rel_dir) / name) if rel_dir != "." else name
            if fnmatch.fnmatch(rel, pat) or fnmatch.fnmatch(name, pat):
                matches.append(str((root / rel).resolve()))
                if len(matches) >= limit:
                    return {"ok": True, "matches": matches, "truncated": True}
    return {"ok": True, "matches": matches, "truncated": False}


async def fs_grep(*, query: str, base_dir: str = ".", limit: int = 50, max_file_bytes: int = 500_000) -> dict:
    """
    Safe content search under tools.allowed_fs_root.
    Simple substring search (case-insensitive). Returns file+line snippets.
    """
    root = _allowed_root()
    base = _resolve_under_root(base_dir)
    q = str(query or "").strip()
    if not q:
        return {"ok": False, "error": "query is required"}
    ql = q.lower()

    limit = max(1, int(limit or 50))
    results: List[Dict[str, Any]] = []

    for dirpath, dirnames, filenames in os.walk(base):
        dirnames[:] = [d for d in dirnames if not d.startswith(".")]
        for name in filenames:
            p = (Path(dirpath) / name).resolve()
            try:
                p.relative_to(root)
            except ValueError:
                continue
            try:
                st = p.stat()
                if st.st_size > int(max_file_bytes):
                    continue
                text = p.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue

            lines = text.splitlines()
            for i, line in enumerate(lines, start=1):
                if ql in line.lower():
                    results.append({"path": str(p), "line": i, "text": line.strip()[:400]})
                    if len(results) >= limit:
                        return {"ok": True, "query": q, "results": results, "truncated": True}

    return {"ok": True, "query": q, "results": results, "truncated": False}

