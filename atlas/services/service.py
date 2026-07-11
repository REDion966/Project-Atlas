"""
Atlas Base Service

Defines the interface for every Atlas service.
"""

from abc import ABC, abstractmethod


class Service(ABC):
    """Base class for all Atlas services."""

    def __init__(self, name: str):
        self.name = name
        self.running = False

    @abstractmethod
    def start(self):
        """Start the service."""
        pass

    def stop(self):
        """Stop the service."""
        self.running = False

    def is_running(self):
        """Return True if the service is running."""
        return self.running