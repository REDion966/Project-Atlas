"""Phase 4.2 — Goal interpretation: evidence contract.

Investigation result: Atlas already transforms a request-level objective into a
structured goal representation, so no new goal model was introduced.

* ``atlas/conversation/task_intake.py::TaskIntake.intake`` → ``TaskSpec`` — a
  structured, provenance-carrying interpretation (task_type, intent, goal,
  constraints, priorities, success_criteria, ambiguity, confidence,
  needs_clarification, input_hash).
* ``atlas/conversation/turn_meaning.py`` — the L7 ``TurnMeaning`` projection
  carries the goal/constraints/success-criteria into reasoning.
* ``atlas/conversation/development_intake.py::task_spec_to_development_need`` —
  maps a development goal to a structured ``DevelopmentNeed``.

These tests pin deterministic, model-free goal interpretation.
"""

from __future__ import annotations

from datetime import datetime

from atlas.conversation.development_intake import task_spec_to_development_need
from atlas.conversation.task_intake import TaskIntake, TaskType
from atlas.conversation.turn_meaning import build_turn_meaning

_TEXT = "add a new capability to Atlas for scheduling"


def _spec(text: str = _TEXT):
    return TaskIntake(now=datetime(2026, 8, 29, 12, 0, 0)).intake(text)


class TestPhase42GoalInterpretation:
    def test_intake_produces_a_structured_goal(self):
        spec = _spec()
        assert spec.task_type is TaskType.DEVELOPMENT_REQUEST
        assert spec.intent
        assert spec.goal
        assert spec.input_hash
        assert spec.needs_clarification is False

    def test_goal_interpretation_is_deterministic(self):
        assert _spec().to_dict() == _spec().to_dict()

    def test_structured_meaning_carries_the_goal_to_reasoning(self):
        spec = _spec()
        projected = build_turn_meaning(spec, _TEXT).to_reasoning_meaning()
        assert projected["task_type"] == TaskType.DEVELOPMENT_REQUEST.value
        assert projected["goal"] == spec.goal
        assert projected["needs_clarification"] is False

    def test_goal_maps_to_a_structured_development_need(self):
        need = task_spec_to_development_need(_spec())
        assert need is not None
        assert need.title
        assert need.summary

    def test_under_specified_goal_is_flagged_not_guessed(self):
        spec = TaskIntake(now=datetime(2026, 8, 29, 12, 0, 0)).intake(
            "improve this module"
        )
        assert spec.task_type is TaskType.DEVELOPMENT_REQUEST
        assert spec.needs_clarification is True
        assert task_spec_to_development_need(spec) is None
