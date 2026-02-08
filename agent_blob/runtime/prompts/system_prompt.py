from __future__ import annotations

from pathlib import Path
from typing import Optional

_PROMPT_PATH = Path(__file__).with_name("system.md")
_DEFAULT_PROMPT = (
    "You are Agent Blob, an always-on master AI assistant.\n"
    "Be concise, factual, and execution-oriented.\n"
    "Use tools only when they materially help complete a user-requested task."
)


def _base_prompt() -> str:
    try:
        text = _PROMPT_PATH.read_text(encoding="utf-8").strip()
        return text or _DEFAULT_PROMPT
    except Exception:
        return _DEFAULT_PROMPT


def _worker_block(worker_type: str, *, include_change_summary: bool) -> str:
    worker_type = (worker_type or "").strip().lower()
    if worker_type == "briefing":
        return (
            "Worker mode: briefing\n"
            "- Gather and synthesize concise briefing output.\n"
            "- Prefer web_fetch when needed.\n"
            "- Return actionable summary."
        )
    if worker_type == "quant":
        return (
            "Worker mode: quant\n"
            "- Use MCP to query quant state and operations.\n"
            "- Prefer read/state queries before write actions.\n"
            "- Return clear status/risk summary."
        )
    if worker_type == "dev":
        suffix = "- Explain what changed and why." if include_change_summary else "- Return concise result."
        return (
            "Worker mode: dev\n"
            "- Focus on filesystem search/read and patch-based edits.\n"
            "- Keep changes minimal and deterministic.\n"
            f"{suffix}"
        )
    return (
        "Worker mode:\n"
        "- Execute delegated task and return concise result."
    )


def build_system_messages(
    *,
    mode: str,
    capability_instructions: Optional[str] = None,
    scheduled_id: Optional[str] = None,
    worker_type: Optional[str] = None,
) -> list[dict]:
    mode = (mode or "master").strip().lower()
    blocks = [_base_prompt()]

    if mode == "scheduled":
        blocks.append(
            "This run was triggered by an existing schedule.\n"
            "Execute the scheduled prompt now and avoid setup suggestions."
        )
        if scheduled_id:
            blocks.append(f"Schedule id: {scheduled_id}")
    if mode == "worker":
        blocks.append(
            _worker_block(
                worker_type or "",
                include_change_summary=True,
            )
        )

    if capability_instructions:
        blocks.append(capability_instructions.strip())

    return [{"role": "system", "content": "\n\n".join([b for b in blocks if b.strip()])}]
