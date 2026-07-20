"""
Atlas Thinking Result
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ThinkingResult:

    conclusion: str

    action: str

    reflection: str