import unittest

from atlas.kernel.atlas import Atlas
from atlas.evolution.insight_scorer import InsightScorer
from atlas.evolution.intelligence_engine import EvolutionIntelligenceEngine
from atlas.evolution.decision_intelligence import DecisionIntelligenceEngine
from atlas.evolution.knowledge.query import EvolutionKnowledgeQuery
from atlas.evolution.scheduler import EvolutionScheduler


class TestKernel(unittest.TestCase):

    def test_create_atlas(self):
        atlas = Atlas()

        self.assertIsNotNone(atlas)

    def test_memory_service_registered_after_start(self):
        atlas = Atlas()
        atlas.start()

        self.assertTrue(atlas.container.has("memory"))

        atlas.shutdown()

    def test_memory_service_available_via_container(self):
        atlas = Atlas()
        atlas.start()

        memory_service = atlas.container.get("memory")

        self.assertIsNotNone(memory_service)

        atlas.shutdown()

    def test_memory_service_cleaned_after_shutdown(self):
        atlas = Atlas()

        atlas.start()
        atlas.shutdown()

        self.assertFalse(
            atlas.container.has("memory")
        )

        self.assertFalse(
            atlas.started
        )

    def test_kernel_registers_knowledge_service(self):
        atlas = Atlas()

        atlas.start()

        knowledge = atlas.container.get("knowledge")

        self.assertIsNotNone(
            knowledge
        )

        atlas.shutdown()

    # ------------------------------------------------------------------
    # Phase 12.5.1 — Evolution Intelligence Kernel Wiring
    # ------------------------------------------------------------------

    def test_kernel_creates_insight_scorer(self):
        """Atlas creates an InsightScorer during startup."""
        atlas = Atlas()
        atlas.start()

        self.assertIsNotNone(atlas._insight_scorer)
        self.assertIsInstance(atlas._insight_scorer, InsightScorer)

        atlas.shutdown()

    def test_kernel_creates_intelligence_engine(self):
        """Atlas creates an EvolutionIntelligenceEngine during startup."""
        atlas = Atlas()
        atlas.start()

        self.assertIsNotNone(atlas._intelligence_engine)
        self.assertIsInstance(
            atlas._intelligence_engine,
            EvolutionIntelligenceEngine,
        )

        atlas.shutdown()

    def test_intelligence_engine_has_evolution_memory(self):
        """EvolutionIntelligenceEngine receives evolution_memory dependency."""
        atlas = Atlas()
        atlas.start()

        engine = atlas._intelligence_engine
        self.assertIsNotNone(engine.evolution_memory)

        atlas.shutdown()

    def test_intelligence_engine_has_experience_repository(self):
        """EvolutionIntelligenceEngine receives experience_repository dependency."""
        atlas = Atlas()
        atlas.start()

        engine = atlas._intelligence_engine
        self.assertIsNotNone(engine.experience_repository)

        atlas.shutdown()

    def test_intelligence_engine_has_insight_scorer(self):
        """EvolutionIntelligenceEngine receives insight_scorer dependency."""
        atlas = Atlas()
        atlas.start()

        engine = atlas._intelligence_engine
        self.assertIsNotNone(engine.insight_scorer)
        self.assertIsInstance(engine.insight_scorer, InsightScorer)

        atlas.shutdown()

    def test_intelligence_engine_has_storage(self):
        """EvolutionIntelligenceEngine receives storage dependency."""
        atlas = Atlas()
        atlas.start()

        engine = atlas._intelligence_engine
        self.assertIsNotNone(engine.storage)

        atlas.shutdown()

    def test_intelligence_engine_registered_in_container(self):
        """EvolutionIntelligenceEngine is accessible via service container."""
        atlas = Atlas()
        atlas.start()

        self.assertTrue(atlas.container.has("intelligence_engine"))
        engine = atlas.container.get("intelligence_engine")
        self.assertIsInstance(engine, EvolutionIntelligenceEngine)

        atlas.shutdown()

    def test_intelligence_engine_property(self):
        """intelligence_engine property returns the engine instance."""
        atlas = Atlas()
        atlas.start()

        engine = atlas.intelligence_engine
        self.assertIsInstance(engine, EvolutionIntelligenceEngine)
        self.assertIs(engine, atlas._intelligence_engine)

        atlas.shutdown()

    def test_intelligence_engine_cleared_on_shutdown(self):
        """Intelligence engine and scorer are cleaned up during shutdown."""
        atlas = Atlas()
        atlas.start()
        atlas.shutdown()

        self.assertIsNone(atlas._intelligence_engine)
        self.assertIsNone(atlas._insight_scorer)

    def test_intelligence_engine_removed_from_container_after_shutdown(self):
        """intelligence_engine is removed from container during shutdown."""
        atlas = Atlas()
        atlas.start()
        atlas.shutdown()

        self.assertFalse(atlas.container.has("intelligence_engine"))

    # ------------------------------------------------------------------
    # Phase 14.4 — Decision Intelligence Kernel Wiring
    # ------------------------------------------------------------------

    def test_kernel_creates_decision_intelligence_engine(self):
        """Atlas.start() creates a DecisionIntelligenceEngine."""
        atlas = Atlas()
        try:
            atlas.start()

            self.assertIsNotNone(atlas._decision_intelligence)
            self.assertIsInstance(
                atlas._decision_intelligence,
                DecisionIntelligenceEngine,
            )
        finally:
            atlas.shutdown()

    def test_decision_intelligence_property(self):
        """decision_intelligence property returns the engine instance."""
        atlas = Atlas()
        try:
            atlas.start()

            engine = atlas.decision_intelligence
            self.assertIsInstance(engine, DecisionIntelligenceEngine)
            self.assertIs(engine, atlas._decision_intelligence)
        finally:
            atlas.shutdown()

    def test_decision_intelligence_receives_knowledge_query(self):
        """DecisionIntelligenceEngine receives EvolutionKnowledgeQuery."""
        atlas = Atlas()
        try:
            atlas.start()

            knowledge = atlas._decision_intelligence.knowledge_query
            self.assertIsInstance(knowledge, EvolutionKnowledgeQuery)
            self.assertIs(knowledge, atlas._knowledge_query)
        finally:
            atlas.shutdown()

    def test_scheduler_receives_decision_intelligence(self):
        """EvolutionScheduler receives the DecisionIntelligenceEngine."""
        atlas = Atlas()
        try:
            atlas.start()

            self.assertIsInstance(atlas._evolution_scheduler, EvolutionScheduler)
            self.assertIs(
                atlas._evolution_scheduler._decision_intelligence,
                atlas._decision_intelligence,
            )
        finally:
            atlas.shutdown()

    def test_decision_intelligence_cleared_on_shutdown(self):
        """DecisionIntelligenceEngine is cleaned up during shutdown."""
        atlas = Atlas()
        atlas.start()
        atlas.shutdown()

        self.assertIsNone(atlas._decision_intelligence)

    def test_decision_intelligence_not_in_service_container(self):
        """DecisionIntelligenceEngine is a private dependency, not in container."""
        atlas = Atlas()
        try:
            atlas.start()

            expected_keys = {
                "component_registry",
                "ai", "conversation", "memory", "knowledge",
                "cognition", "cognitive", "cognition_service",
                "cognition_api", "tasks",
                "runtime_coordinator", "understanding",
                "world_model", "evolution_observer", "learning_engine",
                "identity", "feedback_coordinator",
                "goal_repository", "goal_intelligence",
                "experience_repository", "experience_accumulator", "self_model_engine",
                "intelligence_engine",
                "execution_gateway",
                "evolution_knowledge",
            }
            self.assertEqual(set(atlas.container.names()), expected_keys)
        finally:
            atlas.shutdown()


if __name__ == "__main__":
    unittest.main()
