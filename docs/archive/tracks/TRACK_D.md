# Atlas Capability Track D — Advanced Reasoning

> HISTORICAL DOCUMENT — This track record is preserved for historical/design reference. The current implementation status is maintained in `docs/ATLAS_STATE.md` and `docs/ROADMAP.md`.

**Status:** Design phase (pending approval) · **Version tag:** n/a (design only; current baseline v0.19.1) · **Integration:** Additive, no locked-component redesign

---

## 0. Convention

This document distinguishes two kinds of content:

- **[FACT]** — confirmed by `docs/ATLAS_STATE.md`, `docs/ATLAS_CORE.md`, `docs/ATLAS_VISION.md`, `docs/ARCHITECTURE.md`, or existing source code.
- **[DESIGN]** — a proposal by this document. **Design** entries are not project facts. They require approval before implementation and must not be confused with confirmed architecture.

If any **[DESIGN]** entry conflicts with a future authoritative document, the future documented architecture wins and this document must be revised.

---

## 1. Overview

Track D delivers the advanced-reasoning layer: **multi-step reasoning** (deterministic decomposition of complex queries into chained inference steps), **causal/counterfactual reasoning** (what-if analysis over the existing world model and knowledge), **hypothesis generation** (competing explanations for an observation/claim, ranked deterministically), **self-verification** (step-level consistency and support checking of reasoning outputs), and **meta-reasoning** (strategy selection and effectiveness tracking over reasoning trace history). Reasoning artifacts are persisted, exposed as capability handlers, and distilled insights enter Atlas state only through the governed Evolution Framework.

Atlas's intelligence lives in the pipeline, not the LLM prompt: the deterministic reasoning core is the primary engine, and models are optional, protocol-injected enhancers (the same relationship Track A established with `ExtractionModel`/`VerificationModel`).

### 1.0 Explicitly out of scope for Track D

- **No changes to `atlas/reasoning/`.** The core reasoning package (controller, models, capabilities, execution registry/routing/dispatch, planning, reflection, outcomes) is Core and locked. Track D is a separate package that may *consume* `ReasoningRecorder` output additively but never modifies or imports `atlas/reasoning/` internals beyond its stable public models.
- **No RuntimeCoordinator pipeline change.** The fixed stage order (including the REASONING stage) is locked; Track D is an additive consumer and capability provider, not a pipeline modification.
- **No changes to `atlas/cognition/` or `atlas/ai/`.** No new pipeline stage, no provider changes, no modifications to `_build_cognitive_context`.
- **No LLM-only chain-of-thought as the core mechanism.** Reasoning is deterministic pipeline logic; LLM enhancement is optional and protocol-injected only.
- **No autonomous reasoning-strategy mutation.** Strategy updates/recommendations are proposals; applying them is governed and requires approval.
- **No CODE scope / no code generation.** Reasoning may analyze code, never generate or apply it.
- **No distributed or parallel reasoning execution.** Single-process assumption maintained.
- **No changes to existing public APIs, service keys, models, or protocols.** Only new additive APIs/surfaces are introduced.

[FACT] ATLAS_STATE.md §13 lists Track D as: "*Advanced Reasoning* — Multi-step reasoning, causal/counterfactual reasoning, hypothesis generation, self-verification, meta-reasoning." [FACT]

[FACT] ATLAS_STATE.md marks `atlas/reasoning/` as "Core, pure logic" — locked against redesign, extend additively only. [FACT]

[FACT] The RuntimeCoordinator executes the cognitive pipeline in a fixed order and publishes `runtime.pipeline.completed` on the EventBus at the end of `process()`. [FACT — source: `atlas/runtime/runtime_coordinator.py`]

[DESIGN] This document is the design proposal. It does not modify any source file.

### 1.1 Goals

1. Deterministic multi-step reasoning that decomposes complex inputs into explicit, auditable inference steps — each step bound to available evidence.
2. Causal analysis and counterfactual ("what-if") evaluation built on the existing world model and knowledge surfaces via injected protocols.
3. Competing-hypothesis generation with deterministic ranking, so Atlas can reason about alternative explanations rather than committing to a single answer.
4. Self-verification of reasoning outputs: step-level premise usage, circularity, internal contradiction, and support-from-evidence checks, with confidence calibration.
5. Meta-reasoning: record reasoning traces, score strategy effectiveness, and surface deterministic recommendations for Reflection/Evolution evidence — without mutating strategy state directly.
6. Persistence of reasoning artifacts (traces, steps, hypotheses, verifications, meta-assessments) via additive storage.
7. Capability handlers (`reasoning.*`), CLI surface, and governed distillation of reusable strategy insights (GOV-011) following the established Track A/B/C pattern.

### 1.2 Intended data flow

```
CognitionDecision / question / claim
        ↓ MultiStepReasoner [DESIGN]
ReasoningTrace (steps, strategy, evidence bindings)
        ├─ CausalReasoner [DESIGN]      — causal graph traversal (world-model protocol)
        ├─ ↳ counterfactual evaluation  — assumption-swap re-evaluation
        ├─ HypothesisGenerator [DESIGN] — competing hypotheses + deterministic ranking
        └─ SelfVerifier [DESIGN]        — step-level consistency/support + calibration
                ↓ MetaReasoningEngine [DESIGN]  (consumes trace history + ReasoningRecorder outcomes)
MetaAssessment (strategy effectiveness, recommendations)
        ├─ AdvancedReasoningSQLiteStorage [DESIGN] — reasoning_* tables (migration v10)
        ├─ Observation evidence (RUNTIME_METRICS, reasoning:*) — Evolution evidence [DESIGN]
        └─ ReasoningInsight → EvolutionRequest (KNOWLEDGE) → governed sink (GOV-011) [DESIGN]
Capability handlers reasoning.trace|causal|counterfactual|hypotheses|verify|meta|ingest [DESIGN]
Component metadata + CLI `atlas reasoning ...` [DESIGN]
```

---

## 2. Confirmed Facts vs. Design Decisions

### 2.1 Confirmed facts [FACT]

| # | Fact | Source |
|---|------|--------|
| 1 | `atlas/reasoning/` is Core, pure logic; reasoning controller, capabilities, execution registry/routing/dispatch, planning, reflection, outcomes live there | ATLAS_STATE.md §3 |
| 2 | Stage REASONING (Stage 6 in `RuntimeCoordinator`) builds a `CognitionDecision`, creates a `ReasoningPlan`, analyzes/routes/dispatches capabilities, and records outcomes via `ReasoningRecorder`; the pipeline order is locked | Source: `atlas/runtime/runtime_coordinator.py`; ATLAS_STATE.md §1.4 |
| 3 | `CapabilityRegistry.register(name, handler)` is the additive registration surface; track factories (Track A `research.*`, B `toolchain.*`, C `memory.*`) register handlers at `Atlas.start()` | ATLAS_STATE.md §6.1; `atlas/reasoning/execution/registry.py` |
| 4 | `ReasoningRecorder.recent(n)` is an existing public read API (ReflectionEngine consumes it in the locked pipeline) | Source: `atlas/runtime/runtime_coordinator.py` `_stage_reflection` |
| 5 | `RuntimeCoordinator.process()` publishes `runtime.pipeline.completed` on the EventBus after the pipeline finishes | Source: `atlas/runtime/runtime_coordinator.py` |
| 6 | Track C proved the additive-consumer pattern: `EpisodicRecorder` subscribes to `runtime.pipeline.completed` via kernel wiring — no pipeline change | Source: `tests/test_kernel_longterm_integration.py`; `atlas/longterm/` |
| 7 | Pure logic layers must never import kernel, runtime, dispatcher, gateway, AI providers, EventBus, or scheduler; storage adapters are the only modules importing `sqlite3` | ATLAS_STATE.md §12 |
| 8 | All state mutation flows through `EvolutionExecutionGateway.execute_request()`; KNOWLEDGE scope → INFORMATION level (GOV-004); MEMORY scope → INFORMATION level; governed sink pattern established by Tracks A/B/C (GOV-008/009/010) | ATLAS_STATE.md §1.4, §10 |
| 9 | Storage is additive-only; shared SQLite DB `atlas_data/atlas_experience.db`; migration framework currently at schema v9 (Track C added migration 9) | ATLAS_STATE.md §7; `atlas/storage/migration.py`; `docs/TRACK_C.md` |
| 10 | Environment provides reusable evidence/protocol surfaces: `WorldModelEngine` (causal graph/entities), `KnowledgeManager` (ranked query), `ExperienceRepository`/`StructuredExperience`, `ReasoningRecorder` outcomes, `SelfObservationEngine` observations | ATLAS_STATE.md §3, §8, §9 |
| 11 | Track A/B/C established the module pattern: models → catalog → planner/executor → storage protocol → capability handlers → evolution bridge → wiring → CLI | `docs/TRACK_A.md`, `docs/TRACK_B.md`, `docs/TRACK_C.md` |
| 12 | Full suite at v0.19.1: 2619 passed, 57 subtests passed, 0 failures | ATLAS_STATE.md §2 |

### 2.2 Design decisions [DESIGN]

| # | Decision | Rationale |
|---|----------|-----------|
| D1 | New package `atlas/advanced_reasoning/` | Mirrors self-contained track packages (`atlas/longterm/`); keeps locked `atlas/reasoning/` untouched |
| D2 | No changes to `atlas/reasoning/`, `atlas/cognition/`, `atlas/ai/` | Track D is additive-only; consumes public outputs (`ReasoningRecorder.recent`, pipeline event) without modifying them |
| D3 | Deterministic reasoning core; model enhancement optional via injected protocols (`ReasoningModel`, `VerificationModel`, `HypothesisModel`) | Matches "LLM is the voice, not the brain" and Track A `ExtractionModel`/`VerificationModel` precedent |
| D4 | Capability names `reasoning.*` | Naming convention consistent with `research.*`, `toolchain.*`, `memory.*` (naming still open — Q3) |
| D5 | Additive migration v10 for `reasoning_*` tables | Adheres to additive-only storage policy |
| D6 | `AdvancedReasoningSQLiteStorage` is the only new module importing `sqlite3` | Matches Track A/B/C |
| D7 | Governed distillation via new GOV-011 (KNOWLEDGE scope) | Mirrors GOV-008/009/010; scope choice is open (Q6) |
| D8 | `ReasoningTraceRecorder` is an additive event-bus consumer (kernel-wired subscription to `runtime.pipeline.completed`) | Proven by Track C EpisodicRecorder; no pipeline change |
| D9 | `MetaReasoningEngine` additively consumes `ReasoningRecorder.recent(n)` | Same read API ReflectionEngine already uses; no modification |
| D10 | CLI `atlas reasoning ...`, presentation-only except governed `ingest` | Matches Track A/B/C CLI pattern (naming open — Q4) |
| D11 | Repositories bounded in-memory with dual-write best-effort to storage | Mirrors Track C `EpisodicRepository`/`ProceduralRepository` degradation pattern |
| D12 | Capability handlers are the only runtime-invocation surface; no service-locator or direct service access from pure logic | Preserves DI and layered rules |

---

## 3. Architecture

### 3.1 Dependency direction (pure → infrastructure)

```
atlas/advanced_reasoning/models.py            — frozen dataclasses + enums [DESIGN]
atlas/advanced_reasoning/catalog.py           — strategy names, defaults, thresholds [DESIGN]
atlas/advanced_reasoning/multi_step.py        — MultiStepReasoner (pure) [DESIGN]
atlas/advanced_reasoning/causal.py            — CausalReasoner (pure) [DESIGN]
atlas/advanced_reasoning/hypotheses.py        — HypothesisGenerator (pure) [DESIGN]
atlas/advanced_reasoning/verify.py            — SelfVerifier (pure) [DESIGN]
atlas/advanced_reasoning/meta.py              — MetaReasoningEngine (pure) [DESIGN]
atlas/advanced_reasoning/trace_repository.py  — ReasoningTraceRepository (pure, bounded, dual-write) [DESIGN]
atlas/advanced_reasoning/trace_recorder.py    — ReasoningTraceRecorder (pure; event-triggered builder) [DESIGN]
        │ (pure)
atlas/advanced_reasoning/protocols.py         — ReasoningModel / VerificationModel / HypothesisModel /
                                                 EvidenceProvider / CausalGraphProvider protocols [DESIGN]
atlas/advanced_reasoning/service.py           — AdvancedReasoningService (DI composition; no infra imports) [DESIGN]
atlas/advanced_reasoning/storage_protocol.py  — AdvancedReasoningStorage protocol [DESIGN]
atlas/advanced_reasoning/capability_handlers.py — reasoning.* capability handlers (pure bridges) [DESIGN]
atlas/advanced_reasoning/evolution_integration.py — governed ingest bridge + GOV-011 [DESIGN]
atlas/advanced_reasoning/wiring.py            — ComponentMetadata + GOV-011 registration [DESIGN]
atlas/advanced_reasoning/cli_commands.py      — presentation wrappers [DESIGN]
        │ (infrastructure / presentation)
atlas/storage/advanced_reasoning_storage.py   — AdvancedReasoningSQLiteStorage (migration v10) [DESIGN]
atlas/cli/main.py                             — `atlas reasoning ...` subcommands [DESIGN]
```

### 3.2 Pure-logic isolation

[FACT] Pure logic layers must not import kernel, runtime, dispatcher, scheduler, gateway, storage, events, or AI providers (ATLAS_STATE.md §12). [FACT]

[DESIGN] All pure modules in `atlas/advanced_reasoning/` follow this rule. `AdvancedReasoningSQLiteStorage` is the only new module importing `sqlite3`. The evolution bridge never calls `EvolutionExecutionGateway.execute_request()` directly; an injected governed sink is the sole hand-off point (same discipline as Track A `ResearchIngestSink`, Track B `ToolchainIngestSink`, Track C `LongTermIngestSink`). The service never imports the EventBus; kernel wiring subscribes the trace recorder to `runtime.pipeline.completed`. [DESIGN]

### 3.3 Prohibited imports inside `atlas/advanced_reasoning/`

[FACT] Pure logic layers must never import kernel, runtime, dispatcher, gateway, AI providers, EventBus, or scheduler (ATLAS_STATE.md §12). [FACT]

[DESIGN] Additionally, to keep the two reasoning packages decoupled, pure Track D modules must **never import `atlas.reasoning` implementation modules** (controller, capabilities, execution, planning, reflection, outcomes). The only allowed contact with the existing reasoning stack is through injected public outputs (`ReasoningRecorder` instances injected by the kernel) and the documented `runtime.pipeline.completed` event trigger. The import-confusion risk between `atlas/reasoning/` (locked core) and `atlas/advanced_reasoning/` (track) is mitigated by this rule; a prohibited-import scan test is proposed in §13. [DESIGN]

### 3.4 Existing reusable infrastructure

[DESIGN] Track D reuses the following existing surfaces through constructor injection at the kernel boundary — no module in `atlas/advanced_reasoning/` imports them directly:

| Existing surface | Reuse in Track D |
|---|---|
| `KnowledgeManager.query` | Backs the injected `EvidenceProvider` (evidence for hypothesis scoring and verification support checks) |
| `WorldModelEngine` | Backs the injected `CausalGraphProvider` (causal paths + counterfactual evaluation; never mutated) |
| `ReasoningRecorder` (`recent(n)`, `count`, `summary`) | Read-only input to `MetaReasoningEngine` for strategy-effectiveness scoring |
| `ExperienceRepository` / `StructuredExperience` | Optional evidence feed for trace metadata and verification support aggregation |
| `runtime.pipeline.completed` event | Existing EventBus trigger for the additive `ReasoningTraceRecorder` consumer (kernel-wired, Track C precedent) |
| `CapabilityRegistry.register(name, handler)` | Additive registration surface for the `reasoning.*` capability handlers |

[DESIGN] This mirrors the Track A/B/C consumption pattern (`research_*`, `toolchain_*`, `memory_*` all build on existing kernel services without importing them). [DESIGN]

---

## 4. Pipeline

| Phase | Component | Responsibility | Deterministic |
|---|---|---|---|
| D.1 | `ReasoningTrace`, `ReasoningStep`, `HypothesisSet`, `VerificationReport`, `MetaAssessment`, enums | Pure data containers + serialization (`to_dict`) | Yes |
| D.2 | `STRATEGIES`, defaults (max steps, depth, thresholds, ranking weights) | Shared constants for planners/verifier/meta | Yes |
| D.3 | `MultiStepReasoner` | `question/claim → ReasoningTrace`: structural decomposition (conjunctions, goal markers, entity/evidence binding), step chaining with dependency links, confidence propagation | Yes (timestamps aside) |
| D.4 | `CausalReasoner` | Causal path traversal over injected `CausalGraphProvider`; `counterfactual(event, assumption)` swaps/removes a condition edge and re-evaluates reachability/effect — never mutates the graph | Yes on graph state |
| D.5 | `HypothesisGenerator` | Competing hypotheses from contrast/template families (direct, inverse, alternative-cause, mediating-cause), scored by support/coverage from injected evidence, ranked | Yes |
| D.6 | `SelfVerifier` | Step-level checks: premise usage, circularity, contradiction between steps, support from evidence, confidence calibration; optional `VerificationModel` for semantic checks | Yes without model; model fallback-safe |
| D.7 | `MetaReasoningEngine` | Scores strategy effectiveness (success rate, latency, verification pass rate) from trace history + `ReasoningRecorder.recent(n)`; deterministic recommendations | Yes |
| D.8 | `ReasoningTraceRepository` | Bounded in-memory store for traces/hypotheses/verifications/meta; dual-write to injected storage (best-effort) | Yes |
| D.9 | `ReasoningTraceRecorder` | Pure builder: derives a `ReasoningTrace` from post-pipeline outcomes; triggered by the kernel-wired `runtime.pipeline.completed` subscription (Track C precedent) | Yes |
| D.10 | `AdvancedReasoningSQLiteStorage` | Additive `reasoning_*` tables in shared DB (migration v10) | — |
| D.11 | `reasoning.trace/causal/counterfactual/hypotheses/verify/meta/ingest` | Capability-registry-compatible handlers routing to the track service | Yes (times aside) |
| D.12 | `AdvancedReasoningEvolutionTracker` + `AdvancedReasoningIngestBridge` | Builds INFORMATION-scope KNOWLEDGE `EvolutionRequest` for distilled strategy insights; emits Observation + EvolutionRecord evidence; hands to governed sink; fail-closed | Yes |
| D.13 | Component metadata + CLI | Observational registration; presentation-only commands | — |

---

## 5. Modules (files)

All paths under `atlas/advanced_reasoning/` unless noted. All **[DESIGN]**.

| File | Responsibility |
|---|---|
| `models.py` | Frozen dataclasses: `ReasoningTrace`, `ReasoningTraceStep`, `Hypothesis`, `HypothesisSet`, `VerificationReport`, `VerificationFinding`, `MetaAssessment`; enums: `ReasoningStrategy`, `TraceStatus`, `HypothesisSupport`, `VerificationVerdict` |
| `catalog.py` | Shared constants: strategy names, max-steps/depth defaults, hypothesis ranking weights, verification thresholds |
| `protocols.py` | `ReasoningModel`, `VerificationModel`, `HypothesisModel`, `EvidenceProvider`, `CausalGraphProvider` protocols |
| `multi_step.py` | `MultiStepReasoner` — deterministic decomposition + chaining |
| `causal.py` | `CausalReasoner` — causal paths + counterfactual evaluation |
| `hypotheses.py` | `HypothesisGenerator` — competing hypotheses + ranking |
| `verify.py` | `SelfVerifier` — step-level consistency/support checks + calibration |
| `meta.py` | `MetaReasoningEngine` — strategy effectiveness + recommendations |
| `trace_repository.py` | `ReasoningTraceRepository` — bounded in-memory store + dual-write |
| `trace_recorder.py` | `ReasoningTraceRecorder` — pure, event-triggered trace builder (kernel-wired subscription; never imports the EventBus) |
| `service.py` | `AdvancedReasoningService` — constructor-injected composition (no infra imports) |
| `storage_protocol.py` | `AdvancedReasoningStorage` protocol (lifecycle + trace/hypothesis/verification/meta methods) |
| `capability_handlers.py` | `AdvancedReasoningCapabilityFactory` + `reasoning.*` handlers |
| `evolution_integration.py` | `AdvancedReasoningEvolutionTracker`, `AdvancedReasoningIngestBridge`, `build_ingest_payload`, `register_gov_011` |
| `wiring.py` | `advanced_reasoning_component()`, `advanced_reasoning_evolution_component()` metadata |
| `cli_commands.py` | Presentation wrappers for the track CLI |
| `atlas/storage/advanced_reasoning_storage.py` | `AdvancedReasoningSQLiteStorage` (migration v10) |
| `atlas/storage/migration.py` | Additive migration v10 (existing file, new entry only) |
| `atlas/cli/main.py` | `atlas reasoning ...` subcommands (existing file, additive) |
| `atlas/lifecycle/component_definitions.py` | Additive `ComponentMetadata` entries (existing file, additive) |

---

## 6. Governance

[FACT] KNOWLEDGE scope → INFORMATION level via GOV-004; Track A/B added scoped ingest rules GOV-008/GOV-009 (KNOWLEDGE), Track C added GOV-010 (MEMORY) — all additive (ATLAS_STATE.md §10.5). [FACT]

[DESIGN] Track D introduces **GOV-011 (REASONING_INGEST)** as an additive governance rule documenting the distillation path. Default design: KNOWLEDGE scope, INFORMATION level (distilled reusable reasoning strategies/insights are knowledge-like and surface read-only via `EvolutionKnowledgeQuery`). Scope choice is an open question (Q6).

| Rule | Scope | Min level | Meaning |
|---|---|---|---|
| GOV-011 | KNOWLEDGE | INFORMATION (2) | Distilled reasoning insights/strategies enter Atlas state only through the governed evolution path |

Ingest discipline:

```
ReasoningInsight (from MetaReasoningEngine, explicitly requested)
    → AdvancedReasoningEvolutionTracker [DESIGN]
    → EvolutionRequestFactory.from_cli(KNOWLEDGE, "reasoning_ingest") [DESIGN]
    → AdvancedReasoningIngestSink [DESIGN]  (sole hand-off; wired by kernel to Phase 16 schedule-store/dispatcher)
    → (Phase 16 validator / risk / authorization / dispatcher → gateway → applier → knowledge)
```

Track D never calls `execute_request()` directly. Missing or refusing sink ⇒ fail closed; the trace store and strategy state are never mutated by Track D. Reasoning itself is pure computation (no mutation), so the track writes Atlas state only via this governed distillation path. Track D additionally emits `Observation` evidence (`reasoning:trace`, `reasoning:verify`, `reasoning:meta`) compatible with `SelfObservationEngine`/`EvolutionKnowledgePipeline` — evidence, not mutation.

---

## 7. Storage (migration v10 — conceptual)

[FACT] Additive-only policy; shared DB `atlas_data/atlas_experience.db`; current schema v9 (ATLAS_STATE.md §7; Track C migration 9). [FACT]

[DESIGN] Proposed tables (all additive, none modifying existing tables):

| Table | Purpose | Write semantics |
|---|---|---|
| `reasoning_traces` | Full multi-step reasoning traces | Idempotent upsert by trace_id |
| `reasoning_trace_steps` | Per-trace inference steps | Append-only (INSERT OR IGNORE by step_id) |
| `reasoning_hypotheses` | Generated competing hypotheses | Idempotent upsert by hypothesis_id |
| `reasoning_verifications` | Self-verification reports | Append-only log |
| `reasoning_meta_assessments` | Meta-reasoning strategy effectiveness | Append-only |

Nested fields JSON-serialized. Datetimes ISO strings. All columns additive.

**Trace retention:** reasoning artifacts are bounded in memory (`ReasoningTraceRepository` ring buffer, same pattern as `ReasoningRecorder`) with an append-only database log for durable history. Unbounded growth of the persistent log is addressed by a future consolidation phase (mirroring Track C's `Consolidator`) — explicitly deferred, not part of this batch.

---

## 8. Capabilities & CLI

[DESIGN] Registered capabilities (via `AdvancedReasoningCapabilityFactory.register(registry)`):

- `reasoning.trace` — run deterministic multi-step reasoning to a trace/conclusion
- `reasoning.causal` — causal path analysis for an event/property
- `reasoning.counterfactual` — what-if evaluation under an altered assumption
- `reasoning.hypotheses` — generate and rank competing hypotheses for a claim
- `reasoning.verify` — self-verify a trace or conclusion
- `reasoning.meta` — read meta-reasoning strategy-effectiveness report
- `reasoning.ingest` — GOVERNED: submit distilled reasoning insight through the evolution bridge

[DESIGN] CLI (presentation-only, except `ingest`):

```
atlas reasoning trace "question" [--max-steps N] [--strategy S]
atlas reasoning causal --event E [--property P] [--depth N]
atlas reasoning counterfactual --event E --assumption "A"
atlas reasoning hypotheses --claim "C" [--limit N]
atlas reasoning verify --trace-id ID | --claim "C"
atlas reasoning meta [--limit N] [--strategy S]
atlas reasoning ingest --trace-id ID            # GOVERNED — via evolution bridge
```

`ingest` is the only mutating-intent command and is governed: it builds an INFORMATION-scope KNOWLEDGE `EvolutionRequest` and passes it through `AdvancedReasoningIngestBridge`; without a sink it fails closed and never mutates any store.

---

## 9. Dependency Injection strategy

[FACT] All cross-module edges are constructor-injected; `Atlas.start()` constructs services; shared services register in `ServiceContainer`; private Atlas-owned dependencies inject directly (ATLAS_STATE.md §11.1, §4.2). [FACT]

[DESIGN] Proposed wiring in `Atlas.start()`:

- `MultiStepReasoner`, `CausalReasoner`, `HypothesisGenerator`, `SelfVerifier`, `MetaReasoningEngine`, `ReasoningTraceRepository` are **private Atlas-owned** dependencies — composed into `AdvancedReasoningService`.
- `AdvancedReasoningService` is constructed in `Atlas.start()` and either registered in `ServiceContainer` under key `advanced_reasoning` (shared surface) **OR** kept private — **decision pending approval (Q2)**.
- `AdvancedReasoningSQLiteStorage` is constructed and injected; the repository dual-writes best-effort (same degradation as `ExperienceRepository`/Track C repositories).
- Protocol providers are injected from the kernel: `EvidenceProvider` wraps `KnowledgeManager`, `CausalGraphProvider` wraps `WorldModelEngine`; optional `ReasoningModel`/`VerificationModel`/`HypothesisModel` wrap `AIService` only at the kernel boundary — never imported by pure modules.
- The governed sink (`AdvancedReasoningIngestSink`) is injected into the evolution bridge; never imported.
- `ReasoningTraceRecorder` is the additive EventBus consumer: kernel wiring subscribes it to the existing `runtime.pipeline.completed` event (Track C precedent) to derive traces from pipeline outcomes. The pure module never imports the EventBus — it exposes a handler the kernel subscribes; the subscription itself is kernel-owned.

---

## 10. RuntimeCoordinator interaction

[FACT] RuntimeCoordinator executes the cognitive pipeline in a fixed order (including REASONING stage and `runtime.pipeline.completed` emission); order is locked (ATLAS_STATE.md §1.4; `.clinerules/`; source `atlas/runtime/runtime_coordinator.py`). [FACT]

[DESIGN] **No pipeline change.** Track D does not modify the RuntimeCoordinator, any stage, or the execution order. All interaction is additive:

1. **Explicit capability handlers (no automatic pipeline selection).** `reasoning.*` handlers register in the existing `CapabilityRegistry`. Verified against source: the unchanged `CapabilityAnalyzer._select_capability` maps step actions to a fixed default set (`respond`→`conversation`, `query`→`knowledge_retrieval`, `analyze`→`analysis`, `execute`→`task_execution`, `idle`→`noop`, anything else→`general`) — it **cannot** emit `reasoning.*` capability names. Therefore, in its first batch Track D exposes `reasoning.*` through **explicit** invocation of the registered handlers (CLI, direct dispatcher dispatch, or the track service), matching the Track A/B/C pattern (`research.*`, `toolchain.*`, `memory.*` are likewise exposed as capability handlers + CLI rather than injected into the REASONING stage). Automatic selection of Track D capabilities by the pipeline capability analyzer is a **future additive enhancement** to `CapabilityAnalyzer` that requires separate approval; it is not part of this design and would not touch the RuntimeCoordinator.
2. **Additive event-bus consumer.** `ReasoningTraceRecorder` subscribes (kernel-wired) to the existing `runtime.pipeline.completed` event to record reasoning/planning stage outcomes as traces — identical to Track C `EpisodicRecorder`.
3. **Additive read of existing API.** `MetaReasoningEngine` consumes `ReasoningRecorder.recent(n)` — the same public read API ReflectionEngine already uses in the locked pipeline.
4. **No new stages, no context-section changes.** Feeding advanced-reasoning artifacts into `_build_cognitive_context` is a deferred extension (requires explicit RuntimeCoordinator review), consistent with Track C's deferred `ContextEngine` work.

---

## 11. Public APIs

[FACT] Existing public APIs must not break (ATLAS_STATE.md §14.4). [FACT]

[DESIGN] Track D adds new public APIs only:

- New service key `advanced_reasoning` (if approved, Q2)
- New capability names `reasoning.*` (additive)
- New CLI `atlas reasoning ...` (additive)
- New dataclasses/protocols in `atlas/advanced_reasoning/`

No existing API, service key, model, or protocol is modified.

---

## 12. Error handling

[FACT] Execution layer returns result objects; fail-closed; never silent success (ATLAS_STATE.md §11.1). [FACT]

[DESIGN]

- Reasoning engines never raise for invalid input; they return trace/report objects with error/status fields (fail-closed refusal with meaningful error).
- Repository degrades gracefully on storage write failure (best-effort, never breaks the in-memory path).
- `SelfVerifier` never raises; returns `VerificationReport` with findings and verdict.
- Evolution bridge fails closed when sink missing/refusing.
- Storage adapter marks unavailable on failure; falls back to memory-only operation.

---

## 13. Testing strategy

[DESIGN] New test files (no code written yet):

- `tests/test_advanced_reasoning_models.py`
- `tests/test_advanced_reasoning_catalog.py`
- `tests/test_advanced_reasoning_multi_step.py`
- `tests/test_advanced_reasoning_causal.py`
- `tests/test_advanced_reasoning_hypotheses.py`
- `tests/test_advanced_reasoning_verify.py`
- `tests/test_advanced_reasoning_meta.py`
- `tests/test_advanced_reasoning_repositories.py`
- `tests/test_advanced_reasoning_trace_recorder.py`
- `tests/test_advanced_reasoning_import_scan.py` — prohibits pure `atlas/advanced_reasoning/` modules from importing `atlas.reasoning` internals or infrastructure (ATLAS_STATE §12 + §3.3)
- `tests/test_advanced_reasoning_storage.py`
- `tests/test_advanced_reasoning_capability_handlers.py`
- `tests/test_advanced_reasoning_evolution_integration.py`
- `tests/test_advanced_reasoning_cli.py`
- `tests/test_advanced_reasoning_wiring.py`
- `tests/test_kernel_advanced_reasoning_integration.py`

Full existing suite (2619 tests at v0.19.1) must remain green after implementation.

---

## 14. Migration strategy

- `atlas/storage/migration.py`: bump `CURRENT_SCHEMA_VERSION` to 10; add migration v10 with only new `reasoning_*` tables.
- No existing table is altered or dropped.
- `AdvancedReasoningSQLiteStorage.initialize()` opens the shared DB, applies migrations, marks available.

---

## 15. Future extension points

[DESIGN]

- Feed advanced-reasoning traces/verifications into `_build_cognitive_context` / working memory (requires explicit RuntimeCoordinator review; deferred).
- Autonomous strategy selection via `MetaReasoningEngine` recommendations applied through governed CONFIG scope (requires approval; staged config).
- Hypothesis-driven research integration with Track A (`research.query`) — Track D hypotheses as research sub-queries.
- Learning-loop integration: reuse distilled reasoning insights into `EvolutionKnowledgeQuery` read surface (already supported by GOV-011 KNOWLEDGE scope).
- Causal-model refinement from observation evidence (governed; requires future scope review).
- Multi-agent delegation of sub-traces to Track E — explicitly deferred to Track E boundaries.

---

## 16. Architecture consistency check

| Requirement | Status |
|---|---|
| Modular architecture | PASS — new self-contained `atlas/advanced_reasoning/` package |
| Dependency Injection | PASS — constructor-injected; private + shared pattern; protocol injection for AI/world-model/knowledge; no global state |
| RuntimeCoordinator pipeline | PASS — no change; additive capability handlers, additive event-bus consumer, additive read of `ReasoningRecorder.recent` |
| Existing public APIs | PASS — additive-only; no existing API modified |
| Evolution governance | PASS — GOV-011 additive rule; governed sink; fail-closed; KNOWLEDGE scope at INFORMATION level |
| Evolution Framework only mutation path | PASS — reasoning is pure computation; the only mutation is governed distillation via the sink |
| Storage migration policy | PASS — additive migration v10; no existing table touched |
| Pure-logic isolation | PASS — pure modules import no infrastructure; one `sqlite3` adapter |
| Minimal changes | PASS — only additive edits to existing files (migration, CLI, lifecycle, kernel wiring) |

---

## 17. Potential conflicts

1. **`atlas/reasoning/` untouched** — Track D does not modify or import internals of the locked reasoning package beyond stable public models; `ReasoningRecorder.recent()` is consumed read-only. **[DESIGN]**
2. **RuntimeCoordinator locked** — no pipeline change; only additive capability registration, event-bus consumption, and read-only use of an existing API. **[DESIGN]**
3. **"LLM is the voice, not the brain" invariant** — the deterministic core owns reasoning; `ReasoningModel`/`VerificationModel`/`HypothesisModel` are optional enhancers, protocol-injected, fallback-safe, and never imported directly. **[DESIGN]**
4. **Pure-logic isolation** — protocols live in `atlas/advanced_reasoning/protocols.py`; concrete services are injected by the kernel only. **[DESIGN]**

---

## 18. Questions requiring approval before implementation

1. **Package name** — is `atlas/advanced_reasoning/` acceptable, or should the track use `atlas/reasoning_engine/`, `atlas/deep_reasoning/`, or another name? **[DESIGN — needs approval]**
2. **Service key** — should `AdvancedReasoningService` be registered publicly in `ServiceContainer` (key `advanced_reasoning`) or kept as a private Atlas-owned dependency (not in container)? **[DESIGN — needs approval]**
3. **Capability names** — are `reasoning.trace`, `reasoning.causal`, `reasoning.counterfactual`, `reasoning.hypotheses`, `reasoning.verify`, `reasoning.meta`, `reasoning.ingest` acceptable, or should they be prefixed differently (e.g., `advanced_reasoning.*`)? **[DESIGN — needs approval]**
4. **CLI surface** — is the `atlas reasoning ...` command set acceptable, or should it be `atlas advanced-reasoning ...`? **[DESIGN — needs approval]**
5. **Storage table names** — are `reasoning_traces`, `reasoning_trace_steps`, `reasoning_hypotheses`, `reasoning_verifications`, `reasoning_meta_assessments` acceptable? **[DESIGN — needs approval]**
6. **Governance scope for ingestion** — is KNOWLEDGE scope with new GOV-011 (INFORMATION level) correct, or should Track D reuse GOV-008 (KNOWLEDGE RESEARCH_INGEST) directly — and should a new `REASONING` `ScopeType` ever be added (note: adding a `ScopeType` enum value touches the locked `atlas/evolution/governance/models.py` and is a larger change than an additive GOV rule)? **[DESIGN — needs approval]**
7. **Ingest trigger** — should distillation into knowledge be explicit-only (user/CLI requested, per this design) or should `MetaReasoningEngine` autonomously propose it (requires Evolution authorization flow)? **[DESIGN — needs approval]**

---

*Document created: 2026-08-07 · Project Atlas — docs/TRACK_D.md · Design phase — no production code written.*
