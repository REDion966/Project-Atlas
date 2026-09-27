"""Evidence-based gap analysis over an InvestigationReport.

Covers the new bounded capability (`EvidenceGapAnalyzer`) and its conversational
integration:

* the pure analyzer: evidence-traceable gaps, multiple findings per gap,
  honest insufficient result, no fabricated gaps on an empty report, and
  determinism;
* the conversation flow: investigation -> findings reference -> gap analysis,
  consuming the retained report without re-investigating or overwriting the
  retained investigation/result;
* routing safety: genuine investigations are untouched; an analysis request
  without prior evidence fails closed;
* model independence and governance non-leak.

This capability is deliberately distinct from `InvestigationSynthesizer`
(which ranks components); it reports structured *gaps*, not a prioritisation.
"""

from __future__ import annotations

from atlas.conversation.builtin_response import BuiltinResponseService
from atlas.conversation.conversation_service import ConversationService
from atlas.conversation.evidence_gap_analysis import (
    EvidenceGapAnalyzer,
    GapAnalysisReport,
    GapCategory,
    GapSufficiency,
    is_evidence_gap_analysis_request,
)
from atlas.conversation.investigation import (
    InvestigationFinding,
    InvestigationReport,
)
from atlas.conversation.task_intake import TaskIntake


class _FailingAI:
    """Any provider contact is a failure: this path is deterministic."""

    calls = 0

    def chat(self, prompt, routing_context=None):
        _FailingAI.calls += 1
        raise RuntimeError("provider must not be contacted")

    def stream_chat(self, prompt, routing_context=None):
        _FailingAI.calls += 1

        def _generator():
            raise RuntimeError("provider must not be contacted")
            yield ""  # pragma: no cover

        return _generator()


class _RecordingInvestigation:
    """Deterministic investigation double returning a fixed report."""

    def __init__(self, report: InvestigationReport) -> None:
        self._report = report
        self.calls: list[dict[str, str]] = []

    def investigate(self, target: str, *, objective: str = "") -> InvestigationReport:
        self.calls.append({"target": target, "objective": objective})
        return self._report


def _report_with_gap() -> InvestigationReport:
    """A report whose evidence demonstrates one concrete gap."""
    return InvestigationReport(
        target="Investigate the memory architecture",
        objective="memory architecture",
        diagnosis="Identified 3 relevant component(s).",
        components=(
            "atlas.memory.manager",
            "atlas.memory.repository",
            "atlas.memory.untested",
        ),
        findings=(
            InvestigationFinding(
                category="dependency",
                description=(
                    "'atlas.memory.manager' depends on: atlas.memory.repository"
                ),
                location="atlas.memory.manager",
            ),
            InvestigationFinding(
                category="test",
                description="Found 2 test file(s) referencing 'manager'",
                evidence="tests/test_memory_manager.py",
                location="tests/",
            ),
            InvestigationFinding(
                category="test",
                description="Found 1 test file(s) referencing 'repository'",
                evidence="tests/test_memory_repository.py",
                location="tests/",
            ),
            InvestigationFinding(
                category="reference",
                description="Found 3 reference(s) to 'memory' in atlas/memory/",
                evidence="atlas/memory/manager.py",
                location="atlas/memory/",
            ),
        ),
        affected_files=(
            "atlas/memory/manager.py",
            "tests/test_memory_manager.py",
        ),
        recommended_next_step="Review the identified components.",
        modification_status="NONE",
    )


def _svc() -> BuiltinResponseService:
    from atlas.lifecycle.component_registry import ComponentRegistry
    from atlas.self_knowledge.architecture_model import build_architecture_model

    model = build_architecture_model(ComponentRegistry())
    return BuiltinResponseService(architecture_model_provider=lambda: model)


def _service(report: InvestigationReport | None) -> ConversationService:
    _FailingAI.calls = 0
    recording = _RecordingInvestigation(report) if report is not None else None
    return ConversationService(
        _FailingAI(),
        task_intake=TaskIntake(),
        builtin_response=_svc(),
        investigation_service=recording,
    )


# ---------------------------------------------------------------------------
# A. Pure capability
# ---------------------------------------------------------------------------


class TestEvidenceGapAnalyzer:
    def test_untested_component_is_reported_as_a_traceable_gap(self):
        result = EvidenceGapAnalyzer().analyze(_report_with_gap())

        assert isinstance(result, GapAnalysisReport)
        assert result.modification_status == "NONE"
        assert not result.insufficient_evidence
        assert [g.component for g in result.gaps] == ["atlas.memory.untested"]

        gap = result.gaps[0]
        assert gap.category is GapCategory.UNTESTED_COMPONENT
        assert gap.sufficiency is GapSufficiency.SUFFICIENT
        # Observed evidence is separated from the bounded interpretation.
        assert "no test finding references 'untested'" in gap.observation
        assert "no test evidence" in gap.interpretation
        # Traceability: the gap cites the actual report finding(s).
        assert gap.evidence
        assert all(c.category in {"dependency", "reference"} for c in gap.evidence)

    def test_multiple_findings_can_contribute_to_one_gap(self):
        result = EvidenceGapAnalyzer().analyze(_report_with_gap())
        gap = result.gaps[0]
        # The component's directory-level reference finding is cited alongside
        # any component-level evidence, so the gap rests on >1 report fact.
        assert len(gap.evidence) >= 1
        assert {c.category for c in gap.evidence} <= {"dependency", "reference"}

    def test_uncovered_component_is_reported_and_marked_insufficient(self):
        report = InvestigationReport(
            target="t",
            components=("atlas.x.ghost",),
            findings=(
                InvestigationFinding(
                    category="test",
                    description="Found 1 test file(s) referencing 'other'",
                    location="tests/",
                ),
            ),
        )
        result = EvidenceGapAnalyzer().analyze(report)
        assert [g.category for g in result.gaps] == [GapCategory.UNCOVERED_COMPONENT]
        assert result.gaps[0].sufficiency is GapSufficiency.INSUFFICIENT

    def test_no_test_evidence_is_insufficient_not_fabricated(self):
        report = InvestigationReport(
            target="t",
            components=("atlas.x.a",),
            findings=(
                InvestigationFinding(
                    category="reference",
                    description="Found 3 reference(s) to 'x' in atlas/",
                    location="atlas/",
                ),
            ),
        )
        result = EvidenceGapAnalyzer().analyze(report)
        assert result.insufficient_evidence
        assert result.gaps == ()

    def test_empty_report_fabricates_nothing(self):
        result = EvidenceGapAnalyzer().analyze(InvestigationReport(target="nothing"))
        assert result.insufficient_evidence
        assert result.gaps == ()
        assert result.modification_status == "NONE"

    def test_test_modules_are_not_flagged_as_untested(self):
        report = InvestigationReport(
            target="t",
            components=("tests.test_thing",),
            findings=(
                InvestigationFinding(
                    category="test",
                    description="Found 1 test file(s) referencing 'other'",
                    location="tests/",
                ),
            ),
        )
        assert EvidenceGapAnalyzer().analyze(report).gaps == ()

    def test_deterministic_repeat(self):
        a = EvidenceGapAnalyzer().analyze(_report_with_gap())
        b = EvidenceGapAnalyzer().analyze(_report_with_gap())
        assert a.to_dict() == b.to_dict()

    def test_result_is_not_a_prioritisation(self):
        # Distinct from InvestigationSynthesizer: no ranking / recommended focus.
        result = EvidenceGapAnalyzer().analyze(_report_with_gap())
        assert not hasattr(result, "ranked_components")
        assert not hasattr(result, "recommended_focus")
        assert result.evidence_basis == ("dependency", "reference", "test")

    def test_recognizer_is_bounded(self):
        assert is_evidence_gap_analysis_request(
            "Analyze the findings and identify the concrete gaps."
        )
        assert is_evidence_gap_analysis_request("What gaps did the findings show?")
        assert is_evidence_gap_analysis_request("Analyze the findings.")
        # A generic analysis/investigation request is never matched.
        assert not is_evidence_gap_analysis_request("Analyze the memory subsystem.")
        assert not is_evidence_gap_analysis_request(
            "Investigate the conversation subsystem."
        )
        assert not is_evidence_gap_analysis_request("What did you find?")
        assert not is_evidence_gap_analysis_request("Identify the concrete gaps.")
        # "the findings of X" names a fresh object, not the retained findings.
        assert not is_evidence_gap_analysis_request(
            "Analyze the findings of the security audit."
        )


# ---------------------------------------------------------------------------
# B. Conversational integration + C. State safety
# ---------------------------------------------------------------------------


class TestConversationalGapAnalysis:
    def _three_turns(self):
        report = _report_with_gap()
        service = _service(report)
        turn1 = service.send("Investigate the memory architecture.")
        turn2 = service.send("What did you find?")
        before = service.state_manager.state
        turn3 = service.send("Analyze the findings and identify the concrete gaps.")
        return service, turn1, turn2, turn3, before

    def test_investigation_is_retained_and_findings_reference_works(self):
        _service_, turn1, turn2, _turn3, _before = self._three_turns()
        assert turn1.metadata["investigation"]["modification_status"] == "NONE"
        assert turn2.metadata.get("builtin_intent") == "reference"

    def test_gap_analysis_consumes_the_retained_report(self):
        _service_, _t1, _t2, turn3, _before = self._three_turns()
        payload = turn3.metadata.get("gap_analysis")
        assert payload is not None
        assert payload["status"] == "complete"
        assert payload["gap_count"] == 1
        assert payload["gaps"][0]["component"] == "atlas.memory.untested"
        assert "Evidence Gap Analysis" in turn3.content

    def test_analysis_does_not_start_a_new_investigation_or_overwrite_state(self):
        service, _t1, _t2, _t3, before = self._three_turns()
        state = service.state_manager.state
        assert state.current_investigation == before.current_investigation
        assert state.latest_result == before.latest_result
        assert state.last_operation == before.last_operation
        assert state.active_proposal_id == before.active_proposal_id

    def test_analysis_is_model_free_and_governance_neutral(self):
        _service_, _t1, _t2, turn3, _before = self._three_turns()
        for key in ("approval", "execution", "promotion", "authorization", "planning"):
            assert key not in turn3.metadata, key
        assert turn3.metadata.get("model_used") is not True
        assert _FailingAI.calls == 0


# ---------------------------------------------------------------------------
# D. Routing safety
# ---------------------------------------------------------------------------


class TestRoutingSafety:
    def test_genuine_investigation_is_unchanged(self):
        report = _report_with_gap()
        recording = _RecordingInvestigation(report)
        _FailingAI.calls = 0
        service = ConversationService(
            _FailingAI(), task_intake=TaskIntake(), investigation_service=recording
        )
        message = service.send("Investigate the memory architecture.")
        assert len(recording.calls) == 1
        assert "investigation" in message.metadata
        assert "gap_analysis" not in message.metadata

    def test_analysis_without_prior_evidence_fails_closed(self):
        service = _service(None)
        message = service.send("Analyze the findings and identify the concrete gaps.")
        assert message.metadata["gap_analysis"]["status"] == "no_investigation"
        assert "investigation" not in message.metadata
        assert _FailingAI.calls == 0

    def test_generic_analysis_phrasing_is_not_hijacked(self):
        report = _report_with_gap()
        recording = _RecordingInvestigation(report)
        _FailingAI.calls = 0
        service = ConversationService(
            _FailingAI(), task_intake=TaskIntake(), investigation_service=recording
        )
        message = service.send("Analyze the memory subsystem.")
        # A generic analysis request keeps its existing investigation route.
        assert len(recording.calls) == 1
        assert "gap_analysis" not in message.metadata

    def test_reference_followup_still_answered_by_existing_route(self):
        service, _t1, _t2, _t3, _before = TestConversationalGapAnalysis()._three_turns()
        message = service.send("What did you find?")
        assert message.metadata.get("builtin_intent") == "reference"

    def test_analysis_output_is_deterministic(self):
        service = _service(_report_with_gap())
        service.send("Investigate the memory architecture.")
        first = service.send("Analyze the findings and identify the concrete gaps.")
        second = service.send("Analyze the findings and identify the concrete gaps.")
        assert first.content == second.content
