"""
Atlas Decision Result
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class DecisionResult:

    action: str

    confidence: float