"""
Atlas Agent Coordinator

Coordinates multiple agents.
"""

from __future__ import annotations

from atlas.agents.agent_registry import AgentRegistry
from atlas.agents.agent_communication import AgentCommunication


class AgentCoordinator:
    """
    Multi-agent coordination layer.
    """

    def __init__(
        self,
        registry: AgentRegistry,
        communication: AgentCommunication,
    ):

        self.registry = registry
        self.communication = communication


    def available_agents(self) -> int:
        """
        Return available agent count.
        """

        return self.registry.count()


    def status(self) -> dict:
        """
        Coordinator status.
        """

        return {
            "agents": self.registry.count(),
            "messages": len(
                self.communication.history()
            ),
        }