"""
Atlas Research Coordinator — Interface Only

Defines the abstraction for future research capability.
No implementation in this phase.

Phase 7.0 — Self-Evolution Foundation.
"""

from abc import ABC, abstractmethod

from atlas.evolution.models import ResearchQuery, ResearchResult


class ResearchCoordinator(ABC):
    """
    Abstract interface for research coordination.

    Future implementations will handle web research, documentation
    analysis, and external information gathering. This phase defines
    only the interface — no implementation.

    The ResearchCoordinator must remain independent from any specific
    AI provider. Research may use AI models as reasoning resources,
    but the coordinator itself owns the research workflow.
    """

    @abstractmethod
    async def conduct_research(
        self,
        query: ResearchQuery,
    ) -> ResearchResult:
        """
        Conduct research for a given query.

        Args:
            query: The ResearchQuery defining the research question
                and context.

        Returns:
            A ResearchResult containing the findings.

        Raises:
            NotImplementedError: This method is not yet implemented.
        """
        raise NotImplementedError(
            "ResearchCoordinator.conduct_research is not implemented "
            "in Phase 7.0. This method will be implemented in a "
            "future phase."
        )

    @abstractmethod
    async def validate_findings(
        self,
        result: ResearchResult,
    ) -> float:
        """
        Validate research findings and return a confidence score.

        Args:
            result: The ResearchResult to validate.

        Returns:
            A confidence score between 0.0 and 1.0.

        Raises:
            NotImplementedError: This method is not yet implemented.
        """
        raise NotImplementedError(
            "ResearchCoordinator.validate_findings is not implemented "
            "in Phase 7.0."
        )