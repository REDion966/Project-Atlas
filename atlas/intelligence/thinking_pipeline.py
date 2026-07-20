"""
Atlas Thinking Pipeline
"""

from __future__ import annotations

from atlas.intelligence.reasoning_engine import ReasoningEngine
from atlas.intelligence.reasoning_context import ReasoningContext
from atlas.intelligence.decision_engine import DecisionEngine
from atlas.intelligence.reflection_engine import ReflectionEngine
from atlas.intelligence.thinking_result import ThinkingResult


class ThinkingPipeline:

    def __init__(self):

        self.reasoning = ReasoningEngine()

        self.decision = DecisionEngine()

        self.reflection = ReflectionEngine()

    def think(
        self,
        goal: str,
    ) -> ThinkingResult:

        reasoning = self.reasoning.reason(
            ReasoningContext(goal=goal)
        )

        decision = self.decision.decide(reasoning)

        reflection = self.reflection.reflect(decision)

        return ThinkingResult(
            conclusion=reasoning.conclusion,
            action=decision.action,
            reflection=reflection.feedback,
        )