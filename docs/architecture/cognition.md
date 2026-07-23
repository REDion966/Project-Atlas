# Atlas Cognition Architecture

## Status

**Phase 5 — Complete**  
The Service-based Cognition system is fully integrated into the Atlas runtime.  
Previous phases (1–4) established the legacy `CognitiveLoop` in `atlas/intelligence`.  
Phase 5 introduced a new, decoupled cognition pipeline under `atlas/cognition/` and `atlas/services/cognition_service.py`, preserving backward compatibility with the existing intelligence layer.

---

## 1. Overview

Atlas cognition is decomposed into five distinct components, each with a single responsibility:

| Component             | Module                     | Role                                    |
|-----------------------|----------------------------|-----------------------------------------|
| `CognitionAPI`        | `atlas/cognition/api.py`   | Public boundary, pure delegation        |
| `CognitionService`    | `atlas/services/`          | Orchestration, dependency injection     |
| `CognitionContext`    | `atlas/cognition/`         | Data container                          |
| `CognitionEngine`     | `atlas/cognition/`         | Reasoning logic                         |
| `CognitionDecision`   | `atlas/cognition/`         | Output representation                   |

This separation ensures that infrastructure concerns (memory, knowledge, learning, events) never leak into the reasoning core.

---

## 2. Runtime Flow

The following sequence describes a complete cognition cycle from user input to final decision.

```
User Input
    │
    ▼
CognitionAPI                   ← public boundary, no reasoning
    │
    ▼
CognitionService               ← orchestrator
    │
    ├──→ Memory Retrieval      ← MemoryManagerService.search()
    │
    ├──→ Knowledge Retrieval   ← KnowledgeManager.query()
    │
    ▼
CognitionContext               ← assembled with memory & knowledge results
    │
    ▼
CognitionEngine                ← pure reasoning
    │
    ▼
CognitionDecision              ← action + reasoning + data
    │
    ├──→ Event: decision.made  ← EventBus publish
    │
    ├──→ Feedback Loop
    │       │
    │       ├──→ LearningManager.learn()
    │       ├──→ KnowledgeFeedback.remember()
    │       ├──→ KnowledgeManager.remember()
    │       └──→ Event: learning.completed
    │
    ▼
Returned to caller
```

### 2.1 Conversation Integration (Phase 5.6)

When Atlas routes a user message through `ConversationService`, the cognition pipeline is invoked as an optional context provider:

```
User Message
    │
    ▼
ConversationService.send()
    │
    ├──→ ContextManager.build()       ← conversation history + memories
    │
    ├──→ CognitionAPI.process()       ← optional, if cognition_api injected
    │       │
    │       └──→ (see runtime flow above)
    │
    ├──→ Append cognition Message     ← role="system", metadata includes decision
    │
    ├──→ PromptBuilder.build()
    │
    └──→ AI provider
```

The cognition decision is serialised into a `Message` object with `metadata["cognition"]` containing `action`, `reasoning`, and `data`. Raw `CognitionDecision` objects never enter the conversation context directly.

---

## 3. Component Responsibilities

### CognitionAPI

```python
class CognitionAPI:
    def __init__(self, cognition_service: CognitionService): ...
    def process(self, user_input, memory, metadata, goal) -> CognitionDecision: ...
```

**Rules:**
- Must never contain reasoning logic.
- Must never import or reference `CognitionEngine`, `MemoryManagerService`, `KnowledgeManager`, or `EventBus`.
- Only public method is `process()`.
- Delegates every call to `CognitionService.process()`.

### CognitionService

```python
class CognitionService(Service):
    def __init__(self, engine, memory_service, knowledge_manager,
                 learning_manager, knowledge_feedback, event_bus): ...
    def process(self, user_input, ...) -> CognitionDecision: ...
```

**Responsibilities:**
- Owns all infrastructure dependencies (memory, knowledge, learning, events).
- Retrieves relevant memories via `MemoryManagerService.search()`.
- Retrieves relevant knowledge via `KnowledgeManager.query()`.
- Assembles a `CognitionContext` from all available data.
- Passes the context to `CognitionEngine.process()`.
- Publishes `cognition.decision.made` and `cognition.learning.completed` events.
- Drives the learning feedback loop after each decision.

**Status visibility:**

```python
@property
def status(self) -> dict:
    # Returns: running, has_memory, has_knowledge, has_learning
```

### CognitionContext

```python
class CognitionContext:
    def __init__(self, user_input, memory, metadata, goal,
                 knowledge, memory_results, knowledge_results): ...
```

**Rules:**
- Pure data container. No methods beyond `add_memory()` and `get_input()`.
- Must never import services, engines, or infrastructure.

### CognitionEngine

```python
class CognitionEngine:
    def process(self, context: CognitionContext) -> CognitionDecision: ...
```

**Rules:**
- Must never import `MemoryManagerService`.
- Must never import `KnowledgeManager`.
- Must never access `EventBus`.
- Must never access any service or infrastructure class.
- Receives all necessary data through `CognitionContext` only.

### CognitionDecision

```python
class CognitionDecision:
    def __init__(self, action: str, reasoning: str = "", data=None): ...
```

- Output-only value object.
- `action` identifies the type of decision (e.g. `"respond"`, `"idle"`).
- `reasoning` contains the explanation generated by the engine.
- `data` carries arbitrary structured information.

---

## 4. Architecture Rules

These constraints must be enforced during code review and future development.

### 4.1 Dependency Boundaries

```
┌─────────────────────────────────────────────────┐
│                   CognitionAPI                   │
│  (imports: CognitionService, CognitionDecision)  │
└──────────────────────┬──────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────┐
│                 CognitionService                 │
│  (imports: Service, CognitionContext,            │
│   CognitionEngine, MemoryManagerService,         │
│   KnowledgeManager, LearningManager, etc.)       │
└──────┬─────────────────────┬────────────────────┘
       │                     │
       ▼                     ▼
┌──────────────┐   ┌──────────────────────┐
│CognitionEngine│   │ Memory / Knowledge / │
│  (pure logic) │   │ Learning / Events    │
│               │   │  (infrastructure)    │
└──────────────┘   └──────────────────────┘
```

### 4.2 Prohibited Imports

The following imports are **forbidden**:

| Source file | Must NOT import |
|------------|----------------|
| `CognitionEngine` | `MemoryManagerService`, `KnowledgeManager`, `EventBus`, any service |
| `CognitionContext` | Any service or engine |
| `CognitionAPI` | `CognitionEngine`, `MemoryManagerService`, `KnowledgeManager`, `EventBus` |
| `CognitionDecision` | Any module beyond its own dataclass |

### 4.3 Kernel Registration

The Atlas kernel registers four cognition-related service keys in `ServiceContainer`:

| Key | Instance |
|-----|----------|
| `"cognition"` | `CognitiveLoop` (legacy, **do not modify**) |
| `"cognitive"` | `CognitiveService` (legacy, **do not modify**) |
| `"cognition_service"` | `CognitionService` (new service layer) |
| `"cognition_api"` | `CognitionAPI` (new public API) |

**All four keys must remain registered.** Migration of legacy keys is out of scope.

### 4.4 ConversationService Constraints

- `cognition_api` parameter must default to `None`.
- When `None`, conversation flow must be identical to pre-Phase-5.6 behaviour.
- Cognition data must be serialised into `metadata["cognition"]`, never passed as raw `CognitionDecision`.

---

## 5. Future Evolution

### Phase 6 — Adaptive Intelligence

The following capabilities are planned but not yet implemented:

- **Model Routing**  
  Select the optimal AI model per request based on complexity, latency, and cost constraints.

- **Planning**  
  Decompose complex goals into ordered sub-tasks before execution.

- **Reflection**  
  Allow the system to evaluate its own decisions and adjust future reasoning strategies.

- **Tool Selection**  
  Dynamically choose from available tools and skills based on the cognition decision.

- **Controlled Self-Improvement**  
  Enable safe, bounded optimisation of internal cognition parameters through feedback analysis.

Each of these capabilities should be introduced as an **optional middleware layer** between `CognitionService` and `CognitionEngine`, preserving the existing dependency boundaries.

---

## Appendix: Module Map

```
atlas/cognition/
├── __init__.py          ← exports: CognitionAPI, CognitionContext,
│                           CognitionDecision, CognitionEngine
├── api.py               ← CognitionAPI
├── context.py           ← CognitionContext
├── decision.py          ← CognitionDecision
├── engine.py            ← CognitionEngine
└── pipeline.py          ← (reserved for future use)

atlas/services/
└── cognition_service.py ← CognitionService

atlas/kernel/
├── atlas.py             ← kernel wiring, service registration
└── service_container.py ← ServiceContainer

atlas/conversation/
└── conversation_service.py ← optional cognition context injection

tests/
├── test_cognitive_api.py        ← CognitionAPI delegation & kernel registration
├── test_cognition_service.py    ← CognitionService orchestration
├── test_cognition_service_new.py← dependency injection tests
├── test_cognition_engine.py     ← pure engine tests
├── test_cognition_runtime.py    ← integration tests
└── test_conversation_service.py ← cognition context integration