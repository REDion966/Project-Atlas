"""Phase 7.9 — Model-independent research: evidence contract.

Investigation result: the research/technology-analysis path is deterministic and
requires no external AI model. No production change beyond the Phase-7 analysis
layer was needed.

Verification: (a) static — no provider SDK / network-client imports on the
research core, the analysis layer, or the planner/verifier/extractor (the
governed web source adapter is an information source, not an AI dependency);
(b) runtime — the research read path and the analysis layer work with no AI.
"""

from __future__ import annotations

import ast
from pathlib import Path

from atlas.research.models import (
    CitationRecord,
    ClaimVerification,
    KnowledgeClaim,
    SourceKind,
    VerificationStatus,
)
from atlas.research.technology_analysis import (
    ConclusionStrength,
    EvaluationCriterion,
    assess_suitability,
    build_research_conclusion,
    compare_technologies,
    profile_from_validated_items,
)
from atlas.research.validated_retrieval import ValidatedKnowledgeRetriever
from atlas.storage.research_storage import ResearchSQLiteStorage

_REPO_ROOT = Path(__file__).resolve().parents[1]

_PHASE7_MODULES = (
    "atlas/research/planner.py",
    "atlas/research/extractor.py",
    "atlas/research/verifier.py",
    "atlas/research/coordinator.py",
    "atlas/research/source_selection.py",
    "atlas/research/validated_retrieval.py",
    "atlas/research/evidence_summary.py",
    "atlas/research/technology_analysis.py",
    "atlas/research/models.py",
)


class TestPhase79ModelIndependence:
    def test_research_core_has_no_provider_or_network_imports(self):
        banned = ("openai", "anthropic", "ollama", "requests", "httpx")
        for relative in _PHASE7_MODULES:
            tree = ast.parse((_REPO_ROOT / relative).read_text(encoding="utf-8"))
            imported: set[str] = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imported.update(alias.name for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imported.add(node.module)
            for module in imported:
                assert not module.startswith(banned), f"{relative} imports {module}"

    def test_analysis_layer_is_model_free_and_works_end_to_end(self, tmp_path):
        storage = ResearchSQLiteStorage(db_path=tmp_path / "r.db")
        storage.initialize()
        try:
            storage.store_claim(
                KnowledgeClaim(
                    claim_id="c1",
                    statement="Alpha supports vector search",
                    citations=(
                        CitationRecord(
                            record_id="cite:c1",
                            source_uri="https://example.com/a",
                            source_kind=SourceKind.WEB,
                        ),
                    ),
                )
            )
            storage.store_verification(
                ClaimVerification(
                    verification_id="v1",
                    claim_id="c1",
                    status=VerificationStatus.SUPPORTED,
                    score=0.9,
                )
            )
            result = ValidatedKnowledgeRetriever(storage).retrieve("vector search")
            assert result.items

            profiles = [
                profile_from_validated_items("Alpha", result.items),
                profile_from_validated_items("Beta", ()),
            ]
            criteria = [EvaluationCriterion(name="vector search")]

            comparison = compare_technologies(profiles, criteria)
            assessment = assess_suitability("serve embeddings", profiles[0], criteria)
            conclusion = build_research_conclusion(
                "which technology supports vector search?", profiles
            )

            assert comparison.alternatives == ("Alpha", "Beta")
            assert assessment.verdict.value == "suitable"
            assert conclusion.strength is ConclusionStrength.SUPPORTED
        finally:
            storage.close()
