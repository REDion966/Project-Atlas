# ==========================================================
# Project Atlas Development Rules
# ==========================================================

You are the implementation engineer for Project Atlas.

Project Atlas is a long-term AI Operating Framework under active development.

The architecture already exists.

Never redesign the project unless explicitly instructed.

Your primary objective is to preserve architecture quality while minimizing token usage.

Think before coding.
Read before editing.
Reuse before creating.
Modify only what is necessary.

# ==========================================================
# Architecture Preservation
# ==========================================================

The existing architecture is the source of truth.

Before writing code:

1. Search for existing implementations.
2. Reuse existing services.
3. Extend existing modules.
4. Avoid duplicate systems.

Never replace an existing subsystem unless explicitly instructed.

Preserve:

- Modular Architecture
- RuntimeCoordinator
- Dependency Injection
- Event-driven design
- Memory system
- Evolution system
- Research framework
- Planning system
- Tool framework
- Existing tests
- Existing public APIs

# ==========================================================
# Architecture Locks
# ==========================================================

The following packages are considered architecture-stable.

Do NOT redesign them unless explicitly instructed.

- atlas/kernel
- atlas/runtime
- atlas/memory
- atlas/evolution
- atlas/research
- atlas/toolchain

# ==========================================================
# Read Before Edit
# ==========================================================

Read only the minimum code required.

Search in this order:

1. Symbol search
2. Filename search
3. Small line-range reads
4. Full file reads only when necessary

Prefer:

- symbol lookup
- targeted search
- partial file reads

Avoid repository-wide scans whenever possible.

# ==========================================================
# Context Preservation
# ==========================================================

Do NOT reread files already inspected during the current task unless:

- the file has changed
- another dependency requires rereading
- the user explicitly requests it

Reuse previously discovered information.

# ==========================================================
# Stable Modules
# ==========================================================

Treat completed modules as stable.

Do NOT inspect or modify them unless:

- the current task directly depends on them
- tests indicate a regression
- the user explicitly requests changes

# ==========================================================
# Minimal Changes
# ==========================================================

Modify only the required code.

Prefer:

- append
- insert
- replace a function
- targeted edits

Avoid rewriting entire files when only a few lines require changes.

Preserve:

- formatting
- naming conventions
- architecture

# ==========================================================
# Dependency Injection
# ==========================================================

Always preserve Dependency Injection.

Never introduce global state.

Never bypass service registration.

Reuse injected services whenever possible.

# ==========================================================
# Code Quality
# ==========================================================

Generate:

- production-ready Python
- modular code
- typed code
- maintainable code
- backward-compatible code
- deterministic behavior where applicable

Avoid:

- placeholder implementations
- unnecessary abstractions
- duplicated logic
- unnecessary comments

# ==========================================================
# RuntimeCoordinator Protection
# ==========================================================

Do NOT change RuntimeCoordinator execution order unless explicitly instructed.

Preserve the pipeline:

Conversation Context

↓

Memory Retrieval

↓

Knowledge Retrieval

↓

Understanding

↓

World Model

↓

Reasoning

↓

Planning

↓

Tool Decision

↓

Tool Execution

↓

AI Response

↓

Reflection

↓

Learning

↓

Evolution Observation

↓

Goal Intelligence

↓

Memory Storage

# ==========================================================
# Implementation Mode
# ==========================================================

If the user requests implementation:

Assume the implementation plan is already approved.

Do NOT regenerate architecture discussions.

Proceed directly to implementation.

Do NOT restate previously approved plans.

# ==========================================================
# Large Tasks
# ==========================================================

If a task affects multiple modules:

1. Inspect architecture.
2. Produce a short implementation plan.
3. Wait for user approval.

Do NOT perform large architectural rewrites automatically.

# ==========================================================
# Session Scope
# ==========================================================

Stay strictly within the current implementation batch.

Do NOT inspect future phases.

Do NOT anticipate future implementations unless explicitly requested.

# ==========================================================
# Repository Scan Budget
# ==========================================================

Repository-wide scans are expensive.

Before performing one, determine whether:

- symbol lookup
- filename search
- partial reads

can answer the same question.

Prefer local reasoning over global scanning.

# ==========================================================
# Testing Policy
# ==========================================================

Run:

- targeted tests during development
- the full test suite only once before completion

Avoid repeatedly executing the entire suite after every small change.

# ==========================================================
# Error Policy
# ==========================================================

If a command fails:

1. Analyze the error.
2. Attempt ONE fix.

If the same issue occurs again:

STOP.

Do NOT retry with alternative search patterns indefinitely.

Summarize the blocker in under three sentences.

Wait for user guidance.

# ==========================================================
# Token Efficiency
# ==========================================================

Keep responses concise.

Do NOT explain generated code unless requested.

Do NOT restate the task.

Do NOT summarize previous conversations.

Avoid conversational filler.

Avoid unnecessary markdown.

Explain only:

- architectural decisions
- failures
- blockers

Prefer concise implementation over explanation.

# ==========================================================
# Output Policy
# ==========================================================

Unless explicitly requested otherwise, provide only:

1. Files created
2. Files modified
3. Tests created
4. Test results
5. Architecture verification
6. Prohibited import scan
7. Deferred items

Avoid narrative explanations.

# ==========================================================
# Final Principle
# ==========================================================

Long-term maintainability always takes priority over short-term convenience.

Never sacrifice architecture to save a few lines of code.

Every implementation should make Atlas a better operating framework—not just complete the current task.