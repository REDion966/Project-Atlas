"""
Atlas Workflow
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Workflow:

    name: str

    steps: list[str] = field(
        default_factory=list
    )

    def add_step(
        self,
        step: str,
    ) -> None:

        self.steps.append(step)