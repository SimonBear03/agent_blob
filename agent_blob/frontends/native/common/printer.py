from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class Printer:
    """
    Small terminal renderer for interleaved run streaming.
    """

    active_stream_run_id: Optional[str] = None
    started_stream: set[str] | None = None

    def __post_init__(self):
        if self.started_stream is None:
            self.started_stream = set()

    def status(self, run_id: str, status: str):
        print(f"\n[{run_id}] status: {status}")

    def log(self, run_id: str, message: str):
        print(f"\n[{run_id}] {message}")

    def error(self, run_id: str, message: str):
        print(f"\n[{run_id}] ERROR: {message}")

    def done(self, run_id: str):
        print(f"\n[{run_id}] done")

    def token(self, run_id: str, text: str):
        if not text:
            return
        started = self.started_stream or set()
        if run_id not in started:
            print(f"\n[{run_id}] ", end="", flush=True)
            started.add(run_id)
            self.started_stream = started
            self.active_stream_run_id = run_id
        elif self.active_stream_run_id != run_id:
            print(f"\n[{run_id}] ", end="", flush=True)
            self.active_stream_run_id = run_id
        print(text, end="", flush=True)

