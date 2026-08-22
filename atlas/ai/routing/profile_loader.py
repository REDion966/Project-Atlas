"""
Atlas Model Profile Loader

Loads ModelProfile definitions from configuration with safe defaults.

The kernel previously hard-coded its model profiles. This loader moves
that registration data into an optional ``[ai.profiles]`` configuration
section while preserving the exact default behavior when the section is
absent.
"""

from atlas.ai.routing.models import ModelProfile


# Default profiles replicate the previous hard-coded kernel behavior.
# The Ollama profile's model_name is filled from the configured model.
DEFAULT_PROFILES = [
    {
        "provider_name": "Mock Provider",
        "model_name": "atlas-mock-v1",
        "complexity_score": 0.3,
        "latency_class": "fast",
        "cost_tier": 0.1,
        "supported_tasks": ["conversation"],
        "priority": 10,
    },
    {
        "provider_name": "Ollama",
        "model_name": None,  # resolved to the configured model at load time
        "complexity_score": 0.8,
        "latency_class": "medium",
        "cost_tier": 0.2,
        "supported_tasks": ["conversation", "analysis", "code"],
        "priority": 20,
    },
]


def _build_profile(entry: dict) -> ModelProfile:
    """Build a ModelProfile from a raw configuration entry."""
    return ModelProfile(
        provider_name=str(entry["provider_name"]),
        model_name=str(entry["model_name"]),
        complexity_score=float(entry.get("complexity_score", 0.5)),
        latency_class=str(entry.get("latency_class", "medium")),
        cost_tier=float(entry.get("cost_tier", 0.5)),
        supported_tasks=list(entry.get("supported_tasks", [])),
        priority=int(entry.get("priority", 0)),
        metadata=dict(entry.get("metadata", {})),
    )


def load_model_profiles(
    profile_entries: list[dict] | None,
    configured_model: str,
) -> list[ModelProfile]:
    """
    Load model profiles from configuration entries.

    Args:
        profile_entries: Raw profile dicts from the ``[ai.profiles]``
            config section, or None/empty when unconfigured.
        configured_model: The model configured under ``[ai].model``,
            used for entries whose model_name is empty or null.

    Returns:
        A list of ModelProfile instances. Falls back to DEFAULT_PROFILES
        (with the Ollama entry bound to configured_model) when no
        entries are provided.
    """

    if not profile_entries:
        entries = [
            dict(entry)
            for entry in DEFAULT_PROFILES
        ]
    else:
        entries = [dict(entry) for entry in profile_entries]

    profiles: list[ModelProfile] = []

    for entry in entries:
        if not entry.get("model_name"):
            entry["model_name"] = configured_model
        profiles.append(_build_profile(entry))

    return profiles
