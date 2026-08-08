# ATLAS CURRENT STATUS REPORT

**Onboarding document for future AI assistants and developers.**
**Last updated:** July 28, 2026

---

## Table of Contents

1. [Project Identity](#1-project-identity)
2. [Current Development Stage](#2-current-development-stage)
3. [Current Architecture Map](#3-current-architecture-map)
4. [Important Architectural Discoveries](#4-important-architectural-discoveries)
5. [Completed Phase Details](#5-completed-phase-details)
6. [Current Runtime Data Flow](#6-current-runtime-data-flow)
7. [Current Missing Capabilities](#7-current-missing-capabilities)
8. [Recommended Next Phase](#8-recommended-next-phase)
9. [Development Rules](#9-development-rules)
10. [Instructions for Future AI Assistants](#10-instructions-for-future-ai-assistants)
11. [Current Git/Test Status](#11-current-gittest-status)
12. [Next Session Starting Point](#12-next-session-starting-point)

---

## 1. Project Identity

### What Project Atlas Is

**Project Atlas** is a long-term, Python-based modular AI agent operating framework. It is designed to coordinate memory, knowledge, reasoning, planning, learning, tools, and AI providers into a unified, extensible architecture.

Atlas is built to last for **decades, not demos**. Every design decision prioritizes long-term sustainability, provider independence, and human partnership.

### What Atlas Is NOT

- A chatbot or simple conversational wrapper
- A single AI model prompt chain
- A cloud-dependent service or SaaS product
- A demo, prototype, or short-term project
- An autonomous code-modification agent

### Long-Term Vision

Atlas is an independent AI operating framework. AI models are tools. Atlas is the intelligence. Models may change. Atlas remains.

The evolutionary path is:

```
Documented Self-Analysis  →  Guided Improvement  →  Bounded Optimisation  →  Autonomous Evolution
        (current)              (next)                (medium term)           (long term)
```

Current stage: **Level 5 — Persistent Self-Model** (Phase 9.0-9.2b complete)

### Core Architectural Philosophy

| Principle | Meaning |
|---|---|
| **Build the foundation first** | Core infrastructure before peripheral features |
| **Preserve the existing roadmap** | Do not randomly redesign or re-scope |
| **Prefer additive changes** | New files over modification of working code |
| **Never rebuild — always extend** | Existing working architecture is protected |
| **Modularity** | Every subsystem is independently replaceable |
| **Provider independence** | Never depend on a single AI provider |
| **Test-first** | Every major feature requires tests |
| **Pure logic isolation** | Reasoning layers must not import infrastructure |
| **Dependency injection** | No internal instantiation of services |
| **Human partnership** | Augment people; human judgment is final |

### Important Permanent Principles

1. **Provider independence is constitutional** — No single AI provider is required for Atlas to function.
2. **Understanding over storage** — A system that understands what it stores is more valuable than one that merely stores everything.
3. **Core-first growth** — Depth before breadth. Foundation before decoration.
4. **User-approved self-modification** — Atlas may recommend changes, but never modify itself without permission.
5. **Legacy preservation** — `atlas/intelligence/` is preserved and must NOT be modified.

---

## 2. Current Development Stage

### Current Roadmap Phase

Phase 9.x — Persistent Self-Model & Experience Infrastructure (Phases 9.0 through 9.2b complete)

### Completed Phases

| Phase | Description | Status |
|---|---|---|
| 1–4 | Foundation, kernel, AI providers, conversation | ✅ Complete |
| 5 | Memory system evolution | ✅ Complete |
| 5.6 | Conversation-cognition integration | ✅ Complete |
| 6.1 | Reasoning foundation | ✅ Complete |
| 6.2 | Capability selection | ✅ Complete |
| 6.3 | Capability execution layer | ✅ Complete |
| 6.4 | Adaptive execution routing | ✅ Complete |
| 6.5 | Documentation memory foundation | ✅ Complete |
| 6.5.1 | Reasoning runtime integration | ✅ Complete |
| 6.5.2 | Reasoning outcome recording | ✅ Complete |
| 6.6 | Model routing subsystem | ✅ Complete |
| 6.7 | Reflection foundation | ✅ Complete |
| 6.8 | Planning engine | ✅ Complete |
| 6.9 | Tool intelligence foundation | ✅ Complete |
| 6.10 | Multi-Provider AI Layer | ✅ Complete |
| 7.0 | Self-Evolution Foundation | ✅ Complete |
| 7.1 | Understanding Engine | ✅ Complete |
| 7.2 | Integrated Cognitive Pipeline | ✅ Complete |
| 7.3 | Learning Engine | ✅ Complete |
| 7.4 | World Model Foundation | ✅ Complete |
| 7.5 | Unified Cognitive Runtime | ✅ Complete |
| 8.0 | Cognitive Identity Foundation | ✅ Complete |
| 8.1 | Runtime Cognitive Integration | ✅ Complete |
| 8.2 | Cognitive Feedback Loop | ✅ Complete |
| 8.2.1 | Understanding Consolidation | ✅ Complete |
| 8.3 | Goal Intelligence & Self-Directed Improvement Planner | ✅ Complete |
| **9.0** | **Persistent Self-Model & Experience Accumulation** | **✅ Complete** |
| **9.1** | **Experience Persistence & Self-Model Cognitive Context** | **✅ Complete** |
| **9.2a** | **Experience → Understanding Bridge Wiring** | **✅ Complete** |
| **9.2b** | **Understanding Persistence (verified, no code changes)** | **✅ Complete** |

### Current Maturity Level

**Level 5 — Persistent Self-Model**

Atlas can:
- Execute a 15-stage cognitive pipeline through RuntimeCoordinator
- Accumulate structured experiences from every pipeline execution
- Persist experiences to SQLite and restore them across restarts
- Bridge experiences into understanding (concepts, patterns, insights, relationships)
- Persist understanding data to SQLite and restore on startup
- Produce a self-model snapshot from accumulated experience trends
- Include self-model data in the LLM cognitive context
- Close the cognitive feedback loop via FeedbackCoordinator
- Generate improvement recommendations via GoalIntelligenceEngine
- Detect weaknesses and produce improvement proposals via Evolution system
- All 22 kernel services registered and operational

Atlas does NOT yet:
- Wire the evolution improvement pipeline into the runtime (planner/proposal generator are unwired)
- Execute approved improvement proposals
- Close the improvement verification loop
- Perform autonomous reflection or strategy adjustment

---

## 3. Current Architecture Map

### 3.1 Kernel Layer

**Purpose:** Application lifecycle, dependency injection, service registration.

**Important modules:**
- `atlas/kernel/atlas.py` — Root application class (`Atlas`). Wires all subsystems in `start()`.
- `atlas/kernel/service_container.py` — Dependency injection container. 22 registered service keys.

**Status:** ✅ Complete

### 3.2 Runtime Layer

**Purpose:** Single permanent orchestrator for all cognitive processing.

**Important modules:**
- `atlas/runtime/runtime_coordinator.py` — 15-stage pipeline in invariant order.
- `atlas/runtime/feedback_coordinator.py` — Post-pipeline evidence distribution.

**Status:** ✅ Complete (pipeline) + ⚠️ Partially wired (evolution)

The RuntimeCoordinator currently calls these post-pipeline:
- `FeedbackCoordinator.process_feedback()` ✅
- `ExperienceAccumulator.record()` ✅
- `SelfModelEngine.update()` ✅
- `UnderstandingEngine.process_experiences()` ✅ (Phase 9.2a)

It does NOT call:
- `ImprovementPlanner.detect_weaknesses()` ❌
- `ProposalGenerator.generate_proposal()` ❌
- `GoalIntelligenceEngine.analyze()` ❌ (called during Stage 14 only, not post-pipeline)

### 3.3 Cognition Layer

**Purpose:** Core decision-making, context assembly, engine.

**Important modules:**
- `atlas/cognition/engine.py` — `CognitionEngine` (pure logic)
- `atlas/cognition/context.py` — `CognitionContext`
- `atlas/cognition/decision.py` — `CognitionDecision`
- `atlas/cognition/models.py` — `CognitionState`, `PipelineResult`, `StageType`, etc.
- `atlas/cognition/api.py` — `CognitionAPI` (public boundary)

**Status:** ✅ Complete

### 3.4 Reasoning Layer

**Purpose:** Plan decomposition, capability analysis, routing, dispatch, reflection.

**Important modules:**
- `atlas/reasoning/controller.py` — `ReasoningController`
- `atlas/reasoning/capabilities/analyzer.py` — `CapabilityAnalyzer`
- `atlas/reasoning/execution/` — `CapabilityRegistry`, `CapabilityRouter`, `CapabilityDispatcher`, default handlers
- `atlas/reasoning/planning/` — `PlanningEngine`
- `atlas/reasoning/reflection.py` — `ReflectionEngine` (produces suggestions)
- `atlas/reasoning/outcomes.py` — `ReasoningRecorder` (ring buffer)

**Status:** ✅ Complete. All pure logic. All wired in RuntimeCoordinator stages 6-7 and 11.

### 3.5 Planning Engine

**Purpose:** Decompose complex goals into ordered sub-tasks.

**Important modules:**
- `atlas/reasoning/planning/engine.py` — `PlanningEngine`
- `atlas/reasoning/planning/models.py` — Plan data models

**Status:** ✅ Complete. Wired in RuntimeCoordinator stage 7.

### 3.6 Tool System

**Purpose:** Tool registry, selection, execution, and engine orchestration.

**Important modules:**
- `atlas/tools/registry.py` — `ToolRegistry`
- `atlas/tools/selector.py` — `ToolSelector`
- `atlas/tools/executor.py` — `ToolExecutor`
- `atlas/tools/engine.py` — `ToolEngine`
- `atlas/tools/builtins.py` — Built-in tool definitions

**Status:** ✅ Complete. Wired in RuntimeCoordinator stages 8-9.

### 3.7 Experience System

**Purpose:** Capture, store, analyze, and persist pipeline execution experiences.

**Important modules:**
- `atlas/experience/models.py` — `StructuredExperience`, `TrendAnalysis`, `SelfModelSnapshot`, `TrackedGoal` (frozen dataclasses)
- `atlas/experience/experience_repository.py` — `ExperienceRepository` (bounded in-memory + SQLite dual-write)
- `atlas/experience/experience_accumulator.py` — `ExperienceAccumulator` (converts pipeline state → experience)
- `atlas/experience/trend_analyzer.py` — `TrendAnalyzer` (directional trend detection)
- `atlas/experience/outcome_tracker.py` — `OutcomeTracker` (recommendation outcome evaluation)
- `atlas/experience/self_model_engine.py` — `SelfModelEngine` (self-model snapshot production)
- `atlas/experience/storage_interface.py` — `ExperienceStorage` interface
- `atlas/experience/serialization.py` — Model ↔ dict conversion
- `atlas/storage/experience_storage.py` — `SQLiteExperienceStorage` adapter

**Status:** ✅ Complete. 39 tests for storage, 36 for experience models/accumulator/analyzer/engine. Dual-write (memory + SQLite). Restore on startup.

### 3.8 Understanding System

**Purpose:** Extract concepts, patterns, relationships, and insights from text and structured experiences.

**Important modules:**
- `atlas/understanding/models.py` — Pure data models (Concept, Relationship, Pattern, UnderstandingInsight, BehavioralSignal)
- `atlas/understanding/understanding_engine.py` — `UnderstandingEngine` (orchestrator)
- `atlas/understanding/experience_bridge.py` — `ExperienceBridge` (transforms StructuredExperience → understanding inputs)
- `atlas/understanding/understanding_graph.py` — `UnderstandingGraph` (concept graph)
- `atlas/understanding/understanding_memory.py` — `UnderstandingMemory` (bounded storage)
- `atlas/understanding/concept_extractor.py` — `ConceptExtractor`
- `atlas/understanding/pattern_analyzer.py` — `PatternAnalyzer`
- `atlas/understanding/serialization.py` — Model ↔ dict conversion
- `atlas/understanding/storage_interface.py` — `UnderstandingStorage` interface
- `atlas/storage/understanding_storage.py` — `SQLiteUnderstandingStorage` adapter
- `atlas/understanding/consolidation/` — ConceptConsolidator, RelationshipConsolidator, PatternConsolidator, InsightConsolidator, AbstractionRegistry, UnderstandingScorer

**Status:** ✅ Complete. Two entry points (`process_text`, `process_experiences`), full consolidation pipeline, SQLite persistence, restore on startup.

### 3.9 Reflection System

**Purpose:** Analyze reasoning outcomes and produce structured suggestions.

**Important modules:**
- `atlas/reasoning/reflection.py` — `ReflectionEngine`, `ReflectionSuggestion`
- `atlas/reasoning/outcomes.py` — `ReasoningRecorder`

**Status:** ✅ Complete. Wired in RuntimeCoordinator stage 11. Produces suggestions stored in `CognitionState.reflection_suggestions`.

### 3.10 Learning System

**Purpose:** Extract strategic insights from pipeline executions, consolidate patterns.

**Important modules:**
- `atlas/learning_engine/learning_engine.py` — `LearningEngine`
- `atlas/learning_engine/strategy_analyzer.py` — `StrategyAnalyzer`
- `atlas/learning_engine/insight_consolidator.py` — `InsightConsolidator`
- `atlas/learning_engine/learning_memory.py` — `LearningMemory`
- `atlas/learning/` — Legacy LearningManager + KnowledgeFeedback (preserved)

**Status:** ✅ Complete. Wired in RuntimeCoordinator stage 12.

### 3.11 Goal Intelligence System

**Purpose:** Analyze evidence from all subsystems, produce prioritized improvement recommendations.

**Important modules:**
- `atlas/goals/goal_intelligence_engine.py` — `GoalIntelligenceEngine` (orchestrator)
- `atlas/goals/opportunity_analyzer.py` — `OpportunityAnalyzer` (evidence → candidates → opportunities)
- `atlas/goals/priority_engine.py` — `PriorityEngine` (ranks by priority score)
- `atlas/goals/dependency_resolver.py` — `DependencyResolver`
- `atlas/goals/recommendation_engine.py` — `RecommendationEngine` (generates `RecommendationReport`)
- `atlas/goals/goal_repository.py` — `GoalRepository` (bounded storage)
- `atlas/goals/models.py` — Frozen dataclasses for all goal/opportunity/recommendation types

**Status:** ✅ Complete. Wired in RuntimeCoordinator stage 14. Called during pipeline, but NOT called as a post-pipeline improvement step.

### 3.12 Evolution System

**Purpose:** Observe runtime metrics, detect weaknesses, generate improvement plans, manage approval workflow.

**Important modules:**
- `atlas/evolution/self_observation.py` — `SelfObservationEngine` (records observations, wired in stage 13)
- `atlas/evolution/improvement_planner.py` — `ImprovementPlanner` (detects weaknesses, creates plans)
- `atlas/evolution/proposal_generator.py` — `ProposalGenerator` (plans → human-readable proposals)
- `atlas/evolution/approval_manager.py` — `ApprovalManager` (DRAFT → APPROVED/REJECTED workflow)
- `atlas/evolution/models.py` — Observation, Weakness, ImprovementPlan, EvolutionProposal, ApprovalRequest

**Status:** ⚠️ **Exists but NOT wired into RuntimeCoordinator.** `ImprovementPlanner`, `ProposalGenerator`, and `ApprovalManager` are pure logic modules that are never instantiated or called during pipeline execution. The `SelfObservationEngine` is wired in stage 13 but its observations are never consumed by the planner.

### 3.13 Identity System

**Purpose:** Maintain Atlas's self-identity (beliefs, capabilities, principles, decision style).

**Important modules:**
- `atlas/identity/identity_engine.py` — `IdentityEngine`
- `atlas/identity/identity_memory.py` — `IdentityMemory`
- `atlas/identity/belief_manager.py` — `BeliefManager`
- `atlas/identity/capability_profiler.py` — `CapabilityProfiler`
- `atlas/identity/decision_style_manager.py` — `DecisionStyleManager`

**Status:** ✅ Complete. Wired and active.

### 3.14 World Model System

**Purpose:** Track entities, events, goals, causal relationships.

**Important modules:**
- `atlas/world_model/world_model_engine.py` — `WorldModelEngine`

**Status:** ✅ Complete. Wired in RuntimeCoordinator stage 5.

### 3.15 Storage Layer

**Purpose:** SQLite persistence for experiences and understanding data.

| Adapter | Interface | Schema | Status |
|---|---|---|---|
| `SQLiteExperienceStorage` | `ExperienceStorage` | Version 2 (experiences, trend_analyses, tracked_goals, snapshots) | ✅ Complete |
| `SQLiteUnderstandingStorage` | `UnderstandingStorage` | Version 2 (concepts, relationships, patterns, insights, signals) | ✅ Complete |

Both share the same database file (`atlas_data/atlas_experience.db`) and migration system (`atlas/storage/migration.py`).

**Status:** ✅ Complete. 29 + 29 tests for storage adapters. Restore flow, dual-write, graceful degradation all tested.

### 3.16 Scaffold Modules (Not Wired)

The following modules have code but are NOT wired into the kernel or runtime:

| Module | Status |
|---|---|
| `atlas/agents/` | Scaffold — exists but not wired |
| `atlas/automation/` | Scaffold — exists but not wired |
| `atlas/scheduler/` | Scaffold — exists but not wired |
| `atlas/lifecycle/` | Scaffold — exists but not wired |
| `atlas/interfaces/` | Scaffold — exists but not wired |
| `atlas/skills/` | Scaffold — exists but not wired |
| `atlas/models/` | Scaffold — shared domain models |

These modules contain placeholder or early-stage code. They should NOT be deleted but are not part of the current development focus.

---

## 4. Important Architectural Discoveries

These discoveries prevent future duplication and wasted effort:

### Discovery 1: Improvement System Already Exists

**Do NOT create a new `atlas/improvement/` package.** The complete improvement pipeline already exists across two packages:

- `atlas/evolution/` — `ImprovementPlanner`, `ProposalGenerator`, `ApprovalManager`
- `atlas/goals/` — `GoalIntelligenceEngine`, `OpportunityAnalyzer`, `RecommendationEngine`
- `atlas/experience/` — `OutcomeTracker`, `TrendAnalyzer`

These components just need wiring into the RuntimeCoordinator post-pipeline block.

### Discovery 2: Experience → Understanding Bridge Only Needed Wiring

`atlas/understanding/experience_bridge.py` was already fully implemented. It only needed a 5-line call in RuntimeCoordinator.process() to activate it. No pure logic changes were needed.

### Discovery 3: Understanding Persistence Already Existed

The `SQLiteUnderstandingStorage` adapter, serialization module, restore flow, and all 86 tests were already implemented before Phase 9.2b was identified. Phase 9.2b required zero code changes — only verification.

### Discovery 4: Evolution System is Implemented But Disconnected

The full evolution pipeline exists:
- `SelfObservationEngine` → records observations (wired in stage 13)
- `ImprovementPlanner` → detects weaknesses, creates plans (implemented, NOT wired)
- `ProposalGenerator` → converts plans to proposals (implemented, NOT wired)
- `ApprovalManager` → manages approval workflow (implemented, NOT wired)

The gap is purely wiring in `RuntimeCoordinator.process()` and `Atlas.start()`.

### Discovery 5: Self-Model Context Integration Was Missing

`SelfModelEngine` was producing snapshots, but the `RuntimeCoordinator._build_cognitive_context()` never included self-model data. Phase 9.1 added `_build_self_model_section()` — a single method that renders snapshot data into the LLM prompt.

### Discovery 6: Legacy atlas/intelligence/ is Preserved

The entire `atlas/intelligence/` package (`CognitiveLoop`, `CognitiveService`) is preserved and must NOT be modified. Both are registered in `ServiceContainer` with keys `"cognition"` and `"cognitive"`.

### Discovery 7: All Infrastructure Imports Are Isolated

No SQLite or `atlas.storage` imports exist in any `atlas/understanding/` or `atlas/experience/` module. Storage interfaces are defined in the domain packages; implementations are in `atlas/storage/`. This boundary is verified by tests.

### Discovery 8: Shared Database File

Both `SQLiteExperienceStorage` and `SQLiteUnderstandingStorage` default to the same path: `atlas_data/atlas_experience.db`. They share the schema migration system. This is intentional — both belong to the same "Atlas runtime data" domain.

---

## 5. Completed Phase Details

### Phase 9.0 — Persistent Self-Model & Experience Accumulation

**Completed before this documentation session.**

**What was built:**
- `atlas/experience/` package with pure-logic components:
  - `models.py` — `StructuredExperience`, `TrendAnalysis`, `SelfModelSnapshot`, `TrackedGoal`
  - `experience_repository.py` — bounded in-memory storage
  - `experience_accumulator.py` — pipeline state → `StructuredExperience`
  - `trend_analyzer.py` — directional trend detection
  - `outcome_tracker.py` — recommendation outcome tracking
  - `self_model_engine.py` — orchestrates analysis, produces `SelfModelSnapshot`
- Integration into `RuntimeCoordinator`
- Wiring in `Atlas.start()`
- 3 new service container keys: `experience_repository`, `experience_accumulator`, `self_model_engine`

**Test count at completion:** 948 passing

---

### Phase 9.1 — Experience Persistence & Self-Model Cognitive Context

**Files changed:**
| File | Change |
|---|---|
| `atlas/storage/experience_storage.py` | Fixed `store_tracked_goal` timestamp mapping — now correctly uses `proposed_at` and `last_evaluated` instead of `timestamp` |
| `atlas/experience/experience_repository.py` | Replaced fragile `getattr`-based `_try_storage_write` with explicit `if/elif` method routing |
| `atlas/runtime/runtime_coordinator.py` | Added `_build_self_model_section()` — renders self-model snapshot into LLM cognitive context between Identity and Conversation sections |

**New files:**
| File | Tests |
|---|---|
| `tests/test_experience_storage.py` | 29 tests covering SQLite lifecycle, CRUD for all 4 data types, queries, failure handling, cross-session reopen |
| `tests/test_experience_restore.py` | 10 tests covering restore flow, counter seeding, snapshot restore, cross-session persistence, graceful fallback |
| `tests/test_cognitive_context_self_model.py` | 15 tests covering self-model presence/absence, content rendering, edge cases, ordering in full context |

**Key decisions preserved:**
- No changes to frozen dataclasses
- No changes to pure logic layers (`SelfModelEngine`, `TrendAnalyzer`, `OutcomeTracker`)
- No changes to `Atlas.start()` wiring (persistence was already correctly wired)
- No changes to `ServiceContainer` keys
- Dependency injection preserved — `RuntimeCoordinator` receives `self_model_engine` via `set_self_model_engine()`

**Test results:** 182 passing (36 existing + 54 new)

---

### Phase 9.2a — Experience → Understanding Bridge Wiring

**Files changed:**
| File | Change | Lines |
|---|---|---|
| `atlas/runtime/runtime_coordinator.py` | Added Phase 9.2a block: after `SelfModelEngine.update()`, feeds recent experiences from accumulator into `UnderstandingEngine.process_experiences()` | +12 |

**New files:**
| File | Tests |
|---|---|
| `tests/test_experience_bridge_integration.py` | 13 tests covering: experience→concept flow, insight generation, concept consolidation, cross-run enrichment, text+experience combination, relationship generation, pattern detection, graceful degradation for missing engine/accumulator/empty repo |

**Architectural reasoning:**
- Preserved all existing APIs — no signatures changed
- Preserved stage ordering — Understanding stage (4) runs first for text; experience feeding happens post-pipeline, enriching the graph for future runs
- Preserved dependency injection — uses `self._experience_accumulator.repository` (public property) and `self._understanding_engine.process_experiences()` (public method)
- Zero changes to pure logic — `UnderstandingEngine`, `ExperienceBridge`, all consolidation components untouched
- Graceful degradation — entire block guarded by `if (accumulator and engine)` — if either is missing, it's a no-op

**Data flow before Phase 9.2a:**
```
Pipeline → process_text() → Understanding Graph (text only)
Pipeline → ExperienceAccumulator.record() → SelfModelEngine.update()
Understanding Graph never sees experiences
```

**Data flow after Phase 9.2a:**
```
Pipeline → process_text() → Understanding Graph (text only)
Pipeline → ExperienceAccumulator.record() → SelfModelEngine.update()
         → UnderstandingEngine.process_experiences() → ExperienceBridge
         → Understanding Graph (enriched with experience-derived concepts)
```

**Test results:** 139 passing (36 existing + 54 Phase 9.1 + 13 Phase 9.2a + 27 bridge unit + 11 engine integration)

---

### Phase 9.2b — Understanding Persistence (Verified)

**Code changes: NONE.** All components were already implemented.

**Verified existing components:**

| Component | File | Status |
|---|---|---|
| `UnderstandingStorage` interface | `atlas/understanding/storage_interface.py` | ✅ Existing |
| `UnderstandingRestoreResult` dataclass | Same file | ✅ Existing |
| `SQLiteUnderstandingStorage` adapter | `atlas/storage/understanding_storage.py` | ✅ Existing |
| Serialization (5 model types) | `atlas/understanding/serialization.py` | ✅ Existing |
| `UnderstandingEngine._persist_understanding()` | `atlas/understanding/understanding_engine.py` | ✅ Existing |
| `UnderstandingEngine.restore()` | Same file | ✅ Existing |
| `UnderstandingEngine.close()` | Same file | ✅ Existing |
| `Atlas.start()` wiring | `atlas/kernel/atlas.py` | ✅ Existing |
| `Atlas.shutdown()` close call | Same file | ✅ Existing |
| Schema version 2 tables | `atlas/storage/migration.py` | ✅ Existing |

**Verified existing tests:**

| File | Tests | Coverage |
|---|---|---|
| `tests/test_understanding_serialization.py` | 41 | Round-trip for all 5 model types, enum defaults, extra keys, datetime preservation |
| `tests/test_understanding_storage.py` | 29 | Lifecycle, CRUD for 5 data types, clear_all, max_insight_id, transaction safety, architecture boundaries |
| `tests/test_understanding_engine_persistence.py` | 16 | Engine with/without storage, consolidation writes, restore loads graph, idempotent restore, counter seeding, failure handling, close delegation |
| Total | **86** | |

**Test results after Phase 9.2b:** 225 passing (139 + 86)

---

## 6. Current Runtime Data Flow

### Complete Execution Flow

```
User Input
    │
    ▼
ConversationService.send()
    │
    ├──→ ContextEngine.build()          ← memory + conversation history [✅]
    │
    ├──→ CognitionAPI.process()
    │       │
    │       ▼
    │   CognitionService.process()
    │       │
    │       └──→ RuntimeCoordinator.process()   ← SINGLE orchestrator [✅]
    │               │
    │               ├── Stage 1:  Conversation Context      [✅]
    │               ├── Stage 2:  Memory Retrieval          [✅]
    │               ├── Stage 3:  Knowledge Retrieval       [✅]
    │               ├── Stage 4:  Understanding (text)      [✅]
    │               ├── Stage 5:  World Model Update        [✅]
    │               ├── Stage 6:  Reasoning Pipeline        [✅]
    │               ├── Stage 7:  Planning Engine           [✅]
    │               ├── Stage 8:  Tool Decision             [✅]
    │               ├── Stage 9:  Tool Execution            [✅]
    │               ├── Stage 10: AI Response Generation    [✅]
    │               ├── Stage 11: Reflection                [✅]
    │               ├── Stage 12: Learning Engine           [✅]
    │               ├── Stage 13: Evolution Observation     [✅]
    │               ├── Stage 14: Goal Intelligence         [✅]
    │               └── Stage 15: Memory Storage            [✅]
    │
    ├──→ PromptBuilder.build()
    │
    ▼
AI Provider
    │
    ▼
Response → User

=== POST-PIPELINE (all stages complete) ===

    FeedbackCoordinator.process_feedback()
        ├── CapabilityProfiler.update()       [✅]
        ├── BeliefManager.update()             [✅]
        ├── WorldModelEngine.record_event()    [✅]
        ├── UnderstandingEngine.process_text() [✅]
        └── DecisionStyleManager.observe()     [✅]

    ExperienceAccumulator.record()             [✅ Phase 9.0]

    SelfModelEngine.update()                   [✅ Phase 9.0]

    UnderstandingEngine.process_experiences()  [✅ Phase 9.2a]
        └── ExperienceBridge.transform()
                ├── Concepts created
                ├── Patterns detected
                ├── Insights generated
                └── Relationships built

    ─── EVOLUTION PIPELINE (NOT WIRED) ───    [❌ Phase 10.0]
        ImprovementPlanner.detect_weaknesses()
        ImprovementPlanner.create_improvement_plan()
        ProposalGenerator.generate_proposal()
        ApprovalManager.create_approval_request()
```

### Connection Status Summary

| Connection | Status |
|---|---|
| Pipeline 15 stages → result produced | ✅ Complete |
| result → FeedbackCoordinator | ✅ Complete |
| result → ExperienceAccumulator | ✅ Complete |
| Experiences → SelfModelEngine | ✅ Complete |
| Experiences → UnderstandingEngine (via bridge) | ✅ Complete (Phase 9.2a) |
| Feedback → UnderstandingEngine (reflection/learning) | ✅ Complete |
| Observations → ImprovementPlanner | ❌ Not wired |
| Weaknesses → ProposalGenerator | ❌ Not wired |
| Proposals → ApprovalManager | ❌ Not wired |
| SelfModelSnapshot → LLM context | ✅ Complete (Phase 9.1) |

---

## 7. Current Missing Capabilities

### 7.1 Evolution Pipeline Not Wired (HIGHEST PRIORITY)

The `ImprovementPlanner`, `ProposalGenerator`, and `ApprovalManager` are fully implemented but **never instantiated or called**. The `SelfObservationEngine` records observations in stage 13, but no component consumes them.

**What exists:**
- `SelfObservationEngine` — records observations ✅
- `ImprovementPlanner.detect_weaknesses()` — analyzes observations → `Weakness[]` ✅
- `ImprovementPlanner.create_improvement_plan()` → `ImprovementPlan` ✅
- `ProposalGenerator.generate_proposal()` → `EvolutionProposal` ✅
- `ApprovalManager.create_approval_request()` → `ApprovalRequest` ✅

**What's missing:**
- Instantiation of `ImprovementPlanner` + `ProposalGenerator` in `Atlas.start()`
- Injection into `RuntimeCoordinator`
- Post-pipeline call in `RuntimeCoordinator.process()`
- Tests for evolution pipeline integration

### 7.2 Goal Intelligence Not Called Post-Pipeline (MEDIUM PRIORITY)

`GoalIntelligenceEngine.analyze()` is called during Stage 14 of the pipeline, but it is **not called as a post-pipeline step**. Self-model data and accumulated experiences could produce richer recommendations, but they aren't fed back.

### 7.3 Improvement Proposal Execution (LONG-TERM)

Even after wiring, the evolution pipeline only generates proposals and approval requests. It does not execute them. This is intentional per the ATLAS_VISION.md — "Guided Improvement" is the next evolutionary stage, and execution requires user approval mechanisms.

### 7.4 User-Facing Improvement Management (LONG-TERM)

There is no CLI or UI for:
- Viewing pending improvement proposals
- Approving or rejecting proposals
- Tracking implemented improvements
- Viewing improvement outcome verification

The `ApprovalManager` exists as pure logic with no storage or presentation layer.

### 7.5 Verification Loop (LONG-TERM)

`OutcomeTracker` tracks whether recommendations produced observable outcomes, but this is not connected to the improvement lifecycle. An approved proposal that gets implemented would not automatically trigger before/after comparison.

---

## 8. Recommended Next Phase

### Phase 10.0 — Evolution Pipeline Wiring

**Why this phase is next:**

1. The evolution system (`atlas/evolution/`) is the only major subsystem with components that exist but are completely disconnected from the runtime.
2. All pure logic is already implemented — only wiring is needed (exactly like Phase 9.2a).
3. This directly advances Atlas from "Documented Self-Analysis" toward "Guided Improvement" per the ATLAS_VISION.md.
4. It closes the last architectural gap before Atlas can produce structured improvement proposals for user review.

**What already exists:**
- `SelfObservationEngine` — wired in Stage 13, records observations ✅
- `ImprovementPlanner` — detects weaknesses, creates plans ✅ (code exists, unused)
- `ProposalGenerator` — generates human-readable proposals ✅ (code exists, unused)
- `ApprovalManager` — manages approval workflow ✅ (code exists, unused)
- `EvolutionProposal`, `ImprovementPlan`, `Weakness`, `ApprovalRequest` models ✅

**What only needs wiring:**

| Step | Changes | Lines |
|---|---|---|
| 1 | Add `ImprovementPlanner`, `ProposalGenerator` constructor params to `RuntimeCoordinator` | ~5 |
| 2 | Add post-pipeline call in `RuntimeCoordinator.process()` after Phase 9.2a block | ~15 |
| 3 | Wire components in `Atlas.start()` | ~8 |
| 4 | Add integration tests for evolution pipeline | ~10 tests |

**Files that would likely change:**
| File | Change |
|---|---|
| `atlas/runtime/runtime_coordinator.py` | Add constructor params + post-pipeline call |
| `atlas/kernel/atlas.py` | Wire `ImprovementPlanner` + `ProposalGenerator` |
| `tests/test_evolution_wiring.py` | New — integration tests |

**Files that would NOT change:**
- `atlas/evolution/improvement_planner.py` — pure logic, untouched
- `atlas/evolution/proposal_generator.py` — pure logic, untouched
- `atlas/evolution/approval_manager.py` — pure logic, untouched
- `atlas/evolution/models.py` — pure data models, untouched
- Any existing test file — no modifications

**Risks:**
- Low. All components are pure logic with no infrastructure dependencies. The `SelfObservationEngine` is already wired. Missing planner/proposal_generator are handled by `None` checks (the pattern used throughout RuntimeCoordinator).

---

## 9. Development Rules

### Code Rules

| Rule | Enforcement |
|---|---|
| Each module has one clear responsibility | Separation of concerns |
| High-level modules depend on abstractions | Dependency inversion |
| Data access is encapsulated in repositories | Repository pattern |
| Components are independent and replaceable | Modular design |
| Related logic stays together; modules use clean interfaces | High cohesion / low coupling |
| Reasoning layers must not import infrastructure | Pure logic isolation |
| Services coordinate; managers/engines contain logic | Service orchestration |
| Cross-cutting concerns subscribe to events, not direct calls | Event-driven flow |
| AI providers are replaceable via abstraction | Provider independence |
| Existing public APIs must not break without review | Backward compatibility |
| Prefer adding new files over refactoring old ones | Additive over destructive |
| Legacy components marked as preserved must not be modified | Preservation |

### Prohibited Patterns

| Pattern | Rationale |
|---|---|
| Creating new modules that duplicate existing functionality | Wasteful — always search first |
| Modifying tests to hide failures | Fix the real bug, not the symptom |
| Breaking existing APIs without review | Other modules depend on stable interfaces |
| Importing packages not declared in project | Dependencies must be declared |
| Modifying unrelated code during a task | One change per task keeps history clean |
| Business logic in storage/repository layers | Separation of concerns |
| Business logic in models | Models are data containers only |
| Infrastructure in pure logic | Preserves testability and modularity |
| Hardcoded provider dependencies | Violates provider independence |
| Silent failures | Meaningful actions must be recorded |
| Circular imports | Creates unmaintainable coupling |
| Refactoring without explicit approval | Prefer additive changes |

### Testing Rules

- Tests are **mandatory** — no feature is complete without tests
- Tests must pass before commit
- Never modify tests to hide failures — fix the implementation
- Every test class starts each test with a clean state using `setUp`
- Tests must be order-independent
- Pure logic layers must be testable without mocking infrastructure
- Run the full test suite before finishing any task

---

## 10. Instructions for Future AI Assistants

### Before Coding

1. **Read the documentation first:**
   - `docs/ATLAS_CURRENT_STATUS_REPORT.md` (this file) — current state and discoveries
   - `docs/ATLAS_CORE.md` — permanent architectural principles
   - `docs/ATLAS_STATE.md` — operational state and resume point

2. **Search for existing implementations:**
   - Before creating a new module, search the entire `atlas/` directory for related functionality
   - Check `atlas/evolution/`, `atlas/goals/`, `atlas/experience/`, `atlas/understanding/` for overlapping capabilities
   - Do NOT create `atlas/improvement/` — the improvement system already exists in `atlas/evolution/` + `atlas/goals/`

3. **Understand the current phase:**
   - Check `docs/ATLAS_STATE.md` for the latest completed phase
   - Check this document's section 8 for the recommended next phase
   - If the task seems to require a new subsystem, verify it doesn't already exist

4. **Check existing tests:**
   - Run `python -m pytest --collect-only` to see all available tests
   - Run the full suite before starting: `python -m pytest`
   - Note the baseline passing count

### During Coding

1. **Modify minimum files:**
   - One focused change per task
   - Prefer adding new files over modifying existing ones
   - Do not modify unrelated code

2. **Preserve APIs:**
   - Never break existing public method signatures
   - Add new optional parameters with defaults for backward compatibility
   - Do not modify legacy `atlas/intelligence/` components

3. **Preserve pure logic isolation:**
   - Pure logic components (in `atlas/evolution/`, `atlas/reasoning/`, `atlas/cognition/`, `atlas/experience/`, `atlas/understanding/`, `atlas/goals/`, `atlas/learning_engine/`) must NOT import:
     - `sqlite3`
     - `atlas.storage`
     - `atlas.events`
     - Any service or infrastructure module

4. **Follow the dependency injection pattern:**
   - All dependencies passed via constructor parameters
   - All dependencies optional — `None` means "skip gracefully"
   - No internal instantiation of services

5. **Add tests:**
   - Every new feature requires tests
   - Pure logic tests should not need mocking
   - Integration tests should verify wiring, not duplicate pure logic tests

### Before Finishing

1. **Run the full test suite:**
   ```
   python -m pytest
   ```
   Confirm no regressions.

2. **Update state documentation:**
   - Update `docs/ATLAS_STATE.md` with new phase information
   - Update this document if architecture discoveries were made

3. **Explain architectural impact:**
   - What changed and why
   - Files created/modified
   - Test results (total passing/failing)
   - Any risks discovered
   - The exact next step after this change

---

## 11. Current Git/Test Status

### Git State

| Field | Value |
|---|---|
| Branch | `phase5-memory-evolution` |
| Latest Tag | `phase-7.5-complete` |
| Repository | `github.com/REDion966/Project-Atlas` |

### Test State

| Metric | Value |
|---|---|
| Total test files | 80+ |
| Total collected tests | **1123** |
| Last verified passing | **225+** (Phases 9.0-9.2b) |
| Test framework | pytest 9.1.1 |
| Python version | 3.14.6 |
| Platform | Windows 11 |

### Repository Structure Summary

```
atlas/          — 34+ packages, all source code
atlas_data/     — Runtime data (SQLite database, conversations)
docs/           — Documentation (20+ files)
tests/          — Tests (80+ files)
main.py         — Application entry point
config.toml     — Configuration
```

---

## 12. Next Session Starting Point

### NEXT DEVELOPMENT ACTION

**Phase:** Phase 10.0 — Evolution Pipeline Wiring

**First task:** Wire `ImprovementPlanner` and `ProposalGenerator` into `RuntimeCoordinator` post-pipeline.

**Files to inspect first (read these before coding):**
1. `atlas/runtime/runtime_coordinator.py` — Look at the post-pipeline block after `# --- Phase 9.2a` to see where to add the evolution call
2. `atlas/evolution/improvement_planner.py` — `ImprovementPlanner.detect_weaknesses()` and `create_improvement_plan()` APIs
3. `atlas/evolution/proposal_generator.py` — `ProposalGenerator.generate_proposal()` API
4. `atlas/evolution/models.py` — `Observation`, `Weakness`, `ImprovementPlan`, `EvolutionProposal`, `ProposalStatus`
5. `atlas/kernel/atlas.py` — Look at how other components (e.g., `FeedbackCoordinator`) are wired in `start()`

**What should NOT be changed:**
- `atlas/evolution/improvement_planner.py` — Pure logic, already complete
- `atlas/evolution/proposal_generator.py` — Pure logic, already complete
- `atlas/evolution/approval_manager.py` — Pure logic, already complete
- `atlas/evolution/models.py` — Pure data models, frozen dataclasses
- Any existing test file — Do not modify tests to hide failures
- `atlas/intelligence/` — Preserved legacy, never modify
- `atlas/goals/` — Already wired, not part of this phase
- `atlas/experience/` — Already wired, not part of this phase
- `atlas/understanding/` — Already wired, not part of this phase

**Implementation pattern to follow:** The same pattern used for Phase 9.2a wiring:
1. Add optional constructor parameters to `RuntimeCoordinator` (default `None`)
2. Add post-pipeline block guarded by `if component is not None`
3. Wire in `Atlas.start()` by creating instances and passing them to the coordinator
4. Add integration tests confirming proposals are generated post-pipeline
5. Run full test suite to confirm zero regressions

---

*End of ATLAS_CURRENT_STATUS_REPORT.md*
*Project Atlas — July 2026*
