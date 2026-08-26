"""Stage B — Evolution intelligence consumption of development records.

Closes the feedback loop: ``event_type="development"`` records (bridged
from SelfDevelopmentLoop runs) are now first-class learning inputs for
``EvolutionIntelligenceEngine``, analyzed by the SAME deterministic logic
as ``event_type="execution"`` records (the ``metadata.success`` contract).
"""

from datetime import datetime, timedelta

import pytest

from atlas.evolution.evolution_memory import EvolutionMemory
from atlas.evolution.improvement_planner import (
    ImprovementPlanner,
    ImprovementPriority,
)
from atlas.evolution.intelligence_engine import EvolutionIntelligenceEngine
from atlas.evolution.models import EvolutionRecord


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _record(
    record_id: str,
    event_type: str,
    proposal_id: str,
    success: bool,
    minutes_ago: int = 0,
    extra: dict | None = None,
) -> EvolutionRecord:
    metadata = {
        "success": success,
        "status": "IMPLEMENTED" if success else "APPROVED",
        "error": "" if success else "synthetic failure",
        "tracked_goal_id": "",
    }
    if extra:
        metadata.update(extra)
    return EvolutionRecord(
        record_id=record_id,
        event_type=event_type,
        description=f"{event_type} record for {proposal_id}",
        related_ids=[proposal_id],
        timestamp=datetime.now() - timedelta(minutes=minutes_ago),
        metadata=metadata,
    )


def _make_proposal(memory: EvolutionMemory, proposal_id: str) -> None:
    """Store a minimal DRAFT proposal so analyze_all() can discover it."""
    from atlas.evolution.models import Weakness
    from atlas.evolution.proposal_generator import ProposalGenerator

    weakness = Weakness(
        area="testing",
        description="synthetic",
        severity=ImprovementPriority.LOW,
        supporting_observations=[],
        detected_at=datetime.now(),
    )
    plan = ImprovementPlanner().create_improvement_plan([weakness])
    proposal = ProposalGenerator().generate_proposal(plan)
    proposal.proposal_id = proposal_id
    memory.store_proposal(proposal)


def _memory_with(
    *records: EvolutionRecord,
) -> tuple[EvolutionMemory, EvolutionIntelligenceEngine]:
    memory = EvolutionMemory()
    for record in records:
        memory.store_record(record)
        for related_id in record.related_ids:
            _make_proposal(memory, related_id)
    engine = EvolutionIntelligenceEngine(
        evolution_memory=memory,
        insight_scorer=None,
    )
    return memory, engine


class TestExecutionRecordsUnchanged:
    def test_execution_record_still_produces_insight(self):
        memory, engine = _memory_with(
            _record("EVR-1", "execution", "PROP-E1", success=True)
        )
        insights = engine.analyze_all()
        assert len(insights) == 1
        assert insights[0].proposal_id == "PROP-E1"
        assert insights[0].outcome in ("success", "partial", "inconclusive")
        assert insights[0].execution_record_id == "EVR-1"


class TestDevelopmentRecordConsumption:
    def test_successful_development_record_produces_insight(self):
        memory, engine = _memory_with(
            _record(
                "DEV-1",
                "development",
                "PROP-D1",
                success=True,
                extra={
                    "terminal_status": "SUCCESS",
                    "verification_passed": True,
                    "iterations_used": 2,
                },
            )
        )

        insights = engine.analyze_all()

        assert len(insights) == 1
        insight = insights[0]
        assert insight.proposal_id == "PROP-D1"
        assert insight.execution_record_id == "DEV-1"
        assert insight.outcome != "failure"

    def test_failed_development_record_produces_failure_insight(self):
        memory, engine = _memory_with(
            _record(
                "DEV-2",
                "development",
                "PROP-D2",
                success=False,
                extra={
                    "terminal_status": "FAILED",
                    "rollback_occurred": True,
                    "test_outcome": "2 failed",
                },
            )
        )

        insights = engine.analyze_all()

        assert len(insights) == 1
        insight = insights[0]
        # Deterministic failure classification from the record's own
        # metadata — a failed development run can never score as success.
        assert insight.outcome == "failure"
        assert insight.effectiveness_score == 0.0
        assert insight.confidence == 1.0

    def test_development_record_without_success_metadata_defaults_safely(self):
        """Hostile/malformed metadata must not fabricate a confident outcome."""
        from atlas.evolution.models import EvolutionRecord as _Rec

        record = _Rec(
            record_id="DEV-3",
            event_type="development",
            description="malformed dev record",
            related_ids=["PROP-D3"],
            metadata={"terminal_status": "SUCCESS"},  # no success flag
        )

        memory = EvolutionMemory()
        _make_proposal(memory, "PROP-D3")
        memory.store_record(record)
        engine = EvolutionIntelligenceEngine(evolution_memory=memory)

        insights = engine.analyze_all()
        assert len(insights) == 1
        # metadata.get("success", True) defaults to True; the scorer is
        # unavailable so the outcome is inconclusive rather than fabricated.
        assert insights[0].outcome in ("inconclusive",)


class TestMixedAndEdgeHistories:
    def test_mixed_history_both_kinds_consumed(self):
        memory, engine = _memory_with(
            _record("EVR-M1", "execution", "PROP-M1", success=True),
            _record("DEV-M2", "development", "PROP-M2", success=False),
        )

        insights = engine.analyze_all()

        by_proposal = {i.proposal_id: i for i in insights}
        assert set(by_proposal) == {"PROP-M1", "PROP-M2"}
        assert by_proposal["PROP-M1"].outcome != "failure"
        assert by_proposal["PROP-M2"].outcome == "failure"

    def test_execution_record_wins_when_both_exist_for_proposal(self):
        """Backward compatibility: execution priority over development."""
        memory, engine = _memory_with(
            _record("DEV-BOTH", "development", "PROP-BOTH", success=False),
            _record("EVR-BOTH", "execution", "PROP-BOTH", success=True),
        )

        insights = engine.analyze_all()

        assert len(insights) == 1
        # The execution record was analyzed, not the failed dev record.
        assert insights[0].execution_record_id == "EVR-BOTH"

    def test_empty_history_no_crash(self):
        _, engine = _memory_with()
        assert engine.analyze_all() == []

    def test_unknown_event_types_ignored_safely(self):
        memory, engine = _memory_with(
            _record("OBS-1", "observation", "PROP-U1", success=True),
            _record("REF-1", "refusal", "PROP-U2", success=False),
            _record("REJ-1", "rejection", "PROP-U3", success=False),
        )
        assert engine.analyze_all() == []


class TestAnalyzedOnceSemantics:
    def test_repeated_analyze_does_not_duplicate_insights(self):
        memory, engine = _memory_with(
            _record("DEV-R1", "development", "PROP-R1", success=True),
        )

        first = engine.analyze_all()
        second = engine.analyze_all()

        assert len(first) == 1
        assert second == []