"""
Atlas Configuration Manager.
"""

from pathlib import Path
import tomllib

from atlas.config.configuration_models import (
    AISettings,
    APIKeySettings,
    ApplicationSettings,
    AtlasSettings,
    AuthoritySettings,
    ConversationSettings,
    DevelopmentSettings,
    LoggingSettings,
    ResearchSettings,
    SpecialistsSettings,
)


def _specialists_settings(raw: object) -> SpecialistsSettings:
    """Parse the optional ``[specialists]`` table with fail-safe defaults.

    A malformed/absent table yields the disabled defaults, so a broken config
    can never accidentally enable a model provider.
    """
    if not isinstance(raw, dict):
        return SpecialistsSettings()
    try:
        timeout = float(raw.get("timeout_seconds", 180.0))
    except (TypeError, ValueError):
        timeout = 180.0
    if timeout <= 0:
        timeout = 180.0
    return SpecialistsSettings(
        enabled=bool(raw.get("enabled", False)),
        provider_id=str(raw.get("provider_id") or "ollama.code"),
        model=str(raw.get("model") or "qwen2.5-coder:7b"),
        host=str(raw.get("host") or "http://127.0.0.1:11434"),
        timeout_seconds=timeout,
    )


class Configuration:
    """Loads Atlas configuration."""

    def __init__(self, filename: str = "config.toml"):
        self._path = Path(filename)
        self._settings: AtlasSettings | None = None

    def load(self) -> None:
        """Load configuration from TOML."""

        with self._path.open("rb") as file:
            data = tomllib.load(file)

        api_keys_data = data.get("api_keys", {})
        development_data = data.get("development", {})
        if not isinstance(development_data, dict):
            development_data = {}
        # The bounded Development Envelope table ([development.envelope]) is
        # passed through verbatim to DevelopmentEnvelope.from_mapping, which
        # owns validation and stays fail-closed. An absent table resolves to
        # None (the disabled policy) exactly as before.
        raw_envelope = development_data.get("envelope")

        self._settings = AtlasSettings(
            application=ApplicationSettings(
                name=data["application"]["name"],
                version=data["application"]["version"],
            ),
            ai=AISettings(
                provider=data["ai"]["provider"],
                model=data["ai"]["model"],
                temperature=data["ai"]["temperature"],
                timeout=data["ai"]["timeout"],
                api_keys=APIKeySettings(
                    openai=api_keys_data.get("openai", ""),
                    anthropic=api_keys_data.get("anthropic", ""),
                ),
                profiles=list(data.get("ai", {}).get("profiles", [])),
                allow_fallback=bool(
                    data.get("ai", {}).get("allow_fallback", False)
                ),
                external_providers=bool(
                    data.get("ai", {}).get("external_providers", False)
                ),
                conversation_timeout_s=float(
                    data.get("ai", {}).get("conversation_timeout_s", 20.0)
                ),
            ),
            conversation=ConversationSettings(
                history_limit=data["conversation"]["history_limit"],
            ),
            logging=LoggingSettings(
                level=data["logging"]["level"],
            ),
            research=ResearchSettings(
                web_allowed_hosts=tuple(
                    str(h).strip()
                    for h in data.get("research", {}).get("web_allowed_hosts", ())
                    if str(h).strip()
                ),
            ),
            development=DevelopmentSettings(
                model_assisted_authoring=bool(
                    development_data.get("model_assisted_authoring", False)
                ),
                envelope=(
                    dict(raw_envelope) if isinstance(raw_envelope, dict) else None
                ),
            ),
            authority=AuthoritySettings(
                owner_name=str(
                    data.get("authority", {}).get("owner_name", "Owner")
                ),
            ),
            specialists=_specialists_settings(data.get("specialists")),
        )

    @property
    def settings(self) -> AtlasSettings:
        """Return the typed Atlas settings."""

        if self._settings is None:
            raise RuntimeError(
                "Configuration has not been loaded."
            )

        return self._settings

    @property
    def data(self):
        """
        Backward-compatible access.

        Deprecated. Prefer config.settings.
        """
        return self.settings

    def get(self, *keys, default=None):
        """
        Backward-compatible configuration access.

        Example:
            config.get("ai", "provider")
        """

        if self._settings is None:
            return default

        value = self._settings

        for key in keys:
            if not hasattr(value, key):
                return default

            value = getattr(value, key)

        return value
