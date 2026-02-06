from __future__ import annotations

import fnmatch
import json
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional


@dataclass(frozen=True)
class PolicyDecision:
    decision: str  # "allow" | "ask" | "deny"
    matched: Optional[str] = None


@dataclass
class Policy:
    allow: List[str]
    ask: List[str]
    deny: List[str]

    @staticmethod
    def load(path: str = "agent_blob.json") -> "Policy":
        p = Path(path)
        if not p.exists():
            # sensible defaults
            return Policy(
                allow=["filesystem.read", "filesystem.list"],
                ask=["shell.run", "filesystem.write", "web.*", "git.*"],
                deny=[],
            )
        data = json.loads(p.read_text(encoding="utf-8"))
        perm = (data.get("permissions") or {})
        return Policy(
            allow=list(perm.get("allow") or []),
            ask=list(perm.get("ask") or []),
            deny=list(perm.get("deny") or []),
        )

    @staticmethod
    def persist_decision(*, capability: str, decision: str, path: str = "agent_blob.json") -> None:
        """
        Persist a permission decision into agent_blob.json.

        We store exact capabilities (no pattern synthesis yet).
        Precedence is always deny > ask > allow.
        """
        cap = str(capability or "").strip()
        dec = str(decision or "").strip().lower()
        if not cap or dec not in ("allow", "deny", "ask"):
            return

        p = Path(path)
        if not p.exists():
            data = {}
        else:
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                data = {}
        if not isinstance(data, dict):
            data = {}

        perm = data.get("permissions")
        if not isinstance(perm, dict):
            perm = {}
            data["permissions"] = perm

        allow = list(perm.get("allow") or [])
        ask = list(perm.get("ask") or [])
        deny = list(perm.get("deny") or [])

        # Remove from all lists first
        allow = [x for x in allow if x != cap]
        ask = [x for x in ask if x != cap]
        deny = [x for x in deny if x != cap]

        if dec == "allow":
            allow.append(cap)
        elif dec == "deny":
            deny.append(cap)
        else:
            ask.append(cap)

        perm["allow"] = allow
        perm["ask"] = ask
        perm["deny"] = deny

        p.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    def check(self, capability: str) -> PolicyDecision:
        # deny > ask > allow
        for pat in self.deny:
            if fnmatch.fnmatch(capability, pat):
                return PolicyDecision("deny", pat)
        for pat in self.ask:
            if fnmatch.fnmatch(capability, pat):
                return PolicyDecision("ask", pat)
        for pat in self.allow:
            if fnmatch.fnmatch(capability, pat):
                return PolicyDecision("allow", pat)
        # default: ask for unknown capabilities
        return PolicyDecision("ask", None)
