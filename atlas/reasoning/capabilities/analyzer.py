"""
Atlas Capability Analyzer

Analyzes a ReasoningPlan and produces a list of Capability instances.
Contains no AI calls, no memory access, no knowledge access,
and no EventBus or service dependencies.
"""

from atlas.reasoning.capabilities.models import Capability
from atlas.reasoning.models import ReasoningPlan


class CapabilityAnalyzer:
    """
    Translates a ReasoningPlan into a ranked list of Capability instances.

    This is a pure logic component with no infrastructure dependencies.
    It does not call AI providers, access memory, query knowledge,
    or interact with any service.
    """

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
            capabilities.append(capability)

        capabilities.sort(
            key=lambda c: c.priority,
            reverse=True,
        )

        return capabilities

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