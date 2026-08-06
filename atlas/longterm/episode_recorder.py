"""Atlas Long-Term Learning — EpisodicRecorder (Track C, Batch 3).

Maps a :class:`~atlas.experience.models.StructuredExperience` into a
deterministic :class:`~atlas.longterm.models.Episode` with a fixed event
sequence: ``pipeline_start`` → optional ``tool_execution`` → ``pipeline_end``.
Recording is pure: episodes are data artifacts, never written to storage or
repositories by this module.

No infrastructure dependencies. No AI. No storage. No gateway. No kernel.
"""

from __future__ import annotations

from datetime import timedelta

from atlas.experience.models import StructuredExperience
from atlas.longterm.catalog import EVENT_ID_PREFIX, EPISODE_ID_PREFIX
from atlas.longterm.models import Episode, EpisodeEvent, EpisodeKind

_DEFAULT_IMPORTANCE: float = 0.5


class EpisodicRecorder:
    """Builds deterministic :class:`Episode` objects from experiences.

    Args:
        importance: Importance score assigned to recorded episodes
            (0.0–1.0, used by retention decisions).
    """

    def __init__(self, importance: float = _DEFAULT_IMPORTANCE) -> None:
        self._importance = importance

    # ------------------------------------------------------------------
    # Recording
    # ------------------------------------------------------------------

    def record(
        self, experience: StructuredExperience, session_id: str = ""
    ) -> Episode:
        """Convert one structured experience into an episode.

        Args:
            experience: The pipeline execution to record.
            session_id: Optional session id used to scope the episode id.

        Returns:
            A frozen :class:`Episode` derived entirely from the experience.
        """
        episode_id = self._episode_id(experience, session_id)
        outcome = experience.outcome.name.lower()
        events = self._build_events(experience, episode_id, outcome)
        title = self._build_title(experience)
        summary = self._build_summary(experience, outcome)
        return Episode(
            episode_id=episode_id,
            kind=EpisodeKind.PIPELINE,
            title=title,
            summary=summary,
            events=tuple(events),
            outcome=outcome,
            source_experience_id=experience.experience_id,
            started_at=experience.timestamp,
            ended_at=experience.timestamp
            + timedelta(milliseconds=experience.duration_ms),
            importance=self._importance,
            tags=tuple(sorted(experience.pipeline_path)),
            metadata={
                "pipeline_path": list(experience.pipeline_path),
                "duration_ms": experience.duration_ms,
            },
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _episode_id(experience: StructuredExperience, session_id: str) -> str:
        """Stable episode id (session-scoped when a session id is given)."""
        if session_id:
            return f"{EPISODE_ID_PREFIX}:{session_id}:{experience.experience_id}"
        return f"{EPISODE_ID_PREFIX}:{experience.experience_id}"

    @staticmethod
    def _build_title(experience: StructuredExperience) -> str:
        """Describe the pipeline path in the title."""
        if not experience.pipeline_path:
            return "pipeline"
        return "pipeline: " + " > ".join(experience.pipeline_path)

    @staticmethod
    def _build_summary(experience: StructuredExperience, outcome: str) -> str:
        """Summarize the experience's input or outcome."""
        if experience.user_input:
            return experience.user_input
        return f"{outcome} across {len(experience.pipeline_path)} pipeline stages"

    @classmethod
    def _build_events(
        cls,
        experience: StructuredExperience,
        episode_id: str,
        outcome: str,
    ) -> list[EpisodeEvent]:
        """Build the deterministic event sequence for an episode."""
        prefix = f"{EVENT_ID_PREFIX}:{experience.experience_id}"
        events: list[EpisodeEvent] = [
            EpisodeEvent(
                event_id=f"{prefix}:0000",
                episode_id=episode_id,
                sequence=0,
                event_type="pipeline_start",
                summary="pipeline started",
                occurred_at=experience.timestamp,
                metadata={"pipeline_path": list(experience.pipeline_path)},
            )
        ]

        if experience.tool_name:
            events.append(
                EpisodeEvent(
                    event_id=f"{prefix}:0001",
                    episode_id=episode_id,
                    sequence=1,
                    event_type="tool_execution",
                    summary=f"tool: {experience.tool_name}",
                    occurred_at=experience.timestamp
                    + timedelta(milliseconds=experience.duration_ms / 2),
                    metadata={
                        "tool_name": experience.tool_name,
                        "tool_success": experience.tool_success,
                    },
                )
            )

        end_sequence = events[-1].sequence + 1
        events.append(
            EpisodeEvent(
                event_id=f"{prefix}:{end_sequence:04d}",
                episode_id=episode_id,
                sequence=end_sequence,
                event_type="pipeline_end",
                summary=f"outcome: {outcome}",
                occurred_at=experience.timestamp
                + timedelta(milliseconds=experience.duration_ms),
                metadata={
                    "duration_ms": experience.duration_ms,
                    "outcome": outcome,
                    "learning_insights_count": experience.learning_insights_count,
                },
            )
        )
        return events
