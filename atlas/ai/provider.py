"""
Atlas AI Provider Interface

Every AI provider must inherit from this interface.
"""

from abc import ABC, abstractmethod
from collections.abc import Iterator


class AIProvider(ABC):
    """Base interface for all AI providers."""

    @abstractmethod
    def name(self) -> str:
        """Return provider name."""
        pass

    @abstractmethod
    def chat(self, messages):
        """Generate a complete chat response."""
        pass

    @abstractmethod
    def stream_chat(
        self,
        messages,
    ) -> Iterator[str]:
        """Stream chat response chunks."""
        pass

    @abstractmethod
    def complete(self, prompt):
        """Generate a completion."""
        pass

    @abstractmethod
    def models(self):
        """Return available models."""
        pass