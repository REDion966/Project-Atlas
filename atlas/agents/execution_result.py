"""
Atlas Execution Result
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ExecutionResult:

    success: bool

    output: dict