# Atlas Roadmap

---
> ⚠️ HISTORICAL / REFERENCE DOCUMENT
>
> This document is preserved for detailed context, history, and architectural reference.
>
> Canonical AI startup files:
>
> 1. docs/ATLAS_CORE.md
> 2. docs/ATLAS_STATE.md
>
> Authority order:
>
> - Source code = actual runtime behavior truth
> - ATLAS_CORE.md = permanent architectural principles and rules
> - ATLAS_STATE.md = current operational state and resume point
> - Historical documents = supplementary context only
>
> Historical documents must not override ATLAS_CORE.md or ATLAS_STATE.md.
---

**Future development roadmap for Project Atlas.**

**Last updated:** July 2026

---

## Current Phase

### Phase 6 — Adaptive Intelligence Foundation

Phase 6 is the current major development cycle. Sub-phases:

| Sub-Phase | Description | Status |
|-----------|-------------|--------|
| 6.1 | Reasoning foundation — `ReasoningController`, `ReasoningPlan` | Complete |
| 6.2 | Capability selection — `CapabilityAnalyzer`, `Capability` models | Complete |
| 6.3 | Capability execution layer — `CapabilityRegistry`, `CapabilityDispatcher` | Complete |
| 6.4 | Adaptive execution routing — `CapabilityRouter`, `ExecutionRoute` | Complete |
| **6.5** | **Documentation Memory Foundation** — permanent documentation layer | **Complete** |
| 6.5.1 | Reasoning Runtime Integration — default handlers, CognitionService integration, Atlas wiring | Complete |
| 6.5.2 | Reasoning Outcome Recording & Observability — in-memory ring buffer for reasoning outcomes | Complete |

---

## Documentation Memory Layer Completed

The Documentation Memory Foundation has been completed.

This milestone established Atlas's permanent documentation memory consisting of:

- ATLAS_MASTER_CONTEXT.md (historical reference context)
- CURRENT_STATE.md (historical reference state snapshot)
- ARCHITECTURE.md
- DEVELOPMENT_LOG.md
- ROADMAP.md
- ARCHITECTURE_DECISIONS.md
- CODING_GUIDELINES.md
- MODEL_STRATEGY.md
- AI_WORKFLOW_PROTOCOL.md
- FUTURE_DIRECTION.md

The canonical AI memory entry points are now ATLAS_CORE.md and ATLAS_STATE.md. This documentation layer provides long-term project continuity and allows future AI models, providers, and developers to understand Atlas without relying on previous conversations.

---

## Future Phases

### Phase 6.5.2 — Reasoning Outcome Recording & Observability

**Goal:** Record completed reasoning pipeline outcomes for future reflection and observability.

**Key features:**
- `ReasoningOutcome` dataclass for reasoning pipeline snapshots
- `ReasoningRecorder` bounded in-memory ring buffer (default max 100)
- Optional injection into `CognitionService`
- Private Atlas-owned dependency (not in ServiceContainer)
- Backward compatible when recorder is missing

**Status:** Complete

---

### Phase 6.6 — Model Routing

**Goal:** Select the optimal AI model per request based on complexity, latency, and cost constraints.

**Key features:**
- Model capability profiling
- Request complexity analysis
- Latency and cost optimization
- Fallback strategies when preferred models are unavailable

**Status:** Planned

---

### Phase 6.7 — Reflection System

**Goal:** Allow Atlas to evaluate its own decisions and adjust future reasoning strategies.

**Key features:**
- Decision evaluation engine
- Strategy adjustment based on outcomes
- Configurable reflection depth
- Integration with learning feedback loop

**Status:** Planned

---

### Phase 6.8 — Planning Engine

**Goal:** Decompose complex goals into ordered sub-tasks before execution.

**Key features:**
- Goal decomposition algorithms
- Dependency-aware task ordering
- Parallel execution planning
- Plan validation and recovery

**Status:** Planned

---

### Phase 6.9 — Tool Intelligence

**Goal:** Dynamically choose from available tools and skills based on cognition decisions.

**Key features:**
- Tool capability registry
- Context-aware tool selection
- Tool chaining and composition
- Skill discovery and integration

**Status:** Planned

---

### Phase 6.10+ — Continuous Improvement

**Goal:** Enable safe, bounded optimisation of internal cognition parameters through feedback analysis.

**Key features:**
- Performance metrics collection
- Bounded parameter optimisation
- Safety constraints and oversight
- Approval-based improvement cycles

**Status:** Conceptual

---

## Long-Term Vision Beyond Phase 6

### Memory System Expansion

- **Long-term memory** — persistent recollections across sessions and restarts
- **Short-term memory** — session-aware context with decay
- **Episodic memory** — event-sequence recollection
- **Semantic memory** — structured knowledge representation

### Knowledge System

- **Project knowledge** — structured domain expertise per project
- **Code understanding** — structured comprehension of the Atlas codebase
- **User preferences** — learned behaviour and configuration over time
- **Cross-session learning** — knowledge transfer between sessions

### Intelligence Layer

- **Multi-model orchestration** — strategic use of different models for different tasks
- **Self-directed research** — ability to gather and synthesise information autonomously
- **Controlled self-modification** — safe, approved modification of internal systems
- **Collaborative problem-solving** — multi-agent coordination

### User Interface

- **Rich CLI** — enhanced command-line interface with visual elements
- **Web interface** — browser-based Atlas interaction
- **API server** — programmatic access to Atlas services
- **Plugin system** — extensible user-contributed capabilities

### Reliability and Operations

- **Health monitoring** — comprehensive system health tracking
- **Automated recovery** — self-healing on failure
- **Backup and restore** — full system state preservation
- **Audit logging** — complete action history for accountability

---

## Planning Notes

- This roadmap is a **living document** and will evolve as Atlas develops.
- Phase ordering may change based on technical dependencies and priorities.
- Each phase should be implemented as an **optional middleware layer** where possible.
- No phase should require rebuilding Atlas or breaking existing APIs.
- **Backward compatibility** is always maintained.

---

## Guiding Principles for All Future Work

1. **Provider independence** — never depend on a single AI provider
2. **Modular design** — each feature is independently replaceable
3. **Pure logic separation** — keep reasoning free of infrastructure dependencies
4. **Test coverage** — all new features require tests
5. **Additive changes** — prefer adding over refactoring
6. **Documentation** — document every phase as it is completed