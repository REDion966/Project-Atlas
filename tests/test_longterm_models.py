"""Track C — Long-Term Learning data model tests (Batch 1).

Covers immutability (frozen + slots), defaults, enum membership, and
serialization compatibility for atlas/longterm/models.py.
"""

import json
from datetime import datetime
from enum import Enum

import pytest

from atlas.longterm.models import (
    ConsolidationRecord,
    ConsolidationStatus,
    Episode,
    EpisodeEvent,
    EpisodeKind,
    MemoryDecayPolicy,
    Procedure,
    ProcedureKind,
    ProcedureStep,
)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class TestEpisodeKind:
    def test_members(self):
        expected = {EpisodeKind.PIPELINE, EpisodeKind.SESSION, EpisodeKind.TASK}
        assert set(EpisodeKind) == expected

    def test_members_are_enum(self):
        assert issubclass(EpisodeKind, Enum)


class TestProcedureKind:
    def test_members(self):
        expected = {ProcedureKind.DISTILLED, ProcedureKind.MANUAL}
        assert set(ProcedureKind) == expected


class TestConsolidationStatus:
    def test_members(self):
        expected = {
            ConsolidationStatus.PENDING,
            ConsolidationStatus.APPLIED,
            ConsolidationStatus.REJECTED,
        }
        assert set(ConsolidationStatus) == expected


# ---------------------------------------------------------------------------
# EpisodeEvent
# ---------------------------------------------------------------------------


class TestEpisodeEvent:
    def test_create_minimal(self):
        event = EpisodeEvent(event_id="e1", episode_id="ep1")
        assert event.event_id == "e1"
        assert event.episode_id == "ep1"
        assert event.sequence == 0
        assert event.event_type == ""
        assert event.summary == ""
        assert isinstance(event.occurred_at, datetime)
        assert event.metadata == {}

    def test_create_full(self):
        event = EpisodeEvent(
            event_id="e2",
            episode_id="ep1",
            sequence=1,
            event_type="tool_execution",
            summary="Ran search",
            metadata={"tool": "search"},
        )
        assert event.sequence == 1
        assert event.event_type == "tool_execution"
        assert event.summary == "Ran search"
        assert event.metadata == {"tool": "search"}

    def test_immutability(self):
        event = EpisodeEvent(event_id="e3", episode_id="ep1")
        with pytest.raises(AttributeError):
            event.summary = "changed"  # type: ignore[misc]
        with pytest.raises(AttributeError):
            event.new_field = 1  # type: ignore[attr-defined]

    def test_to_dict(self):
        event = EpisodeEvent(
            event_id="e4",
            episode_id="ep1",
            sequence=2,
            event_type="pipeline_start",
        )
        data = event.to_dict()
        assert data["event_id"] == "e4"
        assert data["episode_id"] == "ep1"
        assert data["sequence"] == 2
        assert data["event_type"] == "pipeline_start"
        assert isinstance(data["occurred_at"], datetime)


# ---------------------------------------------------------------------------
# Episode
# ---------------------------------------------------------------------------


class TestEpisode:
    def test_create_minimal(self):
        episode = Episode(episode_id="ep1")
        assert episode.episode_id == "ep1"
        assert episode.kind == EpisodeKind.PIPELINE
        assert episode.title == ""
        assert episode.summary == ""
        assert episode.events == ()
        assert episode.outcome == ""
        assert episode.source_experience_id == ""
        assert isinstance(episode.started_at, datetime)
        assert episode.ended_at is None
        assert episode.importance == 0.5
        assert episode.tags == ()
        assert episode.metadata == {}

    def test_create_full(self):
        event = EpisodeEvent(event_id="e1", episode_id="ep2", sequence=0)
        episode = Episode(
            episode_id="ep2",
            kind=EpisodeKind.TASK,
            title="Research task",
            summary="Investigated X",
            events=(event,),
            outcome="success",
            source_experience_id="exp1",
            importance=0.8,
            tags=("research",),
        )
        assert episode.kind == EpisodeKind.TASK
        assert episode.event_count == 1
        assert episode.events == (event,)
        assert episode.outcome == "success"
        assert episode.source_experience_id == "exp1"
        assert episode.importance == 0.8
        assert episode.tags == ("research",)

    def test_immutability(self):
        episode = Episode(episode_id="ep3")
        with pytest.raises(AttributeError):
            episode.title = "changed"  # type: ignore[misc]
        with pytest.raises(AttributeError):
            episode.new_field = 1  # type: ignore[attr-defined]

    def test_to_dict(self):
        event = EpisodeEvent(event_id="e1", episode_id="ep4", sequence=0)
        episode = Episode(
            episode_id="ep4",
            kind=EpisodeKind.SESSION,
            events=(event,),
            outcome="partial",
            metadata={"k": "v"},
        )
        data = episode.to_dict()
        assert data["episode_id"] == "ep4"
        assert data["kind"] == "SESSION"
        assert data["events"][0]["event_id"] == "e1"
        assert data["outcome"] == "partial"
        assert data["metadata"] == {"k": "v"}
        assert isinstance(data["started_at"], datetime)

    def test_event_count_property(self):
        episode = Episode(episode_id="ep5")
        assert episode.event_count == 0
        event = EpisodeEvent(event_id="e1", episode_id="ep5")
        episode2 = Episode(episode_id="ep5", events=(event,))
        assert episode2.event_count == 1

    def test_duration_seconds_none_ended(self):
        episode = Episode(episode_id="ep6")
        assert episode.duration_seconds == 0.0

    def test_duration_seconds_with_ended(self):
        start = datetime(2026, 1, 1, 0, 0, 0)
        end = datetime(2026, 1, 1, 0, 1, 30)
        episode = Episode(episode_id="ep7", started_at=start, ended_at=end)
        assert episode.duration_seconds == 90.0


# ---------------------------------------------------------------------------
# ProcedureStep
# ---------------------------------------------------------------------------


class TestProcedureStep:
    def test_create_minimal(self):
        step = ProcedureStep(step_id="s1")
        assert step.step_id == "s1"
        assert step.description == ""
        assert step.tool_name == ""
        assert step.parameters == {}
        assert step.depends_on == ()

    def test_create_full(self):
        step = ProcedureStep(
            step_id="s2",
            description="Search for X",
            tool_name="search",
            parameters={"q": "atlas"},
            depends_on=("s1",),
        )
        assert step.description == "Search for X"
        assert step.tool_name == "search"
        assert step.parameters == {"q": "atlas"}
        assert step.depends_on == ("s1",)

    def test_immutability(self):
        step = ProcedureStep(step_id="s3")
        with pytest.raises(AttributeError):
            step.description = "changed"  # type: ignore[misc]

    def test_to_dict(self):
        step = ProcedureStep(
            step_id="s4",
            description="d",
            tool_name="t",
            parameters={"k": "v"},
            depends_on=("s0",),
        )
        data = step.to_dict()
        assert data["step_id"] == "s4"
        assert data["tool_name"] == "t"
        assert data["parameters"] == {"k": "v"}
        assert data["depends_on"] == ("s0",)


# ---------------------------------------------------------------------------
# Procedure
# ---------------------------------------------------------------------------


class TestProcedure:
    def test_create_minimal(self):
        procedure = Procedure(procedure_id="p1", name="proc")
        assert procedure.procedure_id == "p1"
        assert procedure.name == "proc"
        assert procedure.description == ""
        assert procedure.kind == ProcedureKind.DISTILLED
        assert procedure.category == "utility"
        assert procedure.steps == ()
        assert procedure.source_episode_ids == ()
        assert procedure.success_count == 0
        assert procedure.failure_count == 0
        assert procedure.confidence == 0.0
        assert isinstance(procedure.created_at, datetime)
        assert procedure.last_used_at is None
        assert procedure.tags == ()
        assert procedure.metadata == {}

    def test_create_full(self):
        step = ProcedureStep(step_id="s1", description="d")
        procedure = Procedure(
            procedure_id="p2",
            name="proc2",
            description="desc",
            kind=ProcedureKind.MANUAL,
            category="research",
            steps=(step,),
            source_episode_ids=("ep1", "ep2"),
            success_count=5,
            failure_count=1,
            confidence=0.9,
            tags=("research",),
        )
        assert procedure.kind == ProcedureKind.MANUAL
        assert procedure.step_count == 1
        assert procedure.source_episode_ids == ("ep1", "ep2")
        assert procedure.success_count == 5
        assert procedure.failure_count == 1
        assert procedure.confidence == 0.9
        assert procedure.tags == ("research",)

    def test_immutability(self):
        procedure = Procedure(procedure_id="p3", name="n")
        with pytest.raises(AttributeError):
            procedure.name = "changed"  # type: ignore[misc]

    def test_to_dict(self):
        step = ProcedureStep(step_id="s1", description="d")
        procedure = Procedure(
            procedure_id="p4",
            name="n",
            kind=ProcedureKind.DISTILLED,
            steps=(step,),
            metadata={"k": "v"},
        )
        data = procedure.to_dict()
        assert data["procedure_id"] == "p4"
        assert data["kind"] == "DISTILLED"
        assert data["steps"][0]["step_id"] == "s1"
        assert data["metadata"] == {"k": "v"}
        assert isinstance(data["created_at"], datetime)

    def test_step_count_property(self):
        procedure = Procedure(procedure_id="p5", name="n")
        assert procedure.step_count == 0
        step = ProcedureStep(step_id="s1")
        procedure2 = Procedure(procedure_id="p5", name="n", steps=(step,))
        assert procedure2.step_count == 1

    def test_total_applications(self):
        procedure = Procedure(
            procedure_id="p6",
            name="n",
            success_count=3,
            failure_count=2,
        )
        assert procedure.total_applications == 5

    def test_success_rate(self):
        procedure = Procedure(
            procedure_id="p7",
            name="n",
            success_count=3,
            failure_count=1,
        )
        assert procedure.success_rate == 0.75

    def test_success_rate_zero_applications(self):
        procedure = Procedure(procedure_id="p8", name="n")
        assert procedure.success_rate == 0.0


# ---------------------------------------------------------------------------
# ConsolidationRecord
# ---------------------------------------------------------------------------


class TestConsolidationRecord:
    def test_create_minimal(self):
        record = ConsolidationRecord(record_id="c1")
        assert record.record_id == "c1"
        assert record.status == ConsolidationStatus.PENDING
        assert record.operation == ""
        assert record.target_type == ""
        assert record.target_ids == ()
        assert record.reason == ""
        assert isinstance(record.created_at, datetime)
        assert record.applied_at is None
        assert record.metadata == {}

    def test_create_full(self):
        record = ConsolidationRecord(
            record_id="c2",
            status=ConsolidationStatus.APPLIED,
            operation="merge",
            target_type="episode",
            target_ids=("ep1", "ep2"),
            reason="duplicates",
        )
        assert record.status == ConsolidationStatus.APPLIED
        assert record.operation == "merge"
        assert record.target_type == "episode"
        assert record.target_ids == ("ep1", "ep2")
        assert record.reason == "duplicates"

    def test_immutability(self):
        record = ConsolidationRecord(record_id="c3")
        with pytest.raises(AttributeError):
            record.operation = "merge"  # type: ignore[misc]

    def test_to_dict(self):
        record = ConsolidationRecord(
            record_id="c4",
            status=ConsolidationStatus.REJECTED,
            operation="forget",
            target_ids=("ep1",),
            metadata={"k": "v"},
        )
        data = record.to_dict()
        assert data["record_id"] == "c4"
        assert data["status"] == "REJECTED"
        assert data["operation"] == "forget"
        assert data["target_ids"] == ("ep1",)
        assert data["metadata"] == {"k": "v"}


# ---------------------------------------------------------------------------
# MemoryDecayPolicy
# ---------------------------------------------------------------------------


class TestMemoryDecayPolicy:
    def test_defaults(self):
        policy = MemoryDecayPolicy()
        assert policy.max_episodes == 10_000
        assert policy.max_procedures == 1_000
        assert policy.episode_ttl_days == 0
        assert policy.procedure_ttl_days == 0
        assert policy.min_importance == 0.1
        assert policy.consolidation_threshold == 3
        assert policy.enabled is True

    def test_create_custom(self):
        policy = MemoryDecayPolicy(
            max_episodes=100,
            max_procedures=50,
            episode_ttl_days=30,
            procedure_ttl_days=60,
            min_importance=0.2,
            consolidation_threshold=5,
            enabled=False,
        )
        assert policy.max_episodes == 100
        assert policy.max_procedures == 50
        assert policy.episode_ttl_days == 30
        assert policy.procedure_ttl_days == 60
        assert policy.min_importance == 0.2
        assert policy.consolidation_threshold == 5
        assert policy.enabled is False

    def test_immutability(self):
        policy = MemoryDecayPolicy()
        with pytest.raises(AttributeError):
            policy.max_episodes = 1  # type: ignore[misc]

    def test_to_dict(self):
        policy = MemoryDecayPolicy(max_episodes=100, enabled=False)
        data = policy.to_dict()
        assert data["max_episodes"] == 100
        assert data["enabled"] is False
        assert data["consolidation_threshold"] == 3


# ---------------------------------------------------------------------------
# Serialization compatibility
# ---------------------------------------------------------------------------


class TestSerializationCompatibility:
    def test_nested_episode_serializes_to_json(self):
        event = EpisodeEvent(
            event_id="e1",
            episode_id="ep1",
            sequence=0,
            event_type="pipeline_start",
        )
        episode = Episode(
            episode_id="ep1",
            kind=EpisodeKind.PIPELINE,
            events=(event,),
            outcome="success",
        )
        data = episode.to_dict()

        def drop_datetimes(value):
            if isinstance(value, datetime):
                return value.isoformat()
            if isinstance(value, dict):
                return {k: drop_datetimes(v) for k, v in value.items()}
            if isinstance(value, (tuple, list)):
                return [drop_datetimes(v) for v in value]
            return value

        payload = json.dumps(drop_datetimes(data))
        parsed = json.loads(payload)
        assert parsed["episode_id"] == "ep1"
        assert parsed["events"][0]["event_id"] == "e1"
        assert parsed["events"][0]["event_type"] == "pipeline_start"

    def test_nested_procedure_serializes_to_json(self):
        step = ProcedureStep(step_id="s1", description="d", tool_name="t")
        procedure = Procedure(
            procedure_id="p1",
            name="n",
            steps=(step,),
            source_episode_ids=("ep1",),
        )
        data = procedure.to_dict()

        def drop_datetimes(value):
            if isinstance(value, datetime):
                return value.isoformat()
            if isinstance(value, dict):
                return {k: drop_datetimes(v) for k, v in value.items()}
            if isinstance(value, (tuple, list)):
                return [drop_datetimes(v) for v in value]
            return value

        payload = json.dumps(drop_datetimes(data))
        parsed = json.loads(payload)
        assert parsed["procedure_id"] == "p1"
        assert parsed["steps"][0]["tool_name"] == "t"
        assert parsed["source_episode_ids"] == ["ep1"]

    def test_enum_names_are_stable_strings(self):
        episode = Episode(episode_id="ep1", kind=EpisodeKind.TASK)
        assert episode.to_dict()["kind"] == "TASK"
        procedure = Procedure(
            procedure_id="p1",
            name="n",
            kind=ProcedureKind.MANUAL,
        )
        assert procedure.to_dict()["kind"] == "MANUAL"
        record = ConsolidationRecord(
            record_id="c1",
            status=ConsolidationStatus.APPLIED,
        )
        assert record.to_dict()["status"] == "APPLIED"