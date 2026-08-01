"""
Atlas Goal Execution — ExecutionActionBinder Registry — Phase 15.2

Provides the abstract ``ExecutionActionBinder`` protocol and a registry
that resolves an ``ActionType`` discriminator to the concrete binder
responsible for translating a generic ``ExecutionAction`` envelope into
an executor-specific request.

Phase 15 registers exactly one binder: ``TOOL_INVOCATION`` →
``ToolExecutionActionBinder`` (defined in ``atlas/tools/execution_action_binder.py``).

Future phases add ``TASK_INVOCATION``, ``CAPABILITY_INVOCATION``,
``AGENT_INVOCATION`` binders without changing this module.

Pure logic. No infrastructure. No AI.
"""

from abc import ABC, abstractmethod
from typing import Any

from atlas.goals.execution_models import ActionType, ExecutionAction


class ExecutionActionBinder(ABC):
    """
    Abstract protocol for translating an ``ExecutionAction`` into an
    executor-specific request.

    Every binder declares the ``ActionType`` it handles. The registry
    uses this to route actions to the correct binder.

    Subclasses must implement:
      - ``action_type`` property
      - ``bind(action)`` → executor result
    """

    @property
    @abstractmethod
    def action_type(self) -> ActionType:
        """The ActionType discriminator this binder handles."""
        ...

    @abstractmethod
    def bind(self, action: ExecutionAction) -> Any:
        """
        Translate an ExecutionAction into an executor-specific request
        and return the executor's result.

        Args:
            action: The generic execution envelope.

        Returns:
            An executor-specific result object (e.g. ToolResult).
            The engine normalizes this into a GoalExecutorResult.
        """
        ...


class ExecutionActionBinderRegistry:
    """
    Registry that resolves ``ActionType`` → ``ExecutionActionBinder``.

    Thread-safe for registration only. Lookups are deterministic.
    """

    def __init__(self) -> None:
        self._binders: dict[ActionType, ExecutionActionBinder] = {}

    def register(self, binder: ExecutionActionBinder) -> None:
        """
        Register a binder for its declared ActionType.

        Args:
            binder: An ExecutionActionBinder instance.

        Raises:
            ValueError: If a binder is already registered for the same
                ActionType.
        """
        if binder.action_type in self._binders:
            raise ValueError(
                f"Binder already registered for ActionType "
                f"'{binder.action_type.name}'."
            )
        self._binders[binder.action_type] = binder

    def resolve(self, action_type: ActionType) -> ExecutionActionBinder | None:
        """
        Return the binder registered for an ActionType, or None.

        Args:
            action_type: The ActionType discriminator.

        Returns:
            The registered ExecutionActionBinder, or None.
        """
        return self._binders.get(action_type)

    @property
    def registered_types(self) -> list[ActionType]:
        """Return the currently registered ActionTypes."""
        return list(self._binders.keys())

    def clear(self) -> None:
        """Remove all registered binders."""
        self._binders.clear()