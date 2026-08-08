# Atlas Context

Permanent development context for AI assistants working on the Atlas project.

---

## 1. Project Vision

Atlas is a modular AI operating system / agent framework.

**Long-term goal:** Build a system capable of research, analysis, knowledge management, controlled self-improvement, and assisting its own development with user permission.

---

## 2. Current Architecture

### Kernel

- `atlas/kernel`
- `ServiceContainer` — dependency injection root
- `Atlas` — root application class

### AI

- Provider interface (`atlas/ai/provider.py`)
- Provider Registry (`atlas/ai/registry.py`)
- AI Router (`atlas/ai/router/ai_router.py`)
- AI Service (`atlas/services/ai_service.py`)

### Memory

- Memory Model (`atlas/memory/models/memory.py`)
- Memory Repository (`atlas/memory/repository/memory_repository.py`)
- Memory Search Engine (`atlas/memory/search/search_engine.py`)
- Ranking Engine (`atlas/memory/ranking/ranking_engine.py`)
- MemoryService (`atlas/memory/service/`)

### Conversation

- Conversation service and history (`atlas/conversation/`)

### Workspace

- Projects, resources, permissions (`atlas/workspace/`)

---

## 3. Development Philosophy

**Rules:**

- Modular architecture only. Each subsystem has a single responsibility.
- No duplicated business logic. The service layer delegates without duplicating.
- Use dependency injection. No internal instantiation.
- Every major feature requires tests. Run the full suite before finishing.
- Do not break existing APIs. Maintain backward compatibility.
- Document every completed work session. Create a report in `docs/reports/`.

---

## 4. Current Status

**Completed:**

- AI architecture (providers, registry, router, service)
- Service container and kernel
- Conversation system (service, history)
- Workspace foundation (projects, resources, permissions)
- Memory subsystem (repository, search, ranking, service)
- WS-024 — MemoryService orchestration layer

**Tests:** 194 passing

```
$ python -m unittest discover tests
...194 tests... OK
```

---

## 5. Current Task

**WS-025:** Integrate MemoryService into Atlas Kernel.

**Goal:** Atlas should have memory as a native kernel service — registered in the ServiceContainer and available via the Atlas root application.

---

## 6. Working Process

**Before coding:**

- Inspect existing architecture. Read the relevant files first.
- Check related files for interface compatibility.
- Create a plan.
- Implement minimally.
- Add tests.
- Run full test suite.
- Create a work report.

**Do not modify unrelated files.**

**After completion, create a report in `docs/reports/` with:**

- Task ID
- Changes
- Architecture decisions
- Tests
- Future notes

**Do not execute destructive commands.**
