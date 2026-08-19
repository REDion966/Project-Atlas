# ATLAS CORE — Permanent Operational Memory

**Supporting document.** The canonical entry points are `README.md`, then
`docs/ATLAS_STATE.md`, then `docs/ROADMAP.md`; read this file only when deeper
architectural principles are needed.

---

## 0. Document Authority

Priority order when interpreting Atlas:

1. **Source code** — actual runtime behavior truth.
2. **`ATLAS_CORE.md`** — permanent architectural principles and rules.
3. **`ATLAS_STATE.md`** — current operational state and resume point.
4. **Historical documents** — supplementary reference only; never override CORE or STATE.

If source code and these documents conflict:
- Do not silently choose one over the other.
- Preserve backward compatibility.
- Report the conflict.

`ATLAS_MASTER_CONTEXT.md` is preserved as historical reference and is no longer the primary AI entry point.

---

## 1. Atlas Identity

**Project Atlas** is a modular, AI-independent intelligent agent operating framework.

**Atlas is NOT:**
- A chatbot
- A single AI model wrapper
- A cloud-dependent service
- A demo or short-term project

**Atlas IS:**
- A long-term modular AI operating framework
- A self-evolutionary architecture vision — designed for self-evolution, but NOT currently autonomously self-evolving
- A system designed to augment human capability through trustworthy, modular, intelligent automation
- A permanent memory and identity layer that survives AI model and provider changes

### 1.1 Current Non-Goals

Atlas currently does NOT:
- Autonomously modify source code
- Perform autonomous reflection
- Adjust its own strategy
- Perform autonomous planning
- Perform autonomous improvement

Future capabilities require the corresponding roadmap phases and explicit user approval.

---

## 2. Why Atlas Exists

| Problem | Atlas Solution |
|---|---|
| AI models change | Architecture and knowledge persist |
| AI providers disappear | System remains functional via abstraction |
| Context is fragmented | Centralised memory, knowledge, and decisions |
| Prompts are ephemeral | Structured reasoning and capability routing replace prompt engineering |
| Systems become unmaintainable | Modular, replaceable subsystems with clean boundaries |
| Knowledge without understanding is brittle | Understanding — not storage — is the foundation of intelligence |

**Goal:** Build a system capable of research, analysis, knowledge management, controlled self-improvement, and assisting its own development with user permission.

**Core distinction:** Knowledge != Understanding != Intelligence. Knowledge is stored information. Understanding is the ability to reason about that information. Intelligence is the ability to improve understanding over time. Atlas architecture shall respect all three as distinct layers.

---

## 3. Self-Evolving Architecture Vision

Atlas is designed for self-evolution over years, not months. Atlas is **NOT currently autonomously self-evolving**.

**Evolution principle:** Foundation first → Incremental layers → Verification before progression → Continuous learning.

Atlas grows through capabilities that can be added, replaced, or upgraded without rebuilding the core.

**Self-evolution stages:**

```
Documented Self-Analysis  →  Guided Improvement  →  Bounded Optimisation  →  Autonomous Evolution
        (current)              (near future)          (medium term)           (long term)
```

**Current stage:** Documented Self-Analysis.

**Future stages:** Guided Improvement, Bounded Optimisation, Autonomous Evolution.

**Autonomous Evolution** is long-term. It requires future phases, explicit user approval, and adherence to Constitution constraints (especially Articles 5 and 18).

---

## 4. Intelligence Growth Pipeline

### 4.1 Understanding Layer

Understanding is the permanent foundation upon which reasoning, planning, learning, memory, and tool use operate. It is distinct from both knowledge and intelligence:

- **Knowledge** is stored information — facts, data, records, and learned content.
- **Understanding** is the ability to relate knowledge to context, identify patterns, recognize gaps, and apply knowledge to novel situations.
- **Intelligence** is the ability to improve understanding over time through reasoning, observation, reflection, and learning.

Architecture law: No component shall prioritize raw knowledge accumulation over deepening understanding. Memory storage shall prioritize semantic understanding over raw accumulation whenever practical. A memory system that understands what it stores is more valuable than one that merely stores everything.

All future evolution components must strengthen Atlas's internal understanding rather than simply increasing stored information. The evolution subsystem (`atlas/evolution/`) shall measure its success by how much it deepens Atlas's understanding of itself, its users, and its domain — not by how much data it accumulates.

### 4.2 Growth Pipeline

```
         Understanding Layer  ← permanent foundation
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

**Current position:**
- **Understanding Layer** is established as an architectural concept in this document.
- **Reasoning** and **Observation** are implemented.
- **Learning infrastructure** exists through `LearningManager` and `KnowledgeFeedback`. This is feedback storage, not a closed-loop learning system.
- **Phase 9.0 bridges observation and learning into a persistent self-model.** Outcome-level reflective learning and strategy adjustment remain future capabilities.

---

## 5. Atlas Evolution Principle

**Never rebuild. Always extend.**

- Every subsystem is independently replaceable.
- New capabilities are added as optional middleware layers.
- Existing working architecture is protected.
- Every major change requires verification before progression.

---

## 6. Development Philosophy

```
Understand → Design → Implement → Verify → Record → Improve
```

**Understand:** Read documentation, architecture, and existing code before making changes.

**Design:** Architecture-first design. Every feature must fit existing boundaries.

**Implement:** Additive changes only. Prefer new files over modifying existing ones.

**Verify:** Run the full test suite. Fix failures before proceeding.

**Record:** Update documentation, ADRs, and state files.

**Improve:** Reflect on outcomes and adjust future strategies.

---

## 7. Constitution Principles

Atlas is governed by 20 articles.

| # | Principle | One-line Meaning |
|---|-----------|----------------|
| 1 | User Ownership | Atlas belongs to its owner; no third party controls it |
| 2 | Provider Independence | Never depend on a single AI provider |
| 3 | Modularity | Every subsystem is independently replaceable |
| 4 | Transparency | Important actions are explained and recorded |
| 5 | Trust & Permission | Risky actions require user approval |
| 6 | Privacy | User data belongs to the user |
| 7 | Continuous Learning | Evaluate technologies by evidence, not popularity |
| 8 | Engineering Quality | Readable, maintainable, documented, tested code |
| 9 | Survivability | Recover from hardware, software, provider, and human failures |
| 10 | Human Partnership | Augment people; human judgment is final |
| 11 | Long-Term Vision | Built for decades, not demos |
| 12 | Red Flag Principle | Challenge ideas when evidence suggests a better solution |
| 13 | The Why Principle | Explain why, not just what |
| 14 | Continuous Improvement | Atlas is never finished; every subsystem evolves |
| 15 | Evidence Over Hype | Measure performance, reliability, security, maintainability |
| 16 | Human-Centered Automation | Eliminate repetitive work; preserve creativity and judgment |
| 17 | Knowledge Preservation | Preserve knowledge through docs, version control, recoverable history |
| 18 | Self-Maintenance | Monitor health; self-maintain when safe, ask permission when not |
| 19 | Responsible Intelligence | Honest, thoughtful analysis of complex subjects |
| 20 | Legacy | Outlive current hardware, software, providers, and creators |

**Engineering Promise:** Correctness over speed. Architecture over shortcuts. Reliability over hype. Learning over ego. Transparency over complexity. Long-term value over temporary convenience. Collaboration over individual preference.

---

## 8. Architecture Laws

| # | Law | Enforcement |
|---|-----|-------------|
| 1 | Separation of concerns | Each module has one clear responsibility |
| 2 | Dependency inversion | High-level modules depend on abstractions |
| 3 | Test-first | Every major feature requires tests before completion |
| 4 | Repository pattern | Data access is encapsulated in repositories |
| 5 | Modular design | Components are independent and replaceable |
| 6 | High cohesion / low coupling | Related logic stays together; modules use clean interfaces |
| 7 | Pure logic isolation | Reasoning layers must not import infrastructure |
| 8 | Service orchestration | Services coordinate; managers/engines contain logic |
| 9 | Event-driven flow | Cross-cutting concerns subscribe to events, not direct calls |
| 10 | Provider independence | AI providers are replaceable via abstraction |
| 11 | Backward compatibility | Existing public APIs must not break without review |
| 12 | Additive over destructive | Prefer adding new files over refactoring old ones |

---

## 9. Module Boundaries

### 9.1 Layer Rules

```
CLI / Presentation
        ↓
     Services
        ↓
     Managers
        ↓
   Repositories
        ↓
     Storage
```

- Each layer communicates only with adjacent layers.
- Business logic must never access storage directly.
- Circular dependencies are prohibited.
- Models are plain data with no business logic.

### 9.2 Module Responsibilities

| Layer / Subsystem | Responsibility |
|-------------------|----------------|
| Models | Data representation and serialization only |
| Understanding | Permanent foundation layer: reasoning, learning, memory, tool use — all operate on understanding, not raw knowledge |
| Managers | Domain operations and business logic |
| Repositories | Data access and persistence |
| Services | Coordinate multiple components |
| CLI | User interaction and command routing |
| Storage | Low-level read/write to disk |
| `core` | Boot, startup, and application lifecycle |
| `intelligence` | LEGACY: CognitiveLoop, CognitiveService (preserved, do not modify) |
| `lifecycle` | Lifecycle management |
| `models` | Shared domain models |
| `runtime` | Health, heartbeat, metrics, and runtime monitoring |
| `scheduler` | Scheduling components |
| `memory/context` | Context management layer |
| `evolution` | Self-observation, improvement planning, proposal generation, approval workflow — designed to deepen understanding, not merely accumulate changes |
| `goals` | Goal intelligence and self-directed improvement planning (Phase 8.3) |
| `identity` | Cognitive identity engine (Phase 8.0) |
| `experience` | Persistent experience accumulation and self-model evolution (Phase 9.0) |

### 9.3 Module Maturity Classification

| Maturity | Modules |
|----------|---------|
| Core (active, wired) | `kernel`, `cognition`, `reasoning`, `services`, `evolution`, `identity`, `goals`, `experience` |
| Infrastructure (active, wired) | `memory`, `storage`, `events`, `config` |
| Capability (active, wired) | `ai`, `knowledge`, `learning`, `workspace` |
| Active, wired (not fully wired) | `lifecycle`, `runtime`, `scheduler`, `models` |
| Legacy (preserved, do not modify) | `intelligence` |

### 9.4 Atlas Module Tree

```
atlas/
├── kernel/              Service container and root application
├── core/                Boot, startup, and application lifecycle
├── cognition/           API, context, engine, decisions (pure logic core)
├── reasoning/           Controller, models, capabilities, execution (pure logic)
│   ├── capabilities/    Capability selection
│   └── execution/       Registry, routing, dispatch, handlers
├── services/            High-level orchestration (CognitionService)
├── ai/                  Provider abstraction, registry, router
├── memory/              Models, ranking, search, repository, service, storage
│   └── context/         Context management layer
├── conversation/        Conversation service, history, prompt builder
├── intelligence/        LEGACY: CognitiveLoop, CognitiveService (preserved)
├── knowledge/           Knowledge management
├── learning/            Learning manager, knowledge feedback
├── events/              Event bus
├── config/              Configuration system
├── state/               State management
├── task/                Task management
├── workspace/           Workspace, project, resource management
├── storage/             Generic storage utilities
├── cli/                 Command-line interface
├── utils/               Shared utilities
├── lifecycle/           Lifecycle management
├── models/              Shared domain models
├── runtime/             Health, heartbeat, metrics, runtime monitoring
├── scheduler/           Scheduling components
├── evolution/           Self-evolution architecture (observation, planning, proposals, approval)
├── understanding/       Understanding Layer: concept extraction, pattern analysis, understanding graph, understanding engine
├── cognition/           Integrated cognitive pipeline (orchestration, models, metrics, state)
├── learning_engine/     Learning engine: strategy analysis, insight consolidation, learning memory
├── goals/               Goal intelligence and self-directed improvement planning
├── identity/            Cognitive identity engine
├── experience/          Persistent experience accumulation and self-model evolution
└── ...                 Additional modules (advanced_reasoning, toolchain, research, longterm, etc.)
```

Runtime data and storage locations:
- `atlas_data/` — runtime conversation and Atlas data
- `data/` — memory and knowledge JSON storage

---

## 10. Dependency Boundary Rules

### 10.1 Pure Logic Components

The following components must remain **pure logic** — no AI calls, no memory access, no knowledge access, no EventBus, no service imports:

- `CognitionEngine`
- `CognitionContext`
- `CognitionDecision`
- `ReasoningController`
- `CapabilityAnalyzer`
- `CapabilityRegistry`
- `CapabilityRouter`
- `CapabilityDispatcher`
- `ReasoningRecorder`
- `ReasoningOutcome`
- `SelfObservationEngine`
- `ImprovementPlanner`
- `ProposalGenerator`
- `ApprovalManager`
- `EvolutionMemory`
- All `atlas/evolution/` data models
- `CognitionPipeline`
- `CognitionState`
- `PipelineResult`
- `StageResult`
- `PipelineMetrics`
- All `atlas/cognition/` pipeline models
- `LearningEngine`
- `StrategyAnalyzer`
- `InsightConsolidator`
- `LearningMemory`
- All `atlas/learning_engine/` data models
- `ExperienceRepository`
- `ExperienceAccumulator`
- `TrendAnalyzer`
- `OutcomeTracker`
- `SelfModelEngine`
- All `atlas/experience/` data models

### 10.2 Prohibited Imports

`CognitionAPI` is an orchestration-facing API boundary. It may depend on `CognitionService`, while `CognitionEngine` remains pure logic.

| Component | Must NOT import |
|-----------|-----------------|
| `CognitionEngine` | `MemoryManagerService`, `KnowledgeManager`, `EventBus`, any service |
| `CognitionContext` | Any service or engine |
| `CognitionAPI` | `CognitionEngine`, `MemoryManagerService`, `KnowledgeManager`, `EventBus` |
| `CognitionDecision` | Any module beyond its own dataclass |
| Reasoning components | Any infrastructure module |
| `ReasoningRecorder` | Any infrastructure module |

### 10.3 Private Atlas-Owned Dependencies

The reasoning pipeline components and `ReasoningRecorder` are **private Atlas-owned dependencies**.

- Created and injected into `CognitionService` during `Atlas.start()`.
- **Not registered in `ServiceContainer`.**
- This keeps the public service surface small and preserves reasoning purity.

### 10.4 Kernel Service Keys

`ServiceContainer` registers 9 public service keys:

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
| `"runtime_coordinator"` | `RuntimeCoordinator` | Active (Phase 7.5) |
| `"understanding"` | `UnderstandingEngine` | Active (Phase 7.5) |
| `"world_model"` | `WorldModelEngine` | Active (Phase 7.5) |
| `"evolution_observer"` | `SelfObservationEngine` | Active (Phase 7.5) |
| `"learning_engine"` | `LearningEngine` | Active (Phase 7.5) |
| `"identity"` | `IdentityEngine` | Active (Phase 8.0) |
| `"feedback_coordinator"` | `FeedbackCoordinator` | Active (Phase 8.2) |
| `"goal_repository"` | `GoalRepository` | Active (Phase 8.3) |
| `"goal_intelligence"` | `GoalIntelligenceEngine` | Active (Phase 8.3) |
| `"experience_repository"` | `ExperienceRepository` | Active (Phase 9.0) |
| `"experience_accumulator"` | `ExperienceAccumulator` | Active (Phase 9.0) |
| `"self_model_engine"` | `SelfModelEngine` | Active (Phase 9.0) |

**All four cognition keys must remain registered.** Legacy keys must not be modified.

---

## 11. Coding Rules

### 11.1 Architecture Rules

- Prefer modular architecture with single-responsibility modules.
- Avoid unnecessary coupling.
- Keep pure logic layers separate from AI, memory, services, and EventBus.
- Use dependency injection; no internal instantiation of services.
- Never break existing APIs; maintain backward compatibility.
- Prefer additive changes over refactoring.
- Do not modify unrelated code during a task.

### 11.2 Data Rules

- Use Python `@dataclass` for all pure data models.
- Models represent data only; no business logic beyond serialization.
- Complex behaviour belongs in service or manager classes.
- Use constants for magic numbers and strings.

### 11.3 Code Style

| Element | Convention |
|---------|------------|
| Classes | `PascalCase` |
| Methods / functions | `snake_case` |
| Modules | `snake_case` |
| Packages | short, lowercase |
| Tests | `test_<module_name>.py` |
| Test classes | `Test<ComponentName>` |
| Test methods | `test_<behaviour>` |
| Booleans | predicates (`is_loaded`) |
| Arrays | plurals (`users`) |

### 11.4 Import Rules

- Explicit imports only — no `from module import *`.
- Group: standard library → third-party → atlas modules.
- Pure logic modules must not import infrastructure modules.
- All imports must resolve to real modules with exact exported names.

### 11.5 Error Handling

- Use exceptions for exceptional conditions, not control flow.
- Pure logic raises specific exceptions.
- Services catch and wrap exceptions as needed.
- Execution layer returns `ExecutionResult` with error information rather than raising.

### 11.6 Type Hints

- Use type hints for all function signatures.
- Use `Any` sparingly.
- Use `Optional[Type]` or `Type | None`.
- Use `list[Type]` and `dict[str, Type]`.

### 11.7 Documentation

- Every module has a docstring explaining purpose.
- Every public class and method has a docstring.
- Docstrings explain **what** and **why**, not just **how**.
- Update documentation when making architectural changes.

---

## 12. Testing Philosophy

- **Tests are mandatory.** No feature is complete without tests.
- Tests must pass before commit.
- Never modify tests to hide failures — fix the implementation.
- Every test class starts each test with a clean state using `setUp`.
- Tests must be order-independent.
- Use `tempfile` and `unittest.mock.patch` for isolation.
- Never use shared file state between tests.
- Pure logic layers must be testable without mocking infrastructure.
- Run the full test suite before finishing any task.

---

## 13. AI Working Protocol

### 13.1 Required Workflow

The complete development workflow is documented in `docs/DEVELOPMENT_WORKFLOW.md`. The canonical per-session workflow is:

```
1. Read README.md (public entry point)
2. Read ATLAS_STATE.md (authoritative current state)
3. Read ROADMAP.md (authoritative forward direction)
4. Read ATLAS_CORE.md (supporting/reference) when deeper principles are needed
5. Understand current state and architecture
6. Confirm the requested task
7. Implement only approved changes
8. Verify changes (run the full test suite)
9. Record updates and report result
```

**Entry-point note:** `README.md`, `docs/ATLAS_STATE.md`, and `docs/ROADMAP.md` are the canonical hierarchy. `ATLAS_CORE.md` is supporting/reference material and should be read after `ATLAS_STATE.md` when relevant.

> `ATLAS_MASTER_CONTEXT.md` is preserved as historical reference and is no longer the primary AI entry point.

### 13.2 Architecture Agent

**Allowed:**
- Read any file
- Analyse architecture and suggest designs
- Review code and decisions
- Create documentation and reports
- Ask clarifying questions

**Prohibited:**
- Modify source code without explicit approval
- Create or modify tests without explicit approval
- Run destructive commands
- Make autonomous architectural decisions

### 13.3 Implementation Agent

**Allowed:**
- Read any file
- Implement approved changes
- Write and run tests
- Debug and fix issues
- Modify files according to specifications

**Prohibited:**
- Make autonomous architectural changes
- Modify legacy components marked as preserved
- Break existing APIs
- Modify unrelated files

### 13.4 Safety Rules

1. Never run destructive commands without explicit approval.
2. Never modify legacy components marked as preserved.
3. Never break existing APIs.
4. Never make autonomous architectural changes.
5. Never commit without approval.
6. Never skip tests.

### 13.5 Explicit Approval

**Explicit approval** means user authorization for a specific implementation action.

**Approved additive changes** (within approved scope):
- New files
- New tests
- Isolated implementation changes

**Requires explicit approval:**
- New subsystem
- Architecture boundary changes
- Public API changes
- Dependency changes

### 13.6 Reporting Format

Every report must include:
- Summary: what changed, why, files created/modified
- Test results: total, passing, failing (raw terminal output per `docs/DEVELOPMENT_WORKFLOW.md`)
- Assumptions made
- Issues encountered

---

## 14. Permanent Architectural Decisions

Atlas currently contains two ADR numbering systems:
- **ADR-001 to ADR-010**: primary architecture decisions.
- **ADR-0001 to ADR-0003**: legacy/early architecture records.
- **docs/adr/ADR-001-workspace**: standalone workspace decision record.

| ID | Decision | Status |
|---:|----------|--------|
| ADR-001 | AI model independence via provider abstraction layer | Accepted |
| ADR-002 | Pure logic layer isolation for reasoning components | Accepted |
| ADR-003 | External AI models as replaceable providers | Accepted |
| ADR-004 | Python dataclasses for pure data models | Accepted |
| ADR-005 | Event-driven cognition flow via EventBus | Accepted |
| ADR-006 | Legacy `CognitiveLoop` and `CognitiveService` preserved indefinitely | Accepted |
| ADR-007 | Documentation memory layer as single-entry AI context | Accepted |
| ADR-008 | Two-role AI workflow: Planner + Developer | Accepted |
| ADR-009 | Service-based orchestration | Accepted |
| ADR-010 | Test-first development | Accepted |
| ADR-0001 | Service-oriented architecture | Accepted |
| ADR-0002 | JSON-based memory storage with future backend migration path | Accepted |
| ADR-0003 | Application lifecycle sequence: Boot Screen → Boot Manager → Dependency Checker → Service Registration → Service Startup → Application Ready | Accepted |
| ADR-001-workspace | Workspace as root organizational unit containing Projects containing Resources | Accepted |

> **Lifecycle note:** The documented boot lifecycle represents the intended Atlas lifecycle architecture. Runtime entry points may evolve independently as implementation matures.

---

## 15. Prohibited Patterns

| # | Pattern | Rationale |
|---|---------|-----------|
| 1 | Modify tests to hide failures | Fix the real bug, not the symptom |
| 2 | Delete user data automatically | User data belongs to the user |
| 3 | Break existing APIs without review | Other modules depend on stable interfaces |
| 4 | Ad-hoc security or input sanitisation | Security and input handling must use standard, reviewed approaches |
| 5 | Import packages not declared in project | Dependencies must be declared |
| 6 | Modify unrelated code during a task | One change per task keeps history clean |
| 7 | Write business logic in storage/repository layers | Separation of concerns |
| 8 | Business logic in models | Models are data containers only |
| 9 | Infrastructure in pure logic | Preserves testability and modularity |
| 10 | Hardcoded provider dependencies | Violates provider independence |
| 11 | Silent failures | Meaningful actions must be recorded or logged |
| 12 | Circular imports | Creates unmaintainable coupling |
| 13 | Unnecessary complexity | Hard-to-understand code becomes unmaintainable |
| 14 | Refactoring without explicit approval | Prefer additive changes |

---

## 16. Historical Reference Index

For deeper context, read these preserved files after ATLAS_CORE.md and ATLAS_STATE.md:

| Topic | File |
|-------|------|
| Full constitution | `docs/ATLAS_CONSTITUTION.md` |
| Detailed architecture (historical) | `docs/archive/architecture/ARCHITECTURE_v1.md` |
| Deep cognition architecture (historical) | `docs/archive/architecture/cognition.md` |
| Full decision records | `docs/ARCHITECTURE_DECISIONS.md` |
| Current state (historical) | `docs/archive/context/CURRENT_STATE.md` |
| Roadmap | `docs/ROADMAP.md` |
| Development history (historical) | `docs/archive/development/DEVELOPMENT_LOG.md` |
| Coding guidelines (historical) | `docs/archive/development/CODING_GUIDELINES.md` |
| Development workflow | `docs/DEVELOPMENT_WORKFLOW.md` |
| AI workflow protocol (historical) | `docs/archive/development/AI_WORKFLOW_PROTOCOL.md` |
| Model strategy (historical) | `docs/archive/development/MODEL_STRATEGY.md` |
| Future direction (historical) | `docs/archive/roadmaps/FUTURE_DIRECTION.md` |
| Engineering guide (historical) | `docs/archive/development/ATLAS_ENGINEERING_GUIDE.md` |
| Version history (historical) | `docs/archive/releases/CHANGELOG.md` |
| Historical checkpoints | `docs/archive/*` |
