"""Phase 10.4 — Candidate classification and uncertainty: evidence contract.

Investigation result: the discovery candidate carries its type, evidence,
provenance, affected area, limitations, assumptions, and unresolved questions —
with no opaque universal score and no arbitrary ranking.
"""

from __future__ import annotations

import json

from atlas.evolution.capability_discovery import (
    DiscoverySignalKind,
    DiscoverySourceKind,
    detect_candidates,
    DiscoverySignal,
)


def _candidate(kind, subject, evidence=("e",)):
    return detect_candidates(
        [DiscoverySignal(kind, subject, DiscoverySourceKind.EXPERIENCE, evidence=evidence)]
    )[0]


class TestPhase104Classification:
    def test_candidate_carries_type_evidence_and_provenance(self):
        candidate = _candidate(DiscoverySignalKind.OBSERVED_FAILURE, "cap.x")
        payload = candidate.to_dict()
        assert payload["kind"] == "observed_failure"
        assert payload["sources"] == ["experience"]
        assert payload["evidence"] == ["e"]
        assert payload["affected_area"]
        assert "limitations" in payload

    def test_uncertainty_is_represented_explicitly(self):
        candidate = _candidate(DiscoverySignalKind.UNCERTAINTY, "cap.uncertain")
        assert any("uncertain" in x for x in candidate.limitations)

    def test_already_supported_is_a_limitation_not_a_gap(self):
        candidate = detect_candidates(
            [
                DiscoverySignal(
                    DiscoverySignalKind.UNAVAILABLE_CAPABILITY,
                    "cap.ok",
                    DiscoverySourceKind.CAPABILITY_MODEL,
                    evidence=("m",),
                )
            ],
            capability_names=["cap.ok"],
        )[0]
        assert candidate.already_supported is True

    def test_candidate_has_no_opaque_score(self):
        candidate = _candidate(DiscoverySignalKind.OBSERVED_FAILURE, "cap.x")
        for banned in ("score", "rank", "priority", "weight"):
            assert not hasattr(candidate, banned)

    def test_candidate_is_json_safe(self):
        json.dumps(_candidate(DiscoverySignalKind.OBSERVED_FAILURE, "cap.x").to_dict())
