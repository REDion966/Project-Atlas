"""
Atlas Execution Context
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ExecutionContext:

    workflow: str

    current_step: int = 0

    metadata: dict = field(
        default_factory=dict
    )