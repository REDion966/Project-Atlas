# Project Atlas Development Context

## Mission

Project Atlas is an intelligent operating framework designed to coordinate:

- AI models
- Knowledge
- Memory
- Tools
- Automation
- Reasoning systems

The long-term goal is a self-evolving AI framework that can research, improve, and expand itself under human permission.

---

# Current Development Phase

## Stable Version

v0.5.3-stable

## Active Branch

phase5-memory-evolution


## Current Focus

Memory Evolution.

The objective is not only storing information.

The objective is creating a foundation for:

- retrieval
- ranking
- contextual understanding
- learning
- future autonomous reasoning

---

# Atlas Development Philosophy

Atlas must prioritize:

- Architecture quality
- Modularity
- Long-term maintainability
- Documentation
- Testing
- Controlled evolution

Quality must never be sacrificed for speed.

---

# Core Architecture

Current major systems:

- Kernel
- AI Layer
- Conversation Layer
- Memory Layer
- Knowledge Layer
- Workspace Layer
- Task Layer
- Event System
- State System

---

# Development Rules

Before changing architecture:

1. Understand existing implementation.
2. Review dependencies.
3. Create migration plan.
4. Document decisions.
5. Implement incrementally.
6. Run full tests.

---

# Forbidden Actions

Never:

- create duplicate systems
- replace architecture without migration
- modify tests to hide failures
- remove working features without review
- break backward compatibility without decision record

---

# Testing Requirement

Every architectural change must maintain:

pytest

passing completely.

---

# Source of Truth

The repository documentation and ADR records are the authority.

Conversation history is not the architecture source.