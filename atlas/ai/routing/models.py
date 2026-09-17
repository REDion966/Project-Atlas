"""
Atlas AI Routing Models

Pure dataclasses for model routing decisions.
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ModelProfile:
    """
    Describes an AI model's routing characteristics.

    Attributes:
        provider_name: Name of the provider hosting this model.
        model_name: Model identifier within the provider.
        complexity_score: 0.0-1.0 capability score for this model.
        latency_class: Latency class, e.g. "fast", "medium", "slow".
        cost_tier: 0.0-1.0 relative cost tier.
        supported_tasks: Task types this model supports.
        priority: Higher values are preferred when selecting fallbacks.
        metadata: Additional routing context.
    """

    provider_name: str
    model_name: str
    complexity_score: float = 0.5
    latency_class: str = "medium"
    cost_tier: float = 0.5
    supported_tasks: list[str] = field(default_factory=list)
    priority: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class RoutingRequest:
    """
    Describes a request's routing requirements.

    Attributes:
        complexity: 0.0-1.0 estimated complexity of the request.
        latency_requirement: Desired latency class, e.g. "fast", "any".
        task_type: Type of task being requested.
        context_size: Approximate context size in tokens.
        metadata: Additional request context.
    """

    complexity: float = 0.5
    latency_requirement: str = "any"
    task_type: str = "conversation"
    context_size: int = 0
    # When True, a caller explicitly permits policy-controlled fallback
    # to an eligible candidate on transient/model-unavailable failures.
    # Default False so all existing callers retain current behavior.
    allow_fallback: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


#: Providers that perform network I/O to an external model service.
#: Selection of any of these requires the explicit external-providers
#: opt-in; when the opt-in is off, the model router resolves only the
#: local no-network tier. Unknown provider names are treated as external
#: (deny-by-default).
EXTERNAL_PROVIDER_NAMES: frozenset[str] = frozenset(
    {"Ollama", "OpenAI", "LM Studio", "Anthropic", "OpenRouter"}
)

#: Provider names explicitly recognized as local no-network tiers. When
#: the external-providers opt-in is off, ONLY these profiles are eligible
#: for selection; every other name — known external or unknown — is
#: excluded. This is the allowlist that makes the opt-out policy
#: genuinely deny-by-default.
LOCAL_PROVIDER_NAMES: frozenset[str] = frozenset(
    {"Mock Provider"}
)


@dataclass
class RoutingDecision:
    """
    The result of a model routing decision.

    Attributes:
        provider_name: Selected provider.
        model_name: Selected model within the provider.
        confidence: 0.0-1.0 confidence in this decision.
        reason: Human-readable explanation.
        fallback_chain: Ordered list of (provider_name, model_name) fallbacks.
        metadata: Additional decision context.
    """

    provider_name: str
    model_name: str
    confidence: float = 1.0
    reason: str = ""
    fallback_chain: list[tuple[str, str]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
