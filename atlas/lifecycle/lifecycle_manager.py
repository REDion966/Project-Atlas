"""
Atlas Lifecycle Manager

Coordinates Atlas startup and shutdown phases.
"""

from atlas.lifecycle.phases import LifecyclePhase


class LifecycleManager:
    """
    Controls Atlas lifecycle.
    """

    def __init__(
        self,
        event_bus=None,
        state_manager=None,
    ):
        self._event_bus = event_bus
        self._state_manager = state_manager

        self._components = []

        self._phase = LifecyclePhase.CREATED

    @property
    def phase(self):
        """
        Return current lifecycle phase.
        """

        return self._phase

    def register(self, component):
        """
        Register a lifecycle-aware component.
        """

        self._components.append(component)

    def _set_phase(self, phase: LifecyclePhase):
        """
        Change lifecycle phase.
        """

        self._phase = phase

        if self._state_manager:
            self._state_manager.set(
                "lifecycle",
                phase.value,
            )

        if self._event_bus:
            self._event_bus.publish(
                "lifecycle.changed",
                {
                    "phase": phase.value,
                },
            )

    def initialize(self):
        """
        Initialize components.
        """

        self._set_phase(
            LifecyclePhase.INITIALIZING
        )

        for component in self._components:
            hook = getattr(
                component,
                "before_initialize",
                None,
            )

            if callable(hook):
                hook()

        for component in self._components:
            hook = getattr(
                component,
                "after_initialize",
                None,
            )

            if callable(hook):
                hook()

    def start(self):
        """
        Start components.
        """

        self._set_phase(
            LifecyclePhase.STARTING
        )

        for component in self._components:
            hook = getattr(
                component,
                "before_start",
                None,
            )

            if callable(hook):
                hook()

        for component in self._components:
            hook = getattr(
                component,
                "after_start",
                None,
            )

            if callable(hook):
                hook()

        self._set_phase(
            LifecyclePhase.RUNNING
        )

    def stop(self):
        """
        Stop components.
        """

        self._set_phase(
            LifecyclePhase.STOPPING
        )

        for component in reversed(self._components):
            hook = getattr(
                component,
                "before_stop",
                None,
            )

            if callable(hook):
                hook()

        for component in reversed(self._components):
            hook = getattr(
                component,
                "after_stop",
                None,
            )

            if callable(hook):
                hook()

        self._set_phase(
            LifecyclePhase.STOPPED
        )