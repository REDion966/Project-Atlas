"""Step 2 — Research, capability acquisition & governed self-development.

Evidence contract for the governed capability-acquisition loop that connect the
EXISTING research, knowledge, development, sandbox, verification, promotion, and
self-knowledge infrastructure:

    request -> understand -> inspect/gap -> research/evidence -> design
            -> governed development (proposal) -> sandbox -> test -> verify
            -> OWNER authorization -> promote/activate -> self-knowledge refresh

Scenarios A–G. No provider/network is contacted anywhere in this module.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from atlas.evolution.autonomy.code_sandbox import CodeChangeSet
from atlas.evolution.capability_activation import CapabilityActivationResult
from atlas.evolution.development_cycle import DevelopmentNeed
from atlas.evolution.development_driver import (
    DevelopmentDriver,
    DevelopmentDriveTerminal,
)
from atlas.evolution.development_envelope import (
    DevelopmentAuthority,
    DevelopmentEnvelope,
)
from atlas.evolution.development_gap import (
    DevelopmentGapAssessment,
    DevelopmentGapKind,
    assess_development_gap,
)
from atlas.evolution.development_scaffold_supplier import ScaffoldChangeSupplier
from atlas.evolution.development_verification import (
    DevelopmentVerification,
    VerificationStatus,
)
from atlas.evolution.model_assisted_supplier import ModelAssistedChangeSupplier
from atlas.evolution.promotion_artifact import capture_promotion_artifact
from atlas.evolution.promotion_gate import (
    PromotionGate,
    PromotionRecommendation,
)
from atlas.self_knowledge.capability_model import (
    CapabilityAvailability,
    CapabilityDependency,
)
from atlas.orchestration.development_orchestrator import (
    DevelopmentOrchestrator,
    DevelopmentState,
)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


class _OkResult:
    status = "ok"
    items = ("claim-1",)


class _FakeRetriever:
    def retrieve(self, query):
        return _OkResult()


class _FakeAcquisition:
    status = "ok"

    def to_dict(self):
        return {
            "acquisition_id": "ACQ-STEP2-1",
            "status": "ok",
            "report_id": "report:step2",
            "sources": ("https://example.test/a",),
            "confidence": 0.8,
            "claim_count": 1,
        }


# ---------------------------------------------------------------------------
# SCENARIO A — supported / missing knowledge / missing capability / unclear
# ---------------------------------------------------------------------------


class TestScenarioAGapKinds:
    def test_already_supported(self):
        gap = assess_development_gap("memory search", capability_names=["memory_search"])
        assert gap.kind is DevelopmentGapKind.ALREADY_SUPPORTED

    def test_missing_knowledge(self):
        gap = assess_development_gap(
            "quantum stabilizer control", capability_names=["memory_search"]
        )
        assert gap.kind is DevelopmentGapKind.MISSING_KNOWLEDGE

    def test_missing_capability_when_evidence_exists(self):
        gap = assess_development_gap(
            "widget batching",
            capability_names=["memory_search"],
            knowledge_retriever=_FakeRetriever(),
        )
        assert gap.kind is DevelopmentGapKind.MISSING_CAPABILITY

    def test_unclear_fails_closed(self):
        for text in ("", "   ", None, 12345):
            assert assess_development_gap(text).kind is DevelopmentGapKind.UNCLEAR

    def test_incidental_overlap_is_not_already_supported(self):
        gap = assess_development_gap(
            "Add a capability that lets me export the conversation history "
            "as markdown.",
            capability_names=["conversation"],
        )
        assert gap.kind is not DevelopmentGapKind.ALREADY_SUPPORTED
        assert gap.matched == ()


# ---------------------------------------------------------------------------
# SCENARIO B / D — research evidence validation (raw vs trusted knowledge)
# ---------------------------------------------------------------------------


class TestScenarioBEvidenceValidation:
    def test_unvalidated_claim_does_not_become_trusted_knowledge(self, tmp_path):
        from atlas.research.models import (
            ClaimVerification,
            KnowledgeClaim,
            VerificationStatus,
        )
        from atlas.research.validated_retrieval import ValidatedKnowledgeRetriever
        from atlas.storage.research_storage import ResearchSQLiteStorage

        storage = ResearchSQLiteStorage(db_path=tmp_path / "r.db")
        storage.initialize()
        try:
            storage.store_claim(
                KnowledgeClaim(
                    claim_id="c",
                    statement="widget batching adapter already among supported",
                    confidence=0.8,
                )
            )
            # Raw/UNVERIFIED evidence must NOT confer knowledge.
            storage.store_verification(
                ClaimVerification(
                    verification_id="v-unverified",
                    claim_id="c",
                    status=VerificationStatus.UNVERIFIED,
                    score=0.2,
                )
            )
            unvalidated = assess_development_gap(
                "widget batching adapter already among",
                capability_names=["memory_search"],
                knowledge_retriever=ValidatedKnowledgeRetriever(storage),
            )
            assert unvalidated.kind is DevelopmentGapKind.MISSING_KNOWLEDGE

            # A SUPPORTED verification becomes trusted, validated knowledge.
            storage.store_verification(
                ClaimVerification(
                    verification_id="v-supported",
                    claim_id="c",
                    status=VerificationStatus.SUPPORTED,
                    score=0.9,
                )
            )
            validated = assess_development_gap(
                "widget batching adapter already among",
                capability_names=["memory_search"],
                knowledge_retriever=ValidatedKnowledgeRetriever(storage),
            )
            assert validated.kind is DevelopmentGapKind.MISSING_CAPABILITY
        finally:
            storage.close()


# ---------------------------------------------------------------------------
# SCENARIO C — evidence-informed governed development requirement
# ---------------------------------------------------------------------------


class TestScenarioCGovernedRequirement:
    def test_driver_carries_research_sources_onto_the_need(self):
        captured: dict = {}

        def cycle_runner(need):
            captured["need"] = need
            return SimpleNamespace(ok=False, failures=(("supplier", "no changes"),), proposal_id="")

        driver = DevelopmentDriver(
            gap_assessor=lambda request: DevelopmentGapAssessment(
                kind=DevelopmentGapKind.MISSING_KNOWLEDGE, rationale="knowledge missing"
            ),
            cycle_runner=cycle_runner,
            researcher=lambda **kwargs: _FakeAcquisition(),
        )
        result = driver.drive("add a widget batching capability")

        assert result.terminal is DevelopmentDriveTerminal.AUTHOR_UNAVAILABLE
        need = captured["need"]
        assert need.sources == ("https://example.test/a",)
        assert need.metadata["research"]["acquisition_id"] == "ACQ-STEP2-1"
        assert need.research_question

    def test_no_fabricated_sources_when_research_yields_none(self):
        captured: dict = {}

        def cycle_runner(need):
            captured["need"] = need
            return SimpleNamespace(ok=False, failures=(("supplier", "x"),), proposal_id="")

        class _NoSources(_FakeAcquisition):
            def to_dict(self):
                return {"acquisition_id": "A", "status": "ok"}

        driver = DevelopmentDriver(
            gap_assessor=lambda request: DevelopmentGapAssessment(
                kind=DevelopmentGapKind.MISSING_KNOWLEDGE, rationale="r"
            ),
            cycle_runner=cycle_runner,
            researcher=lambda **kwargs: _NoSources(),
        )
        driver.drive("add a widget batching capability")
        assert captured["need"].sources == ()


# ---------------------------------------------------------------------------
# SCENARIO E — governance (nothing model/research/development can self-promote)
# ---------------------------------------------------------------------------


class TestScenarioEGovernance:
    def test_envelope_can_never_authorize_promotion(self):
        with pytest.raises(ValueError):
            DevelopmentEnvelope(enabled=True, allowed_operations=frozenset({"promotion"}))
        authority = DevelopmentAuthority(
            DevelopmentEnvelope(enabled=True, max_runs_per_window=1)
        )
        assert authority.check("promotion").allowed is False
        assert authority.check("live_repository_write").allowed is False

    def test_driver_has_no_promotion_terminal(self):
        terminals = {t.value for t in DevelopmentDriveTerminal}
        assert "promoted" not in terminals
        assert not hasattr(DevelopmentDriver, "promote")

    def test_model_assisted_authoring_is_off_by_default(self):
        assert ModelAssistedChangeSupplier().supply_changes(
            DevelopmentNeed(title="t", metadata={"scaffold": {}})
        ) is None

    def test_envelope_authorizes_only_sandbox_development(self):
        # The envelope may substitute for OWNER at the bounded sandbox-execution
        # step, but it can never authorize promotion — that stays OWNER-only.
        authority = DevelopmentAuthority(
            DevelopmentEnvelope(enabled=True, max_runs_per_window=2)
        )
        sandbox = authority.check("sandbox_development")
        assert sandbox.allowed is True
        assert sandbox.requires_owner is False  # sandbox-only substitution
        assert authority.check("promotion").allowed is False
        assert authority.authorize(SimpleNamespace(proposal_id="P")) is not None


# ---------------------------------------------------------------------------
# SCENARIO F — failure never becomes a false success
# ---------------------------------------------------------------------------


class TestScenarioFFailureNoFalseSuccess:
    @staticmethod
    def _failed_run():
        outcome = SimpleNamespace(
            verification_passed=False,
            rollback_occurred=True,
            test_outcome="failed",
            changed_files=["atlas/example/x.py"],
        )
        return SimpleNamespace(
            status=SimpleNamespace(name="FAILED"),
            outcomes=[outcome],
            iterations_used=1,
            message="failed",
            plan=None,
        )

    def test_failed_run_is_unverified_and_not_promotable(self):
        run = self._failed_run()
        assert DevelopmentVerification().verify(run).status is VerificationStatus.UNVERIFIED
        assessment = PromotionGate().assess(run, proposal_id="P")
        assert assessment.recommendation is PromotionRecommendation.NOT_PROMOTABLE

    def test_orchestrator_reports_verification_failure_without_promoting(self):
        promoted: list = []

        def execution_runner(session, proposal_id):
            return self._failed_run()

        orchestrator = DevelopmentOrchestrator(
            driver=lambda objective, metadata: SimpleNamespace(proposal_id="DEV-1", terminal="proposed"),
            approval_checker=lambda proposal_id: True,  # OWNER approval present
            execution_runner=execution_runner,
            promotion_reviewer=lambda *a: SimpleNamespace(request_id="PR-1"),
            promotion_executor=lambda session, request_id: promoted.append(request_id),
            self_knowledge_refresher=lambda: {"capabilities": 1},
        )
        run = orchestrator.run("add widget batching capability")
        assert run.state in (DevelopmentState.VERIFICATION_FAILED, DevelopmentState.FAILED)
        assert run.error
        assert promoted == []  # never promoted a failed run


# ---------------------------------------------------------------------------
# SCENARIO G — activation updates the existing self-knowledge
# ---------------------------------------------------------------------------


def _started_atlas(monkeypatch, tmp_path):
    import atlas.kernel.atlas as kernel_mod
    from atlas.storage.research_storage import ResearchSQLiteStorage
    from tests.test_durable_guided_improvement import _storage_class

    monkeypatch.setattr(
        "atlas.kernel.atlas.SQLiteEvolutionStorage", _storage_class(tmp_path)
    )

    class _TmpResearch(ResearchSQLiteStorage):
        def __init__(self, db_path=None):  # noqa: D107
            super().__init__(db_path=tmp_path / "research.db")

    monkeypatch.setattr("atlas.kernel.atlas.ResearchSQLiteStorage", _TmpResearch)
    atlas = kernel_mod.Atlas()
    atlas.start()
    return atlas


class TestScenarioGActivationSelfKnowledge:
    def test_activation_projects_capability_into_self_knowledge(
        self, monkeypatch, tmp_path
    ):
        slug = "widget_batching"
        module_path = f"atlas/reasoning/execution/{slug}.py"
        spec = {
            "module": module_path,
            "capability_name": slug,
            "test_module": f"tests/test_{slug}.py",
        }
        supplied = ScaffoldChangeSupplier().supply_changes(
            DevelopmentNeed(title="t", metadata={"scaffold": spec})
        )
        assert supplied is not None
        module_content = dict(supplied.code_changes)[module_path]

        repo = tmp_path / "repo"
        target = repo / module_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(module_content, encoding="utf-8")

        artifact = capture_promotion_artifact(
            [{"path": module_path, "content": module_content}],
            proposal_id="PROP-STEP2",
            repo_root=repo,
        )

        atlas = _started_atlas(monkeypatch, tmp_path)
        atlas._promotion_repo_root = lambda: repo  # noqa: SLF001
        try:
            before = {e.name for e in atlas.capability_model().entries}
            assert slug not in before

            result = atlas._activate_promoted_capability(artifact)  # noqa: SLF001
            assert isinstance(result, CapabilityActivationResult)
            assert result.activated is True
            assert slug in result.capabilities

            # The capability is registered (existing registry)...
            assert atlas._capability_registry.has(slug)  # noqa: SLF001

            # ...AND the existing self-knowledge now attributes it honestly.
            model = atlas.capability_model()
            entry = next((e for e in model.entries if e.name == slug), None)
            assert entry is not None
            assert entry.components  # projected provider component (not UNKNOWN)
            assert entry.dependency is CapabilityDependency.DETERMINISTIC
            assert entry.availability is CapabilityAvailability.AVAILABLE

            located = atlas.architecture_model().locate(slug)
            assert located.found is True
            assert located.components  # visible via the architecture model

            providers = [
                c.name
                for c in atlas.component_registry.get_by_capability(slug)
            ]
            assert providers
        finally:
            atlas.shutdown()

    def test_self_knowledge_refresh_is_fail_soft_on_projection_error(
        self, monkeypatch, tmp_path
    ):
        atlas = _started_atlas(monkeypatch, tmp_path)
        try:
            activation = CapabilityActivationResult(
                activated=True, capabilities=("no_such_cap",)
            )
            # Artifact with no code modules: projection finds nothing, never raises.
            artifact = SimpleNamespace(files=())
            summary = atlas._refresh_self_knowledge_after_activation(  # noqa: SLF001
                artifact, activation
            )
            assert summary["projected"] == []
        finally:
            atlas.shutdown()
