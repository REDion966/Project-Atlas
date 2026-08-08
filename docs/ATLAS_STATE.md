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
| Released baseline | **v0.19.1** (stable; Track C runtime-integrated) |
| Current HEAD | `35299c7` (branch `phase5-memory-evolution`) |
| In-development work | **Track D — Advanced Reasoning** (post-`v0.19.1`) |
| Track D release | **Unreleased** — no `v0.20` exists in git history |
| Current schema version | **10** |
| Intelligence level | Level 5 — Persistent Self-Model (Level 6+ Bounded Autonomy via Phase 16) |
| Era | **Capability Track Era** |

**CURRENT IMPLEMENTATION:** Track D is implemented and runtime-integrated, but it
is **post-`v0.19.1` and therefore unreleased**. Do not claim a `v0.20` release.

---

## 3. Current Implementation Milestone

The current milestone is **Track D — Advanced Reasoning**, implemented as an
additive capability track on top of the locked core (`v0.19.1` baseline), with a
private kernel-owned service, `reasoning_*` persistence (schema **v10**), and
governed ingestion (**GOV-011**).

### Track Status Summary

| Track | Capability | Status | Baseline |
|---|---|---|---|
| **A** | Research & Knowledge | **COMPLETE** | `v0.17.0` (Phase 17) |
| **B** | Tool Ecosystem | **COMPLETE** | `v0.18.0` (Phase 18) |
| **C** | Long-Term Learning | **COMPLETE & runtime-integrated** | `v0.19.1` (Phase 19) |
| **D** | Advanced Reasoning | **IMPLEMENTED & runtime-integrated** | post-`v0.19.1` (unreleased) |

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

### 3.4 Track D — Advanced Reasoning (IMPLEMENTED & runtime-integrated)
See §18–§20 for the full architecture description.

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

### 5.2 RuntimeCoordinator
`atlas/runtime/runtime_coordinator.py` is the single permanent orchestrator of
the 14-stage cognitive pipeline:

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

**`CURRENT_SCHEMA_VERSION = 10`** (`atlas/storage/migration.py`).

This is confirmed by source and by the migration tests
(`test_evolution_autonomy_storage`, `test_evolution_persistence`,
`test_experience_storage`, `test_longterm_storage`,
`test_understanding_storage`), which assert schema version **10** after the
Track D additive `reasoning_*` tables.

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
`memory` (C), `evolution`, `goal`.

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

**Verified Track D Batch 2 execution** (decision-gate result, ~9 minutes):

```
2973 passed
57 subtests passed
0 failed
0 errors
```

> **Precision rule:** Only an actually-executed number may be stated as a test
> result. The figure above is the verified execution for Track D Batch 2. Any
> snapshot from the Phase 1 repository inventory is a **"current test
> inventory"**, not a result — do not call an inventory count a passing test
> count.

**Current test inventory (not a result):** 178 test files, 766 test classes,
2958 test methods (+ parameterized subtests).

Track D test coverage includes: storage, CLI, capability handlers, service,
trace recorder, repositories, causal/hypotheses/verify/meta engines, models,
protocols, wiring, evolution integration, import-boundary scans, and
kernel integration.

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
- `atlas/runtime/` — RuntimeCoordinator (14-stage order)
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

- **`reasoning.ingest` sink is not wired at runtime.** The
  `ReasoningIngestBridge` is constructed without a real governed sink, so
  `reasoning.ingest` fails closed until the kernel wires a real sink into the
  Phase 16 schedule-store/dispatcher queue. Reasoning artifacts are persisted
  regardless; only *ingestion of distilled insights into Atlas state* is
  deferred.
- Track A deferred follow-ups: knowledge-graph expansion, web adapter,
  coordinator implementation.
- Track B deferred follow-ups: skill authoring, PARALLEL/CONDITIONAL execution,
  learned-skill promotion.
- Track C deferred follow-ups: feeding episodic context into working memory /
  `ContextEngine` (requires RuntimeCoordinator review), semantic memory
  upgrades, forgetting-policy tuning.
- Phase 16: boot activation of staged config + SAFE_MODE rollback are part of
  the governed-autonomy design but remain governed-path behavior; CODE scope is
  unreachable by constitutional design.

## 20. Current Known Limitations

- CODE scope (`CODE_ARTIFACT`, `AUTONOMOUS` levels) is **unreachable** — Atlas
  does not autonomously modify source code or its identity.
- No distributed / multi-process execution (single-process assumption).
- No autonomous reflection/strategy adjustment without approval.
- Large-model enhancement in Track D is optional and protocol-injected; the
  deterministic engine is the primary mechanism.
- `docs/CHANGELOG.md` is not maintained past the early releases; git history is
  the authoritative change log for later work.

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

---

*Document created: 2026-08-02 · Authoritative re-write: 2026-08-08 (Track D
implemented & runtime-integrated; schema v10; post-v0.19.1 / unreleased) ·
Project Atlas — docs/ATLAS_STATE.md. This document is the authoritative current
architecture handbook and replaces all earlier ATLAS_STATE revisions.*
