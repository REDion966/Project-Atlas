"""P4 — Governed Collective Learning (real seams).

Covers the P4 private → candidate → governance → collective pipeline with
REAL InteractionRecorder/Repository, REAL CollectiveGovernance/Repository,
and REAL AuthorityService / ApprovalManager / EvolutionMemory seams.
Mock-only paths are never the proof of a critical candidate→collective
transition; mocks are used only at true external boundaries (never at the
governance-promotion boundary).
"""

from __future__ import annotations

import pytest

from atlas.authority.service import AuthorityService
from atlas.collective import (
    CollectiveGovernance,
    CollectiveRepository,
    CollectiveStatus,
)
from atlas.evolution.approval_manager import ApprovalManager
from atlas.evolution.evolution_memory import EvolutionMemory
from atlas.interaction import (
    InteractionRecorder,
    InteractionRepository,
)
from atlas.session.context import SessionContext
from atlas.session.manager import SessionManager


def _make_ctx(owner=False, user_id="alice", user_name="Alice"):
    authority = AuthorityService("Owner")
    manager = SessionManager(authority)
    if owner:
        session = manager.create_session("owner")
    else:
        authority.add_user(user_name, principal_id=user_id)
        session = manager.create_session(user_id)
    return authority, SessionContext.from_session(session)


# ---------------------------------------------------------------------------
# A. Private learning remains private
# ---------------------------------------------------------------------------

class TestPrivateRemainsPrivate:
    def test_private_not_visible_as_collective_without_promotion(self):
        authority = AuthorityService("Owner")
        manager = SessionManager(authority)
        authority.add_user("Alice", principal_id="alice")
        ctx = SessionContext.from_session(manager.create_session("alice"))

        irec = InteractionRecorder()
        crep = CollectiveRepository()
        gov = CollectiveGovernance(
            repository=crep,
            authority_service=authority,
            approval_manager=ApprovalManager(),
        )

        irec.record_preference(ctx, "tone", "concise")
        # No candidate exists yet — private record alone is never collective.
        assert crep.collective_count == 0
        assert gov.collective_context()["count"] == 0


# ---------------------------------------------------------------------------
# B. Candidate creation works (bounded, structured, eligible-only)
# ---------------------------------------------------------------------------

class TestCandidateCreation:
    def test_candidate_created_from_preference(self):
        authority = AuthorityService("Owner")
        manager = SessionManager(authority)
        authority.add_user("Alice", principal_id="alice")
        ctx = SessionContext.from_session(manager.create_session("alice"))
        irec = InteractionRecorder()

        pref = irec.record_preference(ctx, "response_length", "concise")
        crep = CollectiveRepository()
        gov = CollectiveGovernance(
            repository=crep,
            authority_service=authority,
            approval_manager=ApprovalManager(),
        )
        cands = gov.extract_candidates([pref])
        assert len(cands) == 1
        assert cands[0].kind.value == "preference"
        assert cands[0].status is CollectiveStatus.CANDIDATE
        assert crep.candidate_count == 1


# ---------------------------------------------------------------------------
# C. Candidate provenance preserved
# ---------------------------------------------------------------------------

class TestCandidateProvenance:
    def test_provenance_survives_candidate(self):
        authority = AuthorityService("Owner")
        manager = SessionManager(authority)
        authority.add_user("Alice", principal_id="alice")
        ctx = SessionContext.from_session(manager.create_session("alice"))
        irec = InteractionRecorder()

        rec = irec.record_correction(
            ctx, target="search", description="wrong", correction="prefer semantic"
        )
        crep = CollectiveRepository()
        gov = CollectiveGovernance(
            repository=crep,
            authority_service=authority,
            approval_manager=ApprovalManager(),
        )
        cand = gov.extract_candidates([rec])[0]
        assert cand.provenance.principal_id == "alice"
        assert cand.provenance.authority == "user"
        assert cand.provenance.session_id == ctx.session_id


# ---------------------------------------------------------------------------
# D. User cannot self-promote to trusted collective knowledge
# ---------------------------------------------------------------------------

class TestUserCannotSelfPromote:
    def test_user_approve_is_refused(self):
        authority = AuthorityService("Owner")
        manager = SessionManager(authority)
        authority.add_user("Alice", principal_id="alice")
        owner_ctx = SessionContext.from_session(manager.create_session("owner"))
        alice_ctx = SessionContext.from_session(manager.create_session("alice"))

        irec = InteractionRecorder()
        rec = irec.record_preference(alice_ctx, "tone", "helpful")

        crep = CollectiveRepository()
        approval = ApprovalManager()
        mem = EvolutionMemory()
        gov = CollectiveGovernance(
            repository=crep,
            authority_service=authority,
            approval_manager=approval,
            evolution_memory=mem,
        )
        cand = gov.extract_candidates([rec])[0]
        req = gov.create_approval_request(cand)
        assert req is not None
        # Alice (USER) cannot approve — collective stays empty.
        result = gov.approve(req, "alice")
        assert result is None
        assert crep.collective_count == 0
        assert crep.candidate_count == 1  # still pending


# ---------------------------------------------------------------------------
# E. Owner-authorized promotion works
# ---------------------------------------------------------------------------

class TestOwnerPromotion:
    def test_owner_can_approve_candidate(self):
        authority = AuthorityService("Owner")
        manager = SessionManager(authority)
        authority.add_user("Alice", principal_id="alice")
        alice_ctx = SessionContext.from_session(manager.create_session("alice"))

        irec = InteractionRecorder()
        rec = irec.record_preference(alice_ctx, "tone", "helpful")

        crep = CollectiveRepository()
        approval = ApprovalManager()
        mem = EvolutionMemory()
        gov = CollectiveGovernance(
            repository=crep,
            authority_service=authority,
            approval_manager=approval,
            evolution_memory=mem,
        )
        cand = gov.extract_candidates([rec])[0]
        req = gov.create_approval_request(cand)
        collective = gov.approve(req, "owner")
        assert collective is not None
        assert collective.status is CollectiveStatus.APPROVED
        assert crep.collective_count == 1
        assert crep.candidate_count == 0


# ---------------------------------------------------------------------------
# F. Rejected candidates do not appear as approved collective knowledge
# ---------------------------------------------------------------------------

class TestRejectedNotCollective:
    def test_rejected_candidate_never_in_collective(self):
        authority = AuthorityService("Owner")
        manager = SessionManager(authority)
        authority.add_user("Alice", principal_id="alice")
        alice_ctx = SessionContext.from_session(manager.create_session("alice"))
        irec = InteractionRecorder()
        rec = irec.record_preference(alice_ctx, "k", "v")

        crep = CollectiveRepository()
        approval = ApprovalManager()
        mem = EvolutionMemory()
        gov = CollectiveGovernance(
            repository=crep,
            authority_service=authority,
            approval_manager=approval,
            evolution_memory=mem,
        )
        cand = gov.extract_candidates([rec])[0]
        req = gov.create_approval_request(cand)
        rejected = gov.reject(req, "owner", reason="not ready")
        assert rejected is True
        assert crep.collective_count == 0
        assert crep.rejected_count == 1
        assert gov.collective_context()["count"] == 0


# ---------------------------------------------------------------------------
# G. Approved collective becomes available through advisory context
# ---------------------------------------------------------------------------

class TestApprovedCollectiveContext:
    def test_collective_context_includes_approved(self):
        authority = AuthorityService("Owner")
        manager = SessionManager(authority)
        authority.add_user("Alice", principal_id="alice")
        alice_ctx = SessionContext.from_session(manager.create_session("alice"))
        irec = InteractionRecorder()
        rec = irec.record_preference(alice_ctx, "tone", "helpful")
        crep = CollectiveRepository()
        approval = ApprovalManager()
        mem = EvolutionMemory()
        gov = CollectiveGovernance(
            repository=crep,
            authority_service=authority,
            approval_manager=approval,
            evolution_memory=mem,
        )
        cand = gov.extract_candidates([rec])[0]
        req = gov.create_approval_request(cand)
        gov.approve(req, "owner")
        ctx = gov.collective_context()
        assert ctx["count"] == 1
        assert ctx["collective"][0]["collective_key"] == "tone"


# ---------------------------------------------------------------------------
# H. Alice private data not in Bob's context
# ---------------------------------------------------------------------------

class TestCrossPrincipalIsolation:
    def test_alice_private_not_in_bob_interaction_context(self):
        authority = AuthorityService("Owner")
        manager = SessionManager(authority)
        authority.add_user("Alice", principal_id="alice")
        authority.add_user("Bob", principal_id="bob")
        alice_ctx = SessionContext.from_session(manager.create_session("alice"))

        from atlas.interaction.learning_bridge import InteractionLearningBridge

        irepo = InteractionRepository()
        irec = InteractionRecorder(repository=irepo)
        irec.record_preference(alice_ctx, "tone", "concise")

        bridge = InteractionLearningBridge(repository=irepo)
        alice_provider = bridge.planning_context_provider("alice")
        bob_provider = bridge.planning_context_provider("bob")
        alice_ctx_out = alice_provider()
        bob_ctx_out = bob_provider()
        assert len(alice_ctx_out["preferences"]) == 1
        assert len(bob_ctx_out["preferences"]) == 0
        assert bob_ctx_out["corrections"] == []

    def test_candidate_data_minimal_structured_only(self):
        # A candidate carries structured summaries, not raw text.
        authority = AuthorityService("Owner")
        manager = SessionManager(authority)
        authority.add_user("Alice", principal_id="alice")
        ctx = SessionContext.from_session(manager.create_session("alice"))
        irec = InteractionRecorder()
        rec = irec.record_correction(
            ctx, target="search", description="wrong result", correction="prefer semantic"
        )
        crep = CollectiveRepository()
        gov = CollectiveGovernance(
            repository=crep,
            authority_service=authority,
            approval_manager=ApprovalManager(),
        )
        cand = gov.extract_candidates([rec])[0]
        assert cand.key == "search"
        assert cand.value == "prefer semantic"
        assert cand.description and cand.evidence


# ---------------------------------------------------------------------------
# I. Provenance survives candidate → approval → collective record
# ---------------------------------------------------------------------------

class TestProvenanceSurvivesCollective:
    def test_provenance_survives_end_to_end(self):
        authority = AuthorityService("Owner")
        manager = SessionManager(authority)
        authority.add_user("Alice", principal_id="alice")
        ctx = SessionContext.from_session(manager.create_session("alice"))
        irec = InteractionRecorder()
        rec = irec.record_preference(ctx, "k", "v")
        crep = CollectiveRepository()
        gov = CollectiveGovernance(
            repository=crep,
            authority_service=authority,
            approval_manager=ApprovalManager(),
            evolution_memory=EvolutionMemory(),
        )
        cand = gov.extract_candidates([rec])[0]
        req = gov.create_approval_request(cand)
        coll = gov.approve(req, "owner")
        assert coll is not None
        assert coll.provenance.principal_id == "alice"
        assert coll.provenance.authority == "user"
        assert coll.provenance.session_id == ctx.session_id


# ---------------------------------------------------------------------------
# J. Repeated / duplicate candidate handling is bounded/deterministic
# ---------------------------------------------------------------------------

class TestDuplicateBounded:
    def test_duplicate_source_record_not_extracted_twice(self):
        authority = AuthorityService("Owner")
        manager = SessionManager(authority)
        authority.add_user("Alice", principal_id="alice")
        ctx = SessionContext.from_session(manager.create_session("alice"))
        irec = InteractionRecorder()
        rec = irec.record_preference(ctx, "tone", "concise")

        crep = CollectiveRepository()
        gov = CollectiveGovernance(
            repository=crep,
            authority_service=authority,
            approval_manager=ApprovalManager(),
        )
        first = gov.extract_candidates([rec])
        second = gov.extract_candidates([rec])
        assert len(first) == 1
        assert len(second) == 0
        assert crep.candidate_count == 1

    def test_duplicate_candidate_key_not_re_candidated(self):
        authority = AuthorityService("Owner")
        manager = SessionManager(authority)
        authority.add_user("Alice", principal_id="alice")
        ctx = SessionContext.from_session(manager.create_session("alice"))
        irec = InteractionRecorder()
        r1 = irec.record_preference(ctx, "tone", "concise")
        # Second record with the same key/value is deduplicated at the
        # collective-key level.
        r2 = irec.record_preference(ctx, "tone", "concise")
        crep = CollectiveRepository()
        gov = CollectiveGovernance(
            repository=crep,
            authority_service=authority,
            approval_manager=ApprovalManager(),
        )
        cands = gov.extract_candidates([r1, r2])
        assert len(cands) == 1


# ---------------------------------------------------------------------------
# K. Fail-closed on invalid/missing context
# ---------------------------------------------------------------------------

class TestFailClosed:
    def test_missing_session_returns_none(self):
        repo = InteractionRepository()
        rec = InteractionRecorder(repository=repo)
        assert rec.record_preference(None, "k", "v") is None
        assert rec.record_correction(None, "t", "d", "c") is None

    def test_empty_repository_extract_is_empty(self):
        crep = CollectiveRepository()
        gov = CollectiveGovernance(
            repository=crep,
            authority_service=AuthorityService("Owner"),
            approval_manager=ApprovalManager(),
        )
        assert gov.extract_candidates([]) == []
        assert gov.extract_candidates(None) == []

    def test_unknown_candidate_request_is_none(self):
        crep = CollectiveRepository()
        gov = CollectiveGovernance(
            repository=crep,
            authority_service=AuthorityService("Owner"),
            approval_manager=ApprovalManager(),
        )
        from atlas.collective.models import (
            CollectiveCandidate,
            CollectiveKind,
            CollectiveProvenance,
            CollectiveStatus,
        )
        fake = CollectiveCandidate(
            candidate_id="COLL-C-99999999",
            kind=CollectiveKind.PREFERENCE,
            key="k",
            value="v",
            description="x",
            evidence="x",
            provenance=CollectiveProvenance(
                principal_id="alice", authority="user"
            ),
            source_record_id="PREF-99999999",
            status=CollectiveStatus.CANDIDATE,
        )
        assert gov.create_approval_request(fake) is None


# ---------------------------------------------------------------------------
# L. Authority cannot be changed through the learning path
# ---------------------------------------------------------------------------

class TestAuthorityNotElevated:
    def test_user_record_preserves_user_authority(self):
        authority = AuthorityService("Owner")
        manager = SessionManager(authority)
        authority.add_user("Alice", principal_id="alice")
        ctx = SessionContext.from_session(manager.create_session("alice"))
        irec = InteractionRecorder()
        rec = irec.record_preference(ctx, "tone", "concise")
        assert rec.provenance.authority == "user"
        crep = CollectiveRepository()
        gov = CollectiveGovernance(
            repository=crep,
            authority_service=authority,
            approval_manager=ApprovalManager(),
        )
        cand = gov.extract_candidates([rec])[0]
        assert cand.provenance.authority == "user"
        req = gov.create_approval_request(cand)
        coll = gov.approve(req, "owner")
        assert coll is not None
        assert coll.provenance.authority == "user"  # never upgraded
        assert coll.approved_by == "owner"


# ---------------------------------------------------------------------------
# M. Collective knowledge cannot directly execute anything
# ---------------------------------------------------------------------------

class TestNonExecutableCollective:
    def test_collective_has_no_execution_references(self):
        authority = AuthorityService("Owner")
        manager = SessionManager(authority)
        authority.add_user("Alice", principal_id="alice")
        ctx = SessionContext.from_session(manager.create_session("alice"))
        irec = InteractionRecorder()
        rec = irec.record_preference(ctx, "k", "v")
        crep = CollectiveRepository()
        gov = CollectiveGovernance(
            repository=crep,
            authority_service=authority,
            approval_manager=ApprovalManager(),
            evolution_memory=EvolutionMemory(),
        )
        cand = gov.extract_candidates([rec])[0]
        req = gov.create_approval_request(cand)
        coll = gov.approve(req, "owner")
        for attr in (
            "tool_executor",
            "capability_name",
            "execution_gateway",
            "application_engine",
            "dispatcher",
            "rule_engine",
        ):
            assert not hasattr(coll, attr)
        # And collective_context is advisory dicts, not instructions.
        ctx_out = gov.collective_context()
        assert ctx_out["count"] == 1
        assert all(k.startswith("collective_") for k in ctx_out["collective"][0].keys())


# ---------------------------------------------------------------------------
# N. Existing P1/P2/P3 compatibility (schema v11)
# ---------------------------------------------------------------------------

class TestCompatibilityAndSchema:
    def test_schema_unchanged(self):
        from atlas.storage.migration import CURRENT_SCHEMA_VERSION
        assert CURRENT_SCHEMA_VERSION == 11

    def test_collective_kernel_wiring_present(self):
        from atlas.kernel.atlas import Atlas
        atlas = Atlas()
        try:
            atlas.start()
            assert atlas._collective_repository is not None
            assert atlas._collective_governance is not None
            assert "collective" not in atlas.container.names()
        finally:
            atlas.shutdown()
        assert atlas._collective_governance is None
