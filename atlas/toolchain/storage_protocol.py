"""Atlas Toolchain — Storage Protocol (Phase 18.8).

Pure interfaces for toolchain persistence. Implemented by
:class:`~atlas.storage.toolchain_storage.ToolchainSQLiteStorage`.

Persistence ONLY: skills, chains, effectiveness records, plans, results.
No business logic. No gateway. No kernel.

Mirrors :mod:`atlas.research.storage_protocol` (Track A).
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from atlas.toolchain.models import (
    Skill,
    ToolChain,
    ToolChainPlan,
    ToolChainResult,
    ToolEffectivenessRecord,
)


@runtime_checkable
class ToolchainStorage(Protocol):
    """Persistence surface for Track B toolchain artifacts.

    All methods are fail-closed: if the adapter is unavailable, write
    methods raise ``sqlite3.OperationalError`` and read methods return
    empty lists (or the adapter marks itself unavailable).
    """

    # -- lifecycle ---------------------------------------------------------

    def initialize(self) -> None:
        """Open the connection and apply additive migrations."""
        ...

    def close(self) -> None:
        """Close the connection cleanly."""
        ...

    def is_available(self) -> bool:
        """Return True when the adapter is initialized and usable."""
        ...

    # -- skills (idempotent upsert by skill_id) ----------------------------

    def store_skill(self, skill: Skill) -> None:
        """Store or update a skill."""
        ...

    def load_skills(self) -> list[Skill]:
        """Load all skills sorted by skill_id."""
        ...

    # -- chains (idempotent upsert by chain_id) ----------------------------

    def store_chain(self, chain: ToolChain) -> None:
        """Store or update a tool chain."""
        ...

    def load_chains(self) -> list[ToolChain]:
        """Load all chains sorted by chain_id."""
        ...

    # -- effectiveness records (append-only log) ---------------------------

    def store_effectiveness_record(self, record: ToolEffectivenessRecord) -> None:
        """Append an effectiveness observation (duplicates ignored)."""
        ...

    def load_effectiveness_records(self) -> list[ToolEffectivenessRecord]:
        """Load all effectiveness records sorted by recorded_at."""
        ...

    # -- plans (idempotent upsert by plan_id) ------------------------------

    def store_plan(self, plan: ToolChainPlan) -> None:
        """Store or update a tool chain plan."""
        ...

    def load_plans(self) -> list[ToolChainPlan]:
        """Load all plans sorted by created_at."""
        ...

    # -- results / reports (append-only log) ------------------------------

    def store_result(self, result: ToolChainResult) -> None:
        """Append an execution result to the report log."""
        ...

    def load_results(self) -> list[ToolChainResult]:
        """Load all execution results sorted by stored_at."""
        ...