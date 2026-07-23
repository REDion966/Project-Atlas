"""
Atlas Reasoning Controller

Produces ReasoningPlan instances from CognitionDecision objects.
Contains no AI calls, no memory access, and no knowledge access.
"""

from atlas.cognition.decision import CognitionDecision
from atlas.reasoning.models import ReasoningPlan, ReasoningStep


class ReasoningController:
    """
    Translates a CognitionDecision into a structured ReasoningPlan.

    This is a pure logic component with no infrastructure dependencies.
    It does not call AI providers, access memory, or query knowledge.
    """

    def create_plan(
        self,
        decision: CognitionDecision,
    ) -> ReasoningPlan:
        """
        Produce a ReasoningPlan from a CognitionDecision.

        Args:
            decision: The CognitionDecision to translate.

        Returns:
            A ReasoningPlan with steps derived from the decision.
        """

        goal = f"{decision.action}: {decision.reasoning}"

        steps = [
            ReasoningStep(
                description=f"Process decision action: {decision.action}",
                action=decision.action,
                parameters=dict(decision.data),
            ),
        ]

        return ReasoningPlan(
            goal=goal,
            steps=steps,
            metadata={
                "source": "cognition",
                "action": decision.action,
            },
        )