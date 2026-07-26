"""
Atlas AI Provider Interface

Every AI provider must inherit from this interface.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterator
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from atlas.models.ai_response import AIResponse


class AIProvider(ABC):
    """Base interface for all AI providers."""

    @abstractmethod
    def name(self) -> str:
        """Return provider name."""
        pass

    @abstractmethod
    def chat(self, messages) -> "AIResponse":
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
    def complete(self, prompt) -> "AIResponse":
        """Generate a completion."""
        pass

    @abstractmethod
    def models(self) -> list[str]:
        """Return available models."""
        pass
