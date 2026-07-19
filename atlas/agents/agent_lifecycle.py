"""
Atlas Agent Lifecycle

Controls valid lifecycle transitions
for Atlas agents.
"""

from __future__ import annotations

from atlas.agents.agent import Agent


class AgentLifecycle:
    """
    Controls agent state transitions.
    """

    def start(
        self,
        agent: Agent,
    ) -> None:
        """
        Start an agent.
        """

        if agent.state.status == "running":
            return

        agent.start()


    def pause(
        self,
        agent: Agent,
    ) -> None:
        """
        Pause an agent.
        """

        if agent.state.status != "running":
            return

        agent.pause()


    def stop(
        self,
        agent: Agent,
    ) -> None:
        """
        Stop an agent.
        """

        if agent.state.status == "stopped":
            return

        agent.stop()


    def restart(
        self,
        agent: Agent,
    ) -> None:
        """
        Restart an agent.
        """

        self.stop(agent)

        self.start(agent)