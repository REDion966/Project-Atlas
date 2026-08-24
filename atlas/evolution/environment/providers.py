"""Atlas Post-Core F1 — Environment Provider Abstraction.

``EnvironmentProvider`` is a minimal Protocol exposing a ``domain`` and an
``observe()`` surface. Concrete providers adapt EXISTING registries
(duck-typed — no hard import) into normalized, secret-free
``EnvironmentState`` snapshots. Failing providers fail closed and are surfaced as
bounded ``EnvironmentProviderFailure`` records by the ``EnvironmentObserver``.

Source isolation: the environment layer never talks to a concrete vendor registry
directly; it depends only on the provider protocol and duck-typed registry
interfaces.
"""

from __future__ import annotations

import platform
import sys
from typing import Protocol, runtime_checkable

from atlas.evolution.environment.models import (
    EnvironmentDomain,
    EnvironmentEntity,
    EnvironmentState,
    ObservationReliability,
)


@runtime_checkable
class EnvironmentProvider(Protocol):
    """Contract implemented by every environment-state observer."""

    def provider_name(self) -> str: ...

    def observe(self) -> list[EnvironmentState]:
        """Return normalized environment-state snapshots.

        Raises:
            Exception: The EnvironmentObserver converts any exception into a
                bounded EnvironmentProviderFailure (fail-closed), it never
                crashes the cycle.
        """
        ...


class ModelProfileObserver:
    domain = EnvironmentDomain.MODEL

    def __init__(self, registry, reliability=ObservationReliability.MEDIUM):
        # registry: anything exposing ``list_profiles()``
        self._registry = registry
        self._reliability = reliability

    def provider_name(self) -> str:
        return "model_profile"

    def observe(self) -> list[EnvironmentState]:
        states: list[EnvironmentState] = []
        for profile in self._registry.list_profiles():
            provider = getattr(profile, "provider_name", "unknown")
            model = getattr(profile, "model_name", "unknown")
            state = {
                "provider_name": provider,
                "model_name": model,
                "complexity_score": getattr(profile, "complexity_score", None),
                "latency_class": getattr(profile, "latency_class", None),
                "cost_tier": getattr(profile, "cost_tier", None),
                "supported_tasks": list(getattr(profile, "supported_tasks", []) or []),
                "priority": getattr(profile, "priority", None),
            }
            entity = EnvironmentEntity(
                self.domain, f"{provider}:{model}"
            )
            states.append(EnvironmentState(
                entity=entity,
                state=state,
                source=self.provider_name(),
                reliability=self._reliability,
            ))
        return states


class ProviderAvailabilityObserver:
    domain = EnvironmentDomain.PROVIDER

    def __init__(self, registry, reliability=ObservationReliability.MEDIUM):
        # registry: anything exposing ``providers()``
        self._registry = registry
        self._reliability = reliability

    def provider_name(self) -> str:
        return "provider_availability"

    def observe(self) -> list[EnvironmentState]:
        states = []
        for name in self._registry.providers():
            states.append(EnvironmentState(
                entity=EnvironmentEntity(self.domain, name),
                state={"available": True},
                source=self.provider_name(),
                reliability=self._reliability,
            ))
        return states


class ToolRegistryObserver:
    domain = EnvironmentDomain.TOOL

    def __init__(self, registry, reliability=ObservationReliability.MEDIUM):
        # registry: anything exposing ``list()`` returning Tool-like objects
        self._registry = registry
        self._reliability = reliability

    def provider_name(self) -> str:
        return "tool_registry"

    def observe(self) -> list[EnvironmentState]:
        states = []
        for tool in self._registry.list():
            states.append(EnvironmentState(
                entity=EnvironmentEntity(self.domain, tool.name),
                state={
                    "category": getattr(tool, "category", "utility"),
                    "tags": list(getattr(tool, "tags", []) or []),
                    "has_handler": getattr(tool, "handler", None) is not None,
                },
                source=self.provider_name(),
                reliability=self._reliability,
            ))
        return states


class CapabilityRegistryObserver:
    domain = EnvironmentDomain.CAPABILITY

    def __init__(self, registry, reliability=ObservationReliability.MEDIUM):
        # registry: anything exposing ``registered_names``
        self._registry = registry
        self._reliability = reliability

    def provider_name(self) -> str:
        return "capability_registry"

    def observe(self) -> list[EnvironmentState]:
        states = []
        for name in self._registry.registered_names:
            states.append(EnvironmentState(
                entity=EnvironmentEntity(self.domain, name),
                state={"registered": True},
                source=self.provider_name(),
                reliability=self._reliability,
            ))
        return states


class SkillRegistryObserver:
    domain = EnvironmentDomain.SKILL

    def __init__(self, registry, reliability=ObservationReliability.MEDIUM):
        # registry: anything exposing ``list()`` returning Skill-like objects
        self._registry = registry
        self._reliability = reliability

    def provider_name(self) -> str:
        return "skill_registry"

    def observe(self) -> list[EnvironmentState]:
        states = []
        for skill in self._registry.list():
            kind = getattr(skill, "kind", None)
            status = getattr(skill, "status", None)
            states.append(EnvironmentState(
                entity=EnvironmentEntity(
                    self.domain, getattr(skill, "skill_id", str(skill))
                ),
                state={
                    "name": getattr(skill, "name", ""),
                    "kind": kind.name if hasattr(kind, "name") else str(kind),
                    "status": status.name if hasattr(status, "name") else str(status),
                },
                source=self.provider_name(),
                reliability=self._reliability,
            ))
        return states


class RuntimeEnvironmentObserver:
    """Expose safe, deterministic runtime metadata (never secrets/env dumps)."""

    domain = EnvironmentDomain.RUNTIME

    def __init__(
        self,
        python_version: str | None = None,
        platform_name: str | None = None,
        implementation: str | None = None,
        reliability: ObservationReliability = ObservationReliability.HIGH,
    ) -> None:
        self._python_version = python_version or (
            f"{sys.version_info.major}.{sys.version_info.minor}."
            f"{sys.version_info.micro}"
        )
        self._platform_name = platform_name or sys.platform
        self._implementation = implementation or platform.python_implementation()
        self._reliability = reliability

    def provider_name(self) -> str:
        return "runtime_environment"

    def observe(self) -> list[EnvironmentState]:
        return [
            EnvironmentState(
                entity=EnvironmentEntity(self.domain, "python"),
                state={
                    "version": self._python_version,
                    "platform": self._platform_name,
                    "implementation": self._implementation,
                },
                source=self.provider_name(),
                reliability=self._reliability,
            )
        ]


#: Convenience default provider set used by callers that want the standard
#: model / tool / capability / skill / runtime observation surface.
def default_providers(
    model_registry=None,
    provider_registry=None,
    tool_registry=None,
    capability_registry=None,
    skill_registry=None,
) -> list[EnvironmentProvider]:
    """Build the standard F1 provider set from existing registries.

    Any ``None`` registry is skipped so the cycle stays purely observational
    and never fails on an unavailable subsystem.
    """
    providers: list[EnvironmentProvider] = [RuntimeEnvironmentObserver()]
    if model_registry is not None:
        providers.append(ModelProfileObserver(model_registry))
    if provider_registry is not None:
        providers.append(ProviderAvailabilityObserver(provider_registry))
    if tool_registry is not None:
        providers.append(ToolRegistryObserver(tool_registry))
    if capability_registry is not None:
        providers.append(CapabilityRegistryObserver(capability_registry))
    if skill_registry is not None:
        providers.append(SkillRegistryObserver(skill_registry))
    return providers