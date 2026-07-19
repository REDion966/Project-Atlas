"""
Atlas Agent Manager

Creates and manages Atlas agents.
"""

from __future__ import annotations

from atlas.agents.agent import Agent
from atlas.agents.agent_identity import AgentIdentity


class AgentManager:
    """
    Manages Atlas agents.
    """

    def __init__(self):

        self._agents: dict[str, Agent] = {}


    def create_agent(
        self,
        name: str,
        agent_type: str = "general",
        description: str = "",
    ) -> Agent:
        """
        Create a new agent.
        """

        identity = AgentIdentity(
            name=name,
            agent_type=agent_type,
            description=description,
        )

        agent = Agent(
            identity=identity
        )

        self._agents[agent.id] = agent

        return agent


    def get_agent(
        self,
        agent_id: str,
    ) -> Agent | None:
        """
        Retrieve agent by ID.
        """

        return self._agents.get(
            agent_id
        )


    def remove_agent(
        self,
        agent_id: str,
    ) -> bool:
        """
        Remove agent.
        """

        if agent_id not in self._agents:
            return False

        del self._agents[agent_id]

        return True


    def list_agents(self) -> list[dict]:
        """
        Return all agents.
        """

        return [
            agent.status()
            for agent in self._agents.values()
        ]


    def count(self) -> int:
        """
        Return number of agents.
        """

        return len(
            self._agents
        )