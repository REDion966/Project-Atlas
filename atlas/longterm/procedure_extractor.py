"""Atlas Long-Term Learning — ProcedureExtractor (Track C, Batch 3).

Distills reusable :class:`~atlas.longterm.models.Procedure` objects from
repeated episode patterns. Extraction is deterministic: episodes are grouped
by outcome + first tool event, and a procedure is produced when a group
reaches :attr:`consolidation_threshold` members. Step sequences are built
from the episodes' event types and tool names.

No infrastructure dependencies. No AI. No storage. No gateway. No kernel.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Iterable

from atlas.longterm.catalog import (
    DEFAULT_CONSOLIDATION_THRESHOLD,
    DEFAULT_PROCEDURE_CATEGORY,
    PROCEDURE_ID_PREFIX,
    STEP_ID_PREFIX,
)
from atlas.longterm.models import Episode, Procedure, ProcedureKind, ProcedureStep


class ProcedureExtractor:
    """Deterministic repeated-pattern detector for episodes.

    Args:
        threshold: Minimum number of episodes sharing a pattern before a
            procedure is distilled.
        min_importance: Episodes below this importance never contribute.
    """

    def __init__(
        self,
        threshold: int = DEFAULT_CONSOLIDATION_THRESHOLD,
        min_importance: float = 0.0,
    ) -> None:
        self._threshold = max(1, threshold)
        self._min_importance = min_importance

    # ------------------------------------------------------------------
    # Extraction
    # ------------------------------------------------------------------

    def extract(self, episodes: Iterable[Episode]) -> list[Procedure]:
        """Distill procedures from repeated episode patterns.

        Episodes are grouped into buckets keyed by
        ``(outcome, first_tool_name)``. Buckets that reach the threshold
        produce one procedure each, named after the most common pipeline
        path found in the bucket.

        Returns:
            A list of :class:`Procedure` objects (empty when no bucket
            reaches the threshold).
        """
        buckets: dict[tuple[str, str], list[Episode]] = defaultdict(list)
        for episode in episodes:
            if episode.importance < self._min_importance:
                continue
            buckets[self._pattern_key(episode)].append(episode)

        procedures: list[Procedure] = []
        for (outcome, tool_name), members in sorted(buckets.items()):
            if len(members) < self._threshold:
                continue
            procedures.append(self._build_procedure(members, outcome, tool_name))
        return procedures

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _pattern_key(episode: Episode) -> tuple[str, str]:
        """Grouping key: outcome + first tool event ('' when none)."""
        return episode.outcome, episode_first_tool(episode)

    @classmethod
    def _build_procedure(
        cls,
        members: list[Episode],
        outcome: str,
        tool_name: str,
    ) -> Procedure:
        """Build one procedure from a bucket of matching episodes."""
        sorted_members = sorted(members, key=lambda e: e.episode_id)
        procedure_id = (
            f"{PROCEDURE_ID_PREFIX}:{outcome}:{tool_name or 'no-tool'}"
        )
        steps = cls._build_steps(sorted_members)
        name = cls._name_for(sorted_members)
        success_count = sum(1 for e in sorted_members if e.outcome == "success")
        confidence = round(success_count / len(sorted_members), 4)
        category = (
            "tool"
            if tool_name
            else DEFAULT_PROCEDURE_CATEGORY
        )
        return Procedure(
            procedure_id=procedure_id,
            name=name,
            description=cls._description_for(sorted_members),
            kind=ProcedureKind.DISTILLED,
            category=category,
            steps=tuple(steps),
            source_episode_ids=tuple(e.episode_id for e in sorted_members),
            success_count=success_count,
            failure_count=len(sorted_members) - success_count,
            confidence=confidence,
            created_at=sorted_members[0].started_at,
            last_used_at=sorted_members[-1].ended_at,
            tags=("distilled", outcome, tool_name or "no-tool"),
            metadata={
                "outcome": outcome,
                "tool_name": tool_name,
                "episode_count": len(sorted_members),
            },
        )

    @staticmethod
    def _name_for(members: list[Episode]) -> str:
        """Name a procedure after its most common pipeline path."""
        paths: dict[str, int] = {}
        for episode in members:
            for item in episode.tags:
                paths[item] = paths.get(item, 0) + 1
        if paths:
            best = max(paths.items(), key=lambda pair: pair[1])[0]
            cleaned = best.replace(":", " ").replace("_", " ").strip()
            if cleaned:
                return cleaned.title()
        return "distilled procedure"

    @staticmethod
    def _description_for(members: list[Episode]) -> str:
        """Describe the procedure from the bucket members."""
        outcomes: dict[str, int] = {}
        for episode in members:
            outcomes[episode.outcome] = outcomes.get(episode.outcome, 0) + 1
        parts = ", ".join(
            f"{k}={v}" for k, v in sorted(outcomes.items())
        )
        return f"distilled from {len(members)} episodes ({parts})"

    @staticmethod
    def _step_description(event_type: str, tool_name: str) -> str:
        """Human-readable description for one procedure step."""
        if tool_name:
            return f"{event_type} via {tool_name}"
        return event_type

    @classmethod
    def _build_steps(cls, members: list[Episode]) -> list[ProcedureStep]:

        """Build deterministic steps from the bucket's event sequence."""
        event_types: list[tuple[str, str]] = []
        for episode in members:
            for event in episode.events:
                pair = (event.event_type, event.metadata.get("tool_name", ""))
                if pair not in event_types:
                    event_types.append(pair)
        steps: list[ProcedureStep] = []
        for index, (event_type, tool_name) in enumerate(event_types):
            steps.append(
                ProcedureStep(
                    step_id=f"{STEP_ID_PREFIX}:{index:04d}",
                    description=cls._step_description(event_type, tool_name),
                    tool_name=tool_name,
                    parameters={
                        "event_type": event_type,
                        "expected_outcome": "success",
                    },
                )
            )
        return steps


def episode_first_tool(episode: Episode) -> str:
    """Return the first tool referenced by an episode ('' when none)."""
    for event in episode.events:
        tool = event.metadata.get("tool_name", "")
        if tool:
            return tool
    return ""
