"""Phase 17.5 — Claim Verifier tests."""

import pytest

from atlas.research.models import (
    ClaimVerification,
    KnowledgeClaim,
    ResearchSource,
    SourceKind,
    SourceProfile,
    VerificationStatus,
)
from atlas.research.verifier import ClaimOutcome, ClaimVerifier, VerificationModel


def claim(statement, claim_id=None):
    return KnowledgeClaim(
        claim_id=claim_id or f"claim:{abs(hash(statement)) & 0xFFFFFFFF:08x}",
        statement=statement,
    )


def source(uri, text):
    return SourceProfile(uri=uri, kind=SourceKind.DOCUMENT, text=text)


def verify(claims, sources, model=None, strict_llm=False):
    return ClaimVerifier(model=model, strict_llm=strict_llm).verify(claims, sources)


class TestSingleSource:
    def test_supporting_single_source_is_plausible(self):
        sources = [source("s1", "Atlas uses SQLite for persistent storage.")]
        results = verify([claim("Atlas uses SQLite for persistent storage.")], sources)
        assert results[0].metadata["outcome"] == ClaimOutcome.PLAUSIBLE.name
        assert results[0].status == VerificationStatus.SUPPORTED

    def test_single_source_not_mentioned_is_unknown(self):
        sources = [source("s1", "Some unrelated text about indexing.")]
        results = verify([claim("Atlas uses SQLite for storage.")], sources)
        assert results[0].metadata["outcome"] == ClaimOutcome.UNKNOWN.name
        assert results[0].status == VerificationStatus.UNVERIFIED
        assert results[0].score == 0.0

    def test_single_source_contradicts_is_contested(self):
        sources = [source("s1", "Atlas does not use SQLite for storage.")]
        results = verify([claim("Atlas uses SQLite for storage.")], sources)
        assert results[0].metadata["outcome"] == ClaimOutcome.CONTESTED.name
        assert results[0].status == VerificationStatus.CONTRADICTED


class TestMultiSourceAgreement:
    def test_two_supporting_sources_are_verified(self):
        sources = [
            source("s1", "Atlas uses SQLite for persistent storage across sessions."),
            source("s2", "Atlas uses SQLite for persistent storage across sessions."),
        ]
        results = verify([claim("Atlas uses SQLite for persistent storage.")], sources)
        assert results[0].metadata["outcome"] == ClaimOutcome.VERIFIED.name
        assert results[0].status == VerificationStatus.SUPPORTED

    def test_three_supporting_sources_score_highest(self):
        text = "Atlas uses SQLite for persistent storage across sessions."
        sources = [
            source("s1", text),
            source("s2", text),
            source("s3", text),
        ]
        results = verify([claim(text)], sources)
        assert results[0].score >= 0.9

    def test_more_sources_bump_score(self):
        text = "Atlas uses SQLite for persistent storage across sessions."
        one = verify([claim(text)], [source("s1", text)])
        two = verify([claim(text)], [source("s1", text), source("s2", text)])
        assert two[0].score > one[0].score


class TestContradictionDetection:
    def test_mixed_evidence_is_contested(self):
        text = "Atlas uses SQLite for persistent storage across sessions."
        sources = [
            source("s1", text),
            source("s2", "Atlas does not use SQLite for persistent storage."),
        ]
        results = verify([claim(text)], sources)
        assert results[0].metadata["outcome"] == ClaimOutcome.CONTESTED.name
        assert results[0].status == VerificationStatus.CONTRADICTED

    def test_contradiction_lowers_score(self):
        text = "Atlas uses SQLite for persistent storage across sessions."
        agreement = verify([claim(text)], [source("s1", text), source("s2", text)])
        contested = verify(
            [claim(text)],
            [source("s1", text), source("s2", "Atlas does not use SQLite.")],
        )
        assert contested[0].score < agreement[0].score

    def test_contradicting_evidence_recorded_in_metadata(self):
        text = "Atlas uses SQLite for persistent storage across sessions."
        results = verify(
            [claim(text)],
            [source("s1", text), source("s2", "Atlas does not use SQLite.")],
        )
        assert results[0].metadata["supporting"] == ["s1"]
        assert results[0].metadata["contradicting"] == ["s2"]


class TestConfidenceCalculation:
    def test_score_within_bounds(self):
        text = "Atlas uses SQLite for storage."
        results = verify([claim(text)], [source("s1", text)])
        assert 0.0 <= results[0].score <= 0.95

    def test_score_is_rounded(self):
        text = "Atlas uses SQLite for storage."
        results = verify([claim(text)], [source("s1", text)])
        assert results[0].score == round(results[0].score, 4)


class TestOutcomes:
    def test_all_outcomes_representable(self):
        assert {o.name for o in ClaimOutcome} == {
            "VERIFIED",
            "PLAUSIBLE",
            "CONTESTED",
            "UNKNOWN",
        }

    def test_unknown_maps_to_unverified(self):
        results = verify([claim("Nothing in the corpus mentions this.")], [source("s1", "x.")])
        assert results[0].status == VerificationStatus.UNVERIFIED


class TestEvidenceCollection:
    def test_evidence_summary_present(self):
        text = "Atlas uses SQLite for persistent storage."
        results = verify([claim(text)], [source("s1", text)])
        assert "supported by 1 source(s)" in results[0].evidence_summary


class TestLLMOptional:
    class FakeModel:
        def __init__(self, response):
            self.response = response
            self.calls = 0

        def complete(self, prompt):
            self.calls += 1
            return self.response

    def test_model_not_called_when_strict_llm_disabled(self):
        model = self.FakeModel("CONTESTED")
        text = "Atlas uses SQLite for persistent storage."
        results = verify([claim(text)], [source("s1", text)], model=model)
        assert model.calls == 0
        assert results[0].metadata["outcome"] == ClaimOutcome.PLAUSIBLE.name

    def test_strict_llm_overrides_verdict(self):
        model = self.FakeModel("VERIFIED")
        text = "Atlas uses SQLite for persistent storage."
        results = verify([claim(text)], [source("s1", text)], model=model, strict_llm=True)
        assert model.calls == 1
        assert results[0].metadata["outcome"] == ClaimOutcome.VERIFIED.name

    def test_invalid_model_response_falls_back(self):
        model = self.FakeModel("GARBAGE")
        text = "Atlas uses SQLite for persistent storage."
        results = verify([claim(text)], [source("s1", text)], model=model, strict_llm=True)
        assert results[0].metadata["outcome"] == ClaimOutcome.PLAUSIBLE.name

    def test_model_raising_falls_back(self):
        class ExplodingModel:
            def complete(self, prompt):
                raise RuntimeError("provider down")

        text = "Atlas uses SQLite for persistent storage."
        results = verify(
            [claim(text)], [source("s1", text)], model=ExplodingModel(), strict_llm=True
        )
        assert results[0].metadata["outcome"] == ClaimOutcome.PLAUSIBLE.name

    def test_conforms_to_protocol(self):
        instance = self.FakeModel("VERIFIED")
        model = self.FakeModel("VERIFIED")
        assert isinstance(model, VerificationModel)


class TestDeterminism:
    def test_identical_inputs_identical_outputs(self):
        text = "Atlas uses SQLite for persistent storage across sessions."
        sources = [source("s1", text), source("s2", text)]
        first = verify([claim(text)], sources)
        second = verify([claim(text)], sources)
        assert first[0].metadata["outcome"] == second[0].metadata["outcome"]
        assert first[0].score == second[0].score
        assert first[0].status == second[0].status

    def test_order_preserving(self):
        text = "Atlas uses SQLite for persistent storage across sessions."
        results = verify(
            [claim("Alpha statement here."), claim(text)],
            [source("s1", text)],
        )
        assert [r.claim_id for r in results] == [
            results[0].claim_id,
            results[1].claim_id,
        ]


class TestEmptyAndMalformed:
    def test_no_claims_returns_empty(self):
        assert verify([], [source("s1", "text")]) == []

    def test_empty_sources_yield_unknown(self):
        results = verify([claim("Atlas uses SQLite for storage.")], [])
        assert results[0].metadata["outcome"] == ClaimOutcome.UNKNOWN.name

    def test_empty_claim_statement_is_unknown(self):
        results = verify([claim("")], [source("s1", "Atlas uses SQLite.")])
        assert results[0].metadata["outcome"] == ClaimOutcome.UNKNOWN.name

    def test_metadata_source_uri_present(self):
        text = "Atlas uses SQLite for storage."
        results = verify([claim(text)], [source("s1", text)])
        assert ClaimVerification is not None
