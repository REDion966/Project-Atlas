"""
Atlas Default Capability Handlers

Default pure runtime bridge handlers for adaptive reasoning capabilities.
These handlers are intentionally dependency-free and provide minimal
default behaviour for runtime integration. They are not final production
capability implementations.

Each handler accepts a parameters dictionary and returns a valid
ExecutionResult with success=True, the executed capability name, and
basic output metadata.
"""

from collections.abc import Callable

from atlas.reasoning.execution.models import ExecutionResult


def conversation_handler(params: dict) -> ExecutionResult:
    """
    Default handler for the ``conversation`` capability.

    Returns a successful execution result with a basic conversational
    acknowledgement. This is a placeholder for future runtime integration
    with a conversation service.
    """
    return ExecutionResult(
        capability="conversation",
        success=True,
        output={"status": "handled", "message": "Conversation request acknowledged."},
        metadata={"handler": "conversation_handler"},
    )


def knowledge_retrieval_handler(params: dict) -> ExecutionResult:
    """
    Default handler for the ``knowledge_retrieval`` capability.

    Returns a successful execution result indicating a knowledge query
    placeholder response.
    """
    return ExecutionResult(
        capability="knowledge_retrieval",
        success=True,
        output={"status": "handled", "message": "Knowledge request acknowledged."},
        metadata={"handler": "knowledge_retrieval_handler"},
    )


def analysis_handler(params: dict) -> ExecutionResult:
    """
    Default handler for the ``analysis`` capability.

    Returns a successful execution result with a placeholder analysis
    response. The input parameters are stored as metadata for inspection.
    """
    return ExecutionResult(
        capability="analysis",
        success=True,
        output={"status": "handled", "message": "Analysis request acknowledged."},
        metadata={"handler": "analysis_handler"},
    )


def task_execution_handler(params: dict) -> ExecutionResult:
    """
    Default handler for the ``task_execution`` capability.

    Returns a successful execution result indicating a task execution
    placeholder response.
    """
    return ExecutionResult(
        capability="task_execution",
        success=True,
        output={"status": "handled", "message": "Task request acknowledged."},
        metadata={"handler": "task_execution_handler"},
    )


def noop_handler(params: dict) -> ExecutionResult:
    """
    No-op handler for unsupported or unmapped capabilities.

    Always returns a successful result with an empty capability name
    and no operation performed. This provides a safe fallback when no
    specific handler is required.
    """
    return ExecutionResult(
        capability="",
        success=True,
        output={"status": "noop", "message": "No operation performed."},
        metadata={"handler": "noop_handler"},
    )


DEFAULT_HANDLERS: dict[str, Callable[[dict], ExecutionResult]] = {
    "conversation": conversation_handler,
    "knowledge_retrieval": knowledge_retrieval_handler,
    "analysis": analysis_handler,
    "task_execution": task_execution_handler,
    "noop": noop_handler,
}
"""
Mapping of default capability names to their placeholder handlers.

These handlers are intended for runtime integration testing and
bootstrapping only. Production systems are expected to register
specialised handlers at runtime.
"""
