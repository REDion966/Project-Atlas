"""Phase 10.7 — Discovery → existing capability/development pathway.

Investigation result: a validated candidate is connectable to the EXISTING
governed path via ``assess_development_gap`` + the Phase-8 acquisition strategy
layer. The hand-off is ADVISORY only: it grants no authority, prepares nothing,
and never executes development, promotion, or activation.
"""

from __future__ import annotations

from atlas.evolution.capability_discovery import (
    DiscoverySignal,
    DiscoverySignalKind,
    DiscoverySourceKind,
    detect_candidates,
    handoff_to_development,
)
from atlas.reasoning.execution.registry import CapabilityRegistry


def _candidate(subject, kind=DiscoverySignalKind.OBSERVED_FAILURE):
    return detect_candidates(
        [
            DiscoverySignal(
                kind, subject, DiscoverySourceKind.EXPERIENCE, evidence=("e",)
            )
        ]
    )[0]


class TestPhase107DiscoveryToDevelopment:
    def test_actionable_candidate_hands_off_to_the_existing_path(self):
        handoff = handoff_to_development(_candidate("cap.new"))
        assert handoff is not None
        assert handoff.acquirable is True
        assert handoff.gap_kind in ("missing_knowledge", "missing_capability")
        assert handoff.acquisition_mechanism in (
            "internal_development",
            "researched_internalization",
        )

    def test_already_supported_subject_reports_supported(self):
        handoff = handoff_to_development(
            _candidate("cap.ok"), capability_names=["cap.ok"]
        )
        assert handoff.gap_kind == "already_supported"
        assert handoff.acquisition_mechanism == "existing_capability"

    def test_handoff_is_advisory_only(self):
        registry = CapabilityRegistry()
        handoff = handoff_to_development(_candidate("cap.new"))
        for banned in ("execute", "approve", "promote", "activate", "apply"):
            assert not hasattr(handoff, banned)
        # Nothing was registered by handing off.
        assert registry.registered_names == []

    def test_handoff_is_deterministic(self):
        first = handoff_to_development(_candidate("cap.new")).to_dict()
        second = handoff_to_development(_candidate("cap.new")).to_dict()
        assert first == second

    def test_malformed_candidate_is_refused(self):
        assert handoff_to_development(None) is None
