# Atlas Development Workflow

**Status:** Active
**Version:** 2.0
**Project:** Atlas

---

## Overview

Atlas development follows a structured pipeline from planning through commit. Every change, whether small or large, goes through the same stages.

---

## Workflow Stages

```
Repository Reality Check → Planning → Implementation → Verification → Review → Commit
```

---

## 0. Repository Reality Check ⚠️ Mandatory

Before beginning any major phase, verify that the repository state and documentation agree.

| Check | Command | Expected |
|-------|---------|----------|
| Current Git branch | `git branch --show-current` | Matches the branch in `docs/ATLAS_STATE.md` §1 |
| Current commit hash | `git rev-parse HEAD` | Recorded in `docs/ATLAS_STATE.md` §1 |
| Current pytest total | `python -m pytest -q` | Matches the count in `docs/ATLAS_STATE.md` §6 |
| Working tree status | `git status --short` | Clean (no uncommitted changes) before starting new work |
| README project status | Check `README.md` heading | Project status reflects the current phase |
| ATLAS_STATE.md status | Read §1 and §6 | Branch, HEAD, tag, and test count match repository reality |

**If any of these disagree:**
- Stop implementation work.
- Reconcile the documentation with the repository state before proceeding.
- Update `docs/ATLAS_STATE.md` if a phase was completed but not recorded.
- Commit any orphaned changes before starting a new phase.

**The repository and documentation must be in agreement before a new phase begins.**

---

## 1. Planning

| Step | Role | Action |
|------|------|--------|
| Define requirements | Architecture Agent | Architecture and requirements are defined |
| Design the solution | Architecture Agent | Module structure, interfaces, and contracts are specified |
| Create task description | Architecture Agent | A clear task is written with acceptance criteria |

**Output:** A task specification with exact file paths, expected behavior, and constraints.

---

## 2. Implementation

| Step | Role | Action |
|------|------|--------|
| Read existing code | Implementation Agent | Understand the current module before modifying |
| Implement the feature | Implementation Agent | Write production code following Atlas standards |
| Create tests | Implementation Agent | Write comprehensive unit tests |
| No unrelated changes | Implementation Agent | Only the files specified in the task are touched |

**Rules:**
- Read the relevant files before writing any code.
- Follow the existing module patterns — don't invent new styles.
- Write one test class per module, one test method per behavior.
- Never modify tests to hide failures.

---

## 3. Verification Gate ⚠️ Mandatory

A phase or task may NOT be marked complete until this gate has been passed.

| Step | Action |
|------|--------|
| Run all requested tests | `python -m pytest` |
| Preserve raw terminal output | Copy the full, unedited test output. Do not summarize or truncate. |
| Fix failures | Debug and fix the implementation, never the tests. |
| Run full suite again | All tests must pass — project-wide, not just the changed module. |
| Paste output into report | The raw terminal output must be included verbatim in the completion report. |

**Phase completion requirement:**
- All tests must pass.
- **The raw terminal output must be pasted, unedited**, as evidence.
- No phase or task is complete without this evidence.
- Documentation (`docs/ATLAS_STATE.md`, `docs/ROADMAP.md`, `README.md` when applicable) may only be updated AFTER verification succeeds.

**Acceptance criteria:**
- All tests pass (see `docs/ATLAS_STATE.md` for current expected count).
- No test was modified to work around a bug.
- The implementation is clean and follows the established patterns.

---

## 4. Review

| Step | Role | Action |
|------|------|--------|
| Architecture review | Review Agent | Does the change fit the existing architecture? |
| Code quality review | Review Agent | Is the code clean, modular, and well-named? |
| Test coverage review | Review Agent | Do tests cover the happy path, empty states, and error cases? |
| Side-effect check | Review Agent | Does the change break anything unrelated? |

**The review must pass before commit. No exceptions.**

---

## 5. Commit

| Step | Role | Action |
|------|------|--------|
| Verify tests pass one final time | Implementation Agent | `python -m pytest -q` |
| Stage changes | Implementation Agent | `git add <files>` |
| Write commit message | Implementation Agent | Summary line + bullet list of changes |
| Commit | Implementation Agent | `git commit` |

**Commit message format:**
```
feat(scope): Short description

- Bullet list of specific changes
- Each bullet is one logical change
```

---

## Quick Reference

```bash
# Run all tests
python -m pytest

# Run a specific test file
python -m pytest tests/path/to/test_file.py -v

# Run tests for a specific area
python -m pytest tests/workspace/ tests/memory/ -v

# Run with summary only (pass/fail count)
python -m pytest -q
