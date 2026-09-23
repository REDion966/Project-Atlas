"""Phase 7.1 — Research goal interpretation: evidence contract.

Investigation result: Atlas already turns a request into a structured research
objective, so no second research-goal model was introduced.

* ``atlas/evolution/models.py::ResearchQuery`` → ``ResearchPlanner.plan`` →
  ``ResearchPlan`` (question, sub-queries/aspects, target sources, verification
  strategy, max depth).
* ``TaskIntake`` keeps research goals distinguishable from development/execution
  goals; research-shaped information requests route to a governed RESEARCH step.
"""

from __future__ import annotations

from atlas.conversation.task_intake import TaskIntake, TaskType
from atlas.evolution.models import ResearchQuery
from atlas.orchestration.models import NodeKind
from atlas.orchestration.target_resolution import task_spec_to_execution_steps
from atlas.research.planner import ResearchPlanner


def _plan(question: str):
    return ResearchPlanner().plan(ResearchQuery(query_id="q-1", question=question))


class TestPhase71ResearchGoal:
    def test_plan_represents_questions_and_target_sources(self):
        plan = _plan("how does the memory architecture handle persistence")
        assert plan.question
        assert plan.sub_queries  # research questions/aspects
        assert plan.target_sources
        assert plan.verification_strategy
        assert plan.max_depth >= 1

    def test_planning_is_deterministic(self):
        question = "compare vector database options"
        first = _plan(question)
        second = _plan(question)
        assert first.sub_queries == second.sub_queries
        assert first.target_sources == second.target_sources
        assert first.verification_strategy == second.verification_strategy

    def test_empty_question_produces_no_questions(self):
        plan = _plan("   ")
        assert plan.sub_queries == ()
        assert plan.verification_strategy == "none"

    def test_research_goal_is_distinguishable_from_development(self):
        spec = TaskIntake().intake(
            "research the latest approaches to vector databases"
        )
        assert spec.task_type is not TaskType.DEVELOPMENT_REQUEST
        steps = task_spec_to_execution_steps(spec)
        assert steps is not None
        assert steps[0].kind is NodeKind.RESEARCH
