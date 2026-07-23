"""
Atlas Execution Package

Capability execution and dispatch layer for adaptive reasoning (Phase 6.3).
"""

from atlas.reasoning.execution.models import ExecutionResult, CapabilityHandler
from atlas.reasoning.execution.registry import CapabilityRegistry
from atlas.reasoning.execution.dispatcher import CapabilityDispatcher


__all__ = [
    "ExecutionResult",
    "CapabilityHandler",
    "CapabilityRegistry",
    "CapabilityDispatcher",
]