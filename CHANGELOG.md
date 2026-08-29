# Atlas Changelog

All notable changes to Project Atlas are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to a milestone- and track-based release model
(Phase/track releases, not strict daily semantic releases).

---

## [Unreleased] — Foundation Strengthening

### Guided Self-Improvement Evolution Thread (Stage A1→H)

An additive, post-core self-improvement/promotion-review thread built on the
existing evolution pipeline. Each stage is deterministic, advisory, and
fail-soft; governance boundaries are preserved throughout.

- **Stage A1** — Repository self-knowledge map (`atlas/research/repository_map.py`).
- **Stage B** — Evolution intelligence consumes `development` records
  (`atlas/evolution/intelligence_engine.py`).
- **Stage C** — Impact-aware development planning validation (advisory).
- **Stage D** — Context-aware development intelligence.
- **Stage E** — Promotion gate foundation (`atlas/evolution/promotion_gate.py`):
  deterministic risk assessment plus bounded `PENDING_REVIEW → APPROVED /
  REJECTED` lifecycle; APPROVED never mutates the repository.
- **Stage F** — Research → development intelligence bridge
  (`atlas/research/evidence_summary.py`).
- **Stage G** — Decision-quality scoring (`atlas/evolution/decision_quality.py`):
  deterministic advisory metrics joined into planning context.
- **Stage H** — Promotion-review visibility:
  - kernel bridge `Atlas.submit_development_for_promotion_review()` opens
    `PENDING_REVIEW` audit rows carrying bounded change evidence (no approve/
    reject/promote/execute);
  - read-only views `Atlas.pending_promotion_reviews()` and
    `Atlas.promotion_review_details(request_id)`;
  - operator CLI `atlas promotion pending` and `atlas promotion show
    <request_id>` (presentation-only).
  - Governed-sink integration tests aligned (`test_kernel_advanced_reasoning_integration.py`,
    `test_kernel_longterm_integration.py`, `test_phase21_research_feedback.py`).

### Persistent Learning — reusable learning-insight persistence

The first post-A1→H capability (commit `5bfa615`). Closes the gap where
reusable `LearningInsight` objects (runtime reflection, self-development
outcomes, and other validated conclusions with provenance/confidence) were
produced by the `LearningEngine` but lost on restart.

- `LearningMemory` now accepts an optional storage adapter (the existing
  kernel-owned `SQLiteEvolutionStorage`): insights are dual-written on
  `store_insights` and restored via `restore()`/`bind_storage()`.
- Additive migration v11 adds `learning_insights` (schema version **11**).
- Kernel wires the evolution storage into `LearningMemory` during
  `_init_tracks()`; storage failures degrade gracefully to memory-only.
- No new store, retrieval mechanism, provenance system, or governance bypass —
  the existing evolution storage and governed pipeline are reused.
- Low-quality/transient reasoning is still gated by the existing
  `InsightConsolidator` quality thresholds before it reaches memory.

### Deterministic Semantic Memory Recall (Track C)

Deterministic, read-only recall over the existing long-term stores
(commit `57f0063`):

- New pure `SemanticRecallEngine` (`atlas/longterm/semantic_recall.py`) ranks
  stored episodes and procedures by token overlap with fixed field weights
  (tags 3.0, name/title 2.0, tool names 2.0, category/kind/outcome 1.5,
  summary/description 1.0) × a coverage multiplier, rounded to 4 decimals;
  zero-match items are excluded; results are bounded (hard cap 500) and
  deterministically ordered (`-score, type, id`).
- Every result is fully explained (matched tokens/fields) and
  provenance-preserving (complete existing item `to_dict()` payloads).
- Registered additively as the `memory.semantic_query` capability (required,
  fail-closed `query`; `limit` default 100, capped 500) and exposed via
  `atlas memory search <query> [--limit N]` (presentation-only).
- No new storage, tables, or retrieval subsystem; schema remains **v11**; no
  AI/LLM involvement; strictly read-only — repositories and storage are never
  mutated.
- Full suite verified: 4,285 tests, 0 failed (pytest exit 0).

### Long-Term Memory Forgetting Policy (Track C)

Operationalized the existing principled-forgetting policy (commit `be2bb84`):

- `MemoryDecayPolicy` defaults are now active: episodes inactive > 90 days and
  procedures unused > 180 days become deterministic forgetting candidates
  (`min_importance` 0.1 and all other policy fields unchanged).
- Every forget flag carries deterministic explanation metadata
  (`metadata["flags"]`: reason / days_inactive / importance); the public
  flagged-id tuples are unchanged.
- Consolidation flags remain advisory PENDING records through the existing
  GOV-010 governed path — no applier exists and nothing deletes, merges, or
  mutates memory; repositories and storage are untouched. Schema remains
  **v11**.
- Full suite verified: 4,296 tests, 0 failed (pytest exit 0).

### Conversational Development Intake (B1+B2+B3)

Committed together at `ce12fb8` (branch `phase5-memory-evolution`). An
additive, post-core milestone connecting casual conversational development
requests to the EXISTING governed development-cycle preparation flow. No new
subsystem, governance surface, storage, schema, or execution mechanism;
the RuntimeCoordinator 15-stage order and all locked packages remain
untouched.

- **B1 — README/config reconciliation:** `README.md` updated to the
  post-core state (schema v11, 4,291-test inventory, post-core memory
  thread, "no implementation NEXT" roadmap summary); `config.toml` version
  aligned to `0.20.0`.
- **B2 — Deterministic conversational task intake**
  (`atlas/conversation/task_intake.py`): pure, deterministic-first
  `TaskIntake` producing a bounded, provenance-carrying `TaskSpec` (task
  type, intent, goal, constraints, priorities, success criteria, ambiguity,
  confidence, needs_clarification, source, verified). Optional model
  assistance is an injectable `IntentParser` — OFF by default, output
  untrusted and sanitized. `ConversationService` propagates the structured
  goal and `metadata["task"]`; `task_intake=None` preserves the legacy
  raw-input-as-goal behavior exactly.
- **B3 — Conversational development bridge**
  (`atlas/conversation/development_intake.py` + `ConversationService`
  `development_bridge` + kernel wiring): a pure `TaskSpec → DevelopmentNeed`
  adapter with clarification gating; DEVELOPMENT_REQUEST routes through the
  existing `Atlas.run_development_cycle()` (F9) and STOPS at
  `PENDING_APPROVAL`. The bridge never approves, executes, or promotes;
  `Atlas.tick()` is unchanged.
- **Governance:** unchanged. `SELF_CONFIG`/`INFORMATION` remain the enabled
  governed scopes; `CODE_ARTIFACT`/`SANDBOXED`/`AUTONOMOUS` remain locked.
  The deterministic `ChangeSupplier` remains the default; no model-assisted
  supplier was implemented or wired.
- **Schema:** remains **v11** (no migration).
- Tests: `tests/test_conversation_task_intake.py`,
  `tests/test_conversation_development_intake.py`,
  `tests/test_conversation_development_bridge.py`, plus
  `tests/test_conversation_service.py` additions. Full suite green
  (pytest exit 0); the pre-existing `test_cognition_service_new.py`
  circular-import issue reproduces only in isolation and is unrelated.
- **B4 remains undefined and unapproved.**

### Test Coverage Audit — Placeholder Test-Module Resolution

Closed the recorded test-coverage technical debt (`docs/technical_debt.md`).
The audit verified that every live surface named by the placeholders already
had meaningful coverage elsewhere, so the eight 0-byte placeholder modules
were removed without losing any test content:

- Removed `tests/test_boot.py`, `tests/test_services.py`,
  `tests/test_ai_service.py`, `tests/test_ai_capabilities.py`,
  `tests/test_ai_manager_routing.py`, `tests/test_ai_provider_metadata.py`,
  and `tests/memory/test_memory.py` (each redundant with existing suites —
  AI fallback/routing/model-abstraction, cognition/memory-service, and the
  root `tests/test_memory.py`).
- Removed `tests/test_agent_integration.py` (obsolete — `atlas/agents/` was
  removed in Foundation Strengthening Batch 2).
- No additional placeholder modules were found; no source code changed; no
  meaningful tests were removed.
- Verified post-change: `pytest --collect-only -q` → 4,291 tests, 0 errors;
  full suite `python -m pytest -q` → exit code 0, 0 failures.

### Foundation Strengthening Batch 1 — Kernel Composition-Root Decomposition

- Decomposed the monolithic `Atlas.start()` method into 7 private domain
  helpers (`_init_ai_provider`, `_init_memory_knowledge`,
  `_init_reasoning_pipeline`, `_init_cognitive_engines`, `_init_tracks`,
  `_init_evolution_pipeline`, `_init_runtime_services`). No public API or
  behavioral change; composition-root semantics preserved.

### Foundation Strengthening Batch 2 — Scaffold & Legacy Cleanup

- Removed 30 files of genuinely unused/unwired scaffolding:
  - `atlas/agents/` (27 files) — obsolete multi-agent scaffold
  - `atlas/automation/` (1 file) — empty package
  - `atlas/interfaces/` (1 file) — empty package
  - `atlas/events/agent_event_bridge.py` — referenced only by deleted agents
  - `atlas/runtime/agent_runtime.py` — referenced only by deleted agents
  - `atlas/scheduler/agent_scheduler.py` — referenced only by deleted agents
- Retained `atlas/scheduler/` (used by `atlas/task/task_manager.py`) and
  `atlas/models/ai_response.py` (used by all AI providers).
- Track E (Multi-Agent Collaboration) remains PROPOSED in the roadmap; any
  future agent capability must be designed against the current architecture.

### Batch 5 — Phase 16 Autonomy Persistence Foundation

- Wired `AutonomySQLiteStorage` + `ScheduleStore` into the kernel via
  `atlas/kernel/autonomy_wiring.py` helper.  `ScheduleStore` receives a
  default **disabled** `AutonomyPolicy` — autonomous execution remains
  disabled.  This is the persistence foundation for the future governed
  ingest sink pipeline.

### Post-Core Adaptation Foundation (F1–F6) — working tree

Completed the post-Core **Adaptation Foundation**: a bounded, manually-triggered,
deterministic, governance-safe adaptation pipeline built additively on top of the
frozen Core (Phase E at `e100883`). All layers reuse existing infrastructure —
no new EventBus / scheduler / registry / memory / approval / authorization /
executor / sandbox, no `Atlas.tick()` integration, no daemon.

- **F1 — Environment Foundation** (`atlas/evolution/environment/`): `EnvironmentObserver`
  observes provider state via duck-typed providers and emits deterministic
  `EnvironmentChange` records on the existing EventBus / SelfObservationEngine.
- **F2 — Knowledge Freshness & Provenance** (`atlas/evolution/freshness/`):
  `KnowledgeFreshnessAssessor` classifies knowledge FRESH/STALE/UNCERTAIN/UNASSESSED
  against an injectable `FreshnessPolicy` and emits bounded stale-knowledge candidates.
- **F3 — Capability / Model / Tool Lifecycle** (`atlas/evolution/lifecycle/`):
  `CapabilityLifecycleAssessor` produces deterministic `LifecycleAssessment` records
  (NONE/REVIEW/DEPRECATE/REPLACE/FALLBACK) without mutating registries.
- **F4 — Governed Adaptation Decision Engine** (`atlas/evolution/adaptation/engine.py`):
  `AdaptationDecisionEngine` translates F3 assessments into DRAFT-only
  `EvolutionProposal` candidates; never approves.
- **F5 — Adaptation Evaluation & Feedback** (`atlas/evolution/adaptation/evaluator.py`):
  `AdaptationEvaluator` evaluates proposal lifecycle states + Phase-E outcomes
  (reusing `effectiveness_proxy`), separates governance from technical outcomes,
  and emits bounded `AdaptationFeedback` with F2/F3 bridge signals.
- **F6 — Full Adaptation Orchestration** (`atlas/evolution/adaptation/orchestrator.py` +
  `Atlas.run_adaptation_cycle()`): one bounded, manually-triggered F1→F2→F3→F4
  cycle producing DRAFT proposals (and optional F5 evaluation of supplied
  already-approved proposal/outcome data). Stops at the DRAFT proposal boundary.

**Guarantees:** deterministic, bounded (per-stage caps + surfaced truncation),
fail-closed on malformed input, provenance preserved end-to-end, CODE remains
constitutionally protected, Phase E remains the governed self-development
execution boundary. Verification: F1–F6 focused 177 passed; architecture/container/
governance regressions 106 passed + 10 subtests; Phase-E E2–E6 143 passed, 1
skipped; four known baseline stale failures unchanged.

### Post-Core Autonomous Operation & Research (F7–F8) — `abd6856`

Completed post-Core **F7 Autonomous Operation** and **F8 Autonomous Research &
Information Acquisition**. All layers reuse existing infrastructure additively
— no new scheduler / EventBus / database / memory / governance / AI stack, no
`Atlas.tick()` integration, no daemon.

- **F7 — Autonomous Operation** (`atlas/evolution/operation/`):
  `OperationController` wraps the existing F6 adaptation cycle in a bounded,
  deterministic cooldown / budget / failure policy (`OperationPolicy`). One
  bounded invocation per explicit call (`Atlas.run_operation_cycle()`); never
  a daemon, never tick()-driven; never approves or executes.
- **F8 — Research & Information Acquisition**
  (`atlas/research/sources/web.py`, `atlas/research/acquisition.py`):
  bounded HTTP(S) `WebSourceAdapter` (deny-by-default host allowlist, SSRF
  protection, size/time/redirect caps) composed by the model-independent
  `InformationAcquisitionService` over the EXISTING research pipeline;
  provenance + `extraction_origin`; GOV-008 governed ingest; kernel bridge
  `Atlas.run_information_acquisition()`.

Verification: focused F7/F8 90 passed; full suite **3896 passed, 4 failed**
(pre-existing baseline), **1 skipped, 67 subtests**.

### Governed Autonomous Development Cycle (F9) — `08b5596`

Completed post-Core **F9 Governed Autonomous Development Preparation**
(`atlas/evolution/development_cycle.py`). `DevelopmentCycleController` turns a
development need into a bounded DRAFT `EvolutionProposal` and submits it to the
existing `ApprovalManager`, STOPPING at the human approval boundary
(PENDING_APPROVAL). Deterministic change supplier by default (E5 metadata
convention); optional model assistance injectable, OFF by default, marked
unverified-draft. Kernel bridge: `Atlas.run_development_cycle()`.

Verification: focused F9 21 passed; full suite **3917 passed, 4 failed**
(same pre-existing baseline), **1 skipped, 67 subtests**.

### Deterministic AI Availability (F10) — `9352948`

Completed post-Core **F10 Resource Independence / Model-Optional Intelligence**
foundations (`atlas/ai/availability.py`): `ProviderAvailabilityTracker` derives
HEALTHY / DEGRADED / OFFLINE / UNKNOWN from the existing failure taxonomy over
a bounded outcome window, exposed through the EXISTING F1 environment-
observation cycle as a PROVIDER-domain state. Observation-only, on demand,
model-independent. An invocation-budget subsystem was evaluated and
intentionally skipped (routing already prefers cheapest-capable profiles with
capped attempts). Kernel surface: `Atlas.ai_availability`.

Verification: focused F10 18 passed; full suite **3935 passed, 4 failed**
(same pre-existing baseline), **1 skipped, 67 subtests**.

### Long-Term Self-Management & Recovery (F11) — `e620177`

Completed post-Core **F11 Long-Term Self-Management & Recovery**:

- Wired the EXISTING Phase 16.7 `BootActivationService` into startup
  (`init_boot_activation` in `atlas/kernel/autonomy_wiring.py`) — staged config
  activation/verification with SAFE_MODE narrowing autonomous advancement.
- Added the read-only `SelfManagementReview`
  (`atlas/evolution/self_management.py`) aggregating durable evidence into a
  bounded JSON-safe report via `Atlas.run_self_management_review()`. Stops
  before every governance boundary; flagged needs are inert evidence for the
  existing F6/F9 flows.

Verification: focused F11 23 passed; regression subset 327 passed + 10 subtests;
full suite **3958 passed, 4 failed** (same pre-existing baseline), **1 skipped,
67 subtests**.

### Permanent Architectural Directive — Model Independence & Information Autonomy

Documentation-only permanent boundary adopted ahead of post-Core F7–F11
(recorded at `83b1c0e`; no code, test, or runtime-behavior change):

- **SELF → DIRECT SOURCES → MODEL ASSISTANCE.** Atlas prefers existing verified
  knowledge/memory, then its own deterministic tools/algorithms/reasoning, then
  direct external-source retrieval, and only then AI-model assistance (only
  when the above cannot resolve the need).
- **No single point of failure.** No AI model/provider/family/API/framework/
  external service may become a permanent dependency. AI models are replaceable
  assistants, not permanent authorities or sources of truth.
- **Model-derived information is not automatically durable knowledge.** Claims
  must be traced to evidence, independently verified, associated with
  provenance + retrieval/verification timestamps, assigned confidence, and
  stored via the existing knowledge/provenance architecture.
- **Resource independence** (independence before cost; usage necessity-,
  capability-, risk-, and budget-aware and replaceable).
- Recorded roadmap: F7 Autonomous Operation, F8 Autonomous Research & Knowledge
  Acquisition, F9 Governed Autonomous Development, F10 Resource Independence &
  Model-Optional Intelligence, F11 Long-Term Self-Management & Recovery — all
  preceded by an inspect-before-build review of existing infrastructure.

### Test Status

- **v0.20.0 release gate:** 3260 passed, 0 failed, 57 subtests, 2 warnings
  (identical to the v0.20.0 release gate).
- **Deterministic semantic memory recall batch (`57f0063`):** full suite
  4,285 tests, 0 failed (pytest exit 0).
- **Long-term memory forgetting-policy batch (`be2bb84`):** full suite 4,296
  tests, 0 failed (pytest exit 0).

---

## [v0.20.0] — Atlas Core Release — 2026-08-16

### Atlas Core is COMPLETE at Phase 22

Phase 22 (Toolchain Execution & Learned-Skill Progression) is the **FINAL
numbered implementation phase for Atlas Core**. There is **NO Phase 23**.
Development has transitioned to **post-core guided self-improvement**: Atlas
improves itself through the existing governed mechanisms
(`Observe/record → analyze/plan → propose → approve → execute governed changes
→ verify → repeat`) with `SELF_CONFIG`/`INFORMATION` as the enabled governed
scopes and `CODE_ARTIFACT`/`SANDBOXED`/`AUTONOMOUS` remaining locked in
accordance with the constitution.

### Post-Core Improvements (F1–F8)

- **F1 — Runtime observation coverage**: five observation categories per
  runtime cycle (`atlas/evolution/runtime_observations.py`).
- **F2 — Planner observation aggregation**: weakness detectors average the
  relevant metric over the bounded per-category observation window instead of
  only the newest observation (`ImprovementPlanner._mean_value`).
- **F3 — Subsumed by F8**: proposal list/show/audit visibility supersedes the
  separate audit item.
- **F4 — Deferred/monitored**: `EvolutionScheduler.tick()` has a shared tick
  counter, a new-observations gate, and a reentrancy guard; duplicate-analysis
  risk is monitored, no change was made.
- **F5 — Scheduler fail-soft diagnostics**: `EvolutionSchedulerResult.last_error`
  exposes the most recent integration error while fail-soft semantics remain
  byte-identical.
- **F6 — Expected behavior**: SQLite evolution storage's memory-only fallback
  is the documented degraded mode; `evolution.storage.unavailable` is emitted.
- **F7 — Closed learning feedback loop**: deterministic failure
  `EvolutionRecord`s → insight → planner feedback.
- **F8 — Evolution audit/proposal visibility**: `get_proposal_audit()` plus a
  read-only `atlas proposals list|show|audit` CLI, exposing approval decisions,
  execution outcomes, and failure error/status.

### Hardening

- **Cognition Mock Provider routing**: the cognition runtime test now routes
  via Mock Provider (the `ModelRouter.route → None` patch is scoped to the
  `send()` call), eliminating the previously pre-existing Ollama 404.
- **SQLite INTEGER overflow clamp**: understanding `frequency` /
  `observed_count` binds are saturated deterministically at `2**63 - 1`,
  eliminating the `OverflowError` caused by unbounded counter accumulation
  across restore/merge cycles.

### Test Status

- **3260 passed, 0 failed, 57 subtests, 2 warnings** at HEAD `b2b4674`.
- The 2 warnings are **non-blocking** `asyncio.iscoroutinefunction`
  deprecation warnings in `test_phase21_research_coordinator.py` (they become
  errors only on Python ≥ 3.16).

### Governance

- **Autonomous code mutation remains disabled.** `CODE_ARTIFACT` (3),
  `SANDBOXED` (4), and `AUTONOMOUS` (5) execution levels remain locked and
  unreachable; `SELF_CONFIG` (1) and `INFORMATION` (2) remain the enabled
  governed scopes.
- All state mutation continues to flow through the Evolution Framework; the
  `EvolutionExecutionGateway` remains the single execution choke point and the
  `EvolutionAutonomyDispatcher` its sole caller.
- Capability dispatch remains exclusively
  `CapabilityRegistry → CapabilityRouter → CapabilityDispatcher`; REASONING
  remains candidate-only; the RuntimeCoordinator retains exactly 15 stages.

### Components Changed Since v0.20 (post-core)

- `atlas/evolution/scheduler.py` — fail-soft error diagnostics (`last_error`).
- `atlas/evolution/improvement_planner.py` — window mean aggregation.
- `atlas/cli/evolution_commands.py`, `atlas/cli/main.py` — `proposals` CLI.
- `atlas/storage/understanding_storage.py` — INTEGER saturation clamp.
- Related post-core test suites: F1, F2, F5, F7, F8, hardening clamp, and the
  cognition runtime routing correction.
