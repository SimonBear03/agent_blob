from __future__ import annotations

from typing import Any, Dict


async def web_fetch(url: str, *, max_bytes: int = 1_000_000, timeout_s: float = 15.0) -> dict:
    """
    Fetch a URL (GET) and return text content (best-effort) with safety limits.
    """
    u = str(url or "").strip()
    if not (u.startswith("http://") or u.startswith("https://")):
        return {"ok": False, "error": "URL must start with http:// or https://", "url": u}

    try:
        import httpx  # type: ignore
    except Exception as e:
        return {"ok": False, "error": "httpx is not installed", "url": u}

    max_bytes = max(1_000, int(max_bytes or 0))
    timeout = httpx.Timeout(timeout_s)
    headers = {"User-Agent": "agent_blob/2.0"}

    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True, headers=headers) as client:
            r = await client.get(u)
            content = r.content[:max_bytes]
            ctype = r.headers.get("content-type", "")
            text = ""
            if "text" in ctype or "json" in ctype or "xml" in ctype or ctype == "":
                text = content.decode(r.encoding or "utf-8", errors="replace")
            else:
                text = f"[non-text content-type: {ctype}] (bytes={len(content)})"
            return {
                "ok": True,
                "url": u,
                "status_code": int(r.status_code),
                "content_type": ctype,
                "text": text,
                "truncated": len(r.content) > len(content),
            }
    except Exception as e:
        return {"ok": False, "error": str(e), "url": u}

