"""Phase 7.7 — Evidence-based research conclusions: evidence contract.

Investigation result: conclusions already preserve provenance through the
Phase-3 validated-knowledge path; the Phase-7 analysis layer adds an
evidence-bounded conclusion whose strength can never exceed its evidence.

* Conclusion strength is bounded: CONTRADICTED / SUPPORTED / PARTIAL /
  INSUFFICIENT.
* Contradictory evidence remains distinguishable; insufficient evidence yields
  INSUFFICIENT, never fabricated certainty.
* Provenance (supporting evidence refs) survives into the conclusion.
"""

from __future__ import annotations

import json

from atlas.research.models import CitationRecord, SourceKind
from atlas.research.technology_analysis import (
    ConclusionStrength,
    build_research_conclusion,
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


class TestPhase77ResearchConclusions:
    def test_supported_conclusion_carries_supporting_evidence(self):
        profile = profile_from_validated_items(
            "T", [_item("c", "T supports vector search", "SUPPORTED")]
        )
        conclusion = build_research_conclusion(
            "does T support vector search?", [profile]
        )
        assert conclusion.strength is ConclusionStrength.SUPPORTED
        assert conclusion.supporting_evidence == ("https://example.com/x",)

    def test_unverified_facts_downgrade_to_partial(self):
        profile = profile_from_validated_items(
            "T",
            [
                _item("c1", "T is fast", "SUPPORTED"),
                _item("c2", "T is cheap", "UNVERIFIED"),
            ],
        )
        conclusion = build_research_conclusion("q", [profile])
        assert conclusion.strength is ConclusionStrength.PARTIAL
        assert conclusion.uncertainties

    def test_contradicted_evidence_is_preserved_and_downgrades(self):
        profile = profile_from_validated_items(
            "T",
            [
                _item("c1", "T supports vector search", "SUPPORTED"),
                _item("c2", "T supports vector search at scale", "CONTRADICTED"),
            ],
        )
        conclusion = build_research_conclusion("q", [profile])
        assert conclusion.strength is ConclusionStrength.CONTRADICTED
        assert conclusion.contradictions

    def test_no_evidence_yields_insufficient_not_certainty(self):
        profile = profile_from_validated_items("T", [])
        conclusion = build_research_conclusion("q", [profile])
        assert conclusion.strength is ConclusionStrength.INSUFFICIENT
        assert conclusion.supporting_evidence == ()

    def test_conclusion_is_json_safe(self):
        conclusion = build_research_conclusion("q", [])
        json.dumps(conclusion.to_dict(), sort_keys=True)
