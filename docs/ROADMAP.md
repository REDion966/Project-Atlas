# ATLAS ROADMAP — Authoritative Future Direction

**Current reference for where Atlas is going next.**

This is the authoritative forward-planning document. Status categories are used
strictly:

- **COMPLETED** — shipped and verified
- **CURRENT** — actively in progress
- **NEXT** — the immediate next item with an existing plan
- **PLANNED** — agreed direction with a supporting plan
- **DEFERRED** — agreed but intentionally postponed
- **PROPOSED** — possible future direction, **not yet an approved design**

> **Rule for future AI agents:** anything PROPOSED below is not implemented and
> not approved. Do not build from a PROPOSED item as if it were a plan.
> *Never treat archived documents as current architecture.*

---

## COMPLETED — Shipped Work

### Tracks A, B, C
| Track | Capability | Delivered |
|---|---|---|
| **A** | Research & Knowledge | Complete (`v0.17.0`) — `atlas/research/`, migration v7, `research.*`, GOV-008, CLI |
| **B** | Tool Ecosystem | Complete (`v0.18.0`) — `atlas/toolchain/`, migration v8, GOV-009, CLI |
| **C** | Long-Term Learning | Complete & runtime-integrated (`v0.19.1`) — `atlas/longterm/`, migration v9, GOV-010, CLI |

### Track D — Advanced Reasoning (released)
- Multi-step reasoning, causal/counterfactual analysis, hypothesis generation,
  self-verification, meta-reasoning
- `atlas/advanced_reasoning/` package + kernel-private `AdvancedReasoningService`
- `reasoning_*` persistence (migration **v10**)
- `reasoning.*` capability handlers + `atlas reasoning` CLI
- GOV-011 (additive) + component metadata + trace-recorder pipeline integration
- Verified full suite at release gate: **2973 passed, 57 subtests, 0 failed,
  0 errors**
- **Released as `v0.20`** (annotated tag)

### Track A — Research Coordinator (Phase 21, implemented, not released)
- `ConcreteResearchCoordinator` in `atlas/research/coordinator.py` — first
  concrete implementation of the legacy `ResearchCoordinator` ABC; composes the
  existing Track A planner/extractor/verifier/storage/ingest via DI (no
  duplicates).
- `research.coordinate` capability registered additively by the kernel and
  reachable through a plan step via the existing
  CapabilityRegistry → CapabilityRouter → CapabilityDispatcher path
  (PLANNING-stage dispatch; REASONING stays candidate-only).
- Research execution results enter the existing Phase 20 outcome → Reflection →
  Learning → capability selection feedback loop as normal ReasoningOutcomes; no
  research-specific learning subsystem was added.
- ResearchIngestBridge governed and fail-closed from day one (no direct
  KnowledgeManager injection); its runtime governed sink was wired post-Core
  (F-series close-out) — see DEFERRED/RESOLVED below.
- Tests: `tests/test_phase21_research_coordinator.py`,
  `tests/test_phase21_research_feedback.py`. Commits: `7d86a6b`, `fee0e32`.
- Bundled with the Phase 22 milestone (no separate Phase 21 tag, nothing pushed).

### Phase 22 — Toolchain Execution & Learned-Skill Progression (COMPLETE)
- **Batch 1 — CONDITIONAL execution** (`0926ea2`): deterministic selection of
  later steps from prior step output; no general expression language.
- **Batch 2 — PARALLEL execution** (`7fa81f3`): deterministic sequential
  fan-out/fan-in; NO actual concurrency ("No threading. No async. No
  subprocess." remains in force).
- **Batch 3 — Learned-skill authoring/promotion**: pure in-memory
  `ToolSkillAuthor`/`LearnedSkillPromoter`; promotion governed via
  `ToolchainIngestBridge`/GOV-009, fail-closed without a sink.
- **Batch 4 — Integration & acceptance** (`f501367`): toolchain capabilities
  reachable through the existing capability dispatch path; all invariants hold.
- **Atlas Core is COMPLETE at Phase 22 — the FINAL numbered implementation
  phase for Atlas Core. There is NO Phase 23.** The next development model is
  post-core guided self-improvement (see CURRENT below and
  `docs/ATLAS_STATE.md` §22.4).
- Full suite at acceptance: **3169 passed, 57 subtests, 1 failed** — the
  single failure is the pre-existing Ollama-dependency
  `test_cognition_runtime.py::test_full_cognition_conversation_flow`
  (localhost:11434 unavailable), reproduced on the pre-Phase-21 baseline.

### Post-Core Guided Self-Improvement (COMPLETE — F1–F8 + hardening)
Post-core work completed on top of Atlas Core, ahead of the v0.20.0 release:

- **F1 — Runtime observation coverage**: five observation categories per
  runtime cycle (`atlas/evolution/runtime_observations.py`).
- **F2 — Planner observation aggregation**: weakness detectors average the
  relevant metric over the bounded per-category observation window instead of
  only the newest observation (`ImprovementPlanner._mean_value`).
- **F3 — SUBSUMED by F8**: proposal list/show/audit visibility.
- **F4 — DEFERRED/MONITORED**: EvolutionScheduler shared tick counter +
  new-observations gate + reentrancy guard prevent duplicate analysis.
- **F5 — Scheduler fail-soft diagnostics**: `EvolutionSchedulerResult.last_error`.
- **F6 — EXPECTED BEHAVIOR**: SQLite evolution storage memory-only fallback.
- **F7 — Closed learning feedback loop**: failure EvolutionRecords → insight →
  planner feedback.
- **F8 — Evolution audit/proposal visibility**: `get_proposal_audit()` +
  `atlas proposals list|show|audit` CLI (read-only).
- **Hardening — cognition Mock routing**: `test_cognition_runtime.py` now
  routes via Mock Provider (`ModelRouter.route → None` scoped to `send()`),
  eliminating the Ollama 404.
- **Hardening — SQLite INTEGER clamp**: understanding `frequency` /
  `observed_count` binds saturated at `2**63 - 1`, eliminating the
  `OverflowError` from unbounded counter accumulation.

### Guided Self-Improvement Evolution Thread (Stage A1→H) — COMPLETE

A lettered, additive post-core thread built on the existing evolution
pipeline. Each stage is deterministic, advisory, and fail-soft; none of it
weakens the existing governance boundaries. Reconstructed from source, tests,
and git history (`534da54..6676566`):

| Stage | Capability | Key implementation / tests |
|---|---|---|
| **A1** | Repository self-knowledge map | `atlas/research/repository_map.py`, `test_repository_map.py`, `test_repository_map_kernel.py`, `test_decision_repository_context.py` |
| **B** | Evolution intelligence from development records | `atlas/evolution/intelligence_engine.py`, `test_development_intelligence_feedback.py` |
| **C** | Impact-aware development planning (advisory) | `atlas/evolution/development_planner.py`, `test_impact_aware_development_planning.py` |
| **D** | Context-aware development intelligence | `atlas/evolution/development_planner.py`, `test_development_context_intelligence.py` |
| **E** | Promotion gate foundation | `atlas/evolution/promotion_gate.py`, `test_promotion_gate.py` |
| **F** | Research → development intelligence bridge | `atlas/research/evidence_summary.py`, `test_research_evidence_summary.py`, `test_stage_f_bridge.py` |
| **G** | Decision-quality scoring (advisory) | `atlas/evolution/decision_quality.py`, `test_decision_quality.py`, `test_decision_quality_planning.py` |
| **H** | Promotion-review visibility (pending + detail) | `atlas/evolution/promotion_gate.py`, `atlas/kernel/atlas.py`, `atlas/cli/promotion_commands.py`, `atlas/cli/main.py`, `test_promotion_review_visibility.py`, `test_promotion_cli.py` |

**Stage H promotion-review subsystem (current state):**

- `PromotionGate` is a deterministic risk assessor plus a bounded
  `PENDING_REVIEW → APPROVED / REJECTED` review-request lifecycle. APPROVED
  means *ready for human/operator promotion* — it never mutates the repository.
  `PROMOTED` is reserved for out-of-scope operator tooling.
- The kernel bridge `Atlas.submit_development_for_promotion_review()` opens
  `PENDING_REVIEW` audit rows carrying bounded change evidence; it never
  approves, rejects, promotes, or executes.
- Read-only operator surface: `Atlas.pending_promotion_reviews()` (prioritized
  queue) and `Atlas.promotion_review_details(request_id)` (single-review
  detail), exposed via `atlas promotion pending` and
  `atlas promotion show <request_id>` (presentation-only).
- No approve/reject/promote/execute path is exposed through the CLI; the
  human-approval boundary remains the only advancement channel.

### Conversational Development Intake (B1+B2+B3) — COMPLETE

A three-batch, additive post-core milestone committed together at `ce12fb8`
(branch `phase5-memory-evolution`). It connects casual conversational
development requests to the EXISTING governed development-cycle preparation
flow without adding a subsystem, governance surface, storage, schema, or
execution mechanism:

- **B1 — README/config reconciliation:** `README.md` brought to the
  post-core state (schema v11, 4,291-test inventory, post-core memory
  thread) and `config.toml` version aligned to `0.20.0`.
- **B2 — Deterministic conversational task intake**
  (`atlas/conversation/task_intake.py`): pure `TaskIntake` → bounded
  `TaskSpec` (task type, intent, goal, constraints, priorities, success
  criteria, ambiguity, needs_clarification, provenance). Optional model
  assistance is an injectable `IntentParser`, OFF by default, output
  untrusted. The conversation seam propagates the structured goal and
  `metadata["task"]`; `task_intake=None` preserves legacy behavior.
- **B3 — Conversational development bridge**
  (`atlas/conversation/development_intake.py` + `ConversationService`
  `development_bridge` + kernel wiring): a pure `TaskSpec → DevelopmentNeed`
  adapter with clarification gating, routing `DEVELOPMENT_REQUEST` through
  the existing `Atlas.run_development_cycle()` (F9) and STOPPING at
  `PENDING_APPROVAL`. Nothing is approved, executed, or promoted by the
  bridge; `Atlas.tick()`, the RuntimeCoordinator 15-stage order, and all
  locked packages remain untouched.
- Tests: `tests/test_conversation_task_intake.py`,
  `tests/test_conversation_development_intake.py`,
  `tests/test_conversation_development_bridge.py`, plus
  `tests/test_conversation_service.py` additions.
- **B4 remains undefined and unapproved** — see NEXT below.

### Track C Post-Core Follow-Ups (COMPLETE)

The recorded Track C follow-ups are complete, in three verified batches
(schema remains **v11** throughout — no new migrations):

- **Persistent Learning** (`5bfa615`) — reusable `LearningInsight` objects
  persist via the existing `SQLiteEvolutionStorage` (additive migration v11,
  `learning_insights` table) and restore into `LearningMemory` on startup;
  storage failures degrade gracefully to memory-only. See
  `docs/ATLAS_STATE.md` §28.
- **Deterministic Semantic Recall** (`57f0063`) — pure `SemanticRecallEngine`
  (`atlas/longterm/semantic_recall.py`) ranks stored episodes and procedures
  by deterministic token overlap (tags 3.0 / name·title 2.0 / tool 2.0 /
  category·kind·outcome 1.5 / summary·description 1.0, × coverage
  multiplier), bounded (hard cap 500), sorted by `(-score, type, id)`, fully
  explained (matched tokens/fields), and provenance-preserving (complete
  `to_dict()` payloads). Registered additively as the read-only
  `memory.semantic_query` capability and exposed via
  `atlas memory search <query> [--limit N]`. No new storage, no retrieval
  subsystem, no AI/LLM involvement.
- **Forgetting-Policy Operationalization** (`be2bb84`) — the existing
  `MemoryDecayPolicy` defaults are now operational (episodes inactive > 90
  days, procedures unused > 180 days; `min_importance` 0.1 unchanged), and
  every forget flag carries deterministic reason metadata
  (`metadata["flags"]`). Consolidation flags remain advisory PENDING records
  through GOV-010 — no applier exists and nothing deletes memory.

Full suite verified at each batch: **4,285 tests** (semantic recall) and
**4,296 tests** (forgetting policy), **0 failed** (pytest exit 0).

---

## CURRENT — Foundation Strengthening

**Atlas Core is COMPLETE.** v0.20.0 is released at tag `v0.20.0` (`b92c5d9`).
Development has transitioned from numbered phases to continuous
foundation-strengthening tracks.

**Foundation Strengthening — completed batches:**

- **Batch 1** — Kernel composition-root decomposition: `Atlas.start()` decomposed
  into 7 private domain helpers (see `docs/ATLAS_STATE.md` §5.1 and §24).
- **Batch 2** — Scaffold & legacy cleanup: removed 30 files of genuinely
  unused/unwired scaffolding (`atlas/agents/`, `atlas/automation/`,
  `atlas/interfaces/`, plus 3 unused files from `atlas/events/`,
  `atlas/runtime/`, `atlas/scheduler/`).

Full suite after each batch: **3260 passed, 0 failed, 57 subtests, 2 warnings**
(identical to v0.20.0 release gate).

There is **NO Phase 23 for Atlas Core**. The next development model is
**post-core guided self-improvement** with
`SELF_CONFIG`/`INFORMATION` as the enabled governed scopes and
`CODE_ARTIFACT`/`SANDBOXED`/`AUTONOMOUS` remaining locked (see
`docs/ATLAS_STATE.md` §22.4).

---

## Post-Core Development

Atlas Core is complete (Phase 22, v0.20.0). Development now follows the
post-core milestone sequence below. Each milestone is locked until the
preceding milestone is accepted. M2–M7 scope is defined by acceptance
contract, not by premature implementation.

### M0 — GitHub Synchronization
**STATUS: COMPLETE**

Local and remote histories are synchronized at a verified checkpoint with a
clean working tree.

### M1 — Roadmap Reconciliation
**STATUS: COMPLETE**

Reconciled the original P1–P7 core plan, the authoritative forward roadmap
(`ROADMAP.md`), the current-state handbook (`ATLAS_STATE.md`), and the actual
implementation into one official post-core direction.

- M1.1 roadmap investigation completed.
- M1.2 P1–P7 implementation reconciliation completed and independently verified.
- M1.3 findings classified (blockers / strengthen / debt / future / closed).
- M1.4 official post-core roadmap (M0–M7) established.
- M1.5 final state and git-consistency verification passed.
- Commit: `53b198b`.
- M2 — Execution Integrity became the next active milestone.

### M2 — Execution Integrity
**STATUS: COMPLETE**

F1 resolved: the broken `Task.run()` path reachable from `Atlas.tick()` is fixed
by a minimal lifecycle-only implementation. A terminal Task (COMPLETED / FAILED /
CANCELLED) is left untouched; a non-terminal Task transitions RUNNING then FAILED
with the deterministic reason `"Task has no executable payload"` rather than
falsely claiming success. No external work, no tool/capability dispatch, no new
execution architecture, and no authority bypass are introduced. A due Task passes
safely through `Worker.execute()` and `Scheduler.tick()` without crashing the
runtime loop.

- M2.1 investigation completed.
- M2.2 execution contract defined (lifecycle-only, honest failure).
- M2.3 F1 implementation completed.
- M2.4 regression/baseline verification completed.
- M2.4 verdict: `M2.4 PASS — F1 VERIFIED`.
- The six known datetime failures in `atlas/understanding/consolidation/concept_consolidator.py:119`
  remain deferred under F17 and are not M2 regressions.
- M3 — Tool Governance remains LOCKED as the next milestone.

### M3 — Tool Governance
**STATUS: COMPLETE**

Established the tool-execution governance invariant without modifying
`ToolExecutor` or `ToolEngine`.

**M3.1 — Investigation.** Tool governance was investigated across ToolRegistry,
ToolSelector, ToolExecutor, ToolEngine, OrchestrationExecutor, AuthorityService,
SessionContext, and P7.6 development authorization. F2 was confirmed as an
important architectural concern (a structural bypass exists via ToolEngine) rather
than an active privileged bypass, since privileged development operations already
route through governed boundaries.

**M3.2 — Contract.** The approved architectural decision was **caller-owned
governance**: privileged tool execution must pass through the canonical governed
boundary — `SessionContext` → authoritative identity/session validation →
`AuthorityService` → `OrchestrationExecutor._authorize()` → `ToolExecutor` →
handler. P7.6 privileged development actions retain their existing kernel
authorization boundary. `ToolExecutor` and `ToolEngine` are intentionally not
governance boundaries.

**M3.3 — Implementation.** Added explicit governance regression/invariant tests
without modifying `ToolExecutor` or `ToolEngine`. Commit: `977d06e`.

**M3.4 — Verification.** Independent verification confirmed: canonical tool
execution is authorized before dispatch; unauthorized execution fails closed;
`ToolExecutor` remains caller-trusting; `ToolEngine` remains advisory in current
production usage; no privileged bypass was found; P7.6 authorization remains
intact; M2 execution integrity remains intact. Full suite: 4918 passed, 0
failures. F3 and F17 remain deferred.

### M4 — Self-Development Hardening
**STATUS: COMPLETE**

Hardened the existing P7 self-development pipeline without redesigning it.

**M4.1 — Investigation.** The full conversational self-development lifecycle was
mapped and verified against actual code: detection → dialogue → confirmation →
F9 bridge → DRAFT → PENDING_APPROVAL → OWNER approval → APPROVED →
DevelopmentPlanner → CodeSandbox IMPLEMENT → pytest VERIFY →
DevelopmentOutcome/LearningInsight → PENDING_REVIEW. Every trust boundary
(SessionContext → SessionManager → AuthorityService → OWNER) was verified.
No production privileged bypass or sandbox escape was found.

**M4.2 — Safety invariants regression-tested.** Added 25 focused regression
tests pinning three invariants: (A) failed/partial development outcomes remain
explicitly FAILED in learning and are never recorded as successful/trusted; (B)
approval replay is rejected — a consumed approval cannot be re-applied; (C)
sandbox path confinement rejects parent traversal, absolute paths, Windows drive
prefixes, dot segments, and symlink escapes. No production behavior was changed.

**M4.3 — Sandbox environment boundary.** The M4.1 concern that sandboxed
execution might inherit the full Atlas process environment was found to be
already mitigated in production: ``sandbox_tools._spawn`` passes
``_controlled_env()`` — a minimal, allow-listed environment — to every child
subprocess. Credential-bearing keys (KEY/SECRET/PASSWORD/TOKEN/CREDENTIAL/
AUTHORIZATION/PRIVATE) are explicitly excluded. ``shell=False`` and fixed
command lists are used. No production change was made; 5 regression tests pin
this contract.

**M4.4 — Independent verification.** All M4 invariants pass; M2/M3 regressions
remain green; relevant P7 regression: 385 passed. Full suite: 4948 passed,
0 failures.

M5 — Governance Assurance remains LOCKED as the next milestone.

**Acceptance:** a development proposal moves through the existing governed
lifecycle and produces a durable, reviewable, verifiable result suitable for
an approved promotion/application path.

> Do NOT replace P7. Do NOT weaken OWNER approval. Do NOT remove sandboxing.
> Do NOT make autonomous repository modification unrestricted.

### M5 — Governance Assurance
**STATUS: COMPLETE**

Focused assurance pass over privileged operations after M2–M4.

**M5.1 — Investigation.** The complete privileged surface was inventoried:
AuthorityService, SessionManager, SessionContext, OrchestrationExecutor,
P7.6 privileged kernel methods, PromotionGate, ToolExecutor, ToolEngine,
CognitionService, GoalExecutionEngine, and collective governance. The
authoritative identity/authority chain (SessionContext → AuthorityService →
canonical governed boundary → low-level execution primitive) was verified.
No current privileged bypass was found.

**M5.2 — Regression Hardening.** Added governance assurance tests
(`tests/test_governance_assurance_m5.py`, 14 tests): the
CognitionService→ToolEngine advisory boundary is covered (ToolEngine remains a
governance-free primitive; governance is caller-owned per M3), and
cross-session identity integrity is covered (identity resolved authoritatively
through SessionManager + AuthorityService). Test-only change; no production
behavior was modified.

**M5.3 — Independent Verification.** An independent audit re-classified every
production execution route (all GOVERNED, ADVISORY, or LOW-LEVEL PRIMITIVE —
no privileged bypass), reproduced the full suite (4962 passed, 0 failures),
and confirmed M5.2's test-only scope. Verdict: M5.3 PASS.

**Final M5 result.** Governance assurance is complete. No production
architecture changes were required. The M3 caller-owned governance decision is
preserved: ToolEngine/ToolExecutor remain low-level primitives, and privileged
operations route through canonical governed boundaries (OrchestrationExecutor
per-step authorization, P7.6 kernel authority, gateway + authorization for
goals).

Accepted/deferred items:
- GoalExecutionEngine authorization unification → M6 / F3
- Workspace CRUD authority model → Future Queue
- Tool privilege metadata → Future Queue
- Worker-level failure isolation → Future Queue
- approval TTL/persistence → Future Queue
- F17 datetime policy → deferred hardening item
- concurrency → Future Queue

### M6 — Canonical Execution Architecture
**STATUS: LOCKED**

Document and enforce the final execution architecture before major capability
expansion.

Address **F3**: canonical execution ownership must be clarified and enforced.

Map each execution system (OrchestrationExecutor, Tool execution,
Task/Scheduler, GoalExecutionEngine, EvolutionScheduler,
DevelopmentCycleController, SelfDevelopmentLoop, and any others discovered
during M2–M5) for: ownership, responsibility, entry point, caller,
canonical/supporting/specialized/legacy status, governance boundary, and
relationship to other execution systems.

**Acceptance:** a future Atlas module has one obvious, documented, governed
integration path for each kind of execution.

> Do NOT blindly merge execution systems. Specialized systems may remain
> specialized when justified.

### F17 — Datetime Policy
**STATUS: LOCKED (hardening item, performed within M2–M5 as appropriate)**

Normalize internal timestamps to UTC-aware datetimes and eliminate naive/aware
mixing.

**Acceptance:** no production path mixes naive and UTC-aware timestamps; relevant
serialization/comparison tests pass.

### M7 — Capability Expansion
**STATUS: LOCKED (scope deliberately flexible)**

Only after M2–M6 are complete should Atlas substantially expand capabilities.
Potential areas: workspace capabilities, stronger planning, richer autonomous
operation, advanced capability modules, future Atlas-built modules. Detailed
scope is not locked until M2–M6 are accepted.

---

## Future Queue (explicitly deferred)

The following are deferred and must not silently become M2–M6 scope:

- Registry consolidation
- Legacy cognition cleanup
- Workspace filesystem facade
- Structured logging
- SQLite architecture cleanup
- Python 3.11 test portability cleanup
- Async/concurrency work
- Plugin SDK
- Web/API server
- Distributed execution

---

## NEXT

The next milestone is **M2 — Execution Integrity** (see Post-Core Development
above). The recorded Track C follow-ups (Persistent Learning, deterministic
semantic recall, forgetting-policy tuning) are COMPLETE. No further task carries
an approved design beyond the locked post-core sequence.

Deferred / owner-gated items (unchanged):

- **Episodic context surfacing** — feed long-term episodic memory into the
  RuntimeCoordinator pipeline. **Deferred** pending a RuntimeCoordinator review
  (locked pipeline order).

**No next Stage (e.g. Stage I) is defined.** The Stage A1→H self-improvement
thread is complete at Stage H. Any further promotion-review capability would
touch the human-approval/governance boundary and therefore requires an
explicit, owner-approved design before it may be implemented.

---

## PLANNED

There are **no PLANNED numbered phases** for Atlas Core. Phase 22 was the final
numbered implementation phase. Future foundational changes — pipeline
restructuring, new governance levels, or enabling CODE scope — require a
separate owner-approved design and are post-core evolution work, not an
automatic Phase 23.

### Permanent Architectural Directive — Model Independence & Information Autonomy

A permanent architectural boundary (see `docs/ATLAS_STATE.md` §26) governs all
future post-Core work, including F7–F11:

- **SELF → DIRECT SOURCES → MODEL ASSISTANCE.** Atlas prefers (1) existing
  verified knowledge/memory, (2) its own deterministic tools/algorithms/
  reasoning, (3) direct retrieval from external information sources, and only
  then (4) AI-model assistance — and only when the above cannot resolve the
  need.
- **No single point of failure.** No AI model/provider/family/API/framework/
  external service may become a permanent dependency. AI models are replaceable
  assistants, not permanent authorities or sources of truth.
- **Model-derived information is not automatically durable knowledge.** Claims
  must be traced to evidence, independently verified, associated with
  provenance and retrieval/verification timestamps, assigned confidence, and
  stored via the existing knowledge/provenance architecture. Preserve the
  underlying evidence so model obsolescence cannot invalidate durable knowledge.
- **Resource independence.** Independence is the primary goal (not cost). Model
  usage is necessity-, capability-, risk-, and budget-aware, and replaceable.
- **Permanent design principles.** "Never optimize Atlas for permanence of
  implementation; optimize Atlas for permanence of purpose and adaptability of
  implementation." / "Atlas should not need to know everything. It should know
  how to discover, understand, evaluate, remember, retrieve, and use what it
  needs." / "Atlas should prefer discovering information directly over
  receiving knowledge from an AI model." / "No AI model should become a single
  point of failure." / "AI models are replaceable assistants, not permanent
  authorities."

### Post-Core Continuation (F7–F11) — **COMPLETE**

The planned post-Core continuation, preserving the committed F1–F6 (not renamed
or reordered), has been delivered in full. The inspect-before-build rule
("inspect the existing Atlas infrastructure — scheduler, events, task manager,
runtime — and reuse what already exists rather than rebuilding") was honored
for every phase:

- **F7 — Autonomous Operation** — **COMPLETE** (`abd6856`)
- **F8 — Autonomous Research & Knowledge Acquisition** — **COMPLETE** (`abd6856`)
- **F9 — Governed Autonomous Development** — **COMPLETE** (`08b5596`)
- **F10 — Resource Independence & Model-Optional Intelligence** (includes the
  model-independence / resource-independence principles above) — **COMPLETE**
  (`9352948`)
- **F11 — Long-Term Self-Management & Recovery** — **COMPLETE** (`e620177`)

**The F-series concludes at F11. It is COMPLETE; no F12 exists or is planned.**
Any future development track requires an explicitly written scope before
implementation begins (inspect-before-build remains in force).

---

## DEFERRED — Agreed But Postponed

- **RESOLVED:** the governed `ReasoningIngestSink` runtime wiring deferred from
  Track D Batch 2 has since been completed — `_init_evolution_pipeline()` now
  injects the kernel-owned governed sink into the research, longterm, AND
  advanced-reasoning bridges, so `reasoning.ingest` flows through the Phase 16
  schedule-store/dispatcher queue under GOV-011 instead of failing closed.
- `ContextEngine` episodic-context integration (Track C) is deferred pending a
  RuntimeCoordinator review, because it could touch the locked pipeline order.
- Autonomous (CODE scope / AUTONOMOUS level) evolution remains unreachable by
  constitutional design.
- **BootActivation re-verification semantics — owner decision pending.** On a
  second boot, an already-activated staged-config entry whose session overlay
  marker was lost fails read-back verification and its originating request
  transitions COMPLETED → FAILED without a SAFE_MODE escalation. Existing
  Phase 16.7 behavior surfaced by the F11 wiring; implementation unchanged
  pending an owner ruling on D11 semantics.

---

## DEPENDENCIES

- Every state mutation depends on the **Evolution Framework** (gateway +
  sole-owner dispatcher). No capability bypasses governance.
- New persistence must be **additive** via `atlas/storage/migration.py`
  (currently schema **v11**).
- Adding a capability handler or component requires following the
  `CapabilityRegistry` factory + `ComponentMetadata` patterns.
- Track-private services stay **outside** the ServiceContainer
  (kernel-private, constructor-injected).
- Pure logic layers must never gain infrastructure imports (import-boundary
  invariant).

---

## PROPOSED — Not Approved (Do Not Implement)

The broader Capability Track roadmap references further tracks. **These are
PROPOSED only and have no approved architecture:**

| Label | Direction (as referenced in existing roadmap) | Status |
|---|---|---|
| E | Multi-Agent Collaboration | PROPOSED |
| F | Human Collaboration | PROPOSED |
| G | Self-Improvement | PROPOSED |

No Track E/F/G module, design, or milestone exists in source. They must not be
implemented, and must not be presented as committed direction, until an approved
design exists and this document is updated.

---

## Roadmap Maintenance Rule

When a major implementation milestone is completed:

1. Update `docs/ATLAS_STATE.md` (current state becomes reality)
2. Update `docs/ROADMAP.md` (move the item to COMPLETED, set the next CURRENT)
3. Update `README.md` if the public status changed

Never archive/delete without moving to `docs/archive/`, and never treat archived
documents as current.

---

*Authoritative re-write: 2026-08-08 (post-Track-D, schema v11, ahead of
v0.19.1). Core milestone update: 2026-08-14 (Phase 22 COMPLETE — Atlas Core
complete; post-core guided self-improvement; no Phase 23). Release update:
2026-08-16 (v0.20.0 released at b92c5d9; 3260 passed, 0 failed, 57 subtests,
2 non-blocking warnings). Foundation Strengthening: Batch 1 (kernel
decomposition) and Batch 2 (scaffold cleanup) completed. Track C post-core
follow-ups reconciled: 2026-08-28 (Persistent Learning 5bfa615, deterministic
semantic recall 57f0063, forgetting-policy operationalization be2bb84; schema
v11; no implementation NEXT currently defined). Conversational Development
Intake (B1+B2+B3) reconciled: 2026-08-29 (committed ce12fb8; schema v11;
B4 remains undefined/unapproved; no implementation NEXT currently defined).
Project Atlas — docs/ROADMAP.md.*
