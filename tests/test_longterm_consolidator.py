"""Track C — Consolidator tests (Batch 3)."""

from datetime import datetime, timedelta

from atlas.longterm.consolidator import Consolidator
from atlas.longterm.models import (
    Episode,
    EpisodeKind,
    MemoryDecayPolicy,
    Procedure,
    ProcedureKind,
    ProcedureStep,
)


def _make_episode(
    episode_id: str,
    *,
    importance: float = 0.5,
    outcome: str = "success",
    started_at: datetime | None = None,
    ended_at: datetime | None = None,
) -> Episode:
    return Episode(
        episode_id=episode_id,
        kind=EpisodeKind.PIPELINE,
        title=f"Episode {episode_id}",
        outcome=outcome,
        started_at=started_at or datetime(2026, 1, 1, 12, 0, 0),
        ended_at=ended_at,
        importance=importance,
    )


def _make_procedure(
    procedure_id: str,
    *,
    category: str = "utility",
    confidence: float = 0.8,
    success_count: int = 1,
    failure_count: int = 0,
    created_at: datetime | None = None,
    last_used_at: datetime | None = None,
    steps: tuple[ProcedureStep, ...] = (),
) -> Procedure:
    return Procedure(
        procedure_id=procedure_id,
        name=f"Procedure {procedure_id}",
        kind=ProcedureKind.DISTILLED,
        category=category,
        source_episode_ids=(f"ep:{procedure_id}",),
        success_count=success_count,
        failure_count=failure_count,
        confidence=confidence,
        created_at=created_at or datetime(2026, 1, 1, 12, 0, 0),
        last_used_at=last_used_at,
        steps=steps,
    )


class TestDedup:
    def test_no_duplicates(self):
        consolidator = Consolidator()
        episodes = [_make_episode("e1"), _make_episode("e2")]
        result = consolidator.consolidate(episodes=episodes)
        assert result.ok
        assert len(result.episodes_kept) == 2
        assert result.episodes_consolidated == ()

    def test_duplicate_episodes_keep_highest_importance(self):
        consolidator = Consolidator()
        low = _make_episode("e1", importance=0.2)
        high = _make_episode("e1", importance=0.9)
        result = consolidator.consolidate(episodes=[low, high])
        assert len(result.episodes_kept) == 1
        assert result.episodes_kept[0].importance == 0.9
        assert len(result.episodes_consolidated) == 1


class TestMerge:
    def test_duplicate_procedures_merged(self):
        consolidator = Consolidator()
        first = _make_procedure("p1", success_count=2, failure_count=0)
        second = _make_procedure("p1", success_count=1, failure_count=1)
        result = consolidator.consolidate(procedures=[first, second])
        assert len(result.procedures_kept) == 1
        merged = result.procedures_kept[0]
        assert merged.success_count == 3
        assert merged.failure_count == 1
        assert merged.confidence == 0.75
        assert len(result.procedures_merged) == 1

    def test_merge_unions_steps(self):
        consolidator = Consolidator()
        step_a = ProcedureStep(step_id="s1", description="a")
        step_b = ProcedureStep(step_id="s2", description="b")
        first = _make_procedure("p1", steps=(step_a,))
        second = _make_procedure("p1", steps=(step_b,))
        result = consolidator.consolidate(procedures=[first, second])
        merged = result.procedures_kept[0]
        assert {s.step_id for s in merged.steps} == {"s1", "s2"}


class TestForgetting:
    def test_low_importance_flagged(self):
        consolidator = Consolidator(
            policy=MemoryDecayPolicy(min_importance=0.4),
            now=datetime(2026, 1, 10, 12, 0, 0),
        )
        episodes = [
            _make_episode("e1", importance=0.1),
            _make_episode("e2", importance=0.9),
        ]
        result = consolidator.consolidate(episodes=episodes)
        assert result.episodes_flagged == ("e1",)

    def test_stale_episode_flagged_by_ttl(self):
        now = datetime(2026, 1, 10, 12, 0, 0)
        consolidator = Consolidator(
            policy=MemoryDecayPolicy(episode_ttl_days=3),
            now=now,
        )
        old = _make_episode(
            "e_old",
            started_at=now - timedelta(days=10),
            ended_at=now - timedelta(days=10),
        )
        recent = _make_episode(
            "e_new",
            started_at=now - timedelta(days=1),
            ended_at=now - timedelta(days=1),
        )
        result = consolidator.consolidate(episodes=[old, recent])
        assert result.episodes_flagged == ("e_old",)

    def test_stale_procedure_flagged_by_ttl(self):
        now = datetime(2026, 1, 10, 12, 0, 0)
        consolidator = Consolidator(
            policy=MemoryDecayPolicy(procedure_ttl_days=5),
            now=now,
        )
        procedures = [
            _make_procedure(
                "p_old",
                created_at=now - timedelta(days=30),
                last_used_at=now - timedelta(days=30),
            ),
            _make_procedure(
                "p_new",
                created_at=now - timedelta(days=1),
                last_used_at=now - timedelta(days=1),
            ),
        ]
        result = consolidator.consolidate(procedures=procedures)
        assert result.procedures_flagged == ("p_old",)

    def test_disabled_policy_no_flags(self):
        consolidator = Consolidator(
            policy=MemoryDecayPolicy(enabled=False, min_importance=0.9)
        )
        episode = _make_episode("e1", importance=0.1)
        result = consolidator.consolidate(episodes=[episode])
        assert result.ok
        assert result.episodes_flagged == ()
        assert result.records == ()


class TestRecords:
    def test_records_are_pending(self):
        consolidator = Consolidator(
            policy=MemoryDecayPolicy(min_importance=0.5)
        )
        episode = _make_episode("e1", importance=0.1)
        result = consolidator.consolidate(episodes=[episode])
        assert len(result.records) == 1
        record = result.records[0]
        assert record.target_type == "episode"
        assert record.target_ids == ("e1",)
        assert record.operation == "forget"
        from atlas.longterm.models import ConsolidationStatus

        assert record.status == ConsolidationStatus.PENDING


class TestNoneInputs:
    def test_none_episodes_are_empty(self):
        consolidator = Consolidator()
        result = consolidator.consolidate(episodes=None)
        assert result.ok
        assert result.episodes_kept == ()
        assert result.episodes_flagged == ()

    def test_none_procedures_are_empty(self):
        consolidator = Consolidator()
        result = consolidator.consolidate(procedures=None)
        assert result.ok
        assert result.procedures_kept == ()
        assert result.procedures_flagged == ()


class TestDefaultRetentionPolicy:
    def test_default_policy_flags_100_day_inactive_episode(self):
        now = datetime(2026, 5, 10, 12, 0, 0)
        consolidator = Consolidator(now=now)
        stale = _make_episode(
            "e_old",
            started_at=now - timedelta(days=100),
            ended_at=now - timedelta(days=100),
        )
        result = consolidator.consolidate(episodes=[stale])
        assert result.episodes_flagged == ("e_old",)

    def test_default_policy_keeps_fresh_episode(self):
        now = datetime(2026, 5, 10, 12, 0, 0)
        consolidator = Consolidator(now=now)
        fresh = _make_episode(
            "e_new",
            started_at=now - timedelta(days=1),
            ended_at=now - timedelta(days=1),
        )
        result = consolidator.consolidate(episodes=[fresh])
        assert result.episodes_flagged == ()

    def test_default_policy_flags_200_day_unused_procedure(self):
        now = datetime(2026, 5, 10, 12, 0, 0)
        consolidator = Consolidator(now=now)
        stale = _make_procedure(
            "p_old",
            created_at=now - timedelta(days=200),
            last_used_at=now - timedelta(days=200),
        )
        result = consolidator.consolidate(procedures=[stale])
        assert result.procedures_flagged == ("p_old",)

    def test_default_policy_keeps_fresh_procedure(self):
        now = datetime(2026, 5, 10, 12, 0, 0)
        consolidator = Consolidator(now=now)
        fresh = _make_procedure(
            "p_new",
            created_at=now - timedelta(days=1),
            last_used_at=now - timedelta(days=1),
        )
        result = consolidator.consolidate(procedures=[fresh])
        assert result.procedures_flagged == ()


class TestFlagMetadata:
    def test_age_flags_carry_metadata(self):
        now = datetime(2026, 5, 10, 12, 0, 0)
        consolidator = Consolidator(now=now)
        stale = _make_episode(
            "e_old",
            started_at=now - timedelta(days=100),
            ended_at=now - timedelta(days=100),
        )
        result = consolidator.consolidate(episodes=[stale])
        forget_records = [
            r for r in result.records if r.operation == "forget"
        ]
        assert len(forget_records) == 1
        assert forget_records[0].metadata["flags"] == {
            "e_old": {
                "reason": "age",
                "days_inactive": 100,
                "importance": 0.5,
            }
        }

    def test_procedure_age_flags_carry_metadata(self):
        now = datetime(2026, 5, 10, 12, 0, 0)
        consolidator = Consolidator(now=now)
        stale = _make_procedure(
            "p_old",
            created_at=now - timedelta(days=200),
            last_used_at=now - timedelta(days=200),
        )
        result = consolidator.consolidate(procedures=[stale])
        forget_records = [
            r for r in result.records if r.operation == "forget"
        ]
        assert forget_records[0].metadata["flags"] == {
            "p_old": {
                "reason": "age",
                "days_inactive": 200,
                "importance": 0.8,
            }
        }

    def test_importance_flags_carry_metadata(self):
        consolidator = Consolidator(
            policy=MemoryDecayPolicy(min_importance=0.4),
            now=datetime(2026, 1, 10, 12, 0, 0),
        )
        low = _make_episode("e_low", importance=0.1)
        result = consolidator.consolidate(episodes=[low])
        forget_records = [
            r for r in result.records if r.operation == "forget"
        ]
        flags = forget_records[0].metadata["flags"]
        assert flags["e_low"]["reason"] == "importance"
        assert flags["e_low"]["importance"] == 0.1

    def test_stale_and_low_importance_reports_age_reason(self):
        now = datetime(2026, 5, 10, 12, 0, 0)
        consolidator = Consolidator(
            policy=MemoryDecayPolicy(min_importance=0.9),
            now=now,
        )
        episode = _make_episode(
            "e_sl",
            importance=0.05,
            started_at=now - timedelta(days=100),
            ended_at=now - timedelta(days=100),
        )
        result = consolidator.consolidate(episodes=[episode])
        flags = result.records[0].metadata["flags"]
        assert flags["e_sl"]["reason"] == "age"

    def test_multiple_flags_sorted_deterministically(self):
        now = datetime(2026, 5, 10, 12, 0, 0)
        consolidator = Consolidator(now=now)
        episodes = [
            _make_episode(
                "e_b",
                started_at=now - timedelta(days=100),
                ended_at=now - timedelta(days=100),
            ),
            _make_episode(
                "e_a",
                started_at=now - timedelta(days=120),
                ended_at=now - timedelta(days=120),
            ),
        ]
        result = consolidator.consolidate(episodes=episodes)
        assert result.episodes_flagged == ("e_a", "e_b")
        forget_records = [
            r for r in result.records if r.operation == "forget"
        ]
        flags = forget_records[0].metadata["flags"]
        assert list(flags.keys()) == ["e_a", "e_b"]
        assert flags["e_a"]["days_inactive"] == 120
        assert flags["e_b"]["days_inactive"] == 100

    def test_records_without_flags_have_no_flags_metadata(self):
        consolidator = Consolidator(now=datetime(2026, 5, 10, 12, 0, 0))
        low = _make_episode("e1", importance=0.9)
        high = _make_episode("e1", importance=0.2)
        result = consolidator.consolidate(episodes=[low, high])
        dedup_records = [
            r for r in result.records if r.operation == "dedup"
        ]
        assert dedup_records
        assert "flags" not in dedup_records[0].metadata

    def test_consolidation_does_not_mutate_repositories(self):
        from atlas.longterm.episode_repository import EpisodicRepository
        from atlas.longterm.procedure_repository import ProceduralRepository

        now = datetime(2026, 5, 10, 12, 0, 0)
        episode_repo = EpisodicRepository()
        procedure_repo = ProceduralRepository()
        episode_repo.store_episode(
            _make_episode(
                "e1",
                started_at=now - timedelta(days=100),
                ended_at=now - timedelta(days=100),
            )
        )
        procedure_repo.store_procedure(
            _make_procedure(
                "p1",
                created_at=now - timedelta(days=200),
                last_used_at=now - timedelta(days=200),
            )
        )

        consolidator = Consolidator(now=now)
        result = consolidator.consolidate(
            episodes=episode_repo.get_episodes(n=500),
            procedures=procedure_repo.get_procedures(n=500),
        )
        assert result.episodes_flagged == ("e1",)
        assert result.procedures_flagged == ("p1",)
        assert episode_repo.episode_count == 1
        assert procedure_repo.procedure_count == 1
        assert episode_repo.get_episode("e1") is not None
        assert procedure_repo.get_procedure("p1") is not None
