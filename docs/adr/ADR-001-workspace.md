# ADR-001

## Title

Workspace as the Root Organizational Unit

---

Status

Accepted

Date

2026-07-15

---

## Context

Atlas is intended to become a lifelong intelligence platform rather than a chatbot.

A conversation is only one temporary interaction.

Real work exists inside projects that contain files, knowledge, tasks, memories, permissions, and resources.

Atlas therefore requires a higher-level organizational structure than conversations.

---

## Decision

Workspace becomes the root container of Atlas.

A Workspace contains one or more Projects.

Projects contain Resources.

Resources represent anything Atlas can work with, including files, folders, repositories, websites, APIs, and databases.

Future subsystems including Memory, Knowledge, Planning, Research, and Engineering will operate on Projects rather than conversations.

---

## Consequences

Benefits

- Unified architecture
- Better scalability
- Easier autonomous operation
- Shared resources
- Better permission management
- Cleaner separation of responsibilities

Trade-offs

- Slightly higher implementation complexity.
- Additional abstraction layer.

These trade-offs are considered acceptable because they significantly improve long-term extensibility.

---

## Rationale

Atlas should think in terms of work rather than conversations.

Humans organize work into projects.

Atlas should do the same.

This decision establishes the architectural foundation required for future autonomous behavior.