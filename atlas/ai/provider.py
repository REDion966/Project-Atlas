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
    def chat(self, messages, model: str | None = None) -> "AIResponse":
        """Generate a complete chat response.

        Args:
            messages: Conversation messages.
            model: Optional per-call model override. When None, the
                provider's configured default model is used.
        """
        pass

    @abstractmethod
    def stream_chat(
        self,
        messages,
        model: str | None = None,
    ) -> Iterator[str]:
        """Stream chat response chunks.

        Args:
            messages: Conversation messages.
            model: Optional per-call model override. When None, the
                provider's configured default model is used.
        """
        pass

    @abstractmethod
    def complete(self, prompt, model: str | None = None) -> "AIResponse":
        """Generate a completion.

        Args:
            prompt: The completion prompt.
            model: Optional per-call model override. When None, the
                provider's configured default model is used.
        """
        pass

    @abstractmethod
    def models(self) -> list[str]:
        """Return available models."""
        pass
