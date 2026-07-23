"""
Tests for Atlas Cognition Engine.
"""

import unittest

from atlas.cognition.context import CognitionContext
from atlas.cognition.engine import CognitionEngine


class TestCognitionEngine(unittest.TestCase):

    def setUp(self):
        self.engine = CognitionEngine()

    def test_process_user_input(self):

        context = CognitionContext(
            user_input="Hello Atlas"
        )

        result = self.engine.process(
            context
        )

        self.assertEqual(
            result.action,
            "respond",
        )

        self.assertEqual(
            result.data["input"],
            "Hello Atlas",
        )


    def test_empty_input_returns_idle(self):

        context = CognitionContext(
            user_input=""
        )

        result = self.engine.process(
            context
        )

        self.assertEqual(
            result.action,
            "idle",
        )

    def test_context_with_memory_results(self):

        context = CognitionContext(
            user_input="What do I know?",
            memory_results=[
                {"id": "1", "content": "User likes Python"},
            ],
        )

        result = self.engine.process(context)

        self.assertEqual(result.action, "respond")
        self.assertEqual(
            result.data["input"],
            "What do I know?",
        )

    def test_context_with_knowledge_results(self):

        context = CognitionContext(
            user_input="Explain Atlas",
            knowledge_results=[
                {"title": "Atlas Docs", "content": "Atlas is a framework"},
            ],
        )

        result = self.engine.process(context)

        self.assertEqual(result.action, "respond")
        self.assertEqual(
            result.data["input"],
            "Explain Atlas",
        )

    def test_context_with_goal(self):

        context = CognitionContext(
            user_input="Help me code",
            goal="Write a Python function",
        )

        result = self.engine.process(context)

        self.assertEqual(result.action, "respond")
        self.assertEqual(context.goal, "Write a Python function")

    def test_full_context_processing(self):

        context = CognitionContext(
            user_input="Analyze this",
            memory=[{"role": "user", "content": "Hello"}],
            metadata={"session": "abc123"},
            goal="Analyze conversation",
            memory_results=[{"id": "1", "content": "Prior context"}],
            knowledge_results=[{"title": "Rules", "content": "Be helpful"}],
        )

        result = self.engine.process(context)

        self.assertEqual(result.action, "respond")
        self.assertEqual(context.goal, "Analyze conversation")
        self.assertEqual(len(context.memory_results), 1)
        self.assertEqual(len(context.knowledge_results), 1)
        self.assertEqual(len(context.memory), 1)
        self.assertEqual(context.metadata["session"], "abc123")


if __name__ == "__main__":
    unittest.main()