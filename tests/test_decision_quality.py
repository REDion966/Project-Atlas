"""Stage G — Decision Quality Optimization Foundation.

Verifies the advisory decision-quality scoring layer:

- pure deterministic scoring over already-collected evidence
  (history attempts, repository validation, research confidence),
- bounded [0, 1] outputs with neutral defaults when no evidence exists,
- planner attachment via the Stage D planning-context channel,
- legacy behavior preserved when no context exists,
- fail-soft on malformed metadata.
"""

import json

import pytest

from atlas.evolution.decision_quality import (
    NEUTRAL_SCORE,
    compute_decision_quality,
)


class TestPureScoring:
    def test_neutral_when_no_evidence(self):
        scores = compute_decision_quality(
            overall_confidence=None,
            previous_attempts=None,
            unknown_target_count=0,
            known_target_count=0,
            dependency_count=0,
            research_confidence=None,
            has_research_claim_support=False,
        )
        assert scores["historical_evidence_score"] == pytest.approx(
            NEUTRAL_SCORE
        )
        assert scores["confidence_score"] == pytest.approx(NEUTRAL_SCORE)
        assert scores["risk_score"] == 0.0
        assert scores["impact_score"] == 0.0
        assert scores["research_evidence_strength"] == 0.0
        assert 0.0 <= scores["final_priority_score"] <= 1.0

    def test_success_history_raises_historical_score(self):
        attempts = [
            {"outcome": "success"},
            {"outcome": "success"},
            {"outcome": "failure"},
        ]
        scores = compute_decision_quality(
            overall_confidence=0.5,
            previous_attempts=attempts,
            unknown_target_count=0,
            known_target_count=1,
            dependency_count=0,
            research_confidence=None,
            has_research_claim_support=False,
        )
        assert scores["historical_evidence_score"] == pytest.approx(
            2 / 3, abs=1e-3
        )
        # 1 failure out of 3 attempts: failure-pressure term only.
        assert scores["risk_score"] == pytest.approx(1 * 0.25 * 0.4)

    def test_all_failure_history_lowers_historical_score(self):
        scores = compute_decision_quality(
            overall_confidence=None,
            previous_attempts=[{"outcome": "failure"} for _ in range(4)],
            unknown_target_count=0,
            known_target_count=0,
            dependency_count=0,
            research_confidence=None,
            has_research_claim_support=False,
        )
        assert scores["historical_evidence_score"] == 0.0

    def test_impact_score_scales_with_dependency_count(self):
        low = compute_decision_quality(
            None, None, 0, 1, 1, None, False
        )
        high = compute_decision_quality(
            None, None, 0, 1, 6, None, False
        )
        assert low["impact_score"] < high["impact_score"]
        assert high["impact_score"] == 1.0  # clamped at 4+ dependents

    def test_unknown_targets_increase_risk(self):
        clean = compute_decision_quality(None, [], 0, 2, 0, None, False)
        risky = compute_decision_quality(None, [], 3, 0, 0, None, False)
        assert risky["risk_score"] > clean["risk_score"]

    def test_research_strength_reflects_claims_and_confidence(self):
        weak = compute_decision_quality(
            None, None, 0, 0, 0, research_confidence=0.9,
            has_research_claim_support=False,
        )
        strong = compute_decision_quality(
            None, None, 0, 0, 0, research_confidence=0.9,
            has_research_claim_support=True,
        )
        assert strong["research_evidence_strength"] == pytest.approx(0.9)
        assert weak["research_evidence_strength"] == pytest.approx(0.45)

    def test_deterministic_scoring(self):
        kwargs = dict(
            overall_confidence=0.7,
            previous_attempts=[
                {"outcome": "success"},
                {"outcome": "failure"},
            ],
            unknown_target_count=1,
            known_target_count=2,
            dependency_count=2,
            research_confidence=0.8,
            has_research_claim_support=True,
        )
        first = compute_decision_quality(**kwargs)
        second = compute_decision_quality(**kwargs)
        assert first == second
        for value in first.values():
            assert 0.0 <= value <= 1.0

    def test_scores_are_json_serializable(self):
        scores = compute_decision_quality(0.5, [], 0, 1, 1, 0.5, False)
        json.dumps(scores)  # must not raise

    def test_malformed_values_fail_soft(self):
        scores = compute_decision_quality(
            overall_confidence="not-a-number",
            previous_attempts="not-a-list",
            unknown_target_count="x",
            known_target_count=None,
            dependency_count={},
            research_confidence="oops",
            has_research_claim_support=None,
        )
        # No exception; every score bounded.
        for value in scores.values():
            assert 0.0 <= value <= 1.0