"""Step 25 — Integrated autonomous intelligence loop.

Measured baseline (real Atlas/kernel, before any change): the completed post-L10
capabilities were individually reachable but **unconnected**. `Atlas` had no
integrated-loop API (`integrated_loop`, `integrated_intelligence_loop`,
`run_integrated_loop`, `resume_integrated_loop`, `intelligence_loop` all absent) and
no loop module existed (`atlas/autonomy/` did not exist). Going from one request to a
reviewable specification required **10 separate seams**
(`knowledge_need` → `research_knowledge_need` → `research_provenance` →
`knowledge_retention` → `retained_knowledge` → `temporal_knowledge` →
`refresh_requests` → `monitor_knowledge` → `capability_gap` →
`capability_specification`), each ignoring the previous one's result; no stage/state
machine existed, no single object carried the cycle, and nothing could resume after
the human approval boundary. `Atlas.tick()` still drove only its four settles.

Step 25 adds ONE bounded coordinator that connects those EXISTING seams into a
capability-driven, deterministic, model-free loop. It approves, authorizes,
promotes, refreshes and mutates nothing by itself.
"""

from __future__ import annotations

import inspect
import json
import pkgutil
import socket
import subprocess
from dataclasses import replace
from pathlib import Path

import pytest

import atlas.autonomy.integrated_loop as loop_module
import atlas.storage as storage_pkg
from atlas.autonomy import (
    IntegratedIntelligenceLoop,
    LoopAction,
    LoopSeams,
    LoopStage,
    LoopStatus,
)
from atlas.evolution.specification_development import SelfDevelopmentStage
from atlas.research.knowledge_need import KnowledgeNeedKind, KnowledgeNeedStatus
from atlas.research.research_outcome import ResearchStatus
from atlas.self_knowledge.capability_gap import CapabilityGapKind
from atlas.self_knowledge.capability_specification import SpecificationStatus

REPO_ROOT = Path(__file__).resolve().parents[1]
PASS_CODE = "VALUE = 42\n"
PASS_TEST = (
    "from sandbox_mod import VALUE\n\n\ndef test_value():\n    assert VALUE == 42\n"
)
FAIL_TEST = "def test_fail():\n    assert False\n"


class _Obj:
    """Minimal stand-in for a per-step result type."""

    def __init__(self, **kw):
        self.__dict__.update(kw)


class _Recorder:
    """A recording fake seam."""

    def __init__(self, value=None, error=None):
        self.value = value
        self.error = error
        self.calls: list[tuple[tuple, dict]] = []

    def __call__(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        if self.error is not None:
            raise self.error
        return self.value


def _need(kind="none", status="satisfied"):
    return _Obj(kind=kind, status=status)


def _research(status="researched", mechanism="governed_external_acquisition"):
    return _Obj(status=status, mechanism=mechanism)


def _gap(kind="supported", boundary="none", reason="a reason", capability=""):
    return _Obj(kind=kind, boundary=boundary, reason=reason, capability=capability)


def _spec(
    status="specified", spec_id="spec:1", reason="", mechanism="internal_development"
):
    return _Obj(status=status, spec_id=spec_id, reason=reason, mechanism=mechanism)


def _development(
    stage="awaiting_approval",
    *,
    proposal_id="DEV-1",
    approval_request_id="APPR-1",
    promotion_request_id="",
    verification_status="",
    reasons=(),
    evidence=(),
):
    return _Obj(
        stage=stage,
        proposal_id=proposal_id,
        approval_request_id=approval_request_id,
        promotion_request_id=promotion_request_id,
        verification_status=verification_status,
        reasons=tuple(reasons),
        evidence=tuple(evidence),
    )


def _unsupported():
    """A recorder for the ONE adjudication that is a genuine capability gap."""
    return _Recorder(_gap(CapabilityGapKind.UNSUPPORTED_CAPABILITY.value))


def _no_source():
    """A recorder for the deny-by-default research outcome."""
    return _Recorder(_research(ResearchStatus.NO_AUTHORIZED_SOURCE.value, "none"))


def _seams(**overrides):
    """A full set of recording seams with sensible defaults."""
    seams = {
        "knowledge_need": _Recorder(_need()),
        "research": _Recorder(_research()),
        "provenance": _Recorder(_Obj(claims=(_Obj(),), sources=(_Obj(),))),
        "retention": _Recorder(_Obj(records=(_Obj(),), refused=())),
        "retained": _Recorder(_Obj(status="ok", records=(_Obj(),))),
        "temporal": _Recorder(_Obj(status="ok", entries=(_Obj(),))),
        "refresh_requests": _Recorder(()),
        "refresh": _Recorder(_Obj(outcomes=(_Obj(status="not_required"),))),
        "monitoring": _Recorder(_Obj(status="ok", observations=(_Obj(),))),
        "capability_gap": _Recorder(_gap()),
        "specification": _Recorder(_spec()),
        "development": _Recorder(_development()),
    }
    seams.update(overrides)
    return seams, LoopSeams(**seams)


def _loop(**overrides):
    seams, injected = _seams(**overrides)
    return IntegratedIntelligenceLoop(seams=injected), seams


# ---------------------------------------------------------------------------
# 1. Routing — capability-driven, from each stage's OWN typed result
# ---------------------------------------------------------------------------


class TestRouting:
    def test_satisfied_need_with_supported_gap_answers_without_development(self):
        loop, seams = _loop()
        result = loop.run("Summarize the Zorblax protocol")
        assert result.status is LoopStatus.ANSWERED
        assert result.stage is LoopStage.CAPABILITY
        assert result.action is LoopAction.NONE
        assert result.terminal is True
        assert result.development is None
        assert seams["research"].calls == []  # satisfied: no research
        assert seams["development"].calls == []
        assert "supported by the existing capability" in result.response

    def test_actionable_need_runs_the_full_knowledge_evaluation(self):
        loop, seams = _loop(knowledge_need=_Recorder(_need("missing", "actionable")))
        result = loop.run("What is the current release of the Zorblax protocol?")
        for name in (
            "research",
            "provenance",
            "retention",
            "retained",
            "temporal",
            "refresh_requests",
            "monitoring",
        ):
            assert seams[name].calls, f"{name} was not reached"
        assert result.provenance is not None
        assert result.retention is not None
        assert result.temporal is not None
        assert result.monitoring is not None

    def test_satisfied_need_still_evaluates_retained_knowledge(self):
        loop, seams = _loop()
        loop.run("What is the memory_service module responsible for?")
        assert seams["retained"].calls
        assert seams["temporal"].calls
        assert seams["monitoring"].calls
        assert seams["provenance"].calls == []  # no research outcome to trace

    def test_no_authorized_source_reports_the_source_boundary(self):
        loop, seams = _loop(
            knowledge_need=_Recorder(_need("missing", "actionable")),
            research=_no_source(),
            capability_gap=_Recorder(_gap(CapabilityGapKind.MISSING_KNOWLEDGE.value)),
        )
        result = loop.run("Convert the Zorblax archive format")
        assert result.status is LoopStatus.ANSWERED
        assert result.stage is LoopStage.CAPABILITY
        assert result.action is LoopAction.AUTHORIZE_SOURCE
        assert "research: no_authorized_source" in " ".join(result.evidence)
        assert seams["provenance"].calls == []  # nothing to trace
        assert seams["development"].calls == []

    @pytest.mark.parametrize(
        "research_status, expected",
        [
            (ResearchStatus.INSUFFICIENT.value, LoopAction.PROVIDE_EVIDENCE),
            (ResearchStatus.FAILED.value, LoopAction.ADDRESS_FAILURE),
            (ResearchStatus.UNKNOWN.value, LoopAction.PROVIDE_EVIDENCE),
        ],
    )
    def test_blocked_research_routes_to_its_own_action(self, research_status, expected):
        loop, _seams_map = _loop(
            knowledge_need=_Recorder(_need("missing", "actionable")),
            research=_Recorder(_research(research_status, "none")),
            capability_gap=_Recorder(_gap(CapabilityGapKind.MISSING_KNOWLEDGE.value)),
        )
        result = loop.run("Convert the Zorblax archive format")
        assert result.status is LoopStatus.ANSWERED
        assert result.action is expected
        assert result.reason

    def test_the_adjudicator_verdict_is_authoritative_for_the_action(self):
        # A supported request stays "nothing required" even though the optional
        # knowledge step could not research the subject; the finding is recorded.
        loop, _m = _loop(
            knowledge_need=_Recorder(_need("missing", "actionable")),
            research=_no_source(),
            capability_gap=_Recorder(_gap(CapabilityGapKind.SUPPORTED.value)),
        )
        result = loop.run("Convert the Zorblax archive format")
        assert result.status is LoopStatus.ANSWERED
        assert result.action is LoopAction.NONE
        assert "research: no_authorized_source" in " ".join(result.evidence)

    @pytest.mark.parametrize(
        "kind, expected",
        [
            (CapabilityGapKind.SUPPORTED.value, LoopAction.NONE),
            (CapabilityGapKind.TEMPORARILY_BLOCKED.value, LoopAction.NONE),
            (CapabilityGapKind.GOVERNED.value, LoopAction.NONE),
            (CapabilityGapKind.MISSING_KNOWLEDGE.value, LoopAction.PROVIDE_EVIDENCE),
            (CapabilityGapKind.AMBIGUOUS.value, LoopAction.RESOLVE_AMBIGUITY),
            (CapabilityGapKind.EXECUTION_FAILURE.value, LoopAction.ADDRESS_FAILURE),
            (CapabilityGapKind.UNKNOWN.value, LoopAction.PROVIDE_EVIDENCE),
        ],
    )
    def test_non_gap_adjudications_answer_truthfully(self, kind, expected):
        loop, seams = _loop(capability_gap=_Recorder(_gap(kind)))
        result = loop.run("do something")
        assert result.status is LoopStatus.ANSWERED
        assert result.action is expected
        assert result.development is None
        assert seams["specification"].calls == []
        assert seams["development"].calls == []

    def test_ambiguous_request_never_becomes_development(self):
        loop, seams = _loop(
            capability_gap=_Recorder(_gap(CapabilityGapKind.AMBIGUOUS.value))
        )
        result = loop.run("handle the thing", ambiguous=True)
        assert result.action is LoopAction.RESOLVE_AMBIGUITY
        assert "ambiguous" in result.response
        _, kwargs = seams["capability_gap"].calls[0]
        assert kwargs["ambiguous"] is True
        assert seams["development"].calls == []

    def test_unrecognised_gap_kind_fails_closed_to_the_evidence_action(self):
        loop, _m = _loop(capability_gap=_Recorder(_gap("something-unrecognised")))
        result = loop.run("do something")
        assert result.status is LoopStatus.ANSWERED
        assert result.action is LoopAction.PROVIDE_EVIDENCE

    # -- the development branch -------------------------------------------

    def test_genuine_gap_without_a_payload_pauses_for_the_payload(self):
        loop, seams = _loop(
            capability_gap=_unsupported()
        )
        result = loop.run("Convert memory_service archive format")
        assert result.status is LoopStatus.AWAITING_INPUT
        assert result.stage is LoopStage.PLANNING
        assert result.action is LoopAction.PROVIDE_CHANGE_PAYLOAD
        assert result.specification is not None
        assert seams["development"].calls == []  # nothing invented

    def test_genuine_gap_without_authorization_stops_at_the_approval_boundary(self):
        loop, seams = _loop(
            capability_gap=_unsupported()
        )
        result = loop.run(
            "Convert memory_service archive format",
            code_changes=(("mod.py", PASS_CODE),),
            test_files=(("test_mod.py", PASS_TEST),),
        )
        assert result.status is LoopStatus.AWAITING_APPROVAL
        assert result.action is LoopAction.APPROVE_PROPOSAL
        assert result.stage is LoopStage.PLANNING
        assert result.proposal_id == "DEV-1"
        assert result.approval_request_id == "APPR-1"
        assert result.awaiting is True
        assert result.executed is False
        _, kwargs = seams["development"].calls[0]
        assert kwargs["authorization"] is None
        assert kwargs["proposal_id"] == ""

    def test_refused_specification_never_reaches_development(self):
        loop, seams = _loop(
            capability_gap=_unsupported(),
            specification=_Recorder(_spec("refused", reason="not a genuine gap")),
        )
        result = loop.run("Convert memory_service archive format")
        assert result.status is LoopStatus.REFUSED
        assert result.action is LoopAction.REVISE_DESIGN
        assert result.reason == "not a genuine gap"
        assert seams["development"].calls == []

    @pytest.mark.parametrize(
        "stage, status, action",
        [
            (
                SelfDevelopmentStage.PROMOTION_REVIEW.value,
                LoopStatus.AWAITING_PROMOTION,
                LoopAction.OWNER_PROMOTION,
            ),
            (
                SelfDevelopmentStage.VERIFICATION.value,
                LoopStatus.AWAITING_PROMOTION,
                LoopAction.OWNER_PROMOTION,
            ),
            (
                SelfDevelopmentStage.NOT_PROMOTABLE.value,
                LoopStatus.NOT_PROMOTABLE,
                LoopAction.ADDRESS_FAILURE,
            ),
            (
                SelfDevelopmentStage.REFUSED.value,
                LoopStatus.REFUSED,
                LoopAction.PROVIDE_AUTHORIZATION,
            ),
            (
                SelfDevelopmentStage.FAILED.value,
                LoopStatus.FAILED,
                LoopAction.ADDRESS_FAILURE,
            ),
        ],
    )
    def test_development_stages_map_onto_the_loop_state(self, stage, status, action):
        loop, _m = _loop(
            capability_gap=_unsupported(),
            development=_Recorder(_development(stage)),
        )
        result = loop.run(
            "Convert memory_service archive format",
            code_changes=(("mod.py", PASS_CODE),),
        )
        assert result.status is status
        assert result.action is action

    def test_failed_verification_is_never_promotable(self):
        loop, _m = _loop(
            capability_gap=_unsupported(),
            development=_Recorder(
                _development(
                    SelfDevelopmentStage.NOT_PROMOTABLE.value,
                    verification_status="unverified",
                    reasons=("the run was not verified",),
                )
            ),
        )
        result = loop.run(
            "Convert memory_service archive format",
            code_changes=(("mod.py", PASS_CODE),),
        )
        assert result.status is LoopStatus.NOT_PROMOTABLE
        assert result.verified is False
        assert result.promotable is False
        assert result.promotion_request_id == ""
        assert "did not verify" in result.response

    def test_verified_work_reaches_the_promotion_boundary(self):
        loop, _m = _loop(
            capability_gap=_unsupported(),
            development=_Recorder(
                _development(
                    SelfDevelopmentStage.PROMOTION_REVIEW.value,
                    verification_status="verified",
                    promotion_request_id="PROM-1",
                    evidence=("changed files: mod.py", "verification: status=SUCCESS"),
                )
            ),
        )
        result = loop.run(
            "Convert memory_service archive format",
            code_changes=(("mod.py", PASS_CODE),),
        )
        assert result.status is LoopStatus.AWAITING_PROMOTION
        assert result.verified is True
        assert result.promotable is True
        assert result.promotion_request_id == "PROM-1"
        assert "OWNER decision" in result.response

    def test_unrecognised_development_stage_fails_closed(self):
        loop, _m = _loop(
            capability_gap=_unsupported(),
            development=_Recorder(_development("something-else")),
        )
        result = loop.run(
            "Convert memory_service archive format",
            code_changes=(("mod.py", PASS_CODE),),
        )
        assert result.status is LoopStatus.FAILED
        assert "unrecognised development stage" in result.reason

    # -- fail-closed -------------------------------------------------------

    def test_empty_request_is_refused(self):
        for bad in ("", "   ", None, 42):
            result = IntegratedIntelligenceLoop().run(bad)
            assert result.status is LoopStatus.REFUSED
            assert result.action is LoopAction.NONE
            assert "non-empty request" in result.reason

    def test_missing_seam_fails_closed_naming_the_stage(self):
        loop = IntegratedIntelligenceLoop(seams=LoopSeams())
        result = loop.run("do something")
        assert result.status is LoopStatus.FAILED
        assert result.stage is LoopStage.UNDERSTANDING
        assert "knowledge_need capability is not wired" in result.reason

    def test_raising_seam_fails_closed_naming_the_stage(self):
        loop, _m = _loop(knowledge_need=_Recorder(error=RuntimeError("boom")))
        result = loop.run("do something")
        assert result.status is LoopStatus.FAILED
        assert "knowledge_need stage failed closed" in result.reason

    def test_later_stage_failure_names_that_stage(self):
        loop, _m = _loop(
            capability_gap=_unsupported(),
            specification=_Recorder(error=ValueError("boom")),
        )
        result = loop.run("Convert memory_service archive format")
        assert result.status is LoopStatus.FAILED
        assert result.stage is LoopStage.SPECIFICATION


# ---------------------------------------------------------------------------
# 2. Refresh — observed by default, governed only on explicit request
# ---------------------------------------------------------------------------


class TestRefresh:
    def test_stale_knowledge_is_observed_not_fetched(self):
        loop, seams = _loop(
            refresh_requests=_Recorder((_Obj(required=True, action="research"),)),
        )
        result = loop.run("What is the current release of the Zorblax protocol?")
        assert seams["refresh"].calls == []  # observing only, never fetching
        assert len(result.refresh_requests) == 1  # the finding is reported
        assert "refresh: 1 required of 1" in " ".join(result.evidence)

    def test_stale_knowledge_names_the_source_remedy_when_it_is_the_verdict(self):
        loop, seams = _loop(
            refresh_requests=_Recorder((_Obj(required=True, action="research"),)),
            capability_gap=_Recorder(
                _gap(CapabilityGapKind.MISSING_KNOWLEDGE.value)
            ),
        )
        result = loop.run("What is the current release of the Zorblax protocol?")
        assert result.action is LoopAction.AUTHORIZE_SOURCE
        assert seams["refresh"].calls == []  # still never fetched by the loop

    def test_explicit_refresh_uses_the_governed_seam(self):
        loop, seams = _loop(
            refresh_requests=_Recorder((_Obj(required=True, action="research"),)),
        )
        result = loop.run(
            "What is the current release of the Zorblax protocol?", refresh=True
        )
        assert seams["refresh"].calls
        assert any("refresh outcomes" in line for line in result.evidence)


# ---------------------------------------------------------------------------
# 3. Resume — the human boundary never loses state
# ---------------------------------------------------------------------------


class TestResume:
    def _awaiting(self, loop, seams):
        result = loop.run(
            "Convert memory_service archive format",
            code_changes=(("mod.py", PASS_CODE),),
        )
        assert result.status is LoopStatus.AWAITING_APPROVAL
        return result

    def test_resume_with_authorization_continues_the_same_proposal(self):
        loop, seams = _loop(
            capability_gap=_unsupported(),
            development=_Recorder(_development()),
        )
        first = self._awaiting(loop, seams)
        seams["development"].value = _development(
            SelfDevelopmentStage.PROMOTION_REVIEW.value,
            proposal_id="DEV-1",
            verification_status="verified",
            promotion_request_id="PROM-1",
        )
        resumed = loop.resume(first, authorization=_Obj())
        assert resumed.status is LoopStatus.AWAITING_PROMOTION
        _, kwargs = seams["development"].calls[-1]
        assert kwargs["proposal_id"] == "DEV-1"  # the SAME persisted proposal
        assert kwargs["authorization"] is not None

    def test_resume_without_authorization_is_a_deterministic_no_op(self):
        loop, seams = _loop(
            capability_gap=_unsupported()
        )
        first = self._awaiting(loop, seams)
        again = loop.resume(first)
        assert again.status is LoopStatus.AWAITING_APPROVAL
        assert again.proposal_id == first.proposal_id
        assert again.action is first.action
        assert again.specification is first.specification  # the same preserved design
        assert again.evidence == first.evidence  # nothing was lost or invented

    def test_resume_preserves_the_prefix_without_re_deriving_it(self):
        loop, seams = _loop(
            capability_gap=_unsupported()
        )
        first = self._awaiting(loop, seams)
        assert len(seams["knowledge_need"].calls) == 1
        loop.resume(first, authorization=_Obj())
        assert len(seams["knowledge_need"].calls) == 1  # never re-run
        assert len(seams["capability_gap"].calls) == 1
        assert len(seams["specification"].calls) == 1
        assert len(seams["development"].calls) == 2  # only this stage re-runs

    def test_resume_of_the_payload_pause_continues_once_supplied(self):
        loop, seams = _loop(
            capability_gap=_unsupported()
        )
        paused = loop.run("Convert memory_service archive format")
        assert paused.status is LoopStatus.AWAITING_INPUT
        still = loop.resume(paused)
        assert still.status is LoopStatus.AWAITING_INPUT
        assert seams["development"].calls == []
        resumed = loop.resume(paused, code_changes=(("mod.py", PASS_CODE),))
        assert resumed.status is LoopStatus.AWAITING_APPROVAL

    def test_resume_of_a_terminal_result_is_refused(self):
        loop, _m = _loop()
        answered = loop.run("Summarize the Zorblax protocol")
        resumed = loop.resume(answered)
        assert resumed.status is LoopStatus.REFUSED
        assert "not at a resumable boundary" in resumed.reason

    def test_resume_of_a_promotion_boundary_is_refused(self):
        loop, _m = _loop(
            capability_gap=_unsupported(),
            development=_Recorder(
                _development(
                    SelfDevelopmentStage.PROMOTION_REVIEW.value,
                    verification_status="verified",
                )
            ),
        )
        done = loop.run(
            "Convert memory_service archive format",
            code_changes=(("mod.py", PASS_CODE),),
        )
        resumed = loop.resume(done)
        assert resumed.status is LoopStatus.REFUSED
        assert "separate OWNER decision" in resumed.reason

    def test_resume_without_state_is_refused(self):
        result = IntegratedIntelligenceLoop().resume(None)
        assert result.status is LoopStatus.REFUSED
        assert "no preserved loop state" in result.response


# ---------------------------------------------------------------------------
# 4. Evidence, determinism, immutability, model independence
# ---------------------------------------------------------------------------


class TestEvidenceAndDeterminism:
    def test_evidence_carries_the_cycle_provenance(self):
        loop, _m = _loop(
            knowledge_need=_Recorder(_need("missing", "actionable")),
            capability_gap=_Recorder(
                _gap(CapabilityGapKind.UNSUPPORTED_CAPABILITY.value)
            ),
            development=_Recorder(
                _development(
                    SelfDevelopmentStage.PROMOTION_REVIEW.value,
                    verification_status="verified",
                    evidence=("changed files: mod.py", "verification: status=SUCCESS"),
                )
            ),
        )
        result = loop.run(
            "Convert memory_service archive format",
            code_changes=(("mod.py", PASS_CODE),),
            test_files=(("test_mod.py", PASS_TEST),),
        )
        joined = " ".join(result.evidence)
        assert "knowledge need: missing / actionable" in joined
        assert "research: researched" in joined
        assert "provenance: 1 claims, 1 sources" in joined
        assert "retention: 1 retained" in joined
        assert "temporal: ok" in joined
        assert "monitoring: ok" in joined
        assert "capability assessment: unsupported_capability" in joined
        assert "specification: spec:1 specified" in joined
        assert "development: promotion_review" in joined
        assert "changed files: mod.py" in joined

    def test_deterministic_and_serializable(self):
        def _run_once():
            loop, _m = _loop()
            return loop.run("Summarize the Zorblax protocol")

        first, second = _run_once(), _run_once()
        assert first == second
        json.dumps(first.to_dict())

    def test_result_is_immutable_and_bounded(self):
        loop, _m = _loop()
        result = loop.run("x" * 5000)
        with pytest.raises(Exception):
            result.status = LoopStatus.FAILED  # type: ignore[misc]
        assert len(result.request) <= 300
        assert len(result.evidence) <= 16

    def test_module_is_model_independent(self):
        source = inspect.getsource(loop_module)
        for banned in (
            "atlas.ai",
            "AIService",
            "ai_service",
            "openai",
            "import requests",
            "urllib",
            "socket",
        ):
            assert banned not in source


# ---------------------------------------------------------------------------
# 5. Real Atlas/kernel validation
# ---------------------------------------------------------------------------


@pytest.fixture
def kernel(tmp_path, monkeypatch):
    """A fully isolated real kernel: EVERY sqlite-backed store pinned to tmp."""
    db_path = tmp_path / "kernel.db"
    for info in pkgutil.iter_modules(storage_pkg.__path__):
        try:
            module = __import__(f"atlas.storage.{info.name}", fromlist=["*"])
        except Exception:  # noqa: BLE001
            continue
        for attr in dir(module):
            obj = getattr(module, attr)
            if isinstance(obj, type) and hasattr(obj, "DEFAULT_DB_PATH"):
                monkeypatch.setattr(obj, "DEFAULT_DB_PATH", db_path)
    from atlas.kernel.atlas import Atlas

    atlas = Atlas()
    atlas.start()
    try:
        yield atlas
    finally:
        atlas.shutdown()


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


def _genuine_gap_request(atlas):
    _seed(
        atlas._research_storage,
        "memory",
        "The memory_service convert archive format operation is documented.",
    )
    return "Convert memory_service archive format"


def _git_head():
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
    ).stdout.strip()


class TestRealKernelEndToEnd:
    def test_grounded_gap_to_promotion_boundary_with_owner_interruption(self, kernel):
        request = _genuine_gap_request(kernel)
        head = _git_head()

        # 1. request -> understanding -> knowledge -> gap -> specification -> proposal
        first = kernel.integrated_loop(
            request,
            code_changes=(("sandbox_mod.py", PASS_CODE),),
            test_files=(("test_sandbox_mod.py", PASS_TEST),),
            target_components=("sandbox_mod",),
        )
        assert first.status is LoopStatus.AWAITING_APPROVAL
        assert first.action is LoopAction.APPROVE_PROPOSAL
        assert first.proposal_id.startswith("DEV-")
        assert first.approval_request_id.startswith("APPR-")
        assert first.stage is LoopStage.PLANNING
        assert first.executed is False
        assert first.specification is not None
        assert first.specification.is_specified
        assert first.gap.kind is CapabilityGapKind.UNSUPPORTED_CAPABILITY
        # nothing ran, nothing was promoted, the live repo is untouched
        assert kernel.pending_promotion_reviews() == []
        assert _git_head() == head
        assert not (REPO_ROOT / "sandbox_mod.py").exists()

        # 2. resuming without authorization changes nothing
        stalled = kernel.resume_integrated_loop(first)
        assert stalled.status is LoopStatus.AWAITING_APPROVAL
        assert stalled.proposal_id == first.proposal_id

        # 3. the EXISTING human approval boundary, then resume
        proposal = kernel.confirm_development_approval(
            kernel.session_context, first.proposal_id
        )
        assert proposal.status.name == "APPROVED"
        final = kernel.resume_integrated_loop(first)
        assert final.status is LoopStatus.AWAITING_PROMOTION
        assert final.action is LoopAction.OWNER_PROMOTION
        assert final.stage is LoopStage.PROMOTION
        assert final.verified is True
        assert final.promotable is True
        assert final.promotion_request_id
        assert final.development.execution_status == "SUCCESS"
        # verification really happened, in a sandbox, never in the live repo
        assert _git_head() == head
        assert not (REPO_ROOT / "sandbox_mod.py").exists()
        assert any(
            review.get("proposal_id") == first.proposal_id
            for review in kernel.pending_promotion_reviews()
        )
        # provenance survived the whole cycle
        joined = " ".join(final.evidence)
        assert "capability assessment: unsupported_capability" in joined
        assert first.specification.spec_id in joined
        assert "verification" in joined

    @pytest.mark.parametrize(
        "text, kwargs, expected_gap, expected_action",
        [
            (
                "Summarize the Zorblax protocol",
                {},
                CapabilityGapKind.SUPPORTED,
                LoopAction.NONE,
            ),
            (
                "Have an open-ended chat about anything",
                {"capability": "open_conversation"},
                CapabilityGapKind.TEMPORARILY_BLOCKED,
                LoopAction.NONE,
            ),
            (
                "Verify the development result",
                {"capability": "verify"},
                CapabilityGapKind.GOVERNED,
                LoopAction.NONE,
            ),
        ],
    )
    def test_no_genuine_gap_never_reaches_development(
        self, kernel, text, kwargs, expected_gap, expected_action
    ):
        result = kernel.integrated_loop(text, **kwargs)
        assert result.status is LoopStatus.ANSWERED
        assert result.gap.kind is expected_gap
        assert result.action is expected_action
        assert result.proposal_id == ""
        assert kernel.pending_promotion_reviews() == []

    def test_missing_knowledge_is_not_a_capability_gap(self, kernel):
        result = kernel.integrated_loop("Convert the Zorblax archive format")
        assert result.status is LoopStatus.ANSWERED
        assert result.gap.kind is CapabilityGapKind.MISSING_KNOWLEDGE
        # the knowledge verdict reports the concrete remedy it established
        assert result.action is LoopAction.AUTHORIZE_SOURCE
        assert "research: no_authorized_source" in " ".join(result.evidence)
        assert result.specification is None
        assert "no capability claim is made" in result.response

    def test_insufficient_research_fails_closed_without_a_gap_claim(self, kernel):
        # deny-by-default: no authorized host, so nothing can be researched
        result = kernel.integrated_loop("What is the current release of Zorblax?")
        assert result.status is LoopStatus.ANSWERED
        assert result.research is not None
        assert result.research.status is ResearchStatus.NO_AUTHORIZED_SOURCE
        assert result.action is LoopAction.AUTHORIZE_SOURCE
        assert result.specification is None
        assert result.development is None

    def test_ambiguous_request_stops_the_loop(self, kernel):
        result = kernel.integrated_loop("Do it", ambiguous=True)
        assert result.status is LoopStatus.ANSWERED
        assert result.gap.kind is CapabilityGapKind.AMBIGUOUS
        assert result.action is LoopAction.RESOLVE_AMBIGUITY
        assert result.development is None

    def test_missing_knowledge_payload_pauses_before_development(self, kernel):
        request = _genuine_gap_request(kernel)
        result = kernel.integrated_loop(request)
        assert result.status is LoopStatus.AWAITING_INPUT
        assert result.action is LoopAction.PROVIDE_CHANGE_PAYLOAD
        assert result.specification.is_specified
        assert result.proposal_id == ""  # no proposal was prepared

    def test_failed_verification_never_promoted(self, kernel):
        request = _genuine_gap_request(kernel)
        head = _git_head()
        first = kernel.integrated_loop(
            request,
            code_changes=(("sandbox_mod.py", PASS_CODE),),
            test_files=(("test_sandbox_mod.py", FAIL_TEST),),
            target_components=("sandbox_mod",),
        )
        kernel.confirm_development_approval(kernel.session_context, first.proposal_id)
        final = kernel.resume_integrated_loop(first)
        assert final.status is LoopStatus.NOT_PROMOTABLE
        assert final.verified is False
        assert final.promotable is False
        assert final.promotion_request_id == ""
        assert kernel.pending_promotion_reviews() == []
        assert _git_head() == head

    def test_invalid_authorization_is_refused_without_execution(self, kernel):
        request = _genuine_gap_request(kernel)
        first = kernel.integrated_loop(
            request,
            code_changes=(("sandbox_mod.py", PASS_CODE),),
            test_files=(("test_sandbox_mod.py", PASS_TEST),),
        )
        assert first.status is LoopStatus.AWAITING_APPROVAL

        class _Bogus:
            def is_valid_for(self, proposal):
                return False

        refused = kernel.resume_integrated_loop(first, authorization=_Bogus())
        assert refused.status is LoopStatus.REFUSED
        assert refused.action is LoopAction.PROVIDE_AUTHORIZATION
        assert refused.executed is False
        assert kernel.pending_promotion_reviews() == []

    def test_unknown_proposal_state_fails_closed(self, kernel):
        request = _genuine_gap_request(kernel)
        first = kernel.integrated_loop(
            request,
            code_changes=(("sandbox_mod.py", PASS_CODE),),
            test_files=(("test_sandbox_mod.py", PASS_TEST),),
        )
        lost = kernel.resume_integrated_loop(replace(first, proposal_id="DEV-nope"))
        assert lost.status is LoopStatus.FAILED
        assert lost.stage is LoopStage.PLANNING
        assert "development stage failed closed" in lost.reason
        assert kernel.pending_promotion_reviews() == []

    def test_loop_uses_no_network(self, kernel, monkeypatch):
        def _blocked(*args, **kwargs):
            raise AssertionError("the integrated loop must not touch the network")

        monkeypatch.setattr(socket.socket, "connect", _blocked)
        request = _genuine_gap_request(kernel)
        first = kernel.integrated_loop(
            request,
            code_changes=(("sandbox_mod.py", PASS_CODE),),
            test_files=(("test_sandbox_mod.py", PASS_TEST),),
            target_components=("sandbox_mod",),
        )
        kernel.confirm_development_approval(kernel.session_context, first.proposal_id)
        final = kernel.resume_integrated_loop(first)
        assert final.status is LoopStatus.AWAITING_PROMOTION
        assert final.verified is True
        assert final.promotable is True


class TestPreservation:
    def test_tick_is_unchanged(self, kernel):
        source = inspect.getsource(kernel.tick)
        for banned in ("integrated", "loop", "monitor", "refresh", "freshness"):
            assert banned not in source
        assert "settle" in source

    def test_steps_1_to_24_preserved(self, kernel):
        question = "What is the current release of the Zorblax protocol?"
        assert kernel.knowledge_need(question).kind is KnowledgeNeedKind.MISSING
        outcome = kernel.research_knowledge_need(question)
        assert outcome.status is ResearchStatus.NO_AUTHORIZED_SOURCE
        assert kernel.research_provenance(outcome).claims == ()
        assert kernel.knowledge_retention(outcome).records == ()
        assert kernel.retained_knowledge(question).status.value == "empty"
        assert kernel.temporal_knowledge(question).entries == ()
        assert kernel.refresh_requests(question) == ()
        assert kernel.monitor_knowledge(question).observations == ()
        gap = kernel.capability_gap(question)
        assert gap.kind is CapabilityGapKind.MISSING_KNOWLEDGE
        spec = kernel.capability_specification(question)
        assert spec.status is SpecificationStatus.REFUSED
        assert kernel.capability_contract("research")["state"] == "available"
        assert kernel.capability_specification(question).is_specified is False
        assert kernel.development_planner is not None
