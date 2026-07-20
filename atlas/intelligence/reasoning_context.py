"""
Atlas Reasoning Context
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ReasoningContext:

    goal: str

    metadata: dict = field(
        default_factory=dict
    )