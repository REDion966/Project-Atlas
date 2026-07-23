"""
Atlas Execution Package

Capability execution and dispatch layer for adaptive reasoning (Phase 6.3).
"""

from atlas.reasoning.execution.models import ExecutionResult, ExecutionRoute, CapabilityHandler
from atlas.reasoning.execution.registry import CapabilityRegistry
from atlas.reasoning.execution.dispatcher import CapabilityDispatcher
from atlas.reasoning.execution.routing import CapabilityRouter


__all__ = [
    "ExecutionResult",
    "ExecutionRoute",
    "CapabilityHandler",
    "CapabilityRegistry",
    "CapabilityDispatcher",
    "CapabilityRouter",
]
