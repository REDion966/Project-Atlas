"""Phase 10.2 — Capability-gap signal collection: evidence contract.

Investigation result: signals already exist across Atlas (capability model,
self-model, experience, inventory, human goals); the discovery layer normalizes
them into ``DiscoverySignal`` with provenance. No artificial history is invented.
"""

from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace

from atlas.evolution.capability_discovery import (
    DiscoverySignalKind,
    DiscoverySourceKind,
    signals_from_capability_model,
    signals_from_experiences,
    signals_from_human_goal,
    signals_from_inventory,
    signals_from_self_model,
)
from atlas.experience.models import ExperienceOutcome, StructuredExperience
from atlas.lifecycle.component_registry import ComponentRegistry
from atlas.lifecycle.models import ComponentMetadata, ComponentStatus
from atlas.self_knowledge.capability_model import build_capability_model


def _experience(outcome, capabilities):
    return StructuredExperience(
        experience_id=f"EXP-{outcome.name}-{'-'.join(capabilities)}",
        timestamp=datetime.now(),
        duration_ms=1.0,
        pipeline_path=["reasoning"],
        outcome=outcome,
        reasoning_capabilities=list(capabilities),
    )


class TestPhase102GapSignals:
    def test_signals_from_capability_model(self):
        registry = ComponentRegistry()
        registry.register(
            ComponentMetadata(
                name="down", package="atlas.b", module_path="atlas.b.x",
                status=ComponentStatus.OFFLINE, provided_capabilities=["cap.down"],
            )
        )
        registry.register(
            ComponentMetadata(
                name="ai", package="atlas.ai", module_path="atlas.ai.x",
                status=ComponentStatus.HEALTHY, provided_capabilities=["ai_chat"],
            )
        )
        signals = signals_from_capability_model(build_capability_model(registry))
        kinds = {s.kind for s in signals}
        assert DiscoverySignalKind.UNAVAILABLE_CAPABILITY in kinds
        assert DiscoverySignalKind.EMERGING_OPPORTUNITY in kinds
        assert all(s.source is DiscoverySourceKind.CAPABILITY_MODEL for s in signals)
        assert all(s.evidence for s in signals)

    def test_signals_from_self_model(self):
        snapshot = SimpleNamespace(
            capability_assessments={"cap.weak": 0.2, "cap.strong": 0.9},
            persistent_challenges=["memory recall under load"],
        )
        signals = signals_from_self_model(snapshot)
        subjects = {s.subject for s in signals}
        assert "cap.weak" in subjects
        assert "cap.strong" not in subjects
        assert any(
            s.kind is DiscoverySignalKind.REPEATED_LIMITATION for s in signals
        )

    def test_signals_from_experiences_require_recurrence(self):
        one = signals_from_experiences(
            [_experience(ExperienceOutcome.FAILURE, ["cap.x"])]
        )
        assert one == ()  # a single failure is not yet a signal
        two = signals_from_experiences(
            [
                _experience(ExperienceOutcome.FAILURE, ["cap.x"]),
                _experience(ExperienceOutcome.PARTIAL, ["cap.x"]),
            ]
        )
        assert len(two) == 1
        assert two[0].occurrences == 2
        assert two[0].source is DiscoverySourceKind.EXPERIENCE

    def test_signals_from_human_goal_is_explicit_only(self):
        assert signals_from_human_goal("   ") == ()
        signals = signals_from_human_goal("add a scheduling capability")
        assert len(signals) == 1
        assert signals[0].kind is DiscoverySignalKind.UNMET_REQUIREMENT

    def test_signals_from_inventory(self):
        inventory = SimpleNamespace(missing_required=lambda: ("planning",))
        signals = signals_from_inventory(inventory)
        assert len(signals) == 1
        assert signals[0].kind is DiscoverySignalKind.MISSING_KNOWLEDGE
