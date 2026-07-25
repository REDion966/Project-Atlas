# ATLAS MASTER CONTEXT

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

**The single file an AI model needs to understand Project Atlas.**

> This document was the previous AI onboarding context. It has been replaced as the primary AI entry point by docs/ATLAS_CORE.md and docs/ATLAS_STATE.md. It is now historical context only.

---

## 1. What Is Project Atlas?

Atlas is a modular, AI-independent intelligent agent framework designed to augment human capability through trustworthy, modular, and intelligent automation. Atlas is not a chatbot, not a single AI model wrapper, and not a cloud-dependent service. Atlas is an intelligent operating framework for coordinating memory, knowledge, tools, automation, reasoning, and AI providers in a unified, extensible architecture.

Atlas is built to last for decades, not demos. Every design decision prioritises long-term sustainability, provider independence, and human partnership.

---

## 2. Why Atlas Exists

Modern AI capabilities advance rapidly, but each new model, provider, or framework resets the context of what came before. Atlas exists to solve this problem:

- **AI models change.** Atlas architecture and knowledge must persist.
- **AI providers disappear.** Atlas must remain functional.
- **Context is fragmented.** Atlas centralises memory, knowledge, and decisions in a permanent documentation layer.
- **Prompts are ephemeral.** Atlas replaces prompt engineering with structured reasoning, capability selection, and execution routing.

Atlas is the permanent memory and identity layer that survives any AI model or provider change.

---

## 3. Long-Term Vision

Atlas will eventually contain:

- **Long-term memory** — persistent recollections across sessions.
- **Short-term memory** — session-aware context.
- **Project knowledge** — structured domain expertise.
- **Decision history** — complete record of architectural and operational decisions.
- **User preferences** — learned behaviour and configuration.
- **Code understanding** — structured comprehension of its own codebase.
- **Self-improvement capabilities** — safe, bounded, approved optimisation of its own systems.

Atlas aspires to be a research, analysis, and development partner — capable of assisting its own evolution with user permission.

---

## 4. Core Philosophy

| Principle | Meaning |
|-----------|---------|
| **Provider Independence** | Atlas must never depend on a single AI provider. All AI services are replaceable. |
| **Modularity** | Every subsystem is independently replaceable. No component requires rebuilding Atlas. |
| **Knowledge Preservation** | No important knowledge depends on a single device, person, or AI provider. |
| **Transparency** | Atlas explains important decisions. Meaningful actions are recorded. |
| **User Ownership** | Atlas belongs to its owner. No third party controls Atlas. |
| **Evidence Over Hype** | Technologies are evaluated by measurable performance, not popularity. |
| **Human Partnership** | Atlas augments people. Human judgment remains the final authority. |
| **Engineering Quality** | Readable code, maintainable architecture, meaningful documentation, automated testing. |

---

## 5. Model-Independent AI Architecture

Atlas uses a **Planner + Developer** two-role AI workflow:

**Planner AI:**
- Architecture planning
- System design
- Large-scale decisions
- Design review
- Does not modify code without approval

**Developer AI:**
- Implementation
- Debugging
- Testing
- Code modification

**Critical rule:** Both roles are replaceable. Atlas must never depend on a specific AI provider. The documentation memory layer ensures any AI model can understand and work with Atlas by reading these files first.

---

## 6. Development Principles

- Prefer modular architecture with single-responsibility modules.
- Avoid unnecessary coupling between components.
- Keep pure logic layers separate from AI, memory, services, and EventBus.
- Use dataclasses for pure data models.
- Add tests with every feature.
- Never break existing APIs — maintain backward compatibility.
- Prefer additive changes over refactoring.
- Document every completed work session.

---

## 7. Current Architecture Summary

```
atlas/
├── kernel/              Service container and root application
├── cognition/           Public API, context, engine, decisions
├── reasoning/           Controller, models, capability analysis
│   ├── capabilities/    Capability selection and models
│   └── execution/       Registry, routing, dispatching, handlers
├── services/            High-level orchestration services
├── ai/                  AI provider abstraction (providers, router, registry)
├── memory/              Memory system (models, ranking, search, repository, service)
├── conversation/        Conversation management
├── intelligence/        Legacy cognitive loop
├── knowledge/           Knowledge management
├── learning/            Learning and feedback
├── events/              Event bus
├── config/              Configuration system
└── state/               State management
```

**Current pipeline (runtime integrated):**

```
User Input
    │
    ▼
CognitionService
    │
    ├──→ Memory / Knowledge retrieval
    ├──→ CognitionContext
    ├──→ CognitionEngine
    │
    ▼
CognitionDecision
    │
    └──→ ReasoningController
         │
         ▼
    ReasoningPlan
         │
         ▼
    CapabilityAnalyzer
         │
         ▼
    list[Capability]
         │
         ▼
    CapabilityRouter
         │
         ▼
    list[ExecutionRoute]
         │
         ▼
    CapabilityDispatcher
         │
         ▼
    list[ExecutionResult]
         │
         ▼
     decision.data["reasoning"]  ← goal, capabilities, routes, results
          │
          ▼
     ReasoningRecorder.record()  ← Phase 6.5.2
          │
          ▼
     ReasoningOutcome stored     ← goal, capabilities, routes, results, success
```

All reasoning, capability analysis, routing, execution, and outcome recording layers remain **pure logic** — no AI calls, no memory access, no knowledge access, no EventBus dependencies. `CognitionService` orchestrates the pipeline as an optional runtime integration while preserving this purity.

---

## 8. Current Status

- **Branch:** `phase5-memory-evolution`
- **Completed phases:** Phase 5 (Memory evolution), Phase 6.1–6.5.2 (Reasoning foundation through Reasoning Outcome Recording)
- **Tests passing:** 436
- **Current task:** Phase 6.5.2 Reasoning Outcome Recording & Observability completed.
- **Next:** Continue adaptive intelligence roadmap (model routing, reflection, planning, tool intelligence).

---

## 9. How to Work With Atlas

1. Read the canonical AI memory files in order: `docs/ATLAS_CORE.md`, then `docs/ATLAS_STATE.md`.
2. Refer to this document (`ATLAS_MASTER_CONTEXT.md`) and `docs/CURRENT_STATE.md` as historical/reference context only.
3. Understand the architecture from `ARCHITECTURE.md`.
4. Check `ARCHITECTURE_DECISIONS.md` for past decisions.
5. Review `CODING_GUIDELINES.md` before writing code.
6. Confirm the requested task against `ROADMAP.md`.
7. Implement only approved changes.
8. Run the full test suite.
9. Report the result.

---

## 10. The Constitution

Atlas is governed by the **Atlas Constitution** (see `ATLAS_CONSTITUTION.md`). The constitution defines 20 articles covering user ownership, provider independence, modularity, transparency, trust, privacy, continuous learning, engineering quality, survivability, human partnership, and more. Every design decision should align with the constitution.