"""
Atlas Tools — ToolExecutionActionBinder — Phase 15.2

Concrete ``ExecutionActionBinder`` for ``ActionType.TOOL_INVOCATION``.

Translates a generic ``ExecutionAction`` envelope into a ``ToolRequest``
that ``ToolEngine.fulfill()`` accepts, then returns the ``ToolResult``.

Phase 15 registers exactly this one binder. Future phases add binders
for TASK_INVOCATION, CAPABILITY_INVOCATION, and AGENT_INVOCATION.

Pure logic. Depends only on models. ToolEngine is injected.
"""

from typing import Any

from atlas.goals.execution_action_binders import ExecutionActionBinder
from atlas.goals.execution_models import ActionType, ExecutionAction
from atlas.tools.models import ToolRequest, ToolResult


class ToolExecutionActionBinder(ExecutionActionBinder):
    """
    Binds ``ActionType.TOOL_INVOCATION`` actions to ``ToolEngine.fulfill()``.

    The binder reads the executor-agnostic ``ExecutionAction.payload`` and
    ``.context`` to construct a ``ToolRequest``, delegates to ToolEngine,
    and returns the ``ToolResult``.

    This is the ONLY code that translates ``ExecutionAction`` → ``ToolRequest``.
    The GoalExecutionEngine never knows ToolRequest internals.
    """

    def __init__(self, tool_engine: Any) -> None:
        """
        Initialise the binder with the ToolEngine dependency.

        Args:
            tool_engine: A ToolEngine instance with ``fulfill(request)``
                method. Required — if None, ``bind()`` returns an error
                ToolResult.
        """
        self._tool_engine = tool_engine

    @property
    def action_type(self) -> ActionType:
        """Declare that this binder handles TOOL_INVOCATION actions."""
        return ActionType.TOOL_INVOCATION

    def bind(self, action: ExecutionAction) -> Any:
        """
        Translate an ExecutionAction into a ToolRequest and execute it.

        Args:
            action: The generic execution envelope with action_type
                TOOL_INVOCATION.

        Returns:
            A ToolResult from ToolEngine.fulfill(), or an error
            ToolResult if tool_engine is unavailable.
        """
        if self._tool_engine is None:
            return ToolResult(
                tool_name="",
                success=False,
                error="ToolEngine is not available.",
            )

        # Build a ToolRequest from the executor-agnostic envelope.
        goal_description = action.payload.get("description", "")
        category = action.context.get("category", "")
        goal_id = action.context.get("goal_id", "")

        request = ToolRequest(
            goal=f"Execute goal {goal_id}: {goal_description}",
            context={
                "goal_id": goal_id,
                "category": category,
                "action_id": action.action_id,
                "confidence": str(action.confidence),
            },
        )

        return self._tool_engine.fulfill(request)