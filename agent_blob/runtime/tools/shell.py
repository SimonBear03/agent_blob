from __future__ import annotations

import asyncio


async def shell_run(command: str, timeout_s: int = 60) -> dict:
    """
    Minimal shell runner.
    Safety enforcement is handled by the gateway policy/approval layer.
    """
    proc = await asyncio.create_subprocess_shell(
        command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        out, err = await asyncio.wait_for(proc.communicate(), timeout=timeout_s)
    except asyncio.TimeoutError:
        proc.kill()
        return {"ok": False, "error": f"Timeout after {timeout_s}s"}
    return {
        "ok": proc.returncode == 0,
        "returncode": proc.returncode,
        "stdout": (out or b"").decode("utf-8", errors="replace"),
        "stderr": (err or b"").decode("utf-8", errors="replace"),
    }
