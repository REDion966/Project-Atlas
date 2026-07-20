# Atlas Development Workflow

**Status:** Active  
**Version:** 1.0  
**Project:** Atlas

---

## Overview

Atlas development follows a structured pipeline from planning through commit. Every change, whether small or large, goes through the same stages.

---

## Workflow Stages

```
Planning → Implementation → Verification → Review → Commit
```

---

## 1. Planning

| Step | Who | Action |
|------|-----|--------|
| Define requirements | ChatGPT / Human | Architecture and requirements are defined |
| Design the solution | ChatGPT / Human | Module structure, interfaces, and contracts are specified |
| Create task description | ChatGPT / Human | A clear task is written with acceptance criteria |

**Output:** A task specification with exact file paths, expected behavior, and constraints.

---

## 2. Implementation

| Step | Who | Action |
|------|-----|--------|
| Read existing code | Sixth / Coding AI | Understand the current module before modifying |
| Implement the feature | Sixth / Coding AI | Write production code following Atlas standards |
| Create tests | Sixth / Coding AI | Write comprehensive unit tests |
| No unrelated changes | Sixth / Coding AI | Only the files specified in the task are touched |

**Rules:**
- Read the relevant files before writing any code.
- Follow the existing module patterns — don't invent new styles.
- Write one test class per module, one test method per behavior.
- Never modify tests to hide failures.

---

## 3. Verification

| Step | Action |
|------|--------|
| Run unit tests | `python -m pytest tests/` or `python -m unittest discover tests` |
| Fix failures | Debug and fix the implementation, never the tests |
| Run full suite | All tests must pass — project-wide, not just the changed module |
| Type check | `tsc --noEmit` for TypeScript, or equivalent for Python |
| Build check | Ensure the project builds without errors |

**Acceptance criteria:**
- All tests pass (179+ across the project).
- No test was modified to work around a bug.
- The implementation is clean and follows the established patterns.

---

## 4. Review

| Step | Action |
|------|--------|
| Architecture review | Does the change fit the existing architecture? |
| Code quality review | Is the code clean, modular, and well-named? |
| Test coverage review | Do tests cover the happy path, empty states, and error cases? |
| Side-effect check | Does the change break anything unrelated? |

**The review must pass before commit. No exceptions.**

---

## 5. Commit

| Step | Action |
|------|--------|
| Verify tests pass one final time | `python -m unittest discover tests` |
| Stage changes | `git add <files>` |
| Write commit message | Summary line + bullet list of changes |
| Commit | `git commit` |

**Commit message format:**
```
WS-NNN: Short description

- Bullet list of specific changes
- Each bullet is one logical change
```

---

## Quick Reference

```bash
# Run all tests
python -m unittest discover tests

# Run a specific test file
python -m pytest tests/memory/test_search_engine.py -v

# Run workspace + memory tests together
python -m pytest tests/workspace/ tests/memory/ -v
