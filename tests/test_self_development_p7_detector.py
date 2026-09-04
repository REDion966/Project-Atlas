"""P7.2 — Pure conversational development-need detector contract tests.

These tests pin the P7.2 detector's behavior and boundaries against current
seams. The detector is detection-only: it must never propose, approve,
execute, or promote anything, and it must remain pure (no I/O, no external
calls, no evolution/orchestration/advisory runtime imports).

The P7.1 contract tests (tests/test_self_development_p7.py) remain the
authoritative seam-level contracts; this file adds the detector-specific
contracts.
"""

from __future__ import annotations

import ast
import pathlib
from datetime import datetime, timezone

import pytest

from atlas.conversation.development_need_detector import (
    AdvisorySignal,
    DetectedDevelopmentNeed,
    DevelopmentNeedDetector,
    DevelopmentSignalKind,
)
from atlas.conversation.task_intake import AmbiguityReport, TaskIntake, TaskSpec, TaskType

_ROOT = pathlib.Path(__file__).resolve().parents[1]


def _spec(
    text,
    *,
    now=None,
):
    return TaskIntake(now=now or datetime(2026, 9, 3, 12, 0, 0, tzinfo=timezone.utc)).intake(text)


def _make_spec(
    *,
    task_type=TaskType.ACTION_REQUEST,
    intent="run the quantum stabilizer diagnostic",
    goal=None,
    needs_clarification=False,
    constraints=(),
    priorities=(),
    success_criteria=(),
    context=None,
    ambiguity_score=0.0,
    ambiguities=(),
    clarification_questions=(),
):
    return TaskSpec(
        task_id="abc123",
        task_type=task_type,
        intent=intent,
        goal=goal or f"respond: {intent}",
        constraints=constraints,
        priorities=priorities,
        success_criteria=success_criteria,
        context=context or {},
        ambiguity=AmbiguityReport(
            ambiguity_score=ambiguity_score,
            ambiguities=ambiguities,
            clarification_questions=clarification_questions,
        ),
        confidence=0.6,
        needs_clarification=needs_clarification,
        source="deterministic",
        verified=True,
        model_metadata={},
        created_at=datetime(2026, 9, 3, 12, 0, 0, tzinfo=timezone.utc),
        input_hash="abc123",
    )


@pytest.fixture
def detector():
    return DevelopmentNeedDetector()


# ---------------------------------------------------------------------------
# Signal detection
# ---------------------------------------------------------------------------


class TestCapabilityGapDetection:
    def test_missing_capability_with_unresolved_is_capability_gap(self, detector):
        spec = _make_spec(intent="run the quantum stabilizer diagnostic")
        result = detector.detect(
            spec,
            resolution=False,
            missing_capability="quantum_stabilizer",
        )
        assert isinstance(result, DetectedDevelopmentNeed)
        assert result.signal_kind == DevelopmentSignalKind.CAPABILITY_GAP.value
        assert "quantum_stabilizer" in result.reason
        assert result.capability == "quantum_stabilizer"

    def test_unresolved_without_capability_is_unresolved_action(self, detector):
        spec = _make_spec(intent="generate the quarterly report")
        result = detector.detect(spec, resolution=False)
        assert isinstance(result, DetectedDevelopmentNeed)
        assert result.signal_kind == DevelopmentSignalKind.UNRESOLVED_ACTION.value
        assert result.capability == "generate the quarterly report"

    def test_unresolved_requires_false_resolution_signal(self, detector):
        """resolution=None is insufficient evidence; never invent a gap."""
        spec = _make_spec(intent="generate the quarterly report")
        assert detector.detect(spec) is None
        assert detector.detect(spec, resolution=None) is None

    def test_resolved_action_is_not_a_gap(self, detector):
        spec = _make_spec(intent="echo hello")
        assert detector.detect(spec, resolution=True) is None


class TestRepeatedClarificationDetection:
    def test_below_threshold_returns_none(self, detector):
        spec = _make_spec(
            intent="make it work",
            needs_clarification=True,
            ambiguity_score=0.5,
        )
        assert detector.detect(spec, clarification_count=0) is None
        assert detector.detect(spec, clarification_count=1) is None

    def test_at_or_above_threshold_is_detected(self, detector):
        spec = _make_spec(
            intent="make it work",
            needs_clarification=True,
            ambiguity_score=0.5,
            clarification_questions=("What outcome would tell you this is done?",),
        )
        result = detector.detect(spec, clarification_count=2)
        assert isinstance(result, DetectedDevelopmentNeed)
        assert result.signal_kind == DevelopmentSignalKind.REPEATED_CLARIFICATION.value

    def test_well_specified_action_ignores_clarification_count(self, detector):
        # Even a large clarification_count must not produce a signal for a
        # well-specified, resolvable action.
        spec = _make_spec(intent="echo hello", needs_clarification=False)
        assert detector.detect(spec, resolution=True, clarification_count=5) is None


class TestAdvisorySignalDetection:
    def test_improvement_action_detected(self, detector):
        advisory = AdvisorySignal(
            kind="maintenance_need",
            summary="Self-management review found stale authorizations.",
            suggested_action="atlas.run_self_management_review",
            evidence_ids=("E1",),
            principal_id="owner",
            authority="owner",
        )
        result = detector.detect(None, advisory=advisory)
        assert isinstance(result, DetectedDevelopmentNeed)
        assert result.signal_kind == DevelopmentSignalKind.ADVISORY_OPPORTUNITY.value
        assert result.principal_id == "owner"
        assert result.authority == "owner"

    def test_non_improvement_action_is_ignored(self, detector):
        advisory = AdvisorySignal(
            kind="environment_change",
            summary="Provider X changed.",
            suggested_action="atlas.run_operation_cycle",
            evidence_ids=("E1",),
        )
        assert detector.detect(None, advisory=advisory) is None

    def test_empty_advisory_is_ignored(self, detector):
        assert detector.detect(None, advisory=AdvisorySignal()) is None

    def test_advisory_never_becomes_need_proposal(self, detector):
        """Advisory detection is a DETECTION signal only: it carries no
        proposal/approval/lifecycle fields and never invokes F9."""
        advisory = AdvisorySignal(
            summary="x",
            suggested_action="atlas.run_development_cycle",
        )
        result = detector.detect(None, advisory=advisory)
        assert isinstance(result, DetectedDevelopmentNeed)
        # The record is deliberately free of any proposal/approval state.
        assert not hasattr(result, "proposal_id")
        assert not hasattr(result, "approval_id")
        assert not hasattr(result, "status")


# ---------------------------------------------------------------------------
# Fail-closed: non-development traffic -> None
# ---------------------------------------------------------------------------


class TestFailClosedNoFalsePositives:
    @pytest.mark.parametrize(
        "text",
        [
            "Hello Atlas, how are you today",
            "What does this module do?",
            "Find the latest research on memory consolidation",
        ],
    )
    def test_non_action_inputs_are_none(self, detector, text):
        spec = _spec(text)
        assert spec.task_type is not TaskType.ACTION_REQUEST
        assert detector.detect(spec) is None
        # Even with a false resolution signal, non-action types never become
        # capability gaps: the detector only considers ACTION requests.
        assert detector.detect(spec, resolution=False) is None

    def test_question_is_none(self, detector):
        spec = _spec("What does this module do?")
        assert spec.task_type is TaskType.QUESTION
        assert detector.detect(spec) is None

    def test_information_request_is_none(self, detector):
        spec = _spec("Find the latest research on memory consolidation")
        assert spec.task_type is TaskType.INFORMATION_REQUEST
        assert detector.detect(spec) is None

    def test_normal_conversation_is_none(self, detector):
        spec = _spec("Hello Atlas, how are you today")
        assert spec.task_type is TaskType.CONVERSATION
        assert detector.detect(spec) is None

    def test_resolvable_action_is_none(self, detector):
        spec = _make_spec(intent="echo hello")
        assert detector.detect(spec, resolution=True) is None

    def test_none_spec_is_none(self, detector):
        assert detector.detect(None) is None


# ---------------------------------------------------------------------------
# Explicit development requests: NEVER rerouted by this detector
# ---------------------------------------------------------------------------


class TestExplicitDevelopmentExcluded:
    def test_explicit_development_request_is_none(self, detector):
        spec = _spec(
            "add a new capability to Atlas for scheduling so that tasks run on time"
        )
        assert spec.task_type is TaskType.DEVELOPMENT_REQUEST
        assert detector.detect(spec) is None
        # Even a fake resolution signal must not reroute an explicit dev
        # request through this detector.
        assert detector.detect(spec, resolution=False) is None

    def test_vague_development_request_is_none(self, detector):
        spec = _spec("improve this module")
        assert spec.task_type is TaskType.DEVELOPMENT_REQUEST
        assert spec.needs_clarification
        assert detector.detect(spec) is None
        # Clarification count must not turn a vague dev request into a gap.
        assert detector.detect(spec, clarification_count=5) is None


# ---------------------------------------------------------------------------
# Determinism + purity + no side effects
# ---------------------------------------------------------------------------


class TestDeterminismAndPurity:
    def test_identical_inputs_identical_output(self, detector):
        spec = _make_spec(intent="run the quantum stabilizer diagnostic")
        a = detector.detect(
            spec,
            resolution=False,
            missing_capability="quantum_stabilizer",
        )
        b = detector.detect(
            spec,
            resolution=False,
            missing_capability="quantum_stabilizer",
        )
        assert a == b
        assert a is not b

    def test_detect_does_not_mutate_spec(self, detector):
        spec = _make_spec(intent="run the quantum stabilizer diagnostic")
        before = spec.to_dict()
        detector.detect(spec, resolution=False, missing_capability="x")
        assert spec.to_dict() == before

    def test_detector_is_stateless_and_reusable(self, detector):
        spec = _make_spec(intent="generate the quarterly report")
        first = detector.detect(spec, resolution=False)
        second = detector.detect(spec, resolution=False)
        assert first == second

    def test_record_is_json_safe(self, detector):
        result = detector.detect(
            _make_spec(intent="run the quantum stabilizer diagnostic"),
            resolution=False,
            missing_capability="quantum_stabilizer",
        )
        import json

        json.dumps(result.to_dict())


# ---------------------------------------------------------------------------
# No development machinery invocation + dependency direction
# ---------------------------------------------------------------------------


class TestNoDevelopmentMachinery:
    def test_detector_has_no_development_execution_surface(self):
        detector = DevelopmentNeedDetector()
        for attr in (
            "approval_manager",
            "development_controller",
            "planner",
            "self_development_loop",
            "execution_gateway",
            "promotion_gate",
            "code_sandbox",
            "advisor",
            "scheduler",
            "tick",
        ):
            assert not hasattr(detector, attr), f"detector unexpectedly has {attr}"

    def test_detector_module_imports_no_forbidden_machinery(self):
        source = (
            _ROOT / "atlas" / "conversation" / "development_need_detector.py"
        ).read_text(encoding="utf-8")
        tree = ast.parse(source, filename="development_need_detector.py")
        forbidden = (
            "atlas.evolution",
            "atlas.orchestration",
            "atlas.advisory",
            "atlas.kernel",
            "atlas.runtime",
            "atlas.storage",
        )
        for node in ast.walk(tree):
            module = getattr(node, "module", None)
            if module and any(
                module == p or module.startswith(p + ".") for p in forbidden
            ):
                raise AssertionError(f"detector imports forbidden module: {module}")
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if any(
                        alias.name == p or alias.name.startswith(p + ".")
                        for p in forbidden
                    ):
                        raise AssertionError(
                            f"detector imports forbidden module: {alias.name}"
                        )

    def test_detector_imports_only_conversation_task_intake(self):
        """The detector may only depend on conversation-owned data types."""
        source = (
            _ROOT / "atlas" / "conversation" / "development_need_detector.py"
        ).read_text(encoding="utf-8")
        tree = ast.parse(source, filename="development_need_detector.py")
        for node in ast.walk(tree):
            module = getattr(node, "module", None)
            if module and module.startswith("atlas"):
                assert module == "atlas.conversation.task_intake", (
                    f"detector imports non-conversation module: {module}"
                )
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith("atlas"):
                        assert alias.name == "atlas.conversation.task_intake", (
                            f"detector imports non-conversation module: {alias.name}"
                        )
