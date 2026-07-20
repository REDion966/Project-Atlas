"""
Atlas Thinking Cycle
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ThinkingCycle:

    goal: str

    conclusion: str

    action: str

    lesson: str