"""
Atlas Model Profile Registry

Stores and manages ModelProfile instances for model routing.
"""

from atlas.ai.routing.models import ModelProfile


class ModelProfileRegistry:
    """
    Registry for available model profiles.

    Profiles are stored by a composite key of provider_name and model_name.
    """

    def __init__(self):
        self._profiles: dict[tuple[str, str], ModelProfile] = {}

    def register(
        self,
        profile: ModelProfile,
    ) -> None:
        """
        Register a model profile.

        Args:
            profile: The ModelProfile to register.

        Raises:
            ValueError: If a profile is already registered for the same
                provider and model.
        """

        key = (profile.provider_name, profile.model_name)

        if key in self._profiles:
            raise ValueError(
                f"Profile already registered for provider "
                f"'{profile.provider_name}' model '{profile.model_name}'"
            )

        self._profiles[key] = profile

    def get(
        self,
        provider_name: str,
        model_name: str,
    ) -> ModelProfile | None:
        """
        Retrieve a profile by provider and model name.

        Args:
            provider_name: The provider name.
            model_name: The model name.

        Returns:
            The matching ModelProfile, or None if not found.
        """

        return self._profiles.get((provider_name, model_name))

    def list_profiles(self) -> list[ModelProfile]:
        """
        Return all registered profiles.

        Returns:
            A list of ModelProfile instances.
        """

        return list(self._profiles.values())

    def remove(
        self,
        provider_name: str,
        model_name: str,
    ) -> None:
        """
        Remove a profile from the registry.

        Args:
            provider_name: The provider name.
            model_name: The model name.

        Raises:
            KeyError: If the profile is not registered.
        """

        key = (provider_name, model_name)

        if key not in self._profiles:
            raise KeyError(
                f"No profile registered for provider "
                f"'{provider_name}' model '{model_name}'"
            )

        del self._profiles[key]

    def clear(self) -> None:
        """Remove all registered profiles."""

        self._profiles.clear()
