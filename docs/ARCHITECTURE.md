# Atlas Architecture

**Version:** 1.0  
**Status:** Active  
**Project:** Atlas

---

## Purpose

This document describes the current architecture of Project Atlas.

Every developer and AI assistant working on Atlas should understand this architecture before making changes.

---

## Architecture Principles

| Principle | Description |
|-----------|-------------|
| Separation of Concerns | Each module has one clear responsibility |
| Dependency Inversion | High-level modules depend on abstractions |
| Test-First | Tests are mandatory for every feature |
| Repository Pattern | Data access is encapsulated in repositories |
| Modular Design | Components are independent and replaceable |
| High Cohesion | Related logic stays together |
| Low Coupling | Modules communicate through well-defined interfaces |

---

## Module Structure

```
atlas/
├── core/              # Application lifecycle and boot
├── kernel/            # Service container and wiring
├── services/          # High-level business services
├── workspace/         # Workspace management
│   ├── models/        #   Workspace, project, resource, etc.
│   ├── storage/       #   Workspace persistence
│   └── services/      #   Workspace service layer
├── memory/            # Memory system
│   ├── models/        #   Memory data model
│   ├── ranking/       #   Ranking engine
│   ├── search/        #   Search engine
│   ├── repository/    #   Memory repository
│   └── storage/       #   Memory persistence
├── ai/                # AI provider abstraction
│   ├── providers/     #   LLM providers (Ollama, OpenAI, etc.)
│   ├── router/        #   AI routing logic
│   └── registry/      #   Provider registry
├── conversation/      # Conversation management
├── storage/           # Generic storage utilities
├── config/            # Configuration system
├── cli/               # Command-line interface
└── utils/             # Shared utilities
```

---

## Layer Rules

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
- Models are plain data — no business logic beyond serialization.

---

## Module Responsibilities

| Module | Responsibility |
|--------|---------------|
| **Models** | Data representation and serialization only |
| **Managers** | Domain operations and business logic |
| **Repositories** | Data access and persistence |
| **Services** | Coordinate multiple components |
| **CLI** | User interaction and command routing |
| **Storage** | Low-level read/write to disk |

---

## Startup Sequence

```
main.py
   │
   ▼
Startup → Boot Screen → Boot Manager
                               │
                    ┌──────────┼──────────┐
                    ▼          ▼          ▼
           Dependency    Service       Application
           Checker      Container       Ready
```

---

## Testing Architecture

- Tests reside in `tests/`, mirroring the `atlas/` structure.
- Each test class uses `setUp` for clean state.
- File-backed components use `unittest.mock.patch` to redirect to temporary directories.
- Tests must be order-independent and pass in any sequence.
