"""
Atlas Reasoning Strategy
"""

from __future__ import annotations

from enum import Enum


class ReasoningStrategy(str, Enum):

    DIRECT = "direct"

    ANALYTICAL = "analytical"

    COLLABORATIVE = "collaborative"