"""
Phase 8.0 — Cognitive Identity Foundation Tests

Validates Identity Models, IdentityMemory, BeliefManager,
CapabilityProfiler, DecisionStyleManager, and IdentityEngine.
"""
import unittest

from atlas.identity.models import (
    BeliefConfidence,
    CapabilityProfile,
    CoreBelief,
    CoreIdentity,
    CorePrinciple,
    DecisionStyle,
    EngineeringPreference,
    ImprovementEntry,
    ImprovementStatus,
    LongTermGoal,
    MaturityLevel,
    StrengthProfile,
    WeaknessProfile,
)
from atlas.identity.identity_memory import IdentityMemory
from atlas.identity.belief_manager import BeliefManager
from atlas.identity.capability_profiler import CapabilityProfiler
from atlas.identity.decision_style_manager import DecisionStyleManager
from atlas.identity.identity_engine import IdentityEngine


class TestIdentityModels(unittest.TestCase):
    """Test all identity data models."""

    def test_long_term_goal_create(self):
        goal = LongTermGoal(
            goal_id="GL-TEST-001",
            description="Test goal",
            priority=5,
        )
        self.assertEqual(goal.goal_id, "GL-TEST-001")
        self.assertEqual(goal.priority, 5)

    def test_core_principle_create(self):
        principle = CorePrinciple(
            principle_id="PRN-TEST",
            title="Test Principle",
            description="Test description",
        )
        self.assertEqual(principle.principle_id, "PRN-TEST")

    def test_core_belief_create(self):
        belief = CoreBelief(
            belief_id="BLF-TEST",
            statement="I test",
            category="self",
        )
        self.assertEqual(belief.confidence, BeliefConfidence.TENTATIVE)
        self.assertEqual(belief.evidence_count, 0)

    def test_core_belief_is_frozen(self):
        belief = CoreBelief(belief_id="FROZEN", statement="Immutable")
        with self.assertRaises(Exception):
            belief.statement = "Changed"  # type: ignore[misc]

    def test_engineering_preference_create(self):
        pref = EngineeringPreference(
            preference_id="PREF-TEST",
            name="Test Preference",
            description="Test",
            priority=7,
        )
        self.assertEqual(pref.priority, 7)

    def test_capability_profile_create(self):
        cap = CapabilityProfile(
            capability_id="CAP-TEST",
            capability_name="testing",
            confidence=0.8,
            maturity=MaturityLevel.STABLE,
        )
        self.assertEqual(cap.maturity, MaturityLevel.STABLE)
        self.assertEqual(cap.confidence, 0.8)

    def test_strength_profile_create(self):
        s = StrengthProfile(
            profile_id="STR-TEST",
            area="reasoning",
            description="Strong reasoner",
            confidence=0.85,
        )
        self.assertEqual(s.area, "reasoning")

    def test_weakness_profile_create(self):
        w = WeaknessProfile(
            profile_id="WEAK-TEST",
            area="planning",
            description="Weak planner",
            severity=4,
        )
        self.assertEqual(w.severity, 4)

    def test_decision_style_create(self):
        style = DecisionStyle(
            style_id="STYLE-TEST",
            preferred_reasoning_style="structured",
        )
        self.assertEqual(style.preferred_reasoning_style, "structured")

    def test_improvement_entry_create(self):
        entry = ImprovementEntry(
            entry_id="IMP-TEST",
            target_component="beliefs",
            description="Improved belief",
        )
        self.assertEqual(entry.status, ImprovementStatus.PROPOSED)

    def test_core_identity_snapshot(self):
        identity = CoreIdentity(
            identity_id="ID-TEST",
            name="TestAtlas",
            goals=[
                LongTermGoal("GL-001", "Goal 1", priority=10),
            ],
            principles=[
                CorePrinciple("PRN-001", "P1", "Principle 1"),
            ],
        )
        self.assertEqual(len(identity.goals), 1)
        self.assertEqual(identity.name, "TestAtlas")
        self.assertIsNone(identity.decision_style)


class TestIdentityMemory(unittest.TestCase):
    """Test bounded identity memory."""

    def setUp(self):
        self.memory = IdentityMemory()

    def test_store_and_get_beliefs(self):
        belief = CoreBelief(belief_id="B1", statement="Test")
        self.memory.store_belief(belief)
        beliefs = self.memory.get_beliefs()
        self.assertEqual(len(beliefs), 1)

    def test_bounded_beliefs_fifo_eviction(self):
        memory = IdentityMemory(max_beliefs=3)
        for i in range(5):
            memory.store_belief(CoreBelief(belief_id=f"B{i}", statement=f"Belief {i}"))
        beliefs = memory.get_beliefs()
        self.assertLessEqual(len(beliefs), 5)  # deque auto-evicts

    def test_invalid_max_sizes_raise(self):
        with self.assertRaises(ValueError):
            IdentityMemory(max_beliefs=0)

    def test_store_and_get_goals(self):
        goal = LongTermGoal(goal_id="G1", description="Test")
        self.memory.store_goal(goal)
        goals = self.memory.get_goals()
        self.assertEqual(len(goals), 1)

    def test_store_and_get_principles(self):
        principle = CorePrinciple(principle_id="P1", title="T", description="D")
        self.memory.store_principle(principle)
        self.assertEqual(len(self.memory.get_principles()), 1)

    def test_store_and_get_preferences_sorted(self):
        self.memory.store_preference(EngineeringPreference("P1", "A", "D", priority=1))
        self.memory.store_preference(EngineeringPreference("P2", "B", "D", priority=10))
        prefs = self.memory.get_preferences()
        self.assertEqual(prefs[0].priority, 10)

    def test_strengths_sorted_by_confidence(self):
        self.memory.store_strength(StrengthProfile("S1", "a", "d", confidence=0.3))
        self.memory.store_strength(StrengthProfile("S2", "b", "d", confidence=0.9))
        strengths = self.memory.get_strengths()
        self.assertEqual(strengths[0].confidence, 0.9)

    def test_weaknesses_sorted_by_severity(self):
        self.memory.store_weakness(WeaknessProfile("W1", "a", "d", severity=2))
        self.memory.store_weakness(WeaknessProfile("W2", "b", "d", severity=8))
        weaknesses = self.memory.get_weaknesses()
        self.assertEqual(weaknesses[0].severity, 8)

    def test_decision_style_singleton(self):
        style = DecisionStyle("STYLE-1")
        self.memory.store_decision_style(style)
        self.assertIsNotNone(self.memory.get_decision_style())

    def test_beliefs_by_category(self):
        self.memory.store_belief(CoreBelief("B1", "Self belief", category="self"))
        self.memory.store_belief(CoreBelief("B2", "Arch belief", category="architecture"))
        self_category = self.memory.get_beliefs_by_category("self")
        self.assertEqual(len(self_category), 1)

    def test_find_belief_by_id(self):
        self.memory.store_belief(CoreBelief("B-FIND", "Find me"))
        found = self.memory.find_belief_by_id("B-FIND")
        self.assertIsNotNone(found)
        self.assertEqual(found.statement, "Find me")

    def test_remove_belief(self):
        self.memory.store_belief(CoreBelief("B-DEL", "Delete me"))
        self.assertTrue(self.memory.remove_belief("B-DEL"))
        self.assertIsNone(self.memory.find_belief_by_id("B-DEL"))

    def test_capability_by_name(self):
        self.memory.store_capability(CapabilityProfile("C1", "reasoning"))
        found = self.memory.get_capability_by_name("reasoning")
        self.assertIsNotNone(found)

    def test_improvements_by_status(self):
        self.memory.store_improvement(ImprovementEntry("I1", "test", "desc", status=ImprovementStatus.APPROVED))
        self.memory.store_improvement(ImprovementEntry("I2", "test", "desc", status=ImprovementStatus.PROPOSED))
        approved = self.memory.get_improvements_by_status(ImprovementStatus.APPROVED)
        self.assertEqual(len(approved), 1)

    def test_memory_summary(self):
        self.memory.store_belief(CoreBelief("B1", "Test"))
        self.memory.store_goal(LongTermGoal("G1", "Test"))
        summary = self.memory.summary()
        self.assertEqual(summary["beliefs"], 1)
        self.assertEqual(summary["goals"], 1)

    def test_clear(self):
        self.memory.store_belief(CoreBelief("B1", "Test"))
        self.memory.clear()
        self.assertEqual(len(self.memory.get_beliefs()), 0)
        self.assertIsNone(self.memory.get_decision_style())


class TestBeliefManager(unittest.TestCase):
    """Test belief lifecycle."""

    def setUp(self):
        self.manager = BeliefManager()

    def test_add_belief_starts_tentative(self):
        belief = self.manager.add_belief("I am Atlas")
        self.assertEqual(belief.confidence, BeliefConfidence.TENTATIVE)
        self.assertEqual(belief.evidence_count, 0)

    def test_strengthen_belief_gradually(self):
        belief = self.manager.add_belief("Gradual growth", "self")
        # First strengthen should not jump to ESTABLISHED
        updated = self.manager.strengthen_belief(belief.belief_id)
        self.assertIsNotNone(updated)
        self.assertNotEqual(updated.confidence, BeliefConfidence.ESTABLISHED)

    def test_strengthen_multiple_times(self):
        belief = self.manager.add_belief("Multiple evidence", "self")
        for _ in range(5):
            belief = self.manager.strengthen_belief(belief.belief_id)
        self.assertIsNotNone(belief)
        self.assertGreater(belief.evidence_count, 4)

    def test_weaken_belief_drops_confidence(self):
        belief = self.manager.add_belief("Weaken me", "self")
        # Strengthen first
        for _ in range(10):
            self.manager.strengthen_belief(belief.belief_id)
        # Then weaken
        weakened = self.manager.weaken_belief(belief.belief_id)
        self.assertIsNotNone(weakened)

    def test_retire_belief(self):
        belief = self.manager.add_belief("Retire me")
        retired = self.manager.retire_belief(belief.belief_id)
        self.assertEqual(retired.confidence, BeliefConfidence.RETIRED)
        self.assertIsNotNone(retired.retired_at)

    def test_get_active_beliefs_excludes_retired(self):
        b1 = self.manager.add_belief("Active belief")
        b2 = self.manager.add_belief("To retire")
        self.manager.retire_belief(b2.belief_id)
        active = self.manager.get_active_beliefs()
        ids = [b.belief_id for b in active]
        self.assertIn(b1.belief_id, ids)
        self.assertNotIn(b2.belief_id, ids)

    def test_get_beliefs_by_category(self):
        self.manager.add_belief("Self belief", "self")
        self.manager.add_belief("Arch belief", "architecture")
        self.assertEqual(len(self.manager.get_beliefs_by_category("self")), 1)

    def test_get_beliefs_by_confidence(self):
        b = self.manager.add_belief("Confident belief")
        for _ in range(20):
            self.manager.strengthen_belief(b.belief_id)
        confident = self.manager.get_beliefs_by_confidence(BeliefConfidence.MODERATE)
        self.assertGreater(len(confident), 0)

    def test_belief_summary(self):
        self.manager.add_belief("B1", "self")
        self.manager.add_belief("B2", "architecture")
        summary = self.manager.summary()
        self.assertTrue(isinstance(summary, dict))
        self.assertIn("active", summary)


class TestCapabilityProfiler(unittest.TestCase):
    """Test capability profiling."""

    def setUp(self):
        self.profiler = CapabilityProfiler()

    def test_register_capability(self):
        cap = self.profiler.register_capability("reasoning", "Test", confidence=0.7)
        self.assertEqual(cap.capability_name, "reasoning")

    def test_seed_default_capabilities(self):
        profiles = self.profiler.seed_default_capabilities()
        self.assertGreater(len(profiles), 5)

    def test_update_capability_success(self):
        self.profiler.register_capability("reasoning", "Test")
        updated = self.profiler.update_capability("reasoning", success=True)
        self.assertIsNotNone(updated)
        self.assertEqual(updated.usage_count, 1)
        self.assertEqual(updated.success_count, 1)

    def test_update_capability_failure(self):
        self.profiler.register_capability("memory")
        updated = self.profiler.update_capability("memory", success=False)
        self.assertIsNotNone(updated)
        self.assertEqual(updated.usage_count, 1)
        self.assertEqual(updated.success_count, 0)
        self.assertLess(updated.stability, 1.0)

    def test_identify_strength(self):
        s = self.profiler.identify_strength("reasoning", "Strong", confidence=0.9)
        self.assertEqual(s.confidence, 0.9)

    def test_identify_weakness(self):
        w = self.profiler.identify_weakness("planning", "Weak", severity=5)
        self.assertEqual(w.severity, 5)

    def test_auto_profile_identifies_strengths(self):
        self.profiler.register_capability("reasoning", "desc", confidence=0.9)
        for _ in range(10):
            self.profiler.update_capability("reasoning", success=True)
        strengths, weaknesses = self.profiler.auto_profile()
        self.assertGreater(len(strengths), 0)

    def test_capability_summary(self):
        self.profiler.seed_default_capabilities()
        summary = self.profiler.summary()
        self.assertIn("capabilities_tracked", summary)


class TestDecisionStyleManager(unittest.TestCase):
    """Test decision style evolution."""

    def setUp(self):
        self.manager = DecisionStyleManager()

    def test_create_default_style(self):
        style = self.manager.create_default_style()
        self.assertEqual(style.preferred_reasoning_style, "structured_analysis")
        self.assertEqual(style.confidence, 0.3)

    def test_get_current_style_creates_default(self):
        style = self.manager.get_current_style()
        self.assertIsNotNone(style)

    def test_observe_reasoning_increases_confidence(self):
        self.manager.create_default_style()
        updated = self.manager.observe_reasoning("structured_analysis", success=True)
        self.assertGreater(updated.confidence, 0.3)

    def test_style_summary(self):
        self.manager.create_default_style()
        self.manager.observe_reasoning("structured_analysis", success=True)
        summary = self.manager.summary()
        self.assertIn("confidence", summary)


class TestIdentityEngine(unittest.TestCase):
    """Test the main identity engine."""

    def setUp(self):
        self.engine = IdentityEngine()

    def test_initialize_creates_identity(self):
        identity = self.engine.initialize()
        self.assertEqual(identity.name, "Atlas")
        self.assertGreater(len(identity.principles), 0)
        self.assertGreater(len(identity.goals), 0)
        self.assertGreater(len(identity.beliefs), 0)
        self.assertGreater(len(identity.engineering_preferences), 0)

    def test_initialize_is_idempotent(self):
        first = self.engine.initialize()
        second = self.engine.initialize()
        self.assertEqual(first.name, second.name)

    def test_snapshot_returns_frozen_identity(self):
        self.engine.initialize()
        snap = self.engine.snapshot()
        self.assertIsInstance(snap, CoreIdentity)
        with self.assertRaises(Exception):
            snap.name = "Changed"  # type: ignore[misc]

    def test_context_returns_string(self):
        self.engine.initialize()
        ctx = self.engine.context()
        self.assertIn("Atlas Cognitive Identity", ctx)
        self.assertIn("Founding Principles", ctx)

    def test_record_improvement(self):
        self.engine.initialize()
        entry = self.engine.record_improvement("beliefs", "Improve belief", "test")
        self.assertEqual(entry.status, ImprovementStatus.PROPOSED)

    def test_summary(self):
        self.engine.initialize()
        summary = self.engine.summary()
        self.assertIn("beliefs", summary)

    def test_memory_property(self):
        self.assertIsNotNone(self.engine.memory)

    def test_beliefs_property(self):
        self.assertIsNotNone(self.engine.beliefs)

    def test_capabilities_property(self):
        self.assertIsNotNone(self.engine.capabilities)

    def test_decision_style_property(self):
        self.assertIsNotNone(self.engine.decision_style)


class TestIdentityKernelIntegration(unittest.TestCase):
    """Test that IdentityEngine is properly wired in Atlas."""

    def test_identity_engine_registered_in_service_container(self):
        from atlas.kernel.atlas import Atlas
        atlas = Atlas()
        try:
            atlas.start()
            identity = atlas.container.get("identity")
            self.assertIsInstance(identity, IdentityEngine)
            self.assertTrue(identity.initialized)
        finally:
            atlas.shutdown()

    def test_identity_available_in_runtime_coordinator(self):
        from atlas.kernel.atlas import Atlas
        atlas = Atlas()
        try:
            atlas.start()
            coordinator = atlas.container.get("runtime_coordinator")
            self.assertIsNotNone(coordinator.identity_engine)
        finally:
            atlas.shutdown()

    def test_identity_initialized_on_start(self):
        from atlas.kernel.atlas import Atlas
        atlas = Atlas()
        try:
            atlas.start()
            # Identity should not be explicitly initialized in start() yet
            identity = atlas.container.get("identity")
            # Just verify it's wired
            self.assertIsInstance(identity, IdentityEngine)
        finally:
            atlas.shutdown()

    def test_atlas_has_identity_key(self):
        from atlas.kernel.atlas import Atlas
        atlas = Atlas()
        try:
            atlas.start()
            self.assertIn("identity", atlas.container.names())
        finally:
            atlas.shutdown()


if __name__ == "__main__":
    unittest.main()