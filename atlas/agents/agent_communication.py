"""
Atlas Agent Communication

Handles communication between agents.
"""

from __future__ import annotations

from atlas.agents.agent_message import AgentMessage


class AgentCommunication:
    """
    Agent messaging service.
    """

    def __init__(self):

        self._messages: list[AgentMessage] = []


    def send(
        self,
        message: AgentMessage,
    ) -> None:
        """
        Send message.
        """

        self._messages.append(
            message
        )


    def history(self) -> list[dict]:
        """
        Return communication history.
        """

        return [
            message.to_dict()
            for message in self._messages
        ]


    def clear(self) -> None:
        """
        Clear messages.
        """

        self._messages.clear()