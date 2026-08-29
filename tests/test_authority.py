"""P1/B1.1 — Owner/User/Authority foundation tests.

Validates the explicit single-Owner, ordinary-User, authority, attribution and
audit semantics added in the authority package, plus kernel wiring and
compatibility with existing workspace/identity surfaces.
"""

from __future__ import annotations

import pytest

from atlas.authority.models import (
    AuthorityContext,
    AuthorityDecision,
    AuthorityLevel,
    Principal,
)
from atlas.authority.service import AuthorityService


class _RecordingStore:
    """Duck-typed audit store capturing ``store_record`` calls."""

    def __init__(self):
        self.records = []

    def store_record(self, record):
        self.records.append(record)


class TestAuthorityLevel:
    def test_owner_outranks_user(self):
        assert AuthorityLevel.OWNER > AuthorityLevel.USER
        assert AuthorityLevel.USER < AuthorityLevel.OWNER
        assert AuthorityLevel.OWNER >= AuthorityLevel.USER
        assert AuthorityLevel.USER <= AuthorityLevel.OWNER

    def test_reflexive(self):
        assert AuthorityLevel.OWNER >= AuthorityLevel.OWNER
        assert AuthorityLevel.USER >= AuthorityLevel.USER


class TestPrincipal:
    def test_owner_and_user_distinguishable(self):
        owner = Principal("owner", "Owner", AuthorityLevel.OWNER)
        user = Principal("u1", "Alice", AuthorityLevel.USER)
        assert owner.is_owner
        assert not user.is_owner
        assert owner.authority is not user.authority

    def test_principal_is_frozen(self):
        p = Principal("p", "n", AuthorityLevel.USER)
        with pytest.raises(Exception):
            p.authority = AuthorityLevel.OWNER  # type: ignore[misc]

    def test_to_dict_preserves_authority(self):
        p = Principal("p", "n", AuthorityLevel.OWNER)
        assert p.to_dict()["authority"] == "owner"


class TestAuthorityServiceOwner:
    def test_single_owner_is_created(self):
        service = AuthorityService("Atlas Owner")
        assert service.owner.is_owner
        assert service.owner.name == "Atlas Owner"

    def test_owner_has_highest_authority(self):
        service = AuthorityService("O")
        assert service.owner.authority is AuthorityLevel.OWNER

    def test_owner_name_must_be_non_empty(self):
        with pytest.raises(ValueError):
            AuthorityService("")
        with pytest.raises(ValueError):
            AuthorityService("   ")

    def test_owner_not_listed_as_user(self):
        service = AuthorityService("O")
        assert service.get_user("owner") is None
        assert service.resolve("owner").is_owner

    def test_no_second_owner_through_public_api(self):
        service = AuthorityService("O")
        # add_user always produces USER; there is no owner-creation API.
        user = service.add_user("Alice")
        assert user.authority is AuthorityLevel.USER
        with pytest.raises(ValueError):
            service.add_user("Bob", principal_id="owner")


class TestAuthorityServiceUsers:
    def test_add_and_resolve_user(self):
        service = AuthorityService("O")
        service.add_user("Alice", principal_id="alice")
        assert service.resolve("alice").name == "Alice"
        assert service.resolve("alice").authority is AuthorityLevel.USER

    def test_unknown_identity_resolves_none(self):
        service = AuthorityService("O")
        assert service.resolve("ghost") is None
        assert service.resolve(123) is None  # type: ignore[arg-type]

    def test_user_principal_id_defaults_to_name(self):
        service = AuthorityService("O")
        service.add_user("Alice")
        assert service.resolve("Alice") is not None


class TestAuthorityChecks:
    def _service(self):
        service = AuthorityService("O", audit_store=_RecordingStore())
        service.add_user("Alice", principal_id="alice")
        return service

    def test_owner_satisfies_owner_requirement(self):
        service = self._service()
        decision = service.assert_owner("owner")
        assert decision.allowed
        assert not decision.denied

    def test_user_cannot_satisfy_owner_requirement(self):
        service = self._service()
        decision = service.assert_owner("alice")
        assert not decision.allowed
        assert decision.required is AuthorityLevel.OWNER
        assert decision.held is AuthorityLevel.USER

    def test_unknown_identity_denied(self):
        service = self._service()
        decision = service.assert_owner("ghost")
        assert not decision.allowed

    def test_user_cannot_elevate(self):
        service = self._service()
        # Immutable authority; there is no elevation API.
        user = service.resolve("alice")
        assert user.authority is AuthorityLevel.USER

    def test_deterministic_checks(self):
        s1 = self._service()
        s2 = self._service()
        assert s1.assert_owner("owner") == s2.assert_owner("owner")
        assert s1.assert_owner("alice") == s2.assert_owner("alice")

    def test_require_owner_raises_for_user(self):
        service = self._service()
        with pytest.raises(PermissionError):
            service.require_owner("alice", action="self-elevate")
        # Owner does not raise.
        service.require_owner("owner", action="self-elevate")


class TestAttributionAndAudit:
    def test_context_attribution(self):
        service = AuthorityService("O", audit_store=_RecordingStore())
        service.add_user("Alice", principal_id="alice")
        ctx = service.context("alice", "write_file")
        assert ctx is not None
        assert ctx.principal.authority is AuthorityLevel.USER
        assert ctx.action == "write_file"
        assert ctx.satisfies(AuthorityLevel.USER)
        assert not ctx.satisfies(AuthorityLevel.OWNER)

    def test_unknown_context_is_none(self):
        service = AuthorityService("O")
        assert service.context("ghost", "x") is None

    def test_audit_recorded_for_denial(self):
        store = _RecordingStore()
        service = AuthorityService("O", audit_store=store)
        service.add_user("Alice", principal_id="alice")
        service.assert_owner("alice", action="approve")
        assert any(
            r.event_type == "authority_decision" for r in store.records
        )

    def test_audit_failure_does_not_break_decision(self):
        class BrokenStore:
            def store_record(self, record):
                raise RuntimeError("disk full")

        service = AuthorityService("O", audit_store=BrokenStore())
        decision = service.assert_owner("owner", action="x")
        assert decision.allowed

    def test_no_audit_store_is_safe(self):
        service = AuthorityService("O")
        assert service.assert_owner("owner").allowed


class TestAuthorityDecision:
    def test_decision_serialization(self):
        d = AuthorityDecision(
            allowed=False,
            required=AuthorityLevel.OWNER,
            held=AuthorityLevel.USER,
            reason="requires owner",
        )
        assert d.denied
        assert d.to_dict()["allowed"] is False


class TestKernelWiring:
    def test_authority_service_wired_and_registered(self):
        from atlas.kernel.atlas import Atlas

        atlas = Atlas()
        try:
            atlas.start()
            service = atlas.authority_service
            assert service is not None
            assert service.owner.is_owner
            assert atlas.container.get("authority") is service
        finally:
            atlas.shutdown()

    def test_authority_service_cleared_on_shutdown(self):
        from atlas.kernel.atlas import Atlas

        atlas = Atlas()
        try:
            atlas.start()
            assert atlas.authority_service is not None
        finally:
            atlas.shutdown()
        assert atlas.authority_service is None


class TestCompatibility:
    def test_workspace_member_model_unchanged(self):
        from atlas.workspace.models.member import Member

        member = Member(name="Alice")
        assert member.name == "Alice"

    def test_identity_engine_still_wired(self):
        from atlas.kernel.atlas import Atlas

        atlas = Atlas()
        try:
            atlas.start()
            assert atlas.container.get("identity") is not None
        finally:
            atlas.shutdown()
