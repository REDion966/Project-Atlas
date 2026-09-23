"""Phase 3.4 — External/world knowledge: evidence contract.

Investigation result (evidence, not aspiration): Atlas already owns a governed
external-knowledge acquisition → validation → persistence → retrieval chain, so
no new web/RAG/vector infrastructure was introduced.

* Acquisition — ``atlas/research/sources/web.py::WebSourceAdapter``: bounded,
  fail-closed HTTP(S) retrieval with a **deny-by-default** host allowlist
  (config ``research.web_allowed_hosts``), SSRF protection (loopback/private/
  link-local/metadata ranges rejected, hostnames validated after an injectable
  DNS resolution), redirect re-validation, size/time bounds, content-type
  allowlist, and credential stripping. Document/workspace/codebase adapters
  provide the same ``SourceProfile`` surface for local sources.
* Pipeline — ``atlas/research/coordinator.py::ConcreteResearchCoordinator``:
  plan → source resolution → ``KnowledgeExtractor`` → ``ClaimVerifier`` →
  ``ResearchReport`` → persistence + governed ingest.
* Provenance — ``ResearchSource`` / ``SourceProfile`` / ``CitationRecord``
  (``source_uri``, ``source_kind``, ``title``, ``section``, ``retrieved_at``,
  ``metadata``); ``SourceKind.WEB`` labels external origin.
* Validation — ``ClaimVerifier`` → ``ClaimVerification`` (status
  UNVERIFIED/SUPPORTED/CONTRADICTED/AMBIGUOUS + score + evidence summary).
* Persistence — ``ResearchSQLiteStorage`` (``research_*`` tables).
* Retrieval — ``ValidatedKnowledgeRetriever`` returns only SUPPORTED claims,
  deterministically, preserving provenance and failing closed.
* Governance — durable ingestion into Atlas knowledge is only via the governed
  ``ResearchIngestBridge`` (GOV-008, KNOWLEDGE scope, fail-closed without a
  sink); raw research is never silently promoted to trusted knowledge.

These tests pin: authorized acquisition with provenance, fail-closed
authorization/SSRF, deterministic extraction+verification with provenance, the
raw→validated boundary, process-boundary persistence+retrieval, separation from
self-knowledge, and model independence.
"""

from __future__ import annotations

import ast
import os
import subprocess
import sys
from pathlib import Path

import pytest

from atlas.research.extractor import KnowledgeExtractor
from atlas.research.models import (
    CitationRecord,
    ClaimVerification,
    KnowledgeClaim,
    SourceKind,
    SourceProfile,
    VerificationStatus,
)
from atlas.research.sources.web import (
    WebSourceAdapter,
    web_host_policy_from_hosts,
)
from atlas.research.validated_retrieval import (
    ValidatedKnowledgeRetriever,
    ValidatedKnowledgeStatus,
)
from atlas.research.verifier import ClaimVerifier
from atlas.storage.research_storage import ResearchSQLiteStorage

_REPO_ROOT = Path(__file__).resolve().parents[1]
_GLOBAL_IP = "93.184.216.34"  # global, unblocked IPv4


class _FakeTransport:
    """Deterministic HTTP transport double (never touches the network)."""

    def __init__(self, status=200, content_type="text/plain", body=b"External text."):
        self._status = status
        self._content_type = content_type
        self._body = body
        self.calls: list[str] = []

    def get(self, url, timeout, max_bytes):
        self.calls.append(url)
        headers = [("content-type", self._content_type)] if self._content_type else []
        return self._status, headers, self._body


def _authorized_adapter(transport=None) -> WebSourceAdapter:
    return WebSourceAdapter(
        transport=transport or _FakeTransport(),
        host_policy=web_host_policy_from_hosts(["example.com"]),
        resolver=lambda _host: (_GLOBAL_IP,),
    )


class TestPhase34ExternalKnowledgeEvidence:
    def test_authorized_acquisition_records_provenance(self):
        transport = _FakeTransport(body=b"Atlas external fact about vector databases.")
        profile = _authorized_adapter(transport).load("http://example.com/page")

        assert profile.kind is SourceKind.WEB
        assert profile.text == "Atlas external fact about vector databases."
        assert profile.metadata["host"] == "example.com"
        assert profile.metadata["http_status"] == 200
        assert profile.metadata["final_url"]
        assert profile.metadata["retrieved_at"]
        assert transport.calls == ["http://example.com/page"]

    def test_unauthorized_external_access_fails_closed(self):
        # Deny-by-default: with no allowlist, no host is fetchable.
        default = WebSourceAdapter(
            transport=_FakeTransport(), resolver=lambda _h: (_GLOBAL_IP,)
        )
        assert default.supports("http://example.com/page") is False
        with pytest.raises(ValueError):
            default.load("http://example.com/page")

        # SSRF: a listed loopback/private host is still rejected.
        loopback = WebSourceAdapter(
            transport=_FakeTransport(),
            host_policy=web_host_policy_from_hosts(["127.0.0.1"]),
            resolver=lambda _h: ("127.0.0.1",),
        )
        assert loopback.supports("http://127.0.0.1/") is False
        with pytest.raises(ValueError):
            loopback.load("http://127.0.0.1/")

        # An unresolvable host fails closed (no fetch attempted).
        unresolvable = WebSourceAdapter(
            transport=_FakeTransport(),
            host_policy=web_host_policy_from_hosts(["nope.example"]),
            resolver=lambda _h: (),
        )
        with pytest.raises(ValueError):
            unresolvable.load("http://nope.example/")

    def test_external_text_yields_provenanced_claims_and_verifications(self):
        profile = SourceProfile(
            uri="https://example.com/doc",
            kind=SourceKind.WEB,
            text=(
                "Atlas external fact about vector databases. "
                "Atlas records claims with provenance."
            ),
            title="Example Doc",
        )

        extractor = KnowledgeExtractor()
        claims = extractor.extract(profile)
        assert claims
        assert extractor._last_extraction_origin == "deterministic"  # no model
        first = claims[0]
        assert first.statement
        assert first.citations
        assert first.citations[0].source_kind is SourceKind.WEB
        assert first.citations[0].source_uri == "https://example.com/doc"
        assert first.metadata["source_uri"] == "https://example.com/doc"

        verifications = ClaimVerifier().verify(claims, [profile])
        assert len(verifications) == len(claims)
        assert all(isinstance(v.status, VerificationStatus) for v in verifications)
        assert all(v.claim_id for v in verifications)

    def test_only_supported_claims_become_retrievable_knowledge(self, tmp_path):
        storage = ResearchSQLiteStorage(db_path=tmp_path / "research.db")
        storage.initialize()
        try:
            storage.store_claim(
                KnowledgeClaim(
                    claim_id="c1",
                    statement="External fact about vector databases",
                    citations=(
                        CitationRecord(
                            record_id="cite:c1",
                            source_uri="https://example.com/doc",
                            source_kind=SourceKind.WEB,
                        ),
                    ),
                    confidence=0.8,
                )
            )
            storage.store_verification(
                ClaimVerification(
                    verification_id="v1",
                    claim_id="c1",
                    status=VerificationStatus.UNVERIFIED,
                    score=0.0,
                )
            )
            retriever = ValidatedKnowledgeRetriever(storage)
            # Raw (unverified) external information is NOT trusted knowledge.
            assert (
                retriever.retrieve("vector databases").status
                is ValidatedKnowledgeStatus.EMPTY
            )

            storage.store_verification(
                ClaimVerification(
                    verification_id="v2",
                    claim_id="c1",
                    status=VerificationStatus.SUPPORTED,
                    score=0.9,
                )
            )
            result = retriever.retrieve("vector databases")
            assert result.status is ValidatedKnowledgeStatus.OK
            item = result.items[0]
            assert item.validation_status == "SUPPORTED"
            assert item.citations[0].source_uri == "https://example.com/doc"
            assert item.citations[0].source_kind.name == "WEB"
        finally:
            storage.close()

        # Fail closed when the knowledge store is unavailable.
        unavailable = ValidatedKnowledgeRetriever(None).retrieve("anything")
        assert unavailable.status is ValidatedKnowledgeStatus.STORE_UNAVAILABLE
        assert unavailable.items == ()

    def test_external_knowledge_survives_process_boundary(self, tmp_path):
        driver = tmp_path / "driver.py"
        driver.write_text(_DRIVER, encoding="utf-8")
        db = tmp_path / "research.db"
        env = dict(os.environ, PYTHONPATH=str(_REPO_ROOT))

        proc_a = subprocess.run(
            [sys.executable, str(driver), "write", str(db)],
            cwd=str(tmp_path),
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert proc_a.returncode == 0, proc_a.stderr
        assert "WROTE" in proc_a.stdout

        # A fresh interpreter retrieves the validated knowledge with provenance.
        proc_b = subprocess.run(
            [sys.executable, str(driver), "read", str(db)],
            cwd=str(tmp_path),
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert proc_b.returncode == 0, proc_b.stderr
        assert "READ:SUPPORTED" in proc_b.stdout

    def test_external_knowledge_and_self_knowledge_are_separate_domains(self):
        from atlas.self_knowledge.architecture_model import ArchitectureSourceKind

        self_knowledge_kinds = {kind.value for kind in ArchitectureSourceKind}
        assert self_knowledge_kinds == {
            "component_registry",
            "capability_model",
            "repository_map",
        }
        assert "web" not in self_knowledge_kinds

        # External knowledge is labelled by its own source-kind domain.
        assert {"WEB", "DOCUMENT", "CODEBASE", "WORKSPACE"} <= {
            kind.name for kind in SourceKind
        }

    def test_external_knowledge_core_has_no_model_or_network_imports(self):
        banned = ("openai", "anthropic", "ollama", "requests", "httpx")
        for relative in (
            "atlas/research/coordinator.py",
            "atlas/research/extractor.py",
            "atlas/research/verifier.py",
            "atlas/research/planner.py",
            "atlas/research/source_selection.py",
            "atlas/research/validated_retrieval.py",
        ):
            tree = ast.parse((_REPO_ROOT / relative).read_text(encoding="utf-8"))
            imported: set[str] = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imported.update(alias.name for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imported.add(node.module)
            for module in imported:
                assert not module.startswith(banned), f"{relative} imports {module}"


#: Two-process driver: ``write`` persists a validated external claim; ``read``
#: (a fresh interpreter) retrieves it through the Atlas-owned retriever.
_DRIVER = """
import sys
from pathlib import Path

from atlas.research.models import (
    CitationRecord,
    ClaimVerification,
    KnowledgeClaim,
    SourceKind,
    VerificationStatus,
)
from atlas.research.validated_retrieval import ValidatedKnowledgeRetriever
from atlas.storage.research_storage import ResearchSQLiteStorage

mode = sys.argv[1]
storage = ResearchSQLiteStorage(db_path=Path(sys.argv[2]))
storage.initialize()
try:
    if mode == "write":
        storage.store_claim(
            KnowledgeClaim(
                claim_id="c-ext-1",
                statement="External fact about vector databases and embeddings",
                citations=(
                    CitationRecord(
                        record_id="cite:web:1",
                        source_uri="https://example.com/doc",
                        source_title="Example Doc",
                        source_kind=SourceKind.WEB,
                    ),
                ),
                confidence=0.8,
            )
        )
        storage.store_verification(
            ClaimVerification(
                verification_id="v-ext-1",
                claim_id="c-ext-1",
                status=VerificationStatus.SUPPORTED,
                score=0.9,
                evidence_summary="supported by example.com",
            )
        )
        print("WROTE")
    else:
        result = ValidatedKnowledgeRetriever(storage).retrieve("vector databases")
        assert result.status.value == "ok", result.status
        assert len(result.items) == 1, result.items
        item = result.items[0]
        assert item.claim_id == "c-ext-1"
        assert item.validation_status == "SUPPORTED"
        assert item.citations[0].source_uri == "https://example.com/doc"
        assert item.citations[0].source_kind.name == "WEB"
        print("READ:" + item.validation_status)
finally:
    storage.close()
"""
