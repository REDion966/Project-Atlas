"""
Atlas Configuration Models

Strongly typed configuration objects.
"""

from dataclasses import dataclass


@dataclass(slots=True)
class ApplicationSettings:
    """Application configuration."""

    name: str
    version: str


@dataclass(slots=True)
class AISettings:
    """AI configuration."""

    provider: str
    model: str
    temperature: float
    timeout: int


@dataclass(slots=True)
class ConversationSettings:
    """Conversation configuration."""

    history_limit: int


@dataclass(slots=True)
class LoggingSettings:
    """Logging configuration."""

    level: str


@dataclass(slots=True)
class AtlasSettings:
    """Complete Atlas configuration."""

    application: ApplicationSettings
    ai: AISettings
    conversation: ConversationSettings
    logging: LoggingSettings