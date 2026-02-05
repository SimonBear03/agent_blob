from __future__ import annotations

import difflib
from pathlib import Path
from typing import Any, Dict, List

from agent_blob.runtime.tools.filesystem import filesystem_read_optional, filesystem_write


def _apply_unified_diff(old_text: str, diff_text: str) -> str:
    """
    Apply a unified diff to old_text and return new text.
    Only supports standard unified diffs produced by difflib.unified_diff.
    """
    old_lines = old_text.splitlines(keepends=True)
    diff_lines = diff_text.splitlines(keepends=True)

    # Skip headers if present.
    i = 0
    while i < len(diff_lines) and (diff_lines[i].startswith("---") or diff_lines[i].startswith("+++")):
        i += 1
    if i < len(diff_lines) and diff_lines[i].startswith("@@"):
        pass
    elif i >= len(diff_lines):
        return old_text

    out: List[str] = []
    old_idx = 0

    def _parse_hunk_header(line: str) -> tuple[int, int, int, int]:
        # @@ -l,s +l,s @@
        # s may be omitted (defaults 1)
        parts = line.split()
        a = parts[1]  # -l,s
        b = parts[2]  # +l,s
        def parse(seg: str) -> tuple[int,int]:
            seg = seg[1:]
            if "," in seg:
                l, s = seg.split(",", 1)
                return int(l), int(s)
            return int(seg), 1
        al, asz = parse(a)
        bl, bsz = parse(b)
        return al, asz, bl, bsz

    while i < len(diff_lines):
        line = diff_lines[i]
        if not line.startswith("@@"):
            i += 1
            continue

        al, asz, bl, bsz = _parse_hunk_header(line)
        # hunks are 1-based line numbers
        target_old = max(0, al - 1)
        # copy unchanged prefix
        out.extend(old_lines[old_idx:target_old])
        old_idx = target_old
        i += 1

        while i < len(diff_lines) and not diff_lines[i].startswith("@@"):
            dl = diff_lines[i]
            if dl.startswith(" "):
                # context line: must match
                out.append(old_lines[old_idx])
                old_idx += 1
            elif dl.startswith("-"):
                # deletion
                old_idx += 1
            elif dl.startswith("+"):
                out.append(dl[1:])
            elif dl.startswith("\\"):
                # "\ No newline at end of file"
                pass
            else:
                # unknown line; ignore
                pass
            i += 1

    # copy remaining
    out.extend(old_lines[old_idx:])
    return "".join(out)


async def edit_apply_patch(*, path: str, patch: str, create_parents: bool = True) -> dict:
    """
    Apply a unified diff patch to a file.
    """
    old_res = await filesystem_read_optional(path)
    if not old_res.get("ok"):
        return {"ok": False, "error": old_res.get("error"), "path": old_res.get("path")}
    old = str(old_res.get("content", "") or "")
    try:
        new = _apply_unified_diff(old, str(patch or ""))
    except Exception as e:
        return {"ok": False, "error": f"Patch apply failed: {e}", "path": old_res.get("path")}
    return await filesystem_write(path, new, append=False, create_parents=create_parents)


async def edit_preview_patch(*, path: str, patch: str) -> dict:
    """
    Return a preview diff of applying a patch.
    """
    old_res = await filesystem_read_optional(path)
    if not old_res.get("ok"):
        return {"ok": False, "error": old_res.get("error"), "path": old_res.get("path")}
    old = str(old_res.get("content", "") or "")
    new = _apply_unified_diff(old, str(patch or ""))
    diff = difflib.unified_diff(
        old.splitlines(keepends=True),
        new.splitlines(keepends=True),
        fromfile=f"a/{path}",
        tofile=f"b/{path}",
        n=3,
    )
    text = "".join(diff)
    return {"ok": True, "path": str(old_res.get("path")), "preview": text}

