"""
Atlas Capability Analyzer

Analyzes a ReasoningPlan and produces a list of Capability instances.
Contains no AI calls, no memory access, no knowledge access,
and no EventBus or service dependencies.
"""

from atlas.reasoning.capabilities.models import Capability
from atlas.reasoning.models import ReasoningPlan

# Maximum priority change applied per learning adjustment. The bias is
# deterministic and bounded so learning can influence — but never
# override — the analyzer's normal capability mapping.
_MAX_PRIORITY_ADJUSTMENT = 3
# Minimum total uses before a strategy record may influence selection.
_MIN_EVIDENCE_USES = 3


class _StrategyPerformanceProvider:
    """Optional duck-typed boundary over a strategy-performance store.

    Expected optional method:
      - get_strategy_by_name(name) -> record | None

    The record must expose ``success_rate`` and ``total_uses``. Missing
    or failing lookups degrade to no adjustment.
    """

    def __init__(self, store: object | None = None) -> None:
        self._store = store

    def get_strategy_performance(self, capability_name: str):
        """Return the performance record for a capability, or None."""
        if self._store is None:
            return None
        getter = getattr(self._store, "get_strategy_by_name", None)
        if not callable(getter):
            return None
        try:
            return getter(capability_name)
        except Exception:
            return None


class CapabilityAnalyzer:
    """
    Translates a ReasoningPlan into a ranked list of Capability instances.

    This is a pure logic component with no infrastructure dependencies.
    It does not call AI providers, access memory, query knowledge,
    or interact with any service.

    Optional learning evidence (Phase 20 Batch 4): when a
    ``learning_provider`` is injected, historical strategy performance can
    adjust capability priority within a bounded range. With no provider,
    selection is unchanged.
    """

    def __init__(self, learning_provider: object | None = None) -> None:
        """Initialise the analyzer.

        Args:
            learning_provider: Optional strategy-performance provider
                (e.g. the kernel-owned learning store). When None,
                selection is unchanged.
        """
        self._learning_provider = (
            _StrategyPerformanceProvider(learning_provider)
            if learning_provider is not None
            else None
        )

    def analyze(
        self,
        plan: ReasoningPlan,
    ) -> list[Capability]:
        """
        Produce a list of Capability instances from a ReasoningPlan.

        Each step in the plan is evaluated to determine which
        capabilities are required. Capabilities are returned in
        priority order.

        Args:
            plan: The ReasoningPlan to analyze.

        Returns:
            A list of Capability instances sorted by priority.
        """

        capabilities: list[Capability] = []

        for step in plan.steps:
            capability = self._select_capability(step)
            self._apply_learning_adjustment(capability)
            capabilities.append(capability)

        capabilities.sort(
            key=lambda c: c.priority,
            reverse=True,
        )

        return capabilities

    def analyze_step(
        self,
        step,
    ) -> Capability:
        """
        Produce a Capability for a single step-like object.

        The step may be a ``ReasoningStep`` or a ``PlanningStep``; only
        the ``action`` attribute is needed. This supports plan-driven
        capability selection (Phase 20, Batch 3) where each plan step is
        independently mapped to a capability.

        Args:
            step: A step-like object exposing an ``action`` attribute.

        Returns:
            The Capability selected for the step's action.
        """

        capability = self._select_capability(step)
        self._apply_learning_adjustment(capability)
        return capability

    def _select_capability(
        self,
        step,
    ) -> Capability:
        """
        Select a capability for a single reasoning step.

        Currently maps step actions to default capabilities.
        This method can be extended without adding infrastructure
        dependencies.
        """

        action = step.action or "unknown"

        action_map = {
            "respond": Capability(
                name="conversation",
                priority=10,
                reason=f"Respond to user input via conversation",
                metadata={"action": action},
            ),
            "query": Capability(
                name="knowledge_retrieval",
                priority=8,
                reason=f"Query knowledge base for information",
                metadata={"action": action},
            ),
            "analyze": Capability(
                name="analysis",
                priority=6,
                reason=f"Analyze provided data or context",
                metadata={"action": action},
            ),
            "execute": Capability(
                name="task_execution",
                priority=7,
                reason=f"Execute a defined task or operation",
                metadata={"action": action},
            ),
            "idle": Capability(
                name="noop",
                priority=0,
                reason="No action required",
                metadata={"action": action},
            ),
        }

        return action_map.get(
            action,
            Capability(
                name="general",
                priority=5,
                reason=f"Handle action: {action}",
                metadata={"action": action},
            ),
        )

    def _apply_learning_adjustment(self, capability: Capability) -> None:
        """
        Adjust a capability's priority from recorded strategy performance.

        Evidence is consulted under the capability's mapped name. When the
        analyzer mapped an unregistered plan-step action to the generic
        fallback (``name == "general"``), the step action itself (carried
        in ``metadata["action"]``) is consulted as well so capability-keyed
        evidence recorded for plan-reachable Track capabilities (e.g.
        ``research.coordinate``) can influence later selection (Phase 21
        Batch 3 research feedback).

        The adjustment is deterministic and bounded:
          - no provider → no change
          - no record for a consulted key → no change for that key
          - fewer than MIN_EVIDENCE_USES uses → no change
          - otherwise priority shifts by at most MAX_PRIORITY_ADJUSTMENT.

        Learning may reorder candidates but never replaces the analyzer's
        mapped capability semantics (name, reason, metadata unchanged).
        """
        if self._learning_provider is None:
            return

        keys = [capability.name]
        action = capability.metadata.get("action")
        if capability.name == "general" and isinstance(action, str) and action.strip():
            keys.append(action.strip())

        delta = 0
        for key in keys:
            key_delta = self._evidence_delta_for_key(key)
            if abs(key_delta) > abs(delta):
                delta = key_delta

        if delta:
            capability.priority = capability.priority + delta

    def _evidence_delta_for_key(self, key: str) -> int:
        """Bounded priority delta from strategy evidence for one key."""
        provider = self._learning_provider
        if provider is None:
            return 0
        performance = provider.get_strategy_performance(key)
        if performance is None:
            return 0

        try:
            success_rate = float(getattr(performance, "success_rate", 0.5))
            total_uses = int(getattr(performance, "total_uses", 0))
        except (TypeError, ValueError):
            return 0

        if total_uses < _MIN_EVIDENCE_USES:
            return 0

        # Bias proportional to how far from neutral (0.5) the success
        # rate sits, scaled into the bounded adjustment range.
        delta = round((success_rate - 0.5) * 4.0)
        return max(
            -_MAX_PRIORITY_ADJUSTMENT,
            min(_MAX_PRIORITY_ADJUSTMENT, delta),
        )
