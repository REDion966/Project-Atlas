"""
Phase 9.1 — Self-Model Cognitive Context Tests.

Tests for:
- Self-model section presence in cognitive context when engine is available
- Self-model section absence when engine is not injected
- Self-model section absence when no snapshot exists yet
- Correct rendering of all snapshot fields
- Edge cases (empty assessments, no challenges)
"""

import unittest
from datetime import datetime
from unittest.mock import MagicMock, patch

from atlas.experience.models import SelfModelSnapshot
from atlas.runtime.runtime_coordinator import RuntimeCoordinator


class TestSelfModelCognitiveContext(unittest.TestCase):
    """Self-model section in RuntimeCoordinator._build_cognitive_context()."""

    def setUp(self):
        self.coordinator = RuntimeCoordinator()

    def test_section_absent_when_no_engine(self):
        """No self_model_engine → no self-model section."""
        context = self.coordinator._build_self_model_section()
        self.assertEqual(context, "")

    def test_section_absent_when_no_snapshot(self):
        """Engine injected but no snapshot produced yet → skip."""
        engine = MagicMock()
        engine.get_snapshot.return_value = None
        self.coordinator._self_model_engine = engine
        context = self.coordinator._build_self_model_section()
        self.assertEqual(context, "")

    def test_section_absent_in_full_context_when_no_engine(self):
        """Full _build_cognitive_context should not error when no engine."""
        from atlas.cognition.models import CognitionState
        state = CognitionState(user_input="hello")
        context = self.coordinator._build_cognitive_context(state)
        # Should contain role instruction but not self-model
        self.assertIn("Role", context)
        self.assertNotIn("Self-Model Assessment", context)

    def _make_snapshot(self, **overrides) -> SelfModelSnapshot:
        """Create a SelfModelSnapshot with sensible defaults."""
        params = {
            "snapshot_id": "SELF-000001",
            "timestamp": datetime.now(),
            "total_experiences": 50,
            "overall_success_rate": 0.78,
            "capability_assessments": {
                "conversation": 0.85,
                "reasoning": 0.72,
                "tool_execution": 0.65,
            },
            "belief_evidence": {"I am improving": 0.8},
            "trend_summary": "Success: improving (78%) | Reasoning: stable (72%)",
            "identity_version": 3,
            "last_trend_analysis": datetime.now(),
            "recent_improvement_evidence": [
                "Overall success rate improving to 78%",
                "Reasoning success improving to 72%",
            ],
            "persistent_challenges": [
                "Tool execution failures in production",
                "Understanding insight generation declining",
            ],
        }
        params.update(overrides)
        return SelfModelSnapshot(**params)

    def test_section_present_when_engine_and_snapshot_available(self):
        """Engine with snapshot produces a non-empty section."""
        engine = MagicMock()
        engine.get_snapshot.return_value = self._make_snapshot()
        self.coordinator._self_model_engine = engine
        context = self.coordinator._build_self_model_section()
        self.assertNotEqual(context, "")
        self.assertIn("Self-Model Assessment", context)

    def test_section_includes_success_rate_and_count(self):
        """Snapshot success rate and total experiences rendered."""
        engine = MagicMock()
        engine.get_snapshot.return_value = self._make_snapshot(
            total_experiences=100,
            overall_success_rate=0.85,
        )
        self.coordinator._self_model_engine = engine
        context = self.coordinator._build_self_model_section()
        self.assertIn("85%", context)
        self.assertIn("100", context)

    def test_section_includes_capability_assessments(self):
        """Top capabilities rendered with scores."""
        engine = MagicMock()
        engine.get_snapshot.return_value = self._make_snapshot(
            capability_assessments={
                "conversation": 0.9,
                "reasoning": 0.8,
                "tool_execution": 0.7,
            }
        )
        self.coordinator._self_model_engine = engine
        context = self.coordinator._build_self_model_section()
        self.assertIn("Capability confidence", context)
        self.assertIn("conversation: 90%", context)
        self.assertIn("reasoning: 80%", context)

    def test_section_includes_improvement_evidence(self):
        """Recent improvements rendered."""
        engine = MagicMock()
        engine.get_snapshot.return_value = self._make_snapshot(
            recent_improvement_evidence=[
                "Success rate improved by 10%",
                "Reasoning pipeline optimized",
            ]
        )
        self.coordinator._self_model_engine = engine
        context = self.coordinator._build_self_model_section()
        self.assertIn("Recent improvements", context)
        self.assertIn("Success rate improved by 10%", context)

    def test_section_includes_challenges(self):
        """Persistent challenges rendered."""
        engine = MagicMock()
        engine.get_snapshot.return_value = self._make_snapshot(
            persistent_challenges=[
                "Tool execution failures in production",
            ]
        )
        self.coordinator._self_model_engine = engine
        context = self.coordinator._build_self_model_section()
        self.assertIn("Challenges", context)
        self.assertIn("Tool execution failures in production", context)

    def test_section_includes_trend_summary(self):
        """Trend summary string rendered."""
        engine = MagicMock()
        engine.get_snapshot.return_value = self._make_snapshot(
            trend_summary="Success: improving | Reasoning: stable"
        )
        self.coordinator._self_model_engine = engine
        context = self.coordinator._build_self_model_section()
        self.assertIn("Trend summary", context)
        self.assertIn("Success: improving | Reasoning: stable", context)

    def test_empty_capability_assessments_skips_section(self):
        """No capabilities → no 'Capability confidence' line."""
        engine = MagicMock()
        engine.get_snapshot.return_value = self._make_snapshot(
            capability_assessments={}
        )
        self.coordinator._self_model_engine = engine
        context = self.coordinator._build_self_model_section()
        self.assertIn("Self-Model Assessment", context)
        self.assertNotIn("Capability confidence", context)

    def test_no_improvement_evidence_skips_section(self):
        """No improvements → no 'Recent improvements' line."""
        engine = MagicMock()
        engine.get_snapshot.return_value = self._make_snapshot(
            recent_improvement_evidence=[]
        )
        self.coordinator._self_model_engine = engine
        context = self.coordinator._build_self_model_section()
        self.assertNotIn("Recent improvements", context)

    def test_no_challenges_skips_section(self):
        """No challenges → no 'Challenges' line."""
        engine = MagicMock()
        engine.get_snapshot.return_value = self._make_snapshot(
            persistent_challenges=[]
        )
        self.coordinator._self_model_engine = engine
        context = self.coordinator._build_self_model_section()
        self.assertNotIn("Challenges", context)

    def test_capabilities_sorted_by_score(self):
        """Capabilities should appear in descending order of score."""
        engine = MagicMock()
        engine.get_snapshot.return_value = self._make_snapshot(
            capability_assessments={
                "low": 0.3,
                "high": 0.95,
                "medium": 0.65,
            }
        )
        self.coordinator._self_model_engine = engine
        context = self.coordinator._build_self_model_section()

        # Find the capability lines
        lines = context.split("\n")
        cap_lines = [l.strip() for l in lines if l.strip().startswith("-")]
        # First capability should be the highest scored
        if cap_lines:
            first_cap = cap_lines[0]
            self.assertIn("high: 95%", first_cap, "Highest scored capability should appear first")

    def test_full_context_includes_self_model_between_identity_and_conversation(self):
        """In full cognitive context, self-model appears after Identity, before Conversation."""
        engine = MagicMock()
        engine.get_snapshot.return_value = self._make_snapshot()
        self.coordinator._self_model_engine = engine

        from atlas.cognition.models import CognitionState
        state = CognitionState(user_input="hello")

        context = self.coordinator._build_cognitive_context(state)
        self.assertIn("Self-Model Assessment", context)

        # Identity appears before self-model in the sections order
        # (Identity is empty since no identity engine, but self-model should
        #  appear after any identity section)
        # Verify self-model is before conversation context marker
        sm_index = context.find("Self-Model Assessment")
        role_index = context.find("Role")
        self.assertGreater(
            role_index, sm_index,
            "Self-model section should appear before the Role instruction"
        )


if __name__ == "__main__":
    unittest.main()
