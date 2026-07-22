"""
Atlas AI Event Bus

Internal event communication system for AI subsystem.
"""

from collections import defaultdict
from collections.abc import Callable

from atlas.ai.events import AIEvent


class AIEventBus:
    """
    Publishes and distributes AI events.
    """

    def __init__(self):
        self._listeners = defaultdict(list)

    def subscribe(
        self,
        event_type: type[AIEvent],
        callback: Callable,
    ):
        """
        Subscribe to an event type.
        """

        self._listeners[event_type].append(
            callback
        )

    def publish(
        self,
        event: AIEvent,
    ):
        """
        Publish an event.
        """

        listeners = self._listeners.get(
            type(event),
            [],
        )

        for callback in listeners:
            callback(event)

    def clear(self):
        """
        Remove all listeners.
        """

        self._listeners.clear()