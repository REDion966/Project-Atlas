"""
Atlas Agent Capabilities

Defines abilities available to agents.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class AgentCapabilities:
    """
    Collection of agent abilities.
    """

    capabilities: set[str] = field(
        default_factory=set
    )


    def add(
        self,
        capability: str,
    ) -> None:
        """
        Add a capability.
        """

        self.capabilities.add(
            capability
        )


    def remove(
        self,
        capability: str,
    ) -> None:
        """
        Remove a capability.
        """

        self.capabilities.discard(
            capability
        )


    def has(
        self,
        capability: str,
    ) -> bool:
        """
        Check capability.
        """

        return capability in self.capabilities


    def list(self) -> list[str]:
        """
        Return capabilities.
        """

        return sorted(
            self.capabilities
        )


    def to_dict(self) -> dict:
        """
        Serialize capabilities.
        """

        return {
            "capabilities": self.list()
        }