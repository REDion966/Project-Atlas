# ATLAS STATE — Authoritative Current Architecture Handbook

**Canonical entry point for all future Atlas development.**

This document is the single source of truth for the **current** state of the
Project Atlas codebase. Future implementation prompts should say: *"Read
ATLAS_STATE.md and only the files directly related to the task."*

---

## 0. Source of Truth & Document Authority

This section defines the **single documentation authority model** for Project
Atlas. No other document may define a competing hierarchy.

| Level | Owner | Scope |
|---|---|---|
| **0** | Repository state — source code, tests, Git history, executable behavior | Actual runtime truth |
| **1** | `docs/ATLAS_STATE.md` *(this file)* | Authoritative current state |
| **2** | `docs/ROADMAP.md` | Authoritative future direction |
| **3** | `docs/ATLAS_CORE.md` | Permanent architectural principles |
| **4** | `docs/ATLAS_VISION.md` | Identity and purpose |
| **5** | `docs/adr/` — architectural decision records | Decision records and procedural guidance (§21 holds the agent/development rules) |
| **6** | `README.md` | Public entry point — orientation only; never a second source of truth |
| **7** | `CHANGELOG.md`, `docs/archive/` (phase designs, handoffs, and prior roadmap/workflow copies), evidence reports | Historical record — never current operational authority |

Rules:

- **Level 0 wins.** If source code and any document conflict, source code wins.
  Report the conflict and preserve backward compatibility; never silently choose
  one over the other.
- **This file (Level 1) is the authoritative documentation of current state** —
  current architecture, invariants, governance, verified test baseline,
  completed milestones, and the current evidence boundary.
- **`ROADMAP.md` (Level 2)** is authoritative for authorized future direction
  only; it does not restate current architecture.
- **`ATLAS_CORE.md` (Level 3)** owns permanent principles only; it defers
  current-state facts to this file and future direction to `ROADMAP.md`.
- **`ATLAS_VISION.md` (Level 4)** owns identity and purpose only.
- **`README.md` (Level 6)** is an entry point. It must not outrank this file and
  must not become a second source of truth.
- A document may preserve historical claims without those claims becoming
  current guidance.

> **Rule for future AI agents:** archived documents (`docs/archive/`) and the
> Phase-C evidence reports describe how Atlas looked at earlier points in time.
> They are historical context, not current architecture. Do not reintroduce
> archived designs without an explicit new decision.

**Documentation map (the entire active surface):**

| Document | Purpose |
|---|---|
| `README.md` | Public orientation: what Atlas is, status, entry points |
| `docs/ATLAS_STATE.md` *(this file)* | Authoritative current state (architecture, modules, governance, development lifecycle, verification, limitations, roadmap status) |
| `docs/ROADMAP.md` | Authoritative forward direction (Phase 1–5 complete; no Phase 6/L11+) |
| `docs/ATLAS_CORE.md` | Permanent architectural principles |
| `docs/ATLAS_VISION.md` | Identity and purpose |
| `docs/adr/` | Architectural decision records |
| `CHANGELOG.md`, `docs/archive/` | Historical record only |

Everything else (phase designs, handoffs, prior roadmap/workflow copies,
investigations) lives under `docs/archive/` and is historical.

---

## 1. Current Project Identity

Project Atlas is a long-term, Python-based, modular **AI operating framework** —
not a chatbot, not a model wrapper, not a demo. Atlas coordinates memory,
knowledge, reasoning, planning, learning, tools, and AI providers into a unified
system that grows more capable over time while remaining under human ownership.

> **Core identity:** AI models are tools. Atlas is the intelligence. Models may
> change. Atlas remains.

The system is modular, AI-independent, and event-driven. Layers are
module-owner and constructor-injected; the Evolution Framework is the only
mechanism by which Atlas may change its own operational state.

---

## 2. Current Release & Version State

| Field | Value |
|---|---|
| Released baseline | **v0.20.0** (stable; Atlas Core complete; tag `v0.20.0` at `b92c5d9`) |
| Current state | **Post-Roadmap Operational State** — Phase C evidence-driven evolution (C0 → C9) at its established evidence boundary (§31), extended by the additive **Phase 1 → Phase 5 direct-evolution program** (§32) |
| Direct-evolution program | **Phase 1–5 COMPLETE** — Phase 3 knowledge acquisition & research (deterministic source selection + verifier correction); Phase 4 governed self-development (4.2/4.3); Phase 5 direct Atlas evolution (5.2 IMPLEMENTED; 5.3 VALIDATED with G1 capability activation closed) — see §32 |
| Target-state gates | **G1 COMPLETE · G2 COMPLETE · G3 COMPLETE (Governed Self-Development)** — owner-scoped, additive gates on top of the frozen roadmap and the direct-evolution program; deterministic-first, model-independent, no new engine/planner/router/store/authority — see §33. **No G4 is defined or authorized.** |
| Post-L10 evidence-driven step arc | **Step 1 → Step 7 COMPLETE** — open-ended conversation; goal-centered orchestration; evidence → self-development; continuous self-improvement validation; natural-language understanding; intent & goal understanding (bounded multi-intent handling); context & reference understanding (existing references preserved, unresolved earlier-item references represented instead of guessed) — all additive, model-independent, OWNER-gated, sandbox-verified, fail-closed, with **no new engine/planner/scheduler/store/authority** — see §34.10, §34.11, §34.12 and §34.13. **The next step (Step 8) is NOT STARTED**: development stays evidence-driven and separately authorized. |
| Completed roadmap | Historical Core (Phase A → P18) + Phase C (C0 → C9); C5.2 NOT AUTHORIZED; C8 CLOSED with no evidence-backed gap; C9 READINESS COMPLETE with no evidence-backed gap |
| Track D release | **Released in v0.20** (tag `v0.20` exists in git history) |
| Current schema version | **11** |
| Intelligence level | Level 5 — Persistent Self-Model (Level 6+ Bounded Autonomy via Phase 16) |
| Verified test baseline | **5,945 test items executed: 5,876 test cases passed (plus 67 subtests passed), 0 failed, 0 errors, 2 skipped** (pytest exit 0) |
| Era | **Post-Roadmap Operational Era** (supersedes the Capability Track Era) |

**CURRENT IMPLEMENTATION:** Atlas v0.20.0 is released at tag `v0.20.0`
(`b92c5d9`). Foundation Strengthening Batch 1 (kernel composition-root
decomposition) and Batch 2 (scaffold/legacy cleanup) have been completed, and
the additive Stage A1→H self-improvement/promotion-review thread (repository
self-knowledge map, development intelligence, impact/context-aware planning,
promotion gate, research→development bridge, decision-quality scoring, and
promotion-review visibility) is complete — see §27. The Track C post-core
follow-ups — Persistent Learning (`5bfa615`), deterministic semantic recall
(`57f0063`), and forgetting-policy operationalization (`be2bb84`) — are also
complete; the schema remains **v11** (see §28–§29).

---

## 3. Final Numbered Core Milestone (Phase 22)

**Phase 22 — Toolchain Execution & Learned-Skill Progression** is the FINAL
numbered core milestone for Atlas Core (the current project state is the
post-roadmap Phase-C operational state — see §2 and §31). Phase 22 completed
the recorded Track B NEXT items — CONDITIONAL execution, PARALLEL
execution (deterministic sequential fan-out/fan-in; no actual concurrency), and
learned-skill authoring/promotion (governed via GOV-009, in-memory candidates,
fail-closed without a sink) — and closed integration & acceptance. With Phase 22
accepted, **Atlas Core is COMPLETE**: the next development model is post-core
guided self-improvement (see §22.4). There is NO Phase 23.

**Phase 21 — Track A research coordinator** (complete, bundled with the Phase
22 milestone — not released/tagged) implements the first already-recorded NEXT
item from the roadmap: the concrete `ConcreteResearchCoordinator`, its
plan-reachable `research.coordinate` capability, and the research-output
feedback loop into the existing Phase 20 outcome → ReflectionEngine →
LearningEngine boundary. Validation state is recorded in §3.5 and §22.

### Track Status Summary

| Track | Capability | Status | Baseline |
|---|---|---|---|
| **A** | Research & Knowledge | **COMPLETE** | `v0.17.0` (Phase 17) |
| **B** | Tool Ecosystem | **COMPLETE** | `v0.18.0` (Phase 18) |
| **C** | Long-Term Learning | **COMPLETE & runtime-integrated** | `v0.19.1` (Phase 19) |
| **D** | Advanced Reasoning | **RELEASED (`v0.20`)** — implemented & runtime-integrated | `v0.20` |

### 3.1 Track A — Research & Knowledge (COMPLETE)
`atlas/research/` — research models, local source adapters (document/workspace/
codebase), deterministic planner, knowledge extractor, claim verifier,
`research_*` tables (migration v7), `research.query/verify/summarize` capability
handlers, governed KNOWLEDGE ingest (**GOV-008**), `atlas research` CLI.

### 3.2 Track B — Tool Ecosystem (COMPLETE)
`atlas/toolchain/` — toolchain models + catalog, skill registry, deterministic
tool-chain planner, safe executor + risk policy, effectiveness tracker, tool
learner, `toolchain_*` tables (migration v8), `toolchain.*` capability handlers,
governed skill-activation ingest (**GOV-009**), `atlas toolchain` / `atlas skill`
CLI.

### 3.3 Track C — Long-Term Learning (COMPLETE, runtime-integrated, v0.19.1)
`atlas/longterm/` — episodic recorder, procedure extractor, consolidator
(dedup/merge/principled forgetting), episodic/procedural repositories,
`LongTermSQLiteStorage` (`episodic_*`/`procedural_*`/`memory_consolidation_records`,
migration v9), `memory.*` capability handlers, governed LONGTERM_INGEST
(**GOV-010**), `atlas memory` CLI, and kernel wiring inside `Atlas.start()`.
Post-core follow-ups — Persistent Learning (§28), deterministic semantic
recall, and forgetting-policy operationalization (§29) — are complete.

### 3.4 Track D — Advanced Reasoning (IMPLEMENTED & runtime-integrated)
See §18–§20 for the full architecture description.

### 3.5 Phase 21 — Track A Research Coordinator (COMPLETE, bundled with Phase 22)
`atlas/research/coordinator.py` — `ConcreteResearchCoordinator`, the first
concrete implementation of the legacy `ResearchCoordinator` ABC
(`atlas/evolution/research_coordinator.py`). It composes the existing Track A
components (ResearchPlanner, KnowledgeExtractor, ClaimVerifier,
ResearchSQLiteStorage, governed ResearchIngestBridge) via constructor
injection — no duplicates, no new subsystems.

- **Plan reachability:** `research.coordinate` is registered additively by the
  kernel and reached through a plan step via the existing
  `CapabilityRegistry → CapabilityRouter → CapabilityDispatcher` path in the
  PLANNING stage. REASONING remains candidate-only.
- **Feedback loop:** the research ExecutionResult lands in `PLANNING.results`,
  is recorded as a normal `ReasoningOutcome`, and flows through the existing
  ReflectionEngine → LearningEngine → capability-keyed `StrategyPerformance` →
  later CapabilityAnalyzer selection boundary (Phase 20 architecture reused;
  no research-specific learning subsystem).
- **Governance:** ResearchIngestBridge routes through the kernel-owned
  governed sink (GOV-008); research results are never injected directly into
  KnowledgeManager.
- **Tests:** `tests/test_phase21_research_coordinator.py`,
  `tests/test_phase21_research_feedback.py`.
- **Commits:** `7d86a6b` (coordinator + reachability), `fee0e32` (feedback loop).

---

## 4. Current Architecture

Atlas is a clean, layered, modular system. Layer rules:

```
CLI / Presentation
        ↓
     Services          ← coordinate
        ↓
 Managers / Engines    ← contain domain logic
        ↓
   Repositories        ← data access
        ↓
     Storage           ← low-level persistence
```

- Each layer communicates only with adjacent layers
- Business logic must never access storage directly
- Circular dependencies are prohibited
- Models are plain data (`@dataclass`, often `frozen=True, slots=True`) with no
  business logic beyond serialization
- Pure logic layers never import infrastructure

**ARCHITECTURAL INVARIANT** — pure-logic layers (reasoning, cognition,
understanding, goals, experience, learning models/engines) contain no AI calls,
no memory/knowledge access, no EventBus, no service imports, and no `sqlite3`.

## 5. Kernel & Runtime Architecture

### 5.1 Kernel — Composition Boundary
`atlas/kernel/atlas.py` (`Atlas`) is the root application object and **the only
place where the whole system is wired**. `Atlas.start()` constructs every
service and runtime dependency and injects them via constructor — there is no
internal instantiation of services. Track-specific private dependencies are
built in the kernel and held as private attributes — **not** registered in the
container (see §6).

As of post-v0.20.0 Foundation Strengthening (Batch 1), `start()` delegates to
7 private domain helpers called in dependency order:

1. `_init_ai_provider()` — config, model routing, AI manager
2. `_init_memory_knowledge()` — memory, knowledge, legacy intelligence, learning
3. `_init_reasoning_pipeline()` — capability registry, Track A/B factories,
   LearningEngine, reasoning engine, tools
4. `_init_cognitive_engines()` — understanding, world model, identity, goals,
   experience, self-model, feedback
5. `_init_tracks()` — evolution storage + Tracks A–D infrastructure
6. `_init_evolution_pipeline()` — evolution intelligence, knowledge, governance,
   gateway
7. `_init_runtime_services()` — RuntimeCoordinator, scheduler, goal execution,
   cognition service, conversation, component registry, container

The helpers are private; the composition-root semantics are unchanged.

### 5.2 RuntimeCoordinator
`atlas/runtime/runtime_coordinator.py` is the single permanent orchestrator of
the 15-stage cognitive pipeline:

```
Conversation Context → Memory Retrieval → Knowledge Retrieval → Understanding →
World Model → Reasoning → Planning → Tool Decision → Tool Execution → AI Response →
Reflection → Learning → Evolution Observation → Goal Intelligence → Memory Storage
```

The stage order is **locked**. A `runtime.pipeline.completed` event is published
on the EventBus at the end of `process()`.

**ARCHITECTURAL INVARIANT:** the RuntimeCoordinator stage order is fixed.
Track D **did not modify** RuntimeCoordinator; it consumes
`runtime.pipeline.completed` additively via a kernel-owned trace recorder (§20).

## 6. ServiceContainer & Dependency Injection

`ServiceContainer` (registered key → instance) registers **public shared
services**. Everything is constructed in `Atlas.start()` and constructor-injected.

Representative public service keys: `ai` (`AIService`), `conversation`,
`memory`, `knowledge`, `cognition_service`, `cognition_api`,
`runtime_coordinator`, `understanding`, `world_model`, `evolution_observer`,
`learning_engine`, `identity`, `feedback_coordinator`, `goal_repository`,
`goal_intelligence`, `experience_repository`, `experience_accumulator`,
`self_model_engine`, `intelligence_engine`, `execution_gateway`, etc. (see the
service keys actually registered in `Atlas.start()`).

**DI rules:**
- All cross-module edges are constructor-injected; domain logic never uses a
  service locator
- No component may import the container to fetch a dependency at runtime
- Track-private services (e.g. Track C longterm, Track D
  `AdvancedReasoningService`) are **NOT** in the ServiceContainer

> **CURRENT IMPLEMENTATION:** `AdvancedReasoningService` is a **kernel-private**
> dependency. It is composed directly in the kernel and verified by
> `test_kernel_advanced_reasoning_integration.py` to be absent from the
> container (`assertNotIn("advanced_reasoning", container._services)`).

## 7. Storage Architecture

- All SQLite adapters live in `atlas/storage/` and are the **only** modules that
  import `sqlite3`
- Additive migrations are defined in `atlas/storage/migration.py`; applied in
  ascending version order inside a transaction; **no destructive migrations**
- Each track adds its own `*_*` table families additively:
  - v7 `research_*` (Track A)
  - v8 `toolchain_*` (Track B)
  - v9 `episodic_*` / `procedural_*` / `memory_consolidation_records` (Track C)
  - v10 `reasoning_*` (Track D)
- Storage exposes a read protocol; prototypes (e.g.
  `AdvancedReasoningStorage`) define the surface, adapters implement it
- **Database files are runtime artifacts.** They live in `atlas_data/`
  (e.g. `atlas_experience.db`) and `data/`, are gitignored, and are not source.

## 8. Current Schema Version

**`CURRENT_SCHEMA_VERSION = 11`** (`atlas/storage/migration.py`).

This is confirmed by source and by the migration tests
(`test_evolution_autonomy_storage`, `test_evolution_persistence`,
`test_experience_storage`, `test_longterm_storage`,
`test_understanding_storage`), which assert schema version **11** after the
Track D additive `reasoning_*` tables and the Persistent Learning
`learning_insights` table. The deterministic-semantic-recall and
forgetting-policy batches added no migrations; the schema remains **11**.

## 9. Capability Architecture

Capabilities are exposed through the reasoning `CapabilityRegistry` via the
`CapabilityHandler = Callable[[dict], ExecutionResult]` contract. Each track
provides a capability **factory** that registers its handlers additively:

- Track A: `research.query / verify / summarize`
- Track B: `toolchain.*`
- Track C: `memory.*`
- Track D: `reasoning.trace / causal / counterfactual / hypotheses / verify /
  meta / ingest` (from `AdvancedReasoningCapabilityFactory`)

Handlers are **pure bridges**: they delegate to an injected composed service;
they never mutate state, never import the kernel/container, and never touch
`sqlite3`.

> **COMPONENT METADATA / WIRING:** each track also registers observational
> `ComponentMetadata` with the lifecycle `ComponentRegistry`. Track D registers
> `advanced_reasoning` and `advanced_reasoning_evolution` (GOV-011) via
> `atlas/advanced_reasoning/wiring.py` (`register_advanced_reasoning_component`,
> `register_advanced_reasoning_evolution_component`). Registration is additive.

## 10. CLI Architecture

`atlas/cli/` implements a subcommand-style CLI. Track CLIs are added
additively. Track D adds `atlas reasoning` with actions: `trace`, `causal`,
`counterfactual`, `hypotheses`, `verify`, `meta`, `ingest` (see
`atlas/advanced_reasoning/cli_commands.py`).

Other current subcommands include: `workspace`, `project`, `resource`,
`permission`, `member`, `tag`, `research` (A), `toolchain` / `skill` (B),
`memory` (C), `evolution`, `goal`, `proposals` (post-core F8, read-only).

## 11. Governance / Evolution Framework Boundaries

The **Evolution Framework** (`atlas/evolution/`) is the only channel by which
Atlas may change its own operational state. `EvolutionExecutionGateway` is the
single execution choke point; the `EvolutionAutonomyDispatcher` is the sole
caller of `execute_request()`.

- **Execution levels:** `ADMINISTRATIVE` (0), `SELF_CONFIG` (1), `INFORMATION`
  (2), `CODE_ARTIFACT` (3, unreachable), `SANDBOXED` (4, locked), `AUTONOMOUS`
  (5, locked)
- **Scope types:** `CONFIG`, `MEMORY`, `KNOWLEDGE`, `CODE`, `IDENTITY`,
  `CAPABILITY`, `UNKNOWN` (never executes)
- **Six gates** (Phase 16): RuleEngine, Validator, RiskAssessor,
  AuthorizationManager, dispatcher pre-check, gateway translation — all fail
  closed
- **Constitutional invariants:** identity and code are untouchable; a request
  can never alter the AutonomyPolicy, ConstraintRegistry, or gateway level

### Governance rules (additive)
| Rule | Scope | Requirement |
|---|---|---|
| GOV-001 | IDENTITY | AUTONOMOUS (unreachable) |
| GOV-002 | CODE | CODE_ARTIFACT (unreachable) |
| GOV-003 | CONFIG | SELF_CONFIG |
| GOV-004 | MEMORY / KNOWLEDGE | INFORMATION |
| GOV-008 | KNOWLEDGE (RESEARCH_INGEST) | INFORMATION — Track A |
| GOV-009 | KNOWLEDGE (TOOLCHAIN_INGEST) | INFORMATION — Track B |
| GOV-010 | MEMORY (LONGTERM_INGEST) | INFORMATION — Track C |
| **GOV-011** | KNOWLEDGE (REASONING_INGEST) | INFORMATION — **Track D** (additive) |

**ARCHITECTURAL INVARIANT:** GOV-011 is additive — no constitutional change, no
gateway redesign. Track D never calls `EvolutionExecutionGateway.execute_request()`
directly; the kernel wires a governed ingest sink (`ReasoningIngestSink`
protocol) into the bridge.

> **PROPOSED (not implemented):** GOV-006 (`SKILLS`, reserved) and GOV-007
> (autonomy-envelope membership, policy-enforced in `AuthorizationManager`) are
> referenced by design only; they are not additive registrations present in the
> current registry beyond design notes.

## 12. Advanced Reasoning Architecture (Track D)

`atlas/advanced_reasoning/` implements Track D. It is a **separate package**
that consumes, but does not modify, the core `atlas/reasoning/` package.

Components:

- **`multi_step.py`** — `MultiStepReasoner`: deterministic decomposition of an
  input into chained, dependency-ordered inference steps; confidence propagates
  forward through the chain; produces immutable `ReasoningTrace`s
- **`causal.py`** — `CausalReasoner`: causal path analysis and counterfactual
  ("what-if") evaluation built on a `CausalGraphProvider` protocol
- **`hypotheses.py`** — `HypothesisGenerator`: generates and deterministically
  ranks competing hypotheses for an observation/claim
- **`verify.py`** — `SelfVerifier`: step-level premise/support/contradiction/
  circularity checks; produces `VerificationReport`s
- **`meta.py`** — `MetaReasoningEngine`: strategy effectiveness scoring over
  reasoning trace history (read-only recommendations)
- **`models.py`** — immutable `@dataclass` reasoning artifacts and enums
- **`protocols.py`** — `ReasoningModel` / `VerificationModel` / `HypothesisModel`
  / `EvidenceProvider` / `CausalGraphProvider` (optional, protocol-injected
  large-model enhancement; not required)
- **`trace_recorder.py`** — `ReasoningTraceRecorder`: bounded in-memory surface
  (duck-types the existing `ReasoningRecorder`), additively subscribed by the
  kernel to `runtime.pipeline.completed`
- **`trace_repository.py`** — `ReasoningTraceRepository`: in-memory + storage
  dual-write repository
- **`capability_handlers.py`** — `AdvancedReasoningCapabilityFactory`: pure
  bridge handlers for `reasoning.*`
- **`cli_commands.py`** — `atlas reasoning` CLI actions
- **`storage_protocol.py`** — `AdvancedReasoningStorage` persistence protocol
- **`evolution_integration.py`** — `ReasoningEvolutionTracker` +
  `ReasoningIngestBridge` + `register_gov_011`
- **`service.py`** — `AdvancedReasoningService`: constructor-injected
  composition root owning the engines, repository, and ingest bridge
- **`wiring.py`** — Track D `ComponentMetadata` + registration helpers

**ARCHITECTURAL INVARIANT — pure module:** reasoning itself is pure
computation. Only `atlas/storage/advanced_reasoning_storage.py` imports
`sqlite3`; no Track D pure module imports kernel, runtime, dispatcher, gateway,
AI providers, EventBus, scheduler, storage adapters, or `atlas.reasoning`
internals beyond stable public models.

## 13. Advanced Reasoning Persistence

- Adapter: `atlas/storage/advanced_reasoning_storage.py`
  (`AdvancedReasoningSQLiteStorage`) — the **only** Track D module importing
  `sqlite3`
- Implements the `AdvancedReasoningStorage` protocol (idempotent upserts for
  traces; append-only logs for steps; fail-closed when unavailable)
- Adds `reasoning_*` tables via the shared migration framework — the Track-D
  migration step brought the schema to **version 10** (the current schema is
  **version 11**; see §8)
- Opens the shared `atlas_data/atlas_experience.db`; `initialize()` applies
  additive migrations; no existing table is altered or dropped
- `ReasoningTraceRepository` dual-writes to storage and keeps an in-memory
  working set

## 14. Advanced Reasoning Runtime Integration

Verified in `test_kernel_advanced_reasoning_integration.py` and the kernel
(`atlas/kernel/atlas.py`, Track D block):

1. `AdvancedReasoningSQLiteStorage` initialized and injected
2. `ReasoningTraceRepository` built over storage; `restore()` called
3. `ReasoningIngestBridge` constructed (sink via `ReasoningIngestSink` protocol)
4. `AdvancedReasoningService` constructed (private, kernel-owned) — **NOT**
   registered in the ServiceContainer
5. Provider adapters built in-kernel: `KnowledgeEvidenceProvider` wraps
   `KnowledgeManager`; `WorldModelCausalGraphProvider` wraps `WorldModelEngine`
   (neither registered in the container)
6. `ReasoningTraceRecorder` subscribed by the kernel to
   `runtime.pipeline.completed` (additive; RuntimeCoordinator unchanged)
7. `AdvancedReasoningCapabilityFactory.register(...)` adds `reasoning.*` handlers
8. `register_gov_011(...)` adds GOV-011 additively alongside GOV-008/009/010
9. `register_advanced_reasoning_component` /
   `register_advanced_reasoning_evolution_component` add ComponentMetadata

Shutdown explicitly clears `_advanced_reasoning_*` state and closes storage.

## 15. Current Test / Verification State

> **Precision rule:** Only an actually-executed number may be stated as a test
> result. A collected/inventory count is not a passing test count.

**CURRENT VERIFIED BASELINE — the only current test result:**

```
5,945 test items executed: 5,876 test cases passed (plus 67 subtests passed)
0 failed
0 errors
2 skipped
```

This is the authoritative current baseline (pytest exit 0). Every other number
in this section is a **historical** execution record for the milestone named
beside it; none of them is the current baseline.

**Historical — Track D Batch 2 execution** (decision-gate result, ~9 minutes):

```
2973 passed
57 subtests passed
0 failed
0 errors
```

**Historical — post-core release gate (HEAD `b2b4674`, v0.20.0 preparation):**

```
3260 passed
57 subtests passed
0 failed
2 warnings (non-blocking asyncio.iscoroutinefunction deprecations)
```

**Historical — Phase 1 repository inventory (not a result):** 178 test files,
766 test classes, 2958 test methods (+ parameterized subtests). Superseded — the
current suite contains 300 test files; this inventory is not the current
baseline.

Track D test coverage includes: storage, CLI, capability handlers, service,
trace recorder, repositories, causal/hypotheses/verify/meta engines, models,
protocols, wiring, evolution integration, import-boundary scans, and
kernel integration.

**Historical — Track C post-core follow-up executions:** deterministic semantic
recall batch (`57f0063`) — full suite 4,285 tests, 0 failed (pytest exit 0);
forgetting-policy batch (`be2bb84`) — full suite 4,296 tests, 0 failed
(pytest exit 0).

## 16. Architectural Invariants

- **CURRENT IMPLEMENTATION** vs **ARCHITECTURAL INVARIANT** vs **DEFERRED** vs
  **PROPOSED** are distinguished throughout this document; proposals are never
  presented as implementation.
- The RuntimeCoordinator stage order is fixed (Track D did not modify it).
- Track-private services are never added to the ServiceContainer.
- Pure logic never imports infrastructure; only `atlas/storage/` adapters import
  `sqlite3`.
- All cross-module edges are constructor-injected.
- All state mutation goes through the Evolution Framework; the gateway is the
  only execution entry point and the dispatcher its sole caller.
- All changes are additive; no destructive migrations; no redesign of locked
  packages.
- Systems fail closed: missing governance, validation, or sink ⇒ refusal with a
  meaningful error, never silent success.

## 17. Protected / Locked Components

Do **not** redesign these; extend additively only:

- `atlas/kernel/` — root application + ServiceContainer wiring
- `atlas/runtime/` — RuntimeCoordinator (15-stage order)
- `atlas/reasoning/` — core reasoning (controller, capabilities, planning,
  reflection); Track D may *consume* public models/outputs additively
- `atlas/cognition/`, `atlas/ai/` — no Track D pipeline/provider changes
- `atlas/memory/`, `atlas/knowledge/`, `atlas/understanding/`,
  `atlas/world_model/`, `atlas/learning_engine/`, `atlas/goals/`,
  `atlas/experience/`, `atlas/identity/`
- `atlas/evolution/` — Evolution Framework (governance, autonomy, gateway,
  dispatcher); GOV-011 is only additive rule registration
- `atlas/storage/` migration framework (additive migrations only)
- `atlas/intelligence/` — **LEGACY**, preserved, never modified

## 18. Import Boundaries (prohibited dependencies)

Pure-logic layers (`atlas/reasoning/**`, `atlas/advanced_reasoning/**`,
`atlas/cognition/**`, evolution pure logic, etc.) **must never import**:

- `atlas/kernel/`
- `atlas/runtime/` (RuntimeCoordinator)
- `atlas/evolution/autonomy/dispatcher.py` (only `Atlas.tick()` calls it)
- `atlas/evolution/execution_gateway.py` (autonomy never imports it)
- `atlas/ai/providers/` (only `AIManager` and the router touch providers)
- `atlas/events/` (EventBus)
- `atlas/storage/` adapters (storage modules own `sqlite3`)
- `atlas/evolution/scheduler.py`

Additionally, `atlas/evolution/autonomy/**` never imports the gateway, kernel,
services, ai, or EventBus. These boundaries are enforced by import-boundary
tests (e.g. `test_advanced_reasoning_import_scan.py`).

## 19. Deferred Functionality (DEFERRED)

- **RESOLVED (post-Core F-series):** `reasoning.ingest` governed ingestion is
  now wired at runtime. `_init_evolution_pipeline()` injects the kernel-owned
  governed sink into the research, longterm, AND advanced-reasoning bridges,
  so distilled reasoning insights flow through the Phase 16
  schedule-store/dispatcher queue under GOV-011. Reasoning artifacts are
  persisted regardless; nothing remains deferred on this path.
- Track A deferred follow-ups: knowledge-graph expansion.
  (The research coordinator — formerly a deferred Track A item — is complete
  as Phase 21; the web source adapter was delivered by post-Core F8.)
- Track B deferred follow-ups are **complete** as Phase 22 (skill authoring/
  promotion, CONDITIONAL and PARALLEL execution). No Track B deferred items
  remain.
- Track C deferred follow-ups: feeding episodic context into working memory /
  `ContextEngine` (requires RuntimeCoordinator review).
  (The remaining Track C follow-ups — deterministic semantic recall and
  forgetting-policy tuning — are complete; see §29.)
- Phase 16: boot activation of staged config + SAFE_MODE rollback are part of
  the governed-autonomy design but remain governed-path behavior; CODE scope is
  unreachable by constitutional design.
- **F4 (scheduler double-tick) is DEFERRED/MONITORED**: the EvolutionScheduler's
  shared tick counter, new-observations gate, and reentrancy guard prevent
  duplicate analysis; revisit only if duplicate proposal IDs/content or
  duplicate mutation execution is observed.
- **F6 (persistence degradation) is EXPECTED BEHAVIOR**: SQLite evolution
  storage intentionally degrades to memory-only; `evolution.storage.unavailable`
  is emitted.

## 20. Current Known Limitations

- CODE scope (`CODE_ARTIFACT`, `AUTONOMOUS` levels) is **unreachable** — Atlas
  does not autonomously modify source code or its identity.
- No distributed / multi-process execution (single-process assumption).
- No autonomous reflection/strategy adjustment without approval.
- Large-model enhancement in Track D is optional and protocol-injected; the
  deterministic engine is the primary mechanism.
- **BootActivation re-verification semantics (owner decision pending).** On a
  second boot, an already-activated staged-config entry whose session overlay
  marker was lost fails read-back verification and its originating request is
  transitioned COMPLETED → FAILED without a SAFE_MODE escalation. This is
  existing Phase 16.7 behavior surfaced by the F11 boot-recovery wiring; the
  implementation is unchanged pending an owner ruling on D11 semantics.
- `docs/archive/releases/CHANGELOG.md` is not maintained past the early
  releases; git history is the authoritative change log for later work; the
  active release notes live in the root `CHANGELOG.md` (created at v0.20.0).

## 21. Rules Future AI Agents MUST Follow

1. **Read this file first.** Do not perform repository-wide analysis. Read
   `ATLAS_STATE.md`, then read only the modules directly related to the task
   (verify service keys, models, and conventions above and in source).
2. **Read before writing.** Touching an existing module requires reading it
   first to learn its interface, exports, and patterns. Never guess signatures
   or import paths.
3. **Never redesign Atlas.** Kernel, Core Services, Memory, Workspace,
   Evolution, and Governance are locked. Build additively on top of them.
4. **Preserve backward compatibility.** Existing public APIs and service keys
   must not break without explicit review. `atlas/intelligence/` is never
   modified.
5. **Preserve architecture.** Follow the layer rules (§4) and
   prohibited-dependency rules (§18).
6. **Follow dependency direction.** Pure logic never imports infrastructure;
   storage adapters own all `sqlite3`; all cross-module edges are
   constructor-injected.
7. **Register new capabilities.** New handlers → `CapabilityRegistry`
   (`DEFAULT_HANDLERS`/factory pattern). New components → `ComponentMetadata`
   + container key only if shared. New storage tables → additive via
   `atlas/storage/migration.py`.
8. **Route every mutation through the Evolution Framework.** Never write Atlas
   state directly. Track-private services are not added to the ServiceContainer.
9. **Fail closed.** Missing dependency, governance, or sink ⇒ refusal with a
   meaningful error and audit record.
10. **Test first.** Write tests alongside implementation; run the full suite
    before finishing; fix failures, never hide them.
11. **One focused change at a time.** Prefer new files over edits; do not modify
    unrelated code.
12. **Record changes.** When a major milestone completes, update
    `ATLAS_STATE.md`, then `ROADMAP.md`, then `README.md` if the public status
    changed. Never treat archived docs as current architecture.

## 22. Phase 22 — Toolchain Execution & Learned-Skill Progression (COMPLETE)

Status: **COMPLETE — FINAL numbered implementation phase for Atlas Core.**
The (now historical) specification is `docs/archive/PHASE_22_DESIGN.md`.

### 22.1 Scope delivered (additively in `atlas/toolchain/`)

- **CONDITIONAL execution** — deterministic selection of later steps from
  prior step output via the existing `ToolStep.depends_on` seam.
- **PARALLEL execution** — deterministic sequential fan-out/fan-in. NO actual
  concurrency: the executor's "No threading. No async. No subprocess." promise
  is preserved as an invariant (design §5).
- **Learned-skill authoring/promotion** — a pure authoring surface over the
  existing `ToolLearner` output; promotion (status change / registry mutation /
  persistence of an activated skill) remains governed through
  `ToolchainIngestBridge` / GOV-009 and fails closed without a sink.

### 22.2 Batches (each landed green)

1 = CONDITIONAL execution (`0926ea2`)
2 = PARALLEL execution (`7fa81f3`)
3 = skill authoring/promotion
4 = integration + acceptance (final: `f501367`)

### 22.3 Completion record

- Batches 1–4 implemented and accepted. Batch 3 (authoring/promotion) and
  Batch 4 (integration) are included in the closing commit `f501367`.
- Non-goals honored: no second planner/router/dispatcher; no RuntimeCoordinator
  redesign; no ModelRouter changes; no Phase 16 revival; no Track C
  memory/context work; no actual OS-level concurrency. All Phase 20/21
  invariants listed in design §9 remain intact and verified.
- Full suite at acceptance: 3169 passed, 57 subtests, 1 failed (pre-existing
  Ollama environmental failure at `localhost:11434`); phase-specific and
  regression suites all green.
- Resolved owner decisions (recorded 2026-08-13): (1) Phase 21 is bundled with
  the Phase 22 milestone — no separate Phase 21 tag; (2) learned-skill
  promotion candidates stay in-memory for Phase 22 — no additive migration;
  (3) CONDITIONAL uses a small deterministic predicate vocabulary.

### 22.4 Post-Core Guided Self-Improvement (the next development model)

**Atlas Core is COMPLETE at Phase 22.** Future development is NOT a numbered
Phase 23; it operates through the repository's existing governed self-
improvement mechanisms in a continuous loop:

```
Observe/record → analyze/plan → propose → approve → execute governed changes
→ verify → repeat
```

- **Enabled governed scopes:** `SELF_CONFIG` (1) and `INFORMATION` (2) remain
  the only executable governed scopes; `CODE_ARTIFACT` (3), `SANDBOXED` (4),
  and `AUTONOMOUS` (5) remain locked/unreachable (constitutional design).
- **Human approval:** explicit owner approval remains required wherever the
  existing governance requires it; no fail-closed boundary is bypassed.
- **Code changes:** may initially be produced as reviewable artifacts/patches
  rather than autonomously applied. Autonomous CODE mutation is not enabled.
- **Stopping rule:** "Atlas Core is DONE. We stop adding foundational
  architecture." Further foundational changes — pipeline restructuring, new
  governance levels, or enabling CODE scope — require a separate owner-approved
  design and are post-core evolution work, not an automatic Phase 23.

## 23. Post-Core Completion Record (v0.20.0)

Post-core guided self-improvement delivered F1–F8 plus two hardening fixes.
All are included in the v0.20.0 release at tag `v0.20.0` (`b92c5d9`).

- **F1 — Runtime observation coverage**: five observation categories per
  runtime cycle (`atlas/evolution/runtime_observations.py`).
- **F2 — Planner observation aggregation**: weakness detectors average the
  relevant metric over the bounded per-category window instead of only the
  newest observation (`ImprovementPlanner._mean_value`).
- **F3 — SUBSUMED by F8**: proposal list/show/audit visibility makes a
  separate audit item unnecessary.
- **F4 — DEFERRED/MONITORED**: the EvolutionScheduler's shared tick counter +
  new-observations gate + reentrancy guard prevent duplicate analysis; no
  defect demonstrated, so no change was made.
- **F5 — Scheduler fail-soft diagnostics**: `EvolutionSchedulerResult.last_error`
  surfaces the most recent integration error while fail-soft semantics stay
  byte-identical.
- **F6 — EXPECTED BEHAVIOR**: SQLite evolution storage's memory-only fallback
  is the documented degraded mode; `evolution.storage.unavailable` is emitted.
- **F7 — Closed learning feedback loop**: deterministic failure EvolutionRecords
  → insight → planner feedback.
- **F8 — Evolution audit/proposal visibility**: `get_proposal_audit()` +
  `atlas proposals list|show|audit` CLI (read-only).
- **Hardening — cognition Mock routing**: the cognition runtime test now routes
  via Mock Provider (the `ModelRouter.route → None` patch is scoped to
  `send()`), eliminating the Ollama 404.
- **Hardening — SQLite INTEGER clamp**: understanding `frequency` /
  `observed_count` binds are saturated at `2**63 - 1`, eliminating the
  `OverflowError` from unbounded counter accumulation.

**Final release verification:** full suite **3260 passed, 0 failed, 57
subtests, 2 warnings** (the 2 warnings are non-blocking
`asyncio.iscoroutinefunction` deprecations in `test_phase21_research_coordinator.py`).

**Governance statement (unchanged, reasserted):** autonomous code mutation
remains disabled. `SELF_CONFIG` (1) and `INFORMATION` (2) remain the enabled
governed scopes; `CODE_ARTIFACT` (3), `SANDBOXED` (4), and `AUTONOMOUS` (5)
remain locked/unreachable. No autonomous code mutation exists in the source.

---

## 24. Foundation Strengthening (post-v0.20.0)

After v0.20.0, development transitioned from numbered phases to continuous
foundation-strengthening tracks. Two batches have been completed:

### Batch 1 — Kernel Composition-Root Decomposition
`Atlas.start()` was decomposed into 7 private domain helpers (see §5.1). No
public API, service key, behavioral, or architectural change. 44 kernel tests,
207 integration tests, and 3260 full-suite tests all passed.

### Batch 2 — Scaffold & Legacy Cleanup
Removed 30 files of genuinely unused/unwired scaffolding:

- `atlas/agents/` (27 files) — obsolete multi-agent scaffold never imported by
  the kernel or any active module
- `atlas/automation/` (1 file) — empty `__init__.py` only
- `atlas/interfaces/` (1 file) — empty `__init__.py` only
- `atlas/events/agent_event_bridge.py` — referenced only by deleted `agents/`
- `atlas/runtime/agent_runtime.py` — referenced only by deleted `agents/`
- `atlas/scheduler/agent_scheduler.py` — referenced only by deleted `agents/`

**Retained** (verified as genuinely used): `atlas/scheduler/` (used by
`atlas/task/task_manager.py`) and `atlas/models/ai_response.py` (used by all
AI providers).

The Capability Track roadmap's PROPOSED Track E (Multi-Agent Collaboration) is
preserved as a long-term future direction. The deleted scaffold was an
unwired prototype; any future agent capability must be designed against the
current post-v0.20.0 architecture, not by resurrecting the deleted code.

Full suite after cleanup: **3260 passed, 0 failed, 57 subtests, 2 warnings**
(identical to v0.20.0 release gate).

---

## 25. Post-Core Adaptation Foundation (F1–F6) — COMPLETE

The Post-Core **Adaptation Foundation** adds a bounded, manually-triggered,
deterministic, governance-safe adaptation pipeline on top of the frozen
Core. F1–F6 are additive post-Core layers; Atlas Core remains frozen, Phase E
remains the only governed code-development execution boundary.

| Layer | Purpose | Implementation |
|---|---|---|
| F1 | Environment Foundation | `atlas/evolution/environment/` |
| F2 | Knowledge Freshness & Provenance | `atlas/evolution/freshness/` |
| F3 | Capability / Model / Tool Lifecycle | `atlas/evolution/lifecycle/` |
| F4 | Governed Adaptation Decision Engine | `atlas/evolution/adaptation/engine.py` |
| F5 | Adaptation Evaluation & Feedback | `atlas/evolution/adaptation/evaluator.py` |
| F6 | Full Adaptation Orchestration | `atlas/evolution/adaptation/orchestrator.py` |

### F1 — Environment Foundation
`EnvironmentObserver` observes provider state through duck-typed providers and emits deterministic
`EnvironmentChange` records on the EXISTING EventBus / SelfObservationEngine — no new bus/registry.

### F2 — Knowledge Freshness & Provenance
`KnowledgeFreshnessAssessor` classifies knowledge as FRESH/STALE/UNCERTAIN/UNASSESSED against an
injectable `FreshnessPolicy`, consumes F1 changes deterministically, and emits bounded
`StaleKnowledgeCandidate`s with provenance preserved.

### F3 — Capability / Model / Tool Lifecycle
`CapabilityLifecycleAssessor` converts F1/F2 + lifecycle metadata into deterministic
`LifecycleAssessment` records (NONE / REVIEW / DEPRECATE / REPLACE / FALLBACK). Never mutates registries.

### F4 — Governed Adaptation Decision Engine
`AdaptationDecisionEngine` translates F3 assessments into DRAFT-only `EvolutionProposal`
candidates using the existing proposal model. It never approves; every generated proposal stays `DRAFT`.

### F5 — Adaptation Evaluation & Feedback
`AdaptationEvaluator` evaluates proposal lifecycle states and Phase-E `DevelopmentOutcome`s
(reusing `effectiveness_proxy`), separates governance outcomes from technical outcomes, and emits
bounded `AdaptationFeedback` with F2/F3 bridge signals. May best-effort record into the EXISTING
`EvolutionMemory` / `LearningMemory`; never executes, never approves.

### F6 — Full Adaptation Orchestration
`AdaptationOrchestrator` (plus the kernel bridge `Atlas.run_adaptation_cycle()`)
composes F1→F2→F3→F4 into one bounded, manually-triggered cycle, producing
DRAFT `EvolutionProposal`s and optionally evaluating supplied existing proposal/outcome
pairs via F5. It stops at the DRAFT proposal boundary.

**Guarantees across all layers:**
- Manually triggered and bounded (per-stage caps; deterministic truncation surfaced).
- Deterministic ordering; identical inputs → identical outputs.
- Fail-closed on malformed input (bounded `(stage, message)` failures).
- Provenance survives F1 → F2 → F3 → F4 → governance boundary → Phase E → F5.
- No auto-approval / auto-execution / daemon / `Atlas.tick()` integration.
- No second EventBus / registry / memory / scheduler / approval / authorization / executor / sandbox.
  CODE remains constitutionally protected.
- Phase E remains the governed self-development execution boundary.

Verification: F1–F6 focused tests **177 passed**; architecture/container/governance
regressions **106 passed, 10 subtests passed**; Phase-E E2–E6 **143 passed, 1 skipped**;
four known baseline stale failures remain unchanged by F1–F6.

---

## 26. Permanent Architectural Directive — Model Independence & Information Autonomy

Permanent principle adopted ahead of post-Core work **F7–F11** (recorded at
commit `83b1c0e`, immediately after the F1–F6 Adaptation Foundation). This is an
architectural boundary: every future design, including F7–F11, must honor it.

### 26.1 Model Independence

No particular AI model, provider, model family, API, framework, or external
intelligence service may become a permanent dependency or single point of
failure for Atlas. AI models are **replaceable reasoning, interpretation,
planning, and assistance components** — never permanent authorities or
permanent sources of truth. Atlas must remain useful even if today's AI models
disappear, degrade, or are replaced.

Concretely:

- Model/provider access remains behind the existing replaceable
  `AIProvider` / model-profile abstraction.
- No future design may make a specific model or provider a hard architectural
  dependency.
- Atlas continues operating with degraded or unavailable AI models by relying
  on its own architecture, memory, verified knowledge, deterministic tools,
  direct information sources, capability abstractions, and previously learned
  strategies.

### 26.2 Information-autonomy hierarchy

When Atlas needs information, the preferred order is:

1. **Existing verified Atlas knowledge / memory.**
2. **Atlas's own deterministic capabilities** — tools, algorithms, reasoning.
3. **Direct retrieval from external information sources** — web, APIs,
   documentation, public datasets, local/external files, databases, other
   available information systems.
4. **AI-model assistance** — only when Atlas cannot adequately discover,
   interpret, reason about, or resolve the problem using the above mechanisms.

The model should therefore normally help Atlas **UNDERSTAND** information
rather than become the permanent **OWNER** of that information.

### 26.3 Knowledge rule — model-derived information is not automatically knowledge

Model-generated information must NOT automatically become durable Atlas
knowledge merely because a model produced it. Where appropriate, model-derived
claims must be:

- traced to evidence,
- independently verified,
- associated with provenance,
- associated with retrieval/verification timestamps,
- assigned appropriate confidence,
- stored according to the existing Atlas knowledge/provenance architecture.

Atlas must preserve the underlying evidence and reasoning context so that
future disappearance, replacement, degradation, or obsolescence of today's AI
models does not invalidate Atlas's durable knowledge.

### 26.4 Resource-independence principle

Cost optimization is **not** the primary goal; **independence** is. The desired
hierarchy is **SELF → DIRECT SOURCES → MODEL ASSISTANCE** — never an
unbroken `MODEL → MODEL → MODEL → MODEL` chain. Model usage is
necessity-driven, capability-driven, risk-aware, budget-aware, and replaceable.
Cheap/free model usage is useful but must never become a reason to make Atlas
architecturally dependent on that model. Future resource/model management
optimizes (in priority order): independence, correctness, evidence quality,
reliability, capability, cost — while respecting governance and safety.

### 26.5 Permanent design principles

Add / preserve these principles wherever architecturally appropriate:

1. "Never optimize Atlas for permanence of implementation; optimize Atlas for
   permanence of purpose and adaptability of implementation."
2. "Atlas should not need to know everything. It should know how to discover,
   understand, evaluate, remember, retrieve, and use what it needs."
3. "Atlas should prefer discovering information directly over receiving
   knowledge from an AI model."
4. "No AI model should become a single point of failure for Atlas's knowledge,
   reasoning, or continued existence."
5. "AI models are replaceable assistants, not permanent authorities."

### 26.6 Roadmap position

F1–F6 shown above remain exactly as committed: they are NOT renamed or
reordered. The planned post-Core continuation is:

- **F7 — Autonomous Operation** — **COMPLETE** (`abd6856`)
- **F8 — Autonomous Research & Knowledge Acquisition** — **COMPLETE** (`abd6856`)
- **F9 — Governed Autonomous Development** — **COMPLETE** (`08b5596`)
- **F10 — Resource Independence & Model-Optional Intelligence** (MUST include
  the model-independence / resource-independence principles of this section) —
  **COMPLETE** (`9352948`)
- **F11 — Long-Term Self-Management & Recovery** — **COMPLETE** (`e620177`);
  final F-series implementation phase

**STATUS (post-Core close-out): F7–F11 are COMPLETE.** The inspect-before-build
rule was honored for every phase. **The F-series concludes at F11 — it is
COMPLETE; no F12 exists or is planned.** Any future development track requires
an explicitly written scope before implementation begins.

Before any F7 implementation, future work MUST first inspect the existing
Atlas infrastructure — scheduler, events, task manager, and runtime — and
reuse what already exists rather than rebuilding existing capabilities.

---

## 27. Guided Self-Improvement Evolution Thread (Stage A1→H) — COMPLETE

A lettered, additive post-core thread built on the existing evolution pipeline.
Reconstructed from source, tests, and git history (`534da54..6676566`). Each
stage is deterministic, advisory, and fail-soft; governance boundaries are
preserved throughout.

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

### 27.1 Stage H — Promotion-review subsystem (current state)

- `PromotionGate` is a deterministic risk assessor plus a bounded
  `PENDING_REVIEW → APPROVED / REJECTED` review-request lifecycle. APPROVED
  means *ready for human/operator promotion* — it never mutates the repository.
  `PROMOTED` is reserved for out-of-scope operator tooling.
- Kernel bridge `Atlas.submit_development_for_promotion_review()` opens
  `PENDING_REVIEW` audit rows carrying bounded change evidence (via the existing
  `EvolutionMemory.store_record()` surface). It never approves, rejects,
  promotes, or executes; nothing advances automatically.
- Read-only views: `Atlas.pending_promotion_reviews()` (prioritized
  `PENDING_REVIEW` queue joined with Stage G decision quality) and
  `Atlas.promotion_review_details(request_id)` (single-review bounded detail).
- Operator CLI (presentation-only): `atlas promotion pending` and
  `atlas promotion show <request_id>`. No approve/reject/promote/execute
  subcommand exists; the human-approval boundary remains the only advancement
  channel.

### 27.2 Governed-sink integration alignment (COMPLETE)

The governed `ReasoningIngestSink` runtime wiring (previously listed as
deferred/next) is complete and aligned: `_init_evolution_pipeline()` injects
the kernel-owned governed sink into the research, longterm, and
advanced-reasoning bridges. Integration tests were aligned in
`test_kernel_advanced_reasoning_integration.py`,
`test_kernel_longterm_integration.py`, and `test_phase21_research_feedback.py`
(commit `c23aba9`).

### 27.3 Status of the next task

**No next Stage (e.g. Stage I) is defined.** The Stage A1→H thread is complete
at Stage H. Any further promotion-review capability (for example, an
operator-facing approve/reject decision surface) would touch the
human-approval/governance boundary and requires an **explicit, owner-approved
design** before it may be implemented. Do not infer such a task from the
existing architecture.

---

## 28. Persistent Learning (first post-A1→H capability)

Closes the gap where reusable `LearningInsight` objects (runtime reflection,
self-development outcomes, and other validated conclusions carrying
provenance/confidence) were produced by the `LearningEngine` but lost on
restart (commit `5bfa615`).

- **Storage:** the existing kernel-owned `SQLiteEvolutionStorage` gains
  `store_learning_insight()` / `load_learning_insights()` plus an additive
  migration v11 (`learning_insights` table). No new database, store, or
  retrieval mechanism.
- **Memory:** `LearningMemory` accepts an optional storage adapter; insights
  are dual-written on `store_insights()` and restored via `restore()` /
  `bind_storage()`. Storage failures degrade gracefully to memory-only.
- **Wiring:** `_init_tracks()` binds the evolution storage into the
  `LearningEngine` memory after storage initialization.
- **Quality / governance:** low-quality and transient reasoning is still gated
  by the existing `InsightConsolidator` thresholds; reuse flows through the
  existing `CapabilityAnalyzer` learning-provider path. No governance bypass.
- **Tests:** `tests/test_persistent_learning.py`.

---

## 29. Track C Post-Core Follow-Ups (post-Persistent Learning)

Both remaining recorded Track C follow-ups are complete, additive, verified,
and require no migration — the schema remains **v11**.

### 29.1 Deterministic Semantic Recall (commit `57f0063`)

Closes the retrieval half of the memory story: stored long-term knowledge
(episodes + procedures) becomes deterministically recallable.

- **Engine:** `atlas/longterm/semantic_recall.py` — `SemanticRecallEngine`,
  a pure, read-only ranker over the EXISTING `EpisodicRepository` /
  `ProceduralRepository`. Queries are tokenized into lowercase alphanumeric
  tokens (length ≥ 2); fields are scored with fixed weights (tags 3.0,
  name/title 2.0, tool names 2.0, category/kind/outcome 1.5,
  summary/description 1.0) × a coverage multiplier (distinct matched query
  tokens / total query tokens), rounded to 4 decimals; zero-match items are
  excluded; empty/whitespace queries return no results; results are bounded
  (hard cap 500) and sorted by `(-score, type, id)`.
- **Explainability / provenance:** every result carries
  `{type, score, matched_tokens, matched_fields, item}` where `item` is the
  complete existing `to_dict()` representation of the underlying
  Episode/Procedure. No new provenance infrastructure.
- **Surface:** registered additively as the read-only `memory.semantic_query`
  capability via `LongTermCapabilityFactory` (`query` required and
  fail-closed when missing/blank/non-string; `limit` default 100, capped
  500) and exposed as the presentation-only
  `atlas memory search <query> [--limit N]` CLI. Pure module: no SQLite, no
  kernel, no AI/LLM, no events; repositories and storage are never mutated.
- **Storage:** none added — recall reads in-memory state restored from the
  existing v9 tables; schema remains **v11**.
- **Tests:** `tests/test_longterm_semantic_recall.py` plus handler/wiring/CLI
  updates. Full suite verified: 4,285 tests, 0 failed (pytest exit 0).

### 29.2 Forgetting-Policy Operationalization (commit `be2bb84`)

The existing principled-forgetting machinery was complete and tested but
inert under the shipped default configuration (`*_ttl_days = 0`).

- **Defaults:** `MemoryDecayPolicy` and `catalog` defaults are now
  operational — `episode_ttl_days = 90`, `procedure_ttl_days = 180`
  (`min_importance` 0.1, `max_*` bounds, and `enabled = True` unchanged). The
  kernel-owned default `Consolidator()` therefore emits real, bounded,
  deterministic forgetting candidates.
- **Explainability:** every flagged item carries deterministic metadata
  (`metadata["flags"] = {item_id: {reason, days_inactive, importance}}`;
  reason precedence is "age" over "importance", per the existing flagging
  condition); the public `episodes_flagged`/`procedures_flagged` tuples are
  unchanged.
- **Governance:** consolidation flags remain advisory `PENDING`
  `ConsolidationRecord`s ingested through GOV-010 — **no applier exists and
  nothing deletes, merges, or mutates memory**; repositories and storage are
  untouched by consolidation. The governed payload builder is unchanged.
- **Tests:** `tests/test_longterm_consolidator.py` (plus model/catalog
  default assertions). Full suite verified: 4,296 tests, 0 failed
  (pytest exit 0).

### 29.3 Status of the next task

**No next implementation task is currently defined.** The recorded Track C
follow-ups are complete. The remaining recorded direction (Track A
knowledge-graph expansion) and the deferred episodic-context integration
(require RuntimeCoordinator review) need an explicitly written,
owner-approved scope before implementation begins. **No next Stage (e.g.
Stage I) is defined.**

---

## 30. Conversational Development Intake (B1+B2+B3) — COMPLETE

A three-batch, additive post-core milestone (committed together at
`ce12fb8`) that lets a casual conversational development request flow into
the EXISTING governed development-cycle preparation path. It adds no new
subsystem, governance surface, storage, schema, or execution mechanism; the
RuntimeCoordinator 15-stage order and all locked packages remain untouched.

### B1 — README/config reconciliation

- `README.md` updated to the post-core state (schema v11, 4,291-test
  inventory, post-core memory thread, "no implementation NEXT" roadmap
  summary) and `config.toml` version aligned to `0.20.0`.

### B2 — Deterministic conversational task intake

- `atlas/conversation/task_intake.py` — pure, deterministic-first
  `TaskIntake` producing a bounded, provenance-carrying `TaskSpec`
  (task type, intent, goal, constraints, priorities, success criteria,
  ambiguity, confidence, needs_clarification, source, verified,
  model_metadata). Optional model assistance exists only as an injected
  `IntentParser` protocol; OFF by default, output untrusted and sanitized.
- `ConversationService` runs intake at the conversation seam: the structured
  goal travels as `goal`, the full `TaskSpec` as `metadata["task"]`, and the
  deterministic task type is reflected in the existing model-routing request.
  `task_intake=None` restores the legacy raw-input-as-goal behavior exactly.
- Tests: `tests/test_conversation_task_intake.py` +
  `tests/test_conversation_service.py` additions.

### B3 — Conversational development bridge

- `atlas/conversation/development_intake.py` — pure `TaskSpec →
  DevelopmentNeed` adapter plus clarification gating. DEVELOPMENT_REQUEST
  only; under-specified requests are refused; never fabricates
  `code_changes`/`test_files`.
- `ConversationService` gains an optional duck-typed `development_bridge`
  (no `atlas.evolution` import); DEVELOPMENT_REQUEST routes through it
  exactly once, clarification short-circuits, and a missing bridge preserves
  legacy behavior.
- Kernel wiring: `Atlas._development_bridge` maps `TaskSpec →
  DevelopmentNeed` and calls the EXISTING `Atlas.run_development_cycle()`
  (F9), which submits a bounded DRAFT `EvolutionProposal` to the existing
  `ApprovalManager` and STOPS at `PENDING_APPROVAL`. Nothing is approved,
  executed, or promoted by the bridge.
- Tests: `tests/test_conversation_development_intake.py`,
  `tests/test_conversation_development_bridge.py`.

### Built-in deterministic response path (Phase 1 — non-model boundary)

- `atlas/conversation/builtin_response.py` — pure, deterministic
  `BuiltinResponseService` answering a bounded conversational intent set
  (greeting, help, identity, capabilities, status, unsupported) with no
  external AI provider call. Capabilities/status answers are grounded in the
  injected `ToolRegistry` / `KnowledgeManager` (read-only); nothing is
  invented, mutated, authorized, or executed.
- `ConversationService` consults it after every governed lifecycle handler
  and before orchestration/cognition/AI, in both `send()` and `stream()`.
  It only answers casual turns (`CONVERSATION` / `UNKNOWN` / `QUESTION`,
  never `needs_clarification`); governed turns always return `None` and
  continue through the existing pipeline unchanged. Kernel wires the
  kernel-owned instance (`Atlas.builtin_response`); provider interfaces are
  preserved for optional future augmentation but are not used by this path.
- Tests: `tests/test_builtin_response.py`.
- Phase 2 — built-in by default: normal CLI conversation
  (`ConversationService.send()`/`stream()`, i.e. `Atlas.chat()`/`stream()`)
  is answered by the built-in engine; casual turns never reach a provider,
  so no HTTP request to `localhost:11434` (or any provider) is made for
  greeting/help/identity/status/unsupported turns. The deliberate
  complexity floor that routed ordinary conversation to the configured
  Ollama profile is removed: casual turns (`conversation`/`unknown`/
  `question`) carry baseline 0.3 complexity and ordinary 1-step pipeline
  plans likewise start at 0.3, selecting the no-network tier; deeper plans
  and tool use still escalate. Provider abstraction code is unchanged —
  external providers remain optional integrations for AI-path turns only.
  `config.toml` `[ai]` defaults are intentionally untouched.
- Tests: `tests/test_builtin_default_routing.py` (HTTP-blocked regression +
  no-provider startup + baseline-tier routing).
- Phase 3 — Atlas-owned state answers: the intent set is extended to
  capability listing (tools + reasoning capabilities), named
  capability/tool explanation (registered entries only, otherwise the honest
  unsupported response), status grounded in container/memory/knowledge
  snapshots, deterministic memory/knowledge recall (verbatim keyword lookup;
  honest miss/unwired), and supported commands with safe next steps. New
  collaborators are optional and injected (`CapabilityRegistry`,
  `MemoryManagerService`, service-name snapshot, lifecycle flag); every
  answer distinguishes confirmed state from unavailable/unknown state.
- Tests: `tests/test_builtin_state_answers.py` (realistic fixtures +
  kernel-wiring integration).
- Phase 4 — external providers are explicit opt-in augmentations:
  `config.toml [ai] external_providers` (default `false`) gates all
  external HTTP provider selection. `ModelRouter` excludes external
  profiles without the opt-in, and `AIManager` activates the local
  no-network tier as the active provider — so no `RoutingDecision` can
  silently resolve to an external provider, including on the direct
  (unrouted) provider path. Provider support is intact for explicit
  advanced/augmentation use: with the opt-in on, routing, fallback
  chains, and per-provider calls behave exactly as before. Residual AI-path
  calls carry `conversation_timeout_s` (default 20s) so an opted-in
  provider can never stall ordinary conversation for the full configured
  timeout; any provider failure/timeout/unavailability falls back to the
  built-in engine first (marked `fallback_after_provider_failure`), then
  the legacy deterministic fallback.
- Tests: `tests/test_builtin_optin_providers.py`.

### Status

- **COMPLETE** — committed at `ce12fb8` (10 files, +1898/−24).
- Full suite verified green (pytest exit 0) at the B3 implementation pass;
  the pre-existing `test_cognition_service_new.py` circular-import issue
  reproduces only in isolation and is unrelated to B1–B3.
- **B4 remains undefined and unapproved.** No implementation NEXT is
  currently defined; any future work requires an explicitly written,
  owner-approved scope before implementation begins.

---

## 31. Phase C — Evidence-Driven Evolution (C0 → C9) — COMPLETE

The frozen Phase-C roadmap reached its established evidence boundary. Each
milestone was gated by a read-only evidence investigation (readiness/scope →
contract → implementation → real-world validation → closure); only
capabilities with a validated real-world Category-A gap were built. The
evidence trail is the `C*_*.md` reports in `docs/archive/phase-c/`; Phase C is
recorded as COMPLETE in `docs/ROADMAP.md` and this section.

### Historical Core (COMPLETE)

Phase A — Trustworthy Baseline · P14 — Regression / Contract Closure ·
P15 — Final System Verification · P16 — First Real Atlas Mission ·
P16.5 — Controlled Development Loop · P17 — Real Development System ·
P18 — Controlled Autonomy.

### Phase C status

| Milestone | Scope | Status |
|---|---|---|
| **C0** | Core / Roadmap Freeze | COMPLETE |
| **C1** | Final Readiness Verification | COMPLETE |
| **C2** | Conversational Development Pilot | COMPLETE |
| **C3** | Real-World Capability Evidence | COMPLETE |
| **C4** | Evidence-Driven Capability Evolution | COMPLETE |
| **C5** | Atlas Self-Knowledge / Capability Model | COMPLETE |
| **C6** | Knowledge & Learning Maturity | COMPLETE |
| **C7** | Human Understanding | COMPLETE |
| **C8** | Controlled Autonomy Expansion | CLOSED — NO EVIDENCE-BACKED GAP |
| **C9** | Continuous Atlas Evolution | READINESS COMPLETE — NO EVIDENCE-BACKED GAP |

### Deliveries

- **C1.1** — autonomy-boundary and path hardening; conversation autonomy
  routed through the kernel boundary.
- **C2** — conversational development recovery cycle (fail-closed, truthful
  reporting, sandbox isolation, governed recovery).
- **C3.3** — deterministic investigation synthesis/reporting (GAP-C31-01).
- **C4.2** — deterministic repository impact analysis and conversational
  exposure (`atlas/conversation/repository_impact.py`), reusing
  `RepositoryMap.dependencies_of/dependents_of/impact_set`; full
  investigation → proposal → approval → implementation → verification →
  real-world-validation lifecycle.
- **C5.1** — canonical capability model
  (`atlas/self_knowledge/capability_model.py`): a deterministic, read-only
  projection over the existing registries (classification, attribution,
  health, evidence-based limitations, stable ordering), exposed via a kernel
  accessor and the read-only `atlas capability` CLI. No competing registry.
- **Repository symbol intelligence (external-mechanism adaptation, no new
  subsystem)** — `atlas/research/repository_map.py` additionally extracts each
  module's classes/functions/methods with bounded signatures plus a bounded
  repo-wide reference count used ONLY for relevance ordering, and adds
  deterministic `find_symbol` / `symbols_in_module` / `important_symbols` /
  `context_for` queries. Integrated into `ArchitectureModel.locate` (symbol
  matches), the architecture summary (`symbol_count`), and the kernel
  (`Atlas.repository_symbol`). Deterministic, read-only, model-free; the
  module-level import graph is unchanged.
- **Capability contracts & discovery (external-mechanism adaptation)** —
  `CapabilityModel` entries additionally expose the declared `description`,
  `implementation` module path, and declared tool `inputs` projected from the
  EXISTING `ComponentRegistry`/`ToolRegistry`, plus a deterministic
  `describe_capability` discovery query exposed via `Atlas.capability_contract`.
  Descriptive only: it grants no authority, bypasses no approval/authorization
  boundary, and introduces no second registry.
- **Agent Workbench — bounded governed repair (external-mechanism adaptation)**
  — `atlas/evolution/development_repair.py` adds a drop-in `SelfDevelopmentLoop`
  change supplier. It returns the EXISTING baseline workload unchanged, and —
  only after a sandbox FAILURE and only when `[development].model_assisted_authoring`
  is enabled — authors ONE bounded corrective change through the EXISTING,
  boundary-validated `ModelAssistedChangeSupplier` (path confinement,
  architecture-sensitive-prefix refusal, size/format bounds, fail-closed). It is
  NOT a new loop: the existing loop still applies the change inside a disposable
  `CodeSandbox`, verifies it, and never promotes. Deterministic-first,
  model-optional; mints no authority. The workbench's other primitives (plan,
  implement, sandbox, observe, diagnose, recover, verify, evidence) are the
  existing `DevelopmentPlanner`/`CodeSandbox`/`DevelopmentVerification`/
  `DevelopmentDiagnostic`/`DevelopmentRecovery`/`DevelopmentOutcome` surfaces —
  extended, not duplicated.
- **External repository intelligence (governed GitHub / internet research)** —
  `atlas/research/sources/github.py` acquires a BOUNDED set of files from a
  PUBLIC GitHub repository through GitHub's public API/raw endpoints, reusing
  the EXISTING web safety layer (`WebSourceAdapter` + `WebHostPolicy`:
  deny-by-default, scheme/SSRF/redirect/time/size bounds, path-traversal
  rejection) — no token required, and external code is NEVER executed.
  `atlas/research/external_repository.py` parses the acquired DATA with the
  EXISTING `RepositoryMap` (modules/imports/symbols), ranks relevant symbols
  (`context_for`/importance), and produces a structured Atlas-vs-external
  comparison (`already_supported` / `partially_supported` / `potential_mechanism`
  / `capability_gap` / `architectural_mismatch` / `insufficient_evidence` /
  `not_applicable`) whose findings are ALL `unvalidated` and carry provenance.
  A bounded `development_evidence` dict informs the EXISTING `DevelopmentDriver`
  as EVIDENCE ONLY (never `scaffold`/`code_changes`). Exposed read-only via
  `Atlas.analyze_external_repository(...)` and the
  `external_repository_intelligence` component (capabilities
  `external_repository.acquire/analyze/compare`). Hosts must be explicitly
  allow-listed in `research.web_allowed_hosts` (deny-by-default).
- **Model roles & hardware decision** — Atlas keeps its optional, opt-in model
  roles as background suppliers only: LANGUAGE (`qwen3:8b`), CODING
  (`qwen2.5-coder:7b`), EMBEDDING (`nomic-embed-text`), routed through the
  existing `ModelProfile`/`AIService` seams. Qwen3-Coder-Next (80B MoE / 3B
  active, 256K context) requires ~46–52 GB RAM+VRAM at Q4_K_M and is therefore
  **architecturally relevant but hardware-inappropriate** for the current
  RTX 3060 Ti 8 GB / 32 GB DDR4 host: it is documented and NOT installed, and no
  existing model was replaced. External agent frameworks (Aider, MCP, OpenHands,
  mini-SWE-agent, MiniMax Mini-Agent/Code) are referenced, not embedded.
- **Conversational Self-Knowledge Bridge (bounded language → existing
  self-knowledge)** — Atlas can map bounded natural-language questions about its
  OWN systems onto EXISTING verified knowledge/self-knowledge surfaces:
  natural language → `TaskIntake`/`TaskSpec` → the shared `SemanticFrame`'s
  bounded semantic SUBJECT → self-knowledge topic routing → existing
  capability/architecture/repository/research/development surfaces →
  deterministic, evidence-backed response. It adds NO knowledge database, NO
  second capability registry, NO second repository map and NO model dependency,
  and answers only from existing surfaces / verified anchors. Supported bounded
  subject families (semantic concept classes, so paraphrases converge):
  capabilities; architecture/components; capability contracts;
  repository-symbol intelligence; external repository/research; evidence/trust;
  capability gaps; the governed development lifecycle (ordered: understand →
  inspect/gap → research/evidence → design → sandbox → test → verification →
  promotion request → OWNER authorization → activation → self-knowledge
  refresh); sandbox/verification; governance/OWNER authorization;
  promotion/activation; self-knowledge refresh; model independence. Explaining
  that lifecycle conversationally does NOT execute or authorize it — the
  conversation never bypasses governance. Immediate conversational continuity
  ("What were we just talking about?") resolves from EXISTING structured
  conversation state / prior turns (no new memory subsystem) and stays
  fail-closed when no reliable antecedent exists. Deterministic with
  `ai.external_providers = false`; external models remain optional, untrusted
  interpretation aids with no authority. Verified limitations: the subject
  vocabulary is bounded; context-dependent questions require a reliable
  antecedent; free-form architecture reasoning outside the supported families
  stays unsupported; model-assisted interpretation has not been shown to add
  material benefit for these turns. Evidence: `tests/test_self_knowledge_bridge.py`.
- **C6.1** — validated knowledge retrieval
  (`atlas/research/validated_retrieval.py`): SUPPORTED-only persisted
  research claims (identity, statement, validation status, confidences,
  citations); the legacy `KnowledgeManager`/`KnowledgeBase`/`KnowledgeStore`
  path is behaviorally untouched.
- **C7** — bounded reference/context resolution (GAP-C31-02): word-boundary
  resolver matching + bounded detection, exposed via the existing
  `TaskSpec.context`; AMBIGUOUS → clarification, UNRESOLVED/no-reference
  unchanged.

### Explicit boundary records

- **C5.2 — NOT AUTHORIZED.** Never scoped, approved, or implemented. It is
  not incomplete implementation.
- **C8 — CLOSED — NO EVIDENCE-BACKED GAP.** The controlled-autonomy pilot
  found zero Category-A gaps; the governance chain (intake → approval →
  OWNER execution → sandbox → verification → learning) was verified
  end-to-end with 0 AI calls.
- **C9 — READINESS COMPLETE — NO EVIDENCE-BACKED GAP.** The full evolution
  loop (propose → approve → sandbox → learn) is already operating and
  governed; no additional milestone was authorized.
- **No C10, C9.1, or C5.2 implementation exists or is planned.**

### Current state — POST-ROADMAP OPERATIONAL STATE

The roadmap is complete; Atlas is not "finished forever". Operation follows
the evidence-driven governing loop:

```
USE → OBSERVE → EVIDENCE → INVESTIGATE → PROPOSE → APPROVE → DEVELOP →
VERIFY → LEARN → USE
```

New development originates from validated real-world capability gaps. No new
roadmap milestone may be created without owner-approved, evidence-backed
scope. All architectural invariants (§0 authority model, §16 invariants, §26
model-independence directive) remain in force: deterministic-first operation,
model independence, human approval, governed execution, authorization
boundaries, sandbox verification, fail-closed behavior, evidence-driven
evolution, and controlled self-evolution.

## 32. Direct-Evolution Program (Phase 1 → Phase 5) — reconciled 2026-09-21

An additive, deterministic, model-independent program layered on the completed
Atlas Core (Phase 22 / v0.20.0) and Phase C. It adds no new governance
authority and no parallel storage/registry/planner subsystem, and does not
modify the RuntimeCoordinator 15-stage order, `Atlas.tick()`, or any locked
package. Everything below exists in the current tree and is covered by the
focused suites named.

### 32.1 Phase 1 — Atlas Self-Knowledge (COMPLETE)
- `atlas/self_knowledge/capability_model.py` (`build_capability_model`) and
  `architecture_model.py` (`build_architecture_model`): read-only, deterministic
  projections over the existing `ComponentRegistry`, `CapabilityRegistry`,
  `ToolRegistry`, and the cached `RepositoryMap`.
- Kernel accessors `Atlas.capability_model()` / `Atlas.architecture_model()`;
  read-only CLI `atlas capability` / `atlas architecture`.
- No competing registry; nothing is mutated. (C5.1 delivery — see §31.)

### 32.2 Phase 2 — Natural Language Understanding (COMPLETE)
- Deterministic conversational intake `TaskIntake` → bounded `TaskSpec`
  (`atlas/conversation/task_intake.py`); entity identification; bounded
  reference resolution; `TurnMeaning` boundary projection.
- Built-in deterministic response service
  (`atlas/conversation/builtin_response.py`) answers a bounded casual-intent set
  with no provider call.
- Conversational development intake B1–B3 (§30): casual DEVELOPMENT_REQUEST →
  `DevelopmentNeed` → the existing governed cycle, stopping at
  `PENDING_APPROVAL`.

### 32.3 Phase 3 — Knowledge Acquisition & Research (COMPLETE, lexically bounded)
- Deterministic research pipeline (Track A — §3.1): `ResearchPlanner`,
  document/workspace/codebase adapters, `KnowledgeExtractor`, `ClaimVerifier`,
  `ResearchSQLiteStorage`, governed KNOWLEDGE ingest (GOV-008).
- Deterministic authorized source selection
  (`atlas/research/source_selection.py`): selects only authorized local
  `code://` sources from the cached repository map; it never grants
  authorization and never selects web.
- Bounded lexical canonicalization; validated knowledge retrieval (C6.1).
- Phase 3.3 correction: `ClaimVerifier` contradiction detection is scoped to a
  sentence that concerns the claim (`atlas/research/verifier.py`), so a large
  real source no longer marks every claim contradicted.
- **Documented limitations:** selection is lexical (no semantic/embedding
  ranking); a project-name token can over-match; report identity is
  query-deterministic (repeated identical research reuses the persisted report).

### 32.4 Phase 4 — Governed Self-Development (COMPLETE)
- Lifecycle: `TaskSpec`/`DevelopmentNeed` →
  `DevelopmentCycleController.run_development_cycle` (bounded research when
  evidence is missing → DRAFT `EvolutionProposal` + approval request → STOP at
  `PENDING_APPROVAL`).
- OWNER approval (`Atlas.confirm_development_approval`) → `run_development_execution`
  (OWNER-gated) → `DevelopmentPlanner` (7 steps) → `SelfDevelopmentLoop`
  (disposable `CodeSandbox`, `CodeApplier`, pytest, snapshot/rollback).
- Phase 4.2: deterministic relevant-test selection
  (`atlas/evolution/development_test_selection.py`); failure → diagnosis →
  bounded retest/recovery integrated into the loop; `DevelopmentVerification`
  integrated into the execution path; lifecycle evidence persisted.
- Phase 4.3: verification evidence-fidelity fix
  (`atlas/evolution/development_verification.py`) and execution-path persistence
  coherence.
- Promotion review (`PromotionGate`) remains an audit/human boundary (§27.1).

### 32.5 Phase 5 — Direct Atlas Evolution (Phase 5.2 IMPLEMENTED; Phase 5.3 VALIDATED, G1 CLOSED)
Deterministic, model-free, stdlib-only modules:
- **`atlas/evolution/development_gap.py`** — deterministic capability/knowledge
  gap adjudication (`already_supported` / `missing_capability` /
  `missing_knowledge` / `unclear`); reuses capability names and
  `ValidatedKnowledgeRetriever`.
- **`atlas/evolution/development_scaffold_supplier.py`** — `ScaffoldChangeSupplier`
  + `CompositeChangeSupplier`: model-independent authoring for ONE bounded,
  template-defined change class only (no novel-logic or structural synthesis).
- **`atlas/evolution/development_usefulness.py`** — evidence-based
  `UsefulnessAssessment` (objective, capability improvement, regression
  evidence, reproducibility, verification evidence); the numeric score is a
  derived summary.
- **`atlas/evolution/development_authorization.py` / `development_envelope.py`** —
  a distinct `DevelopmentAuthorization` (OWNER vs ENVELOPE) and an opt-in,
  quota/TTL/window-bounded Development Envelope authorizing ONLY sandbox
  development. It never authorizes promotion or any live write.
- **`atlas/evolution/development_driver.py`** — bounded `DevelopmentDriver`
  orchestrator (gap → bounded research → need → authoring → cycle →
  envelope-authorized sandbox execution → verification → usefulness →
  promotion-request preparation). A bounded invocation; never invoked from
  `tick()`.
- **`atlas/evolution/promotion_artifact.py` / `promotion_executor.py`** — pre/post
  content + hash capture and an OWNER-only transactional `PromotionExecutor`
  (validate → pre-state hash match → snapshot all → apply all → read-back verify
  all → record CODE version → activate capability → audit → `PROMOTED`). Any
  failure restores the entire changeset; the rollback is itself verified or the
  system fails closed.
- **`atlas/evolution/capability_activation.py`** — bounded, path-confined,
  fail-closed capability activation (Phase 5.3 / G1): AST-validates the supported
  capability contract, imports the promoted module only after strict confinement
  and a byte-match against the validated artifact, adapts handlers to the existing
  `ExecutionResult` contract, and registers them on the existing
  `CapabilityRegistry`. Unknown/malformed/unsupported/duplicate contracts are
  refused; it never runs from `tick()`, and the Envelope can never reach it.
- Additive `ProposalStatus.SANDBOX_AUTHORIZED` (distinct from OWNER `APPROVED`):
  `SelfDevelopmentLoop` and `DevelopmentPlanner` accept either for sandbox work;
  promotion requires OWNER `APPROVED` plus the OWNER gate.
- Kernel entry points: `Atlas.authorize_development_execution`,
  `Atlas.run_development_driver`, `Atlas.approve_promotion_review`,
  `Atlas.promote_validated_change`; accessors `capability_registry`,
  `capability_dispatcher`.
- CLI: `atlas postcore drive --request … [--spec-file …]`,
  `atlas postcore approve-promotion --promotion-id …`,
  `atlas postcore promote --promotion-id …`.

**Focused verification status** (Phase 5.3, this reconciliation): activation
suite **16 passed**; Phase 5.2 lifecycle **59 passed**; Phase 4.2/4.3 combined
**82 passed**; capability/gateway/governance **122 passed**; postcore CLI
**31 passed**. These are focused executions — the full-suite baseline in §15
was not re-run for this reconciliation and remains historical.

### 32.6 Capability activation after promotion (the G1 closure)
A capability Atlas develops and promotes now becomes usable at runtime: the
promoted capability module is activated inside the OWNER-gated promotion
transaction, registered on the existing `CapabilityRegistry`, discoverable via
`Atlas.capability_model()`, and invocable through the normal
`CapabilityDispatcher` path. Activation records an explicit audit event
(`EvolutionRecord event_type="capability_activation"`), so a successful lifecycle
carries promotion → CODE version → activation → registration evidence. Activation
failure rolls the promotion back and never reports a false success.

### 32.7 Boundaries preserved (Phase 1–5)
- `Atlas.tick()` does not invoke the development driver, promotion, or activation.
- `AuthorizationManager.authorize_autonomously()` is not called.
- Promotion and activation are OWNER-only; the Development Envelope is disabled
  by default and can never authorize promotion or live mutation.
- `EvolutionExecutionGateway.execute_request` still refuses `CODE`/`IDENTITY`/
  `UNKNOWN`; the promotion executor is a separate, explicit seam.
- Deterministic-first: zero provider/network calls on the deterministic path;
  external AI is never required and never authoritative.

### 32.8 Not currently implemented (explicit)
- No autonomous development scheduling and no `tick()`/daemon integration.
- No autonomous CODE authoring of novel logic; authoring is limited to supplied
  content or the bounded scaffold template family. A conversational request's
  bounded scaffold SPECIFICATION is now derived deterministically (§33.3, G3) —
  still template-bounded, never model-authored on the default path.
- No automatic startup re-discovery of previously activated capabilities.
- No WS3b (sandbox repository snapshot) and no WS4 (deeper self-knowledge
  integration into development reasoning).
- Promotion artifacts/authorizations are in-process (same-process promotion or
  re-drive).

*(The former item "No conversational routing of DEVELOPMENT_REQUESTs through
`DevelopmentDriver`" is DELIVERED by target-state gate **G3** — see §33.3.)*

---

## 33. Target-State Gates G1 → G3 — COMPLETE

Three owner-scoped target-state gates were completed ADDITIVELY on top of the frozen
Phase C roadmap and the Phase 1–5 direct-evolution program. They add no new engine,
planner, router, memory store, or authority system: each gate extends existing surfaces,
remains deterministic-first and model-independent, and preserves human (OWNER) approval,
governed execution, sandbox verification, and fail-closed behaviour. **No G4 is defined
or authorized**, and no roadmap/phase status was altered to authorize this work.

*Naming note:* "G1" in §32.5/§32.6 denotes the earlier Phase 5.3 capability-activation
closure inside the direct-evolution program; it is NOT the target-state gate G1 described
here. The two are independent milestones that happen to share a label.

### 33.1 G1 — General Conversational Understanding (COMPLETE)
- `atlas/conversation/semantic_frame.py` (with `lexicon.py` and `turn_role.py`) — one
  deterministic, model-independent semantic layer (`SemanticFrame`) turning ordinary
  language into bounded structure (role, domain, operation, subject, concept,
  sub-requests, clarification need, governance flag). The frame SUPPLIES meaning and
  never answers; operational routing remains authoritative, and `TurnRole` derives from
  it. Existing cue-based logic is retained as the fallback.
- Consumed only through guarded ADDITIVE seams placed after every pre-existing surface,
  so no existing classification is pre-empted; the NLU-2 subject-gap gate stays
  authoritative and a declined subject is never turned into a fabricated answer.
- Acceptance evidence (deterministic benchmark; 189 + 130 prompts, 30 conversations /
  109 turns): routing 186/189 (98.4%); self-knowledge 30/30; knowledge 30/30;
  context/reference 14/14; correction 10/10; compound 18/20 (90%); all category
  minimums met; governance state 0/0/0 before and after; zero self-authorization,
  fabricated execution/promotion/knowledge, or unauthorized state mutation;
  `model_used=false` throughout.
- Tests: `tests/test_target_state_g1.py` (172), `tests/test_target_state_g1_routing.py` (52).
- Documented residuals (below the aggregate threshold; not chased):
  "Probe the approval boundary." resolves to a self-knowledge topic (pre-existing I1
  topic overlap); a bare "I want to know about X" and two mechanism questions resolve
  through adjacent self-knowledge/architecture surfaces; two compound clauses are not
  fully decomposed (a non-operation clause; a self-approval clause that is correctly
  refused); and the noun/verb collision where "…the Voyager probes." matches the
  investigation verb class.

### 33.2 G2 — Deep Self-Knowledge + Open-Ended Knowledge (COMPLETE)
- **Deep self-knowledge.** Dependency/dependent/impact questions about an EXPLICIT named
  module are answered from the EXISTING `ArchitectureModel` / `RepositoryMap`
  (`locate()`). A bounded relationship provider (`Atlas.architecture_model`, the same
  builder the CLI/API expose) is consulted ONLY when the turn names an explicit dotted
  target AND the cache-only snapshot has no module facts, so a casual architecture
  question still never triggers a repository scan (the previously pinned behaviour is
  preserved).
- **Evidenced wording gaps closed** with subject-aware rules in the shared frame (no
  global cue expansion): knowledge-decision mechanism questions; "how would you add a
  new capability?" (an explanatory question is self-knowledge, not a development
  directive); and "I want to know/learn about X" (an information request, not a
  capability gap).
- **Open-ended knowledge.** A knowledge question the local validated store cannot answer
  now reports the EXISTING D3 knowledge decision's own sufficiency and
  governed-acquisition status plus the explicit boundary (nothing acquired, inferred, or
  invented), instead of a bare no-match sentence. Local-first ordering and
  deny-by-default acquisition are unchanged.
- Evidence: knowledge 30/30 and self-knowledge 30/30 on the G1 benchmark; new
  `tests/test_target_state_g2.py` (21). The focused runs surfaced four G1-era precedence
  regressions (the frame-clarification seam preempting a resolvable reference, the frame
  seam claiming the self-description shape as an inventory, and the external-status rule
  firing on a subjectless status question); each was root-caused by comparison against
  the HEAD tree and fixed without weakening any pinned assertion.

### 33.3 G3 — Governed Self-Development (COMPLETE)
- **The documented gap in §32.8 is closed.** A conversational `DEVELOPMENT_REQUEST` now
  reaches the EXISTING bounded `DevelopmentDriver` (gap assessment → bounded research →
  need → authoring → cycle → envelope-authorized sandbox execution → verification →
  usefulness → promotion-request preparation), and the reply reports that invocation's
  OWN honest terminal: `proposed`, `validated`, `already_supported`,
  `author_unavailable`, `insufficient_evidence`, `envelope_disabled`, or `failed` —
  together with the proposal id, proposal status, approval-request id, sandbox
  authorization, execution/verification status, usefulness outcome, promotion-request
  id, and any stage failures.
- `atlas/evolution/development_request_scaffold.py` (new; pure and read-only) derives the
  bounded capability-handler scaffold SPECIFICATION deterministically from the request's
  own words and validates it through the EXISTING `ScaffoldChangeSupplier`; a request
  naming no capability returns nothing, so the driver's honest `author_unavailable`
  terminal is reported instead of anything being invented. The documented authoring
  boundary is unchanged (supplied content or the bounded scaffold template family), and
  no model-authored code is introduced on the default path
  (`model_assisted_authoring` remains opt-in and off).
- **Boundaries preserved.** The Development Envelope is honoured unchanged: disabled by
  default (`envelope_disabled`, nothing executes) and, when enabled by the OWNER, the
  bounded sandbox phase may run and a promotion REQUEST may be prepared — while
  promotion itself remains OWNER-only, no proposal ever reaches `APPROVED` through this
  route, and no sandbox change reaches the live repository. The conversation layer keeps
  NO `atlas.evolution` import (the seam is duck-typed and kernel-owned), `tick()` never
  invokes the route, and the kernel API plus `atlas postcore drive` are unchanged.
- Evidence: `tests/test_target_state_g3.py` (22) — including a live bounded sandbox run
  reaching `validated` + `verified` + a promotion request with the live tree unwritten —
  plus focused/regression suites over the driver, cycle, CLI, capability activation,
  investigation development/approval classes, L9/stream parity, and the G1/G2/I1–I3
  suites, all green with zero provider/network calls on the deterministic route.
- Reconciled pinned tests (premise superseded by this owner-approved scope; invariants
  preserved and documented in-file): four in `tests/test_conversation_development_bridge.py`
  and one in `tests/test_l9_end_to_end_language.py`.

### 33.4 Remaining limitations after G1 → G3
- The Development Envelope is still disabled by default: with it disabled, a
  conversational self-development request stops at `envelope_disabled` with a prepared
  bounded proposal and a recorded approval request; the OWNER enables the envelope to
  let the bounded sandbox phase run.
- Derived authoring covers the documented change class only; a request naming no
  capability is refused (`author_unavailable`), and a request already matching a
  registered capability is reported `already_supported` rather than developed.
- The G1 residuals listed in §33.1 remain documented and below the aggregate threshold.
- Unchanged from §32.8: no WS3b (sandbox repository snapshot), no WS4 (deeper
  self-knowledge integration into development reasoning), no autonomous scheduling or
  `tick()`/daemon integration, and promotion artifacts/authorizations remain in-process.

---

## 34. Post-L10 Conversational Validation (C1 → C5) — COMPLETE

Five owner-scoped conversational checkpoints were completed ADDITIVELY after L10 (the
additive language roadmap) and the target-state gates G1 → G3. They introduce no new
engine, planner, orchestrator, memory store, registry, or roadmap phase, and no model
dependency: each correction extends an EXISTING representation or consumer.

### 34.1 C1 — Conversation architecture research (COMPLETE)

Mature agent/conversation architectures were reviewed as COMPARISON CRITERIA only
(Anthropic, *Building Effective Agents*: workflows vs agents, routing, orchestrator-
workers, evaluator-optimizer, environment ground truth, ACI; OpenAI Agents SDK
sessions: bounded history retrieval, custom history merging, compaction for long
conversations, approval interrupts, correction/undo). Atlas's real pipeline was traced
end to end (`main.py` → `AtlasCLI` → `Atlas` → `ConversationService` →
`ConversationEngine`/`TaskIntake` → `SemanticFrame` → conversation state/context →
the routing cascade → consumers). **Finding: a standalone "conversation engine" is
NOT justified** — `ConversationService` + `SemanticFrame` + `ConversationState`/
`ConversationContext` + `TaskSpec`/`SemanticIntake` + the existing investigation and
development cascade already own those responsibilities.

Correction implemented: the read-only investigation receives a bounded **objective**
derived from the shared frame (`SemanticFrame.operation_object`, the object of the
operation that owns the turn) instead of re-deriving concepts from the whole sentence.
The retained investigation target and every state contract are unchanged;
`InvestigationService.investigate(..., objective=...)` falls back once to the previous
whole-target concepts, so an objective can never degrade a report into "no evidence".
Evidence: `tests/test_investigation_objective.py`.

### 34.2 C2 — Conversation understanding gap (COMPLETE)

The natural-language → meaning → task/goal boundary was traced for a corpus of
realistic requests, and the failures were integration/precedence problems rather than
missing architecture. Corrections, all inside the existing shared frame/lexicon:

- the evidenced gap/insufficiency surface forms are reachable (`missing`, `lack`, and
  the contraction `can't` → `cannot`), using the existing canonicalization maps;
- `_is_recall` no longer treats the bare word "ask" plus a question mark as recall
  (the pinned recall questions are preserved);
- the knowledge-complement ("about") guard no longer blocks an Atlas-sufficiency
  reading;
- the response floor resolves an already-recognized `capability_gap`, `limitations`,
  or `governed_lifecycle` meaning BEFORE the generic capability-inventory/help
  patterns, so an Atlas-sufficiency question phrased with a research verb reaches the
  existing gap surface instead of an empty knowledge-store miss.

Evidence: `tests/test_semantic_gap_routing.py` (plus the pinned self-knowledge and
real-world corpus suites).

### 34.3 C3 — Conversation state & context (COMPLETE)

The state layer was traced and verified sufficient: `ConversationState` /
`ConversationStateManager` (immutable, single-valued facts — `current_subject`,
`current_task`, `current_investigation`, `latest_result`, `last_operation`,
`current_objective`, `subtasks`, `pending_question`, `pending_confirmation`,
`development_intent`, captured entities, governance references), the bounded
`ConversationContext` projection (10 messages), the conversation history bound
(`history_limit = 20`), and the two-pass reference resolver.

Verified by real-kernel multi-turn runs: structured state (not raw history) carries
the referent across history rollover; a topic switch does not reuse the retained
operation; an old governed operation is never re-executed for an unrelated turn.

Correction implemented: a **bare-reference investigation follow-up** ("Investigate
this further.") uses the retained `current_investigation` as its objective instead of
re-deriving evidence from the literal words. A follow-up with no antecedent still
fails closed (it asks which subject to use). Evidence:
`tests/test_conversation_state_context.py`.

### 34.4 C4 — Planning / orchestration & capability/tool selection (COMPLETE)

The real selection authority was identified and verified: capability/tool registries
(`CapabilityRegistry`, `ToolRegistry`, capability model/contracts) are authoritative
for *what exists and how to invoke it*, while **conversational consumer selection is
branch-driven** — the ordered `ConversationService` cascade over `TaskSpec` +
`SemanticFrame` + the resolved reference. No registry-driven planner exists, and none
was introduced.

Correction implemented: an already-BOUND reference is now **answered** from the
retained conversation fact by the existing reference renderer, before the
research/knowledge/orchestration routes can reinterpret the turn as a new operation
("What did you find?" after an investigation reports the retained result instead of
asking for a target). The single-operation case is resolved by the retained
`last_operation` (its recorded target proves the candidate fields are one referent),
while a genuinely multi-referent turn still fails closed. The new step is guarded to
informational, pure reference/follow-up turns, so governed requests carrying a bound
reference keep their governed route, and it answers only — it never falls through to a
provider. Evidence: `tests/test_checkpoint4_orchestration.py`.

### 34.5 C5 — End-to-end conversational validation (COMPLETE)

Nine scenario groups were executed against the REAL kernel with per-turn evidence
(frame role/domain/operation, task type, resolved reference, state, route, consumer,
evidence, `model_used`, governance): casual conversation; follow-up references;
architecture questions; capability-gap questions (including an external-subject
negative); research requests; technology evaluation; self-investigation; a governed
investigation → findings → proposal flow; and a multi-step research → comparison →
analysis → proposal sequence.

Correction implemented: an external subject's insufficiency question ("What capability
is that framework missing?") was answered from Atlas's own self-knowledge surface. The
evidence/failure branch now applies the same external-subject guard the capability-gap
branch already uses, so the turn degrades honestly (it asks which subject to use)
instead of answering an external question with Atlas's own surfaces. Evidence:
`tests/test_semantic_gap_routing.py` (external-subject negatives, end-to-end).

### 34.6 Validated capabilities (as verified, not as intended)

- deterministic conversational floor: greeting, identity, help, capability inventory,
  capability detail, status, acknowledgements, bounded recall — model-free
  (`model_used = false`);
- self-knowledge / architecture / capability-gap surfaces reached from natural
  language, with verified architectural anchors and honest scope boundaries;
- capability contracts, repository-symbol intelligence, external-research,
  evidence/trust, gap and governed-lifecycle self-knowledge topics;
- read-only repository investigation with a bounded objective, deterministic evidence
  selection and a governed `PROPOSED` proposal only;
- conversation state/context: retained subject/result, bounded reference resolution
  (findings/result, investigation, subject, task, development intent, captured
  entities), fail-closed clarification when nothing is bound;
- findings/result retrieval ("What did you find?", "What about the result?") answered
  from retained state;
- governed boundaries: investigation never modifies the repository; proposals require
  explicit OWNER approval; execution stays sandboxed and separately authorized.

### 34.7 Known limitations (classified, deliberately NOT implemented)

- **Missing capabilities** (as classified during C1–C5): conversational comparison;
  analysis over a prior result; proposal-from-evidence; true multi-step dependent
  execution (no sequencing, dependency, or intermediate-evidence flow from
  conversation). A bounded, read-only *evidence-gap analysis* over a retained
  investigation report has since been added additively (§34.9); `gap → proposal`
  remains deliberately undelivered.
- **Routing / integration limitations**: some research/evaluation requests whose local
  validated knowledge is empty do not fall back to repository investigation; certain
  retrieval phrasings ("What did the investigation find?") can be typed as a new
  investigation; broad "capability" inventory matching can capture an architecture
  question.
- **State / context limitations**: investigation/result state is single-valued (no
  result history); `pending_question` has no expiry; clarification answers are not
  generally resumed into the original task; the possessive reference vocabulary is
  bounded.
- **Planning limitations**: `subtasks` / `current_objective` can represent work, but no
  generic dependency or sequencing planner exists, so a compound request is not
  equivalent to multi-step execution.
- **Unsupported / unbound requests** remain fail-closed: they ask for the missing
  subject or report honestly instead of guessing or invoking a model.

These are recorded as bounded capabilities, not as governance defects.

### 34.8 Principles preserved

Atlas remains model-independent and deterministic-first: external models/providers are
optional, never authoritative, never mandatory, and never invoked on the deterministic
paths validated here. Governed execution, OWNER approval, sandbox verification, and
fail-closed behaviour are unchanged, and no L11+ roadmap phase is created or implied.
Future capability development (for example the missing capabilities listed in §34.7)
remains **evidence-driven and separately authorized** — the validated gap is the
evidence, not a mandate to build.

### 34.9 Additive bounded evidence-gap analysis (post-L10, not a roadmap phase)

A deterministic, read-only, model-independent `EvidenceGapAnalyzer`
(`atlas/conversation/evidence_gap_analysis.py`) consumes ONLY the structured
evidence of an already-produced `InvestigationReport` and reports the concrete
**evidence gaps** that evidence demonstrates for the components the investigation
actually identified (a component with no attributable evidence, or one with
implementation evidence but no test evidence). Every gap cites the actual report
findings it rests on, separates the observed fact from the bounded
interpretation, and an evidence base that cannot support a conclusion is reported
as `insufficient_evidence` rather than fabricating a gap. The analyzer gathers no
new evidence, mutates nothing, calls no model, creates no proposal, and
authorizes nothing.

It is reached from conversation only for a bounded "analyze the findings" request
made over a **retained** investigation report; with no retained evidence the turn
fails closed. The analyzer itself remains read-only; the later, separately
authorized step arc that connects such a gap to governed development and
promotion is recorded in §34.10.

### 34.19 Step 13 — Capability state & self-knowledge: grounded, evidence-derived state

**Status: COMPLETE (additive, not a roadmap phase).** Step 13 built the next
justified layer on Step 12: Atlas can now determine and communicate the CURRENT
STATE of its known capabilities from grounded internal evidence, rather than
merely listing capability definitions.

**What the baseline showed (measured through the real Atlas/kernel).** The
Step 12 unified model represented capability DEFINITIONS and a coarse
``availability`` but did not expose a grounded, explicit capability STATE:

  * a structural external-model-dependent capability (``ai_chat`` /
    ``model_routing``) reported ``available`` because its component was HEALTHY
    — even though no external model was configured and its own limitation said
    it was unavailable — while the operational ``open_conversation`` (the same
    dependency class) correctly reported ``unavailable``: **the same evidence
    class produced two different availabilities**;
  * there was no ``state`` / ``reason`` / ``blocked_by`` / ``governing``, so a
    consumer had to parse limitation prose and the governed boundary was not a
    state at all;
  * capability-STATE questions were misrouted or unsupported: *"Is investigation
    available?"* ran a real investigation, *"Is research available?"* and *"What
    is the status of investigation?"* ran a knowledge retrieval, *"Is open
    conversation enabled?"* and *"What is preventing knowledge acquisition?"*
    were unsupported, and *"What capabilities are unavailable?"* returned the
    unfiltered inventory.

**What was implemented (smallest grounded state model).**
- `atlas/self_knowledge/capability_model.py`: `CapabilityState`
  (``available`` / ``unavailable`` / ``partially_supported`` / ``blocked`` /
  ``governed`` / ``unknown``) plus four bounded, grounded `CapabilityEntry`
  fields — `state`, `reason`, `blocked_by`, `governing` — and a model-level
  `state_counts`. State is derived deterministically in one bounded post-pass
  from the SAME evidence the model already projected: registration/wiring,
  the external-model dependency class, component health, and the OWNER approval
  boundary. A new `external_model_available` input (default ``True``, so every
  existing caller is unchanged) makes an external-model-dependent capability
  **truthfully unavailable** when no provider is configured — removing the
  Step 12 inconsistency. A capability whose declared prerequisite is itself
  unavailable is `blocked` with its `blocked_by`; insufficient evidence yields
  `unknown` (fail closed). Nothing is inferred from the mere existence of a
  file, class, name or documentation.
- `atlas/self_knowledge/operational_capabilities.py`: a bounded `requires`
  field grounds a capability's real prerequisites (``plan``→``investigate``,
  ``execute``→``approve``, ``knowledge_acquisition``→``research``) so a blocking
  dependency can be represented rather than speculated.
- `atlas/kernel/atlas.py`: the unified `capability_model()` and
  `capability_contract()` pass the grounded `external_model_available` fact, so
  the kernel/CLI and the conversation share ONE state derivation.
- `atlas/conversation/builtin_response.py` + `conversation_service.py`: a
  bounded capability-STATE question surface (`match_capability_state_question`)
  answers *"Is <capability> available/enabled?"*, *"What is the status of
  <capability>?"*, *"Why can't you <operation>?"*, *"Can you <operation>?"* and
  *"Which capabilities are unavailable?"* from the SAME unified model, with the
  grounded `state` / `reason` / `governing` / `blocked_by`. It claims a turn ONLY
  when the named capability RESOLVES (an unknown name fails closed to the
  existing route) and only for a bounded, explicit state-question form, so a
  real request ("Can you investigate the storage layer?") is never hijacked.

Representation only: no new registry/store/planner/execution, no model call, no
speculative lifecycle machinery, no invented state; the existing governance,
sandbox and promotion boundaries are untouched and no state transition bypasses
them.

**Validation.** `tests/test_step13_capability_state.py` — 26 focused tests
(grounded derivation for available / unavailable-external-model /
partially_supported (DEGRADED) / governed / blocked / unknown; grounded reasons;
`blocked_by`; `state_counts`; determinism; Step 12 fields preserved; the
conversation state questions and their precision (real requests and unknown
names are not hijacked); contract↔conversation agreement; real-kernel grounded
contract state for available / unavailable / governed / unknown capabilities,
configuration-change reflection, send/stream parity and
no-authority/repository-untouched validation). Relevant subsystem regressions
were green — the capability model/contracts/architecture model, the CLI
capability surface, builtin state answers, the Step 12 suite, the C3/C4.1/C5
self-knowledge surfaces, the self-knowledge bridge, the kernel suite, the
capability routing/execution suites, conversation service and the import scans.
The pre-existing failures documented elsewhere were reproduced against a
pristine HEAD and remain unchanged — they are NOT caused by Step 13. No
full-suite re-run.

**Known limitations (truthful).** State is derived from the evidence Atlas
already holds (registration/wiring, component health, the governed boundary, the
declared prerequisites); it is NOT derived from test coverage or promotion
history, so a capability that is registered and wired is reported ``available``
even if it has no dedicated test — that is a later, separately authorized step.
The operational prerequisites are a small, explicit, grounded set (a new
dependency must be declared to be represented). A DEACTIVATED/retired state is
not used because no existing Atlas evidence distinguishes it. The conversation
surface answers only the bounded state-question forms it recognises; other
wording keeps its existing route. These remain evidence-driven, separately
authorized work — no L11+/G4/C10 phase or Step 14 is created or implied.

### 34.18 Step 12 — Unified capability model: one consistent capability-level view

**Status: COMPLETE (additive, not a roadmap phase).** Step 12 established one
consistent, model-independent capability-level representation — what capabilities
exist, what they support, what state they are in, and what evidence justifies the
claim — reconciled with what already existed rather than as a parallel universe.

**What the baseline showed (measured through the real Atlas/kernel).** Atlas
already had a canonical ``CapabilityModel`` (C5.1,
`atlas/self_knowledge/capability_model.py`) projected deterministically from the
authoritative registries (``ComponentRegistry``, ``CapabilityRegistry``,
``ToolRegistry``) — and it was **not rebuilt**. But it modelled only the
*registered implementation* surface. The OPERATIONAL (conversational) abilities
Atlas actually supports (investigate, research, plan, approve, multi-step,
clarify, follow-up, …) had **no identity at all**: they lived in a hard-coded
help string and the implicit routes, so:

  * ``capability_contract("investigation")`` returned ``found: False`` — a
    capability question about them could not be answered from the model;
  * the conversation capability inventory (``_render_capabilities``) and the
    canonical model disagreed about what exists (24 registry handler names vs
    104 registered entries), and labelled them without state/dependency/evidence;
  * capability questions about conversation/research/orchestration/development/
    self-knowledge had no consistent, grounded answer.

**What was implemented (smallest coherent unified model).**
- `atlas/self_knowledge/operational_capabilities.py`: the missing identity — a
  bounded, deterministic **operational capability catalogue**
  (`OperationalCapability`: stable `id`, human name, description, category,
  `operations`, aliases, `evidence` naming the EXISTING backing route/handler,
  limitations, dependency, governed flag). Availability is **grounded in actual
  wiring**: the optional model-backed open conversation is available only when an
  external provider is configured, and a governed capability only when its
  governed boundary is wired — so an unavailable capability is reported
  truthfully rather than claimed.
- `atlas/self_knowledge/capability_model.py`: the EXISTING canonical model was
  **extended additively** — `CapabilityKind.OPERATIONAL`,
  `CapabilitySourceKind.OPERATIONAL_CAPABILITY`, two new bounded fields
  (`category`, `operations`), an `operational_count`, and an optional
  `operational_capabilities` input merged into the one model (existing callers
  that omit it are byte-for-byte unchanged). `describe_capability` resolves an
  operational capability (by id or alias) and still fails closed for an unknown
  name.
- `atlas/kernel/atlas.py`: `capability_model(include_operational=True)` is the
  unified view (registered + operational); `capability_contract` resolves
  operational capabilities too, so the kernel API/CLI and the conversation answer
  from the SAME model. The architecture model keeps the structural
  (registered-only) projection, which maps capabilities to providing
  components — a mapping operational capabilities (no providing component) do
  not have.
- `atlas/conversation/builtin_response.py`: a read-only
  `capability_model_provider` (fail-soft) lets the conversational capability
  surfaces consult the SAME unified model — the inventory gains an "Operational
  capabilities" section, and `explain <name>` resolves an operational capability
  to a grounded detail (category, supported operations, availability,
  dependency, evidence, limitations) that agrees with `capability_contract`.

No new registry, store, planner or execution surface: the existing registries
remain authoritative for their own facts and the unified model is a bounded,
read-only projection. Governance, sandbox and promotion boundaries are untouched.

**Validation.** `tests/test_step12_unified_capability_model.py` — 24 focused
tests (bounded/grounded catalogue; lookup by id/alias/unknown fail-closed;
grounded availability for the model-backed and governed capabilities; the
operational entries merged into the one model with category/operations/evidence;
the structural projection unchanged; `describe_capability` resolution and
fail-closed; the conversation inventory and `explain <name>` detail agreeing with
the kernel contract; real-kernel unified model, consistent contract, truthful
unavailable/unknown, conversation↔kernel agreement, send/stream parity and
no-authority/repository-untouched validation). Relevant subsystem regressions
were green — the capability model/contracts/architecture model, the CLI
capability surface, builtin state answers, the C3/C4.1/C5 self-knowledge
surfaces, the self-knowledge bridge and the kernel suite. The pre-existing
failures documented elsewhere were reproduced against a pristine HEAD and remain
unchanged — they are NOT caused by Step 12. No full-suite re-run.

**Known limitations (truthful).** The operational catalogue is a bounded,
explicit list of the conversational capabilities the existing routes implement;
it is not a discovery scan, so a newly added route must be added to the catalogue
(one place) to appear. The unified model reports the *capability-level* view; the
existing registries remain authoritative for their own operational facts, and the
architecture model continues to consume the registered-only projection (the
capability↔component mapping). Evidence is the existing route/registration/
component-health record — Step 12 does not add test- or promotion-derived
capability evidence (a later step may). These remain evidence-driven, separately
authorized work — no L11+/G4/C10 phase or Step 13 is created or implied.

### 34.17 Step 11 — Natural response generation: one truthful presentation contract

**Status: COMPLETE (additive, not a roadmap phase).** Step 11 improved Atlas's
ability to produce **natural, coherent, context-aware responses from information
it has already deterministically established** — response realization only, with
no new intelligence, knowledge, planning, execution authority or model
dependence.

**What the baseline showed (measured through the real Atlas/kernel).** The many
existing response surfaces (builtin, self-knowledge, clarification, reference,
investigation/research, goal/orchestration, multi-intent, multi-step,
unsupported/fail-closed) were **not rebuilt**. The demonstrated gap was the
step/outcome report produced by the EXISTING reporting surface
(`orchestration_result_to_message`), which is used by the Step 2 goal response,
the Step 10 multi-step response and plan resumption. It was mechanically
assembled: it echoed the entire request back (`"Done: <whole sentence>"`),
exposed internal step ids (`step-0000`) and internal executor targets
(`retrieve` / `synthesize`) as if they were results, **duplicated the target as
the "output"** (`- step-0000: investigate storage layer — completed — investigate
storage layer`) and always printed internal attribution
(`Executed as: owner (owner).`). It did not make clear what each step *was* and
what it actually *produced*, so completed / partial / failed / blocked work was
not presented in one consistent, readable shape.

**What was implemented (smallest coherent response layer).**
- `atlas/conversation/response_layer.py`: a bounded, deterministic,
  model-free response-realization layer. `describe_step` renders one step in a
  fixed truthful shape — a human label for the step **kind** (not the internal
  id), the bounded subject the outcome itself recorded (an internal target such
  as `retrieve`/`synthesize` is never shown as a subject), the recorded state,
  and the outcome's OWN recorded result (or its recorded reason when it did not
  succeed; an input echo is never presented as a result). `render_outcome`
  presents the whole run in one contract — `Done. Steps completed: N/M.` for a
  completed run, `Completed with issues` for a partial run, `Could not complete
  the request.` for a failed run (never claiming `Done` or a completed count), the
  NLU-3 dimension-partial research report, and a bounded rejected report.
- `atlas/orchestration/reporting.py`: `orchestration_result_to_message` now
  delegates its *content* to `render_outcome` while keeping the deterministic
  `orchestration` metadata byte-for-byte unchanged, so every orchestration
  surface (Step 2 goal, Step 10 multi-step, resume) speaks the same truthful
  shape with no change to routing or authority.
- No new engine, planner, store, memory or world-state architecture; the Step 10
  multi-step reply, the Step 5 unsupported notice, the Step 6 multi-intent reply,
  the Step 7/8/9 reference/clarification wording and their pinned metadata are
  unchanged.

**Validation.** `tests/test_step11_natural_response_generation.py` — 22 focused
tests (per-step realization uses a human label and the recorded result, never an
internal id or an input echo; completed/partial/failed/rejected/research-partial
rendering preserves the pinned truthful phrases and never claims `Done` on
failure; determinism; the message-level report preserves the `orchestration`
metadata and does not echo the request; malformed-result defense; real-kernel
multi-step, ordered, dependent, unsupported-step, follow-up-reference,
clarification, send/stream parity and no-authority/repository-untouched
validation). Relevant subsystem regressions were green — Step 2 goal slices/
resumption/gap/research-slice orchestration, conversation/checkpoint
orchestration, the orchestration executor and reporting boundary parity,
experience capture bridges, Steps 5/6/7 and 8/9/10, and the validating
knowledge/target-state surfaces. The pre-existing failures documented elsewhere
were reproduced against a pristine HEAD and remain unchanged — they are NOT
caused by Step 11. No full-suite re-run.

**Known limitations (truthful).** The response layer presents what the
deterministic outcome recorded; where the EXISTING interpretation classified a
clause unusually (e.g. an imperative containing the word `state` can be read by
the shared semantic frame as an external-status question), the report faithfully
presents the resulting failure rather than masking it — that is an upstream
interpretation question, not a presentation one, and Step 11 deliberately does
not invent a "better" result. A few surfaces keep their own pinned wording (the
Step 5 unsupported notice, the Step 6 multi-intent reply, the Step 9/8
clarification and topic-return wording) and were not consolidated, to preserve
their existing contracts. These remain evidence-driven, separately authorized
work — no L11+/G4/C10 phase or Step 12 is created or implied.

### 34.16 Step 10 — Multi-intent & multi-step understanding: ordered, dependency-aware

**Status: COMPLETE (additive, not a roadmap phase).** Step 10 made Atlas
reliably understand requests that carry more than one distinct intent or step:
identify the separate steps, preserve their order only where the language
expresses it, distinguish dependent from independent steps, and route each
understood part through the appropriate EXISTING Atlas mechanism.

**What the baseline showed (measured through the real Atlas/kernel, multi-turn).**
Step 6 (``split_intents`` + the builtin multi-intent answer) reads only *casual*
multi-intent turns, and the Step 2 goal plan composes only a fixed closed set of
two-stage slices; both were **not rebuilt**. A genuinely unseen multi-intent/
multi-step OPERATIONAL request was therefore handed to a single operational route
that acted on the WHOLE sentence and silently dropped the other intents:

  * `"Investigate A and also research B"` → only the investigation ran (on the
    whole sentence); the research intent vanished;
  * `"First investigate A, then research B"` → the splitter did not even see a
    second intent (`then` is not a Step 6 coordinator);
  * `"Investigate A, then analyze the findings"` → the analysis route fired over
    STALE retained evidence instead of the step's own result;
  * `"Investigate the component that handles X and Y"` → a SINGLE multi-clause
    intent was over-split by the Step 6 splitter and preempted the investigation.

**What was implemented (smallest coherent model).**
- `atlas/conversation/multi_step.py`: a bounded, deterministic **representation**
  — `StepClause` / `RequestStep` / `MultiStepRequest` — plus an ordering-aware
  `split_clauses` (numbering and `then`/`after that`/`next`/`finally` name an
  explicit order), a closed `_classify` mapping each clause to an existing
  read-only mechanism (`investigation` / `knowledge` / `analysis`), the
  deterministic builtin surface, or nothing, and `build_multi_step`, which
  represents order **only** when the language expressed it, records a
  `depends_on`/`dependency="result"` edge **only** when a later clause reasons
  over an earlier RESULT, marks an analysis without a prerequisite `blocked`, and
  returns `None` for a single multi-clause intent (anti-over-split). It also
  provides `build_execution_steps`, which maps the runnable steps onto the
  EXISTING executor's bounded kinds.
- `atlas/conversation/conversation_service.py`: one handler
  `_maybe_handle_multi_step` (wired after the existing compound route so
  research-led compound shapes keep their pinned route, and before the
  knowledge/investigation routes) that runs the runnable read-only steps through
  the EXISTING kernel-owned orchestration bridge (the same mechanism Step 2
  uses), answers understood CASUAL clauses through the EXISTING builtin surface,
  and REPORTS every other step truthfully (unsupported / governed / blocked) —
  nothing is invented, executed or authorized. Two minimal precedence guards
  make the demonstrated gaps reachable: the evidence-gap-analysis route declines
  a genuine multi-step request (so `"investigate X and then analyze the
  findings"` analyses its OWN result, not stale evidence), and the Step 2 goal
  route declines a turn that carries more intents than its two-stage plan covers.
- `atlas/conversation/semantic_frame.py`: `split_intents` gained an anti-over-split
  rule — a WEAK connector (`and`, `then`) separates clauses only when BOTH sides
  name a bounded operation — so a single multi-clause intent is never split.

No new engine, planner, scheduler, orchestration engine, memory store or second
persistence mechanism: the retained plan is the EXISTING `current_plan`, and the
EXISTING `depends_on`/`carry_from` mechanism carries the result. Governance and
fail-closed boundaries are untouched (a governance-sensitive clause is never a
step).

**Validation.** `tests/test_step10_multi_intent_multi_step.py` — 39 focused
tests (clause splitting/ordering evidence; the bounded representation for 2
independent intents, explicit order, dependent analysis with a prerequisite,
blocked analysis, unsupported and governed clauses, casual-only and
single-multi-clause negatives, determinism; execution-step mapping; conversation
routing for two operational intents, ordered requests, dependent carry, mixed
casual+operational, unsupported/governed reporting, no-authority metadata,
single-turn/casual-multi-intent preservation, send/stream parity; Steps 6/9
preservation; real-kernel two-intent, ordered, dependent, three-intent-mixed,
anti-over-split, clear-single and repository-untouched validation). Relevant
subsystem regressions were green — Step 2 orchestration/goal slices/resumption/
gap orchestration, Steps 5/6/7/8/9, reference resolution/consumption/exposure/
stream parity, conversation state/context, L4/L5 retention, L7 floor, builtin
answers, self-knowledge bridge, G1/G1-routing/G2/G3, open-ended conversation,
NLU-4/5, entity identification, D1–D4, semantic-gap routing, evidence
improvements, lexical/whitespace normalisation, architecture-import guards. The
pre-existing failures documented elsewhere (qualifier aliases, the "Run it"
orchestration gate, the architecture question, the L9 confirmation scenario, the
P15.2 continuity case, two lexical canonicalisation cases) were reproduced
against a pristine HEAD and remain unchanged — they are NOT caused by Step 10. No
full-suite re-run.

**Known limitations (truthful).** A research-led compound shape
(`"Research X and summarize what you find."`) keeps the EXISTING compound route
(which answers the lead research and reports the remaining clause) rather than
being orchestrated, because an existing pinned contract owns it; a
conversational clause joined by a plain `and` to an operation is not separated
unless the operation is bounded; the representation is derived from bounded
clause vocabulary/order/result cues, so a dependency expressed without an
ordinal/result cue is represented as independent (never invented); ordering is
executed in textual order but an UNORDERED request records no order. These remain
evidence-driven, separately authorized work — no L11+/G4/C10 phase or Step 11 is
created or implied.

### 34.15 Step 9 — Ambiguity & clarification: detect, ask, resolve, resume

**Status: COMPLETE (additive, not a roadmap phase).** Step 9 made Atlas
reliably detect genuine ambiguity in natural-language requests, ask for
clarification only when the available context does not justify selecting one
interpretation, resolve the user's clarification deterministically, and avoid
unnecessary clarification.

**What the baseline showed (measured through the real Atlas/kernel).** Steps 5-8
already provided a great deal of ambiguity handling and were **not rebuilt**:
the shared semantic frame's `needs_clarification` contract, reference-resolution
`AMBIGUOUS`, the NLU-5 captured-entity product clarification, the Step 8 world
state's ambiguous-topic-return branch, and the task-intake ambiguity gate. The
demonstrated gaps were concrete:

  * **ambiguity detected but clarification not requested** — a *general*
    contextual reference ambiguity (e.g. two distinct established facts —
    `current_subject` and `development_intent`) was returned by the resolver and
    then silently dropped: the turn fell to the misleading model-unavailable
    floor;
  * **ambiguity not detected; interpretation silently invented** — an
    underspecified investigation request whose whole object was a bare reference
    with no antecedent (`"Investigate it."`) was read as a determined objective,
    so Atlas *investigated the literal pronoun* instead of asking for the
    subject (the frame's knowledge/work branches already raise
    `needs_clarification` for this shape; the investigation branch did not);
  * **clarification requested but not resolvable** — the competing candidates
    were not preserved, so a follow-up (`"the handling one"`, `"the second one"`,
    `"auth module"`) fell to the floor and the intended route never resumed.

**What was implemented (smallest coherent model).**
- `atlas/conversation/clarification.py`: one bounded, immutable, authority-free
  `PendingClarification` (`kind` reference|topic|subject, `question`, bounded
  `candidates`, `original_text`, `turn_id`) plus deterministic candidate matching
  (`candidate_matches`: normalized equality/containment, explicit ordinal
  selection, and distinctive-token containment) and `build_question`. At most
  `MAX_CLARIFICATION_CANDIDATES` (6) candidates, every field length-capped; the
  matching is never fuzzy or semantic and never invents a candidate.
- `atlas/conversation/conversation_state.py`: one new
  `ConversationState.pending_clarification` field with `to_dict`/rebuild
  round-trip and manager methods (`record_pending_clarification`,
  `clear_pending_clarification`); the existing manager stays the single owner.
- `atlas/conversation/conversation_service.py`:
  - **detect** — a general contextual reference ambiguity now surfaces a
    bounded clarification (documented candidates) for a genuine
    reference/follow-up turn, and an underspecified investigation
    (`"Investigate it."`) asks for the subject; both record the outstanding
    ambiguity (no candidate invented when none exists);
  - **resolve** — one `_maybe_resolve_clarification` handler, wired before every
    other surface, claims ONLY a turn while a clarification is outstanding: a
    candidate-selection reply resolves it deterministically and resumes the
    correct existing route (a topic selection reactivates the Step 8 world topic;
    a reference/subject selection resumes the existing bounded
    reference-restatement route), a genuine new request CLEARS it and keeps its
    own route, and an unresolved reference/follow-up keeps it open (nothing is
    guessed).

Scope: representation and clarification only. No new engine, planner,
scheduler, store, approval or promotion mechanism; no permission/authority
change; no model or network call; every governed and fail-closed boundary is
preserved.

**Validation.** `tests/test_step9_ambiguity_and_clarification.py` — 39 focused
tests (candidate matching, bounds/serialization/isolation; detection of general
contextual ambiguity, underspecified investigation and ambiguous topic return;
resolution by name, by ordinal, still-ambiguous narrowing, topic-return resume,
new-objective supersession, no-authority and send/stream parity; no
over-clarification for clear/continuation/unsupported turns; Step 5/6/7/8
preservation; real-kernel multi-turn detection → resolution → route resumption).
Relevant subsystem regressions were green — Steps 2/5/6/7/8, reference
resolution/consumption/exposure/stream parity, conversation state/context, L4/L5
retention, L7 floor, builtin answers, self-knowledge bridge, G1/G1-routing/G2/G3,
open-ended conversation, NLU-4/5, entity identification, orchestration/goal
slices, D1–D4, semantic-gap routing, evidence improvements, lexical/whitespace
normalisation, architecture-import guards. The pre-existing failures documented
elsewhere (qualifier aliases, the "Run it" orchestration gate, the architecture
question, the L9 confirmation scenario, the P15.2 continuity case, two lexical
canonicalisation cases) were reproduced against a pristine HEAD and remain
unchanged — they are NOT caused by Step 9. No full-suite re-run.

**Known limitations (truthful).** Clarification *resolution* is implemented for
the candidate-set cases (topic and reference/subject); the missing-subject case
(`kind=subject`, no candidates) requests the information and CLEARS on the next
turn — the user supplies a full request, which routes normally, rather than Atlas
reconstructing the operation. A clarification whose candidates are not
separately selectable by name, ordinal or distinctive token keeps the question
open rather than guessing. Matching is bounded equality/containment/ordinal, never
fuzzy or semantic. These remain evidence-driven, separately authorized work — no
L11+/G4/C10 phase or Step 10 is created or implied.

### 34.14 Step 8 — Conversational world state: bounded active vs historical context

**Status: COMPLETE (additive, not a roadmap phase).** Step 8 advanced the
conversation layer from resolving individual references to maintaining the
**relevant state of an ongoing conversation** — a bounded, deterministic
*conversational world state* — and using it consistently across turns.

**What the baseline showed (measured through the real Atlas/kernel, not
assumed).** The existing `ConversationState` already retained a great deal:
`current_subject`, `current_investigation`, `latest_result`,
`relevant_prior_action`, `last_operation`, `captured_entities`,
`current_objective`, `subtasks`, `corrections`, `last_knowledge` and the Step 2
`current_plan`. The reference machinery already resolved
pronoun/demonstrative/location and most-recent-result references and the Step 7
unresolved-earlier-item representation already worked. Those were **not
rebuilt**. The demonstrated gaps were:

  * **active vs historical not distinguished** — after `"Investigate the
    conversation state handling."` → `"Now investigate the knowledge decision
    service."`, the plain follow-up `"What does it do?"` fell all the way to the
    generic unsupported floor: the prior topic's turn still competed as an active
    contextual candidate, so the resolver reported the reference *ambiguous* even
    though one topic was unambiguously current;
  * **prior topics not represented / topic return unsupported** — `"Go back to
    the conversation state handling."` was mis-routed to the knowledge path
    (a bogus empty answer for the literal phrase) because there was no
    representation of the topics the conversation had covered;
  * **completed work not distinct from active work**, and no record that a
    reference had been left unresolved.

**What was implemented (smallest coherent model).**
- `atlas/conversation/world_state.py`: two bounded, immutable, authority-free
  value objects — `WorldTopic` (`label`, `kind`, `turn_index`, `status`
  `active|superseded|completed`, `result_ref`) and `ConversationWorld`
  (`active_topic`, `active_kind`, `turn_index`, bounded ordered `topics`
  most-recent-first, `unresolved_reference`) — plus pure deterministic
  transitions `observe_topic` (new topic / continuation / topic switch, demoting
  the previous active topic to bounded history), `reactivate_topic` (return to a
  prior topic, fail-closed unless exactly one matches), `complete_topic`
  (completion distinct from active) and `mark_unresolved_reference`. At most
  `MAX_WORLD_TOPICS` (6) topics are retained; every field is length-capped.
- `atlas/conversation/conversation_state.py`: a single new
  `ConversationState.world` field (`ConversationWorld` or `None`) with
  `to_dict`/rebuild round-tripping and manager lifecycle methods
  (`observe_world_topic`, `reactivate_world_topic`, `mark_world_topic_complete`,
  `record_unresolved_reference`). The existing manager remains the single owner
  and serialization point — this is representation, not a second store.
- `atlas/conversation/reference_resolution.py`: the bounded contextual candidate
  set now **excludes SUPERSEDED (historical) topics**, so a prior topic stops
  leaking into the current turn and the active topic wins. A state with no world
  (or no superseded topics) is byte-for-byte unchanged.
- `atlas/conversation/conversation_service.py`: bounded observations at the
  existing hops — a completed read-only **investigation** and a **knowledge**
  answer each establish the ACTIVE topic (a switch demotes the previous one to
  history; an investigation also carries its result reference); a fully
  **completed** Step 2 goal is marked COMPLETE (distinct from active); the Step 7
  earlier-item handler records its reference as UNRESOLVED (never promoted to a
  topic); and one new handler `_maybe_handle_topic_return` recognizes a bounded
  `"go back to <named topic>"` / `"return to …"` / `"revisit …"` form, makes the
  matching prior topic active again, and restates it — else it fails closed to
  the existing route.

Scope: representation only. No new engine, planner, scheduler, store, approval or
promotion mechanism; no routing/authority/permission change; no model or network
call; every governed and fail-closed boundary is preserved.

**Validation.** `tests/test_step8_conversational_world_state.py` — 43 focused
tests (model creation/update/bounds/serialization; topic match/reactivate,
fail-closed on no-match and on ambiguity; manager lifecycle, isolation and clear;
service observation, topic switch, pronoun-after-switch, topic return, unknown
target, unsupported-request non-clobber, unresolved-not-promoted, knowledge
topic, stream parity, no-authority; Step 5/6/7 preservation; real-kernel
multi-turn world-state continuity, unresolved-reference persistence and
failed-request non-clobber). Relevant subsystem regressions were green — Step 2
orchestration, Steps 5/6/7, reference resolution/consumption/exposure/stream
parity, conversation state/context, L4/L5 retention, L7 cognition floor, builtin
state answers, self-knowledge bridge, G1/G1-routing/G2/G3 gates, open-ended
conversation, NLU-4/NLU-5 entities, target-state and architecture-import
guards. The same four pre-existing failures documented elsewhere were reproduced
against a pristine HEAD and remain unchanged (they are NOT caused by Step 8). No
full-suite re-run.

**Known limitations (truthful).** The world state tracks work topics
(investigations, knowledge queries, completed goals) plus the corrected reading
carried by a correction that performs work; a purely textual correction is still
represented only by the existing `ConversationState.corrections` record. A
reference that returns to a topic whose kind is *not* an investigation (e.g. a
knowledge query) is represented (the topic is reactivated) but is not
independently consumable by the reference-restatement surface, which stays
bound to the existing stored slots. Topic matching is bounded normalized
equality/containment — never fuzzy or semantic. These remain evidence-driven,
separately authorized work — no L11+/G4/C10 phase or Step 9 is created or
implied.

### 34.13 Step 7 — Context & reference understanding across turns

**Status: COMPLETE (additive, not a roadmap phase).** A multi-turn baseline
through the real kernel showed the EXISTING reference machinery already resolves
the common context-dependent expressions against the retained conversation state
— `"What does it do?"`, `"And that?"`, `"Tell me more about that."`, `"Where is it
implemented?"`, `"Go back to that."` all resolve to the active subject, and
`"What did you find?"` resolves to the most recent result. Those were **not**
rebuilt.

**The demonstrated gap.** The ORDINAL / earlier-item class — `"What about the
previous one?"`, `"And the second one?"` — names an item in a LIST of earlier
things. Atlas retains the ACTIVE context and the single most recent result, not a
numbered history, and such a turn previously fell through to the generic floor:
the reference was neither resolved nor represented, so the user could not tell
whether Atlas had chosen a referent.

**What was implemented (smallest coherent change).** One bounded handler in
`atlas/conversation/conversation_service.py`
(`_maybe_handle_ordinal_reference`, wired into `send` and `stream` **after** the
existing reference/knowledge/clarification surfaces so every existing route keeps
precedence): for a bounded earlier-item reference surface (`the previous/last/
earlier/first/second/third one|result|subject|…`) it reports the reference as
**UNRESOLVED**, restates the active subject when one exists (otherwise asks for
the item by name), records a bounded
`metadata["reference_clarification"] = {requested, active_subject,
has_prior_context}` for audit, and states that nothing was invented or executed.
No referent is ever invented; nothing is executed, approved or authorized; no
model is contacted.

**Validation.** `tests/test_step7_context_and_reference.py` — 13 passed (five
unresolved earlier-item forms; no-context and with-context replies; no authority
metadata; ordinary turns not claimed; existing demonstrative references and the
Step 5/Step 6 paths untouched; real-kernel continuity → result → unresolved
earlier-item sequence; topic-change safety; live repository untouched). Relevant
regressions: **615 passed, 1 skipped** (Step 2 orchestration, Steps 5 and 6,
reference resolution, conversation state/context, L7 floor, builtin answers,
self-knowledge bridge, G1/G1-routing/G2 gates, open-ended conversation).
Real-kernel validation: **18/18 checks**.

**Known limitations (truthful).** Ordinal references are represented, not
resolved, because Atlas deliberately retains only the active context and the most
recent result (accumulating an unbounded numbered history is not implemented); one
phrasing (`"Tell me about the one we discussed earlier."`) is owned by another
existing kernel surface rather than by this handler; and plural pronoun targets
(`"they"`) with no bounded intent still reach the Step 5 floor. These remain
evidence-driven, separately authorized work — no L11+/G4/C10 or Step 8+ phase is
created or implied.

### 34.12 Step 6 — Intent & goal understanding: bounded multi-intent requests

**Status: COMPLETE (additive, not a roadmap phase).** Step 6 addressed the
limitation §34.11 recorded as truthfully open: *"a partially understood
multi-intent turn can still answer only its first clause without reporting the
unhandled part."*

**What the baseline showed (measured, not assumed).** The limitation was NOT a
language, intent-classification or routing failure — it was a **goal
decomposition** failure. `semantic_frame.decompose` requires every clause to name
a recognised operation, so `decompose("Tell me what you can do and also where the
conversation service lives.")` returned **one** sub-request: the genuine second
reading was never split, and the turn was then answered by whichever surface
matched the first clause, silently discarding the rest. Single-intent turns, the
Step 5 uninterpreted floor, ambiguity clarification and the Step 2 goal
orchestration were all verified to already work and were left untouched.

**What was implemented (smallest coherent extension).**
- `atlas/conversation/semantic_frame.py`: new `split_intents(text)` — a bounded
  coordinator split (`and also`, `and then`, `as well as`, `also`, `plus`, `and`;
  word CLASSES, longest first, at most 4 readings) that reads each clause with the
  EXISTING `interpret` and keeps only clauses that yield a bounded reading
  (domain, operation, subject or a bounded role). It is a *separate* function:
  `decompose` — and therefore Step 2 goal planning — is byte-for-byte unchanged.
- `atlas/conversation/conversation_service.py`: one handler
  (`_maybe_handle_multi_intent`, wired into `send` and `stream` **after** the
  compound/knowledge/clarification surfaces so every existing route keeps
  precedence) that answers each understood clause through the EXISTING builtin
  surface, reports every clause it cannot map as explicitly *not attempted*,
  states that nothing was executed or authorized, and records a bounded
  `metadata["multi_intent"]` = {handled, unhandled} for audit. Governed clauses
  are never answered by this path. It declines (returns ``None``) for
  single-intent turns and when nothing is understood, so the Step 5 floor still
  owns unknown wording.

**Validation.** `tests/test_step6_intent_and_goal_understanding.py` — 19 passed,
1 skipped (bounded coordinator splits; unseen second clauses; clauses the frame
cannot read are never invented; `decompose` unchanged; per-clause answering;
unhandled-portion reporting; no authority metadata; governance clauses not
answered; real-kernel turns). Relevant regressions green (Steps 2 and 5 suites,
L7 cognition floor, builtin state answers, conversation service, self-knowledge
bridge, G1/G1-routing/G2/G3 gates, open-ended conversation, evidence-gap
routing). Real-kernel validation: **21/21 checks** — three unseen multi-intent
requests each answered their understood clause and reported their unhandled
clause; single-intent routing, Step 2 orchestration, the Step 5 floor, ambiguity
clarification and governance all preserved; no approval or promotion created.

**Known limitations (truthful).** Only clauses the shared frame can read count as
separate intents, so a clause with no bounded reading at all (e.g. "who are you"
— the builtin answers it, the frame does not read it) is not split; a multi-clause
turn whose leading clause is a research/goal request is still owned by the
existing goal route, whose report describes its own plan rather than the second
clause; and intents joined without a bounded coordinator are not split. These
remain evidence-driven, separately authorized work — no L11+/G4/C10 phase is
created or implied.

### 34.11 Step 5 — Natural-language understanding: unseen phrasing → bounded meaning

**Status: COMPLETE (additive, not a roadmap phase).** Step 5 advanced the
conversation layer from bounded pattern handling toward scalable interpretation
of *previously unseen* human language, and made the existing semantic
classification visible as truthful conversational meaning.

**What already existed (verified by the Step 5 baseline, not assumed).** The
shared G1 semantic layer (`atlas/conversation/semantic_frame.py`, over the word
CLASSES in `atlas/conversation/lexicon.py`) already turns ordinary utterances
into a bounded, inspectable frame — role, domain (the owning capability),
operation, bounded subject, bounded compound decomposition — and several
genuinely unseen paraphrases already route correctly (`"Spill the beans on what
you're capable of."` → capabilities; `"Which modules make up your conversation
side?"` → architecture self-knowledge; `"Investigate the conversation state
handling and then explain what we should do next."` → the Step 2 orchestration
slice). Ambiguity already reaches the existing clarification seam (`"Handle it."`
→ a bounded request for more detail), and references/follow-ups already resolve
against the retained conversation state. No new engine was added for those.

**The concrete capability gap the baseline demonstrated.** A turn the shared
frame could not map to ANY bounded operation was answered with the
*model-unavailable* floor text (`"I operate deterministically without an external
AI model, so I cannot answer that conversationally yet…"`). That misreported an
**out-of-scope** request as a **missing-model** problem, discarded the
interpretation the semantic layer had just computed (domain `unsupported`,
confidence `0.0`, bounded subject), and said nothing about what the turn *was* or
what Atlas *can* do — the representation of unknown/unsupported input was the
one part of the acceptance surface that was genuinely missing.

**What was implemented (smallest coherent change).** One module-level renderer
`uninterpreted_notice(text)` in `atlas/conversation/builtin_response.py` plus a
single branch in `BuiltinResponseService.respond`: when the intent is
`unsupported` **and** the shared frame shows the turn names no bounded operation
(`domain == unsupported` and no operation), the reply states what was read
(bounded subject), that the request is out of scope rather than a missing-model
problem, restates the bounded capability surface, records the bounded
interpretation in `metadata["frame_interpretation"]`, and states that nothing was
executed. Every other unsupported shape keeps its previous notice verbatim, and
the streaming path is consistent because `respond_stream` delegates to `respond`.
Scope: interpretation only — no routing, no approval, no execution, no promotion,
no model call, no authority, no new engine/planner/store.

**Validation.** `tests/test_step5_natural_language_understanding.py` — 32 focused
tests: truthful representation of unseen out-of-scope wording (content + bounded
`frame_interpretation` metadata + bounded length + determinism), bounded meaning
for unseen paraphrases (domain/operation/confidence/evidence, non-governance-
sensitive), ambiguity → clarification, context-sensitive references, the
preserved unsupported intent/metadata contract, absence of any authority surface,
and real-kernel turns for all of the above. Prior-slice behaviour was unpinned by
nothing: the affected subsystem regressions (L7 cognition floor, builtin state
answers, conversation service, self-knowledge bridge, G1/G2 gates, open-ended
conversation, evidence-gap routing) remained green.

**Known limitations (truthful).** The uninterpreted notice is bounded to
out-of-scope/unknown wording; a *partially* understood multi-intent turn can
still answer only its first clause without reporting the unhandled part, and
correction phrasing beyond the existing bounded markers is not recognised. These
remain evidence-driven, separately authorized work — no L11+/G4/C10 phase is
created or implied, and nothing beyond Step 5 was implemented.

### 34.10 Post-L10 evidence-driven step arc (Steps 1 → 4) — COMPLETE

Four additive, evidence-driven steps were completed after L10. None of them is a
numbered roadmap phase, none introduces a new engine, planner, scheduler,
orchestration engine, memory store, approval system or promotion system, and none
creates or implies an L11+ / G4 / C10 phase.

**Step 1 — Open-ended conversation (COMPLETE).** The existing cognition/model
provider seam is used for genuinely open conversational turns, with Atlas (not any
model) remaining the authority: model output is text only, carries no execution
authority, and the deterministic path is unchanged. Committed at `1132565`.

**Step 2 — Goal-centered orchestration (COMPLETE).** A compound request can be
sequenced as a bounded multi-step goal over **existing** services through the
EXISTING `OrchestrationExecutor`, with explicit typed step kinds and named
injected seams: `INVESTIGATION → ANALYSIS`,
`INVESTIGATION → EVIDENCE_GAP_ANALYSIS`, `KNOWLEDGE → RESEARCH_ANALYSIS`. Result
carry between steps is data-only and bounded (`ExecutionStep.carry_from`, bounded
per-category findings/components/text), the retained plan is the bounded
`ConversationState.current_plan` (no second persistence mechanism), and
multi-turn **plan resumption** re-runs only the incomplete steps while seeding
already-completed ones so their retained bounded result is reused. Composition is
deterministic, D3/local-first knowledge governance is preserved, and every
unknown/insufficient/unwired path fails closed. Committed at `40d1740` and
`e137905`.

**Step 3 — Evidence → self-development (COMPLETE).** For the demonstrated remedy
class (`ConcreteGap` category `untested_component`), a validated evidence gap now
reaches the governed development lifecycle without any new development mechanism:

```
validated ConcreteGap (from a real InvestigationReport via EvidenceGapAnalyzer)
  → DevelopmentNeed                (atlas/evolution/evidence_development.py)
  → component resolved to its real source file
                                  (EXISTING ArchitectureModel / repository map)
  → one deterministic, bounded remedy: a pytest coverage module for that
    component, authored through the EXISTING ChangeSupplier seam
  → EXISTING DevelopmentCycleController → EvolutionProposal + ApprovalRequest
  → PENDING_APPROVAL               (STOP — nothing is approved here)
  → OWNER development approval     (existing ApprovalManager / kernel gate)
  → EXISTING sandbox execution + DevelopmentVerification (VERIFIED required)
  → EXISTING promotion review
  → OWNER promotion approval       (separate decision)
  → EXISTING PromotionExecutor     (the only live-repository writer)
  → persisted proposal/promotion state
```

Two existing defects were corrected on this seam: an already-prepared
(evidence-generated) proposal can now enter the existing governed lifecycle
without re-deriving a different proposal, and the orchestrator's promotion gate
now compares the EXISTING `VerificationStatus` value correctly (a genuinely
`VERIFIED` run previously read as unverified), so a review opened by the
coordinator is actionable. Committed at `2476035`.

**Step 4 — Continuous self-improvement validation (COMPLETE; no production
change).** `tests/test_continuous_self_improvement_validation.py` validates the
whole loop across **two isolated Atlas instances over the same persisted
`EvolutionStorage`**: evidence → gap → OWNER-approved development → sandbox →
`VERIFIED` → OWNER-approved promotion → persisted state → a new instance
re-evaluating the same need → the promoted change is observed by Atlas's own
evidence pipeline (a real `test` finding naming the component) → the original gap
is no longer reported → no redundant development proposal is created. A control
run **without** the promotion still reports the gap and creates a second
proposal, establishing that the closure was caused by the improvement rather than
evaluation drift.

**Scope (explicit).** This is the validated path for the demonstrated evidence-gap
remedy class (`untested_component` → deterministic coverage module). It is **not**
unrestricted autonomous self-development, and it is not a claim that Atlas can
autonomously create arbitrary new capabilities. The capability-activation leg of
self-knowledge remains covered separately by the existing capability-promotion
tests; the Step 4 loop used the coverage-remedy class, which declares no
capability. Governance boundaries demonstrated by the tests: development approval
and promotion approval are separate OWNER decisions, unapproved development does
not execute, promotion before approval is refused, verification is required,
execution stays sandboxed, live writes stay controlled through
`PromotionExecutor`, no permission boundary was expanded, invalid/unknown/
insufficient-evidence/unsupported paths fail closed, and no model or provider
call is required anywhere in this path. **The next step is NOT STARTED** —
further evolution requires validated evidence identifying the next justified
capability gap.

---

*Document created: 2026-08-02 · Authoritative re-write: 2026-08-08 (Track D
implemented & runtime-integrated; schema v10; post-v0.19.1 / unreleased) ·
Release update: 2026-08-09 (Track D released as v0.20; full suite verified:
2973 passed, 57 subtests, 0 failed, 0 errors) · Release update: 2026-08-16
(v0.20.0 released at b92c5d9; 3260 passed, 0 failed, 57 subtests, 2
non-blocking warnings) · Foundation Strengthening: Batch 1 (kernel
decomposition) and Batch 2 (scaffold cleanup) completed. · Track C post-core
follow-ups reconciled: 2026-08-28 (Persistent Learning 5bfa615, deterministic
semantic recall 57f0063, forgetting-policy operationalization be2bb84; schema
v11; no implementation NEXT currently defined). · Conversational Development
Intake (B1+B2+B3) reconciled: 2026-08-29 (committed ce12fb8; schema v11;
B4 remains undefined/unapproved; no implementation NEXT currently defined).
Phase C evidence-driven evolution reconciled: 2026-09-16 (C0 → C9 reached the
established evidence boundary; §31; full suite 5,945 test items executed:
5,876 test cases passed (plus 67 subtests passed), 0 failed, 0 errors, 2
skipped).
Target-state gates G1 → G3 reconciled: 2026-09-25 (G1 — general conversational
understanding; G2 — deep self-knowledge + open-ended knowledge; G3 — governed
self-development: conversational DEVELOPMENT_REQUEST routing through the EXISTING
`DevelopmentDriver` with deterministic bounded scaffold derivation; §33; focused and
regression suites green, no full-suite re-run; no G4 defined or authorized).
Post-L10 conversational validation C1 → C5 reconciled: 2026-09-26 (checkpoint 1 —
conversation architecture research and the investigation-objective correction;
checkpoint 2 — understanding-gap routing corrections; checkpoint 3 — conversation
state/context verification and the bounded follow-up correction; checkpoint 4 —
orchestration/capability-selection trace and the resolved-reference consumer;
checkpoint 5 — end-to-end real-kernel conversational validation and the
external-subject self-knowledge guard. Focused and broader regression subsets were
used (no full-suite re-run); the two documented pre-existing failures were reproduced
against a pristine HEAD and remain unchanged; §34; no L11 defined or authorized).
Post-L10 evidence-driven step arc reconciled: 2026-09-28 (Step 1 open-ended
conversation `1132565`; Step 2 goal-centered orchestration `40d1740` + `e137905`
(three two-stage sequences, bounded carry, bounded retained plan, multi-turn plan
resumption); Step 3 evidence → self-development `2476035`
(`atlas/evolution/evidence_development.py`; validated `untested_component` gap →
`DevelopmentNeed` → resolved real source file → deterministic bounded coverage
remedy through the EXISTING `ChangeSupplier` seam → EXISTING development lifecycle
→ OWNER development approval → sandbox execution → `VERIFIED` → promotion review →
separate OWNER promotion approval → EXISTING `PromotionExecutor`; plus the
already-prepared-proposal entry and the verification-status comparison correction);
Step 4 continuous self-improvement validation `2476035`
(`tests/test_continuous_self_improvement_validation.py`; two isolated Atlas
instances over the same persisted `EvolutionStorage` — the promoted change is
observed by a fresh investigation, the original gap is no longer reported and no
redundant development is created, with a no-promotion control establishing causal
closure; **no production change required**). Focused suites only (Step 3 slices 34 +
20 + 5, Step 4 5; relevant Step 2/evidence regressions green); no full-suite re-run;
no new engine/planner/scheduler/store/authority, no permission expansion, no model
dependency; the validated loop is the demonstrated evidence-gap remedy class, not
unrestricted autonomous self-development; the capability-activation leg remains
covered separately by the existing capability-promotion tests; §34.10; the next step
is NOT STARTED and remains evidence-driven).
Step 5 natural-language understanding reconciled: 2026-09-28 (baseline measured
against the real kernel with unseen phrasing: unseen paraphrases already route
through the shared G1 semantic frame, ambiguity already reaches the clarification
seam, and references already resolve; the demonstrated gap was that a turn mapping
to no bounded operation was answered with the model-unavailable floor text,
misreporting an out-of-scope request as a missing-model problem and discarding the
computed interpretation. Minimal change: `uninterpreted_notice()` in
`atlas/conversation/builtin_response.py` plus one `respond` branch, surfaced only
when the frame shows no bounded operation, with a bounded
`metadata["frame_interpretation"]` record; every other unsupported shape keeps its
notice verbatim and the streaming path is consistent. 32 focused tests plus the
L7 floor/builtin/conversation-service/self-knowledge-bridge/G1–G2/open-ended/
evidence-gap subsystem regressions green; no full-suite re-run; interpretation
only — no routing, approval, execution, promotion, permission or model change;
known limitations recorded in §34.11 (partial multi-intent answers and correction
phrasing beyond the existing bounded markers remain evidence-driven work); §34.11;
the next step is NOT STARTED).
Step 6 intent & goal understanding reconciled: 2026-09-28 (baseline measured the
Step 5 limitation against the real kernel and located its cause precisely: a goal
DECOMPOSITION gap — `semantic_frame.decompose` returned ONE sub-request for a
two-intent turn whose second clause named no recognised operation, so the second
intent was silently absorbed. Minimal change: `semantic_frame.split_intents()` (a
bounded coordinator split over word classes, reusing the EXISTING `interpret` per
clause; `decompose` and Step 2 goal planning untouched) plus one conversation
handler placed after the compound/knowledge/clarification surfaces, which answers
each understood clause through the EXISTING builtin surface, reports every
unmapped clause as explicitly not attempted, and records a bounded
`metadata["multi_intent"]`; no approval, execution, promotion, permission or model
change. 19 focused tests passed (1 skipped) plus the Step 2/Step 5/L7/builtin/
conversation-service/self-knowledge-bridge/G1–G3/open-ended/evidence-gap
regressions green; 21/21 real-kernel validation checks; no full-suite re-run;
known limitations recorded in §34.12 (clauses with no bounded frame reading are
not split; a leading research/goal clause is still owned by the existing goal
route; intents without a bounded coordinator are not split); §34.12; the next step
(Step 7) is NOT STARTED and remains evidence-driven).
Step 7 context & reference understanding reconciled: 2026-09-28 (multi-turn
baseline through the real kernel confirmed the EXISTING reference machinery already
resolves pronouns/demonstratives/location and most-recent-result references against
the retained conversation state; the demonstrated gap was the ORDINAL/earlier-item
class — "What about the previous one?", "And the second one?" — which fell to the
generic floor without being resolved or represented. Minimal change: one bounded
handler (`_maybe_handle_ordinal_reference`, wired after the existing
reference/knowledge/clarification surfaces) that reports the reference as
UNRESOLVED, restates the active subject when one exists, records a bounded
`metadata["reference_clarification"]`, and never invents a referent, executes,
approves or contacts a model. 13 focused tests passed plus 615 relevant
regressions (Step 2 orchestration, Steps 5/6, reference resolution, conversation
state/context, L7 floor, builtin answers, self-knowledge bridge, G1/G2, open-ended
conversation); 18/18 real-kernel validation checks; no full-suite re-run; known
limitations recorded in §34.13 (ordinal references are represented rather than
resolved because no numbered history is retained; one phrasing is owned by another
existing surface; plural pronouns without a bounded intent still reach the Step 5
floor); §34.13; the next step (Step 8) is NOT STARTED and remains
evidence-driven).
Step 8 conversational world state reconciled: 2026-09-28 (multi-turn baseline
through the real kernel confirmed the existing `ConversationState` and reference
machinery already retained/resolved the ACTIVE context and the most recent
result; the demonstrated gap was that ACTIVE and HISTORICAL conversational state
were not distinguished — after a topic switch a prior topic's turn still
competed as an active contextual candidate, so a plain pronoun reference went
AMBIGUOUS and fell to the generic floor, and returning to an earlier topic was
not representable. Minimal change: a bounded, authority-free
`ConversationWorld`/`WorldTopic` representation (`atlas/conversation/world_state.py`)
carried on the existing `ConversationState` as one `world` field, with
deterministic transitions (new topic / continuation / switch / return /
completion / unresolved reference), SUPERSEDED topics excluded from the bounded
contextual reference candidate set, bounded observations at the existing
investigation/knowledge/goal hops, a completed goal marked COMPLETE (distinct
from active), and one `_maybe_handle_topic_return` handler wired after the
existing reference surfaces; no new engine/planner/scheduler/store/authority, no
permission expansion, no routing/approval/execution/promotion change, no model
dependency. 43 focused tests plus relevant subsystem regressions green (Steps
2/5/6/7, reference resolution/consumption/exposure/stream parity, conversation
state/context, L4/L5 retention, L7 floor, builtin answers, self-knowledge bridge,
G1/G1-routing/G2/G3, open-ended conversation, NLU-4/5, architecture-import
guards); the four pre-existing failures were reproduced against a pristine HEAD
and remain unchanged; no full-suite re-run; known limitations recorded in §34.14
(purely textual corrections are represented by the existing `Correction` records
rather than as a world topic; a return to a non-investigation topic is
represented but not independently consumable by the reference-restatement
surface; topic matching is bounded equality/containment, never fuzzy); §34.14;
Steps 1 → 8 are COMPLETE and Step 9 is NOT STARTED and remains evidence-driven).
Step 9 ambiguity & clarification reconciled: 2026-09-28 (multi-turn baseline
through the real kernel confirmed Steps 5-8 already detect a great deal of
ambiguity — frame needs_clarification, resolver AMBIGUOUS, NLU-5 captured-entity
products, the Step 8 ambiguous-topic-return branch, the intake ambiguity gate —
and those were not rebuilt; the demonstrated gaps were (a) a GENERAL contextual
reference ambiguity detected then silently dropped to the model-unavailable
floor, (b) an underspecified investigation request ("Investigate it.") whose
bare-reference object was silently acted on, and (c) clarifications that could
not be resolved because the candidates were not preserved. Minimal change: a
bounded authority-free `PendingClarification` (`atlas/conversation/clarification.py`)
carried on the existing `ConversationState` as one `pending_clarification` field,
with deterministic candidate matching (containment / explicit ordinal /
distinctive tokens); the general contextual-ambiguity and underspecified-
investigation cases now ask for clarification and record the outstanding
ambiguity (no candidate invented when none exists); and one
`_maybe_resolve_clarification` handler, wired before every other surface,
resolves a candidate-selection reply deterministically and resumes the correct
route (topic reactivation / reference restatement), clears on a genuine new
request, and keeps an unresolved reply open. 39 focused tests plus relevant
subsystem regressions green (Steps 2/5/6/7/8, reference resolution/consumption/
exposure/stream parity, conversation state/context, L4/L5 retention, L7 floor,
builtin answers, self-knowledge bridge, G1/G1-routing/G2/G3, open-ended
conversation, NLU-4/5, entity identification, orchestration/goal slices, D1-D4,
semantic-gap routing, evidence improvements, lexical/whitespace normalisation,
architecture-import guards); the pre-existing failures (qualifier aliases, the
"Run it" orchestration gate, the architecture question, the L9 confirmation
scenario, the P15.2 continuity case, two lexical canonicalisation cases) were
reproduced against a pristine HEAD and remain unchanged; no full-suite re-run;
known limitations recorded in §34.15 (the missing-subject case requests the
information and clears on the next turn rather than reconstructing the
operation; a clarification whose candidates are not selectable by name/ordinal/
distinctive token stays open; matching is bounded, never fuzzy); §34.15;
Steps 1 → 9 are COMPLETE and Step 10 is NOT STARTED and remains evidence-driven).
Step 10 multi-intent & multi-step understanding reconciled: 2026-09-28
(multi-turn baseline through the real kernel confirmed Step 6 reads only casual
multi-intent turns and the Step 2 goal plan composes only a fixed closed set of
two-stage slices — neither rebuilt; the demonstrated gap was that a multi-intent/
multi-step OPERATIONAL request was handed to a single operational route that
acted on the whole sentence and silently dropped the other intents, explicit
sequencing ("first … then …") was not split, a dependent
"investigate X and then analyze the findings" fired over stale evidence, and a
single multi-clause intent was over-split. Minimal change: a bounded authority-
free representation (`atlas/conversation/multi_step.py` — ordering-aware
`split_clauses`, closed `_classify`, `build_multi_step` with order only when
expressed and a `"result"` dependency only when justified, and
`build_execution_steps`), one `_maybe_handle_multi_step` handler that runs the
runnable read-only steps through the EXISTING orchestration bridge (the same
mechanism Step 2 uses), answers CASUAL clauses through the EXISTING builtin
surface and reports every other step truthfully (unsupported/governed/blocked),
plus two minimal precedence guards (evidence-gap-analysis declines a genuine
multi-step request; the Step 2 goal route declines a turn with more intents than
its plan covers) and an anti-over-split rule in `split_intents`. 39 focused tests
plus relevant subsystem regressions green (Step 2 orchestration/goal slices/
resumption/gap, Steps 5/6/7/8/9, reference resolution/consumption/exposure/stream
parity, conversation state/context, L4/L5 retention, L7 floor, builtin answers,
self-knowledge bridge, G1/G1-routing/G2/G3, open-ended conversation, NLU-4/5,
entity identification, D1-D4, semantic-gap routing, evidence improvements,
lexical/whitespace normalisation, architecture-import guards); the pre-existing
failures were reproduced against a pristine HEAD and remain unchanged; no
full-suite re-run; known limitations recorded in §34.16 (research-led compound
shapes keep the existing compound route; a plain-`and` clause without a bounded
operation is not separated; bounded order/result cues are required to represent
order/dependency); §34.16; Steps 1 → 10 are COMPLETE and Step 11 is NOT STARTED
and remains evidence-driven).
Step 11 natural response generation reconciled: 2026-09-28 (the real-kernel
baseline showed the many existing response surfaces already natural enough and
did NOT rebuild them; the demonstrated gap was the step/outcome report — it
echoed the whole request back ("Done: <whole sentence>"), exposed internal step
ids ("step-0000") and internal targets ("retrieve"/"synthesize") as results,
duplicated the target as the "output", and always printed internal attribution
("Executed as: owner (owner)."). Minimal change: a bounded, deterministic,
model-free response-realization layer (atlas/conversation/response_layer.py) that
renders each step with a human kind label + the recorded subject + the recorded
state + its OWN recorded result (or recorded reason on non-success), and the
existing orchestration_result_to_message now delegates its content to it while
keeping the orchestration metadata byte-for-byte unchanged; no new engine/store/
world-state, no model call, no invented fact/action/authority. 22 focused tests
plus relevant subsystem regressions green (Step 2 goal slices/resumption/gap/
research-slice orchestration, conversation/checkpoint orchestration, the
orchestration executor and reporting boundary parity, experience capture bridges,
Steps 5/6/7 and 8/9/10, validating knowledge/target-state surfaces); the
pre-existing failures were reproduced against a pristine HEAD and remain
unchanged; no full-suite re-run; known limitations recorded in §34.17 (the layer
presents what the deterministic outcome recorded — an upstream interpretation
oddity is faithfully reported rather than masked — and a few surfaces keep their
own pinned wording); §34.17; Steps 1 → 11 are COMPLETE and Step 12 is NOT STARTED
and remains evidence-driven).
Step 12 unified capability model reconciled: 2026-09-28 (the real-kernel baseline
confirmed Atlas already had a canonical CapabilityModel projected from the
authoritative registries — NOT rebuilt — but it modelled only the registered
implementation surface: the OPERATIONAL (conversational) abilities had no
identity, so capability_contract("investigation") returned found=False and the
conversational capability inventory disagreed with the canonical model. Minimal
change: a bounded, deterministic, evidence-grounded operational capability
catalogue (atlas/self_knowledge/operational_capabilities.py) merged additively
into the EXISTING canonical model (CapabilityKind.OPERATIONAL, category/
operations fields, operational_count, optional operational_capabilities input),
with availability grounded in actual wiring (the model-backed open conversation
and governed capabilities are truthfully unavailable when unwired); the kernel
capability_model(include_operational=True) is the unified view and
capability_contract resolves operational capabilities, while the architecture
model keeps the registered-only structural projection. 24 focused tests plus
relevant subsystem regressions green (capability model/contracts/architecture
model, the CLI capability surface, builtin state answers, C3/C4.1/C5
self-knowledge surfaces, the self-knowledge bridge, the kernel suite); the
pre-existing failures were reproduced against a pristine HEAD and remain
unchanged; no full-suite re-run; known limitations recorded in §34.18 (the
catalogue is a bounded explicit list; registered-only projection retained for the
architecture mapping; no test/promotion-derived capability evidence yet); §34.18;
Steps 1 → 12 are COMPLETE and Step 13 is NOT STARTED and remains evidence-driven).
Step 13 capability state & self-knowledge reconciled: 2026-09-28 (the real-kernel
baseline showed the Step 12 model exposed definitions and a coarse availability
but no grounded STATE: a structural external-model-dependent capability
(ai_chat/model_routing) reported available while the operational
open_conversation — the same dependency class — reported unavailable, and
capability-state questions were misrouted or unsupported. Minimal change:
CapabilityState (available/unavailable/partially_supported/blocked/governed/
unknown) plus bounded grounded entry fields (state/reason/blocked_by/governing)
and model-level state_counts, derived in one deterministic post-pass from the
SAME evidence the model already projected, with a new external_model_available
input (default True → existing callers unchanged) that makes an
external-model-dependent capability truthfully unavailable without a provider; a
bounded `requires` field grounds prerequisites so a blocked dependency is
represented; the kernel model/contract pass the grounded fact; and a bounded
conversation capability-STATE question surface answers is-available / status /
why-can't / can-you / which-are-unavailable from the SAME model, declining
unknown names (fail closed) so real requests are never hijacked. 26 focused
tests plus relevant subsystem regressions green (capability model/contracts/
architecture model, CLI capability surface, builtin state answers, the Step 12
suite, C3/C4.1/C5 self-knowledge surfaces, self-knowledge bridge, kernel suite,
capability routing/execution, conversation service, import scans); the
pre-existing failures were reproduced against a pristine HEAD and remain
unchanged; no full-suite re-run; known limitations recorded in §34.19 (state is
not derived from test coverage or promotion history; the prerequisite set is an
explicit grounded list; no retired state is used; only the bounded
state-question forms are recognised); §34.19; Steps 1 → 13 are COMPLETE and
Step 14 is NOT STARTED and remains evidence-driven).
Project Atlas — docs/ATLAS_STATE.md. This document is the authoritative
current architecture handbook and replaces all earlier ATLAS_STATE revisions.*
