# Atlas Coding Guidelines

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

**Development rules and standards for Project Atlas.**

**Last updated:** July 2026

---

## 1. Modular Architecture

- Each module has a single, clear responsibility.
- Modules communicate through well-defined interfaces.
- No circular dependencies between modules.
- Components should be independently replaceable without rebuilding Atlas.

```
Good:    atlas/reasoning/controller.py → atlas/reasoning/models.py
Bad:     atlas/reasoning/controller.py → atlas/memory/service/memory_manager_service.py
```

---

## 2. Avoid Unnecessary Coupling

- Prefer dependency injection over internal instantiation.
- High-level modules depend on abstractions, not concrete implementations.
- Pure logic layers must not depend on AI, memory, services, or EventBus.
- Services orchestrate; managers/engines contain business logic.

```
Good:    class CapabilityAnalyzer:  # no service imports
Bad:     class CapabilityAnalyzer:  # imports MemoryManagerService
```

---

## 3. Keep Pure Logic Separate

The following layers must remain **pure logic** — no AI calls, no memory access, no knowledge access, no EventBus:

- `ReasoningController`
- `CapabilityAnalyzer`
- `CapabilityRouter`
- `CapabilityDispatcher`
- `CapabilityRegistry`
- `CognitionEngine`
- `CognitionContext`
- `CognitionDecision`

These components receive all data through parameters and return results through data models. They are fully testable without mocking infrastructure.

---

## 4. Use Dataclasses for Pure Models

- All pure data models should use Python `@dataclass`.
- Models represent data only — no business logic beyond serialisation.
- Complex behaviour belongs in service or manager classes.

```python
# Good
@dataclass
class Capability:
    name: str = ""
    priority: int = 0
    reason: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

# Bad
class Capability:
    def __init__(self, name, priority, reason, metadata):
        self.name = name
        self.priority = priority
        self.reason = reason
        self.metadata = metadata

    def execute(self):  # business logic in model
        ...
```

---

## 5. Add Tests With Every Feature

- Every major feature requires tests.
- Pure logic layers must be testable without mocking infrastructure.
- Tests must be order-independent and pass in any sequence.
- Run the full test suite before finishing any work session.

```
$ python -m unittest discover tests
```

---

## 6. Avoid Breaking Existing Architecture

- Never break existing APIs.
- Maintain backward compatibility.
- Prefer additive changes over refactoring.
- Legacy components marked as "preserved" must not be modified.

```
Good:    Add new parameter with default=None
Bad:     Remove existing parameter
```

---

## 7. Prefer Additive Changes

- Add new files, classes, and methods rather than modifying existing ones.
- When adding new functionality, create new modules in the appropriate location.
- Only modify existing code when fixing bugs or when the change is explicitly required.

---

## 8. Naming Conventions

- **Classes:** `PascalCase` — `CognitionService`, `CapabilityRouter`
- **Methods and functions:** `snake_case` — `create_plan()`, `dispatch()`
- **Modules:** `snake_case` — `capability_analyzer.py`, `service_container.py`
- **Packages:** short, lowercase — `cognition/`, `reasoning/`, `execution/`
- **Tests:** `test_<module_name>.py` — `test_capability_analyzer.py`
- **Test classes:** `Test<ComponentName>` — `TestCapabilityAnalyzer`
- **Test methods:** `test_<behaviour>` — `test_analyze_returns_capabilities()`

---

## 9. Documentation Standards

- Every module should have a docstring explaining its purpose.
- Every public class and method should have a docstring.
- Docstrings should explain **what** and **why**, not just **how**.
- Keep documentation in `docs/` for cross-cutting concerns.
- Update documentation when making architectural changes.

```python
def create_plan(self, decision: CognitionDecision) -> ReasoningPlan:
    """
    Produce a ReasoningPlan from a CognitionDecision.

    This is a pure logic component with no infrastructure dependencies.
    It does not call AI providers, access memory, or query knowledge.

    Args:
        decision: The CognitionDecision to translate.

    Returns:
        A ReasoningPlan with steps derived from the decision.
    """
```

---

## 10. Import Rules

- Use explicit imports — no `from module import *`.
- Group imports: standard library → third-party → atlas modules.
- Pure logic modules must not import infrastructure modules.

```python
# Good
from dataclasses import dataclass, field
from typing import Any

from atlas.reasoning.models import ReasoningPlan

# Bad
from atlas.memory.service.memory_manager_service import MemoryManagerService
```

---

## 11. Error Handling

- Use exceptions for exceptional conditions, not control flow.
- Pure logic layers should raise specific exceptions.
- Service layers should catch and wrap exceptions as needed.
- Return `ExecutionResult` with error information rather than raising in execution layer.

---

## 12. Type Hints

- Use type hints for all function signatures.
- Use `Any` sparingly — prefer specific types.
- Use `Optional[Type]` or `Type | None` for nullable values.
- Use `list[Type]` and `dict[str, Type]` for collections.

```python
def dispatch(self, capabilities: list[Capability]) -> list[ExecutionResult]: ...
```

---

## 13. Commit Conventions

- Write clear, descriptive commit messages.
- Reference phases and components in commit messages.
- Keep commits focused on single logical changes.
- Do not commit broken code or failing tests.

```
Good:    "Add adaptive execution routing layer"
Bad:     "fix stuff"
```

---

## 14. Development Workflow

1. Read documentation memory files first.
2. Understand current state and architecture.
3. Confirm the requested task.
4. Implement only approved changes.
5. Add tests for new functionality.
6. Run the full test suite.
7. Report the result.

---

## 15. Prohibited Patterns

- **No circular imports** — restructure to avoid them.
- **No business logic in models** — models are data containers only.
- **No infrastructure in pure logic** — reasoning layers must be service-free.
- **No hardcoded provider dependencies** — all AI providers are dynamically selected.
- **No silent failures** — meaningful actions must be recorded or logged.