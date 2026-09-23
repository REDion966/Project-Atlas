"""Phase 7 integration — evidence-driven research & technology analysis.

Demonstrates the Phase 7 completion criterion with one bounded, deterministic,
model-free path:

    research goal → research questions (ResearchPlan)
      → authorized source discovery/selection
      → information gathering (extraction + verification)
      → persistence with provenance
      → validated knowledge retrieval
      → structured technology analysis
      → criteria-driven comparison
      → contextual suitability
      → evidence-based conclusion
      → capability/development decision (gap adjudication)

  ... with no external AI model.

Negative paths (fail-closed / preserve uncertainty): an unauthorized source is
rejected; unverified claims are not validated; insufficient evidence yields an
INSUFFICIENT conclusion and does not justify a capability conclusion; and
research never activates a capability or modifies production.
"""

from __future__ import annotations

import pytest

from atlas.evolution.development_gap import (
    DevelopmentGapKind,
    assess_development_gap,
)
from atlas.evolution.models import ResearchQuery
from atlas.reasoning.execution.registry import CapabilityRegistry
from atlas.research.extractor import KnowledgeExtractor
from atlas.research.models import (
    CitationRecord,
    ClaimVerification,
    KnowledgeClaim,
    SourceKind,
    SourceProfile,
    VerificationStatus,
)
from atlas.research.planner import ResearchPlanner
from atlas.research.repository_map import RepositoryMapBuilder
from atlas.research.source_selection import select_repository_sources
from atlas.research.sources.web import WebSourceAdapter
from atlas.research.technology_analysis import (
    ConclusionStrength,
    EvaluationCriterion,
    SuitabilityVerdict,
    assess_suitability,
    build_research_conclusion,
    compare_technologies,
    profile_from_validated_items,
)
from atlas.research.validated_retrieval import (
    ValidatedKnowledgeRetriever,
    ValidatedKnowledgeStatus,
)
from atlas.storage.research_storage import ResearchSQLiteStorage

_CRITERIA = [
    EvaluationCriterion(name="vector search"),
    EvaluationCriterion(name="compression"),
]


def _store_validated(storage, claim_id: str, statement: str, uri: str):
    storage.store_claim(
        KnowledgeClaim(
            claim_id=claim_id,
            statement=statement,
            citations=(
                CitationRecord(
                    record_id=f"cite:{claim_id}",
                    source_uri=uri,
                    source_kind=SourceKind.WEB,
                ),
            ),
            confidence=0.8,
        )
    )
    storage.store_verification(
        ClaimVerification(
            verification_id=f"ver:{claim_id}",
            claim_id=claim_id,
            status=VerificationStatus.SUPPORTED,
            score=0.9,
        )
    )


class TestPhase7Integration:
    def test_research_goal_to_development_decision(self, tmp_path):
        # 1-2. Research goal → research questions + target sources.
        plan = ResearchPlanner().plan(
            ResearchQuery(
                query_id="q-int",
                question="compare vector database technologies for embeddings",
            )
        )
        assert plan.sub_queries
        assert plan.target_sources

        # 3. Authorized source discovery: local selection + deny-by-default web.
        root = tmp_path / "repo"
        (root / "atlas").mkdir(parents=True)
        (root / "atlas" / "__init__.py").write_text("", encoding="utf-8")
        (root / "atlas" / "vector_store.py").write_text("x = 1\n", encoding="utf-8")
        repo_map = RepositoryMapBuilder(root).build()
        selected = select_repository_sources("vector store", repo_map)
        assert selected and all(s.startswith("code://") for s in selected)
        assert WebSourceAdapter().supports("http://example.com/x") is False

        # 4. Gathering: a source normalizes into claims with provenance.
        profile = SourceProfile(
            uri="https://example.com/vector",
            kind=SourceKind.WEB,
            text="Alpha supports vector search. Alpha has native compression.",
        )
        claims = KnowledgeExtractor().extract(profile)
        assert claims and claims[0].citations[0].source_kind is SourceKind.WEB

        # 5-6. Persistence with provenance + validated retrieval.
        storage = ResearchSQLiteStorage(db_path=tmp_path / "r.db")
        storage.initialize()
        try:
            _store_validated(
                storage, "alpha-vs", "Alpha supports vector search",
                "https://example.com/vector",
            )
            _store_validated(
                storage, "alpha-comp", "Alpha has native compression",
                "https://example.com/vector",
            )
            _store_validated(
                storage, "beta-vs", "Beta supports vector search",
                "https://example.com/beta",
            )
            retriever = ValidatedKnowledgeRetriever(storage)

            alpha_items = retriever.retrieve("Alpha").items
            beta_items = retriever.retrieve("Beta").items
            assert alpha_items and beta_items
            assert alpha_items[0].citations  # provenance survives

            # 7-10. Structured analysis → comparison → suitability → conclusion.
            profiles = [
                profile_from_validated_items("Alpha", alpha_items),
                profile_from_validated_items("Beta", beta_items),
            ]
            comparison = compare_technologies(profiles, _CRITERIA)
            assert comparison.alternatives == ("Alpha", "Beta")
            assert ("Beta", "compression") in comparison.uncertainties

            suitability = assess_suitability("embeddings backend", profiles[0], _CRITERIA)
            assert suitability.verdict is SuitabilityVerdict.SUITABLE

            conclusion = build_research_conclusion(plan.question, profiles)
            assert conclusion.strength is ConclusionStrength.SUPPORTED
            assert conclusion.supporting_evidence

            # 11. Research feeds the capability/development decision (advisory).
            gap = assess_development_gap(
                "vector search",
                capability_names=["research.query"],
                knowledge_retriever=retriever,
            )
            assert gap.kind is DevelopmentGapKind.MISSING_CAPABILITY
        finally:
            storage.close()

        # Research never activates a capability or modifies production.
        registry = CapabilityRegistry()
        assert registry.registered_names == []

    def test_negative_paths_fail_closed_and_preserve_uncertainty(self, tmp_path):
        # Unauthorized source: deny-by-default web refuses before any I/O.
        with pytest.raises(ValueError):
            WebSourceAdapter().load("http://example.com/x")

        storage = ResearchSQLiteStorage(db_path=tmp_path / "r.db")
        storage.initialize()
        try:
            # Unverified claim -> not validated knowledge.
            storage.store_claim(
                KnowledgeClaim(
                    claim_id="raw",
                    statement="raw statement about alpha",
                    confidence=0.3,
                )
            )
            retriever = ValidatedKnowledgeRetriever(storage)
            assert (
                retriever.retrieve("raw statement about alpha").status
                is ValidatedKnowledgeStatus.EMPTY
            )

            # Insufficient evidence -> explicit uncertainty, not a capability conclusion.
            empty_profile = profile_from_validated_items("Gamma", ())
            suitability = assess_suitability("requirement", empty_profile, _CRITERIA)
            assert suitability.verdict is SuitabilityVerdict.INSUFFICIENT_EVIDENCE

            conclusion = build_research_conclusion("q", [empty_profile])
            assert conclusion.strength is ConclusionStrength.INSUFFICIENT

            gap = assess_development_gap(
                "raw statement about alpha",
                capability_names=["research.query"],
                knowledge_retriever=retriever,
            )
            assert gap.kind is DevelopmentGapKind.MISSING_KNOWLEDGE
        finally:
            storage.close()
