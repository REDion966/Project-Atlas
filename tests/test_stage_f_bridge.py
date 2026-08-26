"""Stage F — Research → Development Intelligence bridge.

Verifies the bounded evidence flow:

    F8 AcquisitionResult
        → kernel evidence cache (summarize_acquisition)
        → DecisionIntelligence planning context ("research" section)
        → scheduler-created ImprovementPlan.metadata["research"]
        → EvolutionProposal.metadata["planning_evidence"]
        → durable EvolutionMemory persistence + insight feedback

Safety invariants: the scheduler never triggers acquisition; providers
are cache-only and fail-soft; legacy behavior without providers is
byte-identical.
"""

import json
from datetime import datetime

import pytest

from atlas.evolution.evolution_memory import EvolutionMemory
from atlas.evolution.improvement_planner import (
    ImprovementPlanner,
    ImprovementPriority,
)
from atlas.evolution.intelligence_engine import EvolutionIntelligenceEngine
from atlas.evolution.models import Weakness
from atlas.evolution.proposal_generator import ProposalGenerator
from atlas.kernel.atlas import Atlas
from atlas.research.acquisition import AcquisitionResult
from atlas.research.evidence_summary import summarize_acquisition
from atlas.storage.evolution_storage import SQLiteEvolutionStorage


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _acquisition(**overrides):
    base = dict(
        acquisition_id="ACQ-F1",
        decision="research",
        status="ok",
        query_id="Q-F1",
        question="what breaks if ranking changes?",
        findings="ranking aggregates recency and confidence",
        sources=("code://atlas/memory/ranking.py",),
        confidence=0.9,
        claim_count=3,
        verification_count=2,
    )
    base.update(overrides)
    return AcquisitionResult(**base)


def _weaknesses(area="testing"):
    return [
        Weakness(
            area=area,
            description="synthetic weakness",
            severity=ImprovementPriority.MEDIUM,
            supporting_observations=[],
            detected_at=datetime.now(),
        )
    ]


def _enriched_proposal(provider=None):
    planner = ImprovementPlanner()
    plan = planner.create_improvement_plan(
        _weaknesses(),
        research_evidence=provider() if provider else None,
    )
    return ProposalGenerator().generate_proposal(plan)


class TestProposalEnrichment:
    def test_evidence_flows_plan_to_proposal(self):
        summary = summarize_acquisition(_acquisition())
        proposal = _enriched_proposal(lambda: summary)

        evidence = proposal.metadata["planning_evidence"]
        assert evidence["research"]["question"] == (
            "what breaks if ranking changes?"
        )
        assert evidence["research"]["confidence"] == pytest.approx(0.9)

    def test_no_evidence_keeps_metadata_empty(self):
        proposal = _enriched_proposal()
        assert proposal.metadata == {}

    def test_json_safe_enrichment(self):
        summary = summarize_acquisition(_acquisition())
        payload = json.dumps(summary)  # must not raise
        assert "ranking" in payload


class TestSchedulerEvidenceProvider:
    def _scheduler(self, memory, evidence_holder):
        from atlas.evolution.approval_manager import ApprovalManager
        from atlas.evolution.scheduler import EvolutionScheduler
        from atlas.evolution.self_observation import SelfObservationEngine

        return EvolutionScheduler(
            observation_engine=SelfObservationEngine(),
            improvement_planner=ImprovementPlanner(),
            proposal_generator=ProposalGenerator(),
            approval_manager=ApprovalManager(),
            evolution_memory=memory,
            tick_interval=1,
            min_observations=1,
            research_evidence_provider=(
                lambda: evidence_holder.get("evidence")
            ),
        )

    @staticmethod
    def _seed_observations(scheduler, count=6):
        """Produce planner-triggering observations (proven F1 pattern)."""
        from atlas.evolution.runtime_observations import (
            collect_runtime_observations,
        )
        from tests.test_postcore_f1_runtime_observations import (
            StubMetrics,
            make_state,
        )

        engine = scheduler._observation_engine
        for _ in range(count):
            collect_runtime_observations(
                engine,
                make_state(reasoning=True, tool=True, memory=True),
                StubMetrics(),
                1.0,
            )

    def test_evidence_lands_on_scheduler_proposal(self):
        memory = EvolutionMemory()
        holder = {
            "memory": memory,
            "evidence": summarize_acquisition(_acquisition()),
        }
        scheduler = self._scheduler(memory, holder)
        self._seed_observations(scheduler)

        result = scheduler.tick()

        assert result.proposals_generated == 1
        proposal = memory.get_all_proposals()[0]
        evidence = proposal.metadata["planning_evidence"]["research"]
        assert evidence["acquisition_id"] == "ACQ-F1"

    def test_no_provider_legacy_behavior(self):
        from atlas.evolution.approval_manager import ApprovalManager
        from atlas.evolution.scheduler import EvolutionScheduler
        from atlas.evolution.self_observation import SelfObservationEngine

        memory = EvolutionMemory()
        scheduler = EvolutionScheduler(
            observation_engine=SelfObservationEngine(),
            improvement_planner=ImprovementPlanner(),
            proposal_generator=ProposalGenerator(),
            approval_manager=ApprovalManager(),
            evolution_memory=memory,
            tick_interval=1,
            min_observations=1,
        )
        self._seed_observations(scheduler)

        result = scheduler.tick()
        assert result.proposals_generated == 1
        proposal = memory.get_all_proposals()[0]
        assert "planning_evidence" not in proposal.metadata

    def test_raising_provider_swallowed(self):
        from atlas.evolution.approval_manager import ApprovalManager
        from atlas.evolution.scheduler import EvolutionScheduler
        from atlas.evolution.self_observation import SelfObservationEngine

        def boom():
            raise RuntimeError("cache exploded")

        memory = EvolutionMemory()
        scheduler = EvolutionScheduler(
            observation_engine=SelfObservationEngine(),
            improvement_planner=ImprovementPlanner(),
            proposal_generator=ProposalGenerator(),
            approval_manager=ApprovalManager(),
            evolution_memory=memory,
            tick_interval=1,
            min_observations=1,
            research_evidence_provider=boom,
        )
        self._seed_observations(scheduler)

        result = scheduler.tick()  # must not raise
        assert result.proposals_generated == 1
        proposal = memory.get_all_proposals()[0]
        # Evidence absent, but the plan itself is unaffected.
        assert "planning_evidence" not in proposal.metadata


# ---------------------------------------------------------------------------
# F3 — kernel cache + context propagation
# ---------------------------------------------------------------------------


class _FakeAcquisitionService:
    def __init__(self, result):
        self.result = result
        self.calls = 0

    def acquire(self, **kwargs):
        self.calls += 1
        return self.result


class TestKernelResearchCache:
    def test_acquisition_populates_kernel_cache_and_context(self):
        atlas = Atlas()
        atlas.start()
        try:
            atlas._acquisition_service = _FakeAcquisitionService(
                _acquisition()
            )

            result = atlas.run_information_acquisition(question="q")
            assert result.status == "ok"
            assert service_calls(atlas) == 1

            cached = atlas._last_research_evidence
            assert cached is not None
            assert cached["question"] == "what breaks if ranking changes?"

            # Planning context carries the research section (Stage D pipe).
            context = atlas._decision_intelligence.get_planning_context()
            assert context.metadata["research"]["claim_count"] == 3
        finally:
            atlas.shutdown()

    def test_context_without_acquisition_has_no_research_section(self):
        atlas = Atlas()
        atlas.start()
        try:
            atlas.refresh_repository_map()
            context = atlas._decision_intelligence.get_planning_context()
            assert "research" not in context.metadata
        finally:
            atlas.shutdown()


def service_calls(atlas):
    return atlas._acquisition_service.calls


# ---------------------------------------------------------------------------
# F4 — feedback closure: durability + intelligence consumption
# ---------------------------------------------------------------------------


class TestFeedbackClosure:
    def test_enriched_metadata_survives_persistence(self, tmp_path):
        storage = SQLiteEvolutionStorage(db_path=tmp_path / "stageF.db")
        storage.initialize()
        try:
            memory = EvolutionMemory(storage=storage)
            planner = ImprovementPlanner()
            plan = planner.create_improvement_plan(
                _weaknesses(),
                research_evidence=summarize_acquisition(_acquisition()),
            )
            proposal = ProposalGenerator().generate_proposal(plan)
            proposal.proposal_id = "PROP-F-DURABLE"
            memory.store_proposal(proposal)

            fresh = EvolutionMemory(storage=storage)
            fresh.restore()
            restored = fresh.get_proposal("PROP-F-DURABLE")
            evidence = restored.metadata["planning_evidence"]["research"]
            assert evidence["acquisition_id"] == "ACQ-F1"
        finally:
            storage.close()

    def test_intelligence_consumes_outcomes_of_enriched_proposals(self):
        memory = EvolutionMemory()
        planner = ImprovementPlanner()
        plan = planner.create_improvement_plan(
            _weaknesses(),
            research_evidence=summarize_acquisition(_acquisition()),
        )
        proposal = ProposalGenerator().generate_proposal(plan)
        proposal.proposal_id = "PROP-F-ENRICHED"
        memory.store_proposal(proposal)

        from atlas.evolution.models import EvolutionRecord

        memory.store_record(
            EvolutionRecord(
                record_id="DEV-ENRICHED",
                event_type="development",
                description="failed sandbox run",
                related_ids=["PROP-F-ENRICHED"],
                timestamp=datetime.now(),
                metadata={
                    "terminal_status": "FAILED",
                    "success": False,
                    "error": "tests failed",
                },
            )
        )

        engine = EvolutionIntelligenceEngine(
            evolution_memory=memory,
            insight_scorer=None,
        )
        insights = engine.analyze_all()
        assert len(insights) == 1
        assert insights[0].outcome == "failure"
        assert insights[0].proposal_id == "PROP-F-ENRICHED"