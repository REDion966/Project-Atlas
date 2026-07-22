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