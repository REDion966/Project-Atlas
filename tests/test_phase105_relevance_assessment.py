"""Phase 10.5 — Opportunity/relevance assessment: evidence contract.

Investigation result: assessment is a deterministic, explainable verdict — never
authorization. Already-supported subjects are never rediscovered as missing;
no evidence yields no conclusion; uncertainty stays visible.
"""

from __future__ import annotations

from types import SimpleNamespace

from atlas.evolution.capability_discovery import (
    CapabilityDiscoveryCandidate,
    DiscoverySignalKind,
    DiscoveryVerdict,
    assess_candidate,
)


def _cand(kind, subject, evidence=("e",), occurrences=1, already_supported=False):
    return CapabilityDiscoveryCandidate(
        candidate_id="disc:x",
        kind=kind,
        subject=subject,
        sources=("experience",),
        evidence=evidence,
        occurrences=occurrences,
        already_supported=already_supported,
    )


class _Retriever:
    def __init__(self, items):
        self._items = items

    def retrieve(self, query):  # noqa: ARG002
        return SimpleNamespace(items=list(self._items))


class TestPhase105Relevance:
    def test_already_supported_is_not_a_gap(self):
        verdict = assess_candidate(
            _cand(DiscoverySignalKind.UNAVAILABLE_CAPABILITY, "cap.ok"),
            capability_names=["cap.ok"],
        )
        assert verdict.verdict is DiscoveryVerdict.ALREADY_SUPPORTED
        assert verdict.actionable is False

    def test_observed_failure_is_actionable(self):
        verdict = assess_candidate(
            _cand(DiscoverySignalKind.OBSERVED_FAILURE, "cap.x")
        )
        assert verdict.verdict is DiscoveryVerdict.ACTIONABLE_GAP
        assert verdict.actionable is True

    def test_missing_knowledge_requires_research_without_evidence(self):
        verdict = assess_candidate(
            _cand(DiscoverySignalKind.MISSING_KNOWLEDGE, "cap.new")
        )
        assert verdict.verdict is DiscoveryVerdict.REQUIRES_RESEARCH
        assert verdict.research_question

    def test_knowledge_present_makes_it_actionable(self):
        verdict = assess_candidate(
            _cand(DiscoverySignalKind.MISSING_KNOWLEDGE, "cap.new"),
            knowledge_retriever=_Retriever([object()]),
        )
        assert verdict.verdict is DiscoveryVerdict.ACTIONABLE_GAP

    def test_uncertainty_is_insufficient_evidence(self):
        verdict = assess_candidate(_cand(DiscoverySignalKind.UNCERTAINTY, "cap.x"))
        assert verdict.verdict is DiscoveryVerdict.INSUFFICIENT_EVIDENCE

    def test_no_evidence_is_insufficient_evidence(self):
        verdict = assess_candidate(
            _cand(DiscoverySignalKind.OBSERVED_FAILURE, "cap.x", evidence=())
        )
        assert verdict.verdict is DiscoveryVerdict.INSUFFICIENT_EVIDENCE

    def test_duplicate_and_blocked_dependency(self):
        duplicate = assess_candidate(
            _cand(DiscoverySignalKind.OBSERVED_FAILURE, "cap.x"),
            seen_subjects=["cap.x"],
        )
        assert duplicate.verdict is DiscoveryVerdict.DUPLICATE

        blocked = assess_candidate(
            _cand(DiscoverySignalKind.OBSERVED_FAILURE, "cap.x"),
            dependency_blocked=True,
        )
        assert blocked.verdict is DiscoveryVerdict.BLOCKED_DEPENDENCY

    def test_malformed_candidate_fails_closed(self):
        verdict = assess_candidate(None)
        assert verdict.verdict is DiscoveryVerdict.INSUFFICIENT_EVIDENCE
