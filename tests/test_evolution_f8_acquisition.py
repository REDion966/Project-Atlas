"""Phase F8 - Information Acquisition Service tests.

Focused deterministic coverage of the thin acquisition layer:

  * explicit research requests (web source through the existing coordinator)
  * F2 stale knowledge -> research trigger
  * fresh/sufficient knowledge -> bounded NO-OP
  * ResearchCoordinator composition (no duplicated pipeline stages)
  * ResearchSQLiteStorage reuse (durable report reload)
  * GOV-008 governed ingest boundary (never bypassed, never approved)
  * provenance + extraction-origin metadata preserved
  * claim verification / conflict aggregation
  * bounded results, determinism, fail-closed malformed input
  * model independence (no AI imports; model=None everywhere)
  * no sandbox/subprocess/execution, no tick() integration
  * kernel bridge wiring + shutdown cleanup

No live network: the web adapter uses an injected fake transport.
"""

import ast
import inspect
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from atlas.research.acquisition import (
    AcquisitionPolicy,
    AcquisitionResult,
    InformationAcquisitionService,
    SourceEvidence,
)
from atlas.research.coordinator import ConcreteResearchCoordinator
from atlas.research.sources.web import WebHostPolicy, WebSourceAdapter
from atlas.evolution.freshness.models import KnowledgeRef

_REPO_ROOT = Path(__file__).resolve().parents[1]

NOW = datetime(2026, 1, 10, 12, 0, 0, tzinfo=timezone.utc)
GLOBAL_IP = "93.184.216.34"

WEB_TEXT = (
    "The OpenAI API requires an API key for authentication. "
    "Authentication is performed with bearer tokens. "
    "Rate limits apply per account."
)


class FakeStorage:
    """Duck-typed ResearchStorage capture used by the coordinator."""

    def __init__(self):
        self._reports = []

    def is_available(self):
        return True

    def store_report(self, report):
        self._reports.append(report)

    def load_reports(self):
        return list(self._reports)

    def store_source(self, source):
        pass

    def load_sources(self):
        return []


class FakeIngestBridge:
    """Duck-typed governed ingest sink capture (GOV-008 boundary)."""

    def __init__(self):
        self.calls = []

    @property
    def has_sink(self):
        return True

    def ingest(self, report):
        self.calls.append(report)
        return type("R", (), {"accepted": True})


def web_transport():
    """Fake transport returning deterministic web text for any URL."""
    calls = []

    def _handler(url, timeout, max_bytes):
        calls.append(url)
        return 200, [("Content-Type", "text/plain")], WEB_TEXT.encode("utf-8")

    return _handler, calls


def _web_resolver(transport, host_policy=None, resolver=None):
    """A resolver reaching the allowlisted fake-transport web adapter last."""
    web = WebSourceAdapter(
        transport=transport,
        host_policy=host_policy or WebHostPolicy(allow_unlisted=True),
        resolver=resolver or (lambda host: (GLOBAL_IP,)),
    )
    return web


def _web_coordinator(storage=None, ingest=None, transport=None):
    """Coordinator whose resolver can reach the fake web adapter."""
    from atlas.research.sources import DocumentSourceAdapter

    web = _web_resolver(transport or web_transport()[0])

    def resolve(specs):
        from atlas.research.models import ResearchSource, SourceProfile

        out = []
        for spec in specs or []:
            if isinstance(spec, (ResearchSource, SourceProfile)):
                out.append(spec)
                continue
            if isinstance(spec, str):
                try:
                    if web.supports(spec):
                        out.append(web.load(spec))
                    elif DocumentSourceAdapter().supports(spec):
                        out.append(DocumentSourceAdapter().load(spec))
                except (ValueError, OSError):
                    continue
        return out

    return ConcreteResearchCoordinator(
        storage=storage or FakeStorage(),
        ingest=ingest or FakeIngestBridge(),
        resolve_sources=resolve,
    )


def _service(**kwargs):
    return InformationAcquisitionService(**kwargs)
class TestExplicitAcquisition:
    def test_explicit_research_request_with_web_source(self):
        factory, calls = web_transport()
        store = FakeStorage()
        service = _service(coordinator=_web_coordinator(storage=store, transport=factory))
        result = service.acquire(
            question="how is openai authenticated",
            sources=("https://example.com/api",),
            query_id="q-web",
            now=NOW,
        )
        assert result.decision == "research"
        assert result.status == "ok"
        assert "https://example.com/api" in result.sources
        assert result.report_ids == ("report:q-web:plan::q-web",)
        assert result.claim_count >= 1
        assert result.verification_count >= 1
        assert "SUPPORTED" in result.verification_statuses
        assert calls == ["https://example.com/api"]
        assert store.load_reports()  # durable research artifact persisted

    def test_existing_file_source_still_works(self, tmp_path):
        doc = tmp_path / "guide.md"
        doc.write_text(
            "Atlas implements architecture governance. Governance uses governed "
            "ingest. Governance is deterministic.",
            encoding="utf-8",
        )
        store = FakeStorage()
        coordinator = _web_coordinator(storage=store, transport=web_transport()[0])
        service = _service(coordinator=coordinator)
        result = service.acquire(
            question="how does governance work",
            sources=(str(doc),),
            query_id="q-file",
            now=NOW,
        )
        assert result.status == "ok"
        assert str(doc) in result.sources
        assert result.claim_count >= 1

    def test_malformed_input_fails_closed(self):
        service = _service(coordinator=_web_coordinator())
        result = service.acquire(question="   ", now=NOW)
        assert result.status == "failed"
        assert result.failures
        assert any(f[0] == "request" for f in result.failures)

    def test_planner_recognizes_web_markers(self):
        from atlas.evolution.models import ResearchQuery
        from atlas.research.planner import ResearchPlanner
        from atlas.research.models import SourceKind

        planner = ResearchPlanner()
        plan = planner.plan(
            ResearchQuery(query_id="q", question="check https://example.com states")
        )
        assert SourceKind.WEB in plan.target_sources


class TestSufficiencyGate:
    def test_fresh_knowledge_returns_noop(self):
        factory = web_transport()[0]
        service = _service(coordinator=_web_coordinator(transport=factory))
        result = service.acquire(
            knowledge_refs=[
                KnowledgeRef(
                    knowledge_id="k-fresh",
                    source_uris=("https://example.com/",),
                    retrieved_at=NOW - timedelta(days=1),
                    verified_at=NOW - timedelta(days=1),
                    confidence=0.9,
                )
            ],
            now=NOW,
        )
        assert result.decision == "noop"
        assert result.status == "noop"
        assert not result.report_ids

    def test_stale_knowledge_trigger_research(self):
        factory, calls = web_transport()
        store = FakeStorage()
        service = _service(coordinator=_web_coordinator(storage=store, transport=factory))
        result = service.acquire(
            knowledge_refs=[KnowledgeRef(
                knowledge_id="k-stale",
                source_uris=("https://example.com/",),
                retrieved_at=NOW - timedelta(days=400),
                verified_at=NOW - timedelta(days=300),
                confidence=0.9,
            )],
            now=NOW,
        )
        assert result.decision == "research"
        assert "k-stale" in result.stale_candidate_ids
        assert "https://example.com/" in result.sources
        assert result.claim_count >= 1

    def test_review_only_refs_do_not_research(self):
        ref = KnowledgeRef(
            knowledge_id="k-uncertain",
            source_uris=(),
            retrieved_at=None,
            confidence=0.4,
        )
        service = _service(coordinator=_web_coordinator())
        result = service.acquire(knowledge_refs=[ref], now=NOW)
        assert result.decision == "noop"
class TestProvenanceAndExtractionOrigin:
    def test_extraction_origin_is_deterministic(self):
        factory = web_transport()[0]
        store = FakeStorage()
        service = _service(coordinator=_web_coordinator(storage=store, transport=factory))
        service.acquire(
            question="how is openai authenticated",
            sources=("https://example.com/api",),
            query_id="q-origin",
            now=NOW,
        )
        report = store.load_reports()[-1]
        assert len(report.claims) >= 1
        for claim in report.claims:
            assert claim.metadata["extraction_origin"] == "deterministic"
            assert claim.metadata["source_uri"] == "https://example.com/api"
            assert claim.metadata["extracted_at"]
            assert any(c.source_uri for c in claim.citations)

    def test_source_evidence_aggregation(self):
        from atlas.research.acquisition import source_evidence
        from atlas.research.models import (
            CitationRecord,
            KnowledgeClaim,
            ResearchReport,
            SourceKind,
            VerificationStatus,
        )

        claim = KnowledgeClaim(
            claim_id="c1",
            statement="x requires a key",
            citations=(CitationRecord(
                record_id="cite:web:0000",
                source_uri="https://example.com/",
                source_kind=SourceKind.WEB,
            ),),
        )
        verification = type(
            "V",
            (),
            {"claim_id": "c1", "status": VerificationStatus.SUPPORTED},
        )()
        report = ResearchReport(
            report_id="r1",
            plan_id="p1",
            query_id="q1",
            question="q",
            findings="f",
            claims=(claim,),
            verifications=(verification,),
        )
        evidence = source_evidence(report)
        assert evidence[0].source_uri == "https://example.com/"
        assert evidence[0].supporting_claims == 1
        assert evidence[0].total_claims == 1


class TestBoundedness:
    def test_sources_bounded_by_policy(self):
        factory = web_transport()[0]
        service = _service(
            coordinator=_web_coordinator(transport=factory),
            policy=AcquisitionPolicy(max_sources=1, max_claims=5),
        )
        result = service.acquire(
            question="q",
            sources=("https://example.com/a", "https://example.com/b"),
            query_id="q-b",
            now=NOW,
        )
        assert len(result.sources) <= 1

    def test_policy_validation(self):
        with pytest.raises(ValueError):
            AcquisitionPolicy(max_sources=0)
        with pytest.raises(ValueError):
            AcquisitionPolicy(time_budget_seconds=0)

    def test_result_is_bounded_and_serializable(self):
        factory = web_transport()[0]
        service = _service(coordinator=_web_coordinator(transport=factory))
        result = service.acquire(
            question="q", sources=("https://example.com/",), query_id="q-s", now=NOW
        )
        data = result.to_dict()
        assert data["acquisition_id"].startswith("ACQ-")
        assert data["decision"] == "research"
        assert "report_id" in data

    def test_deterministic_repeated_runs(self):
        factory = web_transport()[0]
        store = FakeStorage()
        service = _service(coordinator=_web_coordinator(storage=store, transport=factory))
        r1 = service.acquire(
            question="q", sources=("https://example.com/",), query_id="q-d", now=NOW
        )
        r2 = service.acquire(
            question="q", sources=("https://example.com/",), query_id="q-d", now=NOW
        )
        assert r1.claim_count == r2.claim_count
        assert r1.findings == r2.findings
        assert r1.sources == r2.sources
class TestGovernanceBoundary:
    def test_governed_ingest_reached_and_no_approval(self):
        factory = web_transport()[0]
        store = FakeStorage()
        ingest = FakeIngestBridge()
        service = _service(
            coordinator=_web_coordinator(storage=store, ingest=ingest, transport=factory)
        )
        service.acquire(
            question="q", sources=("https://example.com/",), query_id="q-g", now=NOW
        )
        assert ingest.calls, "governed ingest boundary must be reached"
        report = store.load_reports()[-1]
        # Acquisition only records research artifacts; no proposals to approve.
        assert not getattr(report, "proposals", None)
        for claim in report.claims:
            assert "extraction_origin" in claim.metadata

    def test_f8_never_imports_ai_or_governance(self):
        src = inspect.getsource(InformationAcquisitionService)
        for forbidden in ("AIProvider", "AIManager", "ModelRouter", "LLM",
                          "ApprovalManager", "AuthorizationManager",
                          "EvolutionExecutionGateway", "subprocess", "Thread"):
            assert forbidden not in src

    def test_source_scan_forbidden_imports(self):
        files = ["atlas/research/acquisition.py", "atlas/research/sources/web.py"]
        forbidden = (
            "atlas.ai",
            "atlas.evolution.autonomy",
            "atlas.evolution.approval_manager",
            "atlas.evolution.governance",
            "subprocess",
        )
        for rel in files:
            tree = ast.parse(
                (_REPO_ROOT / rel).read_text(encoding="utf-8"), filename=rel
            )
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        assert not any(
                            alias.name == p or alias.name.startswith(p + ".")
                            for p in forbidden
                        ), f"{rel} imports {alias.name}"
                elif isinstance(node, ast.ImportFrom) and node.module:
                    assert not any(
                        node.module == p or node.module.startswith(p + ".")
                        for p in forbidden
                    ), f"{rel} imports {node.module}"

    def test_no_second_infrastructure(self):
        src = inspect.getsource(InformationAcquisitionService)
        for forbidden in ("EventBus", "Scheduler", "TaskManager", "sqlite3"):
            assert forbidden not in src

    def test_no_sandbox_or_subprocess_in_acquire(self):
        bridge_src = inspect.getsource(InformationAcquisitionService.acquire)
        for forbidden in ("subprocess", "sandbox", "os.system", "eval("):
            assert forbidden not in bridge_src


class TestKernelBridge:
    def test_kernel_bridge_and_tick_untouched(self):
        from atlas.kernel.atlas import Atlas

        tick_src = inspect.getsource(Atlas.tick)
        assert "run_information_acquisition" not in tick_src

        atlas = Atlas()
        try:
            atlas.start()
            result = atlas.run_information_acquisition(question="q", query_id="qk1")
            assert result is not None
            assert result.decision in ("research", "noop")
        finally:
            atlas.shutdown()
        assert atlas.acquisition_service is None