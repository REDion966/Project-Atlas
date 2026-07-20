"""
Atlas Learning Result
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class LearningResult:

    success: bool

    knowledge: str