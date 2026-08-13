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
| **C** | Long-Term Learning | Complete & runtime-integrated (`v0.19.1`) — `atlas/longterm/`, migration v9, `memory.*`, GOV-010, CLI |

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
- ResearchIngestBridge remains governed and fail-closed (no sink wired); no
  direct KnowledgeManager injection.
- Tests: `tests/test_phase21_research_coordinator.py`,
  `tests/test_phase21_research_feedback.py`. Commits: `7d86a6b`, `fee0e32`.
- Full suite at acceptance gate: **3070 passed, 57 subtests, 1 failed** — the
  single failure is the pre-existing Ollama-dependency
  `test_cognition_runtime.py::test_full_cognition_conversation_flow`
  (localhost:11434 unavailable), reproduced on the pre-Phase-21 baseline.

---

## CURRENT — Active Work

**Post-Track-D implementation.** Track D was released as `v0.20`. The active
focus is the completed-but-unreleased first NEXT implementation item and its
remaining follow-ups:

- **Track A — research coordinator implementation** is implemented (Phase 21)
  and pending release together with the next milestone. It is not yet tagged.
- The next primed tasks are the already-recorded Track A/B/C follow-ups listed
  under NEXT below.
- Keep `README.md`, `docs/ATLAS_STATE.md`, and `docs/ROADMAP.md` synchronized.

> The governed `ReasoningIngestSink` is a **pending/deferred dependency** — **not**
> an actively approved implementation task. Do not treat it as one; see DEFERRED
> below. `reasoning.ingest` is expected to remain fail-closed until that dependency
> is resolved.

---

## NEXT — Immediate Next Work

Based on the existing repository already recording these deferred follow-ups:

- **Track A** follow-ups: knowledge-graph expansion, web source adapter
- **Track B** follow-ups: skill authoring, PARALLEL / CONDITIONAL tool-chain
  execution, learned-skill promotion
- **Track C** follow-ups: feeding episodic context into working memory /
  `ContextEngine` (requires RuntimeCoordinator review before scheduling),
  semantic-memory upgrades, forgetting-policy tuning

These are the concrete, already-recorded next items. They are not new inventions.

---

## PLANNED

There are no additional **PLANNED** (approved-design) items beyond the deferred
Track A/B/C follow-ups listed under NEXT. Any new capability must first receive
an approved design and be added to this document before implementation.

---

## DEFERRED — Agreed But Postponed

- **Runtime wiring of the governed `ReasoningIngestSink` is deferred.** It
  depends on the Phase 16 schedule-store/dispatcher queue hand-off being
  finalized in the kernel, and was intentionally deferred from Track D Batch 2.
  Until that dependency is resolved, `reasoning.ingest` remains **fail-closed**
  by design.
- `ContextEngine` episodic-context integration (Track C) is deferred pending a
  RuntimeCoordinator review, because it could touch the locked pipeline order.
- Autonomous (CODE scope / AUTONOMOUS level) evolution remains unreachable by
  constitutional design.

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
v0.19.1). Project Atlas — docs/ROADMAP.md.*
