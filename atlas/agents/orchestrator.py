"""
Atlas Orchestrator

Central intelligence coordinator.
"""

from __future__ import annotations

from atlas.agents.goal import Goal
from atlas.agents.agent_planner import AgentPlanner
from atlas.agents.execution_result import ExecutionResult


class Orchestrator:
    """
    Coordinates Atlas execution.
    """

    def __init__(self):

        self.planner = AgentPlanner()

    def execute(
        self,
        goal: Goal,
    ) -> ExecutionResult:

        plan = self.planner.create_plan(
            goal.description
        )

        return ExecutionResult(
            success=True,
            output={
                "goal": goal.description,
                "plan": plan,
            },
        )