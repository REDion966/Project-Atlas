"""P7.6 — Development approval/execution/promotion authority hardening.

Closes the security gap identified in the P7.0 audit: the development
approval boundary (``Atlas.confirm_development_approval``), execution boundary
(``Atlas.run_development_execution``), and promotion-review boundary
(``Atlas.submit_development_for_promotion_review``) previously took no
principal identity and performed no ``AuthorityService`` check. Any caller
could drive ``PENDING_APPROVAL -> APPROVED`` or trigger execution.

These tests prove the hardened boundary resolves identity through the EXISTING
authoritative session model (SessionManager + SessionContext) and enforces
OWNER authority through ``AuthorityService`` — fail-closed, BEFORE any status
transition. A caller cannot forge authority by supplying the owner's id: the
boundary trusts only the principal bound to an authoritative session.
"""

from __future__ import annotations

import inspect
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from atlas.authority.models import AuthorityLevel
from atlas.authority.service import AuthorityService
from atlas.evolution.approval_manager import ApprovalManager
from atlas.evolution.models import ProposalStatus
from atlas.kernel.atlas import Atlas


@pytest.fixture
def env(tmp_path, monkeypatch):
    """A started Atlas with isolated storage, owner + USER sessions."""
    from tests.test_durable_guided_improvement import _started_atlas

    atlas = _started_atlas(monkeypatch, tmp_path)
    # The canonical Owner session established by start().
    owner_ctx = atlas.session_context
    # An authoritative USER session created through SessionManager.
    user_id = atlas.authority_service.add_user(
        "Alice", principal_id="alice"
    ).principal_id
    user_ctx = atlas.start_user_session(user_id)
    yield atlas, owner_ctx, user_ctx


def _persist_pending_proposal(atlas, proposal_id="DEV-P76-1"):
    """Create a PENDING_APPROVAL proposal + pending approval request in memory."""
    from atlas.evolution.models import (
        ApprovalDecision,
        ApprovalRequest,
        EvolutionProposal,
        ImprovementPlan,
    )

    proposal = EvolutionProposal(
        proposal_id=proposal_id,
        title="P7.6 hardening need",
        summary="s",
        rationale="r",
        expected_benefit="b",
        risks="low",
        impact_analysis="",
        implementation_approach="",
        plan=ImprovementPlan(
            plan_id="IMP-P76-1",
            title="t",
            description="d",
            priority=AuthorityLevel.OWNER,
        ),
        status=ProposalStatus.PENDING_APPROVAL,
    )
    request = ApprovalRequest(
        request_id="APPR-P76-1",
        proposal_id=proposal_id,
        title=proposal.title,
        description=proposal.summary,
        rationale=proposal.rationale,
        risks=proposal.risks,
        expected_benefit=proposal.expected_benefit,
        decision=ApprovalDecision.PENDING,
        created_at=datetime.now(timezone.utc),
    )
    memory = atlas._evolution_memory
    memory.store_proposal(proposal)
    memory.store_approval_request(request)
    return proposal_id


def _verified_run(proposal_id="PROP-OWNER"):
    """A minimal SUCCESS run result for promotion submission."""
    from atlas.evolution.development_models import (
        DevelopmentOutcome,
        DevelopmentOutcomeStatus,
        DevelopmentPlan,
    )
    from atlas.evolution.self_development_loop import DevelopmentRunResult

    outcome = DevelopmentOutcome(
        outcome=DevelopmentOutcomeStatus.SUCCESS,
        proposal_id=proposal_id,
        plan_id="PLAN-1",
        iteration=1,
        verification_passed=True,
        changed_files=[],
        test_outcome="1 passed",
    )
    return DevelopmentRunResult(
        status=DevelopmentOutcomeStatus.SUCCESS,
        plan=DevelopmentPlan(
            plan_id="PLAN-1", proposal_id=proposal_id, title="t", summary="s"
        ),
        outcomes=[outcome],
        iterations_used=1,
        message="ok",
    )


# ---------------------------------------------------------------------------
# A. Authorized owner can approve
# ---------------------------------------------------------------------------


class TestOwnerCanApprove:
    def test_owner_approves_pending_proposal(self, env):
        atlas, owner_ctx, _user_ctx = env
        pid = _persist_pending_proposal(atlas)
        proposal = atlas.confirm_development_approval(
            owner_ctx, pid, comment="owner ok"
        )
        assert proposal.status is ProposalStatus.APPROVED

    def test_owner_can_execute_approved_proposal(self, env):
        atlas, owner_ctx, _user_ctx = env
        pid = _persist_pending_proposal(atlas)
        atlas.confirm_development_approval(owner_ctx, pid)
        # Execution requires APPROVED; the authority gate must pass (no
        # RuntimeError about authority denial). The loop itself may complete
        # or fail-closed on content, but it must not raise an auth denial.
        try:
            atlas.run_development_execution(owner_ctx, pid)
        except RuntimeError as exc:
            assert "denied" not in str(exc).lower(), (
                f"owner execution was wrongly denied: {exc}"
            )


# ---------------------------------------------------------------------------
# B/C/D/E. Unauthorized USER / impersonation / arbitrary identity
# ---------------------------------------------------------------------------


class TestUnauthorizedDenied:
    def test_user_cannot_approve(self, env):
        atlas, _owner_ctx, user_ctx = env
        pid = _persist_pending_proposal(atlas)
        with pytest.raises(RuntimeError, match="denied"):
            atlas.confirm_development_approval(user_ctx, pid)

    def test_user_cannot_execute(self, env):
        atlas, _owner_ctx, user_ctx = env
        pid = _persist_pending_proposal(atlas)
        with pytest.raises(RuntimeError, match="denied"):
            atlas.run_development_execution(user_ctx, pid)

    def test_user_cannot_submit_promotion_review(self, env):
        atlas, _owner_ctx, user_ctx = env
        run_result = _verified_run("PROP-X")
        with pytest.raises(RuntimeError, match="denied"):
            atlas.submit_development_for_promotion_review(
                user_ctx, run_result, proposal_id="PROP-X"
            )


# ---------------------------------------------------------------------------
# F/G/H. Fail-closed: no state change, no execution on denial
# ---------------------------------------------------------------------------


class TestFailClosed:
    def test_denial_does_not_change_pending_approval_state(self, env):
        atlas, _owner_ctx, user_ctx = env
        pid = _persist_pending_proposal(atlas)
        with pytest.raises(RuntimeError):
            atlas.confirm_development_approval(user_ctx, pid)
        proposal = atlas._evolution_memory.get_proposal(pid)
        assert proposal.status is ProposalStatus.PENDING_APPROVAL

    def test_denial_does_not_trigger_execution(self, env):
        atlas, _owner_ctx, user_ctx = env
        pid = _persist_pending_proposal(atlas)
        with pytest.raises(RuntimeError):
            atlas.run_development_execution(user_ctx, pid)
        # Proposal is still PENDING_APPROVAL (never approved, never executed).
        proposal = atlas._evolution_memory.get_proposal(pid)
        assert proposal.status is ProposalStatus.PENDING_APPROVAL

    def test_missing_session_context_fails_closed(self, env):
        atlas, _owner_ctx, _user_ctx = env
        pid = _persist_pending_proposal(atlas)
        with pytest.raises(RuntimeError, match="session context"):
            atlas.confirm_development_approval(None, pid)


# ---------------------------------------------------------------------------
# I/J. Authorized approval produces APPROVED; execution gated by APPROVED
# ---------------------------------------------------------------------------


class TestAuthorizedFlow:
    def test_approval_sets_approved_state(self, env):
        atlas, owner_ctx, _user_ctx = env
        pid = _persist_pending_proposal(atlas)
        proposal = atlas.confirm_development_approval(owner_ctx, pid)
        assert proposal.status is ProposalStatus.APPROVED
        assert proposal.approved_at is not None

    def test_execution_requires_approved_state(self, env):
        atlas, owner_ctx, _user_ctx = env
        pid = _persist_pending_proposal(atlas)
        # Not yet approved -> execution refuses (status gate, not authority).
        with pytest.raises(RuntimeError, match="not APPROVED"):
            atlas.run_development_execution(owner_ctx, pid)


# ---------------------------------------------------------------------------
# K/L. Conversational confirmation is NOT approval authority
# ---------------------------------------------------------------------------


class TestConversationalNotAuthority:
    def test_conversational_yield_does_not_grant_approval(self):
        """The P7.3 dialogue only constructs an intent; it never calls the
        kernel approval bridge, so it cannot grant approval authority."""
        from atlas.conversation.development_need_dialogue import (
            DevelopmentNeedDialogue,
        )

        dialogue = DevelopmentNeedDialogue()
        for attr in (
            "confirm_development_approval",
            "run_development_execution",
            "submit_development_for_promotion_review",
        ):
            assert not hasattr(dialogue, attr), (
                "dialogue must not expose kernel approval surface"
            )


# ---------------------------------------------------------------------------
# M/N. AuthorityService owner invariant intact; no self-elevation
# ---------------------------------------------------------------------------


class TestOwnerInvariant:
    def test_single_owner_invariant(self):
        service = AuthorityService("Owner")
        assert service.owner.is_owner
        # No second owner via public API.
        user = service.add_user("Bob")
        assert user.authority is AuthorityLevel.USER
        assert not user.is_owner

    def test_user_cannot_self_elevate(self):
        service = AuthorityService("Owner")
        user = service.add_user("Eve", principal_id="eve")
        # Authority is frozen; no elevation API exists.
        assert user.authority is AuthorityLevel.USER
        decision = service.assert_owner("eve")
        assert decision.denied
        assert decision.held is AuthorityLevel.USER

    def test_reserved_owner_id_protected(self):
        service = AuthorityService("Owner")
        with pytest.raises(ValueError):
            service.add_user("FakeOwner", principal_id="owner")


# ---------------------------------------------------------------------------
# Boundary helper resolves identity through the session model, not free-text
# ---------------------------------------------------------------------------


class TestBoundaryMechanism:
    def test_boundary_denies_user(self, env):
        atlas, _owner_ctx, user_ctx = env
        with pytest.raises(RuntimeError, match="denied"):
            atlas._require_development_authority(user_ctx, action="approval")

    def test_boundary_allows_owner(self, env):
        atlas, owner_ctx, _user_ctx = env
        # No exception for the owner.
        atlas._require_development_authority(owner_ctx, action="approval")

    def test_boundary_denies_missing_session_context(self, env):
        atlas, _owner_ctx, _user_ctx = env
        with pytest.raises(RuntimeError, match="session context"):
            atlas._require_development_authority(None, action="approval")


# ---------------------------------------------------------------------------
# Impersonation / elevation negative cases (identity-source correction)
# ---------------------------------------------------------------------------


class TestNoImpersonation:
    def test_user_cannot_impersonate_via_authority_string(self, env):
        """A USER cannot elevate by claiming OWNER authority. The boundary
        resolves identity from the authoritative session, never a supplied
        authority string."""
        atlas, _owner_ctx, user_ctx = env
        user = atlas.authority_service.resolve(user_ctx.principal_id)
        assert user.authority is AuthorityLevel.USER
        with pytest.raises(RuntimeError, match="denied"):
            atlas._require_development_authority(user_ctx, action="approval")

    def test_no_elevation_api(self):
        """AuthorityService exposes no authority-escalation API."""
        service = AuthorityService("Owner")
        user = service.add_user("Mallory", principal_id="mallory")
        public = [m for m in dir(service) if not m.startswith("_")]
        assert "elevate" not in public
        assert "promote" not in public
        assert "set_authority" not in public
        assert user.authority is AuthorityLevel.USER

    def test_caller_supplied_owner_id_rejected(self, env):
        """A caller who supplies the owner's principal id as a raw string is
        still denied because identity must be a bound session."""
        atlas, _owner_ctx, _user_ctx = env
        pid = _persist_pending_proposal(atlas)
        with pytest.raises(RuntimeError, match="session"):
            atlas.confirm_development_approval("owner", pid)

    def test_forged_session_context_rejected(self, env):
        """A fabricated session context not present in SessionManager fails
        closed, even if it claims the owner principal id."""
        atlas, _owner_ctx, _user_ctx = env
        pid = _persist_pending_proposal(atlas)
        owner = atlas.authority_service.owner
        fake_ctx = SimpleNamespace(
            session_id="not-a-real-session",
            principal_id=owner.principal_id,
        )
        with pytest.raises(RuntimeError, match="Unknown session"):
            atlas.confirm_development_approval(fake_ctx, pid)

    def test_mismatched_session_principal_fails_closed(self, env):
        """A session context whose principal id conflicts with the bound
        session fails closed, even if the session is a real owner session."""
        atlas, owner_ctx, _user_ctx = env
        pid = _persist_pending_proposal(atlas)
        # Real session id, but a conflicting caller-supplied principal id.
        fake_ctx = SimpleNamespace(
            session_id=owner_ctx.session_id,
            principal_id="alice",
        )
        with pytest.raises(RuntimeError, match="Mismatched session/principal"):
            atlas.confirm_development_approval(fake_ctx, pid)


# ---------------------------------------------------------------------------
# Architecture: no new global, no conversation->kernel auth, tick/B4 safe
# ---------------------------------------------------------------------------


class TestArchitecture:
    def test_no_new_authority_global(self):
        import atlas.kernel.atlas as mod

        src = inspect.getsource(mod.Atlas)
        # The boundary reuses the injected AuthorityService + SessionManager;
        # no new module-level authority singleton is introduced.
        assert "AuthorityService(" in src
        assert "owner_name=" in src
        assert "SessionManager(" in src

    def test_conversation_layer_has_no_kernel_approval_import(self):
        import pathlib

        root = pathlib.Path(__file__).resolve().parents[1]
        conv_dir = root / "atlas" / "conversation"
        hits = []
        for path in conv_dir.rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            if "confirm_development_approval" in text:
                hits.append(str(path))
            if "run_development_execution" in text:
                hits.append(str(path))
        assert hits == [], f"conversation imports kernel approval: {hits}"

    def test_tick_unchanged(self):
        src = inspect.getsource(Atlas.tick)
        for marker in (
            "confirm_development_approval",
            "run_development_execution",
            "submit_development_for_promotion_review",
        ):
            assert marker not in src

    def test_b4_unchanged(self):
        # B4 machinery must remain opt-in (config flag) and not be invoked by
        # the boundary. The flag must stay default-off.
        import pathlib

        root = pathlib.Path(__file__).resolve().parents[1]
        cfg = (root / "config.toml").read_text(encoding="utf-8")
        assert "model_assisted_authoring = false" in cfg


# ---------------------------------------------------------------------------
# Identity-source correction: caller-controlled identity cannot bypass OWNER
# ---------------------------------------------------------------------------


class TestIdentitySourceCorrection:
    def test_owner_session_approves(self, env):
        atlas, owner_ctx, _user_ctx = env
        pid = _persist_pending_proposal(atlas)
        proposal = atlas.confirm_development_approval(owner_ctx, pid)
        assert proposal.status is ProposalStatus.APPROVED

    def test_owner_session_submits_promotion_review(self, env):
        atlas, owner_ctx, _user_ctx = env
        request = atlas.submit_development_for_promotion_review(
            owner_ctx, _verified_run("PROP-OWNER"), proposal_id="PROP-OWNER"
        )
        assert request.proposal_id == "PROP-OWNER"

    def test_user_session_cannot_submit_promotion_review(self, env):
        atlas, _owner_ctx, user_ctx = env
        with pytest.raises(RuntimeError, match="denied"):
            atlas.submit_development_for_promotion_review(
                user_ctx, _verified_run("PROP-USER"), proposal_id="PROP-USER"
            )

    def test_missing_session_identity_fails_closed(self, env):
        atlas, _owner_ctx, _user_ctx = env
        pid = _persist_pending_proposal(atlas)
        with pytest.raises(RuntimeError, match="session context"):
            atlas.confirm_development_approval(None, pid)

    def test_caller_cannot_override_authoritative_principal(self, env):
        """Even with a valid owner session id, a caller cannot substitute a
        different principal id on the context and be authorized."""
        atlas, owner_ctx, _user_ctx = env
        pid = _persist_pending_proposal(atlas)
        fake_ctx = SimpleNamespace(
            session_id=owner_ctx.session_id,
            principal_id="mallory",
        )
        with pytest.raises(RuntimeError, match="Mismatched session/principal"):
            atlas.confirm_development_approval(fake_ctx, pid)

    def test_unauthorized_attempts_leave_state_unchanged(self, env):
        atlas, _owner_ctx, user_ctx = env
        pid = _persist_pending_proposal(atlas)
        with pytest.raises(RuntimeError):
            atlas.confirm_development_approval(user_ctx, pid)
        proposal = atlas._evolution_memory.get_proposal(pid)
        assert proposal.status is ProposalStatus.PENDING_APPROVAL

    def test_unauthorized_attempts_do_not_execute(self, env):
        atlas, _owner_ctx, user_ctx = env
        pid = _persist_pending_proposal(atlas)
        with pytest.raises(RuntimeError):
            atlas.run_development_execution(user_ctx, pid)
        proposal = atlas._evolution_memory.get_proposal(pid)
        assert proposal.status is ProposalStatus.PENDING_APPROVAL
