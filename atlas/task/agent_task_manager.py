"""
Atlas Agent Task Manager

Manages tasks assigned to agents.
"""

from __future__ import annotations

from atlas.task.agent_task import AgentTask


class AgentTaskManager:
    """
    Controls agent tasks.
    """

    def __init__(self):

        self._tasks: dict[str, AgentTask] = {}


    def create(
        self,
        name: str,
        agent_id: str,
    ) -> AgentTask:
        """
        Create task.
        """

        task = AgentTask(
            name=name,
            agent_id=agent_id,
        )

        self._tasks[
            task.id
        ] = task

        return task


    def get(
        self,
        task_id: str,
    ) -> AgentTask | None:
        return self._tasks.get(
            task_id
        )


    def list(self) -> list[dict]:
        return [
            task.to_dict()
            for task in self._tasks.values()
        ]