# Atlas Architecture Decisions

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

**Decision record system for Project Atlas.**

**Last updated:** July 2026

---

## Format

Each decision follows this structure:

| Field | Description |
|-------|-------------|
| **ID** | Unique identifier (ADR-NNN) |
| **Date** | When the decision was made |
| **Status** | Proposed, Accepted, Deprecated, Superseded |
| **Context** | Why this decision was needed |
| **Decision** | What was decided |
| **Consequences** | What this decision means for the project |

---

## ADR-001: AI Model Independence

| Field | Value |
|-------|-------|
| **ID** | ADR-001 |
| **Date** | Early 2026 |
| **Status** | Accepted |
| **Context** | AI models and providers change frequently. Different providers offer different capabilities, pricing, and availability. Atlas needed an architecture that would survive provider changes without requiring rewrites. |
| **Decision** | Atlas must be AI-model independent. All AI interactions go through a provider abstraction layer (`atlas/ai/provider.py`). Providers are registered dynamically via `AIManager` and selected at runtime through configuration. The kernel never imports a specific provider implementation directly. |
| **Consequences** | - Adding a new provider requires only implementing the provider interface<br>- Atlas continues functioning if a provider disappears<br- Provider selection can change without code changes<br>- Slight indirection overhead for AI calls |


## ADR-002: Pure Logic Layer Isolation

| Field | Value |
|-------|-------|
| **ID** | ADR-002 |
| **Date** | July 2026 |
| **Status** | Accepted |
| **Context** | During Phase 6 development, it became clear that reasoning, capability analysis, and execution logic should not depend on infrastructure concerns. Mixing pure logic with AI calls, memory access, or service dependencies made testing difficult and created tight coupling. |
| **Decision** | Pure logic layers (reasoning, capability analysis, routing, execution, registry) must not depend on AI providers, memory services, knowledge managers, EventBus, or any infrastructure. They receive all data through parameters and return results through data models. |
| **Consequences** | - Reasoning pipeline is fully testable without mocking infrastructure<br>- Components can be developed and verified independently<br>- Infrastructure changes don't affect pure logic<br>- Clear separation of concerns improves maintainability<br>- Slightly more data passing at component boundaries |


## ADR-003: External AI Models as Replaceable Providers

| Field | Value |
|-------|-------|
| **ID** | ADR-003 |
| **Date** | Early 2026 |
| **Status** | Accepted |
| **Context** | Atlas needs intelligence to process natural language, generate responses, and make decisions. Rather than embedding AI logic directly, Atlas should treat AI models as external services that can be swapped. |
| **Decision** | Use external AI models as replaceable intelligence providers. Atlas owns memory, knowledge, and identity. AI providers are stateless computation resources. The provider interface defines a contract that any AI service must satisfy. |
| **Consequences** | - Atlas identity and knowledge persist across provider changes<br>- AI providers can be upgraded independently<br>- Multiple providers can be used for different tasks (Planner vs Developer)<br>- Provider cost and latency can be optimised per use case |


## ADR-004: Dataclass Models for Pure Data

| Field | Value |
|-------|-------|
| **ID** | ADR-004 |
| **Date** | Early 2026 |
| **Status** | Accepted |
| **Context** | Data models were initially implemented with custom classes, leading to inconsistent serialisation, boilerplate code, and unnecessary complexity. |
| **Decision** | Use Python dataclasses for all pure data models. Models represent data only — no business logic beyond serialisation. Complex behaviour belongs in service or manager classes. |
| **Consequences** | - Consistent serialisation and equality semantics<br>- Reduced boilerplate code<br>- Clear visual distinction between data and logic<br>- Models remain lightweight and testable |


## ADR-005: Event-Driven Cognition Flow

| Field | Value |
|-------|-------|
| **ID** | ADR-005 |
| **Date** | Mid 2026 |
| **Status** | Accepted |
| **Context** | The cognition pipeline needed a way to notify other system components about decisions without creating direct dependencies. Components like learning, knowledge feedback, and monitoring needed to react to cognition events. |
| **Decision** | Publish cognition lifecycle events on the EventBus. The `CognitionService` publishes events when decisions are made and when learning cycles complete. Other components subscribe to these events without the cognition service knowing about them. |
| **Consequences** | - Loosely coupled event producers and consumers<br>- Easy to add new event listeners without modifying cognition service<br>- Events are recorded for audit and debugging<br>- Event ordering must be considered for correctness |


## ADR-006: Legacy Backward Compatibility

| Field | Value |
|-------|-------|
| **ID** | ADR-006 |
| **Date** | Mid 2026 |
| **Status** | Accepted |
| **Context** | During Phase 5, a new cognition system was introduced alongside the existing `CognitiveLoop` and `CognitiveService` in `atlas/intelligence/`. Removing the legacy system would break existing functionality and tests. |
| **Decision** | Preserve the legacy `CognitiveLoop` and `CognitiveService` indefinitely. Register all four keys in the kernel (`"cognition"`, `"cognitive"`, `"cognition_service"`, `"cognition_api"`). New development targets the new cognition service; legacy keys are marked as preserved and must not be modified. |
| **Consequences** | - No breaking changes to existing code<br>- Legacy system remains functional<br>- Slight increase in kernel registration complexity<br>- Clear migration path: new system can eventually replace legacy |


## ADR-007: Documentation Memory Layer

| Field | Value |
|-------|-------|
| **ID** | ADR-007 |
| **Date** | July 2026 |
| **Status** | Accepted |
| **Context** | After completing Phases 5 and 6.1–6.4, Atlas had grown complex enough that understanding the full system required reading many source files. AI assistants working on Atlas had no single entry point to understand the architecture, leading to context fragmentation and repeated exploration. |
| **Decision** | Create a permanent documentation memory layer in `docs/` with a structured set of documents. The master file (`ATLAS_MASTER_CONTEXT.md`) was originally intended to be sufficient for any AI model to understand Atlas by reading only that file first. Supporting documents cover architecture, state, history, roadmap, decisions, guidelines, strategy, and workflow. The canonical AI memory entry points are now `ATLAS_CORE.md` and `ATLAS_STATE.md`; `ATLAS_MASTER_CONTEXT.md` and the other supporting documents are preserved as historical/reference context. |
| **Consequences** | - Any AI model can understand Atlas quickly<br>- Context fragmentation is eliminated<br>- Documentation is persistent and version-controlled<br>- Requires ongoing maintenance as Atlas evolves |


## ADR-008: Two-Role AI Workflow

| Field | Value |
|-------|-------|
| **ID** | ADR-008 |
| **Date** | July 2026 |
| **Status** | Accepted |
| **Context** | Early development showed that using the same AI model for both planning and implementation led to suboptimal outcomes. Planning required broad architectural thinking, while implementation required focused, detail-oriented work. |
| **Decision** | Adopt a two-role AI workflow: **Planner AI** (architecture planning, design review, large decisions) and **Developer AI** (implementation, debugging, testing, file modification). Both roles are replaceable; neither is tied to a specific model or provider. |
| **Consequences** | - Better separation of strategic and tactical work<br>- Each role can use the optimal model for its task type<br>- Clear workflow prevents unauthorised architectural changes<br>- Slight overhead in role coordination |


## ADR-009: Service-Based Orchestration

| Field | Value |
|-------|-------|
| **ID** | ADR-009 |
| **Date** | Mid 2026 |
| **Status** | Accepted |
| **Context** | Early components contained both orchestration logic and business logic. This made testing difficult and created circular dependencies. |
| **Decision** | Use a service layer for orchestration. Services coordinate multiple components, manage dependencies, and handle cross-cutting concerns. Business logic lives in dedicated managers or engines. Services depend on abstractions, not concrete implementations. |
| **Consequences** | - Clear separation between orchestration and logic<br>- Services are independently testable<br>- Components can be swapped without changing orchestration<br>- Slight increase in number of classes and files |


## ADR-010: Test-First Development

| Field | Value |
|-------|-------|
| **ID** | ADR-010 |
| **Date** | Early 2026 |
| **Status** | Accepted |
| **Context** | Early development without tests led to regressions, unclear system behaviour, and difficulty verifying changes. |
| **Decision** | Every major feature requires tests. Run the full test suite before finishing any work session. Pure logic layers must be testable without mocking infrastructure. Tests must be order-independent and pass in any sequence. |
| **Consequences** | - Test coverage provides confidence that regressions are detected quickly<br>- Pure logic tests are fast and reliable<br>- Development pace is slightly slower but quality is higher |
