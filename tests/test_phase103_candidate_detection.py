"""Phase 10.3 — Candidate capability-gap detection: evidence contract.

Investigation result: candidate detection is deterministic; it dedupes by
(kind, subject), preserves provenance/evidence, marks already-registered
subjects, and never emits a candidate without evidence. Matching is LEXICAL
token overlap (explicitly not semantic understanding).
"""

from __future__ import annotations

from atlas.evolution.capability_discovery import (
    DiscoverySignal,
    DiscoverySignalKind,
    DiscoverySourceKind,
    detect_candidates,
)


def _signal(kind, subject, source, evidence):
    return DiscoverySignal(kind, subject, source, evidence=evidence)


class TestPhase103CandidateDetection:
    def test_detects_and_dedups_by_subject(self):
        signals = [
            _signal(
                DiscoverySignalKind.OBSERVED_FAILURE,
                "cap.x",
                DiscoverySourceKind.EXPERIENCE,
                ("e1",),
            ),
            _signal(
                DiscoverySignalKind.OBSERVED_FAILURE,
                "cap.x",
                DiscoverySourceKind.SELF_MODEL,
                ("e2",),
            ),
        ]
        candidates = detect_candidates(signals)
        assert len(candidates) == 1
        assert set(candidates[0].evidence) == {"e1", "e2"}
        assert candidates[0].occurrences == 2
        assert set(candidates[0].sources) == {"experience", "self_model"}

    def test_already_supported_subject_is_marked(self):
        signals = [
            _signal(
                DiscoverySignalKind.UNAVAILABLE_CAPABILITY,
                "vector_search",
                DiscoverySourceKind.CAPABILITY_MODEL,
                ("capability_model:vector_search",),
            )
        ]
        candidate = detect_candidates(
            signals, capability_names=["vector_search"]
        )[0]
        assert candidate.already_supported is True
        assert any("already-registered" in x for x in candidate.limitations)

    def test_signal_without_evidence_produces_no_candidate(self):
        empty = DiscoverySignal(
            DiscoverySignalKind.OBSERVED_FAILURE, "cap.x", DiscoverySourceKind.EXPERIENCE
        )
        assert detect_candidates([empty]) == ()
        blank = DiscoverySignal(
            DiscoverySignalKind.OBSERVED_FAILURE,
            "   ",
            DiscoverySourceKind.EXPERIENCE,
            evidence=("e",),
        )
        assert detect_candidates([blank]) == ()

    def test_detection_is_deterministic(self):
        signals = [
            _signal(
                DiscoverySignalKind.UNMET_REQUIREMENT,
                "b capability",
                DiscoverySourceKind.HUMAN_GOAL,
                ("g",),
            ),
            _signal(
                DiscoverySignalKind.OBSERVED_FAILURE,
                "a capability",
                DiscoverySourceKind.EXPERIENCE,
                ("e",),
            ),
        ]
        first = [c.to_dict() for c in detect_candidates(signals)]
        second = [c.to_dict() for c in detect_candidates(signals)]
        assert first == second
        assert [c["subject"] for c in first] == ["a capability", "b capability"]
