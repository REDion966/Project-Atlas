# ATLAS STATE — Authoritative Current Architecture Handbook

**Canonical entry point for all future Atlas development.**

This document is the single source of truth for the **current** state of the
Project Atlas codebase. Future implementation prompts should say: *"Read
ATLAS_STATE.md and only the files directly related to the task."*

---

## 0. Source of Truth & Document Authority

Priority order when interpreting Atlas:

1. **Source code** — actual runtime behavior truth
2. **Git history** — completed milestones, releases, and implementation record
3. **`ATLAS_STATE.md`** *(this file)* — current authoritative state
4. **`ROADMAP.md`** — authoritative forward direction
5. **Historical / archived documents** (`docs/archive/`) — reference only; NEVER
   treated as current architecture

If source code and this document conflict, source code wins. Report the
conflict and preserve backward compatibility; never silently choose one over
the other.

> **Rule for future AI agents:** archived documents (`docs/archive/`) describe
> how Atlas looked at earlier points in time. They are historical context, not
> current architecture. Do not reintroduce archived designs without an explicit
> new decision.

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
| Current HEAD | `be2bb84` (branch `phase5-memory-evolution`) |
| In-development work | **Foundation Strengthening** — post-release architectural hardening (Batch 1: kernel composition-root decomposition; Batch 2: scaffold/legacy cleanup), the **Stage A1→H guided self-improvement thread** (see §27), and the completed **Track C post-core follow-ups** — Persistent Learning, deterministic semantic recall, forgetting-policy operationalization (see §28–§29) |
| Track D release | **Released in v0.20** (tag `v0.20` exists in git history) |
| Current schema version | **11** |
| Intelligence level | Level 5 — Persistent Self-Model (Level 6+ Bounded Autonomy via Phase 16) |
| Era | **Capability Track Era** |

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

## 3. Current Implementation Milestone

The current milestone is **Phase 22 — Toolchain Execution & Learned-Skill
Progression**, the FINAL numbered implementation phase for Atlas Core. Phase 22
completed the recorded Track B NEXT items — CONDITIONAL execution, PARALLEL
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
- Adds `reasoning_*` tables via the shared migration framework ->
  **schema version 10**
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
> result. The figure above is the verified execution for Track D Batch 2. Any
> snapshot from the Phase 1 repository inventory is a **"current test
> inventory"**, not a result — do not call an inventory count a passing test
> count.

**Verified Track D Batch 2 execution** (decision-gate result, ~9 minutes):

```
2973 passed
57 subtests passed
0 failed
0 errors
```

**Verified post-core release gate (HEAD `b2b4674`, v0.20.0 preparation):**

```
3260 passed
57 subtests passed
0 failed
2 warnings (non-blocking asyncio.iscoroutinefunction deprecations)
```

**Current test inventory (not a result):** 178 test files, 766 test classes,
2958 test methods (+ parameterized subtests).

Track D test coverage includes: storage, CLI, capability handlers, service,
trace recorder, repositories, causal/hypotheses/verify/meta engines, models,
protocols, wiring, evolution integration, import-boundary scans, and
kernel integration.

**Verified Track C post-core follow-up executions:** deterministic semantic
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
The authoritative specification is `docs/PHASE_22_DESIGN.md`.

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

## 25. Post-Core Adaptation Foundation (F1–F6) — working tree

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

*Document created: 2026-08-02 · Authoritative re-write: 2026-08-08 (Track D
implemented & runtime-integrated; schema v10; post-v0.19.1 / unreleased) ·
Release update: 2026-08-09 (Track D released as v0.20; full suite verified:
2973 passed, 57 subtests, 0 failed, 0 errors) · Release update: 2026-08-16
(v0.20.0 released at b92c5d9; 3260 passed, 0 failed, 57 subtests, 2
non-blocking warnings) · Foundation Strengthening: Batch 1 (kernel
decomposition) and Batch 2 (scaffold cleanup) completed. · Track C post-core
follow-ups reconciled: 2026-08-28 (Persistent Learning 5bfa615, deterministic
semantic recall 57f0063, forgetting-policy operationalization be2bb84; schema
v11; no implementation NEXT currently defined). Project Atlas —
docs/ATLAS_STATE.md. This document is the authoritative current architecture
handbook and replaces all earlier ATLAS_STATE revisions.*
