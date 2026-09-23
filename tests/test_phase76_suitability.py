"""Phase 7.6 — Suitability/feasibility analysis: evidence contract.

Investigation result: no contextual suitability mechanism existed, so the
deterministic assessment added with the Phase-7 technology-analysis layer is
used. It is contextual (requirement + explicit criteria) and never stronger than
the available evidence; unresolved unknowns and insufficient evidence are
reported honestly.
"""

from __future__ import annotations

from atlas.research.models import CitationRecord, SourceKind
from atlas.research.technology_analysis import (
    EvaluationCriterion,
    SuitabilityVerdict,
    assess_suitability,
    conclusion_from_suitability,
    profile_from_validated_items,
)
from atlas.research.validated_retrieval import ValidatedKnowledgeItem


def _item(claim_id, statement, status):
    return ValidatedKnowledgeItem(
        claim_id=claim_id,
        statement=statement,
        validation_status=status,
        claim_confidence=0.8,
        verification_score=0.9,
        citations=(
            CitationRecord(
                record_id=f"cite:{claim_id}",
                source_uri="https://example.com/x",
                source_kind=SourceKind.WEB,
            ),
        ),
    )


class TestPhase76Suitability:
    def test_suitable_when_all_required_criteria_are_evidenced(self):
        profile = profile_from_validated_items(
            "T",
            [
                _item("c1", "T supports vector search", "SUPPORTED"),
                _item("c2", "T has native compression", "SUPPORTED"),
            ],
        )
        assessment = assess_suitability(
            "serve embeddings",
            profile,
            [
                EvaluationCriterion(name="vector search"),
                EvaluationCriterion(name="compression"),
            ],
        )
        assert assessment.verdict is SuitabilityVerdict.SUITABLE
        assert assessment.satisfied
        assert assessment.evidence

    def test_not_suitable_when_a_required_criterion_is_refuted(self):
        profile = profile_from_validated_items(
            "T", [_item("c1", "T supports vector search", "CONTRADICTED")]
        )
        assessment = assess_suitability(
            "serve embeddings", profile, [EvaluationCriterion(name="vector search")]
        )
        assert assessment.verdict is SuitabilityVerdict.NOT_SUITABLE
        assert "vector search" in assessment.unmet

    def test_partial_when_some_criteria_lack_evidence(self):
        profile = profile_from_validated_items(
            "T", [_item("c1", "T supports vector search", "SUPPORTED")]
        )
        assessment = assess_suitability(
            "serve embeddings",
            profile,
            [
                EvaluationCriterion(name="vector search"),
                EvaluationCriterion(name="distributed consensus"),
            ],
        )
        assert assessment.verdict is SuitabilityVerdict.PARTIALLY_SUITABLE
        assert "distributed consensus" in assessment.unknown

    def test_insufficient_evidence_when_nothing_supports_the_criteria(self):
        profile = profile_from_validated_items("T", [])
        assessment = assess_suitability(
            "serve embeddings", profile, [EvaluationCriterion(name="vector search")]
        )
        assert assessment.verdict is SuitabilityVerdict.INSUFFICIENT_EVIDENCE

    def test_aggregate_verdict_is_conservative(self):
        sufficient = assess_suitability(
            "r",
            profile_from_validated_items(
                "A", [_item("c", "A supports vector search", "SUPPORTED")]
            ),
            [EvaluationCriterion(name="vector search")],
        )
        refuted = assess_suitability(
            "r",
            profile_from_validated_items(
                "B", [_item("c", "B supports vector search", "CONTRADICTED")]
            ),
            [EvaluationCriterion(name="vector search")],
        )
        # A refuted alternative dominates the aggregate.
        assert (
            conclusion_from_suitability("r", [sufficient, refuted])
            is SuitabilityVerdict.NOT_SUITABLE
        )
        # No evidence -> insufficient.
        assert (
            conclusion_from_suitability("r", [])
            is SuitabilityVerdict.INSUFFICIENT_EVIDENCE
        )
