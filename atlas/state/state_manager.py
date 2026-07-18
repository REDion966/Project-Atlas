"""
Atlas State Manager

Tracks and broadcasts the internal condition of Atlas.
"""


from atlas.events.event_bus import EventBus


class StateManager:
    """
    Central state storage for Atlas.
    """

    def __init__(
        self,
        event_bus: EventBus,
    ):

        self._event_bus = event_bus

        self._default_state = {
            "status": "created",
            "mode": "idle",
            "task": None,
            "active_agent": None,
            "health": "unknown",
        }

        self._state = self._default_state.copy()


    def set(
        self,
        key: str,
        value,
    ):
        """
        Update a state value and publish change.
        """

        old_value = self._state.get(
            key
        )

        self._state[key] = value


        self._event_bus.publish(
            "atlas.state.changed",
            {
                "key": key,
                "old": old_value,
                "new": value,
            }
        )


    def get(
        self,
        key: str,
        default=None,
    ):
        """
        Retrieve a state value.
        """

        return self._state.get(
            key,
            default,
        )


    def update(
        self,
        values: dict,
    ):
        """
        Update multiple state values.
        """

        for key, value in values.items():

            self.set(
                key,
                value,
            )


    def all(self):
        """
        Return complete state.
        """

        return self._state.copy()


    def reset(self):
        """
        Reset Atlas state.
        """

        self._state = self._default_state.copy()


        self._event_bus.publish(
            "atlas.state.reset",
            self.all(),
        )