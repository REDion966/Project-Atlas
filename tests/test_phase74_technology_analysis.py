"""Phase 7.4 — Technology analysis: evidence contract.

Investigation result: no structured technology-analysis representation existed,
so the smallest deterministic, model-free layer was added at
``atlas/research/technology_analysis.py``. It projects EXISTING validated
knowledge (Phase 3) into structured technology facts and criteria-driven
analysis — it is not a second knowledge/evidence/provenance store.

It keeps FACT (verified claim) distinct from ANALYSIS (criterion findings).
"""

from __future__ import annotations

import json

from atlas.research.models import CitationRecord, SourceKind
from atlas.research.technology_analysis import (
    EvaluationCriterion,
    VerificationState,
    evaluate_criterion,
    fact_from_validated_item,
    profile_from_validated_items,
)
from atlas.research.validated_retrieval import ValidatedKnowledgeItem


def _item(claim_id, statement, status, score=0.9, uri="https://example.com/x"):
    return ValidatedKnowledgeItem(
        claim_id=claim_id,
        statement=statement,
        validation_status=status,
        claim_confidence=0.8,
        verification_score=score,
        citations=(
            CitationRecord(
                record_id=f"cite:{claim_id}",
                source_uri=uri,
                source_kind=SourceKind.WEB,
            ),
        ),
    )


class TestPhase74TechnologyAnalysis:
    def test_verified_items_become_facts_with_evidence(self):
        profile = profile_from_validated_items(
            "VectorizerDB",
            [_item("c1", "VectorizerDB supports vector search", "SUPPORTED")],
        )
        assert profile.verified_facts
        fact = profile.verified_facts[0]
        assert fact.state is VerificationState.VERIFIED
        assert fact.evidence == ("https://example.com/x",)

    def test_unsupported_items_are_never_facts(self):
        profile = profile_from_validated_items(
            "X", [_item("c", "X is the best database ever", "UNVERIFIED")]
        )
        assert profile.verified_facts == ()
        assert profile.unverified_facts

    def test_contradicted_items_are_distinguished(self):
        profile = profile_from_validated_items(
            "X", [_item("c", "X requires a GPU", "CONTRADICTED")]
        )
        assert profile.contradicted_facts
        assert profile.verified_facts == ()

    def test_criterion_evaluation_separates_fact_from_analysis(self):
        profile = profile_from_validated_items(
            "T", [_item("c", "T supports vector search", "SUPPORTED")]
        )
        finding = evaluate_criterion(profile, EvaluationCriterion(name="vector search"))
        # ANALYSIS built on a verified fact, citing its evidence.
        assert finding.satisfied is True
        assert finding.evidence == ("https://example.com/x",)

        missing = evaluate_criterion(
            profile, EvaluationCriterion(name="distributed consensus")
        )
        assert missing.satisfied is None  # unknown, never fabricated

    def test_blank_item_yields_no_fact(self):
        assert fact_from_validated_item(_item("c", "   ", "SUPPORTED")) is None

    def test_mechanism_and_dependency_facts_are_distinguishable(self):
        # A profile can carry a transferable-mechanism fact and an external-
        # dependency fact independently; criteria evaluate each on its evidence.
        profile = profile_from_validated_items(
            "X",
            [
                _item("m", "X uses a graph-based index algorithm", "SUPPORTED"),
                _item("d", "X requires an external vector service", "SUPPORTED"),
            ],
        )
        mechanism = evaluate_criterion(
            profile, EvaluationCriterion(name="graph algorithm")
        )
        dependency = evaluate_criterion(
            profile, EvaluationCriterion(name="external vector service")
        )
        assert mechanism.satisfied is True and mechanism.evidence
        assert dependency.satisfied is True and dependency.evidence
        assert mechanism.criterion != dependency.criterion

    def test_profile_is_json_safe(self):
        profile = profile_from_validated_items(
            "T", [_item("c", "T supports something", "SUPPORTED")]
        )
        json.dumps(profile.to_dict(), sort_keys=True)
