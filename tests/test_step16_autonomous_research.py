"""Step 16 — autonomous research.

Measured baseline (real Atlas/kernel, before any change): the authorized
acquisition machinery already existed and worked — the D2 governed boundary
returned ``no_authorized_source`` with the denied hosts recorded and nothing
fetched, and the F8 service produced ``ok`` with claims, sources,
``source_evidence`` and report ids — but there was NO seam connecting a Step 15
``KnowledgeNeed`` to research, and NO structured research result. The existing
statuses also could not distinguish "unavailable source" from "insufficient
result" from "failed/blocked" in one place tied to the need.

Step 16 adds ONE bounded, deterministic, model-free orchestration over that
existing machinery. It enables no source, unlocks no network access, persists
and promotes nothing, consults no model, and never claims knowledge research did
not establish.
"""

from __future__ import annotations

import json

import pytest

from atlas.research.external_acquisition import (
    ExternalAcquisitionResult,
    ExternalAcquisitionStatus,
    ExternalKnowledgeAcquirer,
)
from atlas.research.knowledge_need import classify_knowledge_need
from atlas.research.research_outcome import (
    ResearchMechanism,
    ResearchOrchestrator,
    ResearchStatus,
    map_acquisition_result,
)
from atlas.research.sources.web import DENY_ALL_HOSTS, web_host_policy_from_hosts

GLOBAL_IP = "93.184.216.34"
_URL = "https://example.com/zorblax"
_OTHER = "https://other.example/x"
_TEXT = "The Zorblax protocol release is 7.3. Atlas preserves provenance."
_ALLOW = web_host_policy_from_hosts(["example.com"])


# ---------------------------------------------------------------------------
# Stubs
# ---------------------------------------------------------------------------


class _Acquisition:
    def __init__(
        self,
        *,
        status="ok",
        claim_count=2,
        sources=(_URL,),
        failures=(),
        report_ids=("report:1",),
    ):
        self.status = status
        self.claim_count = claim_count
        self.sources = tuple(sources)
        self.failures = tuple(failures)
        self.report_ids = tuple(report_ids)
        self.acquisition_id = "ACQ-1"
        self.decision = "research"
        self.findings = "verification summary: PLAUSIBLE=2"
        self.confidence = 0.75
        self.verification_count = 2
        self.verification_statuses = ("SUPPORTED",)
        self.source_evidence = (
            type(
                "E",
                (),
                {
                    "source_uri": _URL,
                    "total_claims": claim_count,
                    "supporting_claims": claim_count,
                    "contradicted_claims": 0,
                },
            )(),
        )


def _external(status, **kwargs):
    return ExternalAcquisitionResult(
        status=ExternalAcquisitionStatus(status),
        objective=kwargs.pop("objective", "Q"),
        **kwargs,
    )


class _StubAcquirer:
    def __init__(self, result=None, raise_error=False):
        self.result = result
        self.raise_error = raise_error
        self.calls: list[tuple[str, tuple[str, ...], str]] = []

    def acquire(self, objective, *, candidate_urls=(), knowledge_query=""):
        self.calls.append((objective, tuple(candidate_urls), knowledge_query))
        if self.raise_error:
            raise RuntimeError("boundary exploded")
        return self.result


def _need(**kwargs):
    base = dict(objective="What is the current release of the Zorblax protocol?")
    base.update(kwargs)
    return classify_knowledge_need(**base)


_MISSING_NEED = _need(sufficiency="unknown", acquisition_status="no_authorized_source")
_SATISFIED_NEED = _need(sufficiency="sufficient")


# ---------------------------------------------------------------------------
# 1. Deterministic outcome mapping
# ---------------------------------------------------------------------------


class TestOutcomeMapping:
    def test_existing_knowledge_is_not_needed(self):
        outcome = map_acquisition_result(
            _MISSING_NEED, _external("existing_knowledge", message="covered")
        )
        assert outcome.status is ResearchStatus.NOT_NEEDED
        assert outcome.mechanism == ResearchMechanism.EXISTING_VALIDATED_KNOWLEDGE.value
        assert outcome.established is False

    def test_no_authorized_source_preserves_denials(self):
        outcome = map_acquisition_result(
            _MISSING_NEED,
            _external(
                "no_authorized_source",
                message="No authorized external source is available (deny-by-default).",
                denied_sources=(_URL, _OTHER),
            ),
        )
        assert outcome.status is ResearchStatus.NO_AUTHORIZED_SOURCE
        assert outcome.denied_sources == (_URL, _OTHER)
        assert outcome.established is False
        assert outcome.actionable is True

    def test_failed_maps_to_failed(self):
        outcome = map_acquisition_result(
            _MISSING_NEED, _external("failed", message="Acquisition failed closed.")
        )
        assert outcome.status is ResearchStatus.FAILED
        assert outcome.established is False

    def test_researched_preserves_source_identity_and_evidence(self):
        outcome = map_acquisition_result(
            _MISSING_NEED,
            _external(
                "acquired",
                authorized_sources=(_URL,),
                acquisition=_Acquisition(),
            ),
        )
        assert outcome.status is ResearchStatus.RESEARCHED
        assert outcome.established is True
        assert outcome.claim_count == 2
        assert outcome.sources == (_URL,)
        assert outcome.source_evidence[0].source_uri == _URL
        assert outcome.source_evidence[0].supporting_claims == 2
        assert outcome.report_ids == ("report:1",)
        assert outcome.findings
        assert outcome.acquisition_id == "ACQ-1"
        assert outcome.verification_statuses == ("SUPPORTED",)

    def test_acquired_without_claims_is_insufficient(self):
        outcome = map_acquisition_result(
            _MISSING_NEED,
            _external(
                "acquired",
                authorized_sources=(_URL,),
                acquisition=_Acquisition(status="ok", claim_count=0),
            ),
        )
        assert outcome.status is ResearchStatus.INSUFFICIENT
        assert outcome.established is False
        # Source identity is still preserved for the later provenance step.
        assert outcome.sources == (_URL,)

    def test_unrecognised_result_fails_closed(self):
        unknown = type("R", (), {"status": "weird", "message": "", "denied_sources": ()})()
        outcome = map_acquisition_result(_MISSING_NEED, unknown)
        assert outcome.status is ResearchStatus.UNKNOWN
        assert outcome.established is False

    def test_reached_but_empty_source_is_insufficient_not_failed(self):
        # The EXISTING boundary attaches the inner result when the source was
        # reached; that is "insufficient", not a failed path.
        outcome = map_acquisition_result(
            _MISSING_NEED,
            _external(
                "failed",
                message="External acquisition produced no usable evidence (fail-closed).",
                authorized_sources=(_URL,),
                acquisition=_Acquisition(status="noop", claim_count=0, sources=()),
            ),
        )
        assert outcome.status is ResearchStatus.INSUFFICIENT
        assert outcome.established is False
        assert outcome.mechanism == (
            ResearchMechanism.GOVERNED_EXTERNAL_ACQUISITION.value
        )

    def test_deterministic_and_serializable(self):
        args = (
            _MISSING_NEED,
            _external("acquired", authorized_sources=(_URL,), acquisition=_Acquisition()),
        )
        first = map_acquisition_result(*args)
        second = map_acquisition_result(*args)
        assert first == second
        json.dumps(first.to_dict())

    def test_a_failed_outcome_never_claims_knowledge(self):
        for status in ("no_authorized_source", "failed"):
            outcome = map_acquisition_result(_MISSING_NEED, _external(status))
            assert outcome.established is False
            assert outcome.claim_count == 0
            assert outcome.sources == ()


# ---------------------------------------------------------------------------
# 2. Actionability and orchestration (deterministic, stub boundary)
# ---------------------------------------------------------------------------


class TestOrchestration:
    def test_satisfied_need_is_not_researched(self):
        acquirer = _StubAcquirer(_external("acquired", acquisition=_Acquisition()))
        outcome = ResearchOrchestrator(external_acquirer=acquirer).research(
            _SATISFIED_NEED
        )
        assert outcome.status is ResearchStatus.NOT_NEEDED
        assert outcome.actionable is False
        assert acquirer.calls == []

    def test_ambiguous_and_unsupported_are_not_researched(self):
        acquirer = _StubAcquirer(_external("acquired", acquisition=_Acquisition()))
        orchestrator = ResearchOrchestrator(external_acquirer=acquirer)
        for need in (
            _need(sufficiency="unknown", ambiguous=True),
            _need(capability="open_conversation", capability_state="unavailable"),
        ):
            outcome = orchestrator.research(need)
            assert outcome.status is ResearchStatus.NOT_NEEDED, need.kind
        assert acquirer.calls == []

    def test_contradictory_need_is_still_actionable(self):
        # A contradiction is a genuine need: extra authorized research is the
        # legitimate way to resolve it.
        acquirer = _StubAcquirer(_external("no_authorized_source"))
        outcome = ResearchOrchestrator(external_acquirer=acquirer).research(
            _need(sufficiency="contradictory")
        )
        assert outcome.status is ResearchStatus.NO_AUTHORIZED_SOURCE
        assert outcome.actionable is True
        assert len(acquirer.calls) == 1

    def test_missing_need_is_unknown(self):
        outcome = ResearchOrchestrator(external_acquirer=_StubAcquirer()).research(None)
        assert outcome.status is ResearchStatus.UNKNOWN
        assert outcome.established is False

    def test_no_boundary_wired_fails_closed(self):
        outcome = ResearchOrchestrator().research(_MISSING_NEED)
        assert outcome.status is ResearchStatus.FAILED
        assert outcome.actionable is False
        assert outcome.established is False

    def test_unavailable_research_capability_fails_closed(self):
        acquirer = _StubAcquirer(_external("acquired", acquisition=_Acquisition()))
        orchestrator = ResearchOrchestrator(
            external_acquirer=acquirer,
            capability_state_provider=lambda: "unavailable",
        )
        outcome = orchestrator.research(_MISSING_NEED)
        assert outcome.status is ResearchStatus.FAILED
        assert acquirer.calls == []

    def test_raising_boundary_fails_closed(self):
        outcome = ResearchOrchestrator(
            external_acquirer=_StubAcquirer(raise_error=True)
        ).research(_MISSING_NEED)
        assert outcome.status is ResearchStatus.FAILED
        assert outcome.established is False

    def test_request_formulation_is_bounded_and_passed_through(self):
        acquirer = _StubAcquirer(_external("no_authorized_source"))
        urls = tuple(f"https://example.com/{i}" for i in range(20))
        outcome = ResearchOrchestrator(external_acquirer=acquirer).research(
            _MISSING_NEED, candidate_urls=urls
        )
        assert outcome.request is not None
        assert len(outcome.request.candidate_urls) <= 8
        assert len(acquirer.calls[0][1]) <= 8

    def test_actionable_but_denied_is_reported_honestly(self):
        outcome = ResearchOrchestrator(
            external_acquirer=_StubAcquirer(
                _external("no_authorized_source", denied_sources=(_URL,))
            )
        ).research(_MISSING_NEED, candidate_urls=(_URL,))
        assert outcome.actionable is True
        assert outcome.status is ResearchStatus.NO_AUTHORIZED_SOURCE
        assert outcome.denied_sources == (_URL,)


# ---------------------------------------------------------------------------
# 3. Real governed boundary (production classes, fake transport, no network)
# ---------------------------------------------------------------------------


def _d2_harness(tmp_path, host_policy, transport):
    """The EXISTING production D2 stack over a real tmp storage + fake transport."""
    from atlas.research.acquisition import InformationAcquisitionService
    from atlas.research.coordinator import ConcreteResearchCoordinator
    from atlas.research.sources.document import DocumentSourceAdapter
    from atlas.research.sources.web import WebSourceAdapter
    from atlas.research.validated_retrieval import ValidatedKnowledgeRetriever
    from atlas.storage.research_storage import ResearchSQLiteStorage

    store = ResearchSQLiteStorage(str(tmp_path / "research.db"))
    store.initialize()
    web = WebSourceAdapter(
        transport=transport,
        host_policy=host_policy,
        resolver=lambda host: (GLOBAL_IP,),
    )

    def resolve(specs):
        out = []
        for spec in specs or ():
            if isinstance(spec, str):
                try:
                    if web.supports(spec):
                        out.append(web.load(spec))
                    elif DocumentSourceAdapter().supports(spec):
                        out.append(DocumentSourceAdapter().load(spec))
                except (ValueError, OSError):
                    continue
        return out

    coordinator = ConcreteResearchCoordinator(storage=store, resolve_sources=resolve)
    service = InformationAcquisitionService(coordinator=coordinator)
    acquirer = ExternalKnowledgeAcquirer(
        acquisition_service=service,
        validated_retriever=ValidatedKnowledgeRetriever(store),
        host_policy=host_policy,
    )
    return store, service, acquirer


def _transport(calls, body=_TEXT):
    def _handler(url, timeout, max_bytes):
        calls.append(url)
        return 200, [("Content-Type", "text/plain")], body.encode("utf-8")

    return _handler


class TestGovernedBoundary:
    def test_denied_host_fetches_nothing(self, tmp_path):
        calls: list[str] = []
        store, _, acquirer = _d2_harness(
            tmp_path, DENY_ALL_HOSTS, _transport(calls)
        )
        try:
            outcome = ResearchOrchestrator(external_acquirer=acquirer).research(
                _MISSING_NEED, candidate_urls=(_URL,)
            )
            assert outcome.status is ResearchStatus.NO_AUTHORIZED_SOURCE
            assert outcome.denied_sources == (_URL,)
            assert calls == []  # nothing was fetched
            assert outcome.established is False
        finally:
            store.close()

    def test_authorized_host_researches_and_preserves_evidence(self, tmp_path):
        calls: list[str] = []
        store, _, acquirer = _d2_harness(tmp_path, _ALLOW, _transport(calls))
        try:
            outcome = ResearchOrchestrator(external_acquirer=acquirer).research(
                _MISSING_NEED, candidate_urls=(_URL,)
            )
            assert outcome.status is ResearchStatus.RESEARCHED
            assert outcome.established is True
            assert calls == [_URL]
            assert outcome.sources == (_URL,)
            assert outcome.source_evidence[0].source_uri == _URL
            assert outcome.report_ids
        finally:
            store.close()

    def test_authorized_source_without_evidence_is_insufficient(self, tmp_path):
        calls: list[str] = []
        store, _, acquirer = _d2_harness(
            tmp_path, _ALLOW, _transport(calls, body="")
        )
        try:
            outcome = ResearchOrchestrator(external_acquirer=acquirer).research(
                _MISSING_NEED, candidate_urls=(_URL,)
            )
            assert outcome.status is ResearchStatus.INSUFFICIENT
            assert outcome.established is False
            assert outcome.claim_count == 0
        finally:
            store.close()

    def test_no_candidate_urls_is_deny_by_default(self, tmp_path):
        calls: list[str] = []
        store, _, acquirer = _d2_harness(tmp_path, _ALLOW, _transport(calls))
        try:
            outcome = ResearchOrchestrator(external_acquirer=acquirer).research(
                _MISSING_NEED
            )
            assert outcome.status is ResearchStatus.NO_AUTHORIZED_SOURCE
            assert calls == []
        finally:
            store.close()


# ---------------------------------------------------------------------------
# 4. Real Atlas/kernel validation
# ---------------------------------------------------------------------------


def _tmp_storage(monkeypatch, tmp_path):
    """Pin every kernel-owned store at ``tmp_path`` (never the operator's data)."""
    from atlas.storage.evolution_storage import SQLiteEvolutionStorage
    from atlas.storage.research_storage import ResearchSQLiteStorage

    class TmpSQLiteEvolutionStorage(SQLiteEvolutionStorage):
        def __init__(self, db_path=None):  # noqa: D107 - test shim
            super().__init__(db_path=tmp_path / "evolution.db")

    class TmpResearchSQLiteStorage(ResearchSQLiteStorage):
        def __init__(self, db_path=None):  # noqa: D107 - test shim
            super().__init__(db_path=tmp_path / "research.db")

    monkeypatch.setattr(
        "atlas.kernel.atlas.SQLiteEvolutionStorage", TmpSQLiteEvolutionStorage
    )
    monkeypatch.setattr(
        "atlas.kernel.atlas.ResearchSQLiteStorage", TmpResearchSQLiteStorage
    )


def _started_atlas(monkeypatch, tmp_path):
    _tmp_storage(monkeypatch, tmp_path)
    from atlas.kernel.atlas import Atlas

    atlas = Atlas()
    atlas.start()
    return atlas


def _adapter_factory(transport):
    from atlas.research.sources.web import WebSourceAdapter as Real

    def _factory(*, host_policy=None):
        return Real(
            transport=transport,
            host_policy=host_policy,
            resolver=lambda host: (GLOBAL_IP,),
        )

    return _factory


_QUESTION = "What is the current release of the Zorblax protocol?"


class TestRealKernel:
    def test_unseen_request_is_denied_by_default_and_fetches_nothing(
        self, monkeypatch, tmp_path
    ):
        calls: list[str] = []
        import atlas.research.capability_handlers as cap_mod
        import atlas.research.external_acquisition as ext_mod

        monkeypatch.setattr(cap_mod, "WebSourceAdapter", _adapter_factory(_transport(calls)))
        monkeypatch.setattr(ext_mod, "WebSourceAdapter", _adapter_factory(_transport(calls)))
        atlas = _started_atlas(monkeypatch, tmp_path)
        try:
            outcome = atlas.research_knowledge_need(_QUESTION, candidate_urls=[_URL])
            assert outcome.status is ResearchStatus.NO_AUTHORIZED_SOURCE
            assert outcome.actionable is True
            assert outcome.established is False
            assert outcome.denied_sources == (_URL,)
            assert calls == []  # the policy denied before any I/O
        finally:
            atlas.shutdown()

    def test_no_candidate_urls_is_deny_by_default(self, monkeypatch, tmp_path):
        atlas = _started_atlas(monkeypatch, tmp_path)
        try:
            outcome = atlas.research_knowledge_need(_QUESTION)
            assert outcome.status is ResearchStatus.NO_AUTHORIZED_SOURCE
            assert outcome.mechanism == ResearchMechanism.NONE.value
            assert outcome.established is False
        finally:
            atlas.shutdown()

    def test_existing_validated_knowledge_needs_no_research(
        self, monkeypatch, tmp_path
    ):
        atlas = _started_atlas(monkeypatch, tmp_path)
        try:
            doc = tmp_path / "guide.md"
            doc.write_text(
                "# Zorblax\n\nThe Zorblax protocol release is 7.3.\n",
                encoding="utf-8",
            )
            seeded = atlas.run_information_acquisition(
                question="zorblax protocol release", sources=[str(doc)]
            )
            assert seeded.status == "ok" and seeded.claim_count > 0
            outcome = atlas.research_knowledge_need("zorblax protocol release")
            assert outcome.status is ResearchStatus.NOT_NEEDED
            assert outcome.established is False
        finally:
            atlas.shutdown()

    def test_authorized_kernel_research_succeeds_without_network(
        self, monkeypatch, tmp_path
    ):
        from tests.safe_kernel_config import SAFE_CONFIG_TOML, bound_configuration

        cfg_dir = tmp_path / "cfg"
        cfg_dir.mkdir()
        cfg = cfg_dir / "config.toml"
        cfg.write_text(
            SAFE_CONFIG_TOML + '\n[research]\nweb_allowed_hosts = ["example.com"]\n',
            encoding="utf-8",
        )
        import atlas.kernel.atlas as kernel_mod

        monkeypatch.setattr(kernel_mod, "Configuration", bound_configuration(cfg))

        calls: list[str] = []
        import atlas.research.capability_handlers as cap_mod
        import atlas.research.external_acquisition as ext_mod

        monkeypatch.setattr(cap_mod, "WebSourceAdapter", _adapter_factory(_transport(calls)))
        monkeypatch.setattr(ext_mod, "WebSourceAdapter", _adapter_factory(_transport(calls)))

        atlas = _started_atlas(monkeypatch, tmp_path)
        try:
            outcome = atlas.research_knowledge_need(_QUESTION, candidate_urls=[_URL])
            assert outcome.status is ResearchStatus.RESEARCHED
            assert outcome.established is True
            assert outcome.mechanism == (
                ResearchMechanism.GOVERNED_EXTERNAL_ACQUISITION.value
            )
            assert calls == [_URL]  # exactly the authorized host, once
            assert outcome.sources == (_URL,)
            assert outcome.source_evidence
            assert outcome.report_ids
        finally:
            atlas.shutdown()

    def test_orchestrator_uses_the_existing_authorization_boundary(
        self, monkeypatch, tmp_path
    ):
        atlas = _started_atlas(monkeypatch, tmp_path)
        try:
            assert atlas.research_orchestrator._acquirer is atlas.external_acquisition
        finally:
            atlas.shutdown()

    def test_conversation_and_kernel_agree(self, monkeypatch, tmp_path):
        atlas = _started_atlas(monkeypatch, tmp_path)
        try:
            message = atlas.chat(_QUESTION)
            assert message.metadata["builtin_intent"] == "validated_knowledge"
            assert message.metadata["knowledge_need"]["acquisition_status"] == (
                "no_authorized_source"
            )
            outcome = atlas.research_knowledge_need(_QUESTION)
            assert outcome.status is ResearchStatus.NO_AUTHORIZED_SOURCE
        finally:
            atlas.shutdown()

    def test_no_authority_no_persistence_no_mutation(self, monkeypatch, tmp_path):
        atlas = _started_atlas(monkeypatch, tmp_path)
        try:
            before_components = atlas.component_registry.component_count
            before_knowledge = atlas.validated_knowledge("zorblax protocol release")
            outcome = atlas.research_knowledge_need(_QUESTION, candidate_urls=[_URL])
            assert outcome.status is ResearchStatus.NO_AUTHORIZED_SOURCE
            # No authority surface is touched and nothing is persisted merely
            # because research was attempted.
            payload = outcome.to_dict()
            for key in ("approval", "execution", "promotion", "authorization"):
                assert key not in payload
            assert atlas.pending_promotion_reviews() == []
            assert atlas.component_registry.component_count == before_components
            after_knowledge = atlas.validated_knowledge("zorblax protocol release")
            assert after_knowledge.status == before_knowledge.status
            assert after_knowledge.items == before_knowledge.items
        finally:
            atlas.shutdown()

    def test_steps_1_to_15_surfaces_preserved(self, monkeypatch, tmp_path):
        atlas = _started_atlas(monkeypatch, tmp_path)
        try:
            need = atlas.knowledge_need(_QUESTION)
            assert need.kind.value == "missing"
            assert atlas.chat("Which component owns memory_search?").metadata[
                "architecture"
            ]["kind"] == "ownership"
            assert atlas.chat("Is research available?").metadata[
                "builtin_intent"
            ] == "capability_state"
            assert atlas.chat("Investigate the memory architecture.").metadata.get(
                "investigation"
            ) is not None
        finally:
            atlas.shutdown()

    def test_send_stream_parity_for_research_input(self, monkeypatch, tmp_path):
        # The research seam is kernel-side; the conversation outcome for the same
        # input must be unchanged between send and stream.
        a = _started_atlas(monkeypatch, tmp_path)
        try:
            sent = a.chat(_QUESTION).content
        finally:
            a.shutdown()
        b = _started_atlas(monkeypatch, tmp_path)
        try:
            streamed = "".join(b.stream(_QUESTION))
        finally:
            b.shutdown()
        assert sent == streamed
