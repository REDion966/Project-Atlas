"""
Atlas Agent

Core agent entity.
"""

from __future__ import annotations

from atlas.agents.agent_identity import AgentIdentity
from atlas.agents.agent_state import AgentState


class Agent:
    """
    Core Atlas Agent.

    Combines identity and state.
    """

    def __init__(
        self,
        identity: AgentIdentity,
    ):

        self.identity = identity

        self.state = AgentState()


    @property
    def id(self) -> str:
        """
        Return agent ID.
        """

        return self.identity.id


    @property
    def name(self) -> str:
        """
        Return agent name.
        """

        return self.identity.name


    def start(self):
        """
        Start agent.
        """

        self.state.start()


    def pause(self):
        """
        Pause agent.
        """

        self.state.pause()


    def stop(self):
        """
        Stop agent.
        """

        self.state.stop()


    def execute_action(self):
        """
        Record agent activity.

        Real execution will be added later.
        """

        self.state.record_action()


    def status(self) -> dict:
        """
        Return complete agent status.
        """

        return {
            "identity": self.identity.to_dict(),

            "state": self.state.to_dict(),
        }