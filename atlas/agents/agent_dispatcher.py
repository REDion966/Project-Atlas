"""
Atlas Agent Dispatcher
"""

from __future__ import annotations

from atlas.agents.agent import Agent


class AgentDispatcher:
    """
    Dispatches work to agents.
    """

    def dispatch(
        self,
        agent: Agent,
        task: str,
    ) -> dict:

        return {
            "agent": agent.id,
            "task": task,
            "status": "dispatched",
        }