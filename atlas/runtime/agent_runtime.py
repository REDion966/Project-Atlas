"""
Atlas Agent Runtime Bridge

Connects runtime system
with agent management.
"""

from __future__ import annotations

from atlas.agents.agent import Agent
from atlas.agents.agent_manager import AgentManager


class AgentRuntime:
    """
    Runtime bridge for Atlas agents.
    """

    def __init__(
        self,
        agent_manager: AgentManager,
    ):

        self.agent_manager = agent_manager


    def register_agent(
        self,
        agent: Agent,
    ) -> Agent:
        """
        Register an existing agent.

        Useful for runtime attachment.
        """

        self.agent_manager._agents[
            agent.id
        ] = agent

        return agent


    def get_agent_status(
        self,
        agent_id: str,
    ) -> dict | None:
        """
        Return agent runtime status.
        """

        agent = self.agent_manager.get_agent(
            agent_id
        )

        if agent is None:
            return None

        return agent.status()


    def list_agents(self) -> list[dict]:
        """
        Return all runtime agents.
        """

        return self.agent_manager.list_agents()


    def health_check(self) -> dict:
        """
        Check agent runtime health.
        """

        agents = self.agent_manager.list_agents()

        return {
            "agents": len(agents),
            "healthy": True,
        }