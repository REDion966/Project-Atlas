"""
Atlas Agent Planner

Creates execution plans.
"""

from __future__ import annotations


class AgentPlanner:
    """
    Builds simple execution plans.
    """

    def create_plan(
        self,
        goal: str,
    ) -> list[str]:

        return [
            f"Analyze: {goal}",
            "Create tasks",
            "Execute tasks",
            "Report completion",
        ]