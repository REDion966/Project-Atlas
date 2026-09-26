"""Step 3 — final end-to-end evolution lifecycle (isolated).

ONE focused integration test representing the intended final Atlas lifecycle
through the REAL kernel and the EXISTING components only:

    user request
      -> language understanding (TaskIntake/SemanticFrame; Step 1)
      -> self-knowledge inspection (existing capability model)
      -> gap detection (existing DevelopmentDriver / assess_development_gap)
      -> research/evidence (existing bounded acquisition; stubbed here)
      -> development requirement + authoring (existing cycle/scaffold)
      -> sandbox implementation + tests (existing SelfDevelopmentLoop/CodeSandbox)
      -> verification (existing DevelopmentVerification)
      -> promotion request (existing PromotionGate)
      -> OWNER authorization (existing OWNER-gated promote path)
      -> capability activation (existing CapabilityActivator)
      -> self-knowledge refresh (existing capability/architecture model)

Everything runs against ISOLATED state: temporary storage, a temporary
promotion repository root, and a sandboxed workspace. The real production
repository is never written. Model/network independence is asserted throughout.
"""

from __future__ import annotations

import socket

import pytest

from atlas.evolution.development_envelope import (
    DevelopmentAuthority,
    DevelopmentEnvelope,
)
from atlas.evolution.development_request_scaffold import scaffold_spec_for_request
from atlas.evolution.promotion_executor import PromotionOutcome
from atlas.self_knowledge.capability_model import (
    CapabilityAvailability,
    CapabilityDependency,
)

#: A deterministically-authored capability request the governed bridge handles.
REQUEST = "add a new capability to Atlas for scheduling"


class _FakeAcquisition:
    """Duck-typed bounded research result (no network)."""

    status = "ok"

    def to_dict(self):
        return {
            "acquisition_id": "ACQ-STEP3-1",
            "status": "ok",
            "report_id": "report:step3",
            "sources": ("https://example.test/a",),
            "confidence": 0.8,
            "claim_count": 1,
        }


def _started_atlas(monkeypatch, tmp_path):
    """A real kernel with ALL storage redirected to a temp directory."""
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


def _enable_envelope(atlas, runs: int = 4) -> None:
    """OWNER-controlled bounded sandbox envelope (isolated test only)."""
    envelope = DevelopmentEnvelope(
        enabled=True, max_runs_per_window=runs, window_seconds=3600
    )
    atlas._development_envelope = envelope  # noqa: SLF001
    atlas._development_authority = DevelopmentAuthority(  # noqa: SLF001
        envelope, usage_provider=lambda: atlas._development_envelope_usage
    )


class TestFinalEvolutionLifecycle:
    def test_request_to_activated_self_knowledge(self, monkeypatch, tmp_path):
        spec = scaffold_spec_for_request(REQUEST, registered_names=())
        assert spec is not None
        capability = spec["capability_name"]
        module = spec["module"]

        repo = tmp_path / "repo"
        repo.mkdir(parents=True, exist_ok=True)

        atlas = _started_atlas(monkeypatch, tmp_path)
        atlas._promotion_repo_root = lambda: repo  # noqa: SLF001

        # --- model / network independence (deterministic-first) ---------------
        calls = {"n": 0}

        def _boom(*args, **kwargs):
            calls["n"] += 1
            raise RuntimeError("provider contacted")

        import atlas.ai.ai_service as ai_service

        monkeypatch.setattr(ai_service.AIService, "chat", _boom)
        monkeypatch.setattr(ai_service.AIService, "complete", _boom)
        monkeypatch.setattr(
            socket.socket,
            "connect",
            lambda *a, **k: (_ for _ in ()).throw(RuntimeError("network attempted")),
        )

        try:
            _enable_envelope(atlas)
            # Bounded research is stubbed (no network); the deterministic
            # pipeline is otherwise untouched.
            atlas.development_controller._researcher = (  # noqa: SLF001
                lambda **kwargs: _FakeAcquisition()
            )

            # 1-2. self-knowledge inspection BEFORE: capability absent.
            before_names = set(atlas.capability_registry.registered_names)
            assert capability not in before_names
            assert capability not in {
                e.name for e in atlas.capability_model().entries
            }

            # 3. request -> language understanding -> gap -> governed development
            message = atlas.chat(REQUEST)
            driver = dict(message.metadata or {}).get("development_driver") or {}

            # 4. sandbox implementation + focused tests + verification
            assert driver.get("terminal") == "validated", driver
            assert driver.get("verification_status") == "verified"
            assert driver.get("execution_status") == "SUCCESS"
            assert driver.get("proposal_id")
            rid = driver.get("promotion_request_id")
            assert rid

            # The bounded sandbox may run, but NOTHING is activated or written
            # into the repository before OWNER authorization.
            assert capability not in set(atlas.capability_registry.registered_names)
            assert not (repo / module).exists()

            # 5-6. promotion REQUEST -> OWNER authorization boundary
            assert tuple(atlas.pending_promotion_reviews())  # review is pending
            atlas.approve_promotion_review(atlas.session_context, rid)
            promotion = atlas.promote_validated_change(atlas.session_context, rid)

            # 7. integration: transactional promotion + bounded activation
            assert promotion.outcome is PromotionOutcome.PROMOTED
            assert promotion.activated_capabilities == (capability,)
            assert capability in set(atlas.capability_registry.registered_names)
            assert (repo / module).exists()

            # 8. self-knowledge refresh: existing models now attribute it.
            entry = next(
                (e for e in atlas.capability_model().entries if e.name == capability),
                None,
            )
            assert entry is not None
            assert entry.components  # provider component projected (Step 2)
            assert entry.dependency is CapabilityDependency.DETERMINISTIC
            assert entry.availability is CapabilityAvailability.AVAILABLE
            assert atlas.architecture_model().locate(capability).found

            # Existing registrations remain intact (no clobbering).
            assert before_names <= set(atlas.capability_registry.registered_names)

            # 9. deterministic throughout: no provider/network call.
            assert calls["n"] == 0
        finally:
            atlas.shutdown()

    def test_ambiguous_request_clarifies_instead_of_developing(
        self, monkeypatch, tmp_path
    ):
        """Fail-closed: an under-specified request never enters development."""
        atlas = _started_atlas(monkeypatch, tmp_path)
        try:
            message = atlas.chat("improve this module")
        finally:
            atlas.shutdown()
        assert "more detail" in message.content.lower()
        assert "Proposal ID:" not in message.content

    def test_unsupported_request_does_not_become_success(
        self, monkeypatch, tmp_path
    ):
        """Fail-closed: a request naming no capability is refused honestly."""
        atlas = _started_atlas(monkeypatch, tmp_path)
        try:
            atlas.development_controller._researcher = (  # noqa: SLF001
                lambda **kwargs: _FakeAcquisition()
            )
            message = atlas.chat("Can you add a new capability to Atlas?")
            driver = dict(message.metadata or {}).get("development_driver") or {}
            pending = tuple(atlas.pending_promotion_reviews())
        finally:
            atlas.shutdown()
        assert driver.get("terminal") == "author_unavailable"
        assert "Nothing is approved, executed, or promoted" in message.content
        assert pending == ()  # nothing prepared, nothing to promote

    def test_unauthorized_promotion_is_denied(self, monkeypatch, tmp_path):
        """The OWNER gate is the promotion boundary (non-OWNER is refused)."""
        pytest.importorskip("atlas.evolution.promotion_executor")
        atlas = _started_atlas(monkeypatch, tmp_path)
        try:
            _enable_envelope(atlas)
            atlas._promotion_repo_root = lambda: tmp_path / "repo"  # noqa: SLF001
            (tmp_path / "repo").mkdir(parents=True, exist_ok=True)
            atlas.development_controller._researcher = (  # noqa: SLF001
                lambda **kwargs: _FakeAcquisition()
            )
            result = atlas.run_development_driver(
                REQUEST,
                metadata={
                    "scaffold": scaffold_spec_for_request(REQUEST, registered_names=())
                },
            )
            rid = result.promotion_request_id
            assert rid
            atlas.approve_promotion_review(atlas.session_context, rid)

            atlas._authority_service.add_user("Bob", principal_id="bob")  # noqa: SLF001
            user_ctx = atlas.start_user_session("bob")
            with pytest.raises(RuntimeError):
                atlas.promote_validated_change(user_ctx, rid)
        finally:
            atlas.shutdown()
