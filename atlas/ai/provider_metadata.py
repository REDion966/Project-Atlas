"""
Atlas AI Provider Metadata

Describes provider capabilities and priority.
"""

from dataclasses import dataclass, field

from atlas.ai.capabilities import Capability


@dataclass
class ProviderMetadata:
    """Information about an AI provider."""

    name: str

    version: str

    provider_type: str

    description: str

    models: list[str] = field(
        default_factory=list
    )

    capabilities: list[Capability] = field(
        default_factory=list
    )

    priority: int = 0