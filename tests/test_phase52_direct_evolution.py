"""Phase 5.2 — Direct Atlas Evolution: focused + end-to-end tests.

Covers the approved Phase 5.1 Revision 3 scope:

  * separated development authorization (SANDBOX_AUTHORIZED vs APPROVED);
  * bounded Development Envelope (opt-in, quota/TTL/window, kill-switch);
  * deterministic capability/knowledge gap adjudication;
  * model-independent scaffold authoring;
  * evidence-based usefulness + retention;
  * promotion artifact capture + transactional, consistency-checked promotion;
  * the bounded DevelopmentDriver orchestration;
  * preserved CODE/autonomy/tick boundaries; model independence.
"""

from __future__ import annotations

import socket
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from atlas.evolution.development_authorization import (
    DevelopmentAuthorization,
    DevelopmentAuthorizationMode,
    build_development_authorization,
)
from atlas.evolution.development_envelope import (
    FORBIDDEN_OPERATIONS,
    SANDBOX_DEVELOPMENT,
    DevelopmentAuthority,
    DevelopmentEnvelope,
)
from atlas.evolution.development_gap import (
    DevelopmentGapKind,
    assess_development_gap,
)
from atlas.evolution.development_scaffold_supplier import ScaffoldChangeSupplier
from atlas.evolution.development_usefulness import (
    CapabilityImprovement,
    UsefulnessOutcome,
    assess_usefulness,
)
from atlas.evolution.models import ProposalStatus
from atlas.evolution.promotion_artifact import (
    PromotionArtifact,
    PromotionArtifactError,
    capture_promotion_artifact,
    hash_content,
)
from atlas.evolution.promotion_executor import (
    PromotionExecutor,
    PromotionOutcome,
)
from atlas.evolution.self_development_loop import SelfDevelopmentLoop

_REPO_ROOT = Path(__file__).resolve().parents[1]

PASS_TEST = "def test_visible():\n    assert True\n"


def _proposal(proposal_id="PROP-52", fingerprint="fp-52", benefit="a demo value"):
    return SimpleNamespace(
        proposal_id=proposal_id,
        proposal_fingerprint=fingerprint,
        expected_benefit=benefit,
        metadata={},
    )


class _FakeRetriever:
    def __init__(self, items):
        self._items = list(items)

    def retrieve(self, query):  # noqa: ARG002
        return SimpleNamespace(
            items=self._items, status=SimpleNamespace(value="ok")
        )


# ---------------------------------------------------------------------------
# 1. Authorization separation
# ---------------------------------------------------------------------------


class TestAuthorizationModel:
    def test_owner_authorization_never_expires(self):
        auth = build_development_authorization(
            _proposal(),
            mode=DevelopmentAuthorizationMode.OWNER,
            granted_at=__import__("datetime").datetime(2026, 1, 1),
        )
        assert auth.is_owner
        assert auth.expires_at is None
        assert auth.authorized_by == "user:owner"
        assert auth.is_valid_for(_proposal())

    def test_envelope_authorization_requires_ttl(self):
        with pytest.raises(ValueError):
            build_development_authorization(
                _proposal(),
                mode=DevelopmentAuthorizationMode.ENVELOPE,
                granted_at=__import__("datetime").datetime(2026, 1, 1),
                ttl_minutes=0,
            )

    def test_authorization_is_fingerprint_bound(self):
        auth = build_development_authorization(
            _proposal(fingerprint="fp-A"),
            mode=DevelopmentAuthorizationMode.ENVELOPE,
            granted_at=__import__("datetime").datetime(2099, 1, 1),
            ttl_minutes=30,
        )
        assert auth.is_valid_for(_proposal(fingerprint="fp-A"))
        assert not auth.is_valid_for(_proposal(fingerprint="fp-B"))

    def test_sandbox_authorized_status_is_distinct(self):
        assert ProposalStatus.SANDBOX_AUTHORIZED is not ProposalStatus.APPROVED

    def test_loop_accepts_sandbox_authorized(self):
        from atlas.evolution.models import (
            EvolutionProposal,
            ImprovementPlan,
            ImprovementPriority,
        )

        plan = ImprovementPlan(
            plan_id="IMP-52",
            title="t",
            description="d",
            priority=ImprovementPriority.HIGH,
            target_components=["mod"],
        )
        proposal = EvolutionProposal(
            proposal_id="PROP-52-LOOP",
            title="t",
            summary="s",
            rationale="r",
            expected_benefit="b",
            risks="low",
            impact_analysis="x",
            implementation_approach="y",
            plan=plan,
            status=ProposalStatus.SANDBOX_AUTHORIZED,
            metadata={},  # no code changes -> INVALID_OBJECTIVE, not GOVERNANCE_DENIED
        )
        result = SelfDevelopmentLoop().run(proposal, max_iterations=1)
        assert result.status.name == "INVALID_OBJECTIVE"

    def test_loop_refuses_draft(self):
        proposal = SimpleNamespace(
            proposal_id="P", status=ProposalStatus.DRAFT, metadata={}
        )
        result = SelfDevelopmentLoop().run(proposal, max_iterations=1)
        assert result.status.name == "GOVERNANCE_DENIED"


# ---------------------------------------------------------------------------
# 2. Development Envelope
# ---------------------------------------------------------------------------


class TestDevelopmentEnvelope:
    def test_disabled_by_default(self):
        authority = DevelopmentAuthority(DevelopmentEnvelope())
        assert not authority.check(SANDBOX_DEVELOPMENT).allowed
        assert authority.authorize(_proposal()) is None

    def test_disabled_config_mapping(self):
        assert DevelopmentEnvelope.from_mapping(None).enabled is False
        assert DevelopmentEnvelope.from_mapping({}).enabled is False

    def test_forbidden_operations_cannot_be_enabled(self):
        with pytest.raises(ValueError):
            DevelopmentEnvelope(allowed_operations=frozenset({"promotion"}))

    def test_enabled_authorizes_and_builds_authorization(self):
        envelope = DevelopmentEnvelope(
            enabled=True, max_runs_per_window=2, window_seconds=3600
        )
        authority = DevelopmentAuthority(envelope, usage_provider=lambda: 0)
        assert authority.check(SANDBOX_DEVELOPMENT).allowed
        auth = authority.authorize(_proposal())
        assert auth is not None
        assert auth.mode is DevelopmentAuthorizationMode.ENVELOPE
        assert auth.authorized_by == "system:development-envelope"
        assert auth.expires_at is not None

    def test_forbidden_operation_is_never_allowed(self):
        envelope = DevelopmentEnvelope(enabled=True, max_runs_per_window=2)
        authority = DevelopmentAuthority(envelope)
        assert not authority.check("promotion").allowed

    def test_quota_exhaustion_kill_switch(self):
        envelope = DevelopmentEnvelope(
            enabled=True, max_runs_per_window=1, window_seconds=3600
        )
        authority = DevelopmentAuthority(envelope, usage_provider=lambda: 1)
        assert not authority.check(SANDBOX_DEVELOPMENT).allowed

    def test_quota_requires_window(self):
        envelope = DevelopmentEnvelope(enabled=True, max_runs_per_window=5, window_seconds=None)
        assert not DevelopmentAuthority(envelope).check(SANDBOX_DEVELOPMENT).allowed

    def test_envelope_never_grants_owner_authority(self):
        envelope = DevelopmentEnvelope(enabled=True, max_runs_per_window=5)
        auth = DevelopmentAuthority(envelope).authorize(_proposal())
        assert auth is not None and not auth.is_owner


# ---------------------------------------------------------------------------
# 3. Gap adjudicator
# ---------------------------------------------------------------------------


class TestGapAdjudicator:
    def test_already_supported(self):
        gap = assess_development_gap(
            "run the research pipeline", capability_names=["research.query"]
        )
        assert gap.kind is DevelopmentGapKind.ALREADY_SUPPORTED
        assert "research.query" in gap.matched

    def test_missing_capability_when_knowledge_exists(self):
        gap = assess_development_gap(
            "add a floating widget capability",
            capability_names=["research.query"],
            knowledge_retriever=_FakeRetriever(["widget knowledge"]),
        )
        assert gap.kind is DevelopmentGapKind.MISSING_CAPABILITY

    def test_missing_knowledge_when_no_knowledge(self):
        gap = assess_development_gap(
            "add a floating widget capability",
            capability_names=["research.query"],
            knowledge_retriever=_FakeRetriever([]),
        )
        assert gap.kind is DevelopmentGapKind.MISSING_KNOWLEDGE

    def test_unclear_on_blank(self):
        assert assess_development_gap("").kind is DevelopmentGapKind.UNCLEAR
        assert assess_development_gap(None).kind is DevelopmentGapKind.UNCLEAR

    def test_deterministic(self):
        a = assess_development_gap("add widget", capability_names=["x.y"])
        b = assess_development_gap("add widget", capability_names=["x.y"])
        assert a == b


# ---------------------------------------------------------------------------
# 4. Scaffold authoring
# ---------------------------------------------------------------------------


class TestScaffoldSupplier:
    def _need(self, spec):
        return SimpleNamespace(metadata={"scaffold": spec})

    def test_authors_module_and_test(self):
        spec = {
            "module": "atlas/example/demo_handlers.py",
            "capability_name": "example.run",
        }
        supplied = ScaffoldChangeSupplier().supply_changes(self._need(spec))
        assert supplied is not None
        assert supplied.origin == "deterministic-scaffold"
        assert supplied.code_changes[0][0] == "atlas/example/demo_handlers.py"
        assert supplied.test_files[0][0] == "tests/test_demo_handlers.py"
        assert "example.run" in supplied.code_changes[0][1]

    def test_deterministic_bytes(self):
        spec = {"module": "atlas/example/demo_handlers.py", "capability_name": "example.run"}
        a = ScaffoldChangeSupplier().supply_changes(self._need(spec))
        b = ScaffoldChangeSupplier().supply_changes(self._need(spec))
        assert a == b

    def test_no_spec_returns_none(self):
        assert ScaffoldChangeSupplier().supply_changes(SimpleNamespace(metadata={})) is None

    def test_malformed_spec_fails_closed(self):
        with pytest.raises(ValueError):
            ScaffoldChangeSupplier().supply_changes(self._need({"module": "x.py"}))

    def test_path_escape_refused(self):
        with pytest.raises(ValueError):
            ScaffoldChangeSupplier().supply_changes(
                self._need({"module": "../evil.py", "capability_name": "x.y"})
            )

    def test_architecture_sensitive_module_refused(self):
        with pytest.raises(ValueError):
            ScaffoldChangeSupplier().supply_changes(
                self._need(
                    {"module": "atlas/kernel/evil.py", "capability_name": "x.y"}
                )
            )


# ---------------------------------------------------------------------------
# 5. Usefulness
# ---------------------------------------------------------------------------


class TestUsefulness:
    def test_useful_when_verified_and_capability_gained(self):
        a = assess_usefulness(
            proposal_id="P",
            objective="add X",
            verification_status="verified",
            capability_present_before=False,
            capability_present_after=True,
            regression_detected=False,
            reproducible=True,
            evidence_count=3,
        )
        assert a.outcome is UsefulnessOutcome.USEFUL
        assert a.capability_improvement is CapabilityImprovement.DEMONSTRATED
        assert a.effectiveness_score > 0.8
        assert a.evidence_summary

    def test_partial_when_regression(self):
        a = assess_usefulness(
            proposal_id="P",
            objective="add X",
            verification_status="verified",
            capability_present_before=False,
            capability_present_after=True,
            regression_detected=True,
        )
        assert a.outcome is UsefulnessOutcome.PARTIAL
        assert a.regression_risk == 1.0

    def test_inconclusive_when_unverified(self):
        a = assess_usefulness(
            proposal_id="P",
            objective="add X",
            verification_status="unverified",
            capability_present_before=False,
            capability_present_after=True,
        )
        assert a.outcome is UsefulnessOutcome.INCONCLUSIVE

    def test_deterministic(self):
        fixed = __import__("datetime").datetime(2026, 1, 1)
        kwargs = dict(
            proposal_id="P",
            objective="add X",
            verification_status="verified",
            capability_present_before=False,
            capability_present_after=True,
            evidence_count=2,
            now=fixed,
        )
        assert assess_usefulness(**kwargs) == assess_usefulness(**kwargs)


# ---------------------------------------------------------------------------
# 6. Promotion artifact + executor
# ---------------------------------------------------------------------------


def _tmp_repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    (root / "pkg").mkdir(parents=True)
    (root / "pkg" / "mod.py").write_text("VALUE = 1\n", encoding="utf-8")
    return root


class TestPromotionExecutor:
    def test_capture_records_pre_and_post_hashes(self, tmp_path):
        root = _tmp_repo(tmp_path)
        artifact = capture_promotion_artifact(
            [
                {"path": "pkg/mod.py", "content": "VALUE = 2\n"},
                {"path": "pkg/new.py", "content": "NEW = 1\n"},
            ],
            proposal_id="P",
            repo_root=root,
        )
        by_path = {e.path: e for e in artifact.files}
        assert by_path["pkg/mod.py"].pre_state == "VALUE = 1\n"
        assert by_path["pkg/mod.py"].pre_hash == hash_content("VALUE = 1\n")
        assert by_path["pkg/new.py"].is_new

    def test_capture_refuses_escape(self, tmp_path):
        root = _tmp_repo(tmp_path)
        with pytest.raises(PromotionArtifactError):
            capture_promotion_artifact(
                [{"path": "../evil.py", "content": "x"}],
                proposal_id="P",
                repo_root=root,
            )

    def test_refuses_unauthorized(self, tmp_path):
        root = _tmp_repo(tmp_path)
        artifact = capture_promotion_artifact(
            [{"path": "pkg/mod.py", "content": "VALUE = 2\n"}],
            proposal_id="P",
            repo_root=root,
        )
        result = PromotionExecutor(root).promote(artifact, authorized=False)
        assert result.outcome is PromotionOutcome.REFUSED_UNAUTHORIZED
        assert (root / "pkg" / "mod.py").read_text(encoding="utf-8") == "VALUE = 1\n"

    def test_successful_promotion(self, tmp_path):
        root = _tmp_repo(tmp_path)
        artifact = capture_promotion_artifact(
            [
                {"path": "pkg/mod.py", "content": "VALUE = 2\n"},
                {"path": "pkg/new.py", "content": "NEW = 1\n"},
            ],
            proposal_id="P",
            repo_root=root,
        )
        result = PromotionExecutor(root).promote(artifact, authorized=True)
        assert result.outcome is PromotionOutcome.PROMOTED
        assert (root / "pkg" / "mod.py").read_text(encoding="utf-8") == "VALUE = 2\n"
        assert (root / "pkg" / "new.py").read_text(encoding="utf-8") == "NEW = 1\n"

    def test_refuses_stale_pre_state(self, tmp_path):
        root = _tmp_repo(tmp_path)
        artifact = capture_promotion_artifact(
            [{"path": "pkg/mod.py", "content": "VALUE = 2\n"}],
            proposal_id="P",
            repo_root=root,
        )
        # Drift the live target after capture.
        (root / "pkg" / "mod.py").write_text("VALUE = 99\n", encoding="utf-8")
        result = PromotionExecutor(root).promote(artifact, authorized=True)
        assert result.outcome is PromotionOutcome.REFUSED_STALE
        assert (root / "pkg" / "mod.py").read_text(encoding="utf-8") == "VALUE = 99\n"

    def test_multi_file_failure_restores_entire_changeset(self, tmp_path):
        root = _tmp_repo(tmp_path)
        (root / "pkg" / "mod2.py").write_text("OTHER = 1\n", encoding="utf-8")
        artifact = capture_promotion_artifact(
            [
                {"path": "pkg/mod.py", "content": "VALUE = 2\n"},
                {"path": "pkg/mod2.py", "content": "OTHER = 2\n"},
            ],
            proposal_id="P",
            repo_root=root,
        )

        class _FailingVerify(PromotionExecutor):
            def _verify_post_state(self, art):
                return "injected verification failure"

        result = _FailingVerify(root).promote(artifact, authorized=True)
        assert result.outcome is PromotionOutcome.FAILED_ROLLED_BACK
        assert result.rollback_verified is True
        # BOTH files restored.
        assert (root / "pkg" / "mod.py").read_text(encoding="utf-8") == "VALUE = 1\n"
        assert (root / "pkg" / "mod2.py").read_text(encoding="utf-8") == "OTHER = 1\n"

    def test_rollback_unverified_fails_closed(self, tmp_path):
        root = _tmp_repo(tmp_path)
        artifact = capture_promotion_artifact(
            [{"path": "pkg/mod.py", "content": "VALUE = 2\n"}],
            proposal_id="P",
            repo_root=root,
        )

        class _BadRollback(PromotionExecutor):
            def _verify_post_state(self, art):
                return "injected verification failure"

            def _restore(self, rel_path, pre_state):
                raise RuntimeError("rollback broken")

        result = _BadRollback(root).promote(artifact, authorized=True)
        assert result.outcome is PromotionOutcome.ROLLBACK_UNVERIFIED
        assert result.rollback_verified is False

    def test_sensitive_path_refused(self, tmp_path):
        root = _tmp_repo(tmp_path)
        (root / "atlas" / "kernel").mkdir(parents=True)
        (root / "atlas" / "kernel" / "x.py").write_text("A = 1\n", encoding="utf-8")
        artifact = capture_promotion_artifact(
            [{"path": "atlas/kernel/x.py", "content": "A = 2\n"}],
            proposal_id="P",
            repo_root=root,
        )
        result = PromotionExecutor(root).promote(artifact, authorized=True)
        assert result.outcome is PromotionOutcome.REFUSED_INVALID
        assert (root / "atlas" / "kernel" / "x.py").read_text(encoding="utf-8") == "A = 1\n"


# ---------------------------------------------------------------------------
# 7. DevelopmentDriver (injected doubles)
# ---------------------------------------------------------------------------


_EVIDENCE = {"code_changes": [{"path": "x.py", "content": "X = 1\n"}]}


class TestDevelopmentDriver:
    def _driver(self, **overrides):
        from atlas.evolution.development_driver import DevelopmentDriver

        defaults = dict(
            gap_assessor=lambda request: assess_development_gap(
                request, capability_names=["existing.capability"]
            ),
            cycle_runner=lambda need: SimpleNamespace(
                ok=False, failures=(("supplier", "no changes"),), proposal_id=""
            ),
        )
        defaults.update(overrides)
        return DevelopmentDriver(**defaults)

    def test_already_supported(self):
        result = self._driver().drive("check existing.capability status")
        assert result.terminal.value == "already_supported"

    def test_author_unavailable(self):
        result = self._driver().drive("add a brand new widget", metadata=_EVIDENCE)
        assert result.terminal.value == "author_unavailable"

    def test_proposed_without_authority(self):
        driver = self._driver(
            cycle_runner=lambda need: SimpleNamespace(
                ok=True, failures=(), proposal_id="P-1", proposal=_proposal("P-1")
            )
        )
        result = driver.drive("add a brand new widget", metadata=_EVIDENCE)
        assert result.terminal.value == "proposed"
        assert result.proposal_id == "P-1"

    def test_envelope_disabled(self):
        driver = self._driver(
            cycle_runner=lambda need: SimpleNamespace(
                ok=True, failures=(), proposal_id="P-1", proposal=_proposal("P-1")
            ),
            executor=lambda proposal: None,
            authority=DevelopmentAuthority(DevelopmentEnvelope()),
        )
        result = driver.drive("add a brand new widget", metadata=_EVIDENCE)
        assert result.terminal.value == "envelope_disabled"

    def test_validated_end_to_end_with_doubles(self):
        envelope = DevelopmentEnvelope(enabled=True, max_runs_per_window=3)
        authority = DevelopmentAuthority(envelope)
        run_result = SimpleNamespace(
            status=SimpleNamespace(name="SUCCESS"),
            verification=SimpleNamespace(status=SimpleNamespace(value="verified")),
            outcomes=[1, 2],
        )
        driver = self._driver(
            cycle_runner=lambda need: SimpleNamespace(
                ok=True, failures=(), proposal_id="P-1", proposal=_proposal("P-1")
            ),
            executor=lambda proposal: run_result,
            authority=authority,
            promotion_preparer=lambda proposal, run_result: "PROMO-1",
        )
        result = driver.drive("add a brand new widget", metadata=_EVIDENCE)
        assert result.terminal.value == "validated"
        assert result.verification_status == "verified"
        assert result.promotion_request_id == "PROMO-1"
        assert result.usefulness is not None


# ---------------------------------------------------------------------------
# 8. Kernel end-to-end
# ---------------------------------------------------------------------------


def _make_atlas(tmp_path, monkeypatch):
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


def _enable_envelope(atlas, *, quota=5):
    envelope = DevelopmentEnvelope(
        enabled=True, max_runs_per_window=quota, window_seconds=3600
    )
    atlas._development_envelope = envelope
    atlas._development_authority = DevelopmentAuthority(
        envelope, usage_provider=lambda: atlas._development_envelope_usage
    )


def _drive_metadata():
    return {
        "code_changes": [{"path": "pkg/mod.py", "content": "VALUE = 2\n"}],
        "test_files": {"test_mod.py": PASS_TEST},
    }


class TestKernelE2E:
    def test_drive_then_owner_promotion(self, tmp_path, monkeypatch):
        repo = _tmp_repo(tmp_path)
        atlas = _make_atlas(tmp_path, monkeypatch)
        try:
            _enable_envelope(atlas)
            atlas._promotion_repo_root = lambda: repo

            result = atlas.run_development_driver(
                "add a demo value so that tests pass",
                metadata=_drive_metadata(),
            )
            assert result.terminal.value == "validated", result.to_dict()
            assert result.promotion_request_id
            assert result.verification_status == "verified"

            # Evidence-based usefulness is on the governed path + persisted.
            assert result.usefulness is not None
            stored = atlas._evolution_memory.get_proposal(result.proposal_id)
            assert stored.metadata["usefulness"]["outcome"] in (
                "useful", "partial", "limited", "inconclusive",
            )

            # OWNER-only promotion: approve review, then promote.
            owner = atlas.session_context
            rid = result.promotion_request_id
            atlas.approve_promotion_review(owner, rid)
            promotion = atlas.promote_validated_change(owner, rid)
            assert promotion.outcome is PromotionOutcome.PROMOTED
            assert (repo / "pkg" / "mod.py").read_text(encoding="utf-8") == "VALUE = 2\n"
        finally:
            atlas.shutdown()

    def test_stale_target_refused(self, tmp_path, monkeypatch):
        repo = _tmp_repo(tmp_path)
        atlas = _make_atlas(tmp_path, monkeypatch)
        try:
            _enable_envelope(atlas)
            atlas._promotion_repo_root = lambda: repo
            result = atlas.run_development_driver(
                "add a demo value so that tests pass", metadata=_drive_metadata()
            )
            rid = result.promotion_request_id
            atlas.approve_promotion_review(atlas.session_context, rid)
            # Drift the live target after the artifact was captured.
            (repo / "pkg" / "mod.py").write_text("VALUE = 99\n", encoding="utf-8")
            promotion = atlas.promote_validated_change(atlas.session_context, rid)
            assert promotion.outcome is PromotionOutcome.REFUSED_STALE
            assert (repo / "pkg" / "mod.py").read_text(encoding="utf-8") == "VALUE = 99\n"
        finally:
            atlas.shutdown()

    def test_non_owner_cannot_promote(self, tmp_path, monkeypatch):
        repo = _tmp_repo(tmp_path)
        atlas = _make_atlas(tmp_path, monkeypatch)
        try:
            _enable_envelope(atlas)
            atlas._promotion_repo_root = lambda: repo
            result = atlas.run_development_driver(
                "add a demo value so that tests pass", metadata=_drive_metadata()
            )
            rid = result.promotion_request_id
            atlas.approve_promotion_review(atlas.session_context, rid)

            atlas._authority_service.add_user("Alice", principal_id="alice")
            user_ctx = atlas.start_user_session("alice")
            with pytest.raises(RuntimeError):
                atlas.promote_validated_change(user_ctx, rid)
        finally:
            atlas.shutdown()

    def test_envelope_disabled_requires_owner(self, tmp_path, monkeypatch):
        repo = _tmp_repo(tmp_path)
        atlas = _make_atlas(tmp_path, monkeypatch)
        try:
            atlas._promotion_repo_root = lambda: repo  # envelope left disabled
            result = atlas.run_development_driver(
                "add a demo value so that tests pass", metadata=_drive_metadata()
            )
            assert result.terminal.value == "envelope_disabled"
        finally:
            atlas.shutdown()

    def test_proposal_never_reaches_approved_via_envelope(self, tmp_path, monkeypatch):
        repo = _tmp_repo(tmp_path)
        atlas = _make_atlas(tmp_path, monkeypatch)
        try:
            _enable_envelope(atlas)
            atlas._promotion_repo_root = lambda: repo
            result = atlas.run_development_driver(
                "add a demo value so that tests pass", metadata=_drive_metadata()
            )
            proposal = atlas._evolution_memory.get_proposal(result.proposal_id)
            # Envelope authorization must NOT be the OWNER APPROVED state.
            assert proposal.status is ProposalStatus.SANDBOX_AUTHORIZED
            assert proposal.status is not ProposalStatus.APPROVED
        finally:
            atlas.shutdown()

    def test_model_independence_with_providers_and_network_blocked(
        self, tmp_path, monkeypatch
    ):
        repo = _tmp_repo(tmp_path)
        atlas = _make_atlas(tmp_path, monkeypatch)
        calls = {"n": 0}

        def _boom(*args, **kwargs):
            calls["n"] += 1
            raise RuntimeError("provider contacted")

        import atlas.ai.ai_service as ai_service

        monkeypatch.setattr(ai_service.AIService, "chat", _boom)
        monkeypatch.setattr(ai_service.AIService, "complete", _boom)
        try:
            import atlas.ai.router.ai_router as ai_router

            monkeypatch.setattr(ai_router.AIRouter, "chat", _boom)
            monkeypatch.setattr(ai_router.AIRouter, "complete", _boom)
        except Exception:
            pass
        monkeypatch.setattr(
            socket.socket, "connect",
            lambda *a, **k: (_ for _ in ()).throw(RuntimeError("network attempted")),
        )
        try:
            _enable_envelope(atlas)
            atlas._promotion_repo_root = lambda: repo
            result = atlas.run_development_driver(
                "add a demo value so that tests pass", metadata=_drive_metadata()
            )
            assert result.terminal.value == "validated"
            assert calls["n"] == 0
        finally:
            atlas.shutdown()


# ---------------------------------------------------------------------------
# 9. Preserved boundaries
# ---------------------------------------------------------------------------


class TestBoundariesPreserved:
    def test_tick_has_no_driver_or_promotion_symbols(self):
        from atlas.kernel.atlas import Atlas
        import inspect

        src = inspect.getsource(Atlas.tick)
        for marker in (
            "run_development_driver",
            "promote_validated_change",
            "DevelopmentDriver",
            "PromotionExecutor",
        ):
            assert marker not in src, marker

    def test_execute_request_still_refuses_code(self):
        source = (_REPO_ROOT / "atlas" / "evolution" / "execution_gateway.py").read_text(
            encoding="utf-8"
        )
        assert "ScopeType.CODE" in source

    def test_new_modules_never_call_authorize_autonomously(self):
        for name in (
            "development_authorization",
            "development_envelope",
            "development_gap",
            "development_scaffold_supplier",
            "development_usefulness",
            "promotion_artifact",
            "promotion_executor",
            "development_driver",
        ):
            source = (
                _REPO_ROOT / "atlas" / "evolution" / f"{name}.py"
            ).read_text(encoding="utf-8")
            assert "authorize_autonomously(" not in source, name

    def test_promotion_does_not_route_through_application_engine(self):
        source = (
            _REPO_ROOT / "atlas" / "evolution" / "promotion_executor.py"
        ).read_text(encoding="utf-8")
        assert "ApplicationEngine" not in source
        assert "applier_registry" not in source


# ---------------------------------------------------------------------------
# 10. G-A — CODE version recording
# ---------------------------------------------------------------------------


class TestVersionManagerCodeScope:
    def test_records_a_code_scope_version(self):
        from atlas.evolution.autonomy.models import ChangeReceipt, EvolutionRequest
        from atlas.evolution.autonomy.version_manager import VersionManager
        from atlas.evolution.governance.models import ScopeType

        class _Mem:
            def __init__(self):
                self.v = None

            def store_version(self, v):
                self.v = v

            def load_latest_version(self):
                return self.v

        vm = VersionManager(storage=_Mem())
        version = vm.record_version(
            EvolutionRequest(
                request_id="R1",
                source="promotion",
                target_scope=ScopeType.CODE,
                change_payload={"code_changes": []},
            ),
            ChangeReceipt(
                request_id="R1",
                changed_keys=["pkg/mod.py"],
                after_refs={"pkg/mod.py": hash_content("VALUE = 2\n")},
                version_delta="+0.0.1",
                target_tags=["code"],
            ),
        )
        assert version.scope_versions.get("code") == "1"
        assert version.patch == 1
        assert "code" in version.tags


class TestPromotionVersionIntegration:
    def _artifact(self, root):
        return capture_promotion_artifact(
            [{"path": "pkg/mod.py", "content": "VALUE = 2\n"}],
            proposal_id="P",
            repo_root=root,
        )

    def test_successful_promotion_records_version(self, tmp_path):
        root = _tmp_repo(tmp_path)
        seen = {}

        def recorder(artifact):
            seen["called"] = True
            return "manifest-code-1"

        result = PromotionExecutor(root, version_recorder=recorder).promote(
            self._artifact(root), authorized=True
        )
        assert result.outcome is PromotionOutcome.PROMOTED
        assert result.version_id == "manifest-code-1"
        assert seen.get("called") is True

    def test_version_failure_never_reports_promoted(self, tmp_path):
        root = _tmp_repo(tmp_path)

        def failing(artifact):
            raise RuntimeError("version store down")

        result = PromotionExecutor(root, version_recorder=failing).promote(
            self._artifact(root), authorized=True
        )
        assert result.outcome is PromotionOutcome.FAILED_ROLLED_BACK
        assert result.rollback_verified is True
        assert (root / "pkg" / "mod.py").read_text(encoding="utf-8") == "VALUE = 1\n"

    def test_empty_version_id_never_reports_promoted(self, tmp_path):
        root = _tmp_repo(tmp_path)
        result = PromotionExecutor(
            root, version_recorder=lambda artifact: ""
        ).promote(self._artifact(root), authorized=True)
        assert result.outcome is PromotionOutcome.FAILED_ROLLED_BACK
        assert (root / "pkg" / "mod.py").read_text(encoding="utf-8") == "VALUE = 1\n"

    def test_other_scopes_unaffected(self, tmp_path):
        """A standalone executor (no recorder) still promotes (no regression)."""
        root = _tmp_repo(tmp_path)
        result = PromotionExecutor(root).promote(
            self._artifact(root), authorized=True
        )
        assert result.outcome is PromotionOutcome.PROMOTED


# ---------------------------------------------------------------------------
# 11. G-B — retention → planning reuse
# ---------------------------------------------------------------------------


class TestDevelopmentExperienceRetention:
    def test_verified_run_persists_development_record_and_planning_retrieves_it(
        self, tmp_path, monkeypatch
    ):
        repo = _tmp_repo(tmp_path)
        atlas = _make_atlas(tmp_path, monkeypatch)
        try:
            _enable_envelope(atlas)
            atlas._promotion_repo_root = lambda: repo

            result = atlas.run_development_driver(
                "add a demo value so that tests pass", metadata=_drive_metadata()
            )
            assert result.terminal.value == "validated"

            # G-B: a bounded "development" record carrying usefulness exists.
            records = atlas._evolution_memory.get_records_by_type("development")
            assert records
            assert any(
                (record.metadata.get("usefulness") or {}).get("outcome")
                for record in records
            )

            # …and the EXISTING planning snapshot can retrieve/use it.
            snapshot = atlas._evolution_context_snapshot()
            runs = snapshot.get("development", {}).get("recent_runs", [])
            assert runs
            assert any(run.get("usefulness_outcome") for run in runs)

            # G-A: promotion records a real CODE version produced by
            # VersionManager (manifest id) in addition to the audit record.
            rid = result.promotion_request_id
            atlas.approve_promotion_review(atlas.session_context, rid)
            promotion = atlas.promote_validated_change(atlas.session_context, rid)
            assert promotion.outcome is PromotionOutcome.PROMOTED
            assert promotion.version_id
            assert promotion.audit_id
            assert (repo / "pkg" / "mod.py").read_text(encoding="utf-8") == "VALUE = 2\n"
        finally:
            atlas.shutdown()

    def test_failed_run_records_no_development_experience(self, tmp_path, monkeypatch):
        repo = _tmp_repo(tmp_path)
        atlas = _make_atlas(tmp_path, monkeypatch)
        try:
            _enable_envelope(atlas)
            atlas._promotion_repo_root = lambda: repo
            cycle = atlas.run_development_cycle(
                __import__(
                    "atlas.evolution.development_cycle", fromlist=["DevelopmentNeed"]
                ).DevelopmentNeed(
                    title="failing change",
                    evidence_change_ids=("ev",),
                    metadata={
                        "code_changes": [{"path": "pkg/mod.py", "content": "VALUE = 2\n"}],
                        "test_files": {"test_mod.py": "def test_x():\n    assert False\n"},
                    },
                )
            )
            atlas.authorize_development_execution(cycle.proposal_id)
            run = atlas.run_development_execution(
                None, cycle.proposal_id, allow_envelope=True
            )
            assert run.status.name != "SUCCESS"
            # Unverified/failed work is NOT recorded as successful experience.
            assert atlas._evolution_memory.get_records_by_type("development") == []
        finally:
            atlas.shutdown()
