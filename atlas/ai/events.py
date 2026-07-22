"""
Atlas AI Events

Defines AI lifecycle events.
"""

from dataclasses import dataclass
from datetime import datetime


@dataclass
class AIEvent:
    """Base AI event."""

    name: str
    provider: str
    timestamp: datetime


@dataclass
class ProviderStarted(AIEvent):
    """Provider initialization event."""


@dataclass
class ProviderFailed(AIEvent):
    """Provider failure event."""

    error: str


@dataclass
class ProviderSwitched(AIEvent):
    """Provider switch event."""

    previous: str | None
    current: str