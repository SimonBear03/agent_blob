from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class ArchiveRecord:
    kind: str
    path: str
    rotated_at_ms: int
    bytes: int


def archives_dir(data_dir: Path) -> Path:
    d = data_dir / "archives"
    d.mkdir(parents=True, exist_ok=True)
    return d


def index_path(data_dir: Path) -> Path:
    return archives_dir(data_dir) / "index.json"


def _load_index(data_dir: Path) -> Dict[str, Any]:
    p = index_path(data_dir)
    if not p.exists():
        return {"archives": []}
    try:
        obj = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(obj, dict) and isinstance(obj.get("archives"), list):
            return obj
    except Exception:
        pass
    return {"archives": []}


def _save_index(data_dir: Path, obj: Dict[str, Any]) -> None:
    p = index_path(data_dir)
    p.write_text(json.dumps(obj, indent=2, ensure_ascii=False), encoding="utf-8")


def append_index_record(data_dir: Path, rec: ArchiveRecord) -> None:
    idx = _load_index(data_dir)
    archives = list(idx.get("archives") or [])
    archives.append(
        {
            "kind": rec.kind,
            "path": rec.path,
            "rotated_at_ms": rec.rotated_at_ms,
            "bytes": rec.bytes,
        }
    )
    idx["archives"] = archives
    _save_index(data_dir, idx)


def rotate_jsonl(
    *,
    data_dir: Path,
    kind: str,
    active_path: Path,
    max_bytes: int,
) -> Optional[ArchiveRecord]:
    """
    Rotate a JSONL file into data/archives if it exceeds max_bytes.
    Returns an ArchiveRecord when rotated, else None.
    """
    max_bytes = int(max_bytes or 0)
    if max_bytes <= 0:
        return None
    if not active_path.exists():
        return None

    try:
        size = active_path.stat().st_size
    except Exception:
        return None

    if size < max_bytes:
        return None

    rotated_at_ms = int(time.time() * 1000)
    ts = time.strftime("%Y%m%d_%H%M%S", time.localtime(rotated_at_ms / 1000.0))
    dst = archives_dir(data_dir) / f"{kind}_{ts}.jsonl"

    # Atomic-ish rename; then recreate an empty active file.
    active_path.rename(dst)
    active_path.write_text("", encoding="utf-8")

    rec = ArchiveRecord(kind=kind, path=str(dst), rotated_at_ms=rotated_at_ms, bytes=size)
    append_index_record(data_dir, rec)
    return rec


def prune_archives(
    *,
    data_dir: Path,
    kind: str,
    keep_days: int,
    keep_max_files: int,
) -> Dict[str, int]:
    """
    Delete old archive files of a given kind from data/archives.
    Returns {removed:int, kept:int}.
    """
    keep_days = max(0, int(keep_days or 0))
    keep_max_files = max(0, int(keep_max_files or 0))

    d = archives_dir(data_dir)
    files = sorted(d.glob(f"{kind}_*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)

    now = time.time()
    cutoff = now - (keep_days * 86400) if keep_days else None

    kept: List[Path] = []
    removed = 0
    for p in files:
        if cutoff is not None and p.stat().st_mtime < cutoff:
            try:
                p.unlink()
                removed += 1
            except Exception:
                kept.append(p)
            continue
        kept.append(p)

    if keep_max_files and len(kept) > keep_max_files:
        for p in kept[keep_max_files:]:
            try:
                p.unlink()
                removed += 1
            except Exception:
                pass
        kept = kept[:keep_max_files]

    # Rebuild index best-effort (simple and reliable).
    idx = _load_index(data_dir)
    archives = []
    for p in sorted(d.glob("*.jsonl"), key=lambda x: x.stat().st_mtime, reverse=True):
        stem = p.stem
        k = stem.split("_", 1)[0] if "_" in stem else "unknown"
        try:
            st = p.stat()
            archives.append({"kind": k, "path": str(p), "rotated_at_ms": int(st.st_mtime * 1000), "bytes": st.st_size})
        except Exception:
            continue
    idx["archives"] = archives
    _save_index(data_dir, idx)

    return {"removed": removed, "kept": len(kept)}

