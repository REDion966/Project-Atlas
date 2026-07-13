"""
Atlas Base Service

Defines the interface for every Atlas service.
"""

from abc import ABC, abstractmethod


class Service(ABC):
    """Base class for all Atlas services."""

    def __init__(self, name: str):
        self.name = name
        self._running = False

    @abstractmethod
    def start(self):
        """
        Start the service.
        Concrete services should call
        super().mark_running()
        when startup succeeds.
        """
        raise NotImplementedError

    def stop(self):
        """
        Stop the service.
        """

        self._running = False

    @property
    def running(self) -> bool:
        """
        Return True if the service is running.
        """

        return self._running

    def is_running(self) -> bool:
        """
        Backwards-compatible alias.
        """

        return self._running

    def mark_running(self) -> None:
        """
        Mark the service as running.
        """

        self._running = True