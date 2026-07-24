# Atlas Current State

**Live snapshot of Project Atlas.**

**Date:** July 2026  
**Branch:** `phase5-memory-evolution`  
**Status:** Active Development

---

## 1. Current Branch

```
phase5-memory-evolution
```

The branch name references the Phase 5 memory evolution work that laid the foundation for the current cognition and reasoning architecture.

---

## 2. Completed Phases

### Phase 5 — Memory Evolution
Status: **Complete**

The memory subsystem was evolved to support:
- Memory model and persistence
- Memory search and ranking engines
- Memory repository pattern
- MemoryManagerService orchestration layer
- Context engine for conversation integration

### Phase 6.1 — Reasoning Foundation
Status: **Complete**

- `ReasoningController` — translates `CognitionDecision` to `ReasoningPlan`
- `ReasoningPlan` and `ReasoningStep` data models
- Pure logic layer with no infrastructure dependencies

### Phase 6.2 — Capability Selection
Status: **Complete**

- `CapabilityAnalyzer` — analyzes reasoning plans and produces ranked capabilities
- `Capability` data model with name, priority, reason, and metadata
- Action-to-capability mapping (conversation, knowledge_retrieval, analysis, task_execution, noop)

### Phase 6.3 — Capability Execution Layer
Status: **Complete**

- `CapabilityRegistry` — handler registration and lookup
- `CapabilityDispatcher` — executes capabilities through registered handlers
- `CapabilityHandler` type alias for handler callables
- `ExecutionResult` data model

### Phase 6.4 — Adaptive Execution Routing
Status: **Complete**

- `CapabilityRouter` — converts capabilities to `ExecutionRoute` instances
- `ExecutionRoute` data model with strategy and metadata
- Registry validation during routing
- Strategy placeholder for future model routing (Phase 6.5+)

### Phase 6.5 — Documentation Memory Foundation
Status: **Complete**

The permanent documentation memory system for Atlas has been created:
- `ATLAS_MASTER_CONTEXT.md` — the single-entry context for any AI model
- `ARCHITECTURE.md` — full system architecture documentation
- `CURRENT_STATE.md` — this file, live project snapshot
- `DEVELOPMENT_LOG.md` — chronological development history
- `ROADMAP.md` — future development roadmap
- `ARCHITECTURE_DECISIONS.md` — decision record system
- `CODING_GUIDELINES.md` — development rules and standards
- `MODEL_STRATEGY.md` — AI provider and workflow strategy
- `AI_WORKFLOW_PROTOCOL.md` — AI agent working protocol
- `FUTURE_DIRECTION.md` — long-term vision

### Phase 6.5.1 — Reasoning Runtime Integration
Status: **Complete**

Reasoning pipeline is now wired into the Atlas runtime:
- `CapabilityRegistry` + `DEFAULT_HANDLERS` registered during `Atlas.start()`
- `ReasoningController`, `CapabilityAnalyzer`, `CapabilityRouter`, `CapabilityDispatcher` created and injected into `CognitionService`
- `CognitionService` optionally runs the full reasoning pipeline after each cognition decision
- Pipeline results are attached to `decision.data["reasoning"]`
- All reasoning components remain pure logic with no infrastructure dependencies

---

## 3. Phase Timeline

| Phase | Description | Status |
|-------|-------------|--------|
| 1–4 | Foundation, kernel, AI providers, conversation | Complete |
| 5 | Memory system evolution | Complete |
| 5.6 | Conversation-cognition integration | Complete |
| 6.1 | Reasoning foundation | Complete |
| 6.2 | Capability selection | Complete |
| 6.3 | Capability execution layer | Complete |
| 6.4 | Adaptive execution routing | Complete |
| **6.5** | **Documentation Memory Foundation** | **Complete** |
| 6.5.1 | Reasoning runtime integration | Complete |
| 6.6+ | Model routing, reflection, planning | Planned |

---

## 4. Kernel Services Registered

| Key | Instance | Status |
|-----|----------|--------|
| `"ai"` | `AIService` | Active |
| `"conversation"` | `ConversationService` | Active |
| `"memory"` | `MemoryManagerService` | Active |
| `"knowledge"` | `KnowledgeManager` | Active |
| `"cognition"` | `CognitiveLoop` | Legacy, preserved |
| `"cognitive"` | `CognitiveService` | Legacy, preserved |
| `"cognition_service"` | `CognitionService` | Active |
| `"cognition_api"` | `CognitionAPI` | Active |
| `"tasks"` | `TaskManager` | Active |

---

## 5. Test Status

**Current count: 389 tests collected**

```
pytest
Result: 389 passed
```

Key test files:

| Test File | Area |
|-----------|------|
| `test_reasoning_controller.py` | ReasoningController — plan creation |
| `test_capability_analyzer.py` | CapabilityAnalyzer — plan analysis |
| `test_capability_execution.py` | CapabilityDispatcher — capability execution |
| `test_capability_routing.py` | CapabilityRouter — adaptive routing |
| `test_capability_handlers.py` | Default capability handlers |
| `test_cognition_engine.py` | CognitionEngine — pure reasoning |
| `test_cognition_service.py` | CognitionService — orchestration |
| `test_cognition_service_new.py` | CognitionService — dependency injection |
| `test_cognition_reasoning_integration.py` | CognitionService reasoning pipeline integration |
| `test_cognition_runtime.py` | Cognition runtime integration |
| `test_cognitive_api.py` | CognitionAPI — delegation and registration |
| `test_conversation_service.py` | Conversation service with cognition |
| `test_kernel.py` | Kernel lifecycle |
| `test_memory.py` | Memory system |
| `test_reasoning_runtime_wiring.py` | Atlas runtime reasoning wiring |
| `test_ai_service.py` | AI provider service |
| `test_ai_router.py` | AI routing |

---

## 6. Current Pipeline

The following diagram shows the current operational data flow through the system.

### Currently Implemented Runtime Flow

```
User Input
    │
    ▼
ConversationService
    │
    ├──→ ContextEngine.build()        ← memory + conversation history
    │
    ├──→ CognitionAPI.process()       ← optional cognition layer
    │       │
    │       ▼
    │   CognitionService
    │       │
    │       ├──→ MemoryManagerService.search()
    │       ├──→ KnowledgeManager.query()
    │       ├──→ CognitionEngine.process()
    │       ├──→ EventBus.publish()
    │       ├──→ Feedback loop
    │       │
    │       └──→ Reasoning pipeline   ← Phase 6.5.1
    │               │
    │               ├──→ ReasoningController.create_plan()
    │               ├──→ CapabilityAnalyzer.analyze()
    │               ├──→ CapabilityRouter.route()
    │               ├──→ CapabilityDispatcher.dispatch()
    │               │
    │               └──→ decision.data["reasoning"]
    │
    ├──→ PromptBuilder.build()
    │
    ▼
AI Provider
    │
    ▼
Response → User
```

### Phase 6 Reasoning Pipeline (Runtime Integrated)

The reasoning pipeline is now wired into the cognition runtime. After each `CognitionDecision` is produced, `CognitionService` runs the pipeline and attaches the results to `decision.data["reasoning"]`.

```
CognitionDecision
    │
    ▼
ReasoningController          ← translates decision → ReasoningPlan
    │
    ▼
CapabilityAnalyzer           ← analyzes plan → list of Capability
    │
    ▼
CapabilityRouter             ← routes capabilities → ExecutionRoute
    │
    ▼
CapabilityDispatcher         ← dispatches → list of ExecutionResult
    │
    ▼
decision.data["reasoning"]   ← goal, capabilities, routes, results
```

All reasoning, capability analysis, routing, and execution layers remain **pure logic** — no AI calls, no memory access, no knowledge access, no EventBus dependencies. `CognitionService` provides the orchestration boundary that links them to the runtime while preserving this purity.

---

## 7. Next Steps

Following Phase 6.5.1 completion:

1. **Architecture review** — Evaluate the current runtime integration to identify gaps, inconsistencies, and priorities for the next implementation phase.
2. **Model routing** — Select optimal AI model per request based on complexity and constraints.
3. **Reflection system** — Evaluate own decisions and adjust future reasoning strategies.
4. **Planning engine** — Decompose complex goals into ordered sub-tasks.
5. **Tool intelligence** — Dynamically choose tools and skills based on cognition decisions.
6. **Long-term autonomous improvement** — Safe, bounded optimisation of internal parameters.

---

## 8. Architecture Notes

- The reasoning, capability analysis, routing, and execution layers are **pure logic** — no AI, memory, knowledge, or EventBus dependencies.
- Reasoning components are **Atlas-owned private dependencies**. They are created and injected into `CognitionService` during `Atlas.start()` but are not registered in `ServiceContainer`.
- `DEFAULT_HANDLERS` are registered in the private `CapabilityRegistry` at startup, providing placeholder handlers for the five default capabilities.
- Legacy `CognitiveLoop` and `CognitiveService` in `atlas/intelligence/` are preserved for backward compatibility.
- All new development should target the new cognition service layer in `atlas/cognition/` and `atlas/services/cognition_service.py`.
- The documentation memory layer is designed to survive AI model and provider changes.
