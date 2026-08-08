# Atlas Engineering Guide

**Status:** Active  
**Version:** 1.0  
**Project:** Atlas  

---

# 1. Project Philosophy

Atlas is a modular AI assistant platform built for long-term evolution.

**Core beliefs:**

- Long-term maintainability is more important than quick hacks.
- Every module has one job and does it well.
- Tests are not optional — they are part of the feature.
- Backward compatibility is preserved unless there is a compelling reason to break it.
- Clean, readable code is preferred over clever, unreadable code.

---

# 2. Engineering Principles

## Architecture First

Design before implementation. Every new feature should fit into the existing architecture without bending it.

## Tests Are Mandatory

No feature is complete without tests. Tests must pass before commit. Never modify tests to hide failures — fix the implementation.

## Avoid Unnecessary Complexity

If a solution feels complex, it probably is. Simplify before committing. A module that is hard to understand today will be impossible to maintain tomorrow.

## Preserve Backward Compatibility

Existing public APIs must not change without review. Deprecate gradually, never break abruptly.

---

# 3. Hard Rules

These rules must never be violated:

| Rule | Rationale |
|------|-----------|
| Never modify tests to hide failures | Fix the real bug, not the symptom |
| Never delete user data automatically | User data belongs to the user |
| Never break existing APIs without review | Other modules depend on stable interfaces |
| Never use `escapeHtml` or custom HTML-escaping | The runtime already processes HTML entities |
| Never import a package without verifying it is in the project | Dependencies must be declared |
| Never modify unrelated code during a task | One change per task keeps history clean |
| Never write business logic in storage or repository layers | Separation of concerns |

---

# 4. Module Responsibilities

Each layer in the architecture has a clearly defined responsibility:

| Layer | Responsibility |
|-------|---------------|
| **Models** | Data representation only. No logic beyond serialization. |
| **Managers** | Domain operations and business logic. |
| **Repositories** | Data access and persistence only. |
| **Services** | Coordinate multiple managers and components. |
| **CLI** | User interaction and command routing. |
| **Storage** | Low-level read/write to disk or external systems. |

---

# 5. Code Quality Standards

- **One file per component, hook, utility, type, or service.** Never write a whole feature in one file.
- **Files should remain focused and follow single responsibility principles.** Large files should be reviewed when they exceed reasonable complexity or contain multiple responsibilities.
- **Functions should have a single responsibility and remain readable.** Refactor when complexity harms maintainability.
- **Naming:** verbs for functions (`fetch_user`), predicates for booleans (`is_loaded`), plurals for arrays (`users`). No `data`, `item`, `temp`, `result`, `obj`.
- **Constants** for magic numbers and strings.
- **Explicit TypeScript types** — never `any`.
- **All imports must resolve** to real modules with the exact exported name.

---

# 6. Testing Standards

- Every test class starts each test with a clean state using `setUp`.
- Tests must be order-independent — any test can run first.
- Use `tempfile` and `unittest.mock.patch` for isolation, never shared file state.
- Never modify tests to work around implementation bugs.
- Run the full suite before finishing any task.

---

# 7. Decision Records

All significant architectural decisions are documented as ADRs in `docs/adr/`.

An ADR includes:
- **Context:** Why this decision was necessary.
- **Decision:** What was decided.
- **Consequences:** What trade-offs were accepted.
- **Alternatives Considered:** What other options were evaluated and rejected.
