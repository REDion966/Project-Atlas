"""
Atlas Reflection Result
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ReflectionResult:

    successful: bool

    feedback: str