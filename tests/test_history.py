"""
Tests for Atlas History.
"""

import unittest

from atlas.conversation.history import History


class TestHistory(unittest.TestCase):
    """Tests for the History class."""

    def setUp(self):
        self.history = History()

    def test_new_history_is_empty(self):
        self.assertEqual(self.history.count(), 0)
        self.assertIsNone(self.history.active())

    def test_create_conversation(self):
        conversation = self.history.create("Testing")

        self.assertEqual(self.history.count(), 1)
        self.assertEqual(conversation.title, "Testing")
        self.assertEqual(self.history.active(), conversation)


if __name__ == "__main__":
    unittest.main()