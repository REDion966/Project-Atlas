"""
Atlas Execution Package

Capability execution and dispatch layer for adaptive reasoning (Phase 6.3).
"""

from atlas.reasoning.execution.models import ExecutionResult, ExecutionRoute, CapabilityHandler
from atlas.reasoning.execution.registry import CapabilityRegistry
from atlas.reasoning.execution.dispatcher import CapabilityDispatcher
from atlas.reasoning.execution.routing import CapabilityRouter
from atlas.reasoning.execution.handlers import (
    DEFAULT_HANDLERS,
    conversation_handler,
    analysis_handler,
    task_execution_handler,
    noop_handler,
)


__all__ = [
    "ExecutionResult",
    "ExecutionRoute",
    "CapabilityHandler",
    "CapabilityRegistry",
    "CapabilityDispatcher",
    "CapabilityRouter",
    "DEFAULT_HANDLERS",
    "conversation_handler",
    "analysis_handler",
    "task_execution_handler",
    "noop_handler",
]
