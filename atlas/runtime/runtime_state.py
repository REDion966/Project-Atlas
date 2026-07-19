"""
Atlas Runtime State

Stores the current execution state
of the Atlas runtime.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(slots=True)
class RuntimeState:
    """
    Runtime execution state.
    """

    running: bool = False

    healthy: bool = True

    started_at: datetime | None = None

    last_tick: datetime | None = None

    tick_count: int = 0

    paused: bool = False