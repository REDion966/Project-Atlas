"""Stage G — decision-quality attachment through DevelopmentPlanner.

Verifies that the Stage G scoring layer synthesizes the evidence already
collected by the Stage C/D seams (repository validation + kernel planning
context) into bounded ``decision_quality`` metadata on produced plans,
and that proposals inherit it via the existing metadata copy channel.
"""

from datetime import datetime

import pytest

from atlas.evolution.decision_quality import NEUTRAL_SCORE
from atlas.evolution.development_planner import DevelopmentPlanner

from atlas.evolution.improvement_planner import (
    ImprovementPlanner,
    ImprovementPriority,
)
from atlas.evolution.models import ProposalStatus, Weakness
from atlas.evolution.proposal_generator import ProposalGenerator
from atlas.research.repository_map import RepositoryMapBuilder


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _approved(targets=None, pid="PROP-G1"):
    weakness = Weakness(
        area="testing",
        description="synthetic",
        severity=ImprovementPriority.MEDIUM,
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


def _dependent_repo_map(tmp_path):
    """Tree where pkg.user depends on pkg.core (one impact edge)."""
    root = tmp_path / "repo"
    pkg = root / "pkg"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "core.py").write_text("VALUE = 1\n", encoding="utf-8")
    (pkg / "user.py").write_text(
        "from pkg.core import VALUE\nUSE = VALUE\n", encoding="utf-8"
    )
    return RepositoryMapBuilder(root).build()


def _context(attempts=None, confidence=None):
    payload = {
        "history": {"previous_attempts": list(attempts or [])},
        "development": {},
        "research": {},
    }
    if confidence is not None:
        payload["overall_confidence"] = confidence
    return payload


class TestDecisionQualityAttachment:
    def test_full_context_scores(self, tmp_path):
        map_ = _dependent_repo_map(tmp_path)
        context = {
            "overall_confidence": 0.8,
            "history": {
                "previous_attempts": [{"outcome": "success"}],
                "failed_patterns": [],
            },
            "research": {"confidence": 0.9, "claim_count": 4},
            "development": {},
        }
        planner = DevelopmentPlanner(
            repository_map_provider=lambda: map_,
            planning_context_provider=lambda: context,
        )
        plan = planner.plan(_approved(["pkg/core.py"], pid="PROP-Q1"))

        quality = plan.metadata["decision_quality"]
        assert quality["confidence_score"] == pytest.approx(0.8)
        assert quality["historical_evidence_score"] == pytest.approx(1.0)
        assert quality["impact_score"] > 0.0
        assert quality["research_evidence_strength"] == pytest.approx(0.9)
        assert 0.0 <= quality["final_priority_score"] <= 1.0

    def test_neutral_quality_without_any_context(self):
        planner = DevelopmentPlanner()
        plan = planner.plan(_approved(pid="PROP-NEUTRAL"))

        quality = plan.metadata["decision_quality"]
        assert quality["confidence_score"] == pytest.approx(NEUTRAL_SCORE)
        assert quality["historical_evidence_score"] == pytest.approx(
            NEUTRAL_SCORE
        )
        assert quality["risk_score"] == 0.0

    def test_repository_impact_feeds_impact_score(self, tmp_path):
        map_ = _dependent_repo_map(tmp_path)
        planner = DevelopmentPlanner(
            repository_map_provider=lambda: map_,
            planning_context_provider=lambda: {},
        )
        plan = planner.plan(_approved(["pkg/core.py"], pid="PROP-IMPACT"))

        validation = plan.metadata["repository_validation"]
        assert validation["dependency_count"] >= 1
        quality = plan.metadata["decision_quality"]
        assert (
            quality["impact_score"]
            == validation["dependency_count"] * 0.25
        )

    def test_unknown_targets_raise_risk_score(self, tmp_path):
        map_ = _dependent_repo_map(tmp_path)
        planner = DevelopmentPlanner(
            repository_map_provider=lambda: map_,
            planning_context_provider=lambda: {"overall_confidence": 0.5},
        )
        plan = planner.plan(_approved(["ghost/unknown.py"], pid="PROP-RISK"))

        quality = plan.metadata["decision_quality"]
        assert quality["risk_score"] > 0.0


class TestHistoryInfluenceAndSafety:
    def test_failed_history_lowers_final_priority(self, tmp_path):
        map_ = _dependent_repo_map(tmp_path)
        failing_context = {
            "overall_confidence": 0.5,
            "history": {
                "previous_attempts": [
                    {"outcome": "failure"} for _ in range(4)
                ]
            },
        }
        success_context = {
            "overall_confidence": 0.5,
            "history": {
                "previous_attempts": [
                    {"outcome": "success"} for _ in range(4)
                ]
            },
        }

        fail_plan = DevelopmentPlanner(
            repository_map_provider=lambda: map_,
            planning_context_provider=lambda: failing_context,
        ).plan(_approved(["pkg/core.py"], pid="PROP-FAIL"))
        ok_plan = DevelopmentPlanner(
            repository_map_provider=lambda: map_,
            planning_context_provider=lambda: success_context,
        ).plan(_approved(["pkg/core.py"], pid="PROP-OK"))

        fail_q = fail_plan.metadata["decision_quality"]
        ok_q = ok_plan.metadata["decision_quality"]
        assert (
            ok_q["final_priority_score"] > fail_q["final_priority_score"]
        )

    def test_deterministic_across_repeated_plans(self, tmp_path):
        map_ = _dependent_repo_map(tmp_path)
        context = {"overall_confidence": 0.75, "history": {}}

        plans = [
            DevelopmentPlanner(
                repository_map_provider=lambda: map_,
                planning_context_provider=lambda: context,
            ).plan(_approved(["pkg/core.py"]))
            for _ in range(2)
        ]
        first = plans[0].metadata["decision_quality"]
        second = plans[1].metadata["decision_quality"]
        assert first == second

    def test_malformed_context_fail_soft(self):
        planner = DevelopmentPlanner(
            planning_context_provider=lambda: {
                "history": "not-a-dict",
                "research": None,
                "overall_confidence": "oops",
            },
        )
        plan = planner.plan(_approved(pid="PROP-MALFORMED"))

        # Fail-soft: the advisory section may be absent entirely, but if
        # present every value is bounded.
        quality = plan.metadata.get("decision_quality")
        if quality is not None:
            for value in quality.values():
                assert 0.0 <= value <= 1.0
        assert len(plan.steps) == 7  # planning itself unaffected

    def test_metadata_is_json_safe(self, tmp_path):
        import json

        map_ = _dependent_repo_map(tmp_path)
        planner = DevelopmentPlanner(
            repository_map_provider=lambda: map_,
            planning_context_provider=lambda: {
                "overall_confidence": 0.6,
                "history": {"previous_attempts": [{"outcome": "success"}]},
                "research": {"confidence": 0.7, "claim_count": 2},
            },
        )
        plan = planner.plan(_approved(["pkg/core.py"], pid="PROP-JSON"))
        payload = json.dumps(plan.metadata["decision_quality"])
        assert '"final_priority_score"' in payload

    def test_proposal_inherits_quality_via_plan_copy(self, tmp_path):
        """The proposal object passed to plan() carries the quality scores
        in its own metadata after planning (mirrored by the planner)."""
        map_ = _dependent_repo_map(tmp_path)
        proposal = _approved(["pkg/core.py"], pid="PROP-INHERIT")
        planner = DevelopmentPlanner(
            repository_map_provider=lambda: map_,
            planning_context_provider=lambda: {
                "overall_confidence": 0.6,
                "history": {"previous_attempts": []},
                "research": {},
            },
        )
        plan = planner.plan(proposal)

        assert "decision_quality" in plan.metadata
        assert (
            proposal.metadata.get("decision_quality")
            == plan.metadata["decision_quality"]
        )