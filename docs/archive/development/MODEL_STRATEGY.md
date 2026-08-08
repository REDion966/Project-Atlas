# Atlas Model Strategy

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

**AI provider and workflow strategy for Project Atlas.**

**Last updated:** July 2026

---

## 1. Core Principle

**Models are replaceable. Atlas must never depend on a specific AI provider.**

Atlas is designed to work with any AI model that can follow structured instructions. The documentation memory layer ensures that any AI model — current or future — can understand Atlas by reading the documentation files first.

---

## 2. Two-Role AI Workflow

Atlas uses a **Planner + Developer** two-role workflow to separate strategic thinking from tactical implementation.

### Planner AI

| Attribute | Value |
|-----------|-------|
| **Role** | Architecture planning, design review, large decisions |
| **Scope** | Reads documentation, analyses architecture, suggests designs, reviews decisions |
| **Code modification** | Must NOT modify code without approval |
| **Key skill** | Broad architectural thinking, trade-off analysis |

**Responsibilities:**
- Read and understand the current architecture from documentation
- Design new components and systems
- Review code and architecture decisions
- Identify potential issues before implementation
- Maintain alignment with the Atlas Constitution and roadmap

### Developer AI

| Attribute | Value |
|-----------|-------|
| **Role** | Implementation, debugging, testing, file modification |
| **Scope** | Writes code, runs tests, modifies files |
| **Code modification** | Implements approved changes only |
| **Key skill** | Focused, detail-oriented implementation |

**Responsibilities:**
- Implement approved architectural changes
- Write tests for new functionality
- Debug and fix issues
- Modify files according to specifications
- Run the full test suite before reporting completion

---

## 3. Provider Configuration

Atlas is configured through a configuration file:

```toml
[ai]
provider = "<provider_name>"      # Provider identifier
model = "<model_name>"            # Model name within the provider
timeout = 30                      # Request timeout in seconds
```

The `AIManager` reads this configuration at startup and initialises the appropriate provider dynamically.

---

## 4. Provider Abstraction

### Provider Interface

The abstract `AIProvider` interface defines the contract:

```python
class AIProvider(ABC):
    @abstractmethod
    def chat(self, messages, **kwargs) -> str: ...
    @abstractmethod
    def stream(self, messages, **kwargs) -> Iterator[str]: ...
    @abstractmethod
    def models(self) -> list[str]: ...
```

### Provider Implementations

| Provider | Implementation | Status |
|----------|---------------|--------|
| Provider A | `atlas/ai/providers/provider_a.py` | Active |
| Provider B | `atlas/ai/providers/provider_b.py` | Active |
| (Future) | Any provider implementing the interface | Extensible |

### Adding a New Provider

1. Implement the `AIProvider` interface in a new module under `atlas/ai/providers/`.
2. Register the provider in the `ProviderRegistry`.
3. Update configuration to use the new provider.
4. No kernel or architecture changes required.

---

## 5. Model Selection Strategy

### Current Strategy

Currently, Atlas uses a single configured AI provider for all interactions. The provider is selected at startup and used throughout the session.

### Future Strategy (Phase 6.6+)

Model routing will select optimal models per request based on:

| Factor | Consideration |
|--------|---------------|
| **Complexity** | Simple queries use smaller, faster models; complex reasoning uses larger models |
| **Latency** | Time-sensitive requests use faster models |
| **Cost** | Cost-efficient models for bulk operations |
| **Capability** | Task-specific models (code generation, analysis, creative) |
| **Availability** | Fallback if preferred model is unavailable |

---

## 6. Prompt Strategy

Atlas minimises prompt engineering by structuring intelligence through:

- **Documentation memory** — persistent context files that any AI model reads first
- **Structured reasoning** — `CognitionDecision` → `ReasoningPlan` → `Capability` pipeline
- **Pure logic layers** — reasoning that doesn't require AI calls
- **Clear data models** — typed interfaces between components

This approach means Atlas is not dependent on carefully crafted prompts for a specific model. Instead, it provides structured context that any capable model can use.

---

## 7. Model Independence Rules

1. **No hardcoded model names** in source code.
2. **No model-specific behaviour** — all providers implement the same interface.
3. **No prompt templates** tied to a specific model's formatting.
4. **Documentation memory** must be model-agnostic.
5. **Fallback strategy** — Atlas should work with lower-capability models, even if slower.

---

## 8. Testing with AI Providers

- Tests should mock AI providers rather than calling real models.
- Pure logic layers must be testable without any AI provider.
- Integration tests can optionally use a real provider for validation.
- Test configuration should support provider mocking.

---

## 9. Future: Multi-Model Orchestration

The long-term vision includes:

- **Planner model** — strategic architecture decisions
- **Developer model** — implementation and debugging
- **Specialist models** — code analysis, research, creative tasks
- **Local models** — private, self-hosted inference
- **Cloud models** — remote, managed inference services

Each role is replaceable independently. Atlas never depends on a single provider.