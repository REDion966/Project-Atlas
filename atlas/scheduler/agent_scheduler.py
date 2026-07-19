"""
Atlas Agent Scheduler Bridge

Connects agents with scheduler subsystem.
"""

from __future__ import annotations

from atlas.agents.agent import Agent


class AgentScheduler:
    """
    Scheduler interface for agents.
    """

    def __init__(self):
        self._scheduled_agents: dict[str, Agent] = {}


    def attach(
        self,
        agent: Agent,
    ) -> None:
        """
        Attach agent to scheduler.
        """

        self._scheduled_agents[
            agent.id
        ] = agent


    def detach(
        self,
        agent_id: str,
    ) -> bool:
        """
        Remove agent from scheduler.
        """

        if agent_id not in self._scheduled_agents:
            return False

        del self._scheduled_agents[agent_id]

        return True


    def list_agents(self) -> list[str]:
        """
        Return scheduled agents.
        """

        return list(
            self._scheduled_agents.keys()
        )