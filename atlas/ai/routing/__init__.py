"""
Atlas AI Routing Package

Model routing components for selecting the best AI model per request.
"""

from atlas.ai.routing.models import (
    ModelProfile,
    RoutingDecision,
    RoutingRequest,
)
from atlas.ai.routing.policy import RoutingPolicy
from atlas.ai.routing.registry import ModelProfileRegistry
from atlas.ai.routing.router import ModelRouter


__all__ = [
    "ModelProfile",
    "RoutingDecision",
    "RoutingRequest",
    "RoutingPolicy",
    "ModelProfileRegistry",
    "ModelRouter",
]
