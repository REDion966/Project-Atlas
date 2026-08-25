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

## NEXT — Foundation Strengthening / Post-Core Work

The immediate next foundation-strengthening focus:

- **Governed ingest sink resolution** — wire the governed `ReasoningIngestSink`
  (and corresponding Track A/B/C ingest bridges) so that governed evolution
  can feed distilled insights back into Atlas state.
- **Episodic context surfacing** — feed long-term episodic memory into the
  RuntimeCoordinator pipeline so stored experiences influence current processing.

Remaining already-recorded Track A/C follow-ups (zero required for core
completion):

- **Track A** follow-ups: knowledge-graph expansion, web source adapter
- **Track C** follow-ups: semantic-memory upgrades, forgetting-policy tuning

These are not new inventions. The next implementation focus should be governed
ingest sink resolution (see `docs/ATLAS_STATE.md` §19, §24).

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
  (currently schema **v10**).
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

*Authoritative re-write: 2026-08-08 (post-Track-D, schema v10, ahead of
v0.19.1). Core milestone update: 2026-08-14 (Phase 22 COMPLETE — Atlas Core
complete; post-core guided self-improvement; no Phase 23). Release update:
2026-08-16 (v0.20.0 released at b92c5d9; 3260 passed, 0 failed, 57 subtests,
2 non-blocking warnings). Foundation Strengthening: Batch 1 (kernel
decomposition) and Batch 2 (scaffold cleanup) completed. Project Atlas —
docs/ROADMAP.md.*
