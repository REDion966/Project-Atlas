"""C6.1 — Validated Knowledge Retrieval tests.

Covers the deterministic, read-only retrieval surface over persisted research
claims/verifications/citations: SUPPORTED-only filtering, latest-verification
selection, confidence/provenance preservation, deterministic matching/ordering,
fail-closed storage behavior, no fallback, model independence, and the kernel +
CLI surfaces.
"""

from __future__ import annotations

import ast
import json
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from atlas.research.models import (
    CitationRecord,
    ClaimVerification,
    KnowledgeClaim,
    SourceKind,
    VerificationStatus,
)
from atlas.research.validated_retrieval import (
    ValidatedKnowledgeRetriever,
    ValidatedKnowledgeStatus,
    select_latest_verifications,
)

_REPO_ROOT = Path(__file__).resolve().parents[1]
_T0 = datetime(2026, 1, 1, 12, 0, 0)
_T1 = datetime(2026, 2, 1, 12, 0, 0)


def _citation(record_id: str = "cit-1", uri: str = "docs/spec.md") -> CitationRecord:
    return CitationRecord(
        record_id=record_id,
        source_uri=uri,
        source_title="Spec",
        source_kind=SourceKind.DOCUMENT,
        retrieved_at=_T0,
    )


def _claim(
    claim_id: str,
    statement: str,
    *,
    confidence: float = 0.4,
    citations: tuple[CitationRecord, ...] | None = None,
) -> KnowledgeClaim:
    return KnowledgeClaim(
        claim_id=claim_id,
        statement=statement,
        citations=citations if citations is not None else (_citation(),),
        confidence=confidence,
        extracted_at=_T0,
    )


def _verification(
    claim_id: str,
    status: VerificationStatus,
    *,
    score: float = 0.75,
    verified_at: datetime = _T1,
    verification_id: str | None = None,
) -> ClaimVerification:
    return ClaimVerification(
        verification_id=verification_id or f"verify:{claim_id}",
        claim_id=claim_id,
        status=status,
        score=score,
        evidence_summary="support",
        verified_at=verified_at,
    )


class _FakeStore:
    """Minimal duck-typed research storage (read-only usage)."""

    def __init__(self, claims, verifications, *, available=True, error=False):
        self._claims = list(claims)
        self._verifications = list(verifications)
        self._available = available
        self._error = error
        self.calls: list[str] = []

    def is_available(self) -> bool:
        self.calls.append("is_available")
        return self._available

    def load_claims(self):
        self.calls.append("load_claims")
        if self._error:
            raise RuntimeError("boom")
        return list(self._claims)

    def load_verifications(self):
        self.calls.append("load_verifications")
        return list(self._verifications)

    def store_claim(self, *_a, **_k):  # pragma: no cover - must never be called
        raise AssertionError("retrieval must not write")


def _retrieve(claims, verifications, query, **kw):
    return ValidatedKnowledgeRetriever(
        _FakeStore(claims, verifications, **kw)
    ).retrieve(query)


# ---------------------------------------------------------------------------
# A–E : status filtering
# ---------------------------------------------------------------------------


class TestStatusFiltering:
    def test_supported_is_returned(self):
        result = _retrieve(
            [_claim("c-1", "atlas memory subsystem")],
            [_verification("c-1", VerificationStatus.SUPPORTED)],
            "memory",
        )
        assert result.status is ValidatedKnowledgeStatus.OK
        assert [i.claim_id for i in result.items] == ["c-1"]
        assert result.items[0].validation_status == "SUPPORTED"

    def test_unverified_is_excluded(self):
        result = _retrieve(
            [_claim("c-1", "atlas memory subsystem")],
            [_verification("c-1", VerificationStatus.UNVERIFIED)],
            "memory",
        )
        assert result.status is ValidatedKnowledgeStatus.EMPTY
        assert result.items == ()

    def test_contradicted_is_excluded(self):
        result = _retrieve(
            [_claim("c-1", "atlas memory subsystem")],
            [_verification("c-1", VerificationStatus.CONTRADICTED)],
            "memory",
        )
        assert result.status is ValidatedKnowledgeStatus.EMPTY

    def test_ambiguous_is_excluded(self):
        result = _retrieve(
            [_claim("c-1", "atlas memory subsystem")],
            [_verification("c-1", VerificationStatus.AMBIGUOUS)],
            "memory",
        )
        assert result.status is ValidatedKnowledgeStatus.EMPTY

    def test_missing_verification_is_excluded(self):
        result = _retrieve([_claim("c-1", "atlas memory subsystem")], [], "memory")
        assert result.status is ValidatedKnowledgeStatus.EMPTY


# ---------------------------------------------------------------------------
# F : latest-verification selection
# ---------------------------------------------------------------------------


class TestLatestVerification:
    def test_latest_supported_wins(self):
        claims = [_claim("c-1", "atlas memory subsystem")]
        verifications = [
            _verification("c-1", VerificationStatus.UNVERIFIED, verified_at=_T0),
            _verification("c-1", VerificationStatus.SUPPORTED, verified_at=_T1),
        ]
        result = _retrieve(claims, verifications, "memory")
        assert [i.claim_id for i in result.items] == ["c-1"]

    def test_latest_contradicted_excludes(self):
        claims = [_claim("c-1", "atlas memory subsystem")]
        verifications = [
            _verification("c-1", VerificationStatus.SUPPORTED, verified_at=_T0),
            _verification("c-1", VerificationStatus.CONTRADICTED, verified_at=_T1),
        ]
        result = _retrieve(claims, verifications, "memory")
        assert result.status is ValidatedKnowledgeStatus.EMPTY

    def test_same_timestamp_tiebreak_by_id(self):
        claims = [_claim("c-1", "atlas memory subsystem")]
        verifications = [
            _verification(
                "c-1", VerificationStatus.SUPPORTED, verification_id="verify:b"
            ),
            _verification(
                "c-1", VerificationStatus.CONTRADICTED, verification_id="verify:c"
            ),
        ]
        latest = select_latest_verifications(verifications)
        assert latest["c-1"].status is VerificationStatus.CONTRADICTED

    def test_select_latest_is_deterministic(self):
        verifications = [
            _verification("c-1", VerificationStatus.SUPPORTED, verified_at=_T0),
            _verification("c-1", VerificationStatus.SUPPORTED, verified_at=_T1),
        ]
        a = select_latest_verifications(verifications)
        b = select_latest_verifications(list(reversed(verifications)))
        assert a["c-1"].verified_at == b["c-1"].verified_at == _T1


# ---------------------------------------------------------------------------
# G–I : confidence + provenance
# ---------------------------------------------------------------------------


class TestConfidenceAndProvenance:
    def test_claim_confidence_preserved_exactly(self):
        result = _retrieve(
            [_claim("c-1", "atlas memory subsystem", confidence=0.42)],
            [_verification("c-1", VerificationStatus.SUPPORTED, score=0.83)],
            "memory",
        )
        item = result.items[0]
        assert item.claim_confidence == 0.42
        assert item.verification_score == 0.83
        assert item.claim_confidence != item.verification_score

    def test_citations_preserved(self):
        citation = _citation("cit-x", "docs/design.md")
        result = _retrieve(
            [_claim("c-1", "atlas memory subsystem", citations=(citation,))],
            [_verification("c-1", VerificationStatus.SUPPORTED)],
            "memory",
        )
        assert result.items[0].citations == (citation,)
        assert result.items[0].citations[0].source_uri == "docs/design.md"

    def test_no_citations_is_not_fabricated(self):
        result = _retrieve(
            [_claim("c-1", "atlas memory subsystem", citations=())],
            [_verification("c-1", VerificationStatus.SUPPORTED)],
            "memory",
        )
        assert result.items[0].citations == ()


# ---------------------------------------------------------------------------
# J–L : matching
# ---------------------------------------------------------------------------


class TestMatching:
    def test_norm_alpha_containment(self):
        result = _retrieve(
            [_claim("c-1", "the conversation state subsystem")],
            [_verification("c-1", VerificationStatus.SUPPORTED)],
            "conversation state",
        )
        assert [i.claim_id for i in result.items] == ["c-1"]

    def test_significant_tokens_subset(self):
        result = _retrieve(
            [_claim("c-1", "gamma beta alpha delta")],
            [_verification("c-1", VerificationStatus.SUPPORTED)],
            "alpha beta gamma",
        )
        assert [i.claim_id for i in result.items] == ["c-1"]

    def test_non_matching_query_is_explicit_empty(self):
        result = _retrieve(
            [_claim("c-1", "atlas memory subsystem")],
            [_verification("c-1", VerificationStatus.SUPPORTED)],
            "quantum stabilizer",
        )
        assert result.status is ValidatedKnowledgeStatus.EMPTY
        assert result.items == ()

    def test_blank_query_is_empty_not_error(self):
        result = _retrieve(
            [_claim("c-1", "atlas memory subsystem")],
            [_verification("c-1", VerificationStatus.SUPPORTED)],
            "   ",
        )
        assert result.status is ValidatedKnowledgeStatus.EMPTY


# ---------------------------------------------------------------------------
# M–N : ordering + determinism
# ---------------------------------------------------------------------------


class TestOrderingAndDeterminism:
    def test_stable_ordering_by_claim_id(self):
        claims = [_claim("c-2", "atlas memory"), _claim("c-1", "atlas memory"), _claim("c-3", "atlas memory")]
        verifications = [
            _verification("c-2", VerificationStatus.SUPPORTED),
            _verification("c-1", VerificationStatus.SUPPORTED),
            _verification("c-3", VerificationStatus.SUPPORTED),
        ]
        result = _retrieve(claims, verifications, "atlas memory")
        assert [i.claim_id for i in result.items] == ["c-1", "c-2", "c-3"]

    def test_repeated_retrieval_is_identical(self):
        claims = [_claim("c-2", "atlas memory"), _claim("c-1", "atlas memory")]
        verifications = [
            _verification("c-2", VerificationStatus.SUPPORTED, score=0.8),
            _verification("c-1", VerificationStatus.SUPPORTED, score=0.6),
        ]
        first = _retrieve(claims, verifications, "atlas memory").to_dict()
        second = _retrieve(claims, verifications, "atlas memory").to_dict()
        assert first == second
        assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)


# ---------------------------------------------------------------------------
# O–Q : storage failure / no fallback
# ---------------------------------------------------------------------------


class TestStorageFailure:
    def test_unavailable_store_fails_closed(self):
        result = _retrieve(
            [_claim("c-1", "atlas memory")],
            [_verification("c-1", VerificationStatus.SUPPORTED)],
            "memory",
            available=False,
        )
        assert result.status is ValidatedKnowledgeStatus.STORE_UNAVAILABLE
        assert result.items == ()

    def test_storage_error_fails_closed(self):
        result = _retrieve([], [], "memory", error=True)
        assert result.status is ValidatedKnowledgeStatus.STORE_ERROR
        assert result.items == ()

    def test_missing_storage_fails_closed(self):
        result = ValidatedKnowledgeRetriever(None).retrieve("memory")
        assert result.status is ValidatedKnowledgeStatus.STORE_UNAVAILABLE

    def test_unavailable_does_not_fall_back(self):
        result = _retrieve(
            [_claim("c-1", "atlas memory")],
            [_verification("c-1", VerificationStatus.SUPPORTED)],
            "memory",
            available=False,
        )
        # No unvalidated in-memory knowledge is substituted as validated.
        assert result.items == ()
        assert result.status is not ValidatedKnowledgeStatus.OK

    def test_read_only_store_usage(self):
        store = _FakeStore(
            [_claim("c-1", "atlas memory")],
            [_verification("c-1", VerificationStatus.SUPPORTED)],
        )
        ValidatedKnowledgeRetriever(store).retrieve("memory")
        assert set(store.calls) <= {"is_available", "load_claims", "load_verifications"}


# ---------------------------------------------------------------------------
# R–T : boundaries / independence
# ---------------------------------------------------------------------------


class TestBoundaries:
    def test_module_has_no_forbidden_imports(self):
        source = (
            _REPO_ROOT / "atlas" / "research" / "validated_retrieval.py"
        ).read_text(encoding="utf-8")
        tree = ast.parse(source)
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(a.name for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)
        joined = " ".join(imported)
        for forbidden in (
            "knowledge_manager",
            "knowledge_store",
            "learning_engine",
            "openai",
            "anthropic",
            "ollama",
            "requests",
            "urllib",
            "httpx",
            "sqlite3",
        ):
            assert forbidden not in joined

    def test_no_learning_insight_import(self):
        source = (
            _REPO_ROOT / "atlas" / "research" / "validated_retrieval.py"
        ).read_text(encoding="utf-8")
        assert "LearningInsight" not in source


# ---------------------------------------------------------------------------
# Kernel + CLI surfaces
# ---------------------------------------------------------------------------


@pytest.fixture
def _kernel(monkeypatch, tmp_path):
    import atlas.kernel.atlas as kernel_mod
    from atlas.storage.research_storage import ResearchSQLiteStorage

    class _Tmp(ResearchSQLiteStorage):
        def __init__(self, db_path=None):  # noqa: D107
            super().__init__(db_path=tmp_path / "research.db")

    monkeypatch.setattr(kernel_mod, "ResearchSQLiteStorage", _Tmp)
    from atlas.storage.evolution_storage import SQLiteEvolutionStorage

    class _TmpEvo(SQLiteEvolutionStorage):
        def __init__(self, db_path=None):  # noqa: D107
            super().__init__(db_path=tmp_path / "evolution.db")

    monkeypatch.setattr(kernel_mod, "SQLiteEvolutionStorage", _TmpEvo)

    atlas = kernel_mod.Atlas()
    atlas.start()
    yield atlas
    atlas.shutdown()


class TestKernelAccessor:
    def test_kernel_validated_knowledge(self, _kernel):
        store = _kernel._research_storage
        store.store_claim(_claim("c-sup", "atlas memory subsystem", confidence=0.42))
        store.store_verification(
            _verification("c-sup", VerificationStatus.SUPPORTED, score=0.9)
        )
        store.store_claim(_claim("c-unv", "atlas memory subsystem"))
        store.store_verification(
            _verification("c-unv", VerificationStatus.UNVERIFIED)
        )
        store.store_claim(_claim("c-con", "atlas memory subsystem"))
        store.store_verification(
            _verification("c-con", VerificationStatus.CONTRADICTED)
        )

        result = _kernel.validated_knowledge("memory subsystem")
        assert result.status is ValidatedKnowledgeStatus.OK
        assert [i.claim_id for i in result.items] == ["c-sup"]
        assert result.items[0].claim_confidence == 0.42
        assert result.items[0].verification_score == 0.9

    def test_kernel_deterministic_and_read_only(self, _kernel):
        store = _kernel._research_storage
        store.store_claim(_claim("c-1", "atlas memory"))
        store.store_verification(
            _verification("c-1", VerificationStatus.SUPPORTED)
        )
        a = _kernel.validated_knowledge("atlas memory").to_dict()
        b = _kernel.validated_knowledge("atlas memory").to_dict()
        assert a == b


class TestCliSurface:
    def _stub_atlas(self, result):
        return SimpleNamespace(validated_knowledge=lambda q: result)

    def test_markdown_render(self):
        from atlas.cli.validated_knowledge_commands import cmd_validated_knowledge

        store = _FakeStore(
            [_claim("c-1", "atlas memory subsystem", confidence=0.42)],
            [_verification("c-1", VerificationStatus.SUPPORTED, score=0.9)],
        )
        result = ValidatedKnowledgeRetriever(store).retrieve("memory")
        out = cmd_validated_knowledge(
            self._stub_atlas(result), SimpleNamespace(query="memory", json=False)
        )
        assert "Validated Knowledge Retrieval" in out
        assert "c-1" in out
        assert "**Modification performed:** NONE" in out

    def test_json_render(self):
        from atlas.cli.validated_knowledge_commands import cmd_validated_knowledge

        store = _FakeStore(
            [_claim("c-1", "atlas memory subsystem")],
            [_verification("c-1", VerificationStatus.SUPPORTED)],
        )
        result = ValidatedKnowledgeRetriever(store).retrieve("memory")
        out = cmd_validated_knowledge(
            self._stub_atlas(result), SimpleNamespace(query="memory", json=True)
        )
        parsed = json.loads(out)
        assert parsed["status"] == "ok"
        assert parsed["items"][0]["claim_id"] == "c-1"
        assert parsed["items"][0]["validation_status"] == "SUPPORTED"

    def test_cli_no_discovery_logic(self):
        source = (
            _REPO_ROOT / "atlas" / "cli" / "validated_knowledge_commands.py"
        ).read_text(encoding="utf-8")
        assert "load_claims" not in source
        assert "research" not in source.lower().replace("validated knowledge", "")


# ---------------------------------------------------------------------------
# Command 4 — validated evidence reaching a downstream decision consumer
# ---------------------------------------------------------------------------


class TestValidatedEvidenceInfluencesDownstreamDecision:
    """What validated research knowledge actually changes downstream.

    Command 4 investigation result: the ONLY decision consumer of the
    validated-knowledge surface in the repository is the development
    capability-gap adjudicator (``assess_development_gap``). A SUPPORTED
    (validated) claim changes its verdict; a non-SUPPORTED one does not. This
    is the extent of the research -> validated knowledge -> decision link:
    the conversational response path presents the acquisition rather than
    consuming validated knowledge, and no reasoning/response consumer of the
    validated surface exists.
    """

    @staticmethod
    def _retriever(status):
        claims = [_claim("c-1", "adapter already among sources")]
        verifications = [_verification("c-1", status)]
        return ValidatedKnowledgeRetriever(_FakeStore(claims, verifications))

    def test_supported_knowledge_changes_the_gap_decision(self):
        from atlas.evolution.development_gap import (
            DevelopmentGapKind,
            assess_development_gap,
        )

        request = "adapter already among"

        without = assess_development_gap(
            request, capability_names=["research.query"], knowledge_retriever=None
        )
        with_validated = assess_development_gap(
            request,
            capability_names=["research.query"],
            knowledge_retriever=self._retriever(VerificationStatus.SUPPORTED),
        )

        assert without.kind is DevelopmentGapKind.MISSING_KNOWLEDGE
        assert with_validated.kind is DevelopmentGapKind.MISSING_CAPABILITY

    def test_unvalidated_knowledge_does_not_change_the_decision(self):
        from atlas.evolution.development_gap import (
            DevelopmentGapKind,
            assess_development_gap,
        )

        gap = assess_development_gap(
            "adapter already among",
            capability_names=["research.query"],
            knowledge_retriever=self._retriever(VerificationStatus.CONTRADICTED),
        )
        assert gap.kind is DevelopmentGapKind.MISSING_KNOWLEDGE
