# Project Atlas AI Development Rules

**Status:** Permanent  
**Version:** 1.0  
**Project:** Atlas  
**Scope:** Every AI assistant and developer working on Atlas

---

## 1. Project Understanding

Atlas is a **long-term modular AI operating platform**, not a single application.

Every feature, every module, and every line of code is an investment in a platform that must remain maintainable for years. Quick hacks today create impossible maintenance burdens tomorrow.

**Core architecture layers (top to bottom):**

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

Each layer communicates only with adjacent layers. Circular dependencies are prohibited.

---

## 2. Before Making Changes

Before writing any code, an AI assistant must:

1. **Read the architecture documents:**
   - `docs/ARCHITECTURE.md` — module structure and layer rules
   - `docs/ROADMAP.md` — current phase and planned components
   - `docs/ATLAS_ENGINEERING_GUIDE.md` — engineering principles and hard rules

2. **Understand the existing module** by reading its file before modifying it. Never write code that touches an unfamiliar module without reading it first.

3. **Search for existing functionality** before creating new code. If Atlas already has a mechanism for what you need, reuse or extend it. Do not duplicate.

4. **Identify the correct layer** for your change:
   - Data shape → **Model**
   - Business logic → **Manager**
   - Data access → **Repository**
   - Coordination → **Service**
   - User interaction → **CLI**

---

## 3. Coding Rules

### 3.1 Keep Modules Independent

- One file per component, service, manager, repository, or model.
- Files should remain focused and follow single responsibility principles.
  Large files should be reviewed when they exceed reasonable complexity or contain multiple responsibilities.
- Functions should have a single responsibility and remain readable.
  Refactor when complexity harms maintainability.

### 3.2 Naming

| Kind | Convention | Examples |
|------|-----------|----------|
| Functions | verb | `fetch_user()`, `save_workspace()` |
| Booleans | predicate | `is_loaded`, `has_permission` |
| Collections | plural | `users`, `projects` |
| Classes | PascalCase | `WorkspaceManager`, `RankingEngine` |

No generic names like `data`, `item`, `temp`, `result`, `obj`.

### 3.3 Avoid Duplicate Logic

- Before writing any new method, check if a similar method already exists in the module or in related modules.
- If two pieces of code do the same thing, extract the common logic into a shared helper.
- Never copy-paste serialization, validation, or transformation code.

### 3.4 Respect Existing Architecture

- **Managers** contain domain operations. They may use repositories for data access.
- **Repositories** handle data access only. No business logic.
- **Services** coordinate managers, repositories, and other services. They should not contain raw business logic.
- **Models** are data containers with serialization methods. No business logic beyond `to_dict()`/`from_dict()`.
- **Storage** handles low-level read/write. No business logic.

### 3.5 Backward Compatibility

- Existing public APIs must not change without review.
- Adding new parameters is safe — use default values to preserve the existing signature.
- Deprecate gradually, never break abruptly.
- If you must change an API, update all callers in the same commit.

### 3.6 Imports and Dependencies

- Every import must resolve to a real module with the exact exported name.
- Never import a package without verifying it is declared in `pyproject.toml` (or equivalent).
- Do not add new dependencies without review.

---

## 4. Testing Rules

### 4.1 Tests Are Mandatory

Every new feature must include automated tests. No feature is complete unless its tests are passing.

### 4.2 Never Modify Tests to Hide Failures

If a test fails, the implementation has a bug. **Never modify a test to make it pass without fixing the underlying problem.** This is the single most important rule in this document.

Fix the implementation, then verify the test passes. If the test is genuinely incorrect (e.g., testing the wrong behavior), fix the test **in a separate change** after confirming the implementation is correct.

### 4.3 Investigate Root Causes

When a test fails:
1. Read the full error message — the cause is often mid-stack, not line 1.
2. Find the exact file and line that produced the error.
3. Form a hypothesis about WHY it fails.
4. Fix one thing at a time.
5. Re-verify after each fix.

Never silence errors with broad `try/except`. Fix the root cause.

### 4.4 Test Isolation

- Each test class starts with a clean state via `setUp()`.
- Use `tempfile.mkdtemp()` and `unittest.mock.patch` to isolate file-backed components.
- Tests must be order-independent — any test can run first.
- Never share file state between tests.

### 4.5 Test Coverage

Every method should have at least:
- **Happy path test** — the method works correctly with valid input
- **Empty state test** — the method handles empty input gracefully
- **Error case test** — the method raises appropriate errors for invalid input

---

## 5. Change Management

### 5.1 One Task at a Time

- Every task modifies only the files specified in its requirements.
- Do not fix unrelated bugs or refactor adjacent code during a task.
- If you discover a bug or improvement opportunity, document it — do not fix it in the current task.

### 5.2 Keep Git History Clean

- Each commit represents one logical change.
- No "fix typo" commits — review before committing, not after.

### 5.3 No Unrelated Modifications

Before committing, verify that every changed file is part of the task. Use `git diff --stat` to check. If a file was modified accidentally, revert it with `git checkout -- <file>`.

---

## 6. Architecture Protection

### 6.1 No Major Decisions Without Review

Never make significant architectural decisions without review. Examples of decisions that require review:

- Adding a new top-level module
- Changing the layer architecture
- Adding a new external dependency
- Modifying the startup sequence
- Changing the storage backend

### 6.2 Explain Design Decisions

Every non-trivial design choice must be documented:
- Why was this approach chosen over alternatives?
- What trade-offs were accepted?
- What future implications does this decision have?

Add this explanation to the task report or, for significant decisions, create an ADR in `docs/adr/`.

### 6.3 Preserve Debuggability

- Never swallow errors — log them before handling.
- Never use bare `except:` — catch specific exceptions.
- Keep log messages meaningful and searchable.

---

## 7. Reporting Rules

Every completed task MUST create a report file at:

```
docs/reports/WS-XXX_REPORT.md
```

### 7.1 Report Format

```markdown
# Sixth Report — WS-XXX: Short Title

**Date:** YYYY-MM-DD
**Agent:** Sixth (Coding AI)
**Task ID:** WS-XXX
**Status:** Completed

---

## Task

One-line summary of what was implemented.

## Goal

What problem does this solve? Why was it needed?

## Files Changed

List every modified file with a brief reason.

## New Files

List every newly created file with its purpose.

## Architecture Decisions

- Key design decisions and their rationale.
- Alternatives considered (if any).

## Problems Solved

- Specific problems this implementation addresses.
- Edge cases handled.

## Tests Added

Summary of test coverage:
- What each test verifies.
- Categories covered (happy path, empty state, error case).

## Test Results

```
$ python -m unittest discover tests
Result: OK

| Suite | Tests | Passed |
|-------|-------|--------|
| ...   | ...   | ...    |
```

## Future Compatibility Notes

- What downstream code depends on this change?
- What should future developers know before modifying this code?

## Risks

- Any remaining concerns or edge cases.
- Performance considerations.
- Security implications (if any).
```

### 7.2 Verification Steps

Before completing a task, an AI assistant must:

1. **Run the full test suite:**
   ```
   python -m unittest discover tests
   ```
   All tests must pass.

2. **Check git status:**
   ```
   git status
   ```
   Only task-related files should appear.

3. **Check diff scope:**
   ```
   git diff --stat
   ```
   Only the files specified in the task should be modified.

4. **If any production file was accidentally modified:**
   ```
   git checkout -- <file>
   ```
   Revert it immediately.

5. **Run the test suite one final time** after any reverts.

### 7.3 Do Not Commit

The AI assistant's responsibility ends at verification. The human user reviews the changes and commits them. Never run `git commit` unless explicitly instructed.
