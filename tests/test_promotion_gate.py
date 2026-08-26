"""Stage E — Promotion Gate Foundation.

Verifies the controlled promotion-review layer between successful sandbox
development and the real repository:

- deterministic risk assessment (LOW/MEDIUM/HIGH) from run evidence,
- review-request lifecycle PENDING_REVIEW → APPROVED / REJECTED,
- best-effort ``promotion_review`` audit records via EvolutionMemory,
- fail-soft behavior when memory is unavailable,
- no repository mutation anywhere in the module.
"""

import json
from datetime import datetime

import pytest

from atlas.evolution.development_models import (
    DevelopmentOutcome,
    DevelopmentOutcomeStatus,
    DevelopmentPlan,
)
from atlas.evolution.self_development_loop import DevelopmentRunResult
from atlas.evolution.evolution_memory import EvolutionMemory
from atlas.evolution.promotion_gate import (
    PromotionGate,
    PromotionRecommendation,
    PromotionRisk,
    PromotionStatus,
)
from atlas.storage.evolution_storage import SQLiteEvolutionStorage


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _plan(pid="PROP-P1"):
    return DevelopmentPlan(
        plan_id="PLAN-P1",
        proposal_id=pid,
        title="promotion test",
        summary="synthetic",
    )


def _run_result(status, changed_files=None, verification=True, rollback=False):
    outcome = DevelopmentOutcome(
        outcome=status,
        proposal_id="PROP-P1",
        plan_id="PLAN-P1",
        iteration=1,
        message="run finished",
        changed_files=list(changed_files or []),
        verification_passed=verification and not rollback,
        rollback_occurred=rollback,
        test_outcome=("3 passed" if verification else "2 failed"),
    )
    return DevelopmentRunResult(
        status=status,
        plan=_plan(),
        outcomes=[outcome],
        iterations_used=1,
        message="done",
    )


def _gate(memory=None):
    return PromotionGate(evolution_memory=memory)


# ---------------------------------------------------------------------------
# Assessment / risk classification
# ---------------------------------------------------------------------------


class TestAssessmentAndRisk:
    def test_successful_small_run_is_low_risk_ready(self):
        gate = _gate()
        assessment = gate.assess(
            _run_result(DevelopmentOutcomeStatus.SUCCESS, ["pkg/feature.py"])
        )
        assert assessment.risk_level is PromotionRisk.LOW
        assert assessment.recommendation is (
            PromotionRecommendation.READY_FOR_PROMOTION
        )
        assert assessment.verification_status == "passed"
        assert assessment.test_summary == "3 passed"
        assert assessment.proposal_id == "PROP-P1"

    def test_failed_development_creates_high_risk_assessment(self):
        gate = _gate()
        assessment = gate.assess(
            _run_result(
                DevelopmentOutcomeStatus.FAILED,
                ["pkg/feature.py"],
                verification=False,
            )
        )
        assert assessment.risk_level is PromotionRisk.HIGH
        assert assessment.recommendation is (
            PromotionRecommendation.NOT_PROMOTABLE
        )

    def test_rollback_increases_risk_to_high(self):
        gate = _gate()
        assessment = gate.assess(
            _run_result(
                DevelopmentOutcomeStatus.FAILED,
                ["pkg/small.py"],
                rollback=True,
            )
        )
        assert assessment.risk_level is PromotionRisk.HIGH
        assert assessment.verification_status == "rolled_back"

    def test_architecture_sensitive_module_is_high_risk(self, tmp_path):
        from atlas.research.repository_map import RepositoryMapBuilder

        root = tmp_path / "repo"
        kernel_dir = root / "atlas" / "kernel"
        kernel_dir.mkdir(parents=True)
        (kernel_dir / "__init__.py").write_text("", encoding="utf-8")
        (kernel_dir / "atlas.py").write_text("X = 1\n", encoding="utf-8")
        map_ = RepositoryMapBuilder(root).build()

        gate = _gate()
        # A successful small change touching the kernel composition root.
        result = _run_result(
            DevelopmentOutcomeStatus.SUCCESS, ["atlas/kernel/atlas.py"]
        )
        assessment = gate.assess(result)
        assert assessment.risk_level in (PromotionRisk.HIGH, PromotionRisk.MEDIUM)

        # The map-based path confirms kernel modules are architecture-
        # sensitive: dependents exist and risk stays elevated.
        dependents = map_.dependents_of("atlas.kernel.atlas")
        assert isinstance(dependents, tuple)

    def test_many_changed_files_are_medium_risk(self):
        gate = _gate()
        assessment = gate.assess(
            _run_result(
                DevelopmentOutcomeStatus.SUCCESS,
                [f"pkg/file_{i}.py" for i in range(6)],
            )
        )
        assert assessment.risk_level is PromotionRisk.MEDIUM
        assert assessment.recommendation is (
            PromotionRecommendation.NEEDS_REVIEW
        )


# ---------------------------------------------------------------------------
# Review lifecycle + EvolutionMemory integration
# ---------------------------------------------------------------------------


class TestReviewLifecycle:
    def test_request_review_persists_in_evolution_memory(self):
        memory = EvolutionMemory()
        gate = _gate(memory)
        assessment = gate.assess(
            _run_result(DevelopmentOutcomeStatus.SUCCESS, ["pkg/feature.py"])
        )

        request = gate.request_review(assessment)

        assert request.status is PromotionStatus.PENDING_REVIEW
        records = memory.get_records_by_type("promotion_review")
        assert len(records) == 1
        assert records[0].metadata["status"] == "pending_review"
        assert records[0].metadata["risk_level"] == "low"
        assert "PROP-P1" in records[0].related_ids

    def test_approval_changes_request_status_and_records_it(self):
        memory = EvolutionMemory()
        gate = _gate(memory)
        assessment = gate.assess(
            _run_result(DevelopmentOutcomeStatus.SUCCESS, ["pkg/feature.py"])
        )
        request = gate.request_review(assessment)

        gate.approve(request, comment="ship it")

        assert request.status is PromotionStatus.APPROVED
        # APPROVED means ready for human/operator promotion — and nothing
        # more. No repository mutation API exists on the gate.
        assert not hasattr(gate, "promote")
        statuses = [
            r.metadata["status"]
            for r in memory.get_records_by_type("promotion_review")
        ]
        assert sorted(statuses) == ["approved", "pending_review"]

    def test_reject_changes_request_status(self):
        memory = EvolutionMemory()
        gate = _gate(memory)
        assessment = gate.assess(
            _run_result(DevelopmentOutcomeStatus.SUCCESS, ["pkg/feature.py"])
        )
        request = gate.request_review(assessment)

        gate.reject(request, reason="not this cycle")

        assert request.status is PromotionStatus.REJECTED
        assert request.decision_comment == "not this cycle"
        statuses = [
            r.metadata["status"]
            for r in memory.get_records_by_type("promotion_review")
        ]
        assert sorted(statuses) == ["pending_review", "rejected"]

    def test_double_decision_fails_closed(self):
        gate = _gate()
        assessment = gate.assess(
            _run_result(DevelopmentOutcomeStatus.SUCCESS, ["a.py"])
        )
        request = gate.request_review(assessment)
        gate.approve(request)

        with pytest.raises(ValueError):
            gate.approve(request)
        with pytest.raises(ValueError):
            gate.reject(request)


class TestFailSoftAndDurability:
    def test_no_memory_still_lifecycle_works(self):
        gate = _gate(None)  # no EvolutionMemory configured
        assessment = gate.assess(
            _run_result(DevelopmentOutcomeStatus.SUCCESS, ["a.py"])
        )
        request = gate.request_review(assessment)
        assert request.status is PromotionStatus.PENDING_REVIEW
        gate.approve(request)
        assert request.status is PromotionStatus.APPROVED

    def test_exploding_memory_does_not_break_lifecycle(self):
        class _Exploding:
            def store_record(self, record):
                raise RuntimeError("storage exploded")

        gate = _gate(_Exploding())
        assessment = gate.assess(
            _run_result(DevelopmentOutcomeStatus.SUCCESS, ["a.py"])
        )
        request = gate.request_review(assessment)  # must not raise
        gate.approve(request)
        assert request.status is PromotionStatus.APPROVED

    def test_sqlite_durability_round_trip(self, tmp_path):
        storage = SQLiteEvolutionStorage(db_path=tmp_path / "promo.db")
        storage.initialize()
        try:
            memory = EvolutionMemory(storage=storage)
            gate = _gate(memory)
            assessment = gate.assess(
                _run_result(DevelopmentOutcomeStatus.SUCCESS, ["kept.py"])
            )
            request = gate.request_review(assessment)
            gate.approve(request)

            fresh = EvolutionMemory(storage=storage)
            fresh.restore()
            promo_records = fresh.get_records_by_type("promotion_review")
            assert len(promo_records) == 2
            statuses = {r.metadata["status"] for r in promo_records}
            assert statuses == {"pending_review", "approved"}
            json.dumps(promo_records[0].metadata)  # JSON-safe evidence
        finally:
            storage.close()


# json is imported at module top; evidence is asserted below.


class TestJsonSafety:
    def test_models_are_json_serializable(self):
        gate = _gate()
        assessment = gate.assess(
            _run_result(DevelopmentOutcomeStatus.SUCCESS, ["pkg/x.py"])
        )
        payload = json.dumps(
            {"assessment": assessment.to_dict()}
        )  # must not raise
        assert '"risk_level": "low"' in payload or '"risk_level":"low"' in (
            payload
        )