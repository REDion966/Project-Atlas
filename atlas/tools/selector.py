"""
Atlas Tool Selector

Matches a ToolRequest to the best available Tool instances.
Pure logic component with no infrastructure dependencies.

Phase 6.9 — Tool Intelligence Foundation.
"""

from atlas.tools.models import Tool, ToolRequest


class ToolSelector:
    """
    Matches a ToolRequest to the best available Tool instances.

    This is a pure logic component with no infrastructure dependencies.
    It does not call AI providers, access memory, query knowledge, or
    interact with the EventBus.

    Keyword-based deterministic selection. AI-driven selection is
    deferred to a future phase.
    """

    def select(
        self,
        request: ToolRequest,
        available: list[Tool],
    ) -> list[Tool]:
        """
        Rank and return the best-matching tools for a request.

        Selection strategy:
        1. Filter by preferred category if specified.
        2. Rank by goal keyword relevance.
        3. Return top results up to max_results.

        Args:
            request: The ToolRequest describing what is needed.
            available: The list of available Tool instances.

        Returns:
            A list of Tool instances ranked by relevance, limited to
            request.max_results. Returns an empty list if no tools
            match.
        """
        if not available:
            return []

        candidates = list(available)

        # Filter by preferred category if specified
        if request.preferred_category:
            category_matched = [
                t for t in candidates
                if t.category == request.preferred_category
            ]
            if category_matched:
                candidates = category_matched

        # Rank by goal keyword relevance
        ranked = self.rank_by_goal(request.goal, candidates)

        # Limit to max_results
        return ranked[:request.max_results]

    def rank_by_goal(
        self,
        goal: str,
        tools: list[Tool],
    ) -> list[Tool]:
        """
        Rank tools by keyword relevance to a goal string.

        Scoring:
        - +2 points if the goal contains the tool name.
        - +1 point if the goal contains any tag of the tool.
        - +1 point if the goal contains any word from the tool
          description.
        - Tools with higher scores appear first.
        - Ties are broken by name (alphabetical).

        Args:
            goal: The goal string to match against.
            tools: The list of Tool instances to rank.

        Returns:
            A list of Tool instances sorted by relevance score
            (highest first).
        """
        if not goal or not tools:
            return list(tools)

        goal_lower = goal.lower()
        goal_words = set(goal_lower.split())

        scored: list[tuple[int, Tool]] = []
        for tool in tools:
            score = 0

            # +2 if goal contains tool name
            if tool.name.lower() in goal_lower:
                score += 2

            # +1 if goal contains any tag
            for tag in tool.tags:
                if tag.lower() in goal_lower:
                    score += 1

            # +1 if goal contains any word from description
            desc_words = tool.description.lower().split()
            if goal_words & set(desc_words):
                score += 1

            scored.append((score, tool))

        # Sort by score descending, then by name ascending
        scored.sort(key=lambda x: (-x[0], x[1].name))
        return [tool for _, tool in scored]