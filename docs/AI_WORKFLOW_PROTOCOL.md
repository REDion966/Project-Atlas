# Atlas AI Workflow Protocol

**Standard operating procedure for AI agents working on Project Atlas.**

**Last updated:** July 2026

---

## 1. Purpose

This document defines how AI agents (both Planner and Developer roles) should work with Atlas. Following this protocol ensures consistent, predictable, and safe contributions to the project.

---

## 2. Required Workflow

Every AI agent working on Atlas must follow this workflow:

```
1. Read documentation memory files
2. Understand current state
3. Confirm the requested task
4. Implement only approved changes
5. Run tests
6. Report result
```

---

## 3. Step-by-Step Protocol

### Step 1: Read Documentation Memory Files

Before making any changes, read the following files in order:

1. **`docs/ATLAS_MASTER_CONTEXT.md`** — The single-entry context. Understand what Atlas is, why it exists, and the core philosophy.
2. **`docs/CURRENT_STATE.md`** — Understand the current state of the project, completed phases, and test status.
3. **`docs/ARCHITECTURE.md`** — Understand the system architecture, module structure, and data flow.
4. **`docs/ARCHITECTURE_DECISIONS.md`** — Review past decisions to avoid repeating mistakes or violating established patterns.
5. **`docs/CODING_GUIDELINES.md`** — Review development rules before writing any code.
6. **`docs/ROADMAP.md`** — Confirm the requested task aligns with the project roadmap.

### Step 2: Understand Current State

- Check version control state (e.g., current branch, recent history) when available.
- Run the test suite to confirm current test status.
- Read relevant source files for the area being modified.

### Step 3: Confirm the Requested Task

- Verify the task is clearly defined.
- Check if the task aligns with the roadmap and architecture decisions.
- Identify which files need to be created or modified.
- Identify which tests need to be added or updated.
- **Do not proceed with implementation until the task is confirmed.**

### Step 4: Implement Only Approved Changes

- Implement the minimum changes required to fulfill the task.
- Follow the coding guidelines in `CODING_GUIDELINES.md`.
- Do not modify unrelated files.
- Do not refactor code outside the scope of the task.
- Do not make autonomous architectural changes.
- Add tests for all new functionality.

### Step 5: Run Tests

- Run the full test suite: `pytest`
- Verify all tests pass.
- If tests fail, fix the issues before proceeding.

### Step 6: Report Result

- Report what was changed and why.
- Report test results.
- Report any assumptions made.
- Report any issues encountered.
- Do not commit without explicit approval.

---

## 4. Planner AI Protocol

### Allowed Actions

- Read any file in the repository.
- Analyse architecture and suggest designs.
- Review code and architecture decisions.
- Create documentation and reports.
- Ask clarifying questions.

### Prohibited Actions

- **Do not modify source code** without explicit approval.
- **Do not create or modify tests** without explicit approval.
- **Do not run destructive commands** (delete, overwrite, install/uninstall packages).
- **Do not make autonomous architectural decisions.**

### Workflow

```
1. Read documentation memory files
2. Analyse the current architecture
3. Understand the requested task
4. Design a solution
5. Present the design for review
6. Wait for approval before any implementation
```

---

## 5. Developer AI Protocol

### Allowed Actions

- Read any file in the repository.
- Implement approved changes.
- Write and run tests.
- Debug and fix issues.
- Modify files according to specifications.

### Prohibited Actions

- **Do not make autonomous architectural changes.**
- **Do not modify legacy components** marked as "preserved" or "do not modify".
- **Do not break existing APIs.**
- **Do not modify unrelated files.**

### Workflow

```
1. Read documentation memory files
2. Understand the approved design
3. Implement the changes
4. Add tests
5. Run the full test suite
6. Report the result
```

---

## 6. Communication Protocol

### When Reporting Changes

Include the following in every report:

```
## Summary
- What was changed
- Why it was changed
- Files created/modified

## Test Results
- Total tests: X
- Passing: X
- Failing: X

## Assumptions
- Any assumptions made during implementation

## Issues
- Any issues encountered
- Any unresolved problems
```

### When Requesting Clarification

- Be specific about what is unclear.
- Reference specific files and line numbers.
- Suggest possible interpretations.

---

## 7. Safety Rules

1. **Never run destructive commands** without explicit approval.
2. **Never modify legacy components** marked as preserved.
3. **Never break existing APIs** — maintain backward compatibility.
4. **Never make autonomous architectural changes** — always get approval.
5. **Never commit without approval** — report results first.
6. **Never skip tests** — always run the full suite.

---

## 8. Documentation Updates

- Update documentation when making architectural changes.
- Update `CURRENT_STATE.md` when phases are completed.
- Update `DEVELOPMENT_LOG.md` when new phases begin or complete.
- Update `ARCHITECTURE_DECISIONS.md` when new decisions are made.
- Update `ROADMAP.md` when priorities change.

---

## 9. Working with the Documentation Memory Layer

The documentation memory layer is designed to survive AI model and provider changes. When working with it:

- **Do not delete or rename** any of the core documentation files.
- **Do update** content to reflect the current state of the project.
- **Do add** new architecture decisions as they are made.
- **Do add** new phases to the development log as they are completed.
- **Do update** the roadmap as priorities evolve.

The documentation memory layer is Atlas's permanent identity. Treat it with the same care as source code.