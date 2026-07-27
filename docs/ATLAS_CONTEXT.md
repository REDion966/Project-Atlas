# ATLAS CONTEXT — Permanent AI & Developer Onboarding Document

**Read this document first when starting work on Project Atlas.**

---

## 0. Quick Navigation

| Document | Purpose | Authority |
|---|---|---|
| **ATLAS_CONTEXT.md** *(this file)* | First-read onboarding for AI assistants and developers | **Read first** |
| ATLAS_VISION.md | Long-term North Star and purpose | Vision authority |
| ATLAS_CONSTITUTION.md | 20 immutable engineering articles | Constitutional authority |
| ATLAS_CORE.md | Permanent architectural principles and rules | Architecture authority |
| ATLAS_STATE.md | Current operational state and resume point | State authority |
| ARCHITECTURE.md | Detailed system architecture reference | Reference |
| MODEL_STRATEGY.md | AI provider and workflow strategy | Reference |
| ROADMAP.md | Future development phases | Reference |

**Recommended reading order for deep context:** ATLAS_CONTEXT.md → ATLAS_VISION.md → ATLAS_CONSTITUTION.md → ATLAS_CORE.md → ATLAS_STATE.md

---

## 1. What Is Project Atlas?

**Project Atlas** is a long-term, Python-based modular AI agent operating framework.

Atlas is **NOT**:
- A chatbot or simple conversational wrapper
- A single AI model prompt chain
- A cloud-dependent service or SaaS product
- A demo, prototype, or short-term project
- An autonomous code-modification agent

Atlas **IS**:
- A structured AI operating framework with modular, independently-replaceable subsystems
- A system designed to coordinate memory, knowledge, reasoning, planning, learning, tools, and AI providers into a unified architecture
- A permanent identity and memory layer that survives AI model changes, provider shifts, and technology transitions
- An architecture designed for long-term evolution through incremental, verified, additive changes
- A system to augment human capability — not replace human judgment

### Core Identity Statement

> Atlas is an independent AI operating framework.
> AI models are tools. Atlas is the intelligence.
> Models may change. Atlas remains.

---

## 2. Long-Term Vision

Atlas is built for **decades, not demos**. The long-term vision is a self-evolutionary AI operating system that grows more capable over time while remaining under human ownership and control.

### Evolutionary Stages

```
Documented Self-Analysis  →  Guided Improvement  →  Bounded Optimisation  →  Autonomous Evolution
        (current)              (near future)          (medium term)           (long term)
```

**Current Stage:** Documented Self-Analysis (Phase 9.0 complete)

### Intelligence Maturity Levels

| Level | Name | Status |
|---|---|---|
| 1 | Reactive Response | Past |
| 2 | Structured Cognition | Past |
| 3 | Observable Reasoning | Past |
| 4 | Reflective Learning | Past |
| 5 | Persistent Self-Model | **Current (Phase 9.0)** |
| 6+ | Bounded Autonomy / Autonomous Evolution | Future |

### Capabilities Currently NOT Implemented

Atlas currently does **NOT**:
- Autonomously modify source code
- Perform autonomous reflection or strategy adjustment
- Perform autonomous planning or improvement
- Persist experiences to disk (Phase 9.1+)
- Use cross-session experience loading

These are deliberate constraints. Future capabilities require the corresponding roadmap phases and explicit user approval.

---

## 3. Current Development Philosophy

### Core Principles

| # | Principle | Meaning |
|---|-----------|---------|
| 1 | **Build the foundation first** | Core infrastructure before peripheral features |
| 2 | **Preserve the existing roadmap** | Do not randomly redesign or re-scope |
| 3 | **Prefer additive changes** | New files over modification of working code |
| 4 | **Never rebuild — always extend** | Existing working architecture is protected |
| 5 | **Modularity** | Every subsystem is independently replaceable |
| 6 | **Provider independence** | Never depend on a single AI provider |
| 7 | **Test-first** | Every major feature requires tests |
| 8 | **Long-term thinking** | Every design decision supports long-term sustainability |
| 9 | **Human partnership** | Augment people; human judgment is final |
| 10 | **Evidence over hype** | Technologies evaluated by measurable performance |

### Development Workflow

```
Understand → Design → Implement → Verify → Record → Improve
```

1. **Understand** — Read documentation, architecture, and existing code before making changes
2. **Design** — Architecture-first design; every feature must fit existing boundaries
3. **Implement** — Additive changes only; prefer new files over modifying existing ones
4. **Verify** — Run the full test suite; fix all failures before proceeding
5. **Record** — Update documentation and state files
6. **Improve** — Reflect on outcomes and adjust future strategies

### Engineering Promise

**Correctness over speed. Architecture over shortcuts. Reliability over hype. Learning over ego. Transparency over complexity. Long-term value over temporary convenience. Collaboration over individual preference.**

---

## 4. Architecture Priorities

### Layer Architecture

```
CLI / Presentation
        ↓
     Services
        ↓
     Managers / Engines
        ↓
   Repositories
        ↓
     Storage
```

- Each layer communicates only with adjacent layers
- Business logic must never access storage directly
- Circular dependencies are **prohibited**
- Models are plain data — no business logic beyond serialization

### Pure Logic Isolation

The following components must remain **pure logic** — no AI calls, no memory access, no knowledge access, no EventBus, no service imports:

- All `atlas/reasoning/` components
- `CognitionEngine`, `CognitionContext`, `CognitionDecision`
- All `atlas/cognition/` pipeline models
- All `atlas/evolution/` data models and engines
- All `atlas/learning_engine/` components
- All `atlas/experience/` components
- All `atlas/understanding/` consolidation components
- All `atlas/goals/` components

### Currently Wired Subsystems (22 kernel service keys)

| Key | Module | Phase |
|---|---|---|
| `ai` | AIService | Foundation |
| `conversation` | ConversationService | Foundation |
| `memory` | MemoryManagerService | Phase 5 |
| `knowledge` | KnowledgeManager | Phase 5 |
| `cognition` (legacy) | CognitiveLoop | Preserved |
| `cognitive` (legacy) | CognitiveService | Preserved |
| `cognition_service` | CognitionService | Phase 5.6 |
| `cognition_api` | CognitionAPI | Phase 5.6 |
| `tasks` | TaskManager | Foundation |
| `runtime_coordinator` | RuntimeCoordinator | Phase 7.5 |
| `understanding` | UnderstandingEngine | Phase 7.5 |
| `world_model` | WorldModelEngine | Phase 7.5 |
| `evolution_observer` | SelfObservationEngine | Phase 7.5 |
| `learning_engine` | LearningEngine | Phase 7.5 |
| `identity` | IdentityEngine | Phase 8.0 |
| `feedback_coordinator` | FeedbackCoordinator | Phase 8.2 |
| `goal_repository` | GoalRepository | Phase 8.3 |
| `goal_intelligence` | GoalIntelligenceEngine | Phase 8.3 |
| `experience_repository` | ExperienceRepository | Phase 9.0 |
| `experience_accumulator` | ExperienceAccumulator | Phase 9.0 |
| `self_model_engine` | SelfModelEngine | Phase 9.0 |

### Module Maturity Classification

| Maturity | Modules |
|---|---|
| **Core** (active, wired) | `kernel`, `cognition`, `reasoning`, `services`, `evolution`, `identity`, `goals`, `experience` |
| **Infrastructure** (active, wired) | `memory`, `storage`, `events`, `config` |
| **Capability** (active, wired) | `ai`, `knowledge`, `learning`, `workspace` |
| **Future / scaffold** (not fully wired) | `agents`, `automation`, `lifecycle`, `runtime`, `scheduler`, `skills`, `interfaces`, `models` |
| **Legacy** (preserved, do not modify) | `intelligence` |

---

## 5. Development Rules

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

### Code Style

| Element | Convention |
|---|---|
| Classes | `PascalCase` |
| Methods / functions | `snake_case` |
| Modules | `snake_case` |
| Packages | short, lowercase |
| Tests | `test_<module_name>.py` |
| Test classes | `Test<ComponentName>` |
| Test methods | `test_<behaviour>` |
| Booleans | predicates (`is_loaded`) |
| Arrays | plurals (`users`) |
| Data models | `@dataclass` |
| Type hints | Required for all function signatures |
| Imports | Explicit only — no `from module import *` |

### Prohibited Patterns

| Pattern | Rationale |
|---|---|
| Modify tests to hide failures | Fix the real bug, not the symptom |
| Delete user data automatically | User data belongs to the user |
| Break existing APIs without review | Other modules depend on stable interfaces |
| Import packages not declared in project | Dependencies must be declared |
| Modify unrelated code during a task | One change per task keeps history clean |
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

**Current test count:** 948+ passing (Phase 9.0)

---

## 6. AI Model Usage Strategy

Atlas development uses a structured multi-model strategy. Different models are used for different tasks based on their strengths. This ensures optimal results while maintaining provider independence.

### Usage Philosophy

| Principle | Meaning |
|---|---|
| **Models are tools, not dependencies** | No single model is required for Atlas to function |
| **Match the model to the task** | Different strengths for different work types |
| **Provider independence is constitutional** | No hardcoded model names in source code |
| **Documentation memory is model-agnostic** | Any capable model can understand Atlas by reading docs |
| **Two-role workflow** | Strategic planning and tactical implementation are separated |

### Model Allocation Strategy

#### Cline Pass Models

Used by the Cline AI assistant role (architecture and development):

| Work Type | Recommended Model | Reason |
|---|---|---|
| High-level architecture and complex reasoning | **Claude Opus 5** | Deep reasoning, trade-off analysis, architectural design |
| Large repository analysis | **DeepSeek V4 Pro** | Large context window, efficient code traversal |
| Large coding tasks | **Kimi K2.7 Code** | Code generation, large-scale implementation |

**Other Available (alternative/specialized):**
- GLM 5.2
- Kimi K3
- DeepSeek V4 Flash
- Kimi K2.6
- Mimo v2.5 Pro
- Mimo v2.5
- Minimax M3
- Qwen 3.7 Max
- Qwen 3.7 Plus

#### Sixth Models

Used by the Sixth AI assistant role (daily development, code review):

| Work Type | Recommended Model | Reason |
|---|---|---|
| Daily development | **Claude Sonnet 4.6** | Balanced speed and quality for iterative work |
| Deep code review | **Claude Opus 4.5** | Thorough analysis, edge case detection |
| Fast coding | **Claude Haiku 4.5**, **GPT-5.4 Mini**, **GPT-5 Mini** | Speed for simple implementations |
| Complex reasoning | **GPT-5.4**, **GPT-5.2**, **GPT-5**, **o3**, **o3 Mini**, **o4 Mini**, **o1** | Multi-step logical reasoning |
| Documentation and explanations | **Gemini 2.5 Pro** | Clear, structured explanations |

### How This Affects Development

- When starting a new complex feature: prefer Claude Opus 5 or GPT-5.4 for design
- When implementing: prefer Kimi K2.7 Code or Claude Sonnet 4.6
- When reviewing: prefer Claude Opus 4.5
- When writing documentation: prefer Gemini 2.5 Pro
- When doing quick fixes: prefer Claude Haiku 4.5 or GPT-5.4 Mini

---

## 7. AI Assistant Working Rules

Whenever helping with Atlas, follow these rules:

### Before Doing Anything

1. **First, understand the current architecture** — read this file, then ATLAS_CORE.md, then ATLAS_STATE.md
2. **Read existing documentation** before making assumptions
3. **Check the current git state** — verify branch, HEAD, and tags
4. **Run the test suite** to confirm the baseline before making changes

### During Development

5. **Avoid unnecessary rewrites** — the existing architecture is intentional
6. **Prefer incremental improvements** — one focused change at a time
7. **Explain major technical decisions** — document trade-offs and rationale
8. **Maintain modular design** — keep pure logic separate from infrastructure
9. **Maintain backward compatibility** — never break existing APIs without explicit approval
10. **Do not modify unrelated code** — one change per task

### Before Finishing

11. **Suggest tests for important features** — if a feature needs tests, say so
12. **Keep documentation updated** — update ATLAS_STATE.md when phases complete
13. **Consider long-term scalability** — will this decision hold up over time?
14. **Run the full test suite** — confirm nothing is broken
15. **Record the result** — report what changed, why, and the test status

### Safety Rules

| Rule | Detail |
|---|---|
| Never run destructive commands without approval | No rm -rf, no database drops |
| Never modify legacy components marked as preserved | `atlas/intelligence/` is preserved |
| Never break existing APIs | Backward compatibility always |
| Never make autonomous architectural changes | Requires explicit approval |
| Never commit without approval | The user controls version control |
| Never skip tests | Tests are mandatory |

### What "Explicit Approval" Means

**Explicit approval** = user authorization for a specific implementation action.

**Approved without additional approval** (within agreed scope):
- New files
- New tests
- Isolated implementation changes

**Requires explicit user approval:**
- New subsystem creation
- Architecture boundary changes
- Public API changes
- Dependency additions or changes

---

## 8. Current Project State (Quick Reference)

| Field | Value |
|---|---|
| Git Branch | `phase5-memory-evolution` |
| HEAD | `67bc3c9bf2697ee817a44b471ee72f3ff6f0c708` |
| Latest Tag | `phase-7.5-complete` |
| Latest Phase | **Phase 9.0 — Persistent Self-Model & Experience Accumulation** |
| Tests Passing | **948+** |
| Intelligence Level | **Level 5 — Persistent Self-Model** |
| Repository | `github.com/REDion966/Project-Atlas` |

### Next Milestone

**Phase 9.1+ — Continuous Improvement** (disk persistence, cross-session loading, self-model context integration)

---

## 9. Architectural Map

### Module Directory

```
atlas/
├── kernel/              Service container and root application
├── core/                Boot, startup, application lifecycle
├── cognition/           API, context, engine, decisions, pipeline, state
├── reasoning/           Controller, models, capabilities, execution, planning, reflection
├── tools/               Registry, selector, executor, engine
├── services/            High-level orchestration (CognitionService)
├── ai/                  Provider abstraction, registry, router, routing
│   ├── providers/       Provider implementations (Ollama, OpenAI, Anthropic, LM Studio, Mock)
│   ├── router/          AI routing logic
│   └── routing/         Model routing subsystem
├── memory/              Models, ranking, search, repository, service, context
├── conversation/        Service, history, prompt builder
├── knowledge/           Knowledge management
├── learning/            Learning manager, knowledge feedback
├── learning_engine/     Strategy analysis, insight consolidation, learning memory
├── understanding/       Concept extraction, pattern analysis, consolidation, engine
├── evolution/           Self-observation, improvement planning, proposal generation, approval
├── experience/          Persistent experience accumulation, self-model evolution
├── goals/               Goal intelligence, self-directed improvement planning
├── identity/            Cognitive identity engine
├── events/              Event bus
├── config/              Configuration system
├── state/               State management
├── task/                Task management
├── workspace/           Workspace, project, resource management
├── cli/                 Command-line interface
├── agents/              Agent abstractions (scaffold)
├── automation/          Automation workflows (scaffold)
├── interfaces/          Contracts and abstractions (scaffold)
├── lifecycle/           Lifecycle management (scaffold)
├── runtime/             Health, heartbeat, metrics (scaffold)
├── scheduler/           Scheduling components (scaffold)
├── skills/              Skill abstractions (scaffold)
├── models/              Shared domain models (scaffold)
├── storage/             Generic storage utilities
└── intelligence/        LEGACY — preserved, do not modify
```

### Runtime Data Locations

| Path | Purpose |
|---|---|
| `atlas_data/` | Runtime conversation and Atlas data |
| `atlas_data/atlas_experience.db` | Experience database |
| `data/` | Memory and knowledge JSON storage |

### Test Location

All tests reside in `tests/`, mirroring the `atlas/` structure. Current count: **948+ tests**.

---

## 10. Getting Started Checklist

When beginning work on Atlas for the first time:

- [ ] Read this file (ATLAS_CONTEXT.md)
- [ ] Read ATLAS_VISION.md (North Star)
- [ ] Read ATLAS_CONSTITUTION.md (20 immutable rules)
- [ ] Read ATLAS_CORE.md (Architecture principles)
- [ ] Read ATLAS_STATE.md (Current state)
- [ ] Verify git state: `git branch --show-current`, `git rev-parse HEAD`
- [ ] Run full test suite: `pytest` (confirm 948+ passing)
- [ ] Explore `atlas/` module structure
- [ ] Understand the runtime pipeline in `atlas/runtime/runtime_coordinator.py`
- [ ] Identify where the next task fits within the existing architecture
- [ ] Make additive, backward-compatible changes only
- [ ] Run tests again before finishing
- [ ] Update ATLAS_STATE.md if a phase is completed

---

## 11. File Purpose

This file (`docs/ATLAS_CONTEXT.md`) serves as:

- **The first document** any AI assistant or developer should read when starting work on Atlas
- **A permanent onboarding document** that captures the full context in one place
- **A quick reference** for project vision, philosophy, rules, and architecture
- **A model strategy guide** explaining which AI models to use for which tasks
- **The bridge between high-level vision** (ATLAS_VISION.md) and **day-to-day development** (ATLAS_CORE.md, ATLAS_STATE.md)

It does **not** replace the canonical documents. It **points to** them and provides the framework for understanding them.

---

*Document created: July 2026*
*Project Atlas — docs/ATLAS_CONTEXT.md*
