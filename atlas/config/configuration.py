"""
Atlas Configuration Manager.
"""

from pathlib import Path
import tomllib

from atlas.config.configuration_models import (
    AISettings,
    ApplicationSettings,
    AtlasSettings,
    ConversationSettings,
    LoggingSettings,
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
            ),
            conversation=ConversationSettings(
                history_limit=data["conversation"]["history_limit"],
            ),
            logging=LoggingSettings(
                level=data["logging"]["level"],
            ),
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