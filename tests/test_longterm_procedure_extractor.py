"""Track C — ProcedureExtractor tests (Batch 3)."""

from datetime import datetime

from atlas.longterm.models import (
    Episode,
    EpisodeEvent,
    EpisodeKind,
    Procedure,
    ProcedureKind,
)
from atlas.longterm.procedure_extractor import ProcedureExtractor


def _make_episode(
    episode_id: str,
    *,
    outcome: str = "success",
    tool_name: str = "",
    importance: float = 0.5,
    started_at: datetime | None = None,
    tags: tuple[str, ...] = (),
) -> Episode:
    events: list[EpisodeEvent] = [
        EpisodeEvent(
            event_id=f"event:{episode_id}:0",
            episode_id=episode_id,
            sequence=0,
            event_type="pipeline_start",
        )
    ]
    if tool_name:
        events.append(
            EpisodeEvent(
                event_id=f"event:{episode_id}:1",
                episode_id=episode_id,
                sequence=1,
                event_type="tool_execution",
                metadata={"tool_name": tool_name},
            )
        )
    events.append(
        EpisodeEvent(
            event_id=f"event:{episode_id}:2",
            episode_id=episode_id,
            sequence=len(events),
            event_type="pipeline_end",
        )
    )
    return Episode(
        episode_id=episode_id,
        kind=EpisodeKind.PIPELINE,
        title=f"Episode {episode_id}",
        events=tuple(events),
        outcome=outcome,
        started_at=started_at or datetime(2026, 1, 1, 12, 0, 0),
        importance=importance,
        tags=tags,
    )


class TestExtract:
    def test_no_episodes(self):
        extractor = ProcedureExtractor()
        assert extractor.extract([]) == []

    def test_below_threshold_yields_nothing(self):
        extractor = ProcedureExtractor(threshold=3)
        episodes = [
            _make_episode("e1", tool_name="search"),
            _make_episode("e2", tool_name="search"),
        ]
        assert extractor.extract(episodes) == []

    def test_threshold_reached_distills_procedure(self):
        extractor = ProcedureExtractor(threshold=2)
        episodes = [
            _make_episode("e1", tool_name="search"),
            _make_episode("e2", tool_name="search"),
        ]
        procedures = extractor.extract(episodes)
        assert len(procedures) == 1
        procedure = procedures[0]
        assert isinstance(procedure, Procedure)
        assert procedure.kind == ProcedureKind.DISTILLED
        assert procedure.category == "tool"
        assert len(procedure.source_episode_ids) == 2

    def test_grouped_by_outcome(self):
        extractor = ProcedureExtractor(threshold=2)
        episodes = [
            _make_episode("e1", outcome="success", tool_name="search"),
            _make_episode("e2", outcome="success", tool_name="search"),
            _make_episode("e3", outcome="failure", tool_name="search"),
            _make_episode("e4", outcome="failure", tool_name="search"),
        ]
        procedures = extractor.extract(episodes)
        assert len(procedures) == 2
        outcomes = {p.metadata["outcome"] for p in procedures}
        assert outcomes == {"success", "failure"}

    def test_grouped_by_tool(self):
        extractor = ProcedureExtractor(threshold=2)
        episodes = [
            _make_episode("e1", tool_name="search"),
            _make_episode("e2", tool_name="search"),
            _make_episode("e3", tool_name="read"),
            _make_episode("e4", tool_name="read"),
        ]
        procedures = extractor.extract(episodes)
        assert len(procedures) == 2
        tools = {p.metadata["tool_name"] for p in procedures}
        assert tools == {"search", "read"}

    def test_deterministic_order(self):
        extractor = ProcedureExtractor(threshold=2)
        episodes = [
            _make_episode("e1", tool_name="b"),
            _make_episode("e2", tool_name="b"),
            _make_episode("e3", tool_name="a"),
            _make_episode("e4", tool_name="a"),
        ]
        first = [p.procedure_id for p in extractor.extract(episodes)]
        second = [p.procedure_id for p in extractor.extract(episodes)]
        assert first == second

    def test_success_counts_and_confidence(self):
        extractor = ProcedureExtractor(threshold=2)
        episodes = [
            _make_episode("e1", outcome="success", tool_name="search"),
            _make_episode("e2", outcome="success", tool_name="search"),
        ]
        procedure = extractor.extract(episodes)[0]
        assert procedure.success_count == 2
        assert procedure.failure_count == 0
        assert procedure.confidence == 1.0

    def test_failure_outcome_bucket_counts(self):
        extractor = ProcedureExtractor(threshold=2)
        episodes = [
            _make_episode("e1", outcome="failure", tool_name="search"),
            _make_episode("e2", outcome="failure", tool_name="search"),
        ]
        procedure = extractor.extract(episodes)[0]
        assert procedure.success_count == 0
        assert procedure.failure_count == 2
        assert procedure.confidence == 0.0

    def test_steps_include_tool(self):
        extractor = ProcedureExtractor(threshold=2)
        episodes = [
            _make_episode("e1", tool_name="search"),
            _make_episode("e2", tool_name="search"),
        ]
        procedure = extractor.extract(episodes)[0]
        step = next(s for s in procedure.steps if s.tool_name == "search")
        assert step.tool_name == "search"
        assert "tool_execution" in step.description


class TestImportanceFilter:
    def test_low_importance_skipped(self):
        extractor = ProcedureExtractor(threshold=2, min_importance=0.3)
        episodes = [
            _make_episode("e1", tool_name="search", importance=0.1),
            _make_episode("e2", tool_name="search", importance=0.5),
        ]
        assert extractor.extract(episodes) == []
