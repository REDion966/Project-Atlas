"""
Atlas Execution Pipeline
"""

from __future__ import annotations

from atlas.agents.workflow import Workflow


class ExecutionPipeline:
    """
    Executes workflows.
    """

    def execute(
        self,
        workflow: Workflow,
    ) -> list[str]:

        completed: list[str] = []

        for step in workflow.steps:

            completed.append(step)

        return completed