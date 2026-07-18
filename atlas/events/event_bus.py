"""
Atlas Event Bus

Central communication system between Atlas components.
"""

from collections import defaultdict
from collections.abc import Callable


class EventBus:
    """
    Publish and subscribe event system.
    """

    def __init__(self):

        self._listeners = defaultdict(list)


    def subscribe(
        self,
        event_name: str,
        callback: Callable,
    ):
        """
        Subscribe to an event.
        """

        self._listeners[event_name].append(
            callback
        )


    def publish(
        self,
        event_name: str,
        payload=None,
    ):
        """
        Publish an event.
        """

        listeners = self._listeners.get(
            event_name,
            [],
        )

        for callback in listeners:
            callback(payload)


    def clear(self):
        """
        Remove all listeners.
        """

        self._listeners.clear()