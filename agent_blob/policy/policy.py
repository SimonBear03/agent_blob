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
