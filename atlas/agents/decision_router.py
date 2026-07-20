"""
Atlas Decision Router

Routes work to the most appropriate agent.
"""

from __future__ import annotations

from atlas.agents.agent_registry import AgentRegistry
from atlas.agents.agent import Agent


class DecisionRouter:
    """
    Selects agents for work.
    """

    def __init__(
        self,
        registry: AgentRegistry,
    ):

        self.registry = registry

    def select_agent(self) -> Agent | None:
        """
        Return first available agent.
        """

        agents = self.registry.all()

        if not agents:
            return None

        return agents[0]