"""Phase 7.5 — Comparative analysis: evidence contract.

Investigation result: no comparison framework existed, so the deterministic,
criteria-driven comparison added with the Phase-7 technology-analysis layer is
used. It compares alternatives against EXPLICIT criteria (no opaque overall
score, no "best technology" verdict without criteria and evidence).
"""

from __future__ import annotations

from atlas.research.models import CitationRecord, SourceKind
from atlas.research.technology_analysis import (
    EvaluationCriterion,
    compare_technologies,
    profile_from_validated_items,
)
from atlas.research.validated_retrieval import ValidatedKnowledgeItem


def _item(claim_id, statement, status, uri="https://example.com/x"):
    return ValidatedKnowledgeItem(
        claim_id=claim_id,
        statement=statement,
        validation_status=status,
        claim_confidence=0.8,
        verification_score=0.9,
        citations=(
            CitationRecord(
                record_id=f"cite:{claim_id}",
                source_uri=uri,
                source_kind=SourceKind.WEB,
            ),
        ),
    )


class TestPhase75ComparativeAnalysis:
    def test_comparison_reports_satisfied_unmet_and_unknown(self):
        alpha = profile_from_validated_items(
            "Alpha", [_item("a1", "Alpha supports vector search", "SUPPORTED")]
        )
        beta = profile_from_validated_items(
            "Beta", [_item("b1", "Beta requires gpu acceleration", "SUPPORTED")]
        )
        gamma = profile_from_validated_items(
            "Gamma", [_item("g1", "Gamma supports vector search", "CONTRADICTED")]
        )
        criteria = [
            EvaluationCriterion(name="vector search"),
            EvaluationCriterion(name="gpu acceleration"),
        ]

        comparison = compare_technologies([alpha, beta, gamma], criteria)

        assert comparison.alternatives == ("Alpha", "Beta", "Gamma")
        # A refuted required criterion is an unmet requirement.
        assert ("Gamma", "vector search") in comparison.unmet_requirements
        # Missing evidence is an uncertainty, not a failure.
        assert ("Alpha", "gpu acceleration") in comparison.uncertainties
        # Evidence is preserved on each finding.
        alpha_finding = next(
            f
            for f in comparison.findings_for("Alpha")
            if f.criterion == "vector search"
        )
        assert alpha_finding.satisfied is True
        assert alpha_finding.evidence == ("https://example.com/x",)

    def test_comparison_has_no_opaque_overall_score_or_ranking(self):
        alpha = profile_from_validated_items(
            "Alpha", [_item("a1", "Alpha supports vector search", "SUPPORTED")]
        )
        comparison = compare_technologies(
            [alpha], [EvaluationCriterion(name="vector search")]
        )
        for banned in ("score", "ranking", "best", "winner"):
            assert not hasattr(comparison, banned)

    def test_comparison_is_deterministic_and_json_safe(self):
        import json

        alpha = profile_from_validated_items(
            "Alpha", [_item("a1", "Alpha supports vector search", "SUPPORTED")]
        )
        beta = profile_from_validated_items(
            "Beta", [_item("b1", "Beta supports compression", "SUPPORTED")]
        )
        criteria = [
            EvaluationCriterion(name="vector search"),
            EvaluationCriterion(name="compression"),
        ]
        first = compare_technologies([alpha, beta], criteria).to_dict()
        second = compare_technologies([alpha, beta], criteria).to_dict()
        assert first == second
        json.dumps(first, sort_keys=True)
