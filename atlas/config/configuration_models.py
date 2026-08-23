"""
Atlas Configuration Models

Strongly typed configuration objects.
"""

from dataclasses import dataclass, field


@dataclass(slots=True)
class ApplicationSettings:
    """Application configuration."""

    name: str
    version: str


@dataclass(slots=True)
class APIKeySettings:
    """Provider API key configuration."""

    openai: str = ""
    anthropic: str = ""


@dataclass(slots=True)
class AISettings:
    """AI configuration."""

    provider: str
    model: str
    temperature: float
    timeout: int
    api_keys: APIKeySettings | None = None
    # Optional raw model-profile entries from [ai.profiles].
    # None/empty means the routing defaults apply.
    profiles: list[dict] = field(default_factory=list)
    # Operator-level default for policy-controlled model fallback on routed
    # chat.  Safe default False; explicit opt-in only.  Per-request
    # RoutingRequest.allow_fallback can still enable fallback individually.
    allow_fallback: bool = False


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
