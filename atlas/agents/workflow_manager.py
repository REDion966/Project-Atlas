"""
Atlas Workflow Manager
"""

from __future__ import annotations

from atlas.agents.workflow import Workflow


class WorkflowManager:
    """
    Stores workflows.
    """

    def __init__(self):

        self._workflows: dict[str, Workflow] = {}

    def register(
        self,
        workflow: Workflow,
    ) -> None:

        self._workflows[
            workflow.name
        ] = workflow

    def get(
        self,
        name: str,
    ) -> Workflow | None:

        return self._workflows.get(name)

    def all(self) -> list[Workflow]:

        return list(
            self._workflows.values()
        )