import unittest
from unittest.mock import MagicMock

from atlas.kernel.atlas import Atlas
from atlas.intelligence.cognitive_loop import CognitiveLoop
from atlas.intelligence.cognitive_service import CognitiveService as IntelligenceCognitiveService
from atlas.services.cognition_service import CognitionService
from atlas.cognition.engine import CognitionEngine
from atlas.learning.learning_manager import LearningManager
from atlas.learning.knowledge_feedback import KnowledgeFeedback


class TestCognitionService(unittest.TestCase):

    def test_cognition_service_registered(self):

        atlas = Atlas()

        atlas.start()

        cognition = atlas.container.get(
            "cognition"
        )

        self.assertIsNotNone(
            cognition
        )

        self.assertIsInstance(
            cognition,
            CognitiveLoop,
        )

        atlas.shutdown()

    def test_cognitive_service_registered(self):

        atlas = Atlas()

        atlas.start()

        service = atlas.container.get(
            "cognitive"
        )

        self.assertIsNotNone(
            service
        )

        self.assertIsInstance(
            service,
            IntelligenceCognitiveService,
        )

        atlas.shutdown()

    def test_cognition_service_new_registered(self):

        atlas = Atlas()

        atlas.start()

        service = atlas.container.get(
            "cognition_service"
        )

        self.assertIsNotNone(
            service
        )

        self.assertIsInstance(
            service,
            CognitionService,
        )

        self.assertTrue(
            service.is_running()
        )

        atlas.shutdown()

    def test_cognition_service_new_process(self):

        atlas = Atlas()

        atlas.start()

        service = atlas.container.get(
            "cognition_service"
        )

        result = service.process(
            "Test cognition"
        )

        self.assertEqual(
            result.action,
            "respond",
        )

        self.assertEqual(
            result.data["input"],
            "Test cognition",
        )

        atlas.shutdown()

    # ------------------------------------------------------------------
    # Phase 5.3 — Cognition Feedback Loop Tests
    # ------------------------------------------------------------------

    def test_process_with_learning_manager(self):
        """CognitionService feeds decisions into LearningManager."""

        engine = CognitionEngine()
        learning_manager = LearningManager()
        knowledge_feedback = KnowledgeFeedback()

        service = CognitionService(
            engine=engine,
            learning_manager=learning_manager,
            knowledge_feedback=knowledge_feedback,
        )
        service.start()

        result = service.process("Test learning feedback")

        self.assertEqual(result.action, "respond")
        self.assertIn("Test learning feedback", result.data["input"])

        # Verify knowledge was stored in KnowledgeFeedback
        all_knowledge = knowledge_feedback.store.all()
        self.assertGreater(len(all_knowledge), 0)
        self.assertIn("Experience captured.", all_knowledge[0])

        service.stop()

    def test_process_with_knowledge_manager(self):
        """CognitionService stores learned knowledge into KnowledgeManager."""

        engine = CognitionEngine()
        knowledge_manager = MagicMock()

        service = CognitionService(
            engine=engine,
            knowledge_manager=knowledge_manager,
            learning_manager=LearningManager(),
            knowledge_feedback=KnowledgeFeedback(),
        )
        service.start()

        result = service.process("Test knowledge manager storage")

        self.assertEqual(result.action, "respond")

        # KnowledgeManager.remember should have been called
        knowledge_manager.remember.assert_called_once()
        call_args = knowledge_manager.remember.call_args
        self.assertIn("cognition:", call_args.kwargs["title"])
        self.assertEqual(call_args.kwargs["source"], "cognition_service")

        service.stop()

    def test_feedback_disabled_when_learning_manager_none(self):
        """No feedback occurs when learning_manager is None."""

        engine = CognitionEngine()

        service = CognitionService(engine=engine)
        service.start()

        # Should not raise, should simply return decision without feedback
        result = service.process("No learning test")

        self.assertEqual(result.action, "respond")
        self.assertEqual(result.data["input"], "No learning test")

        service.stop()

    def test_existing_behavior_unchanged(self):
        """Existing process behavior still works without learning dependencies."""

        service = CognitionService()
        service.start()

        result = service.process("Existing behavior test")

        self.assertEqual(result.action, "respond")
        self.assertEqual(result.data["input"], "Existing behavior test")

        service.stop()


if __name__ == "__main__":
    unittest.main()
