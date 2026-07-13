"""
Tests for Atlas Prompt Builder.
"""

import unittest

from atlas.conversation.message import Message
from atlas.conversation.prompt_builder import PromptBuilder


class TestPromptBuilder(unittest.TestCase):

    def test_build_prompt(self):
        builder = PromptBuilder()

        messages = [
            Message(
                role="user",
                content="Hello Atlas"
            )
        ]

        prompt = builder.build(messages)

        self.assertEqual(len(prompt), 1)
        self.assertEqual(prompt[0]["role"], "user")
        self.assertEqual(prompt[0]["content"], "Hello Atlas")


if __name__ == "__main__":
    unittest.main()