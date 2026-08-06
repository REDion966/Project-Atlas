# ATLAS STATE — Permanent Architecture Handbook

**Canonical entry point for all future Atlas development.**

This document is the single source of truth for Atlas architecture. Future implementation prompts should say: **"Read ATLAS_STATE.md and only the files directly related to the task."**

---

## 0. Document Authority

Priority order when interpreting Atlas:

1. **Source code** — actual runtime behavior truth
2. **`ATLAS_CONSTITUTION.md`** — immutable engineering laws
3. **`ATLAS_VISION.md`** — permanent North Star
4. **`ATLAS_CORE.md`** — permanent architectural principles
5. **`ATLAS_STATE.md`** *(this file)* — current architecture handbook
6. **Historical documents** — supplementary reference only

If source code and this document conflict: preserve backward compatibility and report the conflict. Never silently choose one over the other.

---

## 1. Project Overview

### 1.1 Vision

Project Atlas is a long-term, Python-based modular AI operating framework — **not a chatbot, not a model wrapper, not a demo**. Atlas coordinates memory, knowledge, reasoning, planning, learning, tools, and AI providers into a unified system that grows more capable over time while remaining under human ownership.

> **Core identity:** AI models are tools. Atlas is the intelligence. Models may change. Atlas remains.

### 1.2 Philosophy

| Principle | Meaning |
|-----------|---------|
| **Foundation first** | Core infrastructure before peripheral features |
| **Understanding over storage** | A memory system that understands what it stores is more valuable than one that merely stores everything |
| **Knowledge ≠ Understanding ≠ Intelligence** | Knowledge is stored information; Understanding is the ability to reason about it; Intelligence is the ability to improve understanding over time |
| **Never rebuild — always extend** | Existing working architecture is protected; additive changes only |
| **Provider independence** | No single AI provider is ever a permanent dependency |
| **Evidence over hype** | Technologies evaluated by measurable performance |
| **Human partnership** | Atlas augments people; human judgment is final |
| **Test-first** | No feature is complete without tests |

### 1.3 Kernel-First Architecture

The kernel (`atlas/kernel/atlas.py`) is the root application object and the only place where the whole system is wired. A permanent `ServiceContainer` registers public shared services; a `RuntimeCoordinator` orchestrates the 14-stage cognitive pipeline; private Atlas-owned dependencies (reasoning pipeline, tool engine) are injected directly and are **not** registered in the container.

Layer rules:

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
- Models are plain data (`@dataclass`) with no business logic beyond serialization

### 1.4 Evolution-First Mutation Policy

**Atlas may only change its own operational state through the Evolution Framework.** No component may write Atlas state (config, memory, knowledge, capabilities) directly.

- The `EvolutionExecutionGateway` is the **only** entry point for mutation
- Phase 16 added a typed `execute_request()` path for governed `EvolutionRequest`s — the only applied-evolution path
- `EvolutionAutonomyDispatcher` is the sole caller of `execute_request()` (one request per tick, atomic CAS claim)
- All mutations are validated, risk-assessed, authorized, versioned, verified, and rollbackable
- Fail-closed: missing governance, UNKNOWN scope, or missing dependencies ⇒ refusal, never execution

---

## 2. Current Completion Status

| Field | Value |
|---|---|
| Milestone | Phase 19 — Track C (Long-Term Learning) complete; Track B (Phases 18.1–18.10) complete; Phase 16 locked; Track A complete |
| Version tag | **v0.19.0** |
| Test suite | **Full suite passing — 2600+ tests (Phase 19 adds long-term learning tests)** |
| Architecture status | Phase 16 locked; Tracks A, B, and C architecturally complete |
| Intelligence level | Level 5 — Persistent Self-Model (Level 6+ Bounded Autonomy in progress via Phase 16) |
| Era | **Capability Track Era** (post-core roadmap; see §13) |

### 2.1 Completed Major Capabilities (Phase 1–16)

| Phase | Capability |
|---|---|
| 1–4 | Foundation: kernel, service container, AI abstraction, conversation |
| 5 | Memory system evolution (repository, ranking, search, service) |
| 5.6 | Conversation-cognition integration |
| 6.1–6.4 | Reasoning foundation: controller, capability selection, execution layer, adaptive routing |
| 6.5–6.5.2 | Documentation memory layer; reasoning runtime integration; outcome recording (ReasoningRecorder) |
| 6.6 | Model routing (ModelRouter, ModelProfileRegistry) |
| 6.7 | Reflection engine (bounded analysis → suggestions) |
| 6.8 | Planning engine (goal decomposition) |
| 6.9 | Tool intelligence (ToolEngine: registry, selector, executor) |
| 6.10 | Multi-provider AI layer (OpenAI, Anthropic, LM Studio + Ollama, Mock) |
| 7.0 | Self-evolution foundation (SelfObservationEngine, ImprovementPlanner, ProposalGenerator, ApprovalManager, EvolutionMemory, ResearchCoordinator ABC) |
| 7.1–7.3 | Understanding engine; integrated cognitive pipeline; learning engine |
| 7.4–7.5 | World model; unified cognitive runtime (RuntimeCoordinator, 14 stages) |
| 8.0–8.2.1 | Cognitive identity; runtime integration; feedback coordinator; understanding consolidation |
| 8.3 | Goal intelligence & self-directed improvement planning |
| 9.0–9.2 | Persistent self-model, experience accumulation + SQLite persistence, understanding persistence |
| 10.0 | Evolution pipeline completed |
| 11.0–11.3 | Evolution execution engine; execution levels; persistence |
| 12.0–12.3 | Evolution insights; InsightScorer; EvolutionIntelligenceEngine; insight persistence |
| 13.1–13.6 | Governance (RuleEngine, ConstraintRegistry); component registry; evolution scheduler; execution gateway; persistent evolution knowledge; automatic knowledge consolidation pipeline |
| 14.1–14.4 | Decision intelligence (PlanningContext, strategy suggestions, adaptive planning) |
| 15.0 | Goal execution engine + ToolExecutionActionBinder; `GoalExecutionRecord` evidence contract |
| 16.0 | **Governed autonomous evolution**: AutonomyPolicy envelope, EvolutionRequest lifecycle (16 states), six deterministic gates, sole-owner dispatcher, staged config + boot activation + SAFE_MODE, rollback + versioning, `EvolutionOutcomeRecord` evidence contract |
| 17.0–17.9 | **Track A — Research & Knowledge (complete)**: research models, local source adapters (document/workspace/codebase), deterministic planner, knowledge extractor, claim verifier, `research_*` SQLite storage (migration v7), capability handlers (`research.query/verify/summarize`), governed KNOWLEDGE ingest bridge + GOV-008, component metadata + `atlas research` CLI |
| 18.1–18.10 | **Track B — Tool Ecosystem (Batch 1–4, complete)**: toolchain models + catalog, skill registry, deterministic tool-chain planner, safe executor + risk policy, effectiveness tracker, tool learner, `toolchain.*` capability handlers, `toolchain_*` SQLite storage (migration v8), governed skill-activation ingest bridge + GOV-009, `atlas toolchain` / `atlas skill` CLI |
| 19.1–19.5 | **Track C — Long-Term Learning (complete)**: `atlas/longterm/` package — episodic recorder, procedure extractor, consolidator (dedup/merge/principled forgetting), episodic/procedural repositories, `LongTermSQLiteStorage` (migration v9), `memory.*` capability handlers, governed LONGTERM_INGEST bridge + GOV-010, component metadata + `atlas memory` CLI |

### 2.2 Current Non-Goals (unchanged)

Atlas currently does **not** autonomously modify source code (`CODE` scope is unreachable), does not alter its identity autonomously, does not perform autonomous reflection/strategy adjustment without approval, and has no distributed multi-process execution.

---

## 3. Package Map

All packages under `atlas/`. "Locked" = do not redesign; extend additively.

| Package | Responsibility | Status |
|---|---|---|
| `atlas/kernel/` | Root `Atlas` application object, `ServiceContainer` wiring, startup/shutdown, `Atlas.tick()` | Core, locked |
| `atlas/core/` | Boot, startup, application lifecycle | Core |
| `atlas/services/` | High-level orchestration (`CognitionService`, `AIService`) | Core |
| `atlas/cognition/` | Cognition API, context, engine, decisions, pipeline, state | Core, pure logic |
| `atlas/reasoning/` | Reasoning controller, models, capabilities, execution registry/routing/dispatch, planning, reflection | Core, pure logic |
| `atlas/tools/` | Tool registry, selector, executor, engine, builtins, execution action binder | Core |
| `atlas/ai/` | AI provider abstraction; providers (Ollama, OpenAI, Anthropic, LM Studio, Mock); AIRouter; model routing (`atlas/ai/routing/`) | Infrastructure |
| `atlas/memory/` | Memory models, repository, ranking, search, service, context engine | Core |
| `atlas/knowledge/` | Knowledge base, entries, search, ranker, query, manager | Core |
| `atlas/understanding/` | Concept extraction, pattern analysis, understanding graph/memory, consolidation layer, experience bridge, serialization | Core |
| `atlas/world_model/` | World model engine, world graph, behavior model, prediction engine | Core |
| `atlas/learning_engine/` | Learning engine, strategy analyzer, insight consolidator, learning memory | Core |
| `atlas/longterm/` | Long-term learning (Track C): episodic recorder, procedure extractor, consolidator, episodic/procedural repositories, storage protocol, capability handlers, evolution ingest bridge | Core — Track C, stable |
| `atlas/experience/` | Experience repository, accumulator, trend analyzer, outcome tracker, self-model engine, serialization | Core |
| `atlas/identity/` | Identity engine (beliefs, capability profiles, decision style) | Core |
| `atlas/goals/` | Goal repository, intelligence engine, opportunity analyzer, priority engine, dependency resolver, recommendation engine, execution engine, binders | Core |
| `atlas/evolution/` | Self-observation, improvement planning, proposal generation, approval, evolution memory, execution engine, gateway, intelligence engine, research coordinator, scheduler, decision intelligence, knowledge layer (`atlas/evolution/knowledge/`), governance (`atlas/evolution/governance/`), autonomy (`atlas/evolution/autonomy/`) | Core, locked |
| `atlas/runtime/` | RuntimeCoordinator (14-stage orchestration), FeedbackCoordinator | Core |
| `atlas/events/` | EventBus | Infrastructure |
| `atlas/config/` | Configuration system (`config.toml`) | Infrastructure |
| `atlas/state/` | StateManager | Infrastructure |
| `atlas/task/` | TaskManager | Infrastructure |
| `atlas/storage/` | Generic storage utilities + all SQLite adapters + migration framework | Infrastructure |
| `atlas/conversation/` | ConversationService, history, prompt builder | Capability |
| `atlas/workspace/` | Workspace/project/resource management, permissions, members, tags | Capability |
| `atlas/learning/` | Legacy learning manager + knowledge feedback (bounded feedback storage) | Capability, preserved |
| `atlas/lifecycle/` | ComponentRegistry + component metadata definitions | Active scaffold |
| `atlas/agents/` | Agent abstractions and orchestration | Scaffold, not fully wired |
| `atlas/automation/` | Automation workflows | Scaffold, not fully wired |
| `atlas/skills/` | Skill abstractions | Scaffold, not fully wired |
| `atlas/scheduler/` | Scheduling components | Scaffold, not fully wired |
| `atlas/interfaces/` | Contracts and abstractions | Scaffold, not fully wired |
| `atlas/models/` | Shared domain models | Scaffold, not fully wired |
| `atlas/utils/` | Shared utilities | Utility |
| `atlas/state/` | State management | Utility |
| `atlas/cli/` | CLI commands (evolution, goal, etc.) | Presentation |
| `atlas/intelligence/` | **LEGACY** `CognitiveLoop`, `CognitiveService` — preserved, do not modify | Legacy |

**Runtime data locations:** `atlas_data/` (conversations, `atlas_experience.db`), `data/` (memory/knowledge JSON storage).

---

## 4. Service Registry

The `ServiceContainer` registers public shared services. Everything is constructed in `Atlas.start()` and injected via constructor — there is no internal instantiation of services.

### 4.1 Registered Kernel Service Keys

| Key | Instance | Purpose | Lifecycle | Dependencies |
|---|---|---|---|---|
| `component_registry` | `ComponentRegistry` | Structural metadata of all core components | Registered at startup; observational only | — |
| `ai` | `AIService` | AI provider abstraction + chat/stream/complete + model routing | Started at `Atlas.start()`, stopped on shutdown | `AIRouter`, providers, `ModelRouter` |
| `conversation` | `ConversationService` | Chat/stream, history, prompt building, delegates to cognition | Started/stopped via container | `AIService`, `ContextEngine`, `CognitionAPI` |
| `memory` | `MemoryManagerService` | Memory CRUD, search, ranking | Started/stopped | `MemoryRepository`, `RankingEngine`, `MemorySearchEngine` |
| `knowledge` | `KnowledgeManager` | Knowledge base query and store | Started/stopped | `KnowledgeBase`, `KnowledgeSearch`, `KnowledgeRanker` |
| `cognition` | `CognitiveLoop` | Legacy preserved | Started/stopped | `MemoryManagerService`, `KnowledgeManager` |
| `cognitive` | `CognitiveService` | Legacy preserved | Started/stopped | `CognitiveLoop` |
| `cognition_service` | `CognitionService` | Modern cognition orchestration; delegates to RuntimeCoordinator + reasoning pipeline | Started/stopped | Memory, knowledge, reasoning, reflection, planning, tools, learning, `RuntimeCoordinator` |
| `cognition_api` | `CognitionAPI` | Orchestration-facing API boundary | Started/stopped | `CognitionService` |
| `tasks` | `TaskManager` | Task management | Started/stopped | — |
| `runtime_coordinator` | `RuntimeCoordinator` | Single permanent orchestrator, 14-stage cognitive pipeline | Started/stopped | All cognitive subsystems (injected) |
| `understanding` | `UnderstandingEngine` | Concept extraction, consolidation, understanding graph/memory, persistence | Started/stopped; storage restored at boot | `SQLiteUnderstandingStorage`, consolidation components |
| `world_model` | `WorldModelEngine` | Entities, causal graph, predictions, behavior rules | Started/stopped | `WorldModelMemory`, `WorldGraph`, `PredictionEngine`, `BehaviorModel` |
| `evolution_observer` | `SelfObservationEngine` | Produces structured observations of Atlas behavior | Started/stopped | — |
| `learning_engine` | `LearningEngine` | Pipeline learning → insights → recommendations | Started/stopped | `LearningMemory`, `StrategyAnalyzer`, `InsightConsolidator` |
| `identity` | `IdentityEngine` | Beliefs, capability profiles, decision style | Started/stopped; initialized at boot | internal managers |
| `feedback_coordinator` | `FeedbackCoordinator` | Routes cognitive feedback to identity/world/understanding/learning | Started/stopped | identity, world model, understanding, learning |
| `goal_repository` | `GoalRepository` | Goal/candidate/opportunity/report persistence | Started/stopped | — |
| `goal_intelligence` | `GoalIntelligenceEngine` | Evidence → opportunities → prioritized recommendations | Started/stopped | `GoalRepository`, analyzers/resolvers |
| `experience_repository` | `ExperienceRepository` | Structured experience CRUD + persistence | Started/stopped; restored from SQLite at boot | `SQLiteExperienceStorage` |
| `experience_accumulator` | `ExperienceAccumulator` | `CognitionState`/`PipelineResult` → `StructuredExperience` | Started/stopped | `ExperienceRepository` |
| `self_model_engine` | `SelfModelEngine` | Trend analysis, goal tracking, self-model snapshots, evidence feeds | Started/stopped; counter seeded at boot | Experience, outcome tracker, identity, understanding, goals |
| `intelligence_engine` | `EvolutionIntelligenceEngine` | Evolution outcome analysis → `EvolutionInsight` | Started/stopped | `EvolutionMemory`, `ExperienceRepository`, `InsightScorer`, storage, knowledge pipeline |
| `execution_gateway` | `EvolutionExecutionGateway` | Constitutional execution gate (governance choke point) | Started/stopped; level set at startup | `RuleEngine`, `EvolutionExecutionEngine`, `EvolutionMemory` |
| `evolution_knowledge` | `EvolutionKnowledgeQuery` | Read-only surface for durable evolution knowledge | Started/stopped | `EvolutionKnowledgeRepository` |
| `goal_execution` | `GoalExecutionEngine` | Goal activation → authorization → execution via binders | Started/stopped; `settle()` on tick | `GoalRepository`, gateway, binder registry, outcome tracker, evolution memory, decision intelligence, event bus |

### 4.2 Private Atlas-Owned Dependencies (NOT in ServiceContainer)

Created and injected directly during `Atlas.start()`:

- `ReasoningController`, `CapabilityAnalyzer`, `CapabilityRegistry`, `CapabilityRouter`, `CapabilityDispatcher`, `ReasoningRecorder`, `ReflectionEngine`, `PlanningEngine`
- `ToolRegistry`, `ToolSelector`, `ToolExecutor`, `ToolEngine`
- `ModelProfileRegistry`, `ModelRouter`
- `EvolutionScheduler` (ticked by `Atlas.tick()`), `EvolutionExecutionEngine`, `RuleEngine`, `ConstraintRegistry`, `InsightScorer`, `EvolutionKnowledgeRepository/Consolidator/Pipeline`
- Phase 16 autonomy stack (constructed only when `[evolution.autonomy] enabled=true`): policy, factory, validator, risk assessor, authorizer, schedule store, appliers, application engine, verification, rollback, versioning, adapter, dispatcher

### 4.3 Phase 16 Container Keys (when autonomy enabled)

`evolution_autonomy`, `evolution_requests`, `evolution_application`, `evolution_rollback`, `evolution_versioning`, `capability_upgrades`, `evolution_dispatcher`.

---

## 5. Evolution Framework Summary

The Evolution Framework is the **spine** of Atlas. Every capability track reports into it. It deepens understanding rather than merely accumulating changes.

### 5.1 The Pipeline

```
Observation
    ↓
Evidence
    ↓
Proposal
    ↓
Validation
    ↓
Risk Assessment
    ↓
Authorization
    ↓
Gateway
    ↓
Application
    ↓
Verification
    ↓
Versioning
    ↓
Rollback
    ↓
Knowledge Pipeline
```

### 5.2 Stage Explanations

| Stage | Component(s) | Responsibility |
|---|---|---|
| **Observation** | `SelfObservationEngine` | Produces structured `Observation`s (runtime metrics, reasoning quality, tool usage, memory quality, system health). Fed by the RuntimeCoordinator post-pipeline; persisted via `evolution_observations`. |
| **Evidence** | `ExperienceAccumulator`, `OutcomeTracker`, `EvolutionIntelligenceEngine`, `LearningEngine` | Raw outcomes become structured evidence: `StructuredExperience`, tracked goals, `EvolutionInsight`, learning insights. Evidence is never applied — it informs planning. |
| **Proposal** | `ImprovementPlanner`, `ProposalGenerator`, `EvolutionScheduler` | `EvolutionScheduler` (rate-limited, threshold-gated, driven by `Atlas.tick()`) detects weaknesses from observations + insights + planning context, creates an `ImprovementPlan`, and generates an `EvolutionProposal`. |
| **Validation** | `Validator` (Phase 16) | Per-scope payload schema + precondition checks for `EvolutionRequest`. Fail → `REJECTED`, never auto-retried. |
| **Risk Assessment** | `RiskAssessor` (Phase 16) | Deterministic risk score (LOW/MEDIUM/HIGH/CRITICAL) consuming planning context + goal signals. HIGH/CRITICAL requires user approval. |
| **Authorization** | `AuthorizationManager` + `ApprovalManager` | `user:cli` explicit, `user:policy` declarative, or `system:autonomy` inside the policy envelope. Every authorization has a TTL. |
| **Gateway** | `EvolutionExecutionGateway` | Constitutional choke point. Two entry points: `execute(proposal)` (administrative path, Phase 13.4) and `execute_request()` (only applied-evolution path). Six deterministic gates, all fail-closed. `EvolutionAutonomyDispatcher` is the sole caller of `execute_request()`. |
| **Application** | `ApplicationEngine` + scope appliers | `config_applier` (staged, never live), `information_applier` (memory/knowledge/world-model via repository interfaces), `capability_applier` (register/enhance/deprecate via upgrade registry). Snapshot captured before any mutation. |
| **Verification** | `VerificationService` | Per-scope probes; `COMPLETED` only when a change is effective **and** verified (in-session for INFORMATION/CAPABILITY; at boot for staged CONFIG). Failure → rollback. |
| **Versioning** | `VersionManager` | Append-only `evolution_versions` manifest with parent chain; `AtlasStateVersion major.minor.patch`; optimistic-concurrency anchors prevent double application. |
| **Rollback** | `RollbackManager` | Mandatory rollback plan per applied request; store-level checksummed snapshots; LIFO cascade for dependent requests; rollback failure ⇒ `EVOLUTION_HOLD`. |
| **Knowledge Pipeline** | `EvolutionKnowledgePipeline` | Consolidates insights/weaknesses/outcomes into durable knowledge: `RecurringOutcomePattern`, `StrategyKnowledge`, `CapabilityEvolution`, `BottleneckProfile`, snapshots. Consumed read-only by `DecisionIntelligenceEngine` and `EvolutionKnowledgeQuery`. |

### 5.3 EvolutionRequest Lifecycle (16 states)

`DRAFTED → VALIDATED → RISK_ASSESSED → PENDING_AUTHORIZATION → AUTHORIZED → SCHEDULED → APPLIED → PENDING_EFFECTIVE → COMPLETED`, with terminal states `FAILED`, `ROLLED_BACK`, `SUPERSEDED`, `CANCELLED`, `EXPIRED`, `REJECTED`, `EVOLUTION_HOLD`. Revival requires a fresh draft.

### 5.4 Evidence Contracts

- `GoalExecutionRecord` (Phase 15) — typed execution feedback per executed goal
- `EvolutionOutcomeRecord` (Phase 16) — structured terminal outcome per applied request
Both are persisted only; aggregation happens in the Phase 13.6 knowledge pipeline / future Track G analytics.

---

## 6. Capability Registry

### 6.1 Capability Registration

Two registries:

1. **Reasoning `CapabilityRegistry`** (`atlas/reasoning/execution/registry.py`) — routes cognition decisions to handler functions. `DEFAULT_HANDLERS` are registered during `Atlas.start()`; new capabilities register new handlers here.
2. **`ComponentRegistry`** (`atlas/lifecycle/`) — structural metadata registry of all core components (`ComponentMetadata` in `atlas/lifecycle/component_definitions.py`). Purely observational; never modifies/restarts/repairs components.

### 6.2 Capability Lifecycle

`REGISTER → ENHANCE → DEPRECATE` (Phase 16 `upgrade_kind`). Capability changes are **not** a separate artifact — they are `EvolutionRequest`s with `target_scope=CAPABILITY`.

### 6.3 Capability Mutation Path

```
CapabilityUpgradeApplier (upgrade_kind dispatch)
    ← ApplicationEngine (behind Gateway.execute_request())
        ← EvolutionAutonomyDispatcher (sole caller; atomic CAS claim)
            ← request_factory (sources: proposal, goal transcription, scheduler, CLI)
```
No CLI or component ever applies a capability change directly. `CAPABILITY` scope requires `SELF_CONFIG` execution level (GOV-005).

### 6.4 ApplierRegistry

`ApplierRegistry` (`atlas/evolution/autonomy/applier_registry.py`) maps `ScopeType → Applier` implementing the `Applier` protocol: `validate / apply / revert / verify / capture_snapshot`. New scopes (e.g. future `SKILLS`, `AGENT`, `TASK`) are additive — a new applier registered without touching existing ones.

---

## 7. Storage Overview

All SQLite adapters share one database file: **`atlas_data/atlas_experience.db`** (WAL mode, FK on, schema managed by `atlas/storage/migration.py`). Nested fields are JSON-serialized. Every adapter degrades gracefully — failures mark the adapter unavailable and Atlas falls back to memory-only operation.

| Adapter | Tables | Contents |
|---|---|---|
| `SQLiteExperienceStorage` | `experiences` | Structured pipeline execution records (outcome, reasoning, planning, tools, understanding counts) |
| | `trend_analyses` | Windowed trend analysis results (success/reasoning/understanding/planning/tool/learning trends) |
| | `tracked_goals` | Recommendation/goal outcome tracking |
| | `self_model_snapshots` | Point-in-time self-model snapshots |
| `SQLiteEvolutionStorage` | `evolution_proposals`, `evolution_approval_requests`, `evolution_records` | Classic evolution pipeline history |
| | `evolution_insights` | Outcome analysis insights |
| | `evolution_observations` | Persisted observations |
| | `evolution_knowledge_patterns` | Recurring outcome patterns |
| | `evolution_knowledge_strategies` | Strategy effectiveness knowledge |
| | `evolution_knowledge_capabilities` | Capability trajectories |
| | `evolution_knowledge_bottlenecks` | Recurring bottleneck profiles |
| | `evolution_knowledge_snapshots` | Knowledge-layer point-in-time summaries |
| `AutonomySQLiteStorage` (Phase 16, additive) | `evolution_requests` | `EvolutionRequest` lifecycle rows (JSON payloads) |
| | `evolution_versions` | Append-only state version manifest (parent chain) |
| | `evolution_receipts` | Applied change receipts |
| | `evolution_snapshots` | Store-level rollback snapshot artifacts (checksummed) |
| | `evolution_outcomes` | `EvolutionOutcomeRecord` evidence contract |
| | `staged_config` | Staged config entries awaiting boot activation |
| `ToolchainSQLiteStorage` (Phase 18.8, additive) | `toolchain_skills` | Registered skills (nested chain JSON) |
| | `toolchain_chains` | Tool chains (steps JSON) |
| | `toolchain_effectiveness_records` | Effectiveness observations (append-only) |
| | `toolchain_plans` | Planned tool chains |
| | `toolchain_reports` | Executed chain results (append-only log) |
| `LongTermSQLiteStorage` (Phase 19, additive) | `episodic_episodes` | Event-sequence episodes (idempotent upsert by episode_id) |
| | `episodic_episode_events` | Per-episode events (append-only, INSERT OR IGNORE by event_id) |
| | `procedural_procedures` | Distilled reusable methods (idempotent upsert by procedure_id) |
| | `procedural_procedure_steps` | Procedure steps (idempotent upsert) |
| | `memory_consolidation_records` | Consolidation/forgetting audit log (append-only) |
| `SQLiteUnderstandingStorage` | `understanding_concepts` | Extracted/consolidated concepts |
| | `understanding_relationships` | Concept relationships |
| | `understanding_patterns` | Detected patterns |
| | `understanding_insights` | Generated understanding insights |
| | `understanding_signals` | Behavioral signals |

**JSON stores:** `data/` holds memory and knowledge JSON; `atlas_data/conversations/` holds saved conversations.

**Migration rule:** new tables are additive; existing tables are never redesigned; schema versioning via `atlas/storage/migration.py`.

---

## 8. Memory Architecture

| Layer | Component | Description |
|---|---|---|
| **Working memory** | `CognitionState`, `ContextEngine`, conversation history | Active session context assembled per request; exchanged across the 14-stage pipeline; assembled from memory retrieval + conversation history |
| **Long-term memory** | `MemoryManagerService` (`MemoryRepository`, `RankingEngine`, `MemorySearchEngine`) | Persistent recollection with search, tags, importance ranking, and keyword retrieval |
| **Knowledge** | `KnowledgeManager` (`KnowledgeBase`, `KnowledgeSearch`, `KnowledgeRanker`) | Structured project/domain knowledge entries with source attribution and ranked query |
| **Understanding** | `UnderstandingEngine` (concept graph + memory + consolidation) | Concepts, relationships, patterns, insights, behavioral signals; consolidation prevents duplicate accumulation. Persisted to SQLite |
| **Experience** | `ExperienceRepository` + `ExperienceAccumulator` + `SelfModelEngine` + `OutcomeTracker` | Structured per-pipeline experiences, trend windows, self-model snapshots, tracked goal outcomes. Persists cross-session |
| **Evolution memory** | `EvolutionMemory` + `EvolutionKnowledgeQuery` | Proposals, approvals, records, insights, and durable consolidated evolution knowledge |
| **Episodic memory** | `atlas/longterm/` — `EpisodicRecorder`, `EpisodicRepository`, `Episode` | Event-sequence recollection of what Atlas did and observed; built from existing `StructuredExperience` output; consolidated and persisted via `LongTermSQLiteStorage` |
| **Procedural memory** | `atlas/longterm/` — `ProcedureExtractor`, `ProceduralRepository`, `Procedure` | Reusable task/method patterns distilled from repeated episodes; consolidated (dedup/merge/principled forgetting) and persisted via `LongTermSQLiteStorage` |

---

## 9. Understanding Layer

The **permanent foundation** upon which reasoning, planning, learning, memory, and tool use operate. Architecture law: no component prioritizes raw knowledge accumulation over deepening understanding.

```
 UnderstandingLayer (permanent)
      ↓
   Reasoning
      ↓
  Observation
      ↓
  Reflection
      ↓
   Learning
      ↓
  Adaptation
      ↓
Self-improvement
```

| Subsystem | Component | Responsibility |
|---|---|---|
| **Concept Graph** | `UnderstandingGraph` + `UnderstandingMemory` | Concepts, relationships (auto-connected, consolidated), patterns, insights; consolidation layer (Concept/Relationship/Pattern/Insight consolidators, `UnderstandingScorer`, `AbstractionRegistry`) |
| **Identity** | `IdentityEngine` | Long-term cognitive identity: core beliefs (evidence-strengthened/weakened), capability profiles, decision style. Identity changes are evidence-based and approval-safe |
| **World Model** | `WorldModelEngine` | Entities, events, state snapshots, causal relations/chains, behavior rules, predictions |
| **Learning** | `LearningEngine` (strategy analyzer, insight consolidator, learning memory) | Distills pipeline executions into reusable insights and improvement recommendations |
| **Intelligence** | `EvolutionIntelligenceEngine`, `DecisionIntelligenceEngine`, `EvolutionKnowledgeQuery` | Outcome analysis → insights; adaptive planning contexts from consolidated evolution knowledge; read-only durable knowledge surface |

---

## 10. Governance

### 10.1 Rule Engine

`RuleEngine` evaluates proposals/requests against the `ConstraintRegistry` and produces a `GovernanceDecision` (approved, reason, violated_rules). Pure logic, deterministic, auditable. Missing RuleEngine ⇒ **fail closed**.

### 10.2 Constraint Registry

Immutable-once-registered `GovernanceRule`s, keyed by `rule_id`. Registry and gateway level are user-mutable only — no request, applier, or engine may modify them.

### 10.3 Execution Levels

| Level | Value | Meaning |
|---|---|---|
| `ADMINISTRATIVE` | 0 | Record-keeping only |
| `SELF_CONFIG` | 1 | Modify internal Atlas configuration |
| `INFORMATION` | 2 | Modify memory, knowledge, world model |
| `CODE_ARTIFACT` | 3 | Generate code patches (currently unreachable) |
| `SANDBOXED` | 4 | Apply changes in sandbox, test, rollback (locked) |
| `AUTONOMOUS` | 5 | Self-directed evolution within constitutional bounds (locked) |

### 10.4 Scope Types

`CONFIG`, `MEMORY`, `KNOWLEDGE`, `CODE`, `IDENTITY`, `CAPABILITY`, `UNKNOWN`. **UNKNOWN scope never executes at any level** (unconditional gateway refusal).

### 10.5 GOV Rules

| Rule | Scope | Requirement |
|---|---|---|
| GOV-001 | `IDENTITY` | `AUTONOMOUS` level (unreachable) |
| GOV-002 | `CODE` | `CODE_ARTIFACT` level (unreachable) |
| GOV-003 | `CONFIG` | `SELF_CONFIG` level |
| GOV-004 | `MEMORY` / `KNOWLEDGE` | `INFORMATION` level |
| GOV-005 | `CAPABILITY` | `SELF_CONFIG` level |
| GOV-006 | `SKILLS` (reserved) | `SELF_CONFIG` level (registered when `ScopeType.SKILLS` is added) |
| GOV-008 | `KNOWLEDGE` (RESEARCH_INGEST) | `INFORMATION` level — Track A research results enter knowledge only via the governed evolution path |
| GOV-009 | `KNOWLEDGE` (TOOLCHAIN_INGEST) | `INFORMATION` level — Track B skill activation / toolchain ingest enters Atlas state only via the governed evolution path |
| GOV-010 | `MEMORY` (LONGTERM_INGEST) | `INFORMATION` level — Track C memory consolidation / long-term ingest enters Atlas state only via the governed evolution path (`register_gov_010` in `atlas/longterm/evolution_integration.py`) |

**Constitutional invariants:** identity and code are untouchable; a request can never alter `AutonomyPolicy`, `ConstraintRegistry`, or gateway level; UNKNOWN scope can never execute; autonomy-envelope membership (GOV-007) is policy enforced in `AuthorizationManager`, never a registry rule.

### 10.6 The Six Gates (Phase 16)

1. `RuleEngine` at gateway level
2. `Validator` (per-scope schema/preconditions)
3. `RiskAssessor` (≤ policy max risk)
4. `AuthorizationManager` (valid, unexpired authorization)
5. Dispatcher level pre-check (`intended_level` ≤ effective level)
6. Gateway translation + UNKNOWN-close

All gates fail closed; every transition audited via `phase16.*` events.

---

## 11. Coding Standards

### 11.1 Architecture

- **Clean architecture:** layered `CLI → Services → Managers → Repositories → Storage`; business logic never touches storage directly
- **SOLID:** single-responsibility modules; dependency inversion via constructor injection; interfaces in pure layers, implementations in adapters
- **Dependency injection:** all cross-module edges are constructor-injected; no internal instantiation of services; no service locator in domain logic
- **Pure logic vs infrastructure:** reasoning/cognition/evolution/understanding/goals/experience/learning models and engines are pure — no AI calls, no memory/knowledge access, no EventBus, no service imports (see §12)
- **Fail closed:** missing governance, validation, or authorization ⇒ refusal, never silent success
- **Test first:** every feature requires tests before completion; tests are mandatory, order-independent, run against the full suite; never modify tests to hide failures
- **Additive changes only:** prefer new files over modifying existing ones; extend, never redesign
- **No kernel rewrites:** `atlas/kernel/`, core services, and legacy `atlas/intelligence/` are protected
- **No architecture drift:** every new capability must fit existing module boundaries and the Evolution Framework mutation path

### 11.2 Code Style

| Element | Convention |
|---|---|
| Classes | `PascalCase` |
| Methods / functions | `snake_case` |
| Data models | `@dataclass` (often `frozen=True, slots=True`) |
| Type hints | Required on all signatures; `list[...]`/`dict[...]`/`X | None` |
| Booleans | predicates (`is_loaded`) |
| Arrays | plurals (`users`) |
| Imports | Explicit only, grouped stdlib → third-party → atlas; pure logic must not import infrastructure |
| Errors | Execution layer returns result objects with errors rather than raising; services wrap as needed |
| Constants | Magic numbers/strings become named constants |

### 11.3 Documentation

Every module/class/method has a docstring explaining **what and why**. Architecture changes update this file and relevant ADRs.

---

## 12. Prohibited Dependencies

### 12.1 Pure Logic Layers MUST NEVER import

- **kernel** (`atlas/kernel/`)
- **runtime** (`atlas/runtime/`)
- **dispatcher** (`atlas/evolution/autonomy/dispatcher.py` — no component other than `Atlas.tick()` calls it)
- **gateway** (`atlas/evolution/execution_gateway.py` — autonomy modules never import it; it injects the application engine downward)
- **AI providers** (`atlas/ai/providers/` — only `AIManager` and the router touch providers)
- **EventBus** (`atlas/events/`)
- **scheduler runtime** (`atlas/evolution/scheduler.py` is constructed and ticked only from the kernel; pure logic never imports it)

Additionally, `atlas/evolution/autonomy/**` never imports `execution_gateway`, `kernel`, `services`, `ai`, or `EventBus`. `CognitionAPI` may depend on `CognitionService`; `CognitionEngine`/`CognitionContext`/`CognitionDecision` may not.

### 12.2 Violation consequence

Any import that crosses these boundaries is an architecture violation and must be rejected in review. Infrastructure adapters (in `atlas/storage/`) are the *only* modules that import `sqlite3`.

---

## 13. Current Roadmap — Capability Track Era

Post-core development is organized into **Capability Tracks** (roadmap units, not runtime constructs). The runtime remains capability-based; the Evolution Framework is the spine every track reports through. Tracks must not bypass the Evolution Framework.

| Track | Name | Direction (summary only) |
|---|---|---|
| **A** | Research & Knowledge | **COMPLETE (Phase 17.1–17.9)**: research models, local source adapters, deterministic planner, knowledge extractor, claim verifier, `research_*` storage, `research.*` capabilities, governed KNOWLEDGE ingest (GOV-008), CLI. Remaining: knowledge-graph expansion, web adapter, coordinator implementation |
| **B** | Tool Ecosystem | **COMPLETE (Phase 18.1–18.10)**: toolchain models, skill registry, tool-chain planning, safe execution, effectiveness tracking, tool learning, `toolchain_*` storage, `toolchain.*` capabilities, governed skill-activation ingest (GOV-009), CLI. Remaining: skill authoring, PARALLEL/CONDITIONAL execution, learned-skill promotion |
| **C** | Long-Term Learning | **COMPLETE (Phase 19, v0.19.0)**: episodic recorder, procedure extractor, consolidator (dedup/merge/principled forgetting), episodic/procedural repositories, `episodic_*`/`procedural_*`/`memory_consolidation_records` storage (migration v9), `memory.*` capabilities, governed LONGTERM_INGEST (GOV-010), CLI. Remaining: feeding episodic context into working memory/`ContextEngine` (deferred — requires RuntimeCoordinator review), semantic memory upgrades, forgetting-policy tuning |
| **D** | Advanced Reasoning | Multi-step reasoning, causal/counterfactual reasoning, hypothesis generation, self-verification, meta-reasoning |
| **E** | Multi-Agent Collaboration | Agent registry, task decomposition, inter-agent messaging, result synthesis (in-process only; single-process assumption maintained) |
| **F** | Human Collaboration | Unified approval center, audit/explainability surfaces, rich CLI, workspace sharing, optional API/plugin surfaces |
| **G** | Self-Improvement | Bounded optimization under policy, capability trajectory monitoring, strategy-effectiveness analytics, verification benchmarks |

**Era principles:** capabilities not phases; evolution is the only mutation channel; evidence over accumulation; pure logic preserved; additive packaging; fail-closed by default. Full designs for each track live in the approved architecture proposal; Tracks are summarized here by design and not fully designed in this document.

---

## 14. Future Implementation Guidance

> These instructions bind every future coding model working on Atlas.

1. **Read this file first.** Do not perform repository-wide analysis. Read `docs/ATLAS_STATE.md`, then read only the modules directly related to the task (verify their service keys, models, and conventions in §3–§9).
2. **Read before writing.** Any code that touches an existing module requires reading that module first to learn its interface, exports, and patterns. Never guess signatures or import paths.
3. **Never redesign Atlas.** The Kernel, Core Services, Memory, Workspace, Evolution, and Governance are locked. Build on top of them with additive modules.
4. **Preserve backward compatibility.** Existing public APIs and service keys must not break without explicit review. Legacy `atlas/intelligence/` is never modified.
5. **Preserve architecture.** Follow the layered rules (§11.1) and prohibited-dependency rules (§12).
6. **Follow dependency direction.** High-level modules depend on abstractions; pure logic never imports infrastructure; storage adapters own all `sqlite3` imports; all cross-module edges are constructor-injected.
7. **Register all new capabilities.** New reasoning handlers → `CapabilityRegistry` (`DEFAULT_HANDLERS` pattern). New components → `ComponentMetadata` in `atlas/lifecycle/component_definitions.py` + container key if shared. New storage tables → additive tables via `atlas/storage/migration.py`.
8. **Route every mutation through the Evolution Framework.** Never write Atlas state directly. Knowledge/memory ingest = `INFORMATION`-scope `EvolutionRequest`; capability changes = `CAPABILITY`-scope; config = `CONFIG`-scope (staged, boot-activated). The gateway is the only execution entry point.
9. **Fail closed.** Missing dependencies, missing governance, invalid input ⇒ refusal with a meaningful error/audit record — never a silent success, never a 500-style crash in the reasoning layer.
10. **Test first.** Write tests alongside implementation; run the full suite before finishing; fix failures, never hide them.
11. **One focused change at a time.** Do not modify unrelated code. Prefer new files over edits.
12. **Record changes.** Update this document and relevant ADRs when architecture changes; report format: summary, files created/modified, test results, assumptions, issues.

---

*Document created: 2026-08-02 · Last updated: 2026-08-07 (v0.19.0 — Track C complete) · Project Atlas — docs/ATLAS_STATE.md · Replaces historical ATLAS_STATE as the permanent architecture handbook.*
