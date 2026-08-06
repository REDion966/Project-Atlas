"""Track C — EpisodicRecorder tests (Batch 3)."""

from datetime import datetime

from atlas.experience.models import ExperienceOutcome, StructuredExperience
from atlas.longterm.episode_recorder import EpisodicRecorder
from atlas.longterm.models import Episode, EpisodeKind


def _make_experience(
    experience_id: str = "exp1",
    *,
    outcome: ExperienceOutcome = ExperienceOutcome.SUCCESS,
    tool_name: str = "",
    duration_ms: float = 1000.0,
    timestamp: datetime | None = None,
    user_input: str = "",
    pipeline_path: list[str] | None = None,
) -> StructuredExperience:
    return StructuredExperience(
        experience_id=experience_id,
        timestamp=timestamp or datetime(2026, 1, 1, 12, 0, 0),
        duration_ms=duration_ms,
        pipeline_path=pipeline_path or ["understanding", "reasoning"],
        outcome=outcome,
        user_input=user_input,
        tool_name=tool_name,
        tool_success=bool(tool_name),
        learning_insights_count=2 if not tool_name else 3,
    )


class TestRecord:
    def test_returns_episode(self):
        recorder = EpisodicRecorder()
        episode = recorder.record(_make_experience())
        assert isinstance(episode, Episode)
        assert episode.kind == EpisodeKind.PIPELINE
        assert episode.source_experience_id == "exp1"
        assert episode.outcome == "success"

    def test_episode_id_prefix(self):
        recorder = EpisodicRecorder()
        episode = recorder.record(_make_experience("exp9"))
        assert episode.episode_id.startswith("episode:")
        assert episode.episode_id.endswith("exp9")

    def test_session_scoped_id(self):
        recorder = EpisodicRecorder()
        episode = recorder.record(_make_experience("exp1"), session_id="s1")
        assert episode.episode_id == "episode:s1:exp1"

    def test_deterministic(self):
        recorder = EpisodicRecorder()
        first = recorder.record(_make_experience("exp1"))
        second = recorder.record(_make_experience("exp1"))
        assert first.to_dict() == second.to_dict()

    def test_timestamps_from_experience(self):
        recorder = EpisodicRecorder()
        start = datetime(2026, 2, 2, 3, 4, 5)
        episode = recorder.record(_make_experience("exp1", timestamp=start, duration_ms=500))
        assert episode.started_at == start
        assert episode.ended_at is not None
        assert (episode.ended_at - start).total_seconds() == 0.5


class TestEvents:
    def test_pipeline_start_and_end(self):
        recorder = EpisodicRecorder()
        episode = recorder.record(_make_experience("exp1"))
        assert episode.event_count == 2
        assert episode.events[0].event_type == "pipeline_start"
        assert episode.events[-1].event_type == "pipeline_end"

    def test_tool_event_inserted(self):
        recorder = EpisodicRecorder()
        episode = recorder.record(_make_experience("exp1", tool_name="search"))
        assert episode.event_count == 3
        assert episode.events[1].event_type == "tool_execution"
        assert episode.events[1].metadata["tool_name"] == "search"

    def test_sequence_numbers(self):
        recorder = EpisodicRecorder()
        episode = recorder.record(_make_experience("exp1", tool_name="search"))
        assert [e.sequence for e in episode.events] == [0, 1, 2]

    def test_event_ids_unique(self):
        recorder = EpisodicRecorder()
        episode = recorder.record(_make_experience("exp1", tool_name="tool"))
        ids = {e.event_id for e in episode.events}
        assert len(ids) == len(episode.events)


class TestDerivedFields:
    def test_title_from_pipeline_path(self):
        recorder = EpisodicRecorder()
        episode = recorder.record(
            _make_experience("exp1", pipeline_path=["research", "planning"])
        )
        assert "research" in episode.title
        assert "planning" in episode.title

    def test_summary_uses_user_input(self):
        recorder = EpisodicRecorder()
        episode = recorder.record(_make_experience("exp1", user_input="hello atlas"))
        assert episode.summary == "hello atlas"

    def test_summary_fallback(self):
        recorder = EpisodicRecorder()
        episode = recorder.record(_make_experience("exp1"))
        assert episode.summary.startswith("success across")

    def test_tags_from_pipeline_path(self):
        recorder = EpisodicRecorder()
        episode = recorder.record(
            _make_experience("exp1", pipeline_path=["b", "a"])
        )
        assert set(episode.tags) == {"b", "a"}

    def test_importance_configured(self):
        recorder = EpisodicRecorder(importance=0.9)
        episode = recorder.record(_make_experience("exp1"))
        assert episode.importance == 0.9
