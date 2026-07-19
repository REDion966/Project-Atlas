"""
Atlas Agent Registry

Provides discovery and lookup
for available agents.
"""

from __future__ import annotations

from atlas.agents.agent import Agent


class AgentRegistry:
    """
    Central registry for agents.
    """

    def __init__(self):

        self._agents: dict[str, Agent] = {}


    def register(
        self,
        agent: Agent,
    ) -> None:
        """
        Register agent.
        """

        self._agents[
            agent.id
        ] = agent


    def unregister(
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


    def get(
        self,
        agent_id: str,
    ) -> Agent | None:
        """
        Find agent.
        """

        return self._agents.get(
            agent_id
        )


    def all(self) -> list[Agent]:
        """
        Return all agents.
        """

        return list(
            self._agents.values()
        )


    def count(self) -> int:
        """
        Return agent count.
        """

        return len(
            self._agents
        )