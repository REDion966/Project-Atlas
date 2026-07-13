"""
Atlas Prompt Builder

Builds prompts from Atlas context.
"""

from atlas.conversation.message import Message


class PromptBuilder:
    """Builds prompts for AI providers."""

    def build(self, messages: list[Message]) -> list[dict]:
        """
        Convert Message objects into provider-compatible dictionaries.
        """

        prompt = []

        for message in messages:
            prompt.append(
                {
                    "role": message.role,
                    "content": message.content,
                }
            )

        return prompt