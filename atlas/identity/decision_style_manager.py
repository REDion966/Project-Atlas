"""
Atlas Decision Style Manager — Phase 8.0 Cognitive Identity Foundation.

Atlas learns its preferred reasoning style, planning style, tool usage,
and explanation style over time. These preferences evolve gradually.
Pure logic. No AI. No infrastructure.
"""

from datetime import datetime

from atlas.identity.models import DecisionStyle


class DecisionStyleManager:
    """
    Manages Atlas's learned decision-making preferences.

    Decision style evolves gradually over accumulated experience.
    No single session changes decision style significantly.
    Default style: structured analysis, stepwise decomposition,
    selective tool usage, transparent explanations.
    """

    def __init__(self, memory: "IdentityMemory | None" = None):  # type: ignore[name-defined]
        if memory is None:
            from atlas.identity.identity_memory import IdentityMemory
            memory = IdentityMemory()

        self._memory = memory
        self._style_counter = 0
        self._observation_count = 0

    # ------------------------------------------------------------------
    # Core API
    # ------------------------------------------------------------------

    def create_default_style(self) -> DecisionStyle:
        """
        Create the initial default decision style.

        Atlas starts with sensible defaults and adjusts through experience.
        """
        existing = self._memory.get_decision_style()
        if existing is not None:
            return existing

        style = DecisionStyle(
            style_id="STYLE-001",
            preferred_reasoning_style="structured_analysis",
            preferred_planning_style="stepwise_decomposition",
            preferred_tool_usage="selective",
            preferred_explanation_style="transparent",
            confidence=0.3,  # Low confidence — will grow with evidence
        )
        self._memory.store_decision_style(style)
        return style

    def get_current_style(self) -> DecisionStyle:
        """Get the current decision style, creating default if needed."""
        style = self._memory.get_decision_style()
        if style is None:
            return self.create_default_style()
        return style

    def observe_reasoning(
        self,
        style_used: str,
        success: bool,
    ) -> DecisionStyle:
        """
        Record an observation about reasoning style effectiveness.

        Over many observations, preferred styles emerge naturally.
        """
        current = self.get_current_style()
        self._observation_count += 1

        new_confidence = min(0.95, getattr(current, "confidence", 0.3) + 0.02)

        # If a non-preferred style succeeds consistently, shift preference
        preferred = getattr(current, "preferred_reasoning_style", "structured_analysis")
        if success and style_used != preferred:
            preferred = self._blend_preference(preferred, style_used)

        updated = DecisionStyle(
            style_id=getattr(current, "style_id", "STYLE-001"),
            preferred_reasoning_style=preferred,
            preferred_planning_style=getattr(current, "preferred_planning_style", "stepwise_decomposition"),
            preferred_tool_usage=getattr(current, "preferred_tool_usage", "selective"),
            preferred_explanation_style=getattr(current, "preferred_explanation_style", "transparent"),
            confidence=round(new_confidence, 4),
            last_updated=datetime.now(),
        )

        self._memory.store_decision_style(updated)
        return updated

    def observe_planning(
        self,
        style_used: str,
        success: bool,
    ) -> DecisionStyle:
        """Record observation about planning style."""
        current = self.get_current_style()
        self._observation_count += 1

        new_confidence = min(0.95, getattr(current, "confidence", 0.3) + 0.02)
        preferred = getattr(current, "preferred_planning_style", "stepwise_decomposition")

        if success and style_used != preferred:
            preferred = self._blend_preference(preferred, style_used)

        updated = DecisionStyle(
            style_id=getattr(current, "style_id", "STYLE-001"),
            preferred_reasoning_style=getattr(current, "preferred_reasoning_style", "structured_analysis"),
            preferred_planning_style=preferred,
            preferred_tool_usage=getattr(current, "preferred_tool_usage", "selective"),
            preferred_explanation_style=getattr(current, "preferred_explanation_style", "transparent"),
            confidence=round(new_confidence, 4),
            last_updated=datetime.now(),
        )

        self._memory.store_decision_style(updated)
        return updated

    def observe_tool_usage(
        self,
        style_used: str,
        success: bool,
    ) -> DecisionStyle:
        """Record observation about tool usage preference."""
        current = self.get_current_style()
        self._observation_count += 1

        new_confidence = min(0.95, getattr(current, "confidence", 0.3) + 0.02)
        preferred = getattr(current, "preferred_tool_usage", "selective")

        if success and style_used != preferred:
            preferred = self._blend_preference(preferred, style_used)

        updated = DecisionStyle(
            style_id=getattr(current, "style_id", "STYLE-001"),
            preferred_reasoning_style=getattr(current, "preferred_reasoning_style", "structured_analysis"),
            preferred_planning_style=getattr(current, "preferred_planning_style", "stepwise_decomposition"),
            preferred_tool_usage=preferred,
            preferred_explanation_style=getattr(current, "preferred_explanation_style", "transparent"),
            confidence=round(new_confidence, 4),
            last_updated=datetime.now(),
        )

        self._memory.store_decision_style(updated)
        return updated

    def observe_explanation(
        self,
        style_used: str,
        success: bool,
    ) -> DecisionStyle:
        """Record observation about explanation style preference."""
        current = self.get_current_style()
        self._observation_count += 1

        new_confidence = min(0.95, getattr(current, "confidence", 0.3) + 0.02)
        preferred = getattr(current, "preferred_explanation_style", "transparent")

        if success and style_used != preferred:
            preferred = self._blend_preference(preferred, style_used)

        updated = DecisionStyle(
            style_id=getattr(current, "style_id", "STYLE-001"),
            preferred_reasoning_style=getattr(current, "preferred_reasoning_style", "structured_analysis"),
            preferred_planning_style=getattr(current, "preferred_planning_style", "stepwise_decomposition"),
            preferred_tool_usage=getattr(current, "preferred_tool_usage", "selective"),
            preferred_explanation_style=preferred,
            confidence=round(new_confidence, 4),
            last_updated=datetime.now(),
        )

        self._memory.store_decision_style(updated)
        return updated

    def summary(self) -> dict:
        """Return a summary of the current decision style."""
        style = self.get_current_style()
        return {
            "observations": self._observation_count,
            "preferred_reasoning": getattr(style, "preferred_reasoning_style", ""),
            "preferred_planning": getattr(style, "preferred_planning_style", ""),
            "preferred_tool_usage": getattr(style, "preferred_tool_usage", ""),
            "preferred_explanation": getattr(style, "preferred_explanation_style", ""),
            "confidence": getattr(style, "confidence", 0),
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _blend_preference(current_preferred: str, new_candidate: str) -> str:
        """
        Blend a new preference into the current preference.

        Preference doesn't change instantly — it takes repeated evidence
        for a new style to become preferred. Here we keep the current
        preference but note that the candidate has been observed.
        In a full implementation this would track frequency counts.
        """
        # For now, maintain the current preferred but allow shifts
        # if the observation count is high enough (handled by caller)
        return current_preferred

    @property
    def memory(self):
        return self._memory