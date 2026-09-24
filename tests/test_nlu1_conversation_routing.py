"""NLU-1 — conversation correctness & honest task routing (focused contract tests).

Covers the evidenced NLU-1 gaps:

  * planning/assistance requests are ANSWERABLE requests, not Atlas-development
    requests and not unresolved tool actions;
  * ordinary information/comparison questions carry a question illocution so the
    deterministic floor routes them to the answerable (model-assisted) path
    instead of declining them;
  * capability-development requests keep their governed DEVELOPMENT_REQUEST
    classification.

Deterministic and model-free: no provider, no kernel, no network.
"""

from __future__ import annotations

from atlas.conversation.builtin_response import BuiltinResponseService
from atlas.conversation.conversation_service import reasoning_eligibility
from atlas.conversation.development_need_coordinator import DevelopmentNeedCoordinator
from atlas.conversation.task_intake import TaskIntake, TaskType

PLANNING_ASSISTANCE = (
    "Help me create a systematic plan for reviewing a smartphone camera.",
    "Create a review checklist for the smartphone camera I am reviewing.",
    "Create a checklist for reviewing a phone camera.",
)

INFORMATION_COMPARISON = (
    "What should I look for when reviewing a smartphone camera?",
    "Compare the camera systems of three flagship phones and tell me what "
    "matters for a detailed review.",
    "Explain the trade-offs between sensor size and pixel count in a "
    "smartphone camera.",
)

CAPABILITY_DEVELOPMENT = (
    "Atlas, I need you to develop a capability that allows you to automatically "
    "gather and organize information about a smartphone for my review.",
    "Add a capability for scheduled follow-ups.",
    "Create a module for scheduled follow-ups.",
)


def _spec(text: str):
    return TaskIntake().intake(text)


def _eligibility(text: str):
    spec = _spec(text)
    message = BuiltinResponseService().respond(text, spec=spec)
    if message is None:
        return None
    return reasoning_eligibility(spec, message.metadata.get("builtin_intent"))


class TestPlanningAssistanceIsAnswerable:
    def test_planning_artifacts_are_questions_not_actions(self):
        for text in PLANNING_ASSISTANCE:
            spec = _spec(text)
            assert spec.task_type is TaskType.QUESTION, text
            assert spec.task_type is not TaskType.ACTION_REQUEST, text
            assert spec.task_type is not TaskType.DEVELOPMENT_REQUEST, text

    def test_planning_requests_are_not_development_requests(self):
        for text in PLANNING_ASSISTANCE:
            assert _spec(text).task_type is not TaskType.DEVELOPMENT_REQUEST, text

    def test_planning_requests_never_reach_the_development_need_detector(self):
        # The P7 capability-gap detector only considers ACTION requests; a
        # planning/assistance request must not be surfaced as an Atlas
        # development need.
        coordinator = DevelopmentNeedCoordinator()
        for text in PLANNING_ASSISTANCE:
            assert coordinator.detect_unresolved_action(_spec(text)) is None, text
            assert not coordinator.has_pending, text

    def test_planning_requests_are_eligible_for_the_answerable_path(self):
        for text in PLANNING_ASSISTANCE:
            signal = _eligibility(text)
            assert signal is not None and signal.get("eligible") is True, text


class TestInformationComparisonRouting:
    def test_comparison_is_a_leading_request(self):
        text = (
            "Compare the camera systems of three flagship phones and tell me "
            "what matters for a detailed review."
        )
        spec = _spec(text)
        assert spec.task_type is TaskType.QUESTION
        meaning = spec.context["utterance_meaning"]
        # The comparison imperative is an attested leading operation, so the
        # utterance is a REQUEST (not a bare statement the floor declines).
        assert meaning["operation"] == "compare"
        assert meaning["illocution"] == "request"

    def test_information_requests_are_eligible_for_the_answerable_path(self):
        for text in INFORMATION_COMPARISON:
            signal = _eligibility(text)
            assert signal is not None and signal.get("eligible") is True, text


class TestCapabilityDevelopmentPreserved:
    def test_capability_development_remains_a_development_request(self):
        for text in CAPABILITY_DEVELOPMENT:
            assert _spec(text).task_type is TaskType.DEVELOPMENT_REQUEST, text

    def test_development_requests_are_never_delegated_as_information(self):
        # Development is a governed path; it must not be delegated to the
        # answerable model path by the builtin floor.
        for text in CAPABILITY_DEVELOPMENT:
            spec = _spec(text)
            message = BuiltinResponseService().respond(text, spec=spec)
            assert message is None, text


class TestUnresolvedActionDetectionPreserved:
    def test_genuine_unresolved_action_still_detects(self):
        # The P7 capability-gap contract for an unresolved ACTION request is
        # unchanged.
        coordinator = DevelopmentNeedCoordinator()
        explanation = coordinator.detect_unresolved_action(
            _spec("run the quantum stabilizer diagnostic")
        )
        assert explanation is not None
        assert coordinator.has_pending
