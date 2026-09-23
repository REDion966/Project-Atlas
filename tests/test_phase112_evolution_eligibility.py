"""Phase 11.2 — Evolution eligibility assessment: evidence contract.

Investigation result: eligibility reuses the existing gap/decision inputs and
produces an explainable state (never an opaque score, never authorization).
"""

from __future__ import annotations

from types import SimpleNamespace

from atlas.evolution.capability_discovery import (
    CapabilityDiscoveryCandidate,
    DiscoveryAssessment,
    DiscoverySignalKind,
    DiscoveryVerdict,
)
from atlas.evolution.self_evolution import (
    EvolutionEligibilityState,
    assess_evolution_eligibility,
    evolution_candidate_from_discovery,
)


def _candidate(verdict=DiscoveryVerdict.ACTIONABLE_GAP, subject="example.missing"):
    evidence = (f"capability_model:{subject}",)
    discovery = CapabilityDiscoveryCandidate(
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
        research_question=f"what is required to {subject}",
    )
    return evolution_candidate_from_discovery(discovery, assessment)


class _Retriever:
    def __init__(self, items):
        self._items = items

    def retrieve(self, query):  # noqa: ARG002
        return SimpleNamespace(items=list(self._items))


class _RaisingRetriever:
    def retrieve(self, query):  # noqa: ARG002
        raise RuntimeError("knowledge unavailable")


class TestPhase112EvolutionEligibility:
    def test_evidence_backed_gap_is_eligible(self):
        result = assess_evolution_eligibility(_candidate())
        assert result.state is EvolutionEligibilityState.ELIGIBLE
        assert result.eligible is True

    def test_already_supported_is_not_eligible(self):
        result = assess_evolution_eligibility(
            _candidate(), capability_names=["example.missing"]
        )
        assert result.state is EvolutionEligibilityState.ALREADY_SUPPORTED

    def test_insufficient_evidence_requires_research(self):
        result = assess_evolution_eligibility(
            _candidate(verdict=DiscoveryVerdict.REQUIRES_RESEARCH)
        )
        assert result.state is EvolutionEligibilityState.REQUIRES_RESEARCH
        assert result.research_question

    def test_validated_knowledge_makes_a_researched_candidate_eligible(self):
        result = assess_evolution_eligibility(
            _candidate(verdict=DiscoveryVerdict.REQUIRES_RESEARCH),
            knowledge_retriever=_Retriever([object()]),
        )
        assert result.state is EvolutionEligibilityState.ELIGIBLE

    def test_unavailable_knowledge_keeps_the_candidate_blocked(self):
        for retriever in (_Retriever([]), _RaisingRetriever(), None):
            result = assess_evolution_eligibility(
                _candidate(verdict=DiscoveryVerdict.REQUIRES_RESEARCH),
                knowledge_retriever=retriever,
            )
            assert result.state is EvolutionEligibilityState.REQUIRES_RESEARCH

    def test_dependency_and_governance_blocks(self):
        assert (
            assess_evolution_eligibility(
                _candidate(), dependency_blocked=True
            ).state
            is EvolutionEligibilityState.BLOCKED_DEPENDENCY
        )
        assert (
            assess_evolution_eligibility(
                _candidate(), governance_blocked=True
            ).state
            is EvolutionEligibilityState.GOVERNANCE_BLOCKED
        )

    def test_invalid_candidate_is_reported(self):
        result = assess_evolution_eligibility(None)
        assert result.state is EvolutionEligibilityState.INVALID_CANDIDATE
        assert result.eligible is False
        assert result.to_dict()["state"] == "invalid_candidate"
