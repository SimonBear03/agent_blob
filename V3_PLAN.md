# Agent Blob V3 Plan

## Objective
Ship V3 as a reliable, always-on master AI that can:
- handle concurrent user/background work without context confusion,
- run scheduled jobs predictably,
- delegate to sub-agents/workers by role,
- use MCP/skills safely,
- and be operated as a long-running service.

## V3 Product Boundaries
### In Scope
- Runtime reliability and task lifecycle hardening.
- Strong scheduling semantics (interval + cron + daily) with deterministic execution.
- Worker orchestration (spawn, monitor, result reporting).
- Better memory retrieval quality and control.
- Gateway resiliency (disconnect/reconnect safety, permission queue robustness).
- Ops baseline (health, logs, recovery behavior).

### Out of Scope
- Multi-tenant auth/roles.
- Full web UI.
- Quant backend implementation itself (kept as external MCP/service).

## Current Baseline (V2)
- Gateway + runtime split exists.
- Tool calling with permission gating exists.
- Scheduler exists.
- MCP and skills are integrated.
- Structured memory with SQLite + FTS + embeddings exists.
- Main gaps are reliability, deterministic scheduling behavior, cancellation/control plane, and operational hardening.

## V3 Success Criteria
V3 is done when all are true:
1. Scheduled tasks execute consistently and predictably across restarts.
2. Background runs never silently disappear; state is queryable.
3. Worker delegation is visible and manageable (active/finished/failed).
4. Memory recall quality is measurably better on long conversations.
5. Gateway/runtime recover cleanly from client disconnects and transient failures.
6. Core flows are covered by automated tests.

## Architecture Decisions for V3
1. Keep single-user model for now.
2. Keep one master timeline UX (no user-facing session switching).
3. Keep gateway as control plane and runtime as execution plane (same process now, separable later).
4. Keep policy-driven approvals (`deny > ask > allow`) with explicit capability classes.
5. Keep event log canonical; derived indexes remain replaceable.

## Workstreams

## 1) Reliability & Control Plane
### Deliverables
- Implement `run.cancel` end-to-end.
- Add run state machine guardrails (`queued -> running -> waiting_permission -> done/failed/cancelled`).
- Prevent duplicate streaming and orphaned run tasks on disconnect.
- Add idempotent permission response handling.

### Acceptance
- Cancelling a run stops further tool calls and streaming.
- Disconnect/reconnect does not crash gateway or leave invalid websocket send attempts.

## 2) Scheduler Hardening
### Deliverables
- Normalize schedule payload contract (`prompt` only; no pseudo tool-call strings).
- Persist deterministic `last_run_id`, `last_run_at`, `next_run_at`.
- Add missed-run policy on restart (`skip` for MVP; configurable later).
- Add schedule-level run lock to avoid overlapping duplicate triggers.

### Acceptance
- A 10-second schedule triggers consistently while gateway is up.
- Restart behavior is deterministic and documented.
- `list schedules` always reflects true state.

## 3) Worker Orchestration
### Deliverables
- Promote workers to first-class runtime entities with lifecycle states.
- Add worker registry persistence window (recent N) and query APIs.
- Standardize worker result envelope (`summary`, `artifacts`, `errors`).
- Add guardrail against nested unbounded delegation.

### Acceptance
- User can ask "what workers are active?" and receive accurate status.
- Worker failures are surfaced with actionable error details.

## 4) Memory Quality
### Deliverables
- Tighten memory extraction policy (avoid low-value duplicates).
- Add secondary dedup pass before insert/upsert (semantic + normalized text).
- Improve retrieval ranking weights with configurable profile.
- Add explicit memory controls (`forget`, `pin`, `list`, `search`) with stable behavior.

### Acceptance
- Reduced duplicate memory rows on repeated recall prompts.
- Better long-horizon recall in manual regression scenarios.

## 5) MCP & Skills Productionization
### Deliverables
- MCP tool-call robustness (schema validation, better error normalization).
- Skill loading observability (which enabled skills actually injected).
- Capability health checks at startup (non-fatal warnings).

### Acceptance
- MCP tool calls fail gracefully with clear cause.
- Skills availability/injection is deterministic from config.

## 6) Testing & Ops
### Deliverables
- Add test suites for:
  - scheduler behavior,
  - permission flow,
  - run cancellation,
  - memory insert/search/delete,
  - worker lifecycle.
- Add operational docs:
  - restart semantics,
  - backup/cleanup for `data/`,
  - expected retention behavior.

### Acceptance
- Core regression suite passes locally.
- README + V3 docs fully match implementation.

## Proposed Milestones
### M1: Runtime Control Stability
- `run.cancel`, websocket safety, permission queue correctness.

### M2: Scheduler + Workers Stability
- deterministic scheduler behavior and worker lifecycle visibility.

### M3: Memory Quality Upgrade
- dedup improvements, ranking polish, memory controls.

### M4: MCP/Skills Hardening + Tests
- robustness improvements + regression suite + docs finalization.

## Suggested File-Level Targets
- Gateway: `agent_blob/gateway/app.py`
- Runtime loop: `agent_blob/runtime/runtime.py`
- Scheduler: `agent_blob/runtime/storage/scheduler.py`
- Tasks: `agent_blob/runtime/storage/tasks.py`
- Memory DB/store: `agent_blob/runtime/storage/memory_db.py`, `agent_blob/runtime/storage/memory_store.py`
- Capability providers: `agent_blob/runtime/providers/*.py`
- CLI reliability UX: `agent_blob/clients/cli/main.py`
- Docs: `README.md`, `V3_PLAN.md`

## Risk Register
1. LLM non-determinism can still cause schedule/worker drift.
   - Mitigation: stronger tool contracts + runtime guardrails + explicit prompt constraints.
2. Long-running process resource growth.
   - Mitigation: strict retention, archive pruning, worker/task caps, health checks.
3. Permission deadlocks when no client is connected.
   - Mitigation: pending permission queue + expiration policy + explicit status visibility.

## Immediate Next Step
Start M1 first: implement `run.cancel` + websocket-safe run streaming guardrails, then lock this behavior with tests.
