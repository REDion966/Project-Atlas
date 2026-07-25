"""
Atlas Reasoning Outcomes

Pure data models and recorder for reasoning pipeline outcomes.

This module is intentionally dependency-free: it does not import
AI providers, memory services, knowledge managers, EventBus, or any
other infrastructure. It is part of the pure reasoning layer and is
intended to be injected into CognitionService as a private Atlas-owned
dependency (Phase 6.5.2).
"""

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class ReasoningOutcome:
    """
    A recorded snapshot of a completed reasoning pipeline execution.

    Attributes:
        timestamp: When the reasoning pipeline completed.
        goal: The high-level goal derived from the reasoning plan.
        decision_action: The CognitionDecision action that triggered reasoning.
        capabilities: Serialized capability selections from the pipeline.
        routes: Serialized execution routes from the pipeline.
        results: Serialized execution results from the pipeline.
        success: True if all execution results succeeded, False otherwise.
        metadata: Optional additional context (e.g. source identifier).
    """

    timestamp: datetime
    goal: str = ""
    decision_action: str = ""
    capabilities: list[dict[str, Any]] = field(default_factory=list)
    routes: list[dict[str, Any]] = field(default_factory=list)
    results: list[dict[str, Any]] = field(default_factory=list)
    success: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


class ReasoningRecorder:
    """
    In-memory ring buffer for ReasoningOutcome instances.

    This is a pure logic component with no infrastructure dependencies.
    It stores a bounded history of reasoning pipeline outcomes so that
    future components (e.g. reflection, monitoring) can inspect past
    decisions without coupling to the pipeline internals.

    Attributes:
        max_size: Maximum number of outcomes to retain. Older outcomes
            are discarded when the buffer exceeds this size.
    """

    def __init__(self, max_size: int = 100) -> None:
        """
        Initialise an empty recorder with a bounded buffer.

        Args:
            max_size: Maximum number of outcomes to retain. Must be > 0.

        Raises:
            ValueError: If max_size is not a positive integer.
        """
        if max_size <= 0:
            raise ValueError("max_size must be a positive integer")

        self._max_size = max_size
        self._outcomes: deque[ReasoningOutcome] = deque(maxlen=max_size)

    def record(self, outcome: ReasoningOutcome) -> None:
        """
        Record a reasoning outcome.

        If the buffer is full, the oldest outcome is automatically
        discarded to maintain the configured max_size.

        Args:
            outcome: The ReasoningOutcome to store.
        """
        self._outcomes.append(outcome)

    def recent(self, n: int = 10) -> list[ReasoningOutcome]:
        """
        Return the most recent n outcomes, newest first.

        Args:
            n: Number of outcomes to return. Defaults to 10.

        Returns:
            A list of up to n ReasoningOutcome instances, ordered from
            newest to oldest.
        """
        if n <= 0:
            return []

        return list(reversed(self._outcomes))[:n]

    def latest(self) -> ReasoningOutcome | None:
        """
        Return the most recently recorded outcome, if any.

        Returns:
            The latest ReasoningOutcome, or None if no outcomes have
            been recorded.
        """
        if not self._outcomes:
            return None

        return self._outcomes[-1]

    @property
    def count(self) -> int:
        """
        Return the number of recorded outcomes.

        Returns:
            The current buffer size, always <= max_size.
        """
        return len(self._outcomes)

    @property
    def max_size(self) -> int:
        """
        Return the configured maximum buffer size.

        Returns:
            The max_size value passed to the constructor.
        """
        return self._max_size

    def summary(self) -> dict[str, Any]:
        """
        Return a summary of recorded outcomes.

        Returns:
            A dictionary with total count, success count, failure count,
            success rate, and the most recent timestamp (if any).
        """
        total = self.count
        if total == 0:
            return {
                "count": 0,
                "success_count": 0,
                "failure_count": 0,
                "success_rate": None,
                "latest_timestamp": None,
            }

        success_count = sum(1 for o in self._outcomes if o.success)
        failure_count = total - success_count
        success_rate = success_count / total
        latest_timestamp = self._outcomes[-1].timestamp.isoformat()

        return {
            "count": total,
            "success_count": success_count,
            "failure_count": failure_count,
            "success_rate": success_rate,
            "latest_timestamp": latest_timestamp,
        }

    def clear(self) -> None:
        """Remove all recorded outcomes."""
        self._outcomes.clear()
