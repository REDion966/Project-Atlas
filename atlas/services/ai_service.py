"""
Atlas AI Service

Provides the public interface for Atlas AI.
"""

from collections.abc import Iterator
from typing import TYPE_CHECKING

from atlas.ai.router.ai_router import AIRouter
from atlas.ai.routing.models import RoutingRequest
from atlas.services.service import Service

if TYPE_CHECKING:
    from atlas.ai.routing.router import ModelRouter


class AIService(Service):
    """Atlas AI service."""

    def __init__(
        self,
        router: AIRouter,
        model_router: "ModelRouter | None" = None,
    ):
        super().__init__("AI Service")
        self._router = router
        self._model_router = model_router

    def start(self):
        """Start the AI service."""
        self.mark_running()

    def stop(self):
        """Stop the AI service."""
        super().stop()

    def chat(
        self,
        messages,
        routing_context: RoutingRequest | None = None,
    ):
        """Chat with the active AI provider."""

        routing_decision = None

        if self._model_router is not None and routing_context is not None:
            routing_decision = self._model_router.route(
                routing_context
            )

        return self._router.chat(
            messages,
            routing_decision=routing_decision,
        )

    def stream_chat(
        self,
        messages,
        routing_context: RoutingRequest | None = None,
    ) -> Iterator[str]:
        """Stream chat from the active AI provider."""

        routing_decision = None

        if self._model_router is not None and routing_context is not None:
            routing_decision = self._model_router.route(
                routing_context
            )

        return self._router.stream_chat(
            messages,
            routing_decision=routing_decision,
        )

    def complete(self, prompt):
        """Generate a completion."""
        return self._router.complete(prompt)

    def models(self):
        """Return available models."""
        return self._router.models()