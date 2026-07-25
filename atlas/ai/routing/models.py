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
    metadata: dict[str, Any] = field(default_factory=dict)


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
