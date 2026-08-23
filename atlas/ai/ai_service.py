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
    from atlas.ai.fallback import FallbackExecutor
    from atlas.ai.routing.router import ModelRouter


class AIService(Service):
    """Atlas AI service."""

    def __init__(
        self,
        router: AIRouter,
        model_router: "ModelRouter | None" = None,
        fallback_executor: "FallbackExecutor | None" = None,
        allow_fallback_default: bool = False,
    ):
        super().__init__("AI Service")
        self._router = router
        self._model_router = model_router
        self._fallback_executor = fallback_executor
        self._allow_fallback_default = allow_fallback_default

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
        """Chat with the active AI provider.

        When a ``routing_context`` is supplied, the model router produces a
        ``RoutingDecision``.  If the caller explicitly set
        ``routing_context.allow_fallback`` and a fallback executor is wired,
        the chat attempt runs through the policy-controlled fallback
        executor; otherwise the behavior is identical to invoking the active
        provider directly (no fallback).
        """

        routing_decision = None

        if self._model_router is not None and routing_context is not None:
            routing_decision = self._model_router.route(
                routing_context
            )

        effective_allow_fallback = bool(
            routing_context is not None
            and (routing_context.allow_fallback or self._allow_fallback_default)
        )

        if (
            routing_decision is not None
            and routing_context is not None
            and effective_allow_fallback
            and self._fallback_executor is not None
        ):
            return self._fallback_executor.execute(
                routing_context,
                routing_decision,
                call=lambda provider_name, model_name: self._router.chat(
                    messages,
                    routing_decision=_decision_for(
                        routing_decision,
                        provider_name,
                        model_name,
                    ),
                ),
            ).response

        return self._router.chat(
            messages,
            routing_decision=routing_decision,
        )

    def stream_chat(
        self,
        messages,
        routing_context: RoutingRequest | None = None,
    ) -> Iterator[str]:
        """Stream chat from the active AI provider.

        Streaming fallback follows the Phase D policy: a transient failure
        before the first token may move to an eligible candidate when fallback
        is explicitly enabled; after the first token the provider/model is
        never switched.  With fallback disabled (the default) behavior is
        identical to the direct provider router call.
        """

        routing_decision = None

        if self._model_router is not None and routing_context is not None:
            routing_decision = self._model_router.route(
                routing_context
            )

        effective_allow_fallback = bool(
            routing_context is not None
            and (routing_context.allow_fallback or self._allow_fallback_default)
        )

        if (
            routing_decision is not None
            and routing_context is not None
            and effective_allow_fallback
            and self._fallback_executor is not None
        ):
            return self._fallback_executor.execute_stream(
                routing_context,
                routing_decision,
                stream_call=lambda provider_name, model_name: self._router.stream_chat(
                    messages,
                    routing_decision=_decision_for(
                        routing_decision,
                        provider_name,
                        model_name,
                    ),
                ),
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


def _decision_for(
    decision,
    provider_name: str,
    model_name: str,
) -> object:
    """Return a :class:`RoutingDecision` copy resolved to a provider/model.

    This avoids mutating the original routing decision while letting the
    fallback executor address a specific (provider, model) candidate.
    """
    from dataclasses import replace

    return replace(
        decision,
        provider_name=provider_name,
        model_name=model_name,
    )