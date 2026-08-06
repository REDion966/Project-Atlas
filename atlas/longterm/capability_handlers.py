"""Atlas Long-Term Learning — Capability Handlers (Track C, Batch 4).

Registers the three Track C capabilities following the Atlas
``CapabilityRegistry`` pattern (``CapabilityHandler = Callable[[dict], ExecutionResult]``):

  memory.episodic_query  — query recent episodes by time/outcome
  memory.procedure_query — query distilled procedures by category/tool
  memory.consolidate     — run a consolidation pass (governed)

Handlers are pure bridges: all work is delegated to injected components
(repositories, consolidator, evolution tracker). Deterministic, no direct
state mutation. ``memory.consolidate`` NEVER mutates the repositories — it
runs the pure consolidator, records the PENDING audit record, and hands the
governed request through the ``LongTermIngestBridge``. Without a sink it
fails closed.

No handler mutates Atlas state. No handler directly mutates the
``CapabilityRegistry`` — the :meth:`LongTermCapabilityFactory.register`
method is the only registration surface.
"""

from __future__ import annotations

from typing import Any, Callable

from atlas.longterm.consolidator import ConsolidationResult, Consolidator
from atlas.longterm.episode_repository import EpisodicRepository
from atlas.longterm.evolution_integration import (
    IngestHandoffResult,
    LongTermEvolutionTracker,
    LongTermIngestBridge,
)
from atlas.longterm.models import ConsolidationRecord, ConsolidationStatus
from atlas.longterm.procedure_repository import ProceduralRepository

from atlas.reasoning.execution.models import ExecutionResult
from atlas.reasoning.execution.registry import CapabilityRegistry

CapabilityHandler = Callable[[dict[str, Any]], ExecutionResult]

_MAX_QUERY_LIMIT: int = 500


class LongTermCapabilityFactory:
    """Constructs the three Track C capability handlers with DI."""

    def __init__(
        self,
        episodes: EpisodicRepository | None = None,
        procedures: ProceduralRepository | None = None,
        consolidator: Consolidator | None = None,
        tracker: LongTermEvolutionTracker | None = None,
        evolve_bridge: LongTermIngestBridge | None = None,
    ) -> None:
        """Initialise the factory with optional constructor-injected deps."""
        self._episodes = episodes or EpisodicRepository()
        self._procedures = procedures or ProceduralRepository()
        self._consolidator = consolidator or Consolidator()
        self._tracker = tracker or LongTermEvolutionTracker()
        self._evolution = evolve_bridge or LongTermIngestBridge(
            tracker=self._tracker
        )

    @property
    def episodes(self) -> EpisodicRepository:
        return self._episodes

    @property
    def procedures(self) -> ProceduralRepository:
        return self._procedures

    # ------------------------------------------------------------------
    # Registration surface
    # ------------------------------------------------------------------

    def handlers(self) -> dict[str, CapabilityHandler]:
        """Return the three long-term capabilities keyed by name."""
        return {
            "memory.episodic_query": self._episodic_query_handler,
            "memory.procedure_query": self._procedure_query_handler,
            "memory.consolidate": self._consolidate_handler,
        }

    def register(self, registry: CapabilityRegistry) -> None:
        """Register all three handlers into a ``CapabilityRegistry``."""
        for name, handler in self.handlers().items():
            registry.register(name, handler)

    # ------------------------------------------------------------------
    # memory.episodic_query
    # ------------------------------------------------------------------

    def _episodic_query_handler(self, params: dict[str, Any]) -> ExecutionResult:
        """Query recent episodes.

        Params:
            limit (int, optional): Max episodes (default 100, cap 500).
            outcome (str, optional): Filter by outcome label.
            since (str, optional): ISO timestamp; only episodes at/after it.
        """
        limit = self._normalize_limit(params.get("limit"))
        outcome = params.get("outcome")
        since = params.get("since")

        try:
            if isinstance(since, str) and since:
                from datetime import datetime

                episodes = self._episodes.get_episodes_since(
                    datetime.fromisoformat(since)
                )
            elif isinstance(outcome, str) and outcome:
                episodes = self._episodes.get_episodes_by_outcome(outcome, n=limit)
            else:
                episodes = self._episodes.get_episodes(n=limit)
            return ExecutionResult(
                capability="memory.episodic_query",
                success=True,
                output={"episodes": [e.to_dict() for e in episodes]},
                metadata={
                    "handler": "memory.episodic_query",
                    "count": len(episodes),
                },
            )
        except Exception as exc:  # pragma: no cover - defensive boundary
            return ExecutionResult(
                capability="memory.episodic_query",
                success=False,
                error=str(exc),
                metadata={"handler": "memory.episodic_query"},
            )

    # ------------------------------------------------------------------
    # memory.procedure_query
    # ------------------------------------------------------------------

    def _procedure_query_handler(self, params: dict[str, Any]) -> ExecutionResult:
        """Query distilled procedures.

        Params:
            limit (int, optional): Max procedures (default 100, cap 500).
            category (str, optional): Filter by category.
            tool (str, optional): Filter by referenced tool name.
        """
        limit = self._normalize_limit(params.get("limit"))
        category = params.get("category")
        tool_name = params.get("tool")

        try:
            if isinstance(category, str) and category:
                procedures = self._procedures.get_procedures_by_category(
                    category, n=limit
                )
            elif isinstance(tool_name, str) and tool_name:
                procedures = self._procedures.get_procedures_by_tool(
                    tool_name, n=limit
                )
            else:
                procedures = self._procedures.get_procedures(n=limit)
            return ExecutionResult(
                capability="memory.procedure_query",
                success=True,
                output={"procedures": [p.to_dict() for p in procedures]},
                metadata={
                    "handler": "memory.procedure_query",
                    "count": len(procedures),
                },
            )
        except Exception as exc:  # pragma: no cover - defensive boundary
            return ExecutionResult(
                capability="memory.procedure_query",
                success=False,
                error=str(exc),
                metadata={"handler": "memory.procedure_query"},
            )

    # ------------------------------------------------------------------
    # memory.consolidate — governed
    # ------------------------------------------------------------------

    def _consolidate_handler(self, params: dict[str, Any]) -> ExecutionResult:
        """Run a consolidation pass and submit governed ingest.

        Runs the pure :class:`Consolidator` over the repositories' contents,
        builds one PENDING :class:`ConsolidationRecord`, persists the audit
        record to the injected storage (best-effort), and hands the governed
        request through the ``LongTermIngestBridge``. Without a sink the
        request fails closed and the repositories are never mutated.
        """
        try:
            result: ConsolidationResult = self._consolidator.consolidate(
                self._episodes.get_episodes(n=_MAX_QUERY_LIMIT),
                self._procedures.get_procedures(n=_MAX_QUERY_LIMIT),
            )
            if not result.ok:
                return ExecutionResult(
                    capability="memory.consolidate",
                    success=False,
                    error=result.error or "consolidation failed",
                    metadata={"handler": "memory.consolidate"},
                )

            record = self._build_pending_record(result)
            handoff: IngestHandoffResult = self._evolution.ingest(record)
            return ExecutionResult(
                capability="memory.consolidate",
                success=handoff.accepted,
                output={
                    "record": record.to_dict(),
                    "accepted": handoff.accepted,
                    "request_id": handoff.request_id,
                    "episodes_flagged": list(result.episodes_flagged),
                    "procedures_flagged": list(result.procedures_flagged),
                },
                error=handoff.error or "",
                metadata={
                    "handler": "memory.consolidate",
                    "governed": True,
                    "accepted": handoff.accepted,
                    "record_id": record.record_id,
                },
            )
        except Exception as exc:  # pragma: no cover - defensive boundary
            return ExecutionResult(
                capability="memory.consolidate",
                success=False,
                error=str(exc),
                metadata={"handler": "memory.consolidate"},
            )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _normalize_limit(raw: Any) -> int:
        """Coerce an optional limit into a bounded positive int."""
        if isinstance(raw, int) and raw > 0:
            return min(raw, _MAX_QUERY_LIMIT)
        return 100

    @staticmethod
    def _build_pending_record(result: ConsolidationResult) -> ConsolidationRecord:
        """Merge all consolidation actions into one PENDING audit record."""
        target_types: list[str] = []
        operation = "merge"
        target_ids: list[str] = []
        reasons: list[str] = []

        if result.episodes_consolidated:
            target_types.append("episode")
            target_ids.extend(e.episode_id for e in result.episodes_consolidated)
            reasons.append("dedup")
        if result.procedures_merged:
            target_types.append("procedure")
            target_ids.extend(p.procedure_id for p in result.procedures_merged)
            reasons.append("merge")
        if result.episodes_flagged:
            target_types.append("episode")
            target_ids.extend(result.episodes_flagged)
            reasons.append("forget")
        if result.procedures_flagged:
            target_types.append("procedure")
            target_ids.extend(result.procedures_flagged)
            reasons.append("forget")

        if not target_ids:
            return ConsolidationRecord(
                record_id=f"consol:none:{result.records[0].record_id}"
                if result.records
                else "consol:none",
                status=ConsolidationStatus.PENDING,
                operation=result.records[0].operation
                if result.records
                else "noop",
                target_type="episode",
                reason="no consolidation actions",
            )

        from datetime import datetime

        now = datetime.now()
        record_id = (
            f"consol:{now:%Y%m%d%H%M%S}:{len(target_ids)}:"
            f"{target_types[0]}"
        )
        return ConsolidationRecord(
            record_id=record_id,
            status=ConsolidationStatus.PENDING,
            operation=operation,
            target_type=",".join(sorted(set(target_types))),
            target_ids=tuple(sorted(set(target_ids))),
            reason="consolidation pass: " + ", ".join(sorted(set(reasons))),
            created_at=now,
        )
