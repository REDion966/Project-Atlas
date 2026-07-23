"""
Tests for new Atlas Cognition Service.
"""

import unittest
from unittest.mock import MagicMock, patch

from atlas.services.cognition_service import CognitionService
from atlas.memory.models.memory import Memory
from atlas.memory.enums import MemoryImportance, MemoryType
from atlas.knowledge.knowledge_entry import KnowledgeEntry


class TestNewCognitionService(unittest.TestCase):

    def setUp(self):

        self.service = CognitionService()


    def test_service_starts(self):

        self.service.start()

        self.assertTrue(
            self.service.running
        )


    def test_process_returns_decision(self):

        self.service.start()

        result = self.service.process(
            "Test input"
        )

        self.assertEqual(
            result.action,
            "respond",
        )


    def test_process_without_start_fails(self):

        with self.assertRaises(
            RuntimeError
        ):
            self.service.process(
                "Test"
            )


class TestCognitionServiceDependencyInjection(unittest.TestCase):
    """Tests for constructor injection of memory_service and knowledge_manager."""

    def test_constructor_injects_memory_service(self):

        mock_memory = MagicMock()
        service = CognitionService(
            memory_service=mock_memory,
        )

        self.assertIs(
            service.memory_service,
            mock_memory,
        )

    def test_constructor_injects_knowledge_manager(self):

        mock_knowledge = MagicMock()
        service = CognitionService(
            knowledge_manager=mock_knowledge,
        )

        self.assertIs(
            service.knowledge_manager,
            mock_knowledge,
        )

    def test_constructor_injects_both_dependencies(self):

        mock_memory = MagicMock()
        mock_knowledge = MagicMock()

        service = CognitionService(
            memory_service=mock_memory,
            knowledge_manager=mock_knowledge,
        )

        self.assertIs(service.memory_service, mock_memory)
        self.assertIs(service.knowledge_manager, mock_knowledge)

    def test_constructor_defaults_to_none(self):

        service = CognitionService()

        self.assertIsNone(service.memory_service)
        self.assertIsNone(service.knowledge_manager)

    def test_constructor_injects_engine(self):

        mock_engine = MagicMock()
        service = CognitionService(
            engine=mock_engine,
        )

        self.assertIs(
            service.engine,
            mock_engine,
        )


class TestCognitionServiceMemoryRetrieval(unittest.TestCase):
    """Tests that memory retrieval works when memory_service is injected."""

    def setUp(self):
        self.mock_memory = MagicMock()
        self.service = CognitionService(
            memory_service=self.mock_memory,
        )
        self.service.start()

    def test_memory_retrieval_called_on_process(self):

        self.service.process("Find memories")

        self.mock_memory.search.assert_called_once_with(
            keyword="Find memories",
        )

    def test_memory_retrieval_populates_context(self):

        fake_memories = [
            Memory(
                id="1",
                title="Test",
                content="Test content",
                memory_type=MemoryType.GENERAL,
                importance=MemoryImportance.NORMAL,
            ),
        ]
        self.mock_memory.search.return_value = fake_memories

        result = self.service.process("Find memories")

        self.assertEqual(result.action, "respond")

    def test_memory_retrieval_empty_input_skips_search(self):

        self.service.process("")

        self.mock_memory.search.assert_not_called()

    def test_memory_retrieval_with_none_input_skips_search(self):

        self.service.process("")

        self.mock_memory.search.assert_not_called()


class TestCognitionServiceKnowledgeRetrieval(unittest.TestCase):
    """Tests that knowledge retrieval works when knowledge_manager is injected."""

    def setUp(self):
        self.mock_knowledge = MagicMock()
        self.service = CognitionService(
            knowledge_manager=self.mock_knowledge,
        )
        self.service.start()

    def test_knowledge_retrieval_called_on_process(self):

        self.service.process("Query knowledge")

        self.mock_knowledge.query.assert_called_once_with(
            "Query knowledge",
        )

    def test_knowledge_retrieval_populates_context(self):

        fake_entries = [
            KnowledgeEntry(
                title="Atlas",
                content="Atlas docs",
                source="manual",
            ),
        ]
        self.mock_knowledge.query.return_value = fake_entries

        result = self.service.process("Query knowledge")

        self.assertEqual(result.action, "respond")

    def test_knowledge_retrieval_empty_input_skips_query(self):

        self.service.process("")

        self.mock_knowledge.query.assert_not_called()


class TestCognitionServiceNoDependencies(unittest.TestCase):
    """Tests that service works gracefully with missing dependencies."""

    def setUp(self):
        self.service = CognitionService()
        self.service.start()

    def test_process_without_memory_service(self):

        result = self.service.process("Hello")

        self.assertEqual(result.action, "respond")

    def test_process_without_knowledge_manager(self):

        result = self.service.process("Hello")

        self.assertEqual(result.action, "respond")

    def test_process_without_either_dependency(self):

        result = self.service.process("Hello")

        self.assertEqual(result.action, "respond")

    def test_memory_service_property_none(self):

        self.assertIsNone(self.service.memory_service)

    def test_knowledge_manager_property_none(self):

        self.assertIsNone(self.service.knowledge_manager)


class TestCognitionServiceGoalParameter(unittest.TestCase):
    """Tests that the goal parameter is passed through to context."""

    def setUp(self):
        self.service = CognitionService()
        self.service.start()

    def test_goal_passed_to_context(self):

        result = self.service.process(
            "Help me",
            goal="Write code",
        )

        self.assertEqual(result.action, "respond")

    def test_goal_default_none(self):

        result = self.service.process(
            "Help me",
        )

        self.assertEqual(result.action, "respond")


if __name__ == "__main__":
    unittest.main()