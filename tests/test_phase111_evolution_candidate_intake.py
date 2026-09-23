"""Phase 11.1 — Evolution candidate intake: evidence contract.

Investigation result: Phase 10 already produces evidence-bearing discovery
candidates + assessments; Phase 11 adds only the deterministic intake record
that validates them into an evolution input. Creating a candidate grants no
authority — unsupported candidates fail closed.
"""

from __future__ import annotations

from atlas.evolution.capability_discovery import (
    CapabilityDiscoveryCandidate,
    DiscoveryAssessment,
    DiscoverySignalKind,
    DiscoveryVerdict,
)
from atlas.evolution.self_evolution import (
    EvolutionCandidate,
    EvolutionCandidateStatus,
    evolution_candidate_from_discovery,
)


def _discovery(subject="example.missing", verdict=DiscoveryVerdict.ACTIONABLE_GAP):
    evidence = (f"capability_model:{subject}",)
    candidate = CapabilityDiscoveryCandidate(
        candidate_id="disc:x",
        kind=DiscoverySignalKind.UNAVAILABLE_CAPABILITY,
        subject=subject,
        sources=("capability_model",),
        evidence=evidence,
    )
    assessment = DiscoveryAssessment(
        candidate_id="disc:x",
        subject=subject,
        verdict=verdict,
        rationale="evidence-backed",
        evidence=evidence,
        research_question=(
            f"what is required to {subject}"
            if verdict is DiscoveryVerdict.REQUIRES_RESEARCH
            else ""
        ),
    )
    return candidate, assessment


class TestPhase111EvolutionCandidateIntake:
    def test_actionable_discovery_validates_with_full_evidence(self):
        candidate, assessment = _discovery()
        evolution = evolution_candidate_from_discovery(
            candidate, assessment, goal_context="reduce gaps", constraints=["cost"]
        )
        assert evolution.status is EvolutionCandidateStatus.VALIDATED
        assert evolution.validated is True
        assert evolution.evidence == candidate.evidence
        assert evolution.provenance == ("capability_model",)
        assert evolution.discovery_verdict == "actionable_gap"
        assert evolution.goal_context == "reduce gaps"
        assert evolution.constraints == ("cost",)

    def test_research_required_discovery_validates_but_is_marked(self):
        candidate, assessment = _discovery(verdict=DiscoveryVerdict.REQUIRES_RESEARCH)
        evolution = evolution_candidate_from_discovery(candidate, assessment)
        assert evolution.status is EvolutionCandidateStatus.VALIDATED
        assert evolution.research_status == "required"

    def test_insufficient_evidence_is_rejected(self):
        candidate, assessment = _discovery(
            verdict=DiscoveryVerdict.INSUFFICIENT_EVIDENCE
        )
        evolution = evolution_candidate_from_discovery(candidate, assessment)
        assert evolution.status is EvolutionCandidateStatus.REJECTED
        assert evolution.validated is False

    def test_already_supported_and_blocked_verdicts_are_rejected(self):
        for verdict in (
            DiscoveryVerdict.ALREADY_SUPPORTED,
            DiscoveryVerdict.DUPLICATE,
            DiscoveryVerdict.BLOCKED_DEPENDENCY,
            DiscoveryVerdict.GOVERNANCE_BLOCKED,
        ):
            candidate, assessment = _discovery(verdict=verdict)
            evolution = evolution_candidate_from_discovery(candidate, assessment)
            assert evolution.status is EvolutionCandidateStatus.REJECTED, verdict

    def test_malformed_input_fails_closed(self):
        for bad in (None, object()):
            evolution = evolution_candidate_from_discovery(bad, bad)
            assert evolution.status is EvolutionCandidateStatus.REJECTED

    def test_candidate_creation_grants_no_authority(self):
        candidate, assessment = _discovery()
        evolution = evolution_candidate_from_discovery(candidate, assessment)
        assert isinstance(evolution, EvolutionCandidate)
        for banned in ("approve", "promote", "activate", "execute", "authorized"):
            assert not hasattr(evolution, banned)
        assert evolution.to_dict()["status"] == "validated"
