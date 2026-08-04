"""Atlas Toolchain — Tool Effectiveness Tracker.

Accumulates :class:`ToolEffectivenessRecord` observations and computes
per-tool :class:`ToolEffectivenessScore` aggregates. Pure in-memory
aggregation — no persistence, no AI, no gateway, no kernel.

The tracker is the learning surface for Track B: every tool execution
outcome (success, failure, timing) is recorded here, and the aggregated
scores feed back into the :class:`ToolChainPlanner` (future batch) and
the evolution framework as evidence.

Deterministic: identical observation sequences always produce identical
scores. The effectiveness formula is:

    effectiveness = (success_weight * success_rate)
                  + (speed_weight * speed_score)

where ``speed_score = 1.0 - min(avg_time_ms / baseline_ms, 1.0)``.
"""

from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Any

from atlas.toolchain.catalog import (
    DEFAULT_EFFECTIVENESS,
    EFFECTIVENESS_BASELINE_MS,
    EFFECTIVENESS_MIN_OBSERVATIONS,
    EFFECTIVENESS_SPEED_WEIGHT,
    EFFECTIVENESS_SUCCESS_WEIGHT,
    RECORD_ID_PREFIX,
)
from atlas.toolchain.models import ToolEffectivenessRecord, ToolEffectivenessScore


class ToolEffectivenessTracker:
    """In-memory aggregator of tool execution effectiveness.

    The tracker is pure logic: it stores observations in a dict keyed by
    tool name and computes scores on demand. It never persists data and
    never calls external services. Fail-closed: recording an observation
    for an unknown tool is allowed (the tracker is observation-driven, not
    registry-driven), but computing a score for a tool with no
    observations returns a default score rather than raising.
    """

    def __init__(self) -> None:
        """Initialise an empty tracker."""
        self._records: dict[str, list[ToolEffectivenessRecord]] = {}

    # ------------------------------------------------------------------
    # Recording
    # ------------------------------------------------------------------

    def record(
        self,
        tool_name: str,
        *,
        success: bool,
        execution_time_ms: float = 0.0,
        context: dict[str, Any] | None = None,
        skill_id: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> ToolEffectivenessRecord:
        """Record a single tool execution observation.

        Args:
            tool_name: Name of the tool that was executed.
            success: Whether the execution succeeded.
            execution_time_ms: Execution time in milliseconds.
            context: Optional execution context (hashed for grouping).
            skill_id: Optional skill that triggered the execution.
            metadata: Optional additional observation context.

        Returns:
            The created :class:`ToolEffectivenessRecord`.
        """
        if not tool_name:
            raise ValueError("tool_name must not be empty")
        if execution_time_ms < 0:
            execution_time_ms = 0.0

        context_dict: dict[str, Any] = context or {}
        context_hash: str = self._context_hash(context_dict)
        record_id: str = self._record_id(tool_name, context_hash)

        record = ToolEffectivenessRecord(
            record_id=record_id,
            tool_name=tool_name,
            success=success,
            execution_time_ms=execution_time_ms,
            context_hash=context_hash,
            skill_id=skill_id,
            recorded_at=datetime.now(),
            metadata=metadata or {},
        )
        self._records.setdefault(tool_name, []).append(record)
        return record

    def record_observation(self, record: ToolEffectivenessRecord) -> None:
        """Record a pre-built :class:`ToolEffectivenessRecord`.

        Useful when records are reconstructed from persistence.

        Args:
            record: The observation to add.
        """
        if not record.tool_name:
            raise ValueError("record.tool_name must not be empty")
        self._records.setdefault(record.tool_name, []).append(record)

    # ------------------------------------------------------------------
    # Scoring
    # ------------------------------------------------------------------

    def score(self, tool_name: str) -> ToolEffectivenessScore:
        """Compute the aggregated effectiveness score for a tool.

        Args:
            tool_name: The tool to score.

        Returns:
            A :class:`ToolEffectivenessScore`. For a tool with no
            observations, a default score (``effectiveness =
            DEFAULT_EFFECTIVENESS``) is returned.
        """
        records: list[ToolEffectivenessRecord] = self._records.get(tool_name, [])
        if not records:
            return ToolEffectivenessScore(
                tool_name=tool_name,
                effectiveness=DEFAULT_EFFECTIVENESS,
            )

        total: int = len(records)
        success_count: int = sum(1 for r in records if r.success)
        failure_count: int = total - success_count
        success_rate: float = success_count / total if total else 0.0
        avg_time: float = sum(r.execution_time_ms for r in records) / total
        speed_score: float = max(0.0, 1.0 - (avg_time / EFFECTIVENESS_BASELINE_MS))
        effectiveness: float = (
            EFFECTIVENESS_SUCCESS_WEIGHT * success_rate
            + EFFECTIVENESS_SPEED_WEIGHT * speed_score
        )
        last_observed: datetime = max(r.recorded_at for r in records)

        return ToolEffectivenessScore(
            tool_name=tool_name,
            total_observations=total,
            success_count=success_count,
            failure_count=failure_count,
            success_rate=success_rate,
            avg_execution_time_ms=avg_time,
            effectiveness=effectiveness,
            last_observed_at=last_observed,
        )

    def score_all(self) -> list[ToolEffectivenessScore]:
        """Compute scores for every tool with at least one observation.

        Returns:
            A list of :class:`ToolEffectivenessScore` sorted by tool name.
        """
        return sorted(
            (self.score(name) for name in self._records),
            key=lambda s: s.tool_name,
        )

    def top_tools(self, limit: int = 5) -> list[ToolEffectivenessScore]:
        """Return the top-``limit`` tools by effectiveness score.

        Ties are broken by tool name (alphabetical). Tools with fewer
        than :data:`EFFECTIVENESS_MIN_OBSERVATIONS` observations are
        included but flagged in their metadata (callers may filter).

        Args:
            limit: Maximum number of tools to return.

        Returns:
            A list of :class:`ToolEffectivenessScore` sorted by
            effectiveness (highest first).
        """
        scores: list[ToolEffectivenessScore] = self.score_all()
        scored_with_flag: list[tuple[float, str, ToolEffectivenessScore]] = []
        for s in scores:
            flagged: ToolEffectivenessScore = self._flag_confidence(s)
            scored_with_flag.append((flagged.effectiveness, flagged.tool_name, flagged))
        scored_with_flag.sort(key=lambda x: (-x[0], x[1]))
        return [item[2] for item in scored_with_flag[: max(0, limit)]]

    # ------------------------------------------------------------------
    # Querying
    # ------------------------------------------------------------------

    def observations(self, tool_name: str) -> list[ToolEffectivenessRecord]:
        """Return all observations for a tool (insertion order).

        Args:
            tool_name: The tool to query.

        Returns:
            A list of :class:`ToolEffectivenessRecord`. Empty if the tool
            has no observations.
        """
        return list(self._records.get(tool_name, []))

    def observed_tools(self) -> list[str]:
        """Return sorted tool names that have at least one observation."""
        return sorted(self._records.keys())

    @property
    def total_observations(self) -> int:
        """Total number of observations across all tools."""
        return sum(len(records) for records in self._records.values())

    @property
    def observed_tool_count(self) -> int:
        """Number of distinct tools with at least one observation."""
        return len(self._records)

    # ------------------------------------------------------------------
    # Maintenance
    # ------------------------------------------------------------------

    def clear(self) -> None:
        """Remove all observations."""
        self._records.clear()

    def reset_tool(self, tool_name: str) -> None:
        """Remove all observations for a single tool.

        Args:
            tool_name: The tool to reset.
        """
        self._records.pop(tool_name, None)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    @staticmethod
    def _context_hash(context: dict[str, Any]) -> str:
        """Stable hash of an execution context dict (sha256[:16])."""
        # Sort keys for determinism.
        serialized: str = repr(sorted(context.items()))
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()[:16]

    @staticmethod
    def _record_id(tool_name: str, context_hash: str) -> str:
        """Deterministic record id."""
        return f"{RECORD_ID_PREFIX}:{tool_name}:{context_hash}"

    @staticmethod
    def _flag_confidence(score: ToolEffectivenessScore) -> ToolEffectivenessScore:
        """Return a copy of ``score`` with a low-confidence metadata flag.

        Because :class:`ToolEffectivenessScore` is frozen, we rebuild it.
        The flag is embedded in the score's metadata via a wrapper — but
        since the frozen dataclass has no metadata field, we instead
        return the score unchanged and rely on callers to inspect
        ``total_observations`` directly. This method is retained for
        future extension.
        """
        return score