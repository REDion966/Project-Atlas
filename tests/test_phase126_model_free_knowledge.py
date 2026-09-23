"""Phase 12.6 — Model-Free Self-Knowledge, Memory & Research.

Validation result: self-knowledge (architecture/capability/repository map),
knowledge/history, validated-knowledge retrieval, research planning/policy, and
technology analysis all operate deterministically without any external AI. Web
research stays deny-by-default, and unverified claims remain unusable as
validated knowledge.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from atlas.research.models import (
    CitationRecord,
    ClaimVerification,
    KnowledgeClaim,
    SourceKind,
    VerificationStatus,
)
from atlas.research.sources.web import (
    DENY_ALL_HOSTS,
    WebHostPolicy,
    web_host_policy_from_hosts,
)
from atlas.research.validated_retrieval import (
    ValidatedKnowledgeRetriever,
    ValidatedKnowledgeStatus,
)
from tests.phase12_environment import model_free_environment

_T0 = datetime(2026, 1, 1, 12, 0, 0)
_T1 = datetime(2026, 2, 1, 12, 0, 0)


class _FakeStore:
    """Minimal duck-typed research storage (read-only usage)."""

    def __init__(self, claims, verifications):
        self._claims = list(claims)
        self._verifications = list(verifications)

    def is_available(self) -> bool:
        return True

    def load_claims(self):
        return list(self._claims)

    def load_verifications(self):
        return list(self._verifications)

    def store_claim(self, *_a, **_k):  # pragma: no cover - must never be called
        raise AssertionError("retrieval must not write")


def _claim(claim_id: str, statement: str) -> KnowledgeClaim:
    return KnowledgeClaim(
        claim_id=claim_id,
        statement=statement,
        citations=(
            CitationRecord(
                record_id=f"cit-{claim_id}",
                source_uri="docs/spec.md",
                source_title="Spec",
                source_kind=SourceKind.DOCUMENT,
                retrieved_at=_T0,
            ),
        ),
        confidence=0.4,
        extracted_at=_T0,
    )


def _verification(claim_id: str, status: VerificationStatus) -> ClaimVerification:
    return ClaimVerification(
        verification_id=f"verify:{claim_id}",
        claim_id=claim_id,
        status=status,
        score=0.75,
        evidence_summary="support",
        verified_at=_T1,
    )


@pytest.fixture(scope="module")
def model_free_kernel():
    with model_free_environment() as attempts:
        from atlas.kernel.atlas import Atlas

        atlas = Atlas()
        atlas.start()
        try:
            yield atlas, attempts
        finally:
            atlas.shutdown()


class TestPhase126ModelFreeKnowledge:
    def test_self_knowledge_is_available_without_a_model(self, model_free_kernel):
        atlas, _ = model_free_kernel
        architecture = atlas.architecture_model()
        capability = atlas.capability_model()
        repository = atlas.repository_map
        assert architecture is not None
        assert capability is not None and capability.entries
        assert repository is not None

    def test_capability_model_makes_no_external_model_authoritative(
        self, model_free_kernel
    ):
        atlas, _ = model_free_kernel
        model = atlas.capability_model()
        # Every AI-dependent capability is reported as such (evidence-derived),
        # never as silently authoritative.
        external = [
            e
            for e in model.entries
            if e.dependency.value == "external_model_dependent"
        ]
        for entry in external:
            assert entry.limitations  # declared, not hidden

    def test_history_and_evolution_knowledge_are_model_free(self, model_free_kernel):
        atlas, _ = model_free_kernel
        assert atlas.evolution_knowledge is not None

    def test_validated_knowledge_retrieval_is_model_free(self, model_free_kernel):
        atlas, _ = model_free_kernel
        result = atlas.validated_knowledge("memory")
        assert result is not None

    def test_research_infrastructure_is_model_free(self, model_free_kernel):
        atlas, _ = model_free_kernel
        assert atlas.research_coordinator is not None

    def test_web_research_is_deny_by_default(self):
        assert DENY_ALL_HOSTS.allowed_hosts == frozenset()
        assert DENY_ALL_HOSTS.permits("example.com") is False
        empty = web_host_policy_from_hosts([])
        assert empty.permits("example.com") is False
        listed = web_host_policy_from_hosts(["docs.example.com"])
        assert listed.permits("docs.example.com") is True
        assert listed.permits("evil.example.com") is False
        assert isinstance(WebHostPolicy(allowed_hosts=frozenset()), WebHostPolicy)

    def test_unverified_claims_are_unusable_as_validated_knowledge(self):
        with model_free_environment():
            claim = _claim("c-1", "atlas memory retrieval scoring")
            # No verification at all -> not retrievable.
            unverified = ValidatedKnowledgeRetriever(
                _FakeStore([claim], [])
            ).retrieve("memory")
            assert unverified.items == ()
            # An explicit non-SUPPORTED verification -> still not retrievable.
            contradicted = ValidatedKnowledgeRetriever(
                _FakeStore([claim], [_verification("c-1", VerificationStatus.CONTRADICTED)])
            ).retrieve("memory")
            assert contradicted.items == ()
            # Only a SUPPORTED verification becomes validated knowledge.
            supported = ValidatedKnowledgeRetriever(
                _FakeStore([claim], [_verification("c-1", VerificationStatus.SUPPORTED)])
            ).retrieve("memory")
            assert [item.claim_id for item in supported.items] == ["c-1"]

    def test_missing_research_store_fails_closed_without_falling_back(self):
        with model_free_environment():
            result = ValidatedKnowledgeRetriever(None).retrieve("memory")
            assert result.status is ValidatedKnowledgeStatus.STORE_UNAVAILABLE
            assert result.items == ()

    def test_technology_analysis_runs_model_free(self):
        from atlas.research.technology_analysis import (
            EvaluationCriterion,
            TechnologyFact,
            TechnologyProfile,
            VerificationState,
            assess_suitability,
        )

        with model_free_environment():
            profile = TechnologyProfile(
                name="candidate-library",
                facts=(
                    TechnologyFact(
                        statement="the library supports deterministic scoring",
                        state=VerificationState.VERIFIED,
                        confidence=0.9,
                        evidence=("docs/spec.md",),
                    ),
                ),
            )
            outcome = assess_suitability(
                "deterministic scoring",
                profile,
                [EvaluationCriterion(name="deterministic scoring")],
            )
            payload = outcome.to_dict()
            assert any(
                value
                in (
                    "suitable",
                    "partially_suitable",
                    "not_suitable",
                    "insufficient_evidence",
                )
                for value in payload.values()
            )
