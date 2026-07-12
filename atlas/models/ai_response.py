"""
Atlas AI Response Model

Provides a standardized response object for every AI provider.
"""

from dataclasses import dataclass, field


@dataclass(slots=True)
class AIResponse:
    """Standard AI response."""

    text: str

    provider: str

    model: str

    tokens: int | None = None

    finish_reason: str | None = None

    metadata: dict = field(default_factory=dict)