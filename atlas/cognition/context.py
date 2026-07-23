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
        goal: str | None = None,
        knowledge: list | None = None,
        memory_results: list | None = None,
        knowledge_results: list | None = None,
    ):
        self.user_input = user_input
        self.memory = memory or []
        self.metadata = metadata or {}
        self.goal = goal
        self.knowledge = knowledge or []
        self.memory_results = memory_results or []
        self.knowledge_results = knowledge_results or []

    def add_memory(self, item):
        """Add memory information."""

        self.memory.append(item)

    def get_input(self):
        """Return current user input."""

        return self.user_input