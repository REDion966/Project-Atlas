# ADR-0002: Memory System

**Status:** Accepted  
**Date:** 2026-07-12  
**Decision Makers:** Atlas Core Team

---

> **Historical note — implementation superseded (documentation pass).** This
> record captures the original Alpha-stage decision to begin with a **JSON-based**
> memory storage. That backend is **historical**: the current implementation uses
> **SQLite** through the shared additive migration framework (current schema
> **v11**; see `docs/ATLAS_STATE.md` §7–§8). The decision context and the
> "Future Direction" below (the Memory Manager interface is designed to survive a
> backend change) are preserved as recorded history and do **not** describe the
> current backend. Formally superseding this ADR would require a new ADR, which is
> out of scope for this pass.

# Context

Atlas requires persistent memory to maintain information across sessions.

The memory system should be simple, human-readable, easy to debug, and extensible.

---

# Decision

Atlas will initially use a JSON-based storage system.

The Memory Manager will act as the public interface for memory operations.

The Storage layer will handle reading and writing to disk.

Runtime data will be stored inside the `data/` directory.

---

# Consequences

Benefits include:

- Easy debugging
- Human-readable format
- No external database dependency
- Rapid development

Potential drawbacks:

- Not optimized for very large datasets
- No concurrent write protection

These limitations are acceptable during the Alpha stage.

---

# Future Direction

The storage backend may later be replaced with:

- SQLite
- PostgreSQL
- Vector databases
- Distributed storage

without changing the Memory Manager interface.

---

# Outcome

Atlas separates memory logic from storage implementation, allowing future storage upgrades without affecting higher-level modules.