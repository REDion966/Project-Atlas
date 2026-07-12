"""
Atlas AI Provider Interface

Every AI provider must inherit from this interface.
"""

from abc import ABC, abstractmethod


class AIProvider(ABC):
    """Base interface for all AI providers."""

    @abstractmethod
    def name(self) -> str:
        """Return provider name."""
        pass

    @abstractmethod
    def chat(self, messages):
        """Generate a chat response."""
        pass

    @abstractmethod
    def complete(self, prompt):
        """Generate a completion."""
        pass

    @abstractmethod
    def models(self):
        """Return available models."""
        pass