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
class ResearchSettings:
    """Research / information-acquisition configuration.

    ``web_allowed_hosts`` is the explicit allowlist for the bounded web
    source adapter. Empty (the default) keeps the web adapter
    deny-by-default: no external host may be fetched. HTTP/HTTPS remain
    the only accepted schemes and all SSRF protections stay mandatory.
    """

    web_allowed_hosts: tuple[str, ...] = ()


@dataclass(slots=True)
class DevelopmentSettings:
    """Governed development-cycle configuration.

    ``model_assisted_authoring`` is the explicit opt-in for the optional
    model-assisted change supplier (B4). Safe default ``False``: Atlas uses
    the existing ``DeterministicChangeSupplier`` and no model-assisted
    authoring occurs unless explicitly enabled. Owner approval, sandbox-only
    execution, verification, and promotion review remain mandatory.
    """

    model_assisted_authoring: bool = False


@dataclass(slots=True)
class AuthoritySettings:
    """Owner/authority foundation configuration (P1/B1.1).

    ``owner_name`` designates the single logical Owner. No authentication is
    configured here; this is only the explicit, stable owner identity.
    """

    owner_name: str = "Owner"


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
    # Optional research/acquisition settings; defaults keep the web source
    # adapter deny-by-default.
    research: ResearchSettings = field(default_factory=ResearchSettings)
    # Optional governed development settings; safe default False.
    development: DevelopmentSettings = field(default_factory=DevelopmentSettings)
    # Optional authority settings; safe default owner name.
    authority: AuthoritySettings = field(default_factory=AuthoritySettings)
