"""
Atlas Reasoning Result
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ReasoningResult:

    success: bool

    conclusion: str

    confidence: float = 1.0