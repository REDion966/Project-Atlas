"""
Atlas Cognition Context

Contains information provided to the cognitive engine.
"""


class CognitionContext:
    """Context container for Atlas reasoning."""

    def __init__(
        self,
        user_input: str,
        memory=None,
        metadata=None,
    ):
        self.user_input = user_input
        self.memory = memory or []
        self.metadata = metadata or {}

    def add_memory(self, item):
        """Add memory information."""

        self.memory.append(item)

    def get_input(self):
        """Return current user input."""

        return self.user_input