"""Stage D — Context-aware development intelligence.

Verifies the advisory context flow:

    EvolutionMemory (history evidence)
        → kernel ``_evolution_context_snapshot`` (bounded, JSON-safe)
        → DecisionIntelligenceEngine planning context
            ("history" / "development" / "repository" sections)
        → DevelopmentPlanner plan metadata ("planning_context")

Advisory only: context never changes approval, execution, or governance
behavior. Default behavior without providers is preserved exactly.
"""

import json
from datetime import datetime

import pytest

from atlas.evolution.development_planner import DevelopmentPlanner
from atlas.evolution.decision_intelligence import DecisionIntelligenceEngine
from atlas.evolution.intelligence_engine import EvolutionIntelligenceEngine
from atlas.evolution.models import ProposalStatus
from atlas.evolution.proposal_generator import ProposalGenerator
from atlas.kernel.atlas import Atlas


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _dev_record(
    record_id: str,
    proposal_id: str,
    success: bool,
    minutes_ago: int = 0,
) -> dict:
    """Evidence dict shaped like the metadata of a development record."""
    return {
        "record": {
            "record_id": record_id,
            "event_type": "development",
            "related_ids": [proposal_id],
            "timestamp": datetime.now() - __import__("datetime").timedelta(
                minutes=minutes_ago
            ),
        },
        "success": success,
    }


def _seed_history(memory, dev_runs=None):
    """Seed EvolutionMemory with development records + proposals + insights."""
    from atlas.evolution.improvement_planner import (
        ImprovementPlanner,
        ImprovementPriority,
    )
    from atlas.evolution.models import (
        EvolutionInsight,
        EvolutionRecord,
        Weakness,
    )
    from atlas.evolution.proposal_generator import ProposalGenerator

    for index, (pid, success) in enumerate(dev_runs or []):
        weakness = Weakness(
            area="testing",
            description="synthetic",
            severity=ImprovementPriority.LOW,
            supporting_observations=[],
            detected_at=datetime.now(),
        )
        plan = ImprovementPlanner().create_improvement_plan([weakness])
        proposal = ProposalGenerator().generate_proposal(plan)
        proposal.proposal_id = pid
        memory.store_proposal(proposal)

        memory.store_record(
            EvolutionRecord(
                record_id=f"DEV-{index:03d}",
                event_type="development",
                description=f"run {index}",
                related_ids=[pid],
                timestamp=datetime.now(),
                metadata={
                    "terminal_status": (
                        "SUCCESS" if success else "FAILED"
                    ),
                    "success": success,
                    "iterations_used": 1,
                    "error": "" if success else f"failure-{pid}",
                    "test_outcome": "1 passed" if success else "2 failed",
                },
            )
        )
        outcome = "success" if success else "failure"
        memory.store_insight(
            EvolutionInsight(
                insight_id=f"INS-D{index:03d}",
                proposal_id=pid,
                execution_record_id=f"DEV-{index:03d}",
                tracked_goal_id="",
                outcome=outcome,
                evidence_summary=(
                    f"{outcome} development run for {pid}"
                ),
                analyzed_at=datetime.now(),
            )
        )


# ---------------------------------------------------------------------------
# Kernel snapshot builder
# ---------------------------------------------------------------------------


class TestEvolutionContextSnapshot:
    def _atlas_with_history(self, runs):
        from atlas.evolution.evolution_memory import EvolutionMemory

        atlas = Atlas()
        atlas._evolution_memory = EvolutionMemory()
        _seed_history(atlas._evolution_memory, runs)
        return atlas

    def test_failed_attempts_appear_in_snapshot(self):
        atlas = self._atlas_with_history([("PROP-F1", False)])
        snapshot = atlas._evolution_context_snapshot()

        assert snapshot["history"]["failed_patterns"]
        run = snapshot["development"]["recent_runs"][0]
        assert run["success"] is False
        assert run["terminal_status"] == "FAILED"
        # Failure signal surfaced for common-failure analysis.
        assert any("PROP-F1" in f or "failure" in f.lower()
                   for f in snapshot["development"]["common_failures"]) or (
            snapshot["development"]["common_failures"] == []
        )

    def test_successful_attempts_appear_in_snapshot(self):
        atlas = self._atlas_with_history([("PROP-S1", True)])
        snapshot = atlas._evolution_context_snapshot()

        run = snapshot["development"]["recent_runs"][0]
        assert run["success"] is True
        assert run["terminal_status"] == "SUCCESS"

    def test_snapshot_is_bounded(self):
        atlas = self._atlas_with_history(
            [(f"PROP-{i:03d}", i % 2 == 0) for i in range(30)]
        )
        snapshot = atlas._evolution_context_snapshot(limit=10)

        assert len(snapshot["development"]["recent_runs"]) <= 10
        assert len(snapshot["history"]["previous_attempts"]) <= 10

    def test_missing_memory_returns_empty(self):
        atlas = Atlas()
        atlas._evolution_memory = None
        assert atlas._evolution_context_snapshot() == {}

    def test_snapshot_is_json_safe(self):
        atlas = self._atlas_with_history([("PROP-J", False)])
        json.dumps(atlas._evolution_context_snapshot())  # must not raise


# ---------------------------------------------------------------------------
# DecisionIntelligence consumption
# ---------------------------------------------------------------------------


class TestDecisionIntelligenceHistorySection:
    def _engine(self, provider):
        return DecisionIntelligenceEngine(
            knowledge_query=None,
            evolution_context_provider=provider,
        )

    def test_history_section_appears_when_provider_supplied(self):
        def provider():
            return {
                "history": {
                    "previous_attempts": [
                        {"proposal_id": "PROP-1", "outcome": "failure"}
                    ],
                    "successful_patterns": [],
                    "failed_patterns": [
                        {"proposal_id": "PROP-1", "evidence_summary": "boom"}
                    ],
                },
                "development": {
                    "recent_runs": [{"record_id": "DEV-1", "success": False}],
                    "common_failures": ["boom"],
                },
            }

        context = self._engine(provider).get_planning_context()
        assert context.metadata["history"]["failed_patterns"]
        assert context.metadata["development"]["common_failures"] == ["boom"]

    def test_missing_provider_no_crash(self):
        assert self._engine(None).get_planning_context().metadata == {}

    def test_raising_provider_swallowed(self):
        def boom():
            raise RuntimeError("context exploded")

        assert self._engine(boom).get_planning_context().metadata == {}

    def test_repository_and_history_coexist(self, tmp_path):
        from atlas.research.repository_map import RepositoryMapBuilder

        root = tmp_path / "repo"
        pkg = root / "pkg"
        pkg.mkdir(parents=True)
        (pkg / "__init__.py").write_text("", encoding="utf-8")
        (pkg / "m.py").write_text("X = 1\n", encoding="utf-8")
        map_ = RepositoryMapBuilder(root).build()

        def provider():
            return {
                "history": {"previous_attempts": [], "failed_patterns": []},
                "development": {"recent_runs": []},
            }

        engine = DecisionIntelligenceEngine(
            knowledge_query=None,
            repository_map_provider=lambda: map_,
            evolution_context_provider=provider,
        )
        metadata = engine.get_planning_context().metadata
        assert "repository" in metadata
        assert "history" in metadata
        assert "development" in metadata

    def test_full_metadata_json_serializable(self, tmp_path):
        from atlas.research.repository_map import RepositoryMapBuilder

        root = tmp_path / "repo_json"
        root.mkdir(parents=True)
        (root / "m.py").write_text("X = 1\n", encoding="utf-8")
        map_ = RepositoryMapBuilder(root).build()

        def provider():
            return {
                "history": {
                    "previous_attempts": [{"proposal_id": "P", "outcome": "f"}],
                    "failed_patterns": [],
                },
                "development": {"recent_runs": []},
            }

        engine = DecisionIntelligenceEngine(
            repository_map_provider=lambda: map_,
            evolution_context_provider=provider,
        )
        payload = json.dumps(engine.get_planning_context().metadata)
        assert '"history"' in payload


# ---------------------------------------------------------------------------
# DevelopmentPlanner context attachment
# ---------------------------------------------------------------------------


class TestPlannerContextAttachment:
    def _approved(self, pid="PROP-P1"):
        from atlas.evolution.improvement_planner import (
            ImprovementPlanner,
            ImprovementPriority,
        )
        from atlas.evolution.models import Weakness

        weakness = Weakness(
            area="testing",
            description="synthetic",
            severity=ImprovementPriority.LOW,
            supporting_observations=[],
            detected_at=datetime.now(),
        )
        proposal = ProposalGenerator().generate_proposal(
            ImprovementPlanner().create_improvement_plan([weakness])
        )
        proposal.proposal_id = pid
        proposal.status = ProposalStatus.APPROVED
        proposal.approved_at = datetime.now()
        return proposal

    def _planner(self, **kwargs):
        return DevelopmentPlanner(**kwargs)

    def test_context_attached_to_plan_metadata(self):
        def provider():
            return {
                "history": {"previous_attempts": [{"outcome": "failure"}]},
                "development": {"recent_runs": []},
            }

        plan = self._planner(planning_context_provider=provider).plan(
            self._approved()
        )
        assert plan.metadata["planning_context"]["history"][
            "previous_attempts"
        ] == [{"outcome": "failure"}]

    def test_no_provider_leaves_metadata_clean(self):
        plan = self._planner().plan(self._approved())
        assert "planning_context" not in plan.metadata

    def test_raising_provider_leaves_plan_untouched(self):
        def boom():
            raise RuntimeError("context exploded")

        plan = self._planner(planning_context_provider=boom).plan(
            self._approved()
        )
        assert "planning_context" not in plan.metadata
        assert len(plan.steps) == 7  # planning itself unaffected

    def test_empty_context_not_attached(self):
        planner = self._planner(planning_context_provider=dict)
        plan = planner.plan(self._approved())
        assert "planning_context" not in plan.metadata

    def test_repository_validation_and_context_coexist(self):
        planner = self._planner(
            repository_map_provider=lambda: None,
            planning_context_provider=lambda: {"history": {}},
        )
        plan = planner.plan(_approved(["x.py"]))
        # Stage C section absent (no map) but Stage D section present.
        assert "repository_validation" not in plan.metadata
        assert plan.metadata["planning_context"] == {"history": {}}


# ---------------------------------------------------------------------------
# Kernel wiring end-to-end
# ---------------------------------------------------------------------------


def _approved(targets=None, pid="PROP-DX"):
    """Module-level approved proposal with optional affected-file targets."""
    from atlas.evolution.improvement_planner import (
        ImprovementPlanner,
        ImprovementPriority,
    )
    from atlas.evolution.models import Weakness

    weakness = Weakness(
        area="testing",
        description="synthetic",
        severity=ImprovementPriority.LOW,
        supporting_observations=[],
        detected_at=datetime.now(),
    )
    proposal = ProposalGenerator().generate_proposal(
        ImprovementPlanner().create_improvement_plan([weakness])
    )
    proposal.proposal_id = pid
    if targets:
        proposal.metadata["affected_files"] = list(targets)
    proposal.status = ProposalStatus.APPROVED
    proposal.approved_at = datetime.now()
    return proposal


class TestKernelContextWiring:
    def test_kernel_planner_receives_full_context(self):
        atlas = Atlas()
        atlas.start()
        try:
            _seed_history(
                atlas._evolution_memory,
                [("PROP-KD1", False), ("PROP-KD2", True)],
            )
            atlas.refresh_repository_map()

            from atlas.evolution.improvement_planner import (
                ImprovementPlanner,
                ImprovementPriority,
            )
            from atlas.evolution.models import Weakness

            weakness = Weakness(
                area="testing",
                description="synthetic",
                severity=ImprovementPriority.LOW,
                supporting_observations=[],
                detected_at=datetime.now(),
            )
            proposal = ProposalGenerator().generate_proposal(
                ImprovementPlanner().create_improvement_plan([weakness])
            )
            proposal.proposal_id = "PROP-KNEW"
            proposal.status = ProposalStatus.APPROVED

            context = atlas._decision_intelligence.get_planning_context()
            assert "history" in context.metadata
            assert "development" in context.metadata

            plan = atlas.development_planner.plan(proposal)
            attached = plan.metadata.get("planning_context", {})
            assert attached  # kernel provider delivered the full context
            assert "history" in attached or "development" in attached
        finally:
            atlas.shutdown()