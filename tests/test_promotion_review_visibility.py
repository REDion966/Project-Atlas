"""Stage H — Promotion review visibility & evidence-driven prioritization.

Verifies:

H1  bounded change manifests attached to promotion assessments/requests
    (deterministic ordering, per-file and total caps, fail-soft),
H2  ``PromotionGate.pending_reviews()`` — a read-only surface returning
    PENDING_REVIEW requests joined with Stage G decision quality, sorted
    highest priority first,
plus the standing safety invariants: no promote/apply/execute API, no
repository mutation, JSON-safe evidence, existing tests untouched.
"""

import json
from dataclasses import replace
from datetime import datetime

import pytest

from atlas.evolution.development_models import (
    DevelopmentOutcome,
    DevelopmentOutcomeStatus,
    DevelopmentPlan,
)
from atlas.evolution.evolution_memory import EvolutionMemory
from atlas.evolution.models import EvolutionRecord
from atlas.evolution.promotion_gate import (
    MAX_EXCERPT_CHARS,
    PromotionGate,
    PromotionRecommendation,
    PromotionRisk,
    PromotionStatus,
    build_change_manifest,
)
from atlas.evolution.self_development_loop import DevelopmentRunResult


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


def _code_changes(*pairs):
    return [{"path": path, "content": content} for path, content in pairs]


def _seed_pending(
    memory,
    pid,
    score=None,
    risk="medium",
    request_id=None,
):
    """Persist a PENDING_REVIEW promotion record (+ proposal when scored)."""
    from atlas.evolution.improvement_planner import (
        ImprovementPlanner,
        ImprovementPriority,
    )
    from atlas.evolution.models import Weakness
    from atlas.evolution.proposal_generator import ProposalGenerator

    if score is not None:
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
        proposal.metadata["decision_quality"] = {
            "final_priority_score": score
        }
        memory.store_proposal(proposal)

    record = EvolutionRecord(
        record_id=request_id or f"PGATE-{pid}",
        event_type="promotion_review",
        description="pending promotion review",
        related_ids=[pid],
        timestamp=datetime.now(),
        metadata={
            "status": PromotionStatus.PENDING_REVIEW.value,
            "risk_level": risk,
            "recommendation": "needs_review",
            "change_manifest": {
                "files": [{"path": "pkg/x.py", "size": 3, "excerpt": "X"}],
                "total_files": 1,
                "truncated": False,
            },
        },
    )
    memory.store_record(record)
    return record


# ---------------------------------------------------------------------------
# H1 — change manifest
# ---------------------------------------------------------------------------


class TestChangeManifest:
    def test_manifest_creation_and_deterministic_ordering(self):
        manifest = build_change_manifest(
            _code_changes(
                ("pkg/b.py", "B"),
                ("pkg/a.py", "A-content"),
                ("pkg/c.py", "C"),
            )
        )
        paths = [entry["path"] for entry in manifest["files"]]
        assert paths == ["pkg/a.py", "pkg/b.py", "pkg/c.py"]
        assert manifest["total_files"] == 3
        assert manifest["truncated"] is False

        repeat = build_change_manifest(
            _code_changes(
                ("pkg/c.py", "C"),
                ("pkg/b.py", "B"),
                ("pkg/a.py", "A-content"),
            )
        )
        assert repeat == manifest  # deterministic

    def test_per_file_excerpt_limit(self, monkeypatch=None, tmp_excerpt=100):
        content = "x" * (MAX_EXCERPT_CHARS + 500)
        manifest = build_change_manifest(
            _code_changes(("pkg/big.py", content))
        )
        entry = manifest["files"][0]
        assert entry["size"] == len(content)      # true size preserved
        assert len(entry["excerpt"]) == MAX_EXCERPT_CHARS
        assert manifest["truncated"] is True      # total budget consumed

    def test_total_size_budget_enforced(self, monkeypatch):
        monkeypatch.setattr(
            "atlas.evolution.promotion_gate.MAX_EXCERPT_CHARS", 100
        )
        manifest = build_change_manifest(
            _code_changes(
                ("a.py", "a" * 150),
                ("b.py", "b" * 150),
                ("c.py", "c" * 150),
            ),
            max_total_chars=200,
        )
        total_excerpt_chars = sum(
            len(entry["excerpt"]) for entry in manifest["files"]
        )
        assert total_excerpt_chars <= 200
        assert manifest["truncated"] is True

    def test_max_files_cap(self):
        changes = _code_changes(*[(f"f{i}.py", "x") for i in range(30)])
        manifest = build_change_manifest(changes, max_files=5)
        assert len(manifest["files"]) == 5
        assert manifest["total_files"] == 30
        assert manifest["truncated"] is True

    def test_malformed_entries_skipped_fail_soft(self):
        manifest = build_change_manifest(
            [
                "not-a-dict",
                {"content": "no path"},
                {"path": "", "content": "empty"},
                {"path": "ok.py", "content": "OK"},
            ]
        )
        assert [e["path"] for e in manifest["files"]] == ["ok.py"]

    def test_empty_input_yields_empty_manifest(self):
        assert build_change_manifest([]) == {
            "files": [],
            "total_files": 0,
            "truncated": False,
        }
        assert build_change_manifest(None) == {
            "files": [],
            "total_files": 0,
            "truncated": False,
        }

    def test_manifest_is_json_serializable(self):
        payload = json.dumps(
            build_change_manifest(_code_changes(("a.py", "A")))
        )
        assert '"total_files"' in payload


class TestAssessmentManifestIntegration:
    def test_assessment_carries_manifest(self):
        gate = PromotionGate()
        from atlas.evolution.self_development_loop import (
            DevelopmentRunResult,
        )

        result = DevelopmentRunResult(
            status=DevelopmentOutcomeStatus.SUCCESS,
            plan=_plan("PROP-M1"),
            outcomes=[
                DevelopmentOutcome(
                    outcome=DevelopmentOutcomeStatus.SUCCESS,
                    proposal_id="PROP-M1",
                    plan_id="PLAN-P1",
                    iteration=1,
                    verification_passed=True,
                    changed_files=["pkg/x.py"],
                    test_outcome="1 passed",
                )
            ],
            iterations_used=1,
        )
        manifest = build_change_manifest(
            _code_changes(("pkg/x.py", "X"))
        )
        assessment = gate.assess(result, change_manifest=manifest)
        assert assessment.change_manifest["total_files"] == 1


# ---------------------------------------------------------------------------
# H2 — pending review prioritization
# ---------------------------------------------------------------------------


class TestPendingReviews:
    def test_pending_reviews_sorted_by_priority(self):
        memory = EvolutionMemory()
        _seed_pending(memory, "PROP-LOW", score=0.1, risk="low",
                      request_id="PGATE-LOW")
        _seed_pending(memory, "PROP-HIGH", score=0.9, risk="low",
                      request_id="PGATE-HIGH")

        gate = PromotionGate(evolution_memory=memory)
        pending = gate.pending_reviews()

        assert [item["request_id"] for item in pending] == [
            "PGATE-HIGH",
            "PGATE-LOW",
        ]
        assert pending[0]["final_priority_score"] == pytest.approx(0.9)

    def test_missing_scores_sort_last_deterministically(self):
        memory = EvolutionMemory()
        _seed_pending(memory, "PROP-SCORED", score=0.4,
                      request_id="PGATE-SCORED")
        _seed_pending(memory, "PROP-UNSCORED", score=None,
                      request_id="PGATE-UNSCORED")

        gate = PromotionGate(evolution_memory=memory)
        pending = gate.pending_reviews()

        assert [item["request_id"] for item in pending] == [
            "PGATE-SCORED",
            "PGATE-UNSCORED",
        ]
        assert pending[-1]["final_priority_score"] == 0.0

    def test_decided_requests_excluded(self):
        """A decided (approved) record must not appear as pending."""
        memory = EvolutionMemory()
        _seed_pending(memory, "PROP-DONE", score=0.9,
                      request_id="PGATE-DONE")
        # Simulate the later decision: an APPROVED audit record sharing
        # the same request id (append-only storage).
        pending_record = memory.get_records_by_type("promotion_review")[0]
        approved_record = replace(
            pending_record,
            metadata=dict(pending_record.metadata, status="approved"),
        )
        memory.store_record(approved_record)

        gate = PromotionGate(evolution_memory=memory)
        pending = gate.pending_reviews()

        # The pending entry is still there; the approved duplicate is not
        # reported as pending.
        ids = [item["request_id"] for item in pending]
        assert ids == ["PGATE-DONE"]

    def test_multiple_risk_levels_reported(self):
        memory = EvolutionMemory()
        _seed_pending(memory, "PROP-R1", score=0.2, risk="high")
        _seed_pending(memory, "PROP-R2", score=0.8, risk="low")
        gate = PromotionGate(evolution_memory=memory)

        pending = gate.pending_reviews()
        risks = {item["proposal_id"]: item["risk_level"] for item in pending}
        assert risks == {"PROP-R1": "high", "PROP-R2": "low"}

    def test_evidence_completeness_flagged(self):
        memory = EvolutionMemory()
        record = _seed_pending(memory, "PROP-EV", request_id="PGATE-EV")
        # Strip the manifest to simulate incomplete evidence.
        stripped = replace(
            record,
            metadata=dict(record.metadata, change_manifest={"files": []}),
        )
        rebuilt = EvolutionMemory()
        rebuilt.store_record(stripped)

        gate = PromotionGate(evolution_memory=rebuilt)
        pending = gate.pending_reviews()
        assert pending[0]["evidence_complete"] is False
        assert pending[0]["manifest_file_count"] == 0


class TestSafetyInvariants:
    def test_gate_has_no_promotion_execution_api(self):
        gate = PromotionGate()
        for forbidden in ("promote", "execute", "apply"):
            assert not hasattr(gate, forbidden)

    def test_no_repository_mutation_apis_exist(self):
        import ast
        import inspect

        import atlas.evolution.promotion_gate as module

        tree = ast.parse(inspect.getsource(module))

        forbidden_module_roots = {"os", "subprocess", "shutil", "pathlib"}
        forbidden_exec_attrs = {
            "system", "popen", "remove", "unlink", "rmtree", "rename",
            "startfile", "call", "run",
        }

        def _root_name(node):
            while isinstance(node, ast.Attribute):
                node = node.value
            return node.id if isinstance(node, ast.Name) else ""

        imported_roots = set()
        risky_calls = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imported_roots.add(alias.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imported_roots.add(node.module.split(".")[0])
            elif isinstance(node, ast.Call):
                func = node.func
                if isinstance(func, ast.Attribute):
                    base = _root_name(func.value)
                    if base in forbidden_module_roots and func.attr in forbidden_exec_attrs:
                        risky_calls.append(f"{base}.{func.attr}")

        disallowed_imports = imported_roots & {"subprocess", "shutil", "pathlib"}
        assert not disallowed_imports, (
            f"forbidden imports found: {sorted(disallowed_imports)}"
        )
        assert not risky_calls, f"forbidden execution calls: {risky_calls}"

    def test_pending_view_is_json_safe(self):
        memory = EvolutionMemory()
        _seed_pending(memory, "PROP-J", score=0.5, request_id="PGATE-J")
        gate = PromotionGate(evolution_memory=memory)

        payload = json.dumps(gate.pending_reviews())
        assert '"final_priority_score"' in payload


# ---------------------------------------------------------------------------
# Stage H kernel bridge — manual submission of verified development outcomes
# ---------------------------------------------------------------------------


def _make_kernel_for_bridge(memory: EvolutionMemory):
    """Construct a minimal Atlas kernel surface for bridge tests.

    We deliberately bypass ``Atlas.start()`` (which requires a full
    Configuration) and wire only the two attributes touched by the
    Stage H bridge: ``_evolution_memory`` and ``_promotion_gate``.
    Mirrors the read-only view the kernel exposes to operators.
    """
    from atlas.kernel.atlas import Atlas

    kernel = Atlas.__new__(Atlas)
    kernel._evolution_memory = memory
    kernel._promotion_gate = PromotionGate(evolution_memory=memory)
    return kernel


class TestKernelBridge:
    """Stage H kernel bridge: manual submission of verified
    development outcomes into a ``PENDING_REVIEW`` audit row carrying
    bounded change evidence. Read-only with respect to the repository
    and the human-approval boundary.
    """

    def _verified_run(self):
        outcome = DevelopmentOutcome(
            outcome=DevelopmentOutcomeStatus.SUCCESS,
            proposal_id="PROP-K1",
            plan_id="PLAN-K1",
            iteration=1,
            verification_passed=True,
            changed_files=["pkg/k.py"],
            test_outcome="1 passed",
        )
        return DevelopmentRunResult(
            status=DevelopmentOutcomeStatus.SUCCESS,
            plan=_plan("PROP-K1"),
            outcomes=[outcome],
            iterations_used=1,
            message="ok",
        )

    def test_bridge_returns_pending_review_request(self):
        memory = EvolutionMemory()
        kernel = _make_kernel_for_bridge(memory)
        manifest = build_change_manifest(
            _code_changes(("pkg/k.py", "K"))
        )

        request = kernel.submit_development_for_promotion_review(
            self._verified_run(),
            proposal_id="PROP-K1",
            change_manifest=manifest,
            development_record_id="DEV-K1",
        )

        assert request.status is PromotionStatus.PENDING_REVIEW
        assert request.proposal_id == "PROP-K1"
        assert request.metadata["development_record_id"] == "DEV-K1"

    def test_manifest_survives_into_persisted_audit_record(self):
        memory = EvolutionMemory()
        kernel = _make_kernel_for_bridge(memory)
        manifest = build_change_manifest(
            _code_changes(
                ("pkg/a.py", "alpha"),
                ("pkg/b.py", "beta"),
            )
        )

        kernel.submit_development_for_promotion_review(
            self._verified_run(),
            proposal_id="PROP-K2",
            change_manifest=manifest,
        )

        records = memory.get_records_by_type("promotion_review")
        assert len(records) == 1
        meta = records[0].metadata
        # The assessment (carrying the manifest) is nested under
        # ``metadata["assessment"]`` per the gate's write path.
        assert "assessment" in meta
        persisted_manifest = meta["assessment"]["change_manifest"]
        assert persisted_manifest["total_files"] == 2
        persisted_paths = sorted(
            entry["path"] for entry in persisted_manifest["files"]
        )
        assert persisted_paths == ["pkg/a.py", "pkg/b.py"]

    def test_bridge_does_not_approve_or_reject(self):
        memory = EvolutionMemory()
        kernel = _make_kernel_for_bridge(memory)

        request = kernel.submit_development_for_promotion_review(
            self._verified_run(),
            proposal_id="PROP-K3",
        )

        # The request must remain in the PENDING_REVIEW state; the
        # bridge never advances the lifecycle on its own.
        assert request.status is PromotionStatus.PENDING_REVIEW
        assert request.decided_at is None
        assert request.decision_comment == ""

        # The audit row's status must be ``pending_review`` (not
        # ``approved`` / ``rejected`` / ``promoted``).
        records = memory.get_records_by_type("promotion_review")
        assert len(records) == 1
        assert records[0].metadata["status"] == "pending_review"

    def test_bridge_does_not_execute_or_mutate_repository(self):
        """The bridge must not introduce filesystem/git/subprocess
        behavior on its own. We assert it does not add the forbidden
        methods to the kernel surface.
        """
        memory = EvolutionMemory()
        kernel = _make_kernel_for_bridge(memory)

        # No promote/execute/apply API on the bridge entry point.
        for forbidden in ("promote", "execute", "apply"):
            assert not hasattr(
                kernel.submit_development_for_promotion_review, forbidden
            ), (
                f"bridge must not expose '{forbidden}'"
            )

        # And the kernel instance as a whole must not gain those names.
        for forbidden in ("promote", "execute", "apply"):
            assert not hasattr(kernel, forbidden), (
                f"kernel must not expose '{forbidden}'"
            )

    def test_bridge_requires_wired_gate(self):
        """Before ``Atlas.start()`` (or when construction is incomplete)
        the bridge refuses with a clear error rather than silently
        building a stray gate.
        """
        from atlas.kernel.atlas import Atlas

        kernel = Atlas.__new__(Atlas)
        kernel._evolution_memory = None
        kernel._promotion_gate = None

        with pytest.raises(RuntimeError):
            kernel.submit_development_for_promotion_review(
                self._verified_run(),
                proposal_id="PROP-K4",
            )

    def test_pending_view_includes_bridge_submitted_request(self):
        """Round-trip: a request opened via the bridge is visible to
        ``pending_promotion_reviews()`` and reported as a pending
        review. This locks the spec's "review prioritization" path
        end-to-end through the kernel.
        """
        memory = EvolutionMemory()
        kernel = _make_kernel_for_bridge(memory)

        kernel.submit_development_for_promotion_review(
            self._verified_run(),
            proposal_id="PROP-K5",
            change_manifest=build_change_manifest(
                _code_changes(("pkg/k.py", "K"))
            ),
        )

        pending = kernel.pending_promotion_reviews()
        assert len(pending) == 1
        assert pending[0]["proposal_id"] == "PROP-K5"
        assert pending[0]["status"] == "pending_review"
        assert pending[0]["evidence_complete"] is True
        assert pending[0]["manifest_file_count"] == 1
