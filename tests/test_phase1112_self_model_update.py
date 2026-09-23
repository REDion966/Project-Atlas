"""Phase 11.12 — Post-evolution self-model validation: evidence contract.

Investigation result: after governed activation the loop verifies the
self-model through the EXISTING ``CapabilityModel`` + router/dispatcher, and
registers the activated module on the ``ComponentRegistry`` (the smallest
deterministic projection). Nothing is fabricated and inconsistency is reported.
"""

from __future__ import annotations

from atlas.evolution.capability_discovery import (
    CapabilityDiscoveryCandidate,
    DiscoveryAssessment,
    DiscoverySignalKind,
    DiscoveryVerdict,
)
from atlas.evolution.self_evolution import (
    SelfEvolutionLoop,
    SelfEvolutionTerminal,
    project_evolved_capability,
    validate_self_model,
)
from atlas.lifecycle.component_registry import ComponentRegistry
from atlas.reasoning.execution.registry import CapabilityRegistry
from atlas.self_knowledge.capability_model import build_capability_model

_MODULE = "atlas/example/selfmodel_handlers.py"
_CAPABILITY = "example.selfmodelled"


class _InertRegistry(CapabilityRegistry):
    """A registry whose registration silently does nothing (inconsistency probe)."""

    def register(self, name, handler):  # noqa: ARG002
        return None

    def unregister(self, name):  # noqa: ARG002
        return None


def _discovery():
    evidence = ("capability_model:example.missing",)
    candidate = CapabilityDiscoveryCandidate(
        candidate_id="disc:x",
        kind=DiscoverySignalKind.UNAVAILABLE_CAPABILITY,
        subject="example.missing",
        sources=("capability_model",),
        evidence=evidence,
    )
    assessment = DiscoveryAssessment(
        candidate_id="disc:x",
        subject="example.missing",
        verdict=DiscoveryVerdict.ACTIONABLE_GAP,
        rationale="evidence-backed",
        evidence=evidence,
    )
    return candidate, assessment


def _run(tmp_path, *, registry=None, components=None):
    loop = SelfEvolutionLoop(
        component_registry=components or ComponentRegistry(),
        capability_registry=registry or CapabilityRegistry(),
        repo_root=tmp_path,
    )
    candidate, assessment = _discovery()
    return loop.run(
        candidate,
        assessment,
        target_module=_MODULE,
        capability_name=_CAPABILITY,
        owner_approved=True,
        promotion_authorized=True,
    )


class TestPhase1112SelfModelUpdate:
    def test_activated_capability_is_represented_routable_and_invocable(self, tmp_path):
        components = ComponentRegistry()
        capabilities = CapabilityRegistry()
        result = _run(tmp_path, registry=capabilities, components=components)
        assert result.terminal is SelfEvolutionTerminal.ACTIVATED
        self_model = result.self_model
        assert self_model.represented is True
        assert self_model.routable is True
        assert self_model.invocable is True
        assert self_model.consistent is True
        assert self_model.availability == "available"
        assert self_model.dependency == "deterministic"

        # The existing capability model (self-knowledge projection) reflects it,
        # with the activated module recorded as its providing component.
        model = build_capability_model(
            components, capability_registry=capabilities
        )
        entry = next(e for e in model.entries if e.name == _CAPABILITY)
        assert entry.availability.value == "available"
        assert entry.dependency.value == "deterministic"

    def test_self_model_is_not_fabricated(self):
        validation = validate_self_model(
            "example.absent", capability_registry=CapabilityRegistry()
        )
        assert validation.represented is False
        assert validation.consistent is False
        assert validation.reason

    def test_projection_is_deterministic_and_idempotent(self):
        components = ComponentRegistry()
        first = project_evolved_capability(
            components, module_path=_MODULE, capability_name=_CAPABILITY
        )
        second = project_evolved_capability(
            components, module_path=_MODULE, capability_name=_CAPABILITY
        )
        assert first is not None
        assert second is None  # already represented; never duplicated
        model = build_capability_model(components)
        assert [e.name for e in model.entries].count(_CAPABILITY) == 1

    def test_self_model_inconsistency_is_reported_not_hidden(self, tmp_path):
        result = _run(tmp_path, registry=_InertRegistry())
        assert result.terminal is SelfEvolutionTerminal.SELF_MODEL_INCONSISTENT
        assert result.self_model.consistent is False
        assert result.ok is False
