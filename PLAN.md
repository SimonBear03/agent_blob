# Agent Blob V3 Plan

## Objective
Ship V3 as a reliable, always-on master AI with a modular architecture:
- gateway = control plane,
- runtime = execution plane,
- frontends = native/adapters,
- memory = pluggable subsystem with bounded context injection.

The V3 memory target is a full replacement of V2 memory flow (no candidate `memories.jsonl` pipeline).

## V3 Product Boundaries
### In Scope
- Runtime reliability and task lifecycle hardening.
- Strong scheduling semantics (interval + cron + daily) with deterministic execution.
- Worker orchestration (spawn, monitor, result reporting).
- Memory V3 replacement (modular, bounded, low-hardcode behavior).
- Gateway resiliency (disconnect/reconnect safety, permission queue robustness).
- Ops baseline (health, logs, recovery behavior).

### Out of Scope
- Multi-tenant auth/roles.
- Full web UI.
- Quant backend implementation itself (kept as external MCP/service).

## Current Baseline
- Gateway + runtime split exists.
- Tool calling with permission gating exists.
- Scheduler exists.
- MCP and skills are integrated.
- Frontend layout is moving to `frontends/native` + `frontends/adapters`.
- Memory V2 had mixed behavior (event recall + extractor + candidate logs + runtime heuristics).

## V3 Success Criteria
V3 is done when all are true:
1. Scheduled tasks execute consistently and predictably across restarts.
2. Background runs never silently disappear; state is queryable.
3. Worker delegation is visible and manageable (active/finished/failed).
4. Memory recall quality is stable on long conversations with bounded token usage.
5. Gateway/runtime recover cleanly from client disconnects and transient failures.
6. Core flows are covered by automated tests.

## Architecture Decisions
1. Keep single-user model for now.
2. Keep one master timeline UX (no user-facing session switching).
3. Keep gateway as control plane and runtime as execution plane (same process now, separable later).
4. Keep policy-driven approvals (`deny > ask > allow`) with explicit capability classes.
5. Keep event log canonical; retrieval indexes are derived and replaceable.

## Memory V3 (Canonical Workflow)
### Source of Truth
- `events.jsonl` remains canonical run history.
- `agent_blob.sqlite` (`memory_items`) is canonical long-term memory state.
- `pinned.json` is small always-load memory.

### Capture -> Consolidate -> Retrieve -> Inject
1. **Capture**: runtime appends run events (`run.input`, `run.output`).
2. **Extract**: after each completed turn, extractor derives durable memory items.
3. **Consolidate**: extracted items are upserted into SQLite with dedup/merge.
4. **Index**: FTS + embeddings are maintained as derived indexes in SQLite rows.
5. **Retrieve**: each run fetches bounded memory packet:
   - pinned memories,
   - recent turns,
   - related turns,
   - top-K long-term memories (hybrid lexical + vector).
6. **Inject**: runtime adds only bounded packet to model prompt.

### Explicit Non-Goals
- No full-history prompt replay.
- No candidate-memory log as a required runtime dependency.
- No hardcoded "remember" write path in runtime.

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

## 4) Memory V3 Replacement
### Deliverables
- Remove V2 candidate-memory dependency from active runtime path.
- Route all memory retrieval through one service interface.
- Keep retrieval limits and scoring knobs configurable in `agent_blob.json`.
- Keep memory tools deterministic (`search`, `list`, `delete`, `pin` where enabled).

### Acceptance
- Memory retrieval works without `memories.jsonl`.
- Repeated recall prompts do not create uncontrolled duplicate churn.
- Prompt memory packet is bounded and auditable.

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

## Milestones
### M1: Runtime Control Stability
- `run.cancel`, websocket safety, permission queue correctness.

### M2: Scheduler + Workers Stability
- deterministic scheduler behavior and worker lifecycle visibility.

### M3: Memory V3 Cutover
- new memory service in runtime path, bounded retrieval, no candidate-log dependency.

### M4: MCP/Skills Hardening + Tests
- robustness improvements + regression suite + docs finalization.

## File-Level Targets
- Gateway: `agent_blob/gateway/app.py`
- Runtime loop: `agent_blob/runtime/runtime.py`
- Scheduler: `agent_blob/runtime/storage/scheduler.py`
- Tasks: `agent_blob/runtime/storage/tasks.py`
- Memory: `agent_blob/runtime/memory/*`, `agent_blob/runtime/storage/memory_db.py`
- Capability providers: `agent_blob/runtime/providers/*.py`
- Frontends: `agent_blob/frontends/*`
- Docs: `README.md`, `PLAN.md`

## Risk Register
1. LLM non-determinism can still cause schedule/worker drift.
   - Mitigation: stronger tool contracts + runtime guardrails + explicit prompt constraints.
2. Long-running process resource growth.
   - Mitigation: strict retention, archive pruning, worker/task caps, health checks.
3. Permission deadlocks when no client is connected.
   - Mitigation: pending permission queue + expiration policy + explicit status visibility.
4. Memory extraction quality drift.
   - Mitigation: extractor prompt tests + conservative thresholds + explicit deletion tools.

## Immediate Next Step
Finish M3 cutover by removing remaining V2 memory artifacts from docs/config/runtime compatibility shims, then lock behavior with tests.
