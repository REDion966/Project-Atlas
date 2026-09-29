"""Step 24 — Atlas direct self-development.

Measured baseline (real Atlas/kernel, before any change): a Step 23
`CapabilitySpecification` was terminal — `Atlas` had no `specification_development`
API and no bridge module existed
(`atlas/evolution/specification_development.py` absent), so an approved design
could not enter the governed pipeline. The closest existing precedent
(`evidence_development.development_need_from_gap`) consumes a `ConcreteGap` from an
evidence-gap report, never a capability specification; and the envelope that would
authorize sandbox-only execution is DISABLED in the controlled config
(`enabled=False, max_runs_per_window=0`), so the OWNER approval path is the real
governance boundary.

Step 24 adds ONE bounded, deterministic, model-free bridge that carries an
authorized specification through the EXISTING governed pipeline: the existing
cycle prepares the DRAFT proposal + approval request, and only an explicitly
authorized proposal runs the existing sandbox execution, verification and
promotion review. It approves, promotes and mutates nothing.
"""

from __future__ import annotations

import inspect
import json
import socket
import subprocess
from pathlib import Path

import pytest

import atlas.evolution.specification_development as bridge_module
from atlas.evolution.specification_development import (
    SelfDevelopmentStage,
    SpecificationDevelopmentBridge,
    development_need_from_specification,
)
from atlas.self_knowledge.capability_specification import (
    CapabilitySpecification,
    SpecificationStatus,
    build_capability_specification,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
PASS_CODE = "VALUE = 42\n"
PASS_TEST = (
    "from sandbox_mod import VALUE\n\n\ndef test_value():\n    assert VALUE == 42\n"
)
FAIL_TEST = "def test_fail():\n    assert False\n"


def _spec(**overrides):
    base = dict(
        spec_id="spec:widget:1",
        status=SpecificationStatus.SPECIFIED,
        capability="widget_convert",
        request="Convert memory_service archive format",
        purpose="Convert memory_service archive format",
        operations=("archive", "convert", "format", "memory_service"),
        mechanism="internal_development",
        gap_kind="unsupported_capability",
        gap_reason="no existing capability covers this request",
        evidence=("development_gap:missing_capability",),
        known_facts=("no existing capability covers this request",),
        affected_areas=("atlas.memory.service.memory_manager_service",),
    )
    base.update(overrides)
    return CapabilitySpecification(**base)


class _Cycle:
    def __init__(self, ok=True, proposal=None, failures=(), raise_error=False):
        self.ok = ok
        self.proposal = proposal
        self.decision = "prepared" if ok else "failed"
        self.proposal_id = "DEV-1"
        self.approval_request_id = "APPR-1"
        self.proposal_status = "PENDING_APPROVAL" if ok else ""
        self.failures = tuple(failures)
        self._raise = raise_error
        self.calls: list[object] = []

    def __call__(self, need):
        self.calls.append(need)
        if self._raise:
            raise RuntimeError("cycle exploded")
        return self


class _Proposal:
    def __init__(self, status="APPROVED", proposal_id="DEV-1", metadata=None):
        self.proposal_id = proposal_id
        self.status = type("S", (), {"name": status})()
        self.metadata = dict(metadata or {})


class _Authorization:
    def __init__(self, valid=True, proposal_id="DEV-1"):
        self._valid = valid
        self._proposal_id = proposal_id

    def is_valid_for(self, proposal):
        return self._valid and getattr(proposal, "proposal_id", "") == self._proposal_id


class _Report:
    def __init__(self, status="verified", evidence="status=SUCCESS; iterations=1"):
        self.status = type("S", (), {"value": status})()
        self.evidence = evidence


class _Outcome:
    def __init__(self, files=("sandbox_mod.py",)):
        self.changed_files = tuple(files)


class _Run:
    def __init__(self, status="SUCCESS", verification=None, files=("sandbox_mod.py",)):
        self.status = type("S", (), {"name": status})()
        self.plan = type("P", (), {"plan_id": "DEVPLAN-1"})()
        self.outcomes = (_Outcome(files),)
        self.verification = verification if verification is not None else _Report()


class _Gate:
    def __init__(self, recommendation="ready_for_promotion"):
        self.recommendation = recommendation
        self.calls: list[str] = []

    def assess(self, run, proposal_id=""):
        self.calls.append(proposal_id)
        return type("A", (), {"recommendation": self.recommendation})()


def _bridge(
    *,
    cycle=None,
    execute=None,
    gate="default",
    preparer="default",
):
    return SpecificationDevelopmentBridge(
        cycle_runner=cycle if cycle is not None else _Cycle(),
        execute=execute,
        gate=_Gate() if gate == "default" else gate,
        promotion_preparer=(
            (lambda proposal, run: "PROM-1") if preparer == "default" else preparer
        ),
    )


# ---------------------------------------------------------------------------
# 1. Specification -> bounded development workflow
# ---------------------------------------------------------------------------


class TestDevelopmentWorkflow:
    def test_prepares_and_stops_at_the_approval_boundary(self):
        cycle = _Cycle()
        execute_calls: list[object] = []
        result = _bridge(cycle=cycle, execute=execute_calls.append).run(_spec())
        assert result.stage is SelfDevelopmentStage.AWAITING_APPROVAL
        assert result.awaiting_approval is True
        assert result.authorized is False
        assert result.proposal_id == "DEV-1"
        assert result.approval_request_id == "APPR-1"
        assert result.proposal_status == "PENDING_APPROVAL"
        assert execute_calls == []  # nothing ran
        assert result.executed is False
        assert len(cycle.calls) == 1  # the EXISTING cycle was used

    def test_authorized_proposal_runs_implementation_verification_and_review(self):
        execute_calls: list[object] = []

        def _execute(proposal):
            execute_calls.append(proposal)
            return _Run()

        result = _bridge(execute=_execute).run(
            _spec(),
            proposal=_Proposal(status="APPROVED"),
        )
        assert result.authorized is True
        assert result.stage is SelfDevelopmentStage.PROMOTION_REVIEW
        assert result.executed is True
        assert result.verified is True
        assert result.promotable is True
        assert result.plan_id == "DEVPLAN-1"
        assert result.execution_status == "SUCCESS"
        assert result.verification_status == "verified"
        assert result.changed_files == ("sandbox_mod.py",)
        assert result.promotion_request_id == "PROM-1"
        assert len(execute_calls) == 1

    def test_explicit_authorization_object_authorizes_execution(self):
        result = _bridge(execute=lambda proposal: _Run()).run(
            _spec(),
            proposal=_Proposal(status="PENDING_APPROVAL"),
            authorization=_Authorization(valid=True),
        )
        assert result.stage is SelfDevelopmentStage.PROMOTION_REVIEW
        assert result.authorized is True

    def test_invalid_authorization_fails_closed(self):
        execute_calls: list[object] = []
        result = _bridge(execute=execute_calls.append).run(
            _spec(),
            proposal=_Proposal(status="PENDING_APPROVAL"),
            authorization=_Authorization(valid=False),
        )
        assert result.stage is SelfDevelopmentStage.REFUSED
        assert execute_calls == []
        assert "not valid for this proposal" in " ".join(result.reasons)

    def test_no_approval_means_no_implementation(self):
        execute_calls: list[object] = []
        result = _bridge(execute=execute_calls.append).run(
            _spec(), proposal=_Proposal(status="PENDING_APPROVAL")
        )
        assert result.stage is SelfDevelopmentStage.AWAITING_APPROVAL
        assert execute_calls == []
        assert "awaiting approval" in " ".join(result.reasons)

    def test_sandbox_authorized_status_is_accepted(self):
        result = _bridge(execute=lambda proposal: _Run()).run(
            _spec(), proposal=_Proposal(status="SANDBOX_AUTHORIZED")
        )
        assert result.stage is SelfDevelopmentStage.PROMOTION_REVIEW

    def test_need_is_bounded_and_carries_the_specification_provenance(self):
        need = development_need_from_specification(
            _spec(),
            code_changes=(("sandbox_mod.py", PASS_CODE),),
            test_files=(("test_sandbox_mod.py", PASS_TEST),),
            target_components=("sandbox_mod",),
        )
        assert need.title.startswith("Implement the 'widget_convert' capability")
        assert "Convert memory_service archive format" in need.summary
        assert "operations: archive, convert, format, memory_service" in need.summary
        assert need.candidate_id == "spec:widget:1"
        assert need.evidence_change_ids == ("development_gap:missing_capability",)
        assert need.target_components == ("sandbox_mod",)
        # the EXISTING deterministic supplier convention
        assert need.metadata["code_changes"] == [
            {"path": "sandbox_mod.py", "content": PASS_CODE}
        ]
        assert need.metadata["test_files"] == {"test_sandbox_mod.py": PASS_TEST}
        assert need.metadata["specification"]["spec_id"] == "spec:widget:1"
        assert need.metadata["specification"]["gap_kind"] == "unsupported_capability"

    def test_resume_does_not_re_run_the_cycle(self):
        cycle = _Cycle()
        result = _bridge(cycle=cycle, execute=lambda proposal: _Run()).run(
            _spec(), proposal=_Proposal(status="APPROVED")
        )
        assert cycle.calls == []
        assert result.proposal_id == "DEV-1"


# ---------------------------------------------------------------------------
# 2. Fail-closed refusals
# ---------------------------------------------------------------------------


class TestRefusals:
    def test_refused_specification_is_not_a_development_target(self):
        cycle = _Cycle()
        result = _bridge(cycle=cycle).run(build_capability_specification(None))
        assert result.stage is SelfDevelopmentStage.REFUSED
        assert cycle.calls == []
        assert "refused" in " ".join(result.reasons)

    @pytest.mark.parametrize(
        "overrides, expected",
        [
            ({"operations": ()}, "no operations"),
            ({"mechanism": ""}, "no existing development mechanism"),
            ({"request": "", "purpose": ""}, "no request"),
        ],
    )
    def test_incomplete_designs_fail_closed(self, overrides, expected):
        result = _bridge().run(_spec(**overrides))
        assert result.stage is SelfDevelopmentStage.REFUSED
        assert expected in " ".join(result.reasons)

    def test_non_specification_inputs_are_refused(self):
        for bad in (None, "spec", {"status": "specified"}, object()):
            result = _bridge().run(bad)
            assert result.stage is SelfDevelopmentStage.REFUSED
            assert result.reasons

    def test_cycle_failure_is_reported_without_implementation(self):
        execute_calls: list[object] = []
        cycle = _Cycle(ok=False, failures=(("supplier", "no changes"),))
        result = _bridge(cycle=cycle, execute=execute_calls.append).run(_spec())
        assert result.stage is SelfDevelopmentStage.FAILED
        assert "supplier: no changes" in result.reasons
        assert execute_calls == []

    def test_raising_cycle_fails_closed(self):
        result = _bridge(cycle=_Cycle(raise_error=True)).run(_spec())
        assert result.stage is SelfDevelopmentStage.FAILED
        assert "development cycle failed closed" in " ".join(result.reasons)

    def test_missing_collaborators_stop_at_the_honest_boundary(self):
        no_cycle = SpecificationDevelopmentBridge()
        assert no_cycle.run(_spec()).stage is SelfDevelopmentStage.FAILED
        no_executor = _bridge(execute=None).run(
            _spec(), proposal=_Proposal(status="APPROVED")
        )
        assert no_executor.stage is SelfDevelopmentStage.FAILED
        assert "no governed executor" in " ".join(no_executor.reasons)

    def test_raising_executor_fails_closed(self):
        def _boom(proposal):
            raise RuntimeError("sandbox exploded")

        result = _bridge(execute=_boom).run(
            _spec(), proposal=_Proposal(status="APPROVED")
        )
        assert result.stage is SelfDevelopmentStage.FAILED
        assert "authorized execution failed closed" in " ".join(result.reasons)


# ---------------------------------------------------------------------------
# 3. Failed / unverified work is never promoted
# ---------------------------------------------------------------------------


class TestPromotionBoundary:
    def test_failed_verification_is_not_promotable(self):
        preparer_calls: list[object] = []
        result = _bridge(
            execute=lambda proposal: _Run(
                status="FAILED", verification=_Report(status="unverified")
            ),
            preparer=lambda proposal, run: preparer_calls.append(run) or "PROM-1",
        ).run(_spec(), proposal=_Proposal(status="APPROVED"))
        assert result.stage is SelfDevelopmentStage.NOT_PROMOTABLE
        assert result.verified is False
        assert result.promotable is False
        assert result.promotion_request_id == ""
        assert preparer_calls == []  # no review was opened
        assert "not verified" in " ".join(result.reasons)

    def test_gate_not_promotable_is_honoured_even_when_verified(self):
        gate = _Gate(recommendation="not_promotable")
        preparer_calls: list[object] = []
        result = _bridge(
            execute=lambda proposal: _Run(),
            gate=gate,
            preparer=lambda proposal, run: preparer_calls.append(run) or "PROM-1",
        ).run(_spec(), proposal=_Proposal(status="APPROVED"))
        assert result.stage is SelfDevelopmentStage.NOT_PROMOTABLE
        assert gate.calls  # the EXISTING gate decided
        assert preparer_calls == []

    def test_verified_without_a_preparer_stops_at_verification(self):
        result = _bridge(execute=lambda proposal: _Run(), preparer=None).run(
            _spec(), proposal=_Proposal(status="APPROVED")
        )
        assert result.stage is SelfDevelopmentStage.VERIFICATION
        assert result.verified is True
        assert result.promotable is False
        assert result.promotion_request_id == ""

    def test_empty_promotion_request_stops_at_verification(self):
        result = _bridge(
            execute=lambda proposal: _Run(), preparer=lambda proposal, run: ""
        ).run(_spec(), proposal=_Proposal(status="APPROVED"))
        assert result.stage is SelfDevelopmentStage.VERIFICATION


# ---------------------------------------------------------------------------
# 4. Evidence, determinism and model independence
# ---------------------------------------------------------------------------


class TestEvidenceAndDeterminism:
    def test_evidence_records_what_why_and_how(self):
        result = _bridge(execute=lambda proposal: _Run()).run(
            _spec(), proposal=_Proposal(status="APPROVED")
        )
        joined = " ".join(result.evidence)
        assert "spec:widget:1" in joined  # what
        assert "Convert memory_service archive format" in joined
        assert "no existing capability covers this request" in joined  # why
        assert "verification: status=SUCCESS" in joined  # how verified
        assert "changed files: sandbox_mod.py" in joined

    def test_deterministic_and_serializable(self):
        def _run_once():
            return _bridge(execute=lambda proposal: _Run()).run(
                _spec(), proposal=_Proposal(status="APPROVED")
            )

        first, second = _run_once(), _run_once()
        assert first == second
        json.dumps(first.to_dict())

    def test_immutable_and_bounded(self):
        result = _bridge().run(_spec())
        with pytest.raises(Exception):
            result.stage = SelfDevelopmentStage.REFUSED  # type: ignore[misc]
        long_spec = _spec(purpose="x" * 5000)
        assert len(long_spec.purpose) <= 5000
        payload = bridge_module.development_need_from_specification(
            long_spec,
            code_changes=tuple((f"f{i}.py", "x") for i in range(50)),
        )
        assert len(payload.metadata["code_changes"]) <= 5

    def test_module_is_model_independent(self):
        source = inspect.getsource(bridge_module)
        for banned in ("atlas.ai", "ai_service", "AIService", "requests", "openai"):
            assert banned not in source


# ---------------------------------------------------------------------------
# 5. Real Atlas/kernel validation
# ---------------------------------------------------------------------------


def _tmp_storage(monkeypatch, tmp_path):
    from atlas.storage.evolution_storage import SQLiteEvolutionStorage
    from atlas.storage.research_storage import ResearchSQLiteStorage

    class TmpEvolution(SQLiteEvolutionStorage):
        def __init__(self, db_path=None):  # noqa: D107 - test shim
            super().__init__(db_path=tmp_path / "evolution.db")

    class TmpResearch(ResearchSQLiteStorage):
        def __init__(self, db_path=None):  # noqa: D107 - test shim
            super().__init__(db_path=tmp_path / "research.db")

    monkeypatch.setattr("atlas.kernel.atlas.SQLiteEvolutionStorage", TmpEvolution)
    monkeypatch.setattr("atlas.kernel.atlas.ResearchSQLiteStorage", TmpResearch)


def _started_atlas(monkeypatch, tmp_path):
    _tmp_storage(monkeypatch, tmp_path)
    from atlas.kernel.atlas import Atlas

    atlas = Atlas()
    atlas.start()
    return atlas


def _seed(storage, claim_id, statement):
    from atlas.research.models import (
        CitationRecord,
        ClaimVerification,
        KnowledgeClaim,
        SourceKind,
        VerificationStatus,
    )

    uri = f"https://example.com/{claim_id}"
    storage.store_claim(
        KnowledgeClaim(
            claim_id=claim_id,
            statement=statement,
            citations=(
                CitationRecord(
                    record_id=f"cite:{claim_id}:0000",
                    source_uri=uri,
                    source_title=claim_id,
                    source_kind=SourceKind.WEB,
                    section="chunk:0000",
                ),
            ),
            confidence=0.8,
        )
    )
    storage.store_verification(
        ClaimVerification(
            verification_id=f"verify:{claim_id}",
            claim_id=claim_id,
            status=VerificationStatus.SUPPORTED,
            score=0.75,
            metadata={"outcome": "PLAUSIBLE", "supporting": [uri], "contradicting": []},
        )
    )


def _genuine_spec(atlas):
    _seed(
        atlas._research_storage,
        "memory",
        "The memory_service convert archive format operation is documented.",
    )
    return atlas.capability_specification("Convert memory_service archive format")


def _git_head():
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
    ).stdout.strip()


class TestRealKernel:
    def test_prepare_stops_at_approval_without_running_anything(
        self, monkeypatch, tmp_path
    ):
        atlas = _started_atlas(monkeypatch, tmp_path)
        try:
            spec = _genuine_spec(atlas)
            before = _git_head()
            result = atlas.specification_development(
                spec,
                code_changes=(("sandbox_mod.py", PASS_CODE),),
                test_files=(("test_sandbox_mod.py", PASS_TEST),),
                target_components=("sandbox_mod",),
            )
            assert result.stage is SelfDevelopmentStage.AWAITING_APPROVAL
            assert result.authorized is False
            assert result.proposal_id.startswith("DEV-")
            assert result.approval_request_id.startswith("APPR-")
            assert result.proposal_status == "PENDING_APPROVAL"
            assert result.execution_status == ""
            assert atlas.pending_promotion_reviews() == []
            assert _git_head() == before  # the live repository is untouched
        finally:
            atlas.shutdown()

    def test_owner_approved_specification_runs_and_reaches_a_review(
        self, monkeypatch, tmp_path
    ):
        atlas = _started_atlas(monkeypatch, tmp_path)
        try:
            spec = _genuine_spec(atlas)
            prepared = atlas.specification_development(
                spec,
                code_changes=(("sandbox_mod.py", PASS_CODE),),
                test_files=(("test_sandbox_mod.py", PASS_TEST),),
                target_components=("sandbox_mod",),
            )
            atlas.confirm_development_approval(
                atlas.session_context, prepared.proposal_id
            )
            before = _git_head()
            result = atlas.specification_development(
                spec, proposal_id=prepared.proposal_id
            )
            assert result.authorized is True
            assert result.stage is SelfDevelopmentStage.PROMOTION_REVIEW
            assert result.execution_status == "SUCCESS"
            assert result.verification_status == "verified"
            assert result.plan_id.startswith("DEVPLAN-")
            assert result.changed_files == ("sandbox_mod.py",)
            assert result.promotion_request_id
            assert _git_head() == before  # never the live repository
            assert not (REPO_ROOT / "sandbox_mod.py").exists()
            reviews = atlas.pending_promotion_reviews()
            assert any(
                review.get("proposal_id") == prepared.proposal_id
                for review in reviews
            )
            # The actionable id is the one the OWNER promotion seam accepts.
            assert result.promotion_request_id in atlas._promotion_artifacts
        finally:
            atlas.shutdown()

    def test_unapproved_proposal_is_not_executed(self, monkeypatch, tmp_path):
        atlas = _started_atlas(monkeypatch, tmp_path)
        try:
            spec = _genuine_spec(atlas)
            prepared = atlas.specification_development(
                spec,
                code_changes=(("sandbox_mod.py", PASS_CODE),),
                test_files=(("test_sandbox_mod.py", PASS_TEST),),
            )
            before = _git_head()
            result = atlas.specification_development(
                spec, proposal_id=prepared.proposal_id
            )
            assert result.stage is SelfDevelopmentStage.AWAITING_APPROVAL
            assert result.executed is False
            assert _git_head() == before
        finally:
            atlas.shutdown()

    def test_failed_verification_is_not_promoted(self, monkeypatch, tmp_path):
        atlas = _started_atlas(monkeypatch, tmp_path)
        try:
            spec = _genuine_spec(atlas)
            prepared = atlas.specification_development(
                spec,
                code_changes=(("sandbox_mod.py", PASS_CODE),),
                test_files=(("test_sandbox_mod.py", FAIL_TEST),),
                target_components=("sandbox_mod",),
            )
            atlas.confirm_development_approval(
                atlas.session_context, prepared.proposal_id
            )
            result = atlas.specification_development(
                spec, proposal_id=prepared.proposal_id
            )
            assert result.stage is SelfDevelopmentStage.NOT_PROMOTABLE
            assert result.verification_status != "verified"
            assert result.promotion_request_id == ""
            assert result.promotable is False
            assert atlas.pending_promotion_reviews() == []
        finally:
            atlas.shutdown()

    def test_unknown_proposal_id_fails_closed(self, monkeypatch, tmp_path):
        atlas = _started_atlas(monkeypatch, tmp_path)
        try:
            spec = _genuine_spec(atlas)
            with pytest.raises(RuntimeError):
                atlas.specification_development(spec, proposal_id="DEV-does-not-exist")
        finally:
            atlas.shutdown()

    def test_no_network_is_used(self, monkeypatch, tmp_path):
        def _blocked(*args, **kwargs):
            raise AssertionError("the self-development path must not touch the network")

        monkeypatch.setattr(socket.socket, "connect", _blocked)
        atlas = _started_atlas(monkeypatch, tmp_path)
        try:
            spec = _genuine_spec(atlas)
            prepared = atlas.specification_development(
                spec,
                code_changes=(("sandbox_mod.py", PASS_CODE),),
                test_files=(("test_sandbox_mod.py", PASS_TEST),),
                target_components=("sandbox_mod",),
            )
            atlas.confirm_development_approval(
                atlas.session_context, prepared.proposal_id
            )
            result = atlas.specification_development(
                spec, proposal_id=prepared.proposal_id
            )
            assert result.verification_status == "verified"
        finally:
            atlas.shutdown()

    def test_steps_1_to_23_preserved(self, monkeypatch, tmp_path):
        atlas = _started_atlas(monkeypatch, tmp_path)
        try:
            question = "What is the current release of the Zorblax protocol?"
            assert atlas.knowledge_need(question).kind.value == "missing"
            outcome = atlas.research_knowledge_need(question)
            assert atlas.research_provenance(outcome).claims == ()
            assert atlas.knowledge_retention(outcome).records == ()
            assert atlas.retained_knowledge(question).status.value == "empty"
            assert atlas.temporal_knowledge(question).entries == ()
            assert atlas.refresh_requests(question) == ()
            assert atlas.monitor_knowledge(question).observations == ()
            assert atlas.capability_gap(question).is_gap is False
            assert atlas.capability_specification(question).status is (
                SpecificationStatus.REFUSED
            )
            assert atlas.capability_contract("research")["state"] == "available"
        finally:
            atlas.shutdown()
