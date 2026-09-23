"""Phase 6.1 — Development goal intake: evidence contract.

Investigation result: Atlas already turns a development need into a structured
development goal, so no second goal model was introduced.

* ``atlas/conversation/development_intake.py::task_spec_to_development_need`` —
  maps a DEVELOPMENT_REQUEST ``TaskSpec`` to a bounded ``DevelopmentNeed``;
  non-development types and clarification-pending requests are refused.
* ``atlas/evolution/development_cycle.py::DevelopmentNeed`` — structured goal
  (title, summary, rationale, expected_benefit, target_components, evidence ids,
  research_question, sources, metadata).
* A gap alone grants no authority: preparation fails closed without supplied
  design content and stops at the approval boundary.
"""

from __future__ import annotations

from datetime import datetime

from atlas.conversation.development_intake import (
    is_development_request,
    task_spec_to_development_need,
)
from atlas.conversation.task_intake import TaskIntake, TaskType
from atlas.evolution.approval_manager import ApprovalManager
from atlas.evolution.development_cycle import (
    DevelopmentCycleController,
    DevelopmentNeed,
)


def _spec(text: str):
    return TaskIntake(now=datetime(2026, 9, 25, 12, 0, 0)).intake(text)


class TestPhase61DevelopmentGoalIntake:
    def test_development_request_becomes_a_structured_need(self):
        spec = _spec("add a new capability to Atlas for scheduling")
        assert spec.task_type is TaskType.DEVELOPMENT_REQUEST

        need = task_spec_to_development_need(spec)
        assert need is not None
        assert need.title
        assert need.summary
        assert isinstance(need.metadata, dict)
        # A DevelopmentNeed carries the structured goal fields.
        assert hasattr(need, "expected_benefit")
        assert hasattr(need, "target_components")
        assert hasattr(need, "evidence_change_ids")

    def test_non_development_requests_are_not_development_goals(self):
        spec = _spec("hello Atlas how are you")
        assert is_development_request(spec) is False
        assert task_spec_to_development_need(spec) is None

    def test_ambiguous_development_goal_fails_closed(self):
        spec = _spec("improve this module")
        assert spec.task_type is TaskType.DEVELOPMENT_REQUEST
        assert spec.needs_clarification is True
        assert task_spec_to_development_need(spec) is None

    def test_invalid_goal_is_rejected_by_the_cycle(self):
        controller = DevelopmentCycleController(approval_manager=ApprovalManager())
        result = controller.run_development_cycle(DevelopmentNeed(title="   "))
        assert result.ok is False
        assert any(stage == "need" for stage, _ in result.failures)

    def test_a_gap_alone_grants_no_authority_or_approval(self):
        controller = DevelopmentCycleController(approval_manager=ApprovalManager())
        result = controller.run_development_cycle(
            DevelopmentNeed(title="add a scheduling capability")
        )
        # No supplied design content and no evidence -> fails closed; nothing approved.
        assert result.ok is False
        assert result.proposal_id == ""
        assert result.proposal_status == ""
